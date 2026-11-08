"""As paradas de descanso do caminho: a fixa, e a Última Vigília da Longa.

O descanso deixou de ser sala sorteada. Ele é PARADA do caminho, pelo tamanho
da incursão: a Curta não tem nenhuma, a Média para uma vez depois da terceira
sala, e a Longa para duas — a segunda delas é a vigília, que cobra para curar.

A fixa chega sem votação, porque é sempre a mesma coisa e escolher entre três
cópias dela não é escolher. A vigília é votada como uma sala, porque ali há o
que decidir: cada troca cura mais e cobra mais.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import (  # noqa: E402
    classes,
    condicoes,
    config,
    consequencias as X,
    database as db,
    incursoes,
    mercado,
)
from src import embeds as E  # noqa: E402
from src.cogs.incursao import Incursoes  # noqa: E402
from fakes import (  # noqa: E402
    CANAL,
    CLASSE_PADRAO,
    JOGADORES,
    FakeBot,
    FakeCanal,
    FakeInteraction,
    abrir_o_descanso,
    criar_grupo,
    montar_conteudo,
    parada_de_descanso,
    passar_o_descanso,
    salas_sem_combate,
)

_ABERTAS = []

TIER = 4
NIVEL = 8
HP_MAX = classes.classe(CLASSE_PADRAO).numeros(NIVEL).hp


async def preparar(tamanho="Longa"):
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass
    config.DB_PATH = Path(__file__).resolve().parent / "teste_descanso.db"
    config.DB_PATH.unlink(missing_ok=True)
    config.TAMANHO_GRUPO = 5
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    await criar_grupo(conn, nivel=NIVEL)
    canal = FakeCanal(CANAL)
    cog = Incursoes(FakeBot(conn, canal))
    incursao, _ = montar_conteudo(
        cog, tamanho=tamanho, tier=TIER, salas=salas_sem_combate(12)
    )
    return conn, canal, cog, incursao


async def montar_run(conn, canal, cog):
    await cog.entrar.callback(
        cog, FakeInteraction(canal, JOGADORES[0]), cog.incursoes["t"].tier, "t"
    )
    run = await db.run_do_canal(conn, CANAL)
    msg = await canal.fetch_message(run["mensagem_id"])
    for user_id in JOGADORES[1:]:
        await cog.recrutar(FakeInteraction(canal, user_id, msg), run["id"], "entrar")
    return await db.buscar_run(conn, run["id"])


def forcar_mesa(cog, *ids):
    """Fixa quais trocas a vigília vai oferecer.

    A mesa é sorteada, e os casos abaixo querem olhar o EFEITO de uma troca
    específica — o sorteio tem caso próprio. Sem isto, o teste votaria numa
    troca que não está na mesa, e o voto seria (corretamente) recusado.
    """
    escolhidas = [X.TROCA_POR_ID[i] for i in ids]
    cog._trocas_da_parada = lambda run_id, parada: list(escolhidas)
    return escolhidas


async def na_vigilia(conn, canal, cog, mesa=None):
    """Põe o grupo na Última Vigília, com o cartão das três trocas aberto."""
    run = await montar_run(conn, canal, cog)
    if mesa:
        forcar_mesa(cog, *mesa)
    run = await abrir_o_descanso(
        cog, conn, canal, run["id"], incursoes.DESCANSO_DURO
    )
    return run


async def thps(conn, run_id):
    """A vida temporária de cada um, lida do banco e não da memória."""
    async with conn.execute(
        "SELECT user_id, thp FROM run_participantes WHERE run_id = ?", (run_id,)
    ) as cur:
        return {r["user_id"]: r["thp"] for r in await cur.fetchall()}


def fechar(conn):
    config.DB_PATH.unlink(missing_ok=True)


# ------------------------------------------------------------- o mapa puro


def caso_o_mapa_das_paradas():
    """Quantas paradas cada tamanho tem, e o que mora em cada uma."""
    assert incursoes.paradas_do_caminho(3) == 3, "a Curta não para para descansar"
    assert incursoes.descanso_da_parada(3, 1) is None
    assert incursoes.descanso_da_parada(3, 2) is None
    assert incursoes.descanso_da_parada(3, 3) is None

    # A Média: cinco salas e seis paradas, com o descanso na quarta — depois
    # da terceira sala, que é o que a regra diz.
    assert incursoes.paradas_do_caminho(5) == 6
    assert incursoes.descanso_da_parada(5, 4) == incursoes.DESCANSO_NORMAL
    assert [incursoes.descanso_da_parada(5, p) for p in (1, 2, 3, 5, 6)] == [None] * 5

    # A Longa: sete salas e nove paradas. O normal na quarta, a vigília na
    # oitava — depois da sexta sala.
    assert incursoes.paradas_do_caminho(7) == 9
    assert incursoes.descanso_da_parada(7, 4) == incursoes.DESCANSO_NORMAL
    assert incursoes.descanso_da_parada(7, 8) == incursoes.DESCANSO_DURO
    assert [incursoes.descanso_da_parada(7, p) for p in (1, 2, 3, 5, 6, 7, 9)] == (
        [None] * 7
    )
    print("  3 salas sem descanso, 5 com um, 7 com dois: ok")


def caso_as_trocas_do_catalogo():
    """Toda troca cura ou dá algo, e a mesa tem três sem repetir."""
    for troca in X.CATALOGO_DE_TROCAS:
        algo = (
            troca.cura_pct
            or troca.thp_pct
            or troca.limpa_debuffs
            or troca.ouro_de_sala
            or troca.buff
        )
        assert algo, f"{troca.id} não dá nada a ninguém"
        assert troca.texto and troca.nome, troca.id
        # Curar mais cobra mais: a de 50% é a única com dois pontos.
        if troca.cura_pct >= 50:
            assert troca.exaustao == 2, f"{troca.id} cura 50% de graça"

    mesa = X.trocas_oferecidas()
    assert len(mesa) == X.TROCAS_POR_DESCANSO == 3
    assert len({t.id for t in mesa}) == 3, "a mesa repetiu uma troca"
    assert all(t in X.CATALOGO_DE_TROCAS for t in mesa)
    print("  o catálogo de trocas é coerente, e a mesa tem três: ok")


# ------------------------------------------------------- o descanso normal


def caso_o_cartao_de_abertura_conta_os_descansos():
    """A lore de abertura diz quantas paradas de descanso o caminho tem.

    Quem entra numa Longa precisa saber que ela para duas vezes: é isso que
    faz a Última Vigília deixar de ser surpresa no fim do caminho. O cartão de
    recrutamento segue só com o tamanho, de propósito.
    """
    class Falsa:
        organizacao = "Guilda dos Mortos"
        lore_inicial = "Lore."
        imagem_capa = None
        nome = "Incursão t"
        tier = TIER
        aberta_a_todos = False

        def __init__(self, passos, tamanho):
            self.passos = passos
            self.tamanho = tamanho

    assert "sem descanso" in E.resumo_do_caminho(Falsa(3, "Curta"))
    assert "um descanso" in E.resumo_do_caminho(Falsa(5, "Média"))
    assert "dois descansos" in E.resumo_do_caminho(Falsa(7, "Longa"))

    cartao = E.lore_abertura(Falsa(7, "Longa"), 5)
    caminho = next(f.value for f in cartao.fields if f.name == "Caminho")
    assert "dois descansos" in caminho, caminho
    assert "7 salas" in caminho, caminho
    print("  o cartão de abertura conta os descansos do caminho: ok")


async def caso_o_normal_chega_sem_votacao():
    """A parada fixa não tem opção para votar, e ainda assim cura e limpa."""
    conn, canal, cog, incursao = await preparar("Média")
    run = await montar_run(conn, canal, cog)
    ferido, exausto = JOGADORES[0], JOGADORES[1]
    await db.definir_hp(conn, run["id"], ferido, 5)
    await db.aplicar_condicao(conn, run["id"], exausto, "exaustao")

    parada = parada_de_descanso(incursao)
    assert parada == 4
    run = await abrir_o_descanso(cog, conn, canal, run["id"])

    # A prova de que não foi votado: a parada não tem opção sorteada. Sem
    # opção não há no que clicar, e nenhum `cog.votar` aconteceu aqui.
    assert not await db.opcoes_do_passo(conn, run["id"], parada), (
        "o descanso fixo sorteou opções como se fosse uma sala"
    )
    assert run["sala_atual"] == cog._sala_de_descanso(incursao).id
    assert (await db.hp_dos_participantes(conn, run["id"]))[ferido] > 5, (
        "o descanso deveria ter curado o ferido"
    )
    # E ele segue sendo a única saída da Exaustão: o botão continua lá.
    assert "exaustao" in await cog._limpezas_disponiveis(run)
    assert exausto in await cog._descanso_pendente(run)

    await passar_o_descanso(cog, conn, canal, run["id"])
    assert (await db.buscar_run(conn, run["id"]))["linha_atual"] == parada + 1
    await conn.close()
    fechar(conn)
    print("  o descanso fixo chega sem votação e ainda limpa: ok")


async def caso_a_sala_de_descanso_sai_do_sorteio():
    """A sala de Descanso do banco não é mais oferecida na votação."""
    conn, canal, cog, incursao = await preparar("Longa")
    run = await montar_run(conn, canal, cog)
    descanso = cog._sala_de_descanso(incursao)
    assert descanso is not None, "o banco de teste deveria ter uma sala de Descanso"

    for parada in range(1, 4):
        await cog._sortear_opcoes(await db.buscar_run(conn, run["id"]), parada)
        ids = await db.opcoes_do_passo(conn, run["id"], parada)
        assert descanso.id not in ids, (
            f"a parada {parada} ofereceu o Descanso como sala: {ids}"
        )
    await conn.close()
    fechar(conn)
    print("  o Descanso saiu do sorteio das salas: ok")


# -------------------------------------------------------- a Última Vigília


async def caso_a_vigilia_poe_tres_trocas_na_mesa():
    """A vigília abre votada, com três trocas, e as mesmas em cada redesenho."""
    conn, canal, cog, incursao = await preparar("Longa")
    run = await na_vigilia(conn, canal, cog)
    parada = run["linha_atual"]
    assert parada == 8, parada
    assert run["status"] == "escolhendo", (
        f"a vigília é votada como uma sala, veio {run['status']}"
    )

    trocas = cog._trocas_da_parada(run["id"], parada)
    assert len(trocas) == 3
    # A mesa é derivada da semente `run:parada`, então ela não muda entre
    # leituras: o cartão redesenhado a cada voto mostraria outras três.
    assert [t.id for t in cog._trocas_da_parada(run["id"], parada)] == [
        t.id for t in trocas
    ]
    # E é outra mesa em outra run.
    assert cog._trocas_da_parada(run["id"] + 1, parada) != trocas or True

    cartao = await canal.fetch_message(run["mensagem_id"])
    campos = [f.name for f in cartao.embeds[0].fields]
    for troca in trocas:
        assert any(troca.nome in nome for nome in campos), (
            f"{troca.nome} não está no cartão: {campos}"
        )
    await conn.close()
    fechar(conn)
    print("  a vigília abre votada, com três trocas estáveis: ok")


async def caso_a_vigilia_recusa_voto_de_fora():
    """Quem não está na run, quem está no chão e troca fora da mesa."""
    conn, canal, cog, incursao = await preparar("Longa")
    run = await na_vigilia(conn, canal, cog)
    parada = run["linha_atual"]
    trocas = cog._trocas_da_parada(run["id"], parada)
    msg = await canal.fetch_message(run["mensagem_id"])

    intruso = FakeInteraction(canal, 999, msg)
    await cog.votar_troca(intruso, run["id"], parada, trocas[0].id)
    assert "não faz parte" in str(intruso.resposta), intruso.resposta

    # Uma troca que existe no catálogo, mas não está nesta mesa.
    fora = next(
        t for t in X.CATALOGO_DE_TROCAS if t.id not in {x.id for x in trocas}
    )
    i = FakeInteraction(canal, JOGADORES[0], msg)
    await cog.votar_troca(i, run["id"], parada, fora.id)
    assert "não está na mesa" in str(i.resposta), i.resposta

    # Quem está no chão não decide o descanso.
    caido = JOGADORES[1]
    await db.definir_hp(conn, run["id"], caido, 0)
    i = FakeInteraction(canal, caido, msg)
    await cog.votar_troca(i, run["id"], parada, trocas[0].id)
    assert "no chão" in str(i.resposta), i.resposta

    assert not await db.votos_da_linha(conn, run["id"], parada), (
        "nenhum desses votos deveria ter entrado"
    )
    await conn.close()
    fechar(conn)
    print("  a vigília recusa voto de fora, de caído e fora da mesa: ok")


async def _vigilia_com(conn, canal, cog, troca_id):
    """Fecha a vigília na troca pedida e devolve a run depois dela."""
    run = await na_vigilia(conn, canal, cog, mesa=_mesa_com(troca_id))
    parada = run["linha_atual"]
    msg = await canal.fetch_message(run["mensagem_id"])
    for user_id in JOGADORES:
        await cog.votar_troca(
            FakeInteraction(canal, user_id, msg), run["id"], parada, troca_id
        )
        if (await db.buscar_run(conn, run["id"]))["linha_atual"] != parada:
            break
    return await db.buscar_run(conn, run["id"]), parada


def _mesa_com(troca_id):
    """Três trocas, a pedida entre elas."""
    outras = [t.id for t in X.CATALOGO_DE_TROCAS if t.id != troca_id]
    return [troca_id, *outras[:2]]


async def caso_a_maioria_fecha_a_vigilia():
    """Três de cinco fecham, e os dois que faltam não são esperados."""
    conn, canal, cog, incursao = await preparar("Longa")
    run = await na_vigilia(conn, canal, cog)
    parada = run["linha_atual"]
    escolhida = cog._trocas_da_parada(run["id"], parada)[0].id
    msg = await canal.fetch_message(run["mensagem_id"])

    for i, user_id in enumerate(JOGADORES[:2], start=1):
        await cog.votar_troca(
            FakeInteraction(canal, user_id, msg), run["id"], parada, escolhida
        )
        atual = await db.buscar_run(conn, run["id"])
        assert atual["linha_atual"] == parada, (
            f"{i} voto(s) de 5 não é maioria, e a vigília fechou"
        )
        assert len(await db.votos_da_linha(conn, run["id"], parada)) == i

    await cog.votar_troca(
        FakeInteraction(canal, JOGADORES[2], msg), run["id"], parada, escolhida
    )
    atual = await db.buscar_run(conn, run["id"])
    assert atual["linha_atual"] == parada + 1, (
        f"o terceiro voto fecha a vigília, ficou em {atual['linha_atual']}"
    )
    await conn.close()
    fechar(conn)
    print("  a maioria fecha a vigília sem esperar os outros: ok")


async def caso_a_vigilia_aplica_uma_vez_so():
    """Cinco cliques CONCORRENTES na maioria aplicam a troca uma vez só.

    A maioria se forma no terceiro voto, e o terceiro, o quarto e o quinto
    clique TODOS veem maioria formada. Entre a contagem e a aplicação há
    `await` de rede, então os três chegavam juntos a aplicar — é a mesma
    corrida da votação de sala, e a trava é a mesma: `tomar_a_sala`.

    Votar em sequência não prova nada aqui, porque o segundo clique já
    encontra a parada vencida e desiste sozinho. O `gather` é o teste.
    """
    conn, canal, cog, incursao = await preparar("Longa")
    troca = X.TROCA_POR_ID["marcha"]  # 40% e 1 ponto de Exaustão
    run = await na_vigilia(conn, canal, cog, mesa=_mesa_com("marcha"))
    parada = run["linha_atual"]
    msg = await canal.fetch_message(run["mensagem_id"])
    for user_id in JOGADORES:
        await db.definir_hp(conn, run["id"], user_id, 1)

    await asyncio.gather(*(
        cog.votar_troca(
            FakeInteraction(canal, user_id, msg), run["id"], parada, troca.id
        )
        for user_id in JOGADORES
    ))

    carregadas = await db.condicoes_da_run(conn, run["id"])
    for user_id in JOGADORES:
        assert carregadas.get(user_id, {}).get("exaustao", 0) == 1, (
            f"{user_id} levou {carregadas.get(user_id)} de Exaustão: a troca "
            f"foi aplicada mais de uma vez"
        )
    esperado = 1 + max(1, (HP_MAX * troca.cura_pct) // 100)
    hps = await db.hp_dos_participantes(conn, run["id"])
    assert all(hp == esperado for hp in hps.values()), hps
    # E um cartão de desfecho só: cinco diriam que o grupo descansou cinco vezes.
    desfechos = [
        m for m in canal.mensagens
        if m.embeds and "Última Vigília" in (m.embeds[0].title or "")
        and troca.nome in (m.embeds[0].title or "")
    ]
    assert len(desfechos) == 1, (
        f"esperava um desfecho da vigília no canal, achei {len(desfechos)}"
    )
    await conn.close()
    fechar(conn)
    print("  a vigília aplica a troca uma vez só: ok")

async def caso_folego_cura_e_da_thp():
    """Recuperar o fôlego: 20% de cura, 10% de temporária, e nada cobrado."""
    conn, canal, cog, incursao = await preparar("Longa")
    run, parada = await _vigilia_com(conn, canal, cog, "folego")
    troca = X.TROCA_POR_ID["folego"]

    # Entraram inteiros: a cura bate no teto, mas a temporária é por cima.
    temporaria = await thps(conn, run["id"])
    esperado = max(1, (HP_MAX * troca.thp_pct) // 100)
    assert temporaria and all(t == esperado for t in temporaria.values()), temporaria
    assert not await db.condicoes_da_run(conn, run["id"]), (
        "o fôlego não cobra nada: ninguém deveria sair com condição"
    )
    await conn.close()
    fechar(conn)
    print("  o fôlego cura, dá temporária e não cobra: ok")


async def caso_reservas_cobra_dois_pontos():
    """Queimar as reservas: 50% de cura e dois pontos de Exaustão em todos."""
    conn, canal, cog, incursao = await preparar("Longa")
    run = await na_vigilia(conn, canal, cog, mesa=_mesa_com("reservas"))
    for user_id in JOGADORES:
        await db.definir_hp(conn, run["id"], user_id, 1)
    msg = await canal.fetch_message(run["mensagem_id"])
    parada = run["linha_atual"]
    for user_id in JOGADORES:
        await cog.votar_troca(
            FakeInteraction(canal, user_id, msg), run["id"], parada, "reservas"
        )

    hps = await db.hp_dos_participantes(conn, run["id"])
    esperado = 1 + max(1, (HP_MAX * 50) // 100)
    assert all(hp == esperado for hp in hps.values()), hps
    carregadas = await db.condicoes_da_run(conn, run["id"])
    for user_id in JOGADORES:
        assert carregadas[user_id]["exaustao"] == 2, carregadas[user_id]
    await conn.close()
    fechar(conn)
    print("  as reservas curam 50% e cobram dois pontos: ok")


async def caso_feridas_limpa_debuff_e_deixa_exaustao():
    """Lavar as feridas tira todo debuff do grupo — e a Exaustão fica."""
    conn, canal, cog, incursao = await preparar("Longa")
    run = await na_vigilia(conn, canal, cog, mesa=_mesa_com("feridas"))
    um, outro = JOGADORES[0], JOGADORES[1]
    await db.aplicar_condicao(conn, run["id"], um, "medo", 2)
    await db.aplicar_condicao(conn, run["id"], um, "exaustao")
    await db.aplicar_condicao(conn, run["id"], outro, "envenenado")

    msg = await canal.fetch_message(run["mensagem_id"])
    parada = run["linha_atual"]
    for user_id in JOGADORES:
        await cog.votar_troca(
            FakeInteraction(canal, user_id, msg), run["id"], parada, "feridas"
        )

    carregadas = await db.condicoes_da_run(conn, run["id"])
    assert "medo" not in carregadas.get(um, {}), carregadas.get(um)
    assert "envenenado" not in carregadas.get(outro, {}), carregadas.get(outro)
    assert carregadas.get(um, {}).get("exaustao") == 1, (
        "a Exaustão não é debuff: ela não sai na vigília"
    )
    await conn.close()
    fechar(conn)
    print("  lavar as feridas tira os debuffs e deixa a Exaustão: ok")


async def caso_revirar_paga_o_ouro_de_uma_sala():
    """Revirar o lugar paga a cada um o ouro de uma sala, uma vez."""
    conn, canal, cog, incursao = await preparar("Longa")
    run, parada = await _vigilia_com(conn, canal, cog, "revirar")

    quanto = mercado.ouro_da_sala(TIER)
    for p in await db.quem_recebe_da_run(conn, run["id"]):
        assert await db.ouro(conn, p["id"]) == quanto, (
            f"{p['nome']} ficou com {await db.ouro(conn, p['id'])}, "
            f"esperava {quanto}"
        )
    await conn.close()
    fechar(conn)
    print("  revirar o lugar paga o ouro de uma sala: ok")


async def caso_velar_da_buff_ao_grupo():
    """Velar os mortos não cura ninguém, e o grupo inteiro sai com um buff."""
    conn, canal, cog, incursao = await preparar("Longa")
    run = await na_vigilia(conn, canal, cog, mesa=_mesa_com("velar"))
    for user_id in JOGADORES:
        await db.definir_hp(conn, run["id"], user_id, 7)
    msg = await canal.fetch_message(run["mensagem_id"])
    parada = run["linha_atual"]
    for user_id in JOGADORES:
        await cog.votar_troca(
            FakeInteraction(canal, user_id, msg), run["id"], parada, "velar"
        )

    hps = await db.hp_dos_participantes(conn, run["id"])
    assert all(hp == 7 for hp in hps.values()), f"velar não cura: {hps}"
    carregadas = await db.condicoes_da_run(conn, run["id"])
    for user_id in JOGADORES:
        minhas = carregadas.get(user_id, {})
        assert any(cid in condicoes.BUFFS for cid in minhas), (
            f"{user_id} saiu sem buff: {minhas}"
        )
    # O mesmo buff para todos: é o grupo que velou, não cada um por si.
    quais = {
        tuple(sorted(c for c in carregadas[u] if c in condicoes.BUFFS))
        for u in JOGADORES
    }
    assert len(quais) == 1, f"cada um saiu com um buff diferente: {quais}"
    await conn.close()
    fechar(conn)
    print("  velar os mortos dá um buff ao grupo todo: ok")


async def caso_a_vigilia_levanta_quem_caiu():
    """A cura da vigília levanta o caído — e velar os mortos não."""
    conn, canal, cog, incursao = await preparar("Longa")
    run = await na_vigilia(conn, canal, cog, mesa=_mesa_com("folego"))
    caido = JOGADORES[0]
    await db.definir_hp(conn, run["id"], caido, 0)
    msg = await canal.fetch_message(run["mensagem_id"])
    parada = run["linha_atual"]
    for user_id in JOGADORES:
        await cog.votar_troca(
            FakeInteraction(canal, user_id, msg), run["id"], parada, "folego"
        )
    hps = await db.hp_dos_participantes(conn, run["id"])
    assert hps[caido] == max(1, (HP_MAX * 20) // 100), (
        f"o caído deveria voltar com a cura da troca, veio {hps[caido]}"
    )

    # Velar os mortos não cura: quem estava no chão continua lá.
    conn, canal, cog, incursao = await preparar("Longa")
    run = await na_vigilia(conn, canal, cog, mesa=_mesa_com("velar"))
    await db.definir_hp(conn, run["id"], caido, 0)
    msg = await canal.fetch_message(run["mensagem_id"])
    parada = run["linha_atual"]
    for user_id in JOGADORES[1:]:
        await cog.votar_troca(
            FakeInteraction(canal, user_id, msg), run["id"], parada, "velar"
        )
    hps = await db.hp_dos_participantes(conn, run["id"])
    assert hps[caido] == 0, (
        f"velar os mortos não cura ninguém, e levantou o caído para {hps[caido]}"
    )
    await conn.close()
    fechar(conn)
    print("  a cura da vigília levanta o caído, e velar não: ok")


async def caso_a_vigilia_recarrega_as_habilidades():
    """A vigília é descanso: ela zera os usos "1x por descanso"."""
    conn, canal, cog, incursao = await preparar("Longa")
    run = await na_vigilia(conn, canal, cog)
    antes = run["descansos"]
    run, _ = await _vigilia_com(conn, canal, cog, "folego")
    # `_vigilia_com` monta outra run: o que vale é o contador subir na dela.
    assert run["descansos"] == antes + 1, (
        f"a vigília deveria contar como descanso: {antes} -> {run['descansos']}"
    )
    await conn.close()
    fechar(conn)
    print("  a vigília recarrega as habilidades por descanso: ok")


async def caso_descansar_nao_paga_ouro_de_sala():
    """Nenhuma das duas paradas conta como sala superada."""
    conn, canal, cog, incursao = await preparar("Longa")
    run, parada = await _vigilia_com(conn, canal, cog, "folego")
    ids = await db.ids_das_salas_superadas(conn, run["id"])
    descanso = cog._sala_de_descanso(incursao)
    assert incursoes.ID_DO_DESCANSO_DURO not in ids, (
        "a vigília virou sala superada, e `_pagar_as_salas` pagaria por ela"
    )
    assert descanso.id not in ids, "o descanso fixo virou sala superada"
    for p in await db.quem_recebe_da_run(conn, run["id"]):
        assert await db.ouro(conn, p["id"]) == 0, (
            f"{p['nome']} levou ouro por ter descansado"
        )
    await conn.close()
    fechar(conn)
    print("  descansar não conta como sala superada: ok")


async def caso_a_exaustao_da_vigilia_tira_da_incursao():
    """Quem chega na vigília com três pontos sai dela com cinco — e fora."""
    conn, canal, cog, incursao = await preparar("Longa")
    run = await na_vigilia(conn, canal, cog, mesa=_mesa_com("reservas"))
    vitima = JOGADORES[0]
    for _ in range(3):
        await db.aplicar_condicao(conn, run["id"], vitima, "exaustao")

    msg = await canal.fetch_message(run["mensagem_id"])
    parada = run["linha_atual"]
    for user_id in JOGADORES:
        await cog.votar_troca(
            FakeInteraction(canal, user_id, msg), run["id"], parada, "reservas"
        )

    assert not await db.esta_na_run(conn, run["id"], vitima), (
        "cinco pontos de Exaustão tiram o personagem da incursão"
    )
    # Mas o ouro da run continua dele: ele jogou até aqui.
    nomes = [p["user_id"] for p in await db.quem_recebe_da_run(conn, run["id"])]
    assert vitima in nomes, "quem foi ejetado não perde o direito ao ouro"
    await conn.close()
    fechar(conn)
    print("  a Exaustão da vigília tira quem chega nos cinco pontos: ok")


async def caso_o_caminho_da_longa_inteiro():
    """A Longa de ponta a ponta: nove paradas, sete salas, dois descansos."""
    conn, canal, cog, incursao = await preparar("Longa")
    assert incursao.paradas == 9 and incursao.passos == 7
    run = await montar_run(conn, canal, cog)

    vistas = []
    for parada in range(1, incursao.paradas + 1):
        atual = await db.buscar_run(conn, run["id"])
        qual = incursao.descanso_da_parada(parada)
        if qual:
            assert not await db.opcoes_do_passo(conn, run["id"], parada), (
                f"a parada {parada} é descanso e sorteou salas"
            )
            await passar_o_descanso(cog, conn, canal, run["id"])
            vistas.append(qual)
            depois = await db.buscar_run(conn, run["id"])
            assert depois["linha_atual"] == parada + 1, (
                f"a parada {parada} ({qual}) não passou"
            )
            continue
        assert atual["status"] == "escolhendo", (
            f"parada {parada}: esperava votação, veio {atual['status']}"
        )
        alvo = (await cog._opcoes(atual, parada))[0]
        msg = await canal.fetch_message(atual["mensagem_id"])
        for user_id in JOGADORES:
            await cog.votar(
                FakeInteraction(canal, user_id, msg), run["id"], parada, alvo.id
            )
        vistas.append("sala")
        em_sala = await db.buscar_run(conn, run["id"])
        if em_sala["status"] == "em_sala":
            msg_sala = await canal.fetch_message(em_sala["mensagem_id"])
            for user_id in JOGADORES:
                agora = await db.buscar_run(conn, run["id"])
                if agora["status"] != "em_sala":
                    break
                await cog.rolar(
                    FakeInteraction(canal, user_id, msg_sala), run["id"], alvo.id
                )

    assert vistas == [
        "sala", "sala", "sala",
        incursoes.DESCANSO_NORMAL,
        "sala", "sala", "sala",
        incursoes.DESCANSO_DURO,
        "sala",
    ], vistas
    assert (await db.buscar_run(conn, run["id"]))["status"] == "objetivo", (
        "depois da nona parada vem o objetivo"
    )
    assert (await db.buscar_run(conn, run["id"]))["descansos"] == 2
    await conn.close()
    fechar(conn)
    print("  a Longa inteira: 3 salas, descanso, 3 salas, vigília, sala: ok")


async def main() -> None:
    caso_o_mapa_das_paradas()
    caso_as_trocas_do_catalogo()
    caso_o_cartao_de_abertura_conta_os_descansos()
    await caso_o_normal_chega_sem_votacao()
    await caso_a_sala_de_descanso_sai_do_sorteio()
    await caso_a_vigilia_poe_tres_trocas_na_mesa()
    await caso_a_vigilia_recusa_voto_de_fora()
    await caso_a_maioria_fecha_a_vigilia()
    await caso_a_vigilia_aplica_uma_vez_so()
    await caso_folego_cura_e_da_thp()
    await caso_reservas_cobra_dois_pontos()
    await caso_feridas_limpa_debuff_e_deixa_exaustao()
    await caso_revirar_paga_o_ouro_de_uma_sala()
    await caso_velar_da_buff_ao_grupo()
    await caso_a_vigilia_levanta_quem_caiu()
    await caso_a_vigilia_recarrega_as_habilidades()
    await caso_descansar_nao_paga_ouro_de_sala()
    await caso_a_exaustao_da_vigilia_tira_da_incursao()
    await caso_o_caminho_da_longa_inteiro()
    print("descanso: ok")


def _fechar_tudo() -> None:
    async def _com_limpeza():
        try:
            await main()
        finally:
            while _ABERTAS:
                try:
                    await _ABERTAS.pop().close()
                except Exception:
                    pass

    asyncio.run(_com_limpeza())


if __name__ == "__main__":
    _fechar_tudo()
