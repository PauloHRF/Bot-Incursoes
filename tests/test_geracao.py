"""Dungeon gerada: tamanhos, sorteio do caminho e as duas lores."""
from __future__ import annotations

import asyncio
import random
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import config, database as db, motor  # noqa: E402
from src.cogs.incursao import Incursoes  # noqa: E402
from src.incursoes import OPCOES_POR_PASSO, TAMANHOS, Sala  # noqa: E402
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


def salas_falsas(quantas):
    return [
        Sala(id=f"S{i}", nome=f"Sala {i}", tipo="Evento", descricao="x")
        for i in range(quantas)
    ]


async def preparar():
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass
    config.DB_PATH = Path(__file__).resolve().parent / "teste_geracao.db"
    config.DB_PATH.unlink(missing_ok=True)
    config.TAMANHO_GRUPO = 5
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    await criar_grupo(conn)
    canal = FakeCanal(CANAL)
    return conn, canal, Incursoes(FakeBot(conn, canal))


async def montar_run(conn, canal, cog, incursao_id="t"):
    await cog.entrar.callback(cog, FakeInteraction(canal, JOGADORES[0]), incursao_id)
    run = await db.run_do_canal(conn, CANAL)
    msg = await canal.fetch_message(run["mensagem_id"])
    for user_id in JOGADORES[1:]:
        await cog.recrutar(FakeInteraction(canal, user_id, msg), run["id"], "entrar")
    return await db.buscar_run(conn, run["id"])


def caso_sorteio_puro():
    """O sorteio nunca repete dentro do passo e sempre entrega o caminho pedido."""
    rng = random.Random(11)

    # banco folgado: 7 passos x 3 = 21, e o banco tem 21
    mapa = motor.sortear_mapa(salas_falsas(21), 7, rng=rng)
    assert len(mapa) == 7
    assert all(len(set(p)) == OPCOES_POR_PASSO for p in mapa)
    todos = [s for p in mapa for s in p]
    assert len(set(todos)) == 21, "com banco exato, nenhuma sala se repete na run"

    # banco apertado: repete entre passos, nunca dentro de um
    mapa = motor.sortear_mapa(salas_falsas(4), 5, rng=rng)
    assert len(mapa) == 5
    assert all(len(set(p)) == OPCOES_POR_PASSO for p in mapa)

    # o minimo possivel
    mapa = motor.sortear_mapa(salas_falsas(3), 3, rng=rng)
    assert all(sorted(p) == ["S0", "S1", "S2"] for p in mapa)

    # banco menor que um passo nao monta caminho
    try:
        motor.sortear_mapa(salas_falsas(2), 3, rng=rng)
    except ValueError as exc:
        assert "ao menos" in str(exc)
    else:
        raise AssertionError("deveria recusar banco menor que um passo")

    # duas runs do mesmo banco dão caminhos diferentes
    banco = salas_falsas(15)
    a = motor.sortear_mapa(banco, 5, rng=random.Random(1))
    b = motor.sortear_mapa(banco, 5, rng=random.Random(2))
    assert a != b, "o caminho deveria variar entre runs"
    print("  sorteio: sem repetição no passo, varia entre runs: ok")


async def caso_tamanhos():
    """Curta, média e longa geram 3, 5 e 7 passos."""
    for tamanho, esperado in TAMANHOS.items():
        conn, canal, cog = await preparar()
        incursao, _ = montar_conteudo(
            cog, tamanho=tamanho, salas=salas_sem_combate(esperado * OPCOES_POR_PASSO)
        )
        assert incursao.passos == esperado
        run = await montar_run(conn, canal, cog)

        mapa = await db.mapa_da_run(conn, run["id"])
        assert len(mapa) == esperado, f"{tamanho}: esperava {esperado} passos, veio {len(mapa)}"
        assert all(len(p) == OPCOES_POR_PASSO for p in mapa)
        # com banco folgado, nenhuma sala se repete no caminho inteiro
        achatado = [s for p in mapa for s in p]
        assert len(set(achatado)) == len(achatado)
    print(f"  tamanhos {', '.join(f'{t}={n}' for t, n in TAMANHOS.items())}: ok")


async def caso_lore_abre_e_fecha():
    """A lore de abertura sai ao começar; a de fecho só na vitória."""
    conn, canal, cog = await preparar()
    incursao, _ = montar_conteudo(
        cog, tamanho="Curta", salas=salas_sem_combate(9), lore_final="Epílogo combinado."
    )
    run = await montar_run(conn, canal, cog)

    from src.embeds import chamada

    titulos = [m.embeds[0].title for m in canal.mensagens if m.embeds]
    assert any(incursao.nome in (t or "") for t in titulos), titulos
    descricoes = [m.embeds[0].description for m in canal.mensagens if m.embeds]
    # o recrutamento mostra so o gancho; a abertura mostra a lore inteira
    assert descricoes.count(chamada(incursao.lore_inicial)) == 1
    assert descricoes.count(incursao.lore_inicial) == 1
    assert chamada(incursao.lore_inicial) != incursao.lore_inicial
    assert not any("epílogo" in (t or "").lower() for t in titulos), "epílogo cedo demais"

    # atravessa o caminho e vence o objetivo
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

    run = await db.buscar_run(conn, run["id"])
    assert run["status"] == "objetivo", run["status"]
    for _ in range(20):
        atual = await db.buscar_run(conn, run["id"])
        if atual["status"] != "objetivo":
            break
        estado = await cog._estado_combate(atual, incursao.objetivo)
        msg = await canal.fetch_message(atual["mensagem_id"])
        for c in list(estado.vivos):
            await cog.atacar(FakeInteraction(canal, c.user_id, msg), run["id"], incursao.objetivo.id)

    assert (await db.buscar_run(conn, run["id"]))["status"] == "sucesso"
    fechos = [
        m for m in canal.mensagens
        if m.embeds and m.embeds[0].description == incursao.lore_final
    ]
    assert len(fechos) == 1, "o epílogo sai uma vez, só na vitória"
    print("  lore abre a run e o epílogo só vem com a vitória: ok")


async def caso_sala_repetida_tem_estado_proprio():
    """A mesma sala sorteada em dois passos é um desafio novo a cada visita."""
    conn, canal, cog = await preparar()
    # banco do tamanho exato de um passo: os 3 passos oferecem as mesmas 3 salas
    incursao, banco = montar_conteudo(cog, tamanho="Curta", salas=salas_sem_combate(3))
    run = await montar_run(conn, canal, cog)

    mapa = await db.mapa_da_run(conn, run["id"])
    assert len(mapa) == 3 and all(sorted(p) == sorted(mapa[0]) for p in mapa)

    escolhida = (await cog._opcoes(run, 1))[0].id
    for passo in (1, 2):
        run = await db.buscar_run(conn, run["id"])
        assert run["linha_atual"] == passo
        msg = await canal.fetch_message(run["mensagem_id"])
        for user_id in JOGADORES:
            await cog.votar(FakeInteraction(canal, user_id, msg), run["id"], passo, escolhida)

        atual = await db.buscar_run(conn, run["id"])
        assert atual["sala_atual"] == escolhida
        msg_sala = await canal.fetch_message(atual["mensagem_id"])
        rolou = False
        for user_id in JOGADORES:
            agora = await db.buscar_run(conn, run["id"])
            if agora["status"] != "em_sala":
                break
            inter = FakeInteraction(canal, user_id, msg_sala)
            await cog.rolar(inter, run["id"], escolhida)
            # a segunda visita nao pode dizer "ja rolou"
            assert "🎲" in inter.resposta, (passo, inter.resposta)
            rolou = True
        assert rolou, f"passo {passo}: ninguém conseguiu rolar na sala repetida"

        registros = await db.testes_da_sala(conn, run["id"], passo)
        assert registros, f"passo {passo} sem rolagens gravadas"

    print("  sala repetida em outro passo começa do zero: ok")


async def caso_sem_banco_nao_comeca():
    """Sem banco da Organização, a run avisa em vez de quebrar."""
    conn, canal, cog = await preparar()
    montar_conteudo(cog, salas=salas_sem_combate())
    cog.bancos.clear()  # como se o JSON do banco não estivesse carregado

    run = await montar_run(conn, canal, cog)
    assert run["status"] == "recrutando", "sem banco, a run não começa"
    assert any("banco de salas" in (m.content or "") for m in canal.mensagens)
    assert await db.mapa_da_run(conn, run["id"]) == []
    print("  sem banco carregado, o bot avisa e não começa: ok")


async def main():
    try:
        caso_sorteio_puro()
        await caso_tamanhos()
        await caso_lore_abre_e_fecha()
        await caso_sala_repetida_tem_estado_proprio()
        await caso_sem_banco_nao_comeca()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        (Path(__file__).resolve().parent / "teste_geracao.db").unlink(missing_ok=True)


asyncio.run(main())
print("TESTES DE GERACAO PASSARAM")
