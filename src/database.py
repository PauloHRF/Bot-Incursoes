"""Camada de persistencia (SQLite via aiosqlite)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

import aiosqlite

from . import config
from .rules import normalizar_lista_pericias, normalizar_pericia

# sigla do atributo -> coluna no banco
COLUNAS_EDITAVEIS = {"nome", "nivel", "classe", "pericias", "imagem"}

SCHEMA = """
-- Um jogador pode ter varios personagens; escolhe qual usar ao entrar na run.
-- Os numeros de combate nao ficam aqui: saem da tabela da classe no tier atual
-- (src/classes.py) e sao acrescentados na leitura, em _desserializar.
CREATE TABLE IF NOT EXISTS personagens (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id       INTEGER NOT NULL,
    user_id        INTEGER NOT NULL,
    nome           TEXT    NOT NULL,
    classe         TEXT    NOT NULL,
    nivel          INTEGER NOT NULL DEFAULT 1,
    pericias       TEXT    NOT NULL DEFAULT '[]',
    bonus_pericias TEXT    NOT NULL DEFAULT '{}',
    imagem         TEXT,
    criado_em      TEXT    NOT NULL DEFAULT (datetime('now')),
    atualizado_em  TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Dois personagens do mesmo jogador nao podem ter o mesmo nome.
CREATE UNIQUE INDEX IF NOT EXISTS idx_personagem_nome
    ON personagens (guild_id, user_id, nome);

-- O intervalo entre incursoes e do jogador, nao do personagem.
CREATE TABLE IF NOT EXISTS jogadores (
    guild_id        INTEGER NOT NULL,
    user_id         INTEGER NOT NULL,
    ultima_incursao TEXT,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id      INTEGER NOT NULL,
    canal_id      INTEGER NOT NULL,
    incursao_id   TEXT    NOT NULL,
    criador_id    INTEGER NOT NULL,
    status        TEXT    NOT NULL,
    linha_atual   INTEGER NOT NULL DEFAULT 0,
    sala_atual    TEXT,
    mensagem_id   INTEGER,
    votacao_expira_em TEXT,
    criada_em     TEXT NOT NULL DEFAULT (datetime('now')),
    atualizada_em TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS run_participantes (
    run_id        INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    user_id       INTEGER NOT NULL,
    personagem_id INTEGER REFERENCES personagens(id) ON DELETE SET NULL,
    hp_atual      INTEGER,
    PRIMARY KEY (run_id, user_id)
);

-- Chaveado por passo, nao por sala: a mesma sala pode ser sorteada duas vezes
-- na mesma run, e cada visita e um desafio novo.
CREATE TABLE IF NOT EXISTS run_testes (
    run_id      INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    passo       INTEGER NOT NULL,
    sala_id     TEXT    NOT NULL,
    user_id     INTEGER NOT NULL,
    personagem  TEXT    NOT NULL,
    pericia     TEXT    NOT NULL,
    d20         INTEGER NOT NULL,
    modificador INTEGER NOT NULL,
    cd          INTEGER NOT NULL,
    criado_em   TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (run_id, passo, user_id)
);

CREATE TABLE IF NOT EXISTS run_votos (
    run_id    INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    linha     INTEGER NOT NULL,
    user_id   INTEGER NOT NULL,
    opcao     TEXT    NOT NULL,
    criado_em TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (run_id, linha, user_id)
);

-- O caminho sorteado para a run: por passo, as salas oferecidas na votacao.
CREATE TABLE IF NOT EXISTS run_mapa (
    run_id  INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    passo   INTEGER NOT NULL,
    posicao INTEGER NOT NULL,
    sala_id TEXT    NOT NULL,
    PRIMARY KEY (run_id, passo, posicao)
);

-- A sala que o grupo escolheu em cada passo: o sorteio nunca reoferece uma delas.
CREATE TABLE IF NOT EXISTS run_salas (
    run_id  INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    passo   INTEGER NOT NULL,
    sala_id TEXT    NOT NULL,
    PRIMARY KEY (run_id, passo)
);

CREATE TABLE IF NOT EXISTS run_combate (
    run_id  INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    passo   INTEGER NOT NULL,
    sala_id TEXT    NOT NULL,
    rodada  INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (run_id, passo)
);

-- Uma sala de combate pode ter varias criaturas, cada uma com o proprio HP.
CREATE TABLE IF NOT EXISTS run_inimigos (
    run_id   INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    passo    INTEGER NOT NULL,
    indice   INTEGER NOT NULL,
    nome     TEXT    NOT NULL,
    ca       INTEGER NOT NULL,
    ataque   INTEGER NOT NULL,
    dano     TEXT    NOT NULL,
    hp_max   INTEGER NOT NULL,
    hp_atual INTEGER NOT NULL,
    PRIMARY KEY (run_id, passo, indice)
);

CREATE TABLE IF NOT EXISTS run_ataques (
    run_id  INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    passo   INTEGER NOT NULL,
    rodada  INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    d20     INTEGER NOT NULL,
    bonus   INTEGER NOT NULL,
    ca_alvo INTEGER NOT NULL,
    dano    INTEGER NOT NULL,
    alvo    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (run_id, passo, rodada, user_id)
);

CREATE TABLE IF NOT EXISTS placar_organizacoes (
    guild_id    INTEGER NOT NULL,
    organizacao TEXT    NOT NULL,
    pontos      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, organizacao)
);

CREATE TABLE IF NOT EXISTS pontos_lancamentos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    INTEGER NOT NULL,
    organizacao TEXT    NOT NULL,
    run_id      INTEGER REFERENCES runs(id) ON DELETE SET NULL,
    chave       TEXT,
    motivo      TEXT    NOT NULL,
    pontos      INTEGER NOT NULL,
    criado_em   TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- O mesmo motivo nunca e lancado duas vezes na mesma run.
CREATE UNIQUE INDEX IF NOT EXISTS idx_lancamento_unico
    ON pontos_lancamentos (run_id, chave)
    WHERE run_id IS NOT NULL AND chave IS NOT NULL;

CREATE TABLE IF NOT EXISTS config_guilda (
    guild_id          INTEGER PRIMARY KEY,
    intervalo_semanas INTEGER NOT NULL
);

-- Um canal so pode ter uma run viva por vez.
CREATE UNIQUE INDEX IF NOT EXISTS idx_run_viva_por_canal
    ON runs (canal_id) WHERE status IN ('recrutando', 'escolhendo', 'em_sala', 'objetivo');
"""


async def conectar() -> aiosqlite.Connection:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(config.DB_PATH)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys = ON")
    return conn


async def _tabela_existe(conn: aiosqlite.Connection, tabela: str) -> bool:
    async with conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (tabela,)
    ) as cur:
        return await cur.fetchone() is not None


async def _colunas(conn: aiosqlite.Connection, tabela: str) -> set[str]:
    async with conn.execute(f"PRAGMA table_info({tabela})") as cur:
        return {r["name"] for r in await cur.fetchall()}


async def criar_schema(conn: aiosqlite.Connection) -> None:
    """Cria o schema e migra bancos da versao de um personagem por jogador."""
    # A ficha passou a ser por classe: os numeros saem da tabela da classe e nao
    # ha como adivinhar a classe de um personagem antigo, que tinha atributos
    # digitados a mao. As fichas antigas sao apagadas e o grupo recadastra.
    limpando_fichas = await _tabela_existe(conn, "personagens") and (
        "classe" not in await _colunas(conn, "personagens")
    )
    if limpando_fichas:
        await conn.execute("DROP TABLE personagens")
        await conn.execute("DROP TABLE IF EXISTS personagens_v1")

    faltava_run_salas = not await _tabela_existe(conn, "run_salas")

    # O combate de uma criatura so guardava o HP na propria run_combate, e nao
    # guardava CA, ataque nem dano: nao da para remontar um combate em andamento
    # com varias criaturas a partir dele.
    migrando_combate = await _tabela_existe(conn, "run_combate") and (
        "monstro_hp" in await _colunas(conn, "run_combate")
    )
    if migrando_combate:
        await conn.execute("DROP TABLE run_combate")

    # O intervalo passou de dias corridos para semanas com virada na segunda.
    migrando_intervalo = await _tabela_existe(
        conn, "config_guilda"
    ) and "intervalo_semanas" not in await _colunas(conn, "config_guilda")
    if migrando_intervalo:
        await conn.execute("ALTER TABLE config_guilda RENAME TO config_guilda_v1")

    await conn.executescript(SCHEMA)

    if migrando_intervalo:
        # 7 dias viram 1 semana, 14 viram 2; o 0 do playtest continua sendo 0.
        await conn.execute(
            "INSERT INTO config_guilda (guild_id, intervalo_semanas)"
            " SELECT guild_id, CASE WHEN intervalo_dias <= 0 THEN 0"
            "   ELSE MAX(1, (intervalo_dias + 6) / 7) END"
            " FROM config_guilda_v1"
        )
        await conn.execute("DROP TABLE config_guilda_v1")

    if limpando_fichas:
        # Sem fichas, nao ha run viva que sobreviva: todas sao encerradas.
        await conn.execute(
            "UPDATE runs SET status = 'desistiu'"
            " WHERE status IN ('recrutando', 'escolhendo', 'em_sala', 'objetivo')"
        )
        await conn.execute("DELETE FROM run_participantes")

    # Bancos anteriores nao tinham com qual personagem a pessoa entrou na run.
    if "personagem_id" not in await _colunas(conn, "run_participantes"):
        await conn.execute("ALTER TABLE run_participantes ADD COLUMN personagem_id INTEGER")

    # O caminho sorteado mudou o modelo: o estado de sala passou a ser por passo.
    # Runs da versao anterior nao tem mapa gravado, entao sao encerradas.
    if await _tabela_existe(conn, "run_testes") and "passo" not in await _colunas(
        conn, "run_testes"
    ):
        await conn.execute(
            "UPDATE runs SET status = 'desistiu'"
            " WHERE status IN ('recrutando', 'escolhendo', 'em_sala', 'objetivo')"
        )
        for tabela in ("run_testes", "run_combate", "run_ataques"):
            await conn.execute(f"DROP TABLE IF EXISTS {tabela}")
        await conn.executescript(SCHEMA)

    if migrando_combate:
        # Runs paradas num combate do modelo antigo sao encerradas, em vez de
        # voltarem com um inimigo inventado.
        await conn.execute(
            "UPDATE runs SET status = 'desistiu'"
            " WHERE status IN ('recrutando', 'escolhendo', 'em_sala', 'objetivo')"
        )
        await conn.execute("DELETE FROM run_ataques")

    # O log de ataque nao dizia em qual criatura o golpe caiu.
    if "alvo" not in await _colunas(conn, "run_ataques"):
        await conn.execute("ALTER TABLE run_ataques ADD COLUMN alvo INTEGER NOT NULL DEFAULT 0")

    if faltava_run_salas:
        # Runs em andamento nao guardavam por onde o grupo passou. Reconstroi o
        # historico do que da para saber: salas com rolagem ou com combate.
        for tabela in ("run_combate", "run_testes"):
            if await _tabela_existe(conn, tabela):
                await conn.execute(
                    "INSERT OR IGNORE INTO run_salas (run_id, passo, sala_id)"
                    f" SELECT DISTINCT run_id, passo, sala_id FROM {tabela}"
                )

    await conn.commit()


def _normalizar_bonus(bruto: dict[str, Any]) -> dict[str, int]:
    """Aceita a grafia sem acento e descarta pericia desconhecida ou bonus zero."""
    saida: dict[str, int] = {}
    for nome, valor in (bruto or {}).items():
        canonico = normalizar_pericia(str(nome))
        try:
            numero = int(valor)
        except (TypeError, ValueError):
            continue
        if canonico and numero:
            saida[canonico] = numero
    return saida


def _desserializar(row: aiosqlite.Row) -> dict[str, Any]:
    """A ficha como o resto do bot a lê: o gravado mais os números da classe.

    CA, acerto, dano e HP máximo não são gravados — mudam sozinhos quando o
    personagem sobe de tier, e derivar na leitura evita ficha desatualizada.
    """
    from . import classes  # aqui dentro: classes importa rules, nao database

    p = dict(row)
    # Normaliza fichas gravadas antes dos nomes de pericia ganharem acento.
    p["pericias"] = normalizar_lista_pericias(json.loads(p["pericias"]))
    p["bonus_pericias"] = _normalizar_bonus(json.loads(p.get("bonus_pericias") or "{}"))
    numeros = classes.numeros(p.get("classe"), p["nivel"])
    if numeros:
        p["numeros"] = numeros
        p["ca"] = numeros.ca
        p["bonus_ataque"] = numeros.acerto
        p["dano_arma"] = numeros.dano
        p["hp_max"] = numeros.hp
        p["pericias_permitidas"] = numeros.pericias
    return p


async def criar_personagem(
    conn: aiosqlite.Connection,
    guild_id: int,
    user_id: int,
    nome: str,
    classe: str,
    pericias: list[str],
    nivel: int = 1,
    bonus_pericias: Optional[dict[str, int]] = None,
    imagem: Optional[str] = None,
) -> Optional[int]:
    """Cria um personagem. Devolve None se o jogador ja tem outro com esse nome."""
    try:
        cur = await conn.execute(
            "INSERT INTO personagens"
            " (guild_id, user_id, nome, classe, nivel, pericias, bonus_pericias, imagem)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                guild_id, user_id, nome.strip(), classe, nivel,
                json.dumps(normalizar_lista_pericias(pericias), ensure_ascii=False),
                json.dumps(_normalizar_bonus(bonus_pericias or {}), ensure_ascii=False),
                imagem or None,
            ),
        )
    except aiosqlite.IntegrityError:
        return None
    await conn.commit()
    return cur.lastrowid


async def buscar_personagem(
    conn: aiosqlite.Connection, personagem_id: int
) -> Optional[dict[str, Any]]:
    async with conn.execute("SELECT * FROM personagens WHERE id = ?", (personagem_id,)) as cur:
        row = await cur.fetchone()
    return _desserializar(row) if row else None


async def listar_personagens(
    conn: aiosqlite.Connection, guild_id: int, user_id: int
) -> list[dict[str, Any]]:
    async with conn.execute(
        "SELECT * FROM personagens WHERE guild_id = ? AND user_id = ? ORDER BY nome",
        (guild_id, user_id),
    ) as cur:
        return [_desserializar(r) for r in await cur.fetchall()]


async def personagem_por_nome(
    conn: aiosqlite.Connection, guild_id: int, user_id: int, nome: str
) -> Optional[dict[str, Any]]:
    async with conn.execute(
        "SELECT * FROM personagens WHERE guild_id = ? AND user_id = ?"
        " AND nome = ? COLLATE NOCASE",
        (guild_id, user_id, nome.strip()),
    ) as cur:
        row = await cur.fetchone()
    return _desserializar(row) if row else None


async def atualizar_personagem(
    conn: aiosqlite.Connection, personagem_id: int, coluna: str, valor: Any
) -> bool:
    """Atualiza uma coluna. `coluna` nunca vem direto do usuario."""
    if coluna not in COLUNAS_EDITAVEIS:
        raise ValueError(f"coluna de personagem desconhecida: {coluna}")
    cur = await conn.execute(
        f"UPDATE personagens SET {coluna} = ?, atualizado_em = datetime('now')"
        " WHERE id = ?",
        (valor, personagem_id),
    )
    await conn.commit()
    return cur.rowcount > 0


async def atualizar_pericias(
    conn: aiosqlite.Connection, personagem_id: int, pericias: list[str]
) -> bool:
    return await atualizar_personagem(
        conn,
        personagem_id,
        "pericias",
        json.dumps(normalizar_lista_pericias(pericias), ensure_ascii=False),
    )


async def definir_bonus_pericia(
    conn: aiosqlite.Connection, personagem_id: int, pericia: str, valor: int
) -> Optional[dict[str, int]]:
    """Define (ou remove, com 0) o bonus de uma pericia. Devolve o mapa final."""
    personagem = await buscar_personagem(conn, personagem_id)
    if not personagem:
        return None
    canonico = normalizar_pericia(pericia)
    if not canonico:
        return None
    bonus = dict(personagem["bonus_pericias"])
    if valor:
        bonus[canonico] = valor
    else:
        bonus.pop(canonico, None)
    await conn.execute(
        "UPDATE personagens SET bonus_pericias = ?, atualizado_em = datetime('now')"
        " WHERE id = ?",
        (json.dumps(bonus, ensure_ascii=False), personagem_id),
    )
    await conn.commit()
    return bonus


async def remover_personagem(conn: aiosqlite.Connection, personagem_id: int) -> bool:
    cur = await conn.execute("DELETE FROM personagens WHERE id = ?", (personagem_id,))
    await conn.commit()
    return cur.rowcount > 0


# ---------------------------------------------------------------- runs

STATUS_VIVOS = ("recrutando", "escolhendo", "em_sala", "objetivo")
_CAMPOS_RUN = {"status", "linha_atual", "sala_atual", "mensagem_id", "votacao_expira_em"}


async def criar_run(
    conn: aiosqlite.Connection, guild_id: int, canal_id: int, incursao_id: str, criador_id: int
) -> int:
    cur = await conn.execute(
        "INSERT INTO runs (guild_id, canal_id, incursao_id, criador_id, status)"
        " VALUES (?, ?, ?, ?, 'recrutando')",
        (guild_id, canal_id, incursao_id, criador_id),
    )
    await conn.commit()
    return cur.lastrowid


async def buscar_run(conn: aiosqlite.Connection, run_id: int) -> Optional[dict[str, Any]]:
    async with conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def run_do_canal(conn: aiosqlite.Connection, canal_id: int) -> Optional[dict[str, Any]]:
    """A run viva daquele canal, se houver."""
    marcadores = ", ".join("?" * len(STATUS_VIVOS))
    async with conn.execute(
        f"SELECT * FROM runs WHERE canal_id = ? AND status IN ({marcadores})",
        (canal_id, *STATUS_VIVOS),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def runs_vivas(conn: aiosqlite.Connection) -> list[dict[str, Any]]:
    """Usado no boot para reconstruir os botões das mensagens ainda abertas."""
    marcadores = ", ".join("?" * len(STATUS_VIVOS))
    async with conn.execute(
        f"SELECT * FROM runs WHERE status IN ({marcadores})", STATUS_VIVOS
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


async def atualizar_run(conn: aiosqlite.Connection, run_id: int, **campos: Any) -> None:
    desconhecidos = set(campos) - _CAMPOS_RUN
    if desconhecidos:
        raise ValueError(f"campo de run desconhecido: {', '.join(sorted(desconhecidos))}")
    if not campos:
        return
    atribuicoes = ", ".join(f"{c} = ?" for c in campos)
    await conn.execute(
        f"UPDATE runs SET {atribuicoes}, atualizada_em = datetime('now') WHERE id = ?",
        (*campos.values(), run_id),
    )
    await conn.commit()


# ------------------------------------------------------- participantes


async def adicionar_participante(
    conn: aiosqlite.Connection, run_id: int, user_id: int, personagem_id: int
) -> bool:
    """False se o jogador já estava na run."""
    cur = await conn.execute(
        "INSERT OR IGNORE INTO run_participantes (run_id, user_id, personagem_id)"
        " VALUES (?, ?, ?)",
        (run_id, user_id, personagem_id),
    )
    await conn.commit()
    return cur.rowcount > 0


async def personagem_da_run(
    conn: aiosqlite.Connection, run_id: int, user_id: int
) -> Optional[dict[str, Any]]:
    """O personagem com que aquele jogador entrou nesta run."""
    async with conn.execute(
        "SELECT p.* FROM run_participantes rp JOIN personagens p ON p.id = rp.personagem_id"
        " WHERE rp.run_id = ? AND rp.user_id = ?",
        (run_id, user_id),
    ) as cur:
        row = await cur.fetchone()
    return _desserializar(row) if row else None


async def personagens_da_run(conn: aiosqlite.Connection, run_id: int) -> list[dict[str, Any]]:
    """Os personagens em jogo, na ordem em que entraram, com o HP atual da run."""
    async with conn.execute(
        "SELECT p.*, rp.hp_atual AS hp_atual, rp.user_id AS user_id"
        " FROM run_participantes rp JOIN personagens p ON p.id = rp.personagem_id"
        " WHERE rp.run_id = ? ORDER BY rp.rowid",
        (run_id,),
    ) as cur:
        return [_desserializar(r) for r in await cur.fetchall()]


async def remover_participante(conn: aiosqlite.Connection, run_id: int, user_id: int) -> bool:
    cur = await conn.execute(
        "DELETE FROM run_participantes WHERE run_id = ? AND user_id = ?", (run_id, user_id)
    )
    await conn.commit()
    return cur.rowcount > 0


async def participantes(conn: aiosqlite.Connection, run_id: int) -> list[int]:
    async with conn.execute(
        "SELECT user_id FROM run_participantes WHERE run_id = ? ORDER BY rowid", (run_id,)
    ) as cur:
        return [r["user_id"] for r in await cur.fetchall()]


async def esta_na_run(conn: aiosqlite.Connection, run_id: int, user_id: int) -> bool:
    async with conn.execute(
        "SELECT 1 FROM run_participantes WHERE run_id = ? AND user_id = ?", (run_id, user_id)
    ) as cur:
        return await cur.fetchone() is not None


async def run_viva_do_jogador(
    conn: aiosqlite.Connection, guild_id: int, user_id: int
) -> Optional[dict[str, Any]]:
    marcadores = ", ".join("?" * len(STATUS_VIVOS))
    async with conn.execute(
        "SELECT r.* FROM runs r JOIN run_participantes p ON p.run_id = r.id"
        f" WHERE r.guild_id = ? AND p.user_id = ? AND r.status IN ({marcadores})",
        (guild_id, user_id, *STATUS_VIVOS),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------- mapa


async def gravar_opcoes(
    conn: aiosqlite.Connection, run_id: int, passo: int, opcoes: list[str]
) -> None:
    """Fixa as salas sorteadas para um passo, para que nao mudem a cada leitura."""
    await conn.executemany(
        "INSERT OR REPLACE INTO run_mapa (run_id, passo, posicao, sala_id) VALUES (?, ?, ?, ?)",
        [(run_id, passo, posicao, sala_id) for posicao, sala_id in enumerate(opcoes)],
    )
    await conn.commit()


async def registrar_visita(
    conn: aiosqlite.Connection, run_id: int, passo: int, sala_id: str
) -> None:
    """Marca a sala que o grupo atravessou naquele passo."""
    await conn.execute(
        "INSERT OR REPLACE INTO run_salas (run_id, passo, sala_id) VALUES (?, ?, ?)",
        (run_id, passo, sala_id),
    )
    await conn.commit()


async def salas_visitadas(conn: aiosqlite.Connection, run_id: int) -> list[str]:
    """As salas por onde o grupo já passou nesta run."""
    async with conn.execute(
        "SELECT sala_id FROM run_salas WHERE run_id = ? ORDER BY passo", (run_id,)
    ) as cur:
        return [r["sala_id"] for r in await cur.fetchall()]


async def opcoes_do_passo(conn: aiosqlite.Connection, run_id: int, passo: int) -> list[str]:
    async with conn.execute(
        "SELECT sala_id FROM run_mapa WHERE run_id = ? AND passo = ? ORDER BY posicao",
        (run_id, passo),
    ) as cur:
        return [r["sala_id"] for r in await cur.fetchall()]


async def mapa_da_run(conn: aiosqlite.Connection, run_id: int) -> list[list[str]]:
    async with conn.execute(
        "SELECT passo, sala_id FROM run_mapa WHERE run_id = ? ORDER BY passo, posicao",
        (run_id,),
    ) as cur:
        linhas = await cur.fetchall()
    mapa: dict[int, list[str]] = {}
    for r in linhas:
        mapa.setdefault(r["passo"], []).append(r["sala_id"])
    return [mapa[p] for p in sorted(mapa)]


# -------------------------------------------------------------- testes


async def registrar_teste(
    conn: aiosqlite.Connection,
    run_id: int,
    passo: int,
    sala_id: str,
    user_id: int,
    personagem: str,
    pericia: str,
    d20: int,
    modificador: int,
    cd: int,
) -> bool:
    """False se o jogador já rolou neste passo (uma rolagem por sala visitada)."""
    cur = await conn.execute(
        "INSERT OR IGNORE INTO run_testes"
        " (run_id, passo, sala_id, user_id, personagem, pericia, d20, modificador, cd)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, passo, sala_id, user_id, personagem, pericia, d20, modificador, cd),
    )
    await conn.commit()
    return cur.rowcount > 0


async def testes_da_sala(
    conn: aiosqlite.Connection, run_id: int, passo: int
) -> list[dict[str, Any]]:
    async with conn.execute(
        "SELECT * FROM run_testes WHERE run_id = ? AND passo = ? ORDER BY criado_em, rowid",
        (run_id, passo),
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


# --------------------------------------------------------------- votos


async def registrar_voto(
    conn: aiosqlite.Connection, run_id: int, linha: int, user_id: int, opcao: str
) -> None:
    """Voto único por jogador e linha; votar de novo troca o voto anterior."""
    await conn.execute(
        "INSERT INTO run_votos (run_id, linha, user_id, opcao) VALUES (?, ?, ?, ?)"
        " ON CONFLICT (run_id, linha, user_id) DO UPDATE SET"
        " opcao = excluded.opcao, criado_em = datetime('now')",
        (run_id, linha, user_id, opcao),
    )
    await conn.commit()


async def votos_da_linha(conn: aiosqlite.Connection, run_id: int, linha: int) -> dict[int, str]:
    async with conn.execute(
        "SELECT user_id, opcao FROM run_votos WHERE run_id = ? AND linha = ?", (run_id, linha)
    ) as cur:
        return {r["user_id"]: r["opcao"] for r in await cur.fetchall()}


# -------------------------------------------------------------- config


async def intervalo_semanas(conn: aiosqlite.Connection, guild_id: int) -> int:
    async with conn.execute(
        "SELECT intervalo_semanas FROM config_guilda WHERE guild_id = ?", (guild_id,)
    ) as cur:
        row = await cur.fetchone()
    return row["intervalo_semanas"] if row else config.INTERVALO_SEMANAS


async def definir_intervalo(conn: aiosqlite.Connection, guild_id: int, semanas: int) -> None:
    await conn.execute(
        "INSERT INTO config_guilda (guild_id, intervalo_semanas) VALUES (?, ?)"
        " ON CONFLICT (guild_id) DO UPDATE SET intervalo_semanas = excluded.intervalo_semanas",
        (guild_id, semanas),
    )
    await conn.commit()


async def marcar_ultima_incursao(
    conn: aiosqlite.Connection, guild_id: int, user_ids: list[int]
) -> None:
    """O intervalo e do jogador: vale para todos os personagens dele."""
    await conn.executemany(
        "INSERT INTO jogadores (guild_id, user_id, ultima_incursao)"
        " VALUES (?, ?, datetime('now'))"
        " ON CONFLICT (guild_id, user_id) DO UPDATE SET ultima_incursao = datetime('now')",
        [(guild_id, u) for u in user_ids],
    )
    await conn.commit()


async def ultima_incursao(
    conn: aiosqlite.Connection, guild_id: int, user_id: int
) -> Optional[datetime]:
    """Quando o jogador entrou na última incursão, no fuso do servidor.

    O banco grava em UTC; a janela semanal é contada no fuso de quem joga.
    """
    async with conn.execute(
        "SELECT ultima_incursao FROM jogadores"
        " WHERE guild_id = ? AND user_id = ? AND ultima_incursao IS NOT NULL",
        (guild_id, user_id),
    ) as cur:
        row = await cur.fetchone()
    if not row:
        return None
    marcado = datetime.strptime(row["ultima_incursao"], "%Y-%m-%d %H:%M:%S")
    return marcado.replace(tzinfo=timezone.utc).astimezone(config.FUSO)


# ------------------------------------------------------------- combate


async def iniciar_combate(
    conn: aiosqlite.Connection,
    run_id: int,
    passo: int,
    sala_id: str,
    inimigos: list[Any],
) -> None:
    """Cria o estado do combate daquele passo. Reabrir a mensagem não reinicia."""
    await conn.execute(
        "INSERT OR IGNORE INTO run_combate (run_id, passo, sala_id) VALUES (?, ?, ?)",
        (run_id, passo, sala_id),
    )
    await conn.executemany(
        "INSERT OR IGNORE INTO run_inimigos"
        " (run_id, passo, indice, nome, ca, ataque, dano, hp_max, hp_atual)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (run_id, passo, i, m.nome, m.ca, m.ataque, m.dano, m.hp, m.hp)
            for i, m in enumerate(inimigos)
        ],
    )
    await conn.commit()


async def inimigos_do_combate(
    conn: aiosqlite.Connection, run_id: int, passo: int
) -> list[dict[str, Any]]:
    async with conn.execute(
        "SELECT * FROM run_inimigos WHERE run_id = ? AND passo = ? ORDER BY indice",
        (run_id, passo),
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


async def definir_hp_inimigos(
    conn: aiosqlite.Connection, run_id: int, passo: int, por_indice: dict[int, int]
) -> None:
    await conn.executemany(
        "UPDATE run_inimigos SET hp_atual = ? WHERE run_id = ? AND passo = ? AND indice = ?",
        [(hp, run_id, passo, indice) for indice, hp in por_indice.items()],
    )
    await conn.commit()


async def estado_combate(
    conn: aiosqlite.Connection, run_id: int, passo: int
) -> Optional[dict[str, Any]]:
    async with conn.execute(
        "SELECT * FROM run_combate WHERE run_id = ? AND passo = ?", (run_id, passo)
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def atualizar_rodada(
    conn: aiosqlite.Connection, run_id: int, passo: int, rodada: int
) -> None:
    await conn.execute(
        "UPDATE run_combate SET rodada = ? WHERE run_id = ? AND passo = ?",
        (rodada, run_id, passo),
    )
    await conn.commit()


async def registrar_ataque(
    conn: aiosqlite.Connection,
    run_id: int,
    passo: int,
    rodada: int,
    user_id: int,
    d20: int,
    bonus: int,
    ca_alvo: int,
    dano: int,
    alvo: int = 0,
) -> bool:
    """False se o personagem já atacou nesta rodada."""
    cur = await conn.execute(
        "INSERT OR IGNORE INTO run_ataques"
        " (run_id, passo, rodada, user_id, d20, bonus, ca_alvo, dano, alvo)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, passo, rodada, user_id, d20, bonus, ca_alvo, dano, alvo),
    )
    await conn.commit()
    return cur.rowcount > 0


async def ataques_da_rodada(
    conn: aiosqlite.Connection, run_id: int, passo: int, rodada: int
) -> list[dict[str, Any]]:
    async with conn.execute(
        "SELECT * FROM run_ataques WHERE run_id = ? AND passo = ? AND rodada = ?"
        " ORDER BY rowid",
        (run_id, passo, rodada),
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


async def inicializar_hp(conn: aiosqlite.Connection, run_id: int) -> None:
    """No começo da run, cada personagem entra com o HP máximo da própria ficha.

    O HP máximo sai da tabela da classe, não de uma coluna, então a conta é feita
    aqui em vez de num UPDATE com subconsulta.
    """
    await conn.executemany(
        "UPDATE run_participantes SET hp_atual = ? WHERE run_id = ? AND user_id = ?",
        [
            (p["hp_max"], run_id, p["user_id"])
            for p in await personagens_da_run(conn, run_id)
            if p.get("hp_max")
        ],
    )
    await conn.commit()


async def hp_dos_participantes(conn: aiosqlite.Connection, run_id: int) -> dict[int, Optional[int]]:
    async with conn.execute(
        "SELECT user_id, hp_atual FROM run_participantes WHERE run_id = ? ORDER BY rowid",
        (run_id,),
    ) as cur:
        return {r["user_id"]: r["hp_atual"] for r in await cur.fetchall()}


async def definir_hp(conn: aiosqlite.Connection, run_id: int, user_id: int, hp: int) -> None:
    await conn.execute(
        "UPDATE run_participantes SET hp_atual = ? WHERE run_id = ? AND user_id = ?",
        (hp, run_id, user_id),
    )
    await conn.commit()


async def definir_hp_varios(
    conn: aiosqlite.Connection, run_id: int, hps: dict[int, int]
) -> None:
    await conn.executemany(
        "UPDATE run_participantes SET hp_atual = ? WHERE run_id = ? AND user_id = ?",
        [(hp, run_id, user_id) for user_id, hp in hps.items()],
    )
    await conn.commit()


# ------------------------------------------- pontos de Organizacao

# O placar e do servidor inteiro, nao de cada jogador: cada uma das quatro
# Organizacoes acumula os pontos que as runs renderam a ela.


async def lancar_pontos(
    conn: aiosqlite.Connection,
    guild_id: int,
    organizacao: str,
    pontos: int,
    motivo: str,
    run_id: Optional[int] = None,
    chave: Optional[str] = None,
) -> bool:
    """Credita pontos e registra o lançamento.

    `chave` identifica o motivo dentro da run (ex.: 'sala:L2C', 'conclusao').
    Um mesmo par (run_id, chave) nunca é lançado duas vezes, então reprocessar
    uma sala não infla o placar. Devolve False quando o lançamento já existia.
    """
    cur = await conn.execute(
        "INSERT OR IGNORE INTO pontos_lancamentos"
        " (guild_id, organizacao, run_id, chave, motivo, pontos)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (guild_id, organizacao, run_id, chave, motivo, pontos),
    )
    if cur.rowcount == 0:
        await conn.commit()
        return False

    await conn.execute(
        "INSERT INTO placar_organizacoes (guild_id, organizacao, pontos) VALUES (?, ?, ?)"
        " ON CONFLICT (guild_id, organizacao) DO UPDATE SET"
        " pontos = pontos + excluded.pontos",
        (guild_id, organizacao, pontos),
    )
    await conn.commit()
    return True


async def placar(conn: aiosqlite.Connection, guild_id: int) -> dict[str, int]:
    async with conn.execute(
        "SELECT organizacao, pontos FROM placar_organizacoes WHERE guild_id = ?", (guild_id,)
    ) as cur:
        return {r["organizacao"]: r["pontos"] for r in await cur.fetchall()}


async def lancamentos(
    conn: aiosqlite.Connection,
    guild_id: int,
    organizacao: Optional[str] = None,
    limite: int = 10,
) -> list[dict[str, Any]]:
    if organizacao:
        consulta = (
            "SELECT * FROM pontos_lancamentos WHERE guild_id = ? AND organizacao = ?"
            " ORDER BY id DESC LIMIT ?"
        )
        parametros = (guild_id, organizacao, limite)
    else:
        consulta = "SELECT * FROM pontos_lancamentos WHERE guild_id = ? ORDER BY id DESC LIMIT ?"
        parametros = (guild_id, limite)
    async with conn.execute(consulta, parametros) as cur:
        return [dict(r) for r in await cur.fetchall()]


async def pontos_da_run(conn: aiosqlite.Connection, run_id: int) -> list[dict[str, Any]]:
    async with conn.execute(
        "SELECT * FROM pontos_lancamentos WHERE run_id = ? ORDER BY id", (run_id,)
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]
