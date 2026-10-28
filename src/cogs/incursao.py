"""Runs de incursão: recrutamento, votação por linha, salas e testes de perícia.

A run é assíncrona: o estado vive no banco, não na memória, para que o grupo
possa avançar ao longo de dias e o bot possa reiniciar sem perder nada.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

import discord
from discord import app_commands
from discord.ext import commands

from .. import (
    ameaca,
    bestiario,
    classes as cl,
    condicoes,
    config,
    consequencias,
    database as db,
    embeds as E,
    habilidades,
    mercado,
    motor,
)
from ..incursoes import (
    BancoDeSalas,
    Incursao,
    Sala,
    arquivo_da_organizacao,
    carregar_bancos,
    carregar_todas,
    monstros_de_criatura,
)
from ..motor import Combatente, EstadoCombate, ResolucaoSala, ResultadoTeste
from ..rules import fmt, tier
from .ficha import sugerir_personagens

log = logging.getLogger("incursoes.run")


def emboscada_de(sala: Sala) -> Sala:
    """O Tesouro que virou combate, quando a falha acorda os Mímicos.

    Função pura e determinística de propósito: a mesma sala sempre devolve a
    mesma emboscada, então remontá-la depois de um restart dá no mesmo. Vem com
    `monstros` vazio se o bestiário não tiver Mímico.
    """
    do_livro = bestiario.buscar(consequencias.NOME_DO_MIMICO)
    monstros = []
    if do_livro is not None:
        monstros = monstros_de_criatura(
            {
                "nome": consequencias.NOME_DO_MIMICO,
                "quantidade": consequencias.MIMICOS,
            },
            f"{sala.id}: emboscada",
        )
    return Sala(
        id=sala.id,
        nome=f"{sala.nome} — a emboscada",
        tipo="Combate",
        descricao=(
            "O baú abriu antes de alguém encostar nele, e o que estava dentro "
            "era o próprio baú."
        ),
        imagem=sala.imagem,
        monstros=monstros,
    )

# Teto de um efeito que so acaba quando o alvo passa no save: nao e para chegar
# la — e so uma trava para nada ficar preso o combate inteiro.
PRAZO_ATE_PASSAR = 20

# Quantas rodadas seguidas o combate pode correr sozinho quando ninguem
# pode agir (grupo inteiro atordoado) antes de o bot avisar.
MAX_RODADAS_SOZINHAS = 10


def maioria_de(total: int) -> int:
    """Quantos votos fecham a votacao: mais da metade do grupo."""
    return total // 2 + 1


def _resolucao(sala: Sala, registros: list[dict[str, Any]], total: int) -> ResolucaoSala:
    resultados = [
        ResultadoTeste(
            user_id=r["user_id"],
            personagem=r["personagem"],
            pericia=r["pericia"],
            d20=r["d20"],
            modificador=r["modificador"],
            cd=r["cd"],
        )
        for r in registros
    ]
    return ResolucaoSala(sala=sala, resultados=resultados, total_participantes=total)


class BotaoVoto(discord.ui.Button):
    def __init__(self, cog: "Incursoes", run_id: int, linha: int, indice: int, sala: Sala):
        super().__init__(
            label=str(indice + 1),
            emoji=E.EMOJI_TIPO.get(sala.tipo),
            style=discord.ButtonStyle.primary,
            custom_id=f"inc:voto:{run_id}:{linha}:{sala.id}",
        )
        self.cog = cog
        self.run_id = run_id
        self.linha = linha
        self.sala_id = sala.id

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.cog.votar(interaction, self.run_id, self.linha, self.sala_id)


class ViewVotacao(discord.ui.View):
    def __init__(self, cog: "Incursoes", run_id: int, linha: int, opcoes: list[Sala]):
        super().__init__(timeout=None)
        for i, sala in enumerate(opcoes):
            self.add_item(BotaoVoto(cog, run_id, linha, i, sala))


class ViewSala(discord.ui.View):
    def __init__(self, cog: "Incursoes", run_id: int, sala_id: str):
        super().__init__(timeout=None)
        self.cog = cog
        self.run_id = run_id
        self.sala_id = sala_id
        botao = discord.ui.Button(
            label="Rolar teste",
            emoji="🎲",
            style=discord.ButtonStyle.success,
            custom_id=f"inc:rolar:{run_id}:{sala_id}",
        )
        botao.callback = self._rolar
        self.add_item(botao)

    async def _rolar(self, interaction: discord.Interaction) -> None:
        await self.cog.rolar(interaction, self.run_id, self.sala_id)


class ViewDescanso(discord.ui.View):
    """O descanso cura e deixa **cada um** limpar uma condição sua.

    Os botões são a união do que o grupo carrega, porque a mensagem é uma só;
    cada clique age sobre as condições de quem clicou, e vale uma por
    personagem. Quem não carrega nada não precisa clicar. O "Seguir" existe para
    quem carrega algo e prefere não gastar — sem ele, um jogador ausente
    travaria a sala.

    A sala fecha quando todos escolheram, como a de teste fecha quando todos
    rolaram; o estado vive em `run_descansos`, então um restart devolve os
    botões a quem ainda falta.
    """

    OPCOES = (
        ("debuff", "Tirar um debuff meu", "🧪"),
        ("exaustao", "Tirar 1 de Exaustão", "🥵"),
    )

    def __init__(
        self, cog: "Incursoes", run_id: int, sala_id: str, disponiveis: set[str]
    ):
        super().__init__(timeout=None)
        self.cog = cog
        self.run_id = run_id
        self.sala_id = sala_id
        for chave, rotulo, emoji in self.OPCOES:
            if chave not in disponiveis:
                continue
            botao = discord.ui.Button(
                label=rotulo,
                emoji=emoji,
                style=discord.ButtonStyle.primary,
                custom_id=f"inc:limpar:{run_id}:{sala_id}:{chave}",
            )
            botao.callback = self._fazer(chave)
            self.add_item(botao)
        seguir = discord.ui.Button(
            label="Seguir",
            emoji="➡️",
            style=discord.ButtonStyle.secondary,
            custom_id=f"inc:limpar:{run_id}:{sala_id}:nada",
        )
        seguir.callback = self._fazer("nada")
        self.add_item(seguir)

    def _fazer(self, chave: str):
        async def callback(interaction: discord.Interaction) -> None:
            await self.cog.limpar_no_descanso(
                interaction, self.run_id, self.sala_id, chave
            )

        return callback


class ViewCombate(discord.ui.View):
    """Botao de atacar; com mais de um inimigo de pe, vira escolha de alvo."""

    def __init__(
        self,
        cog: "Incursoes",
        run_id: int,
        sala_id: str,
        inimigos: Optional[list[motor.Inimigo]] = None,
    ):
        super().__init__(timeout=None)
        self.cog = cog
        self.run_id = run_id
        self.sala_id = sala_id
        vivos = [i for i in (inimigos or []) if not i.caido]
        if len(vivos) > 1:
            menu = discord.ui.Select(
                placeholder="Atacar quem?",
                custom_id=f"inc:alvo:{run_id}:{sala_id}",
                options=[
                    discord.SelectOption(
                        label=i.nome[:100],
                        value=str(i.indice),
                        description=f"{i.hp_atual}/{i.hp_max} HP · CA {i.ca}",
                    )
                    for i in vivos[:25]
                ],
            )
            menu.callback = self._escolher_alvo
            self.menu = menu
            self.add_item(menu)
            self._botao_habilidade()
            return
        botao = discord.ui.Button(
            label="Atacar",
            emoji="⚔️",
            style=discord.ButtonStyle.danger,
            custom_id=f"inc:atacar:{run_id}:{sala_id}",
        )
        botao.callback = self._atacar
        self.add_item(botao)
        self._botao_habilidade()

    def _botao_habilidade(self) -> None:
        botao = discord.ui.Button(
            label="Habilidade",
            emoji="✨",
            style=discord.ButtonStyle.secondary,
            custom_id=f"inc:hab:{self.run_id}:{self.sala_id}",
        )
        botao.callback = self._habilidade
        self.add_item(botao)

    async def _atacar(self, interaction: discord.Interaction) -> None:
        await self.cog.atacar(interaction, self.run_id, self.sala_id)

    async def _habilidade(self, interaction: discord.Interaction) -> None:
        await self.cog.abrir_habilidades(interaction, self.run_id, self.sala_id)

    async def _escolher_alvo(self, interaction: discord.Interaction) -> None:
        await self.cog.atacar(
            interaction, self.run_id, self.sala_id, int(self.menu.values[0])
        )


class SeletorHabilidade(discord.ui.View):
    """As ativas que o jogador pode usar agora, so para quem clicou."""

    def __init__(self, cog: "Incursoes", run_id: int, sala_id: str, opcoes: list[tuple]):
        super().__init__(timeout=120)
        self.cog = cog
        self.run_id = run_id
        self.sala_id = sala_id
        menu = discord.ui.Select(
            placeholder="Qual habilidade?",
            options=[
                discord.SelectOption(label=nome, value=hid, description=descricao[:100])
                for hid, nome, descricao in opcoes[:25]
            ],
        )
        menu.callback = self._escolher
        self.menu = menu
        self.add_item(menu)

    async def _escolher(self, interaction: discord.Interaction) -> None:
        self.stop()
        await self.cog.usar_habilidade(
            interaction, self.run_id, self.sala_id, self.menu.values[0]
        )


class SeletorAlvoHabilidade(discord.ui.View):
    """Em quem a habilidade cai: um inimigo, varios, ou um aliado."""

    def __init__(
        self,
        cog: "Incursoes",
        run_id: int,
        sala_id: str,
        habilidade_id: str,
        opcoes: list[tuple],
        maximo: int = 1,
    ):
        super().__init__(timeout=120)
        self.cog = cog
        self.run_id = run_id
        self.sala_id = sala_id
        self.habilidade_id = habilidade_id
        menu = discord.ui.Select(
            placeholder="Em quem?" if maximo == 1 else f"Em quem? (ate {maximo})",
            min_values=1,
            max_values=min(maximo, len(opcoes)),
            options=[
                discord.SelectOption(label=nome, value=valor, description=descricao[:100])
                for valor, nome, descricao in opcoes[:25]
            ],
        )
        menu.callback = self._escolher
        self.menu = menu
        self.add_item(menu)

    async def _escolher(self, interaction: discord.Interaction) -> None:
        self.stop()
        await self.cog.usar_habilidade(
            interaction,
            self.run_id,
            self.sala_id,
            self.habilidade_id,
            [int(v) for v in self.menu.values],
        )


class SeletorPersonagemEntrada(discord.ui.View):
    """Escolha de qual personagem levar para a run, mostrada só a quem clicou."""

    def __init__(self, cog: "Incursoes", run_id: int, personagens: list[dict[str, Any]]):
        super().__init__(timeout=180)
        self.cog = cog
        self.run_id = run_id
        menu = discord.ui.Select(
            placeholder="Com qual personagem voce entra?",
            options=[
                discord.SelectOption(
                    label=p["nome"],
                    value=str(p["id"]),
                    description=(
                        f"Tier {tier(p['nivel'])} · "
                        f"CA {p['ca']} · HP {p['hp_max']}"
                    ),
                )
                for p in personagens[:25]
            ],
        )
        menu.callback = self._escolher
        self.menu = menu
        self.add_item(menu)

    async def _escolher(self, interaction: discord.Interaction) -> None:
        self.stop()
        await self.cog.efetivar_entrada(interaction, self.run_id, int(self.menu.values[0]))


class ViewRecrutamento(discord.ui.View):
    def __init__(self, cog: "Incursoes", run_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.run_id = run_id
        for rotulo, emoji, estilo, acao in (
            ("Entrar", "➕", discord.ButtonStyle.success, "entrar"),
            ("Sair", "➖", discord.ButtonStyle.secondary, "sair"),
            ("Começar", "▶️", discord.ButtonStyle.primary, "comecar"),
        ):
            botao = discord.ui.Button(
                label=rotulo, emoji=emoji, style=estilo, custom_id=f"inc:recrut:{run_id}:{acao}"
            )
            botao.callback = self._acao(acao)
            self.add_item(botao)

    def _acao(self, acao: str):
        async def callback(interaction: discord.Interaction) -> None:
            await self.cog.recrutar(interaction, self.run_id, acao)

        return callback


def nome_do_efeito(efeito_id: str) -> str:
    """O nome que o jogador conhece, a partir do id gravado no efeito.

    Os efeitos sao gravados com `habilidade.id`, que serve ao banco e nao a
    quem le: o resumo do golpe tem de dizer "Marca do Cacador" e nao
    "marca_do_cacador".

    Funcao de modulo porque quem precisa dela e `_aplicar_ligado`, que e
    estatica — e porque ela nao olha para o estado de ninguem.
    """
    habilidade = habilidades.POR_ID.get(efeito_id)
    return habilidade.nome if habilidade else efeito_id.replace('_', ' ')


class Incursoes(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.incursoes: dict[str, Incursao] = {}
        self.bancos: dict[str, BancoDeSalas] = {}
        # Limpeza do canal, tudo em memoria: um restart perde as referencias e
        # deixa a mensagem antiga no lugar, o que e melhor que gravar no banco
        # coisa que so vale por 15 minutos (o prazo do token de interacao).
        self._efemeras: dict[int, list[discord.Interaction]] = {}
        self._chamadas: dict[int, Any] = {}
        # O ultimo anuncio publico de habilidade, por run: e com ele que
        # `_avancar` sabe que nao deve repetir a mesma frase em privado.
        self._publicado: dict[int, str] = {}
        # As mensagens de habilidade usada que estao no canal. Elas contam
        # a historia do combate enquanto ele rola, e viram ruido depois que
        # ele acaba — o painel ja guarda o desfecho.
        self._usadas: dict[int, list[Any]] = {}
        # O que o ultimo descanso deu a cada um, enquanto a sala do descanso
        # esta aberta. {run_id: {user_id: motor.Recuperacao}}
        self._recuperacao: dict[int, dict[int, Any]] = {}
        # O log da rodada no painel, e a fila de cada run: um restart perde o
        # log (o combate continua do banco) e recria as travas.
        self._registros: dict[int, dict[str, Any]] = {}
        self._travas: dict[int, asyncio.Lock] = {}
        self._encerrados: set[tuple[int, int]] = set()

    async def cog_load(self) -> None:
        self._carregar_tolerante()
        await self.restaurar_views()

    def recarregar_incursoes(self) -> None:
        pasta = config.RAIZ / "data" / "incursoes"
        bancos = config.RAIZ / "data" / "bancos"
        # Sala que chama criatura pelo nome le o bestiario: ele relê junto.
        bestiario.recarregar()
        self.incursoes = carregar_todas(pasta) if pasta.is_dir() else {}
        self.bancos = carregar_bancos(bancos) if bancos.is_dir() else {}
        log.info(
            "%d incursão(ões) e %d banco(s) carregados: %s",
            len(self.incursoes),
            len(self.bancos),
            ", ".join(self.incursoes),
        )
        for inc in self.incursoes.values():
            if inc.organizacao not in self.bancos:
                log.warning(
                    "a incursão '%s' é de %s, mas não há banco de salas dessa Organização"
                    " (esperado em data/bancos/%s.json)",
                    inc.id,
                    inc.organizacao,
                    arquivo_da_organizacao(inc.organizacao),
                )

    def _carregar_tolerante(self) -> None:
        """No boot, uma incursão inválida não pode impedir o bot de subir."""
        try:
            self.recarregar_incursoes()
        except Exception:
            log.exception("falha ao carregar as incursões; subindo sem nenhuma")
            self.incursoes = {}

    async def restaurar_views(self) -> None:
        """Reativa os botões das runs que ficaram abertas antes de um restart."""
        for run in await db.runs_vivas(self.bot.db):
            view = await self._view_do_estado(run)
            if view and run["mensagem_id"]:
                self.bot.add_view(view, message_id=run["mensagem_id"])

    async def _view_do_estado(self, run: dict[str, Any]) -> Optional[discord.ui.View]:
        incursao = self.incursoes.get(run["incursao_id"])
        if not incursao:
            return None
        if run["status"] == "recrutando":
            return ViewRecrutamento(self, run["id"])
        if run["status"] == "escolhendo":
            opcoes = await self._opcoes(run, run["linha_atual"])
            return ViewVotacao(self, run["id"], run["linha_atual"], opcoes) if opcoes else None
        if run["status"] in ("em_sala", "objetivo") and run["sala_atual"]:
            sala = await self._sala_corrente(run)
            if sala and sala.tem_teste:
                return ViewSala(self, run["id"], sala.id)
            if sala and sala.tipo == "Descanso":
                # O descanso fica aberto ate alguem escolher o que limpar.
                return ViewDescanso(
                    self, run["id"], sala.id, await self._limpezas_disponiveis(run)
                )
            if sala and sala.e_combate:
                estado = await self._estado_combate(run, sala)
                return ViewCombate(
                    self, run["id"], sala.id, estado.inimigos if estado else None
                )
        return None

    # ------------------------------------------------------------ apoio

    async def _canal(self, run: dict[str, Any]) -> Optional[discord.abc.Messageable]:
        canal = self.bot.get_channel(run["canal_id"])
        if canal is None:
            try:
                canal = await self.bot.fetch_channel(run["canal_id"])
            except discord.HTTPException:
                log.warning("canal %s da run %s sumiu", run["canal_id"], run["id"])
                return None
        return canal

    async def _limpar_botoes(self, run: dict[str, Any]) -> None:
        """Tira os botões da mensagem atual quando aquela etapa se encerra."""
        if not run.get("mensagem_id"):
            return
        canal = await self._canal(run)
        if not canal:
            return
        try:
            mensagem = await canal.fetch_message(run["mensagem_id"])
            await mensagem.edit(view=None)
        except discord.HTTPException:
            pass

    async def _encerrar_run(self, run: dict[str, Any], status: str) -> None:
        """Fecha a run e tira os botões da etapa que ficou pendente.

        Sem isso, uma votação ou um combate abertos no momento do encerramento
        continuariam clicáveis depois que a run acabou.
        """
        await self._limpar_botoes(await db.buscar_run(self.bot.db, run["id"]))
        await db.atualizar_run(self.bot.db, run["id"], status=status, votacao_expira_em=None)
        # O que era de memoria e so desta run sai com ela: um bot que fica
        # ligado por semanas acumularia uma entrada por run encerrada.
        self._recuperacao.pop(run["id"], None)
        self._registros.pop(run["id"], None)

    async def _membros(self, run: dict[str, Any]) -> list[discord.abc.User]:
        return [
            await self._membro(run, user_id)
            for user_id in await db.participantes(self.bot.db, run["id"])
        ]

    async def _membro(self, run: dict[str, Any], user_id: int):
        """O membro do servidor, ou o usuário, para menção e apelido."""
        guilda = self.bot.get_guild(run["guild_id"])
        membro = guilda.get_member(user_id) if guilda else None
        if membro is None and guilda is not None:
            # Sem o intent de membros o cache vem vazio; buscar traz o apelido do servidor.
            try:
                membro = await guilda.fetch_member(user_id)
            except discord.HTTPException:
                membro = None
        return membro or await self.bot.fetch_user(user_id)

    async def _apelidos(self, run: dict[str, Any]) -> dict[int, str]:
        return {m.id: m.display_name for m in await self._membros(run)}

    def _incursao_da_run(self, run: dict[str, Any]) -> Optional[Incursao]:
        return self.incursoes.get(run["incursao_id"])

    def _sala(self, incursao: Incursao, sala_id: Optional[str]) -> Optional[Sala]:
        """A sala pelo id: a final da incursão ou uma do banco da Organização."""
        if not sala_id:
            return None
        if sala_id == incursao.objetivo.id:
            return incursao.objetivo
        banco = self.bancos.get(incursao.organizacao)
        return banco.sala(sala_id) if banco else None

    async def _sala_corrente(self, run: dict[str, Any]) -> Optional[Sala]:
        """A sala em que o grupo está, contando o Tesouro que virou emboscada.

        A emboscada de Mímicos não existe no banco, então não dá para achá-la
        por id. O que a identifica é persistente: existe linha de combate aberta
        neste passo e a sala escrita não é de Combate. Assim ela sobrevive a um
        restart sem tabela nova — e o passo avançar basta para esquecê-la.
        """
        incursao = self._incursao_da_run(run)
        if incursao is None:
            return None
        sala = self._sala(incursao, run["sala_atual"])
        if sala is None or sala.e_combate:
            return sala
        if await db.estado_combate(self.bot.db, run["id"], self._passo(run)):
            return emboscada_de(sala)
        return sala

    async def _opcoes(self, run: dict[str, Any], passo: int) -> list[Sala]:
        """As salas sorteadas para aquele passo desta run."""
        incursao = self._incursao_da_run(run)
        if not incursao:
            return []
        ids = await db.opcoes_do_passo(self.bot.db, run["id"], passo)
        return [s for s in (self._sala(incursao, i) for i in ids) if s]

    async def _sortear_opcoes(self, run: dict[str, Any], passo: int) -> list[str]:
        """Sorteia e grava as salas daquele passo, fora as que o grupo já atravessou."""
        incursao = self._incursao_da_run(run)
        banco = self.bancos.get(incursao.organizacao) if incursao else None
        if not banco:
            return []
        visitadas = await db.salas_visitadas(self.bot.db, run["id"])
        opcoes = motor.sortear_passo(banco.salas, visitadas)
        await db.gravar_opcoes(self.bot.db, run["id"], passo, opcoes)
        return opcoes

    async def _run_do_contexto(
        self, interaction: discord.Interaction, exigir_participante: bool = True
    ) -> Optional[dict[str, Any]]:
        run = await db.run_do_canal(self.bot.db, interaction.channel_id)
        if not run:
            await interaction.response.send_message(
                "Não há incursão em andamento neste canal. Comece uma com `/incursao entrar`.",
                ephemeral=True,
            )
            return None
        if exigir_participante and not await db.esta_na_run(self.bot.db, run["id"], interaction.user.id):
            await interaction.response.send_message("Você não faz parte desta run.", ephemeral=True)
            return None
        return run

    # ------------------------------------------------------- recrutamento

    grupo = app_commands.Group(name="incursao", description="Incursões da sua Organização")

    # O Discord corta o nome de uma opcao em 100 caracteres, e corta no meio
    # da palavra. Melhor cortar o NOME DA ORGANIZACAO, que vem por ultimo,
    # do que deixar o tier cair fora da tela por causa de um nome longo.
    LIMITE_DA_OPCAO = 100

    async def _sugerir_incursoes(
        self, interaction: discord.Interaction, atual: str
    ) -> list[app_commands.Choice[str]]:
        """A lista que aparece ao digitar o comando: nome, tier e Organizacao.

        O tier entra aqui e nao so no cartao da run: a escolha acontece
        NESTA lista, e e o tier que decide se o personagem pode entrar. Sem
        ele o jogador escolhia no escuro e descobria no erro.
        """
        termo = atual.lower()
        opcoes = []
        for inc in self.incursoes.values():
            if termo not in inc.id.lower() and termo not in inc.nome.lower():
                continue
            rotulo = E.titulo_da_incursao(inc)
            sobra = self.LIMITE_DA_OPCAO - len(rotulo) - len(" — ")
            if sobra > 1:
                rotulo += f" — {inc.organizacao[:sobra]}"
            opcoes.append(
                app_commands.Choice(name=rotulo[: self.LIMITE_DA_OPCAO], value=inc.id)
            )
        return opcoes[:25]

    @grupo.command(name="listar", description="Mostra as incursões disponíveis")
    async def listar(self, interaction: discord.Interaction) -> None:
        if not self.incursoes:
            await interaction.response.send_message(
                "Nenhuma incursão carregada. Importe uma planilha com "
                "`tools/importar_planilha.py` e reinicie o bot.",
                ephemeral=True,
            )
            return
        e = discord.Embed(title="Incursões disponíveis", color=E.COR_INCURSAO)
        for inc in self.incursoes.values():
            salas_no_banco = len(self.bancos[inc.organizacao].salas) if inc.organizacao in self.bancos else 0
            e.add_field(
                name=f"{E.titulo_da_incursao(inc)}  ·  `{inc.id}`",
                value=(
                    f"{inc.organizacao} — {inc.tamanho.lower()} ({inc.passos} salas + objetivo)"
                    f" — {inc.recompensa_mes} MEs\n"
                    + E.exigencia_de_tier(inc)
                    + ("" if salas_no_banco else "\n⚠️ sem banco de salas carregado")
                ),
                inline=False,
            )
        await interaction.response.send_message(embed=e, ephemeral=True)

    async def _sugerir_personagens(
        self, interaction: discord.Interaction, atual: str
    ) -> list[app_commands.Choice[str]]:
        return await sugerir_personagens(self.bot.db, interaction, atual)

    @grupo.command(name="entrar", description="Abre o recrutamento de uma incursão neste canal")
    @app_commands.describe(
        incursao_id="Qual incursão",
        personagem="Com qual personagem voce entra (opcional se voce so tem um)",
    )
    @app_commands.autocomplete(incursao_id=_sugerir_incursoes, personagem=_sugerir_personagens)
    async def entrar(
        self,
        interaction: discord.Interaction,
        incursao_id: str,
        personagem: Optional[str] = None,
    ) -> None:
        incursao = self.incursoes.get(incursao_id)
        if not incursao:
            await interaction.response.send_message(
                f"Não conheço a incursão `{incursao_id}`. Veja `/incursao listar`.", ephemeral=True
            )
            return
        if await db.run_do_canal(self.bot.db, interaction.channel_id):
            await interaction.response.send_message(
                "Já existe uma incursão em andamento neste canal. Use `/incursao status`.",
                ephemeral=True,
            )
            return

        bloqueio = await self._motivo_de_bloqueio(interaction.guild_id, interaction.user.id)
        if bloqueio:
            await interaction.response.send_message(bloqueio, ephemeral=True)
            return

        meus = await db.listar_personagens(
            self.bot.db, interaction.guild_id, interaction.user.id
        )
        elegiveis = self._elegiveis(incursao, meus)
        if personagem:
            escolhido = await db.personagem_por_nome(
                self.bot.db, interaction.guild_id, interaction.user.id, personagem
            )
            if not escolhido:
                await interaction.response.send_message(
                    f"Voce nao tem nenhum personagem chamado **{personagem}**. "
                    f"Os seus sao: {', '.join(p['nome'] for p in meus)}.",
                    ephemeral=True,
                )
                return
            if not motor.pode_encarar(escolhido["nivel"], incursao.tier):
                await interaction.response.send_message(
                    self._fora_do_tier(incursao, [escolhido]), ephemeral=True
                )
                return
        elif not elegiveis:
            await interaction.response.send_message(
                self._fora_do_tier(incursao, meus), ephemeral=True
            )
            return
        elif len(elegiveis) == 1:
            escolhido = elegiveis[0]
        else:
            await interaction.response.send_message(
                "Voce tem mais de um personagem para esta incursão: "
                f"{', '.join(p['nome'] for p in elegiveis)}. "
                "Diga qual no campo `personagem`.",
                ephemeral=True,
            )
            return

        run_id = await db.criar_run(
            self.bot.db, interaction.guild_id, interaction.channel_id, incursao.id, interaction.user.id
        )
        await db.adicionar_participante(
            self.bot.db, run_id, interaction.user.id, escolhido["id"],
            tier=tier(escolhido["nivel"]),
        )

        run = await db.buscar_run(self.bot.db, run_id)
        view = ViewRecrutamento(self, run_id)
        await interaction.response.send_message(
            embed=E.recrutamento(incursao, await self._membros(run), interaction.user), view=view
        )
        mensagem = await interaction.original_response()
        await db.atualizar_run(self.bot.db, run_id, mensagem_id=mensagem.id)

    @staticmethod
    def _elegiveis(incursao: Incursao, personagens: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Só os personagens que cabem no tier da incursão."""
        return [p for p in personagens if motor.pode_encarar(p["nivel"], incursao.tier)]

    @staticmethod
    def _fora_do_tier(incursao: Incursao, personagens: list[dict[str, Any]]) -> str:
        """Explica por que nenhum daqueles personagens pode entrar."""
        quem = ", ".join(
            f"**{p['nome']}** (tier {tier(p['nivel'])})" for p in personagens
        )
        return (
            f"**{incursao.nome}** é de tier {incursao.tier}: entra quem for tier "
            f"{incursao.tier} ou menos. "
            f"Seus personagens estão acima disso: {quem}."
        )

    async def _motivo_de_bloqueio(self, guild_id: int, user_id: int) -> Optional[str]:
        """Texto do impedimento para entrar numa run, ou None se estiver liberado."""
        personagens = await db.listar_personagens(self.bot.db, guild_id, user_id)
        if not personagens:
            return (
                "Você ainda não tem personagem. Cadastre um com `/ficha registrar` antes de entrar."
            )
        outra = await db.run_viva_do_jogador(self.bot.db, guild_id, user_id)
        if outra:
            return f"Você já está na run #{outra['id']}. Termine ou desista dela antes."
        semanas = await db.intervalo_semanas(self.bot.db, guild_id)
        ultima = await db.ultima_incursao(self.bot.db, guild_id, user_id)
        agora = datetime.now(config.FUSO)
        if not motor.entrada_liberada(ultima, agora, semanas):
            volta = motor.virada_da_vaga(ultima, semanas)
            quantas = "semana" if semanas == 1 else f"{semanas} semanas"
            return (
                f"Você já entrou numa incursão nesta {quantas} "
                f"(em {ultima:%d/%m}). O intervalo vira na segunda-feira: "
                f"sua vaga volta em **{volta:%d/%m}**."
            )
        return None

    async def _atualizar_recrutamento(self, run: dict[str, Any]) -> None:
        """Redesenha a mensagem de recrutamento com o grupo atual."""
        incursao = self._incursao_da_run(run)
        canal = await self._canal(run)
        if not (incursao and canal and run["mensagem_id"]):
            return
        criador = self.bot.get_user(run["criador_id"])
        membros = await self._membros(run)
        try:
            mensagem = await canal.fetch_message(run["mensagem_id"])
            await mensagem.edit(
                embed=E.recrutamento(incursao, membros, criador or membros[0]),
                view=ViewRecrutamento(self, run["id"]),
            )
        except discord.HTTPException:
            pass

    async def efetivar_entrada(
        self, interaction: discord.Interaction, run_id: int, personagem_id: int
    ) -> None:
        """Coloca o jogador na run com o personagem escolhido."""
        run = await db.buscar_run(self.bot.db, run_id)
        if not run or run["status"] != "recrutando":
            await interaction.response.send_message(
                "Este recrutamento já foi encerrado.", ephemeral=True
            )
            return

        personagem = await db.buscar_personagem(self.bot.db, personagem_id)
        if not personagem or personagem["user_id"] != interaction.user.id:
            await interaction.response.send_message(
                "Esse personagem não é seu.", ephemeral=True
            )
            return
        if len(await db.participantes(self.bot.db, run_id)) >= config.TAMANHO_GRUPO:
            await interaction.response.send_message("O grupo já está cheio.", ephemeral=True)
            return

        # Ultima checagem: o menu pode estar velho, e o nivel pode ter subido nesse meio-tempo.
        incursao = self._incursao_da_run(run)
        if incursao and not motor.pode_encarar(personagem["nivel"], incursao.tier):
            await interaction.response.send_message(
                self._fora_do_tier(incursao, [personagem]), ephemeral=True
            )
            return

        await db.adicionar_participante(
            self.bot.db, run_id, interaction.user.id, personagem_id,
            tier=tier(personagem["nivel"]),
        )
        await interaction.response.send_message(
            f"Voce entrou com **{personagem['nome']}** (tier {tier(personagem['nivel'])}).",
            ephemeral=True,
        )

        run = await db.buscar_run(self.bot.db, run_id)
        await self._atualizar_recrutamento(run)
        if len(await db.participantes(self.bot.db, run_id)) >= config.TAMANHO_GRUPO:
            await self._iniciar(run)

    async def recrutar(self, interaction: discord.Interaction, run_id: int, acao: str) -> None:
        run = await db.buscar_run(self.bot.db, run_id)
        if not run or run["status"] != "recrutando":
            await interaction.response.send_message(
                "Este recrutamento já foi encerrado.", ephemeral=True
            )
            return
        incursao = self._incursao_da_run(run)
        if not incursao:
            await interaction.response.send_message(
                f"A incursão `{run['incursao_id']}` não está mais carregada.", ephemeral=True
            )
            return

        if acao == "entrar":
            if await db.esta_na_run(self.bot.db, run_id, interaction.user.id):
                await interaction.response.send_message("Você já está no grupo.", ephemeral=True)
                return
            membros_atuais = await db.participantes(self.bot.db, run_id)
            if len(membros_atuais) >= config.TAMANHO_GRUPO:
                await interaction.response.send_message("O grupo já está cheio.", ephemeral=True)
                return
            bloqueio = await self._motivo_de_bloqueio(run["guild_id"], interaction.user.id)
            if bloqueio:
                await interaction.response.send_message(bloqueio, ephemeral=True)
                return

            personagens = await db.listar_personagens(
                self.bot.db, run["guild_id"], interaction.user.id
            )
            elegiveis = self._elegiveis(incursao, personagens)
            if not elegiveis:
                await interaction.response.send_message(
                    self._fora_do_tier(incursao, personagens), ephemeral=True
                )
                return
            if len(elegiveis) == 1:
                await self.efetivar_entrada(interaction, run_id, elegiveis[0]["id"])
            else:
                await interaction.response.send_message(
                    "Escolha com qual personagem entrar:",
                    view=SeletorPersonagemEntrada(self, run_id, elegiveis),
                    ephemeral=True,
                )
            return

        elif acao == "sair":
            if interaction.user.id == run["criador_id"]:
                await interaction.response.send_message(
                    "Quem abriu a incursão não pode sair. Use `/incursao desistir` para cancelar.",
                    ephemeral=True,
                )
                return
            if not await db.remover_participante(self.bot.db, run_id, interaction.user.id):
                await interaction.response.send_message("Você não está no grupo.", ephemeral=True)
                return
            # Saiu antes de a incursao comecar: nao joga, nao recebe. Quem e
            # ejetado no MEIO da run continua na lista de quem recebe.
            await db.tirar_o_direito_ao_ouro(self.bot.db, run_id, interaction.user.id)

        elif acao == "comecar":
            if interaction.user.id != run["criador_id"]:
                await interaction.response.send_message(
                    "Só quem abriu a incursão pode começar antes do grupo encher.", ephemeral=True
                )
                return
            await interaction.response.defer()
            await self._iniciar(run)
            return

        await interaction.response.defer()
        membros = await self._membros(run)
        criador = self.bot.get_user(run["criador_id"]) or interaction.user
        await interaction.edit_original_response(
            embed=E.recrutamento(incursao, membros, criador), view=ViewRecrutamento(self, run_id)
        )

    async def _iniciar(self, run: dict[str, Any]) -> None:
        participantes = await db.participantes(self.bot.db, run["id"])
        if not participantes:
            return
        incursao = self._incursao_da_run(run)
        canal = await self._canal(run)
        if not incursao:
            return

        banco = self.bancos.get(incursao.organizacao)
        if not banco:
            if canal:
                await canal.send(
                    f"Não há banco de salas de **{incursao.organizacao}** carregado, "
                    "então não dá para sortear o caminho. Avise quem administra o bot."
                )
            return
        await db.marcar_ultima_incursao(self.bot.db, run["guild_id"], participantes)
        await db.inicializar_hp(self.bot.db, run["id"])
        await db.atualizar_run(self.bot.db, run["id"], status="escolhendo", linha_atual=1)

        if canal:
            if run["mensagem_id"]:
                try:
                    mensagem = await canal.fetch_message(run["mensagem_id"])
                    await mensagem.edit(view=None)
                except discord.HTTPException:
                    pass
            # Lore e o grupo na mesma mensagem, com os retratos lado a lado.
            personagens = await db.personagens_da_run(self.bot.db, run["id"])
            membros = [await self._membro(run, p["user_id"]) for p in personagens]
            cartoes, faixa = await E.abertura_do_grupo(personagens, membros)
            await canal.send(
                embeds=[E.lore_abertura(incursao, len(participantes)), *cartoes[:9]],
                file=faixa or discord.utils.MISSING,
            )
        await self._abrir_votacao(await db.buscar_run(self.bot.db, run["id"]), 1)

    # ------------------------------------------------------------ votação

    async def _abrir_votacao(self, run: dict[str, Any], linha: int) -> None:
        incursao = self._incursao_da_run(run)
        canal = await self._canal(run)
        if not (incursao and canal):
            return
        # A sala que o grupo acabou de atravessar sai do canal. No primeiro
        # passo nao ha sala anterior: o que esta la e o recrutamento, que fica.
        if linha > 1:
            await self._apagar_passo_anterior(run)
        opcoes = await self._opcoes(run, linha)
        if not opcoes:
            try:
                await self._sortear_opcoes(run, linha)
            except ValueError as exc:
                await canal.send(f"Não consegui sortear as salas deste passo: {exc}.")
                return
            opcoes = await self._opcoes(run, linha)
        if not opcoes:
            await canal.send(
                "Não achei as salas sorteadas para este passo. O banco da Organização mudou?"
            )
            return
        total = len(await db.participantes_de_pe(self.bot.db, run["id"]))
        votos = await db.votos_da_linha(self.bot.db, run["id"], linha)
        view = ViewVotacao(self, run["id"], linha, opcoes)
        mensagem = await canal.send(
            f"🗳️ {await self._chamar(run)} — escolham por onde seguir.",
            embed=E.votacao(incursao, linha, opcoes, votos, total, incursao.passos),
            view=view,
        )
        await db.atualizar_run(
            self.bot.db,
            run["id"],
            status="escolhendo",
            linha_atual=linha,
            sala_atual=None,
            mensagem_id=mensagem.id,
            votacao_expira_em=None,
        )

    async def votar(
        self, interaction: discord.Interaction, run_id: int, linha: int, sala_id: str
    ) -> None:
        run = await db.buscar_run(self.bot.db, run_id)
        if not run or run["status"] != "escolhendo" or run["linha_atual"] != linha:
            await interaction.response.send_message("Esta votação já foi encerrada.", ephemeral=True)
            return
        if not await db.esta_na_run(self.bot.db, run_id, interaction.user.id):
            await interaction.response.send_message("Você não faz parte desta run.", ephemeral=True)
            return
        if not await db.esta_de_pe(self.bot.db, run_id, interaction.user.id):
            await interaction.response.send_message(
                "Você está caído — quem está no chão não escolhe o caminho.",
                ephemeral=True,
            )
            return

        await db.registrar_voto(self.bot.db, run_id, linha, interaction.user.id, sala_id)
        incursao = self._incursao_da_run(run)
        sala = self._sala(incursao, sala_id)
        await interaction.response.send_message(
            f"Voto registrado: **{sala.nome if sala else sala_id}**.", ephemeral=True
        )
        # O aviso so vale enquanto a votacao esta aberta: some quando o grupo entra.
        self._guardar_efemera(run_id, interaction)

        votos = await db.votos_da_linha(self.bot.db, run_id, linha)
        total = len(await db.participantes_de_pe(self.bot.db, run_id))
        opcoes = await self._opcoes(run, linha)

        if interaction.message is not None:
            try:
                await interaction.message.edit(
                    embed=E.votacao(incursao, linha, opcoes, votos, total, incursao.passos),
                    view=ViewVotacao(self, run_id, linha, opcoes),
                )
            except discord.HTTPException:
                pass

        await self._fechar_votacao(run, linha)

    async def _fechar_votacao(self, run: dict[str, Any], linha: int) -> None:
        """Fecha a votacao assim que uma sala tem a maioria do grupo.

        Nao ha prazo: a run espera indefinidamente, mas nao espera quem falta
        depois que o resultado ja esta decidido.
        """
        run = await db.buscar_run(self.bot.db, run["id"])
        if not run or run["status"] != "escolhendo" or run["linha_atual"] != linha:
            return
        incursao = self._incursao_da_run(run)
        canal = await self._canal(run)
        if not (incursao and canal):
            return

        votos = await db.votos_da_linha(self.bot.db, run["id"], linha)
        contagem: dict[str, int] = {}
        for opcao in votos.values():
            contagem[opcao] = contagem.get(opcao, 0) + 1

        if not contagem:
            return  # ninguem votou ainda: a votacao segue aberta

        total = len(await db.participantes_de_pe(self.bot.db, run["id"]))
        maioria = maioria_de(total)
        maximo = max(contagem.values())
        empatadas = [sala_id for sala_id, n in contagem.items() if n == maximo]
        decidida = len(empatadas) == 1

        if decidida and maximo >= maioria:
            # Maioria fechada: nao ha por que esperar quem ainda nao votou.
            escolhida_id = empatadas[0]
        elif len(votos) >= total and decidida:
            # Todos votaram sem maioria absoluta: vale a mais votada.
            escolhida_id = empatadas[0]
        elif len(votos) >= total:
            await canal.send(
                "Empate na votação, com todo mundo já tendo votado. Ninguém avança "
                "enquanto o grupo não desempatar — clique em outra opção para trocar seu voto."
            )
            return
        else:
            return  # ainda da para virar: espera mais votos

        # A sala e tomada ANTES de qualquer mensagem: o que vem depois tem
        # `await` de rede no meio, e e por ali que o segundo clique passava.
        if not await db.tomar_a_sala(
            self.bot.db, run["id"], linha, escolhida_id
        ):
            return  # outro clique levou esta sala; este nao abre nada

        faltaram = total - len(votos)
        if faltaram > 0:
            nome = self._sala(incursao, escolhida_id).nome
            await canal.send(
                f"**{nome}** fechou com {maximo} de {total} votos — maioria formada, "
                f"o grupo não espera os {faltaram} que faltam."
            )

        await self._limpar_botoes(run)
        await self._entrar_na_sala(
            await db.buscar_run(self.bot.db, run["id"]),
            self._sala(incursao, escolhida_id),
        )

    # -------------------------------------------------------------- salas

    async def _entrar_na_sala(self, run: dict[str, Any], sala: Sala) -> None:
        # A votacao cumpriu o papel dela: o grupo ja escolheu. Sai do canal, e
        # somem com ela os "voto registrado" de cada um.
        await self._apagar_passo_anterior(run)
        await self._limpar_efemeras(run["id"])
        canal = await self._canal(run)
        if not canal:
            return
        # Atravessar a sala a tira do sorteio: ela nao volta a ser oferecida.
        await db.registrar_visita(self.bot.db, run["id"], self._passo(run), sala.id)
        total = len(await db.participantes_de_pe(self.bot.db, run["id"]))

        if sala.tipo == "Descanso":
            await db.atualizar_run(self.bot.db, run["id"], status="em_sala", sala_atual=sala.id)
            # O contador de descansos e o que zera as habilidades por descanso.
            await db.contar_descanso(self.bot.db, run["id"])
            combatentes = await self._combatentes(run)
            feito = motor.aplicar_descanso(combatentes)
            await db.definir_hp_varios(
                self.bot.db, run["id"], {c.user_id: c.hp_atual for c in combatentes}
            )
            # O que o descanso deu fica guardado pelo tempo da sala: o cartao
            # e reescrito a cada limpeza, e so aqui se sabe o "antes".
            self._recuperacao[run["id"]] = feito
            mudancas = await self._linhas_do_descanso(run)
            # Alem de curar, o descanso deixa cada um limpar UMA condicao sua.
            # A sala fecha quando todos escolherem — e quem nao carrega nada ja
            # entra marcado, entao grupo limpo nao precisa clicar.
            disponiveis = await self._limpezas_disponiveis(run)
            faltam = await self._descanso_pendente(run)
            mensagem = await canal.send(
                embed=E.descanso(
                    sala, mudancas, disponiveis, faltam=len(faltam)
                ),
                view=(
                    ViewDescanso(self, run["id"], sala.id, disponiveis)
                    if faltam
                    else None
                ),
            )
            # O descanso tambem e a sala do passo: sai do canal na proxima escolha.
            await db.atualizar_run(self.bot.db, run["id"], mensagem_id=mensagem.id)
            if faltam:
                await canal.send(
                    f"🏕️ {await self._chamar(run, faltam)} — o descanso deixa cada "
                    f"um limpar **uma** condição sua."
                )
                return
            await self._concluir_sala(
                await db.buscar_run(self.bot.db, run["id"]), sala, None
            )
            return

        incursao = self._incursao_da_run(run)
        await db.atualizar_run(
            self.bot.db,
            run["id"],
            status="em_sala",
            sala_atual=sala.id,
            votacao_expira_em=None,
        )

        if sala.e_combate:
            # O painel do combate ja traz descricao, monstro e HP: uma mensagem so.
            await self._abrir_combate(await db.buscar_run(self.bot.db, run["id"]), sala)
            return

        embed, arquivo = E.sala_aberta(
            sala, run["linha_atual"], 0, total,
            incursao.passos if incursao else None,
            # O tier, senao o cartao mostra a CD do tier 1 e `motor.testar`
            # cobra a do tier da run: o grupo via um numero e rolava contra
            # outro.
            tier=self._tier_da_run(run),
        )
        view = ViewSala(self, run["id"], sala.id) if sala.tem_teste else None
        chamada = (
            f"🎲 {await self._chamar(run)} — hora de rolar." if sala.tem_teste else None
        )
        mensagem = await canal.send(
            chamada, embed=embed, view=view, file=arquivo or discord.utils.MISSING
        )
        await db.atualizar_run(self.bot.db, run["id"], mensagem_id=mensagem.id)

    async def _marcar_sala_superada(self, run: dict[str, Any], sala: Sala) -> None:
        """Registra a sala vencida. Nao paga ninguem: o ouro sai no fecho.

        Antes cada sala pagava na hora, e uma run que acabasse com o grupo
        todo no chao deixava o ouro das salas do caminho na bolsa de quem
        tinha chegado ali. Agora a incursao paga de uma vez, e so se for
        concluida — fracasso nao rende nada.

        Os dois caminhos de "sala superada", o combate e o teste, podem
        chamar sem combinar entre si: a marca e por passo, e marcar duas
        vezes marca a mesma linha.
        """
        await db.marcar_sala_superada(
            self.bot.db, run["id"], self._passo(run), sala.id
        )

    async def _pagar_a_run(self, run: dict[str, Any]) -> int:
        """O ouro da incursao inteira, de uma vez, no fecho de uma vitoria.

        Vai para TODOS que passaram pela run, e nao so para quem estava de
        pe no fim: quem caiu no objetivo e quem foi ejetado por Exaustao no
        meio do caminho jogaram a incursao e levam o mesmo que os outros.

        O valor sai da contagem de salas superadas, entao nao depende de
        quem estava presente em qual sala — e o grupo que atravessou, nao
        cada um por si.
        """
        tier = self._tier_da_run(run) or 1
        superadas = await db.salas_superadas(self.bot.db, run["id"])
        das_salas = superadas * mercado.ouro_da_sala(tier)
        do_fecho = mercado.ouro_da_incursao(tier)
        pagos = 0
        for p in await db.quem_recebe_da_run(self.bot.db, run["id"]):
            recebeu = await db.lancar_ouro(
                self.bot.db, p["id"], das_salas,
                f"Salas superadas ({superadas})",
                run_id=run["id"], chave="salas",
            )
            recebeu |= await db.lancar_ouro(
                self.bot.db, p["id"], do_fecho, "Incursao concluida",
                run_id=run["id"], chave="conclusao",
            )
            pagos += 1 if recebeu else 0
        return pagos

    async def _creditar(
        self, run: dict[str, Any], pontos: int, motivo: str, chave: str
    ) -> bool:
        """Credita pontos à Organização da incursão. Ignora repetição e valor zero."""
        incursao = self._incursao_da_run(run)
        if not incursao or pontos <= 0:
            return False
        return await db.lancar_pontos(
            self.bot.db,
            run["guild_id"],
            incursao.organizacao,
            pontos,
            motivo,
            run_id=run["id"],
            chave=chave,
        )

    async def _balanco(self, run: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
        """Os lançamentos da run e o total da Organização, para o embed de desfecho."""
        incursao = self._incursao_da_run(run)
        if not incursao:
            return [], 0
        lancamentos = await db.pontos_da_run(self.bot.db, run["id"])
        placar = await db.placar(self.bot.db, run["guild_id"])
        return lancamentos, placar.get(incursao.organizacao, 0)

    def _passo(self, run: dict[str, Any]) -> int:
        """O passo atual do caminho. O objetivo fica um depois do último."""
        incursao = self._incursao_da_run(run)
        if run["status"] == "objetivo" and incursao:
            return incursao.passos + 1
        return run["linha_atual"]

    def _tier_da_run(self, run: dict[str, Any]) -> Optional[int]:
        """O tier da incursão — é ele que dimensiona debuff, buff e maldição."""
        incursao = self._incursao_da_run(run)
        return incursao.tier if incursao else None

    async def _saldo(self, run: dict[str, Any], user_id: int) -> condicoes.Penalidades:
        """O que este personagem carrega de condição, já somado."""
        return condicoes.penalidades(
            await db.condicoes_de(self.bot.db, run["id"], user_id),
            self._tier_da_run(run),
        )

    async def _combatentes(
        self, run: dict[str, Any], efeitos_ligados: Optional[list[dict]] = None
    ) -> list[Combatente]:
        """Monta os combatentes juntando a ficha de cada um com o HP atual da run."""
        personagens = await db.personagens_da_run(self.bot.db, run["id"])
        tier_atual = self._tier_da_run(run)
        carregadas = await db.condicoes_da_run(self.bot.db, run["id"])
        combatentes = []
        for p in personagens:
            # As passivas da classe entram como numero: multiataque, critico
            # mais facil e dano extra saem daqui.
            efeitos = p.get("efeitos") or {}
            # E por cima delas, o que as salas deixaram: debuff, maldicao,
            # exaustao e buff. Camada propria porque sao somas com sinal, e
            # habilidades.juntar consolida com max().
            saldo = condicoes.penalidades(carregadas.get(p["user_id"], {}), tier_atual)
            hp_max = condicoes.hp_maximo(p["hp_max"], saldo)
            atual = hp_max if p["hp_atual"] is None else min(p["hp_atual"], hp_max)
            combatentes.append(
                Combatente(
                    user_id=p["user_id"],
                    nome=p["nome"],
                    ca=p["ca"],
                    bonus_ataque=p["bonus_ataque"] + saldo.ataque,
                    dano_arma=p["dano_arma"],
                    hp_max=hp_max,
                    hp_atual=atual,
                    thp=p.get("thp") or 0,
                    ataques=efeitos.get("ataques", 1),
                    critico_em=efeitos.get("critico_em", 20),
                    dano_extra=efeitos.get("dano_extra", 0),
                    dano_ferido=efeitos.get("dano_ferido", 0),
                    # Ataques Abencoados, do clerigo: dado a mais em todo golpe.
                    dano_bonus=efeitos.get("dano_bonus", ""),
                    saves={
                        atributo: valor + saldo.saves
                        for atributo, valor in (p.get("saves") or {}).items()
                    },
                    # A Exaustao tira e as botas do mercado somam, no mesmo
                    # lugar: nenhum dos dois e save de DES.
                    mod_iniciativa_extra=(
                        saldo.iniciativa + efeitos.get("bonus_iniciativa", 0)
                    ),
                    cura_recebida_pct=saldo.cura_recebida_pct,
                    # A classe diz onde ele fica na sala; as passivas somam.
                    # O que esta ligado e o que ele gerou agindo entram depois,
                    # em `_aplicar_ligado`, cada um no seu campo.
                    ameaca=ameaca.inicial(p.get("classe")) + efeitos.get("ameaca", 0),
                    classe=str(p.get("classe") or ""),
                )
            )
        for ligado in efeitos_ligados or []:
            self._aplicar_ligado(combatentes, ligado)
        self._aplicar_aura_totemica(combatentes, personagens)
        self._aplicar_infusoes(combatentes, personagens)
        self._aplicar_aura_de_save(combatentes, personagens)
        self._aplicar_escudo_arcano(combatentes, personagens, tier_atual)
        self._aplicar_bichinho(combatentes, personagens, tier_atual)
        # Os aliados conjurados entram como combatentes comuns, com dono: assim
        # herdam ameaca, HP, iniciativa e painel sem nada de novo. O que os
        # separa e `dono`, que faz a vez deles ser resolvida sozinha.
        for conjurado in await db.invocacoes(self.bot.db, run["id"], self._passo(run)):
            combatentes.append(
                Combatente(
                    user_id=conjurado["user_id"],
                    nome=conjurado["nome"],
                    ca=conjurado["ca"],
                    bonus_ataque=conjurado["ataque"],
                    dano_arma=conjurado["dano"],
                    hp_max=conjurado["hp_max"],
                    hp_atual=conjurado["hp_atual"],
                    ameaca=conjurado["ameaca"],
                    dono=conjurado["dono"],
                )
            )
        return combatentes

    @staticmethod
    def _aplicar_infusoes(
        combatentes: list[Combatente], personagens: list[dict[str, Any]]
    ) -> None:
        """O equipamento que o artífice infundiu, no grupo inteiro.

        No livro ele replica itens mágicos e os distribui; aqui os itens ficam
        na planilha do grupo, então o que entra no bot é o que o item faz — um
        ponto a mais para todos, no acerto, na CA ou no dano. Como a aura do
        xamã, vale a melhor quando há mais de um artífice.

        O lado dos testes de perícia não entra aqui: é o Flash of Genius que
        cuida dele, e de um jeito melhor, porque chega depois da rolagem.
        """
        melhor: dict[str, int] = {}
        for p in personagens:
            infusao = ((p.get("efeitos") or {}).get("infusao")) or {}
            for onde, quanto in infusao.items():
                melhor[onde] = max(melhor.get(onde, 0), quanto)
        if not melhor:
            return
        for c in combatentes:
            c.bonus_ataque += melhor.get("acerto", 0)
            c.ca_extra += melhor.get("ca", 0)
            c.dano_extra += melhor.get("dano", 0)

    @staticmethod
    def _aplicar_aura_de_save(
        combatentes: list[Combatente], personagens: list[dict[str, Any]]
    ) -> None:
        """Sabedoria Arcana: o grupo inteiro resiste melhor às criaturas.

        Como a Infusão e a aura do xamã, vale a melhor e não a soma. Entra em
        todos os atributos, porque a criatura escolhe qual save cobra.
        """
        melhor = max(
            (((p.get("efeitos") or {}).get("aura_save") or 0) for p in personagens),
            default=0,
        )
        if melhor <= 0:
            return
        for c in combatentes:
            c.saves = {atributo: valor + melhor for atributo, valor in c.saves.items()}

    @staticmethod
    def _aplicar_bichinho(
        combatentes: list[Combatente], personagens: list[dict[str, Any]], tier: int
    ) -> None:
        """O espírito animal do druida, que cuida dele desde o começo da luta.

        É a opção de cura do Wild Companion: o bicho lambe as feridas quando o
        combate abre. As outras duas opções (dano e teste) são número puro e
        entram pelas chaves que já existiam.
        """
        for p in personagens:
            por_tier = ((p.get("efeitos") or {}).get("bichinho_cura")) or 0
            if not por_tier:
                continue
            quem = next((c for c in combatentes if c.user_id == p["user_id"]), None)
            if quem is not None:
                motor.curar_quanto(quem, por_tier * max(1, tier))

    @staticmethod
    def _aplicar_escudo_arcano(
        combatentes: list[Combatente], personagens: list[dict[str, Any]], tier: int
    ) -> None:
        """Escudo Arcano: o mago entra em combate com o escudo de pé.

        No livro ele recarrega a cada magia de abjuração; aqui recarrega a
        cada combate, que é o que o bot tem de ciclo. É o que deixa o d6 de
        vida do mago jogável sem mexer na tabela dele.
        """
        for p in personagens:
            por_tier = ((p.get("efeitos") or {}).get("escudo_arcano")) or 0
            if not por_tier:
                continue
            quem = next((c for c in combatentes if c.user_id == p["user_id"]), None)
            if quem is not None:
                motor.ganhar_thp(quem, por_tier * max(1, tier))

    @staticmethod
    def _aplicar_aura_totemica(
        combatentes: list[Combatente], personagens: list[dict[str, Any]]
    ) -> None:
        """Enquanto o xama tem THP, o grupo inteiro leva um bonus.

        A aura vem da Convocacao totemica; o tier 5 a substitui por uma
        versao mais forte.
        """
        melhor = {}
        for p in personagens:
            totem = ((p.get("efeitos") or {}).get("totem")) or {}
            if not totem.get("aura"):
                continue
            dono = next((c for c in combatentes if c.user_id == p["user_id"]), None)
            if dono is None or not dono.tem_thp:
                continue
            if totem.get("aura", 0) >= melhor.get("aura", 0):
                melhor = totem
        if not melhor:
            return
        for c in combatentes:
            c.bonus_ataque += melhor.get("aura", 0)
            c.dano_extra += melhor.get("aura_dano", melhor.get("aura", 0))

    @staticmethod
    def _aplicar_ligado(combatentes: list[Combatente], ligado: dict) -> None:
        """Passa um efeito com prazo para o combatente a que ele pertence."""
        valor = ligado["valor"] or {}
        if ligado["alvo_tipo"] == "personagem":
            quem = next(
                (c for c in combatentes if c.user_id == ligado["alvo_id"]), None
            )
            if quem is None:
                return
            quem.dano_extra += valor.get("dano_extra", 0)
            quem.ca_extra += valor.get("ca", 0)
            # A acumulacao chega pelo mesmo `run_efeitos` que as habilidades,
            # mas vai para outro campo: a marca do painel e para quem tem algo
            # LIGADO chamando atencao, nao para quem simplesmente agiu.
            if ligado["efeito"] == "ameaca_gerada":
                quem.ameaca_gerada += valor.get("ameaca", 0)
            else:
                quem.ameaca_extra += valor.get("ameaca", 0)
            quem.reducao_dano = max(quem.reducao_dano, valor.get("reducao_dano", 0.0))
            quem.cura_por_turno = max(
                quem.cura_por_turno, valor.get("cura_por_turno", 0.0)
            )
            quem.vantagem = quem.vantagem or bool(valor.get("vantagem"))
            # Buff curto de grupo: o critico mais facil e o dado de dano a
            # mais. Sem isto a Danca totemica e os Guerreiros ancioes
            # gravavam o efeito e ele nao chegava a valer em golpe nenhum.
            if valor.get("critico_em"):
                quem.critico_em = min(quem.critico_em, valor["critico_em"])
            if valor.get("dano_bonus"):
                quem.dano_bonus = valor["dano_bonus"]
                quem.rotulo_dano_bonus = nome_do_efeito(ligado["efeito"])
            # Haste e afins: o segundo golpe por duracao.
            if valor.get("ataques"):
                quem.ataques = max(quem.ataques, valor["ataques"])
            # Fly: multiplica o peso dele no sorteio de alvo. Vale o menor
            # fator, que e o mais protegido.
            if valor.get("ameaca_fator") is not None:
                quem.ameaca_fator = min(
                    quem.ameaca_fator, float(valor["ameaca_fator"])
                )
            # Circle of Power: passar no save passa a escapar inteiro.
            if valor.get("save_anula"):
                quem.save_anula = True
            # Wild Shape: o corpo dele passa a ser de outro bicho. O dado de
            # arma e substituido, nao somado — e a forma que bate, nao ele.
            if valor.get("dano_arma"):
                quem.dano_arma = valor["dano_arma"]
                quem.forma = valor.get("forma", "")
            if valor.get("veneno_no_golpe"):
                quem.veneno_no_golpe = max(
                    quem.veneno_no_golpe, valor["veneno_no_golpe"]
                )
            # A sequencia do Martial Arts nao entra aqui: ela e contada golpe a
            # golpe dentro do turno, em atacar().
            return

        # Efeito posto num inimigo: quem ganha e o dono da marca.
        dono = next((c for c in combatentes if c.user_id == ligado["dono"]), None)
        if dono is None:
            return
        if valor.get("dano_bonus"):
            # (rotulo, expressao): o resumo do golpe diz "Marca do Cacador
            # 1d6 -> 4", e para isso precisa do NOME de quem marcou.
            dono.dano_por_alvo[ligado["alvo_id"]] = (
                nome_do_efeito(ligado["efeito"]),
                valor["dano_bonus"],
            )
        if valor.get("vantagem"):
            dono.vantagem_contra.add(ligado["alvo_id"])

    async def _estado_combate(
        self, run: dict[str, Any], sala: Sala
    ) -> Optional[EstadoCombate]:
        passo = self._passo(run)
        linha = await db.estado_combate(self.bot.db, run["id"], passo)
        if not linha:
            return None
        # Os numeros vem do banco, nao do conteudo: se o inimigo for escalado, e
        # esse que vale pelo resto do combate.
        inimigos = [
            motor.Inimigo(
                indice=r["indice"],
                nome=r["nome"],
                ca=r["ca"],
                ataque=r["ataque"],
                dano=r["dano"],
                hp_max=r["hp_max"],
                hp_atual=r["hp_atual"],
                ataques=r.get("ataques") or 1,
                carregada=bool(r.get("carregada", 1)),
                saves=r.get("saves") or {},
                saves_vantagem=r.get("saves_vantagem") or [],
                habilidade=r.get("habilidade"),
                golpes=r.get("golpes") or [],
                matilha=bool(r.get("matilha")),
                regeneracao=r.get("regeneracao") or 0,
            )
            for r in await db.inimigos_do_combate(self.bot.db, run["id"], passo)
        ]
        if not inimigos:
            return None
        ligados = await db.efeitos_ativos(
            self.bot.db, run["id"], passo, linha["rodada"] - 1
        )
        for ligado in ligados:
            if ligado["alvo_tipo"] != "inimigo":
                continue
            alvo = next((i for i in inimigos if i.indice == ligado["alvo_id"]), None)
            if alvo is None:
                continue
            if ligado["efeito"] == "atordoado":
                alvo.atordoado = True
            # Synaptic Static: a criatura atrapalhada erra mais enquanto dura.
            penalidade = (ligado["valor"] or {}).get("penalidade_ataque") or 0
            if penalidade:
                alvo.penalidade_ataque = max(alvo.penalidade_ataque, penalidade)
        combatentes = await self._combatentes(run, ligados)
        for ligado in ligados:
            if ligado["alvo_tipo"] == "personagem" and ligado["efeito"] == "atordoado":
                quem = next(
                    (c for c in combatentes if c.user_id == ligado["alvo_id"]), None
                )
                if quem:
                    quem.atordoado = True
        return EstadoCombate(
            inimigos=inimigos,
            rodada=linha["rodada"],
            combatentes=combatentes,
        )

    async def _abrir_combate(self, run: dict[str, Any], sala: Sala) -> None:
        canal = await self._canal(run)
        if not canal:
            return
        # A criatura escrita no banco e a do tier 1: aqui ela vira a do tier
        # de QUEM entrou. Pelo grupo e nao pela incursao, porque incursao sem
        # tier declarado vale TIER_MAXIMO para liberar a entrada — e isso
        # daria criatura de tier 5 em toda incursao aberta.
        tier_do_grupo = motor.tier_do_grupo(await self._niveis(run))
        inimigos = [motor.escalar_monstro(m, tier_do_grupo) for m in sala.monstros]
        await db.iniciar_combate(self.bot.db, run["id"], self._passo(run), sala.id, inimigos)

        incursao = self._incursao_da_run(run)
        e_objetivo = bool(incursao and sala.id == incursao.objetivo.id)
        estado = await self._estado_combate(run, sala)
        ordem = await self._garantir_iniciativa(run, estado) if estado else []
        embed, arquivo = E.combate(
            sala,
            estado,
            ordem=ordem,
            vez=0,
            e_objetivo=e_objetivo,
            recompensa=sala.recompensa if e_objetivo else None,
            condicoes_do_grupo=await db.condicoes_da_run(self.bot.db, run["id"]),
        )
        de_pe = [c.user_id for c in estado.ativos] if estado else None
        mensagem = await canal.send(
            f"⚔️ {await self._chamar(run, de_pe)} — combate! Escolham ataque **ou** "
            f"habilidade: as ações saem uma de cada vez, na ordem da iniciativa.",
            embed=embed,
            view=ViewCombate(self, run["id"], sala.id, estado.inimigos if estado else None),
            file=arquivo or discord.utils.MISSING,
        )
        await db.atualizar_run(self.bot.db, run["id"], mensagem_id=mensagem.id)
        # Quem rolou acima de todo o grupo age antes de alguém clicar.
        await self._avancar(await db.buscar_run(self.bot.db, run["id"]), sala)

    async def _garantir_iniciativa(
        self, run: dict[str, Any], estado: EstadoCombate
    ) -> list[dict[str, Any]]:
        """A ordem do combate: rola na primeira vez e depois só lê do banco.

        Um combate aberto antes de existir a iniciativa rola na hora em que
        alguém mexe nele, e segue dali.
        """
        passo = self._passo(run)
        ordem = await db.iniciativa(self.bot.db, run["id"], passo)
        if not ordem:
            await db.gravar_iniciativa(
                self.bot.db, run["id"], passo, motor.rolar_iniciativas(estado)
            )
            ordem = await db.iniciativa(self.bot.db, run["id"], passo)
        return ordem

    async def _atualizar_painel(
        self,
        run: dict[str, Any],
        sala: Sala,
        estado,
        encerrado: bool = False,
    ) -> None:
        """Reescreve o painel do combate no lugar, sem postar mensagem nova."""
        canal = await self._canal(run)
        atual = await db.buscar_run(self.bot.db, run["id"])
        if not canal or not atual or not atual["mensagem_id"]:
            return
        embed, _ = await self._embed_do_painel(atual, sala, estado, encerrado)
        view = (
            None if encerrado else ViewCombate(self, run["id"], sala.id, estado.inimigos)
        )
        try:
            mensagem = await canal.fetch_message(atual["mensagem_id"])
            await mensagem.edit(embed=embed, view=view)
        except discord.HTTPException:
            pass

    async def _embed_do_painel(
        self, run: dict[str, Any], sala: Sala, estado, encerrado: bool = False
    ):
        """O painel com a ordem da iniciativa, de quem é a vez e o log da rodada."""
        passo = self._passo(run)
        linha = await db.estado_combate(self.bot.db, run["id"], passo)
        incursao = self._incursao_da_run(run)
        registro = self._registros.get(run["id"]) or {}
        return E.combate(
            sala,
            estado,
            ordem=await db.iniciativa(self.bot.db, run["id"], passo),
            vez=linha["vez"] if linha else 0,
            turnos=await db.turnos_da_rodada(
                self.bot.db, run["id"], passo, estado.rodada
            ),
            registro=registro.get("linhas"),
            anterior=registro.get("anterior"),
            e_objetivo=bool(incursao and sala.id == incursao.objetivo.id),
            encerrado=encerrado,
            condicoes_do_grupo=await db.condicoes_da_run(self.bot.db, run["id"]),
        )

    async def _niveis(self, run: dict[str, Any]) -> list[int]:
        return [p["nivel"] for p in await db.personagens_da_run(self.bot.db, run["id"])]

    async def atacar(
        self,
        interaction: discord.Interaction,
        run_id: int,
        sala_id: str,
        alvo_indice: Optional[int] = None,
    ) -> None:
        """Escolhe o ataque da rodada. Ele sai quando a iniciativa chegar em você."""
        self._guardar_efemera(run_id, interaction)
        # Avisa o Discord na hora que a resposta vem depois: isto troca os
        # 3 segundos que ele da para a primeira resposta por 15 minutos. Sem
        # isto, um combate grande numa maquina modesta estoura o prazo e o
        # jogador ve "esta interacao falhou" (erro 10062). Dai em diante
        # toda resposta tem de sair pelo `_dizer`.
        #
        # `thinking=True` NAO e enfeite, e o que faz o `ephemeral` valer.
        # Num clique de botao o defer simples e DEFERRED_MESSAGE_UPDATE —
        # "vou editar a mensagem do botao" — e o ephemeral e ignorado em
        # silencio. Dai `delete_original_response` apagava o PAINEL do
        # combate, que e a mensagem onde os botoes moram.
        await interaction.response.defer(ephemeral=True, thinking=True)
        run = await db.buscar_run(self.bot.db, run_id)
        if not run or run["status"] not in ("em_sala", "objetivo") or run["sala_atual"] != sala_id:
            await self._dizer(interaction, "Este combate já terminou.")
            return
        if not await db.esta_na_run(self.bot.db, run_id, interaction.user.id):
            await self._dizer(interaction, "Você não faz parte desta run.")
            return

        incursao = self._incursao_da_run(run)
        sala = await self._sala_corrente(run)
        estado = await self._estado_combate(run, sala)
        if estado is None:
            await self._dizer(interaction, "Este combate já terminou.")
            return

        atacante = estado.combatente(interaction.user.id)
        if atacante is None:
            await self._dizer(interaction, 
                "Você não tem ficha cadastrada. Use `/ficha registrar`.")
            return
        if atacante.caido:
            await self._dizer(interaction, 
                "Você está caído — fica fora do resto deste combate.")
            return
        if atacante.atordoado:
            await self._dizer(interaction, 
                "Você está atordoado e perde esta rodada.")
            return

        alvo = estado.alvo_preferido(alvo_indice)
        if alvo is None:
            await self._dizer(interaction, 
                "Esse inimigo já caiu — escolha outro alvo.")
            return

        passo = self._passo(run)
        gasto = await db.acao_do_turno(
            self.bot.db, run_id, passo, estado.rodada, interaction.user.id
        )
        if gasto or not await db.marcar_turno(
            self.bot.db, run_id, passo, estado.rodada, interaction.user.id, "ataque",
            alvos=[alvo.indice] if alvo_indice is not None else [],
            resolvida=False,
        ):
            await self._dizer(interaction, 
                self._turno_gasto(gasto or "ataque"))
            return
        await self._avancar(run, sala, interaction)

    async def _resolver_ataque(
        self, run: dict[str, Any], estado: EstadoCombate, user_id: int, alvos: list[int]
    ) -> str:
        """O ataque do turno, quando a vez chega. Devolve o resumo para o jogador."""
        atacante = estado.combatente(user_id)
        passo = self._passo(run)
        # O alvo escolhido pode ter caído enquanto a ação esperava: vai no próximo.
        alvo = (estado.alvo_preferido(alvos[0]) if alvos else None) or estado.alvo_preferido()
        if atacante is None or alvo is None:
            return "Nenhum inimigo de pé para atacar."

        # Multiataque gasta o turno inteiro de uma vez: se o alvo cair no meio,
        # o golpe seguinte vai para o proximo inimigo de pe.
        golpes: list[tuple[motor.GolpeAtaque, Any]] = []
        # O indice continua de onde parou: uma habilidade pode ter gravado
        # golpes antes do turno, e dois golpes nao podem dividir a mesma chave.
        indice = await db.proximo_indice_de_ataque(
            self.bot.db, run["id"], passo, estado.rodada, user_id
        )
        personagem = await self._personagem_na_run(run, user_id)
        sequencia = ((personagem or {}).get("efeitos") or {}).get("sequencia") or {}
        pilha = await self._pilha_de_sequencia(run, user_id, passo)
        for _ in range(max(1, atacante.ataques)):
            atual = estado.alvo_preferido(alvo.indice) or estado.alvo_preferido()
            if atual is None:
                break
            # A sequencia ja conta dentro do turno: o segundo golpe usa o do primeiro.
            golpe = motor.atacar_inimigo(atacante, atual, None, bonus_extra=pilha)
            if sequencia:
                pilha = motor.proxima_sequencia(
                    pilha,
                    golpe.acertou,
                    sequencia.get("por_acerto", 1),
                    sequencia.get("teto", 2),
                )
            golpes.append((golpe, atual))
            await db.registrar_ataque(
                self.bot.db, run["id"], passo, estado.rodada, user_id,
                golpe.d20, golpe.bonus, golpe.ca_alvo, golpe.dano, atual.indice, indice,
            )
            indice += 1

        # Inspiracao no ataque: o golpe que errou por pouco passa a acertar,
        # antes de o HP ir para o banco.
        await self._inspirar_o_golpe(run, estado, atacante, golpes)
        await db.definir_hp_inimigos(
            self.bot.db,
            run["id"],
            passo,
            {inimigo.indice: inimigo.hp_atual for _golpe, inimigo in golpes},
        )
        # A forma de aranha envenena quem ela acerta: o equivalente do lado do
        # inimigo e o ataque dele piorar, que e o que `penalidade_ataque` faz.
        if atacante is not None and atacante.veneno_no_golpe:
            for golpe, inimigo in golpes:
                if not golpe.acertou or inimigo.caido:
                    continue
                inimigo.penalidade_ataque = max(
                    inimigo.penalidade_ataque, atacante.veneno_no_golpe
                )
                await db.aplicar_efeito(
                    self.bot.db, run["id"], passo, "inimigo", inimigo.indice,
                    "veneno_da_aranha",
                    {"penalidade_ataque": atacante.veneno_no_golpe},
                    estado.rodada + 2, dono=user_id,
                )
        if personagem:
            await self._totem_do_golpe(run, personagem, atacante, golpes)
            await self._bencao_do_patrono(run, personagem, atacante, golpes)
        if sequencia:
            await self._guardar_sequencia(run, user_id, passo, pilha)
        self._registrar(run, estado.rodada, [E.linha_golpe(g) for g, _i in golpes])
        return E.resumo_do_golpe([(g, i.nome) for g, i in golpes])

    def _trava(self, run_id: int) -> asyncio.Lock:
        """Uma fila por run: dois cliques ao mesmo tempo não resolvem a vez duas vezes."""
        return self._travas.setdefault(run_id, asyncio.Lock())

    def _registrar(self, run: dict[str, Any], rodada: int, linhas: list[str]) -> None:
        """Guarda no log da rodada o que acabou de acontecer, para o painel.

        Fica em memória: um restart perde o log, não o combate.
        """
        registro = self._registros.setdefault(
            run["id"], {"rodada": rodada, "linhas": [], "anterior": None}
        )
        if registro["rodada"] != rodada:
            registro["anterior"] = (registro["rodada"], registro["linhas"])
            registro["rodada"], registro["linhas"] = rodada, []
        registro["linhas"].extend(linhas)

    async def _avancar(
        self,
        run: dict[str, Any],
        sala: Sala,
        interaction: Optional[discord.Interaction] = None,
    ) -> None:
        """Anda a iniciativa até precisar de alguém que ainda não escolheu.

        Uma de cada vez, na ordem: a criatura age sozinha quando chega a vez
        dela; o personagem que já escolheu tem a ação resolvida; quem está caído
        ou atordoado perde a vez. Para no primeiro personagem sem ação escolhida.
        Passando do último, a rodada vira e a fila recomeça do topo.

        Quem clicou (`interaction`) recebe o resultado se a vez dele chegou
        agora, ou o aviso de que a ação ficou guardada.
        """
        respondido = False

        async def responder(texto: str) -> None:
            nonlocal respondido
            if interaction is None or respondido:
                return
            respondido = True
            # Se esta exata frase ja foi para o canal, nao repete em
            # privado: quem clicou via a propria habilidade duas vezes.
            # Mas a interacao foi adiada e PRECISA ser fechada, senao o
            # Discord deixa o "pensando..." pendurado para sempre.
            if texto == self._publicado.get(run["id"]):
                try:
                    await interaction.delete_original_response()
                except discord.HTTPException:
                    pass
                return
            await self._dizer(interaction, texto)
            # Registra na hora de mandar, nao antes: parte destas respostas sai
            # depois da trava, e a rodada pode ter virado no meio. Registrada
            # antes, ela seria removida da lista por _limpar_efemeras sem ter
            # chegado a existir — e ficaria no canal para sempre.
            self._guardar_efemera(run["id"], interaction)

        esperando: Optional[str] = None
        ativo = True
        # O fim do combate roda fora da trava: vencer pode abrir o combate do
        # objetivo, que entra de novo aqui, e a trava nao e reentrante.
        encerrar = None
        async with self._trava(run["id"]):
            viradas = 0
            while True:
                run = await db.buscar_run(self.bot.db, run["id"])
                if (
                    not run
                    or run["status"] not in ("em_sala", "objetivo")
                    or run["sala_atual"] != sala.id
                ):
                    ativo = False
                    break
                estado = await self._estado_combate(run, sala)
                if estado is None:
                    ativo = False
                    break
                passo = self._passo(run)
                if estado.encerrado:
                    ativo = False
                    # Quem chegar aqui depois nao encerra o mesmo combate de novo.
                    if (run["id"], passo) not in self._encerrados:
                        self._encerrados.add((run["id"], passo))
                        encerrar = (run, estado)
                    break
                ordem = await self._garantir_iniciativa(run, estado)
                vez = (await db.estado_combate(self.bot.db, run["id"], passo))["vez"]

                if vez >= len(ordem):
                    viradas += 1
                    if viradas > MAX_RODADAS_SOZINHAS:
                        # Nunca deve acontecer; se acontecer, o grupo precisa
                        # saber por que o painel parou.
                        canal = await self._canal(run)
                        if canal:
                            await canal.send(
                                f"⏳ O grupo inteiro segue preso depois de "
                                f"{MAX_RODADAS_SOZINHAS} rodadas. O combate espera "
                                f"alguem se soltar — se travar de vez, "
                                f"`/incursao desistir` encerra a run."
                            )
                        break
                    await self._virar_rodada(run, sala, estado)
                    continue

                ator = ordem[vez]
                if ator["tipo"] == motor.INIMIGO:
                    inimigo = estado.inimigo(ator["alvo_id"])
                    if inimigo is not None and not inimigo.caido:
                        await self._vez_do_inimigo(run, estado, inimigo, ordem[:vez])
                    await db.definir_vez(self.bot.db, run["id"], passo, vez + 1)
                    continue

                user_id = ator["alvo_id"]
                combatente = estado.combatente(user_id)
                # Aliado conjurado: ninguem clica por ele. Age sozinho, como a
                # criatura, e a vez anda.
                if combatente is not None and combatente.e_invocacao:
                    if not combatente.caido and not combatente.atordoado:
                        await self._vez_da_invocacao(run, estado, combatente)
                    await db.definir_vez(self.bot.db, run["id"], passo, vez + 1)
                    continue
                turno = await db.turno_de(
                    self.bot.db, run["id"], passo, estado.rodada, user_id
                )
                if combatente is None or combatente.caido or combatente.atordoado:
                    await self._perder_a_vez(run, estado, combatente, turno)
                    await db.definir_vez(self.bot.db, run["id"], passo, vez + 1)
                    continue
                if turno is None:
                    # Combate de antes da iniciativa: o golpe gravado ja valeu.
                    if await db.acao_do_turno(
                        self.bot.db, run["id"], passo, estado.rodada, user_id
                    ):
                        await db.definir_vez(self.bot.db, run["id"], passo, vez + 1)
                        continue
                    esperando = ator["nome"]
                    break
                if not turno["resolvida"]:
                    texto = await self._resolver_turno(run, estado, user_id, turno)
                    await db.resolver_turno(
                        self.bot.db, run["id"], passo, estado.rodada, user_id
                    )
                    if interaction is not None and interaction.user.id == user_id:
                        await responder(texto)
                await db.definir_vez(self.bot.db, run["id"], passo, vez + 1)

            if ativo:
                await self._atualizar_painel(run, sala, estado)
        if encerrar:
            await responder("O combate acabou antes da sua vez.")
            await self._encerrar_combate(encerrar[0], sala, encerrar[1])
            return
        if esperando:
            await responder(
                f"Ação guardada: sai quando a iniciativa chegar em você. "
                f"Agora é a vez de **{esperando}**."
            )
        else:
            await responder("Ação guardada.")

    async def _perder_a_vez(
        self, run: dict[str, Any], estado: EstadoCombate, combatente, turno
    ) -> None:
        """Caído ou atordoado na hora da vez: a ação guardada não sai.

        O uso de uma habilidade escolhida volta — ela não chegou a acontecer.
        """
        if combatente is not None and combatente.atordoado and not combatente.caido:
            self._registrar(run, estado.rodada, [f"💫 {combatente.nome} está atordoado e perde a vez"])
        if not turno or turno["resolvida"]:
            return
        passo = self._passo(run)
        await db.resolver_turno(self.bot.db, run["id"], passo, estado.rodada, turno["user_id"])
        habilidade = cl.POR_ID.get(turno["acao"])
        if habilidade is not None:
            await db.devolver_uso(
                self.bot.db, run["id"], turno["user_id"], habilidade.chave_de_uso,
                self._chave_de_recarga(habilidade, run, passo),
            )

    async def _resolver_turno(
        self, run: dict[str, Any], estado: EstadoCombate, user_id: int, turno: dict
    ) -> str:
        """Faz a ação que o personagem escolheu, agora que a vez chegou."""
        if turno["acao"] == "ataque":
            texto = await self._resolver_ataque(run, estado, user_id, turno["alvos"])
            await self._gerar_ameaca(run, estado, user_id, None)
            return texto
        personagem = await self._personagem_na_run(run, user_id)
        habilidade = next(
            (
                h for _t, h in (personagem or {}).get("habilidades") or []
                if h.id == turno["acao"]
            ),
            None,
        )
        if habilidade is None:
            return "Essa habilidade nao esta mais disponivel."
        texto = await self._resolver_habilidade(
            run, estado, user_id, habilidade, turno["alvos"]
        )
        await self._gerar_ameaca(run, estado, user_id, habilidade.acao)
        self._registrar(run, estado.rodada, [f"✨ {estado.combatente(user_id).nome} usa **{habilidade.nome}**"])
        return texto

    # A ameaca gerada vale pelo combate inteiro, e nao por um numero de
    # rodadas. O prazo grande diz isso: quem apaga a conta e a troca de sala,
    # porque o `passo` faz parte da chave em `run_efeitos`.
    PRAZO_DO_COMBATE = 10 ** 6

    async def _gerar_ameaca(
        self, run: dict[str, Any], estado: EstadoCombate, user_id: int, acao
    ) -> None:
        """O que o personagem acabou de fazer chama atencao da criatura.

        Mora aqui, no `_resolver_turno`, e nao em cada resolvedor: este e o
        gargalo por onde o ataque e a habilidade passam os dois, e o uso FORA
        de combate nao passa — que e o certo, nao ha criatura para chamar.
        """
        quem = estado.combatente(user_id)
        if quem is None or quem.e_invocacao:
            return
        await db.somar_ameaca_gerada(
            self.bot.db, run["id"], self._passo(run), user_id,
            ameaca.gerada_por(quem.classe, acao), self.PRAZO_DO_COMBATE,
        )

    async def _vez_do_inimigo(
        self,
        run: dict[str, Any],
        estado: EstadoCombate,
        inimigo: motor.Inimigo,
        antes: list[dict[str, Any]],
    ) -> None:
        """A criatura age: ataca ou conjura, e o que ela fez vai para o log."""
        if inimigo.atordoado:
            self._registrar(run, estado.rodada, [f"💫 {inimigo.nome} está atordoado e perde a vez"])
            return
        feito = motor.turno_do_inimigo(inimigo, estado, None)
        if feito.regenerou:
            await db.definir_hp_inimigos(
                self.bot.db, run["id"], self._passo(run), {inimigo.indice: inimigo.hp_atual}
            )
        # Inspiracao no save: antes de gravar qualquer coisa. Mexer aqui evita
        # escrever no banco o dano, o atordoamento e a condicao que o bardo
        # acabou de impedir — e so depois apaga-los.
        await self._inspirar_o_save(run, estado, feito.investidas)
        for atingido in feito.atingidos:
            await self._gravar_hp_do_combatente(run, atingido)
        if inimigo.habilidade:
            await db.definir_carga_inimigos(
                self.bot.db, run["id"], self._passo(run), {inimigo.indice: inimigo.carregada}
            )
        # Quem ja passou da vez nesta rodada perde a da proxima; quem ainda
        # nao agiu perde a desta.
        ja_agiram = {a["alvo_id"] for a in antes if a["tipo"] == motor.PERSONAGEM}
        await self._guardar_atordoamentos(run, estado, feito.investidas, ja_agiram)
        pegaram = await self._guardar_debuffs(run, feito.investidas)
        await self._reacoes_do_revide(run, estado, feito.golpes)
        linhas = []
        if feito.regenerou:
            linhas.append(f"🩹 **{inimigo.nome}** regenera **{feito.regenerou}** HP")
        linhas += [
            E.texto_da_investida(investida)
            for investida in feito.investidas
            if not investida.do_golpe
        ]
        for posicao, (golpe, atingido) in enumerate(feito.golpes):
            arma = f" · {golpe.arma}" if golpe.arma else ""
            linhas.append(
                f"↩️ **{golpe.atacante}**{arma} · "
                f"{E.texto_do_contra_ataque(golpe, atingido.nome)}"
            )
            # O teste que o golpe impos sai logo abaixo dele.
            if posicao in feito.efeitos_dos_golpes:
                linhas.append(E.texto_da_investida(feito.efeitos_dos_golpes[posicao]))
        linhas += [f"🧪 {texto}" for texto in pegaram]
        self._registrar(run, estado.rodada, linhas)

    async def _virar_rodada(self, run: dict[str, Any], sala: Sala, estado) -> None:
        """Passou do último da iniciativa: efeitos viram e a fila volta ao topo."""
        estado.rodada += 1
        await db.atualizar_rodada(self.bot.db, run["id"], self._passo(run), estado.rodada)
        await self._virar_efeitos(run, estado)
        self._registrar(run, estado.rodada, [])
        await self._limpar_efemeras(run["id"])
        await self._apagar_chamada(run["id"])
        await self._apagar_usadas(run["id"])
        # O painel e editado no lugar, e edicao nao notifica ninguem: a chamada
        # da rodada vai numa mensagem propria, para todos que podem agir.
        seguinte = await self._estado_combate(run, sala)
        canal = await self._canal(run)
        if canal and seguinte is not None and not seguinte.encerrado and seguinte.ativos:
            self._chamadas[run["id"]] = await canal.send(
                f"⚔️ **Rodada {seguinte.rodada}** — "
                f"{await self._chamar(run, [c.user_id for c in seguinte.ativos])} "
                f"— escolham a ação; ela sai na ordem da iniciativa."
            )

    async def _encerrar_combate(self, run: dict[str, Any], sala: Sala, estado) -> None:
        """Um dos lados caiu: fecha o painel e segue a run (ou a encerra)."""
        await self._atualizar_painel(run, sala, estado, encerrado=True)
        await self._limpar_efemeras(run["id"])
        await self._apagar_chamada(run["id"])
        await self._apagar_usadas(run["id"])
        self._registros.pop(run["id"], None)
        if estado.inimigos_derrotados:
            await self._apos_combate_vencido(run, sala, estado)
            return
        canal = await self._canal(run)
        await self._encerrar_run(run, "fracasso")
        incursao = self._incursao_da_run(run)
        # Mesmo derrotado, o grupo levou a run ate o fim: a participacao conta.
        await self._creditar(
            run, config.PONTOS_PARTICIPACAO, "Participação na incursão", "participacao"
        )
        if canal:
            lancamentos, total = await self._balanco(run)
            await canal.send(
                embed=E.run_fracassada(
                    incursao, lancamentos, total,
                    await self._caminho(run), sala,
                    await db.ouro_da_run(self.bot.db, run["id"]),
                )
            )

    async def _dizer(
        self, interaction: discord.Interaction, texto: str, *, view=None
    ) -> None:
        """Resposta privada que funciona antes e depois do `defer`.

        O Discord da 3 SEGUNDOS para a primeira resposta a uma interacao.
        Passando disso o token morre e qualquer resposta devolve
        `10062 Unknown interaction` — o jogador ve "esta interacao falhou".
        Tres segundos bastavam na maquina de desenvolvimento e nao bastam no
        servidor, que e um oitavo de OCPU compartilhado.

        A saida e `defer()` no inicio do comando, que troca os 3 segundos por
        15 minutos. Mas depois dele `response.send_message` passa a ser erro:
        a resposta ja foi dada. Este ajudante escolhe sozinho.

        Edita a resposta original em vez de mandar followup de proposito:
        `_limpar_efemeras` apaga as efemeras com `delete_original_response`,
        que so alcanca a original. Com followup elas ficariam orfas no canal.

        `view` existe porque nem toda resposta destes comandos e texto: a
        habilidade que pede alvo abre um menu. Tudo que responde depois do
        `defer` tem de passar por aqui — responder direto levanta
        `InteractionResponded` dentro do callback, e o jogador fica com o
        "pensando..." pendurado para sempre.
        """
        if interaction.response.is_done():
            await interaction.edit_original_response(content=texto, view=view)
        else:
            await interaction.response.send_message(
                texto, view=view, ephemeral=True
            )

    def _guardar_efemera(self, run_id: int, interaction: discord.Interaction) -> None:
        """Marca uma resposta privada para sumir quando a rodada virar."""
        self._efemeras.setdefault(run_id, []).append(interaction)

    async def _limpar_efemeras(self, run_id: int) -> None:
        """Apaga as respostas privadas da rodada que acabou.

        Cada uma so pode ser apagada pela propria interacao, e o token dela
        vale 15 minutos — o que passou disso simplesmente fica.
        """
        for interaction in self._efemeras.pop(run_id, []):
            try:
                await interaction.delete_original_response()
            except (discord.HTTPException, AttributeError):
                pass

    async def _apagar_usadas(self, run_id: int) -> None:
        """Tira do canal os anuncios de habilidade da rodada que acabou.

        Enquanto a rodada corre eles sao a narracao: quem conjurou o que,
        e em quem. Virada a rodada viram historico, e o painel — que fica
        e e editado no lugar — ja guarda o estado de agora.

        Roda no virar da rodada E no fim do combate: a segunda chamada
        pega o que foi usado na ultima rodada, que nao chega a virar.
        """
        self._publicado.pop(run_id, None)
        for mensagem in self._usadas.pop(run_id, []):
            try:
                await mensagem.delete()
            except (discord.HTTPException, AttributeError):
                pass

    async def _apagar_chamada(self, run_id: int) -> None:
        """Tira do canal a marcacao da rodada anterior."""
        mensagem = self._chamadas.pop(run_id, None)
        if mensagem is None:
            return
        try:
            await mensagem.delete()
        except (discord.HTTPException, AttributeError):
            pass

    async def _apagar_passo_anterior(self, run: dict[str, Any]) -> None:
        """Apaga a mensagem do passo que acabou: a votacao, ou a sala.

        O canal fica com um cartao so — o do momento. O caminho inteiro volta
        no fim da run, no resumo.
        """
        atual = await db.buscar_run(self.bot.db, run["id"]) or run
        if not atual.get("mensagem_id"):
            return
        canal = await self._canal(atual)
        if canal is None:
            return
        try:
            mensagem = await canal.fetch_message(atual["mensagem_id"])
            await mensagem.delete()
        except (discord.HTTPException, AttributeError):
            pass
        await db.atualizar_run(self.bot.db, run["id"], mensagem_id=None)

    async def _caminho(self, run: dict[str, Any]) -> list[Sala]:
        """As salas por onde o grupo passou, na ordem, para o resumo do fim."""
        incursao = self._incursao_da_run(run)
        if not incursao:
            return []
        visitadas = await db.salas_visitadas(self.bot.db, run["id"])
        salas = [self._sala(incursao, sala_id) for sala_id in visitadas]
        return [s for s in salas if s is not None]

    async def _chamar(
        self, run: dict[str, Any], user_ids: Optional[list[int]] = None
    ) -> str:
        """Marca quem precisa agir agora. Sem lista, marca o grupo inteiro.

        Vai no `content` da mensagem, e nao no embed: e o texto solto que faz o
        Discord notificar.
        """
        if user_ids is None:
            user_ids = await db.participantes(self.bot.db, run["id"])
        return " ".join(f"<@{user_id}>" for user_id in user_ids)

    def _turno_gasto(self, acao: str) -> str:
        """O aviso de quem ja agiu, dizendo com o que gastou o turno."""
        if acao == "ataque":
            return "Você já atacou nesta rodada — é um ataque **ou** uma habilidade."
        habilidade = cl.POR_ID.get(acao)
        nome = habilidade.nome if habilidade else acao
        return (
            f"Você já usou **{nome}** nesta rodada — é uma habilidade **ou** um ataque."
        )

    # ------------------------------------------------------ habilidades

    @staticmethod
    def _chave_de_recarga(habilidade, run: dict[str, Any], passo: int) -> str:
        """Quando esta habilidade zera: por combate, por descanso ou por run."""
        if habilidade.escopo == "combate":
            return f"combate:{passo}"
        if habilidade.escopo == "descanso":
            return f"descanso:{run['descansos']}"
        return "incursao"

    async def _habilidades_disponiveis(
        self, run: dict[str, Any], personagem: dict[str, Any], passo: int
    ) -> list[tuple]:
        """As ativas que o bot ja executa e que ainda tem uso. (hab, restantes)."""
        gastos = await db.usos_da_run(self.bot.db, run["id"], personagem["user_id"])
        disponiveis = []
        for _tier, habilidade in personagem.get("habilidades") or []:
            if not habilidade.acionavel:
                continue
            if (habilidade.acao or {}).get("tipo") == "reacao":
                continue  # dispara sozinha quando o gatilho acontece
            chave = self._chave_de_recarga(habilidade, run, passo)
            restantes = habilidade.vezes - gastos.get((habilidade.chave_de_uso, chave), 0)
            if restantes > 0:
                disponiveis.append((habilidade, restantes))
        return disponiveis

    async def _personagem_na_run(
        self, run: dict[str, Any], user_id: int
    ) -> Optional[dict[str, Any]]:
        for p in await db.personagens_da_run(self.bot.db, run["id"]):
            if p["user_id"] == user_id:
                return p
        return None

    async def abrir_habilidades(
        self, interaction: discord.Interaction, run_id: int, sala_id: str
    ) -> None:
        """Mostra, so para quem clicou, o que ele pode usar agora."""
        self._guardar_efemera(run_id, interaction)
        run = await db.buscar_run(self.bot.db, run_id)
        if not run or run["status"] not in ("em_sala", "objetivo"):
            await interaction.response.send_message("Esta sala ja terminou.", ephemeral=True)
            return
        personagem = await self._personagem_na_run(run, interaction.user.id)
        if personagem is None:
            await interaction.response.send_message(
                "Voce nao faz parte desta run.", ephemeral=True
            )
            return

        # Em combate, quem ja agiu nao abre o menu: o turno e um so.
        incursao = self._incursao_da_run(run)
        sala = await self._sala_corrente(run)
        if sala is not None and sala.e_combate:
            estado = await self._estado_combate(run, sala)
            if estado is not None:
                gasto = await db.acao_do_turno(
                    self.bot.db, run_id, self._passo(run), estado.rodada,
                    interaction.user.id,
                )
                if gasto:
                    await interaction.response.send_message(
                        self._turno_gasto(gasto), ephemeral=True
                    )
                    return

        disponiveis = await self._habilidades_disponiveis(
            run, personagem, self._passo(run)
        )
        if not disponiveis:
            await interaction.response.send_message(
                "Voce nao tem habilidade para usar agora. Veja `/ficha ver`: as ativas "
                "marcadas *(em breve)* ainda nao estao prontas, e as outras podem ter "
                "acabado os usos.",
                ephemeral=True,
            )
            return

        opcoes = [
            (h.id, h.nome, f"{restantes} uso(s) — {h.texto}")
            for h, restantes in disponiveis
        ]
        await interaction.response.send_message(
            "O que voce usa?",
            view=SeletorHabilidade(self, run_id, sala_id, opcoes),
            ephemeral=True,
        )

    async def usar_habilidade(
        self,
        interaction: discord.Interaction,
        run_id: int,
        sala_id: str,
        habilidade_id: str,
        alvos: Optional[list[int]] = None,
    ) -> None:
        """Gasta um uso e escolhe a habilidade, pedindo alvo se precisar.

        Em combate ela sai na vez do personagem, como o ataque; fora dele,
        na hora.
        """
        self._guardar_efemera(run_id, interaction)
        # Avisa o Discord na hora que a resposta vem depois: isto troca os
        # 3 segundos que ele da para a primeira resposta por 15 minutos. Sem
        # isto, um combate grande numa maquina modesta estoura o prazo e o
        # jogador ve "esta interacao falhou" (erro 10062). Dai em diante
        # toda resposta tem de sair pelo `_dizer`.
        #
        # `thinking=True` NAO e enfeite, e o que faz o `ephemeral` valer.
        # Num clique de botao o defer simples e DEFERRED_MESSAGE_UPDATE —
        # "vou editar a mensagem do botao" — e o ephemeral e ignorado em
        # silencio. Dai `delete_original_response` apagava o PAINEL do
        # combate, que e a mensagem onde os botoes moram.
        await interaction.response.defer(ephemeral=True, thinking=True)
        run = await db.buscar_run(self.bot.db, run_id)
        if not run or run["status"] not in ("em_sala", "objetivo"):
            await self._dizer(interaction, "Esta sala ja terminou.")
            return
        personagem = await self._personagem_na_run(run, interaction.user.id)
        if personagem is None:
            await self._dizer(interaction, 
                "Voce nao faz parte desta run.")
            return

        passo = self._passo(run)
        disponiveis = await self._habilidades_disponiveis(run, personagem, passo)
        habilidade = next((h for h, _r in disponiveis if h.id == habilidade_id), None)
        if habilidade is None:
            await self._dizer(interaction, 
                "Essa habilidade nao esta disponivel agora.")
            return

        incursao = self._incursao_da_run(run)
        sala = await self._sala_corrente(run)
        estado = await self._estado_combate(run, sala) if sala and sala.e_combate else None
        acao = habilidade.acao or {}

        # Quem usa precisa estar de pe quando a habilidade e de combate.
        atacante = estado.combatente(interaction.user.id) if estado else None
        if estado is not None and (atacante is None or atacante.caido):
            await self._dizer(interaction, 
                "Voce esta caido — fica fora do resto deste combate.")
            return
        if atacante is not None and atacante.atordoado:
            await self._dizer(interaction, 
                "Você está atordoado e perde esta rodada.")
            return

        exigida = acao.get("exige")
        if exigida and estado is not None:
            ligados = await db.efeitos_ativos(
                self.bot.db, run["id"], passo, estado.rodada - 1
            )
            tem = any(
                e["efeito"] == exigida and e["alvo_id"] == interaction.user.id
                for e in ligados
            )
            if not tem:
                await self._dizer(interaction, 
                    f"**{habilidade.nome}** so vale com a outra habilidade ligada.",
                )
                return

        # So a cura funciona fora do combate: o resto mexe em rodada e inimigo.
        if acao.get("tipo") != "cura" and estado is None:
            await self._dizer(interaction, 
                "Essa habilidade so vale em combate.")
            return

        # Em combate o personagem age uma vez por rodada: ou ataca, ou usa uma
        # habilidade. Reacao nao passa por aqui — dispara sozinha.
        if estado is not None:
            gasto = await db.acao_do_turno(
                self.bot.db, run_id, passo, estado.rodada, interaction.user.id
            )
            if gasto:
                await self._dizer(interaction, 
                    self._turno_gasto(gasto))
                return

        # Falta escolher em quem: abre o segundo menu antes de gastar o uso.
        if alvos is None:
            pedido = await self._pedir_alvo(interaction, run, sala_id, habilidade, estado)
            if pedido is not False:
                return
            alvos = []

        if not await db.gastar_uso(
            self.bot.db,
            run_id,
            interaction.user.id,
            habilidade.chave_de_uso,
            self._chave_de_recarga(habilidade, run, passo),
            habilidade.vezes,
        ):
            await self._dizer(interaction, 
                "Os usos desta habilidade ja acabaram.")
            return

        if estado is None:
            texto = await self._resolver_habilidade(
                run, None, interaction.user.id, habilidade, alvos
            )
            await self._dizer(interaction, texto)
            return

        # Quickened Spell: o feiticeiro lanca a magia como acao de bonus, e o
        # turno fica livre para atacar depois. A magia resolve na hora, em vez
        # de esperar a vez na iniciativa — senao ela nao seria "rapida".
        personagem = await self._personagem_na_run(run, interaction.user.id)
        if ((personagem or {}).get("efeitos") or {}).get("magia_rapida"):
            texto = await self._resolver_habilidade(
                run, estado, interaction.user.id, habilidade, alvos or []
            )
            await self._dizer(interaction, texto)
            self._guardar_efemera(run_id, interaction)
            await self._atualizar_painel(run, sala, estado)
            return

        if not await db.marcar_turno(
            self.bot.db, run_id, passo, estado.rodada, interaction.user.id,
            habilidade.id, alvos=alvos, resolvida=False,
        ):
            await db.devolver_uso(
                self.bot.db, run_id, interaction.user.id, habilidade.chave_de_uso,
                self._chave_de_recarga(habilidade, run, passo),
            )
            await self._dizer(interaction, 
                self._turno_gasto("ataque"))
            return
        await self._avancar(run, sala, interaction)

    async def _resolver_habilidade(
        self, run: dict[str, Any], estado, user_id: int, habilidade, alvos: list[int]
    ) -> str:
        """Faz a habilidade valer. Devolve o que o jogador vê."""
        acao = habilidade.acao or {}
        if acao.get("tipo") == "cura":
            return await self._resolver_cura(run, user_id, habilidade, acao, alvos, estado)
        if acao.get("tipo") == "grupo":
            return await self._resolver_grupo(run, estado, habilidade, acao, user_id)
        if acao.get("tipo") == "duracao":
            return await self._resolver_duracao(run, user_id, estado, habilidade, acao, alvos)
        if acao.get("tipo") == "save":
            return await self._resolver_save(run, user_id, estado, habilidade, acao, alvos)
        if acao.get("tipo") == "invocar":
            return await self._resolver_invocar(run, user_id, estado, habilidade, acao)
        if acao.get("tipo") == "forma":
            return await self._resolver_forma(
                run, user_id, estado, habilidade, acao,
                alvos[0] if (alvos and acao.get("alvo") == "aliado") else None,
            )
        return await self._resolver_golpes(run, user_id, estado, habilidade, acao, alvos)

    async def _resolver_forma(
        self, run: dict[str, Any], user_id: int, estado, habilidade, acao,
        alvo_id: Optional[int] = None,
    ) -> str:
        """Wild Shape: o druida veste o corpo de outro bicho.

        Os números da forma vêm por tier, como o resto da tabela: dado fixo
        quebraria o tier 1 ou seria inútil no 5. A vida temporária é o corpo da
        besta — quando ela acaba, o druida volta a sangrar no HP dele.
        """
        passo = self._passo(run)
        tier_atual = max(1, self._tier_da_run(run))
        # O Wild Shape do druida cai nele; o Polymorph do feiticeiro cai num
        # aliado. A conta e a mesma: muda so quem veste o corpo.
        quem = estado.combatente(alvo_id if alvo_id is not None else user_id)
        if quem is None:
            return "Alvo invalido."

        dano = acao["dano"][min(tier_atual, max(acao["dano"]))]
        efeitos = {"dano_arma": dano, "forma": acao["nome"]}
        if acao.get("ca"):
            efeitos["ca"] = acao["ca"]
        if acao.get("ataques"):
            efeitos["ataques"] = acao["ataques"]
        if acao.get("veneno_no_golpe"):
            efeitos["veneno_no_golpe"] = acao["veneno_no_golpe"]
        await db.aplicar_efeito(
            self.bot.db, run["id"], passo, "personagem", quem.user_id,
            habilidade.id, efeitos, estado.rodada + acao.get("turnos", 3),
        )

        # Forma Lunar: a passiva do tier 4 dobra o corpo que a forma empresta.
        dele = await self._personagem_na_run(run, user_id)
        dobra = 2 if ((dele or {}).get("efeitos") or {}).get("forma_lunar") else 1
        temporaria = acao.get("thp_por_tier", 0) * tier_atual * dobra
        if temporaria:
            motor.ganhar_thp(quem, temporaria)
            await db.definir_thp(self.bot.db, run["id"], quem.user_id, quem.thp)

        pedacos = [f"dano {dano}"]
        if acao.get("ataques", 1) > 1:
            pedacos.append(f"{acao['ataques']} golpes por rodada")
        if acao.get("ca"):
            pedacos.append(f"+{acao['ca']} de CA")
        if temporaria:
            pedacos.append(f"{temporaria} de vida temporaria")
        texto = (
            f"\U0001f43e **{habilidade.nome}**: {quem.nome} vira "
            f"**{acao['nome']}** — {', '.join(pedacos)}. "
            f"Por {acao.get('turnos', 3)} rodadas."
        )
        await self._anunciar_habilidade(run, texto)
        return texto

    async def _resolver_invocar(
        self, run: dict[str, Any], user_id: int, estado, habilidade, acao
    ) -> str:
        """Traz um aliado conjurado para a sala.

        Ele entra como combatente de dono, no fim da ordem da rodada, e vive
        até o grupo trocar de sala — a tabela é por passo, então ele some
        sozinho. Conjurar de novo troca o aliado: o pacto dá um por vez.
        """
        passo = self._passo(run)
        falso = await db.invocar(
            self.bot.db, run["id"], passo, user_id,
            acao["nome"], acao["ca"], acao["ataque"], acao["dano"],
            acao["hp"], acao.get("ameaca", 0),
        )
        rolagem = motor.rolar_iniciativa(
            motor.PERSONAGEM, falso, acao["nome"], acao.get("iniciativa", 0)
        )
        await db.acrescentar_iniciativa(
            self.bot.db, run["id"], passo, motor.PERSONAGEM, falso,
            acao["nome"], rolagem.d20, rolagem.modificador,
        )
        quem = estado.combatente(user_id)
        texto = (
            f"✨ **{habilidade.nome}**: {quem.nome if quem else 'Alguem'} "
            f"invoca **{acao['nome']}** — {acao['hp']} HP, CA {acao['ca']}, "
            f"ataque {fmt(acao['ataque'])} com {acao['dano']}. Ele luta "
            f"sozinho, no fim da ordem."
        )
        await self._anunciar_habilidade(run, texto)
        return texto

    async def _resolver_save(
        self, run: dict[str, Any], user_id: int, estado, habilidade, acao, alvos
    ) -> str:
        """A habilidade que força teste de resistência nas criaturas.

        É o caminho inverso do combate: até aqui só criatura cobrava save de
        personagem. A CD sai da classe de quem usou (8 + acerto), e `alvos`
        pode ser um escolhido ou "todos".
        """
        passo = self._passo(run)
        quem = await self._personagem_na_run(run, user_id)
        cd = cl.cd_de_habilidade((quem or {}).get("classe"), (quem or {}).get("nivel", 1))
        # O Metamagic do feiticeiro torce as magias DELE, para sempre: a CD
        # sobe, o dano soma um dado, a magia pega um alvo a mais, e a criatura
        # resiste com desvantagem. Vem das passivas dele, nao da acao.
        meta = (quem or {}).get("efeitos") or {}
        cd += meta.get("cd_magia", 0)
        desvantagem = bool(meta.get("save_com_desvantagem"))
        dado_extra = meta.get("dano_magia") or ""

        if acao.get("alvos") == "todos":
            mirados = list(estado.inimigos_vivos)
        else:
            quantos = 1 + meta.get("alvos_extra", 0)
            escolhidos = [
                i for i in estado.inimigos_vivos if i.indice in set(alvos or ())
            ]
            # Twinned Spell: a magia de um alvo pega o seguinte tambem. Sem
            # escolha explicita, pega o mais ferido, que e onde o dano fecha.
            if len(escolhidos) < quantos:
                sobram = sorted(
                    (i for i in estado.inimigos_vivos if i not in escolhidos),
                    key=lambda i: i.hp_atual,
                )
                escolhidos += sobram[: quantos - len(escolhidos)]
            mirados = escolhidos[:quantos]
        if not mirados:
            return "Nao ha inimigo de pe para a habilidade."

        linhas: list[str] = []
        caidos: list[str] = []
        for inimigo in mirados:
            # Guiding Bolt nao e resistivel: o dano entra, o save nao e rolado.
            if acao.get("sem_save"):
                passou, rolagem = False, ""
            else:
                save = motor.salvar_inimigo(
                    inimigo, acao["save"], cd, desvantagem=desvantagem
                )
                passou = save.passou
                marca = " (desvantagem)" if desvantagem else ""
                rolagem = (
                    f"🎲 {save.d20} {fmt(save.modificador)} = "
                    f"**{save.total}**{marca}"
                )

            sofridos: list[str] = []
            if acao.get("dano"):
                cheio = motor.rolar_dano(acao["dano"])
                # Empowered Spell: um dado a mais em toda magia dele.
                if dado_extra:
                    cheio += motor.rolar_dano(dado_extra)
                levou = cheio if not passou else (cheio // 2 if acao.get("metade") else 0)
                if levou:
                    inimigo.hp_atual = max(0, inimigo.hp_atual - levou)
                    sofridos.append(f"**{levou}** de dano")
            if not passou and acao.get("atordoa") and not inimigo.caido:
                inimigo.atordoado = True
                await db.aplicar_efeito(
                    self.bot.db, run["id"], passo, "inimigo", inimigo.indice,
                    "atordoado", {"por": habilidade.nome},
                    estado.rodada + acao["atordoa"], dono=user_id,
                )
                sofridos.append("**perde a vez**")
            if not passou and acao.get("vira_contra") and not inimigo.caido:
                sofridos.append(
                    await self._virar_contra_os_seus(run, estado, inimigo, habilidade)
                )
            if not passou and acao.get("dano_por_rodada") and not inimigo.caido:
                await db.aplicar_efeito(
                    self.bot.db, run["id"], passo, "inimigo", inimigo.indice,
                    f"{habilidade.id}:corrente",
                    {"dano_por_rodada": acao["dano_por_rodada"],
                     "save": acao["save"], "cd": cd},
                    estado.rodada + acao.get("turnos", 3), dono=user_id,
                )
                sofridos.append(f"**acorrentado** ({acao['dano_por_rodada']}/rodada)")
            if not passou and acao.get("penalidade_ataque") and not inimigo.caido:
                inimigo.penalidade_ataque = max(
                    inimigo.penalidade_ataque, acao["penalidade_ataque"]
                )
                await db.aplicar_efeito(
                    self.bot.db, run["id"], passo, "inimigo", inimigo.indice,
                    f"{habilidade.id}:atrapalhado",
                    {"penalidade_ataque": acao["penalidade_ataque"]},
                    estado.rodada + acao.get("turnos", 1), dono=user_id,
                )
                sofridos.append(f"**-{acao['penalidade_ataque']} de ataque**")
            if not passou and acao.get("vantagem_do_grupo"):
                await self._vantagem_do_grupo(
                    run, estado, inimigo, habilidade, acao.get("turnos", 1)
                )
                sofridos.append("**o grupo ataca ele com vantagem**")

            if inimigo.caido:
                caidos.append(inimigo.nome)
            resultado = ", ".join(p for p in sofridos if p) or "resistiu"
            meio = f" · {rolagem} vs CD {cd}" if rolagem else ""
            linhas.append(f"{inimigo.nome}{meio} → {resultado}")

        await db.definir_hp_inimigos(
            self.bot.db, run["id"], passo,
            {i.indice: i.hp_atual for i in estado.inimigos},
        )
        cabeca = f"✨ **{habilidade.nome}** (CD {cd})"
        texto = cabeca + "\n" + "\n".join(f"· {l}" for l in linhas)
        if caidos:
            texto += f"\n💀 caem: {', '.join(caidos)}"
        await self._anunciar_habilidade(run, texto)
        return texto

    async def _virar_contra_os_seus(
        self, run: dict[str, Any], estado, dominado, habilidade
    ) -> str:
        """Dominate Person: a criatura ataca outra criatura dela."""
        outros = [i for i in estado.inimigos_vivos if i is not dominado]
        if not outros:
            return "**mas nao tem em quem bater**"
        vitima = motor.sortear_um(outros)
        golpe = motor.atacar(
            dominado.nome, dominado.ataque, dominado.dano, vitima.nome, vitima.ca
        )
        if not golpe.acertou:
            return f"**vira contra {vitima.nome}** e erra"
        vitima.hp_atual = max(0, vitima.hp_atual - golpe.dano)
        await db.definir_hp_inimigos(
            self.bot.db, run["id"], self._passo(run),
            {i.indice: i.hp_atual for i in estado.inimigos},
        )
        return f"**acerta {vitima.nome}** com **{golpe.dano}** de dano"

    async def _vantagem_do_grupo(
        self, run: dict[str, Any], estado, inimigo, habilidade, turnos: int
    ) -> None:
        """Guiding Bolt: todo mundo do grupo ataca aquele inimigo com vantagem.

        A Marca do Caçador só beneficia o dono; esta é do grupo, então entra
        um efeito por pessoa, cada um dono do seu.
        """
        passo = self._passo(run)
        expira = estado.rodada + max(1, turnos)
        for c in estado.vivos:
            await db.aplicar_efeito(
                self.bot.db, run["id"], passo, "inimigo", inimigo.indice,
                f"{habilidade.id}:{c.user_id}", {"vantagem": True}, expira,
                dono=c.user_id,
            )

    async def _pedir_alvo(
        self, interaction: discord.Interaction, run, sala_id, habilidade, estado
    ):
        """Abre o menu de alvo se a habilidade precisa de um. False = nao precisa."""
        acao = habilidade.acao or {}
        # Quem so mexe em si mesmo (Rage, Reckless Attack, Avatar da Luz) ou no
        # grupo inteiro nao tem alvo a escolher — perguntar num combate de
        # quatro criaturas so atrapalha.
        # Quem nao mira ninguem: o buff de grupo, o que vale so em si, e a
        # invocacao, que traz o aliado e nao escolhe inimigo.
        if (
            acao.get("tipo") in ("grupo", "invocar")
            or (acao.get("tipo") == "forma" and acao.get("alvo") != "aliado")
            or acao.get("alvo") == "proprio"
        ):
            return False
        if acao.get("alvo") in ("aliado", "aliados") or acao.get("tipo") == "cura":
            if acao.get("tipo") == "cura" and acao.get("alvo") != "aliado":
                return False
            opcoes = [
                (str(p["user_id"]), p["nome"], f"{p['hp_atual']}/{p['hp_max']} HP")
                for p in await db.personagens_da_run(self.bot.db, run["id"])
            ]
        else:
            # Habilidade que pega todos nao tem alvo a escolher (Flame Strike,
            # Hypnotic Pattern): `alvos` vem como "todos", nao como numero.
            quantos = acao.get("alvos", 1)
            if quantos == "todos":
                return False
            vivos = estado.inimigos_vivos if estado else []
            if len(vivos) <= 1 and quantos <= 1:
                return False
            opcoes = [
                (str(i.indice), i.nome, f"{i.hp_atual}/{i.hp_max} HP · CA {i.ca}")
                for i in vivos
            ]
        if not opcoes:
            await self._dizer(interaction, "Nao ha alvo possivel agora.")
            return True
        await self._dizer(
            interaction,
            f"**{habilidade.nome}** — escolha o alvo:",
            view=SeletorAlvoHabilidade(
                self, run["id"], sala_id, habilidade.id, opcoes,
                acao.get("alvos", 1)
            ),
        )
        return True

    @staticmethod
    def _quanto_cura(alvo, acao: dict, bonus_pct: float = 0.0) -> int:
        """Cura o alvo e devolve quanto entrou de HP.

        Toda cura do jogo é fração do HP máximo — não há mais caminho por
        dado. O bônus de quem cura (o Curandeiro, o anel do santuário) é
        fração também, e soma ANTES de curar, numa conta só: em duas etapas o
        teto do HP engoliria a segunda quando a primeira já tivesse enchido a
        barra, e o bônus simplesmente desapareceria.
        """
        return motor.curar(alvo, acao["fracao"] + max(0.0, bonus_pct or 0.0))

    async def _limpar_atordoamento(self, run: dict[str, Any], alvo) -> None:
        """Tira o atordoamento de quem recebeu cura (Restauração, do clérigo)."""
        if not getattr(alvo, "atordoado", False):
            return
        alvo.atordoado = False
        await db.remover_efeito(
            self.bot.db, run["id"], self._passo(run), "personagem",
            alvo.user_id, "atordoado",
        )

    async def _resolver_cura(
        self, run: dict[str, Any], user_id: int, habilidade, acao, alvos, estado
    ) -> str:
        """Cura a si mesmo ou a um aliado, dentro ou fora do combate."""
        combatentes = estado.combatentes if estado else await self._combatentes(run)
        alvo_id = alvos[0] if alvos else user_id
        alvo = next((c for c in combatentes if c.user_id == alvo_id), None)
        if alvo is None:
            return "Alvo invalido."

        quem_curou = await self._personagem_na_run(run, user_id)
        dele = ((quem_curou or {}).get("efeitos") or {})
        curado = self._quanto_cura(alvo, acao, dele.get("bonus_cura_pct"))
        await db.definir_hp(self.bot.db, run["id"], alvo.user_id, alvo.hp_atual)
        # Restauracao, do clerigo: a cura tira o atordoamento de quem recebe.
        if curado and dele.get("cura_limpa_controle"):
            await self._limpar_atordoamento(run, alvo)
        temporario = 0
        quanto_thp = motor.rolar_dano(acao["thp_alvo"]) if acao.get("thp_alvo") else 0
        # O xama ganha THP ao usar o caminho espiritual, mesmo curando outro.
        if acao.get("thp_proprio"):
            proprio = next((c for c in combatentes if c.user_id == user_id), None)
            if proprio is not None:
                motor.ganhar_thp(proprio, motor.rolar_dano(acao["thp_proprio"]))
                await db.definir_thp(
                    self.bot.db, run["id"], proprio.user_id, proprio.thp
                )
        # Cantico Benevolente: a escolha do Xama soma THP em cima da cura.
        extra_cantico = dele.get("thp_na_cura", 0)
        if extra_cantico and alvo.user_id != user_id:
            quanto_thp += extra_cantico
        if quanto_thp:
            temporario = motor.ganhar_thp(alvo, quanto_thp)
            await db.definir_thp(self.bot.db, run["id"], alvo.user_id, alvo.thp)
        if curado:
            extra = f" e fica com **{temporario}** de THP" if temporario else ""
            texto = (
                f"\u2728 **{habilidade.nome}**: {alvo.nome} recupera **{curado}** de HP "
                f"({alvo.hp_atual}/{alvo.hp_max}){extra}."
            )
        else:
            texto = (
                f"\u2728 **{habilidade.nome}**: {alvo.nome} nao recupera nada "
                "(ja esta cheio, ou caido)."
            )
        await self._anunciar_habilidade(run, texto)
        return texto

    async def _resolver_grupo(self, run, estado, habilidade, acao, user_id: int) -> str:
        """Habilidade que cai no grupo inteiro: THP, cura e um buff curto.

        `melhoria` \u00e9 a vers\u00e3o car\u00edssima dos Guerreiros Anci\u00f5es: quem usa paga
        THP e, por esse pre\u00e7o, o grupo leva a forma melhor e os inimigos levam
        dano. Sem THP suficiente, sai a vers\u00e3o normal.
        """
        passo = self._passo(run)
        acao, pago = self._versao_da_habilidade(acao, estado, user_id)
        linhas: list[str] = []

        # A CURA primeiro, e o THP depois. Duas razoes: ela alcanca quem esta
        # caido (e `estado.vivos` nao), e quem ela levanta entra no THP junto
        # com o resto — a habilidade cai no grupo, e depois de cair o grupo
        # ja inclui quem voltou.
        texto_da_cura = None
        if acao.get("cura_fracao"):
            # O bonus de quem cura (Curandeiro, Especialista em cura, o anel
            # do santuario) vale aqui como na cura de um so.
            quem_curou = await self._personagem_na_run(run, user_id)
            bonus = ((quem_curou or {}).get("efeitos") or {}).get("bonus_cura_pct")
            como = {"fracao": acao["cura_fracao"]}
            curados = {}
            # `combatentes` e nao `vivos`: a cura em grupo levanta os caidos,
            # como a cura de alvo escolhido.
            for c in estado.combatentes:
                if self._quanto_cura(c, como, bonus):
                    curados[c.user_id] = c.hp_atual
            if curados:
                await db.definir_hp_varios(self.bot.db, run["id"], curados)
            total = acao["cura_fracao"] + max(0.0, bonus or 0.0)
            # `round`, e nao `int`: 0.35 + 0.10 da 0.44999999999999996 em
            # float, e truncar mostraria "44%" numa cura de 45%.
            texto_da_cura = f"**{round(total * 100)}%** do HP maximo de volta"

        quanto = motor.rolar_dano(acao["thp"]) if acao.get("thp") else 0
        novos: dict[int, int] = {}
        for c in estado.vivos:
            if quanto:
                motor.ganhar_thp(c, quanto)
            novos[c.user_id] = c.thp
        if quanto:
            linhas.append(f"**{quanto}** de vida temporaria para o grupo")
        if texto_da_cura:
            linhas.append(texto_da_cura)

        if pago:
            novos[pago[0]] = pago[1]
        if novos:
            await db.definir_thp_varios(self.bot.db, run["id"], novos)

        if acao.get("dano_em_todos"):
            caiu = []
            for inimigo in list(estado.inimigos_vivos):
                levou = motor.rolar_dano(acao["dano_em_todos"])
                inimigo.hp_atual = max(0, inimigo.hp_atual - levou)
                if inimigo.caido:
                    caiu.append(inimigo.nome)
            await db.definir_hp_inimigos(
                self.bot.db, run["id"], passo,
                {i.indice: i.hp_atual for i in estado.inimigos},
            )
            linhas.append(f"**{acao['dano_em_todos']}** em todos os inimigos")
            if caiu:
                linhas.append(f"caem: {', '.join(caiu)}")

        if acao.get("efeitos"):
            expira = estado.rodada + acao.get("turnos", 1)
            for c in estado.vivos:
                await db.aplicar_efeito(
                    self.bot.db, run["id"], passo, "personagem", c.user_id,
                    habilidade.id, acao["efeitos"], expira,
                )
            linhas.append("e um bonus nos proximos ataques")

        corpo = "; ".join(linhas) or "o grupo inteiro leva o bonus"
        marca = " \u2b50" if pago else ""
        texto = f"\u2728 **{habilidade.nome}**{marca}: {corpo}."
        await self._anunciar_habilidade(run, texto)
        return texto

    @staticmethod
    def _versao_da_habilidade(
        acao: dict, estado, user_id: int
    ) -> tuple[dict, Optional[tuple[int, int]]]:
        """Escolhe entre a a\u00e7\u00e3o normal e a `melhoria` que custa THP.

        Devolve (a\u00e7\u00e3o a usar, (user_id, THP que sobrou) se pagou). Quem paga \u00e9
        quem usou, e s\u00f3 se tiver o THP inteiro \u2014 a melhoria n\u00e3o sai pela
        metade. \u00c9 o que deixa o xam\u00e3 trocar 20 de vida tempor\u00e1ria pela forma
        grande dos Guerreiros Anci\u00f5es.
        """
        melhoria = acao.get("melhoria") or {}
        custo = melhoria.get("custo_thp", 0)
        dono = next((c for c in estado.vivos if c.user_id == user_id), None)
        if not custo or dono is None or dono.thp < custo:
            return {k: v for k, v in acao.items() if k != "melhoria"}, None
        dono.thp -= custo
        juntas = {k: v for k, v in acao.items() if k != "melhoria"}
        juntas.update(melhoria)
        juntas.pop("custo_thp", None)
        return juntas, (dono.user_id, dono.thp)

    async def _resolver_duracao(
        self, run, user_id: int, estado, habilidade, acao, alvos
    ) -> str:
        """Liga um efeito com prazo em quem usou, ou no inimigo escolhido."""
        passo = self._passo(run)
        expira = estado.rodada + acao.get("turnos", 1)
        if acao.get("alvo") == "inimigo":
            # O escolhido pode ter caido enquanto a acao esperava a vez.
            alvo = (estado.alvo_preferido(alvos[0]) if alvos else None) or estado.alvo_preferido()
            if alvo is None:
                return "Nao ha inimigo de pe para a habilidade."
            await db.aplicar_efeito(
                self.bot.db, run["id"], passo, "inimigo", alvo.indice,
                habilidade.id, acao["efeitos"], expira, dono=user_id,
            )
            alvo_nome = alvo.nome
        elif acao.get("alvo") == "aliados":
            # Fly: pega varios do grupo, nao so quem lancou. Sem escolha vale
            # quem esta de pe, do mais exposto para o menos — o que o mago
            # faria: tirar de alcance quem esta levando pancada.
            quantos = acao.get("alvos", 1)
            escolhidos = [c for c in estado.vivos if c.user_id in set(alvos or ())]
            # Dimension Door leva quem lancou junto, sempre em primeiro — e
            # antes de completar, para nao gastar vaga com outro no lugar dele.
            if acao.get("inclui_quem_usou"):
                proprio = estado.combatente(user_id)
                if proprio is not None and proprio not in escolhidos:
                    escolhidos = [proprio] + escolhidos
            # Escolha parcial COMPLETA, nao trunca: o menu aceita submeter um
            # alvo so, e quem pede dois nao pode entregar um em silencio. Sem
            # escolha nenhuma vale do mais exposto para o menos — o que o mago
            # faria: tirar de alcance quem esta levando pancada.
            if len(escolhidos) < quantos:
                sobram = sorted(
                    (c for c in estado.vivos if c not in escolhidos),
                    key=lambda c: -c.ameaca_total,
                )
                escolhidos += sobram[: quantos - len(escolhidos)]
            if not escolhidos:
                return "Nao ha ninguem de pe para a habilidade."
            for quem_recebe in escolhidos[:quantos]:
                await db.aplicar_efeito(
                    self.bot.db, run["id"], passo, "personagem",
                    quem_recebe.user_id, habilidade.id, acao["efeitos"], expira,
                )
            alvo_nome = ", ".join(c.nome for c in escolhidos[:quantos])
        else:
            await db.aplicar_efeito(
                self.bot.db, run["id"], passo, "personagem", user_id,
                habilidade.id, acao["efeitos"], expira,
            )
            alvo_nome = None

        quem = estado.combatente(user_id)
        turnos = acao.get("turnos", 1)
        alvo_texto = f" em **{alvo_nome}**" if alvo_nome else ""
        await self._anunciar_habilidade(
            run, f"✨ {quem.nome if quem else 'Alguem'} usa **{habilidade.nome}**{alvo_texto}."
        )
        return (
            f"✨ **{habilidade.nome}**{alvo_texto} — vale por "
            f"{turnos} turno(s), ate a rodada {expira - 1}."
        )

    async def _pilha_de_sequencia(
        self, run: dict[str, Any], user_id: int, passo: int
    ) -> int:
        """Martial Arts: quantos acertos seguidos o personagem ja emendou."""
        for ligado in await db.efeitos_ativos(self.bot.db, run["id"], passo, 0):
            if (
                ligado["alvo_tipo"] == "personagem"
                and ligado["alvo_id"] == user_id
                and ligado["efeito"] == "martial_arts"
            ):
                return ligado["valor"].get("pilha", 0)
        return 0

    async def _guardar_sequencia(
        self, run: dict[str, Any], user_id: int, passo: int, pilha: int
    ) -> None:
        # Prazo alto de proposito: a sequencia so morre junto com o combate.
        await db.aplicar_efeito(
            self.bot.db, run["id"], passo, "personagem", user_id,
            "martial_arts", {"pilha": pilha}, 9999,
        )

    async def _totem_do_golpe(
        self, run: dict[str, Any], personagem: dict[str, Any], combatente, golpes
    ) -> None:
        """Convocacao totemica: 18+ no d20 rende THP a quem tem a passiva."""
        totem = ((personagem.get("efeitos") or {}).get("totem")) or {}
        if not totem.get("thp"):
            return
        if not any(g.d20 >= totem.get("gatilho", 18) for g, _alvo in golpes):
            return
        motor.ganhar_thp(combatente, totem["thp"])
        await db.definir_thp(self.bot.db, run["id"], combatente.user_id, combatente.thp)

    async def _resolver_golpes(
        self, run, user_id: int, estado, habilidade, acao, alvos
    ) -> str:
        """Os golpes de uma ativa, no lugar do ataque do turno."""
        passo = self._passo(run)
        atacante = estado.combatente(user_id)
        escolhidos = [i for i in (estado.inimigo(v) for v in alvos) if i and not i.caido]
        if not escolhidos:
            vivo = estado.alvo_preferido()
            escolhidos = [vivo] if vivo else []
        if not escolhidos or atacante is None:
            return "Nao ha inimigo de pe para atacar."

        golpes = []
        indice = await db.proximo_indice_de_ataque(
            self.bot.db, run["id"], passo, estado.rodada, user_id
        )
        # `quantidade` conta GOLPES e `acoes` conta ACOES. A diferenca importa
        # para quem tem Multiattack: uma acao dele sao dois golpes, entao o
        # Action Surge com "quantidade: 1" trocava os dois golpes do turno por
        # um — usar era pior que nao usar. Com `acoes` a conta sai certa
        # sozinha, e continua certa quando o Multiattack mudar.
        por_alvo = acao.get("quantidade")
        if por_alvo is None:
            por_alvo = max(1, acao.get("acoes", 1)) * max(1, atacante.ataques)
        # Alvo unico: se ele cair no meio, os golpes que faltam vao para o
        # proximo de pe, como o ataque comum do turno ja faz. Com varios alvos
        # escolhidos (a Rajada do Cacador) cada um leva o seu, e trocar seria
        # bater duas vezes no mesmo.
        reapontar = len(escolhidos) == 1
        for alvo in escolhidos:
            for _ in range(por_alvo):
                if alvo.caido and reapontar:
                    proximo = estado.alvo_preferido()
                    if proximo is None:
                        break
                    alvo = proximo
                if alvo.caido:
                    break
                golpe = motor.atacar_inimigo(
                    atacante,
                    alvo,
                    None,
                    dano_bonus=acao.get("dano_bonus"),
                    rotulo_bonus=habilidade.nome,
                    garantido=acao.get("garantido", False),
                    critico_forcado=acao.get("critico", False),
                )
                golpes.append((golpe, alvo))
                await db.registrar_ataque(
                    self.bot.db, run["id"], passo, estado.rodada, user_id,
                    golpe.d20, golpe.bonus, golpe.ca_alvo, golpe.dano, alvo.indice,
                    indice, "habilidade",
                )
                indice += 1

        # Bonus de uma vez so (o Brutal Strike): entra no primeiro golpe que
        # acerta, e nao em cada um. `dano_bonus` e por golpe e dobraria num
        # turno de dois ataques; este e o d10 que a habilidade promete, um.
        extra = 0
        if acao.get("bonus_uma_vez"):
            for golpe, inimigo in golpes:
                if not golpe.acertou:
                    continue
                extra = motor.rolar_dano(acao["bonus_uma_vez"])
                golpe.dano += extra
                inimigo.hp_atual = max(0, inimigo.hp_atual - extra)
                break

        await db.definir_hp_inimigos(
            self.bot.db, run["id"], passo,
            {inimigo.indice: inimigo.hp_atual for _g, inimigo in golpes},
        )
        ganho = 0
        if acao.get("thp_proprio"):
            ganho = motor.ganhar_thp(atacante, motor.rolar_dano(acao["thp_proprio"]))
        if acao.get("thp_igual_ao_bonus") and extra:
            # Brutal Strike: a vida temporaria e EXATAMENTE o d10 que saiu no
            # golpe, e nao uma fracao do dano total — "o mesmo em THP".
            ganho = motor.ganhar_thp(atacante, extra)
        if ganho:
            await db.definir_thp(self.bot.db, run["id"], atacante.user_id, atacante.thp)
        personagem = await self._personagem_na_run(run, user_id)
        if personagem:
            await self._totem_do_golpe(run, personagem, atacante, golpes)

        if acao.get("atordoa"):
            certeiro = next(((g, i) for g, i in golpes if g.acertou), None)
            if certeiro:
                # Quem ja agiu nesta rodada perde a vez da proxima; quem ainda
                # vai agir, a desta.
                ordem = await db.iniciativa(self.bot.db, run["id"], passo)
                vez = (await db.estado_combate(self.bot.db, run["id"], passo))["vez"]
                ja_agiu = any(
                    a["tipo"] == motor.INIMIGO and a["alvo_id"] == certeiro[1].indice
                    for a in ordem[:vez]
                )
                await db.aplicar_efeito(
                    self.bot.db, run["id"], passo, "inimigo", certeiro[1].indice,
                    "atordoado", {},
                    estado.rodada + acao["atordoa"] + (1 if ja_agiu else 0),
                )
                await self._anunciar_habilidade(
                    run,
                    f"\u2728 **{habilidade.nome}**: {certeiro[1].nome} fica "
                    "atordoado e perde a proxima vez.",
                )
            else:
                # So gasta o recurso quando acerta.
                await db.devolver_uso(
                    self.bot.db, run["id"], user_id,
                    habilidade.chave_de_uso,
                    self._chave_de_recarga(habilidade, run, passo),
                )

        self._registrar(run, estado.rodada, [E.linha_golpe(g) for g, _i in golpes])
        resumo = E.resumo_do_golpe([(g, i.nome) for g, i in golpes])
        if ganho:
            resumo += f"\nVida temporaria: **{atacante.thp}**."
        await self._anunciar_habilidade(
            run, f"\u2728 {atacante.nome} usa **{habilidade.nome}**."
        )
        return f"\u2728 **{habilidade.nome}**\n{resumo}"

    async def _bencao_do_patrono(
        self, run: dict[str, Any], personagem: dict[str, Any], combatente, golpes
    ) -> None:
        """Dark One's Blessing: derrubar um inimigo rende vida temporária.

        O gatilho é a queda, não o acerto — por isso roda depois de o dano já
        ter entrado no HP, olhando quem ficou no chão nesta sequência.
        """
        por_tier = ((personagem.get("efeitos") or {}).get("thp_ao_derrubar")) or 0
        if not por_tier or combatente is None:
            return
        derrubados = sum(1 for _golpe, inimigo in golpes if inimigo.caido)
        if not derrubados:
            return
        quanto = por_tier * max(1, self._tier_da_run(run))
        motor.ganhar_thp(combatente, quanto)
        await db.definir_thp(
            self.bot.db, run["id"], combatente.user_id, combatente.thp
        )
        self._registrar(
            run, 0,
            [f"🩸 **{combatente.nome}** drena o que caiu: **+{quanto}** de THP"],
        )

    async def _gravar_hp_do_combatente(self, run: dict[str, Any], quem) -> None:
        """Grava o HP de quem levou dano, no lugar certo.

        O aliado conjurado não tem linha em `run_participantes` — ele vive na
        tabela de invocações, dentro do passo. Sem este desvio, o inimigo que
        batesse nele gravaria num lugar que não existe.
        """
        if quem.e_invocacao:
            await db.definir_hp_invocacao(
                self.bot.db, run["id"], self._passo(run), quem.user_id, quem.hp_atual
            )
            return
        await db.definir_hp(self.bot.db, run["id"], quem.user_id, quem.hp_atual)
        await db.definir_thp(self.bot.db, run["id"], quem.user_id, quem.thp)

    async def _vez_da_invocacao(self, run: dict[str, Any], estado, aliado) -> None:
        """A vez do aliado conjurado: ele bate no inimigo mais machucado.

        Sem tática: o bot não joga por ninguém. Mirar o mais ferido é a única
        escolha que não precisa de opinião — fecha combate mais rápido e não
        desperdiça o golpe num alvo que já ia cair de qualquer forma.
        """
        alvo = min(
            estado.inimigos_vivos, key=lambda i: i.hp_atual, default=None
        )
        if alvo is None:
            return
        golpe = motor.atacar(
            aliado.nome, aliado.bonus_ataque, aliado.dano_arma, alvo.nome, alvo.ca
        )
        if golpe.acertou:
            alvo.hp_atual = max(0, alvo.hp_atual - golpe.dano)
            await db.definir_hp_inimigos(
                self.bot.db, run["id"], self._passo(run),
                {i.indice: i.hp_atual for i in estado.inimigos},
            )
        self._registrar(
            run, estado.rodada,
            [f"👹 **{aliado.nome}** · {E.texto_do_contra_ataque(golpe, alvo.nome)}"],
        )

    async def _inspiracao_de(self, run: dict[str, Any], onde: str):
        """Quem no grupo socorre aquele tipo de falha, e com que dado.

        Devolve (personagem, habilidade, dado) do primeiro que serve, ou
        (None, None, ""). `onde` é "ataque", "save" ou "pericia": a escolha do
        tier 2 do bardo decide qual rolagem a Inspiração dele alcança.
        """
        for p in await db.personagens_da_run(self.bot.db, run["id"]):
            habilidade, acao = self._reacao_de(p, "falhou_teste")
            if habilidade is None or acao.get("inspira") != onde:
                continue
            dado = self._dado_de_inspiracao(p, acao)
            if dado:
                return p, habilidade, dado
        return None, None, ""

    async def _inspirar_o_golpe(
        self, run: dict[str, Any], estado, atacante, golpes
    ) -> None:
        """Inspiração no ataque: o golpe que errou por pouco passa a acertar.

        Roda depois de a sequência resolver, e refaz só o que mudou — o d20 do
        golpe sobe, e se agora alcança a CA o dano é rolado e descontado. Quem
        chama grava o HP dos inimigos em seguida.
        """
        passo = self._passo(run)
        for golpe, inimigo in golpes:
            if golpe.acertou or atacante is None:
                continue
            # O 1 natural erra por maior que seja o total: nao ha o que
            # socorrer, e gastar o dado nele seria perder a carga por nada.
            if golpe.falha_critica:
                continue
            p, habilidade, dado = await self._inspiracao_de(run, "ataque")
            if p is None:
                return
            falta = golpe.ca_alvo - golpe.total
            if not motor.pode_virar(falta, dado):
                continue
            if not await db.gastar_uso(
                self.bot.db, run["id"], p["user_id"], habilidade.chave_de_uso,
                self._chave_de_recarga(habilidade, run, passo), habilidade.vezes,
            ):
                return
            ajuda = motor.rolar_dano(dado)
            golpe.bonus += ajuda
            # O dano sai do motor, pela mesma conta do golpe normal: a arma, o
            # dano_ferido e todos os dados a mais. Recalcular aqui fazia o
            # golpe socorrido dar um quarto do golpe que acertou sozinho.
            if not motor.refazer_o_golpe(atacante, inimigo, golpe):
                self._registrar(
                    run, estado.rodada,
                    [f"🎵 **{habilidade.nome}**: {p['nome']} sopra **+{ajuda}** "
                     f"no golpe de {golpe.atacante} — e nao basta"],
                )
                continue
            self._registrar(
                run, estado.rodada,
                [f"🎵 **{habilidade.nome}**: {p['nome']} sopra **+{ajuda}** no "
                 f"golpe de {golpe.atacante} — acerta por **{golpe.dano}**"],
            )

    async def _inspirar_o_save(self, run: dict[str, Any], estado, investidas) -> None:
        """Inspiração no save: quem falhou por pouco passa a resistir.

        Desfaz o que a falha custou, como o Uncanny Dodge já faz com o dano:
        devolve o HP, limpa o atordoamento e a condição. Mexer antes seria
        melhor, mas `impor_save` é do motor puro e não conhece o bardo.
        """
        passo = self._passo(run)
        for investida in investidas:
            if investida.save is None or investida.save.passou:
                continue
            p, habilidade, dado = await self._inspiracao_de(run, "save")
            if p is None:
                return
            falta = investida.save.cd - investida.save.total
            if not motor.pode_virar(falta, dado):
                continue
            if not await db.gastar_uso(
                self.bot.db, run["id"], p["user_id"], habilidade.chave_de_uso,
                self._chave_de_recarga(habilidade, run, passo), habilidade.vezes,
            ):
                return
            ajuda = motor.rolar_dano(dado)
            if ajuda < falta:
                self._registrar(
                    run, estado.rodada,
                    [f"🎵 **{habilidade.nome}**: {p['nome']} sopra **+{ajuda}** "
                     f"no save de {investida.alvo.nome} — e nao basta"],
                )
                continue
            alvo = investida.alvo
            # Desfazer tem de devolver cada parte no lugar de onde saiu: o que
            # a vida temporaria segurou volta para o THP, e so o resto para o
            # HP. Somar tudo no HP gastava o THP de graca e, com a vida cheia,
            # o min() engolia a devolucao — o save resistido nao devolvia nada.
            devolvido = investida.dano
            alvo.thp += investida.absorvido
            alvo.hp_atual = min(
                alvo.hp_max, alvo.hp_atual + (devolvido - investida.absorvido)
            )
            investida.dano = 0
            investida.absorvido = 0
            if investida.atordoou:
                investida.atordoou = False
                alvo.atordoado = False
            investida.debuffs = []
            self._registrar(
                run, estado.rodada,
                [f"🎵 **{habilidade.nome}**: {p['nome']} sopra **+{ajuda}** no "
                 f"save de {alvo.nome} — resiste, e devolve **{devolvido}** de dano"],
            )

    async def _socorrer_o_teste(self, run: dict[str, Any], resultado) -> None:
        """Flash of Genius: quem tem a reação salva o teste falhado de alguém.

        Dispara sozinho, como as outras reações do bot, e só quando o bônus
        vira a falha em sucesso — não queima o uso num teste que já passou nem
        num que falhou longe demais. Serve qualquer um do grupo, inclusive
        quem tem a habilidade.
        """
        passo = self._passo(run)
        for p in await db.personagens_da_run(self.bot.db, run["id"]):
            habilidade, acao = self._reacao_de(p, "falhou_teste")
            if habilidade is None:
                continue
            # A Dark One's Own Luck do bruxo é o patrono torcendo o destino
            # DELE: não socorre o teste de mais ninguém.
            if acao.get("so_em_si") and p["user_id"] != resultado.user_id:
                continue
            # A Inspiracao Bardica socorre com DADO, nao com numero: entra se
            # o teto do dado cobriria a falha, e so depois rola. As outras
            # cinco reacoes de socorro somam um numero fixo e nunca falham.
            dado = self._dado_de_inspiracao(p, acao)
            if dado:
                if (
                    acao.get("inspira") != "pericia"
                    or not motor.pode_virar(resultado.cd - resultado.total, dado)
                ):
                    continue
                bonus = motor.rolar_dano(dado)
            else:
                # O tier 5 sobe o bonus de 5 para 10, por passiva.
                bonus = (
                    ((p.get("efeitos") or {}).get("flash_bonus"))
                    or acao.get("bonus", 0)
                )
                if not motor.vale_ajudar(resultado, bonus):
                    continue
            if not await db.gastar_uso(
                self.bot.db, run["id"], p["user_id"], habilidade.chave_de_uso,
                self._chave_de_recarga(habilidade, run, passo), habilidade.vezes,
            ):
                continue
            resultado.ajuda = bonus
            resultado.quem_ajudou = p["nome"]
            # Com dado, o socorro pode nao bastar: o teto cobria, a rolagem
            # nao. O uso sai de qualquer forma, como na mesa.
            fecho = "o teste passa" if resultado.passou else "e nao basta"
            await self._anunciar_habilidade(
                run,
                f"✨ **{habilidade.nome}**: {p['nome']} socorre "
                f"{resultado.personagem} com **+{bonus}** — {fecho}.",
            )
            return

    @staticmethod
    def _dado_de_inspiracao(personagem: dict[str, Any], acao: dict) -> str:
        """O dado da Inspiração daquele bardo, ou "" se a reação é de número.

        O dado base é o da habilidade; a passiva do tier 4 o substitui por um
        maior. Quem não tem Inspiração (o artífice, o paladino) devolve vazio
        e segue pelo caminho do bônus fixo.
        """
        if not acao.get("inspira"):
            return ""
        melhor = ((personagem.get("efeitos") or {}).get("dado_inspiracao")) or ""
        return melhor or acao.get("dado", "")

    @staticmethod
    def _reacao_de(personagem: dict[str, Any], quando: str):
        """A reacao daquele gatilho, se o personagem tiver alguma."""
        for _tier, habilidade in personagem.get("habilidades") or []:
            acao = habilidade.acao or {}
            if acao.get("tipo") == "reacao" and acao.get("quando") == quando:
                return habilidade, acao
        return None, None

    async def _reacoes_do_revide(self, run: dict[str, Any], estado, revides) -> None:
        """As reacoes que o golpe do inimigo dispara, na ordem em que importam.

        A esquiva vem antes da queda: cortar o golpe pela metade pode evitar
        que a segunda reacao precise acontecer.
        """
        await self._esquivas(run, revides)
        await self._reacoes_ao_cair(run, revides)

    async def _esquivas(self, run: dict[str, Any], revides) -> None:
        """Uncanny Dodge: corta o golpe pesado pela metade, devolvendo o HP."""
        passo = self._passo(run)
        for golpe, atingido in revides:
            if not golpe.acertou or golpe.dano <= 0:
                continue
            personagem = await self._personagem_na_run(run, atingido.user_id)
            if not personagem:
                continue
            habilidade, acao = self._reacao_de(personagem, "sofreu_golpe")
            if habilidade is None:
                continue
            # O golpe ja entrou no HP: a conta e feita sobre como estava antes.
            antes = motor.Combatente(
                atingido.user_id, atingido.nome, atingido.ca, 0, "1d1",
                atingido.hp_max, min(atingido.hp_max, atingido.hp_atual + golpe.dano),
                thp=atingido.thp,
            )
            if not motor.vale_esquivar(antes, golpe.dano, acao.get("limiar", 1 / 3)):
                continue
            if not await db.gastar_uso(
                self.bot.db, run["id"], atingido.user_id, habilidade.chave_de_uso,
                self._chave_de_recarga(habilidade, run, passo), habilidade.vezes,
            ):
                continue
            devolvido = golpe.dano - int(golpe.dano * acao.get("reduz", 0.5))
            golpe.dano -= devolvido
            atingido.hp_atual = min(atingido.hp_max, atingido.hp_atual + devolvido)
            await db.definir_hp(
                self.bot.db, run["id"], atingido.user_id, atingido.hp_atual
            )
            await self._anunciar_habilidade(
                run,
                f"\u2728 **{habilidade.nome}**: {atingido.nome} desvia e segura "
                f"{devolvido} de dano.",
            )

    async def _reacoes_ao_cair(self, run: dict[str, Any], revides) -> None:
        """Relentless e afins: quem caiu nesta rodada pode nao cair de verdade."""
        passo = self._passo(run)
        for _golpe, atingido in revides:
            if not atingido.caido:
                continue
            personagem = await self._personagem_na_run(run, atingido.user_id)
            if not personagem:
                continue
            habilidade, acao = self._reacao_de(personagem, "caiu")
            if habilidade is None:
                continue
            if not await db.gastar_uso(
                self.bot.db, run["id"], atingido.user_id, habilidade.chave_de_uso,
                self._chave_de_recarga(habilidade, run, passo), habilidade.vezes,
            ):
                continue
            atingido.hp_atual = acao.get("hp", 1)
            motor.ganhar_thp(atingido, motor.rolar_dano(acao["thp"]))
            await db.definir_hp(
                self.bot.db, run["id"], atingido.user_id, atingido.hp_atual
            )
            await db.definir_thp(self.bot.db, run["id"], atingido.user_id, atingido.thp)
            await self._anunciar_habilidade(
                run,
                f"\u2728 **{habilidade.nome}**: {atingido.nome} se recusa a cair "
                f"— fica com {atingido.hp_atual} HP e {atingido.thp} de THP.",
            )

    async def _guardar_debuffs(
        self, run: dict[str, Any], investidas: list
    ) -> list[str]:
        """Grava as condições que as criaturas aplicaram, e diz o que cada um pegou.

        São as mesmas condições da armadilha, na mesma tabela: o Envenenado que
        a aranha deixa sai da sala com o grupo e decai por combate como
        qualquer outro. Quem caiu no combate não leva nada — já está fora.
        """
        linhas: list[str] = []
        for investida in investidas:
            if not investida.debuffs or investida.alvo.caido:
                continue
            for cid in investida.debuffs:
                stacks = await db.aplicar_condicao(
                    self.bot.db, run["id"], investida.alvo.user_id, cid
                )
                linhas.append(
                    f"**{investida.alvo.nome}** fica com "
                    f"{condicoes.rotulo(cid, stacks)} — "
                    f"{condicoes.descricao(cid, stacks=stacks)}"
                )
        return linhas

    async def _guardar_atordoamentos(
        self, run: dict[str, Any], estado, investidas: list, ja_agiram: set[int]
    ) -> None:
        """Grava quem ficou atordoado: perde a proxima vez que teria.

        Quem ainda nao agiu nesta rodada perde a vez desta; quem ja passou,
        a da rodada seguinte — por isso o "+ 1" para esses.
        """
        passo = self._passo(run)
        for investida in investidas:
            if not investida.atordoou:
                continue
            ja_agiu = investida.alvo.user_id in ja_agiram
            # "desde" e a rodada antes da primeira que ele perde: o save de
            # quem se livra sozinho so vem depois de perder uma vez.
            valor = {
                "por": investida.habilidade,
                "desde": estado.rodada if ja_agiu else estado.rodada - 1,
            }
            prazo = estado.rodada + max(1, investida.atordoa_por) + (1 if ja_agiu else 0)
            if investida.repete_save:
                # "refaz o save no final do turno": o prazo e so um teto, quem
                # decide e o proprio alvo, rodada a rodada, em _virar_efeitos.
                valor["save"] = investida.save.atributo
                valor["cd"] = investida.save.cd
                prazo = estado.rodada + PRAZO_ATE_PASSAR
            await db.aplicar_efeito(
                self.bot.db,
                run["id"],
                passo,
                "personagem",
                investida.alvo.user_id,
                "atordoado",
                valor,
                prazo,
            )

    async def _virar_efeitos(self, run: dict[str, Any], estado) -> None:
        """No fim da rodada: cura de quem tem cura por turno, e prazos vencidos."""
        passo = self._passo(run)
        curas = {}
        # `combatentes` e nao `vivos`: a cura por turno levanta caido como as
        # outras. Grupo INTEIRO no chao nao chega aqui — o laco do `_avancar`
        # ve `estado.encerrado` antes de virar a rodada e encerra o combate —,
        # entao a regeneracao socorre quem caiu, mas nao desfaz uma derrota.
        for c in estado.combatentes:
            if c.cura_por_turno:
                ganho = motor.curar(c, c.cura_por_turno)
                if ganho:
                    curas[c.user_id] = c.hp_atual
        if curas:
            await db.definir_hp_varios(self.bot.db, run["id"], curas)
        await self._sangrar_acorrentados(run, estado)
        await self._refazer_saves(run, estado)
        await db.limpar_efeitos_vencidos(self.bot.db, run["id"], passo, estado.rodada)

    async def _sangrar_acorrentados(self, run: dict[str, Any], estado) -> None:
        """Grilhões Planares: a criatura presa sangra todo fim de rodada.

        Na mesa ela andaria para fugir do efeito; aqui não há posição, então o
        escape é o save: a cada rodada ela refaz o teste e, passando, a
        corrente arrebenta. Sem isso a magia seria dano garantido e viraria a
        mais forte de alvo único do jogo.
        """
        passo = self._passo(run)
        ligados = await db.efeitos_ativos(self.bot.db, run["id"], passo, estado.rodada)
        linhas: list[str] = []
        mexeu = False
        for ligado in ligados:
            valor = ligado.get("valor") or {}
            if ligado["alvo_tipo"] != "inimigo" or not valor.get("dano_por_rodada"):
                continue
            alvo = estado.inimigo(ligado["alvo_id"])
            if alvo is None or alvo.caido:
                continue
            livre = motor.salvar_inimigo(alvo, valor.get("save", "DES"), valor["cd"])
            if livre.passou:
                await db.remover_efeito(
                    self.bot.db, run["id"], passo, "inimigo",
                    ligado["alvo_id"], ligado["efeito"],
                )
                linhas.append(f"⛓️ **{alvo.nome}** arrebenta a corrente")
                continue
            levou = motor.rolar_dano(valor["dano_por_rodada"])
            alvo.hp_atual = max(0, alvo.hp_atual - levou)
            mexeu = True
            caiu = " e cai" if alvo.caido else ""
            linhas.append(f"⛓️ **{alvo.nome}** sangra **{levou}** na corrente{caiu}")
        if mexeu:
            await db.definir_hp_inimigos(
                self.bot.db, run["id"], passo,
                {i.indice: i.hp_atual for i in estado.inimigos},
            )
        if linhas:
            self._registrar(run, estado.rodada, linhas)

    async def _refazer_saves(self, run: dict[str, Any], estado) -> None:
        """Quem esta preso por um efeito de 'save no fim do turno' rola de novo.

        So depois de perder uma vez: o efeito posto no fim da rodada N custa a
        rodada N+1, e a chance de escapar vem no fim dela.
        """
        passo = self._passo(run)
        ligados = await db.efeitos_ativos(self.bot.db, run["id"], passo, estado.rodada - 1)
        for ligado in ligados:
            valor = ligado.get("valor") or {}
            if ligado["alvo_tipo"] != "personagem" or not valor.get("save"):
                continue
            if estado.rodada - 1 <= valor.get("desde", 0):
                continue  # ainda nao perdeu a vez que o efeito custa
            alvo = estado.combatente(ligado["alvo_id"])
            if alvo is None or alvo.caido:
                continue
            resultado = motor.salvar_combatente(alvo, valor["save"], valor["cd"])
            if not resultado.passou:
                continue
            await db.remover_efeito(
                self.bot.db, run["id"], passo, "personagem", ligado["alvo_id"],
                ligado["efeito"],
            )
            alvo.atordoado = False
            await self._anunciar_habilidade(
                run,
                f"🧿 **{alvo.nome}** se livra de "
                f"**{valor.get('por', 'efeito')}** "
                f"({valor['save']} {resultado.total} vs CD {valor['cd']}).",
            )

    async def _anunciar_habilidade(self, run: dict[str, Any], texto: str) -> None:
        """O grupo ve que alguem usou uma habilidade, sem detalhe de rolagem.

        Guarda o que publicou: a mesma frase ia sair DE NOVO em privado
        para quem clicou, e o jogador via a habilidade dele duas vezes na
        tela. Quem compara e `_avancar`.
        """
        canal = await self._canal(run)
        if canal:
            try:
                mensagem = await canal.send(texto)
            except discord.HTTPException:
                return
            self._publicado[run["id"]] = texto
            self._usadas.setdefault(run["id"], []).append(mensagem)

    async def _apos_combate_vencido(
        self, run: dict[str, Any], sala: Sala, estado=None
    ) -> None:
        incursao = self._incursao_da_run(run)
        if sala.pontos_organizacao:
            await self._creditar(
                run,
                sala.pontos_organizacao,
                f"Sala superada: {sala.nome}",
                f"sala:{self._passo(run)}:{sala.id}",
            )
        await self._marcar_sala_superada(run, sala)

        canal = await self._canal(run)
        if sala.id == incursao.objetivo.id:
            await self._encerrar_run(run, "sucesso")
            await self._creditar(
                run, config.PONTOS_PARTICIPACAO, "Participação na incursão", "participacao"
            )
            await self._creditar(
                run, incursao.pontos_conclusao, "Objetivo cumprido", "conclusao"
            )
            # Aqui, e em nenhum outro lugar: a incursao so paga quando e
            # concluida.
            await self._pagar_a_run(run)
            if canal:
                # Desfecho num embed so: vitoria, como o grupo saiu, MEs e pontos.
                lancamentos, total = await self._balanco(run)
                await canal.send(
                    embed=E.run_concluida(
                        incursao, await self._membros(run), estado, lancamentos, total,
                        await self._caminho(run),
                        await db.ouro_da_run(self.bot.db, run["id"]),
                    )
                )
                if incursao.lore_final:
                    await canal.send(embed=E.lore_fecho(incursao))
            return

        if canal and estado is not None:
            await canal.send(embed=E.combate_vencido(sala, estado))

        # Antes de decair: quem a criatura levou ao teto sai agora. Na outra
        # ordem o decaimento tiraria o stack que estourou, e o teto de uma
        # condicao que decai nunca pegaria ninguem.
        await self._expulsar_estourados(run)

        # Um combate a menos no prazo dos debuffs e dos buffs. As maldicoes e a
        # Exaustao tem prazo NULL e nao sao tocadas: duram a incursao.
        await self._vencer_prazo_das_condicoes(run)

        passo = run["linha_atual"]
        if passo < incursao.passos:
            await self._abrir_votacao(await db.buscar_run(self.bot.db, run["id"]), passo + 1)
        else:
            await self._chegar_ao_objetivo(await db.buscar_run(self.bot.db, run["id"]))

    async def _vencer_prazo_das_condicoes(self, run: dict[str, Any]) -> None:
        """Fecha um combate: toda condição perde 1 stack, menos a Exaustão."""
        acabaram = await db.decair_condicoes(self.bot.db, run["id"])
        if not acabaram:
            return
        canal = await self._canal(run)
        if not canal:
            return
        apelidos = await self._apelidos(run)
        linhas = [
            f"{condicoes.rotulo(cid)} passa em {apelidos.get(user_id, f'<@{user_id}>')}"
            for user_id, cid in acabaram
        ]
        await canal.send("⏳ " + "; ".join(linhas) + ".")

    async def rolar(self, interaction: discord.Interaction, run_id: int, sala_id: str) -> None:
        run = await db.buscar_run(self.bot.db, run_id)
        if not run or run["status"] != "em_sala" or run["sala_atual"] != sala_id:
            await interaction.response.send_message("Esta sala já foi resolvida.", ephemeral=True)
            return
        # A sala pode estar FECHADA com a run ainda nela: a emboscada do
        # Mimico reusa o id e o status da sala do Tesouro, e o combate corre
        # dentro dela. Um botao antigo na tela de alguem ainda mandava a
        # rolagem, e ela reabria o fecho da sala — a votacao do passo
        # seguinte aparecia no meio do combate.
        if await db.sala_fechada(self.bot.db, run_id, self._passo(run)):
            await interaction.response.send_message(
                "Esta sala já foi resolvida.", ephemeral=True
            )
            return
        if not await db.esta_na_run(self.bot.db, run_id, interaction.user.id):
            await interaction.response.send_message("Você não faz parte desta run.", ephemeral=True)
            return

        incursao = self._incursao_da_run(run)
        sala = await self._sala_corrente(run)
        if sala is None or sala.e_combate:
            # O baú acordou entre o clique e a chegada: não há mais teste aqui.
            await interaction.response.send_message(
                "Esta sala virou combate — não há teste para rolar.", ephemeral=True
            )
            return
        if not await db.esta_de_pe(self.bot.db, run_id, interaction.user.id):
            await interaction.response.send_message(
                "Você está caído — quem está no chão não encara a sala. Espere o Descanso.",
                ephemeral=True,
            )
            return
        personagem = await db.personagem_da_run(self.bot.db, run_id, interaction.user.id)
        if not personagem:
            await interaction.response.send_message(
                "Não achei o personagem com que você entrou nesta run.", ephemeral=True
            )
            return

        personagem["user_id"] = interaction.user.id
        resultado = motor.testar(
            personagem, sala,
            saldo=await self._saldo(run, interaction.user.id),
            tier=self._tier_da_run(run),
        )
        # Flash of Genius: alguem do grupo socorre a falha antes de ela virar
        # consequencia. Entra no `modificador` gravado, para a margem e o
        # progresso da sala contarem com a ajuda.
        await self._socorrer_o_teste(run, resultado)
        novo = await db.registrar_teste(
            self.bot.db,
            run_id,
            self._passo(run),
            sala_id,
            interaction.user.id,
            resultado.personagem,
            resultado.pericia,
            resultado.d20,
            resultado.modificador + resultado.ajuda,
            resultado.cd,
        )
        if not novo:
            await interaction.response.send_message(
                "Você já rolou nesta sala — cada um rola uma vez.", ephemeral=True
            )
            return

        # O resumo privado da rolagem — e do dano que ela custou — sai do
        # canal quando a SALA fecha, nao quando a proxima abre: entre uma
        # coisa e outra ha uma votacao inteira.
        self._guardar_efemera(run_id, interaction)
        veredito = (
            f"passou por **{resultado.margem}** de margem"
            if resultado.passou
            else f"falhou por **{resultado.cd - resultado.total}**"
        )
        socorro = (
            f" (+{resultado.ajuda} de {resultado.quem_ajudou})"
            if resultado.ajuda
            else ""
        )
        await interaction.response.send_message(
            f"🎲 **{resultado.d20}** {resultado.modificador:+d}{socorro} = "
            f"**{resultado.total}** em {resultado.pericia} (CD {resultado.cd}) "
            f"— {veredito}.",
            ephemeral=True,
        )

        registros = await db.testes_da_sala(self.bot.db, run_id, self._passo(run))
        total = len(await db.participantes_de_pe(self.bot.db, run_id))
        resolucao = _resolucao(sala, registros, total)

        if resolucao.encerrada:
            await self._concluir_sala(run, sala, resolucao)
        else:
            embed, _ = E.sala_aberta(
                sala, run["linha_atual"], len(registros), total, incursao.passos,
                tier=self._tier_da_run(run),
            )
            if interaction.message is not None:
                try:
                    await interaction.message.edit(embed=embed, view=ViewSala(self, run_id, sala_id))
                except discord.HTTPException:
                    pass

    async def _concluir_sala(
        self, run: dict[str, Any], sala: Sala, resolucao: Optional[ResolucaoSala]
    ) -> None:
        """Fecha a sala e segue a run. Roda uma vez por sala, nunca duas.

        Duas rolagens que resolvam a sala juntas chegavam as duas aqui, e as
        duas seguiam para o passo seguinte — que, no fim do caminho, e o
        combate do objetivo: o painel saia duplicado.
        """
        if not await db.tomar_o_fecho_da_sala(
            self.bot.db, run["id"], self._passo(run), sala.id
        ):
            return
        canal = await self._canal(run)
        if not canal:
            return

        await self._limpar_botoes(await db.buscar_run(self.bot.db, run["id"]))
        # As rolagens privadas do teste saem junto com a sala. Antes elas
        # so sumiam quando a PROXIMA abria, e entre uma coisa e outra ha
        # uma votacao inteira — o jogador ficava com o resultado de uma
        # sala que ja acabou pendurado na tela.
        await self._limpar_efemeras(run["id"])

        desfecho = None
        if resolucao is not None:
            desfecho = await self._consequencias_da_sala(run, sala, resolucao)
            await canal.send(embed=E.resultado_sala(resolucao, desfecho))
            if resolucao.superada and sala.pontos_organizacao:
                await self._creditar(
                    run, sala.pontos_organizacao, f"Sala superada: {sala.nome}", f"sala:{self._passo(run)}:{sala.id}"
                )
            if resolucao.superada:
                await self._marcar_sala_superada(run, sala)
            await self._expulsar_estourados(run)

        if sala.tipo == "Descanso":
            # Pelo TIPO, e nao por `resolucao is None`: sala sem rolagem e o
            # que o descanso tem de particular hoje, nao uma regra geral.
            await canal.send(
                embed=E.descanso_fechado(
                    sala, await self._linhas_do_descanso(run)
                )
            )

        # Mímico acordado no baú: a sala vira combate em vez de devolver à votação.
        if desfecho is not None and desfecho.mimicos:
            await self._soltar_mimicos(run, sala)
            return

        incursao = self._incursao_da_run(run)
        passo = run["linha_atual"]
        if incursao and passo < incursao.passos:
            await self._abrir_votacao(run, passo + 1)
        else:
            await self._chegar_ao_objetivo(run)

    # ------------------------------------------------------------ descanso

    # O descanso tira uma coisa: um stack de debuff, ou um ponto de Exaustao.
    # A Exaustao tem botao proprio porque e a unica que nao decai com o
    # combate — o descanso e a unica saida dela.
    TIPOS_DE_LIMPEZA = {
        "debuff": (condicoes.DEBUFF,),
        "exaustao": (condicoes.EXAUSTAO,),
    }

    @staticmethod
    def _limpezas_de(carregadas: dict[str, int]) -> set[str]:
        """Quais das três limpezas servem para quem carrega isto."""
        return {
            chave
            for chave, tipos in Incursoes.TIPOS_DE_LIMPEZA.items()
            if consequencias.a_limpar(carregadas, tipos)
        }

    async def _limpezas_disponiveis(self, run: dict[str, Any]) -> set[str]:
        """A união do que o grupo carrega — é o que decide quais botões existem.

        Os botões são os mesmos para todos porque a mensagem é uma só; cada
        clique age sobre as condições de quem clicou.
        """
        carregadas = await db.condicoes_da_run(self.bot.db, run["id"])
        disponiveis: set[str] = set()
        for condicoes_do_jogador in carregadas.values():
            disponiveis |= self._limpezas_de(condicoes_do_jogador)
        return disponiveis

    async def _descanso_pendente(self, run: dict[str, Any]) -> list[int]:
        """Quem ainda não escolheu no descanso deste passo.

        Quem não carrega nada não precisa clicar: entra marcado, para um grupo
        limpo não ter de dar cinco cliques à toa.
        """
        passo = self._passo(run)
        carregadas = await db.condicoes_da_run(self.bot.db, run["id"])
        pendentes = []
        for user_id in await db.participantes(self.bot.db, run["id"]):
            if not self._limpezas_de(carregadas.get(user_id, {})):
                await db.marcar_descanso(self.bot.db, run["id"], passo, user_id)
                continue
            pendentes.append(user_id)
        ja = await db.quem_descansou(self.bot.db, run["id"], passo)
        return [u for u in pendentes if u not in ja]

    async def limpar_no_descanso(
        self, interaction: discord.Interaction, run_id: int, sala_id: str, chave: str
    ) -> None:
        """Cada personagem limpa UMA condição sua. A sala fecha quando todos escolhem."""
        run = await db.buscar_run(self.bot.db, run_id)
        if not run or run["status"] != "em_sala" or run["sala_atual"] != sala_id:
            await interaction.response.send_message(
                "Este descanso já terminou.", ephemeral=True
            )
            return
        user_id = interaction.user.id
        if not await db.esta_na_run(self.bot.db, run_id, user_id):
            await interaction.response.send_message(
                "Você não faz parte desta run.", ephemeral=True
            )
            return
        passo = self._passo(run)
        if user_id in await db.quem_descansou(self.bot.db, run_id, passo):
            await interaction.response.send_message(
                "Você já escolheu neste descanso — é uma por personagem.",
                ephemeral=True,
            )
            return

        minhas = await db.condicoes_de(self.bot.db, run_id, user_id)
        tipos = self.TIPOS_DE_LIMPEZA.get(chave)
        if tipos:
            candidatas = consequencias.a_limpar(minhas, tipos)
            if not candidatas:
                # Nao gasta a escolha: o botao existe por causa de outra pessoa.
                await interaction.response.send_message(
                    "Você não carrega nada dessa categoria — escolha outra.",
                    ephemeral=True,
                )
                return
            cid = candidatas[0]
            sobrou = await db.reduzir_condicao(self.bot.db, run_id, user_id, cid)
            resto = f" (ainda ×{sobrou})" if sobrou else ""
            publico = (
                f"o descanso tira {condicoes.rotulo(cid)} de "
                f"**{await self._nome_na_run(run, user_id)}**{resto}"
            )
            privado = f"O descanso tira {condicoes.rotulo(cid)} de você{resto}."
        else:
            publico = f"**{await self._nome_na_run(run, user_id)}** descansa sem limpar nada"
            privado = "Você segue sem limpar nada."

        await db.marcar_descanso(self.bot.db, run_id, passo, user_id)
        await interaction.response.send_message(privado, ephemeral=True)
        self._guardar_efemera(run_id, interaction)
        canal = await self._canal(run)
        if canal:
            await canal.send(f"🏕️ {publico}.")

        if await self._descanso_pendente(run):
            await self._atualizar_descanso(run, sala_id)
            return
        incursao = self._incursao_da_run(run)
        await self._concluir_sala(run, self._sala(incursao, sala_id), None)

    async def _atualizar_descanso(self, run: dict[str, Any], sala_id: str) -> None:
        """Reescreve o cartão do descanso com quem ainda falta escolher."""
        incursao = self._incursao_da_run(run)
        sala = self._sala(incursao, sala_id)
        atual = await db.buscar_run(self.bot.db, run["id"]) or run
        canal = await self._canal(atual)
        if not (canal and sala and atual.get("mensagem_id")):
            return
        disponiveis = await self._limpezas_disponiveis(atual)
        faltam = await self._descanso_pendente(atual)
        try:
            mensagem = await canal.fetch_message(atual["mensagem_id"])
            await mensagem.edit(
                embed=E.descanso(
                    sala,
                    await self._linhas_do_descanso(atual),
                    disponiveis,
                    faltam=len(faltam),
                ),
                view=ViewDescanso(self, run["id"], sala_id, disponiveis),
            )
        except discord.HTTPException:
            pass

    async def _linhas_do_descanso(self, run: dict[str, Any]) -> list[str]:
        """Uma linha por personagem do grupo, com o HP lido do banco agora.

        Do banco a cada desenho, e nao de uma lista guardada na abertura:
        limpar Exaustao ou Debilitacao devolve HP MAXIMO, entao o "50/60"
        da abertura vira "50/70" no meio do descanso. Lista guardada
        mostraria o numero velho.

        E o grupo INTEIRO, nao so quem mudou: quem le o cartao quer saber
        como o grupo vai entrar na proxima sala, e "nao apareci" nao
        responde isso.
        """
        feito = self._recuperacao.get(run["id"], {})
        linhas = []
        for c in await self._combatentes(run):
            r = feito.get(c.user_id)
            if r is not None and r.voltou:
                nota = f" — de pé outra vez (+{r.ganho})"
            elif r is not None and r.ganho:
                nota = f" — o descanso deu **{r.ganho}**"
            elif c.hp_atual >= c.hp_max:
                nota = " — inteiro"
            else:
                # Cheio de Debilitacao, ou a fracao arredondou para nada.
                nota = " — o descanso não rendeu nada"
            linhas.append(f"• **{c.nome}** {c.hp_atual}/{c.hp_max}{nota}")
        return linhas

    async def _nome_na_run(self, run: dict[str, Any], user_id: int) -> str:
        personagem = await db.personagem_da_run(self.bot.db, run["id"], user_id)
        return (personagem or {}).get("nome") or f"<@{user_id}>"

    # ------------------------------------------- o que a sala deixa no grupo

    async def _consequencias_da_sala(
        self, run: dict[str, Any], sala: Sala, resolucao: ResolucaoSala
    ) -> consequencias.Desfecho:
        """Aplica o que a sala faz com o grupo e devolve o texto do embed.

        O que cada tipo faz está em `src/consequencias.py`; aqui só persiste.

        **Sala vencida não castiga ninguém.** Armadilha e Evento batem em
        quem falhou, mas só quando a sala foi PERDIDA: vencer protege o
        grupo inteiro, inclusive quem rolou mal. Antes a Armadilha cobrava
        de quem falhou mesmo com o grupo desarmando a sala, e o jogador que
        tirou 3 saía machucado de uma sala que o grupo venceu.
        """
        desfecho = consequencias.Desfecho()
        if sala.tipo == "Armadilha" and resolucao.superada:
            desfecho.linhas.append(
                "O grupo desarma a armadilha — ninguém se machuca nela."
            )
        elif sala.tipo == "Armadilha" and resolucao.quem_falhou:
            await self._castigo_de_armadilha(run, sala, resolucao, desfecho)
        elif sala.tipo == "Evento":
            if resolucao.superada:
                await self._premio_de_evento(run, desfecho)
            elif resolucao.quem_falhou:
                await self._castigo_de_evento(run, resolucao, desfecho)
        elif sala.tipo == "Tesouro" and not resolucao.superada:
            if consequencias.acordou_mimico():
                desfecho.mimicos = True
                desfecho.linhas.append(
                    "O baú não era um baú. **Mímicos** se descolam da parede."
                )
            else:
                desfecho.linhas.append("O grupo sai sem nada — mas sai inteiro.")
        return desfecho

    async def _castigo_de_armadilha(
        self,
        run: dict[str, Any],
        sala: Sala,
        resolucao: ResolucaoSala,
        desfecho: consequencias.Desfecho,
    ) -> None:
        """Quem falhou leva o Dano (-20% do HP) e um debuff de Armadilha."""
        combatentes = {c.user_id: c for c in await self._combatentes(run)}
        hps: dict[int, int] = {}
        for falhou in resolucao.quem_falhou:
            combatente = combatentes.get(falhou.user_id)
            if combatente is None:
                continue
            dano = consequencias.dano_da_armadilha(combatente.hp_max)
            combatente.hp_atual = max(0, combatente.hp_atual - dano)
            hps[falhou.user_id] = combatente.hp_atual
            debuff = consequencias.debuff_da_armadilha()
            stacks = await db.aplicar_condicao(
                self.bot.db, run["id"], falhou.user_id, debuff
            )
            desfecho.linhas.append(
                f"**{falhou.personagem}** leva **{dano}** de dano e fica com "
                f"{condicoes.rotulo(debuff, stacks)} — "
                f"{condicoes.descricao(debuff, stacks=stacks)}"
            )
        if hps:
            await db.definir_hp_varios(self.bot.db, run["id"], hps)

    async def _premio_de_evento(
        self, run: dict[str, Any], desfecho: consequencias.Desfecho
    ) -> None:
        """O Evento vencido dá uma coisa só: um buff, a Cura ou a Graça."""
        carregadas = await db.condicoes_da_run(self.bot.db, run["id"])
        combatentes = await self._combatentes(run)
        machucados = [c for c in combatentes if c.hp_atual < c.hp_max]
        sujos = consequencias.sortear_para_limpar(carregadas, (condicoes.DEBUFF,))
        premio = consequencias.premio_do_evento(
            tem_debuff=bool(sujos), tem_machucado=bool(machucados)
        )

        # Cura: +20% do HP máximo no personagem com menos vida do grupo.
        if premio == consequencias.CURA and machucados:
            alvo = min(machucados, key=lambda c: c.hp_atual)
            bruta = consequencias.cura_do_evento(alvo.hp_max)
            ganho = min(alvo.hp_max - alvo.hp_atual, motor.cura_liquida(alvo, bruta))
            alvo.hp_atual += ganho
            await db.definir_hp(self.bot.db, run["id"], alvo.user_id, alvo.hp_atual)
            desfecho.linhas.append(
                f"✨ **Cura**: **{alvo.nome}** recupera **{ganho}** de HP "
                f"({alvo.hp_atual}/{alvo.hp_max})."
            )
            return

        # Graça: tira um debuff de alguém do grupo, sorteado entre todos.
        if premio == consequencias.GRACA:
            escolhidos = consequencias.sortear_para_limpar(
                carregadas, (condicoes.DEBUFF,)
            )
            if escolhidos:
                partes = []
                for user_id, cid in escolhidos:
                    await db.reduzir_condicao(self.bot.db, run["id"], user_id, cid)
                    nome = next(
                        (c.nome for c in combatentes if c.user_id == user_id), "alguém"
                    )
                    partes.append(f"{condicoes.rotulo(cid)} de **{nome}**")
                desfecho.linhas.append(
                    f"✨ **{consequencias.NOME_DA_GRACA}** tira "
                    + ", ".join(partes)
                    + "."
                )
                return

        # Sobrou buff, que é o piso do Evento: vale para o grupo inteiro.
        if premio not in condicoes.BUFFS:
            premio = condicoes.BUFFS[0]
        for c in combatentes:
            await db.aplicar_condicao(self.bot.db, run["id"], c.user_id, premio)
        desfecho.linhas.append(
            f"✨ O grupo inteiro ganha {condicoes.rotulo(premio)} — "
            f"{condicoes.descricao(premio)}"
        )

    async def _castigo_de_evento(
        self,
        run: dict[str, Any],
        resolucao: ResolucaoSala,
        desfecho: consequencias.Desfecho,
    ) -> None:
        """Quem falhou pega um debuff de Evento ou um ponto de Exaustão."""
        for falhou in resolucao.quem_falhou:
            castigo = consequencias.castigo_do_evento()
            stacks = await db.aplicar_condicao(
                self.bot.db, run["id"], falhou.user_id, castigo
            )
            desfecho.linhas.append(
                f"**{falhou.personagem}** fica com "
                f"{condicoes.rotulo(castigo, stacks)} — "
                f"{condicoes.descricao(castigo, stacks=stacks)}"
            )

    async def _expulsar_estourados(self, run: dict[str, Any]) -> None:
        """Quem bateu no teto de uma condição sai da incursão.

        O teto é por condição, como na planilha: Deterioração em 10 (que é
        -100% do HP máximo) e Exaustão em 5. As outras não tiram ninguém.
        Esvaziando o grupo, a run fracassa.
        """
        tier_atual = self._tier_da_run(run)
        carregadas = await db.condicoes_da_run(self.bot.db, run["id"])
        canal = await self._canal(run)
        saiu = False
        for user_id, condicoes_do_jogador in sorted(carregadas.items()):
            saldo = condicoes.penalidades(condicoes_do_jogador, tier_atual)
            if not saldo.fora:
                continue
            personagem = await db.personagem_da_run(self.bot.db, run["id"], user_id)
            nome = (personagem or {}).get("nome", f"<@{user_id}>")
            if not await db.remover_participante(self.bot.db, run["id"], user_id):
                continue
            saiu = True
            motivos = ", ".join(condicoes.POR_ID[c].nome for c in saldo.estourou)
            if canal:
                await canal.send(
                    f"<@{user_id}> — **{nome}** não consegue seguir: {motivos} chegou "
                    f"ao limite. O personagem sai da incursão."
                )
        if saiu and not await db.participantes(self.bot.db, run["id"]):
            # Sem ninguem de pe a run termina aqui. Nao ha combate, entao nao ha
            # estado para o embed de derrota: fecha com uma linha e os pontos de
            # participacao, que o grupo levou ate onde deu.
            await self._encerrar_run(run, "fracasso")
            await self._creditar(
                run, config.PONTOS_PARTICIPACAO, "Participação na incursão", "participacao"
            )
            if canal:
                await canal.send(
                    "A incursão termina aqui: não sobrou ninguém em condições de "
                    "seguir."
                )

    async def _soltar_mimicos(self, run: dict[str, Any], sala: Sala) -> None:
        """A falha no Tesouro acordou o baú: a sala vira um combate.

        Os números dos Mímicos ficam gravados em `run_inimigos` por
        `_abrir_combate`, então o combate se remonta sozinho depois de um
        restart — a emboscada não precisa existir no banco de salas.
        """
        emboscada = emboscada_de(sala)
        if not emboscada.monstros:
            # Sem Mímico no bestiário não há emboscada: segue o fluxo normal.
            log.warning("Mímico não encontrado no bestiário; emboscada cancelada")
            incursao = self._incursao_da_run(run)
            passo = run["linha_atual"]
            if incursao and passo < incursao.passos:
                await self._abrir_votacao(run, passo + 1)
            else:
                await self._chegar_ao_objetivo(run)
            return
        await self._abrir_combate(run, emboscada)

    async def _chegar_ao_objetivo(self, run: dict[str, Any]) -> None:
        incursao = self._incursao_da_run(run)
        canal = await self._canal(run)
        if not (incursao and canal):
            return

        # A ultima sala do caminho sai do canal quando o objetivo abre.
        await self._apagar_passo_anterior(run)
        await db.atualizar_run(
            self.bot.db,
            run["id"],
            status="objetivo",
            sala_atual=incursao.objetivo.id,
            votacao_expira_em=None,
        )
        await self._abrir_combate(
            await db.buscar_run(self.bot.db, run["id"]), incursao.objetivo
        )

    # ---------------------------------------------------------- comandos

    @grupo.command(name="votar", description="Vota por comando, caso os botões falhem")
    @app_commands.describe(opcao="1, 2 ou 3 — a opção mostrada na votação")
    async def votar_comando(
        self, interaction: discord.Interaction, opcao: app_commands.Range[int, 1, 3]
    ) -> None:
        run = await self._run_do_contexto(interaction)
        if not run:
            return
        if run["status"] != "escolhendo":
            await interaction.response.send_message("Não há votação aberta agora.", ephemeral=True)
            return
        opcoes = await self._opcoes(run, run["linha_atual"])
        if opcao > len(opcoes):
            await interaction.response.send_message(
                f"Esta votação tem {len(opcoes)} opção(ões).", ephemeral=True
            )
            return
        await self.votar(interaction, run["id"], run["linha_atual"], opcoes[opcao - 1].id)

    @grupo.command(name="status", description="Estado atual da run neste canal")
    async def status(self, interaction: discord.Interaction) -> None:
        run = await self._run_do_contexto(interaction, exigir_participante=False)
        if not run:
            return
        incursao = self._incursao_da_run(run)
        sala = await self._sala_corrente(run)
        registros = (
            await db.testes_da_sala(self.bot.db, run["id"], self._passo(run)) if sala else []
        )
        await interaction.response.send_message(
            embed=E.status(
                run,
                incursao,
                await self._membros(run),
                sala,
                len(registros),
                await db.condicoes_da_run(self.bot.db, run["id"]),
                await self._apelidos(run),
            )
        )

    @grupo.command(name="desistir", description="Propõe abandonar a incursão (precisa de maioria)")
    async def desistir(self, interaction: discord.Interaction) -> None:
        run = await self._run_do_contexto(interaction)
        if not run:
            return
        # A desistencia reusa a tabela de votos com linha = -1.
        await db.registrar_voto(self.bot.db, run["id"], -1, interaction.user.id, "desistir")
        votos = await db.votos_da_linha(self.bot.db, run["id"], -1)
        total = len(await db.participantes(self.bot.db, run["id"]))
        necessarios = maioria_de(total)

        if len(votos) >= necessarios:
            await self._encerrar_run(run, "desistiu")
            await interaction.response.send_message(
                f"A run #{run['id']} foi abandonada por decisão do grupo "
                f"({len(votos)}/{total}). Ninguém recebe MEs."
            )
            return

        await interaction.response.send_message(
            f"{interaction.user.display_name} quer desistir "
            f"({len(votos)}/{necessarios} necessários). Quem concordar, use `/incursao desistir`."
        )

    @grupo.command(name="recarregar", description="(admin) Relê as incursões do disco")
    @app_commands.default_permissions(manage_guild=True)
    async def recarregar(self, interaction: discord.Interaction) -> None:
        try:
            self.recarregar_incursoes()
        except Exception as exc:  # JSON invalido nao pode derrubar o bot
            await interaction.response.send_message(f"Falhou: {exc}", ephemeral=True)
            return
        await interaction.response.send_message(
            f"{len(self.incursoes)} incursão(ões) e {len(self.bancos)} banco(s) de salas: "
            f"{', '.join(self.incursoes) or 'nenhuma'}.",
            ephemeral=True,
        )

    config_grupo = app_commands.Group(
        name="config", description="Ajustes do bot (admin)", default_permissions=discord.Permissions(manage_guild=True)
    )

    @config_grupo.command(
        name="intervalo",
        description="Semanas entre incursões do mesmo jogador (a semana vira na segunda)",
    )
    async def config_intervalo(
        self, interaction: discord.Interaction, semanas: app_commands.Range[int, 0, 52]
    ) -> None:
        await db.definir_intervalo(self.bot.db, interaction.guild_id, semanas)
        if semanas == 0:
            texto = "Intervalo desligado: cada jogador pode entrar quantas vezes quiser."
        else:
            texto = (
                f"Intervalo ajustado para **{semanas} semana(s)**, contadas da "
                "segunda-feira: quem entrar no sábado joga de novo na segunda."
            )
        await interaction.response.send_message(texto, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Incursoes(bot))
