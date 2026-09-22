"""Pontos de Organização: crédito durante a run, placar e extrato.

O placar é do servidor, não de cada jogador.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import config, database as db  # noqa: E402
from src.cogs.incursao import Incursoes  # noqa: E402
from src.cogs.organizacao import Organizacao  # noqa: E402
from src.incursoes import ORGANIZACOES  # noqa: E402
from fakes import (  # noqa: E402
    CLASSE_PADRAO,
    CANAL,
    GUILD,
    IMBATIVEL,
    INDEFESO,
    JOGADORES,
    TREINADAS,
    FakeBot,
    FakeCanal,
    FakeInteraction,
    atacar_ate_cair,
    criar_grupo,
    montar_conteudo,
    salas_sem_combate,
)

_ABERTAS = []


async def preparar(nivel=8):
    # No Windows o arquivo so pode ser apagado depois que ninguem o mantem aberto.
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass
    config.DB_PATH = Path(__file__).resolve().parent / "teste_pontos.db"
    config.DB_PATH.unlink(missing_ok=True)
    config.TAMANHO_GRUPO = 5
    config.PONTOS_PARTICIPACAO = 2
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    await criar_grupo(conn, nivel=nivel)
    canal = FakeCanal(CANAL)
    cog = Incursoes(FakeBot(conn, canal))
    return conn, canal, cog


async def montar_run(conn, canal, cog, incursao_id):
    await cog.entrar.callback(cog, FakeInteraction(canal, JOGADORES[0]), incursao_id)
    run = await db.run_do_canal(conn, CANAL)
    msg = await canal.fetch_message(run["mensagem_id"])
    for user_id in JOGADORES[1:]:
        await cog.recrutar(FakeInteraction(canal, user_id, msg), run["id"], "entrar")
    return await db.buscar_run(conn, run["id"])


async def atravessar(conn, canal, cog, run, incursao):
    """Leva o grupo até o objetivo, escolhendo salas sem combate."""
    for linha in range(1, incursao.passos + 1):
        run = await db.buscar_run(conn, run["id"])
        alvo = next(s for s in await cog._opcoes(run, linha) if not s.e_combate)
        msg = await canal.fetch_message(run["mensagem_id"])
        for user_id in JOGADORES:
            await cog.votar(FakeInteraction(canal, user_id, msg), run["id"], linha, alvo.id)

        atual = await db.buscar_run(conn, run["id"])
        if atual["status"] == "em_sala" and alvo.tem_teste:
            msg_sala = await canal.fetch_message(atual["mensagem_id"])
            for user_id in JOGADORES:
                agora = await db.buscar_run(conn, run["id"])
                if agora["status"] != "em_sala" or agora["sala_atual"] != alvo.id:
                    break
                await cog.rolar(FakeInteraction(canal, user_id, msg_sala), run["id"], alvo.id)
    return await db.buscar_run(conn, run["id"])


async def caso_placar_comeca_zerado():
    conn, canal, cog = await preparar()
    pontos = await db.placar(conn, GUILD)
    assert pontos == {}, pontos

    org_cog = Organizacao(FakeBot(conn, canal))
    inter = FakeInteraction(canal, JOGADORES[0])
    await org_cog.placar.callback(org_cog, inter)
    assert "Pontos das Organizações" in inter.resposta
    print("  placar começa zerado: ok")


async def caso_conclusao_credita():
    """Concluir o objetivo rende participação + conclusão, na Organização certa."""
    conn, canal, cog = await preparar()
    incursao, _ = montar_conteudo(
        cog, incursao_id="vit", pontos_conclusao=10, salas=salas_sem_combate()
    )
    run = await montar_run(conn, canal, cog, "vit")
    run = await atravessar(conn, canal, cog, run, incursao)
    assert run["status"] == "objetivo"

    await atacar_ate_cair(conn, canal, cog, run["id"], "OBJ")

    run = await db.buscar_run(conn, run["id"])
    assert run["status"] == "sucesso"

    lancamentos = await db.pontos_da_run(conn, run["id"])
    motivos = {l["chave"]: l["pontos"] for l in lancamentos}
    assert motivos["participacao"] == 2, motivos
    assert motivos["conclusao"] == 10, motivos

    pontos = await db.placar(conn, GUILD)
    assert pontos["Vórtice Oculto"] == 12, pontos
    # as outras três Organizações não recebem nada
    assert all(o not in pontos for o in ORGANIZACOES if o != "Vórtice Oculto")
    print("  conclusão credita participação + objetivo: ok")


async def caso_salas_secundarias_pontuam():
    """Cada sala superada com valor na planilha soma seu bônus."""
    conn, canal, cog = await preparar()
    # todas as salas do banco valem 3 pontos quando superadas
    incursao, _ = montar_conteudo(
        cog, incursao_id="salas", pontos_conclusao=10, salas=salas_sem_combate(pontos=3)
    )
    run = await montar_run(conn, canal, cog, "salas")
    run = await atravessar(conn, canal, cog, run, incursao)

    lancamentos = await db.pontos_da_run(conn, run["id"])
    por_chave = {l["chave"]: l["pontos"] for l in lancamentos}
    superadas = [c for c in por_chave if c.startswith("sala:")]
    assert superadas, f"nenhuma sala pontuou: {por_chave}"
    for chave in superadas:
        assert por_chave[chave] == 3, por_chave

    await atacar_ate_cair(conn, canal, cog, run["id"], "OBJ")

    total = (await db.placar(conn, GUILD))["Vórtice Oculto"]
    esperado = 2 + 10 + sum(por_chave[c] for c in superadas)
    assert total == esperado, f"esperava {esperado}, veio {total}"
    print("  salas secundárias somam seus bônus: ok")


async def caso_fracasso_credita_so_participacao():
    conn, canal, cog = await preparar(nivel=1)
    incursao, _ = montar_conteudo(
        cog, incursao_id="derrota", monstro_objetivo=IMBATIVEL, pontos_conclusao=10,
        salas=salas_sem_combate(),
    )
    run = await montar_run(conn, canal, cog, "derrota")
    run = await atravessar(conn, canal, cog, run, incursao)

    for _ in range(len(JOGADORES) + 2):
        atual = await db.buscar_run(conn, run["id"])
        if atual["status"] != "objetivo":
            break
        estado = await cog._estado_combate(atual, incursao.objetivo)
        msg = await canal.fetch_message(atual["mensagem_id"])
        for c in list(estado.vivos):
            await cog.atacar(FakeInteraction(canal, c.user_id, msg), run["id"], "OBJ")

    run = await db.buscar_run(conn, run["id"])
    assert run["status"] == "fracasso", run["status"]

    chaves = {l["chave"] for l in await db.pontos_da_run(conn, run["id"])}
    assert "participacao" in chaves, chaves
    assert "conclusao" not in chaves, "fracasso não pode creditar a conclusão"
    assert (await db.placar(conn, GUILD))["Vórtice Oculto"] == 2
    print("  fracasso rende só a participação: ok")


async def caso_nao_credita_duas_vezes():
    """A mesma chave na mesma run nunca entra duas vezes no placar."""
    conn, canal, cog = await preparar()
    montar_conteudo(cog, incursao_id="idem", salas=salas_sem_combate())
    run = await montar_run(conn, canal, cog, "idem")

    assert await db.lancar_pontos(
        conn, GUILD, "Guilda dos Mortos", 5, "Teste", run_id=run["id"], chave="x"
    )
    assert not await db.lancar_pontos(
        conn, GUILD, "Guilda dos Mortos", 5, "Teste de novo", run_id=run["id"], chave="x"
    )
    assert (await db.placar(conn, GUILD))["Guilda dos Mortos"] == 5

    # sem chave, é lançamento avulso e pode repetir (ajuste manual)
    await db.lancar_pontos(conn, GUILD, "Guilda dos Mortos", 5, "Ajuste")
    await db.lancar_pontos(conn, GUILD, "Guilda dos Mortos", 5, "Ajuste")
    assert (await db.placar(conn, GUILD))["Guilda dos Mortos"] == 15
    print("  um motivo não credita duas vezes: ok")


async def caso_ajuste_manual_e_extrato():
    conn, canal, cog = await preparar()
    org_cog = Organizacao(FakeBot(conn, canal))

    class Escolha:
        def __init__(self, value):
            self.value = value
            self.name = value

    inter = FakeInteraction(canal, JOGADORES[0])
    await org_cog.ajustar.callback(
        org_cog, inter, Escolha("Sentinelas do Alvorecer"), 7, "Missão narrada na mesa"
    )
    assert (await db.placar(conn, GUILD))["Sentinelas do Alvorecer"] == 7

    # negativo tira pontos
    inter = FakeInteraction(canal, JOGADORES[0])
    await org_cog.ajustar.callback(
        org_cog, inter, Escolha("Sentinelas do Alvorecer"), -3, "Correção"
    )
    assert (await db.placar(conn, GUILD))["Sentinelas do Alvorecer"] == 4

    # zero é recusado
    inter = FakeInteraction(canal, JOGADORES[0])
    await org_cog.ajustar.callback(org_cog, inter, Escolha("Guilda dos Mortos"), 0, "Nada")
    assert "não muda nada" in inter.resposta

    registros = await db.lancamentos(conn, GUILD, "Sentinelas do Alvorecer")
    assert len(registros) == 2 and registros[0]["pontos"] == -3
    inter = FakeInteraction(canal, JOGADORES[0])
    await org_cog.extrato.callback(org_cog, inter, Escolha("Sentinelas do Alvorecer"), 10)
    assert "Extrato" in inter.resposta
    print("  ajuste manual e extrato: ok")


async def main():
    try:
        await caso_placar_comeca_zerado()
        await caso_conclusao_credita()
        await caso_salas_secundarias_pontuam()
        await caso_fracasso_credita_so_participacao()
        await caso_nao_credita_duas_vezes()
        await caso_ajuste_manual_e_extrato()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass


asyncio.run(main())
print("TESTES DE PONTOS PASSARAM")
