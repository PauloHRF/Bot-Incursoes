"""Regras de ficha: modificadores, proficiência, tier e perícias (5e)."""
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

# Faixas de nível por tier. Ajuste aqui se as Incursões originais usarem outro corte.
TIERS = ((4, 1), (10, 2), (16, 3), (20, 4))

# Peso de cada tier no alvo do objetivo principal (doc: soma dos pesos + C).
PESO_TIER = {1: 1, 2: 2, 3: 3, 4: 4}
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


def modificador(valor: int) -> int:
    """Modificador de atributo: (valor - 10) // 2."""
    return (valor - 10) // 2


def bonus_proficiencia(nivel: int) -> int:
    """2 + floor((nível - 1) / 4)."""
    return 2 + (nivel - 1) // 4


def tier(nivel: int) -> int:
    for teto, t in TIERS:
        if nivel <= teto:
            return t
    return TIERS[-1][1]


def mod_pericia(pericia: str, atributos: dict[str, int], nivel: int, treinadas: list[str]) -> int:
    """Modificador final de uma perícia: mod do atributo + proficiência se treinada."""
    chave = PERICIAS[pericia]
    total = modificador(atributos[chave])
    if pericia in treinadas:
        total += bonus_proficiencia(nivel)
    return total


def melhor_pericia(
    opcoes: list[str], atributos: dict[str, int], nivel: int, treinadas: list[str]
) -> tuple[str, int]:
    """Dentre as perícias listadas pela sala, a melhor para este personagem."""
    ranked = [(p, mod_pericia(p, atributos, nivel, treinadas)) for p in opcoes]
    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked[0]


def fmt(valor: int) -> str:
    """Formata um modificador com sinal: +3 / -1."""
    return f"{valor:+d}"
