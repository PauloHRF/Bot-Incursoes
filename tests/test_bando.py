"""Mais de uma criatura por combate: alvo, HP separado e a vez dos inimigos."""
from __future__ import annotations

import asyncio
import random
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import config, database as db, motor  # noqa: E402
from src.cogs.incursao import Incursoes, ViewCombate  # noqa: E402
from src.incursoes import MAX_INIMIGOS, ErroDeValidacao, de_dict  # noqa: E402
from fakes import (  # noqa: E402
    CANAL,
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


def inimigos(quantos, hp=10, ca=10, ataque=0, dano="1d4"):
    return [
        motor.Inimigo(i, f"Lobo {i + 1}", ca, ataque, dano, hp, hp) for i in range(quantos)
    ]


def grupo(quantos=3, hp=20):
    return [
        motor.Combatente(100 + i, f"P{i}", 15, 5, "1d6", hp, hp) for i in range(quantos)
    ]


async def preparar(inimigos_objetivo=3, monstro=INDEFESO):
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass
    config.DB_PATH = Path(__file__).resolve().parent / "teste_bando.db"
    config.DB_PATH.unlink(missing_ok=True)
    config.TAMANHO_GRUPO = 5
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    await criar_grupo(conn)
    canal = FakeCanal(CANAL)
    cog = Incursoes(FakeBot(conn, canal))
    incursao, _ = montar_conteudo(
        cog,
        tamanho="Curta",
        monstro_objetivo=monstro,
        inimigos_objetivo=inimigos_objetivo,
        salas=salas_sem_combate(),
    )
    return conn, canal, cog, incursao


async def montar_run(conn, canal, cog, incursao_id="t"):
    await cog.entrar.callback(cog, FakeInteraction(canal, JOGADORES[0]), incursao_id)
    run = await db.run_do_canal(conn, CANAL)
    msg = await canal.fetch_message(run["mensagem_id"])
    for user_id in JOGADORES[1:]:
        await cog.recrutar(FakeInteraction(canal, user_id, msg), run["id"], "entrar")
    return await db.buscar_run(conn, run["id"])


async def ate_o_objetivo(conn, canal, cog, run, incursao):
    for passo in range(1, incursao.passos + 1):
        run = await db.buscar_run(conn, run["id"])
        alvo = (await cog._opcoes(run, passo))[0]
        msg = await canal.fetch_message(run["mensagem_id"])
        for user_id in JOGADORES:
            await cog.votar(FakeInteraction(canal, user_id, msg), run["id"], passo, alvo.id)
        atual = await db.buscar_run(conn, run["id"])
        if atual["status"] == "em_sala":
            msg_sala = await canal.fetch_message(atual["mensagem_id"])
            for user_id in JOGADORES:
                agora = await db.buscar_run(conn, run["id"])
                if agora["status"] != "em_sala":
                    break
                await cog.rolar(FakeInteraction(canal, user_id, msg_sala), run["id"], alvo.id)
    return await db.buscar_run(conn, run["id"])


def caso_estado_com_varios():
    """O combate só acaba quando o último inimigo cai."""
    estado = motor.EstadoCombate(inimigos(3), 1, grupo())
    assert len(estado.inimigos_vivos) == 3
    assert not estado.inimigos_derrotados and not estado.encerrado

    estado.inimigos[1].hp_atual = 0
    assert len(estado.inimigos_vivos) == 2
    assert not estado.inimigos_derrotados, "um caído não encerra o combate"

    # o alvo escolhido vale enquanto estiver de pé
    assert estado.alvo_preferido(2) is estado.inimigos[2]
    assert estado.alvo_preferido(1) is None, "não se bate em quem já caiu"
    assert estado.alvo_preferido(99) is None
    # sem escolha, cai no primeiro de pé — com um inimigo só ninguém precisa escolher
    assert estado.alvo_preferido() is estado.inimigos[0]

    for i in estado.inimigos:
        i.hp_atual = 0
    assert estado.inimigos_derrotados and estado.encerrado
    assert estado.alvo_preferido() is None
    print("  o combate só acaba quando o último inimigo cai: ok")


def caso_dano_vai_so_para_o_alvo():
    estado = motor.EstadoCombate(inimigos(3, hp=50), 1, grupo())
    atacante = estado.combatentes[0]
    atacante.bonus_ataque = 40  # acerta sempre, fora o 1 natural

    for _ in range(12):
        motor.atacar_inimigo(atacante, estado.inimigos[1], random.Random(7))
    assert estado.inimigos[0].hp_atual == 50, "o vizinho não pode tomar dano"
    assert estado.inimigos[2].hp_atual == 50
    assert estado.inimigos[1].hp_atual < 50
    print("  o dano cai só no alvo escolhido: ok")


def caso_vez_dos_inimigos():
    """Cada inimigo de pé bate uma vez por rodada — é isso que faz um bando pesar."""
    estado = motor.EstadoCombate(inimigos(4, ataque=40, dano="1d4"), 1, grupo(3, hp=200))
    golpes = motor.rodada_dos_inimigos(estado, random.Random(3))
    assert len(golpes) == 4, "quatro criaturas, quatro ataques"
    assert all(alvo in estado.combatentes for _, alvo in golpes)

    # quem já caiu não ataca
    estado.inimigos[0].hp_atual = 0
    estado.inimigos[3].hp_atual = 0
    assert len(motor.rodada_dos_inimigos(estado, random.Random(3))) == 2

    # e ninguém bate no grupo inteiro caído
    forte = motor.EstadoCombate(
        inimigos(5, ataque=40, dano="1d4+900"), 1, grupo(1, hp=5)
    )
    golpes = motor.rodada_dos_inimigos(forte, random.Random(1))
    assert forte.grupo_caido
    assert len(golpes) < 5, "para de bater quando não sobra ninguém de pé"
    print("  cada inimigo de pé revida uma vez: ok")


def caso_conteudo_com_quantidade():
    base = dict(
        id="x", nome="X", organizacao="Vórtice Oculto", lore_inicial="oi",
        recompensa_mes=10, tier=4,
    )
    sala = dict(
        id="OBJ", nome="Ninho", tipo="Combate", descricao="d",
        monstros=[
            dict(nome="Lobo", quantidade=3, ca=13, ataque=4, dano="1d6+2", hp=11),
            dict(nome="Alfa", ca=15, ataque=6, dano="2d6+3", hp=30),
        ],
    )
    inc = de_dict({**base, "objetivo": sala})
    nomes = [m.nome for m in inc.objetivo.monstros]
    assert nomes == ["Lobo 1", "Lobo 2", "Lobo 3", "Alfa"], nomes
    # com quantidade 1 o nome fica limpo, sem número
    assert inc.objetivo.monstro.nome == "Lobo 1"
    assert de_dict(inc.para_dict()).para_dict() == inc.para_dict()

    # o formato antigo (uma criatura em 'monstro') continua valendo
    legado = dict(id="OBJ", nome="Chefe", tipo="Combate", descricao="d",
                  monstro=dict(nome="M", ca=10, ataque=1, dano="1d6", hp=10))
    assert len(de_dict({**base, "objetivo": legado}).objetivo.monstros) == 1

    # e há um teto de criaturas por sala
    demais = dict(sala, monstros=[dict(nome="Rato", quantidade=4, ca=10, ataque=1,
                                       dano="1d4", hp=3)] * 2)
    try:
        de_dict({**base, "objetivo": demais})
    except ErroDeValidacao as exc:
        assert f"máximo é {MAX_INIMIGOS}" in str(exc), exc
    else:
        raise AssertionError("deveria recusar mais criaturas que o teto")
    print(f"  quantidade vira nomes numerados, com teto de {MAX_INIMIGOS}: ok")


async def caso_cada_inimigo_tem_o_proprio_hp():
    conn, canal, cog, incursao = await preparar(inimigos_objetivo=3)
    run = await montar_run(conn, canal, cog)
    run = await ate_o_objetivo(conn, canal, cog, run, incursao)
    assert run["status"] == "objetivo"

    estado = await cog._estado_combate(run, incursao.objetivo)
    assert len(estado.inimigos) == 3, [i.nome for i in estado.inimigos]
    assert [i.indice for i in estado.inimigos] == [0, 1, 2]
    assert all(i.hp_atual == i.hp_max for i in estado.inimigos)

    # o painel do combate lista as três
    painel = canal.mensagens[-1].embeds[0]
    campos = {f.name: f.value for f in painel.fields}
    rotulo = next(n for n in campos if "Inimigos" in n)
    assert "3 de pé de 3" in rotulo, rotulo
    for i in estado.inimigos:
        assert i.nome in campos[rotulo]

    # com mais de um de pé, o painel traz menu de alvo em vez de botão
    view = canal.mensagens[-1].view
    assert isinstance(view, ViewCombate)
    assert getattr(view, "menu", None) is not None, "esperava o menu de alvos"
    assert {o.value for o in view.menu.options} == {"0", "1", "2"}

    # derrubar um não encerra o combate
    # cada um ataca uma vez por rodada: um golpe so nao basta, o 1 natural erra
    msg = await canal.fetch_message(run["mensagem_id"])
    for _ in range(10):
        atual = await db.buscar_run(conn, run["id"])
        estado = await cog._estado_combate(atual, incursao.objetivo)
        if estado is None or estado.inimigos[0].caido or atual["status"] != "objetivo":
            break
        for c in list(estado.vivos):
            agora = await cog._estado_combate(
                await db.buscar_run(conn, run["id"]), incursao.objetivo
            )
            if agora is None or agora.inimigos[0].caido:
                break
            await cog.atacar(
                FakeInteraction(canal, c.user_id, msg), run["id"], "OBJ", 0
            )
    atual = await db.buscar_run(conn, run["id"])
    estado = await cog._estado_combate(atual, incursao.objetivo)
    assert estado.inimigos[0].caido, "o primeiro alvo deveria ter caído"
    assert atual["status"] == "objetivo", "a run não pode acabar com dois inimigos de pé"
    assert [i.hp_atual for i in estado.inimigos[1:]] == [1, 1], "os outros seguem inteiros"
    print("  cada criatura tem o próprio HP, e uma não encerra o combate: ok")


async def caso_alvo_caido_nao_gasta_o_turno():
    conn, canal, cog, incursao = await preparar(inimigos_objetivo=2)
    run = await montar_run(conn, canal, cog)
    run = await ate_o_objetivo(conn, canal, cog, run, incursao)
    passo = cog._passo(run)

    # derruba o inimigo 0 direto no banco, como se alguém já tivesse batido nele
    await db.definir_hp_inimigos(conn, run["id"], passo, {0: 0})

    msg = await canal.fetch_message(run["mensagem_id"])
    inter = FakeInteraction(canal, JOGADORES[0], msg)
    await cog.atacar(inter, run["id"], "OBJ", 0)
    assert "já caiu" in inter.resposta, inter.resposta
    assert await db.ataques_da_rodada(conn, run["id"], passo, 1) == [], "não gastou o turno"

    # e o menu de alvos já não oferece quem caiu
    estado = await cog._estado_combate(await db.buscar_run(conn, run["id"]), incursao.objetivo)
    view = ViewCombate(cog, run["id"], "OBJ", estado.inimigos)
    assert getattr(view, "menu", None) is None, "com um só de pé, volta o botão Atacar"
    print("  atacar quem já caiu não gasta o turno: ok")


async def caso_bando_inteiro_encerra_a_sala():
    """Com todos abatidos, a run segue e o desfecho fala no plural."""
    conn, canal, cog, incursao = await preparar(inimigos_objetivo=3)
    run = await montar_run(conn, canal, cog)
    run = await ate_o_objetivo(conn, canal, cog, run, incursao)

    msg = await canal.fetch_message(run["mensagem_id"])
    for _ in range(60):
        atual = await db.buscar_run(conn, run["id"])
        if atual["status"] != "objetivo":
            break
        estado = await cog._estado_combate(atual, incursao.objetivo)
        if estado is None:
            break
        alvo = estado.alvo_preferido()
        for c in list(estado.vivos):
            agora = await db.buscar_run(conn, run["id"])
            if agora["status"] != "objetivo":
                break
            atual_estado = await cog._estado_combate(agora, incursao.objetivo)
            vivo = atual_estado.alvo_preferido() if atual_estado else None
            if vivo is None:
                break
            await cog.atacar(
                FakeInteraction(canal, c.user_id, msg), run["id"], "OBJ", vivo.indice
            )

    run = await db.buscar_run(conn, run["id"])
    assert run["status"] == "sucesso", run["status"]
    inimigos_finais = await db.inimigos_do_combate(conn, run["id"], incursao.passos + 1)
    assert all(i["hp_atual"] == 0 for i in inimigos_finais), inimigos_finais

    # o desfecho fala no plural, em vez de citar um monstro só
    vitoria = next(
        m.embeds[0]
        for m in reversed(canal.mensagens)
        if m.embeds and "objetivo cumprido" in (m.embeds[0].title or "")
    )
    campos = " ".join(f.name for f in vitoria.fields)
    assert "3 inimigos foram derrotados" in campos, campos
    print("  abater o bando inteiro encerra a sala: ok")


async def main():
    try:
        caso_estado_com_varios()
        caso_dano_vai_so_para_o_alvo()
        caso_vez_dos_inimigos()
        caso_conteudo_com_quantidade()
        await caso_cada_inimigo_tem_o_proprio_hp()
        await caso_alvo_caido_nao_gasta_o_turno()
        await caso_bando_inteiro_encerra_a_sala()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        (Path(__file__).resolve().parent / "teste_bando.db").unlink(missing_ok=True)


asyncio.run(main())
print("TESTES DE BANDO PASSARAM")
