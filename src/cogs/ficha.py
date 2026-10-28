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

from .. import classes as cl, database as db, retratos
from ..embeds import url_de_imagem
from ..rules import (
    ATRIBUTOS,
    PERICIAS,
    TIER_MAXIMO,
    fmt,
    mod_pericia,
    nivel_do_tier,
    tier,
)

LIMITE_PERSONAGENS = 25  # o seletor do Discord nao mostra mais que isso


class DonoDaFicha(discord.ui.View):
    """Base das views de ficha: so o dono mexe."""

    def __init__(self, dono_id: int, timeout: int = 300):
        super().__init__(timeout=timeout)
        self.dono_id = dono_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.dono_id:
            await interaction.response.send_message("Essa ficha nao e sua.", ephemeral=True)
            return False
        return True


class SeletorPericias(DonoDaFicha):
    """Menu das pericias com proficiencia, limitado ao que a classe concede."""

    def __init__(self, dono_id: int, marcadas: list[str], limite: int):
        super().__init__(dono_id)
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

    async def _escolher(self, interaction: discord.Interaction) -> None:
        self.escolhidas = list(self.menu.values)
        self.stop()
        await interaction.response.defer()


class SeletorOpcao(DonoDaFicha):
    """Uma decisao de caminho unico: Fighting Style, a do Xama."""

    def __init__(self, cog: "Ficha", personagem_id: int, habilidade, dono_id: int = 0):
        super().__init__(dono_id)
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


class SeletorPericiasDaEscolha(DonoDaFicha):
    """Uma decisao que pede pericias: Expertise, Primal Knowledge."""

    def __init__(
        self, cog: "Ficha", personagem_id: int, habilidade, opcoes: list[str], dono_id: int = 0
    ):
        super().__init__(dono_id)
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


class SeletorPericiasDoTier(DonoDaFicha):
    """As proficiencias novas que a subida de tier abriu.

    Grava no clique, como as outras views de decisao — e nao com `view.wait()`
    no meio do comando. Esperar ali prende o handler ate o timeout: no bot o
    `upar` ficaria pendurado, e na suite de testes a rodada inteira parava,
    porque ninguem responde ao menu.
    """

    def __init__(
        self, cog: "Ficha", personagem_id: int, dono_id: int,
        marcadas: list[str], limite: int,
    ):
        super().__init__(dono_id)
        self.cog = cog
        self.personagem_id = personagem_id
        self.menu = discord.ui.Select(
            placeholder=f"Escolha ate {limite} pericia(s) com proficiencia",
            min_values=0,
            max_values=min(limite, len(PERICIAS)),
            options=[
                discord.SelectOption(label=p, default=p in marcadas) for p in PERICIAS
            ],
        )
        self.menu.callback = self._escolher
        self.add_item(self.menu)

    async def _escolher(self, interaction: discord.Interaction) -> None:
        self.stop()
        await db.atualizar_pericias(
            self.cog.bot.db, self.personagem_id, list(self.menu.values)
        )
        atualizado = await db.buscar_personagem(self.cog.bot.db, self.personagem_id)
        await interaction.response.edit_message(
            content="Proficiencias atualizadas.",
            embed=embed_ficha(atualizado, interaction.user),
            view=None,
        )


async def sugerir_personagens(
    conn, interaction: discord.Interaction, atual: str
) -> list[app_commands.Choice[str]]:
    """Autocomplete dos personagens de quem esta digitando."""
    personagens = await db.listar_personagens(conn, interaction.guild_id, interaction.user.id)
    termo = atual.lower()
    return [
        app_commands.Choice(name=f"{p['nome']} (tier {tier(p['nivel'])})", value=p["nome"])
        for p in personagens
        if termo in p["nome"].lower()
    ][:25]


async def sugerir_do_servidor(
    conn, interaction: discord.Interaction, atual: str
) -> list[app_commands.Choice[str]]:
    """Autocomplete de TODOS os personagens do servidor, com o dono no rotulo.

    O `sugerir_personagens` so enxerga os de quem digita; o admin precisa
    alcancar a ficha de outra pessoa. O valor e o id, e nao o nome, porque
    dois jogadores podem ter personagens com o mesmo nome.
    """
    personagens = await db.personagens_da_guilda(conn, interaction.guild_id)
    termo = atual.lower()
    saida = []
    for p in personagens:
        if termo and termo not in p["nome"].lower():
            continue
        dono = interaction.guild.get_member(p["user_id"]) if interaction.guild else None
        quem = dono.display_name if dono else f"id {p['user_id']}"
        saida.append(
            app_commands.Choice(
                name=f"{p['nome']} (tier {tier(p['nivel'])}) - {quem}"[:100],
                value=str(p["id"]),
            )
        )
    return saida[:25]


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
            f"Tier {tier(nivel)} de {TIER_MAXIMO}"
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
    _campo_saves(e, personagem)

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
            value="nenhuma ainda",
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


def _campo_saves(e: discord.Embed, personagem: dict[str, Any]) -> None:
    """As resistencias, com os dois fortes da classe em negrito."""
    saves = personagem.get("saves") or {}
    if not saves:
        return
    fortes = set(personagem.get("saves_fortes") or ())
    linhas = []
    for atributo in ATRIBUTOS:
        valor = fmt(saves[atributo])
        linhas.append(
            f"{atributo} **{valor}**" if atributo in fortes else f"{atributo} {valor}"
        )
    nome = "Resistencias" if fortes else "Resistencias (fortes a definir)"
    e.add_field(name=nome, value=" | ".join(linhas), inline=False)


# A ESCOLHA nao faz nada sozinha: ela DESTRAVA outra habilidade. O "?"
# dizia "nao sei o que e isto"; a bifurcacao diz "aqui voce decide".
ICONE_HABILIDADE = {cl.PASSIVA: "⚙️", cl.ATIVA: "⚡", cl.ESCOLHA: "🔀"}


def _campo_habilidades(e: discord.Embed, personagem: dict[str, Any]) -> None:
    """As habilidades que o personagem ja tem, por tier.

    O icone diz se o bot aplica sozinho ou se o jogador aciona. O que o bot
    ainda nao sabe resolver sai marcado.

    A ESCOLHA fica de fora: ela nao e habilidade, e o rotulo de uma
    decisao ("Escolhe uma: Healing Word, Dissonant Whispers ou Charm
    Person"). Nenhuma das 38 tem efeito ou acao propria — elas so
    destravam a habilidade escolhida, e e ESSA que interessa na lista.
    Qual foi a decisao continua no campo Escolhas, logo abaixo.
    """
    ganhas = [
        (t, h) for t, h in (personagem.get("habilidades") or [])
        if h.tipo != cl.ESCOLHA
    ]
    if not ganhas:
        return
    linhas = []
    for tier_da_habilidade, habilidade in ganhas:
        icone = ICONE_HABILIDADE.get(habilidade.tipo, "")
        # `automatica` e so passiva: testar por ela marcava toda ativa e toda
        # escolha como "em breve", mesmo funcionando. `pronta` e o certo —
        # soma numero, sabe ser acionada, ou sabe conduzir a escolha.
        pendente = "" if habilidade.pronta else " *(em breve)*"
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
        linhas.append(
            f"**{habilidade.nome}**: *a decidir* — `/ficha alterar` abre o menu"
        )
    if linhas:
        e.add_field(name="Escolhas", value="\n".join(linhas), inline=False)


def _rodape_da_ficha(e: discord.Embed, numeros, nivel: int) -> discord.Embed:
    resto = (
        "Proximo tier: /ficha upar" if tier(nivel) < TIER_MAXIMO else "Tier maximo"
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
        return await sugerir_personagens(self.bot.db, interaction, atual)

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
                "Suba ou use os que voce ja tem.",
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
        # A decisao do tier 1 e do REGISTRO. Sem isto ela ficava pendente e
        # aparecia na primeira subida, junto com a do tier 2 — o jogador
        # escolhia a magia de tier 1 ao virar tier 2, sempre um tier atrasado.
        await self._abrir_pendencia_em_seguida(interaction, personagem)

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

    @grupo.command(name="upar", description="Sobe o personagem um tier")
    @app_commands.describe(personagem="Qual personagem (opcional se voce so tem um)")
    @app_commands.autocomplete(personagem=_sugerir_personagens)
    async def upar(
        self, interaction: discord.Interaction, personagem: Optional[str] = None
    ) -> None:
        """Sobe um tier. Se o tier novo tiver decisao, ela e tomada na hora."""
        escolhido = await self._resolver(interaction, personagem)
        if not escolhido:
            return
        antes = tier(escolhido["nivel"])
        if antes >= TIER_MAXIMO:
            await interaction.response.send_message(
                f"**{escolhido['nome']}** ja esta no tier maximo ({TIER_MAXIMO}).",
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
        await db.atualizar_personagem(
            self.bot.db, escolhido["id"], "nivel", nivel_do_tier(depois)
        )
        atualizado = await db.buscar_personagem(self.bot.db, escolhido["id"])

        velhos, novos = classe.numeros(nivel_do_tier(antes)), classe.numeros(nivel_do_tier(depois))
        linhas = [
            f"📈 {interaction.user.mention} subiu **{escolhido['nome']}** "
            f"para o **tier {depois}**."
        ]
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
            linhas.append(" | ".join(mudou) + ".")
        novas = classe.habilidades_do_tier(depois)
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
            linhas.append(f"O tier novo da mais **{sobrando}** proficiencia(s).")

        await self._responder_com_escolha(interaction, atualizado, "\n".join(linhas))
        # As vagas de pericia que o tier abriu: o menu vem aqui, por followup.
        # Antes o texto mandava rodar `/ficha pericias`, e sem aquele comando
        # as vagas novas nao teriam como ser preenchidas nunca.
        if sobrando > 0:
            await self._abrir_pericias_em_seguida(interaction, atualizado)

    @grupo.command(name="voltar", description="Desce o personagem um tier, se voce errou")
    @app_commands.describe(personagem="Qual personagem (opcional se voce so tem um)")
    @app_commands.autocomplete(personagem=_sugerir_personagens)
    async def voltar(
        self, interaction: discord.Interaction, personagem: Optional[str] = None
    ) -> None:
        """Desce um tier e esquece as decisoes do tier perdido, para refaze-las."""
        escolhido = await self._resolver(interaction, personagem)
        if not escolhido:
            return
        antes = tier(escolhido["nivel"])
        if antes <= 1:
            await interaction.response.send_message(
                f"**{escolhido['nome']}** ja esta no tier 1 — nao da para descer mais.",
                ephemeral=True,
            )
            return

        depois = antes - 1
        nivel = nivel_do_tier(depois)
        # As decisoes do tier que ele perdeu somem: o jogador refaz quando subir
        # de novo, que e o motivo de existir este comando.
        mantidas = {
            h.id: escolhido["escolhas"][h.id]
            for _t, h in cl.habilidades(escolhido.get("classe"), nivel)
            if h.id in (escolhido.get("escolhas") or {})
        }
        esquecidas = [
            h.nome
            for _t, h in cl.habilidades(escolhido.get("classe"), escolhido["nivel"])
            if h.id in (escolhido.get("escolhas") or {}) and h.id not in mantidas
        ]
        await db.atualizar_personagem(self.bot.db, escolhido["id"], "nivel", nivel)
        await db.definir_escolhas(self.bot.db, escolhido["id"], mantidas)
        atualizado = await db.buscar_personagem(self.bot.db, escolhido["id"])

        linhas = [
            f"📉 {interaction.user.mention} voltou **{escolhido['nome']}** "
            f"para o **tier {depois}**."
        ]
        if esquecidas:
            linhas.append(
                "Decisao(oes) esquecidas, para refazer ao subir: "
                + ", ".join(f"**{n}**" for n in esquecidas)
                + "."
            )
        sobrando = len(atualizado["pericias"]) - atualizado["numeros"].pericias
        if sobrando > 0:
            linhas.append(
                f"O tier {depois} da menos proficiencias: voce tem **{sobrando}** "
                f"a mais do que a cota. Elas voltam a caber quando ele subir."
            )
        await interaction.response.send_message(
            "\n".join(linhas), embed=embed_ficha(atualizado, interaction.user)
        )

    # ------------------------------------------------------- escolhas

    def _seletor_da_escolha(self, personagem: dict[str, Any], habilidade):
        """(texto, view) de uma decisao. Sem view, o texto diz o que falta fazer."""
        forma = habilidade.escolha
        cabeca = f"**{habilidade.nome}** — {habilidade.texto}"
        if forma["tipo"] == "opcao":
            return cabeca, SeletorOpcao(
                self, personagem["id"], habilidade, personagem["user_id"]
            )

        if forma.get("entre") == "proficientes":
            opcoes = [
                p for p in personagem["pericias"]
                if p not in (personagem["efeitos"] or {}).get("expertise", [])
            ]
            if not opcoes:
                return (
                    "Este personagem ainda nao tem proficiencia nenhuma para "
                    "dobrar. Elas sao escolhidas no registro e a cada subida.",
                    None,
                )
        else:
            opcoes = [p for p in PERICIAS if p not in personagem["pericias"]]
        return cabeca, SeletorPericiasDaEscolha(
            self, personagem["id"], habilidade, opcoes, personagem["user_id"]
        )

    async def _responder_com_escolha(
        self, interaction: discord.Interaction, personagem: dict[str, Any], anuncio: str
    ) -> None:
        """Anuncia o que mudou e, se ficou decisao pendente, ja abre o menu dela.

        O anuncio e do canal; a decisao vai num menu so para o dono. Quando
        sobra mais de uma, a proxima abre sozinha assim que esta for gravada.
        """
        pendencias = personagem.get("pendencias") or []
        if not pendencias:
            await interaction.response.send_message(
                anuncio, embed=embed_ficha(personagem, interaction.user)
            )
            return

        _tier_da, habilidade = pendencias[0]
        texto, view = self._seletor_da_escolha(personagem, habilidade)
        faltam = (
            f"\nDepois desta ainda faltam {len(pendencias) - 1}."
            if len(pendencias) > 1 and view is not None
            else ""
        )
        await interaction.response.send_message(
            f"🧭 Decida agora: {texto}{faltam}", view=view, ephemeral=True
        )
        await self._anunciar(
            interaction, anuncio, embed=embed_ficha(personagem, interaction.user)
        )

    async def _abrir_pericias_em_seguida(
        self, interaction: discord.Interaction, personagem: dict[str, Any]
    ) -> None:
        """Abre o menu de proficiencias por followup, e grava o que vier.

        Existe porque `/ficha pericias` saiu: a cota cresce ao subir de tier, e
        sem um lugar para preencher as vagas novas elas ficariam perdidas. O
        momento certo e o da subida, como ja acontece com as decisoes de tier.
        """
        numeros = personagem.get("numeros")
        if numeros is None:
            return
        view = SeletorPericiasDoTier(
            self, personagem["id"], interaction.user.id,
            personagem["pericias"], numeros.pericias,
        )
        try:
            await interaction.followup.send(
                f"\U0001f393 Proficiencias de **{personagem['nome']}** "
                f"(ate {numeros.pericias}):",
                view=view,
                ephemeral=True,
            )
        except discord.HTTPException:
            pass

    async def _abrir_pendencia_em_seguida(
        self, interaction: discord.Interaction, personagem: dict[str, Any]
    ) -> None:
        """Abre a proxima decisao por followup, com a resposta ja gasta.

        O registro usa a resposta da interacao no seletor de pericias, entao
        aqui nao da para responder de novo — vai por followup. Da segunda
        decisao em diante a cadeia de `gravar_escolha` cuida, porque cada
        clique do menu traz uma interacao nova.
        """
        pendencias = personagem.get("pendencias") or []
        if not pendencias:
            return
        _tier_da, habilidade = pendencias[0]
        texto, view = self._seletor_da_escolha(personagem, habilidade)
        faltam = (
            f"\nDepois desta ainda faltam {len(pendencias) - 1}."
            if len(pendencias) > 1 and view is not None
            else ""
        )
        try:
            await interaction.followup.send(
                f"🧭 Decida agora: {texto}{faltam}", view=view, ephemeral=True
            )
        except discord.HTTPException:
            pass

    async def abrir_escolha(
        self, interaction: discord.Interaction, personagem_id: int, habilidade_id: str
    ) -> None:
        """Mostra as opcoes de uma decisao pendente."""
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
        texto, view = self._seletor_da_escolha(personagem, habilidade)
        await interaction.response.send_message(texto, view=view, ephemeral=True)

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
        # Sobrando decisao, o menu da proxima ja vem junto: o jogador resolve
        # tudo numa sequencia so, sem precisar de outro comando.
        await self._responder_com_escolha(interaction, atualizado, texto)

    async def _sugerir_do_servidor(
        self, interaction: discord.Interaction, atual: str
    ) -> list[app_commands.Choice[str]]:
        return await sugerir_do_servidor(self.bot.db, interaction, atual)

    @grupo.command(
        name="alterar",
        description="Refaz as decisoes e pericias do tier, se voce ainda nao jogou nele",
    )
    @app_commands.describe(personagem="Qual personagem (opcional se voce so tem um)")
    @app_commands.autocomplete(personagem=_sugerir_personagens)
    async def alterar(
        self, interaction: discord.Interaction, personagem: Optional[str] = None
    ) -> None:
        """Esquece o que o tier de agora deu, para o jogador refazer.

        Duas coisas, e nem todo tier tem as duas: as DECISOES (as magias e
        opcoes que o `upar` pediu) e as PROFICIENCIAS, quando aquele tier
        abriu vaga nova. A maioria das classes ganha pericia no tier 1, 3 e
        5; Barbaro, Guerreiro e Ladino so no 1.

        O `/ficha voltar` ja fazia isso, mas pelo caminho longo: descer um
        tier, perder os numeros, e subir de novo. Aqui o nivel nao se mexe.

        A trava e ter jogado: depois que o personagem entrou numa incursao
        naquele tier, as decisoes dele valeram em mesa e nao se desfazem. As
        runs anteriores a coluna `tier` ficam de fora da conta - nelas nao da
        para saber em que tier ele estava, e chutar travaria um tier que
        talvez nunca tenha sido jogado.
        """
        escolhido = await self._resolver(interaction, personagem)
        if not escolhido:
            return

        atual = tier(escolhido["nivel"])
        if atual in await db.tiers_jogados(self.bot.db, escolhido["id"]):
            await interaction.response.send_message(
                f"**{escolhido['nome']}** ja entrou numa incursao no **tier "
                f"{atual}** - as decisoes desse tier valeram em mesa e nao da "
                f"para refazer. Elas voltam a abrir quando ele subir de tier.",
                ephemeral=True,
            )
            return

        classe = cl.classe(escolhido.get("classe"))
        if classe is None:
            await interaction.response.send_message(
                "Nao reconheco a classe desta ficha.", ephemeral=True
            )
            return

        # Esquece so as decisoes DESTE tier: as dos tiers abaixo ja foram
        # jogadas e nao estao em questao.
        deste_tier = {h.id for h in classe.habilidades_do_tier(atual)}
        guardadas = escolhido.get("escolhas") or {}
        mantidas = {k: v for k, v in guardadas.items() if k not in deste_tier}
        apagadas = [
            h.nome for h in classe.habilidades_do_tier(atual) if h.id in guardadas
        ]

        # O tier tambem abriu vaga de proficiencia? Ai as pericias entram no
        # que da para refazer. A cota cresce em tiers diferentes conforme a
        # classe — a maioria ganha no 1, no 3 e no 5, e Barbaro, Guerreiro e
        # Ladino so no 1 —, entao a resposta sai da tabela e nao de uma lista
        # escrita aqui.
        cota = classe.numeros(nivel_do_tier(atual)).pericias
        antes_dela = (
            classe.numeros(nivel_do_tier(atual - 1)).pericias if atual > 1 else 0
        )
        abriu_pericia = cota > antes_dela

        if not apagadas and not abriu_pericia:
            await interaction.response.send_message(
                f"O tier {atual} de **{escolhido['nome']}** nao tem decisao nem "
                f"proficiencia para refazer — ele nao abriu nenhuma das duas.",
                ephemeral=True,
            )
            return

        if apagadas:
            await db.definir_escolhas(self.bot.db, escolhido["id"], mantidas)
        atualizado = await db.buscar_personagem(self.bot.db, escolhido["id"])

        refazendo = [f"**{n}**" for n in apagadas]
        if abriu_pericia:
            refazendo.append(f"as **{cota} proficiencia(s)**")
        texto = (
            f"\U0001f501 {interaction.user.mention} vai refazer no tier "
            f"{atual} de **{escolhido['nome']}**: "
            + ", ".join(refazendo)
            + "."
        )
        await self._responder_com_escolha(interaction, atualizado, texto)
        # O menu das pericias vem por followup, como no `upar`: ele precisa da
        # resposta ja dada.
        if abriu_pericia:
            await self._abrir_pericias_em_seguida(interaction, atualizado)

    @grupo.command(
        name="remover", description="(admin) Apaga o personagem de qualquer jogador"
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(personagem="Qual ficha apagar (de qualquer jogador)")
    @app_commands.autocomplete(personagem=_sugerir_do_servidor)
    async def remover(self, interaction: discord.Interaction, personagem: str) -> None:
        """Apaga uma ficha. So admin, e nunca a de quem esta numa run viva.

        Era auto-servico e saiu numa limpeza de comandos; volta como
        ferramenta do mestre. O limite de 25 personagens por jogador vem do
        seletor do Discord, e sem nenhum jeito de apagar ele virava parede.
        """
        try:
            alvo_id = int(personagem)
        except ValueError:
            await interaction.response.send_message(
                "Escolha a ficha pela lista do autocomplete.", ephemeral=True
            )
            return

        alvo = await db.buscar_personagem(self.bot.db, alvo_id)
        if not alvo or alvo.get("guild_id") != interaction.guild_id:
            await interaction.response.send_message(
                "Nao achei essa ficha neste servidor.", ephemeral=True
            )
            return

        em_run = await db.run_viva_do_jogador(
            self.bot.db, interaction.guild_id, alvo["user_id"]
        )
        if em_run:
            await interaction.response.send_message(
                f"O dono de **{alvo['nome']}** esta na run #{em_run['id']}. "
                f"Termine ou desista dela antes de apagar a ficha.",
                ephemeral=True,
            )
            return

        await db.remover_personagem(self.bot.db, alvo_id)
        dono = (
            interaction.guild.get_member(alvo["user_id"])
            if interaction.guild
            else None
        )
        quem = dono.mention if dono else f"<@{alvo['user_id']}>"
        await interaction.response.send_message(
            f"\U0001f5d1\ufe0f {interaction.user.mention} apagou a ficha "
            f"**{alvo['nome']}** (tier {tier(alvo['nivel'])}), de {quem}."
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

        # A ficha mostra o que o Discord consegue buscar; a faixa da incursao
        # mostra o que ESTE bot consegue baixar. Sao coisas diferentes, entao o
        # link e testado aqui para ninguem descobrir a diferenca no meio da run.
        if retrato:
            deu, motivo = await retratos.diagnosticar(retrato)
            if not deu:
                aviso += (
                    f"\n⚠️ A ficha mostra, mas o bot nao conseguiu baixar a imagem "
                    f"({motivo}) — na incursao vai aparecer a inicial no lugar. "
                    f"Um link direto que termine em .png ou .jpg costuma resolver."
                )
        await interaction.response.send_message(
            aviso, embed=embed_ficha(atualizado, interaction.user)
        )

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Ficha(bot))
