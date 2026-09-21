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
    ATRIBUTOS,
    CANAL,
    GUILD,
    JOGADORES,
    TREINADAS,
    FakeBot,
    FakeCanal,
    FakeInteraction,
)


async def montar_run_em_votacao(conn, canal, cog):
    """Cria uma run com os 5 jogadores, já na votação da linha 1."""
    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.entrar.callback(cog, inter, "vortice_cripta")
    run = await db.run_do_canal(conn, CANAL)
    msg = await canal.fetch_message(run["mensagem_id"])
    for user_id in JOGADORES[1:]:
        await cog.recrutar(FakeInteraction(canal, user_id, msg), run["id"], "entrar")
    return await db.buscar_run(conn, run["id"])


async def preparar():
    config.DB_PATH = Path(__file__).resolve().parent / "teste_votacao.db"
    config.DB_PATH.unlink(missing_ok=True)
    config.TAMANHO_GRUPO = 5
    conn = await db.conectar()
    await db.criar_schema(conn)
    for user_id in JOGADORES:
        await db.salvar_ficha(conn, GUILD, user_id, f"Heroi{user_id}", 8, ATRIBUTOS, TREINADAS)
    canal = FakeCanal(CANAL)
    cog = Incursoes(FakeBot(conn, canal))
    cog._carregar_tolerante()
    return conn, canal, cog


async def caso_maioria_no_prazo():
    """Dois votam numa sala, um noutra; o prazo estoura e a maioria simples vence."""
    conn, canal, cog = await preparar()
    run = await montar_run_em_votacao(conn, canal, cog)
    opcoes = cog.incursoes["vortice_cripta"].opcoes(1)
    msg = await canal.fetch_message(run["mensagem_id"])

    for user_id in JOGADORES[:2]:
        await cog.votar(FakeInteraction(canal, user_id, msg), run["id"], 1, opcoes[0].id)
    await cog.votar(FakeInteraction(canal, JOGADORES[2], msg), run["id"], 1, opcoes[1].id)

    # ainda faltam dois votos: nada se move
    assert (await db.buscar_run(conn, run["id"]))["status"] == "escolhendo"

    await cog._fechar_votacao(run, 1, por_prazo=True)
    depois = await db.buscar_run(conn, run["id"])
    assert depois["status"] in ("em_sala", "escolhendo")
    assert depois["sala_atual"] == opcoes[0].id, "a sala mais votada deveria ter vencido"

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  maioria simples no prazo: ok")


async def caso_empate_antes_do_prazo():
    """Todos votaram mas deu empate: ninguém avança, a votação segue aberta."""
    conn, canal, cog = await preparar()
    run = await montar_run_em_votacao(conn, canal, cog)
    opcoes = cog.incursoes["vortice_cripta"].opcoes(1)
    msg = await canal.fetch_message(run["mensagem_id"])

    # 2 x 2 x 1 -> empate entre as duas primeiras
    for user_id, sala in zip(JOGADORES, [opcoes[0], opcoes[0], opcoes[1], opcoes[1], opcoes[2]]):
        await cog.votar(FakeInteraction(canal, user_id, msg), run["id"], 1, sala.id)

    depois = await db.buscar_run(conn, run["id"])
    assert depois["status"] == "escolhendo", "empate não pode fazer o grupo avançar"
    assert depois["sala_atual"] is None
    assert any("Empate" in (m.content or "") for m in canal.mensagens)

    # alguém troca o voto e o empate se desfaz
    await cog.votar(FakeInteraction(canal, JOGADORES[4], msg), run["id"], 1, opcoes[0].id)
    depois = await db.buscar_run(conn, run["id"])
    assert depois["status"] == "em_sala" and depois["sala_atual"] == opcoes[0].id

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  empate antes do prazo: ok")


async def caso_empate_no_prazo():
    """Empate quando o prazo estoura: sorteio decide, entre as empatadas."""
    conn, canal, cog = await preparar()
    run = await montar_run_em_votacao(conn, canal, cog)
    opcoes = cog.incursoes["vortice_cripta"].opcoes(1)
    msg = await canal.fetch_message(run["mensagem_id"])

    await cog.votar(FakeInteraction(canal, JOGADORES[0], msg), run["id"], 1, opcoes[0].id)
    await cog.votar(FakeInteraction(canal, JOGADORES[1], msg), run["id"], 1, opcoes[1].id)

    await cog._fechar_votacao(run, 1, por_prazo=True)
    depois = await db.buscar_run(conn, run["id"])
    assert depois["sala_atual"] in (opcoes[0].id, opcoes[1].id)
    assert any("Sorteio" in (m.content or "") for m in canal.mensagens)

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  empate no prazo resolvido por sorteio: ok")


async def caso_ninguem_votou():
    """Prazo estoura sem nenhum voto: posição mantida e prazo renovado."""
    conn, canal, cog = await preparar()
    run = await montar_run_em_votacao(conn, canal, cog)
    prazo_antes = run["votacao_expira_em"]

    await cog._fechar_votacao(run, 1, por_prazo=True)
    depois = await db.buscar_run(conn, run["id"])
    assert depois["status"] == "escolhendo" and depois["sala_atual"] is None
    assert depois["votacao_expira_em"] >= prazo_antes
    assert any("Ninguém votou" in (m.content or "") for m in canal.mensagens)

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  ninguém votou: posição mantida: ok")


async def caso_restart():
    """Depois de um restart, os botões da mensagem aberta voltam a funcionar."""
    conn, canal, cog = await preparar()
    run = await montar_run_em_votacao(conn, canal, cog)

    # novo cog, como se o processo tivesse reiniciado
    bot2 = FakeBot(conn, canal)
    cog2 = Incursoes(bot2)
    cog2._carregar_tolerante()
    await cog2.restaurar_views()

    assert bot2.views_registradas, "nenhuma view foi restaurada"
    view, mensagem_id = bot2.views_registradas[0]
    assert isinstance(view, ViewVotacao)
    assert mensagem_id == run["mensagem_id"]
    assert len(view.children) == 3

    # e o voto pelo cog novo continua avançando a run
    msg = await canal.fetch_message(run["mensagem_id"])
    opcoes = cog2.incursoes["vortice_cripta"].opcoes(1)
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


async def main():
    await caso_maioria_no_prazo()
    await caso_empate_antes_do_prazo()
    await caso_empate_no_prazo()
    await caso_ninguem_votou()
    await caso_restart()
    await caso_intervalo_entre_incursoes()


asyncio.run(main())
print("TESTES DE VOTAÇÃO PASSARAM")
