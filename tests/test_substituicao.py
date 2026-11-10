"""Agir no lugar de quem não age: a medida contra o combate travado.

O combate anda por iniciativa, e a fila **para** no primeiro jogador que ainda
não escolheu. Quem fecha o Discord no meio de um combate para o grupo inteiro,
e não havia saída: nem botão, nem comando, nem prazo.

A regra que entrou: passados **15 minutos** sem o jogador agir, outro jogador
propõe uma ação no lugar dele, e a **maioria dos outros** — o grupo de pé menos
o ausente, que não vota sobre a própria vez — fecha a proposta. O comando É o
voto, como no `/incursao desistir`: quem chama primeiro propõe e já concorda, e
os outros chamam de novo para concordar.

Três decisões que moram aqui, e as razões:

**Poção não entra.** Ela foi comprada com o ouro daquele personagem e sai da
bolsa dele para nunca voltar; uso de habilidade volta no descanso. O grupo pode
atacar e pode usar habilidade, e não pode gastar o item de outra pessoa.

**A espera é por ausência, não por rodada.** Quem sumiu custa 15 minutos ao
grupo uma vez. Da segunda rodada em diante, enquanto continuar sumido, a
proposta sai na hora — cobrar 15 minutos por rodada seria o travamento de novo,
em parcelas. E ele aparecer e agir devolve a espera: voltar ao controle é voltar
inclusive ao direito de pensar. Isso não é um sinalizador que alguém liga e
desliga: sai do turno mais recente dele (`run_turnos.substituto`).

**O uso da habilidade é gasto ao resolver, não ao propor.** Entre propor e
resolver passa uma votação, e proposta recusada não pode custar nada a ninguém.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import config, database as db, motor  # noqa: E402
from src.cogs.incursao import Incursoes  # noqa: E402
from fakes import (  # noqa: E402
    CANAL,
    GUILD,
    INDEFESO,
    JOGADORES,
    FakeBot,
    FakeCanal,
    FakeInteraction,
    FakeUsuario,
    criar_grupo,
    leu,
    montar_conteudo,
    salas_sem_combate,
)

BANCO = Path(__file__).resolve().parent / "teste_substituicao.db"
_ABERTAS = []
# Nao morre e nao revida: o combate so acaba quando o caso quer.
DURAO = {**INDEFESO, "hp": 4000}


async def preparar(quantos=3, classe="guerreiro", inimigos=2):
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
    await criar_grupo(conn, nivel=8, classe=classe)
    canal = FakeCanal(CANAL)
    cog = Incursoes(FakeBot(conn, canal))
    incursao, _ = montar_conteudo(
        cog, tamanho="Curta", monstro_objetivo=DURAO, inimigos_objetivo=inimigos,
        salas=salas_sem_combate(),
    )
    run_id = await db.criar_run(conn, GUILD, CANAL, incursao.id, JOGADORES[0])
    for user_id in JOGADORES[:quantos]:
        p = await db.personagem_por_nome(conn, GUILD, user_id, f"Heroi{user_id}")
        await db.adicionar_participante(conn, run_id, user_id, p["id"])
    await db.inicializar_hp(conn, run_id)
    await db.atualizar_run(
        conn, run_id, status="objetivo", sala_atual="OBJ",
        linha_atual=incursao.passos + 1,
    )
    run = await db.buscar_run(conn, run_id)
    await cog._abrir_combate(run, incursao.objetivo)
    return conn, canal, cog, incursao, await db.buscar_run(conn, run_id)


async def envelhecer_a_vez(conn, run_id, passo, minutos):
    """Faz a vez atual parecer aberta há `minutos`, sem esperar de verdade."""
    quando = datetime.now(timezone.utc) - timedelta(minutes=minutos)
    await conn.execute(
        "UPDATE run_combate SET vez_desde = ? WHERE run_id = ? AND passo = ?",
        (quando.strftime("%Y-%m-%d %H:%M:%S"), run_id, passo),
    )
    await conn.commit()


async def pedir(cog, canal, quem, ausente, acao=None, alvo=None):
    """Chama `/incursao substituir` e devolve a interação, para ler o texto."""
    inter = FakeInteraction(canal, quem)
    await cog.substituir.callback(
        cog, inter, FakeUsuario(ausente), acao=acao, alvo=alvo
    )
    return inter


async def turnos(conn, run_id):
    async with conn.execute(
        "SELECT user_id, acao, resolvida, substituto FROM run_turnos"
        " WHERE run_id = ? ORDER BY rodada, user_id", (run_id,),
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


async def _fechar(conn):
    await conn.close()
    BANCO.unlink(missing_ok=True)


# ------------------------------------------------------------ regra pura


def caso_a_espera_e_por_ausencia_e_nao_por_rodada():
    """15 minutos na primeira ausência; nenhum enquanto ela continuar."""
    agora = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
    quinze = motor.ESPERA_PARA_SUBSTITUIR
    assert quinze == timedelta(minutes=15), quinze

    # Primeira ausencia: o relogio manda.
    assert not motor.pode_propor_substituicao(agora - timedelta(minutes=14), agora, False)
    assert motor.pode_propor_substituicao(agora - quinze, agora, True) is True
    assert motor.pode_propor_substituicao(agora - quinze, agora, False) is True
    # Ja substituido na rodada passada: sai na hora, mesmo com a vez nova.
    assert motor.pode_propor_substituicao(agora, agora, True) is True

    # E o que falta, para o aviso poder dizer um numero.
    assert motor.falta_para_substituir(agora - timedelta(minutes=5), agora) == (
        timedelta(minutes=10)
    )
    # Passada a espera, nao falta tempo NEGATIVO.
    assert motor.falta_para_substituir(agora - timedelta(hours=1), agora) == (
        timedelta(0)
    )
    print("  a espera e por ausencia, e nao por rodada: ok")


def caso_maioria_dos_outros_nao_conta_o_ausente():
    """Quem decide é o grupo de pé MENOS o ausente: a vez é dele."""
    # Cinco de pe, um sumido: tres dos quatro restantes.
    assert motor.maioria_dos_outros(5) == 3
    assert motor.maioria_dos_outros(4) == 2
    assert motor.maioria_dos_outros(3) == 2
    # Dois de pe: quem propoe decide sozinho, porque nao ha quem consultar.
    assert motor.maioria_dos_outros(2) == 1
    # E nunca zero: com um de pe nao ha substituicao, mas o numero nao pode
    # virar "ninguem precisa concordar".
    assert motor.maioria_dos_outros(1) == 1
    # Sempre MENOS que o grupo inteiro: o ausente nao entra na conta.
    for presentes in range(2, 9):
        assert motor.maioria_dos_outros(presentes) <= presentes - 1 or presentes == 2
    print("  a maioria e dos OUTROS, e nao do grupo inteiro: ok")


# --------------------------------------------------- com banco e canal


async def caso_a_primeira_ausencia_custa_quinze_minutos():
    """Antes dos 15 minutos o comando recusa, e diz quanto falta."""
    conn, canal, cog, incursao, run = await preparar()
    a, b = JOGADORES[0], JOGADORES[1]
    passo = cog._passo(run)
    estado = await cog._estado_combate(run, incursao.objetivo)
    assert await cog._de_quem_e_a_vez(run, estado) == a, "a vez tinha de ser de A"

    inter = await pedir(cog, canal, b, a)
    texto = leu(inter) or ""
    assert "Faltam" in texto and "min" in texto, texto
    assert await db.substituicao_aberta(
        conn, run["id"], passo, estado.rodada, a
    ) is None, "abriu proposta antes da hora"

    # Catorze minutos ainda nao bastam; dezesseis bastam.
    await envelhecer_a_vez(conn, run["id"], passo, 14)
    assert "Faltam" in (leu(await pedir(cog, canal, b, a)) or "")
    await envelhecer_a_vez(conn, run["id"], passo, 16)
    inter = await pedir(cog, canal, b, a)
    assert "de acordo" in (leu(inter) or ""), leu(inter)
    assert await db.substituicao_aberta(conn, run["id"], passo, estado.rodada, a)

    await _fechar(conn)
    print("  a primeira ausencia custa os quinze minutos: ok")


async def caso_a_maioria_dos_outros_fecha_e_a_acao_sai():
    """Com a maioria dos outros de acordo, a ação vale como a vez do ausente."""
    conn, canal, cog, incursao, run = await preparar()
    a, b, c = JOGADORES[0], JOGADORES[1], JOGADORES[2]
    passo = cog._passo(run)
    estado = await cog._estado_combate(run, incursao.objetivo)
    await envelhecer_a_vez(conn, run["id"], passo, 16)
    antes = [i.hp_atual for i in estado.inimigos]

    # B propoe e ja concorda: 1 de 2.
    inter = await pedir(cog, canal, b, a, alvo="0")
    assert "1/2" in (leu(inter) or ""), leu(inter)
    assert not await turnos(conn, run["id"]), "resolveu sem a maioria"

    # C concorda: fecha.
    inter = await pedir(cog, canal, c, a)
    assert "age no lugar" in (leu(inter) or ""), leu(inter)

    gravados = await turnos(conn, run["id"])
    assert len(gravados) == 1, gravados
    assert gravados[0]["user_id"] == a and gravados[0]["resolvida"] == 1, gravados
    # E fica gravado QUEM escolheu: e disso que a espera da proxima vez sai.
    assert gravados[0]["substituto"] == b, gravados
    # O ataque saiu de verdade, no alvo escolhido.
    novo = await cog._estado_combate(
        await db.buscar_run(conn, run["id"]), incursao.objetivo
    )
    assert novo.inimigos[0].hp_atual < antes[0], "o ataque nao saiu"
    assert novo.inimigos[1].hp_atual == antes[1], "bateu no alvo errado"
    # A proposta sai da mesa quando resolve.
    assert await db.substituicao_aberta(
        conn, run["id"], passo, estado.rodada, a
    ) is None

    await _fechar(conn)
    print("  a maioria dos outros fecha, e a acao sai na vez do ausente: ok")


async def caso_quem_continua_sumido_nao_custa_quinze_de_novo():
    """Da segunda rodada em diante a proposta sai na hora — e voltar a devolve.

    Cobrar 15 minutos por rodada seria o travamento de volta, em parcelas. E a
    memória disso não é sinalizador nenhum: é o turno mais recente dele.
    """
    conn, canal, cog, incursao, run = await preparar(quantos=2)
    a, b = JOGADORES[0], JOGADORES[1]
    passo = cog._passo(run)
    estado = await cog._estado_combate(run, incursao.objetivo)

    # Rodada 1: espera, propoe, e com 2 de pe o proponente fecha sozinho.
    await envelhecer_a_vez(conn, run["id"], passo, 16)
    assert "age no lugar" in (leu(await pedir(cog, canal, b, a)) or "")
    assert await db.turno_foi_substituido(conn, run["id"], passo, a) is True

    # A vez de A volta (rodada nova) com o relogio zerado — e mesmo assim a
    # proposta sai, porque ele continua sumido.
    await db.atualizar_rodada(conn, run["id"], passo, estado.rodada + 1)
    nova = await db.buscar_run(conn, run["id"])
    estado2 = await cog._estado_combate(nova, incursao.objetivo)
    assert await cog._de_quem_e_a_vez(nova, estado2) == a
    inter = await pedir(cog, canal, b, a)
    assert "Faltam" not in (leu(inter) or ""), leu(inter)
    assert "age no lugar" in (leu(inter) or ""), leu(inter)

    # Agora ele APARECE e age: o turno mais recente passa a ser dele.
    await db.atualizar_rodada(conn, run["id"], passo, estado2.rodada + 1)
    terceira = await db.buscar_run(conn, run["id"])
    msg = await canal.fetch_message(terceira["mensagem_id"])
    await cog.atacar(FakeInteraction(canal, a, msg), run["id"], "OBJ")
    assert await db.turno_foi_substituido(conn, run["id"], passo, a) is False, (
        "ele agiu e continua marcado como ausente"
    )

    await _fechar(conn)
    print("  quem continua sumido nao custa 15 min de novo, e voltar devolve: ok")


async def caso_o_ausente_voltando_cancela_a_proposta():
    """O clique dele mata a proposta: quem voltou voltou ao controle."""
    conn, canal, cog, incursao, run = await preparar()
    a, b = JOGADORES[0], JOGADORES[1]
    passo = cog._passo(run)
    estado = await cog._estado_combate(run, incursao.objetivo)
    await envelhecer_a_vez(conn, run["id"], passo, 16)

    await pedir(cog, canal, b, a)
    assert await db.substituicao_aberta(conn, run["id"], passo, estado.rodada, a)

    # Ele age pelo painel, antes de a maioria fechar.
    msg = await canal.fetch_message(run["mensagem_id"])
    await cog.atacar(FakeInteraction(canal, a, msg), run["id"], "OBJ")

    assert await db.substituicao_aberta(
        conn, run["id"], passo, estado.rodada, a
    ) is None, "a proposta sobreviveu ao clique do ausente"
    gravados = await turnos(conn, run["id"])
    assert gravados[0]["substituto"] is None, (
        "a acao ficou marcada como substituida, e foi ele mesmo"
    )
    # E o apoio tambem sai: a rodada seguinte comeca de zero.
    assert not await db.apoios_da_substituicao(
        conn, run["id"], passo, estado.rodada, a
    )

    await _fechar(conn)
    print("  o ausente voltando cancela a proposta: ok")


async def caso_so_na_vez_dele_e_so_por_outro():
    """As recusas que protegem a medida de virar arma."""
    conn, canal, cog, incursao, run = await preparar()
    a, b, c = JOGADORES[0], JOGADORES[1], JOGADORES[2]
    passo = cog._passo(run)
    await envelhecer_a_vez(conn, run["id"], passo, 16)

    # A vez e de A: nao da para propor por B, que nem esta sendo esperado.
    inter = await pedir(cog, canal, c, b)
    assert "não está travada" in (leu(inter) or ""), leu(inter)
    # Nem por si mesmo: para isso existe o painel.
    inter = await pedir(cog, canal, a, a)
    assert "por você mesmo" in (leu(inter) or ""), leu(inter)
    # Quem caiu nao decide a vez de ninguem.
    await db.definir_hp(conn, run["id"], c, 0)
    inter = await pedir(cog, canal, c, a)
    assert "de pé" in (leu(inter) or ""), leu(inter)
    assert await db.substituicao_aberta(
        conn, run["id"], passo, 1, a
    ) is None, "alguma recusa deixou proposta aberta"

    await _fechar(conn)
    print("  so na vez dele, so por outro, e so quem esta de pe: ok")


async def caso_pocao_nao_entra():
    """O grupo pode atacar e usar habilidade. Poção é do ouro dele."""
    conn, canal, cog, incursao, run = await preparar()
    a, b = JOGADORES[0], JOGADORES[1]
    passo = cog._passo(run)
    await envelhecer_a_vez(conn, run["id"], passo, 16)
    await db.devolver_item(
        conn,
        (await db.personagem_por_nome(conn, GUILD, a, f"Heroi{a}"))["id"],
        "pocao_vida",
    )

    inter = await pedir(cog, canal, b, a, acao="pocao_vida")
    texto = leu(inter) or ""
    assert "Poção não entra" in texto, texto
    assert await db.substituicao_aberta(conn, run["id"], passo, 1, a) is None
    # E a lista que o autocomplete oferece tambem nao tem pocao nenhuma.
    personagem = await cog._personagem_na_run(run, a)
    ids = {h.id for h in cog._habilidades_substituiveis(personagem)}
    assert ids, "o ausente tinha de ter alguma habilidade acionavel"
    assert not any(i.startswith("pocao") for i in ids), ids

    await _fechar(conn)
    print("  pocao nao entra na substituicao: ok")


async def caso_uma_proposta_por_rodada():
    """Duas propostas no mesmo instante: uma entra na mesa, e só.

    Quem perde a corrida **não** vira acordo automático, e isso é decisão e
    não acidente: ele propôs outro alvo. Concordar por ele seria fazê-lo
    endossar uma ação que não escolheu — então ele é avisado de que já há uma
    proposta na mesa e chama de novo se concordar com ELA.

    O que a chave primária garante é o que importa: a vez do ausente é gasta
    uma vez, e um inimigo só leva dano.
    """
    conn, canal, cog, incursao, run = await preparar(quantos=4)
    a, b, c, d = JOGADORES[0], JOGADORES[1], JOGADORES[2], JOGADORES[3]
    passo = cog._passo(run)
    estado = await cog._estado_combate(run, incursao.objetivo)
    await envelhecer_a_vez(conn, run["id"], passo, 16)

    # Com 4 de pe sao 2 acordos. As duas propostas saem juntas, em alvos
    # diferentes: uma entra, a outra e recusada com o aviso.
    respostas = await asyncio.gather(
        pedir(cog, canal, b, a, alvo="0"),
        pedir(cog, canal, c, a, alvo="1"),
    )
    textos = [leu(i) or "" for i in respostas]
    assert sum(1 for t in textos if "de acordo" in t) == 1, textos
    assert sum(1 for t in textos if "mesmo instante" in t) == 1, textos
    assert not await turnos(conn, run["id"]), "resolveu com um acordo so"
    apoios = await db.apoios_da_substituicao(conn, run["id"], passo, 1, a)
    assert len(apoios) == 1, f"quem perdeu a corrida concordou sem querer: {apoios}"

    # Agora D concorda com a proposta que esta na mesa: fecha.
    assert "age no lugar" in (leu(await pedir(cog, canal, d, a)) or "")
    gravados = await turnos(conn, run["id"])
    assert len(gravados) == 1, f"a vez do ausente foi gasta {len(gravados)}x"
    assert gravados[0]["user_id"] == a, gravados
    atacados = [
        i for i in (
            await cog._estado_combate(
                await db.buscar_run(conn, run["id"]), incursao.objetivo
            )
        ).inimigos if i.hp_atual < i.hp_max
    ]
    assert len(atacados) == 1, (
        f"dois inimigos levaram dano: as duas propostas resolveram ({atacados})"
    )

    await _fechar(conn)
    print("  uma proposta por rodada, e a vez gasta uma vez so: ok")


async def caso_dois_acordos_no_mesmo_instante_gastam_uma_vez():
    """Dois acordos fechando juntos resolvem a proposta UMA vez.

    Os dois contam a maioria, os dois a encontram fechada, e os dois chamam o
    resolvedor. Sem a reivindicação do `tomar_a_substituicao`, a vez do ausente
    seria gasta duas vezes — e ele atacaria duas vezes numa rodada.

    Chamada sequencial não prova nada aqui: a segunda encontraria a proposta já
    fora da mesa e pararia de qualquer forma.

    A proposta é uma HABILIDADE de propósito. Com um ataque o bug não apareceia:
    o `INSERT OR IGNORE` do `marcar_turno` barraria o segundo sozinho. A
    habilidade gasta o uso ANTES de marcar o turno, então sem a reivindicação o
    segundo chega a mexer nos recursos do ausente — e o grupo lê duas vezes que
    a substituição aconteceu, e depois lê que a habilidade não tinha uso.
    """
    conn, canal, cog, incursao, run = await preparar(quantos=4)
    a, b, c, d = JOGADORES[0], JOGADORES[1], JOGADORES[2], JOGADORES[3]
    passo = cog._passo(run)
    await envelhecer_a_vez(conn, run["id"], passo, 16)
    await db.definir_hp(conn, run["id"], a, 10)
    personagem = await cog._personagem_na_run(run, a)
    hab = next(
        h for h in cog._habilidades_substituiveis(personagem) if h.id == "second_wind"
    )

    # Com 4 de pe sao 2 acordos. B propoe e ja e o primeiro.
    assert "1/2" in (leu(await pedir(cog, canal, b, a, acao=hab.id)) or "")
    # C e D concordam no mesmo instante: os dois veem 2/2.
    respostas = await asyncio.gather(pedir(cog, canal, c, a), pedir(cog, canal, d, a))

    gravados = await turnos(conn, run["id"])
    assert len(gravados) == 1, f"a vez do ausente foi gasta {len(gravados)}x"
    # O grupo foi avisado UMA vez de que a substituicao aconteceu.
    avisos = [leu(i) or "" for i in respostas]
    assert sum(1 for t in avisos if "age no lugar" in t) == 1, avisos
    # E ninguem leu que a habilidade nao tinha uso: ela tinha, e foi usada.
    assert not any(
        "não tem uso" in (m.content or "") for m in canal.enviadas
    ), "o segundo acordo mexeu nos usos do ausente"
    gastos = await db.usos_da_run(conn, run["id"], a)
    assert gastos.get((hab.chave_de_uso, f"combate:{passo}")) == 1, gastos

    await _fechar(conn)
    print("  dois acordos juntos gastam a vez do ausente uma vez: ok")


async def caso_passiva_nao_entra_e_quem_caiu_nao_apoia():
    """Duas bordas que o grupo poderia usar para forçar uma substituição.

    A lista oferecida é só o que o ausente poderia ACIONAR: passiva não é ação
    de turno, e propor uma seria pedir ao combate que resolvesse algo que não
    se resolve.

    E o apoio de quem caiu depois de concordar não conta mais: a maioria é de
    quem está de pé AGORA. Sem isso, três pessoas de pé poderiam fechar uma
    proposta com o voto de alguém que saiu do combate.
    """
    conn, canal, cog, incursao, run = await preparar(quantos=5)
    a, b, c, d = JOGADORES[0], JOGADORES[1], JOGADORES[2], JOGADORES[3]
    passo = cog._passo(run)
    await envelhecer_a_vez(conn, run["id"], passo, 16)

    # A lista oferecida nao tem passiva nenhuma, e propor uma e recusado.
    personagem = await cog._personagem_na_run(run, a)
    todas = [h for _t, h in personagem["habilidades"]]
    passivas = [h for h in todas if not h.acionavel]
    assert passivas, "o guerreiro tinha de ter alguma passiva: o caso precisa de uma"
    oferecidas = {h.id for h in cog._habilidades_substituiveis(personagem)}
    assert not (oferecidas & {h.id for h in passivas}), oferecidas
    inter = await pedir(cog, canal, b, a, acao=passivas[0].id)
    assert "não é uma ação" in (leu(inter) or ""), leu(inter)

    # Agora a maioria. Com 5 de pe sao 3 acordos; o limiar ENCOLHE junto com o
    # grupo, porque a maioria e de quem pode decidir agora.
    assert motor.maioria_dos_outros(5) == 3
    assert motor.maioria_dos_outros(4) == 2
    assert "1/3" in (leu(await pedir(cog, canal, b, a)) or "")
    assert "2/3" in (leu(await pedir(cog, canal, c, a)) or "")

    # C cai: sobram 4 de pe, e o limiar cai para 2. O apoio de C para de
    # contar, entao os acordos validos voltam a ser 1 — e B reafirmando NAO
    # fecha. Contando o apoio de quem caiu, B e C dariam 2 e fechariam aqui.
    await db.definir_hp(conn, run["id"], c, 0)
    inter = await pedir(cog, canal, b, a)
    assert "1/2" in (leu(inter) or ""), (
        f"o apoio de quem caiu continuou contando: {leu(inter)}"
    )
    assert not await turnos(conn, run["id"]), "resolveu com o voto de quem caiu"
    # E com D, que esta de pe, fecha: a regra barra o caido, e nao o acordo.
    assert "age no lugar" in (leu(await pedir(cog, canal, d, a)) or "")

    await _fechar(conn)
    print("  passiva nao entra, e o apoio de quem caiu nao conta: ok")


async def caso_a_habilidade_gasta_o_uso_so_ao_resolver():
    """Proposta recusada não custa o uso de ninguém.

    O uso é gasto na resolução, e não na proposta: entre as duas passa uma
    votação, e quem não foi substituído tem de sair dela com tudo que tinha.
    """
    conn, canal, cog, incursao, run = await preparar()
    a, b, c = JOGADORES[0], JOGADORES[1], JOGADORES[2]
    passo = cog._passo(run)
    await envelhecer_a_vez(conn, run["id"], passo, 16)
    personagem = await cog._personagem_na_run(run, a)
    hab = next(h for h in cog._habilidades_substituiveis(personagem) if h.id == "second_wind")

    # B propoe a habilidade: 1 de 2, e o uso NAO foi gasto ainda.
    inter = await pedir(cog, canal, b, a, acao=hab.id)
    assert "1/2" in (leu(inter) or ""), leu(inter)
    assert "Second Wind" in (leu(inter) or ""), leu(inter)
    gastos = await db.usos_da_run(conn, run["id"], a)
    assert not gastos.get((hab.chave_de_uso, f"combate:{passo}")), (
        "a proposta gastou o uso antes de ser aceita"
    )

    # C concorda: resolve, e agora o uso saiu.
    await db.definir_hp(conn, run["id"], a, 10)
    inter = await pedir(cog, canal, c, a)
    assert "age no lugar" in (leu(inter) or ""), leu(inter)
    gastos = await db.usos_da_run(conn, run["id"], a)
    assert gastos.get((hab.chave_de_uso, f"combate:{passo}")) == 1, gastos
    gravados = await turnos(conn, run["id"])
    assert gravados[0]["acao"] == hab.id and gravados[0]["substituto"] == b, gravados

    await _fechar(conn)
    print("  a habilidade gasta o uso so ao resolver: ok")


async def main():
    try:
        caso_a_espera_e_por_ausencia_e_nao_por_rodada()
        caso_maioria_dos_outros_nao_conta_o_ausente()
        await caso_a_primeira_ausencia_custa_quinze_minutos()
        await caso_a_maioria_dos_outros_fecha_e_a_acao_sai()
        await caso_quem_continua_sumido_nao_custa_quinze_de_novo()
        await caso_o_ausente_voltando_cancela_a_proposta()
        await caso_so_na_vez_dele_e_so_por_outro()
        await caso_pocao_nao_entra()
        await caso_uma_proposta_por_rodada()
        await caso_dois_acordos_no_mesmo_instante_gastam_uma_vez()
        await caso_passiva_nao_entra_e_quem_caiu_nao_apoia()
        await caso_a_habilidade_gasta_o_uso_so_ao_resolver()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        BANCO.unlink(missing_ok=True)


asyncio.run(main())
print("TESTES DE SUBSTITUICAO PASSARAM")
