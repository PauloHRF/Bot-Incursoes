"""Camada de persistencia (SQLite via aiosqlite)."""
from __future__ import annotations

import json
from typing import Any, Optional

import aiosqlite

from . import config

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
    ficha["pericias"] = json.loads(ficha["pericias"])
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
    return await atualizar_campo(conn, guild_id, user_id, "pericias", json.dumps(pericias, ensure_ascii=False))
