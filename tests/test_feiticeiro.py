"""O feiticeiro: mesmo corpo do mago, e o Metamagic que torce cada magia dele
— mais dano, mais alvos, save com desvantagem, ou lançar e atacar no mesmo
turno. Mais os Grilhões Planares, que são magia da casa."""
from __future__ import annotations

import asyncio
import random
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import classes as cl, config, database as db, motor  # noqa: E402
from src.cogs.incursao import Incursoes  # noqa: E402
from fakes import (  # noqa: E402
    leu,
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

SACO = {**INDEFESO, "hp": 500, "ataque": 1, "dano": "1d1"}
# Cai com qualquer magia: e com ele que se testa o FIM do combate.
VELA = {**INDEFESO, "hp": 1, "ataque": 1, "dano": "1d1"}


async def preparar(nivel=9, escolhas=None, quantos=3, monstros=2, monstro=None):
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass
    config.DB_PATH = Path(__file__).resolve().parent / "teste_feiticeiro.db"
    config.DB_PATH.unlink(missing_ok=True)
    config.TAMANHO_GRUPO = 5
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    await criar_grupo(conn, nivel=nivel, classe="feiticeiro")
    canal = FakeCanal(CANAL)
    cog = Incursoes(FakeBot(conn, canal))
    incursao, _ = montar_conteudo(
        cog, tamanho="Curta", salas=salas_sem_combate(),
        monstro_objetivo=monstro or SACO, inimigos_objetivo=monstros,
    )
    run_id = await db.criar_run(conn, GUILD, CANAL, incursao.id, JOGADORES[0])
    for user_id in JOGADORES[:quantos]:
        p = await db.personagem_por_nome(conn, GUILD, user_id, f"Heroi{user_id}")
        await db.adicionar_participante(conn, run_id, user_id, p["id"])
        for escolha, opcao in (escolhas or {}).items():
            await db.definir_escolha(conn, p["id"], escolha, opcao)
    await db.inicializar_hp(conn, run_id)
    await db.atualizar_run(
        conn, run_id, status="objetivo", sala_atual="OBJ",
        linha_atual=incursao.passos + 1,
    )
    run = await db.buscar_run(conn, run_id)
    await cog._abrir_combate(run, incursao.objetivo)
    return conn, canal, cog, incursao, await db.buscar_run(conn, run_id)


# ------------------------------------------------------------------- a tabela


def caso_mesmo_corpo_do_mago():
    """De propósito: o que separa os dois é o Metamagic, não a tabela."""
    feiticeiro, mago = cl.CLASSES["feiticeiro"], cl.CLASSES["mago"]
    for t in range(1, 6):
        meu, dele = feiticeiro.tiers[t], mago.tiers[t]
        assert (meu.hp, meu.ca, meu.dano) == (dele.hp, dele.ca, dele.dano), t
    assert feiticeiro.saves == ("DES", "CON")
    assert "Feiticeiro" not in cl.CLASSES_PENDENTES
    print("  tabela identica a do mago; o Metamagic e que separa: ok")


def caso_metamagia_nos_dois_tiers():
    feiticeiro = cl.CLASSES["feiticeiro"]
    for t, quantas in ((2, 3), (4, 4)):
        escolha = [h for h in feiticeiro.habilidades[t] if h.tipo == cl.ESCOLHA]
        assert len(escolha) == 1, t
        assert len(escolha[0].escolha["opcoes"]) == quantas, (t, len(escolha[0].escolha["opcoes"]))
        for o in escolha[0].escolha["opcoes"]:
            assert o["efeito"], (t, o["id"])
    print("  tres metamagias no T2 e quatro no T4, todas com efeito: ok")


# ------------------------------------------------------------- o Metamagic


def caso_desvantagem_existe_e_e_pior():
    rng = random.Random(1)
    n = 30000
    normal = sum(motor.rolar_d20(rng) for _ in range(n)) / n
    pior = sum(motor.rolar_d20(rng, desvantagem=True) for _ in range(n)) / n
    melhor = sum(motor.rolar_d20(rng, vantagem=True) for _ in range(n)) / n
    assert 6.8 < pior < 7.5, pior
    assert pior < normal < melhor
    # as duas juntas se anulam, como na mesa
    anuladas = sum(
        motor.rolar_d20(rng, vantagem=True, desvantagem=True) for _ in range(n)
    ) / n
    assert abs(anuladas - normal) < 0.2, (anuladas, normal)
    print(f"  desvantagem puxa o d20 de {normal:.1f} para {pior:.1f}: ok")


async def caso_empowered_soma_dado_na_magia():
    conn, canal, cog, incursao, run = await preparar(
        escolhas={"magia_feit_t1": "burning_hands", "metamagia_t2": "empowered"},
        monstros=1,
    )
    estado = await cog._estado_combate(run, incursao.objetivo)
    antes = estado.inimigos[0].hp_atual
    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.usar_habilidade(inter, run["id"], "OBJ", "burning_hands")
    estado = await cog._estado_combate(await db.buscar_run(conn, run["id"]),
                                       incursao.objetivo)
    levou = antes - estado.inimigos[0].hp_atual
    # 3d6 + 1d8 = 4 a 26; sem o Empowered seria 3 a 18. Na metade, 2 a 13.
    assert levou >= 2, levou
    assert cl.efeitos("feiticeiro", 9, {"metamagia_t2": "empowered"})["dano_magia"] == "1d8"
    print(f"  Empowered soma 1d8 no dano da magia ({levou} de dano): ok")


async def caso_twinned_pega_um_alvo_a_mais():
    conn, canal, cog, incursao, run = await preparar(
        escolhas={"magia_feit_t1": "chromatic_orb", "metamagia_t2": "twinned"},
        monstros=3,
    )
    estado = await cog._estado_combate(run, incursao.objetivo)
    antes = {i.indice: i.hp_atual for i in estado.inimigos}
    alvo = estado.inimigos[0].indice

    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.usar_habilidade(inter, run["id"], "OBJ", "chromatic_orb", [alvo])
    estado = await cog._estado_combate(await db.buscar_run(conn, run["id"]),
                                       incursao.objetivo)
    feridos = [i for i in estado.inimigos if i.hp_atual < antes[i.indice]]
    # magia de um alvo passou a pegar dois
    assert len(feridos) == 2, [(i.nome, i.hp_atual) for i in estado.inimigos]
    print("  Twinned faz a magia de um alvo pegar dois: ok")


async def caso_heightened_poe_desvantagem_no_save():
    conn, canal, cog, incursao, run = await preparar(
        escolhas={"magia_feit_t1": "burning_hands", "metamagia_t2": "heightened"},
        monstros=2,
    )
    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.usar_habilidade(inter, run["id"], "OBJ", "burning_hands")
    assert "desvantagem" in leu(inter), leu(inter)
    print("  Heightened mostra e aplica a desvantagem no save do inimigo: ok")


async def caso_quickened_deixa_o_turno_livre():
    """Lança e ainda ataca: no bot, cada um age uma vez por rodada."""
    conn, canal, cog, incursao, run = await preparar(
        escolhas={"magia_feit_t1": "chromatic_orb", "metamagia_t4": "quickened"},
        monstros=1,
    )
    estado = await cog._estado_combate(run, incursao.objetivo)
    alvo = estado.inimigos[0].indice
    antes = estado.inimigos[0].hp_atual

    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.usar_habilidade(inter, run["id"], "OBJ", "chromatic_orb", [alvo])
    # a magia resolveu na hora, e o turno nao foi gasto
    gasto = await db.acao_do_turno(
        conn, run["id"], cog._passo(run), estado.rodada, JOGADORES[0]
    )
    assert not gasto, f"o turno devia ficar livre, e veio {gasto}"
    # E o combate NAO foi encerrado: o alvo tem 500 de HP e segue de pe. A
    # magia rapida passou a reparar no fim do combate (ver
    # `caso_quickened_que_mata_o_ultimo_encerra_o_combate`), e encerrar sempre
    # em vez de so quando acaba seria pior que o bug de antes: pagaria a sala
    # e abriria a parada seguinte com inimigo vivo na mesa.
    assert (run["id"], cog._passo(run)) not in cog._encerrados, (
        "a magia rapida encerrou um combate que nao acabou"
    )
    assert (await db.buscar_run(conn, run["id"]))["status"] == "objetivo"
    # e ele ainda ataca na mesma rodada
    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.atacar(inter, run["id"], "OBJ", alvo)
    estado = await cog._estado_combate(await db.buscar_run(conn, run["id"]),
                                       incursao.objetivo)
    levou = antes - estado.inimigos[0].hp_atual
    # 4d8 da magia (4-32) mais o cantrip 4d10 (4-40): o total passa de 8
    assert levou >= 8, levou
    print(f"  Quickened: ele lanca E ataca no mesmo turno ({levou} de dano): ok")


async def caso_quickened_que_mata_o_ultimo_encerra_o_combate():
    """Matando o último inimigo com a magia rápida, o combate FECHA.

    A magia rápida resolve na hora, fora da vez — e por isso não passa por
    `_avancar`, que era o único lugar que reparava no fim do combate. Com o
    último inimigo caindo por ela, a run ficava em `objetivo` **sem inimigo
    vivo**: atacar respondia *"esse inimigo já caiu — escolha outro alvo"*, e
    não havia outro para escolher. A incursão não tinha saída, e sair dela
    pedia mexer no banco na mão.

    O caso irmão é `caso_quickened_deixa_o_turno_livre`, que garante a outra
    metade: quando o combate NÃO acaba, o turno continua livre para atacar.
    Fechar o combate cedo demais quebraria aquele, que é o motivo de a
    habilidade existir.
    """
    conn, canal, cog, incursao, run = await preparar(
        escolhas={"magia_feit_t1": "chromatic_orb", "metamagia_t4": "quickened"},
        monstros=1, monstro=VELA,
    )
    estado = await cog._estado_combate(run, incursao.objetivo)
    passo = cog._passo(run)
    alvo = estado.inimigos[0].indice

    await cog.usar_habilidade(
        FakeInteraction(canal, JOGADORES[0]), run["id"], "OBJ",
        "chromatic_orb", [alvo],
    )

    atual = await db.buscar_run(conn, run["id"])
    depois = await cog._estado_combate(atual, incursao.objetivo)
    assert depois is None or depois.encerrado, "o inimigo de 1 HP tinha de cair"
    assert atual["status"] != "objetivo", (
        f"a run ficou em `{atual['status']}` sem inimigo vivo: e o travamento"
    )
    assert atual["status"] == "sucesso", atual["status"]
    # E o fecho foi reivindicado: e ele que paga o ouro e segue a run.
    assert (run["id"], passo) in cog._encerrados, cog._encerrados

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  Quickened que mata o ultimo inimigo encerra o combate: ok")


def caso_o_fecho_do_combate_e_tomado_uma_vez():
    """Dois caminhos chegam ao fim do mesmo combate; só um o encerra.

    `_encerrar_combate` paga o ouro da sala e abre a parada seguinte, então
    rodar duas vezes pagaria duas vezes. A reivindicação é síncrona de
    propósito: sem `await` entre olhar e marcar, o loop de eventos não tem
    onde entrar.
    """
    cog = Incursoes.__new__(Incursoes)
    cog._encerrados = set()
    assert cog._tomar_o_fecho_do_combate(7, 3) is True
    assert cog._tomar_o_fecho_do_combate(7, 3) is False, "encerrou duas vezes"
    # Outra parada da mesma run e outro combate, e tem o fecho dela.
    assert cog._tomar_o_fecho_do_combate(7, 4) is True
    # E uma run nao tranca o combate da outra.
    assert cog._tomar_o_fecho_do_combate(8, 3) is True
    print("  o fecho de um combate e tomado uma vez so: ok")


# ------------------------------------------------------- Grilhoes Planares


async def caso_grilhoes_acorrenta_e_sangra():
    conn, canal, cog, incursao, run = await preparar(
        escolhas={"magia_feit_t3": "grilhoes_planares"}, monstros=1
    )
    estado = await cog._estado_combate(run, incursao.objetivo)
    alvo = estado.inimigos[0].indice
    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.usar_habilidade(inter, run["id"], "OBJ", "grilhoes_planares", [alvo])

    ligados = await db.efeitos_ativos(conn, run["id"], cog._passo(run), 0)
    correntes = [
        l for l in ligados
        if (l["valor"] or {}).get("dano_por_rodada") == "2d8"
    ]
    if not correntes:
        # Sem corrente so ha um jeito: o save passou. Grilhoes tem `metade`,
        # entao resistir nao e sair ileso — a criatura leva metade do 4d8, e
        # e ISSO que o galho prova. Metade do maximo e o teto: acima dele, o
        # `metade` nao entrou.
        #
        # Este galho quase nunca rodava, porque a criatura quase sempre
        # falhava. Com os saves dela escalando por tier passou a rodar, e o
        # que estava escrito aqui checava a palavra "resistiu" em
        # `leu(inter)` — que no duble guarda o TITULO do embed, nao o
        # corpo. Nunca teria pegado nada.
        estado_apos = await cog._estado_combate(
            await db.buscar_run(conn, run["id"]), incursao.objetivo
        )
        inimigo = estado_apos.inimigos[0]
        levou = inimigo.hp_max - inimigo.hp_atual
        teto = motor.maior_do_dado("4d8") // 2
        assert 0 < levou <= teto, (levou, teto)
        print(f"  Grilhoes: o alvo resistiu, levou {levou} (metade) e nao "
              f"foi acorrentado: ok")
        return
    assert "acorrentado" in leu(inter), leu(inter)

    # e a corrente sangra no virar da rodada
    run = await db.buscar_run(conn, run["id"])
    estado = await cog._estado_combate(run, incursao.objetivo)
    antes = estado.inimigos[0].hp_atual
    await cog._sangrar_acorrentados(run, estado)
    depois = estado.inimigos[0].hp_atual
    # Ou sangrou 2d8, ou arrebentou a corrente no save. Olhando so a
    # CORRENTE: `run_efeitos` guarda tambem a ameaca que o feiticeiro gerou
    # ao lancar a magia, que vale pelo combate e nao sai no escape.
    corrente_ainda = [
        l for l in await db.efeitos_ativos(conn, run["id"], cog._passo(run), 0)
        if (l["valor"] or {}).get("dano_por_rodada")
    ]
    assert depois < antes or not corrente_ainda, (antes, depois, corrente_ainda)
    print(f"  Grilhoes acorrenta e sangra 2d8 por rodada ({antes - depois}): ok")


def caso_a_corrente_tem_escape():
    """Sem posição, o escape é o save — senão seria dano garantido."""
    grilhoes = next(
        h
        for lista in cl.CLASSES["feiticeiro"].habilidades.values()
        for h in lista
        if h.id == "grilhoes_planares"
    )
    assert grilhoes.acao["dano_por_rodada"] == "2d8"
    assert grilhoes.acao["save"] == "DES", "e pelo save que ela escapa"
    assert grilhoes.acao["turnos"] == 3
    print("  a corrente guarda o atributo do save, que e a saida dela: ok")


# --------------------------------------------------------------- o T5


async def caso_polymorph_veste_um_aliado():
    """A forma do druida, emprestada a outro."""
    conn, canal, cog, incursao, run = await preparar(
        escolhas={"magia_feit_t5": "polymorph"}
    )
    aliado = JOGADORES[1]
    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.usar_habilidade(inter, run["id"], "OBJ", "polymorph", [aliado])
    estado = await cog._estado_combate(await db.buscar_run(conn, run["id"]),
                                       incursao.objetivo)
    fera = estado.combatente(aliado)
    assert fera.forma == "Fera", fera.forma
    assert fera.dano_arma == "3d10+5", fera.dano_arma
    assert fera.ca_extra == 2 and fera.thp == 15
    # e quem lancou NAO virou fera
    assert not estado.combatente(JOGADORES[0]).forma
    print("  Polymorph veste o aliado, nao quem lancou: ok")


async def caso_dimension_door_leva_dois():
    conn, canal, cog, incursao, run = await preparar(
        escolhas={"magia_feit_t5": "dimension_door"}
    )
    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.usar_habilidade(
        inter, run["id"], "OBJ", "dimension_door", [JOGADORES[1]]
    )
    estado = await cog._estado_combate(await db.buscar_run(conn, run["id"]),
                                       incursao.objetivo)
    fora = [c for c in estado.vivos if c.ameaca_fator == 0.0]
    assert len(fora) == 2, [c.nome for c in fora]
    # quem lancou vai sempre, e o aliado escolhido tambem
    assert {c.user_id for c in fora} == {JOGADORES[0], JOGADORES[1]}
    # e o terceiro continua na mira
    assert estado.combatente(JOGADORES[2]).ameaca_fator == 1.0
    print("  Dimension Door tira ele e um aliado da mira, e so os dois: ok")


async def main():
    try:
        caso_mesmo_corpo_do_mago()
        caso_metamagia_nos_dois_tiers()
        caso_desvantagem_existe_e_e_pior()
        await caso_empowered_soma_dado_na_magia()
        await caso_twinned_pega_um_alvo_a_mais()
        await caso_heightened_poe_desvantagem_no_save()
        await caso_quickened_deixa_o_turno_livre()
        await caso_quickened_que_mata_o_ultimo_encerra_o_combate()
        caso_o_fecho_do_combate_e_tomado_uma_vez()
        await caso_grilhoes_acorrenta_e_sangra()
        caso_a_corrente_tem_escape()
        await caso_polymorph_veste_um_aliado()
        await caso_dimension_door_leva_dois()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        (Path(__file__).resolve().parent / "teste_feiticeiro.db").unlink(missing_ok=True)


asyncio.run(main())
print("TESTES DO FEITICEIRO PASSARAM")
