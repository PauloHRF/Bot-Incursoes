"""Regras de ficha: modificadores, proficiencia, tier e pericias (5e)."""
from __future__ import annotations

ATRIBUTOS = {
    "FOR": "Forca",
    "DES": "Destreza",
    "CON": "Constituicao",
    "INT": "Inteligencia",
    "SAB": "Sabedoria",
    "CAR": "Carisma",
}

# pericia -> atributo-chave
PERICIAS = {
    "Acrobacia": "DES",
    "Adestrar Animais": "SAB",
    "Arcanismo": "INT",
    "Atletismo": "FOR",
    "Atuacao": "CAR",
    "Enganacao": "CAR",
    "Furtividade": "DES",
    "Historia": "INT",
    "Intimidacao": "CAR",
    "Intuicao": "SAB",
    "Investigacao": "INT",
    "Medicina": "SAB",
    "Natureza": "INT",
    "Percepcao": "SAB",
    "Persuasao": "CAR",
    "Prestidigitacao": "DES",
    "Religiao": "INT",
    "Sobrevivencia": "SAB",
}

# Faixas de nivel por tier. Ajuste aqui se as Incursoes originais usarem outro corte.
TIERS = ((4, 1), (10, 2), (16, 3), (20, 4))

# Peso de cada tier no alvo do objetivo principal (doc: soma dos pesos + C).
PESO_TIER = {1: 1, 2: 2, 3: 3, 4: 4}
CONSTANTE_OBJETIVO = 9


def modificador(valor: int) -> int:
    """Modificador de atributo: (valor - 10) // 2."""
    return (valor - 10) // 2


def bonus_proficiencia(nivel: int) -> int:
    """2 + floor((nivel - 1) / 4)."""
    return 2 + (nivel - 1) // 4


def tier(nivel: int) -> int:
    for teto, t in TIERS:
        if nivel <= teto:
            return t
    return TIERS[-1][1]


def mod_pericia(pericia: str, atributos: dict[str, int], nivel: int, treinadas: list[str]) -> int:
    """Modificador final de uma pericia: mod do atributo + proficiencia se treinada."""
    chave = PERICIAS[pericia]
    total = modificador(atributos[chave])
    if pericia in treinadas:
        total += bonus_proficiencia(nivel)
    return total


def melhor_pericia(opcoes: list[str], atributos: dict[str, int], nivel: int, treinadas: list[str]) -> tuple[str, int]:
    """Dentre as pericias listadas pela sala, a melhor para este personagem."""
    ranked = [(p, mod_pericia(p, atributos, nivel, treinadas)) for p in opcoes]
    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked[0]


def fmt(valor: int) -> str:
    """Formata um modificador com sinal: +3 / -1."""
    return f"{valor:+d}"
