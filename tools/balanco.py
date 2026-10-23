"""Escreve docs/BALANCO.md: mede o jogo e aponta os desequilíbrios.

    .venv/Scripts/python.exe tools/balanco.py

Nada aqui é opinião e nada é derivado à mão: o dano sai de
`motor.atacar_inimigo`, com as mesmas rolagens do combate de verdade, e as
referências de criatura saem do bestiário. Rodar de novo depois de mexer num
número diz na hora o que mudou — é para isso que isto é um gerador e não um
texto.

O que ele NÃO sabe medir, e diz quando não sabe: reação (socorrer um teste
falhado), vantagem, e efeito que não vira HP. Essas aparecem com valor zero e
uma nota, nunca como "fraca".
"""
from __future__ import annotations

import json
import random
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import ameaca, classes as cl, habilidades as H, motor, rules  # noqa: E402

SAIDA = RAIZ / "docs" / "BALANCO.md"
RODADAS = 20000
RNG = random.Random(20261024)

# Usos por masmorra Média, medidos no mapa de 12 salas com 1 de Descanso.
POR_MASMORRA = {"combate": 3.08, "descanso": 1.42, "incursao": 1.00}

# Chance de a criatura falhar num save de magia de jogador, medida no
# bestiário contra a CD de 8+acerto do tier.
FALHA = 0.55


# ------------------------------------------------------- a mesa de referência
def referencia_do_bestiario() -> dict[int, tuple[int, int, int]]:
    """CA, ataque e dano por rodada da criatura típica de cada tier.

    Sai da mediana da faixa de CR que aquele tier encontra, e não de um número
    escolhido: é o bestiário de 385 criaturas que define a dificuldade.
    """
    arquivo = RAIZ / "data" / "bestiario.json"
    criaturas = json.loads(arquivo.read_text(encoding="utf-8"))["criaturas"]

    def cr(c) -> float:
        texto = str(c.get("cr", "0"))
        if "/" in texto:
            a, b = texto.split("/")
            return float(a) / float(b)
        return float(texto or 0)

    faixas = {1: (0, 1), 2: (2, 4), 3: (5, 8), 4: (9, 13), 5: (14, 99)}
    saida = {}
    for tier, (lo, hi) in faixas.items():
        grupo = [c for c in criaturas if lo <= cr(c) <= hi]
        cas, ataques, danos = [], [], []
        for c in grupo:
            golpes = c.get("golpes") or []
            if not golpes:
                continue
            cas.append(c["ca"])
            ataques.append(max(g["ataque"] for g in golpes))
            quantos = c.get("num_acoes") or 1
            danos.append(sum(H.media_do_dado(g["dano"]) for g in golpes[:quantos]))
        saida[tier] = (
            round(st.median(cas)),
            round(st.median(ataques)),
            round(st.median(danos)),
        )
    return saida


REFERENCIA = referencia_do_bestiario()


def mesa(tier: int) -> dict:
    """A sala típica daquele tier: o que bate, quantos batem, quanto o grupo tem."""
    _ca, _atk, dano = REFERENCIA[tier]
    return dict(
        dano_inimigo=dano,
        inimigos=2 if tier == 1 else (3 if tier < 5 else 4),
        hp=cl.numeros("clerigo", rules.nivel_do_tier(tier)).hp,
        grupo=5,
        rodadas=3,
    )


# ------------------------------------------------------------- as escolhas
def melhores_escolhas(classe_id: str, nivel: int, nota) -> dict:
    """As opções que maximizam aquele critério, uma por ESCOLHA do tier.

    Mede o TETO da classe: o jogador que escolhe para bater escolhe assim, e é
    o teto que decide se uma classe está absurda.
    """
    feitas: dict[str, str] = {}
    for _t, h in cl.habilidades(classe_id, nivel):
        if not h.decidivel or (h.escolha or {}).get("tipo") != "opcao":
            continue
        melhor, melhor_nota = None, -1.0
        for o in h.escolha["opcoes"]:
            valor = nota(cl.efeitos(classe_id, nivel, dict(feitas, **{h.id: o["id"]})))
            if valor > melhor_nota:
                melhor, melhor_nota = o["id"], valor
        if melhor:
            feitas[h.id] = melhor
    return feitas


def nota_de_dano(efeitos: dict) -> float:
    return (
        efeitos.get("ataques", 1) * 100
        + efeitos.get("dano_extra", 0) * 10
        + H.media_do_dado(efeitos.get("dano_bonus") or "") * 10
        + (20 - efeitos.get("critico_em", 20))
        + efeitos.get("dano_ferido", 0)
    )


# ----------------------------------------------------------------- as medidas
def dpr(classe_id: str, tier: int) -> float:
    """Dano por rodada contra a CA de referência, rolado pelo motor."""
    nivel = rules.nivel_do_tier(tier)
    numeros = cl.numeros(classe_id, nivel)
    efeitos = cl.efeitos(classe_id, nivel, melhores_escolhas(classe_id, nivel, nota_de_dano))
    c = motor.Combatente(
        1, "Teste", numeros.ca + efeitos.get("ca", 0),
        numeros.acerto + efeitos.get("acerto", 0),
        numeros.dano, numeros.hp, numeros.hp,
    )
    c.ataques = efeitos.get("ataques", 1)
    c.critico_em = efeitos.get("critico_em", 20)
    c.dano_extra = efeitos.get("dano_extra", 0)
    c.dano_ferido = efeitos.get("dano_ferido", 0)
    c.dano_bonus = efeitos.get("dano_bonus", "")
    ca_alvo = REFERENCIA[tier][0]
    total = 0
    for _ in range(RODADAS):
        alvo = motor.Inimigo(0, "Alvo", ca_alvo, 0, "1d1", 10**9, 10**9)
        for _golpe in range(max(1, c.ataques)):
            total += motor.atacar_inimigo(c, alvo, RNG).dano
    return total / RODADAS


def rodadas_de_pe(classe_id: str, tier: int) -> float:
    """Quantas rodadas o personagem aguenta sob a criatura de referência."""
    nivel = rules.nivel_do_tier(tier)
    numeros = cl.numeros(classe_id, nivel)
    efeitos = cl.efeitos(
        classe_id, nivel, melhores_escolhas(classe_id, nivel, lambda e: e.get("ca", 0))
    )
    ca = numeros.ca + efeitos.get("ca", 0)
    _ca_ref, ataque, dano = REFERENCIA[tier]
    # 1 natural erra sempre, 20 acerta sempre; o resto é o total contra a CA.
    faces = [d for d in range(1, 21) if d == 20 or (d != 1 and d + ataque >= ca)]
    return numeros.hp / max(0.1, len(faces) / 20 * dano)


def cura_por_masmorra(classe_id: str, tier: int) -> float:
    """O máximo de HP que a classe devolve ao grupo numa masmorra Média."""
    nivel = rules.nivel_do_tier(tier)
    m = mesa(tier)

    def soma(escolhas: dict) -> float:
        total = 0.0
        for _t, h in cl.habilidades(classe_id, nivel, escolhas):
            a = h.acao or {}
            if not h.usos:
                continue
            vezes = h.vezes * POR_MASMORRA.get(h.escopo, 1.0)
            if a.get("fracao"):
                total += a["fracao"] * m["hp"] * vezes
            if a.get("cura_fracao"):
                total += a["cura_fracao"] * m["hp"] * m["grupo"] * vezes
            porturno = (a.get("efeitos") or {}).get("cura_por_turno")
            if porturno:
                total += porturno * m["hp"] * a.get("turnos", 1) * vezes
        return total

    base = melhores_escolhas(classe_id, nivel, lambda e: 0)
    melhor = soma(base)
    for _t, h in cl.habilidades(classe_id, nivel):
        if not h.decidivel or (h.escolha or {}).get("tipo") != "opcao":
            continue
        for o in h.escolha["opcoes"]:
            melhor = max(melhor, soma(dict(base, **{h.id: o["id"]})))
    return melhor


def melhor_pericia(classe_id: str, tier: int) -> int:
    nivel = rules.nivel_do_tier(tier)
    efeitos = cl.efeitos(
        classe_id, nivel,
        melhores_escolhas(
            classe_id, nivel,
            lambda e: e.get("bonus_teste", 0) + len(e.get("expertise") or []) * 5,
        ),
    )
    return rules.mod_pericia("Atletismo", cl.numeros(classe_id, nivel), ["Atletismo"], None, efeitos)


def media_do_valor(expressao, tier: int) -> float:
    """A média de um dado. Forma e Polymorph guardam um dado POR TIER."""
    if isinstance(expressao, dict):
        expressao = expressao.get(tier) or expressao.get(max(expressao))
    return H.media_do_dado(expressao) if isinstance(expressao, str) and expressao else 0.0


def valor_da_ativa(classe_id: str, tier: int, h, ataques: int) -> tuple[float, str]:
    """HP-equivalente por uso: dano causado, cura dada, THP dado, dano negado.

    Numa moeda só, para dar para comparar uma bola de fogo com uma cura. É
    aproximado de propósito: a pergunta é "tem alguma absurda?", e para isso
    ordem de grandeza basta.
    """
    a = h.acao or {}
    m = mesa(tier)
    partes: list[str] = []
    v = 0.0
    alvos = a.get("alvos", 1)
    n = m["inimigos"] if alvos == "todos" else (alvos if isinstance(alvos, int) else 1)

    if a.get("dano") and a.get("tipo") not in ("forma", "invocar"):
        bruto = media_do_valor(a["dano"], tier) * n
        if not a.get("sem_save"):
            bruto *= FALHA + (1 - FALHA) * 0.5 if a.get("metade") else FALHA
        v += bruto
        partes.append(f"{bruto:.0f} de dano")
    if a.get("dano_por_rodada"):
        bruto = media_do_valor(a["dano_por_rodada"], tier) * a.get("turnos", 3) * 0.5
        v += bruto
        partes.append(f"{bruto:.0f} sangrando")
    if a.get("dano_em_todos"):
        bruto = media_do_valor(a["dano_em_todos"], tier) * m["inimigos"]
        v += bruto
        partes.append(f"{bruto:.0f} em todos")

    if a.get("tipo") == "golpes":
        q = a.get("quantidade")
        golpes = q if q is not None else max(1, a.get("acoes", 1)) * max(1, ataques)
        golpes *= n if isinstance(alvos, int) else 1
        por_golpe = H.media_do_dado(cl.numeros(classe_id, rules.nivel_do_tier(tier)).dano) * 0.6
        bruto = max(0, golpes - ataques) * por_golpe
        bruto += media_do_valor(a.get("dano_bonus"), tier)
        bruto += media_do_valor(a.get("bonus_uma_vez"), tier)
        if a.get("critico"):
            bruto += por_golpe
        v += bruto
        if bruto:
            partes.append(f"{bruto:.0f} de golpe a mais")

    if a.get("fracao"):
        bruto = a["fracao"] * m["hp"]
        v += bruto
        partes.append(f"{bruto:.0f} de cura")
    if a.get("cura_fracao"):
        bruto = a["cura_fracao"] * m["hp"] * m["grupo"]
        v += bruto
        partes.append(f"{bruto:.0f} de cura no grupo")
    if (a.get("efeitos") or {}).get("cura_por_turno"):
        bruto = a["efeitos"]["cura_por_turno"] * m["hp"] * a.get("turnos", 1)
        v += bruto
        partes.append(f"{bruto:.0f} de regeneração")

    for chave, mult in (
        ("thp", m["grupo"] if a.get("tipo") == "grupo" else 1),
        ("thp_proprio", 1),
        ("thp_alvo", 1),
    ):
        if a.get(chave):
            bruto = media_do_valor(a[chave], tier) * mult
            v += bruto
            partes.append(f"{bruto:.0f} de THP")
    if a.get("thp_por_tier") and a.get("tipo") != "forma":
        v += a["thp_por_tier"] * tier
        partes.append(f"{a['thp_por_tier'] * tier} de THP")

    if a.get("atordoa"):
        turnos = a["atordoa"] * (n if alvos == "todos" else 1)
        bruto = turnos * m["dano_inimigo"]
        v += bruto
        partes.append(f"{bruto:.0f} de dano negado ({turnos} turno(s) de criatura)")

    if a.get("tipo") == "invocar":
        bruto = media_do_valor(a["dano"], tier) * 0.6 * m["rodadas"] + a["hp"] * 0.3
        v += bruto
        partes.append(f"{bruto:.0f} de aliado conjurado")

    if a.get("tipo") == "forma":
        turnos = a.get("turnos", 3)
        proprio = H.media_do_dado(cl.numeros(classe_id, rules.nivel_do_tier(tier)).dano)
        da_fera = media_do_valor(a.get("dano"), tier) * max(1, a.get("ataques", 1))
        bruto = max(0, da_fera - proprio) * 0.6 * turnos + a.get("thp_por_tier", 0) * tier
        v += bruto
        partes.append(f"{bruto:.0f} da forma em {turnos} rodadas")

    if a.get("tipo") == "duracao":
        ef = a.get("efeitos") or {}
        turnos = a.get("turnos", 1)
        if ef.get("reducao_dano"):
            bruto = ef["reducao_dano"] * m["dano_inimigo"] * turnos
            v += bruto
            partes.append(f"{bruto:.0f} de dano cortado")
        if ef.get("ameaca_fator") is not None:
            bruto = m["dano_inimigo"] * turnos * 0.2 * a.get("alvos", 1)
            v += bruto
            partes.append(f"{bruto:.0f} de mira desviada")
        if ef.get("dano_extra"):
            v += ef["dano_extra"] * turnos * max(1, ataques)
            partes.append("dano extra enquanto dura")
        if ef.get("ataques"):
            v += H.media_do_dado(cl.numeros(classe_id, rules.nivel_do_tier(tier)).dano) * 0.6 * turnos
            partes.append("um ataque a mais enquanto dura")

    return v, "; ".join(partes) or "efeito que esta conta não cobre (reação, vantagem)"


def salas_de_teste() -> list[dict]:
    salas = []
    for pasta in ("bancos", "incursoes"):
        for arquivo in (RAIZ / "data" / pasta).glob("*.json"):
            dados = json.loads(arquivo.read_text(encoding="utf-8"))
            candidatas = list(dados.get("salas") or [])
            if dados.get("objetivo"):
                candidatas.append(dados["objetivo"])
            salas += [s for s in candidatas if s.get("cd")]
    return salas


def chance_do_grupo(mods: list[int], cd: int, alvo: int, tentativas: int = 40000) -> float:
    """Chance de o grupo somar margem suficiente. Cada um rola uma vez."""
    ganhou = 0
    for _ in range(tentativas):
        progresso = 0
        for mod in mods:
            total = RNG.randint(1, 20) + mod
            if total >= cd:
                progresso += total - cd
            if progresso >= alvo:
                break
        ganhou += progresso >= alvo
    return ganhou / tentativas * 100


# ------------------------------------------------------------------ o texto
def tabela(cabecalho: list[str], linhas: list[list[str]]) -> list[str]:
    saida = ["| " + " | ".join(cabecalho) + " |",
             "|" + "|".join("---" for _ in cabecalho) + "|"]
    saida += ["| " + " | ".join(l) + " |" for l in linhas]
    saida.append("")
    return saida


def documento() -> str:
    L: list[str] = []
    nome = {cid: c.nome for cid, c in cl.CLASSES.items()}

    L += [
        "# Rodada de balanceamento",
        "",
        "**Este arquivo é gerado.** Ele sai de `tools/balanco.py`, que mede o jogo",
        "rodando o motor de verdade. Para refazer depois de mexer num número:",
        "",
        "```",
        ".venv/Scripts/python.exe tools/balanco.py",
        "```",
        "",
        "## Como ler",
        "",
        "O **dano por rodada** sai de `motor.atacar_inimigo`, 20 mil rolagens por",
        "célula, contra a CA da criatura típica do tier. Não é fórmula: é o que",
        "acontece na mesa, com 1 natural errando e crítico dobrando dados.",
        "",
        "A criatura típica sai do bestiário de 385 — a mediana da faixa de CR que",
        "cada tier encontra, não um número escolhido a dedo:",
        "",
    ]
    L += tabela(
        ["Tier", "CA", "Ataque", "Dano/rodada"],
        [[f"T{t}", str(ca), f"+{atk}", str(dano)] for t, (ca, atk, dano) in REFERENCIA.items()],
    )
    L += [
        "Cada classe é medida no seu **teto**: as escolhas de tier são resolvidas",
        "para maximizar o que está sendo medido, porque é o teto que diz se uma",
        "classe está absurda.",
        "",
        "O que esta conta **não** sabe medir: reação que socorre um teste falhado,",
        "vantagem, e efeito que não vira HP. Essas aparecem com valor zero e uma",
        "nota — nunca como \"fraca\".",
        "",
    ]

    # ---------------------------------------------------------------- dano
    dpr_tab = {cid: [dpr(cid, t) for t in range(1, 6)] for cid in cl.CLASSES}
    L += ["## Dano por rodada", ""]
    L += tabela(
        ["Classe"] + [f"T{t}" for t in range(1, 6)],
        [
            [nome[cid]] + [f"{v:.1f}" for v in linha]
            for cid, linha in sorted(dpr_tab.items(), key=lambda x: -x[1][4])
        ],
    )
    L += ["Espalhamento por tier:", ""]
    linhas = []
    for t in range(1, 6):
        col = {cid: v[t - 1] for cid, v in dpr_tab.items()}
        pior, melhor = min(col, key=col.get), max(col, key=col.get)
        linhas.append([
            f"T{t}", f"{col[pior]:.1f} ({nome[pior]})",
            f"{col[melhor]:.1f} ({nome[melhor]})", f"{col[melhor] / col[pior]:.1f}x",
        ])
    L += tabela(["Tier", "Piso", "Teto", "Razão"], linhas)

    # --------------------------------------------------------- durabilidade
    dur = {cid: [rodadas_de_pe(cid, t) for t in range(1, 6)] for cid in cl.CLASSES}
    L += ["## Durabilidade: rodadas de pé sob a criatura de referência", ""]
    L += tabela(
        ["Classe"] + [f"T{t}" for t in range(1, 6)],
        [
            [nome[cid]] + [f"{v:.1f}" for v in linha]
            for cid, linha in sorted(dur.items(), key=lambda x: -x[1][4])
        ],
    )

    # ------------------------------------------------------------- cura
    L += ["## Cura devolvida ao grupo, por masmorra Média (HP)", ""]
    for t in (3, 5):
        curas = {cid: cura_por_masmorra(cid, t) for cid in cl.CLASSES}
        L += [f"**Tier {t}:**", ""]
        L += tabela(
            ["Classe", "HP por masmorra"],
            [[nome[cid], f"{v:.0f}"] for cid, v in sorted(curas.items(), key=lambda x: -x[1]) if v],
        )

    # ----------------------------------------------------------- ameaça
    L += ["## Ameaça: fatia da atenção das criaturas", "",
          "Num grupo de cinco onde os outros quatro estão no piso (2).", ""]
    L += tabela(
        ["Classe", "Ameaça", "Fatia"],
        [
            [nome[cid], str(ameaca.inicial(cid)),
             f"{ameaca.porcentagens([ameaca.inicial(cid), 2, 2, 2, 2])[0]:.1f}%"]
            for cid in sorted(cl.CLASSES, key=lambda c: -ameaca.inicial(c))
        ],
    )
    L += ["O uniforme seria 20%.", ""]

    # ---------------------------------------------------------- perícia
    L += ["## Perícia: melhor modificador por tier", ""]
    L += tabela(
        ["Classe"] + [f"T{t}" for t in range(1, 6)],
        [
            [nome[cid]] + [f"{melhor_pericia(cid, t):+d}" for t in range(1, 6)]
            for cid in sorted(cl.CLASSES, key=lambda c: -melhor_pericia(c, 5))
        ],
    )

    # -------------------------------------------------------- habilidades
    L += ["## Habilidades: valor em HP-equivalente por masmorra", "",
          "Uso × frequência de recarga. `>>` marca o que está acima de 2,5× a",
          "mediana do tier, e `<<` o que está abaixo de 2,5× para baixo.", ""]
    for tier in range(1, 6):
        nivel = rules.nivel_do_tier(tier)
        itens = []
        for cid, c in cl.CLASSES.items():
            ataques = cl.efeitos(cid, nivel, {}).get("ataques", 1)
            for h in c.habilidades_do_tier(tier):
                if h.tipo != cl.ATIVA or not h.acao:
                    continue
                por_uso, de_onde = valor_da_ativa(cid, tier, h, ataques)
                vezes = h.vezes * POR_MASMORRA.get(h.escopo, 1.0) if h.usos else 0
                itens.append((por_uso * vezes, por_uso, vezes, c.nome, h.nome, de_onde))
        if not itens:
            continue
        itens.sort(reverse=True)
        mediana = sorted(x[0] for x in itens)[len(itens) // 2]
        L += [f"### Tier {tier} — mediana {mediana:.0f} HP-eq, {len(itens)} ativas", ""]
        linhas = []
        for total, por_uso, vezes, classe, hab, de_onde in itens:
            marca = ">>" if total > mediana * 2.5 else ("<<" if total < mediana / 2.5 else "")
            linhas.append([marca, classe, hab, f"{total:.0f}", f"{por_uso:.0f} × {vezes:.2f}", de_onde])
        L += tabela(["", "Classe", "Habilidade", "Por masmorra", "Conta", "De onde vem"], linhas)

    # ------------------------------------------------------------ escopo
    L += ["## O escopo de recarga se autocorrige", "",
          "Por uso, quem recarrega por incursão é o mais forte; multiplicado pela",
          "frequência, os três escopos encostam. Isto é desenho funcionando.", ""]
    por_escopo: dict[str, list[float]] = defaultdict(list)
    for tier in (1, 3, 5):
        nivel = rules.nivel_do_tier(tier)
        for cid, c in cl.CLASSES.items():
            ataques = cl.efeitos(cid, nivel, {}).get("ataques", 1)
            for h in c.habilidades_do_tier(tier):
                if h.tipo != cl.ATIVA or not h.acao or not h.usos:
                    continue
                v, _ = valor_da_ativa(cid, tier, h, ataques)
                if v:
                    por_escopo[h.escopo].append(v)
    L += tabela(
        ["Escopo", "Ativas", "Mediana por uso", "Usos/masmorra", "Mediana por masmorra"],
        [
            [e, str(len(por_escopo[e])), f"{st.median(por_escopo[e]):.0f}",
             f"{POR_MASMORRA[e]:.2f}", f"{st.median(por_escopo[e]) * POR_MASMORRA[e]:.0f}"]
            for e in ("combate", "descanso", "incursao") if por_escopo[e]
        ],
    )

    # A mesma magia com escopo diferente entre classes.
    repetidas: dict[str, list] = defaultdict(list)
    for tier in range(1, 6):
        for cid, c in cl.CLASSES.items():
            for h in c.habilidades_do_tier(tier):
                if h.tipo == cl.ATIVA and h.usos:
                    repetidas[h.nome].append((c.nome, tier, h.escopo, h.vezes))
    divergentes = {
        n: onde for n, onde in repetidas.items()
        if len(onde) > 1 and len({e for _c, _t, e, _v in onde}) > 1
    }
    if divergentes:
        L += ["### A mesma magia com disponibilidade diferente", "",
              "Mesmo nome, mesmo efeito, escopo de recarga diferente entre classes:", ""]
        linhas = []
        for n, onde in sorted(divergentes.items()):
            for classe, tier, escopo, vezes in sorted(onde, key=lambda x: -POR_MASMORRA[x[2]]):
                linhas.append([n, classe, f"T{tier}", f"{vezes}x por {escopo}",
                               f"{vezes * POR_MASMORRA[escopo]:.2f}"])
        L += tabela(["Magia", "Classe", "Tier", "Recarga", "Usos/masmorra"], linhas)

    # ------------------------------------------------------- tier vazio
    L += ["## Tier que não melhora nada ofensivo", ""]
    vazios = []
    for cid, c in cl.CLASSES.items():
        for t in range(1, 5):
            a, b = c.tiers[t], c.tiers[t + 1]
            if a.acerto == b.acerto and H.media_do_dado(a.dano) == H.media_do_dado(b.dano):
                vazios.append([nome[cid], f"T{t} → T{t + 1}", f"+{a.acerto}", a.dano])
    if vazios:
        L += ["Só HP e CA sobem. Como a CA da criatura de referência sobe junto, o",
              "dano por rodada **cai** nessa passagem.", ""]
        L += tabela(["Classe", "Passagem", "Acerto (igual)", "Dano (igual)"], vazios)
    else:
        L += ["Nenhum: toda passagem de tier melhora acerto ou dano.", ""]

    # ----------------------------------------------------------- testes
    salas = salas_de_teste()
    faixas = sorted(Counter((s["cd"], s.get("alvo_progresso")) for s in salas).items())
    L += ["## Testes de sala", "",
          f"As {len(salas)} salas de teste do conteúdo caem em faixas fechadas, com",
          "CD e alvo de progresso acoplados:", ""]
    L += tabela(
        ["CD", "Alvo de progresso", "Salas", "Fatia"],
        [[str(cd), str(alvo), str(q), f"{q / len(salas) * 100:.0f}%"]
         for (cd, alvo), q in faixas],
    )
    tipico = {t: melhor_pericia("guerreiro", t) for t in range(1, 6)}
    L += ["Chance de um grupo de cinco superar a sala, cada um rolando uma vez:", ""]
    linhas = []
    for t in range(1, 6):
        mods = [tipico[t]] * 5
        linhas.append([f"T{t}", f"{tipico[t]:+d}"]
                      + [f"{chance_do_grupo(mods, cd, alvo):.0f}%" for (cd, alvo), _q in faixas])
    L += tabela(["Tier", "Mod típico"] + [f"CD {cd}" for (cd, _a), _q in faixas], linhas)
    L += ["As CDs não escalam com o tier: o mesmo banco de salas serve a todos.", ""]

    return "\n".join(L).rstrip() + "\n"


def main() -> int:
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(documento(), encoding="utf-8")
    print(f"{SAIDA.relative_to(RAIZ)}: {len(cl.CLASSES)} classes medidas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
