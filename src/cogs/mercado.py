"""O mercado: a vitrine da semana, a bolsa e os cinco slots do corpo.

Fora da incursão, e de propósito: trocar de armadura no meio de uma sala
viraria uma decisão de combate, e não é isso que o mercado é. Quem está numa
run viva leva uma recusa com o número dela.

A vitrine não é guardada em lugar nenhum — é derivada de (personagem, semana)
em `src/mercado.py`. Por isso toda compra reconfere a prateleira de hoje em
vez de confiar no id que veio do autocomplete: um comando repetido da semana
passada não leva um item que já saiu de cartaz.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import discord
from discord import app_commands
from discord.ext import commands

from .. import config, database as db, itens, mercado
from .ficha import sugerir_personagens

COR = 0xC8743A

ICONE_DA_RARIDADE = {
    "comum": "⚪",
    "incomum": "🟢",
    "raro": "🔵",
    "lendario": "🟠",
}


def _icone(peca: itens.Item) -> str:
    return ICONE_DA_RARIDADE.get(peca.raridade, "·")


def _descricao(peca: itens.Item) -> str:
    return (
        f"{itens.NOME_DO_SLOT[peca.slot]} · "
        f"{itens.NOME_DA_RARIDADE[peca.raridade]}\n{peca.texto}"
    )


def embed_vitrine(
    personagem: dict[str, Any], saldo: int, semana: str, prateleira: list[itens.Item]
) -> discord.Embed:
    e = discord.Embed(
        title=f"Mercado · {personagem['nome']}",
        description=(
            f"**{saldo}** de ouro na bolsa.\n"
            f"A prateleira é desta semana ({semana}) e é só deste personagem. "
            "Ela vira na segunda, junto com a vaga de incursão."
        ),
        color=COR,
    )
    for peca in prateleira:
        e.add_field(
            name=f"{_icone(peca)} {peca.nome} — {peca.custo} de ouro",
            value=_descricao(peca),
            inline=False,
        )
    if not prateleira:
        e.add_field(name="Vazia", value="Nada à venda nesta semana.", inline=False)
    e.set_footer(text="/mercado comprar para levar · /mercado bolsa para vestir")
    return e


def embed_bolsa(
    personagem: dict[str, Any],
    saldo: int,
    vestido: dict[str, str],
    bolsa: dict[str, int],
) -> discord.Embed:
    e = discord.Embed(
        title=f"Bolsa e equipamento · {personagem['nome']}",
        description=(
            f"**{saldo}** de ouro · CA **{personagem.get('ca') or 0}** · "
            f"acerto **{personagem.get('bonus_ataque') or 0:+d}**"
        ),
        color=COR,
    )
    corpo = []
    for slot in itens.SLOTS:
        peca = itens.item(vestido.get(slot))
        if peca is None:
            corpo.append(f"**{itens.NOME_DO_SLOT[slot]}** — vazio")
        else:
            corpo.append(
                f"**{itens.NOME_DO_SLOT[slot]}** — {_icone(peca)} {peca.nome}\n"
                f"　{peca.texto}"
            )
    e.add_field(name="No corpo", value="\n".join(corpo), inline=False)

    guardados = []
    for item_id, quantos in sorted(bolsa.items()):
        peca = itens.item(item_id)
        if peca is None:
            continue
        vezes = f" ×{quantos}" if quantos > 1 else ""
        guardados.append(
            f"{_icone(peca)} **{peca.nome}**{vezes} · "
            f"{itens.NOME_DO_SLOT[peca.slot]}"
        )
    e.add_field(
        name="Na bolsa",
        value="\n".join(guardados) if guardados else "Nada guardado.",
        inline=False,
    )
    e.set_footer(text="/mercado equipar para vestir · /mercado desequipar para tirar")
    return e


class Mercado(commands.Cog):
    """Ouro, vitrine e equipamento. Tudo fora da incursão."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    grupo = app_commands.Group(
        name="mercado", description="Ouro, itens e equipamento dos seus personagens"
    )

    # ------------------------------------------------------------ bastidores

    def _semana(self) -> str:
        return mercado.semana_de(datetime.now(config.FUSO))

    async def _sugerir_personagens(
        self, interaction: discord.Interaction, atual: str
    ) -> list[app_commands.Choice[str]]:
        return await sugerir_personagens(self.bot.db, interaction, atual)

    async def _resolver(
        self, interaction: discord.Interaction, nome: Optional[str]
    ) -> Optional[dict[str, Any]]:
        """Em qual personagem mexer. Responde à interação quando não dá."""
        personagens = await db.listar_personagens(
            self.bot.db, interaction.guild_id, interaction.user.id
        )
        if not personagens:
            await interaction.response.send_message(
                "Você ainda não tem personagem. Use `/ficha registrar`.",
                ephemeral=True,
            )
            return None
        if nome:
            escolhido = await db.personagem_por_nome(
                self.bot.db, interaction.guild_id, interaction.user.id, nome
            )
            if not escolhido:
                await interaction.response.send_message(
                    f"Você não tem personagem chamado **{nome}**.", ephemeral=True
                )
                return None
            return escolhido
        if len(personagens) > 1:
            lista = ", ".join(f"**{p['nome']}**" for p in personagens)
            await interaction.response.send_message(
                f"Você tem mais de um personagem: {lista}. Diga qual.",
                ephemeral=True,
            )
            return None
        return personagens[0]

    async def _quieto(self, interaction: discord.Interaction) -> Optional[dict[str, Any]]:
        """O personagem para um autocomplete: o único, ou nada. Nunca responde.

        Autocomplete não pode mandar mensagem, e com mais de um personagem não
        há como saber de qual é a lista — aí ela sai vazia e o jogador digita
        o nome do personagem primeiro.
        """
        personagens = await db.listar_personagens(
            self.bot.db, interaction.guild_id, interaction.user.id
        )
        return personagens[0] if len(personagens) == 1 else None

    async def _fora_de_incursao(self, interaction: discord.Interaction) -> bool:
        """False, e já recusou, se o jogador está numa run viva."""
        viva = await db.run_viva_do_jogador(
            self.bot.db, interaction.guild_id, interaction.user.id
        )
        if viva:
            await interaction.response.send_message(
                f"O mercado fecha durante a incursão. Você está na run "
                f"#{viva['id']} — termine ou desista antes de comprar.",
                ephemeral=True,
            )
            return False
        return True

    # ----------------------------------------------------------------- olhar

    @grupo.command(name="vitrine", description="O que está à venda para você nesta semana")
    @app_commands.describe(personagem="Qual personagem (opcional se você só tem um)")
    @app_commands.autocomplete(personagem=_sugerir_personagens)
    async def vitrine(
        self, interaction: discord.Interaction, personagem: Optional[str] = None
    ) -> None:
        escolhido = await self._resolver(interaction, personagem)
        if not escolhido:
            return
        semana = self._semana()
        await interaction.response.send_message(
            embed=embed_vitrine(
                escolhido,
                await db.ouro(self.bot.db, escolhido["id"]),
                semana,
                mercado.vitrine(escolhido["id"], semana),
            ),
            ephemeral=True,
        )

    @grupo.command(name="bolsa", description="O que você tem vestido e guardado")
    @app_commands.describe(personagem="Qual personagem (opcional se você só tem um)")
    @app_commands.autocomplete(personagem=_sugerir_personagens)
    async def bolsa(
        self, interaction: discord.Interaction, personagem: Optional[str] = None
    ) -> None:
        escolhido = await self._resolver(interaction, personagem)
        if not escolhido:
            return
        await interaction.response.send_message(
            embed=embed_bolsa(
                escolhido,
                await db.ouro(self.bot.db, escolhido["id"]),
                await db.equipamento(self.bot.db, escolhido["id"]),
                await db.itens_na_bolsa(self.bot.db, escolhido["id"]),
            ),
            ephemeral=True,
        )

    @grupo.command(name="ouro", description="Seu saldo e de onde ele veio")
    @app_commands.describe(personagem="Qual personagem (opcional se você só tem um)")
    @app_commands.autocomplete(personagem=_sugerir_personagens)
    async def ouro(
        self, interaction: discord.Interaction, personagem: Optional[str] = None
    ) -> None:
        escolhido = await self._resolver(interaction, personagem)
        if not escolhido:
            return
        saldo = await db.ouro(self.bot.db, escolhido["id"])
        extrato = await db.extrato_de_ouro(self.bot.db, escolhido["id"])
        linhas = [
            f"`{lanc['ouro']:+5d}` {lanc['motivo']}" for lanc in extrato
        ] or ["Nenhum lançamento ainda. Ouro vem de sala superada e de incursão fechada."]
        e = discord.Embed(
            title=f"Ouro · {escolhido['nome']}",
            description=f"**{saldo}** de ouro.",
            color=COR,
        )
        e.add_field(name="Últimos lançamentos", value="\n".join(linhas), inline=False)
        await interaction.response.send_message(embed=e, ephemeral=True)

    # --------------------------------------------------------------- comprar

    async def _sugerir_vitrine(
        self, interaction: discord.Interaction, atual: str
    ) -> list[app_commands.Choice[str]]:
        escolhido = await self._quieto(interaction)
        if not escolhido:
            return []
        termo = atual.lower()
        return [
            app_commands.Choice(
                name=f"{peca.nome} — {peca.custo} de ouro", value=peca.id
            )
            for peca in mercado.vitrine(escolhido["id"], self._semana())
            if termo in peca.nome.lower()
        ][:25]

    @grupo.command(name="comprar", description="Leva um item da sua vitrine da semana")
    @app_commands.describe(
        item="O que comprar (só o que está na sua vitrine desta semana)",
        personagem="Qual personagem (opcional se você só tem um)",
    )
    @app_commands.autocomplete(item=_sugerir_vitrine, personagem=_sugerir_personagens)
    async def comprar(
        self,
        interaction: discord.Interaction,
        item: str,
        personagem: Optional[str] = None,
    ) -> None:
        if not await self._fora_de_incursao(interaction):
            return
        escolhido = await self._resolver(interaction, personagem)
        if not escolhido:
            return
        peca = itens.item(item)
        semana = self._semana()
        # A prateleira de HOJE, e nao o id que chegou: o comando pode ter sido
        # copiado de uma semana em que o item estava a venda.
        if peca is None or not mercado.esta_na_vitrine(
            escolhido["id"], semana, peca.id
        ):
            await interaction.response.send_message(
                "Esse item não está na vitrine desta semana. "
                "Veja o que tem com `/mercado vitrine`.",
                ephemeral=True,
            )
            return
        if not await db.comprar(self.bot.db, escolhido["id"], peca.id, peca.custo):
            saldo = await db.ouro(self.bot.db, escolhido["id"])
            await interaction.response.send_message(
                f"**{peca.nome}** custa {peca.custo} e você tem {saldo}. "
                f"Faltam **{peca.custo - saldo}** de ouro.",
                ephemeral=True,
            )
            return
        saldo = await db.ouro(self.bot.db, escolhido["id"])
        await interaction.response.send_message(
            f"{_icone(peca)} **{escolhido['nome']}** compra **{peca.nome}** por "
            f"{peca.custo}. Sobram **{saldo}** de ouro.\n"
            f"Está na bolsa — use `/mercado equipar` para vestir."
        )

    # --------------------------------------------------------------- vestir

    async def _sugerir_bolsa(
        self, interaction: discord.Interaction, atual: str
    ) -> list[app_commands.Choice[str]]:
        escolhido = await self._quieto(interaction)
        if not escolhido:
            return []
        termo = atual.lower()
        guardados = await db.itens_na_bolsa(self.bot.db, escolhido["id"])
        saida = []
        for item_id in guardados:
            peca = itens.item(item_id)
            if peca is None or termo not in peca.nome.lower():
                continue
            saida.append(
                app_commands.Choice(
                    name=f"{peca.nome} — {itens.NOME_DO_SLOT[peca.slot]}",
                    value=peca.id,
                )
            )
        return saida[:25]

    @grupo.command(name="equipar", description="Veste um item da sua bolsa")
    @app_commands.describe(
        item="O que vestir (tem de estar na bolsa)",
        personagem="Qual personagem (opcional se você só tem um)",
    )
    @app_commands.autocomplete(item=_sugerir_bolsa, personagem=_sugerir_personagens)
    async def equipar(
        self,
        interaction: discord.Interaction,
        item: str,
        personagem: Optional[str] = None,
    ) -> None:
        if not await self._fora_de_incursao(interaction):
            return
        escolhido = await self._resolver(interaction, personagem)
        if not escolhido:
            return
        peca = itens.item(item)
        if peca is None:
            await interaction.response.send_message(
                "Esse item não existe.", ephemeral=True
            )
            return
        # O slot sai do item, nunca de quem pediu: e o slot que impede o stack,
        # e aceitar um slot digitado seria aceitar burlar o dominio.
        vestiu, anterior = await db.equipar(
            self.bot.db, escolhido["id"], peca.id, peca.slot
        )
        if not vestiu:
            await interaction.response.send_message(
                f"**{peca.nome}** não está na sua bolsa. "
                f"Veja o que você tem com `/mercado bolsa`.",
                ephemeral=True,
            )
            return
        atualizado = await db.buscar_personagem(self.bot.db, escolhido["id"])
        saiu = itens.item(anterior)
        troca = f" {saiu.nome} volta para a bolsa." if saiu else ""
        await interaction.response.send_message(
            f"{_icone(peca)} **{atualizado['nome']}** veste **{peca.nome}** "
            f"({itens.NOME_DO_SLOT[peca.slot]}).{troca}\n"
            f"CA **{atualizado['ca']}** · acerto **{atualizado['bonus_ataque']:+d}**"
        )

    @grupo.command(name="desequipar", description="Tira o item de um slot")
    @app_commands.describe(
        slot="Qual lugar do corpo",
        personagem="Qual personagem (opcional se você só tem um)",
    )
    @app_commands.choices(
        slot=[
            app_commands.Choice(name=itens.NOME_DO_SLOT[s], value=s)
            for s in itens.SLOTS
        ]
    )
    @app_commands.autocomplete(personagem=_sugerir_personagens)
    async def desequipar(
        self,
        interaction: discord.Interaction,
        slot: app_commands.Choice[str],
        personagem: Optional[str] = None,
    ) -> None:
        if not await self._fora_de_incursao(interaction):
            return
        escolhido = await self._resolver(interaction, personagem)
        if not escolhido:
            return
        saiu = await db.desequipar(self.bot.db, escolhido["id"], slot.value)
        peca = itens.item(saiu)
        if peca is None:
            await interaction.response.send_message(
                f"Não há nada em {itens.NOME_DO_SLOT[slot.value]}.", ephemeral=True
            )
            return
        atualizado = await db.buscar_personagem(self.bot.db, escolhido["id"])
        await interaction.response.send_message(
            f"**{atualizado['nome']}** tira **{peca.nome}** e guarda na bolsa.\n"
            f"CA **{atualizado['ca']}** · acerto **{atualizado['bonus_ataque']:+d}**"
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Mercado(bot))
