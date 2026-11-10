"""Acrescenta `meta.ambientes` às criaturas de data/bestiario.json.

    python tools/importar_ambientes.py bestiary-mm.json
    python tools/importar_ambientes.py bestiary-mm.json --saida /tmp/novo.json

O ambiente é o `environment` do 5etools, e serve ao sugeridor de combate do
estúdio: "um bando difícil de underdark". Ele NÃO existia no bestiário do bot
porque `importar_bestiario.py` não copiava o campo.

Por que isto é um importador separado, e não uma linha a mais naquele: o
`meta` de cada criatura (tipo, função, tier, xp) não vem do 5etools — vem de
`importar_fichas.py`, que rodou depois. Re-importar o bestiário do livro
apagaria o `meta` inteiro. Este aqui só ACRESCENTA um campo às entradas que já
existem, casando por `nome_en`, e não mexe em mais nada.

Criatura que o livro deixa sem ambiente nenhum fica com a lista vazia, e isso
é informação e não falta: o Monster Manual não dá bioma a quem não é nativo de
bioma nenhum — demônio, golem, celestial. Elas formam o balde "de lugar
nenhum", que o sugeridor oferece em qualquer ambiente.

Roda quantas vezes quiser: reescrever com a mesma origem dá o mesmo arquivo.
"""
from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "data" / "bestiario.json"


def _chave(texto: object) -> str:
    """Nome comparável: sem acento, sem espaço nas pontas, minúsculo."""
    bruto = unicodedata.normalize("NFKD", str(texto or ""))
    sem_acento = "".join(c for c in bruto if not unicodedata.combining(c))
    return sem_acento.strip().lower()


def ambientes_da_origem(caminho: Path) -> dict[str, list[str]]:
    """nome em inglês -> ambientes, lido do bestiário do 5etools."""
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    monstros = bruto.get("monster") or []
    if not monstros:
        raise SystemExit(
            f"{caminho.name} não tem a lista 'monster': não parece um bestiário do 5etools."
        )
    return {
        _chave(m.get("name")): sorted({str(a) for a in (m.get("environment") or [])})
        for m in monstros
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("arquivo", type=Path, help="bestiário do 5etools (JSON)")
    parser.add_argument("--saida", type=Path, default=DESTINO)
    parser.add_argument(
        "--bestiario", type=Path, default=DESTINO,
        help="o bestiário do bot a enriquecer (padrão: data/bestiario.json)",
    )
    args = parser.parse_args()

    por_nome = ambientes_da_origem(args.arquivo)
    nosso = json.loads(args.bestiario.read_text(encoding="utf-8"))
    criaturas = nosso.get("criaturas") or []

    nao_achadas: list[str] = []
    com = sem = 0
    vocabulario: Counter = Counter()
    for criatura in criaturas:
        ambientes = por_nome.get(_chave(criatura.get("nome_en")))
        if ambientes is None:
            nao_achadas.append(str(criatura.get("nome_en")))
            continue
        # `meta` existe em toda entrada que passou por importar_fichas; a
        # criatura sem ele ganha um, para o campo ter onde morar.
        meta = criatura.setdefault("meta", {})
        meta["ambientes"] = ambientes
        if ambientes:
            com += 1
            vocabulario.update(ambientes)
        else:
            sem += 1

    args.saida.write_text(
        json.dumps({"criaturas": criaturas}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )

    print(f"{len(criaturas)} criatura(s) no bestiário do bot.")
    print(f"  casadas na origem: {len(criaturas) - len(nao_achadas)}")
    print(f"  com ao menos um ambiente: {com}")
    print(f"  de lugar nenhum (lista vazia): {sem}")
    if nao_achadas:
        print(
            f"  SEM PAR na origem ({len(nao_achadas)}), ficaram sem o campo: "
            + ", ".join(nao_achadas[:12])
        )
    print(f"\n{len(vocabulario)} ambiente(s) no vocabulário:")
    for ambiente, quantas in vocabulario.most_common():
        print(f"  {quantas:4d}  {ambiente}")
    print(f"\nescrito em {args.saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
