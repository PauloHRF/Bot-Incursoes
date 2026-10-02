"""O que cada tipo de sala faz com o grupo quando ele passa ou falha.

Módulo puro: decide, não grava. Devolve o nome da condição, o dano ou o prêmio,
e quem chama (o cog) é que persiste — ele é o único que tem banco.

O desenho por tipo de sala:

  Armadilha  passou: atravessa e pronto (a CD dela já vem com desconto, em
             `incursoes.DESCONTO_CD_ARMADILHA`).
             falhou: **Dano** (-20% do HP) mais um debuff de Armadilha
             sorteado — é o "Dano e Debuffs" da regra.
  Evento     passou: um **prêmio** sorteado entre os 12 buffs do catálogo, a
             Cura e a Graça. Sorteia só entre os que fazem diferença agora.
             falhou: um debuff de Evento ou um ponto de Exaustão.
  Tesouro    passou: o texto de recompensa da sala (os itens vivem na planilha
             do grupo, não no bot).
             falhou: nada, e uma chance de acordar Mímicos.
  Descanso   cura uma fatia e cada um limpa uma condição sua (ver o cog).

Cura, Dano e Graça não viram condição: não têm stack nem prazo, acontecem na
hora. Os números delas estão aqui.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Iterable, Optional

from . import condicoes

# As duas linhas de HP da planilha: Cura (+20%) e Dano (-20%), do HP máximo.
CURA_PCT = 20
DANO_PCT = 20

# Chance de falhar num Tesouro acordar Mímicos.
CHANCE_DE_MIMICO = 0.35

# Quantos Mímicos aparecem quando acordam.
MIMICOS = 2
NOME_DO_MIMICO = "Mímico"

# Os prêmios de Evento que não são buff com stack.
CURA = "cura"
GRACA = "graca"
NOME_DA_GRACA = "Graça"


@dataclass
class Desfecho:
    """O que a sala deixou no grupo, já em texto pronto para o embed.

    `mimicos` diz que a sala virou combate em vez de devolver o grupo à
    votação; `fora` lista quem bateu no teto de uma condição e saiu.
    """

    linhas: list[str] = field(default_factory=list)
    mimicos: bool = False
    fora: list[str] = field(default_factory=list)

    @property
    def vazio(self) -> bool:
        return not (self.linhas or self.mimicos or self.fora)


def _rng(rng: Optional[random.Random]) -> random.Random:
    return rng or random


def dano_da_armadilha(hp_max: int) -> int:
    """O Dano da planilha: -20% do HP máximo. Nunca menos de 1."""
    return max(1, (hp_max * DANO_PCT) // 100)


def cura_do_evento(hp_max: int) -> int:
    """A Cura da planilha: +20% do HP máximo. Nunca menos de 1."""
    return max(1, (hp_max * CURA_PCT) // 100)


def debuff_da_armadilha(rng: Optional[random.Random] = None) -> str:
    """Qual debuff de Armadilha a falha deixa, além do Dano."""
    return _rng(rng).choice(condicoes.DEBUFFS_DE_ARMADILHA)


def castigo_do_evento(rng: Optional[random.Random] = None) -> str:
    """O que um Evento perdido deixa: um debuff de Evento ou Exaustão."""
    return _rng(rng).choice(condicoes.DEBUFFS_DE_EVENTO)


def premio_do_evento(
    tem_debuff: bool = False,
    tem_machucado: bool = False,
    rng: Optional[random.Random] = None,
) -> str:
    """O prêmio de um Evento vencido: um dos 12 buffs, a Cura ou a Graça.

    Sorteia só entre o que faz diferença: não oferece Graça a um grupo limpo
    nem Cura a um grupo inteiro. Os buffs são sempre candidatos — é o piso.
    """
    opcoes: list[str] = list(condicoes.BUFFS)
    if tem_debuff:
        opcoes.append(GRACA)
    if tem_machucado:
        opcoes.append(CURA)
    return _rng(rng).choice(opcoes)


def a_limpar(carregadas: dict[str, int], tipos: Iterable[str]) -> tuple[str, ...]:
    """As condições do personagem que são de um destes tipos e podem sair."""
    return tuple(
        cid
        for cid, stacks in sorted(carregadas.items())
        if stacks > 0 and (c := condicoes.POR_ID.get(cid)) and c.tipo in tipos
    )


def sortear_para_limpar(
    por_personagem: dict[int, dict[str, int]],
    tipos: Iterable[str],
    rng: Optional[random.Random] = None,
    quantas: int = 1,
) -> list[tuple[int, str]]:
    """Sorteia até `quantas` pares (personagem, condição) para limpar.

    Sorteia no conjunto achatado, não o personagem primeiro: assim quem carrega
    mais coisa tem mais chance de ser aliviado, que é o que a mesa espera. É
    também a regra da Graça — cada stack dela pode tirar de outro personagem
    ou outro debuff, então o sorteio é sem reposição no conjunto todo.
    """
    candidatos = [
        (user_id, cid)
        for user_id, carregadas in sorted(por_personagem.items())
        for cid in a_limpar(carregadas, tipos)
    ]
    if not candidatos:
        return []
    gerador = _rng(rng)
    quantas = max(1, min(quantas, len(candidatos)))
    return gerador.sample(candidatos, quantas)


def acordou_mimico(rng: Optional[random.Random] = None) -> bool:
    """A falha no Tesouro acordou o que estava fingindo ser um baú?"""
    return _rng(rng).random() < CHANCE_DE_MIMICO
