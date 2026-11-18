"""A substituição: o grupo age no lugar de quem não aparece na vez dele.

O comando `/incursao substituir` mora em `cog.py`, com os autocompletes; aqui
fica o que ele usa — o que o ausente pode fazer, a proposta, e a ação que
sai na vez dele quando a maioria concorda.
"""


from __future__ import annotations

from ... import database as db


class Substituicao:
    """O que o grupo pode fazer pelo ausente, e a ação que sai por ele."""

    @staticmethod
    def _nome_no_combate(estado, user_id: int) -> str:
        quem = estado.combatente(user_id)
        return quem.nome if quem is not None else f"<@{user_id}>"

    @staticmethod
    def _habilidades_substituiveis(personagem) -> list:
        """As habilidades que o grupo pode usar pelo ausente.

        **Poção não entra**, e é decisão de regra, não de implementação: ela
        foi comprada com o ouro daquele personagem e sai da bolsa dele para
        nunca voltar. Uso de habilidade volta no descanso.

        So entram ativas de turno: reacoes disparam pelo proprio gatilho.
        Quem confere se ainda ha uso e `gastar_uso`, na hora de resolver,
        porque entre propor e resolver passa uma votacao.
        """
        return [
            habilidade
            for _tier, habilidade in (personagem or {}).get("habilidades") or []
            if habilidade.acionavel and (habilidade.acao or {}).get("tipo") != "reacao"
        ]

    async def _contexto_da_substituicao(self, run):
        """(estado, sala, de quem é a vez) do combate aberto, ou None."""
        # `_sala_corrente`, e nao `_sala`: ela acha tambem a emboscada de
        # Mimicos, que nao existe no banco de salas e e combate como qualquer
        # outro — travar nela travaria igual.
        sala = await self._sala_corrente(run)
        if sala is None or not sala.e_combate:
            return None
        estado = await self._estado_combate(run, sala)
        if estado is None or estado.encerrado:
            return None
        return estado, sala, await self._de_quem_e_a_vez(run, estado)

    async def _resolver_substituicao(self, run, sala, estado, alvo_id: int, proposta):
        """Grava a ação como a vez do ausente e deixa a iniciativa andar."""
        passo = self._passo(run)
        habilidade = None
        if proposta["acao"] != "ataque":
            personagem = await self._personagem_na_run(run, alvo_id)
            habilidade = next(
                (
                    h for h in self._habilidades_substituiveis(personagem)
                    if h.id == proposta["acao"]
                ),
                None,
            )
            if habilidade is not None:
                aviso = await self._aviso_de_requisito(run, estado, alvo_id, habilidade)
                if aviso:
                    canal = await self._canal(run)
                    if canal:
                        await canal.send(aviso + " A vez continua aberta.")
                    return
            # O uso e gasto AQUI, e nao ao propor: entre propor e resolver passa
            # uma votacao, e proposta recusada nao pode custar o uso de ninguem.
            # Se ele acabou nesse meio-tempo, o grupo e avisado e a vez continua
            # aberta — mudar a acao por conta propria seria resolver outra coisa
            # que ninguem votou.
            if habilidade is None or not await db.gastar_uso(
                self.bot.db, run["id"], alvo_id, habilidade.chave_de_uso,
                self._chave_de_recarga(habilidade, run, passo), habilidade.vezes,
            ):
                canal = await self._canal(run)
                if canal:
                    await canal.send(
                        "A habilidade escolhida já não tem uso. A vez continua "
                        "aberta: o grupo pode propor outra coisa."
                    )
                return
        if not await db.marcar_turno(
            self.bot.db, run["id"], passo, estado.rodada, alvo_id,
            proposta["acao"], alvos=proposta["alvos"], resolvida=False,
            substituto=proposta["proposto_por"],
        ):
            # Ele agiu no intervalo: a acao dele vale, e a do grupo nao.
            if habilidade is not None:
                await db.devolver_uso(
                    self.bot.db, run["id"], alvo_id, habilidade.chave_de_uso,
                    self._chave_de_recarga(habilidade, run, passo),
                )
            return
        await self._avancar(run, sala)

    async def _acao_proposta(self, run, estado, alvo_id: int, acao, alvo):
        """Valida o par (ação, alvo) proposto. Devolve ((ação, alvos), aviso)."""
        personagem = await self._personagem_na_run(run, alvo_id)
        if acao in (None, "", "ataque"):
            alvos: list[int] = []
            if alvo:
                indices = {str(i.indice) for i in estado.inimigos_vivos}
                if alvo not in indices:
                    return None, "Esse alvo não está de pé no combate."
                alvos = [int(alvo)]
            return ("ataque", alvos), ""
        habilidade = next(
            (h for h in self._habilidades_substituiveis(personagem) if h.id == acao),
            None,
        )
        if habilidade is None:
            return None, (
                f"`{acao}` não é uma ação que o grupo possa usar por ele. "
                f"Poção não entra: ela é do ouro dele."
            )
        aviso = await self._aviso_de_requisito(run, estado, alvo_id, habilidade)
        if aviso:
            return None, aviso
        opcoes = await self._alvos_possiveis(run, habilidade, estado)
        if opcoes is None:
            return (habilidade.id, []), ""
        if not opcoes:
            return None, "Não há alvo possível para essa habilidade agora."
        validos = {valor for valor, _n, _d in opcoes}
        if alvo is None:
            return None, (
                f"**{habilidade.nome}** precisa de alvo: escolha um no campo `alvo`."
            )
        if alvo not in validos:
            return None, "Esse alvo não serve para essa habilidade."
        return (habilidade.id, [int(alvo)]), ""

    async def _texto_da_acao(self, run, estado, alvo_id: int, proposta) -> str:
        """A proposta em uma linha, para o grupo saber no que está votando."""
        if proposta["acao"] == "ataque":
            if proposta["alvos"]:
                inimigo = estado.inimigo(proposta["alvos"][0])
                return f"atacar **{inimigo.nome if inimigo else 'o alvo'}**"
            return "atacar"
        personagem = await self._personagem_na_run(run, alvo_id)
        habilidade = next(
            (
                h for h in self._habilidades_substituiveis(personagem)
                if h.id == proposta["acao"]
            ),
            None,
        )
        return f"usar **{habilidade.nome if habilidade else proposta['acao']}**"
