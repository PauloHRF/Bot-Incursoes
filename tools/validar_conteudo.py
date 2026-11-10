"""Confere arquivos de incursão e de banco de salas ANTES de entrarem no bot.

    python tools/validar_conteudo.py                        # tudo que está em data/
    python tools/validar_conteudo.py minha_dungeon.json     # um arquivo só

Existe para quem escreve conteúdo poder conferir sozinho. É o MESMO validador
que o bot usa (`incursoes.de_dict` e `incursoes.banco_de_dict`), então passar
aqui é passar no bot — não há segunda régua.

E há uma razão forte para ele existir: o bot carrega as incursões com
`carregar_todas`, que **estoura no primeiro arquivo inválido**. No boot o
`_carregar_tolerante` segura a exceção para o bot subir, e sobe *sem nenhuma
incursão*. Ou seja: um arquivo quebrado de um colaborador não tira só a
dungeon dele — tira o catálogo inteiro do ar. Rodar isto antes de copiar o
arquivo para `data/` é o que impede esse acidente.

Sai com 0 quando está tudo bem e 1 quando há qualquer problema, para dar em
gancho de git ou em CI.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src.incursoes import (  # noqa: E402
    ErroDeValidacao,
    arquivo_da_organizacao,
    banco_de_dict,
    de_dict,
)

PASTA_INCURSOES = RAIZ / "data" / "incursoes"
PASTA_BANCOS = RAIZ / "data" / "bancos"


def _tipo_do_arquivo(dados: dict) -> str:
    """Incursão ou banco, pelo que o arquivo tem dentro.

    Olha o CONTEÚDO e não a pasta, porque quem escreve conteúdo valida o
    arquivo onde ele está — na área de trabalho, antes de mandar.
    """
    if "salas" in dados:
        return "banco"
    return "incursao"


def conferir(caminho: Path) -> list[str]:
    """Os problemas daquele arquivo. Lista vazia quer dizer que passou."""
    try:
        bruto = json.loads(caminho.read_text(encoding="utf-8"))
    except json.JSONDecodeError as erro:
        # O erro de JSON vem antes de qualquer regra, e e o mais comum de
        # todos: virgula sobrando, aspas faltando.
        return [f"JSON inválido na linha {erro.lineno}, coluna {erro.colno}: {erro.msg}"]
    except OSError as erro:
        return [f"não deu para ler o arquivo: {erro}"]
    if not isinstance(bruto, dict):
        return ["o arquivo precisa ser um objeto JSON (começa com '{')."]

    converter = banco_de_dict if _tipo_do_arquivo(bruto) == "banco" else de_dict
    try:
        converter(bruto)
    except ErroDeValidacao as erro:
        return list(erro.args[0]) if erro.args else [str(erro)]
    return []


def avisos(caminho: Path, bruto: dict) -> list[str]:
    """O que não impede de carregar, mas o autor quer saber.

    Separado dos problemas de propósito: isto passa no bot, e ainda assim não
    faz o que o autor espera.
    """
    saida: list[str] = []
    if _tipo_do_arquivo(bruto) == "banco":
        descansos = [
            s.get("id") for s in bruto.get("salas") or []
            if str(s.get("tipo") or "").strip().lower().startswith("descans")
        ]
        if descansos:
            saida.append(
                "sala(s) de Descanso no banco "
                f"({', '.join(str(d) for d in descansos)}): elas NÃO são "
                "sorteadas. O descanso virou parada fixa do caminho — a Média "
                "tem um, a Longa tem dois — e sala de Descanso escrita à mão "
                "fica no arquivo sem nunca aparecer no jogo."
            )
        return saida

    organizacao = str(bruto.get("organizacao") or "").strip()
    if organizacao:
        try:
            esperado = PASTA_BANCOS / f"{arquivo_da_organizacao(organizacao)}.json"
        except Exception:
            return saida
        if not esperado.exists():
            saida.append(
                f"a incursão é de '{organizacao}', e não há banco de salas dessa "
                f"Organização em {esperado.relative_to(RAIZ)}. Sem o banco, o "
                f"caminho não tem de onde sortear sala e a run não começa."
            )
    return saida


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "caminhos", nargs="*", type=Path,
        help="arquivos ou pastas; sem nada, confere data/incursoes e data/bancos",
    )
    args = parser.parse_args()

    alvos: list[Path] = []
    for caminho in args.caminhos or [PASTA_INCURSOES, PASTA_BANCOS]:
        if caminho.is_dir():
            alvos.extend(sorted(caminho.glob("*.json")))
        else:
            alvos.append(caminho)
    if not alvos:
        print("nada para conferir.")
        return 0

    com_problema = 0
    for caminho in alvos:
        problemas = conferir(caminho)
        try:
            bruto = json.loads(caminho.read_text(encoding="utf-8"))
        except Exception:
            bruto = {}
        recados = avisos(caminho, bruto) if isinstance(bruto, dict) else []
        nome = caminho.name
        if problemas:
            com_problema += 1
            print(f"[x] {nome}")
            for problema in problemas:
                print(f"      {problema}")
        elif recados:
            print(f"[!] {nome}")
        else:
            print(f"[ok] {nome}")
        for recado in recados:
            print(f"      aviso: {recado}")

    print()
    if com_problema:
        print(
            f"{com_problema} de {len(alvos)} arquivo(s) com problema. Nenhum "
            f"deles pode entrar em data/: um arquivo invalido faz o bot subir "
            f"SEM NENHUMA incursao, e nao so sem a dele."
        )
        return 1
    print(f"{len(alvos)} arquivo(s) conferido(s), nenhum problema.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
