"""Placar de pontos das quatro Organizações.

Os pontos são do servidor como um todo, não de cada jogador: cada incursão
credita a Organização a que pertence.
"""
from __future__ import annotations

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from .. import database as db, embeds as E
from ..incursoes import ORGANIZACOES

ESCOLHAS_ORG = [app_commands.Choice(name=o, value=o) for o in ORGANIZACOES]


class Organizacao(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    grupo = app_commands.Group(name="organizacao", description="Pontos das Organizações")

    @grupo.command(name="placar", description="Pontos de cada Organização no servidor")
    async def placar(self, interaction: discord.Interaction) -> None:
        pontos = await db.placar(self.bot.db, interaction.guild_id)
        await interaction.response.send_message(
            embed=E.placar_organizacoes(pontos, ORGANIZACOES)
        )

    @grupo.command(name="extrato", description="Últimos pontos lançados")
    @app_commands.describe(
        organizacao="Filtra por uma Organização (opcional)",
        quantidade="Quantos lançamentos mostrar (padrão 10)",
    )
    @app_commands.choices(organizacao=ESCOLHAS_ORG)
    async def extrato(
        self,
        interaction: discord.Interaction,
        organizacao: Optional[app_commands.Choice[str]] = None,
        quantidade: app_commands.Range[int, 1, 25] = 10,
    ) -> None:
        nome = organizacao.value if organizacao else None
        registros = await db.lancamentos(
            self.bot.db, interaction.guild_id, nome, limite=quantidade
        )
        await interaction.response.send_message(embed=E.extrato_pontos(registros, nome))

    @grupo.command(name="ajustar", description="(admin) Lança pontos na mão, para correções")
    @app_commands.describe(
        organizacao="Qual Organização",
        pontos="Quanto somar (use negativo para tirar)",
        motivo="Por que este ajuste existe",
    )
    @app_commands.choices(organizacao=ESCOLHAS_ORG)
    @app_commands.default_permissions(manage_guild=True)
    async def ajustar(
        self,
        interaction: discord.Interaction,
        organizacao: app_commands.Choice[str],
        pontos: app_commands.Range[int, -9999, 9999],
        motivo: app_commands.Range[str, 1, 200],
    ) -> None:
        if pontos == 0:
            await interaction.response.send_message("Zero ponto não muda nada.", ephemeral=True)
            return
        await db.lancar_pontos(
            self.bot.db,
            interaction.guild_id,
            organizacao.value,
            pontos,
            f"{motivo} — ajuste de {interaction.user.display_name}",
        )
        total = (await db.placar(self.bot.db, interaction.guild_id)).get(organizacao.value, 0)
        await interaction.response.send_message(
            f"**{pontos:+d}** para {organizacao.value}: {motivo}. Total agora: **{total}**."
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Organizacao(bot))
