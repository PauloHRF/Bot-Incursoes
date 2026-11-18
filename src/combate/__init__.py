"""As regras do combate, fora do cog do Discord.

`Combate` é o combate inteiro: a mesa (onde a run está, quem joga, a fila),
os botões de ação, o fluxo (o estado, a vez de cada um, a criatura, a virada
da rodada) e os resolvedores das habilidades. Ele não fala com o Discord.
Tudo o que precisa dizer, ele diz por uma PORTA — um método que quem o herda
implementa: o cog com mensagens, a bancada da simulação calado.

As portas são a união do `DA_MESA` de cada módulo, e estão em `PORTAS`.
`tests/test_fronteira_do_combate.py` cobra que a lista seja exata, que o cog
implemente todas, e que a bancada também.
"""
from __future__ import annotations

from .acoes import DA_MESA as _DA_ACOES, Acoes
from .fluxo import DA_MESA as _DA_FLUXO, Fluxo
from .mesa import DA_MESA as _DA_MESA, Mesa
from .resolvedores import DA_MESA as _DA_RESOLVEDORES, Resolvedores

# O que o combate pede de quem o herda, com o porquê de cada uma.
PORTAS = {**_DA_MESA, **_DA_RESOLVEDORES, **_DA_FLUXO, **_DA_ACOES}


class Combate(Acoes, Fluxo, Resolvedores, Mesa):
    """O combate sem o Discord. O `__init__` é o da mesa: `Combate(bot)`."""
