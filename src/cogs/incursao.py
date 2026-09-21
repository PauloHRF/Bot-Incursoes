"""Runs de incursão: recrutamento, votação por linha, salas e testes de perícia.

A run é assíncrona: o estado vive no banco, não na memória, para que o grupo
possa avançar ao longo de dias e o bot possa reiniciar sem perder nada.
"""
from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from .. import config, database as db, embeds as E, motor
from ..incursoes import Incursao, Monstro, Sala, carregar_todas
from ..motor import Combatente, EstadoCombate, ResolucaoSala, ResultadoTeste

log = logging.getLogger("incursoes.run")

LINHAS = 3


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _prazo() -> str:
    return (_agora() + timedelta(minutes=config.MINUTOS_VOTACAO)).strftime("%Y-%m-%d %H:%M:%S")


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


class ViewCombate(discord.ui.View):
    def __init__(self, cog: "Incursoes", run_id: int, sala_id: str):
        super().__init__(timeout=None)
        self.cog = cog
        self.run_id = run_id
        self.sala_id = sala_id
        botao = discord.ui.Button(
            label="Atacar",
            emoji="⚔️",
            style=discord.ButtonStyle.danger,
            custom_id=f"inc:atacar:{run_id}:{sala_id}",
        )
        botao.callback = self._atacar
        self.add_item(botao)

    async def _atacar(self, interaction: discord.Interaction) -> None:
        await self.cog.atacar(interaction, self.run_id, self.sala_id)


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
                    description=f"Nivel {p['nivel']} · CA {p['ca']} · HP {p['hp_max']}",
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


class Incursoes(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.incursoes: dict[str, Incursao] = {}

    async def cog_load(self) -> None:
        self._carregar_tolerante()
        await self.restaurar_views()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        # O loop so pode comecar com o cliente ja conectado, e on_ready repete
        # a cada reconexao.
        if not self.verificar_prazos.is_running():
            self.verificar_prazos.start()

    async def cog_unload(self) -> None:
        self.verificar_prazos.cancel()

    def recarregar_incursoes(self) -> None:
        pasta = config.RAIZ / "data" / "incursoes"
        self.incursoes = carregar_todas(pasta) if pasta.is_dir() else {}
        log.info("%d incursão(ões) carregada(s): %s", len(self.incursoes), ", ".join(self.incursoes))

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
            view = self._view_do_estado(run)
            if view and run["mensagem_id"]:
                self.bot.add_view(view, message_id=run["mensagem_id"])

    def _view_do_estado(self, run: dict[str, Any]) -> Optional[discord.ui.View]:
        incursao = self.incursoes.get(run["incursao_id"])
        if not incursao:
            return None
        if run["status"] == "recrutando":
            return ViewRecrutamento(self, run["id"])
        if run["status"] == "escolhendo":
            return ViewVotacao(self, run["id"], run["linha_atual"], incursao.opcoes(run["linha_atual"]))
        if run["status"] in ("em_sala", "objetivo") and run["sala_atual"]:
            sala = incursao.sala(run["sala_atual"])
            if sala and sala.tem_teste:
                return ViewSala(self, run["id"], sala.id)
            if sala and sala.e_combate:
                return ViewCombate(self, run["id"], sala.id)
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

    async def _membros(self, run: dict[str, Any]) -> list[discord.abc.User]:
        ids = await db.participantes(self.bot.db, run["id"])
        guilda = self.bot.get_guild(run["guild_id"])
        membros = []
        for user_id in ids:
            membro = guilda.get_member(user_id) if guilda else None
            if membro is None and guilda is not None:
                # Sem o intent de membros o cache vem vazio; buscar traz o apelido do servidor.
                try:
                    membro = await guilda.fetch_member(user_id)
                except discord.HTTPException:
                    membro = None
            membros.append(membro or await self.bot.fetch_user(user_id))
        return membros

    async def _apelidos(self, run: dict[str, Any]) -> dict[int, str]:
        return {m.id: m.display_name for m in await self._membros(run)}

    def _incursao_da_run(self, run: dict[str, Any]) -> Optional[Incursao]:
        return self.incursoes.get(run["incursao_id"])

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

    async def _sugerir_incursoes(
        self, interaction: discord.Interaction, atual: str
    ) -> list[app_commands.Choice[str]]:
        termo = atual.lower()
        return [
            app_commands.Choice(name=f"{inc.nome} ({inc.organizacao})", value=inc.id)
            for inc in self.incursoes.values()
            if termo in inc.id.lower() or termo in inc.nome.lower()
        ][:25]

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
            e.add_field(
                name=f"{inc.nome}  ·  `{inc.id}`",
                value=f"{inc.organizacao} — {inc.recompensa_mes} MEs",
                inline=False,
            )
        await interaction.response.send_message(embed=e, ephemeral=True)

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
        elif len(meus) == 1:
            escolhido = meus[0]
        else:
            await interaction.response.send_message(
                "Voce tem mais de um personagem: "
                f"{', '.join(p['nome'] for p in meus)}. "
                "Diga qual no campo `personagem`.",
                ephemeral=True,
            )
            return

        run_id = await db.criar_run(
            self.bot.db, interaction.guild_id, interaction.channel_id, incursao.id, interaction.user.id
        )
        await db.adicionar_participante(
            self.bot.db, run_id, interaction.user.id, escolhido["id"]
        )

        run = await db.buscar_run(self.bot.db, run_id)
        view = ViewRecrutamento(self, run_id)
        await interaction.response.send_message(
            embed=E.recrutamento(incursao, await self._membros(run), interaction.user), view=view
        )
        mensagem = await interaction.original_response()
        await db.atualizar_run(self.bot.db, run_id, mensagem_id=mensagem.id)

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
        intervalo = await db.intervalo_dias(self.bot.db, guild_id)
        dias = await db.dias_desde_ultima_incursao(self.bot.db, guild_id, user_id)
        if dias is not None and dias < intervalo:
            faltam = intervalo - dias
            return (
                f"Você participou de uma incursão há {dias:.1f} dia(s). "
                f"O intervalo é de {intervalo} dias — faltam {faltam:.1f}."
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

        await db.adicionar_participante(self.bot.db, run_id, interaction.user.id, personagem_id)
        await interaction.response.send_message(
            f"Voce entrou com **{personagem['nome']}** (nivel {personagem['nivel']}).",
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
            if len(personagens) == 1:
                await self.efetivar_entrada(interaction, run_id, personagens[0]["id"])
            else:
                await interaction.response.send_message(
                    "Escolha com qual personagem entrar:",
                    view=SeletorPersonagemEntrada(self, run_id, personagens),
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
        await db.marcar_ultima_incursao(self.bot.db, run["guild_id"], participantes)
        await db.inicializar_hp(self.bot.db, run["id"])
        await db.atualizar_run(self.bot.db, run["id"], status="escolhendo", linha_atual=1)

        canal = await self._canal(run)
        if canal:
            incursao = self._incursao_da_run(run)
            if run["mensagem_id"]:
                try:
                    mensagem = await canal.fetch_message(run["mensagem_id"])
                    await mensagem.edit(view=None)
                except discord.HTTPException:
                    pass
            await canal.send(
                f"**{incursao.nome}** começa agora com {len(participantes)} "
                f"aventureiro(s). Que a Organização registre o que for trazido de volta."
            )
        await self._abrir_votacao(await db.buscar_run(self.bot.db, run["id"]), 1)

    # ------------------------------------------------------------ votação

    async def _abrir_votacao(self, run: dict[str, Any], linha: int) -> None:
        incursao = self._incursao_da_run(run)
        canal = await self._canal(run)
        if not (incursao and canal):
            return
        opcoes = incursao.opcoes(linha)
        total = len(await db.participantes(self.bot.db, run["id"]))
        votos = await db.votos_da_linha(self.bot.db, run["id"], linha)
        view = ViewVotacao(self, run["id"], linha, opcoes)
        mensagem = await canal.send(
            embed=E.votacao(incursao, linha, opcoes, votos, max(0, total - len(votos))), view=view
        )
        await db.atualizar_run(
            self.bot.db,
            run["id"],
            status="escolhendo",
            linha_atual=linha,
            sala_atual=None,
            mensagem_id=mensagem.id,
            votacao_expira_em=_prazo(),
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

        await db.registrar_voto(self.bot.db, run_id, linha, interaction.user.id, sala_id)
        incursao = self._incursao_da_run(run)
        sala = incursao.sala(sala_id)
        await interaction.response.send_message(f"Voto registrado: **{sala.nome}**.", ephemeral=True)

        votos = await db.votos_da_linha(self.bot.db, run_id, linha)
        total = len(await db.participantes(self.bot.db, run_id))
        opcoes = incursao.opcoes(linha)

        if interaction.message is not None:
            try:
                await interaction.message.edit(
                    embed=E.votacao(incursao, linha, opcoes, votos, max(0, total - len(votos))),
                    view=ViewVotacao(self, run_id, linha, opcoes),
                )
            except discord.HTTPException:
                pass

        if len(votos) >= total:
            await self._fechar_votacao(run, linha, por_prazo=False)

    async def _fechar_votacao(self, run: dict[str, Any], linha: int, por_prazo: bool) -> None:
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
            # Ninguem votou: acao conservadora, o grupo mantem a posicao atual.
            await db.atualizar_run(self.bot.db, run["id"], votacao_expira_em=_prazo())
            await canal.send(
                "Ninguém votou dentro do prazo. A votação continua aberta — "
                "o grupo não avança até alguém escolher."
            )
            return

        maximo = max(contagem.values())
        empatadas = [sala_id for sala_id, n in contagem.items() if n == maximo]

        if len(empatadas) > 1 and not por_prazo:
            await canal.send(
                "Empate na votação. Ninguém avança enquanto o grupo não desempatar — "
                "clique em outra opção para trocar seu voto."
            )
            return

        if len(empatadas) > 1:
            escolhida_id = random.SystemRandom().choice(empatadas)
            nomes = ", ".join(incursao.sala(s).nome for s in empatadas)
            await canal.send(f"Prazo esgotado com empate entre {nomes}. Sorteio decidiu.")
        else:
            escolhida_id = empatadas[0]

        await self._limpar_botoes(run)
        await self._entrar_na_sala(run, incursao.sala(escolhida_id))

    # -------------------------------------------------------------- salas

    async def _entrar_na_sala(self, run: dict[str, Any], sala: Sala) -> None:
        canal = await self._canal(run)
        if not canal:
            return
        total = len(await db.participantes(self.bot.db, run["id"]))

        if sala.tipo == "Descanso":
            await db.atualizar_run(self.bot.db, run["id"], status="em_sala", sala_atual=sala.id)
            combatentes = await self._combatentes(run)
            mudancas = motor.aplicar_descanso(combatentes)
            await db.definir_hp_varios(
                self.bot.db, run["id"], {c.user_id: c.hp_atual for c in combatentes}
            )
            await canal.send(embed=E.descanso(sala, mudancas))
            await self._concluir_sala(await db.buscar_run(self.bot.db, run["id"]), sala, None)
            return

        embed, arquivo = E.sala_aberta(sala, run["linha_atual"], 0, total)
        view = ViewSala(self, run["id"], sala.id) if sala.tem_teste else None
        mensagem = await canal.send(embed=embed, view=view, file=arquivo or discord.utils.MISSING)
        await db.atualizar_run(
            self.bot.db,
            run["id"],
            status="em_sala",
            sala_atual=sala.id,
            mensagem_id=mensagem.id,
            votacao_expira_em=None,
        )

        if sala.e_combate:
            await self._abrir_combate(await db.buscar_run(self.bot.db, run["id"]), sala)

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

    async def _anunciar_pontos(self, run: dict[str, Any]) -> None:
        """Fecha o balanço da run e posta o que cada motivo rendeu."""
        incursao = self._incursao_da_run(run)
        canal = await self._canal(run)
        if not (incursao and canal):
            return
        lancamentos = await db.pontos_da_run(self.bot.db, run["id"])
        if not lancamentos:
            return
        total_org = (await db.placar(self.bot.db, run["guild_id"])).get(incursao.organizacao, 0)
        await canal.send(embed=E.pontos_da_run(incursao, lancamentos, total_org))

    async def _combatentes(self, run: dict[str, Any]) -> list[Combatente]:
        """Monta os combatentes juntando a ficha de cada um com o HP atual da run."""
        combatentes = []
        for p in await db.personagens_da_run(self.bot.db, run["id"]):
            combatentes.append(
                Combatente(
                    user_id=p["user_id"],
                    nome=p["nome"],
                    ca=p["ca"],
                    bonus_ataque=p["bonus_ataque"],
                    dano_arma=p["dano_arma"],
                    hp_max=p["hp_max"],
                    hp_atual=p["hp_max"] if p["hp_atual"] is None else p["hp_atual"],
                )
            )
        return combatentes

    async def _estado_combate(
        self, run: dict[str, Any], sala: Sala
    ) -> Optional[EstadoCombate]:
        linha = await db.estado_combate(self.bot.db, run["id"], sala.id)
        if not linha:
            return None
        # O HP maximo vem do banco: se o monstro for escalado, e esse que vale.
        base = sala.monstro
        monstro = Monstro(base.nome, base.ca, base.ataque, base.dano, linha["monstro_hp_max"])
        return EstadoCombate(
            monstro=monstro,
            monstro_hp=linha["monstro_hp"],
            rodada=linha["rodada"],
            combatentes=await self._combatentes(run),
        )

    async def _abrir_combate(self, run: dict[str, Any], sala: Sala) -> None:
        canal = await self._canal(run)
        if not canal:
            return
        niveis = await self._niveis(run)
        monstro = motor.escalar_monstro(sala.monstro, niveis)
        await db.iniciar_combate(self.bot.db, run["id"], sala.id, monstro.hp)

        estado = await self._estado_combate(run, sala)
        embed, arquivo = E.combate(sala, estado, 0)
        mensagem = await canal.send(
            embed=embed,
            view=ViewCombate(self, run["id"], sala.id),
            file=arquivo or discord.utils.MISSING,
        )
        await db.atualizar_run(self.bot.db, run["id"], mensagem_id=mensagem.id)

    async def _niveis(self, run: dict[str, Any]) -> list[int]:
        return [p["nivel"] for p in await db.personagens_da_run(self.bot.db, run["id"])]

    async def atacar(self, interaction: discord.Interaction, run_id: int, sala_id: str) -> None:
        run = await db.buscar_run(self.bot.db, run_id)
        if not run or run["status"] not in ("em_sala", "objetivo") or run["sala_atual"] != sala_id:
            await interaction.response.send_message("Este combate já terminou.", ephemeral=True)
            return
        if not await db.esta_na_run(self.bot.db, run_id, interaction.user.id):
            await interaction.response.send_message("Você não faz parte desta run.", ephemeral=True)
            return

        incursao = self._incursao_da_run(run)
        sala = incursao.sala(sala_id)
        estado = await self._estado_combate(run, sala)
        if estado is None:
            await interaction.response.send_message("Este combate já terminou.", ephemeral=True)
            return

        atacante = estado.combatente(interaction.user.id)
        if atacante is None:
            await interaction.response.send_message(
                "Você não tem ficha cadastrada. Use `/ficha registrar`.", ephemeral=True
            )
            return
        if atacante.caido:
            await interaction.response.send_message(
                "Você está caído — fica fora do resto deste combate.", ephemeral=True
            )
            return

        golpe = motor.atacar_monstro(atacante, estado, None)
        novo = await db.registrar_ataque(
            self.bot.db,
            run_id,
            sala_id,
            estado.rodada,
            interaction.user.id,
            golpe.d20,
            golpe.bonus,
            golpe.ca_alvo,
            golpe.dano,
        )
        if not novo:
            await interaction.response.send_message(
                "Você já atacou nesta rodada.", ephemeral=True
            )
            return

        await db.atualizar_combate(
            self.bot.db, run_id, sala_id, estado.monstro_hp, estado.rodada
        )

        if golpe.acertou:
            texto = (
                f"⚔️ 🎲 **{golpe.d20}** {golpe.bonus:+d} = **{golpe.total}** vs CA "
                f"{golpe.ca_alvo} — acertou, **{golpe.dano}** de dano."
            )
        else:
            texto = (
                f"💨 🎲 **{golpe.d20}** {golpe.bonus:+d} = **{golpe.total}** vs CA "
                f"{golpe.ca_alvo} — errou."
            )
        await interaction.response.send_message(texto, ephemeral=True)

        ataques = await db.ataques_da_rodada(self.bot.db, run_id, sala_id, estado.rodada)
        if estado.monstro_derrotado or len(ataques) >= len(estado.vivos):
            await self._fechar_rodada(run, sala, estado, ataques)
        elif interaction.message is not None:
            embed, _ = E.combate(sala, estado, len(ataques))
            try:
                await interaction.message.edit(
                    embed=embed, view=ViewCombate(self, run_id, sala_id)
                )
            except discord.HTTPException:
                pass

    async def _fechar_rodada(
        self,
        run: dict[str, Any],
        sala: Sala,
        estado: EstadoCombate,
        ataques: list[dict[str, Any]],
    ) -> None:
        canal = await self._canal(run)
        if not canal:
            return
        await self._limpar_botoes(await db.buscar_run(self.bot.db, run["id"]))

        golpes = [
            motor.GolpeAtaque(
                atacante=(estado.combatente(a["user_id"]).nome
                          if estado.combatente(a["user_id"]) else "?"),
                alvo=estado.monstro.nome,
                d20=a["d20"],
                bonus=a["bonus"],
                ca_alvo=a["ca_alvo"],
                dano=a["dano"],
            )
            for a in ataques
        ]

        contra, alvo = None, None
        if not estado.monstro_derrotado:
            alvo = motor.sortear_alvo(estado)
            if alvo is not None:
                contra = motor.contra_atacar(estado, alvo, None)
                await db.definir_hp(self.bot.db, run["id"], alvo.user_id, alvo.hp_atual)

        await canal.send(
            embed=E.rodada_resolvida(
                estado.rodada, golpes, contra, alvo.nome if alvo else None, estado
            )
        )

        if estado.monstro_derrotado:
            await canal.send(embed=E.combate_vencido(sala, estado))
            await self._apos_combate_vencido(run, sala)
            return

        if estado.grupo_caido:
            await self._encerrar_run(run, "fracasso")
            incursao = self._incursao_da_run(run)
            await canal.send(embed=E.run_fracassada(incursao, estado))
            # Mesmo derrotado, o grupo levou a run ate o fim: a participacao conta.
            await self._creditar(
                run, config.PONTOS_PARTICIPACAO, "Participação na incursão", "participacao"
            )
            await self._anunciar_pontos(await db.buscar_run(self.bot.db, run["id"]))
            return

        # Proxima rodada: novo painel, novos ataques.
        estado.rodada += 1
        await db.atualizar_combate(
            self.bot.db, run["id"], sala.id, estado.monstro_hp, estado.rodada
        )
        embed, _ = E.combate(sala, estado, 0)
        mensagem = await canal.send(embed=embed, view=ViewCombate(self, run["id"], sala.id))
        await db.atualizar_run(self.bot.db, run["id"], mensagem_id=mensagem.id)

    async def _apos_combate_vencido(self, run: dict[str, Any], sala: Sala) -> None:
        incursao = self._incursao_da_run(run)
        if sala.pontos_organizacao:
            await self._creditar(
                run, sala.pontos_organizacao, f"Sala superada: {sala.nome}", f"sala:{sala.id}"
            )

        if sala.id == incursao.objetivo.id:
            await self._encerrar_run(run, "sucesso")
            await self._creditar(
                run, config.PONTOS_PARTICIPACAO, "Participação na incursão", "participacao"
            )
            await self._creditar(
                run, incursao.pontos_conclusao, "Objetivo cumprido", "conclusao"
            )
            canal = await self._canal(run)
            if canal:
                await canal.send(embed=E.run_concluida(incursao, await self._membros(run)))
            await self._anunciar_pontos(await db.buscar_run(self.bot.db, run["id"]))
            return

        linha = run["linha_atual"]
        if linha < LINHAS:
            await self._abrir_votacao(await db.buscar_run(self.bot.db, run["id"]), linha + 1)
        else:
            await self._chegar_ao_objetivo(await db.buscar_run(self.bot.db, run["id"]))

    async def rolar(self, interaction: discord.Interaction, run_id: int, sala_id: str) -> None:
        run = await db.buscar_run(self.bot.db, run_id)
        if not run or run["status"] != "em_sala" or run["sala_atual"] != sala_id:
            await interaction.response.send_message("Esta sala já foi resolvida.", ephemeral=True)
            return
        if not await db.esta_na_run(self.bot.db, run_id, interaction.user.id):
            await interaction.response.send_message("Você não faz parte desta run.", ephemeral=True)
            return

        incursao = self._incursao_da_run(run)
        sala = incursao.sala(sala_id)
        personagem = await db.personagem_da_run(self.bot.db, run_id, interaction.user.id)
        if not personagem:
            await interaction.response.send_message(
                "Não achei o personagem com que você entrou nesta run.", ephemeral=True
            )
            return

        personagem["user_id"] = interaction.user.id
        resultado = motor.testar(personagem, sala)
        novo = await db.registrar_teste(
            self.bot.db,
            run_id,
            sala_id,
            interaction.user.id,
            resultado.personagem,
            resultado.pericia,
            resultado.d20,
            resultado.modificador,
            resultado.cd,
        )
        if not novo:
            await interaction.response.send_message(
                "Você já rolou nesta sala — cada um rola uma vez.", ephemeral=True
            )
            return

        veredito = (
            f"passou por **{resultado.margem}** de margem"
            if resultado.passou
            else f"falhou por **{resultado.cd - resultado.total}**"
        )
        await interaction.response.send_message(
            f"🎲 **{resultado.d20}** {resultado.modificador:+d} = **{resultado.total}** "
            f"em {resultado.pericia} (CD {resultado.cd}) — {veredito}.",
            ephemeral=True,
        )

        registros = await db.testes_da_sala(self.bot.db, run_id, sala_id)
        total = len(await db.participantes(self.bot.db, run_id))
        resolucao = _resolucao(sala, registros, total)

        if resolucao.encerrada:
            await self._concluir_sala(run, sala, resolucao)
        else:
            embed, _ = E.sala_aberta(sala, run["linha_atual"], len(registros), total)
            if interaction.message is not None:
                try:
                    await interaction.message.edit(embed=embed, view=ViewSala(self, run_id, sala_id))
                except discord.HTTPException:
                    pass

    async def _concluir_sala(
        self, run: dict[str, Any], sala: Sala, resolucao: Optional[ResolucaoSala]
    ) -> None:
        canal = await self._canal(run)
        if not canal:
            return

        await self._limpar_botoes(await db.buscar_run(self.bot.db, run["id"]))

        if resolucao is not None:
            apelidos = await self._apelidos(run)
            await canal.send(embed=E.resultado_sala(resolucao, apelidos))
            if resolucao.superada and sala.pontos_organizacao:
                await self._creditar(
                    run, sala.pontos_organizacao, f"Sala superada: {sala.nome}", f"sala:{sala.id}"
                )

        linha = run["linha_atual"]
        if linha < LINHAS:
            await self._abrir_votacao(run, linha + 1)
        else:
            await self._chegar_ao_objetivo(run)

    async def _chegar_ao_objetivo(self, run: dict[str, Any]) -> None:
        incursao = self._incursao_da_run(run)
        canal = await self._canal(run)
        if not (incursao and canal):
            return

        niveis = await self._niveis(run)
        monstro = motor.escalar_monstro(incursao.objetivo.monstro, niveis)

        embed, arquivo = E.objetivo(incursao, monstro.nome)
        await canal.send(embed=embed, file=arquivo or discord.utils.MISSING)
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

    @grupo.command(name="sala", description="Reenvia a mensagem da sala atual")
    async def sala(self, interaction: discord.Interaction) -> None:
        run = await self._run_do_contexto(interaction, exigir_participante=False)
        if not run:
            return
        incursao = self._incursao_da_run(run)
        if run["status"] == "escolhendo":
            await interaction.response.send_message(
                "O grupo está votando a próxima sala.", ephemeral=True
            )
            return
        sala = incursao.sala(run["sala_atual"]) if run["sala_atual"] else None
        if not sala:
            await interaction.response.send_message("A run ainda não entrou numa sala.", ephemeral=True)
            return
        if sala.e_combate:
            estado = await self._estado_combate(run, sala)
            if estado is None:
                await interaction.response.send_message(
                    "Este combate já terminou.", ephemeral=True
                )
                return
            ataques = await db.ataques_da_rodada(
                self.bot.db, run["id"], sala.id, estado.rodada
            )
            embed, arquivo = E.combate(sala, estado, len(ataques))
            await interaction.response.send_message(
                embed=embed,
                view=ViewCombate(self, run["id"], sala.id),
                file=arquivo or discord.utils.MISSING,
            )
            mensagem = await interaction.original_response()
            await db.atualizar_run(self.bot.db, run["id"], mensagem_id=mensagem.id)
            return

        registros = await db.testes_da_sala(self.bot.db, run["id"], sala.id)
        total = len(await db.participantes(self.bot.db, run["id"]))
        embed, arquivo = E.sala_aberta(sala, run["linha_atual"], len(registros), total)
        view = ViewSala(self, run["id"], sala.id) if sala.tem_teste else None
        await interaction.response.send_message(
            embed=embed, view=view, file=arquivo or discord.utils.MISSING
        )
        mensagem = await interaction.original_response()
        await db.atualizar_run(self.bot.db, run["id"], mensagem_id=mensagem.id)

    @grupo.command(name="teste", description="Rola o teste da sala atual (mesmo efeito do botão)")
    async def teste(self, interaction: discord.Interaction) -> None:
        run = await self._run_do_contexto(interaction)
        if not run:
            return
        if run["status"] != "em_sala" or not run["sala_atual"]:
            await interaction.response.send_message("Não há teste aberto agora.", ephemeral=True)
            return
        incursao = self._incursao_da_run(run)
        sala = incursao.sala(run["sala_atual"])
        if sala and sala.e_combate:
            await interaction.response.send_message(
                "Sala de combate não usa teste de perícia — use `/incursao atacar`.",
                ephemeral=True,
            )
            return
        await self.rolar(interaction, run["id"], run["sala_atual"])

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
        incursao = self._incursao_da_run(run)
        sala = incursao.opcoes(run["linha_atual"])[opcao - 1]
        await self.votar(interaction, run["id"], run["linha_atual"], sala.id)

    @grupo.command(name="atacar", description="Ataca o monstro da sala (mesmo efeito do botão)")
    async def atacar_comando(self, interaction: discord.Interaction) -> None:
        run = await self._run_do_contexto(interaction)
        if not run:
            return
        if run["status"] not in ("em_sala", "objetivo") or not run["sala_atual"]:
            await interaction.response.send_message("Não há combate aberto agora.", ephemeral=True)
            return
        incursao = self._incursao_da_run(run)
        sala = incursao.sala(run["sala_atual"])
        if not (sala and sala.e_combate):
            await interaction.response.send_message(
                "Esta sala não é de combate.", ephemeral=True
            )
            return
        await self.atacar(interaction, run["id"], run["sala_atual"])

    @grupo.command(name="status", description="Estado atual da run neste canal")
    async def status(self, interaction: discord.Interaction) -> None:
        run = await self._run_do_contexto(interaction, exigir_participante=False)
        if not run:
            return
        incursao = self._incursao_da_run(run)
        sala = incursao.sala(run["sala_atual"]) if run["sala_atual"] else None
        registros = (
            await db.testes_da_sala(self.bot.db, run["id"], sala.id) if sala else []
        )
        await interaction.response.send_message(
            embed=E.status(run, incursao, await self._membros(run), sala, len(registros))
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
        necessarios = total // 2 + 1

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
            f"{len(self.incursoes)} incursão(ões) carregada(s): "
            f"{', '.join(self.incursoes) or 'nenhuma'}.",
            ephemeral=True,
        )

    config_grupo = app_commands.Group(
        name="config", description="Ajustes do bot (admin)", default_permissions=discord.Permissions(manage_guild=True)
    )

    @config_grupo.command(name="intervalo", description="Dias mínimos entre incursões do mesmo jogador")
    async def config_intervalo(
        self, interaction: discord.Interaction, dias: app_commands.Range[int, 0, 365]
    ) -> None:
        await db.definir_intervalo(self.bot.db, interaction.guild_id, dias)
        await interaction.response.send_message(
            f"Intervalo entre incursões ajustado para **{dias} dia(s)**.", ephemeral=True
        )

    # ------------------------------------------------------------- prazos

    @tasks.loop(minutes=1)
    async def verificar_prazos(self) -> None:
        try:
            for run in await db.votacoes_expiradas(self.bot.db):
                await self._fechar_votacao(run, run["linha_atual"], por_prazo=True)
        except Exception:
            log.exception("erro ao fechar votações vencidas")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Incursoes(bot))
