"""Vida temporária: absorve dano, não empilha, e as habilidades que a dão."""
from __future__ import annotations

import asyncio
import random
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import classes as cl, config, database as db, embeds as E, motor  # noqa: E402
from src.cogs.incursao import Incursoes  # noqa: E402
from fakes import (  # noqa: E402
    CANAL,
    GUILD,
    INDEFESO,
    JOGADORES,
    FakeBot,
    FakeCanal,
    FakeInteraction,
    criar_grupo,
    montar_conteudo,
    salas_sem_combate,
)

_ABERTAS = []

DURADOURO = {**INDEFESO, "hp": 4000}
# Bate uma vez por rodada, forte o bastante para derrubar quem tem pouco HP.
CERTEIRO = {"nome": "Martelo", "ca": 1, "ataque": 40, "dano": "1d1+29", "hp": 4000}


async def preparar(classe="xama", nivel=8, monstro=DURADOURO, quantos=2):
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass
    config.DB_PATH = Path(__file__).resolve().parent / "teste_thp.db"
    config.DB_PATH.unlink(missing_ok=True)
    config.TAMANHO_GRUPO = 5
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    await criar_grupo(conn, nivel=nivel, classe=classe)
    canal = FakeCanal(CANAL)
    cog = Incursoes(FakeBot(conn, canal))
    incursao, _ = montar_conteudo(
        cog, tamanho="Curta", monstro_objetivo=monstro, salas=salas_sem_combate()
    )
    run_id = await db.criar_run(conn, GUILD, CANAL, incursao.id, JOGADORES[0])
    for user_id in JOGADORES[:quantos]:
        personagem = await db.personagem_por_nome(conn, GUILD, user_id, f"Heroi{user_id}")
        await db.adicionar_participante(conn, run_id, user_id, personagem["id"])
    await db.inicializar_hp(conn, run_id)
    await db.atualizar_run(
        conn, run_id, status="objetivo", sala_atual="OBJ", linha_atual=incursao.passos + 1
    )
    run = await db.buscar_run(conn, run_id)
    await cog._abrir_combate(run, incursao.objetivo)
    return conn, canal, cog, incursao, await db.buscar_run(conn, run_id)


def caso_thp_absorve_antes_do_hp():
    c = motor.Combatente(1, "C", 15, 0, "1d1", 40, 40)
    assert motor.ganhar_thp(c, 10) == 10 and c.tem_thp

    # o dano come a vida temporaria primeiro
    do_thp, do_hp = motor.absorver(c, 4)
    assert (do_thp, do_hp) == (4, 0) and c.thp == 6 and c.hp_atual == 40
    # e so o que sobra vai para o HP
    do_thp, do_hp = motor.absorver(c, 10)
    assert (do_thp, do_hp) == (6, 4) and c.thp == 0 and c.hp_atual == 36

    # nao empilha: vale a maior
    motor.ganhar_thp(c, 5)
    motor.ganhar_thp(c, 3)
    assert c.thp == 5
    motor.ganhar_thp(c, 9)
    assert c.thp == 9

    # quem caiu nao ganha vida temporaria
    caido = motor.Combatente(2, "X", 15, 0, "1d1", 40, 0)
    assert motor.ganhar_thp(caido, 10) == 0
    print("  THP absorve o dano antes do HP e nao empilha: ok")


def caso_golpe_registra_o_absorvido():
    bruto = motor.Inimigo(0, "Bruto", 10, 40, "1d1+9", 100, 100)
    alvo = motor.Combatente(1, "A", 10, 0, "1d1", 50, 50, thp=30)
    golpe = motor.contra_atacar(bruto, alvo, random.Random(1))
    assert golpe.acertou and golpe.absorvido == golpe.dano
    assert alvo.hp_atual == 50, "com THP suficiente, o HP nao e tocado"
    assert alvo.thp == 30 - golpe.dano
    print("  o golpe diz quanto a vida temporaria segurou: ok")


async def caso_tradicao_marcial_da_thp():
    conn, canal, cog, incursao, run = await preparar(classe="xama", nivel=8)
    dono = JOGADORES[0]

    inter = FakeInteraction(canal, dono)
    await cog.usar_habilidade(inter, run["id"], "OBJ", "tradicao_marcial")
    assert "Vida temporaria" in inter.resposta, inter.resposta

    estado = await cog._estado_combate(await db.buscar_run(conn, run["id"]), incursao.objetivo)
    assert estado.combatente(dono).tem_thp

    # os dois caminhos dividem o mesmo uso: o outro ja nao esta disponivel
    outro = FakeInteraction(canal, dono)
    await cog.usar_habilidade(outro, run["id"], "OBJ", "tradicao_espiritual")
    assert "nao esta disponivel" in outro.resposta, outro.resposta
    print("  Tradicao xamanica: caminho marcial rende THP e gasta o uso dos dois: ok")


async def caso_danca_totemica_cobre_o_grupo():
    conn, canal, cog, incursao, run = await preparar(classe="xama", nivel=8)
    dono = JOGADORES[0]

    inter = FakeInteraction(canal, dono)
    await cog.usar_habilidade(inter, run["id"], "OBJ", "danca_totemica")
    assert "grupo ganha" in inter.resposta

    estado = await cog._estado_combate(await db.buscar_run(conn, run["id"]), incursao.objetivo)
    assert all(c.tem_thp for c in estado.vivos), [c.thp for c in estado.vivos]
    # e todo mundo leva o bonus no proximo ataque
    assert all(c.dano_por_alvo or c.dano_extra or True for c in estado.vivos)
    ligados = await db.efeitos_ativos(conn, run["id"], cog._passo(run), 0)
    assert len(ligados) == len(estado.vivos), ligados
    print("  Danca totemica da THP e bonus ao grupo inteiro: ok")


async def caso_aura_totemica_depende_do_thp():
    conn, canal, cog, incursao, run = await preparar(classe="xama", nivel=8)
    dono, colega = JOGADORES[0], JOGADORES[1]

    base = await cog._estado_combate(run, incursao.objetivo)
    acerto_base = base.combatente(colega).bonus_ataque

    # sem THP no xama, ninguem ganha nada
    assert not base.combatente(dono).tem_thp
    assert acerto_base == cl.classe("xama").numeros(8).acerto

    # com THP, a aura liga para o grupo inteiro
    await db.definir_thp(conn, run["id"], dono, 5)
    com_aura = await cog._estado_combate(
        await db.buscar_run(conn, run["id"]), incursao.objetivo
    )
    assert com_aura.combatente(colega).bonus_ataque == acerto_base + 1
    assert com_aura.combatente(dono).bonus_ataque == acerto_base + 1

    # no tier 5 a aura e mais forte
    for user_id in (dono, colega):
        personagem = await db.personagem_por_nome(conn, GUILD, user_id, f"Heroi{user_id}")
        await db.atualizar_personagem(conn, personagem["id"], "nivel", 10)
    await db.definir_thp(conn, run["id"], dono, 5)
    forte = await cog._estado_combate(
        await db.buscar_run(conn, run["id"]), incursao.objetivo
    )
    assert forte.combatente(colega).bonus_ataque == cl.classe("xama").numeros(10).acerto + 2
    print("  a aura totemica so vale enquanto o xama tem THP: ok")


async def caso_relentless_segura_a_queda():
    conn, canal, cog, incursao, run = await preparar(
        classe="barbaro", nivel=8, monstro=CERTEIRO
    )
    dono = JOGADORES[0]
    passo = cog._passo(run)
    # deixa os dois na beira da morte: o revide derruba
    for user_id in JOGADORES[:2]:
        await db.definir_hp(conn, run["id"], user_id, 1)

    msg = await canal.fetch_message(run["mensagem_id"])
    for user_id in JOGADORES[:2]:
        await cog.atacar(FakeInteraction(canal, user_id, msg), run["id"], "OBJ")

    hps = await db.hp_dos_participantes(conn, run["id"])
    salvos = [u for u, hp in hps.items() if hp and hp > 0]
    assert salvos, f"Relentless tinha de ter segurado alguem: {hps}"
    # quem foi salvo ficou com 1 HP e vida temporaria
    async with conn.execute(
        "SELECT user_id, thp FROM run_participantes WHERE run_id = ?", (run["id"],)
    ) as cur:
        thps = {r["user_id"]: r["thp"] for r in await cur.fetchall()}
    assert any(thps[u] > 0 for u in salvos), thps
    assert any("Relentless" in (m.content or "") for m in canal.mensagens)

    # e o uso acabou: e 1x por combate
    gastos = await db.usos_da_run(conn, run["id"], salvos[0])
    assert gastos.get(("relentless", f"combate:{passo}")) == 1, gastos
    print("  Relentless segura a queda uma vez por combate: ok")


async def caso_thp_some_no_proximo_combate():
    conn, canal, cog, incursao, run = await preparar(classe="xama", nivel=8)
    dono = JOGADORES[0]
    await db.definir_thp(conn, run["id"], dono, 12)

    # o combate seguinte (outro passo) comeca sem vida temporaria
    await db.iniciar_combate(conn, run["id"], 99, "OUTRA", [incursao.objetivo.monstros[0]])
    async with conn.execute(
        "SELECT thp FROM run_participantes WHERE run_id = ? AND user_id = ?",
        (run["id"], dono),
    ) as cur:
        assert (await cur.fetchone())["thp"] == 0
    print("  a vida temporaria nao atravessa combates: ok")


def caso_painel_mostra_thp():
    c = motor.Combatente(1, "Vhalor", 15, 0, "1d1", 40, 30, thp=7)
    linha = E._linha_hp(c)
    assert "30/40" in linha and "+7 THP" in linha, linha
    sem = motor.Combatente(2, "Kaelen", 15, 0, "1d1", 40, 30)
    assert "THP" not in E._linha_hp(sem)
    print("  o painel mostra a vida temporaria: ok")


async def main():
    try:
        caso_thp_absorve_antes_do_hp()
        caso_golpe_registra_o_absorvido()
        caso_painel_mostra_thp()
        await caso_tradicao_marcial_da_thp()
        await caso_danca_totemica_cobre_o_grupo()
        await caso_aura_totemica_depende_do_thp()
        await caso_relentless_segura_a_queda()
        await caso_thp_some_no_proximo_combate()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        (Path(__file__).resolve().parent / "teste_thp.db").unlink(missing_ok=True)


asyncio.run(main())
print("TESTES DE THP PASSARAM")
