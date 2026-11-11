"""Experimentos controlados e exportacao. Nao contem regras de combate."""
from __future__ import annotations

from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
import random

from src import classes, incursoes as I, rules
from .execucao import Ficha, simular_async
from .estatisticas import intervalo, resumir

PADRAO = Path(__file__).with_name("cenarios.json")
BASES = (("guerreiro", "patrulheiro", "mago", "clerigo"),
         ("barbaro", "ladino", "feiticeiro", "xama"))
TRIOS = (("guerreiro", "clerigo"), ("barbaro", "mago"))


def carregar_cenarios(caminho=None):
    dados = json.loads(Path(caminho or PADRAO).read_text(encoding="utf-8-sig"))
    resultado = {}
    if not isinstance(dados, dict):
        raise ValueError("Cenarios deve ser um objeto com listas por tier.")
    for chave, entradas in dados.items():
        if chave not in {str(t) for t in range(1, 6)} or not isinstance(entradas, list) or not entradas:
            raise ValueError(f"Lista de cenarios invalida no tier {chave}.")
        salas, ids = [], set()
        for entrada in entradas:
            if not isinstance(entrada, dict):
                raise ValueError("Cada cenario precisa ser um objeto.")
            sala = I.sala_de_dict({"tipo": "Combate", "descricao": "Cenario de comparacao.",
                                  "nome": entrada.get("id", ""), **entrada})
            if not sala.e_combate or sala.id in ids:
                raise ValueError(f"Cenario repetido ou sem combate: {sala.id}")
            ids.add(sala.id)
            salas.append(sala)
        resultado[int(chave)] = salas
    return resultado


def carregar_builds(caminho=None, candidatas=None):
    if caminho and candidatas:
        raise ValueError("Use --builds ou --classe/--classes.")
    if caminho:
        dados = json.loads(Path(caminho).read_text(encoding="utf-8-sig"))
        if not isinstance(dados, dict) or not dados:
            raise ValueError("Builds deve ser um objeto nao vazio: nome -> classe/escolhas.")
    else:
        dados = {c: {"classe": c} for c in (candidatas or sorted(classes.CLASSES))}
    for nome, perfil in dados.items():
        if not isinstance(perfil, dict) or not isinstance(perfil.get("escolhas", {}), dict):
            raise ValueError(f"Build invalida: {nome}")
        if set(perfil) - {"classe", "escolhas"}:
            raise ValueError(f"Build {nome}: use somente classe e escolhas.")
        Ficha(perfil.get("classe"), 10, perfil.get("escolhas"))
    return dados


def ficha_do_tier(perfil, tier):
    nivel = rules.nivel_do_tier(tier)
    cid = perfil["classe"]
    abertas = {h.id for t, hs in classes.CLASSES[cid].habilidades.items() if t <= tier for h in hs}
    escolhas = {k: v for k, v in perfil.get("escolhas", {}).items() if k in abertas}
    return Ficha(cid, nivel, escolhas)


def bases_do_grupo(tamanho, bases=None):
    if bases is None:
        if tamanho == 1:
            return [()]
        return TRIOS if tamanho == 3 else [base[:tamanho-1] for base in BASES]
    for base in bases:
        if len(base) != tamanho-1:
            raise ValueError(f"Grupo de {tamanho}: --base precisa ter {tamanho-1} classes fixas.")
        for cid in base:
            Ficha(cid, 1)
    if len({tuple(b) for b in bases}) != len(bases):
        raise ValueError("As bases nao podem repetir.")
    return bases


async def comparar(builds, cenarios, tiers, tamanhos, repeticoes, semente, *, bases=None, progresso=None):
    if not builds or not tiers or not tamanhos:
        raise ValueError("Informe candidatos, tiers e tamanhos de grupo.")
    if repeticoes < 1 or any(n < 1 or n > 5 for n in tamanhos):
        raise ValueError("Use repeticoes positivas e grupos de 1 a 5.")
    if bases is not None and len(tamanhos) != 1:
        raise ValueError("Bases personalizadas exigem um unico tamanho em --grupos.")
    # Valida o experimento inteiro antes da primeira luta.
    for t in tiers:
        if t not in cenarios:
            raise ValueError(f"Sem cenarios para o tier {t}.")
        for perfil in builds.values():
            ficha_do_tier(perfil, t)
    for tamanho in tamanhos:
        bases_do_grupo(tamanho, bases)
    resultados = []
    for t in tiers:
        for tamanho in tamanhos:
            for base in bases_do_grupo(tamanho, bases):
                for sala in cenarios[t]:
                    # O nome da build e sua posicao na lista nao entram na
                    # semente: todas enfrentam o mesmo conjunto de sorteios.
                    chave = f"{semente}:{t}:{tamanho}:{','.join(base)}:{sala.id}"
                    for nome, perfil in sorted(builds.items()):
                        fichas = [Ficha(c, rules.nivel_do_tier(t)) for c in base] + [ficha_do_tier(perfil, t)]
                        medidas = await simular_async(sala.monstros_do_tier(t), fichas,
                                                     repeticoes, random.Random(chave), tier=t)
                        resumo = resumir(medidas)
                        linha = {
                            "build": nome, "classe": perfil["classe"], "tier": t,
                            "nivel": rules.nivel_do_tier(t), "grupo": tamanho,
                            "base": ",".join(base), "encontro": sala.id,
                            "semente": chave, "escolhas": json.dumps(fichas[-1].escolhas, ensure_ascii=False, sort_keys=True),
                            "simulacoes": repeticoes, "vitorias": resumo["vitorias"],
                            "vitoria_pct": 100*resumo["taxa"],
                            "ic95_inf": 100*resumo["ic95"][0], "ic95_sup": 100*resumo["ic95"][1],
                            "rodadas_media": resumo["rodadas"], "hp_restante_pct": resumo["hp_restante_pct"],
                            "cura_media": resumo["cura"], "thp_gerado_medio": resumo["thp_gerado"],
                            "caidos_media": resumo["caidos"], "recursos_gastos_media": resumo["recursos"],
                            "limites": resumo["limites"],
                        }
                        resultados.append(linha)
                        if progresso:
                            progresso(linha)
    raiz = Path(__file__).resolve().parents[2]
    arquivos = sorted((raiz/"src").rglob("*.py")) + sorted(Path(__file__).parent.glob("*.py"))
    modelo = hashlib.sha256()
    for arquivo in arquivos:
        modelo.update(str(arquivo.relative_to(raiz)).encode())
        modelo.update(arquivo.read_bytes())
    return {"metodo": {
        "motor": "resolvedores de src.cogs.incursao; SQLite em memoria", "semente": semente,
        "sha256_modelo": modelo.hexdigest(),
        "repeticoes_por_celula": repeticoes, "tiers": list(tiers), "grupos": list(tamanhos),
        "builds": builds, "cenarios": {str(t): [s.para_dict() for s in cenarios[t]] for t in tiers},
        "condicoes": "combate isolado; HP e recursos completos; sem equipamento ou pocoes",
        "politica": "tools.simulacao.politica; requisitos/usos/alvos conferidos pelo bot",
    }, "resultados": resultados}


def ranking(resultados):
    grupos = defaultdict(list)
    for r in resultados:
        grupos[(r["build"], r["grupo"])].append(r)
    saida = []
    for (nome, tamanho), linhas in grupos.items():
        n = sum(r["simulacoes"] for r in linhas)
        v = sum(r["vitorias"] for r in linhas)
        lo, hi = intervalo(v, n)
        saida.append(dict(build=nome, grupo=tamanho, simulacoes=n, vitorias=v,
                          vitoria_pct=100*v/n, ic95_inf=100*lo, ic95_sup=100*hi,
                          limites=sum(r["limites"] for r in linhas)))
    return sorted(saida, key=lambda r: (r["grupo"], -r["vitoria_pct"], r["build"]))


def gravar_csv(caminho, resultados):
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", newline="", encoding="utf-8-sig") as arq:
        writer = csv.DictWriter(arq, fieldnames=list(resultados[0]))
        writer.writeheader()
        writer.writerows(resultados)


def gravar_relatorio(pasta, experimento):
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    rows = experimento["resultados"]
    resumo = ranking(rows)
    gravar_csv(pasta/"por_cenario.csv", rows)
    gravar_csv(pasta/"resumo.csv", resumo)
    (pasta/"experimento.json").write_text(json.dumps(experimento, ensure_ascii=False, indent=2), encoding="utf-8")
    texto = ["# Comparacao de classes", "", "Cada candidato ocupa a ultima vaga; as demais classes ficam fixas.",
             "", "| Build | Grupo | Combates | Vitorias | IC aproximado de 95% |",
             "|---|---:|---:|---:|---:|"]
    for r in resumo:
        texto.append(f"| {r['build']} | {r['grupo']} | {r['simulacoes']} | {r['vitoria_pct']:.1f}% | {r['ic95_inf']:.1f}–{r['ic95_sup']:.1f}% |")
    texto += ["", f"Semente: `{experimento['metodo']['semente']}`. Tiers: {experimento['metodo']['tiers']}.",
              "", "Combates isolados com recursos cheios, sem equipamento ou pocoes. O CSV detalha tier, composicao, encontro e escolhas.",
              "", "O intervalo mede variacao dos sorteios. Builds e politica automatica nao representam todas as formas de jogar; testes de pericia e desgaste entre salas ficam fora desta bateria.",
              "", "Empates e intervalos proximos pedem mais amostras. As taxas reunem os cenarios selecionados com o mesmo peso; nao representam a frequencia das salas em producao.",
              "", f"Combates no limite de rodadas: {sum(r['limites'] for r in rows)} (contados como nao vitorias)."]
    (pasta/"relatorio.md").write_text("\n".join(texto)+"\n", encoding="utf-8")


def gravar_grafico(caminho, resultados):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as erro:
        raise ValueError("Para --grafico, instale requirements-simulacao.txt.") from erro
    rows = ranking(resultados)[::-1]
    fig, ax = plt.subplots(figsize=(10, max(4, len(rows)*.35)))
    y = list(range(len(rows)))
    ax.barh(y, [r["vitoria_pct"] for r in rows])
    ax.errorbar([r["vitoria_pct"] for r in rows], y,
                xerr=[[r["vitoria_pct"]-r["ic95_inf"] for r in rows],
                      [r["ic95_sup"]-r["vitoria_pct"] for r in rows]], fmt="none", color="black", capsize=3)
    ax.set_yticks(y, [f"{r['build']} · grupo {r['grupo']}" for r in rows])
    ax.set_xlim(0, 100)
    ax.set_xlabel("Vitorias do grupo (%) · intervalo aproximado de 95%")
    fig.tight_layout()
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(caminho, dpi=160)
    plt.close(fig)
