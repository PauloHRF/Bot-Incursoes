"""O cog das incursões: recrutamento, votação, salas, descanso e o combate no canal.

As regras do combate moram em `src/combate`; aqui fica o Discord — os
comandos, os botões e as mensagens. É uma pasta, e não um arquivo, para cada
assunto ter o seu:

- `cog.py` — a classe que o bot carrega, e os comandos de `/incursao`;
- `recrutamento.py` — quem entra no grupo, e o começo da run;
- `votacao.py` — as salas de cada passo, e o voto do grupo;
- `salas.py` — entrar na sala, o teste de perícia, o que ela dá ou cobra;
- `descanso.py` — as paradas de descanso, a troca e a limpeza;
- `tela_do_combate.py` — o painel, os menus, as poções e o fim da luta;
- `substituicao.py` — o grupo agindo pelo ausente;
- `canal.py` — falar no canal, chamar quem joga, limpar o que passou;
- `views.py` — os botões e menus.

Este `__init__` é a porta de entrada: é ele que o bot carrega
(`src.cogs.incursao`, com o `setup`), e é dele que os testes importam o cog,
as views e o `maioria_de` — pelos mesmos nomes de quando o cog era um
arquivo só.
"""
from .cog import Incursoes, setup
from .views import (
    BotaoVoto,
    SeletorAlvoHabilidade,
    SeletorHabilidade,
    SeletorPersonagemEntrada,
    SeletorPocao,
    SeletorRecarga,
    ViewCombate,
    ViewDescanso,
    ViewMarcaOrfa,
    ViewRecrutamento,
    ViewSala,
    ViewTrocaDoDescanso,
    ViewVotacao,
)
from .votacao import maioria_de

__all__ = [
    "BotaoVoto",
    "Incursoes",
    "SeletorAlvoHabilidade",
    "SeletorHabilidade",
    "SeletorPersonagemEntrada",
    "SeletorPocao",
    "SeletorRecarga",
    "ViewCombate",
    "ViewDescanso",
    "ViewMarcaOrfa",
    "ViewRecrutamento",
    "ViewSala",
    "ViewTrocaDoDescanso",
    "ViewVotacao",
    "maioria_de",
    "setup",
]
