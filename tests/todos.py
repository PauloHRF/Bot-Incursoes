"""Roda todos os testes do projeto.

    .venv/Scripts/python.exe tests/todos.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SUITES = ("smoke.py", "test_run.py", "test_votacao.py", "test_combate.py", "test_pontos.py", "test_personagens.py", "test_critico_expertise.py", "test_ajuda_feedback.py", "test_geracao.py", "test_faixa.py", "test_tier.py", "test_semana.py", "test_registro.py", "test_bando.py")


def main() -> int:
    falhas = []
    for suite in SUITES:
        print(f"\n=== {suite} ===")
        try:
            processo = subprocess.run(
                [sys.executable, str(AQUI / suite)],
                env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
                timeout=180,
            )
        except subprocess.TimeoutExpired:
            print(f"{suite}: estourou o tempo limite", flush=True)
            falhas.append(suite)
            continue
        if processo.returncode != 0:
            falhas.append(suite)

    print()
    if falhas:
        print(f"FALHARAM: {', '.join(falhas)}")
        return 1
    print(f"tudo verde ({len(SUITES)} suítes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
