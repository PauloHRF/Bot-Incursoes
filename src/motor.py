"""Resolução de regras da run, sem nenhuma dependência do Discord.

Tudo aqui é função pura sobre dados simples, para que as mecânicas possam mudar
sem tocar na camada de comandos — e para que o playtest possa ser simulado.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Iterable, Optional

from .incursoes import OPCOES_POR_PASSO, Monstro, Sala
from .rules import PESO_TIER, melhor_pericia, tier

# Uma expressao de dano e uma soma de termos: "3d8+3", "1d6", "3d8+3+2d6".
# Cada termo e NdM ou um numero solto, com sinal opcional.
TERMO_DANO = re.compile(r"([+-]?)(?:(\d*)d(\d+)|(\d+))", re.IGNORECASE)
EXPR_DANO = re.compile(
    r"^[+-]?(?:\d*d\d+|\d+)(?:[+-](?:\d*d\d+|\d+))*$", re.IGNORECASE
)


def _rng(rng: Optional[random.Random]) -> random.Random:
    return rng or random.SystemRandom()


def rolar_d20(rng: Optional[random.Random] = None, vantagem: bool = False) -> int:
    gerador = _rng(rng)
    if vantagem:
        # Vantagem: rola dois e fica com o melhor.
        return max(gerador.randint(1, 20), gerador.randint(1, 20))
    return gerador.randint(1, 20)


def termos_de_dano(expressao: str) -> list[tuple[int, int, int]]:
    """Quebra '3d8+2d6+3' em termos (sinal, quantidade, faces).

    Faces 0 é um número solto: ('+3' vira (1, 3, 0)). Uma criatura que bate de
    corte e de veneno no mesmo golpe cabe numa expressão só.
    """
    limpa = str(expressao).replace(" ", "")
    if not limpa or not EXPR_DANO.match(limpa):
        raise ValueError(f"expressão de dano inválida: {expressao!r}")
    termos = []
    for sinal, quantidade, faces, constante in TERMO_DANO.findall(limpa):
        peso = -1 if sinal == "-" else 1
        if faces:
            termos.append((peso, int(quantidade or 1), int(faces)))
        else:
            termos.append((peso, int(constante), 0))
    return termos


def rolar_dano(
    expressao: str, rng: Optional[random.Random] = None, critico: bool = False
) -> int:
    """Rola uma expressão como '2d6+3' ou '3d8+3+2d6'. Nunca devolve menos que 1.

    Num crítico, os dados são rolados em dobro e os números soltos entram uma
    vez só, como manda a regra de 5e: 2d6+3 vira 4d6+3.
    """
    gerador = _rng(rng)
    total = 0
    for peso, quantidade, faces in termos_de_dano(expressao):
        if faces:
            dados = quantidade * (2 if critico else 1)
            total += peso * sum(gerador.randint(1, faces) for _ in range(dados))
        else:
            total += peso * quantidade
    return max(1, total)


@dataclass
class ResultadoTeste:
    """Uma rolagem de perícia de um personagem contra a CD da sala."""

    user_id: int
    personagem: str
    pericia: str
    d20: int
    modificador: int
    cd: int

    @property
    def total(self) -> int:
        return self.d20 + self.modificador

    @property
    def passou(self) -> bool:
        return self.total >= self.cd

    @property
    def margem(self) -> int:
        """Progresso que este personagem contribui. Nunca negativo."""
        return max(0, self.total - self.cd)


def testar(ficha: dict[str, Any], sala: Sala, rng: Optional[random.Random] = None) -> ResultadoTeste:
    """Rola o teste da sala usando a melhor perícia da ficha entre as listadas."""
    if not sala.tem_teste or sala.cd is None:
        raise ValueError(f"a sala {sala.id} ({sala.tipo}) não é resolvida por teste de perícia")
    efeitos = ficha.get("efeitos") or {}
    pericia, modificador = melhor_pericia(
        sala.pericias,
        ficha["numeros"],
        ficha["pericias"],
        ficha.get("bonus_pericias"),
        efeitos,
    )
    return ResultadoTeste(
        user_id=ficha["user_id"],
        personagem=ficha["nome"],
        pericia=pericia,
        d20=rolar_d20(rng),
        modificador=modificador,
        cd=sala.cd,
    )


def sortear_passo(
    salas: list[Sala],
    visitadas: Iterable[str] = (),
    opcoes: int = OPCOES_POR_PASSO,
    rng: Optional[random.Random] = None,
) -> list[str]:
    """As salas oferecidas num passo, sorteadas do banco da Organização.

    Nenhuma sala que o grupo já atravessou volta a ser oferecida: o caminho é
    sorteado passo a passo, quando o passo abre, e não de uma vez no começo.
    Se sobrarem menos salas novas que o número de opções, o passo sai menor —
    melhor escolher entre duas portas do que voltar para a mesma câmara.
    """
    ja_visitadas = set(visitadas)
    candidatas = [s for s in salas if s.id not in ja_visitadas]
    if not candidatas:
        raise ValueError(
            f"o banco tem {len(salas)} sala(s) e o grupo já passou por todas elas"
        )
    return [s.id for s in _rng(rng).sample(candidatas, min(opcoes, len(candidatas)))]


# ------------------------------------------------------- janela semanal


def segunda_da_semana(momento: datetime) -> datetime:
    """A segunda-feira 00:00 da semana daquele momento."""
    return (momento - timedelta(days=momento.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def virada_da_vaga(ultima: datetime, semanas: int = 1) -> datetime:
    """Quando a vaga do jogador volta: a segunda-feira N semanas depois da que ele jogou.

    Contando pela segunda, e não por 7 dias corridos: quem entrou no sábado joga
    de novo na segunda, e a semana do grupo inteiro vira junto.
    """
    return segunda_da_semana(ultima) + timedelta(weeks=max(1, semanas))


def entrada_liberada(
    ultima: Optional[datetime], agora: datetime, semanas: int = 1
) -> bool:
    """Se o jogador já pode entrar numa nova incursão."""
    if semanas <= 0 or ultima is None:
        return True
    return agora >= virada_da_vaga(ultima, semanas)


# Consequência individual de falhar, por tipo de sala (tabela do documento de design).
CONSEQUENCIA_FALHA = {
    "Armadilha": "sofre uma penalidade leve — dano superficial ou material gasto",
    "Evento": "não contribui para a descoberta, mas sai ileso",
    "Tesouro": "não leva o item extra",
    "Combate": "sofre dano e fica fora do resto do combate",
}


@dataclass
class ResolucaoSala:
    """Estado de uma sala depois que o grupo rolou."""

    sala: Sala
    resultados: list[ResultadoTeste]
    total_participantes: int

    @property
    def progresso(self) -> int:
        return sum(r.margem for r in self.resultados)

    @property
    def alvo(self) -> int:
        return self.sala.alvo_progresso or 0

    @property
    def superada(self) -> bool:
        return self.progresso >= self.alvo

    @property
    def todos_rolaram(self) -> bool:
        return len(self.resultados) >= self.total_participantes

    @property
    def encerrada(self) -> bool:
        """A sala para de aceitar rolagens quando o alvo é atingido ou todos rolaram."""
        return self.superada or self.todos_rolaram

    @property
    def quem_falhou(self) -> list[ResultadoTeste]:
        return [r for r in self.resultados if not r.passou]

    @property
    def quem_passou(self) -> list[ResultadoTeste]:
        return [r for r in self.resultados if r.passou]


def escalar_monstro(monstro: Monstro, tiers_do_grupo: list[int]) -> Monstro:
    """Ajusta o monstro à composição do grupo.

    Hoje devolve o monstro como está: a regra de escala do chefe ainda não foi
    definida. Este é o único ponto a mudar quando ela for — a soma de pesos por
    tier já vem calculada em `peso_do_grupo`.
    """
    return monstro


def peso_do_grupo(niveis: list[int]) -> int:
    """Soma dos pesos por tier dos participantes (fórmula do objetivo principal)."""
    return sum(PESO_TIER[tier(n)] for n in niveis)


def pode_encarar(nivel: int, tier_incursao: int) -> bool:
    """Se um personagem daquele nível pode entrar numa incursão daquele tier.

    Abaixo do tier pode: o personagem novo pega carona com o grupo e sobe. Acima
    não: uma incursão feita para quem está começando não é lugar de quem já
    passou dela.
    """
    return tier(nivel) <= tier_incursao


@dataclass
class Combatente:
    user_id: int
    nome: str
    ca: int
    bonus_ataque: int
    dano_arma: str
    hp_max: int
    hp_atual: int
    # Vida temporaria: absorve dano antes do HP e some no fim do combate.
    thp: int = 0
    # O que as passivas da classe somam. Os defaults sao o personagem sem
    # nenhuma habilidade automatica.
    ataques: int = 1
    critico_em: int = 20
    dano_extra: int = 0
    dano_ferido: int = 0
    # Efeitos com prazo, ligados por habilidade dentro do combate.
    reducao_dano: float = 0.0
    vantagem: bool = False
    ca_extra: int = 0
    cura_por_turno: float = 0.0
    # Marca do Cacador e afins: valem so contra aquele inimigo.
    dano_por_alvo: dict = field(default_factory=dict)
    vantagem_contra: set = field(default_factory=set)
    # Resistencias: {atributo: modificador}, ja com os saves fortes da classe.
    saves: dict = field(default_factory=dict)
    # Perde a proxima vez: habilidade de criatura que atordoa.
    atordoado: bool = False

    @property
    def ca_efetiva(self) -> int:
        return self.ca + self.ca_extra

    @property
    def tem_thp(self) -> bool:
        return self.thp > 0

    @property
    def caido(self) -> bool:
        return self.hp_atual <= 0


@dataclass
class GolpeAtaque:
    atacante: str
    alvo: str
    d20: int
    bonus: int
    ca_alvo: int
    dano: int = 0
    # Improved Critical desce este numero: o critico deixa de ser so o 20.
    critico_em: int = 20
    # Ativas que dispensam a rolagem: o golpe acerta, ou ja sai critico.
    garantido: bool = False
    critico_forcado: bool = False
    # Quanto do dano a vida temporaria do alvo segurou.
    absorvido: int = 0

    @property
    def total(self) -> int:
        return self.d20 + self.bonus

    @property
    def acertou(self) -> bool:
        if self.garantido:
            return True
        # 20 natural sempre acerta; 1 natural sempre erra, por maior que seja o bonus.
        if self.d20 == 20:
            return True
        if self.critico:  # o critico de 19 tambem acerta por si so
            return True
        if self.d20 == 1:
            return False
        return self.total >= self.ca_alvo

    @property
    def critico(self) -> bool:
        return self.critico_forcado or self.d20 >= self.critico_em

    @property
    def falha_critica(self) -> bool:
        return self.d20 == 1


def atacar(
    atacante_nome: str,
    bonus: int,
    dano: str,
    alvo_nome: str,
    ca_alvo: int,
    rng: Optional[random.Random] = None,
    critico_em: int = 20,
    dano_extra: int = 0,
    dano_bonus: Optional[str] = None,
    garantido: bool = False,
    critico_forcado: bool = False,
    vantagem: bool = False,
) -> GolpeAtaque:
    """Uma rolagem de ataque: d20 + bônus contra a CA. Acertou, rola o dano.

    `dano_extra` é o que as passivas somam por golpe; entra depois do crítico,
    porque dobra os dados, não os bônus fixos. `dano_bonus` é uma expressão a
    mais (o +3d8 do Golpe Divino), e `garantido`/`critico_forcado` são as
    ativas que dispensam a rolagem de acerto.
    """
    golpe = GolpeAtaque(
        atacante_nome,
        alvo_nome,
        rolar_d20(rng, vantagem),
        bonus,
        ca_alvo,
        critico_em=critico_em,
        garantido=garantido,
        critico_forcado=critico_forcado,
    )
    if golpe.acertou:
        golpe.dano = rolar_dano(dano, rng, critico=golpe.critico) + dano_extra
        if dano_bonus:
            golpe.dano += rolar_dano(dano_bonus, rng, critico=golpe.critico)
    return golpe


def progresso_da_run(linha_atual: int, total_linhas: int = 3) -> str:
    """Barra textual do avanço pelas linhas, para o embed de status."""
    cheias = max(0, min(linha_atual, total_linhas))
    return "▰" * cheias + "▱" * (total_linhas - cheias)


def barra(valor: int, maximo: int, casas: int = 10) -> str:
    """Barra proporcional para progresso de sala ou HP."""
    if maximo <= 0:
        return "▱" * casas
    cheias = max(0, min(casas, round(casas * valor / maximo)))
    return "▰" * cheias + "▱" * (casas - cheias)


# ------------------------------------------------------------ combate

# Rodada de combate: todo personagem de pé ataca uma vez o inimigo que escolher,
# depois cada inimigo de pé revida num alvo sorteado. Repete até um dos lados cair.


@dataclass
class Inimigo:
    """Uma criatura da sala, com HP próprio. Uma sala pode ter várias."""

    indice: int
    nome: str
    ca: int
    ataque: int
    dano: str
    hp_max: int
    hp_atual: int
    # Perde a vez na proxima rodada: Stunning Strike e afins.
    atordoado: bool = False
    # Resistencias da criatura: {atributo: modificador}. O que nao vier aqui
    # cai no padrao de DEFASAGEM_DE_SAVE.
    saves: dict = field(default_factory=dict)
    # Recharge: comeca carregada e so volta quando o d6 deixar.
    carregada: bool = True
    # Quantos golpes por rodada, e em que resiste com vantagem.
    ataques: int = 1
    saves_vantagem: list = field(default_factory=list)
    # A acao especial da criatura (HabilidadeDoMonstro), se tiver uma.
    habilidade: Optional[Any] = None

    @property
    def caido(self) -> bool:
        return self.hp_atual <= 0

    def usa_habilidade(self, rodada: int, rng: Optional[random.Random] = None) -> bool:
        """Se a criatura usa a habilidade nesta rodada, em vez de atacar.

        Com ritmo fixo (`cada`) a conta e do numero da rodada. Com recarga
        (Recharge 5-6), ela sai carregada, e depois de usada so volta quando o
        d6 da criatura tirar o numero da recarga ou mais — por isso este metodo
        mexe no estado dela.
        """
        if self.habilidade is None:
            return False
        if not self.habilidade.recarga:
            return self.habilidade.disponivel(rodada)
        if not self.carregada:
            self.carregada = self.habilidade.recarregou(rng)
        if self.carregada:
            self.carregada = False  # gasta a carga ao usar
            return True
        return False

    def save(self, atributo: str) -> int:
        """O modificador de resistência desta criatura naquele atributo.

        Enquanto o banco de criaturas não trouxer os saves, a criatura resiste
        com o próprio bônus de ataque menos uma defasagem — é um número
        provisório, que some assim que a planilha tiver a coluna.
        """
        if atributo in self.saves:
            return self.saves[atributo]
        return self.ataque - DEFASAGEM_DE_SAVE


@dataclass
class EstadoCombate:
    inimigos: list[Inimigo]
    rodada: int
    combatentes: list[Combatente]

    @property
    def vivos(self) -> list[Combatente]:
        return [c for c in self.combatentes if not c.caido]

    @property
    def caidos(self) -> list[Combatente]:
        return [c for c in self.combatentes if c.caido]

    @property
    def ativos(self) -> list[Combatente]:
        """Quem ainda age nesta rodada: de pé e sem atordoamento.

        A rodada fecha quando todos estes já agiram — quem está atordoado não
        segura o combate esperando um clique que não vai vir.
        """
        return [c for c in self.vivos if not c.atordoado]

    @property
    def inimigos_vivos(self) -> list[Inimigo]:
        return [i for i in self.inimigos if not i.caido]

    @property
    def inimigos_derrotados(self) -> bool:
        """Só acaba quando a sala inteira cai, não o primeiro inimigo."""
        return not self.inimigos_vivos

    @property
    def grupo_caido(self) -> bool:
        return not self.vivos

    @property
    def encerrado(self) -> bool:
        return self.inimigos_derrotados or self.grupo_caido

    def combatente(self, user_id: int) -> Optional[Combatente]:
        for c in self.combatentes:
            if c.user_id == user_id:
                return c
        return None

    def inimigo(self, indice: int) -> Optional[Inimigo]:
        for i in self.inimigos:
            if i.indice == indice:
                return i
        return None

    def alvo_preferido(self, indice: Optional[int] = None) -> Optional[Inimigo]:
        """O inimigo escolhido, se ainda estiver de pé; senão o primeiro vivo.

        Com um inimigo só na sala ninguém precisa escolher nada.
        """
        if indice is not None:
            alvo = self.inimigo(indice)
            if alvo is not None and not alvo.caido:
                return alvo
            return None
        vivos = self.inimigos_vivos
        return vivos[0] if vivos else None


def esta_ferido(inimigo: Inimigo) -> bool:
    """Metade ou menos do HP — o gatilho do Predador."""
    return inimigo.hp_atual * 2 <= inimigo.hp_max


# Quanto uma criatura sem save na planilha fica abaixo do próprio bônus de ataque.
DEFASAGEM_DE_SAVE = 3


@dataclass
class ResultadoSave:
    """Um teste de resistência: d20 + modificador contra a CD de quem forçou."""

    quem: str
    atributo: str
    d20: int
    modificador: int
    cd: int

    @property
    def total(self) -> int:
        return self.d20 + self.modificador

    @property
    def passou(self) -> bool:
        # Diferente do ataque, um 1 ou um 20 natural não decidem nada sozinhos:
        # o save é só o total contra a CD.
        return self.total >= self.cd


def salvar(
    quem: str,
    atributo: str,
    modificador: int,
    cd: int,
    rng: Optional[random.Random] = None,
    vantagem: bool = False,
) -> ResultadoSave:
    """A rolagem crua, para quem já sabe o modificador."""
    return ResultadoSave(quem, atributo, rolar_d20(rng, vantagem), modificador, cd)


def salvar_combatente(
    combatente: Combatente,
    atributo: str,
    cd: int,
    rng: Optional[random.Random] = None,
    vantagem: bool = False,
) -> ResultadoSave:
    """O save de um personagem. Quem não tem o atributo na ficha resiste com 0."""
    modificador = (combatente.saves or {}).get(atributo, 0)
    return salvar(
        combatente.nome, atributo, modificador, cd, rng, vantagem or combatente.vantagem
    )


def salvar_inimigo(
    inimigo: Inimigo,
    atributo: str,
    cd: int,
    rng: Optional[random.Random] = None,
    vantagem: bool = False,
) -> ResultadoSave:
    """O save de uma criatura, pela planilha dela ou pelo padrão provisório."""
    com_vantagem = vantagem or atributo in (inimigo.saves_vantagem or ())
    return salvar(inimigo.nome, atributo, inimigo.save(atributo), cd, rng, com_vantagem)


def atacar_inimigo(
    combatente: Combatente,
    inimigo: Inimigo,
    rng: Optional[random.Random] = None,
    dano_bonus: Optional[str] = None,
    garantido: bool = False,
    critico_forcado: bool = False,
    bonus_extra: int = 0,
) -> GolpeAtaque:
    """O personagem ataca um inimigo. O dano já sai descontado do HP dele."""
    extra = combatente.dano_extra
    if combatente.dano_ferido and esta_ferido(inimigo):
        extra += combatente.dano_ferido
    marcado = combatente.dano_por_alvo.get(inimigo.indice)
    vantagem = combatente.vantagem or inimigo.indice in combatente.vantagem_contra
    golpe = atacar(
        combatente.nome,
        combatente.bonus_ataque + bonus_extra,
        combatente.dano_arma,
        inimigo.nome,
        inimigo.ca,
        rng,
        critico_em=combatente.critico_em,
        dano_extra=extra,
        dano_bonus=dano_bonus or marcado,
        garantido=garantido,
        critico_forcado=critico_forcado,
        vantagem=vantagem,
    )
    # A marca soma junto com o dano bonus da propria habilidade.
    if dano_bonus and marcado and golpe.acertou:
        golpe.dano += rolar_dano(marcado, rng, critico=golpe.critico)
    if golpe.acertou:
        inimigo.hp_atual = max(0, inimigo.hp_atual - golpe.dano)
    return golpe


def sortear_alvo(
    estado: EstadoCombate, rng: Optional[random.Random] = None
) -> Optional[Combatente]:
    """Quem um inimigo ataca. Só quem está de pé pode ser alvo."""
    vivos = estado.vivos
    return _rng(rng).choice(vivos) if vivos else None


def sortear_alvos(
    estado: EstadoCombate, quantos: int, rng: Optional[random.Random] = None
) -> list[Combatente]:
    """Vários alvos diferentes, para habilidades que pegam mais de um.

    Quem já está atordoado não é sorteado enquanto houver alguém de pé sem
    atordoamento — atordoar duas vezes a mesma pessoa não faz nada.
    """
    vivos = estado.vivos
    if not vivos:
        return []
    preferidos = [c for c in vivos if not c.atordoado] or vivos
    gerador = _rng(rng)
    if quantos >= len(preferidos):
        escolhidos = list(preferidos)
        gerador.shuffle(escolhidos)
        return escolhidos
    return gerador.sample(preferidos, quantos)


def contra_atacar(
    inimigo: Inimigo, alvo: Combatente, rng: Optional[random.Random] = None
) -> GolpeAtaque:
    """Um inimigo revida contra um personagem. O dano já sai descontado do HP dele."""
    golpe = atacar(
        inimigo.nome, inimigo.ataque, inimigo.dano, alvo.nome, alvo.ca_efetiva, rng
    )
    if golpe.acertou:
        # Rage e companhia cortam o dano recebido antes de ele entrar no HP.
        sofrido = golpe.dano
        if alvo.reducao_dano:
            sofrido = max(1, int(round(sofrido * (1 - alvo.reducao_dano))))
            golpe.dano = sofrido
        golpe.absorvido, _ = absorver(alvo, sofrido)
    return golpe


@dataclass
class Investida:
    """Uma habilidade de criatura resolvida contra um personagem."""

    inimigo: str
    habilidade: str
    alvo: Combatente
    save: ResultadoSave
    dano: int = 0
    absorvido: int = 0
    atordoou: bool = False
    # Por quantas rodadas o alvo fica atordoado, quando fica.
    atordoa_por: int = 0
    # Se o alvo refaz o save no fim do turno para se livrar.
    repete_save: bool = False

    @property
    def escapou(self) -> bool:
        return self.save.passou


def usar_habilidade_do_inimigo(
    inimigo: Inimigo, estado: EstadoCombate, rng: Optional[random.Random] = None
) -> list[Investida]:
    """A criatura conjura em vez de atacar: cada alvo rola a resistência dela.

    Quem passa escapa inteiro; quem falha leva o dano (pela vida temporária
    primeiro, como qualquer golpe) e fica atordoado, se for o caso. Quem cai
    com o dano não fica atordoado — já está fora do combate.
    """
    habilidade = inimigo.habilidade
    if habilidade is None:
        return []
    investidas = []
    for alvo in sortear_alvos(estado, habilidade.alvos, rng):
        resultado = salvar_combatente(alvo, habilidade.save, habilidade.cd, rng)
        investida = Investida(inimigo.nome, habilidade.nome, alvo, resultado)
        if not resultado.passou:
            if habilidade.dano:
                sofrido = rolar_dano(habilidade.dano, rng)
                if alvo.reducao_dano:
                    sofrido = max(1, int(round(sofrido * (1 - alvo.reducao_dano))))
                investida.dano = sofrido
                investida.absorvido, _ = absorver(alvo, sofrido)
            # Atordoar quem ja esta atordoado nao renova nada: o alvo perde
            # uma rodada, nao uma sequencia infinita delas.
            if habilidade.atordoa and not alvo.caido and not alvo.atordoado:
                alvo.atordoado = True
                investida.atordoou = True
                investida.atordoa_por = habilidade.atordoa
                investida.repete_save = bool(habilidade.save_repete)
        investidas.append(investida)
    return investidas


@dataclass
class RodadaInimiga:
    """O que as criaturas fizeram na vez delas."""

    golpes: list[tuple[GolpeAtaque, Combatente]] = field(default_factory=list)
    investidas: list[Investida] = field(default_factory=list)

    @property
    def atingidos(self) -> list[Combatente]:
        """Quem teve HP ou THP mexido, sem repetir."""
        saida = []
        for _golpe, alvo in self.golpes:
            if alvo not in saida:
                saida.append(alvo)
        for investida in self.investidas:
            if investida.alvo not in saida:
                saida.append(investida.alvo)
        return saida


def rodada_dos_inimigos(
    estado: EstadoCombate, rng: Optional[random.Random] = None
) -> RodadaInimiga:
    """A vez dos inimigos: cada um de pé age uma vez.

    Quem tem habilidade pronta nesta rodada conjura em vez de atacar; o resto
    bate, tantas vezes quanto o multiataque permitir, cada golpe num alvo
    sorteado — o bot não faz tática, então não concentra tudo numa pessoa.
    É aqui que um grupo de criaturas pesa: cinco lobos batem cinco vezes por
    rodada. Para quando o grupo inteiro cai: não se ataca quem já está no chão.
    """
    rodada = RodadaInimiga()
    for inimigo in estado.inimigos_vivos:
        if inimigo.atordoado:
            continue  # perdeu a vez
        if not estado.vivos:
            break
        if inimigo.usa_habilidade(estado.rodada, rng):
            rodada.investidas.extend(usar_habilidade_do_inimigo(inimigo, estado, rng))
            continue
        for _ in range(max(1, inimigo.ataques)):
            alvo = sortear_alvo(estado, rng)
            if alvo is None:
                break
            rodada.golpes.append((contra_atacar(inimigo, alvo, rng), alvo))
    return rodada


def ganhar_thp(combatente: Combatente, quantidade: int) -> int:
    """Vida temporária não empilha: vale a maior. Devolve quanto ficou.

    Quem está caído não ganha THP — voltar a lutar é outra história.
    """
    if combatente.caido or quantidade <= 0:
        return combatente.thp
    combatente.thp = max(combatente.thp, quantidade)
    return combatente.thp


def absorver(combatente: Combatente, dano: int) -> tuple[int, int]:
    """Passa o dano pela vida temporária primeiro. Devolve (do THP, do HP)."""
    if dano <= 0:
        return 0, 0
    no_thp = min(combatente.thp, dano)
    combatente.thp -= no_thp
    no_hp = dano - no_thp
    combatente.hp_atual = max(0, combatente.hp_atual - no_hp)
    return no_thp, no_hp


def vale_esquivar(combatente: Combatente, dano: int, limiar: float) -> bool:
    """Se um golpe merece gastar a esquiva do combate.

    Gasta quando o golpe derrubaria, ou quando leva uma fatia grande do que
    resta — não faz sentido queimar o recurso num arranhão.
    """
    if dano <= 0:
        return False
    restante = combatente.hp_atual + combatente.thp
    return dano >= restante or dano >= max(1, int(restante * limiar))


def proxima_sequencia(pilha: int, acertou: bool, por_acerto: int, teto: int) -> int:
    """Martial Arts: acerto empilha até o teto, erro zera."""
    if not acertou:
        return 0
    return min(teto, pilha + por_acerto)


def curar(combatente: Combatente, fracao: float) -> int:
    """Cura uma fração do HP máximo, sem passar do teto. Devolve quanto curou.

    Não levanta caído: quem está em 0 HP está fora do combate, e voltar é
    assunto do descanso ou de uma habilidade que diga isso.
    """
    if combatente.caido:
        return 0
    antes = combatente.hp_atual
    combatente.hp_atual = min(combatente.hp_max, antes + max(1, int(combatente.hp_max * fracao)))
    return combatente.hp_atual - antes


# Quanto do HP máximo um personagem caído recupera ao descansar.
FRACAO_DESCANSO_CAIDO = 0.5


def aplicar_descanso(combatentes: list[Combatente]) -> list[str]:
    """Descanso: quem está de pé recupera tudo, quem caiu volta com metade.

    Devolve uma linha por personagem que mudou, para o embed da sala.
    """
    mudancas = []
    for c in combatentes:
        antes = c.hp_atual
        if c.caido:
            c.hp_atual = max(1, int(c.hp_max * FRACAO_DESCANSO_CAIDO))
            mudancas.append(f"{c.nome} volta a lutar com {c.hp_atual}/{c.hp_max} de HP")
        elif c.hp_atual < c.hp_max:
            c.hp_atual = c.hp_max
            mudancas.append(f"{c.nome} recupera {c.hp_max - antes} de HP ({c.hp_max}/{c.hp_max})")
    return mudancas
