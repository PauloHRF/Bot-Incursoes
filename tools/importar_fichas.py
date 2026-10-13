"""Converte a tabela de fichas do grupo no bestiário do bot (data/bestiario.json).

    python tools/importar_fichas.py Fichas_Monstros.json

A tabela de fichas já nasce quase no formato do bot — ela foi escrita para ele.
O que este importador acerta é o vocabulário que divergiu:

- `cada: "5-6"` é a recarga no d6, não "a cada N rodadas". Vira `recarga: 5`.
  A chave `cada` do bot quer um inteiro, e `"5-6"` cairia no default 2 sem
  reclamar — é a diferença mais perigosa das duas tabelas, porque é silenciosa.
- `debuff: ["Atordoado 2"]` é o `atordoa: 2` do bot: o número são as rodadas.
  "Impedido" é a mesma coisa — sem posicionamento, estar preso é perder a vez.
- Os outros debuffs são as condições de `src/condicoes.py`, pelo nome exato.
  Viram a lista de ids que o motor aplica.
- `save: "ATK"` fica como está: é o sinal de que a habilidade rola ataque
  contra a CA em vez de impor resistência.
- `cr` vira texto ("1/8"), que é como o resto do bot escreve.
- `id` troca `_` por `-`, a grafia que o bestiário já usava.
- `golpes` é o menu da criatura e `num_acoes` diz quantos ataques ela dá; o bot
  lê a lista como a sequência, então ela é expandida para esse tamanho.
- Os 14 nomes que ficaram em inglês e já tinham tradução voltam ao português.

E completa o que a fonte deixou em branco, sempre anotando no relatório:

- Habilidade sem `save`: pela mesma habilidade em outra criatura; não havendo
  irmã, dano sem debuff e sem CD é ATK, e debuff de veneno pede CON.
- Habilidade sem `cd`: 11 + tier, que é a progressão da própria tabela
  (T1 12, T2 13, T3 14, T4 15, T5 16).
- Saves nulos e golpe sem dano: das tabelas no topo deste arquivo, com os
  números do livro. O que não está lá e vem sem dano é agarrão, e vale 0.

Nada é inventado em silêncio: `--relatorio` lista cada preenchimento, e o que
não fechar sai na validação, que é o mesmo leitor que as salas usam.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src import condicoes  # noqa: E402
from src.incursoes import _monstros_de_dict  # noqa: E402

DESTINO = RAIZ / "data" / "bestiario.json"


# O numero no debuff sao rodadas perdidas, e as duas condicoes acabam no mesmo
# lugar: sem posicionamento no bot, estar preso e ficar atordoado sao a vez
# perdida. "Impedido 3" e tres rodadas sem agir.
PERDE_A_VEZ = ("Atordoado", "Impedido")

# A tabela sobe a CD um ponto por tier. Serve de preenchimento para a
# habilidade que veio sem CD.
CD_BASE = 11

# Habilidade sem irma para consultar: o debuff diz qual resistencia cabe.
SAVE_POR_DEBUFF = {
    "Envenenado": "CON",
    "Debilidade": "CON",
    "Deterioração": "CON",
    "Exaustão": "CON",
    "Perturbação": "SAB",
    "Medo": "SAB",
    "Tolice": "INT",
    "Insensatez": "INT",
    "Introversão": "CAR",
    "Moleza": "FOR",
    "Fraqueza": "FOR",
    "Perdição": "CAR",
    "Letargia": "DES",
}

ID_POR_NOME = {c.nome: c.id for c in condicoes.CATALOGO}

# A tabela deixou 94 nomes em inglês. Estes 14 o bestiário anterior traduzia, e
# a tradução vale: a sala que pede "Carniçal" precisa achar o Ghoul. O nome em
# inglês continua valendo na busca, pelo `nome_en`. Os outros 80 são nomes que
# não têm versão em português (Flumph, Stirge, Drider, Kenku).
TRADUCOES = {
    "Beholder": "Observador",
    "Cloaker": "Espreitador Manto",
    "Darkmantle": "Manto Negro",
    "Ghast": "Lívido",
    "Ghoul": "Carniçal",
    "Jackalwere": "Chacalobisomem",
    "Merfolk": "Tritão",
    "Piercer": "Perfurador",
    "Roc": "Roca",
    "Roper": "Laçador",
    "Treant": "Ente",
    "Umber Hulk": "Colosso Umbral",
    "Wyvern": "Serpe",
}
# O bestiário anterior também traduzia Wight por "Aparição", mas a tabela nova
# dá esse nome ao Wraith. A escolha dela manda, e o Wight fica em inglês: dois
# monstros com o mesmo nome deixariam a busca por nome ambígua.

# A ficha veio com os seis saves nulos nestas três. São os modificadores de
# atributo do livro, que é de onde o bot os tirava antes.
SAVES_QUE_FALTAM = {
    "giant_badger": {"FOR": 1, "DES": 0, "CON": 2, "INT": -4, "SAB": 1, "CAR": -3},
    "giant_bat": {"FOR": 2, "DES": 3, "CON": 0, "INT": -4, "SAB": 1, "CAR": -2},
    "giant_centipede": {"FOR": -3, "DES": 2, "CON": 1, "INT": -5, "SAB": -2, "CAR": -4},
}

# Golpe que a ficha deixou sem dano mas que tem dano no livro. O que não está
# aqui e vem sem dano é agarrão de verdade (o tentáculo do Laçador), e vale 0.
DANOS_QUE_FALTAM = {("gas_spore", "Toque"): "1"}


def _cr(valor: Any) -> str:
    """O CR como o resto do bot escreve: inteiro sem casa, fração com barra."""
    if isinstance(valor, str):
        return valor
    fracoes = {0.125: "1/8", 0.25: "1/4", 0.5: "1/2"}
    if valor in fracoes:
        return fracoes[valor]
    return str(int(valor)) if float(valor).is_integer() else str(valor)


def _recarga(cada: Any) -> Optional[int]:
    """A menor face do d6 que recarrega: '5-6' é 5, '6' é 6."""
    if cada is None:
        return None
    achado = re.match(r"\s*(\d)", str(cada))
    return int(achado.group(1)) if achado else None


def _separar_debuffs(debuffs: Any) -> tuple[list[str], int, list[str]]:
    """Divide a lista de debuffs em condições, rodadas atordoado e nomes estranhos.

    Devolve (ids do catálogo, atordoa, não reconhecidos).
    """
    condicoes_ids: list[str] = []
    atordoa = 0
    estranhos: list[str] = []
    for bruto in debuffs or []:
        texto = str(bruto).strip()
        prefixo = next((p for p in PERDE_A_VEZ if texto.startswith(p)), None)
        if prefixo:
            achado = re.search(r"(\d+)", texto)
            atordoa = max(atordoa, int(achado.group(1)) if achado else 1)
            continue
        if texto in ID_POR_NOME:
            condicoes_ids.append(ID_POR_NOME[texto])
            continue
        estranhos.append(texto)
    return condicoes_ids, atordoa, estranhos


def _saves_irmas(fichas: list[dict]) -> dict[str, str]:
    """O save que cada habilidade usa, pela maioria das criaturas que a têm.

    A fonte deixou `save` em branco em algumas; a mesma habilidade em outra
    criatura diz qual era a intenção.
    """
    votos: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for ficha in fichas:
        habilidade = ficha.get("habilidade") or {}
        save = habilidade.get("save")
        if habilidade.get("nome") and save:
            votos[habilidade["nome"]][save] += 1
    return {nome: contagem.most_common(1)[0][0] for nome, contagem in votos.items()}


def _habilidade(
    bruta: dict[str, Any],
    tier: int,
    irmas: dict[str, str],
    nota,
) -> dict[str, Any]:
    """A ação especial no formato do bot, com o que faltava preenchido."""
    saida: dict[str, Any] = {"nome": bruta["nome"], "alvos": bruta.get("alvos") or 1}

    ids, atordoa, estranhos = _separar_debuffs(bruta.get("debuff"))
    for estranho in estranhos:
        nota(f"debuff '{estranho}' não está no catálogo de condições")

    save = bruta.get("save")
    if not save:
        irma = irmas.get(bruta["nome"])
        if irma:
            save = irma
            nota(f"habilidade '{bruta['nome']}' sem save: {save}, como nas irmãs")
        elif bruta.get("dano") and not ids and not atordoa and not bruta.get("cd"):
            save = "ATK"
            nota(f"habilidade '{bruta['nome']}' sem save: ATK, pela forma (dano puro)")
        else:
            primeiro = next(
                (
                    SAVE_POR_DEBUFF[n]
                    for n in (bruta.get("debuff") or [])
                    if n in SAVE_POR_DEBUFF
                ),
                "CON",
            )
            save = primeiro
            nota(f"habilidade '{bruta['nome']}' sem save: {save}, pelo debuff")
    saida["save"] = save

    if save != "ATK":
        cd = bruta.get("cd")
        if not cd:
            cd = CD_BASE + tier
            nota(f"habilidade '{bruta['nome']}' sem CD: {cd} (11 + tier {tier})")
        saida["cd"] = cd

    for chave in ("dano", "tipo"):
        if bruta.get(chave):
            saida[chave] = bruta[chave]
    if ids:
        saida["debuff"] = ids
    if atordoa:
        saida["atordoa"] = atordoa
    if bruta.get("metade"):
        saida["metade"] = True
    if bruta.get("save_repete"):
        saida["save_repete"] = True

    recarga = bruta.get("recarga") or _recarga(bruta.get("cada"))
    if recarga:
        saida["recarga"] = recarga
    return saida


def _golpe(bruto: dict[str, Any], id_ficha: str, nota) -> dict[str, Any]:
    """Um golpe no formato do bot. Sem dano, é agarrão — ou lacuna conhecida."""
    saida: dict[str, Any] = {"nome": bruto["nome"], "ataque": bruto.get("ataque") or 0}

    dano = bruto.get("dano")
    if not dano:
        dano = DANOS_QUE_FALTAM.get((id_ficha, bruto["nome"]))
        if dano:
            nota(f"golpe '{bruto['nome']}' sem dano: {dano}, do livro")
        else:
            dano = "0"
            nota(f"golpe '{bruto['nome']}' sem dano: 0 (o golpe só agarra)")
    saida["dano"] = dano
    if bruto.get("tipo"):
        saida["tipo"] = bruto["tipo"]

    efeito = bruto.get("efeito") or {}
    if efeito:
        ids, atordoa, estranhos = _separar_debuffs(efeito.get("debuff"))
        for estranho in estranhos:
            nota(f"debuff '{estranho}' do golpe '{bruto['nome']}' não está no catálogo")
        convertido: dict[str, Any] = {
            "nome": bruto["nome"],
            "save": efeito.get("save") or "CON",
            "cd": efeito.get("cd"),
        }
        if efeito.get("dano"):
            convertido["dano"] = efeito["dano"]
        if ids:
            convertido["debuff"] = ids
        if atordoa:
            convertido["atordoa"] = atordoa
        saida["efeito"] = convertido
    return saida


def _sequencia(golpes: list[dict[str, Any]], num_acoes: int) -> list[dict[str, Any]]:
    """Os golpes da rodada, repetindo o que falta para dar `num_acoes`.

    A tabela de fichas lista os golpes *distintos* da criatura e diz em
    `num_acoes` quantos ela dá por rodada — nunca repete um nome. O bot lê a
    outra convenção: a lista É a sequência, e `ataques` é o tamanho dela. Sem
    esta expansão, 82 criaturas atacariam mais do que a ficha manda (quase
    todas Minion) e 82 menos (quase todas Boss) — infla o lixo e mutila o chefe.

    Faltando golpe, repete o último: é o "uma mordida e duas garras" do livro.
    Sobrando, valem os primeiros, que são os principais.
    """
    if not golpes or num_acoes <= 0:
        return list(golpes)
    if num_acoes <= len(golpes):
        return golpes[:num_acoes]
    return golpes + [golpes[-1]] * (num_acoes - len(golpes))


def converter(
    ficha: dict[str, Any], irmas: dict[str, str]
) -> tuple[dict[str, Any], list[str]]:
    """Uma ficha no formato do bestiário do bot, com as notas do que foi preenchido."""
    notas: list[str] = []
    nota = notas.append
    meta = ficha.get("meta") or {}
    tier = meta.get("tier") or 1
    id_ficha = ficha["id"]

    saves = dict(ficha.get("saves") or {})
    if any(valor is None for valor in saves.values()):
        do_livro = SAVES_QUE_FALTAM.get(id_ficha, {})
        for atributo, valor in list(saves.items()):
            if valor is None:
                saves[atributo] = do_livro.get(atributo, 0)
        nota("saves nulos preenchidos " + ("do livro" if do_livro else "zerados"))

    nome = ficha["nome"]
    nome_en = ficha.get("nome_en") or nome
    if nome == nome_en and nome_en in TRADUCOES:
        nome = TRADUCOES[nome_en]
        nota(f"nome traduzido: {nome_en} -> {nome}")

    saida: dict[str, Any] = {
        "id": id_ficha.replace("_", "-"),
        "nome": nome,
        "nome_en": nome_en,
        "cr": _cr(ficha["cr"]),
        "ca": ficha["ca"],
        "hp": ficha["hp"],
        "golpes": [
            _golpe(g, id_ficha, nota)
            for g in _sequencia(ficha.get("golpes") or [], meta.get("num_acoes") or 0)
        ],
        "saves": saves,
    }
    if ficha.get("habilidade"):
        habilidade = _habilidade(ficha["habilidade"], tier, irmas, nota)
        # Habilidade sem dano, sem atordoamento e sem debuff não faz nada: a
        # ficha a deixou pela metade. A criatura fica, com os golpes dela, em
        # vez de a entrada inteira ser recusada por causa de uma ação vazia.
        if habilidade.get("dano") or habilidade.get("atordoa") or habilidade.get("debuff"):
            saida["habilidade"] = habilidade
        else:
            nota(f"habilidade '{habilidade['nome']}' descartada: não faz nada na ficha")
    if ficha.get("matilha"):
        saida["matilha"] = ficha["matilha"]
    if ficha.get("regeneracao"):
        saida["regeneracao"] = ficha["regeneracao"]
    if ficha.get("saves_vantagem"):
        saida["saves_vantagem"] = ficha["saves_vantagem"]
    if ficha.get("fora"):
        saida["fora"] = ficha["fora"]
    if meta:
        saida["meta"] = meta
    return saida, notas


def validar(entrada: dict[str, Any]) -> list[str]:
    """Passa a entrada pelo mesmo leitor das salas: o que ele recusar, a sala recusaria."""
    problemas: list[str] = []
    _monstros_de_dict(dict(entrada), entrada["nome_en"], problemas)
    return problemas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("arquivo", type=Path, help="a tabela de fichas (JSON)")
    parser.add_argument("--saida", type=Path, default=DESTINO)
    parser.add_argument("--relatorio", action="store_true", help="lista o que foi preenchido")
    args = parser.parse_args()

    fichas = json.loads(args.arquivo.read_text(encoding="utf-8"))["monstros"]
    irmas = _saves_irmas(fichas)
    criaturas: list[dict[str, Any]] = []
    recusadas: list[tuple[str, list[str]]] = []
    preenchidas: list[tuple[str, list[str]]] = []
    for ficha in fichas:
        convertida, notas = converter(ficha, irmas)
        problemas = validar(convertida)
        if problemas:
            recusadas.append((ficha["nome"], problemas))
            continue
        criaturas.append(convertida)
        if notas:
            preenchidas.append((ficha["nome"], notas))

    criaturas.sort(key=lambda c: c["nome"])
    # A sala chama a criatura pelo nome, então dois nomes iguais tornam a busca
    # ambígua: quem for indexado por último ganha, em silêncio.
    repetidos = collections.Counter(c["nome"] for c in criaturas)
    for nome, vezes in sorted(repetidos.items()):
        if vezes > 1:
            quais = ", ".join(c["nome_en"] for c in criaturas if c["nome"] == nome)
            print(
                f"AMBÍGUO: '{nome}' é o nome de {vezes} criaturas ({quais}).",
                file=sys.stderr,
            )
    if args.relatorio and preenchidas:
        print(f"preenchido em {len(preenchidas)} criaturas:")
        for nome, notas in preenchidas:
            for texto in notas:
                print(f"  {nome}: {texto}")
        print()
    if recusadas:
        print(f"RECUSADAS {len(recusadas)}:", file=sys.stderr)
        for nome, problemas in recusadas:
            for texto in problemas:
                print(f"  {nome}: {texto}", file=sys.stderr)
        print(file=sys.stderr)

    args.saida.write_text(
        json.dumps({"criaturas": criaturas}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    print(f"{len(criaturas)} criaturas em {args.saida}")
    return 1 if recusadas else 0


if __name__ == "__main__":
    raise SystemExit(main())
