"""Ponto de entrada do bot Incursoes 2.0."""
from __future__ import annotations

import logging

import discord
from discord.ext import commands

from . import config, database

log = logging.getLogger("incursoes")

COGS = (
    "src.cogs.ajuda",
    "src.cogs.ficha",
    "src.cogs.mercado",
    "src.cogs.incursao",
    "src.cogs.organizacao",
)


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

        await self._sincronizar()

    async def _sincronizar(self) -> None:
        """Registra os comandos: em cada guilda do .env, ou globalmente.

        Por guilda e um POST por guilda, e os comandos aparecem na hora.
        Globalmente e um POST so, vale em qualquer servidor onde o bot entre
        depois, e a primeira propagacao leva ate ~1h.

        Uma guilda que falha nao derruba o bot: um id errado no .env, ou um
        servidor de onde o bot foi removido, devolve 403 — e perder os
        comandos de um servidor por isso e muito melhor que nao subir.
        """
        if not config.GUILD_IDS:
            sincronizados = await self.tree.sync()
            log.info(
                "%d comandos sincronizados globalmente (pode levar ~1h)",
                len(sincronizados),
            )
            return
        for guild_id in config.GUILD_IDS:
            guilda = discord.Object(id=guild_id)
            self.tree.copy_global_to(guild=guilda)
            try:
                sincronizados = await self.tree.sync(guild=guilda)
            except discord.HTTPException as erro:
                log.error("guilda %s: nao deu para sincronizar (%s)", guild_id, erro)
                continue
            log.info(
                "%d comandos sincronizados na guilda %s",
                len(sincronizados), guild_id,
            )

    async def on_ready(self) -> None:
        log.info("Conectado como %s (id %s)", self.user, self.user.id)

    async def close(self) -> None:
        if self.db is not None:
            await self.db.close()
        await super().close()


def main() -> None:
    if not config.TOKEN:
        raise SystemExit("DISCORD_TOKEN ausente: copie .env.example para .env e preencha o token.")
    # root_logger=True porque o default do discord.py e False: sem ele, o
    # `setup_logging` configura so o logger "discord", e tudo que ESTE modulo
    # registra em `log` — o "Conectado como", a contagem de comandos
    # sincronizados — e escrito e descartado, sem handler nenhum.
    #
    # Na maquina de desenvolvimento isso passa despercebido. Num servidor e
    # cegueira: o journalctl mostraria o bot conectando ao gateway e mais
    # nada, nem se os comandos chegaram na guilda nem se um cog quebrou.
    IncursoesBot().run(config.TOKEN, log_level=logging.INFO, root_logger=True)


if __name__ == "__main__":
    main()
