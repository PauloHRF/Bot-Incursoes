"""Ponto de entrada do bot Incursoes 2.0."""
from __future__ import annotations

import logging

import discord
from discord.ext import commands

from . import config, database

log = logging.getLogger("incursoes")

COGS = ("src.cogs.ficha", "src.cogs.incursao", "src.cogs.organizacao")


class IncursoesBot(commands.Bot):
    def __init__(self) -> None:
        # Comandos de barra nao precisam de message_content.
        super().__init__(command_prefix="!", intents=discord.Intents.default())
        self.db = None

    async def setup_hook(self) -> None:
        self.db = await database.conectar()
        await database.criar_schema(self.db)

        for cog in COGS:
            await self.load_extension(cog)

        if config.GUILD_ID:
            guilda = discord.Object(id=config.GUILD_ID)
            self.tree.copy_global_to(guild=guilda)
            sincronizados = await self.tree.sync(guild=guilda)
            log.info("%d comandos sincronizados na guilda %s", len(sincronizados), config.GUILD_ID)
        else:
            sincronizados = await self.tree.sync()
            log.info("%d comandos sincronizados globalmente (pode levar ~1h)", len(sincronizados))

    async def on_ready(self) -> None:
        log.info("Conectado como %s (id %s)", self.user, self.user.id)

    async def close(self) -> None:
        if self.db is not None:
            await self.db.close()
        await super().close()


def main() -> None:
    if not config.TOKEN:
        raise SystemExit("DISCORD_TOKEN ausente: copie .env.example para .env e preencha o token.")
    IncursoesBot().run(config.TOKEN, log_level=logging.INFO)


if __name__ == "__main__":
    main()
