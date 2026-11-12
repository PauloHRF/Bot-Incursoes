"""Quem senta na mesa quando uma sala é medida.

Medir com cinco cópias da mesma classe dava um número que nunca vai
acontecer: não existe mesa de cinco guerreiros. E o número dependia de QUAL
classe — a mesma sala sai fácil contra uma linha de paladinos e letal contra
uma de magos —, então quem escolhia a classe escolhia a resposta sem saber.

Aqui a sala é medida contra VÁRIAS mesas sorteadas. O que volta é a média
mais os extremos, porque são duas perguntas diferentes:

- a média responde "esta sala é justa?";
- a pior composição responde "existe mesa que ela mata?" — e é essa que
  esconde o problema, porque some na média.

POR QUE EM COMPOSIÇÕES, e não uma mesa nova a cada luta. Primeiro porque
montar a mesa custa um banco em memória com os personagens gravados, e
refazer isso a cada luta pagaria o preço do banco em vez do combate. Mas
sobretudo porque **uma luta por composição não mede composição nenhuma**:
para dizer "este grupo venceu 41%" é preciso tê-lo medido várias vezes. As
repetições são divididas entre N mesas, e cada uma leva o mesmo número de
lutas.

COM REPOSIÇÃO, de propósito: duas mesas com dois bárbaros existem, e uma
mesa sem curandeiro nenhum é justamente o caso que o autor precisa ver. O
degenerado — as cinco iguais, que é o que estamos saindo de — tem chance de
uma em quatorze mil por composição, então ele não volta pela porta dos
fundos.
"""
from __future__ import annotations

import random
from typing import Iterable

from src import classes

from .execucao import Ficha

# Quantas mesas diferentes medir, quando cabe. Doze cobre bem o espaço sem
# fatiar a amostra a ponto de nenhuma composição ter número próprio.
COMPOSICOES_PADRAO = 12

# E o piso de lutas por mesa. Abaixo disto a taxa de UMA composição é ruído:
# dizer "esta mesa venceu 40%" com cinco lutas é inventar um dígito. Quando a
# amostra é pequena demais para doze mesas, mede-se menos mesas — nunca mesas
# com menos lutas.
MINIMO_POR_COMPOSICAO = 15


def dividir(repeticoes: int, quantas: int = COMPOSICOES_PADRAO) -> tuple[int, int]:
    """Quantas mesas medir e quantas lutas cada uma leva.

    Devolve `(mesas, lutas_por_mesa)`. O produto pode ficar abaixo de
    `repeticoes` — sobra que não dá uma luta inteira para cada mesa é
    descartada, e não jogada numa mesa só, senão uma composição pesaria mais
    que as outras na média sem nada dizer a respeito.
    """
    if repeticoes < 1 or quantas < 1:
        raise ValueError("Repetições e composições precisam ser positivas.")
    por_mesa = max(MINIMO_POR_COMPOSICAO, repeticoes // quantas)
    return max(1, repeticoes // por_mesa), por_mesa


def sortear(
    tamanho: int, nivel: int, quantas: int, rng: random.Random
) -> list[tuple[Ficha, ...]]:
    """`quantas` mesas de `tamanho` jogadores, sorteadas entre as classes.

    O mesmo `rng` dá as mesmas mesas: é o que deixa dois autores comparando
    números verem o mesmo número, e é por isso que a semente da medição
    aparece na resposta.
    """
    if tamanho < 1:
        raise ValueError("A mesa precisa de pelo menos um jogador.")
    nomes = sorted(classes.CLASSES)
    return [
        tuple(Ficha(rng.choice(nomes), nivel) for _ in range(tamanho))
        for _ in range(max(1, quantas))
    ]


def nomes_da_mesa(mesa: Iterable[Ficha]) -> list[str]:
    """As classes da mesa, ordenadas — é como ela aparece na tela."""
    return sorted(f.classe for f in mesa)
