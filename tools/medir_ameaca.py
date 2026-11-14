"""Mede o HP que uma ação move, para calibrar `ameaca.ESCALA_DO_HP`.

    python tools/medir_ameaca.py
    python tools/medir_ameaca.py --tier 3 --repeticoes 400

A ameaça que se gera agindo é o HP que a ação mexeu, em FRAÇÃO da poça do
lado afetado (ver `src/ameaca.py`). A fração é invariante por tier de
propósito — a mesma Fireball vale igual em T1 e em T5 —, mas quanto ela VALE
em pontos de ameaça é calibragem, e calibragem precisa de medida.

O que este comando faz: liga um gravador em `ameaca.pontos_do_hp`, roda a
bateria de cenários de `tools/simulacao/cenarios.json` com mesas sorteadas e
os resolvedores reais do bot, e devolve a distribuição das frações por AÇÃO e
por RODADA de personagem.

O ALVO, que é decisão de design e não medida: uma rodada muito boa — o p90 das
rodadas medidas — deve render uns **10 pontos** de ameaça. Numa mesa de um
personagem por grupo (12/10/8/6/4), 10 pontos levam o último de 14,4% para
23,9% da atenção: ele encosta no tanque sem passar por cima. Abaixo disso o
dano é tempero e a classe decide tudo; acima, quem bate mais vira o alvo
principal e o papel de tanque se confunde com dano.

A saída traz a ESCALA que acerta esse alvo. Rodar de novo depois de mexer em
dano de classe, HP de criatura ou tamanho de sala é o jeito de saber se ela
continua valendo.
"""
from __future__ import annotations

import argparse
import random
import statistics
import sys
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import ameaca  # noqa: E402
from src.rules import TIER_MAXIMO  # noqa: E402

from tools.simulacao import medidas, medidor  # noqa: E402
from tools.simulacao.comparacao import carregar_cenarios  # noqa: E402

MESA = 5
# O alvo de design: quanto uma rodada p90 deve render de ameaça.
PONTOS_NA_RODADA_BOA = 10
# Quantas mesas sortear. Menos que as 40 da calibragem da emboscada: aqui o
# que se quer é a DISTRIBUIÇÃO das frações, e cada luta dá dezenas de amostras.
COMPOSICOES = 12


class Gravador:
    """Anota cada fração que passa por `ameaca.pontos_do_hp`.

    Substitui a função por um invólucro em vez de instrumentar o cog: a conta
    é um ponto só, e tudo que gera ameaça passa por ela — inclusive o que
    vier por caminhos que ainda não existem.
    """

    def __init__(self) -> None:
        self.fracoes: list[float] = []
        self._original = ameaca.pontos_do_hp

    def __enter__(self) -> "Gravador":
        def espiao(dano=0, cura=0, evitado=0, hp_dos_inimigos=0, hp_do_grupo=0):
            fracao = 0.0
            if hp_dos_inimigos > 0:
                fracao += max(0, dano) / hp_dos_inimigos
            if hp_do_grupo > 0:
                fracao += (max(0, cura) + max(0, evitado)) / hp_do_grupo
            if fracao > 0:
                self.fracoes.append(fracao)
            return self._original(
                dano=dano, cura=cura, evitado=evitado,
                hp_dos_inimigos=hp_dos_inimigos, hp_do_grupo=hp_do_grupo,
            )

        ameaca.pontos_do_hp = espiao  # type: ignore[assignment]
        return self

    def __exit__(self, *_erro) -> None:
        ameaca.pontos_do_hp = self._original  # type: ignore[assignment]


def medir_tier(tier: int, repeticoes: int, semente: int) -> list[float]:
    """As frações de HP movido por ação, na bateria daquele tier."""
    fracoes: list[float] = []
    for sala in carregar_cenarios()[tier]:
        with Gravador() as gravador:
            medidor.medir(
                list(sala.monstros), tamanho=MESA, tier=tier,
                repeticoes=repeticoes, semente=semente, mesas=COMPOSICOES,
            )
        fracoes.extend(gravador.fracoes)
    return fracoes


def percentis(valores: list[float]) -> dict[str, float]:
    if not valores:
        return {}
    ordenados = sorted(valores)
    quantis = statistics.quantiles(ordenados, n=100) if len(ordenados) > 2 else None
    return {
        "n": len(ordenados),
        "media": statistics.fmean(ordenados),
        "p50": quantis[49] if quantis else ordenados[len(ordenados) // 2],
        "p90": quantis[89] if quantis else ordenados[-1],
        "p99": quantis[98] if quantis else ordenados[-1],
        "max": ordenados[-1],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tier", type=int, choices=range(1, TIER_MAXIMO + 1))
    parser.add_argument("--repeticoes", type=int, default=120)
    parser.add_argument("--semente", type=int, default=20261113)
    args = parser.parse_args()

    tiers = [args.tier] if args.tier else list(range(1, TIER_MAXIMO + 1))
    print(
        f"Fração do HP da poça movida por AÇÃO de personagem "
        f"({COMPOSICOES} mesas de {MESA}, {args.repeticoes} lutas por cenário)\n"
    )
    print(f"{'tier':<6}{'ações':>8}{'média':>9}{'p50':>8}{'p90':>8}{'p99':>8}{'máx':>8}")
    todas: list[float] = []
    por_tier: dict[int, dict[str, float]] = {}
    for tier in tiers:
        fracoes = medir_tier(tier, args.repeticoes, args.semente)
        todas.extend(fracoes)
        p = percentis(fracoes)
        por_tier[tier] = p
        if not p:
            print(f"{tier:<6}{'—':>8}")
            continue
        print(
            f"{tier:<6}{p['n']:>8}{p['media']:>8.1%}{p['p50']:>8.1%}"
            f"{p['p90']:>8.1%}{p['p99']:>8.1%}{p['max']:>8.1%}"
        )

    geral = percentis(todas)
    if not geral:
        print("\nNenhuma ação moveu HP — a medição não mediu nada.")
        return 1
    print(
        f"\n{'todos':<6}{geral['n']:>8}{geral['media']:>8.1%}{geral['p50']:>8.1%}"
        f"{geral['p90']:>8.1%}{geral['p99']:>8.1%}{geral['max']:>8.1%}"
    )

    # A invariância por tier é a premissa da escala única: se as colunas
    # andarem muito entre tiers, um número só não serve para o jogo todo.
    p90s = [p["p90"] for p in por_tier.values() if p]
    if len(p90s) > 1:
        espalhamento = max(p90s) / min(p90s)
        print(
            f"\nO p90 varia {espalhamento:.1f}x entre os tiers "
            f"({min(p90s):.1%} a {max(p90s):.1%}). "
            + ("Uma escala só serve." if espalhamento < 2 else
               "ATENÇÃO: espalhado demais para uma escala só.")
        )

    sugerida = round(PONTOS_NA_RODADA_BOA / geral["p90"])
    print(
        f"\nAlvo: a rodada p90 ({geral['p90']:.1%} da poça) rendendo "
        f"{PONTOS_NA_RODADA_BOA} pontos.\n"
        f"  ESCALA_DO_HP sugerida: {sugerida}   "
        f"(está em {ameaca.ESCALA_DO_HP})"
    )
    print(
        f"  com ela, a ação média rende {round(ameaca.ESCALA_DO_HP * geral['media'])} "
        f"ponto(s), a p90 {round(ameaca.ESCALA_DO_HP * geral['p90'])} e a p99 "
        f"{round(ameaca.ESCALA_DO_HP * geral['p99'])}"
    )

    if args.tier:
        print("\nMedição parcial (um tier): não gravada.")
        return 0
    medidas.gravar("ameaca_por_acao", {
        "acoes": geral["n"],
        "media": geral["media"],
        "p50": geral["p50"],
        "p90": geral["p90"],
        "p99": geral["p99"],
        "escala": ameaca.ESCALA_DO_HP,
        "espalhamento_entre_tiers": (
            round(max(p90s) / min(p90s), 2) if len(p90s) > 1 else None
        ),
        "repeticoes_por_cenario": args.repeticoes,
        "mesas": COMPOSICOES,
        "semente": args.semente,
    })
    print(f"\nGravado em {medidas.ARQUIVO.relative_to(RAIZ)} — "
          "`balanco.py` e o gerador de mecânicas leem daí, em vez de o número "
          "ser copiado à mão para dentro do documento.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
