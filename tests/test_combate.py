"""Combate: rodadas, contra-ataque, vitória, derrota total e descanso.

Usa incursões sintéticas com monstros impossíveis de errar ou de acertar, para
que o resultado não dependa do dado.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import config, database as db, motor  # noqa: E402
from src.cogs.incursao import Incursoes, ViewCombate  # noqa: E402
from fakes import (  # noqa: E402
    ATRIBUTOS,
    CANAL,
    GUILD,
    IMBATIVEL,
    INDEFESO,
    JOGADORES,
    TREINADAS,
    FakeBot,
    FakeCanal,
    FakeInteraction,
    incursao_teste,
)

_ABERTAS = []


async def preparar(hp_max=40, ca=18, bonus_ataque=8, dano="1d6+3"):
    config.DB_PATH = Path(__file__).resolve().parent / "teste_combate.db"
    config.DB_PATH.unlink(missing_ok=True)
    config.TAMANHO_GRUPO = 5
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    for user_id in JOGADORES:
        await db.salvar_ficha(conn, GUILD, user_id, f"Heroi{user_id}", 8, ATRIBUTOS, TREINADAS)
        for coluna, valor in (
            ("hp_max", hp_max), ("ca", ca), ("bonus_ataque", bonus_ataque), ("dano_arma", dano)
        ):
            await db.atualizar_campo(conn, GUILD, user_id, coluna, valor)
    canal = FakeCanal(CANAL)
    cog = Incursoes(FakeBot(conn, canal))
    cog.incursoes = {}
    return conn, canal, cog


async def montar_run(conn, canal, cog, incursao_id):
    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.entrar.callback(cog, inter, incursao_id)
    run = await db.run_do_canal(conn, CANAL)
    msg = await canal.fetch_message(run["mensagem_id"])
    for user_id in JOGADORES[1:]:
        await cog.recrutar(FakeInteraction(canal, user_id, msg), run["id"], "entrar")
    return await db.buscar_run(conn, run["id"])


async def atravessar_ate_objetivo(conn, canal, cog, run, incursao):
    """Vota e resolve as três linhas escolhendo sempre uma sala sem combate."""
    for linha in (1, 2, 3):
        run = await db.buscar_run(conn, run["id"])
        assert run["status"] == "escolhendo", run["status"]
        alvo = next(s for s in incursao.opcoes(linha) if not s.e_combate)
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


async def caso_hp_inicial():
    """Ao começar a run, todo mundo entra com o HP máximo da ficha."""
    conn, canal, cog = await preparar(hp_max=37)
    cog.incursoes["t"] = incursao_teste("t", INDEFESO)
    run = await montar_run(conn, canal, cog, "t")
    hps = await db.hp_dos_participantes(conn, run["id"])
    assert set(hps.values()) == {37}, hps
    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  HP inicializado no começo da run: ok")


async def caso_vitoria_no_objetivo():
    """Chegando ao objetivo, o combate abre e a vitória conclui a run."""
    conn, canal, cog = await preparar()
    incursao = incursao_teste("facil", INDEFESO)
    cog.incursoes["facil"] = incursao
    run = await montar_run(conn, canal, cog, "facil")
    run = await atravessar_ate_objetivo(conn, canal, cog, run, incursao)

    assert run["status"] == "objetivo" and run["sala_atual"] == "OBJ", run
    estado = await cog._estado_combate(run, incursao.objetivo)
    assert estado is not None and estado.monstro_hp == 1 and estado.rodada == 1

    # um golpe basta contra CA 1 / 1 HP
    msg = await canal.fetch_message(run["mensagem_id"])
    inter = FakeInteraction(canal, JOGADORES[0], msg)
    await cog.atacar(inter, run["id"], "OBJ")
    assert "acertou" in inter.resposta

    run = await db.buscar_run(conn, run["id"])
    assert run["status"] == "sucesso", f"esperava sucesso, veio {run['status']}"
    assert any("objetivo cumprido" in (m.embeds[0].title or "") for m in canal.mensagens if m.embeds)

    # combate encerrado não aceita mais ataque
    tarde = FakeInteraction(canal, JOGADORES[1], msg)
    await cog.atacar(tarde, run["id"], "OBJ")
    assert "já terminou" in tarde.resposta

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  vitória no objetivo conclui a run: ok")


async def caso_combate_no_meio_do_mapa():
    """Vencer uma sala de combate da linha 1 leva o grupo para a linha 2."""
    conn, canal, cog = await preparar()
    incursao = incursao_teste("meio", INDEFESO, monstro_meio=INDEFESO)
    cog.incursoes["meio"] = incursao
    run = await montar_run(conn, canal, cog, "meio")

    msg = await canal.fetch_message(run["mensagem_id"])
    for user_id in JOGADORES:
        await cog.votar(FakeInteraction(canal, user_id, msg), run["id"], 1, "A1")

    run = await db.buscar_run(conn, run["id"])
    assert run["status"] == "em_sala" and run["sala_atual"] == "A1"

    msg_combate = await canal.fetch_message(run["mensagem_id"])
    await cog.atacar(FakeInteraction(canal, JOGADORES[0], msg_combate), run["id"], "A1")

    run = await db.buscar_run(conn, run["id"])
    assert run["status"] == "escolhendo" and run["linha_atual"] == 2, run
    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  combate no meio do mapa devolve à votação: ok")


async def caso_rodadas_e_contra_ataque():
    """Todos atacam uma vez; aí o monstro revida e a rodada vira."""
    conn, canal, cog = await preparar(hp_max=200)
    incursao = incursao_teste("rodadas", IMBATIVEL)
    cog.incursoes["rodadas"] = incursao
    run = await montar_run(conn, canal, cog, "rodadas")
    run = await atravessar_ate_objetivo(conn, canal, cog, run, incursao)
    assert run["status"] == "objetivo"

    msg = await canal.fetch_message(run["mensagem_id"])
    for i, user_id in enumerate(JOGADORES):
        inter = FakeInteraction(canal, user_id, msg)
        await cog.atacar(inter, run["id"], "OBJ")
        assert "errou" in inter.resposta  # CA 40 é inalcançável

        # o mesmo personagem não ataca duas vezes na mesma rodada
        if i < len(JOGADORES) - 1:
            repetido = FakeInteraction(canal, user_id, msg)
            await cog.atacar(repetido, run["id"], "OBJ")
            assert "já atacou nesta rodada" in repetido.resposta

    estado = await cog._estado_combate(await db.buscar_run(conn, run["id"]), incursao.objetivo)
    assert estado.rodada == 2, f"a rodada deveria ter virado, veio {estado.rodada}"
    assert len(estado.caidos) == 1, "o contra-ataque deveria ter derrubado exatamente um"
    assert estado.monstro_hp == 999, "ninguém acertou, o monstro não perde HP"

    # quem caiu não ataca mais
    caido = estado.caidos[0]
    inter = FakeInteraction(canal, caido.user_id, msg)
    await cog.atacar(inter, run["id"], "OBJ")
    assert "caído" in inter.resposta

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  rodadas e contra-ataque: ok")


async def caso_derrota_total():
    """Com o grupo inteiro caído, a run termina em fracasso."""
    conn, canal, cog = await preparar(hp_max=10)
    incursao = incursao_teste("letal", IMBATIVEL)
    cog.incursoes["letal"] = incursao
    run = await montar_run(conn, canal, cog, "letal")
    run = await atravessar_ate_objetivo(conn, canal, cog, run, incursao)

    for _ in range(len(JOGADORES) + 2):
        atual = await db.buscar_run(conn, run["id"])
        if atual["status"] != "objetivo":
            break
        estado = await cog._estado_combate(atual, incursao.objetivo)
        msg = await canal.fetch_message(atual["mensagem_id"])
        for c in list(estado.vivos):
            await cog.atacar(FakeInteraction(canal, c.user_id, msg), run["id"], "OBJ")

    run = await db.buscar_run(conn, run["id"])
    assert run["status"] == "fracasso", f"esperava fracasso, veio {run['status']}"
    assert any("fracassada" in (m.embeds[0].title or "") for m in canal.mensagens if m.embeds)

    hps = await db.hp_dos_participantes(conn, run["id"])
    assert all(hp == 0 for hp in hps.values()), hps
    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  derrota total encerra a run: ok")


async def caso_descanso_cura():
    """A sala de Descanso levanta os caídos e completa quem está machucado."""
    conn, canal, cog = await preparar(hp_max=40)
    incursao = incursao_teste("cura", INDEFESO)
    cog.incursoes["cura"] = incursao
    run = await montar_run(conn, canal, cog, "cura")

    # machuca o grupo antes do descanso
    await db.definir_hp_varios(conn, run["id"], {JOGADORES[0]: 0, JOGADORES[1]: 5})

    msg = await canal.fetch_message(run["mensagem_id"])
    for user_id in JOGADORES:
        await cog.votar(FakeInteraction(canal, user_id, msg), run["id"], 1, "A3")  # Descanso

    hps = await db.hp_dos_participantes(conn, run["id"])
    assert hps[JOGADORES[0]] == 20, f"caído deveria voltar com metade, veio {hps[JOGADORES[0]]}"
    assert hps[JOGADORES[1]] == 40, f"machucado deveria completar, veio {hps[JOGADORES[1]]}"
    assert (await db.buscar_run(conn, run["id"]))["linha_atual"] == 2

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  descanso cura e levanta caídos: ok")


async def caso_restart_no_combate():
    """Os botões de ataque voltam a funcionar depois de um restart."""
    conn, canal, cog = await preparar()
    incursao = incursao_teste("restart", IMBATIVEL)
    cog.incursoes["restart"] = incursao
    run = await montar_run(conn, canal, cog, "restart")
    run = await atravessar_ate_objetivo(conn, canal, cog, run, incursao)
    assert run["status"] == "objetivo"

    bot2 = FakeBot(conn, canal)
    cog2 = Incursoes(bot2)
    cog2.incursoes = {"restart": incursao}
    await cog2.restaurar_views()

    assert bot2.views_registradas, "nenhuma view restaurada"
    view, mensagem_id = bot2.views_registradas[0]
    assert isinstance(view, ViewCombate)
    assert mensagem_id == run["mensagem_id"]

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  botões de combate sobrevivem a um restart: ok")


async def caso_motor_puro():
    """O dano nunca fica negativo e o HP nunca passa do máximo nem do zero."""
    from src.incursoes import Monstro

    monstro = Monstro("Teste", ca=10, ataque=5, dano="1d4", hp=10)
    grupo = [motor.Combatente(1, "A", ca=10, bonus_ataque=5, dano_arma="1d4", hp_max=10, hp_atual=3)]
    estado = motor.EstadoCombate(monstro, 2, 1, grupo)

    for _ in range(50):
        motor.atacar_monstro(grupo[0], estado)
        assert estado.monstro_hp >= 0
    assert estado.monstro_derrotado

    grupo[0].hp_atual = 1
    for _ in range(50):
        alvo = motor.sortear_alvo(estado)
        if alvo is None:
            break
        motor.contra_atacar(estado, alvo)
        assert grupo[0].hp_atual >= 0
    assert estado.grupo_caido and motor.sortear_alvo(estado) is None
    print("  motor: HP não passa dos limites: ok")


async def main():
    try:
        await _casos()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass


async def _casos():
    await caso_motor_puro()
    await caso_hp_inicial()
    await caso_vitoria_no_objetivo()
    await caso_combate_no_meio_do_mapa()
    await caso_rodadas_e_contra_ataque()
    await caso_derrota_total()
    await caso_descanso_cura()
    await caso_restart_no_combate()


asyncio.run(main())
print("TESTES DE COMBATE PASSARAM")
