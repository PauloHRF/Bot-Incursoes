"""Ameaça: quem a criatura escolhe bater.

Sem isto o alvo é sorteado uniformemente, então não existe tanque — o mago
leva tanta pancada quanto o guerreiro de armadura pesada. A Ameaça dá a cada
personagem um peso nesse sorteio, e esse peso vem de quatro partes:

  - a INICIAL da classe, que é a posição dela na sala: quem bate de perto
    aparece primeiro;
  - o que as habilidades LIGADAS somam enquanto duram;
  - o que o personagem GEROU agindo, que acumula do primeiro golpe ao fim do
    combate e morre com a sala;
  - o bônus de quem está FERIDO, que é a criatura indo terminar o serviço.

A terceira é a que dá história ao combate: quem bate, cura e conjura vai
chamando atenção, e a criatura troca de alvo conforme a luta anda.

O peso não é a ameaça crua. Ela passa por uma curva de retorno decrescente:

    peso = x ** K,  com K = 0.5

Cada ponto novo vale menos que o anterior, então ninguém trava o combate
stackando ameaça. Num grupo de cinco — guerreiro 12, paladino 10, clérigo 6,
mago 4, ladino 2 — o guerreiro abre com 27,7% da atenção e o ladino com
11,3%, contra os 20% do sorteio uniforme.

**Os valores da inicial só importam como RAZÃO.** A potência normalizada
cancela qualquer fator comum — `12/10/8/6/4/2` e `6/5/4/3/2/1` dão exatamente
a mesma distribuição —, então o tamanho absoluto da escala só importa contra
o que é SOMADO por cima: o `+3` de quem está ferido, o `+6` do Reckless
Attack e os pontos de ação. Dobrar a escala sem dobrar esses é enfraquecê-los
em silêncio.

É `x ** K`, e não o `x / (x + Y)` que os jogos usam para armadura, porque a
ameaça ACUMULA. A fórmula de armadura satura: ela tem teto em 1, e com
100/60/40 a razão 5:3:2 virava 35,4/33,4/31,2 — quase o sorteio uniforme de
volta, e o tanque deixava de ser tanque conforme a luta durasse. A potência
comprime igual embaixo e não tem teto: os mesmos 100/60/40 dão
41,5/32,2/26,3, que ainda é um tanque.

K é o botão de calibragem, e anda ao contrário do que parece: **K pequeno
achata** (tudo encosta em 1) e **K = 1 é o stack simples**, somar e dividir.
"""
from __future__ import annotations

import random
from typing import Any, Iterable, Optional, Sequence, TypeVar

from . import aleatorio

T = TypeVar("T")

# O expoente da curva. Ver o cabeçalho: menor achata, 1 é o stack simples.
# Em 0,5 um "+3 de ameaça" move a atenção de um grupo de cinco em ~4 pontos.
K = 0.5

# Quanto cada classe atrai antes de qualquer habilidade. É a linha de frente
# virando número: quem fecha a porta está na cara do inimigo, e o ladino ataca
# pelos lados. Não escala por tier — ameaça é o papel na sala, não o poder do
# personagem.
#
# SEIS grupos, e não os três de antes. Com cinco classes empatadas no piso,
# metade da ficha era a mesma pessoa para a criatura: ladino, mago, bardo,
# bruxo, druida, feiticeiro e xamã tinham todos 2, e o combate não distinguia
# o druida de urso do mago atrás da coluna. Os degraus abrem a janela de
# 20–30% para 20–38%.
GRUPOS: tuple[tuple[int, tuple[str, ...]], ...] = (
    (12, ("guerreiro", "barbaro")),
    (10, ("paladino",)),
    (8, ("druida", "xama", "patrulheiro")),
    (6, ("monge", "clerigo", "bruxo")),
    (4, ("artifice", "mago", "feiticeiro", "bardo")),
    (2, ("ladino",)),
)
AMEACA_INICIAL: dict[str, int] = {
    classe: valor for valor, nomes in GRUPOS for classe in nomes
}
# Classe desconhecida fica no meio da escala, que é o quarto grupo.
PADRAO = 6

# Quem está por cair chama mais atenção: a criatura vai terminar o serviço.
#
# PONTOS FIXOS, e não uma fração da inicial dele. Por ser plano, o bônus
# empurra muito mais quem tem ameaça baixa — o ladino sai de 20% para 28,3%
# da atenção, o guerreiro de 38% para 40,6% —, e é exatamente isso que se
# quer: a criatura abandona o tanque inteiro para ir no mago sangrando.
# Proporcional faria o contrário, somando mais em quem já era o alvo.
LIMIAR_DE_FERIDO = 0.30
AMEACA_DE_FERIDO = 3


def inicial(classe: Optional[str]) -> int:
    """A ameaça que a classe traz de fábrica. Classe desconhecida fica no meio."""
    return AMEACA_INICIAL.get(str(classe or "").strip().lower(), PADRAO)


def de_ferido(hp_atual: int, hp_max: int) -> int:
    """Os pontos a mais de quem está abaixo do limiar de vida.

    Quem está no chão não entra: ele já saiu do sorteio por outro caminho, e
    somar ameaça a um caído só poluiria a linha do painel.
    """
    if hp_atual <= 0 or hp_max <= 0:
        return 0
    return AMEACA_DE_FERIDO if hp_atual <= hp_max * LIMIAR_DE_FERIDO else 0


# A regra cabe numa frase: **cada ação gera a ameaça da própria classe, em
# dobro se for área ou cura**. Esta tabela é só o "em dobro" — o multiplicador
# do valor da classe, por tipo de ação.
#
# Cura dobra porque é o motivo clássico de o curandeiro precisar de alguém na
# frente dele; área dobra porque acertar cinco criaturas é mais notável que
# acertar uma.
#
# Multiplicar o valor da CLASSE, em vez de somar um valor fixo igual para
# todos, é o que mantém o tanque de pé: as razões entre o grupo quase não
# mudam ao longo do combate, e a deriva vem só de quem faz o quê. Somar fixo
# diluiria a inicial — em três rodadas o mago que estoura área passaria o
# guerreiro, e o combate voltaria a focar justamente quem não aguenta.
#
# O valor é DECLARADO, e não o dano feito: o jogador precisa saber de antemão
# o que chama atenção, e ameaça-por-dano faria o mesmo golpe valer o dobro só
# por ter critado.
DOBRA_A_AMEACA = ("cura", "grupo", "area")


def gerada_por(classe: Optional[str], acao: Optional[dict] = None) -> int:
    """Quanta ameaça quem acabou de agir acrescenta à conta dele.

    Uma habilidade pode declarar `ameaca_gerada` e pular a regra inteira,
    classe e tudo. É o gancho para uma provocação de verdade.
    """
    acao = acao or {}
    declarada = acao.get("ameaca_gerada")
    if declarada is not None:
        return max(0, int(declarada))
    tipo = acao.get("tipo") or "golpes"
    if tipo == "save" and acao.get("alvos") == "todos":
        tipo = "area"
    return inicial(classe) * (2 if tipo in DOBRA_A_AMEACA else 1)


def peso(x: int) -> float:
    """A ameaça crua na curva de retorno decrescente. Nunca negativa."""
    return max(0, x) ** K


def fracoes(
    ameacas: Sequence[int], fatores: Optional[Sequence[float]] = None
) -> list[float]:
    """A fatia da atenção de cada um, somando 1.

    `fatores` multiplica o peso já curvado, e não a ameaça crua. É o que o Fly
    usa: a curva é quase reta embaixo — `peso(1)` e `peso(2)` estão a 1,8x de
    distância —, então mexer na ameaça só dá "modesto" ou "imune". No peso o
    fator é um botão de verdade: 0,2 tira de alcance sem tornar invulnerável.

    Todos em zero (ou lista vazia de peso) caem no uniforme: sem ameaça
    nenhuma, a criatura não tem motivo para preferir alguém.
    """
    if not ameacas:
        return []
    pesos = [peso(x) for x in ameacas]
    if fatores is not None:
        pesos = [p * max(0.0, f) for p, f in zip(pesos, fatores)]
    total = sum(pesos)
    if total <= 0:
        return [1 / len(ameacas)] * len(ameacas)
    return [p / total for p in pesos]


def porcentagens(
    ameacas: Sequence[int], fatores: Optional[Sequence[float]] = None
) -> list[float]:
    """As frações em pontos percentuais, para mostrar na ficha e no painel."""
    return [f * 100 for f in fracoes(ameacas, fatores)]


def _rng(rng: Optional[random.Random]) -> Any:
    return aleatorio.gerador(rng)


def sortear(
    itens: Sequence[T],
    ameacas: Sequence[int],
    rng: Optional[random.Random] = None,
    fatores: Optional[Sequence[float]] = None,
) -> Optional[T]:
    """Um alvo, sorteado com a ameaça como peso."""
    escolhidos = sortear_varios(itens, ameacas, 1, rng, fatores)
    return escolhidos[0] if escolhidos else None


def sortear_varios(
    itens: Sequence[T],
    ameacas: Sequence[int],
    quantos: int,
    rng: Optional[random.Random] = None,
    fatores: Optional[Sequence[float]] = None,
) -> list[T]:
    """Vários alvos diferentes, sorteados com a ameaça como peso.

    Sem reposição: quem já foi escolhido sai do bolo, e os pesos dos que
    sobraram são renormalizados. Pedindo tudo (ou mais), devolve todos — mas
    embaralhados pela ameaça, porque a ordem decide quem leva o quê quando a
    habilidade resolve alvo por alvo.
    """
    pesados = fatores if fatores is not None else [1.0] * len(ameacas)
    restantes = list(zip(itens, ameacas, pesados))
    gerador = _rng(rng)
    escolhidos: list[T] = []
    while restantes and len(escolhidos) < max(0, quantos):
        escolhidos.append(restantes.pop(_qual(restantes, gerador))[0])
    return escolhidos


# O sorteio sai de `randint`, e não de `random()`, porque é a única primitiva
# que o resto do bot usa — e a única que os dados dos testes sabem fingir.
# Fatiar 1 em dez mil deixa o arredondamento muito abaixo de um ponto
# percentual, que é a resolução que a ficha mostra.
PRECISAO = 10_000


def _qual(restantes: Sequence[tuple[Any, int, float]], gerador: Any) -> int:
    """A posição sorteada entre os que sobraram, com a ameaça como peso."""
    fatias = [
        round(f * PRECISAO)
        for f in fracoes(
            [x for _, x, _ in restantes], [g for _, _, g in restantes]
        )
    ]
    total = sum(fatias)
    if total <= 0:
        return 0
    sorteado = gerador.randint(1, total)
    acumulado = 0
    for posicao, fatia in enumerate(fatias):
        acumulado += fatia
        if sorteado <= acumulado:
            return posicao
    return len(restantes) - 1


def de_quem(combatentes: Iterable[Any]) -> list[int]:
    """A ameaça de cada combatente, para passar junto com a lista deles."""
    return [getattr(c, "ameaca_total", 0) for c in combatentes]


def fatores_de(combatentes: Iterable[Any]) -> list[float]:
    """O multiplicador de peso de cada um — o Fly, por enquanto."""
    return [float(getattr(c, "ameaca_fator", 1.0)) for c in combatentes]
