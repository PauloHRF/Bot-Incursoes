"""Audita classes com os resolvedores reais do bot.

    python tools/simular_balanceamento.py --simulacoes 100 --csv resultado.csv
    python tools/simular_balanceamento.py --comparar --simulacoes 10 --relatorio resultados
    python tools/simular_balanceamento.py --comparar --tier 3 --grupos 3 5

Cada luta usa SQLite em memoria e recursos completos; nao acessa Discord nem
bancos do servidor. A politica automatica fica em tools/simulacao/politica.py.
"""
from __future__ import annotations
import argparse
import asyncio
import json
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import bestiario, classes, incursoes as I, rules
from tools.simulacao.execucao import Bancada, Ficha
from tools.simulacao.estatisticas import resumir
from tools.simulacao.politica import escolhas_automaticas, habilidades_da_ficha, media_dado, pontuar_acao
from tools.simulacao.comparacao import (carregar_builds, carregar_cenarios, comparar,
                                      gravar_csv, gravar_grafico, gravar_relatorio, ranking)

CLASSES = tuple(classes.CLASSES)


def monstros_do_tier(tier: int) -> list[dict]:
    """Retorna criaturas reais do bestiário na faixa de CR do tier."""
    minimo, maximo = bestiario.FAIXAS_DE_CR[tier]
    criaturas = [
        c for c in bestiario.carregar()
        if minimo <= bestiario.cr_de(c) <= maximo and c.get("golpes")
    ]
    if not criaturas:
        raise RuntimeError(
            f"Nenhuma criatura com golpes encontrada para o tier {tier}. "
            "Confira data/bestiario.json."
        )
    return criaturas


async def _medir(classe_id, tier, simulacoes, rng):
    if simulacoes < 1:
        raise ValueError("Simulacoes deve ser maior que zero.")
    pool = monstros_do_tier(tier)
    fichas = [Ficha(classe_id, rules.nivel_do_tier(tier)) for _ in range(5)]
    resultados, catalogo = [], {}
    # O sorteio do encontro nao consome o RNG do combate: uma classe que
    # age mais vezes nao recebe inimigos diferentes na proxima repeticao.
    async with Bancada(fichas, [I.Monstro("Alvo", 10, 1, "1d1", 1)], tier=tier, limite=40) as bancada:
        for _ in range(simulacoes):
            criatura = rng.choice(pool)
            nome = criatura["nome"]
            if nome not in catalogo:
                catalogo[nome] = I.monstros_de_criatura({"nome": nome})
            bancada.monstros = catalogo[nome]
            resultado = await bancada.lutar(random.Random(rng.getrandbits(128)))
            resultado.pop("estado")
            resultados.append(resultado)
    r = resumir(resultados)
    return {
        "classe": classe_id, "tier": tier, "simulacoes": simulacoes,
        "vitoria_pct": round(100*r["taxa"], 2), "rodadas_media": round(r["rodadas"], 2),
        "dano_grupo_rodada": round(statistics.mean(x["dano"]/x["rodadas"] for x in resultados), 2),
        "dano_recebido_medio": round(r["recebido"], 2), "cura_media": round(r["cura"], 2),
        "recursos_gastos_media": round(r["recursos"], 2), "thp_gasto_medio": round(r["thp_gasto"], 2),
        "thp_restante_medio": round(r["thp_restante"], 2), "hp_restante_pct": round(r["hp_restante_pct"], 2),
        "caidos_media": round(r["caidos"], 2), "limite_40_rodadas_pct": round(100*r["limites"]/simulacoes, 2),
        "ic95_inf": round(100*r["ic95"][0], 2), "ic95_sup": round(100*r["ic95"][1], 2),
    }


def medir(classe_id, tier, simulacoes, rng):
    """Mantem a API e as colunas antigas; acrescenta o intervalo de 95%."""
    return asyncio.run(_medir(classe_id, tier, simulacoes, rng))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simulacoes", type=int, help="Repeticoes por cenario (padrao: 1000; --comparar: 10)")
    parser.add_argument("--seed", type=int, default=20261111)
    parser.add_argument("--tier", type=int, choices=range(1, 6))
    parser.add_argument("--classe", choices=CLASSES)
    parser.add_argument("--classes", nargs="+", choices=CLASSES)
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--comparar", action="store_true", help="Troca somente o ultimo integrante de grupos mistos")
    parser.add_argument("--grupos", type=int, nargs="+", choices=range(1, 6))
    parser.add_argument("--base", action="append", help="Classes fixas separadas por virgula; pode repetir")
    parser.add_argument("--builds", type=Path, help="JSON de builds nomeadas: nome -> classe/escolhas")
    parser.add_argument("--cenarios", type=Path, help="JSON de salas de combate por tier")
    parser.add_argument("--relatorio", type=Path, help="Pasta para CSVs, JSON reproduzivel e Markdown")
    parser.add_argument("--grafico", type=Path, help="PNG opcional; requer requirements-simulacao.txt")
    args = parser.parse_args()
    repeticoes = args.simulacoes if args.simulacoes is not None else (10 if args.comparar else 1000)
    if repeticoes < 1:
        parser.error("--simulacoes precisa ser maior que zero")
    if args.classe and args.classes:
        parser.error("Use --classe ou --classes.")
    if not args.comparar and any((args.grupos, args.base, args.builds, args.cenarios, args.relatorio, args.grafico)):
        parser.error("--grupos, --base, --builds, --cenarios, --relatorio e --grafico exigem --comparar.")
    tiers = [args.tier] if args.tier else list(range(1, 6))
    candidatas = [args.classe] if args.classe else args.classes
    try:
        if args.comparar:
            builds = carregar_builds(args.builds, candidatas)
            cenarios = carregar_cenarios(args.cenarios)
            bases = [tuple(c.strip() for c in base.split(",") if c.strip()) for base in args.base] if args.base else None
            tamanhos = sorted(set(args.grupos or [5]))
            def progresso(r):
                print(f"T{r['tier']} grupo {r['grupo']} {r['encontro']:12} {r['build']:16} "
                      f"vitorias={r['vitoria_pct']:6.2f}% ({r['vitorias']}/{r['simulacoes']})", flush=True)
            experimento = asyncio.run(comparar(builds, cenarios, tiers, tamanhos, repeticoes, args.seed,
                                              bases=bases, progresso=progresso))
            resultados = experimento["resultados"]
            print("\nComparacao por tamanho de grupo; todos os cenarios selecionados tem o mesmo peso:")
            for r in ranking(resultados):
                print(f"grupo {r['grupo']} {r['build']:16} {r['vitoria_pct']:6.2f}% "
                      f"IC95 {r['ic95_inf']:.1f}–{r['ic95_sup']:.1f}% · {r['simulacoes']} combates · limites={r['limites']}")
            if args.relatorio:
                gravar_relatorio(args.relatorio, experimento)
                print(f"Relatorio: {args.relatorio}")
            if args.grafico:
                gravar_grafico(args.grafico, resultados)
        else:
            resultados = []
            for t in tiers:
                for cid in candidatas or CLASSES:
                    r = medir(cid, t, repeticoes, random.Random(f"{args.seed}:{t}"))
                    resultados.append(r)
                    print(f"T{t} {cid:12} vitorias={r['vitoria_pct']:6.2f}% "
                          f"dano/rod={r['dano_grupo_rodada']:7.2f} cura={r['cura_media']:7.2f} "
                          f"recursos={r['recursos_gastos_media']:5.2f} HP restante={r['hp_restante_pct']:6.2f}% "
                          f"caidos={r['caidos_media']:.2f}", flush=True)
        if args.csv:
            gravar_csv(args.csv, resultados)
            print(f"CSV: {args.csv}")
    except (ValueError, I.ErroDeValidacao, OSError) as erro:
        parser.error(str(erro))
    print("Combates isolados com recursos cheios e politica automatica. Pericias e desgaste entre salas exigem outra bateria.")


if __name__ == "__main__":
    main()
