"""Converte um bestiário 2024 do 5etools num arquivo do banco de criaturas.

    python tools/importar_livro.py bestiary-abh.json --previa   # só mostra
    python tools/importar_livro.py bestiary-abh.json            # grava data/criaturas/abh.json

É o irmão de `importar_bestiario.py` para o formato novo dos livros (`{@atkr m}`,
`{@actSave dex} {@dc 11}`, `{@actSaveFail}`), que o importador do Monster Manual
não lê. As regras são as dele, e as que mudaram estão marcadas:

- CA: a primeira. HP: a média. CR: o texto do livro.
- Saves: os declarados; os que faltam saem do modificador do atributo.
- Golpes: a sequência do Multiattack. Com alternativas ("usando A ou B em
  qualquer combinação"), vale a primeira arma citada. Sem Multiattack, um golpe:
  o que mais pesa. Dano extra ("plus 7 (2d6) Fire") soma no golpe; o que só vale
  sob condição ("se estiver Sangrando") fica de fora.
- Ação especial: só a principal — a de recarga, senão a de mais dano. Pode ser
  de resistência ou um ataque com recarga, que vira habilidade de `ATK`. NOVO: o
  "e usa X" do Multiattack 2024 vira a habilidade, no ritmo dela, porque no bot
  a habilidade toma a vez inteira. Ação bônus só entra se não houver ação.
- Condição, pela tabela fixa decidida em 26/11/2026 (ver `CONDICOES`). NOVO: a
  condição que o golpe impõe SEM teste no livro ganha um teste no bot, porque o
  efeito de golpe do motor sempre tem um — o atributo sai do debuff e a CD é
  alta de propósito: 12 + o bônus do golpe (ver `CD_SEM_TESTE_SOBRE_O_ATAQUE`).
  A prévia avisa cada uma.
- Traits: Táticas de Matilha e Regeneração. Conjuração, ações lendárias,
  bônus, reações e o resto ficam anotados em `fora`.
- Fora do banco: reimpressão (`_copy`), criatura sem CR, invocação (HP sem
  média) e criatura sem ataque.

Nada é gravado com problema: a entrada passa pelo mesmo leitor das salas, e nome
que já existe no bestiário (ou em outro livro) barra a gravação.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from livros_traducao import ACOES, AMBIENTES, CRIATURAS, NOMEADAS  # noqa: E402

from src import bestiario  # noqa: E402
from src.incursoes import MAX_ATAQUES_DO_MONSTRO, _monstros_de_dict  # noqa: E402
from src.motor import media_do_dano  # noqa: E402
from src.rules import chave_comparacao  # noqa: E402

PASTA = RAIZ / "data" / "criaturas"

ATRIBUTOS = {"str": "FOR", "dex": "DES", "con": "CON", "int": "INT", "wis": "SAB", "cha": "CAR"}
POR_EXTENSO = {
    "strength": "FOR", "dexterity": "DES", "constitution": "CON",
    "intelligence": "INT", "wisdom": "SAB", "charisma": "CAR",
}

# A tabela decidida em 26/11/2026. VEZ é "perde a vez" (atordoa); o resto é o
# id da condição em src/condicoes.py. Derrubado, agarrado, surdo, velocidade e
# "sem reação" não estão aqui de propósito: sem posição no bot, não fazem nada.
VEZ = "vez"
CONDICOES = {
    "frightened": "medo",
    "poisoned": "envenenado",
    "blinded": "perdicao",
    "exhaustion": "exaustao",
    "paralyzed": VEZ,
    "stunned": VEZ,
    "incapacitated": VEZ,
    "restrained": VEZ,
    "unconscious": VEZ,
    "petrified": VEZ,
    "charmed": VEZ,
}
# A condição que o livro impõe sem teste ganha um: este é o atributo.
SAVE_DO_EFEITO = {
    "medo": "SAB", "envenenado": "CON", "perdicao": "CAR", "exaustao": "CON",
    "deterioracao": "CON", VEZ: "CON",
}
# "Refaz o save no fim do turno": sem prazo fixo no livro, o bot precisa de um
# teto. 2 é o que as 385 mais usam com save_repete.
RODADAS_COM_REPETE = 2
# A condição que o livro impõe SEM teste ganha um, com CD "bem alta": 12 + o
# bônus do golpe, número escolhido por ele em 26/11/2026. A CD de uma criatura
# 5e costuma ser o bônus de ataque + 8, então isto fica 4 acima do que o próprio
# livro cobraria num teste dela — Szass Tam (+13) paralisa com CD 25. É alta de
# propósito: no livro o efeito nem tinha teste.
CD_SEM_TESTE_SOBRE_O_ATAQUE = 12

# Criaturas que o banco não leva, com o porquê.
PULAR = {
    "Drow Priestess of Lolth": "já existe no Monster Manual; fica a de lá (decidido em 26/11/2026)",
}

ALVOS_EM_AREA = 3
PALAVRAS_DE_AREA = (
    "emanation", "cone", "sphere", "line", "cylinder", "cube", "each creature",
    "each other creature", "creatures of its choice", "each enemy",
)
NUMEROS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
NUM = r"(one|two|three|four|five|six|seven|eight|nine|ten)"

# Multiattack que o texto não diz em número ("tantas mordidas quanto cabeças").
GOLPES_POR_NOME = {
    "Aku'mai": 3,  # "Aku'mai has three heads" (traço Tearing the Void)
}

TIPOS_DE_DANO = {
    "slashing": "cortante", "piercing": "perfurante", "bludgeoning": "contundente",
    "fire": "fogo", "cold": "gélido", "lightning": "elétrico", "acid": "ácido",
    "poison": "veneno", "psychic": "psíquico", "necrotic": "necrótico",
    "radiant": "radiante", "force": "energia", "thunder": "trovejante",
}

XP_POR_CR = {
    "0": 10, "1/8": 25, "1/4": 50, "1/2": 100, "1": 200, "2": 450, "3": 700,
    "4": 1100, "5": 1800, "6": 2300, "7": 2900, "8": 3900, "9": 5000,
    "10": 5900, "11": 7200, "12": 8400, "13": 10000, "14": 11500, "15": 13000,
    "16": 15000, "17": 18000, "18": 20000, "19": 22000, "20": 25000,
    "21": 33000, "22": 41000, "23": 50000, "24": 62000, "25": 75000,
    "26": 90000, "27": 105000, "28": 120000, "29": 135000, "30": 155000,
}


# ------------------------------------------------------------------ texto

def texto(entradas: Any) -> str:
    """As entradas de uma ação (strings e listas aninhadas) numa linha só."""
    if isinstance(entradas, str):
        return entradas
    if isinstance(entradas, list):
        return " ".join(texto(e) for e in entradas)
    if isinstance(entradas, dict):
        return " ".join(texto(entradas[c]) for c in ("entries", "items", "entry") if c in entradas)
    return ""


def sem_tags(linha: str) -> str:
    """'{@condition Prone|XPHB}' vira 'Prone'; '{@hit 4}' vira '+4'."""
    linha = re.sub(r"\{@hit (-?\d+)\}", r"+\1", linha)
    linha = re.sub(r"\{@(?:atkr?|h|hom|recharge|actSave\w*|actTrigger|actResponse)[^}]*\}", "", linha)
    linha = re.sub(r"\{@variantrule [^}|]*\|[^}|]*\|([^}]*)\}", r"\1", linha)
    linha = re.sub(r"\{@\w+ ([^}|]*)[^}]*\}", r"\1", linha)
    return " ".join(linha.split())


def nome_limpo(nome: str) -> str:
    """'Bite (Vampire Form Only)' vira 'Bite'; tira a recarga e o '(1/Day)'."""
    nome = re.sub(r"\{@recharge[^}]*\}", "", nome)
    nome = re.sub(r"\([^)]*\)", "", nome)
    return " ".join(nome.split())


def dado(expressao: str) -> str:
    return re.sub(r"\s+", "", expressao)


def traduzir_acao(nome: str) -> str:
    limpo = nome_limpo(nome)
    return ACOES.get(limpo, limpo)


def frases(trecho: str) -> list[str]:
    return [f for f in re.split(r"(?<=\.)\s+(?=[A-Z{])", trecho) if f.strip()]


def _id(nome: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", nome.lower()).strip("-")


# ------------------------------------------------------------------ efeitos

def condicoes_do_trecho(trecho: str, avisos: list[str], onde: str) -> tuple[list[str], int, bool]:
    """Debuffs, rodadas sem agir e se refaz o save, lidos de um trecho do livro.

    Frase que começa com "If the target is already" fica de fora: é a regra do
    segundo golpe na mesma vítima, que o bot não acompanha.
    """
    debuffs: list[str] = []
    vez = False
    for frase in frases(trecho):
        limpa = sem_tags(frase)
        if re.match(r"If (?:the target|it) (?:is |has )?already", limpa):
            continue
        achadas = re.findall(r"\{@condition (\w+)", frase)
        achadas += re.findall(r"\b(Frightened|Poisoned|Blinded|Paralyzed|Stunned|Incapacitated|"
                              r"Restrained|Unconscious|Petrified|Charmed) condition", frase)
        for bruto in achadas:
            alvo = CONDICOES.get(bruto.lower())
            if alvo == VEZ:
                vez = True
            elif alvo and alvo not in debuffs:
                debuffs.append(alvo)
        if re.search(r"Hit Points? maximum decreases", limpa) and "deterioracao" not in debuffs:
            debuffs.append("deterioracao")
        if re.search(r"Disadvantage on (?:attack rolls|saving throws)", limpa) and not achadas:
            avisos.append(f"{onde}: desvantagem no livro, que o bot não joga")
    repete = vez and bool(re.search(r"repeats? the sav", trecho))
    rodadas = (RODADAS_COM_REPETE if repete else 1) if vez else 0
    return debuffs, rodadas, repete


def danos_do_trecho(trecho: str) -> list[str]:
    """Os danos de quem falha, sem os condicionais ('se estiver caído, +2d6')."""
    saida = []
    for frase in frases(trecho):
        if sem_tags(frase).startswith("If "):
            continue
        for achado in re.finditer(r"\{@damage ([^}]+)\}\)?\s*([\w ]*?)damage(\s+if\b)?", frase):
            if not achado.group(3):
                saida.append(dado(achado.group(1)))
    return saida


def tipo_do_dano(trecho: str) -> Optional[str]:
    achado = re.search(r"\b([A-Z][a-z]+) damage", sem_tags(trecho))
    return TIPOS_DE_DANO.get(achado.group(1).lower()) if achado else None


def efeito_de_save(nome_acao: str, bruto: str, avisos: list[str], onde: str) -> Optional[dict]:
    """O teste que a ação impõe: atributo, CD, dano, metade e condições."""
    achado = re.search(r"\{@actSave (\w+)\}\s*\{@dc (\d+)\}", bruto)
    if achado:
        save, cd = ATRIBUTOS[achado.group(1).lower()], int(achado.group(2))
        resto = bruto[achado.end():]
    else:
        achado = re.search(
            r"\{@dc (\d+)\}\s+(Strength|Dexterity|Constitution|Intelligence|Wisdom|Charisma)"
            r" saving throw", bruto)
        achado = achado or re.search(
            r"(Strength|Dexterity|Constitution|Intelligence|Wisdom|Charisma)"
            r" \{@variantrule Saving Throw[^}]*\}\s*\{@dc (\d+)\}", bruto)
        if not achado:
            return None
        grupos = achado.groups()
        atributo = next(g for g in grupos if not g.isdigit())
        cd = int(next(g for g in grupos if g.isdigit()))
        save = POR_EXTENSO[atributo.lower()]
        resto = bruto[achado.end():]
    falha = resto
    if "{@actSaveFail}" in resto:
        falha = resto.split("{@actSaveFail}", 1)[1]
    falha = re.split(r"\{@actSaveSuccess(?:OrFail)?\}", falha)[0]
    sucesso = resto.split("{@actSaveSuccess}", 1)[1] if "{@actSaveSuccess}" in resto else resto
    danos = danos_do_trecho(falha)
    debuffs, atordoa, repete = condicoes_do_trecho(falha, avisos, onde)
    if not danos and not debuffs and not atordoa:
        return None
    efeito: dict[str, Any] = {"nome": traduzir_acao(nome_acao), "save": save, "cd": cd}
    if danos:
        efeito["dano"] = "+".join(danos)
        tipo = tipo_do_dano(falha)
        if tipo:
            efeito["tipo"] = tipo
        if re.search(r"half (?:as much )?damage|half damage", sem_tags(sucesso), re.IGNORECASE):
            efeito["metade"] = True
    if debuffs:
        efeito["debuff"] = debuffs
    if atordoa:
        efeito["atordoa"] = atordoa
    if repete:
        efeito["save_repete"] = True
    texto_alvo = sem_tags(resto.split("{@actSaveFail}")[0] if "{@actSaveFail}" in resto else resto[:200]).lower()
    ate = re.search(r"up to " + NUM + r" creatures", texto_alvo)
    if ate:
        efeito["alvos"] = NUMEROS[ate.group(1)]
    elif any(p in texto_alvo for p in PALAVRAS_DE_AREA):
        efeito["alvos"] = ALVOS_EM_AREA
    else:
        efeito["alvos"] = 1
    return efeito


def ritmo(nome_acao: str) -> dict[str, int]:
    """'{@recharge 5}' é recarga 5; '(1/Day)' sai uma vez (recarga 6); o resto, a cada 2."""
    recarga = re.search(r"\{@recharge ?(\d)?\}", nome_acao)
    if recarga:
        return {"recarga": int(recarga.group(1) or 6)}
    if re.search(r"\(1/Day", nome_acao):
        return {"recarga": 6}
    return {"cada": 2}


# ------------------------------------------------------------------ golpes

def golpe_de_acao(acao: dict, tier: int, avisos: list[str]) -> Optional[dict]:
    """Uma ação de ataque do livro vira um golpe do bot."""
    bruto = texto(acao.get("entries", []))
    acerto = re.search(r"\{@hit (-?\d+)\}", bruto)
    if not acerto or "{@h}" not in bruto or not re.search(r"\{@atkr? ", bruto):
        return None
    apos = bruto.split("{@h}", 1)[1]
    primeira = frases(apos)[0] if frases(apos) else apos
    base = re.search(r"\{@damage ([^}]+)\}", primeira)
    solto = re.match(r"\s*(\d+)\s+\w+ damage", primeira)
    if not base and not solto:
        return None
    partes: list[str] = []
    inicio_extra = 0
    if base and (not solto or base.start() < (solto.end() if solto else 0) + 5):
        partes.append(dado(base.group(1)))
        inicio_extra = base.end()
    else:
        partes.append(solto.group(1))
        inicio_extra = solto.end()
    for extra in re.finditer(
        r"(?:plus|and)\s+(?:(\d+)\s*)?(?:\(\{@damage ([^}]+)\}\)|\{@damage ([^}]+)\})?\s*([A-Z][a-z]+) damage(\s+if\b)?",
        primeira[inicio_extra:],
    ):
        if extra.group(5):
            avisos.append(f"{acao['name']}: dano extra condicional ficou de fora")
            continue
        partes.append(dado(extra.group(2) or extra.group(3) or extra.group(1) or "0"))
    nome = traduzir_acao(acao["name"])
    golpe: dict[str, Any] = {"nome": nome, "ataque": int(acerto.group(1)), "dano": "+".join(partes)}
    tipo = tipo_do_dano(primeira)
    if tipo:
        golpe["tipo"] = tipo
    onde = nome_limpo(acao["name"])
    # Teste dentro do golpe ("e o alvo faz CON CD 13")...
    efeito = efeito_de_save(acao["name"], apos, avisos, onde)
    if efeito is None:
        # ...ou condição sem teste, que o motor só sabe jogar com teste.
        debuffs, atordoa, repete = condicoes_do_trecho(apos, avisos, onde)
        if debuffs or atordoa:
            chave = VEZ if atordoa else debuffs[0]
            efeito = {
                "nome": nome,
                "save": SAVE_DO_EFEITO[chave],
                "cd": int(acerto.group(1)) + CD_SEM_TESTE_SOBRE_O_ATAQUE,
            }
            if debuffs:
                efeito["debuff"] = debuffs
            if atordoa:
                efeito["atordoa"] = atordoa
            if repete:
                efeito["save_repete"] = True
            avisos.append(
                f"{onde}: o livro impõe {', '.join(debuffs + (['perde a vez'] if atordoa else []))}"
                f" sem teste; no bot virou {efeito['save']} CD {efeito['cd']}"
            )
    if efeito:
        efeito.pop("alvos", None)
        efeito.pop("tipo", None)
        golpe["efeito"] = efeito
    golpe["_corpo_a_corpo"] = "{@atkr m" in bruto or "{@atk m" in bruto
    golpe["_chave"] = onde.lower()
    golpe["_recarga"] = "{@recharge" in acao["name"]
    return golpe


def _peso(golpe: dict) -> float:
    efeito = golpe.get("efeito") or {}
    return (
        media_do_dano(golpe["dano"])
        + (media_do_dano(efeito["dano"]) if efeito.get("dano") else 0)
        + (10 if efeito.get("atordoa") else 0)
    )


def sequencia(multi: Optional[str], golpes: list[dict], avisos: list[str]) -> list[dict]:
    """A ordem dos golpes na vez da criatura, lida do Multiattack."""
    if not multi:
        return [max(golpes, key=_peso)]
    corpo = sem_tags(multi)
    corpo = frases(corpo)[0].lower() if frases(corpo) else corpo.lower()
    por_nome = {g["_chave"]: g for g in golpes}
    nomes = sorted(por_nome, key=len, reverse=True)
    achados: list[tuple[int, list[dict]]] = []
    ocupado: list[tuple[int, int]] = []
    for nome in nomes:
        for m in re.finditer(rf"\b{NUM}\s+{re.escape(nome)}s?\s+(?:attacks?|strikes?)\b", corpo):
            if any(a < m.end() and m.start() < b for a, b in ocupado):
                continue
            ocupado.append((m.start(), m.end()))
            achados.append((m.start(), [por_nome[nome]] * NUMEROS[m.group(1)]))
    generico = re.search(rf"\b{NUM}\s+(?:\w+\s+)?attacks?,?\s+(?:using|with)\s+(.+)", corpo)
    if generico and not any(a <= generico.start() < b for a, b in ocupado):
        resto = generico.group(2)
        primeiro = min(
            ((resto.find(n), n) for n in nomes if resto.find(n) >= 0), default=None
        )
        if primeiro:
            achados.append((generico.start(), [por_nome[primeiro[1]]] * NUMEROS[generico.group(1)]))
    if not achados:
        total = re.search(rf"\b{NUM}\b", corpo)
        principal = next((g for g in golpes if g["_corpo_a_corpo"]), golpes[0])
        avisos.append(f"Multiattack não lido ({corpo[:60]}...): {principal['nome']}")
        return [principal] * (NUMEROS[total.group(1)] if total else 1)
    achados.sort(key=lambda p: p[0])
    saida = [g for _, lista in achados for g in lista]
    if len(saida) > MAX_ATAQUES_DO_MONSTRO:
        avisos.append(f"{len(saida)} golpes cortados para {MAX_ATAQUES_DO_MONSTRO}")
    return saida[:MAX_ATAQUES_DO_MONSTRO]


# ------------------------------------------------------------------ criatura

def _cr(bruto: Any) -> Optional[str]:
    valor = bruto.get("cr") if isinstance(bruto, dict) else bruto
    return None if valor in (None, "None", "Unknown") else str(valor)


def _tipo(m: dict) -> tuple[str, list[str]]:
    t = m.get("type")
    if isinstance(t, dict):
        tags = [x if isinstance(x, str) else x.get("tag", "") for x in t.get("tags") or []]
        return t.get("type", ""), tags
    return t or "", []


def _ambientes(nome_en: str, bruto: Optional[list[str]]) -> tuple[list[str], str]:
    """Os ambientes que o bot conhece, e a nota de onde eles vieram."""
    if nome_en in AMBIENTES:
        return list(AMBIENTES[nome_en]), "proposto na revisão"
    if not bruto:
        return [], "o livro não dá ambiente"
    bons = [a for a in bruto if a in bestiario.AMBIENTES]
    sobra = [a for a in bruto if a not in bestiario.AMBIENTES]
    nota = f"livro: {', '.join(bruto)}" if sobra else ""
    return bons, nota


def motivo_de_fora(m: dict) -> Optional[str]:
    if m.get("name") in PULAR:
        return PULAR[m["name"]]
    if "_copy" in m:
        return "reimpressão de outro livro"
    if _cr(m.get("cr")) is None:
        return "sem CR"
    if (m.get("hp") or {}).get("average") is None:
        return "invocação (HP sem média)"
    return None


def converter(m: dict, livro: str) -> tuple[Optional[dict], list[str]]:
    """Uma criatura do livro no formato do bot, com os avisos para a revisão."""
    avisos: list[str] = []
    motivo = motivo_de_fora(m)
    if motivo:
        return None, [motivo]
    nome_en = m["name"]
    cr = _cr(m["cr"])
    tier = bestiario.tier_do_cr(bestiario.cr_de({"cr": cr}))
    acoes = m.get("action") or []
    candidatos = []
    for acao in acoes:
        # Cada golpe guarda os próprios avisos: o do golpe que a criatura não
        # usa (a besta de quem tem Multiattack só com a espada) é ruído.
        dele: list[str] = []
        golpe = golpe_de_acao(acao, tier, dele)
        if golpe:
            golpe["_avisos"] = dele
            candidatos.append(golpe)
    golpes = [g for g in candidatos if not g["_recarga"]] or candidatos
    if not golpes:
        return None, ["sem ataque"]
    multi = next((texto(a["entries"]) for a in acoes if a["name"].startswith("Multiattack")), None)
    if nome_en in GOLPES_POR_NOME:
        principal = next((g for g in golpes if g["_corpo_a_corpo"]), golpes[0])
        ordem = [principal] * GOLPES_POR_NOME[nome_en]
    else:
        ordem = sequencia(multi, golpes, avisos)
    for golpe in ordem:
        for aviso in golpe["_avisos"]:
            if aviso not in avisos:
                avisos.append(aviso)

    saves = {ATRIBUTOS[a]: (m.get(a, 10) - 10) // 2 for a in ATRIBUTOS}
    for atributo, valor in (m.get("save") or {}).items():
        saves[ATRIBUTOS[atributo]] = int(valor)

    # A ação especial: ações primeiro; a bônus só sem nenhuma de ação.
    usados = {g["_chave"] for g in ordem}
    especiais: list[tuple[dict, str]] = []
    for origem, lista in (("ação", acoes), ("bônus", m.get("bonus") or [])):
        if origem == "bônus" and especiais:
            break
        for acao in lista:
            if acao["name"].startswith("Multiattack"):
                continue
            bruto = texto(acao.get("entries", []))
            if re.search(r"\{@atkr? ", bruto):
                golpe = next((g for g in candidatos if g["_chave"] == nome_limpo(acao["name"]).lower()), None)
                if golpe and golpe["_recarga"]:
                    efeito = {"nome": golpe["nome"], "alvos": 1, "save": "ATK", "dano": golpe["dano"]}
                    if golpe.get("tipo"):
                        efeito["tipo"] = golpe["tipo"]
                    efeito.update(ritmo(acao["name"]))
                    especiais.append((efeito, origem))
                continue
            efeito = efeito_de_save(acao["name"], bruto, avisos, nome_limpo(acao["name"]))
            if efeito:
                efeito.update(ritmo(acao["name"]))
                especiais.append((efeito, origem))
    habilidade = None
    if especiais:
        especiais.sort(
            key=lambda p: ("recarga" in p[0], media_do_dano(p[0].get("dano") or "0"), p[0].get("atordoa", 0)),
            reverse=True,
        )
        habilidade, origem = especiais[0]
        if origem == "bônus":
            avisos.append(f"habilidade veio de ação bônus ({habilidade['nome']}): no bot ela toma a vez")

    traits = {t["name"]: texto(t.get("entries", [])) for t in m.get("trait") or []}
    regeneracao = 0
    for nome_trait, corpo in traits.items():
        if nome_trait.startswith("Regeneration"):
            achado = re.search(r"regains (\d+)", corpo)
            regeneracao = int(achado.group(1)) if achado else 0

    fora: list[str] = []
    resto_traits = [nome_limpo(n) for n in traits if not n.startswith(("Pack Tactics", "Regeneration"))]
    if resto_traits:
        fora.append("traços: " + ", ".join(resto_traits))
    if m.get("spellcasting"):
        fora.append("conjuração: " + ", ".join(nome_limpo(s["name"]) for s in m["spellcasting"]))
    nome_hab = habilidade["nome"] if habilidade else None
    bonus = [nome_limpo(b["name"]) for b in m.get("bonus") or [] if traduzir_acao(b["name"]) != nome_hab]
    if bonus:
        fora.append("bônus: " + ", ".join(bonus))
    if m.get("reaction"):
        fora.append("reações: " + ", ".join(nome_limpo(r["name"]) for r in m["reaction"]))
    if m.get("legendary"):
        fora.append("lendárias: " + ", ".join(nome_limpo(r["name"]) for r in m["legendary"]))
    sobras = [
        nome_limpo(a["name"]) for a in acoes
        if not a["name"].startswith("Multiattack")
        and nome_limpo(a["name"]).lower() not in usados
        and traduzir_acao(a["name"]) != nome_hab
    ]
    if sobras:
        fora.append("ações do livro: " + ", ".join(sobras))

    tipo, tags = _tipo(m)
    ambientes, nota_ambiente = _ambientes(nome_en, m.get("environment"))
    if nota_ambiente:
        avisos.append(f"ambiente: {nota_ambiente}")
    nomeada = bool(m.get("isNamedCreature") or m.get("isNpc")) or nome_en in NOMEADAS
    nome = nome_en if nomeada else CRIATURAS.get(nome_en, nome_en)
    if not nomeada and nome_en not in CRIATURAS:
        avisos.append("nome sem tradução")
    for g in ordem:
        if g["nome"] == nome_limpo(g["nome"]) and g["nome"] not in ACOES.values():
            avisos.append(f"golpe sem tradução: {g['nome']}")
    if habilidade and habilidade["nome"] not in ACOES.values():
        avisos.append(f"habilidade sem tradução: {habilidade['nome']}")

    saida: dict[str, Any] = {
        "id": _id(nome_en),
        "nome": nome,
        "nome_en": nome_en,
        "cr": cr,
        "ca": m["ac"][0] if isinstance(m["ac"][0], int) else m["ac"][0]["ac"],
        "hp": m["hp"]["average"],
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
        saida["fora"] = " | ".join(fora)
    saida["meta"] = {
        "tipo": tipo,
        "subtipo": tags,
        "num_acoes": len(ordem),
        "tier": tier,
        "xp": XP_POR_CR.get(cr, 0),
        "ambientes": ambientes,
        "fonte": m.get("source", livro.upper()),
        "nomeada": nomeada,
    }
    return saida, sorted(set(avisos), key=avisos.index)


def validar(entrada: dict) -> list[str]:
    """O mesmo leitor das salas: o que ele recusar, a sala recusaria."""
    problemas: list[str] = []
    _monstros_de_dict(dict(entrada), entrada["nome_en"], problemas)
    return problemas


# ------------------------------------------------------------------ prévia

def linha_do_efeito(e: dict) -> str:
    partes = []
    if e.get("save") == "ATK":
        partes.append("rola ataque")
    else:
        partes.append(f"{e['save']} CD {e['cd']}")
    if e.get("alvos", 1) > 1:
        partes.append(f"{e['alvos']} alvos")
    if e.get("dano"):
        partes.append(e["dano"] + (" (metade no sucesso)" if e.get("metade") else ""))
    if e.get("atordoa"):
        partes.append(f"perde a vez {e['atordoa']}" + (" (refaz o save)" if e.get("save_repete") else ""))
    if e.get("debuff"):
        partes.append(", ".join(e["debuff"]))
    if e.get("recarga"):
        partes.append(f"rec. {e['recarga']}+")
    elif e.get("cada"):
        partes.append(f"a cada {e['cada']} rodadas")
    return " · ".join(partes)


def previa(entrada: dict, avisos: list[str]) -> str:
    meta = entrada["meta"]
    titulo = entrada["nome"] + ("" if entrada["nome"] == entrada["nome_en"] else f" ({entrada['nome_en']})")
    linhas = [
        f"### {titulo}",
        f"CR {entrada['cr']} · tier {meta['tier']} · CA {entrada['ca']} · HP {entrada['hp']} · "
        f"{meta['tipo']} · ambiente: {', '.join(meta['ambientes']) or '— (serve a qualquer)'}",
    ]
    contagem: dict[str, int] = {}
    for g in entrada["golpes"]:
        rotulo = f"{g['nome']} +{g['ataque']} {g['dano']}"
        if g.get("efeito"):
            rotulo += f" [{linha_do_efeito(g['efeito'])}]"
        contagem[rotulo] = contagem.get(rotulo, 0) + 1
    linhas.append("- golpes: " + "; ".join(f"{r}{f' ×{n}' if n > 1 else ''}" for r, n in contagem.items()))
    if entrada.get("habilidade"):
        h = entrada["habilidade"]
        linhas.append(f"- habilidade: **{h['nome']}** · {linha_do_efeito(h)}")
    extras = []
    if entrada.get("matilha"):
        extras.append("matilha")
    if entrada.get("regeneracao"):
        extras.append(f"regenera {entrada['regeneracao']}")
    if extras:
        linhas.append("- traços que o bot joga: " + ", ".join(extras))
    if entrada.get("fora"):
        linhas.append(f"- fora: {entrada['fora']}")
    for aviso in avisos:
        linhas.append(f"- ⚠ {aviso}")
    return "\n".join(linhas)


def nomes_ocupados(ignorar: Optional[Path] = None) -> dict[str, str]:
    """Os nomes que já existem: o bestiário de hoje e os outros livros do banco."""
    ocupados: dict[str, str] = {}
    for c in bestiario.carregar(livros=None):
        for n in (c.get("nome_en"), c.get("nome"), c.get("id")):
            if n:
                ocupados[chave_comparacao(n)] = f"{c['nome_en']} (Monster Manual)"
    for arquivo in sorted(PASTA.glob("*.json")) if PASTA.exists() else []:
        if ignorar and arquivo.resolve() == ignorar.resolve():
            continue
        for c in json.loads(arquivo.read_text(encoding="utf-8"))["criaturas"]:
            for n in (c.get("nome_en"), c.get("nome"), c.get("id")):
                if n:
                    ocupados[chave_comparacao(n)] = f"{c['nome_en']} ({arquivo.stem})"
    return ocupados


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("arquivo", type=Path, help="bestiário 2024 do 5etools (JSON)")
    parser.add_argument("--previa", action="store_true", help="só mostra, não grava")
    parser.add_argument("--resumo", action="store_true", help="na prévia, só os números")
    args = parser.parse_args()
    # O console do Windows não é UTF-8, e a prévia tem acento e ⚠.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    livro = args.arquivo.stem.replace("bestiary-", "").lower()
    destino = PASTA / f"{livro}.json"
    fonte = json.loads(args.arquivo.read_text(encoding="utf-8"))["monster"]
    ocupados = nomes_ocupados(ignorar=destino)

    criaturas, problemas, fora_do_banco, blocos = [], [], [], []
    vistos: dict[str, str] = {}
    for m in fonte:
        entrada, avisos = converter(m, livro)
        if entrada is None:
            fora_do_banco.append(f"{m['name']} ({avisos[0]})")
            continue
        for p in validar(entrada):
            problemas.append(f"{m['name']}: {p}")
        for n in (entrada["nome_en"], entrada["nome"], entrada["id"]):
            chave = chave_comparacao(n)
            if chave in ocupados:
                problemas.append(f"{m['name']}: o nome '{n}' já é de {ocupados[chave]}")
            if chave in vistos and vistos[chave] != entrada["nome_en"]:
                problemas.append(f"{m['name']}: o nome '{n}' repete {vistos[chave]} neste livro")
            vistos[chave] = entrada["nome_en"]
        criaturas.append(entrada)
        blocos.append(previa(entrada, avisos))

    if args.previa:
        por_tier: dict[int, int] = {}
        for c in criaturas:
            por_tier[c["meta"]["tier"]] = por_tier.get(c["meta"]["tier"], 0) + 1
        print(f"# {livro.upper()}: {len(criaturas)} criaturas entram")
        print("por tier: " + ", ".join(f"T{t} {n}" for t, n in sorted(por_tier.items())))
        if fora_do_banco:
            print("ficam de fora: " + "; ".join(fora_do_banco))
        if problemas:
            print("\nPROBLEMAS (barrariam a gravação):")
            for p in problemas:
                print(f"  - {p}")
        if not args.resumo:
            print()
            print("\n\n".join(blocos))
        return 1 if problemas else 0

    if problemas:
        print("Nada foi gravado. Problemas:", file=sys.stderr)
        for p in problemas:
            print(f"  - {p}", file=sys.stderr)
        return 1
    PASTA.mkdir(parents=True, exist_ok=True)
    criaturas.sort(key=lambda c: c["nome"])
    destino.write_text(
        json.dumps({"livro": livro.upper(), "criaturas": criaturas}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    print(f"{len(criaturas)} criaturas gravadas em {destino}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
