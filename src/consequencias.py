"""O que cada tipo de sala faz com o grupo quando ele passa ou falha.

Módulo puro: decide, não grava. Devolve o nome da condição, o dano ou o prêmio,
e quem chama (o cog) é que persiste — ele é o único que tem banco.

O desenho por tipo de sala:

  Armadilha  passou: atravessa e pronto (a CD dela já vem com desconto, em
             `incursoes.DESCONTO_CD_ARMADILHA`).
             falhou: **Dano** (-35% do HP) mais um debuff de Armadilha
             sorteado — é o "Dano e Debuffs" da regra.
  Evento     passou: um **prêmio** sorteado entre os 12 buffs do catálogo, a
             Cura e a Graça. Sorteia só entre os que fazem diferença agora.
             falhou: um debuff de Evento ou um ponto de Exaustão.
  Tesouro    passou: o texto de recompensa da sala (os itens vivem na planilha
             do grupo, não no bot).
             falhou: os Mímicos acordam, e a sala vira combate.
  Descanso   cura uma fatia e cada um limpa uma condição sua (ver o cog).

Cura, Dano e Graça não viram condição: não têm stack nem prazo, acontecem na
hora. Os números delas estão aqui.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Iterable, Optional

from . import aleatorio, condicoes

# As duas linhas de HP da planilha: Cura (+20%) e Dano (-35%), do HP máximo.
# A Cura e o Dano deixaram de ser simétricos de propósito: falhar numa
# Armadilha custava um quinto do HP e isso fazia a sala ser votada como
# atalho barato. A Armadilha já é a sala com a CD mais fácil do caminho
# (ver DESCONTO_CD_ARMADILHA) — se ela também doer pouco ao falhar, passar
# nela deixa de importar.
CURA_PCT = 20
DANO_PCT = 35

# Falhar num Tesouro acorda Mímicos SEMPRE. A constante fica em 1.0 e não
# some para o número continuar num lugar só — e porque voltar a sortear é
# mudar este 1.0, e não reescrever a sala.
CHANCE_DE_MIMICO = 1.0

# Quem aparece quando os Mímicos acordam, tier por tier.
#
# Nada é esticado por multiplicador aqui, como em nenhuma outra sala. E o
# Mímico sozinho não dá conta de todos os tiers: ele é CR 2 e satura — seis
# deles deixam 85% do HP de um grupo de tier 3 e 93% de um de tier 4. Do tier
# 3 para cima o baú tem companhia, e quem dá o peso é quem morava com ele: o
# Xorn come metal e pedra preciosa, a Naga Guardiã guarda tesouro e o Golem de
# Pedra é guardião de câmara. A ficção é a mesma — o tesouro era isca.
#
# Medido com a mesa de cinco no nível do tier, 300 combates por linha, mirando
# o que uma sala do caminho deve cobrar (vitória ≥ 95%, HP restante 55–75%):
#   T1 3 Mímicos (65% do HP sobra)   T2 5 Mímicos (70%)
#   T3 2 Mímicos + 2 Xorn (60%)      T4 1 Mímico + 2 Nagas Guardiãs (60%)
#   T5 1 Mímico + 2 Golens de Pedra (67%)
NOME_DO_MIMICO = "Mímico"
A_EMBOSCADA: dict[int, tuple[tuple[str, int], ...]] = {
    1: ((NOME_DO_MIMICO, 3),),
    2: ((NOME_DO_MIMICO, 5),),
    3: ((NOME_DO_MIMICO, 2), ("Xorn", 2)),
    4: ((NOME_DO_MIMICO, 1), ("Naga Guardiã", 2)),
    5: ((NOME_DO_MIMICO, 1), ("Golem de Pedra", 2)),
}


def emboscada_do_tier(tier: Optional[int] = None) -> tuple[tuple[str, int], ...]:
    """Quem acorda com o baú, no tier da incursão.

    Sem tier declarado vale o tier 1: a emboscada é consequência de uma falha,
    e errar para o lado leve é melhor que dizimar um grupo por falta de dado.
    """
    escritos = sorted(A_EMBOSCADA)
    if not tier:
        return A_EMBOSCADA[escritos[0]]
    if tier in A_EMBOSCADA:
        return A_EMBOSCADA[tier]
    abaixo = [t for t in escritos if t <= tier]
    return A_EMBOSCADA[abaixo[-1] if abaixo else escritos[0]]

# ------------------------------------------------- o descanso duro
#
# A parada que a Longa traz depois da sexta sala. O descanso normal é sempre o
# mesmo e por isso nem é votado; este é uma ESCOLHA, com três trocas sorteadas
# do catálogo abaixo e decididas pela maioria, como uma sala.
#
# Toda troca é "cura mais, e cobra" — menos a primeira, que é a opção de quem
# chegou inteiro e não quer dever nada. A Exaustão é a moeda cara: ela não
# decai com o combate, só sai no descanso normal, e em 5 pontos tira o
# personagem da incursão.
TROCAS_POR_DESCANSO = 3


@dataclass(frozen=True)
class Troca:
    """Uma escolha do descanso duro: o que ela cura e o que ela cobra."""

    id: str
    nome: str
    texto: str
    # Fração do HP máximo que cada um recupera.
    cura_pct: int = 0
    # Vida temporária, também em fração do HP máximo.
    thp_pct: int = 0
    # Pontos de Exaustão em cada um do grupo.
    exaustao: int = 0
    # Tira TODO debuff de TODO mundo (a Exaustão não é debuff e fica).
    limpa_debuffs: bool = False
    # Paga ao grupo o ouro de uma sala superada.
    ouro_de_sala: bool = False
    # Dá ao grupo inteiro um dos 12 buffs do catálogo, sorteado.
    buff: bool = False


CATALOGO_DE_TROCAS: tuple[Troca, ...] = (
    Troca("folego", "Recuperar o fôlego",
          "Cura **20%** do HP máximo e dá **10%** de vida temporária. "
          "Não cobra nada.",
          cura_pct=20, thp_pct=10),
    Troca("marcha", "Forçar a marcha",
          "Cura **40%**, e cada um leva **1 ponto de Exaustão**.",
          cura_pct=40, exaustao=1),
    Troca("reservas", "Queimar as reservas",
          "Cura **50%**, e cada um leva **2 pontos de Exaustão**.",
          cura_pct=50, exaustao=2),
    Troca("feridas", "Lavar as feridas",
          "Cura só **10%**, e tira **todos os debuffs** do grupo. "
          "A Exaustão não é debuff e fica.",
          cura_pct=10, limpa_debuffs=True),
    Troca("revirar", "Revirar o lugar",
          "Cura **15%**, e o grupo leva o ouro de **uma sala** por ter "
          "procurado em vez de dormir.",
          cura_pct=15, ouro_de_sala=True),
    Troca("velar", "Velar os mortos",
          "Não cura ninguém, e o grupo inteiro sai com **um buff** da tabela.",
          buff=True),
)

TROCA_POR_ID = {t.id: t for t in CATALOGO_DE_TROCAS}


def trocas_oferecidas(
    quantas: int = TROCAS_POR_DESCANSO, rng: Optional[random.Random] = None
) -> list[Troca]:
    """As trocas que este descanso duro põe na mesa, sorteadas sem repetição.

    Sorteadas e não fixas pelo mesmo motivo que as salas: a decisão interessa
    quando o grupo não sabe o que vem. Com o catálogo inteiro na tela, a
    escolha seria sempre a mesma.
    """
    gerador = _rng(rng)
    return gerador.sample(
        list(CATALOGO_DE_TROCAS), min(quantas, len(CATALOGO_DE_TROCAS))
    )


# Os prêmios de Evento que não são buff com stack.
CURA = "cura"
GRACA = "graca"
NOME_DA_GRACA = "Graça"


@dataclass
class CondicaoAplicada:
    """A benção ou a maldição que a sala grudou no grupo, por personagem.

    Os stacks são por cabeça e não um número só: quem já carregava a mesma
    condição sai com mais que os outros. A linha antiga dizia "todos ficam
    com Medo ×2" usando o número de quem por acaso foi o último do laço, e
    era o único número errado da tela.

    `cid` é o id no catálogo de `condicoes`; `stacks` vai do nome do
    personagem para o que ele carrega AGORA, somando o que já tinha.
    """

    cid: str
    stacks: dict[str, int] = field(default_factory=dict)


@dataclass
class Desfecho:
    """O que a sala deixou no grupo, já em texto pronto para o embed.

    `mimicos` diz que a sala virou combate em vez de devolver o grupo à
    votação; `fora` lista quem bateu no teto de uma condição e saiu.

    `condicao` é a única parte que NÃO vem em texto: ela ganha painel próprio
    no resultado da sala, com o que faz, quem ficou com quanto e o prazo.
    Uma condição por sala — a armadilha que disparou é uma, e o evento que
    deu errado aconteceu uma vez.
    """

    linhas: list[str] = field(default_factory=list)
    mimicos: bool = False
    fora: list[str] = field(default_factory=list)
    condicao: Optional[CondicaoAplicada] = None

    @property
    def vazio(self) -> bool:
        return not (self.linhas or self.mimicos or self.fora or self.condicao)


def _rng(rng: Optional[random.Random]) -> random.Random:
    return aleatorio.gerador(rng, padrao=random)


def dano_da_armadilha(hp_max: int) -> int:
    """O Dano da planilha: -35% do HP máximo. Nunca menos de 1."""
    return max(1, (hp_max * DANO_PCT) // 100)


def cura_do_evento(hp_max: int) -> int:
    """A Cura da planilha: +20% do HP máximo. Nunca menos de 1."""
    return max(1, (hp_max * CURA_PCT) // 100)


def debuff_da_armadilha(rng: Optional[random.Random] = None) -> str:
    """Qual debuff de Armadilha a falha deixa, além do Dano."""
    return _rng(rng).choice(condicoes.DEBUFFS_DE_ARMADILHA)


# Quantas unidades do debuff um Evento perdido deixa. Duas, e não uma: o
# Evento perdeu os cinco debuffs próprios dele — os de grupo de perícia — e
# passou a sortear da mesma lista da Armadilha. Sem o dobro de stacks, falhar
# um Evento passaria a doer menos do que caiu numa Armadilha, que ainda cobra
# o Dano por cima.
UNIDADES_DO_CASTIGO = 2


def castigo_do_evento(rng: Optional[random.Random] = None) -> str:
    """O que um Evento perdido deixa: um debuff ou Exaustão."""
    return _rng(rng).choice(condicoes.DEBUFFS_DE_EVENTO)


def unidades_do_castigo(castigo: str) -> int:
    """Quantas unidades daquele castigo caem de uma vez.

    A Exaustão é a exceção, e fica em UMA. Ela não é um debuff como os
    outros: vale -2 nos ataques, -2 nos testes e -5 de iniciativa POR PONTO,
    não passa com o combate e com cinco pontos tira o personagem da incursão.
    Dois pontos por Evento perdido expulsariam alguém em três falhas.
    """
    if castigo == condicoes.EXAUSTAO:
        return 1
    return UNIDADES_DO_CASTIGO


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
    """Falhar num Tesouro acorda o que fingia ser um baú. SEMPRE.

    Já foi um sorteio de 35%, e por isso a função continua existindo e
    recebendo um `rng` que não usa mais: quem chama não precisou mudar de
    forma. O sorteio saiu porque ele deixava a sala sem castigo em dois
    terços das falhas — e "sair sem o tesouro" não é castigo quando o tesouro
    só existia se você passasse.
    """
    return True
