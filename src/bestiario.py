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
# O `meta.tier` que vem em cada entrada NÃO é isto: ele veio com a tabela de
# fichas que `tools/importar_fichas.py` converteu, e discorda desta tabela em
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


# O vocabulário de ambiente do Monster Manual, que `tools/importar_ambientes.py`
# copia para `meta.ambientes`. Fechado: estes onze são os que o livro usa, e
# nada no bot inventa um décimo segundo.
AMBIENTES = (
    "arctic", "coastal", "desert", "forest", "grassland", "hill",
    "mountain", "swamp", "underdark", "underwater", "urban",
)


def ambientes_de(criatura: dict[str, Any]) -> list[str]:
    """Os ambientes daquela criatura. Lista vazia quer dizer algo.

    Vazia NÃO é dado faltando: o livro não dá bioma a quem não é nativo de
    bioma nenhum — demônio, golem, celestial. São 70 das 385, e elas formam o
    balde "de lugar nenhum", que serve a qualquer ambiente escolhido. Um
    demônio cabe numa cripta tão bem quanto numa floresta.

    Criatura importada antes de `meta.ambientes` existir também cai aqui, e
    por isso quem filtra precisa tratar a lista vazia como "serve a tudo" e
    não como "não serve a nada".
    """
    return list((criatura.get("meta") or {}).get("ambientes") or [])


def de_lugar_nenhum(criatura: dict[str, Any]) -> bool:
    """A criatura que o livro não prende a bioma nenhum."""
    return not ambientes_de(criatura)


def candidatas(
    ambiente: Optional[str] = None,
    tipo: Optional[str] = None,
    tier: Optional[int] = None,
    faixa_cr: Optional[tuple[float, float]] = None,
) -> list[dict[str, Any]]:
    """As criaturas que servem a um ambiente, a um tipo e a um tier.

    Os três filtros são independentes e cada um vazio quer dizer "qualquer":
    é o autor que decide o quanto apertar.

    O AMBIENTE tem uma regra que não é óbvia. Criatura sem ambiente nenhum
    entra em TODO ambiente pedido, porque a lista vazia não é dado faltando —
    o livro não prende a bioma quem não é nativo de bioma: demônio, golem,
    celestial. São 70 das 385, e sem essa regra uma cripta ou um templo não
    acharia quase nada.

    O TIER vira faixa de CR por `FAIXAS_DE_CR`, que é a mesma tabela que
    `tools/balanco.py` usa para medir as classes. Quem decide a dificuldade
    depois é a QUANTIDADE, e ela é medida por simulação, não escolhida aqui.

    `faixa_cr` substitui a do tier quando quem chama quer uma janela própria —
    um chefe legitimamente vem de cima da criatura típica do tier.
    """
    faixa = faixa_cr or FAIXAS_DE_CR.get(tier or 0)
    alvo_tipo = (tipo or "").strip().lower()
    saida = []
    for criatura in carregar():
        meta = criatura.get("meta") or {}
        if alvo_tipo and str(meta.get("tipo") or "").lower() != alvo_tipo:
            continue
        if faixa:
            cr = cr_de(criatura)
            if not faixa[0] <= cr <= faixa[1]:
                continue
        if ambiente:
            seus = ambientes_de(criatura)
            if seus and ambiente not in seus:
                continue
        saida.append(criatura)
    return saida


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
