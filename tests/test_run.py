"""Roda uma incursão de ponta a ponta com dublês do Discord.

Cobre recrutamento, início automático ao encher o grupo, votação por linha,
entrada nas salas, testes de perícia, conclusão e chegada ao objetivo.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import config, database as db  # noqa: E402
from src.cogs.incursao import Incursoes  # noqa: E402
from fakes import (  # noqa: E402
    ATRIBUTOS,
    CANAL,
    GUILD,
    JOGADORES,
    TREINADAS,
    FakeBot,
    FakeCanal,
    FakeInteraction,
    criar_grupo,
)


# ------------------------------------------------------------------ teste


_ABERTAS = []


async def main() -> None:
    config.DB_PATH = Path(__file__).resolve().parent / "teste_run.db"
    config.DB_PATH.unlink(missing_ok=True)
    config.TAMANHO_GRUPO = 5

    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    await criar_grupo(conn)

    canal = FakeCanal(CANAL)
    bot = FakeBot(conn, canal)
    cog = Incursoes(bot)
    cog._carregar_tolerante()
    assert "vortice_cripta" in cog.incursoes, "a incursão de exemplo precisa estar importada"
    incursao = cog.incursoes["vortice_cripta"]

    # --- recrutamento ---
    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.entrar.callback(cog, inter, "vortice_cripta")
    run = await db.run_do_canal(conn, CANAL)
    assert run and run["status"] == "recrutando"
    assert await db.participantes(conn, run["id"]) == [JOGADORES[0]]

    # mesma pessoa nao entra duas vezes
    msg_recrut = await canal.fetch_message(run["mensagem_id"])
    dupe = FakeInteraction(canal, JOGADORES[0], msg_recrut)
    await cog.recrutar(dupe, run["id"], "entrar")
    assert "já está no grupo" in dupe.resposta

    # quem nao tem personagem e barrado
    sem_ficha = FakeInteraction(canal, 999, msg_recrut)
    await cog.recrutar(sem_ficha, run["id"], "entrar")
    assert "não tem personagem" in sem_ficha.resposta

    # os outros quatro entram; o quinto dispara o inicio automatico
    for user_id in JOGADORES[1:]:
        await cog.recrutar(FakeInteraction(canal, user_id, msg_recrut), run["id"], "entrar")

    run = await db.buscar_run(conn, run["id"])
    assert run["status"] == "escolhendo", f"esperava escolhendo, veio {run['status']}"
    assert run["linha_atual"] == 1
    assert len(await db.participantes(conn, run["id"])) == 5
    # entrar na run marca o intervalo de todo mundo
    assert await db.dias_desde_ultima_incursao(conn, GUILD, JOGADORES[3]) is not None

    # --- as tres linhas ---
    for linha in (1, 2, 3):
        run = await db.buscar_run(conn, run["id"])
        assert run["status"] == "escolhendo" and run["linha_atual"] == linha

        # escolhe uma sala que se resolve por teste (combate e da proxima fase)
        alvo = next(s for s in incursao.opcoes(linha) if s.tem_teste)
        msg_voto = await canal.fetch_message(run["mensagem_id"])

        # quem nao esta na run nao vota
        intruso = FakeInteraction(canal, 999, msg_voto)
        await cog.votar(intruso, run["id"], linha, alvo.id)
        assert "não faz parte" in intruso.resposta

        for user_id in JOGADORES:
            await cog.votar(FakeInteraction(canal, user_id, msg_voto), run["id"], linha, alvo.id)

        run = await db.buscar_run(conn, run["id"])
        assert run["status"] == "em_sala", f"linha {linha}: esperava em_sala, veio {run['status']}"
        assert run["sala_atual"] == alvo.id

        # --- testes de pericia ---
        msg_sala = await canal.fetch_message(run["mensagem_id"])
        rolaram = 0
        for user_id in JOGADORES:
            atual = await db.buscar_run(conn, run["id"])
            if atual["status"] != "em_sala" or atual["sala_atual"] != alvo.id:
                break  # o alvo de progresso foi atingido antes de todos rolarem
            inter = FakeInteraction(canal, user_id, msg_sala)
            await cog.rolar(inter, run["id"], alvo.id)
            assert "🎲" in inter.resposta
            rolaram += 1

            # ninguem rola duas vezes na mesma sala
            de_novo = FakeInteraction(canal, user_id, msg_sala)
            await cog.rolar(de_novo, run["id"], alvo.id)
            assert "já rolou" in de_novo.resposta or "já foi resolvida" in de_novo.resposta

        registros = await db.testes_da_sala(conn, run["id"], alvo.id)
        assert 1 <= len(registros) <= 5 and len(registros) == rolaram
        for r in registros:
            assert 1 <= r["d20"] <= 20 and r["pericia"] in alvo.pericias and r["cd"] == alvo.cd

    # --- objetivo ---
    run = await db.buscar_run(conn, run["id"])
    assert run["status"] == "objetivo", f"esperava objetivo, veio {run['status']}"
    assert run["sala_atual"] == incursao.objetivo.id
    assert incursao.objetivo.tipo == "Combate"

    # depois do fim, a run do canal continua sendo essa e ninguem entra em outra
    outra = FakeInteraction(canal, JOGADORES[0])
    await cog.entrar.callback(cog, outra, "vortice_cripta")
    assert "Já existe uma incursão" in outra.resposta

    # --- status e desistencia ---
    st = FakeInteraction(canal, JOGADORES[0])
    await cog.status.callback(cog, st)
    assert f"Run #{run['id']}" in st.resposta

    for user_id in JOGADORES[:3]:  # maioria de 5
        d = FakeInteraction(canal, user_id)
        await cog.desistir.callback(cog, d)
    run = await db.buscar_run(conn, run["id"])
    assert run["status"] == "desistiu", f"esperava desistiu, veio {run['status']}"

    # com a run encerrada, o canal aceita uma nova
    assert await db.run_do_canal(conn, CANAL) is None

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print(f"run simulada com {len(canal.mensagens)} mensagens postadas")


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
print("TESTE DE RUN PASSOU")
