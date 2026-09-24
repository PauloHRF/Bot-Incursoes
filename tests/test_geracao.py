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
    """O sorteio nunca repete dentro do passo nem oferece sala ja visitada."""
    rng = random.Random(11)
    banco = salas_falsas(12)

    passo = motor.sortear_passo(banco, rng=rng)
    assert len(passo) == OPCOES_POR_PASSO and len(set(passo)) == OPCOES_POR_PASSO

    # o que ja foi visitado sai do bolo
    visitadas = ["S0", "S1", "S2", "S3"]
    for _ in range(30):
        passo = motor.sortear_passo(banco, visitadas, rng=rng)
        assert not (set(passo) & set(visitadas)), passo
        assert len(set(passo)) == OPCOES_POR_PASSO

    # sobrando menos que 3 salas novas, o passo sai menor em vez de repetir
    quase_tudo = [f"S{i}" for i in range(10)]
    passo = motor.sortear_passo(banco, quase_tudo, rng=rng)
    assert sorted(passo) == ["S10", "S11"], passo

    # sem sala nova nenhuma, o sorteio recusa em vez de reoferecer
    try:
        motor.sortear_passo(banco, [f"S{i}" for i in range(12)], rng=rng)
    except ValueError as exc:
        assert "passou por todas" in str(exc)
    else:
        raise AssertionError("deveria recusar quando o banco acabou")

    # duas runs do mesmo banco dao caminhos diferentes
    a = motor.sortear_passo(banco, rng=random.Random(1))
    b = motor.sortear_passo(banco, rng=random.Random(2))
    assert a != b, "o caminho deveria variar entre runs"
    print("  sorteio: sem repetição no passo, varia entre runs: ok")


async def atravessar(conn, canal, cog, run, incursao, ate=None):
    """Leva o grupo passo a passo, sempre pela primeira opção. Devolve as visitadas."""
    escolhidas = []
    for passo in range(1, (ate or incursao.passos) + 1):
        run = await db.buscar_run(conn, run["id"])
        if run["status"] != "escolhendo":
            break
        alvo = (await cog._opcoes(run, passo))[0]
        escolhidas.append(alvo.id)
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
    return escolhidas


async def caso_sala_visitada_nao_volta():
    """Uma sala atravessada some do sorteio dos passos seguintes."""
    conn, canal, cog = await preparar()
    # banco justo: 5 passos e 6 salas, entao o sorteio precisa mesmo se virar
    incursao, _ = montar_conteudo(cog, tamanho="Média", salas=salas_sem_combate(6))
    run = await montar_run(conn, canal, cog)

    # no comeco so o primeiro passo esta sorteado: o caminho e gerado passo a passo
    assert len(await db.mapa_da_run(conn, run["id"])) == 1

    escolhidas = await atravessar(conn, canal, cog, run, incursao)
    assert len(escolhidas) == incursao.passos
    assert len(set(escolhidas)) == len(escolhidas), f"o grupo repetiu sala: {escolhidas}"
    assert await db.salas_visitadas(conn, run["id"]) == escolhidas

    # nenhuma opcao de um passo era uma sala ja visitada antes dele
    mapa = await db.mapa_da_run(conn, run["id"])
    for indice, opcoes in enumerate(mapa):
        ja_vistas = set(escolhidas[:indice])
        assert not (set(opcoes) & ja_vistas), (indice, opcoes, ja_vistas)
    print("  sala visitada não volta a ser oferecida: ok")


async def caso_tamanhos():
    """Curta, média e longa geram 3, 5 e 7 passos."""
    for tamanho, esperado in TAMANHOS.items():
        conn, canal, cog = await preparar()
        incursao, _ = montar_conteudo(
            cog, tamanho=tamanho, salas=salas_sem_combate(esperado * OPCOES_POR_PASSO)
        )
        assert incursao.passos == esperado
        run = await montar_run(conn, canal, cog)

        # o caminho e sorteado passo a passo, entao so o primeiro nasce com a run
        assert len(await db.mapa_da_run(conn, run["id"])) == 1
        await atravessar(conn, canal, cog, run, incursao)

        mapa = await db.mapa_da_run(conn, run["id"])
        assert len(mapa) == esperado, f"{tamanho}: esperava {esperado} passos, veio {len(mapa)}"
        assert all(len(p) == OPCOES_POR_PASSO for p in mapa)
        assert (await db.buscar_run(conn, run["id"]))["status"] == "objetivo"
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
        await caso_sala_visitada_nao_volta()
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
