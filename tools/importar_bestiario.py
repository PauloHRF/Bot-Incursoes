"""Converte um bestiário do 5etools no bestiário do bot (data/bestiario.json).

    python tools/importar_bestiario.py bestiary-mm.json

O livro tem mais regra do que o bot joga. O que entra, e como:

- CA: a primeira da lista (a forma base). HP: a média.
- Saves: os declarados; os que faltam saem do modificador do atributo.
- Golpes: a sequência do Multiattack, cada golpe com acerto e dano próprios.
  Havendo alternativas ("pique e cascos ou dois arcos"), vale a primeira. Sem
  Multiattack, a criatura dá um golpe: o primeiro corpo a corpo.
- Dano "mais 1d6 de fogo" soma no golpe. O teste que um golpe impõe ao acertar
  (a garra que paralisa) vira o efeito dele.
- Ação especial: só a principal — a de recarga, senão a de mais dano. Dano com
  "metade no sucesso" vale metade para quem resiste.
- Condição: paralisado, petrificado, inconsciente, incapacitado e atordoado
  viram "perde a vez"; as outras não têm efeito no bot.
- Traits: Táticas de Matilha e Regeneração. O resto fica de fora.
- Conjuração, ações lendárias e reações ficam de fora, anotadas em `fora`.
- Criatura sem nenhum ataque fica de fora do bestiário.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bestiario_traducao import ACOES, CRIATURAS  # noqa: E402

from src.incursoes import (  # noqa: E402
    EXPR_DANO,
    MAX_ATAQUES_DO_MONSTRO,
    _monstros_de_dict,
)
from src.motor import termos_de_dano  # noqa: E402
from src.rules import chave_comparacao  # noqa: E402

DESTINO = RAIZ / "data" / "bestiario.json"

ATRIBUTOS = {
    "str": "FOR", "dex": "DES", "con": "CON", "int": "INT", "wis": "SAB", "cha": "CAR",
    "strength": "FOR", "dexterity": "DES", "constitution": "CON",
    "intelligence": "INT", "wisdom": "SAB", "charisma": "CAR",
}

# As condições que tiram a vez de quem as sofre.
INCAPACITANTES = {"paralyzed", "petrified", "unconscious", "incapacitated", "stunned"}

# Quantos personagens uma ação em área (cone, linha, raio) atinge.
ALVOS_EM_AREA = 3
PALAVRAS_DE_AREA = (
    "cone", "line", "radius", "sphere", "cube", "each creature", "each target",
    "creatures of its choice", "creatures within", "each other creature",
)

NUMEROS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "twice": 2, "thrice": 3,
}

# Multiattack que o texto não diz em número.
GOLPES_POR_NOME = {
    "Hydra": 5,  # "tantas mordidas quanto cabeças": começa com cinco
}


# ------------------------------------------------------------------ texto

def texto(entradas) -> str:
    """Junta as entradas de uma ação (strings e listas aninhadas) numa linha só."""
    if isinstance(entradas, str):
        return entradas
    if isinstance(entradas, list):
        return " ".join(texto(e) for e in entradas)
    if isinstance(entradas, dict):
        partes = []
        for chave in ("entries", "items", "entry"):
            if chave in entradas:
                partes.append(texto(entradas[chave]))
        return " ".join(partes)
    return ""


def sem_tags(linha: str) -> str:
    """'{@condition prone}' vira 'prone'; '{@hit 4}' vira '+4'."""
    linha = re.sub(r"\{@hit (-?\d+)\}", r"+\1", linha)
    linha = re.sub(r"\{@(?:atk|h|recharge)[^}]*\}", "", linha)
    linha = re.sub(r"\{@\w+ ([^}|]*)[^}]*\}", r"\1", linha)
    return " ".join(linha.split())


def nome_limpo(nome: str) -> str:
    """'Bite (Wolf or Hybrid Form Only)' vira 'Bite'; tira a recarga do nome."""
    nome = re.sub(r"\{@recharge[^}]*\}", "", nome)
    nome = re.sub(r"\([^)]*\)", "", nome)
    return " ".join(nome.split())


def dado(expressao: str) -> str:
    """'2d10 + 6' vira '2d10+6'."""
    return re.sub(r"\s+", "", expressao)


def media(expressao: str) -> float:
    total = 0.0
    for sinal, quantos, faces in termos_de_dano(expressao):
        total += sinal * (quantos * (faces + 1) / 2 if faces else quantos)
    return total


def traduzir_acao(nome: str) -> str:
    return ACOES.get(nome_limpo(nome), nome_limpo(nome))


# ------------------------------------------------------------------ partes

def _dano_do_trecho(trecho: str) -> str | None:
    """O primeiro dano de um trecho: '7 ({@damage 2d4 + 2})' ou só '1'."""
    achado = re.search(r"\{@damage ([^}]+)\}", trecho)
    if achado:
        return dado(achado.group(1))
    solto = re.match(r"\s*(\d+)\s+\w+ damage", trecho)
    return solto.group(1) if solto else None


def efeito_de_save(bruto: str, nome: str) -> dict | None:
    """O teste que o texto impõe: save, CD, dano, metade e atordoamento.

    Devolve None se o teste não faz nada que o bot jogue (derrubar, agarrar).
    """
    achado = re.search(
        r"\{@dc (\d+)\}\s+(Strength|Dexterity|Constitution|Intelligence|Wisdom|Charisma)"
        r" saving throw",
        bruto,
    )
    if not achado:
        return None
    depois = bruto[achado.end():]
    # Dano e condição de quem falha. Ficam de fora as frases de outra regra:
    # "se o veneno derrubar o alvo a 0 HP, ele fica paralisado" e "num sucesso".
    frases = [
        f for f in re.split(r"(?<=\.)\s", depois)
        if "0 hit points" not in f and not f.lower().startswith(("on a success", "on a successful"))
    ]
    frase = " ".join(frases)
    dano = None
    falha = re.search(r"\{@damage ([^}]+)\}\)?\s*[\w ]*?damage", frase)
    if falha:
        dano = dado(falha.group(1))
    condicoes = set(re.findall(r"\{@condition ([a-z]+)", frase))
    atordoa = 1 if condicoes & INCAPACITANTES else 0
    if not dano and not atordoa:
        return None
    efeito = {
        "nome": nome,
        "save": ATRIBUTOS[achado.group(2).lower()],
        "cd": int(achado.group(1)),
        "dano": dano or "",
        "atordoa": atordoa,
        "metade": bool(dano) and "half as much" in frase,
        "save_repete": bool(atordoa) and "repeat the saving throw" in depois,
    }
    return efeito


def golpe_de_acao(acao: dict) -> dict | None:
    """Uma ação de ataque do livro vira um golpe do bot."""
    bruto = texto(acao.get("entries", []))
    acerto = re.search(r"\{@hit (-?\d+)\}", bruto)
    if not acerto or "{@h}" not in bruto:
        return None
    apos = bruto.split("{@h}", 1)[1]
    fim = re.search(r"\.\s", apos)
    frase = apos[: fim.start()] if fim else apos
    base = _dano_do_trecho(frase)
    if not base:
        return None
    partes = [base]
    for extra in re.finditer(r"plus (\d+)(?: \(\{@damage ([^}]+)\}\))?", frase):
        partes.append(dado(extra.group(2)) if extra.group(2) else extra.group(1))
    dano = "+".join(partes)
    nome = traduzir_acao(acao["name"])
    golpe = {"nome": nome, "ataque": int(acerto.group(1)), "dano": dano}
    # O teste pode vir na mesma frase do dano ("..., e o alvo faz CON CD 11").
    efeito = efeito_de_save(apos, nome)
    if efeito:
        golpe["efeito"] = {k: v for k, v in efeito.items() if k != "nome"}
    golpe["_corpo_a_corpo"] = "{@atk m" in bruto
    # "uma criatura caída", "agarrada pelo devorador de mentes": o bot não joga
    # essas condições, então o golpe só entra se for o único da criatura.
    golpe["_condicional"] = bool(
        re.search(r"grappled by|restrained|incapacitated|prone", bruto.split("{@h}")[0])
    )
    golpe["_chave"] = _chave_de_arma(nome_limpo(acao["name"]))
    return golpe


def _chave_de_arma(nome: str) -> str:
    """Forma de comparar 'claws' do texto com 'Claw' da ação."""
    nome = nome.lower().strip()
    irregulares = {"hooves": "hoof", "teeth": "tooth", "talons": "talon"}
    if nome in irregulares:
        return irregulares[nome]
    for sufixo in ("es", "s"):
        if nome.endswith(sufixo) and len(nome) > 4 and not nome.endswith("ss"):
            candidato = nome[: -len(sufixo)]
            if sufixo == "es" and not candidato.endswith(("sh", "ch", "x", "s")):
                continue
            return candidato
    return nome


def _peso_do_golpe(golpe: dict) -> float:
    efeito = golpe.get("efeito") or {}
    return (
        media(golpe["dano"])
        + (media(efeito["dano"]) if efeito.get("dano") else 0)
        + (10 if efeito.get("atordoa") else 0)
    )


def sequencia(nome_criatura: str, multi: str | None, golpes: list[dict]) -> list[dict]:
    """A ordem dos golpes na vez da criatura, lida do texto do Multiattack."""
    principal = next((g for g in golpes if g["_corpo_a_corpo"]), golpes[0])
    if not multi:
        # Um golpe só: o que mais pesa, contando o teste que ele impõe.
        return [max(golpes, key=_peso_do_golpe)]
    linha = sem_tags(multi).lower()
    faz = re.search(r"\bmakes?\b(.*)", linha)
    corpo = faz.group(1) if faz else linha
    # Alternativas: vale a primeira sequência descrita.
    corpo = " ".join(re.sub(r"\beither\b", "", corpo).split())
    corpo = re.split(r"\bor\b|\balternatively\b", corpo)[0]
    numero = r"(one|two|three|four|five|six|seven|eight|nine|ten)"
    total_achado = re.search(numero + r"\b", corpo)
    total = NUMEROS[total_achado.group(1)] if total_achado else GOLPES_POR_NOME.get(nome_criatura)

    por_arma = {}
    for g in golpes:
        por_arma.setdefault(g["_chave"], g)
    corpo_a_corpo = next((g for g in golpes if g["_corpo_a_corpo"]), None)
    a_distancia = next((g for g in golpes if not g["_corpo_a_corpo"]), None)

    def achar(arma: str):
        arma = arma.strip()
        if arma in ("melee", "melee weapon", "weapon", ""):
            return corpo_a_corpo or golpes[0]
        if arma in ("ranged", "ranged weapon"):
            return a_distancia or golpes[0]
        palavras = arma.split()
        return (
            por_arma.get(_chave_de_arma(arma))
            or por_arma.get(_chave_de_arma(palavras[-1]))
            or por_arma.get(_chave_de_arma(palavras[0]))
        )

    fim = r"(?=[,(\u2014;]| and\b|\.|$)"
    dono = r"(?:its|his|her|their)"
    montada: list[dict] = []
    padroes = (
        # "one with its bite", "two with its claws"
        numero + r" (?:with|using) " + dono + r" ([a-z' -]+?)" + fim,
        # "four attacks with its tendrils", "two attacks, with its glaive"
        numero + r" (?:[a-z]+ )?attacks?,? (?:with|using) " + dono + r" ([a-z' -]+?)" + fim,
        # "one to constrict"
        numero + r" to ([a-z]+)" + fim,
        # "two claw attacks", "two unarmed strikes", "two melee attacks"
        numero + r" ([a-z'-]+(?: [a-z'-]+)?) (?:attacks?|strikes?)\b",
    )
    usados: list[tuple[int, int]] = []
    genericos: list[tuple[int, list]] = []
    sem_golpe = False
    for padrao in padroes:
        for achado in re.finditer(padrao, corpo):
            if any(a < achado.end() and achado.start() < b for a, b in usados):
                continue  # o mesmo trecho ja foi lido por um padrao anterior
            quantos, arma = achado.group(1), achado.group(2)
            if arma in ("unarmed", ):
                arma = "unarmed strike"
            golpe = achar(arma)
            if golpe is None:
                # Arma que não causa dano (o tentáculo que só agarra): não entra.
                sem_golpe = True
                continue
            usados.append((achado.start(), achado.end()))
            destino = genericos if arma in ("melee", "ranged", "weapon") else montada
            destino.append((achado.start(), [golpe] * NUMEROS[quantos]))
    # "três ataques corpo a corpo: um com o cabelo e dois com a espada" — o
    # genérico só conta quando nenhum golpe foi nomeado.
    montada = montada or genericos
    montada.sort(key=lambda par: par[0])
    montada = [g for _, lista in montada for g in lista]
    if sem_golpe and montada:
        return montada[:MAX_ATAQUES_DO_MONSTRO]
    total = total or max(1, len(montada))
    if len(montada) == 1 and total > 1:
        # "três ataques com a espada longa": a arma citada vale para todos.
        principal = montada[0]
    if len(montada) < total:
        montada += [principal] * (total - len(montada))
    return montada[:MAX_ATAQUES_DO_MONSTRO]


def especial(acoes: list[dict]) -> tuple[dict | None, list[str]]:
    """A ação especial principal da criatura e o nome das que ficaram de fora."""
    candidatas = []
    for acao in acoes:
        bruto = texto(acao.get("entries", []))
        if "{@atk" in bruto or acao["name"].startswith("Multiattack"):
            continue
        nome = traduzir_acao(acao["name"])
        efeito = efeito_de_save(bruto, nome)
        if not efeito:
            continue
        recarga = re.search(r"\{@recharge ?(\d)?\}", acao["name"])
        por_dia = re.search(r"\((\d)/Day\)", acao["name"])
        if recarga:
            efeito["recarga"] = int(recarga.group(1) or 6)
        elif por_dia and por_dia.group(1) == "1":
            # Uma vez por dia: sai na primeira rodada e quase nunca volta.
            efeito["recarga"] = 6
        else:
            efeito["cada"] = 2
        minusculo = bruto.lower()
        efeito["alvos"] = (
            ALVOS_EM_AREA if any(p in minusculo for p in PALAVRAS_DE_AREA) else 1
        )
        efeito["texto"] = ""
        candidatas.append(efeito)
    if not candidatas:
        return None, []
    candidatas.sort(
        key=lambda e: (
            "recarga" in e,
            media(e["dano"]) if e["dano"] else 0,
            e["atordoa"],
        ),
        reverse=True,
    )
    return candidatas[0], [c["nome"] for c in candidatas[1:]]


# ------------------------------------------------------------------ criatura

def _modificador(valor: int) -> int:
    return (valor - 10) // 2


def _ca(bruta) -> int:
    primeira = bruta[0]
    return primeira if isinstance(primeira, int) else primeira["ac"]


def _cr(bruto) -> str:
    return bruto["cr"] if isinstance(bruto, dict) else str(bruto)


def _id(nome: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", nome.lower()).strip("-")


def converter(criatura: dict) -> tuple[dict | None, str]:
    """Uma criatura do livro no formato do bot, ou None com o motivo."""
    nome_en = criatura["name"]
    acoes = criatura.get("action") or []
    golpes = [g for g in (golpe_de_acao(a) for a in acoes) if g]
    if not golpes:
        return None, "sem nenhum ataque"
    golpes = [g for g in golpes if not g["_condicional"]] or golpes
    multi = next(
        (texto(a["entries"]) for a in acoes if a["name"].startswith("Multiattack")), None
    )
    ordem = sequencia(nome_en, multi, golpes)

    saves = {ATRIBUTOS[a]: _modificador(criatura[a]) for a in ("str", "dex", "con", "int", "wis", "cha")}
    for atributo, valor in (criatura.get("save") or {}).items():
        saves[ATRIBUTOS[atributo]] = int(valor)

    habilidade, outras = especial(acoes)
    fora = []
    if criatura.get("spellcasting"):
        fora.append("Conjuração")
    if criatura.get("legendary"):
        fora.append("Ações lendárias")
    for reacao in criatura.get("reaction") or []:
        fora.append(f"Reação: {traduzir_acao(reacao['name'])}")
    fora += [f"Ação: {n}" for n in outras]

    traits = {t["name"]: texto(t.get("entries", [])) for t in criatura.get("trait") or []}
    regeneracao = 0
    for nome_trait, corpo in traits.items():
        if nome_trait.startswith("Regeneration"):
            achado = re.search(r"regains (\d+) hit points", corpo)
            regeneracao = int(achado.group(1)) if achado else 0

    nome = CRIATURAS.get(nome_en, nome_en)
    saida = {
        "id": _id(nome_en),
        "nome": nome,
        "nome_en": nome_en,
        "cr": _cr(criatura["cr"]),
        "ca": _ca(criatura["ac"]),
        "hp": criatura["hp"]["average"],
        "golpes": [{k: v for k, v in g.items() if not k.startswith("_")} for g in ordem],
        "saves": saves,
    }
    if habilidade:
        saida["habilidade"] = habilidade
    if "Pack Tactics" in traits:
        saida["matilha"] = True
    if regeneracao:
        saida["regeneracao"] = regeneracao
    if fora:
        saida["fora"] = fora
    return saida, ""


def validar(entrada: dict) -> list[str]:
    """Passa a entrada pelo mesmo leitor das salas: o que ele recusar, a sala recusaria."""
    problemas: list[str] = []
    _monstros_de_dict(dict(entrada), entrada["nome_en"], problemas)
    for golpe in entrada["golpes"]:
        if not EXPR_DANO.match(golpe["dano"]):
            problemas.append(f"{entrada['nome_en']}: dano '{golpe['dano']}'")
    return problemas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("arquivo", type=Path, help="bestiário do 5etools (JSON)")
    parser.add_argument("--saida", type=Path, default=DESTINO)
    args = parser.parse_args()

    livro = json.loads(args.arquivo.read_text(encoding="utf-8"))["monster"]
    criaturas, excluidas, problemas = [], [], []
    for criatura in livro:
        convertida, motivo = converter(criatura)
        if convertida is None:
            excluidas.append(f"{criatura['name']} ({motivo})")
            continue
        problemas += validar(convertida)
        criaturas.append(convertida)

    nomes: dict[str, str] = {}
    for c in criaturas:
        chave = chave_comparacao(c["nome"])
        if chave in nomes:
            problemas.append(f"nome repetido: '{c['nome']}' ({nomes[chave]} e {c['nome_en']})")
        nomes[chave] = c["nome_en"]
    sem_traducao = [c["nome_en"] for c in criaturas if c["nome_en"] not in CRIATURAS]

    if problemas:
        print("Nada foi gravado. Problemas:", file=sys.stderr)
        for p in problemas:
            print(f"  - {p}", file=sys.stderr)
        return 1

    criaturas.sort(key=lambda c: c["nome"])
    args.saida.write_text(
        json.dumps({"criaturas": criaturas}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    print(f"{len(criaturas)} criaturas gravadas em {args.saida}.")
    if excluidas:
        print(f"{len(excluidas)} de fora: {', '.join(excluidas)}")
    if sem_traducao:
        print(f"{len(sem_traducao)} sem tradução: {', '.join(sem_traducao)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
