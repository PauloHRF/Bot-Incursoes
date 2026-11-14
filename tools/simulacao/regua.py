"""A régua: o que um número medido QUER DIZER.

Medir é metade do trabalho. A outra metade é o veredito — dizer se 62% de
vitória é o que a sala queria ser, e se a média esconde uma mesa sendo
dizimada —, e essa metade estava escrita três vezes com três formas
diferentes:

- o `calibrar_emboscada.py` tinha o alvo em constantes nomeadas no topo e uma
  função `veredito()` separada da medição, que é a forma certa;
- o `sugestor.py` tinha as faixas, mas devolvia só `na_faixa: True/False`;
- o **Estúdio não tinha nada**: media, mostrava a porcentagem e deixava o
  autor adivinhar se aquilo era fácil, médio ou letal.

Aqui ficam as duas coisas que valem para os três: as faixas de dificuldade e
o piso da mesa azarada. O alvo de uma consequência específica — a emboscada
do Mímico, por exemplo — continua no arquivo dela, porque é conteúdo daquele
lugar; o que vem para cá é o vocabulário.

NADA AQUI É REGRA DO JOGO. Mudar uma faixa muda o que o sugeridor procura e o
rótulo que a bancada mostra, e mais nada: nenhum combate resolve diferente.
"""
from __future__ import annotations

from typing import Any, Optional

# A faixa de taxa de vitória de cada dificuldade, para um grupo de 5 no tier
# da sala, contra MESAS SORTEADAS.
#
# ESTES NÚMEROS SÃO PROPOSTA E PRECISAM DE CALIBRAÇÃO contra docs/BALANCO.md.
# O método é que não é proposta: a dificuldade de um combate não é declarada,
# é medida — num combate quem decide a dificuldade são as criaturas, e por
# isso sala de combate não tem campo de dificuldade no formato.
FAIXAS_DE_VITORIA: dict[str, tuple[float, float]] = {
    "facil": (0.85, 0.95),
    "media": (0.65, 0.80),
    "dificil": (0.45, 0.60),
}

# Como cada uma se escreve na tela.
ROTULOS = {"facil": "Fácil", "media": "Média", "dificil": "Difícil"}

# E a mesa azarada — a do décimo percentil — não pode ser dizimada.
#
# A média sozinha aprova sala que aposta em quem sentou: 95% de vitória com
# uma mesa em cada dez sendo varrida não é "no alvo", é uma sala que mata o
# grupo sem curandeiro e passa batido no número de cima. O percentil entra no
# veredito porque o grupo sorteado põe esse desvio na mão — e não usá-lo seria
# jogar fora a informação que ele trouxe.
#
# É o PERCENTIL, e não o mínimo: o mínimo de uma amostra afunda conforme ela
# cresce, então o pior de quarenta sorteios não se compara ao pior de doze.
# Ver `estatisticas.mesa_azarada`.
PIOR_MESA_MINIMA = 0.80


def faixa_de(dificuldade: str) -> tuple[float, float]:
    """A faixa daquele rótulo. Erro claro para rótulo que não existe."""
    if dificuldade not in FAIXAS_DE_VITORIA:
        raise ValueError(
            f"dificuldade '{dificuldade}' não existe. "
            f"Use {', '.join(FAIXAS_DE_VITORIA)}."
        )
    return FAIXAS_DE_VITORIA[dificuldade]


def dificuldade_de(taxa: Optional[float]) -> Optional[str]:
    """Em que faixa aquela taxa medida caiu, ou None se caiu entre duas.

    As faixas têm buraco entre elas de propósito (80–85% e 60–65%): são alvos
    a perseguir, não uma classificação que cobre a reta inteira. Uma sala que
    mede 82% não é "quase fácil" — ela é uma sala que não foi mirada, e dizer
    None é mais honesto que arredondar para o vizinho.
    """
    if taxa is None:
        return None
    for nome, (piso, teto) in FAIXAS_DE_VITORIA.items():
        if piso <= taxa <= teto:
            return nome
    return None


def veredito(taxa: Optional[float], azarada: Optional[float] = None) -> dict[str, Any]:
    """O que a medição quer dizer: a faixa, e o aviso da mesa azarada.

    Devolve `{"dificuldade", "rotulo", "dizima"}`. `dizima` é True quando uma
    mesa em dez é varrida, e ele vale MESMO com a média dentro da faixa — são
    duas perguntas diferentes, e a segunda é a que a média esconde.
    """
    nome = dificuldade_de(taxa)
    if taxa is None:
        rotulo = "sem medida"
    elif nome:
        rotulo = ROTULOS[nome]
    elif taxa > max(teto for _p, teto in FAIXAS_DE_VITORIA.values()):
        rotulo = "mais fácil que Fácil"
    elif taxa < min(piso for piso, _t in FAIXAS_DE_VITORIA.values()):
        rotulo = "mais dura que Difícil"
    else:
        rotulo = "entre duas faixas"
    return {
        "dificuldade": nome,
        "rotulo": rotulo,
        "dizima": azarada is not None and azarada < PIOR_MESA_MINIMA,
    }
