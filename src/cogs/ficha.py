"""Comandos de ficha digital: cadastro, consulta e manutencao (nivel / ASI)."""
from __future__ import annotations

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from .. import database as db
from ..rules import (
    ATRIBUTOS,
    PERICIAS,
    bonus_proficiencia,
    fmt,
    mod_pericia,
    modificador,
    tier,
)


class SeletorPericias(discord.ui.View):
    """Menu de selecao das pericias treinadas, restrito a quem abriu."""

    def __init__(self, dono_id: int, marcadas: list[str]):
        super().__init__(timeout=300)
        self.dono_id = dono_id
        self.escolhidas: Optional[list[str]] = None
        opcoes = [
            discord.SelectOption(label=p, description=ATRIBUTOS[attr], default=p in marcadas)
            for p, attr in PERICIAS.items()
        ]
        self.menu = discord.ui.Select(
            placeholder="Escolha as pericias treinadas",
            min_values=0,
            max_values=len(opcoes),
            options=opcoes,
        )
        self.menu.callback = self._escolher
        self.add_item(self.menu)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.dono_id:
            await interaction.response.send_message("Essa ficha nao e sua.", ephemeral=True)
            return False
        return True

    async def _escolher(self, interaction: discord.Interaction) -> None:
        self.escolhidas = list(self.menu.values)
        self.stop()
        await interaction.response.defer()


def embed_ficha(ficha: dict, autor: discord.abc.User) -> discord.Embed:
    nivel = ficha["nivel"]
    treinadas = ficha["pericias"]
    atributos = ficha["atributos"]

    e = discord.Embed(
        title=ficha["nome"],
        description=f"Nivel {nivel} | Tier {tier(nivel)} | Proficiencia {fmt(bonus_proficiencia(nivel))}",
        color=discord.Color.dark_gold(),
    )
    e.set_author(name=autor.display_name, icon_url=autor.display_avatar.url)
    e.add_field(
        name="Atributos",
        value=" | ".join(
            f"**{s}** {atributos[s]} ({fmt(modificador(atributos[s]))})" for s in ATRIBUTOS
        ),
        inline=False,
    )
    if treinadas:
        linhas = [
            f"{p} {fmt(mod_pericia(p, atributos, nivel, treinadas))}" for p in sorted(treinadas)
        ]
        e.add_field(
            name=f"Pericias treinadas ({len(treinadas)})", value=" | ".join(linhas), inline=False
        )
    else:
        e.add_field(name="Pericias treinadas", value="nenhuma - use /ficha pericias", inline=False)
    e.add_field(
        name="Combate",
        value=(
            f"CA **{ficha['ca']}** | Ataque **{fmt(ficha['bonus_ataque'])}** | "
            f"Dano **{ficha['dano_arma']}** | HP **{ficha['hp_max']}**"
        ),
        inline=False,
    )
    e.set_footer(text="Modificadores calculados a partir do nivel e dos atributos")
    return e


class Ficha(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    grupo = app_commands.Group(name="ficha", description="Ficha digital do seu personagem")

    @grupo.command(name="registrar", description="Cadastra nivel, atributos e pericias treinadas")
    @app_commands.describe(
        nome="Nome do personagem",
        nivel="Nivel atual (1-20)",
        forca="Valor de Forca",
        destreza="Valor de Destreza",
        constituicao="Valor de Constituicao",
        inteligencia="Valor de Inteligencia",
        sabedoria="Valor de Sabedoria",
        carisma="Valor de Carisma",
    )
    async def registrar(
        self,
        interaction: discord.Interaction,
        nome: app_commands.Range[str, 1, 60],
        nivel: app_commands.Range[int, 1, 20],
        forca: app_commands.Range[int, 1, 30],
        destreza: app_commands.Range[int, 1, 30],
        constituicao: app_commands.Range[int, 1, 30],
        inteligencia: app_commands.Range[int, 1, 30],
        sabedoria: app_commands.Range[int, 1, 30],
        carisma: app_commands.Range[int, 1, 30],
    ) -> None:
        atributos = {
            "FOR": forca,
            "DES": destreza,
            "CON": constituicao,
            "INT": inteligencia,
            "SAB": sabedoria,
            "CAR": carisma,
        }
        existente = await db.buscar_ficha(self.bot.db, interaction.guild_id, interaction.user.id)
        view = SeletorPericias(interaction.user.id, existente["pericias"] if existente else [])
        await interaction.response.send_message(
            f"**{nome}**, nivel {nivel}. Agora marque as pericias treinadas:",
            view=view,
            ephemeral=True,
        )
        await view.wait()
        if view.escolhidas is None:
            await interaction.edit_original_response(
                content="Tempo esgotado - rode /ficha registrar de novo.", view=None
            )
            return

        await db.salvar_ficha(
            self.bot.db,
            interaction.guild_id,
            interaction.user.id,
            nome,
            nivel,
            atributos,
            view.escolhidas,
        )
        ficha = await db.buscar_ficha(self.bot.db, interaction.guild_id, interaction.user.id)
        await interaction.edit_original_response(
            content="Ficha salva. Use /ficha combate para CA, ataque, dano e HP.",
            embed=embed_ficha(ficha, interaction.user),
            view=None,
        )

    @grupo.command(name="ver", description="Mostra a ficha com os modificadores ja calculados")
    @app_commands.describe(membro="Ver a ficha de outro jogador (opcional)")
    async def ver(
        self, interaction: discord.Interaction, membro: Optional[discord.Member] = None
    ) -> None:
        alvo = membro or interaction.user
        ficha = await db.buscar_ficha(self.bot.db, interaction.guild_id, alvo.id)
        if not ficha:
            quem = (
                "Voce ainda nao tem"
                if alvo == interaction.user
                else f"{alvo.display_name} ainda nao tem"
            )
            await interaction.response.send_message(
                f"{quem} ficha. Use /ficha registrar.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            embed=embed_ficha(ficha, alvo), ephemeral=membro is None
        )

    @grupo.command(
        name="nivel", description="Atualiza o nivel (o bonus de proficiencia se recalcula sozinho)"
    )
    async def nivel(
        self, interaction: discord.Interaction, novo_nivel: app_commands.Range[int, 1, 20]
    ) -> None:
        ok = await db.atualizar_campo(
            self.bot.db, interaction.guild_id, interaction.user.id, "nivel", novo_nivel
        )
        if not ok:
            await interaction.response.send_message(
                "Voce ainda nao tem ficha. Use /ficha registrar.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            f"Nivel {novo_nivel} | Tier {tier(novo_nivel)} | "
            f"Proficiencia {fmt(bonus_proficiencia(novo_nivel))}.",
            ephemeral=True,
        )

    @grupo.command(name="atributo", description="Atualiza um atributo apos um ASI")
    @app_commands.choices(
        atributo=[
            app_commands.Choice(name=f"{nome} ({sigla})", value=sigla)
            for sigla, nome in ATRIBUTOS.items()
        ]
    )
    async def atributo(
        self,
        interaction: discord.Interaction,
        atributo: app_commands.Choice[str],
        valor: app_commands.Range[int, 1, 30],
    ) -> None:
        coluna = db.COLUNA_ATRIBUTO[atributo.value]
        ok = await db.atualizar_campo(
            self.bot.db, interaction.guild_id, interaction.user.id, coluna, valor
        )
        if not ok:
            await interaction.response.send_message(
                "Voce ainda nao tem ficha. Use /ficha registrar.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            f"{atributo.name} agora e {valor} ({fmt(modificador(valor))}).", ephemeral=True
        )

    @grupo.command(name="pericias", description="Ajusta quais pericias sao treinadas")
    async def pericias(self, interaction: discord.Interaction) -> None:
        ficha = await db.buscar_ficha(self.bot.db, interaction.guild_id, interaction.user.id)
        if not ficha:
            await interaction.response.send_message(
                "Voce ainda nao tem ficha. Use /ficha registrar.", ephemeral=True
            )
            return
        view = SeletorPericias(interaction.user.id, ficha["pericias"])
        await interaction.response.send_message(
            "Marque as pericias treinadas:", view=view, ephemeral=True
        )
        await view.wait()
        if view.escolhidas is None:
            await interaction.edit_original_response(
                content="Tempo esgotado - nada foi alterado.", view=None
            )
            return
        await db.atualizar_pericias(
            self.bot.db, interaction.guild_id, interaction.user.id, view.escolhidas
        )
        ficha = await db.buscar_ficha(self.bot.db, interaction.guild_id, interaction.user.id)
        await interaction.edit_original_response(
            content="Pericias atualizadas.",
            embed=embed_ficha(ficha, interaction.user),
            view=None,
        )

    @grupo.command(name="combate", description="Define CA, bonus de ataque, dano da arma e HP maximo")
    async def combate(
        self,
        interaction: discord.Interaction,
        ca: app_commands.Range[int, 1, 40],
        bonus_ataque: app_commands.Range[int, -5, 30],
        dano_arma: app_commands.Range[str, 1, 20],
        hp_max: app_commands.Range[int, 1, 999],
    ) -> None:
        ficha = await db.buscar_ficha(self.bot.db, interaction.guild_id, interaction.user.id)
        if not ficha:
            await interaction.response.send_message(
                "Voce ainda nao tem ficha. Use /ficha registrar.", ephemeral=True
            )
            return
        campos = (
            ("ca", ca),
            ("bonus_ataque", bonus_ataque),
            ("dano_arma", dano_arma),
            ("hp_max", hp_max),
        )
        for coluna, valor in campos:
            await db.atualizar_campo(
                self.bot.db, interaction.guild_id, interaction.user.id, coluna, valor
            )
        ficha = await db.buscar_ficha(self.bot.db, interaction.guild_id, interaction.user.id)
        await interaction.response.send_message(
            embed=embed_ficha(ficha, interaction.user), ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Ficha(bot))
