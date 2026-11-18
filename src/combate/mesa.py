"""A mesa: o que o combate consulta para andar.

Terceira fatia da extração das regras de `src/cogs/incursao.py`, saída de lá
sem mudar uma linha. É o que os outros módulos de `src/combate` perguntam o
tempo todo e que não é regra de ninguém em particular:

- **onde a run está** — a incursão, a sala do passo (e a emboscada, quando o
  Tesouro acorda os Mímicos), o passo, o tier, o tema;
- **quem está jogando** — a ficha montada na run, com as passivas;
- **o que ele pode fazer agora** — o menu de habilidades, o requisito de
  cada uma, os alvos que o seletor oferece, quando um uso volta;
- **a vez dele** — se ela já foi gasta, e a troca da ação guardada;
- **a fila** — a trava por run, o log da rodada e a reivindicação do fecho.

Ela guarda estado em memória — a trava, o log, os fechos já tomados — e as
incursões carregadas, e é ela quem cria esse estado, no `__init__`. Quem a
herda (o cog, a bancada) chama esse `__init__` e enche `incursoes` e
`bancos`: a mesa não sabe de onde as incursões vêm.
"""
from __future__ import annotations

import asyncio
import random
from typing import Any, Optional, Protocol

from .. import (
    bestiario,
    classes as cl,
    consequencias,
    consumiveis,
    database as db,
    incursoes,
    motor,
)
from ..incursoes import BancoDeSalas, Incursao, Sala, monstros_de_criatura

# A mesa não pede nada ao cog: o estado que ela usa, ela mesma cria.
DA_MESA: dict[str, str] = {}


def emboscada_de(sala: Sala, tier: Optional[int] = None) -> Sala:
    """O Tesouro que virou combate, quando a falha acorda os Mímicos.

    Função pura e determinística de propósito: a mesma sala e o mesmo tier
    sempre devolvem a mesma emboscada, então remontá-la depois de um restart
    dá no mesmo. Vem com `monstros` vazio se o bestiário não tiver Mímico.

    Quem entra sai de `consequencias.A_EMBOSCADA`, que tem uma linha medida
    por tier — o Mímico é CR 2 e sozinho não pesa num grupo de tier alto.
    """
    do_livro = bestiario.buscar(consequencias.NOME_DO_MIMICO)
    monstros = []
    if do_livro is not None:
        monstros = [
            m
            for nome, quantas in consequencias.emboscada_do_tier(tier)
            for m in monstros_de_criatura(
                {"nome": nome, "quantidade": quantas}, f"{sala.id}: emboscada"
            )
        ]
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


class Clique(Protocol):
    """Quem clicou: a interação do Discord, como o combate a vê.

    O combate só lê DE QUEM é o clique (`user.id`) e avisa que a resposta vem
    depois (`response.defer`). Responder é com o cog: passa pelas portas que
    ele implementa (`_dizer`, `_responder_no_clique`), e é isso que deixa a
    bancada jogar com um clique falso que só tem essas duas coisas.
    """

    user: Any
    response: Any


class Mesa:
    """Onde a run está, quem joga, o que ele pode fazer, e a fila da run."""

    def __init__(self, bot: Any) -> None:
        # `bot.db` é a conexão do banco; o resto do bot o combate não usa.
        self.bot = bot
        self.incursoes: dict[str, Incursao] = {}
        self.bancos: dict[str, BancoDeSalas] = {}
        # O log da rodada no painel, e a fila de cada run: um restart perde o
        # log (o combate continua do banco) e recria as travas.
        self._registros: dict[int, dict[str, Any]] = {}
        self._travas: dict[int, asyncio.Lock] = {}
        self._encerrados: set[tuple[int, int]] = set()

    def _incursao_da_run(self, run: dict[str, Any]) -> Optional[Incursao]:
        return self.incursoes.get(run["incursao_id"])

    def _sala(self, incursao: Incursao, sala_id: Optional[str]) -> Optional[Sala]:
        """A sala pelo id: a final da incursão ou uma do banco da Organização."""
        if not sala_id:
            return None
        if sala_id == incursao.objetivo.id:
            return incursao.objetivo
        # A parada do descanso duro nao vem de banco: ela e a mesma em toda
        # Organizacao, porque o que decide ali sao as TROCAS.
        if sala_id == incursoes.ID_DO_DESCANSO_DURO:
            return incursoes.sala_do_descanso_duro()
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
            return emboscada_de(sala, self._tier_da_run(run))
        return sala

    def _passo(self, run: dict[str, Any]) -> int:
        """O passo atual do caminho. O objetivo fica um depois do último."""
        incursao = self._incursao_da_run(run)
        if run["status"] == "objetivo" and incursao:
            return incursao.paradas + 1
        return run["linha_atual"]

    def _tier_da_run(self, run: dict[str, Any]) -> Optional[int]:
        """O tier da incursão — é ele que dimensiona debuff, buff e maldição."""
        incursao = self._incursao_da_run(run)
        return incursao.tier if incursao else None

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

    def _tomar_o_fecho_do_combate(self, run_id: int, passo: int) -> bool:
        """Reivindica o direito de encerrar ESTE combate. Uma vez por combate.

        **Dois caminhos** chegam ao fim de um combate: a iniciativa, em
        `_avancar`, e a magia que resolve na hora — o Quickened Spell, que
        sai fora da vez e por isso nao passa por lá. Os dois podem chegar no
        mesmo instante, e `_encerrar_combate` paga o ouro da sala e abre a
        parada seguinte: rodar duas vezes pagaria duas vezes.

        **E sincrono de propósito.** Entre o `in` e o `add` nao existe
        `await`, entao o loop de eventos nao tem onde entrar e a reivindicacao
        e indivisivel sem trava nenhuma. Um `async def` aqui abriria
        exatamente o buraco que ele existe para fechar.
        """
        if (run_id, passo) in self._encerrados:
            return False
        self._encerrados.add((run_id, passo))
        return True

    def _turno_gasto(self, acao: str) -> str:
        """O aviso de quem ja agiu, dizendo com o que gastou o turno."""
        if acao == "ataque":
            return "Você já atacou nesta rodada — é um ataque **ou** uma habilidade."
        pocao = consumiveis.item(acao)
        if pocao is not None:
            return (
                f"Você já bebeu **{pocao.nome}** nesta rodada — beber é a ação "
                f"do turno. Só a Poção da Aceleração não custa a ação."
            )
        habilidade = cl.POR_ID.get(acao)
        nome = habilidade.nome if habilidade else acao
        return (
            f"Você já usou **{nome}** nesta rodada — é uma habilidade **ou** um ataque."
        )

    @staticmethod
    def _nome_da_acao(acao: str) -> str:
        """Como a ação guardada se chama numa frase: "o ataque", "**Fireball**"."""
        if acao == "ataque":
            return "o ataque"
        pocao = consumiveis.item(acao)
        if pocao is not None:
            return f"**{pocao.nome}**"
        habilidade = cl.POR_ID.get(acao)
        return f"**{habilidade.nome}**" if habilidade else f"**{acao}**"

    async def _turno_ja_resolvido(
        self, run_id: int, passo: int, rodada: int, user_id: int
    ) -> Optional[str]:
        """Com o que ele gastou o turno — e só quando já não dá para mudar.

        A ação **guardada** não responde nada aqui, de propósito: ela ainda
        não aconteceu, então ela não gasta nada que já não possa ser
        devolvido. O que fecha a porta é a ação resolvida.
        """
        turno = await db.turno_de(self.bot.db, run_id, passo, rodada, user_id)
        if turno and not turno["resolvida"]:
            return None
        return await db.acao_do_turno(self.bot.db, run_id, passo, rodada, user_id)

    async def _trocar_acao_guardada(
        self, run: dict[str, Any], passo: int, rodada: int, user_id: int
    ) -> Optional[str]:
        """Tira da mesa a ação preparada, para outra entrar no lugar.

        Preparar antes da vez é o normal, não a exceção: o painel é UMA
        mensagem para o grupo e todo mundo clica quando vê. Mas a iniciativa
        chegava nele com a escolha de dois minutos atrás, feita contra uma
        sala que entretanto mudou de cara — o alvo caiu, o curandeiro ficou em
        1 de HP, o inimigo que importava acordou. Mudar de ideia não era
        possível: o jogador lia "você já usou X nesta rodada" e assistia à
        própria escolha sair errada.

        Agora a escolha guardada é **substituível** até a iniciativa chegar
        nela. O uso da habilidade e a poção que ela tinha reservado voltam
        pelo mesmo caminho de quando a vez não chega: a ação não aconteceu, e
        é só isso que a devolução pergunta.

        Também é por aqui que quem foi substituído retoma a vez: a ação que o
        grupo escolheu por ele está guardada como qualquer outra, então ele
        aparecer e clicar desfaz a do grupo. Era o que já se esperava de
        `marcar_turno`, que mata a proposta aberta quando ele volta ao
        controle — faltava poder voltar depois de a proposta ter fechado.

        Devolve o nome da ação que saiu, ou None se não havia nada para sair.
        """
        turno = await db.desfazer_turno(self.bot.db, run["id"], passo, rodada, user_id)
        if turno is None:
            return None
        await self._devolver_reservas(run, turno, passo)
        return self._nome_da_acao(turno["acao"])

    @staticmethod
    def _chave_de_recarga(habilidade, run: dict[str, Any], passo: int) -> str:
        """Quando esta habilidade zera: por combate, por descanso ou por run."""
        if habilidade.escopo == "combate":
            return f"combate:{passo}"
        if habilidade.escopo == "descanso":
            return f"descanso:{run['descansos']}"
        return "incursao"

    async def _aviso_de_requisito(self, run, estado, user_id: int, habilidade) -> Optional[str]:
        """O requisito de uma ativa vale no painel e na substituicao."""
        exigida = (habilidade.acao or {}).get("exige")
        if not exigida or estado is None:
            return None
        ligados = await db.efeitos_ativos(
            self.bot.db, run["id"], self._passo(run), estado.rodada - 1
        )
        if any(
            e["efeito"] == exigida and e["alvo_id"] == user_id
            and e["alvo_tipo"] == "personagem"
            for e in ligados
        ):
            return None
        return f"**{habilidade.nome}** so vale com a outra habilidade ligada."

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

    async def _alvos_possiveis(self, run, habilidade, estado):
        """As opções de alvo de uma habilidade: `[(valor, nome, detalhe)]`.

        **`None` quer dizer que ela não escolhe alvo**: o buff de grupo, o que
        vale só em quem usa, a invocação, e a que pega todos. Lista vazia quer
        dizer que escolhe e não há ninguém — que é outra coisa.

        Vive separada do menu porque DUAS coisas precisam desta lista: o menu
        de quem clicou, e o autocomplete de `/incursao substituir`. Elas têm de
        ser a mesma lista, senão o grupo poderia propor para o ausente um alvo
        que ele mesmo não poderia escolher.
        """
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
            return None
        if acao.get("alvo") in ("aliado", "aliados") or acao.get("tipo") == "cura":
            if acao.get("tipo") == "cura" and acao.get("alvo") != "aliado":
                return None
            return [
                (str(p["user_id"]), p["nome"], f"{p['hp_atual']}/{p['hp_max']} HP")
                for p in await db.personagens_da_run(self.bot.db, run["id"])
            ]
        # Habilidade que pega todos nao tem alvo a escolher (Flame Strike,
        # Hypnotic Pattern): `alvos` vem como "todos", nao como numero.
        quantos = acao.get("alvos", 1)
        if quantos == "todos":
            return None
        vivos = estado.inimigos_vivos if estado else []
        if len(vivos) <= 1 and quantos <= 1:
            return None
        return [
            (str(i.indice), i.nome, f"{motor.barra(i.hp_atual, i.hp_max, 8)} · CA {i.ca}")
            for i in vivos
        ]

    def _tema_da_sala(self, run: dict[str, Any], sala: Sala) -> Optional[str]:
        """O tema que vale para esta sala nesta run, ou None.

        Só entra em jogo o tema que a sala TEM e a incursão PEDIU no filtro.
        Com mais de um candidato a escolha é sorteada — e semeada por
        `run:sala`, do mesmo jeito que `_trocas_da_parada`: o mesmo par dá
        sempre o mesmo tema, então redesenhar o cartão ou reiniciar o bot não
        troca o bando no meio do combate, e nada precisa ser gravado.

        O cartão da sala e a abertura do combate chamam os dois daqui, pela
        mesma razão que o tier: senão a sala mostraria uma criatura e o
        combate abriria com outra.
        """
        incursao = self._incursao_da_run(run)
        if incursao is None:
            return None
        return sala.tema_em_jogo(
            incursao.filtro.temas, random.Random(f"{run['id']}:{sala.id}")
        )
