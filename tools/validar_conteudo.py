"""Confere arquivos de incursão e de banco de salas ANTES de entrarem no bot.

    python tools/validar_conteudo.py                        # tudo que está em data/
    python tools/validar_conteudo.py minha_dungeon.json     # um arquivo só

Existe para quem escreve conteúdo poder conferir sozinho. É o MESMO validador
que o bot usa (`incursoes.de_dict` e `incursoes.banco_de_dict`), então passar
aqui é passar no bot — não há segunda régua.

O bot hoje carrega arquivo por arquivo (`carregar_todas_tolerante`): o inválido
fica de fora sozinho e o resto do catálogo sobe. Ele já foi pior — um JSON
quebrado abortava o carregamento inteiro e o bot subia *sem nenhuma incursão*,
então a vírgula errada de um colaborador tirava todas as dungeons do ar.

Isso não dispensa validar antes: o arquivo que fica de fora **fica de fora**.
A dungeon simplesmente não existe para quem for jogar, e o aviso mora no log
do servidor e na resposta do `/incursao recarregar` — ou seja, longe de quem
escreveu. Rodar isto antes de mandar o arquivo é o que evita descobrir isso
pelo lado errado.

Sai com 0 quando está tudo bem e 1 quando há qualquer problema, para dar em
gancho de git ou em CI.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src.incursoes import (  # noqa: E402
    LIMITE_DESCRICAO,
    LIMITE_TITULO,
    ErroDeValidacao,
    arquivo_da_organizacao,
    banco_de_dict,
    de_dict,
)

PASTA_INCURSOES = RAIZ / "data" / "incursoes"
PASTA_BANCOS = RAIZ / "data" / "bancos"

# Onde o texto deixa de caber bem num celular, muito antes de o Discord
# recusar. O teto duro (LIMITE_*) é recusa e mora na validação; estes são
# aviso, porque texto comprido é escolha de quem escreve e não erro.
AVISO_TITULO = 80
AVISO_DESCRICAO_SALA = 600
AVISO_LORE = 1500


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
        # `.problemas` e nao `args[0]`: args[0] e o resumo ("2 problema(s)
        # encontrado(s)"), e list() de uma string devolve letra por letra.
        return list(erro.problemas)
    return []


def avisos(caminho: Path, bruto: dict) -> list[str]:
    """O que não impede de carregar, mas o autor quer saber.

    Separado dos problemas de propósito: isto passa no bot, e ainda assim não
    faz o que o autor espera.
    """
    saida: list[str] = []

    def comprido(texto: Any, aviso: int, teto: int, rotulo: str) -> None:
        tamanho = len(str(texto or ""))
        if aviso < tamanho <= teto:
            saida.append(
                f"{rotulo} tem {tamanho} caracteres. Cabe (o Discord recusa só "
                f"acima de {teto}), mas acima de {aviso} vira parede de texto "
                f"na tela de um celular."
            )

    if _tipo_do_arquivo(bruto) == "banco":
        for sala in bruto.get("salas") or []:
            onde = f"a sala {sala.get('id') or '?'}"
            comprido(sala.get("nome"), AVISO_TITULO, LIMITE_TITULO, f"o nome de {onde}")
            comprido(
                sala.get("descricao"), AVISO_DESCRICAO_SALA, LIMITE_DESCRICAO,
                f"a descrição de {onde}",
            )
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

    comprido(bruto.get("nome"), AVISO_TITULO, LIMITE_TITULO, "o nome da incursão")
    comprido(
        bruto.get("lore_inicial") or bruto.get("descricao"),
        AVISO_LORE, LIMITE_DESCRICAO, "a lore de abertura",
    )
    comprido(bruto.get("lore_final"), AVISO_LORE, LIMITE_DESCRICAO, "a lore de fecho")

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
            f"deles pode entrar em data/: o bot pula o arquivo invalido, entao "
            f"a dungeon simplesmente NAO EXISTE para quem for jogar."
        )
        return 1
    print(f"{len(alvos)} arquivo(s) conferido(s), nenhum problema.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
