"""A votação do caminho: as salas que aparecem em cada passo, e o voto do grupo.

Quantas opções o grupo vê, quais são (sorteadas do banco da Organização, a
mesma escolha depois de um restart), o voto de cada um, e o fecho quando a
maioria decide.
"""


from __future__ import annotations

from typing import Any

import discord

from ... import database as db, embeds as E, incursoes, motor
from ...incursoes import Sala, salas_sorteaveis
from .views import ViewVotacao


def maioria_de(total: int) -> int:
    """Quantos votos fecham a votacao: mais da metade do grupo."""
    return total // 2 + 1


class Votacao:
    """As opções de cada passo e o voto do grupo."""

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
        # `salas_sorteaveis` tira o Descanso: ele deixou de ser sorteado e
        # virou parada fixa. Depois o filtro da incursao corta por tema ou por
        # lista — vazio, ele devolve o banco inteiro, que e o que toda
        # incursao escrita antes do filtro faz.
        #
        # A conferencia cruzada (`conferir_filtro`) ja barrou, na validacao, o
        # filtro que deixa sala de menos. Aqui nao ha rede: se o pool acabar,
        # `sortear_passo` levanta, e e por isso que a conferencia existe.
        sorteaveis = incursao.filtro.aplicar(salas_sorteaveis(banco))
        opcoes = motor.sortear_passo(sorteaveis, visitadas)
        await db.gravar_opcoes(self.bot.db, run["id"], passo, opcoes)
        return opcoes

    async def _abrir_votacao(self, run: dict[str, Any], linha: int) -> None:
        """Abre a parada `linha`: a votação das salas, ou o descanso dela.

        Descanso deixou de ser sorteado. Ele era sala do banco como as outras,
        então um grupo atravessava uma Longa inteira sem nenhum e outro pegava
        dois — e o que a sala do caminho cobra é HP, que não volta entre salas.
        Agora ele é parada FIXA, pelo tamanho da incursão
        (`incursoes.DESCANSOS_DO_CAMINHO`), e parada a mais, não sala a menos.

        O normal nem passa por votação: ele é sempre o mesmo, e escolher entre
        três cópias da mesma coisa não é escolha. O duro é votado, porque ali
        há o que decidir.
        """
        incursao = self._incursao_da_run(run)
        canal = await self._canal(run)
        if not (incursao and canal):
            return
        # A sala que o grupo acabou de atravessar sai do canal. No primeiro
        # passo nao ha sala anterior: o que esta la e o recrutamento, que fica.
        if linha > 1:
            await self._apagar_passo_anterior(run)

        descanso = incursao.descanso_da_parada(linha)
        if descanso == incursoes.DESCANSO_NORMAL:
            await db.atualizar_run(
                self.bot.db, run["id"], status="escolhendo", linha_atual=linha,
                sala_atual=None, votacao_expira_em=None,
            )
            atual = await db.buscar_run(self.bot.db, run["id"])
            sala = self._sala_de_descanso(incursao)
            if sala is None:
                await canal.send(
                    "O banco desta Organização não tem sala de Descanso, e o "
                    "caminho pede uma aqui. O grupo segue sem descansar."
                )
                await self._seguir_do_descanso(atual, linha)
                return
            await self._entrar_na_sala(atual, sala)
            return
        if descanso == incursoes.DESCANSO_DURO:
            await db.atualizar_run(
                self.bot.db, run["id"], status="escolhendo", linha_atual=linha,
                sala_atual=None, votacao_expira_em=None,
            )
            await self._abrir_descanso_duro(
                await db.buscar_run(self.bot.db, run["id"]), linha
            )
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
        total = len(await db.participantes_de_pe(self.bot.db, run["id"]))
        votos = await db.votos_da_linha(self.bot.db, run["id"], linha)
        view = ViewVotacao(self, run["id"], linha, opcoes)
        mensagem = await canal.send(
            f"🗳️ {await self._chamar(run)} — escolham por onde seguir.",
            embed=E.votacao(incursao, linha, opcoes, votos, total, incursao.paradas),
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
                    embed=E.votacao(incursao, linha, opcoes, votos, total, incursao.paradas),
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
