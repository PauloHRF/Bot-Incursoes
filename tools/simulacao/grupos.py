"""Grupos fixos para medir salas: frente, cura e dano, sem sortear classes.

O catálogo em grupos.json usa as primeiras N classes de cada formação.
Cada formação tem uma frente e um curandeiro nas duas primeiras vagas; a
terceira traz dano. Vagas seguintes complementam o grupo, sem repetir classe.
As escolhas de tank e cura são explícitas e só entram no tier que as libera.

Média e extremos descrevem ESTES grupos de referência. Não representam
todas as combinações possíveis das catorze classes.
"""
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from typing import Iterable

from src import classes, rules
from .execucao import Ficha

ARQUIVO = Path(__file__).with_name("grupos.json")


@lru_cache(maxsize=1)
def catalogo() -> dict:
    dados = json.loads(ARQUIVO.read_text(encoding="utf-8"))
    ids = set()
    for grupo in dados["grupos"]:
        elenco = grupo["classes"]
        if grupo["id"] in ids or len(elenco) != 6 or len(set(elenco)) != len(elenco):
            raise ValueError(f"Formação repetida ou inválida: {grupo['id']}")
        if any(classes.classe(c) is None for c in elenco):
            raise ValueError(f"Classe desconhecida na formação: {grupo['id']}")
        ids.add(grupo["id"])
    if not ids:
        raise ValueError("O catálogo precisa de pelo menos um grupo.")
    for classe, escolhas in dados["escolhas"].items():
        Ficha(classe, 10, escolhas)
    return dados


COMPOSICOES_PADRAO = len(catalogo()["grupos"])
MINIMO_POR_COMPOSICAO = 15
MINIMO_PARA_A_MEDIA = 10


def dividir(repeticoes: int, quantas: int = COMPOSICOES_PADRAO,
            minimo: int = MINIMO_POR_COMPOSICAO) -> tuple[int, int]:
    """Divide as lutas igualmente, limitado às formações do catálogo.

    Amostras pequenas usam um prefixo fixo de formações, sem sorteio. Com
    60 ou mais lutas cabem os quatro grupos do padrão. Mais repetições
    medem melhor os mesmos grupos; nunca duplicam formações para inflar N.
    """
    if repeticoes < 1 or quantas < 1 or minimo < 1:
        raise ValueError("Repetições, composições e mínimo precisam ser positivos.")
    quantas = min(quantas, COMPOSICOES_PADRAO)
    por_mesa = max(minimo, repeticoes // quantas)
    return max(1, min(quantas, repeticoes // por_mesa)), por_mesa


def fixas(tamanho: int, nivel: int, quantas: int = COMPOSICOES_PADRAO) -> list[tuple[Ficha, ...]]:
    """Mesmas classes e funções, independentemente da semente de combate."""
    if not 1 <= tamanho <= 6 or quantas < 1:
        raise ValueError("Use grupos de 1 a 6 e uma quantidade positiva de formações.")
    dados = catalogo()
    mesas = []
    for grupo in dados["grupos"][:quantas]:
        fichas = []
        for classe in grupo["classes"][:tamanho]:
            abertas = {h.id for t, hs in classes.CLASSES[classe].habilidades.items()
                       if t <= rules.tier(nivel) for h in hs}
            escolhas = {k: v for k, v in dados["escolhas"].get(classe, {}).items() if k in abertas}
            fichas.append(Ficha(classe, nivel, escolhas))
        mesas.append(tuple(fichas))
    return mesas


def descricao(mesa: Iterable[Ficha]) -> dict:
    elenco = list(mesa)
    nomes = [f.classe for f in elenco]
    grupo = next(g for g in catalogo()["grupos"] if g["classes"][:len(nomes)] == nomes)
    return {"id": grupo["id"], "nome": grupo["nome"],
            "fichas": [{"classe": f.classe, "escolhas": f.escolhas} for f in elenco]}


def nomes_da_mesa(mesa: Iterable[Ficha]) -> list[str]:
    return sorted(f.classe for f in mesa)
