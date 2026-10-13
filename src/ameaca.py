"""Ameaça: quem a criatura escolhe bater.

Sem isto o alvo é sorteado uniformemente, então não existe tanque — o mago
leva tanta pancada quanto o guerreiro de armadura pesada. A Ameaça dá a cada
personagem um peso nesse sorteio: a classe traz um valor inicial, que é a
posição dela na sala (quem bate de perto aparece primeiro), e habilidades
somam por cima.

O peso não é a ameaça crua. Ela passa pela curva de resistência, a mesma de
`x / (x + Y)` que os jogos usam para armadura:

    peso = x / (x + Y)

Isso dá retorno decrescente: cada ponto novo vale menos que o anterior, então
ninguém trava o combate stackando ameaça. Com Y = 10 e um grupo de cinco, o
guerreiro (ameaça 6) sai de 29,5% da atenção e, somando +3, +6 e +9, chega a
34,5%, 37,8% e 40,1% — os três degraus rendem +5,1, +3,3 e +2,3 pontos.

Y é o botão de calibragem, e ele anda ao contrário do que parece: **Y pequeno
achata** (todo mundo encosta no teto da curva) e **Y grande aproxima do stack
simples** (a curva fica reta). No limite, Y → ∞ é exatamente somar e dividir.

A escolha de manter a ameaça estável — inicial da classe mais o que estiver
ligado agora, em vez de acumular golpe a golpe — é o que deixa esta fórmula
funcionar. Ameaça que cresce a luta inteira satura: com 100/60/40 a mesma razão
5:3:2 daria 35,4/33,4/31,2, quase o sorteio uniforme de volta, e o tanque
deixaria de ser tanque conforme a luta durasse. Se um dia a ameaça passar a
acumular, a curva precisa virar `x ** k` com k < 1, que comprime igual mas não
satura.
"""
from __future__ import annotations

import random
from typing import Any, Iterable, Optional, Sequence, TypeVar

T = TypeVar("T")

# A constante da curva. Ver o cabeçalho: menor achata, maior aproxima do stack
# simples. Em 10 um "+3 de ameaça" move a atenção do grupo em ~5 pontos.
Y = 10

# Quanto cada classe atrai antes de qualquer habilidade. É a linha de frente
# virando número: o guerreiro e o paladino estão na cara do inimigo, o ladino
# ataca pelos lados e o xamã fica atrás. Não escala por tier — ameaça é o papel
# na sala, não o poder do personagem.
PADRAO = 3
AMEACA_INICIAL: dict[str, int] = {
    "guerreiro": 6,
    "paladino": 6,
    "barbaro": 5,
    "monge": 4,
    "patrulheiro": 3,
    "ladino": 2,
    "xama": 2,
    # Ainda sem tabela de números, mas já com a ameaça definida:
    "clerigo": 3,
    "artifice": 3,
    "druida": 2,
    "bardo": 2,
    "bruxo": 2,
    "feiticeiro": 2,
    "mago": 2,
}


def inicial(classe: Optional[str]) -> int:
    """A ameaça que a classe traz de fábrica. Classe desconhecida fica no meio."""
    return AMEACA_INICIAL.get(str(classe or "").strip().lower(), PADRAO)


def peso(x: int) -> float:
    """A ameaça crua na curva de retorno decrescente. Nunca negativa."""
    bruta = max(0, x)
    return bruta / (bruta + Y)


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
    return rng or random.SystemRandom()


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
