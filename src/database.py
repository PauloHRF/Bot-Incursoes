"""Camada de persistencia (SQLite via aiosqlite)."""
from __future__ import annotations

import json
from typing import Any, Optional

import aiosqlite

from . import config
from .rules import normalizar_lista_pericias, normalizar_pericia

# sigla do atributo -> coluna no banco
COLUNA_ATRIBUTO = {
    "FOR": "forca",
    "DES": "destreza",
    "CON": "constituicao",
    "INT": "inteligencia",
    "SAB": "sabedoria",
    "CAR": "carisma",
}

COLUNAS_EDITAVEIS = {
    "nome", "nivel", "pericias", "ca", "bonus_ataque", "dano_arma", "hp_max",
    *COLUNA_ATRIBUTO.values(),
}

SCHEMA = """
-- Um jogador pode ter varios personagens; escolhe qual usar ao entrar na run.
CREATE TABLE IF NOT EXISTS personagens (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id       INTEGER NOT NULL,
    user_id        INTEGER NOT NULL,
    nome           TEXT    NOT NULL,
    nivel          INTEGER NOT NULL,
    forca          INTEGER NOT NULL,
    destreza       INTEGER NOT NULL,
    constituicao   INTEGER NOT NULL,
    inteligencia   INTEGER NOT NULL,
    sabedoria      INTEGER NOT NULL,
    carisma        INTEGER NOT NULL,
    pericias       TEXT    NOT NULL DEFAULT '[]',
    bonus_pericias TEXT    NOT NULL DEFAULT '{}',
    ca             INTEGER NOT NULL DEFAULT 10,
    bonus_ataque   INTEGER NOT NULL DEFAULT 0,
    dano_arma      TEXT    NOT NULL DEFAULT '1d6',
    hp_max         INTEGER NOT NULL DEFAULT 10,
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

CREATE TABLE IF NOT EXISTS run_combate (
    run_id         INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    passo          INTEGER NOT NULL,
    sala_id        TEXT    NOT NULL,
    monstro_hp_max INTEGER NOT NULL,
    monstro_hp     INTEGER NOT NULL,
    rodada         INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (run_id, passo)
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
    guild_id       INTEGER PRIMARY KEY,
    intervalo_dias INTEGER NOT NULL
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
    migrando = await _tabela_existe(conn, "personagens") and "id" not in await _colunas(
        conn, "personagens"
    )
    if migrando:
        # A tabela antiga tinha PK (guild_id, user_id). Guardamos de lado, deixamos
        # o schema criar a nova e copiamos cada ficha como o primeiro personagem.
        await conn.execute("ALTER TABLE personagens RENAME TO personagens_v1")

    await conn.executescript(SCHEMA)

    if migrando:
        await conn.execute(
            "INSERT INTO personagens"
            " (guild_id, user_id, nome, nivel, forca, destreza, constituicao,"
            "  inteligencia, sabedoria, carisma, pericias, ca, bonus_ataque, dano_arma, hp_max)"
            " SELECT guild_id, user_id, nome, nivel, forca, destreza, constituicao,"
            "  inteligencia, sabedoria, carisma, pericias, ca, bonus_ataque, dano_arma, hp_max"
            " FROM personagens_v1"
        )
        await conn.execute(
            "INSERT OR IGNORE INTO jogadores (guild_id, user_id, ultima_incursao)"
            " SELECT guild_id, user_id, ultima_incursao FROM personagens_v1"
            " WHERE ultima_incursao IS NOT NULL"
        )
        await conn.execute("DROP TABLE personagens_v1")

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

    # Nem os bonus avulsos por pericia (expertise).
    if "bonus_pericias" not in await _colunas(conn, "personagens"):
        await conn.execute(
            "ALTER TABLE personagens ADD COLUMN bonus_pericias TEXT NOT NULL DEFAULT '{}'"
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
    p = dict(row)
    # Normaliza fichas gravadas antes dos nomes de pericia ganharem acento.
    p["pericias"] = normalizar_lista_pericias(json.loads(p["pericias"]))
    p["bonus_pericias"] = _normalizar_bonus(json.loads(p.get("bonus_pericias") or "{}"))
    p["atributos"] = {sigla: p[col] for sigla, col in COLUNA_ATRIBUTO.items()}
    return p


async def criar_personagem(
    conn: aiosqlite.Connection,
    guild_id: int,
    user_id: int,
    nome: str,
    nivel: int,
    atributos: dict[str, int],
    pericias: list[str],
    combate: Optional[dict[str, Any]] = None,
    bonus_pericias: Optional[dict[str, int]] = None,
) -> Optional[int]:
    """Cria um personagem. Devolve None se o jogador ja tem outro com esse nome."""
    combate = combate or {}
    try:
        cur = await conn.execute(
            "INSERT INTO personagens (guild_id, user_id, nome, nivel, forca, destreza,"
            " constituicao, inteligencia, sabedoria, carisma, pericias,"
            " bonus_pericias, ca, bonus_ataque, dano_arma, hp_max)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                guild_id, user_id, nome.strip(), nivel,
                atributos["FOR"], atributos["DES"], atributos["CON"],
                atributos["INT"], atributos["SAB"], atributos["CAR"],
                json.dumps(normalizar_lista_pericias(pericias), ensure_ascii=False),
                json.dumps(_normalizar_bonus(bonus_pericias or {}), ensure_ascii=False),
                combate.get("ca", 10),
                combate.get("bonus_ataque", 0),
                combate.get("dano_arma", "1d6"),
                combate.get("hp_max", 10),
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


async def gravar_mapa(
    conn: aiosqlite.Connection, run_id: int, mapa: list[list[str]]
) -> None:
    """Fixa o caminho sorteado, para que ele nao mude a cada leitura."""
    await conn.executemany(
        "INSERT OR REPLACE INTO run_mapa (run_id, passo, posicao, sala_id) VALUES (?, ?, ?, ?)",
        [
            (run_id, passo, posicao, sala_id)
            for passo, opcoes in enumerate(mapa, start=1)
            for posicao, sala_id in enumerate(opcoes)
        ],
    )
    await conn.commit()


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


async def intervalo_dias(conn: aiosqlite.Connection, guild_id: int) -> int:
    async with conn.execute(
        "SELECT intervalo_dias FROM config_guilda WHERE guild_id = ?", (guild_id,)
    ) as cur:
        row = await cur.fetchone()
    return row["intervalo_dias"] if row else config.INTERVALO_DIAS


async def definir_intervalo(conn: aiosqlite.Connection, guild_id: int, dias: int) -> None:
    await conn.execute(
        "INSERT INTO config_guilda (guild_id, intervalo_dias) VALUES (?, ?)"
        " ON CONFLICT (guild_id) DO UPDATE SET intervalo_dias = excluded.intervalo_dias",
        (guild_id, dias),
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


async def dias_desde_ultima_incursao(
    conn: aiosqlite.Connection, guild_id: int, user_id: int
) -> Optional[float]:
    """None se o jogador nunca participou de uma incursão."""
    async with conn.execute(
        "SELECT julianday('now') - julianday(ultima_incursao) AS dias FROM jogadores"
        " WHERE guild_id = ? AND user_id = ? AND ultima_incursao IS NOT NULL",
        (guild_id, user_id),
    ) as cur:
        row = await cur.fetchone()
    return row["dias"] if row else None


# ------------------------------------------------------------- combate


async def iniciar_combate(
    conn: aiosqlite.Connection, run_id: int, passo: int, sala_id: str, monstro_hp: int
) -> None:
    """Cria o estado do combate daquele passo. Reabrir a mensagem não reinicia."""
    await conn.execute(
        "INSERT OR IGNORE INTO run_combate (run_id, passo, sala_id, monstro_hp_max, monstro_hp)"
        " VALUES (?, ?, ?, ?, ?)",
        (run_id, passo, sala_id, monstro_hp, monstro_hp),
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


async def atualizar_combate(
    conn: aiosqlite.Connection, run_id: int, passo: int, monstro_hp: int, rodada: int
) -> None:
    await conn.execute(
        "UPDATE run_combate SET monstro_hp = ?, rodada = ? WHERE run_id = ? AND passo = ?",
        (monstro_hp, rodada, run_id, passo),
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
) -> bool:
    """False se o personagem já atacou nesta rodada."""
    cur = await conn.execute(
        "INSERT OR IGNORE INTO run_ataques"
        " (run_id, passo, rodada, user_id, d20, bonus, ca_alvo, dano)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, passo, rodada, user_id, d20, bonus, ca_alvo, dano),
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
    """No começo da run, cada personagem entra com o HP máximo da própria ficha."""
    await conn.execute(
        "UPDATE run_participantes SET hp_atual = ("
        "  SELECT hp_max FROM personagens p WHERE p.id = run_participantes.personagem_id"
        ") WHERE run_id = ?",
        (run_id,),
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
