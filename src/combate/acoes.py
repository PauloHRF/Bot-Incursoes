"""O que o jogador escolhe: o ataque, a habilidade, a magia rápida.

São os botões do combate, menos o botão: cada um confere se quem clicou pode
agir, guarda a ação na vez dele e anda a fila. Saíram de
`src/cogs/incursao.py` sem mudar a regra, na terceira fatia da extração, e a
referência gravada (`tests/test_referencia_combate.py`) é o que confere.

**O clique continua sendo um clique.** Os botões recebem a interação do
Discord (`Clique`, em `mesa.py`), mas só leem de quem ela é e avisam que a
resposta vem depois. Toda resposta sai pelas portas que o cog implementa —
`_dizer`, o menu de alvo, o painel —, e é isso que deixa a bancada jogar com
um clique falso, pelo mesmo caminho dos botões.

A poção ficou no cog: o menu da Poção de Mana é uma view no meio da regra, e
a bancada não bebe.
"""
from __future__ import annotations

from typing import Any, Optional

from .. import database as db
from ..incursoes import Sala
from .mesa import Clique

# O que os botões usam do cog — o que não está em `src/combate`. São todas
# portas de saída: é por elas que o jogador lê o que aconteceu.
DA_MESA = {
    "_dizer": "a resposta privada de quem clicou",
    "_guardar_efemera": "marcar a resposta para sumir quando a rodada virar",
    "_pedir_alvo": "o menu de alvo, quando a habilidade precisa de um",
    "_atualizar_painel": "o painel do combate, depois da magia rápida",
    "_encerrar_combate": "o fecho, quando a magia rápida derruba o último",
}


# A recusa de quem esta no chao, nos tres caminhos de acao (ataque, habilidade,
# pocao). Dizia "fica fora do resto deste combate", de quando uma queda so se
# desfazia no descanso — hoje a cura levanta, e a vez perdida no chao volta se
# alguem levantar o personagem na mesma rodada (ver `resolver_atrasados`).
AVISO_CAIDO = (
    "Você está caído — espere alguém te levantar com uma cura. "
    "A rodada só é perdida se ninguém levantar você nela."
)


class Acoes:
    """Os botões de ação do combate, sem o Discord."""

    async def atacar(
        self,
        interaction: Clique,
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
        if estado.encerrado:
            # Um lado já caiu, e a run não andou: o fecho parou no meio. Antes
            # o clique respondia "esse inimigo já caiu — escolha outro alvo",
            # e não havia outro para escolher. `_avancar` é quem repara no fim
            # do combate, e é por ele que este clique fecha o que faltou.
            await self._avancar(run, sala, interaction)
            return

        atacante = estado.combatente(interaction.user.id)
        if atacante is None:
            await self._dizer(interaction, 
                "Você não tem ficha cadastrada. Use `/ficha registrar`.")
            return
        if atacante.caido:
            await self._dizer(interaction, AVISO_CAIDO)
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
        gasto = await self._turno_ja_resolvido(
            run_id, passo, estado.rodada, interaction.user.id
        )
        if gasto:
            await self._dizer(interaction, self._turno_gasto(gasto))
            return
        # A ação que ele tinha preparado sai da mesa para esta entrar.
        trocada = await self._trocar_acao_guardada(
            run, passo, estado.rodada, interaction.user.id
        )
        if not await db.marcar_turno(
            self.bot.db, run_id, passo, estado.rodada, interaction.user.id, "ataque",
            alvos=[alvo.indice] if alvo_indice is not None else [],
            resolvida=False,
        ):
            await self._dizer(interaction, self._turno_gasto("ataque"))
            return
        await self._avancar(run, sala, interaction, trocada)

    async def usar_habilidade(
        self,
        interaction: Clique,
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
            await self._dizer(interaction, AVISO_CAIDO)
            return
        if atacante is not None and atacante.atordoado:
            await self._dizer(interaction, 
                "Você está atordoado e perde esta rodada.")
            return

        aviso = await self._aviso_de_requisito(run, estado, interaction.user.id, habilidade)
        if aviso:
            await self._dizer(interaction, aviso)
            return

        # So a cura funciona fora do combate: o resto mexe em rodada e inimigo.
        if acao.get("tipo") != "cura" and estado is None:
            await self._dizer(interaction, 
                "Essa habilidade so vale em combate.")
            return

        # Em combate o personagem age uma vez por rodada: ou ataca, ou usa uma
        # habilidade. Reacao nao passa por aqui — dispara sozinha.
        if estado is not None:
            gasto = await self._turno_ja_resolvido(
                run_id, passo, estado.rodada, interaction.user.id
            )
            if gasto:
                await self._dizer(interaction, self._turno_gasto(gasto))
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
            await self._magia_rapida(interaction, run, sala, habilidade, alvos or [])
            return

        # Depois de o uso estar gasto, e nao antes: se os usos tivessem
        # acabado, desfazer a escolha anterior deixaria o jogador sem nenhuma.
        trocada = await self._trocar_acao_guardada(
            run, passo, estado.rodada, interaction.user.id
        )
        if not await db.marcar_turno(
            self.bot.db, run_id, passo, estado.rodada, interaction.user.id,
            habilidade.id, alvos=alvos, resolvida=False,
        ):
            await db.devolver_uso(
                self.bot.db, run_id, interaction.user.id, habilidade.chave_de_uso,
                self._chave_de_recarga(habilidade, run, passo),
            )
            await self._dizer(interaction, self._turno_gasto("ataque"))
            return
        await self._avancar(run, sala, interaction, trocada)

    async def _magia_rapida(
        self, interaction: Clique, run: dict[str, Any], sala: Sala,
        habilidade, alvos: list[int],
    ) -> None:
        """Quickened Spell: a magia sai na hora, fora da vez — mas na fila da run.

        Fora da VEZ, e nao fora da FILA. Ela resolvia sem a trava de
        `_avancar`, a partir do estado lido no começo do clique, e as magias
        de save gravam o HP de TODOS os inimigos de uma vez. Com outro jogador
        resolvendo um golpe no mesmo instante, um dos dois gravava por cima do
        outro: o dano de um deles sumia da sala, em todas as vezes que a sonda
        tentou. Dentro da trava, as duas ações se enfileiram como quaisquer
        outras.

        O estado é relido DENTRO da trava, e não reaproveitado de quem chamou:
        enquanto este clique esperava a vez dele na fila, o combate pode ter
        andado — e até acabado. Acabado, ou com quem lançou no chão, o uso
        volta: a magia não aconteceu.

        O fim do combate fica FORA da trava, pelo mesmo motivo de `_avancar`:
        vencer pode abrir o combate do objetivo, que entra de novo na trava, e
        ela não é reentrante. A magia rápida não passa por `_avancar`, e era
        por isso que matar o último inimigo com ela deixava a run sem saída —
        então ela repara no fim do combate aqui mesmo.
        """
        run_id, user_id = run["id"], interaction.user.id
        passo = self._passo(run)
        encerrar = None
        async with self._trava(run_id):
            atual = await db.buscar_run(self.bot.db, run_id)
            estado = (
                await self._estado_combate(atual, sala)
                if atual
                and atual["status"] in ("em_sala", "objetivo")
                and atual["sala_atual"] == sala.id
                else None
            )
            quem = estado.combatente(user_id) if estado else None
            recusa = None
            if estado is None or estado.encerrado:
                recusa = "O combate acabou antes da sua magia sair."
            elif quem is None or quem.caido:
                recusa = AVISO_CAIDO
            elif quem.atordoado:
                recusa = "Você está atordoado e perde esta rodada."
            if recusa:
                await db.devolver_uso(
                    self.bot.db, run_id, user_id, habilidade.chave_de_uso,
                    self._chave_de_recarga(habilidade, run, passo),
                )
                await self._dizer(interaction, recusa)
                return
            texto = await self._resolver_habilidade(
                atual, estado, user_id, habilidade, alvos
            )
            # Relido do banco, como `_avancar` faz: a magia pode ter mexido em
            # mais do que o objeto em mãos sabe.
            depois = await self._estado_combate(atual, sala)
            if depois is not None and depois.encerrado:
                if self._tomar_o_fecho_do_combate(run_id, passo):
                    encerrar = (atual, depois)
            else:
                await self._atualizar_painel(atual, sala, depois or estado)
        await self._dizer(interaction, texto)
        if encerrar:
            await self._encerrar_combate(encerrar[0], sala, encerrar[1])
