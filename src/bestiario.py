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
