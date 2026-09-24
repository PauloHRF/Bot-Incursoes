"""Caminhos de borda da votação: maioria no prazo, empate, silêncio e restart."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import config, database as db  # noqa: E402
from src.cogs.incursao import Incursoes, ViewVotacao  # noqa: E402
from fakes import (  # noqa: E402
    CANAL,
    GUILD,
    JOGADORES,
    FakeBot,
    FakeCanal,
    FakeInteraction,
    criar_grupo,
    montar_conteudo,
    salas_sem_combate,
)


async def montar_run_em_votacao(conn, canal, cog):
    """Cria uma run com os 5 jogadores, já na votação da linha 1."""
    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.entrar.callback(cog, inter, "t")
    run = await db.run_do_canal(conn, CANAL)
    msg = await canal.fetch_message(run["mensagem_id"])
    for user_id in JOGADORES[1:]:
        await cog.recrutar(FakeInteraction(canal, user_id, msg), run["id"], "entrar")
    return await db.buscar_run(conn, run["id"])


_ABERTAS = []


async def preparar():
    config.DB_PATH = Path(__file__).resolve().parent / "teste_votacao.db"
    config.DB_PATH.unlink(missing_ok=True)
    config.TAMANHO_GRUPO = 5
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    await criar_grupo(conn)
    canal = FakeCanal(CANAL)
    cog = Incursoes(FakeBot(conn, canal))
    montar_conteudo(cog, tamanho="Média", salas=salas_sem_combate(8))
    return conn, canal, cog


async def caso_maioria_fecha_sem_esperar():
    """Assim que 3 dos 5 votam na mesma sala, o grupo avança."""
    conn, canal, cog = await preparar()
    run = await montar_run_em_votacao(conn, canal, cog)
    opcoes = await cog._opcoes(run, 1)
    msg = await canal.fetch_message(run["mensagem_id"])
    # a votacao marca o grupo: sem mencao ninguem e avisado da vez
    assert all(f"<@{u}>" in (msg.content or "") for u in JOGADORES[:5]), msg.content

    # dois votos ainda nao decidem nada
    for user_id in JOGADORES[:2]:
        await cog.votar(FakeInteraction(canal, user_id, msg), run["id"], 1, opcoes[0].id)
    assert (await db.buscar_run(conn, run["id"]))["status"] == "escolhendo"

    # o terceiro fecha a maioria de 5, sem esperar os outros dois
    await cog.votar(FakeInteraction(canal, JOGADORES[2], msg), run["id"], 1, opcoes[0].id)
    depois = await db.buscar_run(conn, run["id"])
    assert depois["status"] == "em_sala", depois["status"]
    assert depois["sala_atual"] == opcoes[0].id
    assert len(await db.votos_da_linha(conn, run["id"], 1)) == 3, "avançou com 3 de 5"
    assert any("não espera" in (m.content or "") for m in canal.mensagens)

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  maioria fecha sem esperar os que faltam: ok")


async def caso_votos_divididos_esperam():
    """Enquanto ninguém tem maioria, a votação continua aberta."""
    conn, canal, cog = await preparar()
    run = await montar_run_em_votacao(conn, canal, cog)
    opcoes = await cog._opcoes(run, 1)
    msg = await canal.fetch_message(run["mensagem_id"])

    # 2 x 1: ninguem chegou a 3
    for user_id in JOGADORES[:2]:
        await cog.votar(FakeInteraction(canal, user_id, msg), run["id"], 1, opcoes[0].id)
    await cog.votar(FakeInteraction(canal, JOGADORES[2], msg), run["id"], 1, opcoes[1].id)
    parado = await db.buscar_run(conn, run["id"])
    assert parado["status"] == "escolhendo" and parado["sala_atual"] is None

    # o quarto voto fecha a maioria na primeira
    await cog.votar(FakeInteraction(canal, JOGADORES[3], msg), run["id"], 1, opcoes[0].id)
    depois = await db.buscar_run(conn, run["id"])
    assert depois["status"] == "em_sala" and depois["sala_atual"] == opcoes[0].id

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  votos divididos seguem esperando: ok")


async def caso_empate_com_todos_votando():
    """2x2x1: todos votaram, ninguém tem maioria, ninguém avança."""
    conn, canal, cog = await preparar()
    run = await montar_run_em_votacao(conn, canal, cog)
    opcoes = await cog._opcoes(run, 1)
    msg = await canal.fetch_message(run["mensagem_id"])

    for user_id, sala in zip(JOGADORES, [opcoes[0], opcoes[0], opcoes[1], opcoes[1], opcoes[2]]):
        await cog.votar(FakeInteraction(canal, user_id, msg), run["id"], 1, sala.id)

    depois = await db.buscar_run(conn, run["id"])
    assert depois["status"] == "escolhendo", "empate não pode fazer o grupo avançar"
    assert depois["sala_atual"] is None
    assert any("Empate" in (m.content or "") for m in canal.mensagens)

    # alguém troca o voto e a maioria se forma
    await cog.votar(FakeInteraction(canal, JOGADORES[4], msg), run["id"], 1, opcoes[0].id)
    depois = await db.buscar_run(conn, run["id"])
    assert depois["status"] == "em_sala" and depois["sala_atual"] == opcoes[0].id

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  empate com todos votando espera desempate: ok")


async def caso_sem_prazo():
    """A votação não guarda prazo nenhum: espera indefinidamente."""
    conn, canal, cog = await preparar()
    run = await montar_run_em_votacao(conn, canal, cog)
    assert run["votacao_expira_em"] is None, run["votacao_expira_em"]

    # sem voto nenhum, nada acontece e nada e postado
    antes = len(canal.mensagens)
    await cog._fechar_votacao(run, 1)
    depois = await db.buscar_run(conn, run["id"])
    assert depois["status"] == "escolhendo" and depois["sala_atual"] is None
    assert len(canal.mensagens) == antes

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  sem prazo: a votação espera sem reclamar: ok")


async def caso_restart():
    """Depois de um restart, os botões da mensagem aberta voltam a funcionar."""
    conn, canal, cog = await preparar()
    run = await montar_run_em_votacao(conn, canal, cog)

    # novo cog, como se o processo tivesse reiniciado
    bot2 = FakeBot(conn, canal)
    cog2 = Incursoes(bot2)
    montar_conteudo(cog2, tamanho="Média", salas=salas_sem_combate(8))
    await cog2.restaurar_views()

    assert bot2.views_registradas, "nenhuma view foi restaurada"
    view, mensagem_id = bot2.views_registradas[0]
    assert isinstance(view, ViewVotacao)
    assert mensagem_id == run["mensagem_id"]
    assert len(view.children) == 3

    # e o voto pelo cog novo continua avançando a run
    msg = await canal.fetch_message(run["mensagem_id"])
    opcoes = await cog2._opcoes(run, 1)
    for user_id in JOGADORES:
        await cog2.votar(FakeInteraction(canal, user_id, msg), run["id"], 1, opcoes[0].id)
    assert (await db.buscar_run(conn, run["id"]))["status"] == "em_sala"

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  botões sobrevivem a um restart: ok")


async def caso_intervalo_entre_incursoes():
    """Quem acabou de participar fica bloqueado pelo intervalo configurado."""
    conn, canal, cog = await preparar()
    run = await montar_run_em_votacao(conn, canal, cog)
    await db.atualizar_run(conn, run["id"], status="desistiu")

    bloqueio = await cog._motivo_de_bloqueio(GUILD, JOGADORES[0])
    assert bloqueio and "intervalo" in bloqueio.lower(), bloqueio

    await db.definir_intervalo(conn, GUILD, 0)
    assert await cog._motivo_de_bloqueio(GUILD, JOGADORES[0]) is None

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  intervalo entre incursões: ok")


async def caso_canal_fica_com_um_cartao_so():
    """Cada passo apaga o anterior: o canal mostra so o momento atual."""
    conn, canal, cog = await preparar()
    run = await montar_run_em_votacao(conn, canal, cog)

    id_votacao = run["mensagem_id"]
    assert (await canal.fetch_message(id_votacao)).view is not None, "a votacao abre com botoes"

    # votada, a mensagem da votacao sai do canal
    alvo = next(s for s in await cog._opcoes(run, 1) if s.tem_teste)
    msg = await canal.fetch_message(id_votacao)
    for user_id in JOGADORES:
        await cog.votar(FakeInteraction(canal, user_id, msg), run["id"], 1, alvo.id)
    assert not [m for m in canal.mensagens if m.id == id_votacao], "a votacao devia sumir"

    # a sala aberta tem botao, e fica ate a proxima votacao
    atual = await db.buscar_run(conn, run["id"])
    id_sala = atual["mensagem_id"]
    msg_sala = await canal.fetch_message(id_sala)
    assert msg_sala.view is not None

    for user_id in JOGADORES:
        agora = await db.buscar_run(conn, run["id"])
        if agora["status"] != "em_sala" or agora["sala_atual"] != alvo.id:
            break
        await cog.rolar(FakeInteraction(canal, user_id, msg_sala), run["id"], alvo.id)
    assert not [m for m in canal.mensagens if m.id == id_sala], "a sala devia sumir"

    # agora a votacao da linha 2 esta aberta; desistir precisa fecha-la
    atual = await db.buscar_run(conn, run["id"])
    id_votacao2 = atual["mensagem_id"]
    assert (await canal.fetch_message(id_votacao2)).view is not None

    for user_id in JOGADORES[:3]:
        await cog.desistir.callback(cog, FakeInteraction(canal, user_id))
    assert (await db.buscar_run(conn, run["id"]))["status"] == "desistiu"
    assert (
        await canal.fetch_message(id_votacao2)
    ).view is None, "a votacao aberta ficou clicavel depois da run encerrada"

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  cada passo apaga o anterior e os botoes somem ao encerrar: ok")


async def main():
    await caso_maioria_fecha_sem_esperar()
    await caso_votos_divididos_esperam()
    await caso_empate_com_todos_votando()
    await caso_sem_prazo()
    await caso_restart()
    await caso_intervalo_entre_incursoes()
    await caso_canal_fica_com_um_cartao_so()


async def _com_limpeza():
    try:
        await main()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass


def _fechar_tudo():
    asyncio.run(_com_limpeza())


_fechar_tudo()
print("TESTES DE VOTAÇÃO PASSARAM")
