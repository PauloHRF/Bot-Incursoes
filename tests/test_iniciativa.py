"""Iniciativa: 1d20 + Destreza, e as ações saindo uma de cada vez, na ordem."""
from __future__ import annotations

import asyncio
import random
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import config, database as db, motor  # noqa: E402
from src.cogs.incursao import Incursoes  # noqa: E402
from fakes import (  # noqa: E402
    CANAL,
    INDEFESO,
    GUILD,
    JOGADORES,
    FakeBot,
    FakeCanal,
    FakeInteraction,
    criar_grupo,
    iniciativa_de_verdade,
    montar_conteudo,
    salas_de_combate,
    salas_sem_combate,
)

_ABERTAS = []
BANCO = Path(__file__).resolve().parent / "teste_iniciativa.db"

# Aguenta o combate inteiro sem machucar ninguem.
PARADO = {"nome": "Estatua", "ca": 1, "ataque": -20, "dano": "1d1", "hp": 4000}
# Acerta sempre (so o 1 natural erra), sem derrubar ninguem de uma vez.
BATEDOR = {"nome": "Batedor", "ca": 1, "ataque": 40, "dano": "1d1+4", "hp": 4000}
PESADO = {"nome": "Britador", "ca": 1, "ataque": 40, "dano": "1d1+19", "hp": 4000}
# Prende sem falhar: toda rodada, ou so nas pares.
PRENDEDOR = {
    "nome": "Prendedor", "ca": 1, "ataque": -20, "dano": "1d1", "hp": 4000,
    "habilidade": {
        "nome": "Prisão", "save": "CON", "cd": 99, "atordoa": 1, "alvos": 1, "cada": 1
    },
}
PRENDE_NAS_PARES = {
    **PRENDEDOR,
    "habilidade": {**PRENDEDOR["habilidade"], "cada": 2},
}


def ordem_fixa(*quem):
    """Fixa a ordem do proximo combate: ("p", user_id) ou ("i", indice)."""

    def rolar(estado, rng=None):
        ordem = []
        for posicao, (tipo, ident) in enumerate(quem):
            if tipo == "p":
                nome = estado.combatente(ident).nome
                ordem.append(motor.Iniciativa(motor.PERSONAGEM, ident, nome, 20 - posicao, 0))
            else:
                nome = estado.inimigo(ident).nome
                ordem.append(motor.Iniciativa(motor.INIMIGO, ident, nome, 20 - posicao, 0))
        return ordem

    motor.rolar_iniciativas = rolar


async def preparar(monstro=PARADO, quantos=2, classe="guerreiro", nivel=8):
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass
    config.DB_PATH = BANCO
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
    return conn, canal, cog, incursao, await db.buscar_run(conn, run_id)


async def abrir(conn, cog, incursao, run):
    await cog._abrir_combate(run, incursao.objetivo)
    return await db.buscar_run(conn, run["id"])


async def situacao(conn, cog, run):
    """(rodada, vez) do combate agora."""
    linha = await db.estado_combate(conn, run["id"], cog._passo(run))
    return linha["rodada"], linha["vez"]


def caso_modificador_e_o_save_de_des():
    heroi = motor.Combatente(1, "H", 15, 0, "1d1", 30, 30, saves={"DES": 4, "FOR": 1})
    assert motor.mod_iniciativa(heroi) == 4
    # sem o save na ficha, entra com 0
    assert motor.mod_iniciativa(motor.Combatente(2, "S", 15, 0, "1d1", 30, 30)) == 0

    # a criatura usa o save de DES da planilha; sem ele, o padrao provisorio
    com_save = motor.Inimigo(0, "Gato", 12, 5, "1d4", 10, 10, saves={"DES": 7})
    sem_save = motor.Inimigo(1, "Ogro", 11, 6, "2d8", 50, 50)
    assert motor.mod_iniciativa(com_save) == 7
    assert motor.mod_iniciativa(sem_save) == 6 - motor.DEFASAGEM_DE_SAVE

    rolada = motor.rolar_iniciativa(motor.PERSONAGEM, 1, "H", 4, random.Random(3))
    assert 1 <= rolada.d20 <= 20 and rolada.total == rolada.d20 + 4
    print("  iniciativa e 1d20 + o save de DES, de heroi e de criatura: ok")


def caso_ordem_e_desempate():
    a = motor.Iniciativa(motor.PERSONAGEM, 1, "A", 10, 2, desempate=1)
    b = motor.Iniciativa(motor.INIMIGO, 0, "B", 8, 4, desempate=9)  # mesmo total, mod maior
    c = motor.Iniciativa(motor.PERSONAGEM, 2, "C", 15, 0, desempate=1)
    d = motor.Iniciativa(motor.PERSONAGEM, 3, "D", 10, 2, desempate=5)  # empata com A
    ordem = motor.ordenar_iniciativa([a, b, c, d])
    assert [r.nome for r in ordem] == ["C", "B", "D", "A"], [r.nome for r in ordem]
    print("  maior total primeiro; no empate, maior modificador, depois a sorte: ok")


async def caso_rolagem_de_verdade_no_combate():
    iniciativa_de_verdade(True)
    try:
        conn, canal, cog, incursao, run = await preparar(quantos=3)
        run = await abrir(conn, cog, incursao, run)
    finally:
        iniciativa_de_verdade(False)
    ordem = await db.iniciativa(conn, run["id"], cog._passo(run))
    assert len(ordem) == 4, ordem
    estado = await cog._estado_combate(run, incursao.objetivo)
    for entrada in ordem:
        assert 1 <= entrada["d20"] <= 20
        if entrada["tipo"] == motor.PERSONAGEM:
            esperado = estado.combatente(entrada["alvo_id"]).saves["DES"]
        else:
            esperado = estado.inimigo(entrada["alvo_id"]).save("DES")
        assert entrada["modificador"] == esperado, entrada
    totais = [e["d20"] + e["modificador"] for e in ordem]
    assert totais == sorted(totais, reverse=True), totais

    # e a ordem aparece no painel
    painel = canal.mensagens[-1].embeds[0]
    campos = {f.name: f.value for f in painel.fields}
    assert all(e["nome"] in campos["Iniciativa"] for e in ordem), campos["Iniciativa"]

    # reabrir o combate (restart, /incursao sala) nao rola de novo
    await cog._garantir_iniciativa(run, estado)
    assert await db.iniciativa(conn, run["id"], cog._passo(run)) == ordem
    print("  o combate rola a iniciativa de todos uma vez e mostra a ordem: ok")


async def caso_monstro_no_topo_age_sem_clique():
    ordem_fixa(("i", 0), ("p", JOGADORES[0]), ("p", JOGADORES[1]))
    conn, canal, cog, incursao, run = await preparar(monstro=BATEDOR)
    run = await abrir(conn, cog, incursao, run)
    assert await situacao(conn, cog, run) == (1, 1)
    linhas = cog._registros[run["id"]]["linhas"]
    assert any("Batedor" in linha for linha in linhas), linhas
    print("  a criatura no topo da ordem age antes de alguem clicar: ok")


async def caso_acao_fora_da_vez_fica_guardada():
    primeiro, segundo = JOGADORES[0], JOGADORES[1]
    ordem_fixa(("p", primeiro), ("p", segundo), ("i", 0))
    conn, canal, cog, incursao, run = await preparar(monstro=PARADO)
    run = await abrir(conn, cog, incursao, run)
    passo = cog._passo(run)

    # o segundo escolhe antes: a acao fica guardada e nada acontece ainda
    antes = await cog._estado_combate(run, incursao.objetivo)
    inter = FakeInteraction(canal, segundo)
    await cog.atacar(inter, run["id"], "OBJ")
    assert "guardada" in inter.resposta and "Heroi101" in inter.resposta, inter.resposta
    turno = await db.turno_de(conn, run["id"], passo, 1, segundo)
    assert turno["acao"] == "ataque" and not turno["resolvida"]
    agora = await cog._estado_combate(run, incursao.objetivo)
    assert agora.inimigos[0].hp_atual == antes.inimigos[0].hp_atual
    assert await situacao(conn, cog, run) == (1, 0)

    # quem ja escolheu nao escolhe de novo
    repetido = FakeInteraction(canal, segundo)
    await cog.atacar(repetido, run["id"], "OBJ")
    assert "já atacou" in repetido.resposta, repetido.resposta

    # o primeiro age: o golpe dele sai, o guardado sai logo depois, o monstro
    # age e a rodada vira, esperando de novo pelo primeiro
    inter = FakeInteraction(canal, primeiro)
    await cog.atacar(inter, run["id"], "OBJ")
    assert "🎲" in inter.resposta, inter.resposta
    assert (await db.turno_de(conn, run["id"], passo, 1, segundo))["resolvida"]
    ataques = await db.ataques_da_rodada(conn, run["id"], passo, 1)
    assert {a["user_id"] for a in ataques} == {primeiro, segundo}
    # os dois golpes na ordem da iniciativa
    assert ataques[0]["user_id"] == primeiro, ataques
    assert await situacao(conn, cog, run) == (2, 0)
    print("  a acao escolhida fora da vez fica guardada e sai na ordem: ok")


async def caso_monstro_entre_jogadores():
    primeiro, segundo = JOGADORES[0], JOGADORES[1]
    ordem_fixa(("p", primeiro), ("i", 0), ("p", segundo))
    conn, canal, cog, incursao, run = await preparar(monstro=BATEDOR)
    run = await abrir(conn, cog, incursao, run)
    assert await situacao(conn, cog, run) == (1, 0)

    await cog.atacar(FakeInteraction(canal, primeiro), run["id"], "OBJ")
    # o monstro ja agiu, e a vez e do segundo
    assert await situacao(conn, cog, run) == (1, 2)
    linhas = cog._registros[run["id"]]["linhas"]
    assert any("↩️ **Batedor**" in linha for linha in linhas), linhas
    painel = {f.name: f.value for f in canal.mensagens[-1].embeds[0].fields}
    assert "▶️" in painel["Iniciativa"] and "Heroi102" in painel["Iniciativa"]
    print("  a criatura age na vez dela, entre os jogadores: ok")


async def caso_habilidade_guardada_sai_na_vez():
    primeiro, segundo = JOGADORES[0], JOGADORES[1]
    ordem_fixa(("p", primeiro), ("p", segundo), ("i", 0))
    conn, canal, cog, incursao, run = await preparar(
        monstro=PARADO, classe="barbaro"
    )
    run = await abrir(conn, cog, incursao, run)
    passo = cog._passo(run)

    inter = FakeInteraction(canal, segundo)
    await cog.usar_habilidade(inter, run["id"], "OBJ", "rage")
    assert "guardada" in inter.resposta, inter.resposta
    # o uso ja foi gasto, mas a Rage ainda nao ligou
    gastos = await db.usos_da_run(conn, run["id"], segundo)
    assert sum(gastos.values()) == 1, gastos
    ligados = await db.efeitos_ativos(conn, run["id"], passo, 0)
    assert not any(e["efeito"] == "rage" for e in ligados)

    await cog.atacar(FakeInteraction(canal, primeiro), run["id"], "OBJ")
    ligados = await db.efeitos_ativos(conn, run["id"], passo, 0)
    assert any(e["efeito"] == "rage" and e["alvo_id"] == segundo for e in ligados), ligados
    assert any("Rage" in (m.content or "") for m in canal.mensagens)
    print("  a habilidade escolhida fora da vez sai quando a vez chega: ok")


async def caso_atordoado_depois_da_vez_perde_a_proxima():
    ordem_fixa(("p", JOGADORES[0]), ("i", 0))
    conn, canal, cog, incursao, run = await preparar(monstro=PRENDEDOR, quantos=1)
    run = await abrir(conn, cog, incursao, run)

    # ele ja agiu na rodada 1 quando e preso: perde a vez da 2, e na 3 volta
    await cog.atacar(FakeInteraction(canal, JOGADORES[0]), run["id"], "OBJ")
    assert await situacao(conn, cog, run) == (3, 0)
    anterior = cog._registros[run["id"]]["anterior"]
    assert anterior[0] == 2 and any("perde a vez" in linha for linha in anterior[1]), anterior
    print("  preso depois de agir, perde a vez da rodada seguinte: ok")


async def caso_atordoado_antes_da_vez_perde_a_desta():
    ordem_fixa(("i", 0), ("p", JOGADORES[0]))
    conn, canal, cog, incursao, run = await preparar(monstro=PRENDE_NAS_PARES, quantos=1)
    run = await abrir(conn, cog, incursao, run)
    assert await situacao(conn, cog, run) == (1, 1)

    # rodada 2: o Prendedor age antes dele e o prende — ele perde a vez da 2
    await cog.atacar(FakeInteraction(canal, JOGADORES[0]), run["id"], "OBJ")
    assert await situacao(conn, cog, run) == (3, 1)
    anterior = cog._registros[run["id"]]["anterior"]
    assert anterior[0] == 2, anterior
    assert any("Prisão" in linha for linha in anterior[1]), anterior
    assert any("perde a vez" in linha for linha in anterior[1]), anterior
    print("  preso antes de agir, perde a vez da propria rodada: ok")


async def caso_guardada_de_quem_foi_preso_devolve_o_uso():
    primeiro, segundo = JOGADORES[0], JOGADORES[1]
    ordem_fixa(("p", primeiro), ("i", 0), ("p", segundo))
    conn, canal, cog, incursao, run = await preparar(
        monstro={**PRENDEDOR, "habilidade": {**PRENDEDOR["habilidade"], "alvos": 2}},
        classe="barbaro",
    )
    run = await abrir(conn, cog, incursao, run)

    # o segundo guarda a Rage, mas o Prendedor age antes dele e o prende
    await cog.usar_habilidade(FakeInteraction(canal, segundo), run["id"], "OBJ", "rage")
    await cog.atacar(FakeInteraction(canal, primeiro), run["id"], "OBJ")
    gastos = await db.usos_da_run(conn, run["id"], segundo)
    assert sum(gastos.values()) == 0, gastos
    passo = cog._passo(run)
    assert not any(
        e["efeito"] == "rage" for e in await db.efeitos_ativos(conn, run["id"], passo, 0)
    )
    print("  a habilidade guardada de quem foi preso nao sai, e o uso volta: ok")


async def caso_rage_guardada_vale_contra_o_monstro_seguinte():
    ordem_fixa(("p", JOGADORES[0]), ("i", 0))
    conn, canal, cog, incursao, run = await preparar(
        monstro=PESADO, quantos=1, classe="barbaro"
    )
    run = await abrir(conn, cog, incursao, run)
    dono = JOGADORES[0]
    antes = (await db.hp_dos_participantes(conn, run["id"]))[dono]
    await cog.usar_habilidade(FakeInteraction(canal, dono), run["id"], "OBJ", "rage")
    depois = (await db.hp_dos_participantes(conn, run["id"]))[dono]
    assert antes - depois == 10, (antes, depois)
    print("  a Rage ja corta o golpe do monstro que vem depois na ordem: ok")


async def caso_vencer_a_ultima_sala_abre_o_objetivo():
    """Vencer um combate no ultimo passo abre o do objetivo sem travar a fila."""
    ordem_fixa(("p", JOGADORES[0]), ("i", 0))
    conn, canal, cog, incursao, run = await preparar(quantos=1)
    montar_conteudo(cog, tamanho="Curta", salas=salas_de_combate(INDEFESO))
    await db.atualizar_run(
        conn, run["id"], status="em_sala", sala_atual="C1", linha_atual=incursao.passos
    )
    run = await db.buscar_run(conn, run["id"])
    combate = cog._sala(incursao, "C1")
    await cog._abrir_combate(run, combate)

    for _ in range(10):  # o 1 natural erra ate o saco de pancada
        atual = await db.buscar_run(conn, run["id"])
        if atual["status"] == "objetivo":
            break
        ordem_fixa(("p", JOGADORES[0]), ("i", 0))
        await asyncio.wait_for(
            cog.atacar(FakeInteraction(canal, JOGADORES[0]), run["id"], "C1"), 10
        )
    atual = await db.buscar_run(conn, run["id"])
    assert atual["status"] == "objetivo" and atual["sala_atual"] == "OBJ", atual
    assert await db.iniciativa(conn, run["id"], cog._passo(atual))
    print("  vencer a ultima sala abre o objetivo, com iniciativa nova: ok")


async def main():
    try:
        caso_modificador_e_o_save_de_des()
        caso_ordem_e_desempate()
        await caso_rolagem_de_verdade_no_combate()
        await caso_monstro_no_topo_age_sem_clique()
        await caso_acao_fora_da_vez_fica_guardada()
        await caso_monstro_entre_jogadores()
        await caso_habilidade_guardada_sai_na_vez()
        await caso_atordoado_depois_da_vez_perde_a_proxima()
        await caso_atordoado_antes_da_vez_perde_a_desta()
        await caso_guardada_de_quem_foi_preso_devolve_o_uso()
        await caso_rage_guardada_vale_contra_o_monstro_seguinte()
        await caso_vencer_a_ultima_sala_abre_o_objetivo()
    finally:
        iniciativa_de_verdade(False)
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        BANCO.unlink(missing_ok=True)


asyncio.run(main())
print("TESTES DE INICIATIVA PASSARAM")
