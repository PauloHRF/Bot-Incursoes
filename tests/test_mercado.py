"""O mercado: ouro por sala, a vitrine derivada da semana e os cinco slots.

O caso que importa mais aqui é o do domínio: ele é a única coisa que impede o
equipamento de virar cinco fontes do mesmo bônus, e é uma regra de dados, não
de código. Se ela só existisse no comentário, o primeiro item novo a furá-la
passaria em silêncio.
"""
from __future__ import annotations

import asyncio
import collections
import sys

import discord
from datetime import date, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import classes as cl, config, database as db, itens, mercado, motor  # noqa: E402
from src.cogs.incursao import Incursoes  # noqa: E402
from src.cogs.mercado import (  # noqa: E402
    BotaoDeCompra,
    Mercado,
    ViewDaVitrine,
    tentar_comprar,
)
from fakes import (  # noqa: E402
    menu_de,
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
BANCO = Path(__file__).resolve().parent / "teste_mercado.db"


async def preparar(nivel=8, classe="guerreiro"):
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
    ids = await criar_grupo(conn, nivel=nivel, classe=classe)
    canal = FakeCanal(CANAL)
    bot = FakeBot(conn, canal)
    cog = Incursoes(bot)
    # O cog do mercado divide o mesmo bot: os testes de botao precisam dos dois.
    cog.loja = Mercado(bot)
    return conn, canal, cog, ids


# ------------------------------------------------------------- o catálogo


def caso_todo_item_respeita_o_dominio_do_slot():
    """A regra que impede o stack, conferida peça por peça.

    Cada slot manda num número só, então não existe empilhar cinco fontes de
    CA — só cabe uma armadura. O domínio é o que torna isso verdade, e este
    caso é o que torna o domínio uma regra em vez de um comentário.
    """
    furaram = {
        peca.id: itens.fora_do_dominio(peca)
        for peca in itens.CATALOGO
        if itens.fora_do_dominio(peca)
    }
    assert not furaram, furaram

    # E todo domínio só cita chaves que o motor de efeitos entende: chave fora
    # do NEUTRO é descartada em silêncio por `juntar_efeito`.
    from src import habilidades as H

    for slot, chaves in itens.DOMINIO.items():
        desconhecidas = set(chaves) - set(H.NEUTRO)
        assert not desconhecidas, (slot, desconhecidas)
    print(f"  as {len(itens.CATALOGO)} pecas respeitam o dominio do slot: ok")


def caso_o_catalogo_cobre_os_cinco_slots():
    por_slot = collections.Counter(p.slot for p in itens.CATALOGO)
    assert set(por_slot) == set(itens.SLOTS), por_slot
    assert min(por_slot.values()) >= 4, por_slot
    # Id repetido faria POR_ID perder uma peça em silêncio.
    assert len(itens.POR_ID) == len(itens.CATALOGO)
    # Raridade conhecida, e preço saindo dela quando não é dito.
    for peca in itens.CATALOGO:
        assert peca.raridade in itens.RARIDADES, peca.id
        assert peca.custo == (peca.preco or itens.PRECO_BASE[peca.raridade])
        assert peca.nome and peca.texto, peca.id
    print(f"  cinco slots cobertos, {len(itens.POR_ID)} ids unicos: ok")


def caso_o_item_nao_passa_de_dois_de_ca():
    """Teto de calibragem: +2 é o que o melhor domínio de clérigo dá."""
    for peca in itens.CATALOGO:
        assert peca.efeito.get("ca", 0) <= 2, (peca.id, peca.efeito)
    print("  nenhum item passa de +2 de CA: ok")


# -------------------------------------------------------------- a vitrine


def caso_a_vitrine_e_derivada_e_estavel():
    """Mesma dupla, mesma prateleira — é isso que permite não guardá-la."""
    uma = mercado.vitrine(7, "2026-W43")
    outra = mercado.vitrine(7, "2026-W43")
    assert [p.id for p in uma] == [p.id for p in outra]
    assert len(uma) == mercado.VAGAS
    # Sem repetição dentro da mesma prateleira.
    assert len({p.id for p in uma}) == len(uma)
    print("  a vitrine e deterministica e sem repeticao: ok")


def caso_a_vitrine_muda_por_personagem_e_por_semana():
    de_um = [p.id for p in mercado.vitrine(7, "2026-W43")]
    de_outro = [p.id for p in mercado.vitrine(8, "2026-W43")]
    semana_seguinte = [p.id for p in mercado.vitrine(7, "2026-W44")]
    assert de_um != de_outro, "dois personagens veriam a mesma loja"
    assert de_um != semana_seguinte, "a loja nao viraria na semana"
    print("  a prateleira e por personagem e vira na semana: ok")


def caso_a_semana_vira_na_segunda():
    """O mesmo calendário da vaga de incursão, que vira na segunda."""
    domingo = date(2026, 10, 25)   # domingo
    segunda = date(2026, 10, 26)   # segunda
    assert domingo.isoweekday() == 7 and segunda.isoweekday() == 1
    assert mercado.semana_de(domingo) != mercado.semana_de(segunda)
    # Dentro da mesma semana, nada muda.
    assert mercado.semana_de(segunda) == mercado.semana_de(date(2026, 10, 30))
    # E aceita datetime, que é o que o cog tem na mão.
    assert mercado.semana_de(
        datetime(2026, 10, 26, 23, 59, tzinfo=config.FUSO)
    ) == mercado.semana_de(segunda)
    print("  a semana vira na segunda, igual a vaga de incursao: ok")


def caso_o_lendario_e_raro_na_prateleira():
    """A raridade pesa o sorteio: lendário aparece pouco, e aparece."""
    conta = collections.Counter()
    for personagem_id in range(400):
        for peca in mercado.vitrine(personagem_id, "2026-W43"):
            conta[peca.raridade] += 1
    total = sum(conta.values())
    fatia = {r: conta[r] / total for r in itens.RARIDADES}
    assert fatia["comum"] > fatia["incomum"] > fatia["raro"] > fatia["lendario"], fatia
    assert 0 < fatia["lendario"] < 0.10, fatia
    print(
        "  a raridade pesa o sorteio "
        f"(lendario em {fatia['lendario'] * 100:.1f}% das vagas): ok"
    )


def caso_comprar_confere_a_prateleira_de_hoje():
    prateleira = mercado.vitrine(7, "2026-W43")
    assert mercado.esta_na_vitrine(7, "2026-W43", prateleira[0].id)
    fora = next(p for p in itens.CATALOGO if p not in prateleira)
    assert not mercado.esta_na_vitrine(7, "2026-W43", fora.id)
    print("  o que nao esta na vitrine da semana nao e vendido: ok")


# ----------------------------------------------------------------- o ouro


async def caso_o_ouro_e_a_soma_do_livro_caixa():
    conn, _canal, _cog, ids = await preparar()
    heroi = ids[JOGADORES[0]]
    assert await db.ouro(conn, heroi) == 0
    await db.lancar_ouro(conn, heroi, 50, "Sala superada")
    await db.lancar_ouro(conn, heroi, 30, "Sala superada")
    await db.lancar_ouro(conn, heroi, -20, "Compra")
    assert await db.ouro(conn, heroi) == 60
    extrato = await db.extrato_de_ouro(conn, heroi)
    assert [l["ouro"] for l in extrato] == [-20, 30, 50], extrato
    print("  o saldo e a soma, e o extrato sai do mais novo: ok")


async def caso_a_mesma_sala_nunca_paga_duas_vezes():
    conn, _canal, _cog, ids = await preparar()
    heroi = ids[JOGADORES[0]]
    # Run de verdade: o lancamento tem chave estrangeira para runs(id).
    run_id = await db.criar_run(conn, GUILD, CANAL, "t", JOGADORES[0])
    primeira = await db.lancar_ouro(
        conn, heroi, 15, "Sala superada: E1", run_id=run_id, chave="sala:1:E1"
    )
    repetida = await db.lancar_ouro(
        conn, heroi, 15, "Sala superada: E1", run_id=run_id, chave="sala:1:E1"
    )
    assert primeira and not repetida
    assert await db.ouro(conn, heroi) == 15
    # Outra sala da mesma run paga normalmente.
    assert await db.lancar_ouro(
        conn, heroi, 15, "Sala superada: E2", run_id=run_id, chave="sala:1:E2"
    )
    assert await db.ouro(conn, heroi) == 30
    print("  a mesma sala nao paga duas vezes, outra paga: ok")


def caso_o_ouro_escala_por_tier():
    assert mercado.ouro_da_sala(1) == 5 and mercado.ouro_da_sala(3) == 15
    assert mercado.ouro_da_incursao(3) == 60
    # Uma incursão Média de 12 salas mais o fecho, no tier 3.
    rodada = mercado.ouro_da_sala(3) * 12 + mercado.ouro_da_incursao(3)
    assert rodada == 240, rodada
    # Que é três peças comuns, ou um quarto de uma lendária.
    assert rodada // itens.PRECO_BASE["comum"] == 3
    print(f"  o tier 3 tira {rodada} de ouro por incursao Media: ok")


async def caso_a_sala_superada_nao_paga_na_hora():
    """A sala vencida fica registrada, e ninguem recebe nada ainda.

    Antes cada sala pagava na hora, e uma run que acabasse com o grupo
    inteiro no chao deixava o ouro do caminho na bolsa de quem chegou ate
    ali. Agora a incursao paga de uma vez, no fecho, e so se for concluida.
    """
    conn, canal, cog, ids = await preparar()
    montar_conteudo(cog, tamanho="Curta", salas=salas_sem_combate(), tier=3)
    run_id = await db.criar_run(conn, GUILD, CANAL, "t", JOGADORES[0])
    for user_id in JOGADORES[:3]:
        await db.adicionar_participante(conn, run_id, user_id, ids[user_id])
    run = await db.buscar_run(conn, run_id)
    sala = cog._sala(cog._incursao_da_run(run), "E1")

    await cog._marcar_sala_superada(run, sala)
    assert await db.salas_superadas(conn, run_id) == 1
    for user_id in JOGADORES[:3]:
        assert await db.ouro(conn, ids[user_id]) == 0, "a sala pagou na hora"

    # Marcar de novo nao conta duas vezes: os dois caminhos de "sala
    # superada" — o combate e o teste — chamam sem combinar entre si.
    await cog._marcar_sala_superada(run, sala)
    assert await db.salas_superadas(conn, run_id) == 1
    print("  a sala vencida fica registrada e nao paga na hora: ok")


async def caso_a_run_concluida_paga_todos_que_passaram():
    """O fecho paga todo mundo que passou pela run, de pe ou nao.

    Inclusive quem foi ejetado no meio por Exaustao: jogou a incursao. Quem
    desistiu ANTES de ela comecar e que fica de fora.
    """
    conn, canal, cog, ids = await preparar()
    montar_conteudo(cog, tamanho="Curta", salas=salas_sem_combate(), tier=3)
    run_id = await db.criar_run(conn, GUILD, CANAL, "t", JOGADORES[0])
    ficou, ejetado, desistiu = JOGADORES[0], JOGADORES[1], JOGADORES[2]
    for user_id in (ficou, ejetado, desistiu):
        await db.adicionar_participante(conn, run_id, user_id, ids[user_id])

    # um sai no recrutamento (perde o direito), outro e ejetado no meio
    await db.remover_participante(conn, run_id, desistiu)
    await db.tirar_o_direito_ao_ouro(conn, run_id, desistiu)
    await db.remover_participante(conn, run_id, ejetado)

    run = await db.buscar_run(conn, run_id)
    # Duas salas do caminho mais o objetivo, cada uma no passo dela. A marca
    # e por passo: marcar duas salas no MESMO passo marca a mesma linha, que
    # e o que acontece quando a run nao avanca.
    objetivo = cog._incursao_da_run(run).objetivo
    for passo, sala_id in ((1, "E1"), (2, "E2"), (3, objetivo.id)):
        await db.marcar_sala_superada(conn, run_id, passo, sala_id)

    pagos = await cog._pagar_a_run(run)
    assert pagos == 2, f"esperava pagar 2 (o que ficou e o ejetado), pagou {pagos}"

    tier = cog._tier_da_run(run) or 1
    esperado = 3 * mercado.ouro_da_sala(tier) + mercado.ouro_da_incursao(tier)
    assert await db.ouro(conn, ids[ficou]) == esperado
    assert await db.ouro(conn, ids[ejetado]) == esperado, (
        "quem foi ejetado no meio jogou a incursao e recebe igual"
    )
    assert await db.ouro(conn, ids[desistiu]) == 0, (
        "quem desistiu antes de comecar nao recebe"
    )
    assert await db.ouro(conn, ids[JOGADORES[4]]) == 0, "quem nunca entrou"

    # Pagar de novo nao paga de novo: a chave e por run.
    assert await cog._pagar_a_run(run) == 0
    assert await db.ouro(conn, ids[ficou]) == esperado
    print(f"  o fecho paga {esperado} a cada um que passou, uma vez: ok")


# ------------------------------------------------------- comprar e vestir


async def caso_comprar_debita_e_guarda():
    conn, _canal, _cog, ids = await preparar()
    heroi = ids[JOGADORES[0]]
    peca = itens.item("gibao_de_couro")

    # Sem ouro, nao compra.
    assert not await db.comprar(conn, heroi, peca.id, peca.custo)
    assert await db.itens_na_bolsa(conn, heroi) == {}

    await db.lancar_ouro(conn, heroi, 200, "teste")
    assert await db.comprar(conn, heroi, peca.id, peca.custo)
    assert await db.ouro(conn, heroi) == 200 - peca.custo
    assert await db.itens_na_bolsa(conn, heroi) == {peca.id: 1}
    print(f"  comprar debita {peca.custo} e poe na bolsa: ok")


async def caso_equipar_tira_da_bolsa_e_troca_sem_perder():
    conn, _canal, _cog, ids = await preparar()
    heroi = ids[JOGADORES[0]]
    await db.lancar_ouro(conn, heroi, 2000, "teste")
    gibao = itens.item("gibao_de_couro")
    peitoral = itens.item("peitoral_de_serpe")
    await db.comprar(conn, heroi, gibao.id, gibao.custo)
    await db.comprar(conn, heroi, peitoral.id, peitoral.custo)

    vestiu, saiu = await db.equipar(conn, heroi, gibao.id, gibao.slot)
    assert vestiu and saiu is None
    assert await db.equipamento(conn, heroi) == {"armadura": gibao.id}
    # A bolsa so mostra o que tem: a linha do gibao fica com quantidade zero
    # e some da listagem, em vez de aparecer como "x0".
    assert await db.itens_na_bolsa(conn, heroi) == {peitoral.id: 1}

    # Trocar devolve a antiga para a bolsa, nao a perde.
    vestiu, saiu = await db.equipar(conn, heroi, peitoral.id, peitoral.slot)
    assert vestiu and saiu == gibao.id
    assert await db.equipamento(conn, heroi) == {"armadura": peitoral.id}
    assert (await db.itens_na_bolsa(conn, heroi)) == {gibao.id: 1}

    # O que nao esta na bolsa nao veste, e a resposta diz isso.
    vestiu, _saiu = await db.equipar(conn, heroi, peitoral.id, peitoral.slot)
    assert not vestiu
    print("  equipar troca sem perder a peca antiga: ok")


async def caso_so_cabe_um_por_slot():
    """A chave primária da tabela é a regra — não há código conferindo."""
    conn, _canal, _cog, ids = await preparar()
    heroi = ids[JOGADORES[0]]
    await db.lancar_ouro(conn, heroi, 2000, "teste")
    for id_do_item in ("gibao_de_couro", "tunica_acolchoada", "peitoral_de_serpe"):
        peca = itens.item(id_do_item)
        await db.comprar(conn, heroi, peca.id, peca.custo)
        await db.equipar(conn, heroi, peca.id, peca.slot)
    vestido = await db.equipamento(conn, heroi)
    assert list(vestido) == ["armadura"], vestido
    assert vestido["armadura"] == "peitoral_de_serpe"
    # As duas que sairam voltaram para a bolsa.
    bolsa = {k: v for k, v in (await db.itens_na_bolsa(conn, heroi)).items() if v}
    assert set(bolsa) == {"gibao_de_couro", "tunica_acolchoada"}, bolsa
    print("  tres armaduras, um slot: so a ultima fica vestida: ok")


async def caso_o_equipamento_entra_na_ca_e_no_acerto():
    conn, _canal, _cog, ids = await preparar(classe="guerreiro")
    heroi = ids[JOGADORES[0]]
    antes = await db.buscar_personagem(conn, heroi)
    await db.lancar_ouro(conn, heroi, 2000, "teste")

    peitoral = itens.item("peitoral_de_serpe")   # +2 CA
    espada = itens.item("espada_do_arsenal")     # +1 acerto, +2 dano
    for peca in (peitoral, espada):
        await db.comprar(conn, heroi, peca.id, peca.custo)
        await db.equipar(conn, heroi, peca.id, peca.slot)

    depois = await db.buscar_personagem(conn, heroi)
    assert depois["ca"] == antes["ca"] + 2, (antes["ca"], depois["ca"])
    assert depois["bonus_ataque"] == antes["bonus_ataque"] + 1
    assert depois["efeitos"]["dano_extra"] >= 2
    assert set(depois["equipados"]) == {peitoral.id, espada.id}
    print(
        f"  vestido, a CA vai de {antes['ca']} a {depois['ca']} "
        "e o acerto sobe 1: ok"
    )


async def caso_o_item_nao_soma_com_a_passiva_da_classe():
    """Item e passiva resolvem como duas passivas: vale o melhor, não a soma.

    O Protetor do clérigo dá +2 de CA e o gibão dá +1. Se as duas camadas
    fossem consolidadas em separado e somadas depois, o resultado seria +3 —
    e aí o equipamento furaria a contenção por outro caminho.
    """
    conn, _canal, _cog, _ids = await preparar(classe="clerigo")
    protetor = await db.criar_personagem(
        conn, GUILD, JOGADORES[0], "Protegido", "clerigo", ["Religião"], nivel=8
    )
    await db.definir_escolha(conn, protetor, "dominio_t2", "protetor")
    base = await db.buscar_personagem(conn, protetor)
    assert base["efeitos"]["ca"] == 2, base["efeitos"]["ca"]

    await db.lancar_ouro(conn, protetor, 500, "teste")
    gibao = itens.item("gibao_de_couro")   # +1 de CA, que e menos que o Protetor
    await db.comprar(conn, protetor, gibao.id, gibao.custo)
    await db.equipar(conn, protetor, gibao.id, gibao.slot)

    com_item = await db.buscar_personagem(conn, protetor)
    assert com_item["efeitos"]["ca"] == 2, com_item["efeitos"]["ca"]
    assert com_item["ca"] == base["ca"], (base["ca"], com_item["ca"])
    print("  +1 de item com +2 de classe da 2, nao 3: ok")


async def caso_as_botas_entram_na_ordem_do_combate():
    conn, canal, cog, ids = await preparar()
    heroi = ids[JOGADORES[0]]
    await db.lancar_ouro(conn, heroi, 2000, "teste")
    botas = itens.item("passos_do_primeiro")   # +6 de iniciativa
    await db.comprar(conn, heroi, botas.id, botas.custo)
    await db.equipar(conn, heroi, botas.id, botas.slot)

    montar_conteudo(cog, tamanho="Curta", salas=salas_sem_combate())
    run_id = await db.criar_run(conn, GUILD, CANAL, "t", JOGADORES[0])
    for user_id in JOGADORES[:2]:
        await db.adicionar_participante(conn, run_id, user_id, ids[user_id])
    run = await db.buscar_run(conn, run_id)

    pessoal = await db.personagens_da_run(conn, run_id)
    assert pessoal[0]["efeitos"]["bonus_iniciativa"] == 6
    combatentes = await cog._combatentes(run)
    calcado = next(c for c in combatentes if c.user_id == JOGADORES[0])
    descalco = next(c for c in combatentes if c.user_id == JOGADORES[1])
    assert motor.mod_iniciativa(calcado) == motor.mod_iniciativa(descalco) + 6
    print("  as botas somam 6 na iniciativa de quem as calca: ok")


async def caso_o_anel_mexe_em_quem_a_criatura_bate():
    conn, _canal, cog, ids = await preparar()
    heroi = ids[JOGADORES[0]]
    await db.lancar_ouro(conn, heroi, 2000, "teste")
    anel = itens.item("anel_do_para_raios")   # +8 de ameaca
    await db.comprar(conn, heroi, anel.id, anel.custo)
    await db.equipar(conn, heroi, anel.id, anel.slot)

    montar_conteudo(cog, tamanho="Curta", salas=salas_sem_combate())
    run_id = await db.criar_run(conn, GUILD, CANAL, "t", JOGADORES[0])
    for user_id in JOGADORES[:3]:
        await db.adicionar_participante(conn, run_id, user_id, ids[user_id])
    run = await db.buscar_run(conn, run_id)
    combatentes = await cog._combatentes(run)
    com_anel = next(c for c in combatentes if c.user_id == JOGADORES[0])
    sem_anel = next(c for c in combatentes if c.user_id == JOGADORES[1])
    assert com_anel.ameaca_total == sem_anel.ameaca_total + 8
    print("  o anel do para-raios soma 8 de ameaca: ok")


async def caso_item_desconhecido_nao_derruba_a_ficha():
    """Id velho no banco depois de o catálogo mudar: ignora, não estoura."""
    conn, _canal, _cog, ids = await preparar()
    heroi = ids[JOGADORES[0]]
    await conn.execute(
        "INSERT INTO personagem_equipamento (personagem_id, slot, item_id)"
        " VALUES (?, 'armadura', 'item_que_sumiu')",
        (heroi,),
    )
    await conn.commit()
    ficha = await db.buscar_personagem(conn, heroi)
    assert ficha is not None and ficha["ca"] > 0
    print("  id de item que sumiu do catalogo e ignorado: ok")




# -------------------------------------------------------- os botões da vitrine


# Semana fixa para os casos que dependem do QUE esta na prateleira. Sem isso
# eles passariam hoje e poderiam falhar na segunda — a vitrine e derivada da
# semana corrente, e nao ha garantia de que a proxima tenha peca caia.
SEMANA = "2026-W43"


async def _abrir_vitrine(conn, canal, cog, personagem_id, user_id):
    """Abre a vitrine pelo COMANDO, para provar que ele monta a view.

    Usa a semana de verdade, entao nao sirva para caso que depende do que esta
    na prateleira — para esses, `_vitrine_fixa`.
    """
    personagem = await db.buscar_personagem(conn, personagem_id)
    inter = FakeInteraction(canal, user_id)
    await cog.loja.vitrine.callback(cog.loja, inter, personagem["nome"])
    return inter, menu_de(inter)


async def _vitrine_fixa(conn, canal, cog, personagem_id, user_id, semana=SEMANA):
    """A mesma view, numa semana fixa, enviada pelo mesmo caminho do comando."""
    personagem = await db.buscar_personagem(conn, personagem_id)
    view = ViewDaVitrine(cog.loja, personagem, semana)
    inter = FakeInteraction(canal, user_id)
    await inter.response.send_message(
        embed=await view.desenhar(), view=view, ephemeral=True
    )
    return inter, view


async def caso_a_vitrine_abre_com_um_botao_por_peca():
    conn, canal, cog, ids = await preparar()
    heroi = ids[JOGADORES[0]]
    inter, view = await _abrir_vitrine(conn, canal, cog, heroi, JOGADORES[0])

    assert isinstance(view, ViewDaVitrine), view
    botoes = [f for f in view.children if isinstance(f, BotaoDeCompra)]
    prateleira = mercado.vitrine(heroi, view.semana)
    assert [b.peca.id for b in botoes] == [p.id for p in prateleira]
    # Sem ouro nenhum, nada é clicável.
    assert all(b.disabled for b in botoes), [b.label for b in botoes]

    # O embed nao diz mais quanto falta — a vitrine mostra so o status da
    # peca. Mas o motivo continua legivel: o PRECO esta em cada botao e o
    # SALDO no topo. E o que o caso afirma agora.
    embed = inter._mensagem_resposta.embeds[0]
    assert "0** de ouro" in embed.description, embed.description
    for botao in botoes:
        assert str(botao.peca.custo) in botao.label, botao.label

    # E o que cada campo mostra e o efeito, nao a prosa do catalogo.
    valores = [c.value for c in embed.fields]
    assert all(v and v != "sem efeito" for v in valores), valores
    prosa = [p.texto for p in prateleira]
    assert not any(v in prosa for v in valores), valores
    print(f"  a vitrine abre com {len(botoes)} botoes, travados sem ouro: ok")


async def caso_o_clique_compra_e_redesenha():
    conn, canal, cog, ids = await preparar()
    heroi = ids[JOGADORES[0]]
    await db.lancar_ouro(conn, heroi, 500, "teste")
    inter, view = await _vitrine_fixa(conn, canal, cog, heroi, JOGADORES[0])

    alvo = next(
        b for b in view.children
        if isinstance(b, BotaoDeCompra) and not b.disabled
    )
    peca = alvo.peca
    clique = FakeInteraction(canal, JOGADORES[0], inter._mensagem_resposta)
    await alvo.callback(clique)

    assert await db.ouro(conn, heroi) == 500 - peca.custo
    assert peca.id in await db.itens_na_bolsa(conn, heroi)
    # A compra saiu no canal, para o grupo ver.
    assert any(peca.nome in (m.content or "") for m in canal.enviadas), canal.enviadas
    # E a tela foi redesenhada: o botão daquela peça agora está travado.
    depois = clique.editada["view"]
    mesmo = next(b for b in depois.children if b.peca.id == peca.id)
    assert mesmo.disabled, "o botao do que ja e dele continuou clicavel"
    nomes = " ".join(c.name for c in clique.editada["embed"].fields)
    assert "já tem" in nomes, nomes
    print(f"  o clique compra e trava o proprio botao: ok")


async def caso_o_clique_sem_ouro_avisa_sem_cobrar():
    conn, canal, cog, ids = await preparar()
    heroi = ids[JOGADORES[0]]
    # Ouro para a peça mais barata do catálogo, e só.
    barata = min(itens.CATALOGO, key=lambda p: p.custo)
    await db.lancar_ouro(conn, heroi, barata.custo, "teste")
    inter, view = await _vitrine_fixa(conn, canal, cog, heroi, JOGADORES[0])

    # Forçar o clique num botão travado é o que um botão velho faria, e a
    # resposta tem de ser recusa — não compra.
    caro = max(
        (b for b in view.children if isinstance(b, BotaoDeCompra)),
        key=lambda b: b.peca.custo,
    )
    assert caro.peca.custo > barata.custo, "semana sem peca caia, caso inutil"
    clique = FakeInteraction(canal, JOGADORES[0], inter._mensagem_resposta)
    await caro.callback(clique)
    assert await db.ouro(conn, heroi) == barata.custo, "cobrou sem poder"
    assert "Faltam" in (clique.seguimento or ""), clique.seguimento
    print("  clicar no que nao da para pagar avisa e nao cobra: ok")


async def caso_o_botao_velho_nao_compra_fora_de_cartaz():
    """O Discord mantém o botão clicável; a semana virou, a peça saiu."""
    conn, canal, cog, ids = await preparar()
    heroi = ids[JOGADORES[0]]
    await db.lancar_ouro(conn, heroi, 5000, "teste")
    inter, view = await _vitrine_fixa(conn, canal, cog, heroi, JOGADORES[0])

    prateleira = {p.id for p in mercado.vitrine(heroi, view.semana)}
    sumida = next(p for p in itens.CATALOGO if p.id not in prateleira)
    clique = FakeInteraction(canal, JOGADORES[0], inter._mensagem_resposta)
    await view.comprar(clique, sumida.id)

    assert await db.ouro(conn, heroi) == 5000
    assert sumida.id not in await db.itens_na_bolsa(conn, heroi)
    assert "vitrine desta semana" in (clique.seguimento or ""), clique.seguimento
    print("  botao de peca fora de cartaz nao compra: ok")


async def caso_a_vitrine_do_outro_nao_e_clicavel():
    conn, canal, cog, ids = await preparar()
    heroi = ids[JOGADORES[0]]
    await db.lancar_ouro(conn, heroi, 500, "teste")
    inter, view = await _vitrine_fixa(conn, canal, cog, heroi, JOGADORES[0])

    intruso = FakeInteraction(canal, JOGADORES[1], inter._mensagem_resposta)
    assert not await view.interaction_check(intruso)
    assert "não é sua" in (intruso.resposta or ""), intruso.resposta
    print("  a vitrine de um nao aceita o clique do outro: ok")


async def caso_o_mercado_fecha_durante_a_incursao():
    conn, canal, cog, ids = await preparar()
    heroi = ids[JOGADORES[0]]
    await db.lancar_ouro(conn, heroi, 500, "teste")
    inter, view = await _vitrine_fixa(conn, canal, cog, heroi, JOGADORES[0])
    alvo = next(
        b for b in view.children
        if isinstance(b, BotaoDeCompra) and not b.disabled
    )

    # Entra numa run: o clique guardado deixa de valer.
    run_id = await db.criar_run(conn, GUILD, CANAL, "t", JOGADORES[0])
    await db.adicionar_participante(conn, run_id, JOGADORES[0], heroi)
    clique = FakeInteraction(canal, JOGADORES[0], inter._mensagem_resposta)
    await alvo.callback(clique)

    assert await db.ouro(conn, heroi) == 500, "comprou dentro da incursao"
    assert f"#{run_id}" in (clique.resposta or ""), clique.resposta
    print("  o botao nao compra durante a incursao: ok")


async def caso_a_mesma_peca_nao_e_comprada_duas_vezes():
    """Equipamento é único: a segunda cópia não faria nada e queimaria ouro."""
    conn, canal, cog, ids = await preparar()
    heroi = ids[JOGADORES[0]]
    await db.lancar_ouro(conn, heroi, 5000, "teste")
    semana = SEMANA
    peca = mercado.vitrine(heroi, semana)[0]

    comprada, _texto = await tentar_comprar(conn, heroi, semana, peca.id)
    assert comprada is not None
    gastou = 5000 - await db.ouro(conn, heroi)
    repetida, texto = await tentar_comprar(conn, heroi, semana, peca.id)
    assert repetida is None and "já tem" in texto, texto
    assert 5000 - await db.ouro(conn, heroi) == gastou, "cobrou a segunda copia"
    print("  equipamento e unico por personagem: ok")




async def caso_o_ouro_da_run_sai_no_fecho():
    """O que a incursão pagou aparece no embed de desfecho, por personagem.

    Por sala seria uma linha a cada passo; o grupo quer saber com quanto saiu,
    e é no fecho que isso cabe.
    """
    from src import embeds as E

    conn, _canal, cog, ids = await preparar()
    run_id = await db.criar_run(conn, GUILD, CANAL, "t", JOGADORES[0])
    for user_id in JOGADORES[:2]:
        await db.adicionar_participante(conn, run_id, user_id, ids[user_id])
    await db.lancar_ouro(
        conn, ids[JOGADORES[0]], 15, "Sala superada", run_id=run_id, chave="s1"
    )
    await db.lancar_ouro(
        conn, ids[JOGADORES[0]], 60, "Incursao concluida", run_id=run_id, chave="fim"
    )
    await db.lancar_ouro(
        conn, ids[JOGADORES[1]], 15, "Sala superada", run_id=run_id, chave="s1"
    )
    # Compra depois da run NAO entra: o fecho mostra o que a incursao pagou,
    # e nao o saldo da bolsa.
    await db.lancar_ouro(conn, ids[JOGADORES[0]], -80, "Compra: gibao")

    por_personagem = await db.ouro_da_run(conn, run_id)
    assert dict(por_personagem) == {
        f"Heroi{JOGADORES[0]}": 75,
        f"Heroi{JOGADORES[1]}": 15,
    }, por_personagem

    e = discord.Embed(title="x")
    E.campo_ouro(e, por_personagem)
    campo = next(c for c in e.fields if "Ouro" in c.name)
    assert "+90" in campo.name, campo.name
    assert "+75" in campo.value and "+15" in campo.value, campo.value
    print("  o ouro da incursao sai no fecho, por personagem: ok")


def caso_sem_ouro_o_campo_nao_aparece():
    """Run que não pagou nada não ganha um campo vazio no embed."""
    from src import embeds as E

    e = discord.Embed(title="x")
    E.campo_ouro(e, [])
    E.campo_ouro(e, None)
    E.campo_ouro(e, [("Ninguem", 0)])
    assert not e.fields, [c.name for c in e.fields]
    print("  sem ouro, o campo nao entra no embed: ok")


async def main():
    try:
        caso_todo_item_respeita_o_dominio_do_slot()
        caso_o_catalogo_cobre_os_cinco_slots()
        caso_o_item_nao_passa_de_dois_de_ca()
        caso_a_vitrine_e_derivada_e_estavel()
        caso_a_vitrine_muda_por_personagem_e_por_semana()
        caso_a_semana_vira_na_segunda()
        caso_o_lendario_e_raro_na_prateleira()
        caso_comprar_confere_a_prateleira_de_hoje()
        caso_o_ouro_escala_por_tier()
        await caso_o_ouro_e_a_soma_do_livro_caixa()
        await caso_a_mesma_sala_nunca_paga_duas_vezes()
        await caso_a_sala_superada_nao_paga_na_hora()
        await caso_a_run_concluida_paga_todos_que_passaram()
        await caso_comprar_debita_e_guarda()
        await caso_equipar_tira_da_bolsa_e_troca_sem_perder()
        await caso_so_cabe_um_por_slot()
        await caso_o_equipamento_entra_na_ca_e_no_acerto()
        await caso_o_item_nao_soma_com_a_passiva_da_classe()
        await caso_as_botas_entram_na_ordem_do_combate()
        await caso_o_anel_mexe_em_quem_a_criatura_bate()
        await caso_item_desconhecido_nao_derruba_a_ficha()
        await caso_a_vitrine_abre_com_um_botao_por_peca()
        await caso_o_clique_compra_e_redesenha()
        await caso_o_clique_sem_ouro_avisa_sem_cobrar()
        await caso_o_botao_velho_nao_compra_fora_de_cartaz()
        await caso_a_vitrine_do_outro_nao_e_clicavel()
        await caso_o_mercado_fecha_durante_a_incursao()
        await caso_a_mesma_peca_nao_e_comprada_duas_vezes()
        await caso_o_ouro_da_run_sai_no_fecho()
        caso_sem_ouro_o_campo_nao_aparece()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        BANCO.unlink(missing_ok=True)


asyncio.run(main())
print("TESTES DO MERCADO PASSARAM")
