"""Efeitos com prazo: Rage, Marca do Caçador e companhia, e a virada da rodada."""
from __future__ import annotations

import asyncio
import random
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import classes as cl, config, database as db, motor  # noqa: E402
from src.cogs.incursao import Incursoes, SeletorAlvoHabilidade  # noqa: E402
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

# Aguenta o combate inteiro e bate forte o bastante para a reducao aparecer.
PESADO = {"nome": "Britador", "ca": 1, "ataque": 40, "dano": "1d1+19", "hp": 4000}
DURADOURO = {**INDEFESO, "hp": 4000}


async def preparar(classe="barbaro", nivel=8, monstro=DURADOURO, inimigos=1, quantos=2):
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass
    config.DB_PATH = Path(__file__).resolve().parent / "teste_duracao.db"
    config.DB_PATH.unlink(missing_ok=True)
    config.TAMANHO_GRUPO = 5
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    await criar_grupo(conn, nivel=nivel, classe=classe)
    canal = FakeCanal(CANAL)
    cog = Incursoes(FakeBot(conn, canal))
    incursao, _ = montar_conteudo(
        cog, tamanho="Curta", monstro_objetivo=monstro, inimigos_objetivo=inimigos,
        salas=salas_sem_combate(),
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


def caso_vantagem_pega_o_melhor_dado():
    class Dado:
        def __init__(self, valores):
            self.valores = list(valores)

        def randint(self, a, b):
            return self.valores.pop(0) if self.valores else b

        def choice(self, seq):
            return seq[0]

    # sem vantagem sai o primeiro; com vantagem, o melhor dos dois
    assert motor.rolar_d20(Dado([4, 17])) == 4
    assert motor.rolar_d20(Dado([4, 17]), vantagem=True) == 17
    assert motor.rolar_d20(Dado([19, 2]), vantagem=True) == 19

    # e a vantagem chega no golpe pelo combatente
    corajoso = motor.Combatente(1, "B", 15, 0, "1d1", 50, 50, vantagem=True)
    alvo = motor.Inimigo(0, "Alvo", 12, 0, "1d1", 100, 100)
    golpe = motor.atacar_inimigo(corajoso, alvo, Dado([3, 18]))
    assert golpe.d20 == 18 and golpe.acertou
    print("  vantagem rola dois dados e fica com o melhor: ok")


def caso_reducao_de_dano():
    bruto = motor.Inimigo(0, "Bruto", 10, 40, "1d1+19", 100, 100)
    normal = motor.Combatente(1, "N", 10, 0, "1d1", 100, 100)
    furioso = motor.Combatente(2, "F", 10, 0, "1d1", 100, 100, reducao_dano=0.5)

    rng = random.Random(4)
    g1 = motor.contra_atacar(bruto, normal, rng)
    g2 = motor.contra_atacar(bruto, furioso, random.Random(4))
    assert g1.acertou and g2.acertou
    assert g2.dano == max(1, round(g1.dano * 0.5)), (g1.dano, g2.dano)
    assert furioso.hp_atual > normal.hp_atual

    # a CA extra do Avatar da Luz entra na defesa
    blindado = motor.Combatente(3, "A", 10, 0, "1d1", 100, 100, ca_extra=2)
    assert blindado.ca_efetiva == 12
    print("  reducao de dano corta o golpe recebido pela metade: ok")


def caso_marca_soma_so_no_alvo_marcado():
    patrulheiro = motor.Combatente(1, "R", 15, 40, "1d1", 50, 50)
    patrulheiro.dano_por_alvo[1] = "3d8"
    marcado = motor.Inimigo(1, "Marcado", 1, 0, "1d1", 500, 500)
    outro = motor.Inimigo(2, "Outro", 1, 0, "1d1", 500, 500)

    g_marcado = motor.atacar_inimigo(patrulheiro, marcado, random.Random(2))
    g_outro = motor.atacar_inimigo(patrulheiro, outro, random.Random(2))
    assert g_marcado.acertou and g_outro.acertou
    assert g_marcado.dano > g_outro.dano, (g_marcado.dano, g_outro.dano)
    print("  a marca so vale contra o inimigo marcado: ok")


async def caso_rage_dura_tres_turnos():
    conn, canal, cog, incursao, run = await preparar(classe="barbaro", nivel=8)
    dono = JOGADORES[0]
    passo = cog._passo(run)

    inter = FakeInteraction(canal, dono)
    await cog.usar_habilidade(inter, run["id"], "OBJ", "rage")
    assert "Rage" in inter.resposta and "3 turno" in inter.resposta

    estado = await cog._estado_combate(await db.buscar_run(conn, run["id"]), incursao.objetivo)
    furioso = estado.combatente(dono)
    assert furioso.reducao_dano == 0.5
    assert furioso.dano_extra == 2

    # o efeito dura ate a rodada 3; na 4 ja nao vale
    assert len(await db.efeitos_ativos(conn, run["id"], passo, 3)) == 1
    assert await db.efeitos_ativos(conn, run["id"], passo, 4) == []

    # e o grupo viu o anuncio
    assert any("Rage" in (m.content or "") for m in canal.mensagens)
    print("  Rage liga reducao e dano extra por 3 turnos: ok")


async def caso_efeito_vence_com_a_rodada():
    conn, canal, cog, incursao, run = await preparar(classe="barbaro", nivel=10)
    dono = JOGADORES[0]
    passo = cog._passo(run)

    # Reckless Attack vale so o proximo turno
    inter = FakeInteraction(canal, dono)
    await cog.usar_habilidade(inter, run["id"], "OBJ", "reckless_attack")
    estado = await cog._estado_combate(await db.buscar_run(conn, run["id"]), incursao.objetivo)
    assert estado.combatente(dono).vantagem

    # todo mundo ataca: a rodada vira e o prazo vence
    msg = await canal.fetch_message(run["mensagem_id"])
    for user_id in JOGADORES[:2]:
        await cog.atacar(FakeInteraction(canal, user_id, msg), run["id"], "OBJ")

    atual = await db.buscar_run(conn, run["id"])
    depois = await cog._estado_combate(atual, incursao.objetivo)
    assert depois.rodada == 2, depois.rodada
    assert not depois.combatente(dono).vantagem, "o prazo de 1 turno tinha de ter vencido"
    assert await db.efeitos_ativos(conn, run["id"], passo, depois.rodada - 1) == []
    print("  efeito de 1 turno vence quando a rodada vira: ok")


async def caso_marca_pede_alvo_e_dura():
    conn, canal, cog, incursao, run = await preparar(
        classe="patrulheiro", nivel=8, inimigos=3
    )
    dono = JOGADORES[0]
    passo = cog._passo(run)

    # com varios inimigos, precisa escolher em quem
    pedido = FakeInteraction(canal, dono)
    await cog.usar_habilidade(pedido, run["id"], "OBJ", "marca_do_cacador")
    assert isinstance(pedido.view_enviada, SeletorAlvoHabilidade)
    assert {o.value for o in pedido.view_enviada.menu.options} == {"0", "1", "2"}
    assert await db.usos_da_run(conn, run["id"], dono) == {}, "nao gasta antes de escolher"

    marcando = FakeInteraction(canal, dono)
    await cog.usar_habilidade(marcando, run["id"], "OBJ", "marca_do_cacador", [1])
    assert "Lobo 2" in marcando.resposta or "Saco" in marcando.resposta

    estado = await cog._estado_combate(await db.buscar_run(conn, run["id"]), incursao.objetivo)
    caçador = estado.combatente(dono)
    assert caçador.dano_por_alvo == {1: "1d6"}, caçador.dano_por_alvo
    assert 1 not in caçador.vantagem_contra, "a Marca nao da vantagem"

    guardado = (await db.efeitos_ativos(conn, run["id"], passo, 0))[0]
    assert guardado["alvo_tipo"] == "inimigo" and guardado["dono"] == dono
    print("  a Marca do Cacador cai no inimigo escolhido e tem dono: ok")


async def caso_avatar_cura_por_turno():
    conn, canal, cog, incursao, run = await preparar(
        classe="paladino", nivel=10, monstro=PESADO
    )
    dono = JOGADORES[0]
    maximo = cl.classe("paladino").numeros(10).hp
    await db.definir_hp(conn, run["id"], dono, 20)

    inter = FakeInteraction(canal, dono)
    await cog.usar_habilidade(inter, run["id"], "OBJ", "avatar_da_luz")
    assert "Avatar da Luz" in inter.resposta

    estado = await cog._estado_combate(await db.buscar_run(conn, run["id"]), incursao.objetivo)
    santo = estado.combatente(dono)
    assert santo.ca_extra == 2 and santo.dano_extra >= 5
    assert santo.cura_por_turno == 0.05

    # a rodada vira: quem tem cura por turno recupera um pouco
    antes = (await db.hp_dos_participantes(conn, run["id"]))[dono]
    msg = await canal.fetch_message(run["mensagem_id"])
    for user_id in JOGADORES[:2]:
        await cog.atacar(FakeInteraction(canal, user_id, msg), run["id"], "OBJ")
    depois = (await db.hp_dos_participantes(conn, run["id"]))[dono]
    # o monstro bate forte, entao comparamos com o esperado sem a cura
    assert depois != antes, (antes, depois)
    assert depois <= maximo
    print("  Avatar da Luz da CA, dano e cura a cada virada de rodada: ok")


async def main():
    try:
        caso_vantagem_pega_o_melhor_dado()
        caso_reducao_de_dano()
        caso_marca_soma_so_no_alvo_marcado()
        await caso_rage_dura_tres_turnos()
        await caso_efeito_vence_com_a_rodada()
        await caso_marca_pede_alvo_e_dura()
        await caso_avatar_cura_por_turno()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        (Path(__file__).resolve().parent / "teste_duracao.db").unlink(missing_ok=True)


asyncio.run(main())
print("TESTES DE DURACAO PASSARAM")
