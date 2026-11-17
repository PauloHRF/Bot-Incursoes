"""Roda todos os testes do projeto.

    .venv/Scripts/python.exe tests/todos.py
    .venv/Scripts/python.exe tests/todos.py --sem-pular   # pulada conta como falha

**As suítes são achadas, e não listadas.** Toda `tests/test_*.py` entra, mais
o `smoke.py` na frente. A lista era escrita à mão, e uma suíte inteira ficou
fora dela: `test_estudio_interface.py`, com 20 provas, nunca rodou por aqui —
o próprio código de "pulada" abaixo foi criado para ela, no mesmo commit que
esqueceu de pô-la na lista. Achando pelo nome, a suíte nova entra no dia em
que o arquivo nasce.

`--sem-pular` é para o CI, que instala tudo: lá uma suíte pulada quer dizer
que faltou instalar alguma coisa, e isso tem de ficar vermelho.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
# A de fumaça primeiro: se o bot nem carrega, as outras só repetiriam o erro.
SUITES = ("smoke.py", *sorted(p.name for p in AQUI.glob("test_*.py")))


# Codigo que uma suite devolve para dizer "nao rodei" — hoje so a da
# interface, que precisa do playwright. Nao e falha, e nao pode ser silencio:
# contar como verde foi o que escondeu 12 provas paradas.
PULADA = 3


def main(argv: list[str]) -> int:
    sem_pular = "--sem-pular" in argv
    falhas, puladas = [], []
    for suite in SUITES:
        # `flush`: com a saida num arquivo ou num cano (o CI), o cabecalho
        # ficava preso no buffer e saia depois da saida da propria suite.
        print(f"\n=== {suite} ===", flush=True)
        try:
            processo = subprocess.run(
                [sys.executable, str(AQUI / suite)],
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                timeout=180,
            )
        except subprocess.TimeoutExpired:
            print(f"{suite}: estourou o tempo limite", flush=True)
            falhas.append(suite)
            continue
        if processo.returncode == PULADA:
            puladas.append(suite)
        elif processo.returncode != 0:
            falhas.append(suite)

    print()
    if puladas:
        print(f"PULADAS, nao rodaram: {', '.join(puladas)}")
        if sem_pular:
            falhas.extend(puladas)
    if falhas:
        print(f"FALHARAM: {', '.join(falhas)}")
        return 1
    rodaram = len(SUITES) - len(puladas)
    print(f"tudo verde ({rodaram} de {len(SUITES)} suítes"
          + (f"; {len(puladas)} pulada(s))" if puladas else ")"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
