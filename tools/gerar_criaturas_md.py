"""Escreve docs/CRIATURAS.md: as fichas do bestiário, tier por tier.

É o documento de consulta de quem escreve sala e objetivo: o que cada
criatura tem, agrupado pela faixa de CR que define qual tier a encontra.
Gerado do bestiário em vez de mantido à mão — o arquivo é refeito com um
comando depois de cada importação:

    .venv/Scripts/python.exe tools/gerar_criaturas_md.py

Tudo que sai daqui vem de data/bestiario.json e de src/bestiario.py. Para
mudar o documento, importe o bestiário de novo — não edite o arquivo.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import bestiario  # noqa: E402

SAIDA = RAIZ / "docs" / "CRIATURAS.md"


def cr_legivel(criatura: dict[str, Any]) -> str:
    """O CR como está escrito no livro: '1/2' continua '1/2'."""
    return str(criatura.get("cr", "0") or "0")


def faixa_legivel(lo: float, hi: float, maior: float) -> str:
    """'CR 0 a 1', e 'CR 14 ou mais' no topo, onde o teto é artificial."""
    def numero(v: float) -> str:
        return str(int(v)) if v == int(v) else str(v)

    if hi >= maior:
        return f"CR {numero(lo)} ou mais"
    return f"CR {numero(lo)} a {numero(hi)}"


def golpes_de(criatura: dict[str, Any]) -> str:
    """Os golpes que a criatura dá numa rodada.

    É o TAMANHO DA LISTA que manda, e não `meta.num_acoes`: quem monta a
    criatura é `incursoes._monstros_de_dict`, e lá `ataques = len(golpes)`.
    O `num_acoes` não é lido por ninguém no motor — ele e a lista coincidem
    hoje porque o importador já expande uma, mas descrever o campo que o
    motor ignora faria este documento mentir na primeira importação que
    saísse torta.
    """
    golpes = criatura.get("golpes") or []
    if not golpes:
        return "— *(só habilidade)*"
    # Golpe igual repetido vira "×N", para a célula não repetir o mesmo
    # texto: 82 criaturas atacam duas ou mais vezes com o mesmo golpe.
    saida: list[str] = []
    for golpe in golpes:
        texto = f"{golpe['nome']} +{golpe['ataque']} {golpe['dano']}"
        if golpe.get("efeito"):
            efeito = golpe["efeito"]
            marca = ", ".join(efeito.get("debuff") or []) or "efeito"
            texto += f" + {marca} (save {efeito.get('save')} CD {efeito.get('cd')})"
        if saida and saida[-1][0] == texto:
            saida[-1][1] += 1
        else:
            saida.append([texto, 1])
    return " · ".join(t if n == 1 else f"{t} ×{n}" for t, n in saida)


def habilidade_de(criatura: dict[str, Any]) -> str:
    """A habilidade com prazo de recarga ou ritmo fixo, e o que ela cobra."""
    h = criatura.get("habilidade")
    if not h:
        return "—"
    partes = [f"**{h['nome']}**"]
    if h.get("dano"):
        partes.append(h["dano"])
    if h.get("save") and h["save"] != "ATK":
        cd = f" CD {h['cd']}" if h.get("cd") else ""
        partes.append(f"save {h['save']}{cd}")
    elif h.get("save") == "ATK":
        partes.append("rola ataque")
    alvos = h.get("alvos")
    if alvos and alvos != 1:
        partes.append(f"em {alvos}")
    if h.get("debuff"):
        partes.append("deixa " + ", ".join(h["debuff"]))
    if h.get("atordoa"):
        partes.append(f"atordoa {h['atordoa']}")
    if h.get("metade"):
        partes.append("metade quem resiste")
    # Recarga sai CARREGADA: a habilidade cai na rodada 1 e depois espera o
    # d6. Quem escreve objetivo precisa saber disso antes do playtest.
    if h.get("recarga"):
        partes.append(f"*rec. {h['recarga']}+, sai na rodada 1*")
    elif h.get("cada"):
        partes.append(f"*a cada {h['cada']} rodadas*")
    return " · ".join(partes)


def notas_de(criatura: dict[str, Any]) -> str:
    """O que muda o combate e não cabe nas outras colunas."""
    notas = []
    if criatura.get("matilha"):
        notas.append("matilha")
    if criatura.get("regeneracao"):
        notas.append(f"regenera {criatura['regeneracao']}/rodada")
    for atributo in criatura.get("saves_vantagem") or []:
        notas.append(f"vantagem em {atributo}")
    meta = criatura.get("meta") or {}
    if meta.get("funcao"):
        notas.append(", ".join(meta["funcao"]).lower())
    return " · ".join(notas) or "—"


def nome_de(criatura: dict[str, Any]) -> str:
    """O nome traduzido, com o original quando ele é diferente."""
    nome, original = criatura["nome"], criatura.get("nome_en") or criatura["nome"]
    if nome == original:
        return f"**{nome}**"
    return f"**{nome}** *({original})*"


def tabela(cabecalho: list[str], linhas: list[list[str]]) -> list[str]:
    saida = ["| " + " | ".join(cabecalho) + " |",
             "|" + "|".join("---" for _ in cabecalho) + "|"]
    saida += ["| " + " | ".join(l) + " |" for l in linhas]
    saida.append("")
    return saida


def documento() -> str:
    criaturas = bestiario.carregar()
    por_tier: dict[int, list[dict[str, Any]]] = {t: [] for t in bestiario.FAIXAS_DE_CR}
    for c in criaturas:
        por_tier[bestiario.tier_do_cr(bestiario.cr_de(c))].append(c)

    maior = max(hi for _lo, hi in bestiario.FAIXAS_DE_CR.values())
    L = [
        "# Criaturas",
        "",
        "**Este arquivo é gerado.** Ele sai de `tools/gerar_criaturas_md.py`, que lê o",
        "bestiário. Para refazer depois de importar criaturas novas:",
        "",
        "```",
        ".venv/Scripts/python.exe tools/gerar_criaturas_md.py",
        "```",
        "",
        f"São **{len(criaturas)} criaturas**, e uma sala pode chamar qualquer uma delas",
        "**só pelo nome** — os números saem daqui no lugar das colunas vazias. A regra",
        "de como isso funciona está em [mecanicas/bestiario.md](mecanicas/bestiario.md);",
        "aqui estão as fichas.",
        "",
        "## Como ler",
        "",
        "**Os números são os do tier 1**, como todo conteúdo do bot. Quem escala é o",
        "combate, na hora de abrir, pelo tier do GRUPO que entrou: HP e dano crescem",
        "pelo mesmo multiplicador do HP do grupo, e CA, ataque e saves sobem pelo",
        "ajuste do bônus de proficiência. Uma criatura de 52 HP aqui tem 182 no tier 4.",
        "",
        "**O agrupamento é por faixa de CR**, que é a tabela que decide a dificuldade do",
        "jogo: `tools/balanco.py` tira dela a criatura típica de cada tier, e é contra",
        "essa criatura que as 14 classes são medidas. O campo `meta.tier` de cada entrada",
        "do JSON **não** é isto — ele vem do arquivo de origem e discorda desta tabela em",
        "um terço do bestiário. Quem manda na dificuldade é a faixa de CR.",
        "",
        "**Golpes por rodada** é a lista inteira: a criatura dá todos eles a cada",
        "rodada, e `×2` quer dizer o mesmo golpe duas vezes. Quem monta a criatura usa",
        "`ataques = len(golpes)` — o `num_acoes` do JSON não é lido por ninguém.",
        "",
        "**Habilidade com `rec. N+` sai carregada**: ela cai na **rodada 1** e só volta",
        "quando o d6 da criatura tirar N ou mais. É a surpresa que mais pega quem monta",
        "objetivo — um Golpe Poderoso de 5d6 em 3 alvos abre o combate, não o fecha.",
        "",
        "**Traços do livro que o motor não implementa** ficam no campo `fora` de cada",
        "entrada do JSON (invisibilidade, voo, mudança de forma, regeneração condicional).",
        "Eles não valem em jogo: o que vale é o que está nas colunas abaixo.",
        "",
    ]

    L += tabela(
        ["Tier", "Faixa de CR", "Criaturas"],
        [
            [str(tier), faixa_legivel(lo, hi, maior), str(len(por_tier[tier]))]
            for tier, (lo, hi) in bestiario.FAIXAS_DE_CR.items()
        ],
    )

    for tier, (lo, hi) in bestiario.FAIXAS_DE_CR.items():
        grupo = sorted(por_tier[tier], key=lambda c: c["nome"].lower())
        L += [
            f"## Tier {tier} — {faixa_legivel(lo, hi, maior)}",
            "",
            f"{len(grupo)} criaturas.",
            "",
        ]
        L += tabela(
            ["Criatura", "CR", "CA", "HP", "Golpes por rodada", "Habilidade", "Notas"],
            [
                [
                    nome_de(c), cr_legivel(c), str(c["ca"]), str(c["hp"]),
                    golpes_de(c), habilidade_de(c), notas_de(c),
                ]
                for c in grupo
            ],
        )

    L += [
        "---",
        "",
        "Gerado por `tools/gerar_criaturas_md.py` a partir de `data/bestiario.json`.",
        "Não edite à mão: rode o gerador.",
        "",
    ]
    return "\n".join(L)


def main() -> int:
    criaturas = bestiario.carregar()
    if not criaturas:
        print("bestiário vazio: nada a gerar", file=sys.stderr)
        return 1
    SAIDA.write_text(documento(), encoding="utf-8")
    print(f"{SAIDA.relative_to(RAIZ)}: {len(criaturas)} criaturas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
