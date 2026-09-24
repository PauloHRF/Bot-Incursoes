"""Habilidades ativas: usos por combate/descanso/incursão, cura e golpes extras."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import classes as cl, config, database as db, motor  # noqa: E402
from src.cogs.incursao import (  # noqa: E402
    Incursoes,
    SeletorAlvoHabilidade,
    SeletorHabilidade,
    ViewCombate,
)
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

# Um saco de pancada que aguenta o combate inteiro sem revidar.
DURADOURO = {**INDEFESO, "hp": 4000}


async def preparar(classe="guerreiro", nivel=8, monstro=DURADOURO, inimigos=1):
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass
    config.DB_PATH = Path(__file__).resolve().parent / "teste_ativas.db"
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
    return conn, canal, cog, incursao


async def abrir_combate(conn, canal, cog, incursao, quantos=2):
    """Coloca o grupo direto no objetivo, com o painel de combate aberto."""
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
    return await db.buscar_run(conn, run_id)


async def usar(cog, canal, run, user_id, habilidade_id, alvos=None, msg=None):
    inter = FakeInteraction(canal, user_id, msg)
    await cog.usar_habilidade(inter, run["id"], run["sala_atual"], habilidade_id, alvos)
    return inter


def caso_catalogo_das_ativas():
    """Toda ativa declara quando recarrega; as prontas declaram o que fazem."""
    prontas, futuras = [], []
    for classe in cl.CLASSES.values():
        for _t, h in classe.habilidades_ate(10):
            if h.tipo != cl.ATIVA:
                continue
            assert h.usos, f"{classe.nome}/{h.nome} sem frequencia de uso"
            assert h.escopo in ("combate", "descanso", "incursao"), h.escopo
            assert h.vezes >= 1
            (prontas if h.acionavel else futuras).append(h.id)

    assert "second_wind" in prontas and "cura_pelas_maos" in prontas
    assert "rage" in prontas and "marca_do_cacador" in prontas
    assert "uncanny_dodge" in prontas and "stunning_strike" in prontas
    # so sobram as que repetem um teste de pericia: dependem do fluxo da sala
    assert set(futuras) == {
        "sobrevivente_repeticao", "lider_sagrado_repeticao"
    }, futuras
    # toda acao tem um tipo que o cog sabe resolver
    for classe in cl.CLASSES.values():
        for _t, h in classe.habilidades_ate(10):
            if h.acionavel:
                assert h.acao["tipo"] in (
                    "cura", "golpes", "duracao", "grupo", "reacao"
                ), h.acao
    print(f"  {len(prontas)} ativas prontas, {len(futuras)} declaradas para depois: ok")


async def caso_cura_em_si_mesmo():
    conn, canal, cog, incursao = await preparar(classe="guerreiro", nivel=8)
    run = await abrir_combate(conn, canal, cog, incursao)
    dono = JOGADORES[0]

    # machuca antes, senao nao ha o que curar
    await db.definir_hp(conn, run["id"], dono, 10)
    inter = await usar(cog, canal, run, dono, "second_wind")
    assert "Second Wind" in inter.resposta and "recupera" in inter.resposta

    hp = (await db.hp_dos_participantes(conn, run["id"]))[dono]
    maximo = cl.classe("guerreiro").numeros(8).hp
    assert hp == 10 + int(maximo * 0.3), hp

    # o uso acabou: e 1x por combate
    de_novo = await usar(cog, canal, run, dono, "second_wind")
    assert "nao esta disponivel" in de_novo.resposta, de_novo.resposta
    print("  Second Wind cura e gasta o uso do combate: ok")


async def caso_uso_volta_no_proximo_combate():
    """O escopo 'combate' zera a cada sala, o 'descanso' so ao descansar."""
    conn, canal, cog, incursao = await preparar(classe="guerreiro", nivel=8)
    run = await abrir_combate(conn, canal, cog, incursao)
    dono = JOGADORES[0]
    passo = cog._passo(run)

    assert await db.gastar_uso(conn, run["id"], dono, "second_wind", f"combate:{passo}", 1)
    assert not await db.gastar_uso(
        conn, run["id"], dono, "second_wind", f"combate:{passo}", 1
    )
    # outra sala, outra chave: o uso volta
    assert await db.gastar_uso(
        conn, run["id"], dono, "second_wind", f"combate:{passo + 1}", 1
    )

    # descanso: a chave muda quando o grupo descansa
    assert await db.gastar_uso(conn, run["id"], dono, "flurry_of_blows", "descanso:0", 1)
    assert not await db.gastar_uso(
        conn, run["id"], dono, "flurry_of_blows", "descanso:0", 1
    )
    assert await db.contar_descanso(conn, run["id"]) == 1
    assert await db.gastar_uso(conn, run["id"], dono, "flurry_of_blows", "descanso:1", 1)
    print("  usos zeram por combate e por descanso: ok")


async def caso_habilidade_gasta_o_turno():
    """Na rodada, o personagem ou ataca ou usa uma habilidade — nunca os dois."""
    conn, canal, cog, incursao = await preparar(classe="guerreiro", nivel=8)
    run = await abrir_combate(conn, canal, cog, incursao)
    dono, outro = JOGADORES[0], JOGADORES[1]
    passo = cog._passo(run)
    msg = await canal.fetch_message(run["mensagem_id"])

    inter = await usar(cog, canal, run, dono, "action_surge", msg=msg)
    assert "Action Surge" in inter.resposta

    ataques = await db.ataques_da_rodada(conn, run["id"], passo, 1)
    assert len(ataques) == 1 and ataques[0]["origem"] == "habilidade"
    # o turno foi gasto na habilidade, entao o ataque e recusado
    assert await db.acao_do_turno(conn, run["id"], passo, 1, dono) == "action_surge"
    assert dono in await db.quem_agiu(conn, run["id"], passo, 1)

    ataque = FakeInteraction(canal, dono, msg)
    await cog.atacar(ataque, run["id"], "OBJ")
    assert "Action Surge" in ataque.resposta, ataque.resposta
    assert len(await db.ataques_da_rodada(conn, run["id"], passo, 1)) == 1

    # nem outra habilidade entra no mesmo turno
    outra = await usar(cog, canal, run, dono, "second_wind", msg=msg)
    assert "Action Surge" in outra.resposta, outra.resposta

    # e quem atacou gasta o turno do mesmo jeito
    normal = FakeInteraction(canal, outro, msg)
    await cog.atacar(normal, run["id"], "OBJ")
    assert await db.acao_do_turno(conn, run["id"], passo, 1, outro) == "ataque"
    print("  a rodada tem uma acao: ataque ou habilidade: ok")


async def caso_habilidade_sem_golpe_fecha_a_rodada():
    """Rage nao rola golpe nenhum — mas gasta o turno, e a rodada precisa virar."""
    conn, canal, cog, incursao = await preparar(classe="barbaro", nivel=8, inimigos=3)
    run = await abrir_combate(conn, canal, cog, incursao)
    dono, outro = JOGADORES[0], JOGADORES[1]
    passo = cog._passo(run)
    msg = await canal.fetch_message(run["mensagem_id"])

    await cog.atacar(FakeInteraction(canal, dono, msg), run["id"], "OBJ")
    estado = await cog._estado_combate(await db.buscar_run(conn, run["id"]), incursao.objetivo)
    assert estado.rodada == 1, "com dois de pe, um golpe nao fecha a rodada"

    # Rage e "duracao" com alvo proprio: nao pede alvo, mesmo com tres criaturas
    inter = await usar(cog, canal, run, outro, "rage", msg=msg)
    assert inter.view_enviada is None, "habilidade em si mesmo nao pergunta o alvo"
    assert "Rage" in inter.resposta, inter.resposta

    assert await db.acao_do_turno(conn, run["id"], passo, 1, outro) == "rage"
    assert await db.quem_agiu(conn, run["id"], passo, 1) == {dono, outro}

    depois = await cog._estado_combate(await db.buscar_run(conn, run["id"]), incursao.objetivo)
    assert depois.rodada == 2, "a rodada travou: a habilidade nao fechou o turno"
    print("  habilidade sem golpe tambem fecha a rodada: ok")


async def caso_perfect_strike_acerta_sempre():
    conn, canal, cog, incursao = await preparar(classe="monge", nivel=10)
    run = await abrir_combate(conn, canal, cog, incursao)
    dono = JOGADORES[0]
    passo = cog._passo(run)

    inter = await usar(cog, canal, run, dono, "perfect_strike")
    assert "CRITICO" in inter.resposta, inter.resposta
    golpe = (await db.ataques_da_rodada(conn, run["id"], passo, 1))[0]
    assert golpe["dano"] > 0, "um golpe garantido nunca sai sem dano"
    print("  Perfect Strike acerta e sai critico: ok")


async def caso_golpe_divino_soma_dados():
    """O +3d8 entra no dano, e o motor sabe aplicar sem o alvo mudar."""
    import random

    paladino = motor.Combatente(1, "P", 20, 40, "1d1", 50, 50)
    alvo = motor.Inimigo(0, "Alvo", 1, 0, "1d1", 500, 500)
    # a mesma semente nos dois: so o 3d8 difere, sem depender da sorte do d20
    simples = motor.atacar_inimigo(paladino, alvo, random.Random(7))
    divino = motor.atacar_inimigo(paladino, alvo, random.Random(7), dano_bonus="3d8")
    assert simples.acertou and divino.acertou
    assert simples.d20 == divino.d20
    assert divino.dano >= simples.dano + 3, (simples.dano, divino.dano)
    print("  Golpe Divino soma os dados extras: ok")


async def caso_cura_em_aliado_pede_alvo():
    conn, canal, cog, incursao = await preparar(classe="paladino", nivel=8)
    run = await abrir_combate(conn, canal, cog, incursao)
    curandeiro, ferido = JOGADORES[0], JOGADORES[1]
    await db.definir_hp(conn, run["id"], ferido, 5)

    # sem alvo, o bot abre o menu em vez de curar a esmo
    pedido = FakeInteraction(canal, curandeiro)
    await cog.usar_habilidade(pedido, run["id"], "OBJ", "cura_pelas_maos")
    assert isinstance(pedido.view_enviada, SeletorAlvoHabilidade)
    assert {o.value for o in pedido.view_enviada.menu.options} == {
        str(curandeiro), str(ferido)
    }
    # nada foi gasto ainda
    assert await db.usos_da_run(conn, run["id"], curandeiro) == {}

    inter = await usar(cog, canal, run, curandeiro, "cura_pelas_maos", [ferido])
    assert "recupera" in inter.resposta
    maximo = cl.classe("paladino").numeros(8).hp
    assert (await db.hp_dos_participantes(conn, run["id"]))[ferido] == 5 + int(maximo * 0.3)
    # e o grupo fica sabendo
    assert any("Cura pelas Maos" in (m.content or "") for m in canal.mensagens)
    print("  Cura pelas Maos pede o alvo e cura o aliado: ok")


async def caso_menu_so_mostra_o_que_da_para_usar():
    conn, canal, cog, incursao = await preparar(classe="guerreiro", nivel=8)
    run = await abrir_combate(conn, canal, cog, incursao)
    dono = JOGADORES[0]

    inter = FakeInteraction(canal, dono)
    await cog.abrir_habilidades(inter, run["id"], "OBJ")
    view = inter.view_enviada
    assert isinstance(view, SeletorHabilidade)
    ids = {o.value for o in view.menu.options}
    # Guerreiro nivel 8: Second Wind e Action Surge estao prontas
    assert ids == {"second_wind", "action_surge"}, ids
    # Fighting Style (escolha) e Improved Critical (passiva) nao entram
    assert "fighting_style" not in ids and "improved_critical" not in ids

    # usada a primeira, o menu nem abre: o turno acabou
    await usar(cog, canal, run, dono, "second_wind")
    fechado = FakeInteraction(canal, dono)
    await cog.abrir_habilidades(fechado, run["id"], "OBJ")
    assert fechado.view_enviada is None
    assert "Second Wind" in fechado.resposta, fechado.resposta

    # na rodada seguinte da para usar a outra
    await cog.atacar(FakeInteraction(canal, JOGADORES[1]), run["id"], "OBJ")
    await usar(cog, canal, run, dono, "action_surge")

    # gastos os dois usos, o menu some de vez
    await cog.atacar(FakeInteraction(canal, JOGADORES[1]), run["id"], "OBJ")
    vazio = FakeInteraction(canal, dono)
    await cog.abrir_habilidades(vazio, run["id"], "OBJ")
    assert vazio.view_enviada is None
    assert "nao tem habilidade" in vazio.resposta
    print("  o menu lista so as ativas prontas e com uso: ok")


async def caso_painel_tem_o_botao():
    conn, canal, cog, incursao = await preparar(classe="guerreiro", nivel=8)
    run = await abrir_combate(conn, canal, cog, incursao)
    view = canal.mensagens[-1].view
    assert isinstance(view, ViewCombate)
    rotulos = [getattr(i, "label", None) for i in view.children]
    assert "Atacar" in rotulos and "Habilidade" in rotulos, rotulos

    # com varios inimigos, o menu de alvo convive com o botao de habilidade
    conn, canal, cog, incursao = await preparar(inimigos=3)
    run = await abrir_combate(conn, canal, cog, incursao)
    view = canal.mensagens[-1].view
    assert any(getattr(i, "label", None) == "Habilidade" for i in view.children)
    assert getattr(view, "menu", None) is not None
    print("  o painel de combate traz o botao de habilidade: ok")


async def main():
    try:
        caso_catalogo_das_ativas()
        await caso_cura_em_si_mesmo()
        await caso_uso_volta_no_proximo_combate()
        await caso_habilidade_gasta_o_turno()
        await caso_habilidade_sem_golpe_fecha_a_rodada()
        await caso_perfect_strike_acerta_sempre()
        await caso_golpe_divino_soma_dados()
        await caso_cura_em_aliado_pede_alvo()
        await caso_menu_so_mostra_o_que_da_para_usar()
        await caso_painel_tem_o_botao()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        (Path(__file__).resolve().parent / "teste_ativas.db").unlink(missing_ok=True)


asyncio.run(main())
print("TESTES DE ATIVAS PASSARAM")
