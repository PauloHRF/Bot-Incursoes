"""Quantas salas cada tema tem, e que tamanhos ele aguenta.

    python tools/relatorio_de_pool.py
    python tools/relatorio_de_pool.py "Vórtice Oculto"

Serve para decidir ONDE escrever a próxima sala, em vez de descobrir a falta
no dia em que uma dungeon é recusada.

A conta é a do sorteio, e ela é apertada: `motor.sortear_passo` nunca repete
sala, então uma Longa precisa de 7 salas no pool só para poder terminar, e de
9 para oferecer 3 portas em toda parada. Os bancos têm 11 a 13 salas
sorteáveis — a de Descanso não entra, porque ela é o cenário da parada fixa e
não é sorteada.

Daí a regra de quem escreve: marque TODOS os temas em que a sala cabe. Tema
que dividisse o banco em gavetas não daria uma Longa em gaveta nenhuma; tema
que se acumula na mesma sala mantém cada pool de pé.

Sala sem tema escrito entra em qualquer filtro, então ela conta em todas as
colunas — e é por isso que um banco ainda não etiquetado aparece aqui com
todos os temas cheios: não é cobertura, é a falta dela.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src.incursoes import (  # noqa: E402
    OPCOES_POR_PASSO,
    TAMANHOS,
    TEMAS,
    FiltroDeSalas,
    carregar_bancos,
    salas_sorteaveis,
)

PASTA_BANCOS = RAIZ / "data" / "bancos"


def minimos() -> dict[str, tuple[int, int]]:
    """Por tamanho: (salas para terminar, salas para 3 portas sempre)."""
    return {
        nome: (passos, passos + OPCOES_POR_PASSO - 1)
        for nome, passos in TAMANHOS.items()
    }


def linha_do_tema(salas, tema: str) -> tuple[int, int, dict[str, str]]:
    """Quantas salas o tema tem, quantas delas são etiquetadas, e o veredito."""
    pool = FiltroDeSalas(temas=[tema]).aplicar(salas)
    etiquetadas = [s for s in pool if tema in s.temas]
    veredito = {}
    for nome, (terminar, folga) in minimos().items():
        if len(pool) < terminar:
            veredito[nome] = f"faltam {terminar - len(pool)}"
        elif len(pool) < folga:
            veredito[nome] = "aperta"
        else:
            veredito[nome] = "cabe"
    return len(pool), len(etiquetadas), veredito


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "organizacao", nargs="?", help="só esta Organização; sem nada, todas"
    )
    args = parser.parse_args()

    bancos = carregar_bancos(PASTA_BANCOS)
    if args.organizacao:
        bancos = {
            nome: banco for nome, banco in bancos.items()
            if nome.lower() == args.organizacao.lower()
        }
        if not bancos:
            print(f"não há banco de '{args.organizacao}' em {PASTA_BANCOS}.")
            return 1

    tamanhos = list(TAMANHOS)
    cabecalho = (
        f"{'tema':<12}{'salas':>6}{'etiq.':>7}  "
        + "".join(f"{t:>10}" for t in tamanhos)
    )

    for nome, banco in sorted(bancos.items()):
        salas = salas_sorteaveis(banco)
        sem_tema = [s for s in salas if not s.temas]
        print(f"\n=== {nome} — {len(salas)} sala(s) sorteáveis")
        if sem_tema:
            print(
                f"    {len(sem_tema)} sem tema escrito, e elas entram em TODO "
                f"filtro: as colunas abaixo estão infladas por elas."
            )
        print(cabecalho)
        print("-" * len(cabecalho))
        for tema in TEMAS:
            total, etiquetadas, veredito = linha_do_tema(salas, tema)
            print(
                f"{tema:<12}{total:>6}{etiquetadas:>7}  "
                + "".join(f"{veredito[t]:>10}" for t in tamanhos)
            )

    print("\nmínimos por tamanho (o sorteio nunca repete sala):")
    for nome, (terminar, folga) in minimos().items():
        print(
            f"  {nome:<6} atravessa {TAMANHOS[nome]} sala(s): "
            f"{terminar} para terminar, {folga} para {OPCOES_POR_PASSO} portas sempre"
        )
    print("\n'etiq.' é quantas daquelas salas carregam o tema de verdade.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
