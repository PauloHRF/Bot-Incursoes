"""As salas do caminho: entrar, rolar a perícia, e o que a sala faz depois.

A sala que abre, o teste do grupo e a resolução dele, o que cada tipo de
sala dá ou cobra (armadilha, evento, tesouro, os Mímicos), quem sai da run
por exaustão, a chegada ao objetivo, e o ouro e os pontos das salas
superadas.
"""


from __future__ import annotations

import logging

from typing import Any, Optional

import discord

from ... import (
    condicoes,
    config,
    consequencias,
    database as db,
    embeds as E,
    mercado,
    motor,
)
from ...combate.mesa import emboscada_de
from ...incursoes import Sala
from ...motor import ResolucaoSala, ResultadoTeste
from .views import ViewDescanso, ViewSala

log = logging.getLogger("incursoes.run")


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


class Salas:
    """Entrar na sala, o teste, as consequências, e o que ela paga."""

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

        # Só a sala de teste cobra nome de alguém: numa sem teste isto seriam
        # duas leituras de banco para um campo que o cartão não desenha.
        faltam_rolar: list[str] = []
        if sala.tem_teste:
            _, faltam_rolar = await self._quem_rolou(run, [])
        embed, arquivo = E.sala_aberta(
            sala, run["linha_atual"], (), faltam_rolar,
            incursao.paradas if incursao else None,
            # O tier, senao o cartao mostra a CD do tier 1 e `motor.testar`
            # cobra a do tier da run: o grupo via um numero e rolava contra
            # outro.
            tier=self._tier_da_run(run),
            tema=self._tema_da_sala(run, sala),
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

    async def _pagar_as_salas(self, run: dict[str, Any]) -> int:
        """O ouro das salas que o grupo venceu, no fecho da run.

        Vai para TODOS que passaram pela run, e nao so para quem estava de
        pe no fim: quem caiu no objetivo e quem foi ejetado por Exaustao no
        meio do caminho jogaram a incursao e levam o mesmo que os outros.

        O valor sai das salas superadas e nao de quem estava em qual: e o
        grupo que atravessou, nao cada um por si. A de Combate conta por
        duas, porque e a unica que cobra HP.

        Duas salas ficam de fora da dobra. O objetivo, porque ele nao e
        escolha de ninguem: a dobra existe para a sala de Combate competir
        na votacao com a de Tesouro, e o objetivo e obrigatorio — quem paga
        por ele e o bonus de conclusao. E o Tesouro que virou emboscada de
        Mimico, que continua contando como Tesouro: a emboscada e castigo
        por falhar no bau, e nao da para pagar dobrado por ter falhado.

        Separado do fecho porque a desistencia paga isto e nao paga aquele:
        o grupo atravessou as salas, so nao terminou a incursao.
        """
        tier = self._tier_da_run(run) or 1
        ids = await db.ids_das_salas_superadas(self.bot.db, run["id"])
        superadas = len(ids)
        # A de Combate paga dobrado: é a única que cobra HP, e o HP não volta
        # entre salas. Pagando igual à de Tesouro, evitar combate era sempre
        # a melhor jogada.
        incursao = self._incursao_da_run(run)
        do_caminho = (
            (self._sala(incursao, i) for i in ids if i != incursao.objetivo.id)
            if incursao
            else ()
        )
        de_combate = sum(1 for s in do_caminho if s and s.e_combate)
        quanto = mercado.ouro_das_salas(tier, superadas, de_combate)
        motivo = f"Salas superadas ({superadas})"
        if de_combate:
            motivo = f"Salas superadas ({superadas}, {de_combate} de combate)"
        pagos = 0
        for p in await db.quem_recebe_da_run(self.bot.db, run["id"]):
            if await db.lancar_ouro(
                self.bot.db, p["id"], quanto, motivo,
                run_id=run["id"], chave="salas",
            ):
                pagos += 1
        return pagos

    async def _pagar_o_fecho(self, run: dict[str, Any]) -> int:
        """O bonus de ter CONCLUIDO a incursao. So a vitoria paga."""
        quanto = mercado.ouro_da_incursao(self._tier_da_run(run) or 1)
        pagos = 0
        for p in await db.quem_recebe_da_run(self.bot.db, run["id"]):
            if await db.lancar_ouro(
                self.bot.db, p["id"], quanto, "Incursao concluida",
                run_id=run["id"], chave="conclusao",
            ):
                pagos += 1
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

    async def rolar(self, interaction: discord.Interaction, run_id: int, sala_id: str) -> None:
        # Adiado antes de tudo: o socorro de teste (`_socorrer_o_teste`) pode
        # anunciar no CANAL antes de a rolagem responder — uma ida a rede
        # dentro dos 3 s que o Discord da para a primeira resposta. Ver `atacar`
        # para o `thinking=True`, que e o que faz o `ephemeral` valer.
        await interaction.response.defer(ephemeral=True, thinking=True)
        run = await db.buscar_run(self.bot.db, run_id)
        if not run or run["status"] != "em_sala" or run["sala_atual"] != sala_id:
            await self._dizer(interaction, "Esta sala já foi resolvida.")
            return
        # A sala pode estar FECHADA com a run ainda nela: a emboscada do
        # Mimico reusa o id e o status da sala do Tesouro, e o combate corre
        # dentro dela. Um botao antigo na tela de alguem ainda mandava a
        # rolagem, e ela reabria o fecho da sala — a votacao do passo
        # seguinte aparecia no meio do combate.
        if await db.sala_fechada(self.bot.db, run_id, self._passo(run)):
            await self._dizer(interaction,
                "Esta sala já foi resolvida."
            )
            return
        if not await db.esta_na_run(self.bot.db, run_id, interaction.user.id):
            await self._dizer(interaction, "Você não faz parte desta run.")
            return

        incursao = self._incursao_da_run(run)
        sala = await self._sala_corrente(run)
        if sala is None or sala.e_combate:
            # O baú acordou entre o clique e a chegada: não há mais teste aqui.
            await self._dizer(interaction,
                "Esta sala virou combate — não há teste para rolar."
            )
            return
        if not await db.esta_de_pe(self.bot.db, run_id, interaction.user.id):
            await self._dizer(interaction,
                "Você está caído — quem está no chão não encara a sala. Espere o Descanso."
            )
            return
        personagem = await db.personagem_da_run(self.bot.db, run_id, interaction.user.id)
        if not personagem:
            await self._dizer(interaction,
                "Não achei o personagem com que você entrou nesta run."
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
            await self._dizer(interaction,
                "Você já rolou nesta sala — cada um rola uma vez."
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
        await self._dizer(interaction,
            f"🎲 **{resultado.d20}** {resultado.modificador:+d}{socorro} = "
            f"**{resultado.total}** em {resultado.pericia} (CD {resultado.cd}) "
            f"— {veredito}."
        )

        registros = await db.testes_da_sala(self.bot.db, run_id, self._passo(run))
        total = len(await db.participantes_de_pe(self.bot.db, run_id))
        resolucao = _resolucao(sala, registros, total)

        if resolucao.encerrada:
            await self._concluir_sala(run, sala, resolucao)
        else:
            ja_rolaram, faltam_rolar = await self._quem_rolou(run, registros)
            embed, _ = E.sala_aberta(
                sala, run["linha_atual"], ja_rolaram, faltam_rolar,
                incursao.paradas, tier=self._tier_da_run(run),
                tema=self._tema_da_sala(run, sala),
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
            if await self._expulsar_estourados(run):
                return

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

        await self._seguir_do_descanso(run, run["linha_atual"])

    async def _quem_rolou(
        self, run: dict[str, Any], registros: list[dict[str, Any]]
    ) -> tuple[list[str], list[str]]:
        """Quem ja rolou nesta sala e quem ainda falta, por nome de personagem.

        Quem caiu depois de rolar continua na primeira lista e sai da segunda:
        a sala fecha quando os de pe rolarem, e e essa a conta que o cartao
        mostra.
        """
        ja = {r["user_id"] for r in registros}
        nomes = {
            p["user_id"]: p["nome"]
            for p in await db.personagens_da_run(self.bot.db, run["id"])
        }
        faltam = [
            nomes.get(user_id, f"<@{user_id}>")
            for user_id in await db.participantes_de_pe(self.bot.db, run["id"])
            if user_id not in ja
        ]
        return [r["personagem"] for r in registros], faltam

    async def _consequencias_da_sala(
        self, run: dict[str, Any], sala: Sala, resolucao: ResolucaoSala
    ) -> consequencias.Desfecho:
        """Aplica o que a sala faz com o grupo e devolve o texto do embed.

        O que cada tipo faz está em `src/consequencias.py`; aqui só persiste.

        **A sala é do grupo, nos dois sentidos.** Vencida, não castiga
        ninguém — nem quem rolou mal. Perdida, castiga todos que a
        encararam — inclusive quem rolou bem. O dado de cada um decide o
        PROGRESSO da sala; o desfecho dela é do grupo.

        As duas metades vieram do mesmo relato da mesa: punir quem tirou 3
        numa sala que o grupo venceu, e deixar limpo quem tirou 18 numa sala
        que o grupo perdeu, apontavam o dado em vez da decisão.
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
            # `acordou_mimico` hoje responde SEMPRE que sim, e a chamada fica
            # para a decisao continuar num lugar so: voltar a sortear e mexer
            # na CHANCE_DE_MIMICO, e nao reescrever esta sala.
            #
            # O sorteio saiu porque falhar num Tesouro era a unica falha do
            # caminho que podia nao custar nada: em dois terços das vezes o
            # grupo "saia sem nada, mas inteiro" — e sair sem nada nao e
            # castigo quando o tesouro so existia se voce passasse.
            if consequencias.acordou_mimico():
                desfecho.mimicos = True
                desfecho.linhas.append(
                    "O baú não era um baú. **Mímicos** se descolam da parede."
                )
            else:
                desfecho.linhas.append("O grupo sai sem nada — mas sai inteiro.")
        return desfecho

    @staticmethod
    def _quem_encarou(resolucao: ResolucaoSala) -> list[ResultadoTeste]:
        """Quem enfrentou a sala: todos que rolaram, passando ou falhando.

        Sala perdida cobra do GRUPO, e não de quem tirou o dado mais baixo.
        A outra metade da regra está em `_consequencias_da_sala`: sala
        vencida não cobra de ninguém. Vencer protege todos, perder custa a
        todos — e o resultado da sala deixa de depender de quem rolou mal.

        É quem ROLOU, e não quem está na run: uma sala só se perde quando
        todos os de pé rolaram (é a única forma de uma sala perdida fechar),
        e quem está caído não encarou nada. Cobrar de quem não pôde rolar
        seria cobrar duas vezes pela mesma queda.
        """
        return list(resolucao.resultados)

    async def _castigo_de_armadilha(
        self,
        run: dict[str, Any],
        sala: Sala,
        resolucao: ResolucaoSala,
        desfecho: consequencias.Desfecho,
    ) -> None:
        """A armadilha que o grupo não desarmou: -20% do HP e um debuff.

        Cai em todos que encararam a sala, e não só em quem falhou a própria
        rolagem — ver `_quem_encarou`.

        **Um sorteio só para o grupo inteiro**: é uma armadilha que
        disparou, não cinco. Cinco debuffs diferentes do mesmo alçapão não
        contariam a mesma história, e a linha do desfecho fica legível.

        O dano continua por cabeça, porque é porcentagem: 20% do máximo de
        cada um, e quem tem mais HP perde mais.
        """
        combatentes = {c.user_id: c for c in await self._combatentes(run)}
        encararam = self._quem_encarou(resolucao)
        if not encararam:
            return
        debuff = consequencias.debuff_da_armadilha()
        hps: dict[int, int] = {}
        nomes: list[str] = []
        caiu = consequencias.CondicaoAplicada(debuff)
        for quem in encararam:
            combatente = combatentes.get(quem.user_id)
            if combatente is None:
                continue
            dano = consequencias.dano_da_armadilha(combatente.hp_max)
            combatente.hp_atual = max(0, combatente.hp_atual - dano)
            hps[quem.user_id] = combatente.hp_atual
            caiu.stacks[quem.personagem] = await db.aplicar_condicao(
                self.bot.db, run["id"], quem.user_id, debuff
            )
            nomes.append(f"**{quem.personagem}** (-{dano})")
        if hps:
            await db.definir_hp_varios(self.bot.db, run["id"], hps)
        if nomes:
            desfecho.linhas.append(
                "A armadilha pega o grupo: " + ", ".join(nomes) + "."
            )
            desfecho.condicao = caiu

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
        ganho = consequencias.CondicaoAplicada(premio)
        for c in combatentes:
            ganho.stacks[c.nome] = await db.aplicar_condicao(
                self.bot.db, run["id"], c.user_id, premio
            )
        desfecho.linhas.append("✨ O evento corre bem, e o grupo sai melhor dele.")
        desfecho.condicao = ganho

    async def _castigo_de_evento(
        self,
        run: dict[str, Any],
        resolucao: ResolucaoSala,
        desfecho: consequencias.Desfecho,
    ) -> None:
        """O Evento que deu errado: um debuff de Evento, ou Exaustão.

        Cai em todos que encararam a sala, e num sorteio só: o Evento é um
        acontecimento da sala, e aconteceu para o grupo inteiro.
        """
        encararam = self._quem_encarou(resolucao)
        if not encararam:
            return
        castigo = consequencias.castigo_do_evento()
        unidades = consequencias.unidades_do_castigo(castigo)
        caiu = consequencias.CondicaoAplicada(castigo)
        for quem in encararam:
            caiu.stacks[quem.personagem] = await db.aplicar_condicao(
                self.bot.db, run["id"], quem.user_id, castigo, unidades
            )
        desfecho.linhas.append("O evento sai pela culatra para o grupo.")
        desfecho.condicao = caiu

    async def _expulsar_estourados(self, run: dict[str, Any]) -> bool:
        """Quem bateu no teto de uma condição sai da incursão. True se a run acabou.

        O teto é por condição, como na planilha: Deterioração em 10 (que é
        -100% do HP máximo) e Exaustão em 5. As outras não tiram ninguém.
        Esvaziando o grupo, a run fracassa.

        **Quem chama tem de parar quando ela devolve True.** Os três que
        chamam (o fecho do combate, o da sala de teste e o da vigília)
        seguiam para a parada seguinte depois dela — e `_abrir_votacao` não
        olha o status: a run marcada como fracasso voltava a `escolhendo`,
        sem ninguém dentro, com um cartão de votação em que ninguém podia
        votar. O canal ficava preso nela, recusando run nova, até um admin
        rodar `/incursao encerrar`.
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
                # A saida ja foi gravada acima. Recusado, este aviso nao pode
                # abortar o laco: os outros estourados ficariam no grupo.
                await self._avisar_no_canal(
                    canal,
                    f"<@{user_id}> — **{nome}** não consegue seguir: {motivos} chegou "
                    f"ao limite. O personagem sai da incursão.",
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
                await self._avisar_no_canal(
                    canal,
                    "A incursão termina aqui: não sobrou ninguém em condições de "
                    "seguir.",
                )
            return True
        return False

    async def _soltar_mimicos(self, run: dict[str, Any], sala: Sala) -> None:
        """A falha no Tesouro acordou o baú: a sala vira um combate.

        Os números dos Mímicos ficam gravados em `run_inimigos` por
        `_abrir_combate`, então o combate se remonta sozinho depois de um
        restart — a emboscada não precisa existir no banco de salas.
        """
        emboscada = emboscada_de(sala, self._tier_da_run(run))
        if not emboscada.monstros:
            # Sem Mímico no bestiário não há emboscada: segue o fluxo normal.
            log.warning("Mímico não encontrado no bestiário; emboscada cancelada")
            incursao = self._incursao_da_run(run)
            passo = run["linha_atual"]
            if incursao and passo < incursao.paradas:
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
