"""Converte a planilha de uma incursão no JSON que o bot lê.

    python tools/importar_planilha.py data/planilhas/incursao_exemplo.xlsx
    python tools/importar_planilha.py minha_incursao.xlsx --saida data/incursoes

Valida tudo antes de gravar: se houver qualquer problema, nada é escrito e os
problemas saem listados. Funciona com planilhas do Excel e do Google Sheets
(baixe como .xlsx em Arquivo > Fazer download > Microsoft Excel).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.incursoes import ErroDeValidacao, de_dict  # noqa: E402
from src.rules import chave_comparacao  # noqa: E402

ABA_META = "Incursao"
ABA_SALAS = "Salas"
ABA_DIFICULDADES = "Dificuldades"

CAMPOS_META = ("id", "nome", "organizacao", "descricao", "imagem_capa", "recompensa_mes")


class ErroDePlanilha(Exception):
    pass


def _texto(valor: Any) -> str:
    return "" if valor is None else str(valor).strip()


def _aba(wb, nome: str):
    for candidata in wb.sheetnames:
        if chave_comparacao(candidata) == chave_comparacao(nome):
            return wb[candidata]
    raise ErroDePlanilha(
        f"A planilha nao tem a aba '{nome}'. Abas encontradas: {', '.join(wb.sheetnames)}."
    )


def ler_dificuldades(wb) -> dict[str, tuple[int | None, int | None]]:
    """dificuldade (normalizada) -> (cd, alvo_progresso)."""
    ws = _aba(wb, ABA_DIFICULDADES)
    tabela = {}
    for nome, cd, alvo in ws.iter_rows(min_row=2, max_col=3, values_only=True):
        if not _texto(nome):
            continue
        tabela[chave_comparacao(_texto(nome))] = (
            int(cd) if cd is not None else None,
            int(alvo) if alvo is not None else None,
        )
    if not tabela:
        raise ErroDePlanilha("A aba 'Dificuldades' esta vazia.")
    return tabela


def ler_meta(wb) -> dict[str, Any]:
    ws = _aba(wb, ABA_META)
    meta: dict[str, Any] = {}
    for campo, valor in ws.iter_rows(min_row=2, max_col=2, values_only=True):
        chave = chave_comparacao(_texto(campo))
        if not chave:
            continue
        for esperado in CAMPOS_META:
            if chave == chave_comparacao(esperado):
                meta[esperado] = valor
    faltando = [c for c in ("id", "nome", "organizacao") if not _texto(meta.get(c))]
    if faltando:
        raise ErroDePlanilha(
            f"A aba '{ABA_META}' nao tem: {', '.join(faltando)}. "
            "A coluna A traz o nome do campo e a coluna B o valor."
        )
    return meta


def ler_salas(wb, dificuldades) -> tuple[list[list[dict]], dict | None]:
    ws = _aba(wb, ABA_SALAS)
    cabecalho = [chave_comparacao(_texto(c.value)) for c in ws[1]]
    try:
        col = {nome: cabecalho.index(chave_comparacao(nome)) for nome in (
            "sala_id", "linha", "nome", "tipo", "dificuldade", "cd", "alvo_progresso",
            "pericias", "descricao", "imagem", "monstro_nome", "monstro_ca",
            "monstro_ataque", "monstro_dano", "monstro_hp", "recompensa",
        )}
    except ValueError as exc:
        raise ErroDePlanilha(
            f"A aba '{ABA_SALAS}' esta sem uma coluna obrigatoria ({exc}). "
            "Regenere o modelo com tools/gerar_modelo_planilha.py e compare os cabecalhos."
        ) from exc

    linhas: dict[int, list[dict]] = {1: [], 2: [], 3: []}
    objetivo = None

    for numero, celulas in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        def valor(nome):
            indice = col[nome]
            return celulas[indice] if indice < len(celulas) else None

        sala_id = _texto(valor("sala_id"))
        if not sala_id:
            continue  # linha em branco no fim da planilha

        dif_bruta = _texto(valor("dificuldade"))
        cd, alvo = valor("cd"), valor("alvo_progresso")
        # A planilha calcula cd/alvo por formula; sem cache (ou recem-gerada),
        # resolvemos pela aba Dificuldades.
        if dif_bruta and (cd is None or isinstance(cd, str)):
            cd = dificuldades.get(chave_comparacao(dif_bruta), (None, None))[0]
        if dif_bruta and (alvo is None or isinstance(alvo, str)):
            alvo = dificuldades.get(chave_comparacao(dif_bruta), (None, None))[1]
        if dif_bruta and chave_comparacao(dif_bruta) not in dificuldades:
            raise ErroDePlanilha(
                f"Linha {numero} da aba '{ABA_SALAS}': dificuldade '{dif_bruta}' nao esta na aba "
                f"'{ABA_DIFICULDADES}'."
            )

        pericias = [p.strip() for p in _texto(valor("pericias")).replace(",", ";").split(";") if p.strip()]

        sala: dict[str, Any] = {
            "id": sala_id,
            "nome": _texto(valor("nome")),
            "tipo": _texto(valor("tipo")),
            "descricao": _texto(valor("descricao")),
            "dificuldade": dif_bruta or None,
            "cd": cd,
            "alvo_progresso": alvo,
            "pericias": pericias,
            "imagem": _texto(valor("imagem")) or None,
            "recompensa": _texto(valor("recompensa")) or None,
        }
        if _texto(valor("monstro_nome")):
            sala["monstro"] = {
                "nome": _texto(valor("monstro_nome")),
                "ca": valor("monstro_ca"),
                "ataque": valor("monstro_ataque"),
                "dano": _texto(valor("monstro_dano")),
                "hp": valor("monstro_hp"),
            }

        bruto_linha = _texto(valor("linha"))
        if chave_comparacao(bruto_linha) in ("objetivo", "obj", "4"):
            if objetivo is not None:
                raise ErroDePlanilha(
                    f"Linha {numero}: ja existe uma sala de Objetivo ('{objetivo['id']}'). So pode haver uma."
                )
            objetivo = sala
            continue

        try:
            indice = int(float(bruto_linha))
        except ValueError as exc:
            raise ErroDePlanilha(
                f"Linha {numero} da aba '{ABA_SALAS}': coluna 'linha' com '{bruto_linha}'. "
                "Use 1, 2, 3 ou Objetivo."
            ) from exc
        if indice not in linhas:
            raise ErroDePlanilha(
                f"Linha {numero} da aba '{ABA_SALAS}': linha {indice} nao existe. Use 1, 2, 3 ou Objetivo."
            )
        linhas[indice].append(sala)

    return [linhas[1], linhas[2], linhas[3]], objetivo


def importar(planilha: Path, saida: Path) -> Path:
    if not planilha.exists():
        raise ErroDePlanilha(f"Planilha nao encontrada: {planilha}")

    wb = load_workbook(planilha, data_only=True)
    dificuldades = ler_dificuldades(wb)
    meta = ler_meta(wb)
    linhas, objetivo = ler_salas(wb, dificuldades)

    dados = {
        "id": _texto(meta.get("id")),
        "nome": _texto(meta.get("nome")),
        "organizacao": _texto(meta.get("organizacao")),
        "descricao": _texto(meta.get("descricao")),
        "imagem_capa": _texto(meta.get("imagem_capa")) or None,
        "recompensa_mes": meta.get("recompensa_mes"),
        "linhas": linhas,
        "objetivo": objetivo,
    }

    incursao = de_dict(dados)  # levanta ErroDeValidacao com a lista de problemas

    saida.mkdir(parents=True, exist_ok=True)
    destino = saida / f"{incursao.id}.json"
    destino.write_text(
        json.dumps(incursao.para_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return destino


def main() -> int:
    parser = argparse.ArgumentParser(description="Converte a planilha de incursao em JSON.")
    parser.add_argument("planilha", type=Path, help="Arquivo .xlsx da incursao")
    parser.add_argument(
        "--saida", type=Path, default=Path("data/incursoes"), help="Pasta de destino do JSON"
    )
    args = parser.parse_args()

    try:
        destino = importar(args.planilha, args.saida)
    except ErroDePlanilha as exc:
        print(f"Nao consegui ler a planilha:\n  - {exc}", file=sys.stderr)
        return 1
    except ErroDeValidacao as exc:
        print(f"A planilha tem {len(exc.problemas)} problema(s); nada foi gravado:", file=sys.stderr)
        print(exc, file=sys.stderr)
        return 1

    print(f"JSON gravado em: {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
