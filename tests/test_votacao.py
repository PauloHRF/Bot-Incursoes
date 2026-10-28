"""Caminhos de borda da votação: maioria no prazo, empate, silêncio e restart."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import config, database as db  # noqa: E402
from src.cogs.incursao import Incursoes, ViewVotacao  # noqa: E402
from fakes import (  # noqa: E402
    CANAL,
    GUILD,
    JOGADORES,
    FakeBot,
    FakeCanal,
    FakeInteraction,
    criar_grupo,
    montar_conteudo,
    salas_de_combate,
    salas_sem_combate,
)

# Aguenta o combate inteiro: este arquivo quer a ABERTURA do combate, não o
# desfecho dele.
DURAO = {"nome": "Durao", "ca": 30, "ataque": -20, "dano": "1d1", "hp": 4000}


async def montar_run_em_votacao(conn, canal, cog, incursao_id="t"):
    """Cria uma run com os 5 jogadores, já na votação da linha 1."""
    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.entrar.callback(cog, inter, incursao_id)
    run = await db.run_do_canal(conn, CANAL)
    msg = await canal.fetch_message(run["mensagem_id"])
    for user_id in JOGADORES[1:]:
        await cog.recrutar(FakeInteraction(canal, user_id, msg), run["id"], "entrar")
    return await db.buscar_run(conn, run["id"])


_ABERTAS = []


async def preparar():
    config.DB_PATH = Path(__file__).resolve().parent / "teste_votacao.db"
    config.DB_PATH.unlink(missing_ok=True)
    config.TAMANHO_GRUPO = 5
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    await criar_grupo(conn)
    canal = FakeCanal(CANAL)
    cog = Incursoes(FakeBot(conn, canal))
    montar_conteudo(cog, tamanho="Média", salas=salas_sem_combate(8))
    return conn, canal, cog


async def caso_maioria_fecha_sem_esperar():
    """Assim que 3 dos 5 votam na mesma sala, o grupo avança."""
    conn, canal, cog = await preparar()
    run = await montar_run_em_votacao(conn, canal, cog)
    opcoes = await cog._opcoes(run, 1)
    msg = await canal.fetch_message(run["mensagem_id"])
    # a votacao marca o grupo: sem mencao ninguem e avisado da vez
    assert all(f"<@{u}>" in (msg.content or "") for u in JOGADORES[:5]), msg.content

    # dois votos ainda nao decidem nada, e o "voto registrado" fica na tela
    votos = []
    for user_id in JOGADORES[:2]:
        votos.append(FakeInteraction(canal, user_id, msg))
        await cog.votar(votos[-1], run["id"], 1, opcoes[0].id)
    assert (await db.buscar_run(conn, run["id"]))["status"] == "escolhendo"
    assert "Voto registrado" in votos[0].resposta
    assert not any(getattr(v, "efemera_apagada", False) for v in votos)

    # o terceiro fecha a maioria de 5, sem esperar os outros dois
    votos.append(FakeInteraction(canal, JOGADORES[2], msg))
    await cog.votar(votos[-1], run["id"], 1, opcoes[0].id)
    depois = await db.buscar_run(conn, run["id"])
    assert depois["status"] == "em_sala", depois["status"]
    # chegando na sala, os avisos de voto de todo mundo somem
    assert all(getattr(v, "efemera_apagada", False) for v in votos)
    assert depois["sala_atual"] == opcoes[0].id
    assert len(await db.votos_da_linha(conn, run["id"], 1)) == 3, "avançou com 3 de 5"
    assert any("não espera" in (m.content or "") for m in canal.mensagens)

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  maioria fecha sem esperar os que faltam: ok")


async def caso_votos_divididos_esperam():
    """Enquanto ninguém tem maioria, a votação continua aberta."""
    conn, canal, cog = await preparar()
    run = await montar_run_em_votacao(conn, canal, cog)
    opcoes = await cog._opcoes(run, 1)
    msg = await canal.fetch_message(run["mensagem_id"])

    # 2 x 1: ninguem chegou a 3
    for user_id in JOGADORES[:2]:
        await cog.votar(FakeInteraction(canal, user_id, msg), run["id"], 1, opcoes[0].id)
    await cog.votar(FakeInteraction(canal, JOGADORES[2], msg), run["id"], 1, opcoes[1].id)
    parado = await db.buscar_run(conn, run["id"])
    assert parado["status"] == "escolhendo" and parado["sala_atual"] is None

    # o quarto voto fecha a maioria na primeira
    await cog.votar(FakeInteraction(canal, JOGADORES[3], msg), run["id"], 1, opcoes[0].id)
    depois = await db.buscar_run(conn, run["id"])
    assert depois["status"] == "em_sala" and depois["sala_atual"] == opcoes[0].id

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  votos divididos seguem esperando: ok")


async def caso_empate_com_todos_votando():
    """2x2x1: todos votaram, ninguém tem maioria, ninguém avança."""
    conn, canal, cog = await preparar()
    run = await montar_run_em_votacao(conn, canal, cog)
    opcoes = await cog._opcoes(run, 1)
    msg = await canal.fetch_message(run["mensagem_id"])

    for user_id, sala in zip(JOGADORES, [opcoes[0], opcoes[0], opcoes[1], opcoes[1], opcoes[2]]):
        await cog.votar(FakeInteraction(canal, user_id, msg), run["id"], 1, sala.id)

    depois = await db.buscar_run(conn, run["id"])
    assert depois["status"] == "escolhendo", "empate não pode fazer o grupo avançar"
    assert depois["sala_atual"] is None
    assert any("Empate" in (m.content or "") for m in canal.mensagens)

    # alguém troca o voto e a maioria se forma
    await cog.votar(FakeInteraction(canal, JOGADORES[4], msg), run["id"], 1, opcoes[0].id)
    depois = await db.buscar_run(conn, run["id"])
    assert depois["status"] == "em_sala" and depois["sala_atual"] == opcoes[0].id

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  empate com todos votando espera desempate: ok")


async def caso_sem_prazo():
    """A votação não guarda prazo nenhum: espera indefinidamente."""
    conn, canal, cog = await preparar()
    run = await montar_run_em_votacao(conn, canal, cog)
    assert run["votacao_expira_em"] is None, run["votacao_expira_em"]

    # sem voto nenhum, nada acontece e nada e postado
    antes = len(canal.mensagens)
    await cog._fechar_votacao(run, 1)
    depois = await db.buscar_run(conn, run["id"])
    assert depois["status"] == "escolhendo" and depois["sala_atual"] is None
    assert len(canal.mensagens) == antes

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  sem prazo: a votação espera sem reclamar: ok")


async def caso_restart():
    """Depois de um restart, os botões da mensagem aberta voltam a funcionar."""
    conn, canal, cog = await preparar()
    run = await montar_run_em_votacao(conn, canal, cog)

    # novo cog, como se o processo tivesse reiniciado
    bot2 = FakeBot(conn, canal)
    cog2 = Incursoes(bot2)
    montar_conteudo(cog2, tamanho="Média", salas=salas_sem_combate(8))
    await cog2.restaurar_views()

    assert bot2.views_registradas, "nenhuma view foi restaurada"
    view, mensagem_id = bot2.views_registradas[0]
    assert isinstance(view, ViewVotacao)
    assert mensagem_id == run["mensagem_id"]
    assert len(view.children) == 3

    # e o voto pelo cog novo continua avançando a run
    msg = await canal.fetch_message(run["mensagem_id"])
    opcoes = await cog2._opcoes(run, 1)
    for user_id in JOGADORES:
        await cog2.votar(FakeInteraction(canal, user_id, msg), run["id"], 1, opcoes[0].id)
    assert (await db.buscar_run(conn, run["id"]))["status"] == "em_sala"

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  botões sobrevivem a um restart: ok")


async def caso_intervalo_entre_incursoes():
    """Quem acabou de participar fica bloqueado pelo intervalo configurado."""
    conn, canal, cog = await preparar()
    run = await montar_run_em_votacao(conn, canal, cog)
    await db.atualizar_run(conn, run["id"], status="desistiu")

    bloqueio = await cog._motivo_de_bloqueio(GUILD, JOGADORES[0])
    assert bloqueio and "intervalo" in bloqueio.lower(), bloqueio

    await db.definir_intervalo(conn, GUILD, 0)
    assert await cog._motivo_de_bloqueio(GUILD, JOGADORES[0]) is None

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  intervalo entre incursões: ok")


async def caso_canal_fica_com_um_cartao_so():
    """Cada passo apaga o anterior: o canal mostra so o momento atual."""
    conn, canal, cog = await preparar()
    run = await montar_run_em_votacao(conn, canal, cog)

    id_votacao = run["mensagem_id"]
    assert (await canal.fetch_message(id_votacao)).view is not None, "a votacao abre com botoes"

    # votada, a mensagem da votacao sai do canal
    alvo = next(s for s in await cog._opcoes(run, 1) if s.tem_teste)
    msg = await canal.fetch_message(id_votacao)
    for user_id in JOGADORES:
        await cog.votar(FakeInteraction(canal, user_id, msg), run["id"], 1, alvo.id)
    assert not [m for m in canal.mensagens if m.id == id_votacao], "a votacao devia sumir"

    # a sala aberta tem botao, e fica ate a proxima votacao
    atual = await db.buscar_run(conn, run["id"])
    id_sala = atual["mensagem_id"]
    msg_sala = await canal.fetch_message(id_sala)
    assert msg_sala.view is not None

    for user_id in JOGADORES:
        agora = await db.buscar_run(conn, run["id"])
        if agora["status"] != "em_sala" or agora["sala_atual"] != alvo.id:
            break
        await cog.rolar(FakeInteraction(canal, user_id, msg_sala), run["id"], alvo.id)
    assert not [m for m in canal.mensagens if m.id == id_sala], "a sala devia sumir"

    # agora a votacao da linha 2 esta aberta; desistir precisa fecha-la
    atual = await db.buscar_run(conn, run["id"])
    id_votacao2 = atual["mensagem_id"]
    assert (await canal.fetch_message(id_votacao2)).view is not None

    for user_id in JOGADORES[:3]:
        await cog.desistir.callback(cog, FakeInteraction(canal, user_id))
    assert (await db.buscar_run(conn, run["id"]))["status"] == "desistiu"
    assert (
        await canal.fetch_message(id_votacao2)
    ).view is None, "a votacao aberta ficou clicavel depois da run encerrada"

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  cada passo apaga o anterior e os botoes somem ao encerrar: ok")


async def caso_o_caido_nao_vota_e_nao_conta():
    """Quem está no chão não escolhe o caminho — nem atrasa quem está de pé.

    O segundo ponto é o que machucaria em produção: a votação fecha na
    MAIORIA, e a maioria é uma fração do grupo. Tirando o voto do caído sem
    tirá-lo da conta, 2 de 5 nunca formariam a maioria de 3 e a run ficaria
    parada esperando um voto que não pode existir.
    """
    conn, canal, cog = await preparar()
    run = await montar_run_em_votacao(conn, canal, cog)
    opcoes = await cog._opcoes(run, 1)
    msg = await canal.fetch_message(run["mensagem_id"])

    # tres dos cinco caem
    for user_id in JOGADORES[2:5]:
        await db.definir_hp(conn, run["id"], user_id, 0)
    assert len(await db.participantes_de_pe(conn, run["id"])) == 2

    # o caido tenta votar e e recusado
    caido = FakeInteraction(canal, JOGADORES[4], msg)
    await cog.votar(caido, run["id"], 1, opcoes[0].id)
    assert "caído" in caido.resposta, caido.resposta
    assert not await db.votos_da_linha(conn, run["id"], 1), "o voto do caido entrou"

    # e os dois de pe decidem sozinhos: a maioria agora e 2
    for user_id in JOGADORES[:2]:
        await cog.votar(FakeInteraction(canal, user_id, msg), run["id"], 1, opcoes[0].id)

    depois = await db.buscar_run(conn, run["id"])
    assert depois["status"] == "em_sala", (
        f"a run travou esperando voto de quem esta caido: {depois['status']}"
    )
    assert depois["sala_atual"] == opcoes[0].id

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  o caido nao vota, e os de pe decidem sem esperar por ele: ok")


async def caso_o_caido_nao_rola_o_teste_da_sala():
    """E na sala vale o mesmo: ele não rola, e a sala não espera por ele."""
    conn, canal, cog = await preparar()
    run = await montar_run_em_votacao(conn, canal, cog)
    opcoes = await cog._opcoes(run, 1)
    msg = await canal.fetch_message(run["mensagem_id"])
    for user_id in JOGADORES[:3]:
        await cog.votar(FakeInteraction(canal, user_id, msg), run["id"], 1, opcoes[0].id)
    run = await db.buscar_run(conn, run["id"])
    assert run["status"] == "em_sala", run["status"]

    alvo = run["sala_atual"]
    sala_msg = await canal.fetch_message(run["mensagem_id"])
    await db.definir_hp(conn, run["id"], JOGADORES[4], 0)

    caido = FakeInteraction(canal, JOGADORES[4], sala_msg)
    await cog.rolar(caido, run["id"], alvo)
    assert "caído" in caido.resposta, caido.resposta

    registros = await db.testes_da_sala(conn, run["id"], run["linha_atual"])
    assert not any(r["user_id"] == JOGADORES[4] for r in registros), registros

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  o caido nao rola o teste da sala: ok")


async def caso_dois_cliques_juntos_abrem_a_sala_uma_vez():
    """Dois cliques que fecham a maioria juntos abrem UMA sala.

    Com grupo de cinco a maioria é três, então o terceiro, o quarto e o
    quinto clique todos veem maioria formada e todos seguiam para abrir a
    sala. Entre a conferência do status e a gravação havia dois `canal.send`
    de rede — tempo de sobra para dois passarem juntos, e o painel do
    combate saía duplicado.

    Para a corrida aparecer os dois cliques precisam estar NO AR ao mesmo
    tempo: conferir o status antes nao resolve nada, porque e o `await` do
    meio que solta a vez. Chamar um depois do outro nao reproduz — o
    segundo releria o status ja mudado e desistiria sozinho.
    """
    conn, canal, cog = await preparar()
    montar_conteudo(cog, incursao_id="dupla", salas=salas_de_combate(DURAO))
    run = await montar_run_em_votacao(conn, canal, cog, "dupla")
    opcoes = await cog._opcoes(run, 1)
    assert opcoes[0].e_combate, "este caso quer uma sala de COMBATE"
    msg = await canal.fetch_message(run["mensagem_id"])

    # dois votos: ainda falta um para a maioria de cinco
    for user_id in JOGADORES[:2]:
        await cog.votar(FakeInteraction(canal, user_id, msg), run["id"], 1, opcoes[0].id)
    assert (await db.buscar_run(conn, run["id"]))["status"] == "escolhendo"

    # o terceiro e o quarto clicam juntos: os DOIS veem maioria formada
    await asyncio.gather(
        cog.votar(FakeInteraction(canal, JOGADORES[2], msg), run["id"], 1, opcoes[0].id),
        cog.votar(FakeInteraction(canal, JOGADORES[3], msg), run["id"], 1, opcoes[0].id),
    )
    depois = await db.buscar_run(conn, run["id"])
    assert depois["status"] == "em_sala", depois["status"]
    assert depois["sala_atual"] == opcoes[0].id

    paineis = [
        m for m in canal.enviadas
        if m.embeds and "combate!" in (m.content or "")
    ]
    assert len(paineis) == 1, f"abriu {len(paineis)} paineis de combate"

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  dois cliques juntos abrem a sala uma vez: ok")


async def caso_a_sala_fecha_uma_vez_so():
    """Duas rolagens que resolvem a sala juntas fecham UMA vez.

    Mesma corrida do outro lado: cada rolagem que chega ao alvo de
    progresso vê a sala resolvida e segue para o passo seguinte. No fim do
    caminho o passo seguinte é o combate do objetivo.
    """
    conn, canal, cog = await preparar()
    run = await montar_run_em_votacao(conn, canal, cog)
    opcoes = await cog._opcoes(run, 1)
    msg = await canal.fetch_message(run["mensagem_id"])
    for user_id in JOGADORES:
        await cog.votar(FakeInteraction(canal, user_id, msg), run["id"], 1, opcoes[0].id)
    dentro = await db.buscar_run(conn, run["id"])
    if dentro["status"] != "em_sala":
        # A sala se resolveu com os testes do próprio voto: nada a fazer.
        await conn.close()
        config.DB_PATH.unlink(missing_ok=True)
        print("  a sala fecha uma vez só: ok (resolvida na entrada)")
        return

    sala = cog._sala(cog._incursao_da_run(dentro), dentro["sala_atual"])
    # `enviadas` e nao `mensagens`: abrir o passo seguinte APAGA o cartao
    # anterior e posta outro, entao a conta liquida de mensagens vivas da
    # zero mesmo tendo postado.
    antes = len(canal.enviadas)
    await cog._concluir_sala(dentro, sala, None)
    assert len(canal.enviadas) > antes, "o fecho da sala não postou nada"

    # O segundo chamador tem o mesmo `run` da corrida: não posta nada.
    antes = len(canal.enviadas)
    await cog._concluir_sala(dentro, sala, None)
    assert len(canal.enviadas) == antes, (
        "o segundo fecho da sala postou de novo"
    )

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  a sala fecha uma vez só: ok")


async def caso_o_tier_aparece_na_hora_de_escolher():
    """A lista de incursões diz o tier, e o `/incursao listar` também.

    O tier decide se o personagem pode entrar, e a escolha acontece na
    lista do autocomplete: sem ele ali o jogador escolhia no escuro e só
    descobria no erro. Pôr o tier no cartão da run já aberta não resolve —
    o cartão vem depois da escolha.
    """
    conn, canal, cog = await preparar()
    montar_conteudo(cog, incursao_id="t1", tier=1, salas=salas_sem_combate(8))
    montar_conteudo(cog, incursao_id="t4", tier=4, salas=salas_sem_combate(8))
    montar_conteudo(cog, incursao_id="livre", tier=None, salas=salas_sem_combate(8))

    inter = FakeInteraction(canal, JOGADORES[0])
    opcoes = await cog._sugerir_incursoes(inter, "")
    por_valor = {o.value: o.name for o in opcoes}
    assert "(T1)" in por_valor["t1"], por_valor["t1"]
    assert "(T4)" in por_valor["t4"], por_valor["t4"]
    # Incursão sem tier declarado diz isso em vez de inventar um número.
    assert "tier livre" in por_valor["livre"], por_valor["livre"]
    # E o Discord corta o nome de uma opção em 100 caracteres.
    for nome in por_valor.values():
        assert len(nome) <= cog.LIMITE_DA_OPCAO, (len(nome), nome)

    # Nome comprido: o que cede é a Organização, não o tier.
    comprido = "A" * 150
    montar_conteudo(cog, incursao_id="comprido", tier=2, salas=salas_sem_combate(8))
    cog.incursoes["comprido"].nome = comprido
    opcoes = await cog._sugerir_incursoes(inter, "comprido")
    assert len(opcoes) == 1, opcoes
    assert len(opcoes[0].name) <= cog.LIMITE_DA_OPCAO, len(opcoes[0].name)

    # O `/incursao listar` traz o tier no título de cada uma.
    lista = FakeInteraction(canal, JOGADORES[0])
    await cog.listar.callback(cog, lista)
    cartao = await lista.original_response()
    campos = {f.name: f.value for f in cartao.embeds[0].fields}
    assert any("(T1)" in nome for nome in campos), list(campos)
    assert any("(T4)" in nome for nome in campos), list(campos)

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  o tier aparece na hora de escolher a incursão: ok")


async def main():
    await caso_maioria_fecha_sem_esperar()
    await caso_o_tier_aparece_na_hora_de_escolher()
    await caso_dois_cliques_juntos_abrem_a_sala_uma_vez()
    await caso_a_sala_fecha_uma_vez_so()
    await caso_votos_divididos_esperam()
    await caso_empate_com_todos_votando()
    await caso_sem_prazo()
    await caso_restart()
    await caso_intervalo_entre_incursoes()
    await caso_canal_fica_com_um_cartao_so()
    await caso_o_caido_nao_vota_e_nao_conta()
    await caso_o_caido_nao_rola_o_teste_da_sala()


async def _com_limpeza():
    try:
        await main()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass


def _fechar_tudo():
    asyncio.run(_com_limpeza())


_fechar_tudo()
print("TESTES DE VOTAÇÃO PASSARAM")
