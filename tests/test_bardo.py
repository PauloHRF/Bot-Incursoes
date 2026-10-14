"""O bardo: o dono do socorro. Cinco habilidades de outras classes usam a
máquina dele; a versão dele é a melhor — dado em vez de número, três usos em
vez de um, e o jogador escolhe em que rolagem o dado entra."""
from __future__ import annotations

import asyncio
import collections
import random
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import classes as cl, config, database as db, motor  # noqa: E402
from src.cogs.incursao import Incursoes  # noqa: E402
from src.rules import mod_pericia  # noqa: E402
from fakes import (  # noqa: E402
    CANAL,
    GUILD,
    INDEFESO,
    JOGADORES,
    TREINADAS,
    FakeBot,
    FakeCanal,
    FakeInteraction,
    criar_grupo,
    montar_conteudo,
    sala,
    salas_sem_combate,
)

_ABERTAS = []

SACO = {**INDEFESO, "hp": 500, "ataque": 1, "dano": "1d1"}
# Criatura que sempre acerta e cobra save impossivel: forca a falha que o
# bardo vem socorrer.
CRUEL = {
    "nome": "Algoz", "ca": 40, "ataque": 40, "dano": "1d4", "hp": 4000,
    "habilidade": {"nome": "Grito", "save": "CAR", "cd": 99, "dano": "2d6",
                   "alvos": 1},
}


async def preparar(nivel=9, escolhas=None, quantos=3, monstro=SACO, monstros=2,
                   salas=None):
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass
    config.DB_PATH = Path(__file__).resolve().parent / "teste_bardo.db"
    config.DB_PATH.unlink(missing_ok=True)
    config.TAMANHO_GRUPO = 5
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    await criar_grupo(conn, nivel=nivel, classe="bardo")
    canal = FakeCanal(CANAL)
    cog = Incursoes(FakeBot(conn, canal))
    incursao, _ = montar_conteudo(
        cog, tamanho="Curta",
        salas=salas if salas is not None else salas_sem_combate(),
        monstro_objetivo=monstro, inimigos_objetivo=monstros,
    )
    run_id = await db.criar_run(conn, GUILD, CANAL, incursao.id, JOGADORES[0])
    for user_id in JOGADORES[:quantos]:
        p = await db.personagem_por_nome(conn, GUILD, user_id, f"Heroi{user_id}")
        await db.adicionar_participante(conn, run_id, user_id, p["id"])
        for escolha, opcao in (escolhas or {}).items():
            await db.definir_escolha(conn, p["id"], escolha, opcao)
    await db.inicializar_hp(conn, run_id)
    return conn, canal, cog, incursao, run_id


async def em_combate(conn, cog, incursao, run_id):
    await db.atualizar_run(
        conn, run_id, status="objetivo", sala_atual="OBJ",
        linha_atual=incursao.passos + 1,
    )
    run = await db.buscar_run(conn, run_id)
    await cog._abrir_combate(run, incursao.objetivo)
    return await db.buscar_run(conn, run_id)


# ------------------------------------------------------- a tabela e a forma


def caso_tabela_de_suporte():
    bardo = cl.CLASSES["bardo"]
    assert [bardo.tiers[t].hp for t in range(1, 6)] == [19, 31, 45, 59, 73]
    assert [bardo.tiers[t].ca for t in range(1, 6)] == [14, 15, 16, 17, 18]
    assert bardo.tiers[1].dano == "1d6" and bardo.tiers[5].dano == "2d8"
    assert bardo.saves == ("DES", "CAR")
    # e o dano dele empata com o piso do jogo
    from src.habilidades import media_do_dado
    meu = media_do_dado(bardo.tiers[5].dano)
    piso = min(
        media_do_dado(c.tiers[5].dano) * cl.efeitos(cid, 10, {}).get("ataques", 1)
        for cid, c in cl.CLASSES.items()
    )
    assert meu == piso, (meu, piso)
    print("  d8 de couro, e o dano no piso do jogo: ele nao esta ali para bater: ok")


def caso_todas_as_catorze_entraram():
    """O bardo era a última: o documento fechou."""
    assert cl.CLASSES_PENDENTES == (), cl.CLASSES_PENDENTES
    assert len(cl.CLASSES) == len(cl.CLASSES_PREVISTAS) == 14
    for nome in cl.CLASSES_PREVISTAS:
        assert cl.classe(nome) is not None, nome
        assert cl.numeros(nome, 1) is not None, nome
    print("  as 14 classes previstas estao todas jogaveis: ok")


def caso_a_inspiracao_tem_tres_usos():
    """Todas as outras cinco reações de socorro têm um uso; esta tem três."""
    inspiracoes = [
        h
        for lista in cl.CLASSES["bardo"].habilidades.values()
        for h in lista
        if (h.acao or {}).get("inspira")
    ]
    assert len(inspiracoes) == 3, [h.id for h in inspiracoes]
    for h in inspiracoes:
        assert h.vezes == 3, (h.id, h.vezes)
        assert h.escopo == "descanso"
    # e as outras cinco continuam com um uso e numero fixo
    fixas = [
        h
        for c in cl.CLASSES.values()
        for lista in c.habilidades.values()
        for h in lista
        if (h.acao or {}).get("quando") == "falhou_teste"
        and not (h.acao or {}).get("inspira")
    ]
    assert len(fixas) == 5, [h.id for h in fixas]
    for h in fixas:
        assert h.vezes == 1 and h.acao.get("bonus"), h.id
    print("  a Inspiracao tem tres usos e dado; as outras cinco, um e numero: ok")


# ------------------------------------------------------------------ o dado


def caso_pode_virar_usa_o_teto():
    """Com dado o socorro é incerto: entra pelo teto, e depois rola."""
    assert motor.maior_do_dado("1d6") == 6
    assert motor.maior_do_dado("1d10") == 10
    assert motor.pode_virar(6, "1d6") and not motor.pode_virar(7, "1d6")
    assert motor.pode_virar(10, "1d10") and not motor.pode_virar(11, "1d10")
    # quem ja passou (falta <= 0) nunca gasta uso
    assert not motor.pode_virar(0, "1d10")
    assert not motor.pode_virar(-3, "1d10")
    print("  o socorro entra se o TETO do dado cobriria a falha: ok")


def caso_o_dado_cresce_no_tier_4():
    cedo = cl.efeitos("bardo", 5, {})
    assert not cedo.get("dado_inspiracao"), "antes do tier 4 vale o d6 da acao"
    tarde = cl.efeitos("bardo", 9, {})
    assert tarde["dado_inspiracao"] == "1d10"
    base = next(
        h
        for lista in cl.CLASSES["bardo"].habilidades.values()
        for h in lista
        if h.id == "inspira_pericia"
    )
    assert base.acao["dado"] == "1d6"
    print("  o dado vai de d6 a d10 na passiva do tier 4: ok")


# ------------------------------------------------------- os tres gatilhos


async def caso_inspiracao_na_pericia():
    """CD alta de propósito: a falha é quase certa, e o d10 socorre ou não."""
    dificil = [
        sala("S1", "Evento", cd=30, alvo_progresso=1, pericias=["Atletismo"]),
        sala("S2", "Evento", cd=30, alvo_progresso=1, pericias=["Atletismo"]),
        sala("S3", "Evento", cd=30, alvo_progresso=1, pericias=["Atletismo"]),
    ]
    socorreu = False
    for _ in range(14):
        conn, canal, cog, incursao, run_id = await preparar(
            escolhas={"inspiracao_t2": "inspira_pericia"}, salas=dificil
        )
        await db.atualizar_run(
            conn, run_id, status="em_sala", sala_atual="S1", linha_atual=1
        )
        await db.gravar_opcoes(conn, run_id, 1, ["S1", "S2", "S3"])
        inter = FakeInteraction(canal, JOGADORES[0])
        await cog.rolar(inter, run_id, "S1")
        if "de Heroi" in (inter.resposta or ""):
            socorreu = True
            # o uso saiu, e o canal contou
            anuncios = " ".join(str(m.content or "") for m in canal.enviadas)
            assert "socorre" in anuncios, anuncios[-200:]
            break
    assert socorreu, "em 14 tentativas o socorro na pericia nunca entrou"
    print("  Inspiracao na pericia socorre o teste de sala: ok")


async def caso_inspiracao_no_ataque():
    """CA 40: o golpe erra sempre, e o d10 nunca cobre — o uso fica guardado."""
    conn, canal, cog, incursao, run_id = await preparar(
        escolhas={"inspiracao_t2": "inspira_ataque"}, monstro=CRUEL, monstros=1
    )
    run = await em_combate(conn, cog, incursao, run_id)
    estado = await cog._estado_combate(run, incursao.objetivo)
    alvo = estado.inimigos[0].indice

    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.atacar(inter, run["id"], "OBJ", alvo)
    gastos = await db.usos_da_run(conn, run_id, JOGADORES[0])
    # CA 40 contra +11: falta 18 ou mais, e o d10 nunca cobre
    assert not any(c[0] == "inspira_ataque" for c in gastos), gastos
    print("  no ataque impossivel a Inspiracao nao queima o uso: ok")


async def caso_inspiracao_no_ataque_quando_cobre():
    """CA ajustada para o golpe errar por pouco: aí o dado entra."""
    quase = {**SACO, "ca": 22}
    entrou = False
    for _ in range(14):
        conn, canal, cog, incursao, run_id = await preparar(
            escolhas={"inspiracao_t2": "inspira_ataque"}, monstro=quase, monstros=1
        )
        run = await em_combate(conn, cog, incursao, run_id)
        estado = await cog._estado_combate(run, incursao.objetivo)
        alvo = estado.inimigos[0].indice
        inter = FakeInteraction(canal, JOGADORES[0])
        await cog.atacar(inter, run["id"], "OBJ", alvo)
        gastos = await db.usos_da_run(conn, run_id, JOGADORES[0])
        if any(c[0] == "inspira_ataque" for c in gastos):
            entrou = True
            break
    assert entrou, "em 14 golpes contra CA 22 a Inspiracao nunca entrou"
    print("  no ataque que errou por pouco, o dado entra e pode fazer acertar: ok")


async def caso_inspiracao_no_save_devolve_o_dano():
    """A criatura cobra save de CD 99: falha sempre, e o d10 nunca cobre."""
    conn, canal, cog, incursao, run_id = await preparar(
        escolhas={"inspiracao_t2": "inspira_save"}, monstro=CRUEL, monstros=1
    )
    run = await em_combate(conn, cog, incursao, run_id)
    estado = await cog._estado_combate(run, incursao.objetivo)
    # CD 99: a falta passa de 80, muito acima do teto do d10
    alvo = estado.vivos[0]
    investida = motor.Investida(
        "Algoz", "Grito", alvo,
        save=motor.ResultadoSave(alvo.nome, "CAR", 5, 5, 99), dano=7,
    )
    await cog._inspirar_o_save(run, estado, [investida])
    assert investida.dano == 7, "nao devia mexer: o dado nao cobre"
    gastos = await db.usos_da_run(conn, run_id, JOGADORES[0])
    assert not any(c[0] == "inspira_save" for c in gastos), gastos

    # e agora um save que falhou por 3: o d10 cobre, e o dano volta
    perto = motor.Investida(
        "Algoz", "Grito", alvo,
        save=motor.ResultadoSave(alvo.nome, "CAR", 9, 3, 15), dano=7,
        atordoou=True,
    )
    hp_antes = alvo.hp_atual
    await cog._inspirar_o_save(run, estado, [perto])
    if perto.dano == 0:
        assert not perto.atordoou, "resistindo, o atordoamento sai tambem"
        assert alvo.hp_atual == hp_antes + 7, (hp_antes, alvo.hp_atual)
        print("  Inspiracao no save devolve o dano e tira o atordoamento: ok")
    else:
        assert perto.dano == 7, "ou o dado nao bastou, e nada mudou"
        print("  Inspiracao no save entrou e o dado nao bastou: ok")


# -------------------------------------------------------- Jack of All Trades


def caso_jack_of_all_trades_so_no_que_falta():
    """O único bônus do bot que depende de NÃO ter proficiência."""
    numeros = cl.numeros("bardo", 9)
    treinadas = list(TREINADAS)
    nao_treinada = next(
        p for p in ("Arcanismo", "Religião", "Medicina") if p not in treinadas
    )
    efeitos = cl.efeitos("bardo", 9, {"saber_t4": "jack_of_all_trades"})
    assert efeitos["bonus_sem_treino"] == 3

    sem = mod_pericia(nao_treinada, numeros, treinadas, None, {})
    com = mod_pericia(nao_treinada, numeros, treinadas, None, efeitos)
    assert com == sem + 3, (sem, com)
    # e na treinada nao muda nada
    treinada = treinadas[0]
    assert mod_pericia(treinada, numeros, treinadas, None, efeitos) == mod_pericia(
        treinada, numeros, treinadas, None, {}
    )
    print(f"  Jack of All Trades soma 3 em {nao_treinada} e nada na treinada: ok")


def caso_as_outras_duas_do_repertorio():
    expertise = cl.efeitos("bardo", 9, {"saber_t4": "expertise_bardo"})
    assert "Atuação" in expertise["expertise"]
    versatil = cl.efeitos("bardo", 9, {"saber_t4": "versatilidade"})
    assert versatil["bonus_teste"] == 2
    print("  Expertise dobra duas pericias, Versatilidade soma em todas: ok")


# ------------------------------------------------------------------ o T5


async def caso_ottos_dance_prende_e_atrapalha():
    conn, canal, cog, incursao, run_id = await preparar(
        escolhas={"magia_bardo_t5": "ottos_dance"}, monstros=1
    )
    run = await em_combate(conn, cog, incursao, run_id)
    estado = await cog._estado_combate(run, incursao.objetivo)
    alvo = estado.inimigos[0].indice
    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.usar_habilidade(inter, run["id"], "OBJ", "ottos_dance", [alvo])
    estado = await cog._estado_combate(await db.buscar_run(conn, run_id),
                                       incursao.objetivo)
    inimigo = estado.inimigo(alvo)
    if inimigo.penalidade_ataque:
        assert inimigo.penalidade_ataque == 5, inimigo.penalidade_ataque
        assert "perde a vez" in inter.resposta, inter.resposta
    else:
        assert "resistiu" in inter.resposta, inter.resposta
    print("  Otto's prende e tira 5 do ataque de quem dança: ok")


async def caso_aid_da_thp_e_cura():
    conn, canal, cog, incursao, run_id = await preparar(
        escolhas={"magia_bardo_t3": "aid"}
    )
    run = await em_combate(conn, cog, incursao, run_id)
    for uid in JOGADORES[:3]:
        await db.definir_hp(conn, run_id, uid, 20)
    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.usar_habilidade(inter, run["id"], "OBJ", "aid")
    pessoas = {p["user_id"]: p for p in await db.personagens_da_run(conn, run_id)}
    for uid in JOGADORES[:3]:
        assert pessoas[uid]["thp"] >= 3, pessoas[uid]["thp"]
        assert pessoas[uid]["hp_atual"] > 20, pessoas[uid]["hp_atual"]
    print("  Aid da vida temporaria E cura o grupo no mesmo lance: ok")


async def main():
    try:
        caso_tabela_de_suporte()
        caso_todas_as_catorze_entraram()
        caso_a_inspiracao_tem_tres_usos()
        caso_pode_virar_usa_o_teto()
        caso_o_dado_cresce_no_tier_4()
        await caso_inspiracao_na_pericia()
        await caso_inspiracao_no_ataque()
        await caso_inspiracao_no_ataque_quando_cobre()
        await caso_inspiracao_no_save_devolve_o_dano()
        caso_jack_of_all_trades_so_no_que_falta()
        caso_as_outras_duas_do_repertorio()
        await caso_ottos_dance_prende_e_atrapalha()
        await caso_aid_da_thp_e_cura()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        (Path(__file__).resolve().parent / "teste_bardo.db").unlink(missing_ok=True)


asyncio.run(main())
print("TESTES DO BARDO PASSARAM")
