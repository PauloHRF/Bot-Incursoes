"""Uma medição de bando, com a semente pareada e a procedência junto.

Quatro comandos repetiam as mesmas seis linhas — monta as criaturas pelo
nome, monta o `SimpleNamespace` de argumentos, chama `simular_combate` com um
`random.Random` montado na mão — e cada um montava a semente do jeito dele.
Dois montavam errado:

- o `sugestor.py` punha o bando na semente, então cada ponto da bisseção
  enfrentava mesas diferentes;
- o `--varrer` do `calibrar_emboscada.py` punha a QUANTIDADE na semente, no
  mesmo arquivo que tem a regra escrita no corpo ("a semente NÃO leva o
  elenco").

A regra não cabe num comentário: cabe numa função. Aqui a semente é montada
em um lugar só, e **o bando nunca entra nela** — o que separa duas medições é
o tier e o tamanho do grupo, que são perguntas diferentes, e não o candidato,
que é a coisa sendo comparada.

PROCEDÊNCIA. A resposta traz o hash do código que mediu. O
`calibrar_emboscada.py` diz, no próprio cabeçalho, que "sem um comando para
refazê-los, 'foi medido' vira uma afirmação sem data" — e a única ferramenta
que gravava a identidade do código era a comparação de classes. Agora todo
número medido pode dizer de qual código ele saiu.
"""
from __future__ import annotations

import hashlib
import random
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable, Optional, Sequence

from src.incursoes import monstros_de_criatura

from . import grupos

RAIZ = Path(__file__).resolve().parents[2]

# Quantas mesas sortear quando ninguém pede outra coisa. Doze é o da bancada,
# que quer ordem de grandeza; quem vai ESCREVER número pede quarenta. Ver
# `grupos.dividir`: mais repetições compram lutas por mesa, nunca mesas.
MESAS_PADRAO = grupos.COMPOSICOES_PADRAO


def bando_de(elenco: Iterable[tuple[str, int]], onde: str = "medicao") -> list:
    """`[("Mímico", 2), ("Xorn", 3)]` vira a lista de criaturas do bestiário.

    Levanta se algum nome não virar ficha, em vez de medir um bando menor do
    que o pedido e devolver um número que não é do que se perguntou.
    """
    elenco = list(elenco)
    monstros = [
        m
        for nome, quantas in elenco
        for m in monstros_de_criatura({"nome": nome, "quantidade": quantas}, onde)
    ]
    esperado = sum(max(0, q) for _n, q in elenco)
    if len(monstros) != esperado:
        achados = {m.nome for m in monstros}
        faltam = [n for n, _q in elenco if not any(n.split()[0] in a for a in achados)]
        raise ValueError(
            f"criatura fora do bestiário: {', '.join(faltam) or elenco}"
        )
    return monstros


def semente_de(semente: Any, tier: Optional[int], tamanho: int) -> random.Random:
    """O sorteio das mesas daquela medição.

    **O bando não entra.** É o que faz a diferença entre dois números ser a
    diferença entre dois bandos, e não entre dois sorteios. O tier e o tamanho
    entram porque são perguntas diferentes: medir mesa de cinco e de três não
    são duas amostras da mesma coisa.
    """
    return random.Random(f"{semente}:{tier}:{tamanho}")


def hash_do_modelo() -> str:
    """O sha256 do código que mediu: `src/` mais este pacote.

    É a data da medição em forma de identidade. Um número no documento que
    não diz de qual código saiu é uma afirmação sem prazo de validade.
    """
    arquivos = sorted((RAIZ / "src").rglob("*.py")) + sorted(
        Path(__file__).parent.glob("*.py")
    )
    modelo = hashlib.sha256()
    for arquivo in arquivos:
        modelo.update(str(arquivo.relative_to(RAIZ)).encode())
        modelo.update(arquivo.read_bytes())
    return modelo.hexdigest()


def medir(
    monstros: Sequence[Any],
    *,
    tamanho: int,
    repeticoes: int,
    semente: Any,
    tier: Optional[int] = None,
    nivel: Optional[int] = None,
    classe: Optional[str] = None,
    mesas: int = MESAS_PADRAO,
    minimo: Optional[int] = None,
    detalhes: bool = True,
) -> dict[str, Any]:
    """Aquele bando contra um grupo daquele tamanho, pelo caminho do bot.

    `nivel` sem valor vira o primeiro nível do tier, que é a mesa que a sala
    daquele tier encontra. `classe` só para diagnóstico ("dura para quem?");
    sem ela, as mesas são sorteadas, que é o padrão.

    `minimo` é o piso de lutas por mesa. Quem publica só a média pode baixá-lo
    e comprar mesas com as mesmas lutas (`grupos.MINIMO_PARA_A_MEDIA`).
    """
    if tamanho < 1 or repeticoes < 1:
        raise ValueError("Tamanho de grupo e repetições precisam ser positivos.")
    # O import é tardio de propósito: `simular_combate` é um comando de linha
    # na pasta `tools/`, e importá-lo no topo amarraria este pacote ao
    # `sys.path` de quem o carrega.
    if str(RAIZ / "tools") not in sys.path:
        sys.path.insert(0, str(RAIZ / "tools"))
    import simular_combate as sc

    args = SimpleNamespace(
        classe=classe or None,
        nivel=nivel if nivel is not None else min(10, (tier or 1) * 2),
        tier=tier,
        repeticoes=repeticoes,
        composicoes=mesas,
        minimo_por_mesa=minimo or grupos.MINIMO_POR_COMPOSICAO,
        coletar_detalhes=detalhes,
    )
    return sc.simular(monstros, tamanho, args, semente_de(semente, tier, tamanho))
