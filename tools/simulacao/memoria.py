"""SQLite descartavel com a interface async usada por src.database.

As consultas sao locais, imediatas e executadas na thread da simulacao.
Evita milhares de trocas de thread por luta sem trocar SQL ou regras do bot.
"""
import sqlite3


class Consulta:
    def __init__(self, cursor):
        self.cursor = cursor

    @property
    def lastrowid(self):
        return self.cursor.lastrowid

    @property
    def rowcount(self):
        return self.cursor.rowcount

    async def fetchone(self):
        return self.cursor.fetchone()

    async def fetchall(self):
        return self.cursor.fetchall()

    async def close(self):
        self.cursor.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.close()

    def __await__(self):
        async def pronta():
            return self
        return pronta().__await__()


class Memoria:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    def execute(self, sql, parametros=()):
        return Consulta(self.conn.execute(sql, parametros))

    def executemany(self, sql, parametros):
        return Consulta(self.conn.executemany(sql, parametros))

    def executescript(self, sql):
        return Consulta(self.conn.executescript(sql))

    async def commit(self):
        self.conn.commit()

    async def close(self):
        self.conn.close()
