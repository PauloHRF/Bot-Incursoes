"""Fichas digitais: cadastro por classe, consulta e manutencao.

O personagem e a classe: o jogador escolhe uma e as pericias com proficiencia,
e os numeros (HP, CA, acerto, dano) saem da tabela da classe no tier atual.
Um jogador pode ter varios personagens. Os comandos aceitam o nome de qual
mexer; quem so tem um nao precisa dizer nada.
"""
from __future__ import annotations

from typing import Any, Optional

import discord
from discord import app_commands
from discord.ext import commands

from .. import classes as cl, database as db
from ..embeds import url_de_imagem
from ..rules import NIVEL_MAXIMO, PERICIAS, fmt, mod_pericia, tier

LIMITE_PERSONAGENS = 25  # o seletor do Discord nao mostra mais que isso


class SeletorPericias(discord.ui.View):
    """Menu das pericias com proficiencia, limitado ao que a classe concede."""

    def __init__(self, dono_id: int, marcadas: list[str], limite: int):
        super().__init__(timeout=300)
        self.dono_id = dono_id
        self.limite = limite
        self.escolhidas: Optional[list[str]] = None
        opcoes = [
            discord.SelectOption(label=p, default=p in marcadas) for p in PERICIAS
        ]
        self.menu = discord.ui.Select(
            placeholder=f"Escolha ate {limite} pericia(s) com proficiencia",
            min_values=0,
            max_values=min(limite, len(opcoes)),
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


class SeletorEscolha(discord.ui.View):
    """As decisoes de tier que o personagem ainda nao tomou."""

    def __init__(self, cog: "Ficha", personagem_id: int, pendencias: list):
        super().__init__(timeout=300)
        self.cog = cog
        self.personagem_id = personagem_id
        menu = discord.ui.Select(
            placeholder="Qual decisao?",
            options=[
                discord.SelectOption(
                    label=f"T{tier_da}: {h.nome}"[:100], value=h.id, description=h.texto[:100]
                )
                for tier_da, h in pendencias[:25]
            ],
        )
        menu.callback = self._escolher
        self.menu = menu
        self.add_item(menu)

    async def _escolher(self, interaction: discord.Interaction) -> None:
        self.stop()
        await self.cog.abrir_escolha(interaction, self.personagem_id, self.menu.values[0])


class SeletorOpcao(discord.ui.View):
    """Uma decisao de caminho unico: Fighting Style, a do Xama."""

    def __init__(self, cog: "Ficha", personagem_id: int, habilidade):
        super().__init__(timeout=300)
        self.cog = cog
        self.personagem_id = personagem_id
        self.habilidade = habilidade
        menu = discord.ui.Select(
            placeholder=f"{habilidade.nome}: escolha um",
            options=[
                discord.SelectOption(
                    label=o["nome"][:100], value=o["id"], description=o["texto"][:100]
                )
                for o in habilidade.escolha["opcoes"]
            ],
        )
        menu.callback = self._escolher
        self.menu = menu
        self.add_item(menu)

    async def _escolher(self, interaction: discord.Interaction) -> None:
        self.stop()
        await self.cog.gravar_escolha(
            interaction, self.personagem_id, self.habilidade, self.menu.values[0]
        )


class SeletorPericiasDaEscolha(discord.ui.View):
    """Uma decisao que pede pericias: Expertise, Primal Knowledge."""

    def __init__(self, cog: "Ficha", personagem_id: int, habilidade, opcoes: list[str]):
        super().__init__(timeout=300)
        self.cog = cog
        self.personagem_id = personagem_id
        self.habilidade = habilidade
        quantas = habilidade.escolha.get("quantidade", 1)
        menu = discord.ui.Select(
            placeholder=f"{habilidade.nome}: escolha {quantas}",
            min_values=1,
            max_values=min(quantas, len(opcoes)),
            options=[discord.SelectOption(label=p) for p in opcoes[:25]],
        )
        menu.callback = self._escolher
        self.menu = menu
        self.add_item(menu)

    async def _escolher(self, interaction: discord.Interaction) -> None:
        self.stop()
        await self.cog.gravar_escolha(
            interaction, self.personagem_id, self.habilidade, list(self.menu.values)
        )


def embed_ficha(personagem: dict[str, Any], autor: discord.abc.User) -> discord.Embed:
    nivel = personagem["nivel"]
    treinadas = personagem["pericias"]
    bonus = personagem.get("bonus_pericias") or {}
    classe = cl.classe(personagem.get("classe"))
    numeros = personagem.get("numeros")

    e = discord.Embed(
        title=personagem["nome"],
        description=(
            f"{classe.nome if classe else personagem.get('classe')} | "
            f"Nivel {nivel} | Tier {tier(nivel)}"
        ),
        color=discord.Color.dark_gold(),
    )
    e.set_author(name=autor.display_name, icon_url=autor.display_avatar.url)
    if numeros is None:
        e.add_field(
            name="Classe desconhecida",
            value="Esta ficha aponta para uma classe que o bot nao conhece mais.",
            inline=False,
        )
        return e

    # CA e acerto saem do personagem, nao da tabela: o Fighting Style ja entrou.
    e.add_field(
        name="Combate",
        value=(
            f"HP **{numeros.hp}** | CA **{personagem.get('ca', numeros.ca)}** | "
            f"Acerto **{fmt(personagem.get('bonus_ataque', numeros.acerto))}** | "
            f"Dano **{numeros.dano}**"
        ),
        inline=False,
    )
    if treinadas:
        efeitos = personagem.get("efeitos")
        linhas = [
            f"{p} {fmt(mod_pericia(p, numeros, treinadas, bonus, efeitos))}"
            for p in sorted(treinadas)
        ]
        e.add_field(
            name=f"Proficiencias ({len(treinadas)}/{numeros.pericias})",
            value=" | ".join(linhas),
            inline=False,
        )
    else:
        e.add_field(
            name=f"Proficiencias (0/{numeros.pericias})",
            value="nenhuma - use /ficha pericias",
            inline=False,
        )

    _campo_habilidades(e, personagem)
    _campo_escolhas(e, personagem)

    if bonus:
        # Uma pericia sem proficiencia tambem pode ter bonus: mostramos o total.
        avulsas = [
            f"{p} {fmt(bonus[p])} (total "
            f"{fmt(mod_pericia(p, numeros, treinadas, bonus, personagem.get('efeitos')))})"
            for p in sorted(bonus)
        ]
        e.add_field(name="Expertises", value=" | ".join(avulsas), inline=False)

    retrato = url_de_imagem(personagem.get("imagem"))
    if retrato:
        e.set_thumbnail(url=retrato)
    return _rodape_da_ficha(e, numeros, nivel)


ICONE_HABILIDADE = {cl.PASSIVA: "⚙️", cl.ATIVA: "⚡", cl.ESCOLHA: "❓"}


def _campo_habilidades(e: discord.Embed, personagem: dict[str, Any]) -> None:
    """As habilidades que o personagem ja tem, por tier.

    O icone diz se o bot aplica sozinho, se o jogador aciona ou se ha algo a
    decidir. O que o bot ainda nao sabe resolver sai marcado.
    """
    ganhas = personagem.get("habilidades") or []
    if not ganhas:
        return
    linhas = []
    for tier_da_habilidade, habilidade in ganhas:
        icone = ICONE_HABILIDADE.get(habilidade.tipo, "")
        pendente = "" if habilidade.automatica else " *(em breve)*"
        linhas.append(
            f"{icone} **{habilidade.nome}** (T{tier_da_habilidade}) — "
            f"{habilidade.texto}{pendente}"
        )
    texto = "\n".join(linhas)
    if len(texto) > 1024:
        texto = texto[:1000].rsplit("\n", 1)[0] + "\n…"
    e.add_field(name=f"Habilidades ({len(ganhas)})", value=texto, inline=False)


def _campo_escolhas(e: discord.Embed, personagem: dict[str, Any]) -> None:
    """O que o jogador ja decidiu, e o que ainda falta decidir."""
    feitas = personagem.get("escolhas") or {}
    pendencias = personagem.get("pendencias") or []
    linhas = []
    for _tier, habilidade in personagem.get("habilidades") or []:
        valor = feitas.get(habilidade.id)
        if not valor or not habilidade.decidivel:
            continue
        if isinstance(valor, list):
            escrito = ", ".join(valor)
        else:
            opcao = next(
                (o for o in habilidade.escolha.get("opcoes", []) if o["id"] == valor),
                None,
            )
            escrito = opcao["nome"] if opcao else str(valor)
        linhas.append(f"**{habilidade.nome}**: {escrito}")
    for _tier, habilidade in pendencias:
        linhas.append(f"**{habilidade.nome}**: *a decidir* — `/ficha escolhas`")
    if linhas:
        e.add_field(name="Escolhas", value="\n".join(linhas), inline=False)


def _rodape_da_ficha(e: discord.Embed, numeros, nivel: int) -> discord.Embed:
    resto = (
        f"Proximo tier no nivel {tier(nivel) * 2 + 1}"
        if nivel < NIVEL_MAXIMO
        else "Nivel maximo"
    )
    e.set_footer(
        text=(
            f"Teste de pericia: {fmt(numeros.bonus_pericia)}, "
            f"{fmt(numeros.bonus_proficiencia)} com proficiencia | {resto}"
        )
    )
    return e


class Ficha(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    grupo = app_commands.Group(name="ficha", description="Fichas dos seus personagens")

    async def _anunciar(
        self,
        interaction: discord.Interaction,
        texto: str,
        embed: Optional[discord.Embed] = None,
    ) -> None:
        """Avisa o canal. O grupo acompanha quem entrou e quem mudou de ficha."""
        canal = interaction.channel
        if canal is None:
            return
        try:
            if embed is not None:
                await canal.send(texto, embed=embed)
            else:
                await canal.send(texto)
        except discord.HTTPException:
            pass

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
        description="Cria um personagem: nome, classe e as pericias com proficiencia",
    )
    @app_commands.describe(
        nome="Nome do personagem",
        classe="Qual classe. Todo personagem comeca no nivel 1.",
        imagem="Link do retrato (opcional, http ou https)",
    )
    @app_commands.choices(
        classe=[
            app_commands.Choice(name=c.nome, value=c.id)
            for c in sorted(cl.CLASSES.values(), key=lambda c: c.nome)
        ]
    )
    async def registrar(
        self,
        interaction: discord.Interaction,
        nome: app_commands.Range[str, 1, 60],
        classe: app_commands.Choice[str],
        imagem: Optional[app_commands.Range[str, 1, 500]] = None,
    ) -> None:
        escolhida = cl.classe(classe.value)
        if escolhida is None:
            await interaction.response.send_message(
                f"A classe **{classe.name}** ainda nao esta pronta. "
                f"Por enquanto da para jogar de: {self._classes_prontas()}.",
                ephemeral=True,
            )
            return

        retrato = url_de_imagem(imagem)
        if imagem and not retrato:
            await interaction.response.send_message(
                "O link do retrato precisa comecar com http:// ou https://.", ephemeral=True
            )
            return

        nome = nome.strip()
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
        if any(p["nome"].lower() == nome.lower() for p in existentes):
            await interaction.response.send_message(
                f"Voce ja tem um personagem chamado **{nome}**. Escolha outro nome.",
                ephemeral=True,
            )
            return

        numeros = escolhida.numeros(1)
        view = SeletorPericias(interaction.user.id, [], numeros.pericias)
        await interaction.response.send_message(
            f"**{nome}**, {escolhida.nome} de nivel 1 — HP {numeros.hp}, CA {numeros.ca}, "
            f"acerto {fmt(numeros.acerto)}, dano {numeros.dano}.\n"
            f"Agora escolha ate **{numeros.pericias}** pericia(s) com proficiencia:",
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
            escolhida.id,
            view.escolhidas,
            imagem=retrato,
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
        await self._anunciar(
            interaction,
            f"📜 {interaction.user.mention} registrou **{personagem['nome']}**, "
            f"{escolhida.nome} de nivel 1.",
            embed=embed_ficha(personagem, interaction.user),
        )

    @staticmethod
    def _classes_prontas() -> str:
        return ", ".join(sorted(c.nome for c in cl.CLASSES.values()))

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

    @grupo.command(name="upar", description="Sobe um nivel do personagem")
    @app_commands.describe(personagem="Qual personagem (opcional se voce so tem um)")
    @app_commands.autocomplete(personagem=_sugerir_personagens)
    async def upar(
        self, interaction: discord.Interaction, personagem: Optional[str] = None
    ) -> None:
        escolhido = await self._resolver(interaction, personagem)
        if not escolhido:
            return
        antes = escolhido["nivel"]
        if antes >= NIVEL_MAXIMO:
            await interaction.response.send_message(
                f"**{escolhido['nome']}** ja esta no nivel maximo ({NIVEL_MAXIMO}).",
                ephemeral=True,
            )
            return

        classe = cl.classe(escolhido.get("classe"))
        if classe is None:
            await interaction.response.send_message(
                "Nao reconheco a classe desta ficha.", ephemeral=True
            )
            return

        depois = antes + 1
        await db.atualizar_personagem(self.bot.db, escolhido["id"], "nivel", depois)
        atualizado = await db.buscar_personagem(self.bot.db, escolhido["id"])

        velhos, novos = classe.numeros(antes), classe.numeros(depois)
        linhas = [
            f"📈 {interaction.user.mention} subiu **{escolhido['nome']}** "
            f"para o **nivel {depois}** (tier {tier(depois)})."
        ]
        if novos is not velhos:
            mudou = [
                f"{rotulo} {antigo} → **{novo}**"
                for rotulo, antigo, novo in (
                    ("HP", velhos.hp, novos.hp),
                    ("CA", velhos.ca, novos.ca),
                    ("Acerto", fmt(velhos.acerto), fmt(novos.acerto)),
                    ("Dano", velhos.dano, novos.dano),
                )
                if antigo != novo
            ]
            if mudou:
                linhas.append("Subiu de tier: " + " | ".join(mudou) + ".")
            novas = classe.habilidades_do_tier(tier(depois))
            if novas:
                linhas.append(
                    "Habilidade(s) novas: "
                    + " | ".join(f"**{h.nome}** — {h.texto}" for h in novas)
                )
            # As proficiencias ganhas por escolha nao contam na cota da classe.
            proprias = [
                pericia
                for pericia in atualizado["pericias"]
                if pericia not in (atualizado.get("pericias_extras") or [])
            ]
            sobrando = novos.pericias - len(proprias)
            if sobrando > 0:
                linhas.append(
                    f"Voce pode escolher mais **{sobrando}** pericia(s): use `/ficha pericias`."
                )
        else:
            proximo = tier(antes) * 2 + 1
            linhas.append(f"Os numeros sobem no nivel {proximo}, quando o tier virar.")

        pendencias = atualizado.get("pendencias") or []
        if pendencias:
            quais = " | ".join(f"**{h.nome}**" for _t, h in pendencias)
            linhas.append(f"Decisao pendente: {quais} — use `/ficha escolhas`.")

        await interaction.response.send_message(
            "\n".join(linhas), embed=embed_ficha(atualizado, interaction.user)
        )

    @grupo.command(
        name="pericias", description="Escolhe as pericias com proficiencia"
    )
    @app_commands.describe(personagem="Qual personagem (opcional se voce so tem um)")
    @app_commands.autocomplete(personagem=_sugerir_personagens)
    async def pericias(
        self, interaction: discord.Interaction, personagem: Optional[str] = None
    ) -> None:
        escolhido = await self._resolver(interaction, personagem)
        if not escolhido:
            return
        numeros = escolhido.get("numeros")
        if numeros is None:
            await interaction.response.send_message(
                "Nao reconheco a classe desta ficha.", ephemeral=True
            )
            return
        view = SeletorPericias(interaction.user.id, escolhido["pericias"], numeros.pericias)
        await interaction.response.send_message(
            f"Proficiencias de **{escolhido['nome']}** "
            f"({escolhido['classe']}, ate {numeros.pericias}):",
            view=view,
            ephemeral=True,
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
        await self._anunciar(
            interaction,
            f"🎓 {interaction.user.mention} atualizou as proficiencias de "
            f"**{atualizado['nome']}** ({len(atualizado['pericias'])}/{numeros.pericias}).",
            embed=embed_ficha(atualizado, interaction.user),
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
                atualizado["numeros"],
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
            f"✨ {interaction.user.mention} — {aviso}",
            embed=embed_ficha(atualizado, interaction.user),
        )

    # ------------------------------------------------------- escolhas

    @grupo.command(
        name="escolhas", description="Decide as escolhas de tier que ficaram pendentes"
    )
    @app_commands.describe(personagem="Qual personagem (opcional se voce so tem um)")
    @app_commands.autocomplete(personagem=_sugerir_personagens)
    async def escolhas(
        self, interaction: discord.Interaction, personagem: Optional[str] = None
    ) -> None:
        escolhido = await self._resolver(interaction, personagem)
        if not escolhido:
            return
        pendencias = escolhido.get("pendencias") or []
        if not pendencias:
            await interaction.response.send_message(
                f"**{escolhido['nome']}** nao tem nenhuma decisao pendente.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            f"**{escolhido['nome']}** tem {len(pendencias)} decisao(oes) para tomar:",
            view=SeletorEscolha(self, escolhido["id"], pendencias),
            ephemeral=True,
        )

    async def abrir_escolha(
        self, interaction: discord.Interaction, personagem_id: int, habilidade_id: str
    ) -> None:
        """Segundo passo: mostra as opcoes daquela decisao."""
        personagem = await db.buscar_personagem(self.bot.db, personagem_id)
        if not personagem or personagem["user_id"] != interaction.user.id:
            await interaction.response.send_message("Esse personagem nao e seu.", ephemeral=True)
            return
        habilidade = next(
            (h for _t, h in personagem.get("pendencias") or [] if h.id == habilidade_id),
            None,
        )
        if habilidade is None:
            await interaction.response.send_message(
                "Essa decisao ja foi tomada.", ephemeral=True
            )
            return

        forma = habilidade.escolha
        if forma["tipo"] == "opcao":
            await interaction.response.send_message(
                f"**{habilidade.nome}** — {habilidade.texto}",
                view=SeletorOpcao(self, personagem_id, habilidade),
                ephemeral=True,
            )
            return

        if forma.get("entre") == "proficientes":
            opcoes = [
                p for p in personagem["pericias"]
                if p not in (personagem["efeitos"] or {}).get("expertise", [])
            ]
            if not opcoes:
                await interaction.response.send_message(
                    "Escolha as proficiencias primeiro, com `/ficha pericias`.",
                    ephemeral=True,
                )
                return
        else:
            opcoes = [p for p in PERICIAS if p not in personagem["pericias"]]

        await interaction.response.send_message(
            f"**{habilidade.nome}** — {habilidade.texto}",
            view=SeletorPericiasDaEscolha(self, personagem_id, habilidade, opcoes),
            ephemeral=True,
        )

    async def gravar_escolha(
        self, interaction: discord.Interaction, personagem_id: int, habilidade, valor
    ) -> None:
        """Ultimo passo: grava e mostra a ficha ja com a decisao valendo."""
        await db.definir_escolha(self.bot.db, personagem_id, habilidade.id, valor)
        atualizado = await db.buscar_personagem(self.bot.db, personagem_id)
        escrito = valor if isinstance(valor, str) else ", ".join(valor)
        if habilidade.escolha["tipo"] == "opcao":
            opcao = next(
                (o for o in habilidade.escolha["opcoes"] if o["id"] == valor), None
            )
            escrito = f"{opcao['nome']} ({opcao['texto']})" if opcao else valor
        texto = (
            f"\U0001f9ed {interaction.user.mention} decidiu **{habilidade.nome}** de "
            f"**{atualizado['nome']}**: {escrito}."
        )
        await interaction.response.send_message(texto, ephemeral=True)
        await self._anunciar(
            interaction, texto, embed=embed_ficha(atualizado, interaction.user)
        )

    @grupo.command(name="imagem", description="Associa um retrato ao personagem")
    @app_commands.describe(
        link="URL da imagem (http ou https). Deixe vazio para tirar o retrato.",
        personagem="Qual personagem (opcional se voce so tem um)",
    )
    @app_commands.autocomplete(personagem=_sugerir_personagens)
    async def imagem(
        self,
        interaction: discord.Interaction,
        link: Optional[app_commands.Range[str, 1, 500]] = None,
        personagem: Optional[str] = None,
    ) -> None:
        escolhido = await self._resolver(interaction, personagem)
        if not escolhido:
            return
        retrato = url_de_imagem(link)
        if link and not retrato:
            await interaction.response.send_message(
                "O link precisa comecar com http:// ou https:// e nao pode ter espacos.",
                ephemeral=True,
            )
            return

        await db.atualizar_personagem(self.bot.db, escolhido["id"], "imagem", retrato)
        atualizado = await db.buscar_personagem(self.bot.db, escolhido["id"])
        if retrato:
            aviso = f"🖼️ {interaction.user.mention} deu um rosto a **{escolhido['nome']}**."
        else:
            aviso = f"🖼️ {interaction.user.mention} tirou o retrato de **{escolhido['nome']}**."
        await interaction.response.send_message(
            aviso, embed=embed_ficha(atualizado, interaction.user)
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
            f"🗑️ {interaction.user.mention} apagou o personagem **{escolhido['nome']}**."
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Ficha(bot))
