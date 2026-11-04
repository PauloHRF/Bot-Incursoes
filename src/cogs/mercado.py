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

from .. import config, consumiveis, database as db, itens, mercado
from .ficha import sugerir_personagens

COR = 0xC8743A

ICONE_DA_RARIDADE = {
    "comum": "⚪",
    "incomum": "🟢",
    "raro": "🔵",
    "lendario": "🟠",
}


def _icone(peca) -> str:
    """O ícone da peça. A poção não tem raridade: tem o alambique."""
    if isinstance(peca, consumiveis.Consumivel):
        return consumiveis.ICONE
    return ICONE_DA_RARIDADE.get(peca.raridade, "·")


def _o_que_faz(peca) -> str:
    """Uma linha com o que a peça faz, para a vitrine.

    O equipamento lê isso do EFEITO (`itens.status`), para o número mostrado
    ser o número que o motor aplica. A poção tem o texto escrito à mão, porque
    o que ela faz nem sempre é um número — a de Mana devolve um uso, e a de
    buff empilha uma condição da tabela.
    """
    if isinstance(peca, consumiveis.Consumivel):
        return peca.texto
    return itens.status(peca)


async def ja_tem(conn, personagem_id: int, item_id: str) -> bool:
    """Se o personagem já possui aquela peça, vestida ou na bolsa."""
    if item_id in (await db.equipamento(conn, personagem_id)).values():
        return True
    return item_id in await db.itens_na_bolsa(conn, personagem_id)


async def tentar_comprar(
    conn, personagem_id: int, semana: str, item_id: str
) -> tuple[Optional[Any], str]:
    """A compra, uma vez só, para as duas portas que levam a ela.

    O comando digitado e o botão da vitrine passam os dois por aqui — se cada
    um tivesse a sua cópia das checagens, uma delas envelheceria. Devolve
    (a peça comprada ou None, o texto para o jogador).

    Serve equipamento e poção, e a diferença entre os dois é só a contenção:
    o equipamento é único por personagem (o slot já impede o stack) e a poção
    empilha até `consumiveis.TETO_NA_BOLSA`.
    """
    pocao = consumiveis.item(item_id)
    peca = pocao if pocao is not None else itens.item(item_id)
    # A prateleira de HOJE, e nao o id que chegou: o botao pode ser de uma
    # mensagem da semana passada, que o Discord mantem clicavel.
    em_cartaz = (
        consumiveis.esta_na_vitrine(personagem_id, semana, item_id)
        if pocao is not None
        else peca is not None and mercado.esta_na_vitrine(personagem_id, semana, peca.id)
    )
    if peca is None or not em_cartaz:
        return None, (
            "Esse item não está na vitrine desta semana. "
            "Veja o que tem com `/mercado vitrine`."
        )
    if pocao is not None:
        # O teto por tipo é o que segura a guerra de atrito: sem ele, ouro
        # guardado virava estoque e a incursão longa deixava de cobrar HP.
        quantos = (await db.itens_na_bolsa(conn, personagem_id)).get(pocao.id, 0)
        if quantos >= consumiveis.TETO_NA_BOLSA:
            return None, (
                f"Você já tem {quantos} **{pocao.nome}** na bolsa, que é o "
                f"máximo ({consumiveis.TETO_NA_BOLSA} de cada)."
            )
    # Equipamento e unico por personagem: a segunda copia nao faria nada, e so
    # queimaria ouro.
    elif peca.slot in itens.SLOTS and await ja_tem(conn, personagem_id, peca.id):
        return None, f"Você já tem **{peca.nome}**. Uma segunda não faria nada."
    if not await db.comprar(conn, personagem_id, peca.id, peca.custo):
        saldo = await db.ouro(conn, personagem_id)
        return None, (
            f"**{peca.nome}** custa {peca.custo} e você tem {saldo}. "
            f"Faltam **{peca.custo - saldo}** de ouro."
        )
    saldo = await db.ouro(conn, personagem_id)
    return peca, (
        f"{_icone(peca)} **{peca.nome}** por {peca.custo}. "
        f"Sobram **{saldo}** de ouro, e está na bolsa."
    )


def embed_vitrine(
    nome: str,
    saldo: int,
    prateleira: list[itens.Item],
    tendo: Optional[set] = None,
    pocoes: Optional[list] = None,
    bolsa: Optional[dict[str, int]] = None,
) -> discord.Embed:
    """A prateleira em texto. `tendo` são os ids que o personagem já possui.

    O embed diz o preço e o botão repete, de propósito: no celular o botão
    corta o nome longo, e no embed cabe o que a peça faz.

    Mostra o STATUS da peça, e não a prosa do catálogo: na hora de comparar
    cinco peças para decidir uma compra, a prosa atrapalha. E o número que
    aparece é lido do efeito, então é o mesmo que o motor aplica.
    """
    ja = tendo or set()
    e = discord.Embed(
        title=f"Mercado · {nome}",
        description=f"**{saldo}** de ouro na bolsa.",
        color=COR,
    )
    for peca in prateleira:
        marca = " · já tem" if peca.id in ja else ""
        e.add_field(
            name=f"{_icone(peca)} {peca.nome} — {peca.custo} de ouro{marca}",
            value=_o_que_faz(peca),
            inline=False,
        )
    if not prateleira:
        e.add_field(name="Vazia", value="Nada à venda nesta semana.", inline=False)
    # As poções ficam num campo só, e não um por poção: são três, a prateleira
    # delas muda pouco (duas são fixas) e o embed já tem seis peças em cima.
    if pocoes:
        guardadas = bolsa or {}
        linhas = []
        for pocao in pocoes:
            tem = guardadas.get(pocao.id, 0)
            cheio = tem >= consumiveis.TETO_NA_BOLSA
            quanto = (
                f" · você tem {tem}{' (cheio)' if cheio else ''}" if tem else ""
            )
            linhas.append(
                f"{consumiveis.ICONE} **{pocao.nome}** — {pocao.custo} de "
                f"ouro{quanto}\n　{pocao.texto}"
            )
        e.add_field(
            name=f"Poções · até {consumiveis.TETO_NA_BOLSA} de cada na bolsa",
            value="\n".join(linhas),
            inline=False,
        )
    e.set_footer(
        text="Clique para comprar · /mercado bolsa para vestir · poção se bebe "
        f"no combate, pelo botão {consumiveis.ICONE}"
    )
    return e


def embed_bolsa(
    personagem: dict[str, Any],
    saldo: int,
    vestido: dict[str, str],
    bolsa: dict[str, int],
    extrato: Optional[list] = None,
) -> discord.Embed:
    """A bolsa, o corpo e o ouro numa tela só.

    Eram dois comandos, `bolsa` e `ouro`, e as duas perguntas são a mesma:
    "com o que eu estou e quanto me sobra". Separar obrigava a abrir os dois
    para decidir uma compra.
    """
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
    frascos = []
    for item_id, quantos in sorted(bolsa.items()):
        pocao = consumiveis.item(item_id)
        if pocao is not None:
            vezes = f" ×{quantos}" if quantos > 1 else ""
            frascos.append(
                f"{consumiveis.ICONE} **{pocao.nome}**{vezes}\n　{pocao.texto}"
            )
            continue
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
    # As poções em campo próprio: o que se veste e o que se bebe são duas
    # listas diferentes, e misturá-las fazia o jogador procurar.
    if frascos:
        e.add_field(name="Poções", value="\n".join(frascos), inline=False)
    e.set_footer(
        text="/mercado equipar para vestir · equipar outro no mesmo slot troca"
        + (
            f" · poção se bebe no combate, pelo botão {consumiveis.ICONE}"
            if frascos
            else ""
        )
    )
    return e


class BotaoDeCompra(discord.ui.Button):
    """Uma peça da prateleira. O clique só delega — a regra é da view."""

    def __init__(self, dona: "ViewDaVitrine", peca, travado: str):
        super().__init__(
            label=f"{peca.nome} · {peca.custo}"[:80],
            emoji=(
                consumiveis.ICONE
                if isinstance(peca, consumiveis.Consumivel)
                else None
            ),
            style=(
                discord.ButtonStyle.secondary if travado
                else discord.ButtonStyle.success
            ),
            disabled=bool(travado),
            # Tres por fileira. O Discord so aceita cinco fileiras, e
            # seis vagas cabem em duas — o min() e seguro para quem
            # um dia aumentar mercado.VAGAS sem pensar nisso.
            row=min(4, len(dona.children) // 3),
        )
        self.dona = dona
        self.peca = peca

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.dona.comprar(interaction, self.peca.id)


class ViewDaVitrine(discord.ui.View):
    """A prateleira com um botão por peça, e o estado redesenhado a cada compra.

    A view não guarda a prateleira nem o saldo: ela relê os dois do banco a
    cada desenho. É o que mantém o botão honesto depois de uma compra feita
    pelo comando digitado, ou pelo celular, ou na semana que virou — o que
    está na tela sempre foi conferido agora.
    """

    def __init__(self, cog: "Mercado", personagem: dict[str, Any], semana: str):
        super().__init__(timeout=300)
        self.cog = cog
        self.personagem_id = personagem["id"]
        self.nome = personagem["nome"]
        self.dono_id = personagem["user_id"]
        self.semana = semana
        self.mensagem = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.dono_id:
            await interaction.response.send_message(
                "Essa vitrine não é sua.", ephemeral=True
            )
            return False
        return True

    async def desenhar(self) -> discord.Embed:
        """Relê o estado, refaz os botões e devolve o embed que combina com eles."""
        conn = self.cog.bot.db
        saldo = await db.ouro(conn, self.personagem_id)
        prateleira = mercado.vitrine(self.personagem_id, self.semana)
        pocoes = consumiveis.vitrine(self.personagem_id, self.semana)
        vestido = set((await db.equipamento(conn, self.personagem_id)).values())
        bolsa = await db.itens_na_bolsa(conn, self.personagem_id)
        na_bolsa = set(bolsa)

        self.clear_items()
        for peca in prateleira:
            if peca.id in vestido or peca.id in na_bolsa:
                travado = "tem"
            elif peca.custo > saldo:
                travado = "ouro"
            else:
                travado = ""
            self.add_item(BotaoDeCompra(self, peca, travado))
        # A poção trava por teto na bolsa, e não por "já tem": é dela empilhar.
        for pocao in pocoes:
            if bolsa.get(pocao.id, 0) >= consumiveis.TETO_NA_BOLSA:
                travado = "cheio"
            elif pocao.custo > saldo:
                travado = "ouro"
            else:
                travado = ""
            self.add_item(BotaoDeCompra(self, pocao, travado))
        return embed_vitrine(
            self.nome, saldo, prateleira, tendo=vestido | na_bolsa,
            pocoes=pocoes, bolsa=bolsa,
        )

    async def comprar(self, interaction: discord.Interaction, item_id: str) -> None:
        """O clique: compra pela mesma porta do comando, e redesenha a tela."""
        if not await self.cog._fora_de_incursao(interaction):
            return
        peca, texto = await tentar_comprar(
            self.cog.bot.db, self.personagem_id, self.semana, item_id
        )
        embed = await self.desenhar()
        await interaction.response.edit_message(embed=embed, view=self)
        if peca is None:
            await interaction.followup.send(texto, ephemeral=True)
            return
        # A compra sai no canal, como a do comando digitado: o grupo ve quem
        # esta se equipando, e e metade da graca de ter mercado.
        await self.cog._anunciar(
            interaction, f"🪙 **{self.nome}** compra {texto}"
        )

    async def on_timeout(self) -> None:
        for filho in self.children:
            filho.disabled = True
        if self.mensagem is not None:
            try:
                await self.mensagem.edit(view=self)
            except discord.HTTPException:
                pass


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

    async def _para_listar(
        self, interaction: discord.Interaction
    ) -> list[dict[str, Any]]:
        """Os personagens que o autocomplete deve considerar.

        O que o jogador JÁ digitou no campo `personagem`, se ele digitou;
        senão todos os dele.

        Antes isto devolvia "o único, ou nada", e nada virava lista vazia.
        Quem tinha dois personagens nunca via item nenhum para vestir — nem
        depois de dizer qual personagem era, porque o campo digitado não era
        lido. Lista vazia sem explicação é a pior resposta possível num
        autocomplete: o jogador conclui que o item sumiu da bolsa.

        O `namespace` é o que o Discord já preencheu nos OUTROS campos do
        comando, e é por ele que o `personagem` chega aqui.
        """
        todos = await db.listar_personagens(
            self.bot.db, interaction.guild_id, interaction.user.id
        )
        nome = getattr(getattr(interaction, "namespace", None), "personagem", None)
        if nome:
            achado = await db.personagem_por_nome(
                self.bot.db, interaction.guild_id, interaction.user.id, nome
            )
            if achado:
                return [achado]
        return todos

    async def _anunciar(self, interaction: discord.Interaction, texto: str) -> None:
        """Manda no canal, e nao na resposta.

        O clique do botao responde editando a vitrine efemera, que so o dono
        ve — a compra em si vai para o canal, como a do comando digitado, para
        o grupo ver quem esta se equipando.
        """
        canal = interaction.channel
        if canal is None:
            return
        try:
            await canal.send(texto)
        except discord.HTTPException:
            pass

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
        view = ViewDaVitrine(self, escolhido, self._semana())
        await interaction.response.send_message(
            embed=await view.desenhar(), view=view, ephemeral=True
        )
        # Guardado so para apagar os botoes no timeout. Mensagem efemera nem
        # sempre devolve handle, e ficar sem ele nao e problema: o Discord
        # para de aceitar o clique quando a view expira de qualquer forma.
        try:
            view.mensagem = await interaction.original_response()
        except (discord.HTTPException, AttributeError):
            pass

    @grupo.command(
        name="bolsa", description="Seu ouro, o que está vestido e o que está guardado"
    )
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

    # --------------------------------------------------------------- comprar

    async def _sugerir_vitrine(
        self, interaction: discord.Interaction, atual: str
    ) -> list[app_commands.Choice[str]]:
        personagens = await self._para_listar(interaction)
        termo = atual.lower()
        # A vitrine é POR personagem: com dois, os dois aparecem com o nome
        # no rótulo. Comprar ainda confere a prateleira de quem o comando
        # resolver — e `_resolver` exige o nome quando há mais de um —, então
        # o rótulo orienta e a validação continua sendo a do comando.
        de_varios = len(personagens) > 1
        saida, vistos = [], set()
        for quem in personagens:
            # Equipamento e poção na mesma lista: as duas coisas se compram
            # pelo mesmo comando, e o jogador não tem por que saber que são
            # dois catálogos.
            prateleira = [
                *mercado.vitrine(quem["id"], self._semana()),
                *consumiveis.vitrine(quem["id"], self._semana()),
            ]
            for peca in prateleira:
                if termo not in peca.nome.lower():
                    continue
                rotulo = f"{peca.nome} — {peca.custo} de ouro"
                if de_varios:
                    rotulo = f"{rotulo} ({quem['nome']})"
                if rotulo in vistos:
                    continue
                vistos.add(rotulo)
                saida.append(app_commands.Choice(name=rotulo, value=peca.id))
        return saida[:25]

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
        peca, texto = await tentar_comprar(
            self.bot.db, escolhido["id"], self._semana(), item
        )
        if peca is None:
            await interaction.response.send_message(texto, ephemeral=True)
            return
        await interaction.response.send_message(
            f"🪙 **{escolhido['nome']}** compra {texto}"
        )

    # --------------------------------------------------------------- vestir

    async def _sugerir_bolsa(
        self, interaction: discord.Interaction, atual: str
    ) -> list[app_commands.Choice[str]]:
        personagens = await self._para_listar(interaction)
        termo = atual.lower()
        # Com mais de um personagem em jogo, o nome dele entra no rótulo: o
        # item é o mesmo id para os dois, e sem isso o jogador veria a mesma
        # peça duas vezes sem saber de quem é qual.
        de_varios = len(personagens) > 1
        saida, vistos = [], set()
        for quem in personagens:
            for item_id in await db.itens_na_bolsa(self.bot.db, quem["id"]):
                peca = itens.item(item_id)
                if peca is None or termo not in peca.nome.lower():
                    continue
                rotulo = f"{peca.nome} — {itens.NOME_DO_SLOT[peca.slot]}"
                if de_varios:
                    rotulo = f"{rotulo} ({quem['nome']})"
                if rotulo in vistos:
                    continue
                vistos.add(rotulo)
                saida.append(app_commands.Choice(name=rotulo, value=peca.id))
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
            # Poção digitada à mão aqui é o erro esperado: ela está na bolsa
            # como os outros itens, e o autocomplete de vestir não a oferece.
            pocao = consumiveis.item(item)
            await interaction.response.send_message(
                f"**{pocao.nome}** não se veste: ela se bebe no combate, pelo "
                f"botão {consumiveis.ICONE} do painel."
                if pocao is not None
                else "Esse item não existe.",
                ephemeral=True,
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

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Mercado(bot))
