"""Runs de incursão: recrutamento, votação por linha, salas e testes de perícia.

A run é assíncrona: o estado vive no banco, não na memória, para que o grupo
possa avançar ao longo de dias e o bot possa reiniciar sem perder nada.
"""
from __future__ import annotations

import logging
import random
from datetime import datetime, timezone
from typing import Any, Optional

import discord
from discord import app_commands
from discord.ext import commands

from .. import config, database as db, embeds as E, motor
from ..incursoes import (
    BancoDeSalas,
    Incursao,
    Sala,
    arquivo_da_organizacao,
    carregar_bancos,
    carregar_todas,
)
from ..motor import Combatente, EstadoCombate, ResolucaoSala, ResultadoTeste
from ..rules import tier

log = logging.getLogger("incursoes.run")


def _agora() -> datetime:
    return datetime.now(timezone.utc)


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
                        f"Nivel {p['nivel']} (tier {tier(p['nivel'])}) · "
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


class Incursoes(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.incursoes: dict[str, Incursao] = {}
        self.bancos: dict[str, BancoDeSalas] = {}

    async def cog_load(self) -> None:
        self._carregar_tolerante()
        await self.restaurar_views()

    def recarregar_incursoes(self) -> None:
        pasta = config.RAIZ / "data" / "incursoes"
        bancos = config.RAIZ / "data" / "bancos"
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
            sala = self._sala(incursao, run["sala_atual"])
            if sala and sala.tem_teste:
                return ViewSala(self, run["id"], sala.id)
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

    async def _membro(self, run: dict[str, Any], user_id: int):
        """O membro do servidor, ou o usuário, para menção e apelido."""
        guilda = self.bot.get_guild(run["guild_id"])
        membro = guilda.get_member(user_id) if guilda else None
        if membro is None and guilda is not None:
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
            salas_no_banco = len(self.bancos[inc.organizacao].salas) if inc.organizacao in self.bancos else 0
            e.add_field(
                name=f"{inc.nome}  ·  `{inc.id}`",
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
            self.bot.db, run_id, interaction.user.id, escolhido["id"]
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
            f"**{p['nome']}** (nível {p['nivel']}, tier {tier(p['nivel'])})" for p in personagens
        )
        return (
            f"**{incursao.nome}** é de tier {incursao.tier}: entra quem for tier "
            f"{incursao.tier} ou menos, ou seja, até o nível {incursao.nivel_maximo}. "
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
        total = len(await db.participantes(self.bot.db, run["id"]))
        votos = await db.votos_da_linha(self.bot.db, run["id"], linha)
        view = ViewVotacao(self, run["id"], linha, opcoes)
        mensagem = await canal.send(
            embed=E.votacao(incursao, linha, opcoes, votos, total, incursao.passos), view=view
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

        await db.registrar_voto(self.bot.db, run_id, linha, interaction.user.id, sala_id)
        incursao = self._incursao_da_run(run)
        sala = self._sala(incursao, sala_id)
        await interaction.response.send_message(
            f"Voto registrado: **{sala.nome if sala else sala_id}**.", ephemeral=True
        )

        votos = await db.votos_da_linha(self.bot.db, run_id, linha)
        total = len(await db.participantes(self.bot.db, run_id))
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

        total = len(await db.participantes(self.bot.db, run["id"]))
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

        faltaram = total - len(votos)
        if faltaram > 0:
            nome = self._sala(incursao, escolhida_id).nome
            await canal.send(
                f"**{nome}** fechou com {maximo} de {total} votos — maioria formada, "
                f"o grupo não espera os {faltaram} que faltam."
            )

        await self._limpar_botoes(run)
        await self._entrar_na_sala(run, self._sala(incursao, escolhida_id))

    # -------------------------------------------------------------- salas

    async def _entrar_na_sala(self, run: dict[str, Any], sala: Sala) -> None:
        canal = await self._canal(run)
        if not canal:
            return
        # Atravessar a sala a tira do sorteio: ela nao volta a ser oferecida.
        await db.registrar_visita(self.bot.db, run["id"], self._passo(run), sala.id)
        total = len(await db.participantes(self.bot.db, run["id"]))

        if sala.tipo == "Descanso":
            await db.atualizar_run(self.bot.db, run["id"], status="em_sala", sala_atual=sala.id)
            # O contador de descansos e o que zera as habilidades por descanso.
            await db.contar_descanso(self.bot.db, run["id"])
            combatentes = await self._combatentes(run)
            mudancas = motor.aplicar_descanso(combatentes)
            await db.definir_hp_varios(
                self.bot.db, run["id"], {c.user_id: c.hp_atual for c in combatentes}
            )
            await canal.send(embed=E.descanso(sala, mudancas))
            await self._concluir_sala(await db.buscar_run(self.bot.db, run["id"]), sala, None)
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
            sala, run["linha_atual"], 0, total, incursao.passos if incursao else None
        )
        view = ViewSala(self, run["id"], sala.id) if sala.tem_teste else None
        mensagem = await canal.send(embed=embed, view=view, file=arquivo or discord.utils.MISSING)
        await db.atualizar_run(self.bot.db, run["id"], mensagem_id=mensagem.id)

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

    async def _combatentes(
        self, run: dict[str, Any], efeitos_ligados: Optional[list[dict]] = None
    ) -> list[Combatente]:
        """Monta os combatentes juntando a ficha de cada um com o HP atual da run."""
        combatentes = []
        for p in await db.personagens_da_run(self.bot.db, run["id"]):
            # As passivas da classe entram como numero: multiataque, critico
            # mais facil e dano extra saem daqui.
            efeitos = p.get("efeitos") or {}
            combatentes.append(
                Combatente(
                    user_id=p["user_id"],
                    nome=p["nome"],
                    ca=p["ca"],
                    bonus_ataque=p["bonus_ataque"],
                    dano_arma=p["dano_arma"],
                    hp_max=p["hp_max"],
                    hp_atual=p["hp_max"] if p["hp_atual"] is None else p["hp_atual"],
                    thp=p.get("thp") or 0,
                    ataques=efeitos.get("ataques", 1),
                    critico_em=efeitos.get("critico_em", 20),
                    dano_extra=efeitos.get("dano_extra", 0),
                    dano_ferido=efeitos.get("dano_ferido", 0),
                    saves=p.get("saves") or {},
                )
            )
        for ligado in efeitos_ligados or []:
            self._aplicar_ligado(combatentes, ligado)
        self._aplicar_aura_totemica(
            combatentes, await db.personagens_da_run(self.bot.db, run["id"])
        )
        return combatentes

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
            quem.reducao_dano = max(quem.reducao_dano, valor.get("reducao_dano", 0.0))
            quem.cura_por_turno = max(
                quem.cura_por_turno, valor.get("cura_por_turno", 0.0)
            )
            quem.vantagem = quem.vantagem or bool(valor.get("vantagem"))
            # A sequencia do Martial Arts nao entra aqui: ela e contada golpe a
            # golpe dentro do turno, em atacar().
            return

        # Efeito posto num inimigo: quem ganha e o dono da marca.
        dono = next((c for c in combatentes if c.user_id == ligado["dono"]), None)
        if dono is None:
            return
        if valor.get("dano_bonus"):
            dono.dano_por_alvo[ligado["alvo_id"]] = valor["dano_bonus"]
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
            )
            for r in await db.inimigos_do_combate(self.bot.db, run["id"], passo)
        ]
        if not inimigos:
            return None
        ligados = await db.efeitos_ativos(
            self.bot.db, run["id"], passo, linha["rodada"] - 1
        )
        for ligado in ligados:
            if ligado["alvo_tipo"] == "inimigo" and ligado["efeito"] == "atordoado":
                alvo = next((i for i in inimigos if i.indice == ligado["alvo_id"]), None)
                if alvo:
                    alvo.atordoado = True
        return EstadoCombate(
            inimigos=inimigos,
            rodada=linha["rodada"],
            combatentes=await self._combatentes(run, ligados),
        )

    async def _abrir_combate(self, run: dict[str, Any], sala: Sala) -> None:
        canal = await self._canal(run)
        if not canal:
            return
        niveis = await self._niveis(run)
        inimigos = [motor.escalar_monstro(m, niveis) for m in sala.monstros]
        await db.iniciar_combate(self.bot.db, run["id"], self._passo(run), sala.id, inimigos)

        incursao = self._incursao_da_run(run)
        e_objetivo = bool(incursao and sala.id == incursao.objetivo.id)
        estado = await self._estado_combate(run, sala)
        embed, arquivo = E.combate(
            sala,
            estado,
            0,
            e_objetivo=e_objetivo,
            recompensa=sala.recompensa if e_objetivo else None,
        )
        mensagem = await canal.send(
            embed=embed,
            view=ViewCombate(self, run["id"], sala.id, estado.inimigos if estado else None),
            file=arquivo or discord.utils.MISSING,
        )
        await db.atualizar_run(self.bot.db, run["id"], mensagem_id=mensagem.id)

    async def _atualizar_painel(
        self,
        run: dict[str, Any],
        sala: Sala,
        estado,
        ja_atacaram: int,
        rodada_anterior=None,
        encerrado: bool = False,
    ) -> None:
        """Reescreve o painel do combate no lugar, sem postar mensagem nova."""
        canal = await self._canal(run)
        atual = await db.buscar_run(self.bot.db, run["id"])
        if not canal or not atual or not atual["mensagem_id"]:
            return
        incursao = self._incursao_da_run(run)
        embed, _ = E.combate(
            sala,
            estado,
            ja_atacaram,
            e_objetivo=bool(incursao and sala.id == incursao.objetivo.id),
            rodada_anterior=rodada_anterior,
            encerrado=encerrado,
        )
        view = (
            None if encerrado else ViewCombate(self, run["id"], sala.id, estado.inimigos)
        )
        try:
            mensagem = await canal.fetch_message(atual["mensagem_id"])
            await mensagem.edit(embed=embed, view=view)
        except discord.HTTPException:
            pass

    async def _niveis(self, run: dict[str, Any]) -> list[int]:
        return [p["nivel"] for p in await db.personagens_da_run(self.bot.db, run["id"])]

    async def atacar(
        self,
        interaction: discord.Interaction,
        run_id: int,
        sala_id: str,
        alvo_indice: Optional[int] = None,
    ) -> None:
        run = await db.buscar_run(self.bot.db, run_id)
        if not run or run["status"] not in ("em_sala", "objetivo") or run["sala_atual"] != sala_id:
            await interaction.response.send_message("Este combate já terminou.", ephemeral=True)
            return
        if not await db.esta_na_run(self.bot.db, run_id, interaction.user.id):
            await interaction.response.send_message("Você não faz parte desta run.", ephemeral=True)
            return

        incursao = self._incursao_da_run(run)
        sala = self._sala(incursao, sala_id)
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

        alvo = estado.alvo_preferido(alvo_indice)
        if alvo is None:
            await interaction.response.send_message(
                "Esse inimigo já caiu — escolha outro alvo.", ephemeral=True
            )
            return

        passo = self._passo(run)
        if await db.ja_atacou(
            self.bot.db, run_id, passo, estado.rodada, interaction.user.id
        ):
            await interaction.response.send_message(
                "Você já atacou nesta rodada.", ephemeral=True
            )
            return

        # Multiataque gasta o turno inteiro num clique so: se o alvo cair no
        # meio, o golpe seguinte vai para o proximo inimigo de pe.
        golpes: list[tuple[motor.GolpeAtaque, Any]] = []
        # O indice continua de onde parou: uma habilidade pode ter gravado
        # golpes antes do turno, e dois golpes nao podem dividir a mesma chave.
        indice = await db.proximo_indice_de_ataque(
            self.bot.db, run_id, passo, estado.rodada, interaction.user.id
        )
        personagem = await self._personagem_na_run(run, interaction.user.id)
        sequencia = ((personagem or {}).get("efeitos") or {}).get("sequencia") or {}
        pilha = await self._pilha_de_sequencia(run, interaction.user.id, passo)
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
                self.bot.db,
                run_id,
                passo,
                estado.rodada,
                interaction.user.id,
                golpe.d20,
                golpe.bonus,
                golpe.ca_alvo,
                golpe.dano,
                atual.indice,
                indice,
            )
            indice += 1

        await db.definir_hp_inimigos(
            self.bot.db,
            run_id,
            passo,
            {inimigo.indice: inimigo.hp_atual for _golpe, inimigo in golpes},
        )
        if personagem:
            await self._totem_do_golpe(run, personagem, atacante, golpes)
        if sequencia:
            await self._guardar_sequencia(run, interaction.user.id, passo, pilha)

        await interaction.response.send_message(
            E.resumo_do_golpe([(g, i.nome) for g, i in golpes]), ephemeral=True
        )

        ataques = await db.ataques_da_rodada(self.bot.db, run_id, passo, estado.rodada)
        agiram = {a["user_id"] for a in ataques}
        if estado.inimigos_derrotados or len(agiram) >= len(estado.vivos):
            await self._fechar_rodada(run, sala, estado, ataques)
        else:
            await self._atualizar_painel(run, sala, estado, len(agiram))

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
        """Gasta um uso e resolve a habilidade, pedindo alvo se precisar."""
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

        passo = self._passo(run)
        disponiveis = await self._habilidades_disponiveis(run, personagem, passo)
        habilidade = next((h for h, _r in disponiveis if h.id == habilidade_id), None)
        if habilidade is None:
            await interaction.response.send_message(
                "Essa habilidade nao esta disponivel agora.", ephemeral=True
            )
            return

        incursao = self._incursao_da_run(run)
        sala = self._sala(incursao, sala_id)
        estado = await self._estado_combate(run, sala) if sala and sala.e_combate else None
        acao = habilidade.acao or {}

        # Quem usa precisa estar de pe quando a habilidade e de combate.
        atacante = estado.combatente(interaction.user.id) if estado else None
        if estado is not None and (atacante is None or atacante.caido):
            await interaction.response.send_message(
                "Voce esta caido — fica fora do resto deste combate.", ephemeral=True
            )
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
                await interaction.response.send_message(
                    f"**{habilidade.nome}** so vale com a outra habilidade ligada.",
                    ephemeral=True,
                )
                return

        if acao.get("tipo") == "golpes" and estado is None:
            await interaction.response.send_message(
                "Essa habilidade so vale em combate.", ephemeral=True
            )
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
            await interaction.response.send_message(
                "Os usos desta habilidade ja acabaram.", ephemeral=True
            )
            return

        if acao.get("tipo") == "cura":
            await self._resolver_cura(interaction, run, habilidade, acao, alvos, estado)
            return
        if acao.get("tipo") == "grupo":
            await self._resolver_grupo(
                interaction, run, sala, estado, habilidade, acao
            )
            return
        if acao.get("tipo") == "duracao":
            await self._resolver_duracao(
                interaction, run, sala, estado, habilidade, acao, alvos
            )
            return
        await self._resolver_golpes(
            interaction, run, sala, estado, atacante, habilidade, acao, alvos
        )

    async def _pedir_alvo(
        self, interaction: discord.Interaction, run, sala_id, habilidade, estado
    ):
        """Abre o menu de alvo se a habilidade precisa de um. False = nao precisa."""
        acao = habilidade.acao or {}
        if acao.get("tipo") == "cura":
            if acao.get("alvo") != "aliado":
                return False
            opcoes = [
                (str(p["user_id"]), p["nome"], f"{p['hp_atual']}/{p['hp_max']} HP")
                for p in await db.personagens_da_run(self.bot.db, run["id"])
            ]
        else:
            vivos = estado.inimigos_vivos if estado else []
            if len(vivos) <= 1 and acao.get("alvos", 1) <= 1:
                return False
            opcoes = [
                (str(i.indice), i.nome, f"{i.hp_atual}/{i.hp_max} HP · CA {i.ca}")
                for i in vivos
            ]
        if not opcoes:
            await interaction.response.send_message(
                "Nao ha alvo possivel agora.", ephemeral=True
            )
            return True
        await interaction.response.send_message(
            f"**{habilidade.nome}** — escolha o alvo:",
            view=SeletorAlvoHabilidade(
                self, run["id"], sala_id, habilidade.id, opcoes, acao.get("alvos", 1)
            ),
            ephemeral=True,
        )
        return True

    async def _resolver_cura(
        self, interaction, run, habilidade, acao, alvos, estado
    ) -> None:
        """Cura a si mesmo ou a um aliado, dentro ou fora do combate."""
        combatentes = estado.combatentes if estado else await self._combatentes(run)
        alvo_id = alvos[0] if alvos else interaction.user.id
        alvo = next((c for c in combatentes if c.user_id == alvo_id), None)
        if alvo is None:
            await interaction.response.send_message("Alvo invalido.", ephemeral=True)
            return

        curado = motor.curar(alvo, acao["fracao"])
        await db.definir_hp(self.bot.db, run["id"], alvo.user_id, alvo.hp_atual)
        temporario = 0
        quanto_thp = motor.rolar_dano(acao["thp_alvo"]) if acao.get("thp_alvo") else 0
        # Cantico Benevolente: a escolha do Xama soma THP em cima da cura.
        quem_curou = await self._personagem_na_run(run, interaction.user.id)
        extra_cantico = ((quem_curou or {}).get("efeitos") or {}).get("thp_na_cura", 0)
        if extra_cantico and alvo.user_id != interaction.user.id:
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
        await interaction.response.send_message(texto, ephemeral=True)
        await self._anunciar_habilidade(run, texto)
        if estado is not None:
            sala = self._sala(self._incursao_da_run(run), run["sala_atual"])
            ataques = await db.ataques_da_rodada(
                self.bot.db, run["id"], self._passo(run), estado.rodada
            )
            agiram = {a["user_id"] for a in ataques if a["origem"] == "turno"}
            await self._atualizar_painel(run, sala, estado, len(agiram))

    async def _resolver_grupo(
        self, interaction, run, sala, estado, habilidade, acao
    ) -> None:
        """Habilidade que cai no grupo inteiro: THP para todos e um buff curto."""
        passo = self._passo(run)
        quanto = motor.rolar_dano(acao["thp"]) if acao.get("thp") else 0
        novos = {}
        for c in estado.vivos:
            motor.ganhar_thp(c, quanto)
            novos[c.user_id] = c.thp
        if novos:
            await db.definir_thp_varios(self.bot.db, run["id"], novos)

        if acao.get("efeitos"):
            expira = estado.rodada + acao.get("turnos", 1)
            for c in estado.vivos:
                await db.aplicar_efeito(
                    self.bot.db, run["id"], passo, "personagem", c.user_id,
                    habilidade.id, acao["efeitos"], expira,
                )

        if quanto:
            texto = (
                f"\u2728 **{habilidade.nome}**: o grupo ganha **{quanto}** de vida "
                "temporaria e um bonus no proximo ataque."
            )
        else:
            texto = f"\u2728 **{habilidade.nome}**: o grupo inteiro leva o bonus."
        await interaction.response.send_message(texto, ephemeral=True)
        await self._anunciar_habilidade(run, texto)
        atualizado = await self._estado_combate(run, sala)
        if atualizado is not None:
            ataques = await db.ataques_da_rodada(
                self.bot.db, run["id"], passo, atualizado.rodada
            )
            agiram = {a["user_id"] for a in ataques if a["origem"] == "turno"}
            await self._atualizar_painel(run, sala, atualizado, len(agiram))

    async def _resolver_duracao(
        self, interaction, run, sala, estado, habilidade, acao, alvos
    ) -> None:
        """Liga um efeito com prazo em quem usou, ou no inimigo escolhido."""
        passo = self._passo(run)
        expira = estado.rodada + acao.get("turnos", 1)
        if acao.get("alvo") == "inimigo":
            alvo = estado.inimigo(alvos[0]) if alvos else estado.alvo_preferido()
            if alvo is None or alvo.caido:
                await interaction.response.send_message(
                    "Esse inimigo nao esta de pe.", ephemeral=True
                )
                return
            await db.aplicar_efeito(
                self.bot.db, run["id"], passo, "inimigo", alvo.indice,
                habilidade.id, acao["efeitos"], expira, dono=interaction.user.id,
            )
            alvo_nome = alvo.nome
        else:
            await db.aplicar_efeito(
                self.bot.db, run["id"], passo, "personagem", interaction.user.id,
                habilidade.id, acao["efeitos"], expira,
            )
            alvo_nome = None

        quem = estado.combatente(interaction.user.id)
        turnos = acao.get("turnos", 1)
        alvo_texto = f" em **{alvo_nome}**" if alvo_nome else ""
        texto = (
            f"✨ **{habilidade.nome}**{alvo_texto} — vale por "
            f"{turnos} turno(s), ate a rodada {expira - 1}."
        )
        await interaction.response.send_message(texto, ephemeral=True)
        await self._anunciar_habilidade(
            run, f"✨ {quem.nome if quem else 'Alguem'} usa **{habilidade.nome}**{alvo_texto}."
        )

        atualizado = await self._estado_combate(run, sala)
        if atualizado is not None:
            ataques = await db.ataques_da_rodada(
                self.bot.db, run["id"], passo, atualizado.rodada
            )
            agiram = {a["user_id"] for a in ataques if a["origem"] == "turno"}
            await self._atualizar_painel(run, sala, atualizado, len(agiram))

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
        self, interaction, run, sala, estado, atacante, habilidade, acao, alvos
    ) -> None:
        """Os golpes extras de uma ativa: fora do turno, sem gastar o ataque."""
        passo = self._passo(run)
        escolhidos = [i for i in (estado.inimigo(v) for v in alvos) if i and not i.caido]
        if not escolhidos:
            vivo = estado.alvo_preferido()
            escolhidos = [vivo] if vivo else []
        if not escolhidos:
            await interaction.response.send_message(
                "Nao ha inimigo de pe para atacar.", ephemeral=True
            )
            return

        golpes = []
        indice = await db.proximo_indice_de_ataque(
            self.bot.db, run["id"], passo, estado.rodada, interaction.user.id
        )
        for alvo in escolhidos:
            for _ in range(acao.get("quantidade", 1)):
                if alvo.caido:
                    break
                golpe = motor.atacar_inimigo(
                    atacante,
                    alvo,
                    None,
                    dano_bonus=acao.get("dano_bonus"),
                    garantido=acao.get("garantido", False),
                    critico_forcado=acao.get("critico", False),
                )
                golpes.append((golpe, alvo))
                await db.registrar_ataque(
                    self.bot.db, run["id"], passo, estado.rodada, interaction.user.id,
                    golpe.d20, golpe.bonus, golpe.ca_alvo, golpe.dano, alvo.indice,
                    indice, "habilidade",
                )
                indice += 1

        await db.definir_hp_inimigos(
            self.bot.db, run["id"], passo,
            {inimigo.indice: inimigo.hp_atual for _g, inimigo in golpes},
        )
        ganho = 0
        if acao.get("thp_proprio"):
            ganho = motor.ganhar_thp(atacante, motor.rolar_dano(acao["thp_proprio"]))
        if acao.get("thp_igual_ao_bonus"):
            # Brutal Strike: a vida temporaria acompanha o tamanho do golpe.
            ganho = motor.ganhar_thp(
                atacante, max(1, sum(g.dano for g, _i in golpes) // 4)
            )
        if ganho:
            await db.definir_thp(self.bot.db, run["id"], atacante.user_id, atacante.thp)
        personagem = await self._personagem_na_run(run, interaction.user.id)
        if personagem:
            await self._totem_do_golpe(run, personagem, atacante, golpes)

        if acao.get("atordoa"):
            certeiro = next(((g, i) for g, i in golpes if g.acertou), None)
            if certeiro:
                await db.aplicar_efeito(
                    self.bot.db, run["id"], passo, "inimigo", certeiro[1].indice,
                    "atordoado", {}, estado.rodada + acao["atordoa"],
                )
                await self._anunciar_habilidade(
                    run,
                    f"\u2728 **{habilidade.nome}**: {certeiro[1].nome} fica "
                    "atordoado e perde a proxima vez.",
                )
            else:
                # So gasta o recurso quando acerta.
                await db.devolver_uso(
                    self.bot.db, run["id"], interaction.user.id,
                    habilidade.chave_de_uso,
                    self._chave_de_recarga(habilidade, run, passo),
                )

        resumo = E.resumo_do_golpe([(g, i.nome) for g, i in golpes])
        if ganho:
            resumo += f"\nVida temporaria: **{atacante.thp}**."
        await interaction.response.send_message(
            f"\u2728 **{habilidade.nome}**\n{resumo}", ephemeral=True
        )
        await self._anunciar_habilidade(
            run, f"\u2728 {atacante.nome} usa **{habilidade.nome}**."
        )

        ataques = await db.ataques_da_rodada(self.bot.db, run["id"], passo, estado.rodada)
        agiram = {a["user_id"] for a in ataques if a["origem"] == "turno"}
        if estado.inimigos_derrotados or len(agiram) >= len(estado.vivos):
            await self._fechar_rodada(run, sala, estado, ataques)
        else:
            await self._atualizar_painel(run, sala, estado, len(agiram))

    async def _reacao_de(self, personagem: dict[str, Any], quando: str):
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
            habilidade, acao = await self._reacao_de(personagem, "sofreu_golpe")
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
            habilidade, acao = await self._reacao_de(personagem, "caiu")
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

    async def _virar_efeitos(self, run: dict[str, Any], estado) -> None:
        """No fim da rodada: cura de quem tem cura por turno, e prazos vencidos."""
        passo = self._passo(run)
        curas = {}
        for c in estado.vivos:
            if c.cura_por_turno:
                ganho = motor.curar(c, c.cura_por_turno)
                if ganho:
                    curas[c.user_id] = c.hp_atual
        if curas:
            await db.definir_hp_varios(self.bot.db, run["id"], curas)
        await db.limpar_efeitos_vencidos(self.bot.db, run["id"], passo, estado.rodada)

    async def _anunciar_habilidade(self, run: dict[str, Any], texto: str) -> None:
        """O grupo ve que alguem usou uma habilidade, sem detalhe de rolagem."""
        canal = await self._canal(run)
        if canal:
            try:
                await canal.send(texto)
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

        def nome_do_alvo(indice: int) -> str:
            inimigo = estado.inimigo(indice)
            return inimigo.nome if inimigo else "?"

        golpes = []
        for a in ataques:
            quem = estado.combatente(a["user_id"])
            golpes.append(
                motor.GolpeAtaque(
                    atacante=quem.nome if quem else "?",
                    alvo=nome_do_alvo(a["alvo"]),
                    d20=a["d20"],
                    bonus=a["bonus"],
                    ca_alvo=a["ca_alvo"],
                    dano=a["dano"],
                    critico_em=quem.critico_em if quem else 20,
                )
            )

        # A vez dos inimigos: cada um de pe bate uma vez.
        revides: list[tuple[motor.GolpeAtaque, Any]] = []
        if not estado.inimigos_derrotados:
            revides = motor.rodada_dos_inimigos(estado, None)
            for _, atingido in revides:
                await db.definir_hp(
                    self.bot.db, run["id"], atingido.user_id, atingido.hp_atual
                )
                await db.definir_thp(
                    self.bot.db, run["id"], atingido.user_id, atingido.thp
                )
            await self._reacoes_do_revide(run, estado, revides)

        log = (estado.rodada, golpes, revides)

        if estado.inimigos_derrotados:
            await self._atualizar_painel(
                run, sala, estado, len(ataques), rodada_anterior=log, encerrado=True
            )
            await self._apos_combate_vencido(run, sala, estado)
            return

        if estado.grupo_caido:
            await self._atualizar_painel(
                run, sala, estado, len(ataques), rodada_anterior=log, encerrado=True
            )
            await self._encerrar_run(run, "fracasso")
            incursao = self._incursao_da_run(run)
            # Mesmo derrotado, o grupo levou a run ate o fim: a participacao conta.
            await self._creditar(
                run, config.PONTOS_PARTICIPACAO, "Participação na incursão", "participacao"
            )
            lancamentos, total = await self._balanco(run)
            await canal.send(embed=E.run_fracassada(incursao, estado, lancamentos, total))
            return

        # Proxima rodada no mesmo painel, com o log da que acabou.
        estado.rodada += 1
        await db.atualizar_rodada(self.bot.db, run["id"], self._passo(run), estado.rodada)
        await self._virar_efeitos(run, estado)
        await self._atualizar_painel(run, sala, estado, 0, rodada_anterior=log)

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

        canal = await self._canal(run)
        if sala.id == incursao.objetivo.id:
            await self._encerrar_run(run, "sucesso")
            await self._creditar(
                run, config.PONTOS_PARTICIPACAO, "Participação na incursão", "participacao"
            )
            await self._creditar(
                run, incursao.pontos_conclusao, "Objetivo cumprido", "conclusao"
            )
            if canal:
                # Desfecho num embed so: vitoria, como o grupo saiu, MEs e pontos.
                lancamentos, total = await self._balanco(run)
                await canal.send(
                    embed=E.run_concluida(
                        incursao, await self._membros(run), estado, lancamentos, total
                    )
                )
                if incursao.lore_final:
                    await canal.send(embed=E.lore_fecho(incursao))
            return

        if canal and estado is not None:
            await canal.send(embed=E.combate_vencido(sala, estado))

        passo = run["linha_atual"]
        if passo < incursao.passos:
            await self._abrir_votacao(await db.buscar_run(self.bot.db, run["id"]), passo + 1)
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
        sala = self._sala(incursao, sala_id)
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
            self._passo(run),
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

        registros = await db.testes_da_sala(self.bot.db, run_id, self._passo(run))
        total = len(await db.participantes(self.bot.db, run_id))
        resolucao = _resolucao(sala, registros, total)

        if resolucao.encerrada:
            await self._concluir_sala(run, sala, resolucao)
        else:
            embed, _ = E.sala_aberta(
                sala, run["linha_atual"], len(registros), total, incursao.passos
            )
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
                    run, sala.pontos_organizacao, f"Sala superada: {sala.nome}", f"sala:{self._passo(run)}:{sala.id}"
                )

        incursao = self._incursao_da_run(run)
        passo = run["linha_atual"]
        if incursao and passo < incursao.passos:
            await self._abrir_votacao(run, passo + 1)
        else:
            await self._chegar_ao_objetivo(run)

    async def _chegar_ao_objetivo(self, run: dict[str, Any]) -> None:
        incursao = self._incursao_da_run(run)
        canal = await self._canal(run)
        if not (incursao and canal):
            return

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
        sala = self._sala(incursao, run["sala_atual"])
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
                self.bot.db, run["id"], self._passo(run), estado.rodada
            )
            embed, arquivo = E.combate(
                sala,
                estado,
                len(ataques),
                e_objetivo=sala.id == incursao.objetivo.id,
            )
            await interaction.response.send_message(
                embed=embed,
                view=ViewCombate(self, run["id"], sala.id),
                file=arquivo or discord.utils.MISSING,
            )
            mensagem = await interaction.original_response()
            await db.atualizar_run(self.bot.db, run["id"], mensagem_id=mensagem.id)
            return

        registros = await db.testes_da_sala(self.bot.db, run["id"], self._passo(run))
        total = len(await db.participantes(self.bot.db, run["id"]))
        embed, arquivo = E.sala_aberta(
            sala, run["linha_atual"], len(registros), total, incursao.passos
        )
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
        sala = self._sala(incursao, run["sala_atual"])
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
        opcoes = await self._opcoes(run, run["linha_atual"])
        if opcao > len(opcoes):
            await interaction.response.send_message(
                f"Esta votação tem {len(opcoes)} opção(ões).", ephemeral=True
            )
            return
        await self.votar(interaction, run["id"], run["linha_atual"], opcoes[opcao - 1].id)

    @grupo.command(
        name="habilidade", description="Usa uma habilidade ativa do seu personagem"
    )
    async def habilidade_comando(self, interaction: discord.Interaction) -> None:
        run = await self._run_do_contexto(interaction)
        if not run:
            return
        if run["status"] not in ("em_sala", "objetivo") or not run["sala_atual"]:
            await interaction.response.send_message(
                "Só dentro de uma sala.", ephemeral=True
            )
            return
        await self.abrir_habilidades(interaction, run["id"], run["sala_atual"])

    @grupo.command(
        name="atacar", description="Ataca o primeiro inimigo de pé (mesmo efeito do botão)"
    )
    async def atacar_comando(self, interaction: discord.Interaction) -> None:
        run = await self._run_do_contexto(interaction)
        if not run:
            return
        if run["status"] not in ("em_sala", "objetivo") or not run["sala_atual"]:
            await interaction.response.send_message("Não há combate aberto agora.", ephemeral=True)
            return
        incursao = self._incursao_da_run(run)
        sala = self._sala(incursao, run["sala_atual"])
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
        sala = self._sala(incursao, run["sala_atual"])
        registros = (
            await db.testes_da_sala(self.bot.db, run["id"], self._passo(run)) if sala else []
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
