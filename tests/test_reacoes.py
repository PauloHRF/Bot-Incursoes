"""Uncanny Dodge, Stunning Strike e Martial Arts: reação, condição e sequência."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import classes as cl, config, database as db, motor  # noqa: E402
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
# Acerta sempre e bate forte: bom para medir o que a esquiva segurou.
MARRETA = {"nome": "Marreta", "ca": 1, "ataque": 40, "dano": "1d1+39", "hp": 4000}


async def preparar(classe="ladino", nivel=8, monstro=DURADOURO, quantos=2, inimigos=1):
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass
    config.DB_PATH = Path(__file__).resolve().parent / "teste_reacoes.db"
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


def caso_quando_vale_esquivar():
    """A esquiva é de uma vez por combate: não se gasta num arranhão."""
    c = motor.Combatente(1, "C", 15, 0, "1d1", 100, 60)
    # um terco do que resta e o limiar padrao
    assert not motor.vale_esquivar(c, 5, 1 / 3)
    assert motor.vale_esquivar(c, 20, 1 / 3)
    # um golpe que derrubaria sempre vale
    assert motor.vale_esquivar(c, 60, 1 / 3)
    # a vida temporaria conta como sobrevida
    com_thp = motor.Combatente(2, "T", 15, 0, "1d1", 100, 10, thp=50)
    assert not motor.vale_esquivar(com_thp, 10, 1 / 3)
    assert motor.vale_esquivar(com_thp, 60, 1 / 3)
    print("  a esquiva so vale a pena no golpe pesado: ok")


def caso_sequencia_do_monge():
    assert motor.proxima_sequencia(0, True, 1, 2) == 1
    assert motor.proxima_sequencia(1, True, 1, 2) == 2
    assert motor.proxima_sequencia(2, True, 1, 2) == 2, "nao passa do teto"
    assert motor.proxima_sequencia(2, False, 1, 2) == 0, "errar zera"
    print("  a sequencia do Martial Arts empilha ate o teto e zera no erro: ok")


def caso_atordoado_perde_a_vez():
    grupo = [motor.Combatente(1, "A", 15, 0, "1d1", 50, 50)]
    inimigos = [
        motor.Inimigo(0, "Um", 10, 40, "1d1", 50, 50),
        motor.Inimigo(1, "Dois", 10, 40, "1d1", 50, 50),
    ]
    estado = motor.EstadoCombate(inimigos, 1, grupo)
    assert len(motor.rodada_dos_inimigos(estado, None).golpes) == 2

    inimigos[0].atordoado = True
    golpes = motor.rodada_dos_inimigos(estado, None).golpes
    assert len(golpes) == 1 and golpes[0][0].atacante == "Dois"
    print("  inimigo atordoado perde a vez: ok")


async def caso_uncanny_dodge_corta_o_golpe():
    conn, canal, cog, incursao, run = await preparar(
        classe="ladino", nivel=8, monstro=MARRETA
    )
    dono = JOGADORES[0]
    passo = cog._passo(run)
    maximo = cl.classe("ladino").numeros(8).hp

    msg = await canal.fetch_message(run["mensagem_id"])
    for _ in range(4):
        atual = await db.buscar_run(conn, run["id"])
        if atual["status"] != "objetivo":
            break
        estado = await cog._estado_combate(atual, incursao.objetivo)
        for c in list(estado.vivos):
            await cog.atacar(FakeInteraction(canal, c.user_id, msg), run["id"], "OBJ")
        if any("Uncanny Dodge" in (m.content or "") for m in canal.mensagens):
            break
        # volta todo mundo ao topo para a proxima tentativa
        for user_id in JOGADORES[:2]:
            await db.definir_hp(conn, run["id"], user_id, maximo)

    assert any("Uncanny Dodge" in (m.content or "") for m in canal.mensagens), [
        m.content for m in canal.mensagens if m.content
    ]
    # gastou o uso do combate
    gastos = {}
    for user_id in JOGADORES[:2]:
        gastos.update(await db.usos_da_run(conn, run["id"], user_id))
    assert gastos.get(("uncanny_dodge", f"combate:{passo}")) == 1, gastos
    print("  Uncanny Dodge corta o golpe pesado e gasta o uso: ok")


async def caso_stunning_strike_atordoa_ou_devolve():
    conn, canal, cog, incursao, run = await preparar(classe="monge", nivel=6)
    dono = JOGADORES[0]
    passo = cog._passo(run)

    inter = FakeInteraction(canal, dono)
    await cog.usar_habilidade(inter, run["id"], "OBJ", "stunning_strike")

    gastos = await db.usos_da_run(conn, run["id"], dono)
    acertou = any("atordoado" in (m.content or "") for m in canal.mensagens)
    if acertou:
        # o inimigo perde a proxima vez
        ligados = await db.efeitos_ativos(conn, run["id"], passo, 0)
        assert any(e["efeito"] == "atordoado" for e in ligados), ligados
        estado = await cog._estado_combate(
            await db.buscar_run(conn, run["id"]), incursao.objetivo
        )
        assert estado.inimigos[0].atordoado
        assert gastos.get(("stunning_strike", f"descanso:0")) == 1
    else:
        # errou: o uso volta, porque so gasta quando acerta
        assert gastos.get(("stunning_strike", "descanso:0"), 0) == 0, gastos
    print(f"  Stunning Strike {'atordoou' if acertou else 'errou e devolveu o uso'}: ok")


async def caso_martial_arts_sobe_dentro_do_turno():
    conn, canal, cog, incursao, run = await preparar(classe="monge", nivel=6)
    dono = JOGADORES[0]
    passo = cog._passo(run)
    msg = await canal.fetch_message(run["mensagem_id"])

    # o monstro tem CA 1: os dois golpes do turno acertam (fora o 1 natural)
    await cog.atacar(FakeInteraction(canal, dono, msg), run["id"], "OBJ")
    pilha = await cog._pilha_de_sequencia(run, dono, passo)
    assert pilha in (0, 1, 2), pilha

    golpes = await db.ataques_da_rodada(conn, run["id"], passo, 1)
    assert len(golpes) == 2, "o Monge do tier 3 bate duas vezes"
    # o bonus do segundo golpe e maior que o do primeiro quando o primeiro acerta
    primeiro, segundo = golpes
    if primeiro["d20"] != 1:
        assert segundo["bonus"] == primeiro["bonus"] + 1, (primeiro, segundo)
    else:
        assert segundo["bonus"] == primeiro["bonus"]
    print("  Martial Arts soma no golpe seguinte, dentro do mesmo turno: ok")


async def main():
    try:
        caso_quando_vale_esquivar()
        caso_sequencia_do_monge()
        caso_atordoado_perde_a_vez()
        await caso_uncanny_dodge_corta_o_golpe()
        await caso_stunning_strike_atordoa_ou_devolve()
        await caso_martial_arts_sobe_dentro_do_turno()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        (Path(__file__).resolve().parent / "teste_reacoes.db").unlink(missing_ok=True)


asyncio.run(main())
print("TESTES DE REACOES PASSARAM")
