"""Fichas digitais: cadastro, consulta e manutencao (nivel / ASI / pericias).

Um jogador pode ter varios personagens. Os comandos aceitam o nome de qual
mexer; quem so tem um nao precisa dizer nada.
"""
from __future__ import annotations

from typing import Any, Optional

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

LIMITE_PERSONAGENS = 25  # o seletor do Discord nao mostra mais que isso


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


def embed_ficha(personagem: dict[str, Any], autor: discord.abc.User) -> discord.Embed:
    nivel = personagem["nivel"]
    treinadas = personagem["pericias"]
    atributos = personagem["atributos"]
    bonus = personagem.get("bonus_pericias") or {}

    e = discord.Embed(
        title=personagem["nome"],
        description=(
            f"Nivel {nivel} | Tier {tier(nivel)} | "
            f"Proficiencia {fmt(bonus_proficiencia(nivel))}"
        ),
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
            f"{p} {fmt(mod_pericia(p, atributos, nivel, treinadas, bonus))}"
            for p in sorted(treinadas)
        ]
        e.add_field(
            name=f"Pericias treinadas ({len(treinadas)})", value=" | ".join(linhas), inline=False
        )
    else:
        e.add_field(name="Pericias treinadas", value="nenhuma - use /ficha pericias", inline=False)

    if bonus:
        # Uma pericia nao treinada tambem pode ter bonus: mostramos o total dela.
        avulsas = [
            f"{p} {fmt(bonus[p])} (total {fmt(mod_pericia(p, atributos, nivel, treinadas, bonus))})"
            for p in sorted(bonus)
        ]
        e.add_field(name="Expertises", value=" | ".join(avulsas), inline=False)
    e.add_field(
        name="Combate",
        value=(
            f"CA **{personagem['ca']}** | Ataque **{fmt(personagem['bonus_ataque'])}** | "
            f"Dano **{personagem['dano_arma']}** | HP **{personagem['hp_max']}**"
        ),
        inline=False,
    )
    e.set_footer(text="Modificadores calculados a partir do nivel e dos atributos")
    return e


class Ficha(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    grupo = app_commands.Group(name="ficha", description="Fichas dos seus personagens")

    async def _sugerir_personagens(
        self, interaction: discord.Interaction, atual: str
    ) -> list[app_commands.Choice[str]]:
        personagens = await db.listar_personagens(
            self.bot.db, interaction.guild_id, interaction.user.id
        )
        termo = atual.lower()
        return [
            app_commands.Choice(name=f"{p['nome']} (nivel {p['nivel']})", value=p["nome"])
            for p in personagens
            if termo in p["nome"].lower()
        ][:25]

    async def _resolver(
        self, interaction: discord.Interaction, nome: Optional[str]
    ) -> Optional[dict[str, Any]]:
        """Descobre em qual personagem mexer, respondendo à interação se não der."""
        personagens = await db.listar_personagens(
            self.bot.db, interaction.guild_id, interaction.user.id
        )
        if not personagens:
            await interaction.response.send_message(
                "Voce ainda nao tem personagem. Use `/ficha registrar`.", ephemeral=True
            )
            return None

        if nome:
            escolhido = await db.personagem_por_nome(
                self.bot.db, interaction.guild_id, interaction.user.id, nome
            )
            if not escolhido:
                disponiveis = ", ".join(p["nome"] for p in personagens)
                await interaction.response.send_message(
                    f"Voce nao tem nenhum personagem chamado **{nome}**. "
                    f"Os seus sao: {disponiveis}.",
                    ephemeral=True,
                )
                return None
            return escolhido

        if len(personagens) == 1:
            return personagens[0]

        disponiveis = ", ".join(p["nome"] for p in personagens)
        await interaction.response.send_message(
            f"Voce tem mais de um personagem: {disponiveis}. Diga qual no campo `personagem`.",
            ephemeral=True,
        )
        return None

    @grupo.command(
        name="registrar",
        description="Cadastra um personagem: nivel, atributos, combate e pericias",
    )
    @app_commands.describe(
        nome="Nome do personagem",
        nivel="Nivel atual (1-20)",
        forca="Valor de Forca",
        destreza="Valor de Destreza",
        constituicao="Valor de Constituicao",
        inteligencia="Valor de Inteligencia",
        sabedoria="Valor de Sabedoria",
        carisma="Valor de Carisma",
        ca="Classe de Armadura",
        bonus_ataque="Bonus de ataque da arma principal",
        dano_arma="Dado de dano da arma, ex.: 1d8+3",
        hp_maximo="Pontos de vida maximos",
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
        ca: app_commands.Range[int, 1, 40],
        bonus_ataque: app_commands.Range[int, -5, 30],
        dano_arma: app_commands.Range[str, 1, 20],
        hp_maximo: app_commands.Range[int, 1, 999],
    ) -> None:
        existentes = await db.listar_personagens(
            self.bot.db, interaction.guild_id, interaction.user.id
        )
        if len(existentes) >= LIMITE_PERSONAGENS:
            await interaction.response.send_message(
                f"Voce ja tem {LIMITE_PERSONAGENS} personagens. "
                "Apague um com `/ficha remover` antes de criar outro.",
                ephemeral=True,
            )
            return
        if any(p["nome"].lower() == nome.strip().lower() for p in existentes):
            await interaction.response.send_message(
                f"Voce ja tem um personagem chamado **{nome}**. Escolha outro nome.",
                ephemeral=True,
            )
            return

        atributos = {
            "FOR": forca,
            "DES": destreza,
            "CON": constituicao,
            "INT": inteligencia,
            "SAB": sabedoria,
            "CAR": carisma,
        }
        combate = {
            "ca": ca,
            "bonus_ataque": bonus_ataque,
            "dano_arma": dano_arma,
            "hp_max": hp_maximo,
        }
        view = SeletorPericias(interaction.user.id, [])
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

        personagem_id = await db.criar_personagem(
            self.bot.db,
            interaction.guild_id,
            interaction.user.id,
            nome,
            nivel,
            atributos,
            view.escolhidas,
            combate=combate,
        )
        if personagem_id is None:
            await interaction.edit_original_response(
                content=f"Voce ja tem um personagem chamado **{nome}**.", view=None
            )
            return

        personagem = await db.buscar_personagem(self.bot.db, personagem_id)
        total = len(existentes) + 1
        await interaction.edit_original_response(
            content=f"Personagem salvo. Voce tem {total} agora.",
            embed=embed_ficha(personagem, interaction.user),
            view=None,
        )

    @grupo.command(name="listar", description="Mostra todos os seus personagens")
    @app_commands.describe(membro="Ver os personagens de outro jogador (opcional)")
    async def listar(
        self, interaction: discord.Interaction, membro: Optional[discord.Member] = None
    ) -> None:
        alvo = membro or interaction.user
        personagens = await db.listar_personagens(self.bot.db, interaction.guild_id, alvo.id)
        if not personagens:
            quem = "Voce ainda nao tem" if alvo == interaction.user else f"{alvo.display_name} nao tem"
            await interaction.response.send_message(f"{quem} personagem.", ephemeral=True)
            return

        e = discord.Embed(
            title=f"Personagens de {alvo.display_name}", color=discord.Color.dark_gold()
        )
        for p in personagens:
            e.add_field(
                name=p["nome"],
                value=(
                    f"Nivel {p['nivel']} | Tier {tier(p['nivel'])} | "
                    f"CA {p['ca']} | HP {p['hp_max']}"
                ),
                inline=False,
            )
        e.set_footer(text=f"{len(personagens)} personagem(ns)")
        await interaction.response.send_message(embed=e, ephemeral=membro is None)

    @grupo.command(name="ver", description="Mostra a ficha com os modificadores ja calculados")
    @app_commands.describe(
        personagem="Qual personagem (opcional se voce so tem um)",
        membro="Ver a ficha de outro jogador (opcional)",
    )
    @app_commands.autocomplete(personagem=_sugerir_personagens)
    async def ver(
        self,
        interaction: discord.Interaction,
        personagem: Optional[str] = None,
        membro: Optional[discord.Member] = None,
    ) -> None:
        if membro is not None:
            personagens = await db.listar_personagens(self.bot.db, interaction.guild_id, membro.id)
            if not personagens:
                await interaction.response.send_message(
                    f"{membro.display_name} nao tem personagem.", ephemeral=True
                )
                return
            escolhido = personagens[0]
            if personagem:
                por_nome = await db.personagem_por_nome(
                    self.bot.db, interaction.guild_id, membro.id, personagem
                )
                if not por_nome:
                    await interaction.response.send_message(
                        f"{membro.display_name} nao tem **{personagem}**.", ephemeral=True
                    )
                    return
                escolhido = por_nome
            await interaction.response.send_message(embed=embed_ficha(escolhido, membro))
            return

        escolhido = await self._resolver(interaction, personagem)
        if not escolhido:
            return
        await interaction.response.send_message(
            embed=embed_ficha(escolhido, interaction.user), ephemeral=True
        )

    @grupo.command(
        name="nivel", description="Atualiza o nivel (o bonus de proficiencia se recalcula sozinho)"
    )
    @app_commands.describe(personagem="Qual personagem (opcional se voce so tem um)")
    @app_commands.autocomplete(personagem=_sugerir_personagens)
    async def nivel(
        self,
        interaction: discord.Interaction,
        novo_nivel: app_commands.Range[int, 1, 20],
        personagem: Optional[str] = None,
    ) -> None:
        escolhido = await self._resolver(interaction, personagem)
        if not escolhido:
            return
        await db.atualizar_personagem(self.bot.db, escolhido["id"], "nivel", novo_nivel)
        await interaction.response.send_message(
            f"**{escolhido['nome']}**: nivel {novo_nivel} | Tier {tier(novo_nivel)} | "
            f"Proficiencia {fmt(bonus_proficiencia(novo_nivel))}.",
            ephemeral=True,
        )

    @grupo.command(name="atributo", description="Atualiza um atributo apos um ASI")
    @app_commands.describe(personagem="Qual personagem (opcional se voce so tem um)")
    @app_commands.choices(
        atributo=[
            app_commands.Choice(name=f"{nome} ({sigla})", value=sigla)
            for sigla, nome in ATRIBUTOS.items()
        ]
    )
    @app_commands.autocomplete(personagem=_sugerir_personagens)
    async def atributo(
        self,
        interaction: discord.Interaction,
        atributo: app_commands.Choice[str],
        valor: app_commands.Range[int, 1, 30],
        personagem: Optional[str] = None,
    ) -> None:
        escolhido = await self._resolver(interaction, personagem)
        if not escolhido:
            return
        coluna = db.COLUNA_ATRIBUTO[atributo.value]
        await db.atualizar_personagem(self.bot.db, escolhido["id"], coluna, valor)
        await interaction.response.send_message(
            f"**{escolhido['nome']}**: {atributo.name} agora e {valor} "
            f"({fmt(modificador(valor))}).",
            ephemeral=True,
        )

    @grupo.command(name="pericias", description="Ajusta quais pericias sao treinadas")
    @app_commands.describe(personagem="Qual personagem (opcional se voce so tem um)")
    @app_commands.autocomplete(personagem=_sugerir_personagens)
    async def pericias(
        self, interaction: discord.Interaction, personagem: Optional[str] = None
    ) -> None:
        escolhido = await self._resolver(interaction, personagem)
        if not escolhido:
            return
        view = SeletorPericias(interaction.user.id, escolhido["pericias"])
        await interaction.response.send_message(
            f"Pericias treinadas de **{escolhido['nome']}**:", view=view, ephemeral=True
        )
        await view.wait()
        if view.escolhidas is None:
            await interaction.edit_original_response(
                content="Tempo esgotado - nada foi alterado.", view=None
            )
            return
        await db.atualizar_pericias(self.bot.db, escolhido["id"], view.escolhidas)
        atualizado = await db.buscar_personagem(self.bot.db, escolhido["id"])
        await interaction.edit_original_response(
            content="Pericias atualizadas.",
            embed=embed_ficha(atualizado, interaction.user),
            view=None,
        )

    @grupo.command(name="combate", description="Atualiza CA, ataque, dano e HP de um personagem")
    @app_commands.describe(personagem="Qual personagem (opcional se voce so tem um)")
    @app_commands.autocomplete(personagem=_sugerir_personagens)
    async def combate(
        self,
        interaction: discord.Interaction,
        ca: app_commands.Range[int, 1, 40],
        bonus_ataque: app_commands.Range[int, -5, 30],
        dano_arma: app_commands.Range[str, 1, 20],
        hp_maximo: app_commands.Range[int, 1, 999],
        personagem: Optional[str] = None,
    ) -> None:
        escolhido = await self._resolver(interaction, personagem)
        if not escolhido:
            return
        for coluna, valor in (
            ("ca", ca),
            ("bonus_ataque", bonus_ataque),
            ("dano_arma", dano_arma),
            ("hp_max", hp_maximo),
        ):
            await db.atualizar_personagem(self.bot.db, escolhido["id"], coluna, valor)
        atualizado = await db.buscar_personagem(self.bot.db, escolhido["id"])
        await interaction.response.send_message(
            embed=embed_ficha(atualizado, interaction.user), ephemeral=True
        )

    @grupo.command(
        name="expertise", description="Soma um bonus avulso a uma pericia (item, talento, etc)"
    )
    @app_commands.describe(
        pericia="Qual pericia recebe o bonus",
        bonus="Quanto somar. Use 0 para tirar o bonus.",
        personagem="Qual personagem (opcional se voce so tem um)",
    )
    @app_commands.choices(
        pericia=[app_commands.Choice(name=p, value=p) for p in sorted(PERICIAS)][:25]
    )
    @app_commands.autocomplete(personagem=_sugerir_personagens)
    async def expertise(
        self,
        interaction: discord.Interaction,
        pericia: app_commands.Choice[str],
        bonus: app_commands.Range[int, -10, 20],
        personagem: Optional[str] = None,
    ) -> None:
        escolhido = await self._resolver(interaction, personagem)
        if not escolhido:
            return
        await db.definir_bonus_pericia(self.bot.db, escolhido["id"], pericia.value, bonus)
        atualizado = await db.buscar_personagem(self.bot.db, escolhido["id"])
        if bonus:
            total = mod_pericia(
                pericia.value,
                atualizado["atributos"],
                atualizado["nivel"],
                atualizado["pericias"],
                atualizado["bonus_pericias"],
            )
            aviso = (
                f"**{escolhido['nome']}**: {pericia.value} com {fmt(bonus)} de bonus "
                f"— modificador total {fmt(total)}."
            )
        else:
            aviso = f"**{escolhido['nome']}**: bonus de {pericia.value} removido."
        await interaction.response.send_message(
            aviso, embed=embed_ficha(atualizado, interaction.user), ephemeral=True
        )

    @grupo.command(name="remover", description="Apaga um personagem seu")
    @app_commands.describe(personagem="Qual personagem apagar")
    @app_commands.autocomplete(personagem=_sugerir_personagens)
    async def remover(self, interaction: discord.Interaction, personagem: str) -> None:
        escolhido = await self._resolver(interaction, personagem)
        if not escolhido:
            return
        em_run = await db.run_viva_do_jogador(
            self.bot.db, interaction.guild_id, interaction.user.id
        )
        if em_run:
            await interaction.response.send_message(
                f"Voce esta na run #{em_run['id']}. Termine ou desista dela antes de apagar "
                "um personagem.",
                ephemeral=True,
            )
            return
        await db.remover_personagem(self.bot.db, escolhido["id"])
        await interaction.response.send_message(
            f"**{escolhido['nome']}** foi apagado.", ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Ficha(bot))
