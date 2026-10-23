"""A vitrine do mercado: o que está à venda, para quem e nesta semana.

Nada aqui é guardado. A prateleira é **derivada** de (personagem, semana) por
um sorteio semeado, que é a mesma escolha que a ficha já faz ao derivar CA e
dano da classe em vez de gravá-los: o que é derivado não envelhece. Em troca
disso o bot não precisa de tabela de estoque, nem de rotina em segundo plano
para repor a loja, nem de quem lembre de rodá-la.

A semana vira na **segunda-feira**, porque é quando a vaga de incursão já
vira (`motor.virada_da_vaga`). Ter dois calendários no mesmo jogo seria pedir
confusão: na segunda o grupo ganha vaga nova e vitrine nova.

A vitrine é **por personagem**: dois jogadores na mesma semana veem
prateleiras diferentes, e o mesmo jogador com dois personagens também. Quem
quer o item lendário não pede para o outro comprar — ou ele saiu na sua
semana, ou não saiu.
"""
from __future__ import annotations

import random
from datetime import date, datetime
from typing import Iterable, Optional, Sequence

from . import itens

# Quantas vagas a prateleira tem. Seis dá escolha de verdade sem virar lista
# infinita, e com 35 peças no catálogo a repetição entre semanas é rara.
VAGAS = 6

# Entra na semente junto com personagem e semana. Mudar este número embaralha
# todas as vitrines de uma vez — é o botão de "nova temporada".
TEMPERO = "incursoes-mercado-v1"


# ------------------------------------------------------------------- o ouro
#
# Escala por tier, porque o preço não escala: um gibão custa 80 para o tier 1
# e para o tier 5, e é o ganho por sala que precisa acompanhar o personagem.
# A sala paga o passo e a incursão paga o fecho — assim desistir no meio rende
# menos do que terminar, sem precisar de penalidade nenhuma.
#
# Na conta de hoje, um tier 3 tira 15 por sala; uma incursão Média de 12 salas
# mais o fecho dá 240, que é três peças comuns ou um quarto de uma lendária.
# São duas constantes: recalibrar a economia é mexer aqui.
OURO_POR_SALA = 5
OURO_POR_INCURSAO = 20


def ouro_da_sala(tier: int) -> int:
    """O que uma sala superada paga a cada um que estava nela."""
    return OURO_POR_SALA * max(1, tier)


def ouro_da_incursao(tier: int) -> int:
    """O bônus de fechar a incursão, pago a quem chegou ao fim."""
    return OURO_POR_INCURSAO * max(1, tier)


def semana_de(quando: datetime | date) -> str:
    """A semana ISO daquele instante, como '2026-W43'.

    A semana ISO começa na segunda, que é exatamente a virada que o intervalo
    de incursão já usa. Devolve texto porque é o que vai na semente e no
    rodapé da vitrine, e texto não depende de fuso na comparação.
    """
    dia = quando.date() if isinstance(quando, datetime) else quando
    ano, numero, _dia_da_semana = dia.isocalendar()
    return f"{ano}-W{numero:02d}"


def semente(personagem_id: int, semana: str) -> str:
    return f"{TEMPERO}:{personagem_id}:{semana}"


def _sortear_sem_reposicao(
    pecas: Sequence[itens.Item], quantos: int, gerador: random.Random
) -> list[itens.Item]:
    """Tira `quantos` itens diferentes do bolo, com a raridade como peso.

    Sem reposição: quem saiu deixa o bolo e os pesos dos que ficaram são
    renormalizados. É o mesmo desenho de `ameaca.sortear_varios`, e pela mesma
    razão — sai de `randint`, e não de `random()`, que é a única primitiva que
    o resto do bot usa.
    """
    restantes = list(pecas)
    escolhidos: list[itens.Item] = []
    while restantes and len(escolhidos) < max(0, quantos):
        total = sum(p.peso for p in restantes)
        if total <= 0:
            escolhidos.append(restantes.pop(0))
            continue
        sorteado = gerador.randint(1, total)
        acumulado = 0
        for posicao, peca in enumerate(restantes):
            acumulado += peca.peso
            if sorteado <= acumulado:
                escolhidos.append(restantes.pop(posicao))
                break
        else:
            escolhidos.append(restantes.pop())
    return escolhidos


def vitrine(
    personagem_id: int,
    semana: str,
    catalogo: Optional[Iterable[itens.Item]] = None,
    vagas: int = VAGAS,
) -> list[itens.Item]:
    """O que aquele personagem vê à venda naquela semana.

    Determinístico: a mesma dupla devolve a mesma prateleira, chamada quantas
    vezes for. É isso que deixa a vitrine existir sem ser guardada — recarregar
    a mensagem do Discord não embaralha a loja debaixo de quem está comprando.

    A ordem de saída é a do sorteio, não a do catálogo, então a prateleira
    muda de cara de semana para semana mesmo quando duas peças se repetem.
    """
    bolo = list(catalogo if catalogo is not None else itens.CATALOGO)
    gerador = random.Random(semente(personagem_id, semana))
    return _sortear_sem_reposicao(bolo, vagas, gerador)


def esta_na_vitrine(personagem_id: int, semana: str, item_id: str) -> bool:
    """Se aquele item está à venda para aquele personagem nesta semana.

    Quem compra manda o id, e o id pode vir de uma mensagem da semana passada
    — então a compra confere a prateleira de hoje em vez de confiar no botão.
    """
    return any(p.id == item_id for p in vitrine(personagem_id, semana))


__all__ = [
    "OURO_POR_INCURSAO", "OURO_POR_SALA", "TEMPERO", "VAGAS",
    "esta_na_vitrine", "ouro_da_incursao", "ouro_da_sala", "semana_de",
    "semente", "vitrine",
]
