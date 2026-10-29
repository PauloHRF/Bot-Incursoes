"""O bestiário: as criaturas prontas que uma sala pode chamar só pelo nome.

O arquivo `data/bestiario.json` sai de `tools/importar_bestiario.py`, que lê o
Monster Manual no formato do 5etools e padroniza o que o bot entende. Cada
entrada já tem o formato que `incursoes._monstros_de_dict` lê, então a sala que
diz só "Lobo" recebe os números do livro no lugar das colunas vazias.

A busca aceita o nome em português e o original em inglês, com ou sem acento.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from .rules import chave_comparacao

ARQUIVO = Path(__file__).resolve().parent.parent / "data" / "bestiario.json"

_indice: Optional[dict[str, dict[str, Any]]] = None


# A faixa de CR que cada tier do grupo encontra. É esta tabela que decide
# a dificuldade do jogo: `tools/balanco.py` tira dela a criatura típica de
# cada tier, e é contra essa criatura que as classes são medidas.
#
# O `meta.tier` que vem em cada entrada NÃO é isto: ele vem do arquivo de
# origem, `data/planilhas/fichas_monstros.json`, e discorda desta tabela em
# um terço do bestiário. Quem manda na dificuldade é esta — a outra é um
# rótulo de quem exportou os dados.
FAIXAS_DE_CR = {1: (0.0, 1.0), 2: (2.0, 4.0), 3: (5.0, 8.0), 4: (9.0, 13.0),
                5: (14.0, 99.0)}


def cr_de(criatura: dict[str, Any]) -> float:
    """O CR como número: '1/2' vira 0.5, e o que falta vira 0."""
    texto = str(criatura.get("cr", "0") or "0")
    if "/" in texto:
        a, b = texto.split("/")
        return float(a) / float(b)
    try:
        return float(texto)
    except ValueError:
        return 0.0


def tier_do_cr(cr: float) -> int:
    """O tier do grupo que encontra uma criatura daquele CR."""
    for tier, (lo, hi) in FAIXAS_DE_CR.items():
        if lo <= cr <= hi:
            return tier
    return max(FAIXAS_DE_CR)


def carregar(arquivo: Path = ARQUIVO) -> list[dict[str, Any]]:
    """Todas as criaturas do bestiário. Sem o arquivo, o bestiário está vazio."""
    if not arquivo.exists():
        return []
    with arquivo.open(encoding="utf-8") as f:
        return json.load(f)["criaturas"]


def _montar_indice() -> dict[str, dict[str, Any]]:
    indice: dict[str, dict[str, Any]] = {}
    for criatura in carregar():
        for nome in (criatura.get("nome_en"), criatura.get("id"), criatura["nome"]):
            if nome:
                indice[chave_comparacao(nome)] = criatura
    return indice


def buscar(nome: str) -> Optional[dict[str, Any]]:
    """A criatura com aquele nome (português ou inglês), ou None."""
    global _indice
    if _indice is None:
        _indice = _montar_indice()
    return _indice.get(chave_comparacao(nome))


def recarregar() -> None:
    """Esquece o índice: a próxima busca relê o arquivo."""
    global _indice
    _indice = None
