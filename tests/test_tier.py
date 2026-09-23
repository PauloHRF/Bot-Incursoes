"""Tier da incursão: quem está abaixo entra, quem está acima fica de fora."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import config, database as db, embeds as E, motor  # noqa: E402
from src.cogs.incursao import Incursoes, SeletorPersonagemEntrada  # noqa: E402
from src.rules import TIER_MAXIMO, faixa_do_tier, tier  # noqa: E402
from fakes import (  # noqa: E402
    CLASSE_PADRAO,
    CANAL,
    GUILD,
    JOGADORES,
    TREINADAS,
    FakeBot,
    FakeCanal,
    FakeInteraction,
    montar_conteudo,
    salas_sem_combate,
)

_ABERTAS = []


async def preparar(tier_incursao=None):
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass
    config.DB_PATH = Path(__file__).resolve().parent / "teste_tier.db"
    config.DB_PATH.unlink(missing_ok=True)
    config.TAMANHO_GRUPO = 5
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    canal = FakeCanal(CANAL)
    cog = Incursoes(FakeBot(conn, canal))
    incursao, _ = montar_conteudo(cog, tier=tier_incursao, salas=salas_sem_combate())
    return conn, canal, cog, incursao


async def heroi(conn, user_id, nome, nivel):
    return await db.criar_personagem(
        conn, GUILD, user_id, nome, CLASSE_PADRAO, TREINADAS, nivel=nivel
    )


def caso_tier_a_cada_dois_niveis():
    """A conta do tier e a faixa de níveis que ele cobre."""
    assert [tier(n) for n in (1, 2, 3, 4, 5, 6, 7, 8)] == [1, 1, 2, 2, 3, 3, 4, 4]
    assert tier(19) == tier(20) == TIER_MAXIMO
    assert faixa_do_tier(1) == (1, 2) and faixa_do_tier(4) == (7, 8)
    # nivel fora da tabela nao estoura: fica preso nas pontas
    assert tier(0) == 1 and tier(99) == TIER_MAXIMO
    print("  tier: um a cada 2 níveis, 1-2 = tier 1: ok")


def caso_so_sobe_quem_esta_abaixo():
    """Abaixo do tier da incursão pode; acima, não."""
    for nivel in (1, 2, 5, 6, 7, 8):  # tier 1 ate 4
        assert motor.pode_encarar(nivel, 4), nivel
    for nivel in (9, 10, 11, 20):  # tier 5 em diante
        assert not motor.pode_encarar(nivel, 4), nivel
    # uma incursão de tier 1 só aceita quem está começando
    assert motor.pode_encarar(2, 1) and not motor.pode_encarar(3, 1)
    # o tier maximo é a incursão aberta a todo mundo
    assert all(motor.pode_encarar(n, TIER_MAXIMO) for n in range(1, 21))
    print("  quem está acima do tier não encara a incursão: ok")


async def caso_entrar_recusa_quem_esta_acima():
    conn, canal, cog, incursao = await preparar(tier_incursao=3)  # ate o nivel 6
    dono = JOGADORES[0]
    await heroi(conn, dono, "Veterano", 12)

    inter = FakeInteraction(canal, dono)
    await cog.entrar.callback(cog, inter, "t")
    assert "tier 3" in inter.resposta and "tier 5" in inter.resposta, inter.resposta
    assert "Veterano" in inter.resposta
    assert await db.run_do_canal(conn, CANAL) is None, "não podia ter aberto a run"
    print("  /incursao entrar barra o personagem acima do tier: ok")


async def caso_entrar_escolhe_o_que_cabe():
    """Com vários personagens, o bot leva o único que cabe no tier."""
    conn, canal, cog, incursao = await preparar(tier_incursao=2)  # ate o nivel 4
    dono = JOGADORES[0]
    await heroi(conn, dono, "Veterano", 12)
    novato = await heroi(conn, dono, "Novato", 3)

    inter = FakeInteraction(canal, dono)
    await cog.entrar.callback(cog, inter, "t")
    run = await db.run_do_canal(conn, CANAL)
    assert run is not None, "com um personagem elegível, a run abre"
    escolhidos = await db.personagens_da_run(conn, run["id"])
    assert [p["id"] for p in escolhidos] == [novato], escolhidos

    # pedir o veterano pelo nome continua sendo recusado
    conn, canal, cog, incursao = await preparar(tier_incursao=2)
    await heroi(conn, dono, "Veterano", 12)
    await heroi(conn, dono, "Novato", 3)
    pedido = FakeInteraction(canal, dono)
    await cog.entrar.callback(cog, pedido, "t", personagem="Veterano")
    assert "Veterano" in pedido.resposta and "tier 2" in pedido.resposta
    assert await db.run_do_canal(conn, CANAL) is None
    print("  entrar leva o personagem que cabe, e recusa o pedido fora do tier: ok")


async def caso_botao_entrar_respeita_o_tier():
    conn, canal, cog, incursao = await preparar(tier_incursao=3)  # ate o nivel 6
    anfitriao, visitante, misto = JOGADORES[0], JOGADORES[1], JOGADORES[2]
    await heroi(conn, anfitriao, "Anfitriao", 5)
    await heroi(conn, visitante, "Grandao", 14)
    await heroi(conn, misto, "Um", 2)
    await heroi(conn, misto, "Dois", 6)
    await heroi(conn, misto, "Alto", 20)

    await cog.entrar.callback(cog, FakeInteraction(canal, anfitriao), "t")
    run = await db.run_do_canal(conn, CANAL)
    msg = await canal.fetch_message(run["mensagem_id"])

    # so tem personagem acima do tier: nao entra
    barrado = FakeInteraction(canal, visitante, msg)
    await cog.recrutar(barrado, run["id"], "entrar")
    assert "tier 3" in barrado.resposta and "Grandao" in barrado.resposta
    assert not await db.esta_na_run(conn, run["id"], visitante)

    # tem tres personagens, mas o menu so oferece os dois que cabem
    escolha = FakeInteraction(canal, misto, msg)
    await cog.recrutar(escolha, run["id"], "entrar")
    view = escolha.view_enviada
    assert isinstance(view, SeletorPersonagemEntrada)
    rotulos = {o.label for o in view.menu.options}
    assert rotulos == {"Um", "Dois"}, rotulos
    print("  o botão Entrar filtra o menu pelo tier: ok")


async def caso_menu_velho_nao_fura_a_regra():
    """O menu fica aberto por minutos: a checagem se repete na hora de efetivar."""
    conn, canal, cog, incursao = await preparar(tier_incursao=3)
    anfitriao, esperto = JOGADORES[0], JOGADORES[1]
    await heroi(conn, anfitriao, "Anfitriao", 5)
    pequeno = await heroi(conn, esperto, "Pequeno", 4)
    await heroi(conn, esperto, "Outro", 6)

    await cog.entrar.callback(cog, FakeInteraction(canal, anfitriao), "t")
    run = await db.run_do_canal(conn, CANAL)

    # o personagem sobe de nivel depois que o menu ja estava na tela
    await db.atualizar_personagem(conn, pequeno, "nivel", 15)
    tarde = FakeInteraction(canal, esperto)
    await cog.efetivar_entrada(tarde, run["id"], pequeno)
    assert "tier 3" in tarde.resposta, tarde.resposta
    assert not await db.esta_na_run(conn, run["id"], esperto)
    print("  menu velho não fura a regra do tier: ok")


async def caso_incursao_sem_tier_e_aberta():
    conn, canal, cog, incursao = await preparar()  # sem tier na planilha
    assert incursao.tier == TIER_MAXIMO and incursao.aberta_a_todos
    dono = JOGADORES[0]
    await heroi(conn, dono, "Lenda", 20)

    inter = FakeInteraction(canal, dono)
    await cog.entrar.callback(cog, inter, "t")
    run = await db.run_do_canal(conn, CANAL)
    assert run is not None and await db.esta_na_run(conn, run["id"], dono)

    # e o recrutamento diz isso, em vez de deixar o grupo adivinhar
    texto = E.exigencia_de_tier(incursao)
    assert "livre" in texto, texto
    print("  incursão sem tier declarado fica aberta a todos: ok")


async def caso_recrutamento_mostra_o_tier():
    conn, canal, cog, incursao = await preparar(tier_incursao=4)
    dono = JOGADORES[0]
    await heroi(conn, dono, "Heroi", 7)
    await cog.entrar.callback(cog, FakeInteraction(canal, dono), "t")
    run = await db.run_do_canal(conn, CANAL)
    msg = await canal.fetch_message(run["mensagem_id"])
    campos = {f.name: f.value for f in msg.embeds[0].fields}
    assert "Quem pode entrar" in campos, campos
    assert "Tier 4" in campos["Quem pode entrar"]
    assert "tier 4 ou menos" in campos["Quem pode entrar"]

    # e a listagem tambem, para escolher antes de abrir
    listagem = FakeInteraction(canal, dono)
    await cog.listar.callback(cog, listagem)
    valores = " ".join(f.value for f in listagem._mensagem_resposta.embeds[0].fields)
    assert "Tier 4" in valores, valores
    print("  recrutamento e listagem dizem o tier: ok")


async def main():
    try:
        caso_tier_a_cada_dois_niveis()
        caso_so_sobe_quem_esta_abaixo()
        await caso_entrar_recusa_quem_esta_acima()
        await caso_entrar_escolhe_o_que_cabe()
        await caso_botao_entrar_respeita_o_tier()
        await caso_menu_velho_nao_fura_a_regra()
        await caso_incursao_sem_tier_e_aberta()
        await caso_recrutamento_mostra_o_tier()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        (Path(__file__).resolve().parent / "teste_tier.db").unlink(missing_ok=True)


asyncio.run(main())
print("TESTES DE TIER PASSARAM")
