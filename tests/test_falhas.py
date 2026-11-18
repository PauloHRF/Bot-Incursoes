"""Quando o bot quebra no meio de um clique, o jogador fica sabendo.

Sem tratador, a exceção ia só para o log, e o jogador ficava com "o
aplicativo não respondeu" — ou, nos cliques que adiam a resposta, com o
"pensando..." pendurado para sempre. Quanto mais respostas adiadas o bot tem,
mais isso pesa: é o par do prazo de 3 segundos.
"""
from __future__ import annotations

import asyncio
import importlib
import inspect
import logging
import pkgutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import discord  # noqa: E402
from discord import app_commands  # noqa: E402

from src import falhas  # noqa: E402
import src.cogs  # noqa: E402
from src.cogs import incursao  # noqa: E402
from fakes import CANAL, JOGADORES, FakeCanal, FakeInteraction  # noqa: E402


class _Anotador(logging.Handler):
    def __init__(self):
        super().__init__()
        self.registros: list[logging.LogRecord] = []

    def emit(self, record):
        self.registros.append(record)


def caso_toda_view_do_bot_fecha_a_interacao():
    """Toda view dos cogs herda de `ViewDoBot`, e nenhuma da View crua.

    A regra só vale se valer para TODAS: o botão que ficar de fora é o que
    vai quebrar em silêncio. Por isso a conta é por varredura, e não por
    lista — a view que alguém criar amanhã entra nela sozinha.

    A varredura desce nas pastas: o cog das incursões virou uma pasta, com as
    views em `incursao/views.py`, e uma lista de módulos escrita à mão as
    deixou de fora na primeira vez.
    """
    soltas = []
    vistas = 0
    modulos = [
        importlib.import_module(info.name)
        for info in pkgutil.walk_packages(src.cogs.__path__, "src.cogs.")
    ]
    for modulo in modulos:
        for nome, cls in inspect.getmembers(modulo, inspect.isclass):
            if cls.__module__ != modulo.__name__:
                continue
            if not issubclass(cls, discord.ui.View):
                continue
            vistas += 1
            if not issubclass(cls, falhas.ViewDoBot):
                soltas.append(f"{modulo.__name__}.{nome}")
    assert vistas >= 15, f"a varredura achou views de menos: {vistas}"
    assert not soltas, f"views que quebram em silencio: {soltas}"
    print(f"  as {vistas} views do bot fecham a interacao quando quebram: ok")


async def caso_o_aviso_sai_pela_porta_que_sobrou():
    """Sem resposta, adiada com "pensando..." e adiada editando o cartão.

    O terceiro é o que pede cuidado: o `defer` de botão sem `thinking` diz
    "vou editar a mensagem do botão", e preencher a original ali escreveria o
    erro em cima do cartão do grupo. Ele vai em privado.
    """
    canal = FakeCanal(CANAL)

    # 1. ninguém respondeu ainda: responde, em privado
    crua = FakeInteraction(canal, JOGADORES[0])
    await falhas.avisar(crua, RuntimeError("quebrou"))
    assert crua.resposta == falhas.AVISO, crua.resposta
    assert crua._original_e_efemera, "o aviso saiu publico"

    # 2. "pensando..." privado: o aviso preenche ele
    privada = FakeInteraction(canal, JOGADORES[0])
    await privada.response.defer(ephemeral=True, thinking=True)
    await falhas.avisar(privada, RuntimeError("quebrou"))
    assert privada.resposta_atual == falhas.AVISO, privada.resposta_atual

    # 3. "pensando..." publico (o `/incursao status`): preenche tambem
    publica = FakeInteraction(canal, JOGADORES[0])
    await publica.response.defer(thinking=True)
    await falhas.avisar(publica, RuntimeError("quebrou"))
    assert (await publica.original_response()).content == falhas.AVISO

    # 4. o botao que adia para editar o cartao: o cartao fica intacto
    cartao = await canal.send("o cartao do grupo")
    botao = FakeInteraction(canal, JOGADORES[0], cartao)
    await botao.response.defer()
    await falhas.avisar(botao, RuntimeError("quebrou"))
    assert botao.seguimento == falhas.AVISO, botao.seguimento
    assert cartao.content == "o cartao do grupo", "o erro foi escrito no cartao"
    print("  o aviso sai pela porta que sobrou, e nunca em cima do cartao: ok")


async def caso_a_falha_vai_inteira_para_o_log():
    """O aviso não substitui o log: o traceback continua indo para o journal.

    O erro de comando chega embrulhado (`CommandInvokeError`), e o que
    interessa é o de dentro: é ele que diz a linha que quebrou.
    """
    anotador = _Anotador()
    logging.getLogger("incursoes.falha").addHandler(anotador)
    try:
        try:
            raise KeyError("a linha que quebrou")
        except KeyError as dentro:
            embrulho = app_commands.AppCommandError("embrulho")
            embrulho.original = dentro
        await falhas.avisar(FakeInteraction(FakeCanal(CANAL), JOGADORES[0]), embrulho)
    finally:
        logging.getLogger("incursoes.falha").removeHandler(anotador)
    assert len(anotador.registros) == 1, anotador.registros
    registro = anotador.registros[0]
    assert registro.exc_info and registro.exc_info[0] is KeyError, registro.exc_info
    assert registro.exc_info[2] is not None, "o traceback nao foi junto"
    print("  a falha vai inteira para o log, com o erro de dentro: ok")


async def caso_botao_e_comando_que_quebram_avisam():
    """As duas portas por onde o discord.py entrega um erro chegam no aviso."""
    canal = FakeCanal(CANAL)
    logging.getLogger("incursoes.falha").disabled = True
    try:
        # O botao: o `on_error` da view.
        view = incursao.ViewRecrutamento(None, 1)
        clique = FakeInteraction(canal, JOGADORES[0])
        await view.on_error(clique, RuntimeError("quebrou"), view.children[0])
        assert clique.resposta == falhas.AVISO, clique.resposta

        # O comando de barra: o tratador da arvore.
        from src.main import IncursoesBot

        bot = IncursoesBot()
        comando = FakeInteraction(canal, JOGADORES[0])
        await bot.tree.on_error(comando, app_commands.AppCommandError("quebrou"))
        assert comando.resposta == falhas.AVISO, comando.resposta
    finally:
        logging.getLogger("incursoes.falha").disabled = False
    print("  botao e comando de barra que quebram avisam o jogador: ok")


async def main():
    caso_toda_view_do_bot_fecha_a_interacao()
    # As falhas abaixo sao de proposito: o log delas so sujaria a saida.
    logging.getLogger("incursoes.falha").disabled = True
    try:
        await caso_o_aviso_sai_pela_porta_que_sobrou()
    finally:
        logging.getLogger("incursoes.falha").disabled = False
    await caso_a_falha_vai_inteira_para_o_log()
    await caso_botao_e_comando_que_quebram_avisam()


asyncio.run(main())
print("TESTES DE FALHAS PASSARAM")
