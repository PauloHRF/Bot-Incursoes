"""Criaturas com multiataque, resistências e ação especial que força save."""
from __future__ import annotations

import asyncio
import random
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import config, database as db, embeds as E, motor  # noqa: E402
from src.cogs.incursao import Incursoes  # noqa: E402
from src.incursoes import ErroDeValidacao, de_dict  # noqa: E402
from fakes import (  # noqa: E402
    CANAL,
    GUILD,
    JOGADORES,
    LORE_TESTE,
    ORG_PADRAO,
    FakeBot,
    FakeCanal,
    FakeInteraction,
    criar_grupo,
    montar_conteudo,
    sala,
    salas_sem_combate,
)

_ABERTAS = []

# O Golem de Ambar do documento, com a Prisao de Ambar.
GOLEM = {
    "nome": "Golem de Âmbar", "ca": 15, "ataque": 6, "dano": "1d8+4", "hp": 75,
    "ataques": 2,
    "habilidade": {
        "nome": "Prisão de Âmbar", "save": "CON", "cd": 13,
        "texto": "Uma explosão de âmbar prende quem não resistir.",
        "atordoa": 1, "cada": 2,
    },
}
# Versoes de teste: prendem sem falhar, e sem machucar ninguem.
PRENDEDOR = {
    "nome": "Prendedor", "ca": 1, "ataque": -20, "dano": "1d1", "hp": 400,
    "habilidade": {
        "nome": "Prisão", "save": "CON", "cd": 99, "atordoa": 1, "alvos": 1, "cada": 1
    },
}
CARCEREIRO = {**PRENDEDOR, "nome": "Carcereiro",
              "habilidade": {**PRENDEDOR["habilidade"], "alvos": 4}}


def monstro_de(bruto: dict):
    """Passa o dicionario pelo validador e devolve a criatura pronta."""
    incursao = de_dict(
        {
            "id": "t", "nome": "T", "organizacao": ORG_PADRAO, "tamanho": "Curta",
            "lore_inicial": LORE_TESTE,
            "recompensa_mes": 10,
            "pontos_conclusao": 10,
            "objetivo": sala("OBJ", "Combate", monstros=[bruto]),
        }
    )
    return incursao.objetivo.monstros


def problemas_de(bruto: dict) -> list[str]:
    try:
        monstro_de(bruto)
    except ErroDeValidacao as erro:
        return erro.problemas
    return []


async def preparar(monstro, quantos=2, nivel=4, classe="guerreiro"):
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass
    config.DB_PATH = Path(__file__).resolve().parent / "teste_criaturas.db"
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


def caso_conteudo_da_criatura():
    """A criatura do documento atravessa o validador inteira."""
    golem = monstro_de(GOLEM)[0]
    assert golem.ataques == 2
    assert golem.habilidade.save == "CON" and golem.habilidade.cd == 13
    assert golem.habilidade.atordoa == 1 and golem.habilidade.alvos == 1
    assert golem.habilidade.cada == 2

    # e volta igual do JSON
    volta = monstro_de(golem.para_dict())[0]
    assert volta.para_dict() == golem.para_dict()

    # saves e vantagem, como no Golem Menor
    menor = monstro_de({
        "nome": "Golem Menor", "ca": 14, "ataque": 5, "dano": "1d8+3", "hp": 36,
        "quantidade": 2, "saves": "FOR +5, CON +5", "saves_vantagem": "FOR, CON",
    })
    assert len(menor) == 2 and menor[0].nome == "Golem Menor 1"
    assert menor[0].saves == {"FOR": 5, "CON": 5}
    assert menor[1].saves_vantagem == ["FOR", "CON"]
    # a criatura simples continua simples
    simples = monstro_de({"nome": "Zumbi", "ca": 10, "ataque": 3, "dano": "1d6+1", "hp": 22})[0]
    assert simples.ataques == 1 and simples.habilidade is None and simples.saves == {}
    print("  a planilha da criatura vira monstro com habilidade e saves: ok")


def caso_validacao_da_habilidade():
    base = {"nome": "X", "ca": 10, "ataque": 3, "dano": "1d6", "hp": 10}
    def com(habilidade, **resto):
        return {**base, **resto, "habilidade": {"nome": "Sopro", **habilidade}}

    assert any("atributo" in p for p in problemas_de(com({"save": "SOR", "cd": 12, "dano": "2d6"})))
    assert any("CD" in p for p in problemas_de(com({"save": "CON", "dano": "2d6"})))
    assert any("não faz nada" in p for p in problemas_de(com({"save": "CON", "cd": 12})))
    assert any("alvos" in p for p in problemas_de(
        com({"save": "CON", "cd": 12, "dano": "2d6", "alvos": 99})
    ))
    assert any("dano" in p for p in problemas_de(
        com({"save": "CON", "cd": 12, "dano": "muito"})
    ))
    assert any("ataques por rodada" in p for p in problemas_de({**base, "ataques": 9}))
    assert any("não é atributo" in p for p in problemas_de({**base, "saves": "XPT +4"}))
    # sem nome de habilidade, a criatura so nao tem uma — nao e erro
    assert problemas_de(base) == []
    print("  o validador reclama do que a criatura nao pode ter: ok")


def caso_ritmo_da_habilidade():
    golem = monstro_de(GOLEM)[0]
    inimigo = motor.Inimigo(
        0, golem.nome, golem.ca, golem.ataque, golem.dano, golem.hp, golem.hp,
        ataques=golem.ataques, habilidade=golem.habilidade,
    )
    assert not inimigo.usa_habilidade(1), "a primeira rodada e de porrada"
    assert inimigo.usa_habilidade(2) and not inimigo.usa_habilidade(3)
    assert inimigo.usa_habilidade(4)
    # criatura sem habilidade nunca conjura
    assert not motor.Inimigo(0, "Zumbi", 10, 3, "1d6", 22, 22).usa_habilidade(2)
    print("  a habilidade sai no ritmo que a planilha pediu: ok")


def caso_multiataque_e_investida():
    golem = monstro_de(GOLEM)[0]
    grupo = [motor.Combatente(i, f"P{i}", 30, 0, "1d1", 100, 100) for i in (1, 2)]
    inimigo = motor.Inimigo(
        0, golem.nome, golem.ca, 40, golem.dano, golem.hp, golem.hp,
        ataques=golem.ataques, habilidade=golem.habilidade,
    )

    # rodada de ataque: dois golpes, nenhuma investida
    vez = motor.rodada_dos_inimigos(motor.EstadoCombate([inimigo], 1, grupo), random.Random(2))
    assert len(vez.golpes) == 2 and not vez.investidas

    # rodada da habilidade: conjura e nao bate
    vez = motor.rodada_dos_inimigos(motor.EstadoCombate([inimigo], 2, grupo), random.Random(2))
    assert not vez.golpes, "na rodada da habilidade a criatura nao ataca"
    assert len(vez.investidas) == 1
    print("  multiataque bate duas vezes; na rodada da habilidade, nenhuma: ok")


def caso_save_decide_a_investida():
    dificil = {**GOLEM["habilidade"], "cd": 99, "dano": "2d6"}
    facil = {**GOLEM["habilidade"], "cd": 1, "dano": "2d6"}  # d20 minimo ja passa

    def investir(habilidade, alvo):
        inimigo = motor.Inimigo(0, "Golem", 15, 6, "1d8", 75, 75,
                                habilidade=monstro_de({**GOLEM, "habilidade": habilidade})[0].habilidade)
        estado = motor.EstadoCombate([inimigo], 2, [alvo])
        return motor.usar_habilidade_do_inimigo(inimigo, estado, random.Random(5))[0]

    # quem falha leva o dano e fica atordoado
    alvo = motor.Combatente(1, "P", 15, 0, "1d1", 40, 40, saves={"CON": 5})
    caiu = investir(dificil, alvo)
    assert not caiu.escapou and caiu.dano > 0 and caiu.atordoou
    assert alvo.atordoado and alvo.hp_atual == 40 - caiu.dano

    # quem passa nao sofre nada
    forte = motor.Combatente(2, "Q", 15, 0, "1d1", 40, 40, saves={"CON": 5})
    escapou = investir(facil, forte)
    assert escapou.escapou and escapou.dano == 0 and not forte.atordoado
    assert forte.hp_atual == 40

    # a vida temporaria segura o dano da habilidade, como a de um golpe
    protegido = motor.Combatente(3, "R", 15, 0, "1d1", 40, 40, thp=50, saves={"CON": 5})
    com_thp = investir(dificil, protegido)
    assert com_thp.absorvido == com_thp.dano and protegido.hp_atual == 40
    # e quem ja esta atordoado nao e atordoado de novo
    preso = motor.Combatente(4, "S", 15, 0, "1d1", 40, 40, atordoado=True, saves={"CON": 5})
    de_novo = investir(dificil, preso)
    assert not de_novo.atordoou and de_novo.dano > 0
    print("  o save decide: quem falha leva dano e trava, quem passa escapa: ok")


def caso_varios_alvos():
    habilidade = monstro_de(
        {**GOLEM, "habilidade": {**GOLEM["habilidade"], "alvos": 2, "cd": 99}}
    )[0].habilidade
    inimigo = motor.Inimigo(0, "Necromante", 13, 6, "1d8+3", 55, 55, habilidade=habilidade)
    grupo = [motor.Combatente(i, f"P{i}", 15, 0, "1d1", 40, 40) for i in (1, 2, 3)]
    estado = motor.EstadoCombate([inimigo], 2, grupo)

    investidas = motor.usar_habilidade_do_inimigo(inimigo, estado, random.Random(4))
    assert len(investidas) == 2
    assert len({i.alvo.user_id for i in investidas}) == 2, "dois alvos diferentes"

    # quem ja esta atordoado fica por ultimo na fila
    grupo[0].atordoado = True
    for c in grupo[1:]:
        c.atordoado = False
    alvos = motor.sortear_alvos(estado, 2, random.Random(4))
    assert grupo[0] not in alvos, "prefere quem ainda pode agir"
    print("  a habilidade pega varios alvos, sem repetir ninguem: ok")


def caso_vantagem_da_criatura():
    """Corpo Inflexivel: o Golem Menor resiste com vantagem em FOR e CON."""
    menor = monstro_de({
        "nome": "Golem Menor", "ca": 14, "ataque": 5, "dano": "1d8+3", "hp": 36,
        "saves": "FOR +5, CON +5", "saves_vantagem": "FOR, CON",
    })[0]
    inimigo = motor.Inimigo(
        0, menor.nome, menor.ca, menor.ataque, menor.dano, menor.hp, menor.hp,
        saves=menor.saves, saves_vantagem=menor.saves_vantagem,
    )
    assert inimigo.save("CON") == 5
    # sem save na planilha, o padrao provisorio vale
    assert inimigo.save("CAR") == menor.ataque - motor.DEFASAGEM_DE_SAVE

    com = motor.salvar_inimigo(inimigo, "CON", 15, random.Random(8))
    sem = motor.salvar_inimigo(inimigo, "CAR", 15, random.Random(8))
    assert com.d20 >= sem.d20, "vantagem rola dois dados e fica com o melhor"
    print("  a criatura resiste com vantagem onde a planilha disse: ok")


async def caso_atordoamento_no_combate():
    conn, canal, cog, incursao, run = await preparar(PRENDEDOR, quantos=2)

    # a criatura veio do conteudo com a habilidade inteira
    estado = await cog._estado_combate(run, incursao.objetivo)
    assert estado.inimigos[0].habilidade.nome == "Prisão"
    assert len(estado.ativos) == 2

    # rodada 1: os dois batem, a rodada fecha e a criatura prende um deles
    for quem in JOGADORES[:2]:
        await cog.atacar(FakeInteraction(canal, quem), run["id"], "OBJ")

    run = await db.buscar_run(conn, run["id"])
    estado = await cog._estado_combate(run, incursao.objetivo)
    assert estado.rodada == 2
    presos = [c for c in estado.combatentes if c.atordoado]
    assert len(presos) == 1, "com CD 99 quem foi mirado nao resiste"
    preso, livre = presos[0], estado.ativos[0]

    # quem esta atordoado nao ataca
    inter = FakeInteraction(canal, preso.user_id)
    await cog.atacar(inter, run["id"], "OBJ")
    assert "atordoado" in inter.resposta, inter.resposta

    # e o painel conta so quem ainda pode agir
    embed, _ = E.combate(incursao.objetivo, estado, 0)
    campos = {f.name: f.value for f in embed.fields}
    assert "atordoado" in campos["Grupo"]
    assert campos["Agiram nesta rodada"] == "0/1"

    # o golpe de quem sobrou fecha a rodada sozinho
    inter = FakeInteraction(canal, livre.user_id)
    await cog.atacar(inter, run["id"], "OBJ")
    depois = await cog._estado_combate(await db.buscar_run(conn, run["id"]), incursao.objetivo)
    assert depois.rodada == 3, "a rodada nao ficou esperando o atordoado"
    assert not depois.combatente(preso.user_id).atordoado, "o atordoamento dura uma rodada"
    print("  atordoado perde a vez e a rodada fecha sem ele: ok")


async def caso_grupo_todo_preso_nao_trava():
    """Se ninguem pode agir, a rodada corre sozinha em vez de esperar clique."""
    conn, canal, cog, incursao, run = await preparar(CARCEREIRO, quantos=2)
    for quem in JOGADORES[:2]:
        await cog.atacar(FakeInteraction(canal, quem), run["id"], "OBJ")

    estado = await cog._estado_combate(await db.buscar_run(conn, run["id"]), incursao.objetivo)
    assert estado.rodada >= 3, "a rodada de ninguem passou sozinha"
    assert estado.ativos, "ninguem fica atordoado duas rodadas seguidas"

    # e o combate continua respondendo a cliques
    inter = FakeInteraction(canal, estado.ativos[0].user_id)
    await cog.atacar(inter, await db.buscar_run(conn, run["id"]) and run["id"], "OBJ")
    assert "atordoado" not in inter.resposta, inter.resposta
    print("  grupo inteiro preso nao trava o combate: ok")


async def caso_criatura_sobrevive_ao_reinicio():
    """O bot pode reiniciar no meio do combate: a habilidade esta no banco."""
    conn, canal, cog, incursao, run = await preparar(GOLEM, quantos=2)
    linhas = await db.inimigos_do_combate(conn, run["id"], cog._passo(run))
    assert linhas[0]["ataques"] == 2
    assert linhas[0]["habilidade"].nome == "Prisão de Âmbar"
    assert linhas[0]["habilidade"].cd == 13

    # e o estado remontado do banco tem tudo de volta
    estado = await cog._estado_combate(run, incursao.objetivo)
    inimigo = estado.inimigos[0]
    assert inimigo.ataques == 2 and inimigo.usa_habilidade(2)
    print("  a criatura volta inteira do banco depois de um reinicio: ok")


async def main():
    try:
        caso_conteudo_da_criatura()
        caso_validacao_da_habilidade()
        caso_ritmo_da_habilidade()
        caso_multiataque_e_investida()
        caso_save_decide_a_investida()
        caso_varios_alvos()
        caso_vantagem_da_criatura()
        await caso_atordoamento_no_combate()
        await caso_grupo_todo_preso_nao_trava()
        await caso_criatura_sobrevive_ao_reinicio()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        (Path(__file__).resolve().parent / "teste_criaturas.db").unlink(missing_ok=True)


asyncio.run(main())
print("TESTES DE CRIATURAS PASSARAM")
