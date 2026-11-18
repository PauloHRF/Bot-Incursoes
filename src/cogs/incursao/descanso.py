"""O descanso: as paradas fixas do caminho, e o que cada uma cura ou troca.

O descanso normal, que recupera; o descanso duro, em que o grupo vota uma
troca; e a limpeza de condição, que cada um escolhe para si.
"""


from __future__ import annotations

import random

from typing import Any, Optional

import discord

from ... import (
    condicoes,
    consequencias,
    database as db,
    embeds as E,
    incursoes,
    mercado,
    motor,
)
from ...incursoes import Incursao, Sala
from .views import ViewDescanso, ViewTrocaDoDescanso
from .votacao import maioria_de


class Descanso:
    """As paradas de descanso, a troca do descanso duro e a limpeza."""

    async def _seguir_do_descanso(self, run: dict[str, Any], parada: int) -> None:
        """Fecha a parada e abre a seguinte — ou o objetivo, se era a última.

        Conta PARADAS e não salas: com o descanso virando parada a mais, a
        Média tem seis e a Longa nove. Estava escrito em dois lugares com
        `passos` no lugar de `paradas`, e os dois passariam direto para o
        objetivo no meio do caminho.
        """
        incursao = self._incursao_da_run(run)
        if not incursao:
            return
        if parada < incursao.paradas:
            await self._abrir_votacao(run, parada + 1)
        else:
            await self._chegar_ao_objetivo(run)

    def _sala_de_descanso(self, incursao: Incursao) -> Optional[Sala]:
        """A sala de Descanso do banco da Organização, que o caminho usa.

        O descanso fixo reusa a sala que o banco já tem — a Cela do Coveiro da
        Guilda, a Adega Falsa das Sombras — em vez de inventar uma genérica:
        a ficção é de cada Organização, e ela já estava escrita.
        """
        banco = self.bancos.get(incursao.organizacao)
        if not banco:
            return None
        return next((s for s in banco.salas if s.tipo == "Descanso"), None)

    def _trocas_da_parada(self, run_id: int, parada: int) -> list:
        """As três trocas desta parada — sempre as mesmas três.

        Derivadas da semente `run:parada` em vez de gravadas: assim o mapa da
        run continua sendo o mapa das SALAS, e redesenhar o cartão, ou reabri-lo
        depois de um restart, devolve a mesma mesa.
        """
        return consequencias.trocas_oferecidas(
            rng=random.Random(f"{run_id}:{parada}")
        )

    async def _abrir_descanso_duro(self, run: dict[str, Any], parada: int) -> None:
        """O descanso da Longa depois da sexta sala: três trocas, uma escolha.

        Reusa o caminho do voto de sala: o voto fica em `run_votos`, e a
        maioria fecha. O que muda é o que o id guardado significa — e por isso
        não há tabela nova nem um segundo jeito de votar.

        A mesa não é gravada em `run_mapa`, como as salas são: ela sai da
        semente (`_trocas_da_parada`), e é de lá que o restart a remonta.
        """
        incursao = self._incursao_da_run(run)
        canal = await self._canal(run)
        if not (incursao and canal):
            return
        sala = incursoes.sala_do_descanso_duro()
        trocas = self._trocas_da_parada(run["id"], parada)
        if not trocas:
            await canal.send(
                "Não achei as trocas deste descanso. O grupo segue sem descansar."
            )
            await self._seguir_do_descanso(run, parada)
            return

        total = len(await db.participantes_de_pe(self.bot.db, run["id"]))
        votos = await db.votos_da_linha(self.bot.db, run["id"], parada)
        mensagem = await canal.send(
            f"🌙 {await self._chamar(run)} — falta uma sala. O que o grupo "
            f"gasta para chegar nela?",
            embed=E.descanso_duro(
                sala, trocas, votos, total, parada, incursao.paradas
            ),
            view=ViewTrocaDoDescanso(self, run["id"], parada, trocas),
        )
        # A run fica em 'escolhendo', como numa votacao de sala: e esse o
        # estado que `tomar_a_sala` exige para fechar a parada uma unica vez.
        await db.atualizar_run(
            self.bot.db, run["id"], status="escolhendo", sala_atual=None,
            linha_atual=parada, mensagem_id=mensagem.id,
        )

    async def votar_troca(
        self, interaction: discord.Interaction, run_id: int, parada: int, troca_id: str
    ) -> None:
        """Um voto na troca do descanso duro. A maioria fecha, como na sala."""
        run = await db.buscar_run(self.bot.db, run_id)
        if not run or run["linha_atual"] != parada or run["status"] != "escolhendo":
            await interaction.response.send_message(
                "Este descanso já passou.", ephemeral=True
            )
            return
        if not await db.esta_na_run(self.bot.db, run_id, interaction.user.id):
            await interaction.response.send_message(
                "Você não faz parte desta run.", ephemeral=True
            )
            return
        if not await db.esta_de_pe(self.bot.db, run_id, interaction.user.id):
            await interaction.response.send_message(
                "Você está caído — quem está no chão não decide o descanso.",
                ephemeral=True,
            )
            return
        oferecidas = {t.id for t in self._trocas_da_parada(run_id, parada)}
        troca = consequencias.TROCA_POR_ID.get(troca_id)
        if troca is None or troca_id not in oferecidas:
            await interaction.response.send_message(
                "Essa troca não está na mesa deste descanso.", ephemeral=True
            )
            return

        await db.registrar_voto(
            self.bot.db, run_id, parada, interaction.user.id, troca_id
        )
        await interaction.response.send_message(
            f"Voto em **{troca.nome}** registrado.", ephemeral=True
        )
        self._guardar_efemera(run_id, interaction)

        votos = await db.votos_da_linha(self.bot.db, run_id, parada)
        total = len(await db.participantes_de_pe(self.bot.db, run_id))
        contagem: dict[str, int] = {}
        for escolhida in votos.values():
            contagem[escolhida] = contagem.get(escolhida, 0) + 1
        vencedora, quantos = max(
            contagem.items(), key=lambda par: par[1], default=("", 0)
        )
        if quantos < maioria_de(total):
            await self._redesenhar_descanso_duro(run, parada, votos, total)
            return
        # So UM clique fecha a parada: `tomar_a_sala` e o mesmo atomico que a
        # votacao de sala usa, e sem ele cinco cliques simultaneos aplicariam
        # a troca cinco vezes.
        if not await db.tomar_a_sala(
            self.bot.db, run_id, parada, incursoes.ID_DO_DESCANSO_DURO
        ):
            return
        await self._resolver_descanso_duro(
            await db.buscar_run(self.bot.db, run_id), parada,
            consequencias.TROCA_POR_ID[vencedora],
        )

    async def _redesenhar_descanso_duro(
        self, run: dict[str, Any], parada: int, votos: dict, total: int
    ) -> None:
        """Reescreve o cartao com a contagem de votos de agora."""
        incursao = self._incursao_da_run(run)
        canal = await self._canal(run)
        if not (incursao and canal and run.get("mensagem_id")):
            return
        trocas = self._trocas_da_parada(run["id"], parada)
        try:
            mensagem = await canal.fetch_message(run["mensagem_id"])
            await mensagem.edit(
                embed=E.descanso_duro(
                    incursoes.sala_do_descanso_duro(), trocas, votos, total,
                    parada, incursao.paradas,
                ),
                view=ViewTrocaDoDescanso(self, run["id"], parada, trocas),
            )
        except discord.HTTPException:
            pass

    async def _resolver_descanso_duro(
        self, run: dict[str, Any], parada: int, troca
    ) -> None:
        """Aplica a troca escolhida no grupo inteiro, e segue o caminho."""
        canal = await self._canal(run)
        tier = max(1, self._tier_da_run(run) or 1)
        await db.registrar_visita(
            self.bot.db, run["id"], parada, incursoes.ID_DO_DESCANSO_DURO
        )
        await self._limpar_botoes(run)
        await self._limpar_efemeras(run["id"])
        combatentes = await self._combatentes(run)
        linhas: list[str] = []

        hps: dict[int, int] = {}
        thps: dict[int, int] = {}
        for c in combatentes:
            nota = []
            if troca.cura_pct:
                # `curar_quanto` ja levanta quem caiu e ja aplica a Debilidade
                # e o Vigor: a cura da vigilia e cura como qualquer outra, e
                # nao o valor fixado que o descanso normal usa nos caidos.
                quanto = motor.curar_quanto(
                    c, max(1, (c.hp_max * troca.cura_pct) // 100)
                )
                if quanto:
                    hps[c.user_id] = c.hp_atual
                    nota.append(f"+{quanto} de HP")
            if troca.thp_pct:
                ganho = max(1, (c.hp_max * troca.thp_pct) // 100)
                motor.ganhar_thp(c, ganho)
                thps[c.user_id] = c.thp
                nota.append(f"+{ganho} de vida temporária")
            if nota:
                linhas.append(f"• **{c.nome}** {', '.join(nota)}")
        if hps:
            await db.definir_hp_varios(self.bot.db, run["id"], hps)
        if thps:
            await db.definir_thp_varios(self.bot.db, run["id"], thps)

        if troca.exaustao:
            for c in combatentes:
                for _ in range(troca.exaustao):
                    await db.aplicar_condicao(
                        self.bot.db, run["id"], c.user_id, condicoes.EXAUSTAO
                    )
            linhas.append(
                f"🫩 Todos levam **{troca.exaustao} ponto(s) de Exaustão** — "
                f"ela não decai com o combate, e só o descanso normal a tira."
            )
        if troca.limpa_debuffs:
            carregadas = await db.condicoes_da_run(self.bot.db, run["id"])
            limpos = 0
            for user_id, minhas in carregadas.items():
                for cid in consequencias.a_limpar(minhas, (condicoes.DEBUFF,)):
                    while await db.reduzir_condicao(
                        self.bot.db, run["id"], user_id, cid
                    ):
                        pass
                    limpos += 1
            linhas.append(
                f"✨ **{limpos} debuff(s)** saem do grupo."
                if limpos
                else "✨ Não havia debuff nenhum para lavar."
            )
        if troca.ouro_de_sala:
            quanto = mercado.ouro_da_sala(tier)
            pagos = 0
            for p in await db.quem_recebe_da_run(self.bot.db, run["id"]):
                if await db.lancar_ouro(
                    self.bot.db, p["id"], quanto, "Revirou o lugar",
                    run_id=run["id"], chave=f"troca:{parada}",
                ):
                    pagos += 1
            linhas.append(f"💰 **+{quanto}** de ouro para {pagos} personagem(ns).")
        if troca.buff:
            # Sem debuff nem machucado declarados, `premio_do_evento` sorteia
            # so entre os 12 buffs — que e o que a troca promete.
            premio = consequencias.premio_do_evento()
            ganho = consequencias.CondicaoAplicada(premio)
            for c in combatentes:
                ganho.stacks[c.nome] = await db.aplicar_condicao(
                    self.bot.db, run["id"], c.user_id, premio
                )
            nome, valor = E.painel_da_condicao(ganho)
            linhas.append(f"**{nome}**")
            linhas.append(valor)

        # O descanso duro tambem recarrega as habilidades por descanso: ele e
        # descanso, por mais caro que seja.
        # NAO e "sala superada": `_pagar_as_salas` paga por superada, e
        # descansar nao e vencer nada — o normal tambem nao e marcado.
        await db.contar_descanso(self.bot.db, run["id"])
        if canal:
            await canal.send(embed=E.descanso_duro_feito(troca, linhas))
        if await self._expulsar_estourados(await db.buscar_run(self.bot.db, run["id"])):
            return
        await self._seguir_do_descanso(
            await db.buscar_run(self.bot.db, run["id"]), parada
        )

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
            for chave, tipos in Descanso.TIPOS_DE_LIMPEZA.items()
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
        cid = None
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

        # A escolha e reivindicada ANTES de valer, e nao depois. A conferencia
        # la em cima le e decide com `await` no meio: os dois botoes clicados
        # juntos passavam os dois por ela, e o mesmo personagem saia do
        # descanso sem um debuff E sem um ponto de Exaustao — a regra e uma
        # coisa por personagem. O INSERT de `marcar_descanso` e quem decide:
        # quem leva o True limpa, o outro le que ja escolheu.
        #
        # Vem depois da recusa de cima de proposito, para a categoria que ele
        # nao carrega continuar nao gastando a escolha.
        #
        # A ordem escolhe um lado, como em `db.resolver_turno`: se o processo
        # morrer entre a marca e a limpeza, a escolha se perde em vez de valer
        # duas vezes.
        if not await db.marcar_descanso(self.bot.db, run_id, passo, user_id):
            await interaction.response.send_message(
                "Você já escolheu neste descanso — é uma por personagem.",
                ephemeral=True,
            )
            return

        if cid is not None:
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
