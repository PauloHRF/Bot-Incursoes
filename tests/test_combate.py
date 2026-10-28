"""Combate: rodadas, contra-ataque, vitória, derrota total e descanso.

Usa incursões sintéticas com monstros impossíveis de errar ou de acertar, para
que o resultado não dependa do dado.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import classes, config, database as db, embeds, motor  # noqa: E402
from src.cogs.incursao import Incursoes, ViewCombate  # noqa: E402
from fakes import (  # noqa: E402
    CLASSE_PADRAO,
    CANAL,
    DURAO,
    IMBATIVEL,
    INDEFESO,
    JOGADORES,
    FakeBot,
    FakeCanal,
    FakeInteraction,
    atacar_ate_cair,
    criar_grupo,
    montar_conteudo,
    salas_de_combate,
    salas_sem_combate,
)

_ABERTAS = []


async def preparar(classe=CLASSE_PADRAO, nivel=8):
    # No Windows o arquivo so pode ser apagado depois que ninguem o mantem aberto.
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass
    config.DB_PATH = Path(__file__).resolve().parent / "teste_combate.db"
    config.DB_PATH.unlink(missing_ok=True)
    config.TAMANHO_GRUPO = 5
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    await criar_grupo(conn, nivel=nivel, classe=classe)
    canal = FakeCanal(CANAL)
    cog = Incursoes(FakeBot(conn, canal))
    return conn, canal, cog


async def montar_run(conn, canal, cog, incursao_id):
    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.entrar.callback(cog, inter, incursao_id)
    run = await db.run_do_canal(conn, CANAL)
    msg = await canal.fetch_message(run["mensagem_id"])
    for user_id in JOGADORES[1:]:
        await cog.recrutar(FakeInteraction(canal, user_id, msg), run["id"], "entrar")
    return await db.buscar_run(conn, run["id"])


async def atravessar_ate_objetivo(conn, canal, cog, run, incursao):
    """Vota e resolve as três linhas escolhendo sempre uma sala sem combate."""
    for linha in range(1, incursao.passos + 1):
        run = await db.buscar_run(conn, run["id"])
        assert run["status"] == "escolhendo", run["status"]
        alvo = next(s for s in await cog._opcoes(run, linha) if not s.e_combate)
        msg = await canal.fetch_message(run["mensagem_id"])
        for user_id in JOGADORES:
            await cog.votar(FakeInteraction(canal, user_id, msg), run["id"], linha, alvo.id)

        atual = await db.buscar_run(conn, run["id"])
        if atual["status"] == "em_sala" and alvo.tem_teste:
            msg_sala = await canal.fetch_message(atual["mensagem_id"])
            for user_id in JOGADORES:
                agora = await db.buscar_run(conn, run["id"])
                if agora["status"] != "em_sala" or agora["sala_atual"] != alvo.id:
                    break
                await cog.rolar(FakeInteraction(canal, user_id, msg_sala), run["id"], alvo.id)
    return await db.buscar_run(conn, run["id"])


async def caso_hp_inicial():
    """Ao começar a run, todo mundo entra com o HP máximo da ficha."""
    conn, canal, cog = await preparar(classe="monge", nivel=3)
    montar_conteudo(cog, salas=salas_sem_combate())
    run = await montar_run(conn, canal, cog, "t")
    hps = await db.hp_dos_participantes(conn, run["id"])
    # o HP e o da tabela do Monge no tier 2, nao um numero digitado na ficha
    esperado = classes.classe("monge").numeros(3).hp
    assert set(hps.values()) == {esperado}, (hps, esperado)
    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  HP inicializado no começo da run: ok")


async def caso_vitoria_no_objetivo():
    """Chegando ao objetivo, o combate abre e a vitória conclui a run."""
    conn, canal, cog = await preparar()
    incursao, _ = montar_conteudo(cog, incursao_id="facil", salas=salas_sem_combate())
    run = await montar_run(conn, canal, cog, "facil")
    run = await atravessar_ate_objetivo(conn, canal, cog, run, incursao)

    assert run["status"] == "objetivo" and run["sala_atual"] == "OBJ", run
    estado = await cog._estado_combate(run, incursao.objetivo)
    assert estado is not None and estado.rodada == 1
    # O HP escrito e 1, e a escala por tier do grupo o multiplica: o que
     # importa aqui e que o inimigo esta de pe e inteiro, nao o numero.
    assert len(estado.inimigos) == 1 and estado.inimigos[0].hp_atual >= 1
    assert estado.inimigos[0].hp_atual == estado.inimigos[0].hp_max

    # CA 1 e 1 HP caem rapido, mas o 1 natural ainda erra: ataca ate derrubar
    msg = await canal.fetch_message(run["mensagem_id"])
    await atacar_ate_cair(conn, canal, cog, run["id"], "OBJ")

    run = await db.buscar_run(conn, run["id"])
    assert run["status"] == "sucesso", f"esperava sucesso, veio {run['status']}"
    desfecho = next(
        m.embeds[0] for m in canal.mensagens
        if m.embeds and "objetivo cumprido" in (m.embeds[0].title or "")
    )
    # o caminho inteiro so reaparece no fim, ja que cada passo apagou o anterior
    campos = {f.name: f.value for f in desfecho.fields}
    caminho = next(v for k, v in campos.items() if k.startswith("Caminho"))
    visitadas = await db.salas_visitadas(conn, run["id"])
    assert len(visitadas) == incursao.passos
    for sala_id in visitadas:
        assert cog._sala(incursao, sala_id).nome in caminho, (sala_id, caminho)

    # combate encerrado não aceita mais ataque
    tarde = FakeInteraction(canal, JOGADORES[1], msg)
    await cog.atacar(tarde, run["id"], "OBJ")
    assert "já terminou" in tarde.resposta

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  vitória no objetivo conclui a run: ok")


async def caso_combate_no_meio_do_mapa():
    """Vencer uma sala de combate da linha 1 leva o grupo para a linha 2."""
    conn, canal, cog = await preparar()
    # banco so de combate: o primeiro passo cai numa sala de Combate na certa
    incursao, _ = montar_conteudo(
        cog, incursao_id="meio", salas=salas_de_combate(INDEFESO)
    )
    run = await montar_run(conn, canal, cog, "meio")

    msg = await canal.fetch_message(run["mensagem_id"])
    alvo = (await cog._opcoes(run, 1))[0]
    assert alvo.e_combate
    for user_id in JOGADORES:
        await cog.votar(FakeInteraction(canal, user_id, msg), run["id"], 1, alvo.id)

    run = await db.buscar_run(conn, run["id"])
    assert run["status"] == "em_sala" and run["sala_atual"] == alvo.id

    await atacar_ate_cair(conn, canal, cog, run["id"], alvo.id)

    run = await db.buscar_run(conn, run["id"])
    assert run["status"] == "escolhendo" and run["linha_atual"] == 2, run
    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  combate no meio do mapa devolve à votação: ok")


async def caso_rodadas_e_contra_ataque():
    """Todos atacam uma vez; aí o monstro revida e a rodada vira."""
    conn, canal, cog = await preparar(classe="barbaro", nivel=10)
    incursao, _ = montar_conteudo(
        cog, incursao_id="rodadas", monstro_objetivo=IMBATIVEL, salas=salas_sem_combate()
    )
    run = await montar_run(conn, canal, cog, "rodadas")
    run = await atravessar_ate_objetivo(conn, canal, cog, run, incursao)
    assert run["status"] == "objetivo"

    msg = await canal.fetch_message(run["mensagem_id"])
    for i, user_id in enumerate(JOGADORES):
        inter = FakeInteraction(canal, user_id, msg)
        await cog.atacar(inter, run["id"], "OBJ")
        # CA 40 so cai com 20 natural; o 1 natural sai como erro critico
        assert any(
            marca in inter.resposta for marca in ("errou", "CRITICO", "erro critico")
        ), inter.resposta

        # o mesmo personagem não ataca duas vezes na mesma rodada
        if i < len(JOGADORES) - 1:
            repetido = FakeInteraction(canal, user_id, msg)
            await cog.atacar(repetido, run["id"], "OBJ")
            assert "já atacou nesta rodada" in repetido.resposta

    estado = await cog._estado_combate(await db.buscar_run(conn, run["id"]), incursao.objetivo)
    assert estado.rodada == 2, f"a rodada deveria ter virado, veio {estado.rodada}"
    # o monstro tem +40 de ataque, mas um 1 natural ainda erra: 0 ou 1 caido
    assert len(estado.caidos) <= 1, estado.caidos
    # so um 20 natural tira HP desse monstro — e o HP maximo escala com o
    # tier do grupo, entao a comparacao e com o proprio maximo
    assert estado.inimigos[0].hp_atual <= estado.inimigos[0].hp_max

    # quem caiu não ataca mais
    if estado.caidos:
        caido = estado.caidos[0]
        inter = FakeInteraction(canal, caido.user_id, msg)
        await cog.atacar(inter, run["id"], "OBJ")
        assert "caído" in inter.resposta

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  rodadas e contra-ataque: ok")


async def caso_combate_nao_polui_o_canal():
    """O combate inteiro cabe num painel editado, não numa mensagem por rodada."""
    conn, canal, cog = await preparar()
    incursao, _ = montar_conteudo(
        cog, incursao_id="limpo", monstro_objetivo=DURAO, salas=salas_sem_combate()
    )
    run = await montar_run(conn, canal, cog, "limpo")
    run = await atravessar_ate_objetivo(conn, canal, cog, run, incursao)
    assert run["status"] == "objetivo"

    antes = len(canal.enviadas)
    painel_id = run["mensagem_id"]
    privadas = []
    rodadas = 0
    for _ in range(40):
        atual = await db.buscar_run(conn, run["id"])
        if atual["status"] != "objetivo":
            break
        estado = await cog._estado_combate(atual, incursao.objetivo)
        rodadas = max(rodadas, estado.rodada)
        msg = await canal.fetch_message(atual["mensagem_id"])
        for c in list(estado.vivos):
            agora = await db.buscar_run(conn, run["id"])
            if agora["status"] != "objetivo":
                break
            inter = FakeInteraction(canal, c.user_id, msg)
            privadas.append(inter)
            await cog.atacar(inter, run["id"], incursao.objetivo.id)

    assert (await db.buscar_run(conn, run["id"]))["status"] == "sucesso"
    assert rodadas >= 3, f"o combate precisa durar algumas rodadas para o teste valer ({rodadas})"

    novas = canal.enviadas[antes:]
    # O painel e editado no lugar: nenhum embed novo de combate. O que o combate
    # posta e a chamada de cada rodada, uma linha de texto marcando quem joga.
    chamadas = [m for m in novas if not m.embeds and "Rodada" in (m.content or "")]
    assert len(chamadas) == rodadas - 1, (
        f"{len(chamadas)} chamadas em {rodadas} rodadas — uma por rodada nova"
    )
    assert all("<@" in (m.content or "") for m in chamadas), "a chamada marca o grupo"
    # e cada chamada sai do canal quando a proxima rodada abre
    assert all(m.apagada for m in chamadas), "a chamada da rodada anterior deve sumir"
    assert all(i.efemera_apagada for i in privadas), "o resumo privado devia sumir tambem"
    assert not [m for m in canal.mensagens if "Rodada" in (m.content or "")]
    sem_chamada = len(novas) - len(chamadas)
    assert sem_chamada <= 3, (
        f"{sem_chamada} mensagens novas fora as chamadas — o combate voltou a poluir"
    )
    novas = len(novas)

    # o painel continua sendo o mesmo, atualizado
    painel = await canal.fetch_message(painel_id)
    assert painel.embeds and "rodada" in (painel.embeds[0].title or "").lower()
    assert painel.view is None, "o painel encerrado não mantém o botão de atacar"
    print(f"  combate de {rodadas} rodadas em {novas} mensagens novas: ok")


async def caso_sala_de_combate_nao_duplica_entrada():
    """Entrar numa sala de combate posta só o painel, não a descrição antes."""
    conn, canal, cog = await preparar()
    incursao, _ = montar_conteudo(
        cog, incursao_id="entrada", salas=salas_de_combate(DURAO)
    )
    run = await montar_run(conn, canal, cog, "entrada")

    antes = len(canal.mensagens)
    alvo = (await cog._opcoes(run, 1))[0]
    assert alvo.e_combate
    msg = await canal.fetch_message(run["mensagem_id"])
    for user_id in JOGADORES:
        await cog.votar(FakeInteraction(canal, user_id, msg), run["id"], 1, alvo.id)

    run = await db.buscar_run(conn, run["id"])
    assert run["status"] == "em_sala" and run["sala_atual"] == alvo.id
    novas = canal.mensagens[antes:]
    com_embed = [m for m in novas if m.embeds]
    assert len(com_embed) == 1, f"esperava só o painel, vieram {len(com_embed)} embeds"

    painel = com_embed[0]
    # a abertura do combate marca quem esta de pe
    assert all(f"<@{u}>" in (painel.content or "") for u in JOGADORES), painel.content
    # o painel ja traz descricao, monstro e HP: nada se perdeu ao tirar a entrada
    assert painel.embeds[0].description == alvo.descricao
    campos = {f.name: f.value for f in painel.embeds[0].fields}
    assert alvo.monstros[0].nome in campos
    assert "Grupo" in campos
    print("  sala de combate posta só o painel: ok")


async def caso_derrota_total():
    """Com o grupo inteiro caído, a run termina em fracasso."""
    conn, canal, cog = await preparar(classe="monge", nivel=1)
    incursao, _ = montar_conteudo(
        cog, incursao_id="letal", monstro_objetivo=IMBATIVEL, salas=salas_sem_combate()
    )
    run = await montar_run(conn, canal, cog, "letal")
    run = await atravessar_ate_objetivo(conn, canal, cog, run, incursao)

    # Com o 1 natural, o monstro erra de vez em quando: sobra rodada para todos cairem.
    for _ in range(len(JOGADORES) * 5):
        atual = await db.buscar_run(conn, run["id"])
        if atual["status"] != "objetivo":
            break
        estado = await cog._estado_combate(atual, incursao.objetivo)
        msg = await canal.fetch_message(atual["mensagem_id"])
        for c in list(estado.vivos):
            await cog.atacar(FakeInteraction(canal, c.user_id, msg), run["id"], "OBJ")

    run = await db.buscar_run(conn, run["id"])
    assert run["status"] == "fracasso", f"esperava fracasso, veio {run['status']}"
    assert any("fracassada" in (m.embeds[0].title or "") for m in canal.mensagens if m.embeds)

    hps = await db.hp_dos_participantes(conn, run["id"])
    assert all(hp == 0 for hp in hps.values()), hps

    # E a run perdida nao rende ouro a ninguem — nem o das salas do caminho.
    # A incursao paga de uma vez, no fecho, e so quando e concluida.
    assert await db.ouro_da_run(conn, run["id"]) == [], (
        await db.ouro_da_run(conn, run["id"])
    )
    for p in await db.quem_recebe_da_run(conn, run["id"]):
        assert await db.ouro(conn, p["id"]) == 0, f"{p['nome']} levou ouro de uma derrota"
    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  derrota total encerra a run: ok")


async def caso_descanso_cura():
    """A sala de Descanso levanta os caídos e cura uma fatia de quem está vivo."""
    conn, canal, cog = await preparar()
    # banco so de Descanso: o primeiro passo cura o grupo na certa
    incursao, _ = montar_conteudo(
        cog, incursao_id="cura", salas=salas_sem_combate(tipo="Descanso")
    )
    run = await montar_run(conn, canal, cog, "cura")

    # machuca o grupo antes do descanso
    await db.definir_hp_varios(conn, run["id"], {JOGADORES[0]: 0, JOGADORES[1]: 5})

    msg = await canal.fetch_message(run["mensagem_id"])
    alvo = (await cog._opcoes(run, 1))[0]
    for user_id in JOGADORES:
        await cog.votar(FakeInteraction(canal, user_id, msg), run["id"], 1, alvo.id)

    # o HP maximo vem da classe: o teste compara com a tabela, nao com um numero solto
    maximo = classes.classe(CLASSE_PADRAO).numeros(8).hp
    hps = await db.hp_dos_participantes(conn, run["id"])
    assert hps[JOGADORES[0]] == maximo // 2, (
        f"caído deveria voltar com metade, veio {hps[JOGADORES[0]]}"
    )
    # O descanso espera a escolha do que limpar, mas quem nao carrega nada ja
    # entra marcado: grupo limpo atravessa sem clique. Ver test_condicoes.py
    # para o descanso com condicoes na mesa.
    # O descanso nao completa mais: cura FRACAO_DESCANSO do maximo, sem passar do teto.
    esperado = min(maximo, 5 + max(1, int(maximo * motor.FRACAO_DESCANSO)))
    assert hps[JOGADORES[1]] == esperado, (
        f"machucado deveria ir a {esperado}, veio {hps[JOGADORES[1]]}"
    )
    assert (await db.buscar_run(conn, run["id"]))["linha_atual"] == 2

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  descanso cura uma fatia e levanta caídos: ok")


async def caso_restart_no_combate():
    """Os botões de ataque voltam a funcionar depois de um restart."""
    conn, canal, cog = await preparar()
    incursao, _ = montar_conteudo(
        cog, incursao_id="restart", monstro_objetivo=IMBATIVEL, salas=salas_sem_combate()
    )
    run = await montar_run(conn, canal, cog, "restart")
    run = await atravessar_ate_objetivo(conn, canal, cog, run, incursao)
    assert run["status"] == "objetivo"

    bot2 = FakeBot(conn, canal)
    cog2 = Incursoes(bot2)
    montar_conteudo(
        cog2, incursao_id="restart", monstro_objetivo=IMBATIVEL, salas=salas_sem_combate()
    )
    await cog2.restaurar_views()

    assert bot2.views_registradas, "nenhuma view restaurada"
    view, mensagem_id = bot2.views_registradas[0]
    assert isinstance(view, ViewCombate)
    assert mensagem_id == run["mensagem_id"]

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  botões de combate sobrevivem a um restart: ok")


async def caso_motor_puro():
    """O dano nunca fica negativo e o HP nunca passa do máximo nem do zero."""

    inimigo = motor.Inimigo(0, "Teste", ca=10, ataque=5, dano="1d4", hp_max=10, hp_atual=2)
    grupo = [motor.Combatente(1, "A", ca=10, bonus_ataque=5, dano_arma="1d4", hp_max=10, hp_atual=3)]
    estado = motor.EstadoCombate([inimigo], 1, grupo)

    for _ in range(50):
        motor.atacar_inimigo(grupo[0], inimigo)
        assert inimigo.hp_atual >= 0
    assert estado.inimigos_derrotados

    inimigo.hp_atual = inimigo.hp_max  # de pe de novo, para revidar
    grupo[0].hp_atual = 1
    for _ in range(50):
        alvo = motor.sortear_alvo(estado)
        if alvo is None:
            break
        motor.contra_atacar(inimigo, alvo)
        assert grupo[0].hp_atual >= 0
    assert estado.grupo_caido and motor.sortear_alvo(estado) is None
    print("  motor: HP não passa dos limites: ok")


async def caso_o_resumo_abre_a_conta_do_dano():
    """O resumo privado diz quanto foi da arma e quanto foi de cada extra.

    Com multiataque e uma marca no inimigo, "16 de dano" não dizia de onde
    os 16 saíram — e era a conta que o jogador queria ver. A abertura sai
    só no resumo privado: o painel é reescrito a cada ação e carrega o
    grupo inteiro.
    """

    def arqueiro():
        c = motor.Combatente(
            1, "Arqueiro", ca=15, bonus_ataque=7, dano_arma="1d8+4",
            hp_max=60, hp_atual=60, dano_extra=3,
        )
        c.dano_por_alvo[0] = ("Marca do Cacador", "1d6")
        c.dano_bonus = "1d4"
        c.rotulo_dano_bonus = "Danca totemica"
        return c

    def ogro():
        return motor.Inimigo(
            0, "Ogro", ca=13, ataque=5, dano="1d10", hp_max=200, hp_atual=200
        )

    # Dado fixo no meio da faixa: sem isto um 20 natural no primeiro golpe
    # vira critico, as expressoes saem dobradas e o caso acusa falso.
    class DezNoDado:
        def randint(self, a, b):
            return 10 if b == 20 else (a + b) // 2

    alvo = ogro()
    golpe = motor.atacar_inimigo(
        arqueiro(), alvo, rng=DezNoDado(), garantido=True
    )
    rotulos = [parte.rotulo for parte in golpe.partes]
    assert rotulos == [
        "arma", "passiva", "Marca do Cacador", "Danca totemica"
    ], rotulos
    # A conta fecha: as partes SÃO o dano, não uma estimativa dele.
    assert sum(p.valor for p in golpe.partes) == golpe.dano, golpe.partes

    texto = embeds.resumo_do_golpe([(golpe, alvo.nome)])
    for parte in golpe.partes:
        assert parte.rotulo in texto, f"{parte.rotulo} não saiu no resumo: {texto}"
    assert "1d8+4" in texto and "1d6" in texto, texto

    # No crítico, a expressão mostrada é a que foi ROLADA: dados em dobro.
    critico = ogro()
    g = motor.atacar_inimigo(
        arqueiro(), critico, rng=DezNoDado(), garantido=True,
        critico_forcado=True,
    )
    assert sum(p.valor for p in g.partes) == g.dano, g.partes
    texto = embeds.resumo_do_golpe([(g, critico.nome)])
    assert "2d8+4" in texto and "2d6" in texto, texto

    # Fonte única não ganha abertura: repetir o total embaixo dele não diz nada.
    simples = motor.Combatente(
        2, "Bruto", ca=15, bonus_ataque=7, dano_arma="2d6+4",
        hp_max=60, hp_atual=60,
    )
    so_um = ogro()
    g = motor.atacar_inimigo(simples, so_um, rng=DezNoDado(), garantido=True)
    assert embeds.abertura_do_dano(g) == [], g.partes

    # O golpe socorrido pela Inspiração sai pela MESMA conta, aberta igual.
    perdido = ogro()
    quem = arqueiro()
    g = motor.atacar(
        quem.nome, -50, quem.dano_arma, perdido.nome, perdido.ca,
        rng=DezNoDado(),
    )
    assert not g.acertou, g.total
    g.bonus += 60
    assert motor.refazer_o_golpe(quem, perdido, g, rng=DezNoDado())
    rotulos = [parte.rotulo for parte in g.partes]
    assert rotulos == [
        "arma", "passiva", "Marca do Cacador", "Danca totemica"
    ], rotulos
    assert sum(p.valor for p in g.partes) == g.dano, g.partes
    print("  o resumo abre o dano por fonte, e a conta fecha: ok")


async def main():
    try:
        await _casos()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass


async def caso_o_ataque_adia_antes_de_resolver():
    """O clique de atacar avisa o Discord ANTES de resolver o turno.

    O Discord da 3 segundos para a primeira resposta a uma interacao. O
    caminho do ataque resolve o turno, faz as criaturas agirem e redesenha o
    painel antes de responder — numa maquina modesta isso passa dos 3
    segundos, o token morre e o jogador ve "esta interacao falhou"
    (erro 10062). Aconteceu em producao no primeiro dia no servidor.

    O `defer` troca os 3 segundos por 15 minutos. Este caso prova as tres
    coisas que a correcao precisa manter de pe ao mesmo tempo.
    """
    conn, canal, cog = await preparar()
    incursao, _ = montar_conteudo(
        cog, incursao_id="adiar", monstro_objetivo=DURAO, salas=salas_sem_combate()
    )
    run = await montar_run(conn, canal, cog, "adiar")
    run = await atravessar_ate_objetivo(conn, canal, cog, run, incursao)
    assert run["status"] == "objetivo"

    painel = await canal.fetch_message(run["mensagem_id"])
    inter = FakeInteraction(canal, JOGADORES[0], painel)
    await cog.atacar(inter, run["id"], "OBJ")

    # 1. adiou — e e isso que compra os 15 minutos
    assert inter.adiado, "o ataque tem de adiar antes de resolver o turno"

    # 1b. e adiou do jeito CERTO. Num clique de botao, `defer(ephemeral=True)`
    #     sozinho vira DEFERRED_MESSAGE_UPDATE e o ephemeral e ignorado: a
    #     "resposta original" passa a ser a mensagem do botao, que aqui e o
    #     proprio painel. So com `thinking=True` nasce uma efemera de
    #     verdade. Isto ja foi para producao errado e apagava o painel a
    #     cada troca de turno.
    assert inter._original() is not painel, (
        "a resposta adiada virou o painel: faltou thinking=True no defer"
    )

    # 2. o jogador continua recebendo o texto, so que por outro caminho
    assert inter.resposta, "o jogador ficou sem resposta nenhuma"

    # 3. e a efemera apagavel e a do defer, NAO o painel do combate.
    #    `_limpar_efemeras` apaga com `delete_original_response`, que so
    #    alcanca a resposta original — foi por isso que a correcao usou
    #    `edit_original_response` em vez de `followup.send`. Se a original
    #    fosse o painel, limpar as efemeras apagaria o combate da tela.
    antes_do_painel = painel.apagada if hasattr(painel, "apagada") else None
    await cog._limpar_efemeras(run["id"])
    depois_do_painel = painel.apagada if hasattr(painel, "apagada") else None
    assert depois_do_painel == antes_do_painel, "limpar as efemeras apagou o painel"
    assert await canal.fetch_message(run["mensagem_id"]) is not None, (
        "o painel do combate sumiu do canal"
    )
    print("  o ataque adia a interacao e nao sacrifica o painel: ok")


async def _casos():
    await caso_motor_puro()
    await caso_o_resumo_abre_a_conta_do_dano()
    await caso_hp_inicial()
    await caso_vitoria_no_objetivo()
    await caso_combate_no_meio_do_mapa()
    await caso_rodadas_e_contra_ataque()
    await caso_combate_nao_polui_o_canal()
    await caso_sala_de_combate_nao_duplica_entrada()
    await caso_derrota_total()
    await caso_descanso_cura()
    await caso_restart_no_combate()
    await caso_o_ataque_adia_antes_de_resolver()


asyncio.run(main())
print("TESTES DE COMBATE PASSARAM")
