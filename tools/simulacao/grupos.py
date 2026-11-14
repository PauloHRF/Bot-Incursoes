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

O QUE O NÚMERO DE MESAS CUSTA, e que custou caro descobrir: o sorteio é ele
próprio uma amostra. Entre mesas, a taxa do MESMO combate vai de 0% a 100%,
então a média de uma dúzia delas carrega cerca de dez pontos de erro — o
mesmo elenco mediu 57,5% com um sorteio e 32,5% com outro. Doze mesas servem
para olhar uma sala na bancada, onde o que se quer é a ordem de grandeza e a
pior mesa. Para CALIBRAR, não servem: `tools/calibrar_emboscada.py` sorteia
quarenta, e quem for escrever número que vai para o jogo deve fazer o mesmo.
"""
from __future__ import annotations

import random
import statistics
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

# O piso de quem só publica a MÉDIA. Ver `dividir`: o número de uma mesa
# precisa de quinze lutas, a média do conjunto não — e para a média o sorteio
# das mesas é a maior fonte de erro, então trocar lutas por mesas é compra
# boa. Dez é onde a conta ainda fecha para quem queira dar uma olhada no
# detalhe sem acreditar nele.
MINIMO_PARA_A_MEDIA = 10


def dividir(
    repeticoes: int,
    quantas: int = COMPOSICOES_PADRAO,
    minimo: int = MINIMO_POR_COMPOSICAO,
) -> tuple[int, int]:
    """Quantas mesas medir e quantas lutas cada uma leva.

    Devolve `(mesas, lutas_por_mesa)`. O produto pode ficar abaixo de
    `repeticoes` — sobra que não dá uma luta inteira para cada mesa é
    descartada, e não jogada numa mesa só, senão uma composição pesaria mais
    que as outras na média sem nada dizer a respeito.

    **Mais repetições compram lutas por mesa, não mesas.** Com `quantas` em
    doze e o piso em quinze, 200 repetições dão 12×16 e 600 dão 12×50: o
    número de mesas não se move, e o sorteio das mesas é justamente a maior
    fonte de erro da média. Quem quer reduzir ESSE erro precisa pedir mais
    `quantas` — foi o que o calibrador da emboscada aprendeu, e por isso ele
    pede quarenta.

    `minimo` é o piso de lutas por mesa, e ele existe para proteger o número
    DE UMA MESA. Quem publica só a média pode baixá-lo (`MINIMO_PARA_A_MEDIA`)
    e comprar mesas com as mesmas lutas, que é melhor negócio: o erro da média
    cai com a raiz do número de mesas, e não com o de lutas por mesa.
    """
    if repeticoes < 1 or quantas < 1 or minimo < 1:
        raise ValueError("Repetições, composições e mínimo precisam ser positivos.")
    por_mesa = max(minimo, repeticoes // quantas)
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


def mesa_azarada(composicoes) -> float:
    """A taxa no DÉCIMO PERCENTIL: "uma mesa em dez vai pior que isto".

    E não o mínimo, que é o que se pega primeiro. O mínimo de uma amostra
    afunda conforme a amostra cresce — quanto mais mesas se sorteia, maior a
    chance de tirar uma péssima —, então o pior de quarenta sorteios não é
    comparável ao pior de doze. A MESMA emboscada "piorou" de 93% para 80%
    só porque foi medida com mais mesas, sem nada ter mudado nela.

    O percentil estima a mesma coisa para qualquer número de sorteios, e é
    por isso que ele serve para comparar duas medições e para entrar num
    veredito. O mínimo continua útil para MOSTRAR — a bancada nomeia a pior
    mesa e diz em quantas lutas ela foi medida —, mas mostrar e decidir são
    coisas diferentes.
    """
    taxas = sorted(c["taxa"] for c in composicoes)
    if len(taxas) < 2:
        return taxas[0] if taxas else 1.0
    return statistics.quantiles(taxas, n=10)[0]
