"""Fonte de sorteios por contexto; o jogo continua usando SystemRandom.

A bancada pode fornecer um Random sem substituir funcoes globais. ContextVar
isola simulacoes simultaneas, inclusive as requisicoes do Estudio.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import random

_ATUAL = ContextVar("gerador_de_sorteios", default=None)


def gerador(rng=None, padrao=None):
    if rng is not None:
        return rng
    atual = _ATUAL.get()
    return atual if atual is not None else (padrao if padrao is not None else random.SystemRandom())


@contextmanager
def usar(rng):
    """Semente local, restaurada inclusive quando o combate falha."""
    token = _ATUAL.set(rng)
    try:
        yield
    finally:
        _ATUAL.reset(token)
