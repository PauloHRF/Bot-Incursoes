"""Regras de ficha: tier, bônus de perícia e a tabela de perícias.

Os números de combate não estão aqui: saem da classe, em src/classes.py.
"""
from __future__ import annotations

import unicodedata

ATRIBUTOS = {
    "FOR": "Força",
    "DES": "Destreza",
    "CON": "Constituição",
    "INT": "Inteligência",
    "SAB": "Sabedoria",
    "CAR": "Carisma",
}

# perícia -> atributo-chave
PERICIAS = {
    "Acrobacia": "DES",
    "Adestrar Animais": "SAB",
    "Arcanismo": "INT",
    "Atletismo": "FOR",
    "Atuação": "CAR",
    "Enganação": "CAR",
    "Furtividade": "DES",
    "História": "INT",
    "Intimidação": "CAR",
    "Intuição": "SAB",
    "Investigação": "INT",
    "Medicina": "SAB",
    "Natureza": "INT",
    "Percepção": "SAB",
    "Persuasão": "CAR",
    "Prestidigitação": "DES",
    "Religião": "INT",
    "Sobrevivência": "SAB",
}

# Um tier a cada 2 níveis: 1-2 = tier 1, 3-4 = tier 2, ... 9-10 = tier 5.
# O teto de nível é o alcance das tabelas de classe (src/classes.py), que hoje
# vão até o tier 5. Subir o teto é acrescentar tiers lá e mexer só nestes números.
NIVEIS_POR_TIER = 2
NIVEL_MAXIMO = 10
TIER_MAXIMO = NIVEL_MAXIMO // NIVEIS_POR_TIER

# Peso de cada tier no alvo do objetivo principal (doc: soma dos pesos + C).
# Com o tier a cada 2 níveis o peso é o próprio tier; a constante precisa ser
# recalibrada junto quando a regra de escala do chefe for fechada.
PESO_TIER = {t: t for t in range(1, TIER_MAXIMO + 1)}
CONSTANTE_OBJETIVO = 9


def chave_comparacao(texto: str) -> str:
    """Forma canônica para comparação: sem acento, sem caixa, sem espaço sobrando."""
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return " ".join(sem_acento.lower().split())


_INDICE_PERICIAS = {chave_comparacao(p): p for p in PERICIAS}


def normalizar_pericia(texto: str) -> str | None:
    """Nome canônico da perícia, aceitando grafia sem acento ou em outra caixa.

    Aceita 'investigacao', 'INVESTIGAÇÃO' e 'Investigação' -> 'Investigação'.
    Devolve None se não for uma perícia conhecida.
    """
    return _INDICE_PERICIAS.get(chave_comparacao(texto))


def normalizar_lista_pericias(nomes: list[str]) -> list[str]:
    """Normaliza uma lista, descartando silenciosamente nomes desconhecidos."""
    saida = []
    for nome in nomes:
        canonico = normalizar_pericia(nome)
        if canonico and canonico not in saida:
            saida.append(canonico)
    return saida


def tier(nivel: int) -> int:
    """Tier do personagem: um a cada 2 níveis (1-2 = 1, 3-4 = 2, ... 19-20 = 10)."""
    return max(1, min(TIER_MAXIMO, (nivel + NIVEIS_POR_TIER - 1) // NIVEIS_POR_TIER))


def nivel_maximo_do_tier(tier_alvo: int) -> int:
    """O maior nível que ainda cabe naquele tier: tier 3 -> nível 6."""
    return tier_alvo * NIVEIS_POR_TIER


def faixa_do_tier(tier_alvo: int) -> tuple[int, int]:
    """Os níveis daquele tier: tier 3 -> (5, 6)."""
    teto = nivel_maximo_do_tier(tier_alvo)
    return teto - NIVEIS_POR_TIER + 1, teto


def mod_pericia(
    pericia: str,
    numeros,
    treinadas: list[str],
    bonus: dict[str, int] | None = None,
    efeitos: dict | None = None,
) -> int:
    """Modificador de um teste, somando tudo que vale para aquela perícia.

    `numeros` são os da classe no tier atual (bonus_pericia e bonus_proficiencia),
    `bonus` são as expertises (valores avulsos por perícia) e `efeitos` é o que as
    passivas da classe dão: um bônus geral e outro por perícia.
    """
    total = (
        numeros.bonus_proficiencia if pericia in treinadas else numeros.bonus_pericia
    )
    if bonus:
        total += bonus.get(pericia, 0)
    if efeitos:
        total += efeitos.get("bonus_teste", 0)
        total += (efeitos.get("bonus_pericia") or {}).get(pericia, 0)
    return total


def melhor_pericia(
    opcoes: list[str],
    numeros,
    treinadas: list[str],
    bonus: dict[str, int] | None = None,
    efeitos: dict | None = None,
) -> tuple[str, int]:
    """Dentre as perícias listadas pela sala, a melhor para este personagem."""
    ranked = [(p, mod_pericia(p, numeros, treinadas, bonus, efeitos)) for p in opcoes]
    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked[0]


def fmt(valor: int) -> str:
    """Formata um modificador com sinal: +3 / -1."""
    return f"{valor:+d}"
