"""Onde as medições ficam guardadas, para os documentos citarem em vez de copiar.

Um número medido que chega ao documento por cópia manual é uma afirmação sem
prazo de validade: ele continua lá depois de o código mudar, e ninguém sabe
dizer de quando ele é. Aconteceu neste projeto — o `BALANCO.md` ganhou
`media, p90 = 5, 10` digitados à mão a partir de uma rodada do
`tools/medir_ameaca.py`, dentro de um documento que é gerado justamente para
não ter número copiado.

Então: quem mede **grava**, com a data e o hash do código que mediu; quem
gera documento **lê**, e diz "não medido" quando não há medição, em vez de
inventar um número.

O arquivo é versionado de propósito. Ele é o registro de que a medição
aconteceu, e o diff dele é a pergunta "o que mudou desde a última vez?".
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Optional

from . import medidor

ARQUIVO = Path(__file__).with_name("medidas.json")
RAIZ = Path(__file__).resolve().parents[2]


def ler() -> dict[str, Any]:
    """Tudo que está gravado. Arquivo ausente é dicionário vazio, não erro."""
    if not ARQUIVO.exists():
        return {}
    try:
        return json.loads(ARQUIVO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def de(nome: str) -> Optional[dict[str, Any]]:
    """Uma medição pelo nome, ou None se ela nunca foi feita."""
    valor = ler().get(nome)
    return valor if isinstance(valor, dict) else None


def esta_velha(medida: Optional[dict[str, Any]]) -> bool:
    """A medição é de um código que não é mais este?

    Não é "está errada": é "foi feita noutro código, então ninguém conferiu
    que ela continua valendo". Quem mostra o número decide o que fazer com
    isso — o mínimo é dizer.
    """
    return bool(medida) and medida.get("sha256_modelo") != medidor.hash_do_modelo()


def gravar(nome: str, valores: dict[str, Any]) -> dict[str, Any]:
    """Guarda uma medição com a data e o hash do código que a produziu."""
    registro = {
        **valores,
        "quando": date.today().isoformat(),
        "sha256_modelo": medidor.hash_do_modelo(),
    }
    tudo = ler()
    tudo[nome] = registro
    ARQUIVO.write_text(
        json.dumps(tudo, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return registro
