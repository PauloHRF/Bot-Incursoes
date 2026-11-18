"""O combate andando: quem está na mesa, de quem é a vez, o que a criatura faz.

Segunda fatia da extração das regras de `src/cogs/incursao.py`, saída de lá
sem mudar uma linha, e conferida pela mesma referência gravada
(`tests/test_referencia_combate.py`). Mora aqui:

- a **montagem do estado** — o grupo com ficha, passivas, auras, condições e
  os efeitos ligados, e as criaturas da sala (`_estado_combate`);
- a **vez de cada um** — o ataque do turno, a ação guardada que sai na
  iniciativa, quem perde a vez e o que ela devolve;
- a **vez da criatura** e a do aliado conjurado, com a ameaça que escolhe o
  alvo;
- as **reações** e a **inspiração**, que entram no meio da vez dos outros;
- os **efeitos que viram** com a rodada: o atordoamento, a corrente, o save
  que se refaz;
- a **Marca Fatal** do ladino, que é estado do combate e não de uma ação.

**O que ficou no cog, e por quê.** `_avancar` e `_virar_rodada` são a fila,
mas são também onde a fila encontra o Discord: respondem a quem clicou,
apagam as respostas privadas da rodada, chamam o grupo no canal. Separar a
regra da mensagem nelas é reescrever, e esta fatia só move. O fecho do
combate também ficou, porque ele é a run andando: paga a sala, abre o
objetivo, encerra a incursão.

Como em `resolvedores.py`, o cog HERDA esta classe — os nomes continuam os de
antes, e a simulação, que sobrescreve sete destes métodos para medir o
combate, continua sendo ouvida por dentro. O que ela pede do cog está em
`DA_MESA`, e `tests/test_fronteira_do_combate.py` cobra a lista exata.
"""
from __future__ import annotations

from typing import Any, Optional

from .. import (
    ameaca,
    classes as cl,
    condicoes,
    consumiveis,
    database as db,
    embeds as E,
    habilidades,
    motor,
)
from ..incursoes import Sala
from ..motor import Combatente, EstadoCombate
from ..rules import tier

# O que o fluxo usa do cog — o que não está em `src/combate`. A chave é o
# atributo; o texto, para que ele serve aqui.
DA_MESA = {
    "bot": "a conexão do banco, em `bot.db`",
    "_passo": "o passo do caminho, que é parte da chave de todo efeito",
    "_tier_da_run": "o tier da incursão, que dimensiona condição e abertura",
    "_tema_da_sala": "o tema que escolhe as criaturas da sala",
    "_personagem_na_run": "a ficha montada de quem age, com as passivas",
    "_chave_de_recarga": "quando o uso de uma habilidade volta",
    "_registrar": "o log da rodada, no painel",
    "_anunciar_habilidade": "o canal: o grupo vê a reação e a inspiração",
    "_marcas_orfas": "o aviso, com botão, da Marca Fatal que ficou sem dono",
}

# Teto de um efeito que so acaba quando o alvo passa no save: nao e para chegar
# la — e so uma trava para nada ficar preso o combate inteiro.
PRAZO_ATE_PASSAR = 20


def nome_do_efeito(efeito_id: str) -> str:
    """O nome que o jogador conhece, a partir do id gravado no efeito.

    Os efeitos sao gravados com `habilidade.id`, que serve ao banco e nao a
    quem le: o resumo do golpe tem de dizer "Marca do Cacador" e nao
    "marca_do_cacador".

    Funcao de modulo porque quem precisa dela e `_aplicar_ligado`, que e
    estatica — e porque ela nao olha para o estado de ninguem.
    """
    habilidade = habilidades.POR_ID.get(efeito_id)
    if habilidade:
        return habilidade.nome
    # A poção grava o efeito pela FAMÍLIA ("pocao_aceleracao"), para a segunda
    # renovar a primeira em vez de somar com ela — então o nome sai da família.
    da_pocao = consumiveis.nome_do_efeito(efeito_id)
    if da_pocao:
        return da_pocao
    return efeito_id.replace('_', ' ')


class Fluxo:
    """A mesa do combate, menos a parte que fala com o Discord.

    `_estado_combate` monta a mesa a partir do banco; `_resolver_turno` e
    `_vez_do_inimigo` fazem cada um agir; `_virar_efeitos` passa a rodada nos
    efeitos. Quem chama tudo isso na ordem é o `_avancar` do cog.
    """

    EFEITO_DA_MARCA = "marca_fatal"
    ID_DA_MARCA_FATAL = "marca_fatal"
    # Gravado no ladino quando a explosao sai: ela sai UMA vez por combate, e
    # dali em diante ele para de marcar. Mora em `run_efeitos` com o prazo do
    # combate, como a ameaca gerada — quem apaga e a troca de sala.
    EFEITO_MARCA_GASTA = "marca_fatal_gasta"

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

    async def _aplicar_aberturas(self, run: dict[str, Any]) -> None:
        """O que vale "ao abrir o combate": a cura do bichinho e o escudo.

        **Roda uma vez por combate, e grava.** As duas moravam em
        `_combatentes`, que e o remontador de estado: ele corre a cada clique
        e a cada redesenho do painel, entao as duas eram reaplicadas sem fim.
        A do druida nao acumulava no banco, mas era recolocada em cima do HP
        gravado toda vez — o druida tinha +9 permanente que voltava depois de
        cada golpe recebido. O THP do mago era pior: `ganhar_thp` SOMA em vez
        de substituir, e ele e gravado.

        **A cura do bichinho e do GRUPO.** O bicho lambe as feridas de quem
        esta na sala, nao so as do druida — era a intencao da habilidade, e o
        codigo cuidava so de quem a tinha.

        As outras duas opcoes do Wild Companion (dano e teste) sao numero puro
        e entram pelas chaves que ja existiam, sem passar por aqui.
        """
        tier = max(1, self._tier_da_run(run) or 1)
        personagens = await db.personagens_da_run(self.bot.db, run["id"])
        combatentes = await self._combatentes(run)
        por_user = {c.user_id: c for c in combatentes}

        # A maior cura do grupo, e nao a soma: dois druidas com o bichinho nao
        # curam em dobro, pelo mesmo motivo que duas passivas iguais nao somam.
        cura = max(
            (((p.get("efeitos") or {}).get("bichinho_cura")) or 0 for p in personagens),
            default=0,
        )
        hps: dict[int, int] = {}
        if cura:
            for c in combatentes:
                if c.caido:
                    continue
                if motor.curar_quanto(c, cura * tier):
                    hps[c.user_id] = c.hp_atual
        if hps:
            await db.definir_hp_varios(self.bot.db, run["id"], hps)

        thps: dict[int, int] = {}
        for p in personagens:
            por_tier = ((p.get("efeitos") or {}).get("escudo_arcano")) or 0
            quem = por_user.get(p["user_id"])
            if por_tier and quem is not None:
                motor.ganhar_thp(quem, por_tier * tier)
                thps[quem.user_id] = quem.thp
        if thps:
            await db.definir_thp_varios(self.bot.db, run["id"], thps)

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
            # A conta da rodada chega pelo mesmo `run_efeitos` que as
            # habilidades, mas vai para outro campo: a marca do painel e para
            # quem tem algo LIGADO chamando atencao, nao para quem
            # simplesmente agiu.
            if ameaca.rodada_do_efeito(ligado["efeito"]) is not None:
                quem.ameaca_gerada += valor.get("ameaca", 0)
            else:
                quem.ameaca_extra += valor.get("ameaca", 0)
            quem.reducao_dano = max(quem.reducao_dano, valor.get("reducao_dano", 0.0))
            # Poção de Resistência: corte plano, depois da fração acima. Vale
            # o maior, como a fração — duas fontes não somam proteção.
            quem.reducao_plana = max(
                quem.reducao_plana, valor.get("reducao_plana", 0)
            )
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
            # Poção da Aceleração: golpe A MAIS, e por isso soma em vez de
            # valer o maior. `ataques` é absoluto ("passa a atacar 2x") e não
            # serviria — num guerreiro de Multiattack ele não daria nada.
            if valor.get("ataques_extra"):
                quem.ataques += valor["ataques_extra"]
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
        # A JANELA da ameaça gerada: vale a rodada seguinte à que a gerou, e
        # só ela. O filtro mora aqui porque este é o único lugar que tem a
        # rodada na mão e os efeitos ainda por aplicar; `_aplicar_ligado` é
        # estático e recebe uma linha de cada vez.
        #
        # A conta da rodada CORRENTE também vem do banco (ela está sendo
        # escrita agora), e é justamente a que não pode entrar: quem age antes
        # na iniciativa chamaria atenção na própria rodada e quem age depois
        # não, e a posição na fila viraria metade da mecânica.
        ligados = [
            l for l in ligados
            if ameaca.rodada_do_efeito(l["efeito"]) in (None, linha["rodada"] - 1)
        ]
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

    async def _preparar_combate(self, run: dict[str, Any], sala: Sala):
        """Inicializa estado, passivas de abertura e iniciativa sem renderizar."""
        # A sala diz QUEM mora nela em cada tier, e a ficha de cada criatura
        # vale como esta escrita. Nada e esticado por multiplicador: se a
        # criatura nao serve ao tier, o conteudo usa outra.
        #
        # Antes daqui saia `escalar_monstro(m, tier)`, que multiplicava HP e
        # dano em cima de criaturas ja escritas em forca cheia de Monster
        # Manual. Cinco Gargulas de 52 HP viravam 416 numa sala de tier 2, e
        # as cinco salas de combate de um dos bancos dizimavam o grupo
        # SEMPRE — 0% de vitoria com o grupo de HP cheio.
        #
        # O tier e o da INCURSAO, o mesmo que dimensiona CD, debuff e ouro:
        # um tier por run, para o cartao da sala nunca mostrar uma criatura
        # e o combate abrir com outra. Incursao aberta a todos vale
        # TIER_MAXIMO, e ai a sala cai no maior tier que ela tem escrito.
        inimigos = sala.monstros_do_tier(
            self._tier_da_run(run), self._tema_da_sala(run, sala)
        )
        await db.iniciar_combate(self.bot.db, run["id"], self._passo(run), sala.id, inimigos)

        # O que vale "ao abrir o combate" acontece AQUI, uma vez, e vai para o
        # banco. Estava em `_combatentes`, que e o remontador de estado — ele
        # roda a cada clique, a cada redesenho do painel, a cada leitura. Na
        # pratica a cura do bichinho era recolocada depois de cada dano (o
        # druida tinha +9 permanente que voltava sozinho), e o THP do mago
        # empilhava, porque `ganhar_thp` SOMA em vez de substituir.
        await self._aplicar_aberturas(run)

        estado = await self._estado_combate(run, sala)
        ordem = await self._garantir_iniciativa(run, estado) if estado else []
        return estado, ordem

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
                    # Sem `teto` na passiva, a pilha nao tem teto: o freio e o
                    # prazo, e nao um numero.
                    sequencia.get("teto"),
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
        # A Marca Fatal entra DEPOIS da Inspiracao — ela vira erro em acerto,
        # e acerto marca — e ANTES de gravar o HP, para a explosao ir no
        # mesmo write.
        marcas = await self._marcar_fatal(run, estado, atacante, user_id, golpes)
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
        self._registrar(
            run, estado.rodada, [E.linha_golpe(g) for g, _i in golpes] + marcas
        )
        resumo = E.resumo_do_golpe([(g, i.nome) for g, i in golpes])
        return resumo + ("\n" + "\n".join(marcas) if marcas else "")

    async def _perder_a_vez(
        self, run: dict[str, Any], estado: EstadoCombate, combatente, turno
    ) -> None:
        """Caído ou atordoado na hora da vez: a ação guardada não sai.

        O uso de uma habilidade escolhida volta — ela não chegou a acontecer.
        """
        if combatente is not None and combatente.atordoado and not combatente.caido:
            self._registrar(
                run,
                estado.rodada,
                [f"{E.MARCA_ATORDOADO} {combatente.nome} está atordoado e perde a vez"],
            )
        if not turno or turno["resolvida"]:
            return
        passo = self._passo(run)
        if not await db.resolver_turno(
            self.bot.db, run["id"], passo, estado.rodada, turno["user_id"]
        ):
            # Alguem ja reivindicou esta acao: devolver aqui tambem devolveria
            # a reserva duas vezes.
            return
        await self._devolver_reservas(run, turno, passo)

    async def _devolver_reservas(
        self, run: dict[str, Any], turno: dict, passo: int
    ) -> None:
        """Devolve o que a ação guardada tinha reservado: o item ou o uso.

        A poção sai da bolsa na **escolha**, e a habilidade gasta o uso na
        escolha — as duas são reservadas antes de a vez chegar, para dois
        cliques no mesmo instante não gastarem a mesma coisa. Quando a vez não
        chega, a reserva tem de voltar.

        Dois caminhos chamam aqui, e são os dois jeitos de a vez não chegar:
        `_perder_a_vez` (caiu ou foi atordoado) e `_devolver_pendentes` (o
        combate ou a run acabou antes).
        """
        pocao = consumiveis.item(turno["acao"])
        if pocao is not None:
            personagem = await self._personagem_na_run(run, turno["user_id"])
            if personagem is not None:
                await db.devolver_item(self.bot.db, personagem["id"], pocao.id)
            return
        habilidade = cl.POR_ID.get(turno["acao"])
        if habilidade is not None:
            await db.devolver_uso(
                self.bot.db, run["id"], turno["user_id"], habilidade.chave_de_uso,
                self._chave_de_recarga(habilidade, run, passo),
            )

    async def _devolver_pendentes(self, run: dict[str, Any]) -> None:
        """O combate acabou antes da vez de alguém: a reserva volta.

        Vencer antes do turno de quem já tinha escolhido queimava a escolha: a
        Poção de Vida desaparecia da bolsa e a Fireball ficava gasta, sem
        nenhuma das duas ter acontecido. É a mesma devolução de
        `_perder_a_vez`, pelo mesmo motivo — a ação não aconteceu —, e o
        combate que termina é só o terceiro jeito de a vez não chegar.
        """
        passo = self._passo(run)
        for turno in await db.turnos_pendentes(self.bot.db, run["id"], passo):
            if not await db.resolver_turno(
                self.bot.db, run["id"], passo, turno["rodada"], turno["user_id"]
            ):
                continue
            await self._devolver_reservas(run, turno, passo)

    async def _resolver_turno(
        self, run: dict[str, Any], estado: EstadoCombate, user_id: int, turno: dict
    ) -> str:
        """Faz a ação que o personagem escolheu, agora que a vez chegou."""
        # O retrato da sala ANTES de a ação valer: o que ela mover é a ameaça
        # que ela gera. Tirado aqui, uma vez, para os três caminhos abaixo
        # medirem a mesma coisa.
        antes = await self._retrato_da_sala(run, estado)
        if turno["acao"] == "ataque":
            texto = await self._resolver_ataque(run, estado, user_id, turno["alvos"])
            await self._gerar_ameaca(run, estado, user_id, None, antes)
            await self._marcas_orfas(run, estado)
            return texto
        # A poção guardada na vez: ela já saiu da bolsa quando foi escolhida,
        # então aqui ela só precisa valer. O id dela não está entre as
        # habilidades do personagem — é do catálogo de consumíveis.
        pocao = consumiveis.item(turno["acao"])
        if pocao is not None:
            texto = await self._resolver_habilidade(
                run, estado, user_id, consumiveis.habilidade_de(pocao), turno["alvos"]
            )
            await self._gerar_ameaca(run, estado, user_id, pocao.acao, antes)
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
        await self._gerar_ameaca(run, estado, user_id, habilidade.acao, antes)
        await self._marcas_orfas(run, estado)
        self._registrar(run, estado.rodada, [f"✨ {estado.combatente(user_id).nome} usa **{habilidade.nome}**"])
        return texto

    async def _marcacao_gasta(self, run: dict[str, Any], user_id: int) -> bool:
        """A explosao deste combate ja saiu?

        `rodada=0` de proposito: a chave vale o combate inteiro, entao a
        pergunta nao e "vale nesta rodada" e sim "existe" — e 0 pede tudo que
        ainda nao venceu.
        """
        return any(
            e["alvo_tipo"] == "personagem"
            and e["alvo_id"] == user_id
            and e["efeito"] == self.EFEITO_MARCA_GASTA
            for e in await db.efeitos_ativos(
                self.bot.db, run["id"], self._passo(run), 0
            )
        )

    async def _marcacao_aberta(self, run: dict[str, Any], user_id: int) -> bool:
        """A Marca Fatal esta aberta neste combate para este personagem?

        A habilidade era passiva, e o que a ligava era `efeitos["marca_fatal"]`:
        o ladino marcava desde o primeiro golpe, sem decidir nada. Agora ela e
        uma chave — ele gasta a acao uma vez por combate para abrir, e dali em
        diante todo acerto marca, como antes.

        **O registro do uso E o interruptor**, e nao um estado novo:
        `gastar_uso` grava sob `combate:{passo}`, entao a chave nasce quando a
        ativa e usada, vale pelo combate inteiro e morre com ele — e ja esta
        gravada quando o golpe da propria ativa resolve, porque `usar_habilidade`
        gasta o uso antes de resolver. Por isso o ataque que abre tambem marca.

        So quem tem a habilidade consegue gastar o uso dela, entao isto tambem
        responde "este personagem e um ladino do tier 2 ou mais".
        """
        habilidade = habilidades.POR_ID.get(self.ID_DA_MARCA_FATAL)
        if habilidade is None:
            return False
        gastos = await db.usos_da_run(self.bot.db, run["id"], user_id)
        chave = self._chave_de_recarga(habilidade, run, self._passo(run))
        if gastos.get((habilidade.chave_de_uso, chave), 0) <= 0:
            return False
        # A torneira fecha sozinha na explosao: ela sai UMA vez por combate.
        return not await self._marcacao_gasta(run, user_id)

    async def _fechar_marcacao(self, run: dict[str, Any], user_id: int, estado) -> None:
        """Grava que a explosao deste ladino ja saiu, e limpa o que sobrou.

        Chamado pela propria explosao. O prazo e o do combate inteiro, como a
        ameaca gerada: quem apaga e a troca de sala, porque o `passo` faz
        parte da chave em `run_efeitos`.
        """
        passo = self._passo(run)
        await db.aplicar_efeito(
            self.bot.db, run["id"], passo, "personagem", user_id,
            self.EFEITO_MARCA_GASTA, {}, self.PRAZO_DO_COMBATE, dono=user_id,
        )
        # As marcas que ficaram em outro inimigo morrem com a marcacao: sem
        # ela aberta nao ha terceira marca, e elas so enfeitariam o painel.
        for indice, marca in (await self._marcas_de(run, estado.rodada)).items():
            if marca["dono"] == user_id:
                await db.remover_efeito(
                    self.bot.db, run["id"], passo, "inimigo", indice,
                    self.EFEITO_DA_MARCA,
                )

    async def _marcas_de(self, run: dict[str, Any], rodada: int) -> dict[int, dict]:
        """As Marcas Fatais vivas, por índice de inimigo."""
        return {
            e["alvo_id"]: e
            for e in await db.efeitos_ativos(
                self.bot.db, run["id"], self._passo(run), rodada
            )
            if e["alvo_tipo"] == "inimigo" and e["efeito"] == self.EFEITO_DA_MARCA
        }

    async def _marcar_fatal(
        self, run: dict[str, Any], estado, atacante, user_id: int, golpes: list
    ) -> list[str]:
        """Com a marcação aberta, todo acerto marca; a terceira explode.

        As regras da ficha, e como elas se encaixam:

        - **a marcação não vem de graça**: o ladino gasta a ativa do tier 2
          uma vez por combate para abri-la (`_marcacao_aberta`). O golpe
          dessa própria ativa já marca, porque o uso é gravado antes de o
          golpe resolver;
        - acertar aplica 1 marca, e **devolve o prazo inteiro** às que já
          estão lá — não decrementa para 2, volta para 3;
        - na terceira marca elas explodem na hora, sem rolar acerto;
        - passar 3 turnos sem marcar o mesmo inimigo perde as marcas dele,
          e disso quem cuida é `limpar_efeitos_vencidos`, que já roda ao
          virar a rodada.

        O dado sai do tier do LADINO, e não do grupo: é a ficha dele que
        cresce. Chamado dos dois caminhos de ataque — o do turno e o da
        ativa —, porque "sempre que acerta um ataque" vale para os dois.

        Não altera o HP no banco: o estrago entra em `inimigo.hp_atual`, e
        quem chama grava junto com o dano dos golpes.
        """
        if atacante is None or not golpes:
            return []
        if not await self._marcacao_aberta(run, user_id):
            return []
        personagem = await self._personagem_na_run(run, user_id)
        dado = habilidades.DANO_DA_MARCA[tier((personagem or {}).get("nivel") or 1)]
        vivas = await self._marcas_de(run, estado.rodada)
        # Conta local porque um multiataque marca duas vezes no mesmo turno,
        # e a segunda precisa ver a primeira.
        quantas = {i: (e["valor"] or {}).get("marcas", 0) for i, e in vivas.items()}
        passo, linhas = self._passo(run), []
        for golpe, inimigo in golpes:
            if not golpe.acertou or inimigo.caido:
                continue
            marcas = quantas.get(inimigo.indice, 0) + 1
            if marcas >= habilidades.MARCAS_PARA_EXPLODIR:
                dano = sum(motor.rolar_dano(dado) for _ in range(marcas))
                inimigo.hp_atual = max(0, inimigo.hp_atual - dano)
                await db.remover_efeito(
                    self.bot.db, run["id"], passo, "inimigo", inimigo.indice,
                    self.EFEITO_DA_MARCA,
                )
                caiu = " — e **cai**" if inimigo.caido else ""
                linhas.append(
                    f"🎯 As **{marcas}** Marcas Fatais explodem em "
                    f"**{inimigo.nome}**: **{dano}** de dano ({marcas}×{dado})"
                    f"{caiu}"
                )
                # A explosão sai UMA vez por combate, e fecha a torneira: o
                # ciclo não recomeça. E as marcas que ficaram em OUTRO inimigo
                # saem com ela — sem marcação aberta elas nunca mais crescem,
                # e o 🎯 no nome dele passaria a prometer uma explosão que não
                # vem.
                #
                # O `break` é precaução e não regra testada: o ladino tem UM
                # golpe, então hoje não há golpe seguinte neste turno para
                # marcar. Se um dia ele ganhar Multiataque, é o `break` que
                # impede o segundo golpe de abrir a pilha de novo.
                await self._fechar_marcacao(run, user_id, estado)
                linhas.append(
                    "🎯 A Marca Fatal se fecha: foi a explosão deste combate."
                )
                break
            quantas[inimigo.indice] = marcas
            await db.aplicar_efeito(
                self.bot.db, run["id"], passo, "inimigo", inimigo.indice,
                self.EFEITO_DA_MARCA, {"marcas": marcas},
                estado.rodada + habilidades.TURNOS_DA_MARCA, dono=user_id,
            )
            linhas.append(
                f"🎯 **{inimigo.nome}** fica com **Marca Fatal ×{marcas}**"
            )
        return linhas

    async def _escondido(self, run: dict[str, Any], user_id: int, rodada: int) -> bool:
        """O ladino está em Stealth nesta rodada?

        O `desde` existe porque o ataque que ABRE a Furtividade conta ameaça
        normalmente — a ficha diz "realiza um ataque e depois entra em
        Stealth". Sem ele, o próprio golpe que liga a habilidade já sairia
        de graça.
        """
        for e in await db.efeitos_ativos(
            self.bot.db, run["id"], self._passo(run), rodada
        ):
            if (
                e["alvo_tipo"] == "personagem"
                and e["alvo_id"] == user_id
                and e["efeito"] == self.EFEITO_DA_FURTIVIDADE
                and rodada >= (e["valor"] or {}).get("desde", 0)
            ):
                return True
        return False

    async def _prisoes(
        self, run: dict[str, Any], estado: EstadoCombate
    ) -> dict[int, int]:
        """Até que rodada cada criatura está presa, pelo que está gravado.

        A chave de `run_efeitos` tem o alvo e o efeito, então há no máximo um
        `atordoado` por criatura — o dicionário não perde nada.
        """
        return {
            e["alvo_id"]: e["expira"]
            for e in await db.efeitos_ativos(
                self.bot.db, run["id"], self._passo(run), estado.rodada - 1
            )
            if e["alvo_tipo"] == "inimigo" and e["efeito"] == "atordoado"
        }

    async def _retrato_da_sala(
        self, run: dict[str, Any], estado: EstadoCombate
    ) -> tuple[motor.RetratoDaSala, dict[int, int]]:
        """O que a medição da ameaça compara: o HP dos dois lados e as prisões.

        O retrato do HP vem de `motor`, e é o MESMO que a bancada de simulação
        usa para atribuir dano e cura às habilidades: eram duas contas
        separadas, e o "dano" que o simulador reportava podia não ser o
        "dano" que o jogo paga em ameaça.
        """
        return motor.retrato(estado), await self._prisoes(run, estado)

    @staticmethod
    def _ca_que_a_criatura_enfrenta(estado: EstadoCombate) -> int:
        """A CA média que uma criatura encontra, pesada pela ameaça.

        Pesada, e não a média simples: a criatura bate mais em quem puxa mais
        atenção, e quem puxa mais atenção é justamente quem veste a armadura
        pesada. A média simples subestimaria a armadura que ela enfrenta de
        verdade — e esta conta serve para dizer quanto dano ela daria.
        """
        de_pe = estado.vivos
        if not de_pe:
            return 15
        fatias = ameaca.fracoes(ameaca.de_quem(de_pe), ameaca.fatores_de(de_pe))
        return round(sum(c.ca_efetiva * f for c, f in zip(de_pe, fatias)))

    def _dano_evitado(
        self,
        estado: EstadoCombate,
        antes: dict[int, int],
        depois: dict[int, int],
    ) -> int:
        """O dano que as criaturas recém-presas não vão dar.

        É o "dano que poderia ter sido dado e não foi": as rodadas que a ação
        tirou de cada criatura, vezes o que ela daria numa rodada. Prender um
        troll por três rodadas é devolver ao grupo o HP de três rodadas de
        troll, e isso chama atenção como curar o mesmo tanto chamaria.

        Conta o GANHO, e não o prazo inteiro: estender uma prisão de uma
        rodada para três vale duas, e renovar uma que já ia até lá vale zero.
        """
        ca = self._ca_que_a_criatura_enfrenta(estado)
        total = 0.0
        for indice, ate in depois.items():
            inimigo = estado.inimigo(indice)
            if inimigo is None or inimigo.caido:
                continue
            desde = max(antes.get(indice, 0), estado.rodada)
            rodadas = max(0, ate - desde)
            if rodadas:
                total += rodadas * motor.media_por_rodada(inimigo, ca)
        return round(total)

    async def _gerar_ameaca(
        self,
        run: dict[str, Any],
        estado: EstadoCombate,
        user_id: int,
        acao,
        antes: tuple[motor.RetratoDaSala, dict[int, int]],
    ) -> None:
        """O HP que a ação acabou de mover chama a atenção da criatura.

        Mora aqui, no `_resolver_turno`, e nao em cada resolvedor: este e o
        gargalo por onde o ataque e a habilidade passam os dois, e o uso FORA
        de combate nao passa — que e o certo, nao ha criatura para chamar.

        **A medição é por fora**, comparando o HP dos dois lados antes e
        depois. São doze resolvedores, cada um devolvendo texto, e nenhum
        deles sabe dizer um número: fazê-los devolver o dano seria mexer nos
        doze e manter os doze em sincronia para sempre. De fora, o que se mede
        é o que de fato aconteceu com a sala — inclusive o que vier por
        caminhos que ainda não existem.

        O overkill fica de fora por consequência, e isso é o certo: bater 40
        num inimigo de 5 move 5 de HP, e matar o que já ia morrer não é
        notável.
        """
        quem = estado.combatente(user_id)
        if quem is None or quem.e_invocacao:
            return
        # Furtividade: a ameaca para de SUBIR, e nao e zerada. O que ele
        # acumulou continua valendo, e segue podendo cair por outros efeitos.
        if await self._escondido(run, user_id, estado.rodada):
            return
        pontos = ameaca.declarada_por(acao)
        if pontos is None:
            depois = motor.retrato(estado)
            dos_inimigos, do_grupo = motor.potes_de_hp(estado)
            pontos = ameaca.pontos_do_hp(
                dano=motor.dano_tomado(antes[0], depois),
                cura=motor.hp_devolvido(antes[0], depois),
                evitado=self._dano_evitado(
                    estado, antes[1], await self._prisoes(run, estado)
                ),
                hp_dos_inimigos=dos_inimigos,
                hp_do_grupo=do_grupo,
            )
        await db.somar_ameaca_da_rodada(
            self.bot.db, run["id"], self._passo(run), estado.rodada,
            user_id, pontos,
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
            self._registrar(
                run,
                estado.rodada,
                [f"{E.MARCA_ATORDOADO} {inimigo.nome} está atordoado e perde a vez"],
            )
            return
        feito = motor.turno_do_inimigo(inimigo, estado, None)
        if feito.regenerou:
            await db.definir_hp_inimigos(
                self.bot.db, run["id"], self._passo(run), {inimigo.indice: inimigo.hp_atual}
            )
        # Inspiracao no save: antes de gravar qualquer coisa. Mexer aqui evita
        # escrever no banco o dano, o atordoamento e a condicao que o bardo
        # acabou de impedir — e so depois apaga-los.
        await self._inspirar_o_save(run, estado, feito)
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
        await self._reacoes_do_revide(run, estado, feito.golpes, feito.investidas)
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

    async def _inspirar_o_save(self, run: dict[str, Any], estado, feito) -> None:
        """Inspiração no save: quem falhou por pouco passa a resistir.

        O motor refaz o dano a partir da vida anterior a acao da criatura,
        respeitando metade no sucesso, vida temporaria e os outros golpes.
        """
        passo = self._passo(run)
        for investida in feito.investidas:
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
            dano_anterior = investida.dano
            motor.refazer_o_save(feito, investida, ajuda)
            evitado = dano_anterior - investida.dano
            self._registrar(
                run, estado.rodada,
                [f"🎵 **{habilidade.nome}**: {p['nome']} sopra **+{ajuda}** no "
                 f"save de {alvo.nome} — resiste, e evita **{evitado}** de dano"],
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

    async def _reacoes_do_revide(
        self, run: dict[str, Any], estado, golpes, investidas=()
    ) -> None:
        """As reacoes que o turno do inimigo dispara, na ordem em que importam.

        A esquiva vem antes da queda: cortar o golpe pela metade pode evitar
        que a segunda reacao precise acontecer.

        **A esquiva vale so contra GOLPE**, e isso e de propósito: Uncanny
        Dodge corta um ataque que o ladino ve vir, nao uma explosao em que ele
        falhou a resistencia.

        **A queda vale contra tudo.** Relentless dispara por chegar a zero, e
        nao importa o que levou ate lá. Aqui so os golpes chegavam, entao o
        barbaro se recusava a cair quando a criatura BATIA nele e ficava no
        chao quando ela o matava com a habilidade — que e justamente o golpe
        mais pesado que ela tem.

        As investidas `do_golpe` ficam de fora porque o dano delas ja veio no
        golpe que as disparou: elas estao representadas em `golpes`. Hoje esse
        filtro nao MUDA nada — a deduplicacao abaixo ja descartaria essas
        entradas, porque o golpe que as trouxe vem antes na lista —, e esta
        aqui para dizer a intencao e para o dia em que uma das duas coisas sair
        de cena. Nao ha caso cobrindo ele: cobrir pediria uma reacao de queda
        com mais de um uso, e nenhuma existe.
        """
        await self._esquivas(run, golpes)
        # Um alvo por reacao, mesmo aparecendo duas vezes: criatura com dois
        # ataques entrega dois golpes no mesmo personagem, e uma reacao de
        # varios usos dispararia duas vezes por uma unica queda.
        caiu = []
        vistos: set[int] = set()
        candidatos = list(golpes) + [
            (investida, investida.alvo)
            for investida in investidas
            if investida.dano and not investida.do_golpe
        ]
        for origem, atingido in candidatos:
            if atingido.user_id in vistos:
                continue
            vistos.add(atingido.user_id)
            caiu.append((origem, atingido))
        await self._reacoes_ao_cair(run, caiu)

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
        levantados = []
        # `combatentes` e nao `vivos`: a cura por turno levanta caido como as
        # outras. Grupo INTEIRO no chao nao chega aqui — o laco do `_avancar`
        # ve `estado.encerrado` antes de virar a rodada e encerra o combate —,
        # entao a regeneracao socorre quem caiu, mas nao desfaz uma derrota.
        for c in estado.combatentes:
            if c.cura_por_turno:
                estava_caido = c.caido
                ganho = motor.curar(c, c.cura_por_turno)
                if ganho:
                    curas[c.user_id] = c.hp_atual
                if estava_caido and not c.caido:
                    levantados.append(c)
        if curas:
            await db.definir_hp_varios(self.bot.db, run["id"], curas)
        # A regeneracao levanta sem ninguem decidir, e cobra igual: a linha
        # entra no registro da rodada para o grupo ver o preco.
        for c in levantados:
            self._registrar(run, estado.rodada, [await self._cobrar_o_retorno(run, c)])
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

    async def _de_quem_e_a_vez(self, run, estado) -> Optional[int]:
        """O jogador que a fila está esperando, ou None.

        É a mesma leitura que `_avancar` faz para parar: `ordem[vez]`, quando o
        ator é um personagem de pé, não atordoado, não invocado, e sem ação
        escolhida nesta rodada. Fora disso ninguém está sendo esperado — a
        criatura age sozinha, e quem está caído perde a vez sozinho.
        """
        passo = self._passo(run)
        ordem = await self._garantir_iniciativa(run, estado)
        combate = await db.estado_combate(self.bot.db, run["id"], passo)
        vez = (combate or {}).get("vez", 0)
        if vez >= len(ordem):
            return None
        ator = ordem[vez]
        if ator["tipo"] != motor.PERSONAGEM:
            return None
        user_id = ator["alvo_id"]
        quem = estado.combatente(user_id)
        if quem is None or quem.caido or quem.atordoado or quem.e_invocacao:
            return None
        if await db.acao_do_turno(
            self.bot.db, run["id"], passo, estado.rodada, user_id
        ):
            return None
        return user_id
