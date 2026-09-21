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
from ..incursoes import Incursao, Sala, carregar_todas
from ..motor import ResolucaoSala, ResultadoTeste

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
        if run["status"] == "em_sala" and run["sala_atual"]:
            sala = incursao.sala(run["sala_atual"])
            if sala and sala.tem_teste:
                return ViewSala(self, run["id"], sala.id)
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

    @grupo.command(name="entrar", description="Abre o recrutamento de uma incursão neste canal")
    @app_commands.autocomplete(incursao_id=_sugerir_incursoes)
    async def entrar(self, interaction: discord.Interaction, incursao_id: str) -> None:
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

        run_id = await db.criar_run(
            self.bot.db, interaction.guild_id, interaction.channel_id, incursao.id, interaction.user.id
        )
        await db.adicionar_participante(self.bot.db, run_id, interaction.user.id)

        run = await db.buscar_run(self.bot.db, run_id)
        view = ViewRecrutamento(self, run_id)
        await interaction.response.send_message(
            embed=E.recrutamento(incursao, await self._membros(run), interaction.user), view=view
        )
        mensagem = await interaction.original_response()
        await db.atualizar_run(self.bot.db, run_id, mensagem_id=mensagem.id)

    async def _motivo_de_bloqueio(self, guild_id: int, user_id: int) -> Optional[str]:
        """Texto do impedimento para entrar numa run, ou None se estiver liberado."""
        ficha = await db.buscar_ficha(self.bot.db, guild_id, user_id)
        if not ficha:
            return "Você ainda não tem ficha. Cadastre com `/ficha registrar` antes de entrar."
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
            await db.adicionar_participante(self.bot.db, run_id, interaction.user.id)

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
        if len(membros) >= config.TAMANHO_GRUPO:
            await self._iniciar(await db.buscar_run(self.bot.db, run_id))

    async def _iniciar(self, run: dict[str, Any]) -> None:
        participantes = await db.participantes(self.bot.db, run["id"])
        if not participantes:
            return
        await db.marcar_ultima_incursao(self.bot.db, run["guild_id"], participantes)
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
            await canal.send(embed=E.descanso(sala))
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
            await canal.send(
                "⚔️ Sala de combate. A resolução por rodadas (CA, ataque e HP) entra na "
                "próxima fase do bot — por ora o grupo fica parado aqui."
            )

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
        ficha = await db.buscar_ficha(self.bot.db, run["guild_id"], interaction.user.id)
        if not ficha:
            await interaction.response.send_message(
                "Você não tem ficha cadastrada. Use `/ficha registrar`.", ephemeral=True
            )
            return

        ficha["user_id"] = interaction.user.id
        resultado = motor.testar(ficha, sala)
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

        ids = await db.participantes(self.bot.db, run["id"])
        niveis = []
        for user_id in ids:
            ficha = await db.buscar_ficha(self.bot.db, run["guild_id"], user_id)
            if ficha:
                niveis.append(ficha["nivel"])
        monstro = motor.escalar_monstro(incursao.objetivo.monstro, niveis)

        embed, arquivo = E.objetivo(incursao, monstro.nome)
        mensagem = await canal.send(embed=embed, file=arquivo or discord.utils.MISSING)
        await db.atualizar_run(
            self.bot.db,
            run["id"],
            status="objetivo",
            sala_atual=incursao.objetivo.id,
            mensagem_id=mensagem.id,
            votacao_expira_em=None,
        )
        await canal.send(
            f"O grupo atravessou as três linhas e chegou ao objetivo (peso do grupo: "
            f"{motor.peso_do_grupo(niveis)}). O combate final entra na próxima fase do bot."
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
            await db.atualizar_run(self.bot.db, run["id"], status="desistiu", votacao_expira_em=None)
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
