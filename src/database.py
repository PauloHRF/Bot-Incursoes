"""Camada de persistencia (SQLite via aiosqlite)."""
from __future__ import annotations

import json
from typing import Any, Optional

import aiosqlite

from . import config
from .rules import normalizar_lista_pericias

# sigla do atributo -> coluna no banco
COLUNA_ATRIBUTO = {
    "FOR": "forca",
    "DES": "destreza",
    "CON": "constituicao",
    "INT": "inteligencia",
    "SAB": "sabedoria",
    "CAR": "carisma",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS personagens (
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
    ca             INTEGER NOT NULL DEFAULT 10,
    bonus_ataque   INTEGER NOT NULL DEFAULT 0,
    dano_arma      TEXT    NOT NULL DEFAULT '1d6',
    hp_max         INTEGER NOT NULL DEFAULT 10,
    ultima_incursao TEXT,
    atualizado_em  TEXT    NOT NULL DEFAULT (datetime('now')),
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
    run_id   INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    user_id  INTEGER NOT NULL,
    hp_atual INTEGER,
    PRIMARY KEY (run_id, user_id)
);

CREATE TABLE IF NOT EXISTS run_testes (
    run_id      INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    sala_id     TEXT    NOT NULL,
    user_id     INTEGER NOT NULL,
    personagem  TEXT    NOT NULL,
    pericia     TEXT    NOT NULL,
    d20         INTEGER NOT NULL,
    modificador INTEGER NOT NULL,
    cd          INTEGER NOT NULL,
    criado_em   TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (run_id, sala_id, user_id)
);

CREATE TABLE IF NOT EXISTS run_votos (
    run_id    INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    linha     INTEGER NOT NULL,
    user_id   INTEGER NOT NULL,
    opcao     TEXT    NOT NULL,
    criado_em TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (run_id, linha, user_id)
);

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


async def criar_schema(conn: aiosqlite.Connection) -> None:
    await conn.executescript(SCHEMA)
    await conn.commit()


def _desserializar(row: aiosqlite.Row) -> dict[str, Any]:
    ficha = dict(row)
    # Normaliza fichas gravadas antes dos nomes de pericia ganharem acento.
    ficha["pericias"] = normalizar_lista_pericias(json.loads(ficha["pericias"]))
    ficha["atributos"] = {sigla: ficha[col] for sigla, col in COLUNA_ATRIBUTO.items()}
    return ficha


async def buscar_ficha(conn: aiosqlite.Connection, guild_id: int, user_id: int) -> Optional[dict[str, Any]]:
    async with conn.execute(
        "SELECT * FROM personagens WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)
    ) as cur:
        row = await cur.fetchone()
    return _desserializar(row) if row else None


async def salvar_ficha(
    conn: aiosqlite.Connection,
    guild_id: int,
    user_id: int,
    nome: str,
    nivel: int,
    atributos: dict[str, int],
    pericias: list[str],
) -> None:
    """Cria ou substitui nivel/atributos/pericias, preservando os campos de combate."""
    pericias = normalizar_lista_pericias(pericias)
    await conn.execute(
        """
        INSERT INTO personagens (guild_id, user_id, nome, nivel, forca, destreza,
                                 constituicao, inteligencia, sabedoria, carisma, pericias)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (guild_id, user_id) DO UPDATE SET
            nome = excluded.nome,
            nivel = excluded.nivel,
            forca = excluded.forca,
            destreza = excluded.destreza,
            constituicao = excluded.constituicao,
            inteligencia = excluded.inteligencia,
            sabedoria = excluded.sabedoria,
            carisma = excluded.carisma,
            pericias = excluded.pericias,
            atualizado_em = datetime('now')
        """,
        (
            guild_id, user_id, nome, nivel,
            atributos["FOR"], atributos["DES"], atributos["CON"],
            atributos["INT"], atributos["SAB"], atributos["CAR"],
            json.dumps(pericias, ensure_ascii=False),
        ),
    )
    await conn.commit()


async def atualizar_campo(conn: aiosqlite.Connection, guild_id: int, user_id: int, coluna: str, valor: Any) -> bool:
    """Atualiza uma coluna da ficha. `coluna` nunca vem do usuario direto."""
    cur = await conn.execute(
        f"UPDATE personagens SET {coluna} = ?, atualizado_em = datetime('now')"
        " WHERE guild_id = ? AND user_id = ?",
        (valor, guild_id, user_id),
    )
    await conn.commit()
    return cur.rowcount > 0


async def atualizar_pericias(conn: aiosqlite.Connection, guild_id: int, user_id: int, pericias: list[str]) -> bool:
    pericias = normalizar_lista_pericias(pericias)
    return await atualizar_campo(conn, guild_id, user_id, "pericias", json.dumps(pericias, ensure_ascii=False))


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


async def votacoes_expiradas(conn: aiosqlite.Connection) -> list[dict[str, Any]]:
    async with conn.execute(
        "SELECT * FROM runs WHERE status = 'escolhendo' AND votacao_expira_em IS NOT NULL"
        " AND votacao_expira_em <= datetime('now')"
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


# ------------------------------------------------------- participantes


async def adicionar_participante(conn: aiosqlite.Connection, run_id: int, user_id: int) -> bool:
    """False se o jogador já estava na run."""
    cur = await conn.execute(
        "INSERT OR IGNORE INTO run_participantes (run_id, user_id) VALUES (?, ?)", (run_id, user_id)
    )
    await conn.commit()
    return cur.rowcount > 0


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


# -------------------------------------------------------------- testes


async def registrar_teste(
    conn: aiosqlite.Connection,
    run_id: int,
    sala_id: str,
    user_id: int,
    personagem: str,
    pericia: str,
    d20: int,
    modificador: int,
    cd: int,
) -> bool:
    """False se o jogador já rolou nesta sala (uma rolagem por sala)."""
    cur = await conn.execute(
        "INSERT OR IGNORE INTO run_testes"
        " (run_id, sala_id, user_id, personagem, pericia, d20, modificador, cd)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, sala_id, user_id, personagem, pericia, d20, modificador, cd),
    )
    await conn.commit()
    return cur.rowcount > 0


async def testes_da_sala(
    conn: aiosqlite.Connection, run_id: int, sala_id: str
) -> list[dict[str, Any]]:
    async with conn.execute(
        "SELECT * FROM run_testes WHERE run_id = ? AND sala_id = ? ORDER BY criado_em, rowid",
        (run_id, sala_id),
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
    await conn.executemany(
        "UPDATE personagens SET ultima_incursao = datetime('now')"
        " WHERE guild_id = ? AND user_id = ?",
        [(guild_id, u) for u in user_ids],
    )
    await conn.commit()


async def dias_desde_ultima_incursao(
    conn: aiosqlite.Connection, guild_id: int, user_id: int
) -> Optional[float]:
    """None se o jogador nunca participou de uma incursão."""
    async with conn.execute(
        "SELECT julianday('now') - julianday(ultima_incursao) AS dias FROM personagens"
        " WHERE guild_id = ? AND user_id = ? AND ultima_incursao IS NOT NULL",
        (guild_id, user_id),
    ) as cur:
        row = await cur.fetchone()
    return row["dias"] if row else None
