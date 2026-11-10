"""Encerrar a incursão na mão: o comando de quem administra.

O `/incursao desistir` é do grupo e precisa de maioria. Há casos em que não há
grupo para votar: a sessão morreu, a run ficou presa, ou ela foi aberta por
engano. O `/incursao encerrar` fecha a run sem votação, e **decide o que ela
deixa** em duas perguntas:

- `pagar`: o ouro das salas vencidas e os pontos de participação saem, ou não
  sai nada e a run some como se não tivesse acontecido;
- `devolver_vaga`: a semana é cobrada do grupo, ou volta e eles podem entrar
  em outra incursão hoje.

Os dois são **obrigatórios**. A ação não tem volta e cada um move ouro ou a
semana de cinco pessoas: um padrão silencioso decidiria isso no lugar de quem
administra.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import config, database as db  # noqa: E402
from src.cogs.incursao import Incursoes  # noqa: E402
from fakes import (  # noqa: E402
    CANAL,
    GUILD,
    JOGADORES,
    FakeBot,
    FakeCanal,
    FakeInteraction,
    criar_grupo,
    leu,
    montar_conteudo,
    salas_sem_combate,
)

BANCO = Path(__file__).resolve().parent / "teste_encerrar.db"
_ABERTAS = []


async def preparar():
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass
    config.DB_PATH = BANCO
    BANCO.unlink(missing_ok=True)
    config.TAMANHO_GRUPO = 5
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    ids = await criar_grupo(conn, nivel=8)
    canal = FakeCanal(CANAL)
    cog = Incursoes(FakeBot(conn, canal))
    incursao, _ = montar_conteudo(cog, tamanho="Curta", salas=salas_sem_combate())
    return conn, canal, cog, incursao, ids


async def run_no_meio(conn, canal, cog, incursao, salas_vencidas=2):
    """Uma run começada, com algumas salas já vencidas e a semana marcada."""
    run_id = await db.criar_run(conn, GUILD, CANAL, incursao.id, JOGADORES[0])
    for user_id in JOGADORES:
        p = await db.personagem_por_nome(conn, GUILD, user_id, f"Heroi{user_id}")
        await db.adicionar_participante(conn, run_id, user_id, p["id"])
    await db.inicializar_hp(conn, run_id)
    # A semana e cobrada quando a run COMECA: e isso que `devolver_vaga` desfaz.
    await db.marcar_ultima_incursao(conn, GUILD, list(JOGADORES))
    for passo in range(1, salas_vencidas + 1):
        await db.registrar_visita(conn, run_id, passo, f"S{passo}")
        await db.marcar_sala_superada(conn, run_id, passo, f"S{passo}")
    await db.atualizar_run(
        conn, run_id, status="escolhendo", linha_atual=salas_vencidas + 1
    )
    return await db.buscar_run(conn, run_id)


async def ouro_total(conn, ids):
    return sum([await db.ouro(conn, pid) for pid in ids.values()])


async def sem_vaga(conn):
    """Quem ainda tem a semana marcada."""
    async with conn.execute(
        "SELECT user_id FROM jogadores"
        " WHERE guild_id = ? AND ultima_incursao IS NOT NULL", (GUILD,),
    ) as cur:
        return {r["user_id"] for r in await cur.fetchall()}


async def _fechar(conn):
    await conn.close()
    BANCO.unlink(missing_ok=True)


async def caso_encerrar_pagando_deixa_o_que_as_salas_pagaram():
    """`pagar: sim` — o grupo leva o ouro das salas vencidas e os pontos."""
    conn, canal, cog, incursao, ids = await preparar()
    run = await run_no_meio(conn, canal, cog, incursao)
    antes = await ouro_total(conn, ids)
    assert antes == 0, antes

    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.encerrar.callback(cog, inter, pagar=True, devolver_vaga=False)

    atual = await db.buscar_run(conn, run["id"])
    assert atual["status"] == "encerrada", atual["status"]
    assert await ouro_total(conn, ids) > antes, "as salas vencidas nao pagaram"
    lancamentos, _total = await cog._balanco(atual)
    assert any(
        l["motivo"] == "Participação na incursão" for l in lancamentos
    ), lancamentos
    # A semana segue cobrada: foi o que o moderador escolheu.
    assert await sem_vaga(conn) == set(JOGADORES)
    assert "As salas vencidas pagaram" in (leu(inter) or ""), leu(inter)

    await _fechar(conn)
    print("  encerrar pagando deixa o ouro das salas e os pontos: ok")


async def caso_encerrar_sem_pagar_nao_deixa_nada():
    """`pagar: não` — nem ouro nem pontos. A run sai como se não tivesse sido."""
    conn, canal, cog, incursao, ids = await preparar()
    run = await run_no_meio(conn, canal, cog, incursao)

    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.encerrar.callback(cog, inter, pagar=False, devolver_vaga=False)

    atual = await db.buscar_run(conn, run["id"])
    assert atual["status"] == "encerrada", atual["status"]
    assert await ouro_total(conn, ids) == 0, "pagou ouro com `pagar: nao`"
    lancamentos, total = await cog._balanco(atual)
    assert not lancamentos and total == 0, (lancamentos, total)
    assert "Nada foi pago" in (leu(inter) or ""), leu(inter)

    await _fechar(conn)
    print("  encerrar sem pagar nao deixa ouro nem ponto: ok")


async def caso_a_vaga_da_semana_e_opcao_separada():
    """As duas perguntas são independentes: dá para pagar e devolver a vaga.

    Elas não andam juntas de propósito — pagar o que o grupo jogou e ainda
    assim não cobrar a semana é um caso real, de uma run que travou por culpa
    do bot.
    """
    conn, canal, cog, incursao, ids = await preparar()
    await run_no_meio(conn, canal, cog, incursao)
    # Alguem de FORA da run, com a semana marcada por outra incursao: a vaga do
    # grupo voltando nao pode levar a marca dele junto. Sem este jogador, apagar
    # a guilda inteira e apagar so o grupo dao o mesmo resultado.
    de_fora = 4242
    await db.marcar_ultima_incursao(conn, GUILD, [de_fora])
    assert await sem_vaga(conn) == set(JOGADORES) | {de_fora}

    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.encerrar.callback(cog, inter, pagar=True, devolver_vaga=True)

    assert await sem_vaga(conn) == {de_fora}, (
        "a devolucao da vaga passou por cima de quem nao estava na run"
    )
    assert await ouro_total(conn, ids) > 0, "devolver a vaga nao podia tirar o ouro"
    texto = leu(inter) or ""
    assert "vaga da semana voltou" in texto, texto
    assert f"{len(JOGADORES)} jogador" in texto, texto

    await _fechar(conn)
    print("  a vaga da semana e opcao separada do pagamento: ok")


async def caso_quem_recebeu_a_vaga_pode_entrar_de_novo():
    """Devolver a vaga tem de destravar a entrada de verdade, e não só a coluna."""
    conn, canal, cog, incursao, ids = await preparar()
    await run_no_meio(conn, canal, cog, incursao)
    dono = JOGADORES[0]
    assert await cog._motivo_de_bloqueio(GUILD, dono) is not None, (
        "a semana tinha de estar bloqueando"
    )

    inter = FakeInteraction(canal, dono)
    await cog.encerrar.callback(cog, inter, pagar=False, devolver_vaga=True)
    assert await cog._motivo_de_bloqueio(GUILD, dono) is None, (
        "a vaga voltou na tabela e o bloqueio continuou"
    )

    await _fechar(conn)
    print("  quem recebeu a vaga de volta pode entrar em outra: ok")


async def caso_sem_devolver_a_vaga_o_bloqueio_fica():
    """`devolver_vaga: não` — a semana foi gasta e fica gasta."""
    conn, canal, cog, incursao, ids = await preparar()
    await run_no_meio(conn, canal, cog, incursao)
    dono = JOGADORES[0]

    inter = FakeInteraction(canal, dono)
    await cog.encerrar.callback(cog, inter, pagar=True, devolver_vaga=False)
    assert await cog._motivo_de_bloqueio(GUILD, dono) is not None, (
        "a vaga voltou sem ninguem pedir"
    )
    assert await sem_vaga(conn) == set(JOGADORES)
    assert "segue gasta" in (leu(inter) or ""), leu(inter)

    await _fechar(conn)
    print("  sem devolver a vaga, a semana segue gasta: ok")


async def caso_encerrar_fecha_a_run_para_todo_efeito():
    """Encerrada, a run sai do caminho: o canal fica livre e os botões morrem."""
    conn, canal, cog, incursao, ids = await preparar()
    run = await run_no_meio(conn, canal, cog, incursao)

    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.encerrar.callback(cog, inter, pagar=False, devolver_vaga=False)

    # `run_do_canal` so acha run VIVA: o canal esta livre para outra.
    assert await db.run_do_canal(conn, CANAL) is None, "a run continua viva no canal"
    # E o cartao do desfecho foi para o canal, dizendo as duas decisoes.
    cartoes = [
        m for m in canal.mensagens
        if m.embeds and "encerrada" in (m.embeds[0].title or "")
    ]
    assert cartoes, "o grupo nao recebeu o cartao do desfecho"
    descricao = cartoes[-1].embeds[0].description or ""
    assert "Nada foi pago" in descricao, descricao
    assert "segue gasta" in descricao, descricao

    await _fechar(conn)
    print("  encerrada, a run libera o canal e o cartao explica: ok")


async def caso_so_vale_onde_ha_run():
    """Sem run no canal o comando avisa, e não encerra nada por acidente."""
    conn, canal, cog, incursao, ids = await preparar()
    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.encerrar.callback(cog, inter, pagar=True, devolver_vaga=True)
    assert "Não há incursão" in (leu(inter) or ""), leu(inter)
    assert await sem_vaga(conn) == set(), "mexeu na semana sem run nenhuma"

    await _fechar(conn)
    print("  sem run no canal, o comando nao encerra nada: ok")


async def caso_e_de_admin_e_nao_precisa_estar_na_run():
    """Quem administra encerra a run do canal mesmo sem estar nela.

    É justamente o caso de limpar uma run presa: quem administra pode não ter
    jogado. E o comando é de admin pela permissão declarada, que é o mesmo
    portão do `/incursao recarregar` — não por um `if` dentro dele.
    """
    import discord

    conn, canal, cog, incursao, ids = await preparar()
    await run_no_meio(conn, canal, cog, incursao)
    de_fora = 9999
    assert not await db.esta_na_run(
        conn, (await db.run_do_canal(conn, CANAL))["id"], de_fora
    )

    inter = FakeInteraction(canal, de_fora)
    await cog.encerrar.callback(cog, inter, pagar=False, devolver_vaga=False)
    assert await db.run_do_canal(conn, CANAL) is None, (
        f"quem administra nao conseguiu encerrar de fora: {leu(inter)}"
    )

    # A permissao declarada e a mesma do `recarregar`: e ela que esconde o
    # comando de quem nao administra, no proprio Discord.
    exigida = discord.Permissions(manage_guild=True)
    assert cog.encerrar.default_permissions == exigida, cog.encerrar.default_permissions
    assert cog.recarregar.default_permissions == exigida

    await _fechar(conn)
    print("  e de admin, e encerra mesmo sem estar na run: ok")


async def main():
    try:
        await caso_encerrar_pagando_deixa_o_que_as_salas_pagaram()
        await caso_encerrar_sem_pagar_nao_deixa_nada()
        await caso_a_vaga_da_semana_e_opcao_separada()
        await caso_quem_recebeu_a_vaga_pode_entrar_de_novo()
        await caso_sem_devolver_a_vaga_o_bloqueio_fica()
        await caso_encerrar_fecha_a_run_para_todo_efeito()
        await caso_so_vale_onde_ha_run()
        await caso_e_de_admin_e_nao_precisa_estar_na_run()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        BANCO.unlink(missing_ok=True)


asyncio.run(main())
print("TESTES DE ENCERRAR PASSARAM")
