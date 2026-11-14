"""Mede a emboscada do Mímico tier por tier, contra a régua do estúdio.

    python tools/calibrar_emboscada.py
    python tools/calibrar_emboscada.py --tier 3 --repeticoes 600

Falhar num Tesouro acorda o que fingia ser um baú, SEMPRE (`CHANCE_DE_MIMICO`
é 1.0). O que acorda está em `consequencias.A_EMBOSCADA`, tier por tier — e é
conteúdo medido, não escolhido no olho: a emboscada anterior deixava o grupo
com 87% do HP no tier 1 e 99% no tier 5, ou seja, a sala acontecia e não
cobrava nada.

O ALVO, que é decisão de design e não medida:

- **vitória ≥ 95%** — a emboscada é castigo por falhar num teste, não um
  segundo chefe. Ela cobra; não deve encerrar a incursão.
- **HP restante entre 55% e 75%** — abaixo disso ela vira o combate da sala
  seguinte por tabela; acima, falhar no Tesouro sai de graça.

POR QUE ESTE ARQUIVO EXISTE em vez de uma medição no terminal: a régua muda.
Quando o grupo medido deixou de ser cinco cópias da mesma classe e passou a
ser mesas sorteadas, todos os números abaixo mudaram junto — e sem um comando
para refazê-los, "foi medido" vira uma afirmação sem data.
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import consequencias  # noqa: E402
from src.incursoes import MAX_INIMIGOS, monstros_de_criatura  # noqa: E402
from src.rules import TIER_MAXIMO  # noqa: E402

import simular_combate as sc  # noqa: E402
from tools.simulacao.grupos import mesa_azarada  # noqa: E402
from tools.simulacao import regua  # noqa: E402

# O alvo. Ver o cabeçalho: é intenção de design, e por isso mora aqui em cima
# com nome, e não espalhado em comparações pelo código.
VITORIA_MINIMA = 0.95
HP_RESTANTE = (55.0, 75.0)
# E a mesa azarada — a do decimo percentil — nao pode ser dizimada. O piso
# mora na regua compartilhada: e o mesmo criterio que a bancada do Estudio
# usa para avisar que uma sala aposta em quem sentou, e ter dois numeros para
# a mesma ideia era o jeito de eles divergirem.
PIOR_MESA_MINIMA = regua.PIOR_MESA_MINIMA
MESA = 5

# Quantas mesas sortear para CALIBRAR — bem mais que as doze da bancada.
#
# O sorteio das mesas é ele próprio uma amostra, e foi uma surpresa cara: o
# mesmo elenco do tier 4 mediu 57,5% com um sorteio e 32,5% com outro. Entre
# mesas, a taxa vai de 0% a 100% no mesmo combate, então o desvio é enorme e
# a média de doze mesas carrega uns dez pontos de erro. Para olhar uma sala na
# bancada isso serve (o autor quer a ordem de grandeza e a pior mesa); para
# escrever um número que vai para o jogo, não serve.
COMPOSICOES_DA_CALIBRACAO = 40


def medir(tier: int, repeticoes: int, semente: int, composicoes: int) -> dict:
    """A emboscada daquele tier contra a mesa, pelo caminho do bot."""
    monstros = [
        m
        for nome, quantas in consequencias.emboscada_do_tier(tier)
        for m in monstros_de_criatura({"nome": nome, "quantidade": quantas}, "emboscada")
    ]
    args = SimpleNamespace(classe=None, nivel=min(10, tier * 2), tier=tier,
                           repeticoes=repeticoes, composicoes=composicoes)
    return sc.simular(monstros, MESA, args, random.Random(f"{semente}:{tier}"))


def ler_bando(texto: str) -> list[tuple[str, int]]:
    """`"Mímico:1, Xorn:4, Armadura Animada:1"` vira o elenco da emboscada.

    Existe porque a curva de uma criatura só é grossa: entre quatro e cinco
    Xorns o HP restante cai de 81% para 66%, e o alvo mora no meio. Para
    chegar lá é preciso misturar — uma âncora pesada mais lacaios —, e isso
    não é uma quantidade, é uma hipótese a medir.
    """
    elenco = []
    for parte in texto.split(","):
        nome, _, quantas = parte.rpartition(":")
        if not nome.strip() or not quantas.strip().isdigit():
            raise ValueError(f"escreva 'Nome:quantidade', e não {parte.strip()!r}")
        elenco.append((nome.strip(), int(quantas)))
    return elenco


def medir_elenco(elenco, tier: int, repeticoes: int, semente: int,
                 composicoes: int) -> dict:
    monstros = [
        m
        for nome, quantas in elenco
        for m in monstros_de_criatura({"nome": nome, "quantidade": quantas}, "emboscada")
    ]
    if len(monstros) != sum(q for _n, q in elenco):
        faltam = [n for n, _ in elenco if not any(n.split()[0] in m.nome for m in monstros)]
        raise SystemExit(f"criatura fora do bestiário: {', '.join(faltam) or elenco}")
    args = SimpleNamespace(classe=None, nivel=min(10, tier * 2), tier=tier,
                           repeticoes=repeticoes, composicoes=composicoes)
    # A semente NÃO leva o elenco: assim todo candidato do mesmo tier enfrenta
    # AS MESMAS mesas, e a diferença entre eles é a diferença entre eles.
    #
    # Levava, e isso quase me fez escolher ruído: o mesmo elenco do tier 5
    # mediu 95,8% com um sorteio e 93,3% com outro, e a "melhora" de um
    # candidato sobre o outro era menor que isso. Comparar cada candidato
    # contra mesas próprias é comparar duas amostras, não duas emboscadas.
    return sc.simular(monstros, MESA, args, random.Random(f"{semente}:{tier}"))


def veredito(taxa: float, hp: float, azarada: float = 1.0) -> str:
    """O parecer, com a MESA AZARADA entrando na conta.

    A média sozinha aprovava o tier 5 com quatro Golens: 95,8% de vitória e
    67,4% de HP restante, tudo dentro do alvo — e uma mesa em cada doze sendo
    dizimada. Isso não é "no alvo"; é uma emboscada que aposta em quem
    sentou. Com o grupo sorteado o desvio está na mão, e não usá-lo no
    veredito seria jogar fora a informação que ele trouxe.
    """
    if taxa < VITORIA_MINIMA:
        return "LETAL — mata o grupo"
    if azarada < PIOR_MESA_MINIMA:
        return "instável — dizima a mesa sem cura"
    if hp > HP_RESTANTE[1]:
        return "barata — falhar sai de graça"
    if hp < HP_RESTANTE[0]:
        return "cara — leva o combate seguinte junto"
    return "no alvo"


def varrer(tier: int, repeticoes: int, semente: int, composicoes: int) -> list[dict]:
    """A curva da emboscada daquele tier, de uma criatura até o teto.

    Varredura e não bisseção, de propósito: a bisseção devolve UM ponto, e
    quem vai escolher a emboscada precisa ver a inclinação. Entre quatro e
    cinco cópias a taxa costuma pular faixa inteira, e saber disso é o que
    separa "escolhi o número" de "o número caiu no meu colo".
    """
    base = consequencias.emboscada_do_tier(tier)
    # Varia a quantidade da ÚLTIMA entrada: nos tiers 1 e 2 é o próprio
    # Mímico, e do 3 para cima é quem mora com o tesouro — o Mímico ali é
    # a ficção da sala, não o peso dela.
    fixos, (nome, _) = list(base[:-1]), base[-1]
    curva = []
    for quantas in range(1, MAX_INIMIGOS - sum(q for _, q in fixos) + 1):
        monstros = [
            m
            for n, q in fixos + [(nome, quantas)]
            for m in monstros_de_criatura({"nome": n, "quantidade": q}, "emboscada")
        ]
        a = SimpleNamespace(classe=None, nivel=min(10, tier * 2), tier=tier,
                            repeticoes=repeticoes, composicoes=composicoes)
        r = sc.simular(monstros, MESA, a, random.Random(f"{semente}:{tier}:{quantas}"))
        curva.append({
            "quantas": quantas, "nome": nome,
            "taxa": r["taxa"], "hp": r["hp_restante_pct"],
            "pior": mesa_azarada(r["composicoes"]),
            "veredito": veredito(r["taxa"], r["hp_restante_pct"],
                                 mesa_azarada(r["composicoes"])),
        })
    return curva


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tier", type=int, default=None, help="só este tier")
    parser.add_argument("--repeticoes", type=int, default=300)
    parser.add_argument("--semente", type=int, default=20261112)
    parser.add_argument(
        "--composicoes", type=int, default=COMPOSICOES_DA_CALIBRACAO, metavar="N",
        help=f"quantas mesas sortear por ponto medido (padrao: {COMPOSICOES_DA_CALIBRACAO})",
    )
    parser.add_argument(
        "--varrer", action="store_true",
        help="mede de 1 criatura até o teto, em vez de só o que está escrito",
    )
    parser.add_argument(
        "--bando", action="append", default=[], metavar="ELENCO",
        help='mede este elenco em vez do escrito; pode repetir. '
             'Ex.: --bando "Mímico:1,Xorn:4,Armadura Animada:1"',
    )
    args = parser.parse_args()

    tiers = [args.tier] if args.tier else list(range(1, TIER_MAXIMO + 1))
    if any(not 1 <= t <= TIER_MAXIMO for t in tiers):
        parser.error(f"tier precisa ir de 1 a {TIER_MAXIMO}")

    print(f"Alvo: vitória >= {VITORIA_MINIMA:.0%}, HP restante "
          f"{HP_RESTANTE[0]:.0f}–{HP_RESTANTE[1]:.0f}%, mesa azarada (1 em 10) >= {PIOR_MESA_MINIMA:.0%}  "
          f"({args.composicoes} mesas de {MESA}, {args.repeticoes} lutas por ponto)")

    if args.bando:
        if not args.tier:
            parser.error("--bando precisa de --tier: o alvo é por tier")
        print(f"\n{'vitória':>8}  {'HP rest.':>9}  {'1 em 10':>9}  {'veredito':<32}  elenco")
        for texto in args.bando:
            elenco = ler_bando(texto)
            r = medir_elenco(elenco, args.tier, args.repeticoes, args.semente, args.composicoes)
            pior = mesa_azarada(r["composicoes"])
            quem = ", ".join(f"{q}x {n}" for n, q in elenco)
            print(f"{r['taxa']:>7.1%}  {r['hp_restante_pct']:>8.1f}%  {pior:>8.0%}  "
                  f"{veredito(r['taxa'], r['hp_restante_pct'], pior):<32}  {quem}")
        return 0

    if args.varrer:
        for tier in tiers:
            fixos = list(consequencias.emboscada_do_tier(tier)[:-1])
            companhia = (", ".join(f"{q}x {n}" for n, q in fixos) + " + ") if fixos else ""
            print(f"\n--- tier {tier} (nível {min(10, tier * 2)}) · {companhia}N x "
                  f"{consequencias.emboscada_do_tier(tier)[-1][0]}")
            print(f"{'N':>3}  {'vitória':>8}  {'HP rest.':>9}  {'1 em 10':>9}  veredito")
            for p in varrer(tier, args.repeticoes, args.semente, args.composicoes):
                print(f"{p['quantas']:>3}  {p['taxa']:>7.1%}  {p['hp']:>8.1f}%  "
                      f"{p['pior']:>8.0%}  {p['veredito']}")
        return 0

    print(f"\n{'tier':>4}  {'vitória':>8}  {'HP rest.':>9}  {'1 em 10':>9}  "
          f"{'veredito':<32}  emboscada")
    fora = 0
    for tier in tiers:
        r = medir(tier, args.repeticoes, args.semente, args.composicoes)
        azarada = mesa_azarada(r["composicoes"])
        quem = ", ".join(f"{q}x {n}" for n, q in consequencias.emboscada_do_tier(tier))
        parecer = veredito(r["taxa"], r["hp_restante_pct"], azarada)
        fora += parecer != "no alvo"
        print(f"{tier:>4}  {r['taxa']:>7.1%}  {r['hp_restante_pct']:>8.1f}%  "
              f"{azarada:>8.0%}  {parecer:<32}  {quem}")
    print()
    if fora:
        print(f"{fora} tier(s) fora do alvo. Ajuste A_EMBOSCADA e rode de novo.")
    else:
        print("Todos os tiers no alvo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
