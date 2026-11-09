"""As telas: quem já rolou a sala, o painel da benção/maldição e a iniciativa.

Três coisas que o bot sabia e não dizia. O cartão da sala contava as rolagens
("3/5") sem nomear ninguém, então o grupo esperava sem saber de quem. A
condição que a sala deixava virava uma linha no meio das outras, com o número
de stacks de quem por acaso foi o último do laço. E a iniciativa não aparecia
em lugar nenhum da ficha, nem quando o jogador comprava botas para mexer nela.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import (  # noqa: E402
    classes as cl,
    condicoes as C,
    config,
    consequencias as X,
    database as db,
    embeds as E,
    itens,
    motor,
)
from src.incursoes import Sala  # noqa: E402
from src.cogs.ficha import Ficha, embed_ficha  # noqa: E402
from src.cogs.incursao import Incursoes  # noqa: E402
from fakes import (  # noqa: E402
    CANAL,
    JOGADORES,
    FakeBot,
    FakeCanal,
    FakeInteraction,
    leu,
    FakeUsuario,
    criar_grupo,
    montar_conteudo,
    sala,
    salas_sem_combate,
)

_ABERTAS = []
BANCO = Path(__file__).resolve().parent / "teste_telas.db"

IMPOSSIVEL = 99  # CD que ninguém alcança: a sala se perde sem depender do dado


# --------------------------------------------------------------- regra pura


def caso_efeito_somado_faz_a_conta():
    """O catálogo diz o que UM stack faz; a tela precisa do total."""
    assert C.efeito_somado("medo", 1) == "-2 em saves", C.efeito_somado("medo", 1)
    assert C.efeito_somado("medo", 3) == "-6 em saves", C.efeito_somado("medo", 3)
    # Condição que mexe em duas coisas soma as duas.
    assert C.efeito_somado("perdicao", 2) == "-2 em ataques · -2 em saves"
    # Porcentagem também é número: a Deterioração é -10% por stack.
    assert C.efeito_somado("deterioracao", 3) == "-30% de HP máximo"
    # E a de grupo de perícia nomeia as perícias.
    somado = C.efeito_somado("fraqueza", 2)
    assert somado.startswith("-4 em "), somado
    assert "Atletismo" in somado, somado
    print("  efeito_somado multiplica os números do catálogo: ok")


def caso_painel_diz_quem_ficou_com_quanto():
    """O painel nomeia cada um com o stack DELE, e não um número para todos."""
    titulo, corpo = E.painel_da_condicao(
        X.CondicaoAplicada("medo", {"Mira": 1, "Dorn": 1, "Kael": 2})
    )
    assert "Medo" in titulo and C.POR_ID["medo"].icone in titulo, titulo
    assert "o grupo inteiro" in titulo, titulo
    for nome in ("Mira", "Dorn", "Kael"):
        assert nome in corpo, (nome, corpo)
    # O ×2 é de quem tem dois, e só dele.
    assert "Kael ×2" in corpo, corpo
    assert "Mira ×" not in corpo, corpo
    # O total de quem empilhou aparece feito.
    assert "-4 em saves" in corpo, corpo
    # E o prazo, que é a regra que o jogador não tem como adivinhar.
    assert "Decai 1 stack" in corpo, corpo
    print("  o painel dá o stack de cada um e o prazo: ok")


def caso_painel_de_um_so_nao_fala_do_grupo():
    """Com um nome, o título não mente dizendo 'o grupo inteiro'."""
    titulo, corpo = E.painel_da_condicao(X.CondicaoAplicada("bencao", {"Mira": 1}))
    assert "grupo" not in titulo, titulo
    # Um stack não ganha a linha do total: repetiria a de cima.
    assert "isso vale" not in corpo, corpo
    print("  painel de um personagem só não inventa grupo: ok")


def caso_painel_avisa_o_teto():
    """Quem está a um ponto de sair da incursão é nomeado."""
    _, corpo = E.painel_da_condicao(
        X.CondicaoAplicada("exaustao", {"Mira": 4, "Dorn": 5, "Kael": 1})
    )
    assert "⚠️" in corpo, corpo
    assert "Mira** (4/5)" in corpo, corpo
    assert "Dorn** (5/5)" in corpo, corpo
    assert "Kael** (1/5)" not in corpo, corpo
    # A Exaustão não decai, e o texto dela já diz isso: a tela não repete.
    assert "Decai 1 stack" not in corpo, corpo

    # Longe do teto, nada de aviso.
    _, longe = E.painel_da_condicao(X.CondicaoAplicada("deterioracao", {"Mira": 3}))
    assert "⚠️" not in longe, longe
    print("  o painel avisa quem está a um ponto de sair: ok")


def caso_cartao_nomeia_quem_rolou_e_quem_falta():
    """O cartão da sala troca o '3/5' pelos nomes."""
    cenario = Sala(
        id="S1",
        nome="Sala S1",
        tipo="Armadilha",
        descricao="Descrição da sala S1.",
        cd=14,
        alvo_progresso=5,
        pericias=["Percepção"],
    )

    embed, _ = E.sala_aberta(cenario, 2, (), ["Mira", "Dorn"], 6, tier=2)
    campos = {f.name: f.value for f in embed.fields}
    nome = next(n for n in campos if n.startswith("Rolaram"))
    assert nome == "Rolaram 0/2", nome
    assert "Mira" in campos[nome] and "Dorn" in campos[nome], campos[nome]

    embed, _ = E.sala_aberta(cenario, 2, ["Mira"], ["Dorn"], 6, tier=2)
    campos = {f.name: f.value for f in embed.fields}
    nome = next(n for n in campos if n.startswith("Rolaram"))
    assert nome == "Rolaram 1/2", nome
    linhas = campos[nome].split("\n")
    assert len(linhas) == 2, linhas
    assert "Mira" in linhas[0] and "Dorn" not in linhas[0], linhas
    assert "Dorn" in linhas[1], linhas
    # O dado de cada um fica para o fecho da sala.
    assert "🎲" in linhas[0] and "CD" not in campos[nome], campos[nome]
    print("  o cartão da sala nomeia quem rolou e quem falta: ok")


def caso_o_caminho_diz_passou_ou_falhou():
    """O resumo do fim marca cada sala com ✅ ou ❌, e não com a dificuldade.

    A dificuldade é a CD escrita no banco — número de quem monta a sala. Quem
    lê o fecho de uma run quer saber em qual sala o grupo se deu mal.
    """
    import discord

    def feita(ident, nome, dificuldade):
        return Sala(
            id=ident, nome=nome, tipo="Armadilha", descricao="",
            dificuldade=dificuldade, cd=14, alvo_progresso=5,
        )

    venceu = feita("A", "Corredor que range", "Fácil")
    perdeu = feita("B", "Poço sem fundo", "Difícil")
    e = discord.Embed()
    E.campo_caminho(e, [(venceu, True), (perdeu, False)])

    campo = next(f for f in e.fields if f.name.startswith("Caminho"))
    assert f"✅ 🕸️ **{venceu.nome}**" in campo.value, campo.value
    assert f"❌ 🕸️ **{perdeu.nome}**" in campo.value, campo.value
    # A dificuldade saiu de vez.
    for rotulo in ("Fácil", "Média", "Difícil"):
        assert rotulo not in campo.value, (rotulo, campo.value)
    # Caminho vazio não desenha campo nenhum.
    vazio = discord.Embed()
    E.campo_caminho(vazio, [])
    assert not vazio.fields
    print("  o caminho marca passou ou falhou, sem a dificuldade: ok")


def _resolucao_de_evento(alvo_progresso, *dados):
    """Uma sala de Evento resolvida com os dados dados, sem banco nenhum.

    O primeiro de `dados` é de quem passa fácil; os outros entram como estão.
    """
    evento = Sala(
        id="EV", nome="O Mercador Cego", tipo="Evento", descricao="",
        pericias=["Intuição"], cd=12, alvo_progresso=alvo_progresso,
    )
    return motor.ResolucaoSala(
        sala=evento,
        resultados=[
            motor.ResultadoTeste(
                user_id=i, personagem=f"Heroi{i}", pericia="Intuição",
                d20=d20, modificador=4, cd=12,
            )
            for i, d20 in enumerate(dados, start=1)
        ],
        total_participantes=len(dados),
    )


def caso_sala_vencida_nao_anuncia_castigo():
    """Sala vencida com alguém falhando o dado: a tela não pode prometer castigo.

    A regra do motor é "a sala é do grupo": vencida, não cobra de NINGUÉM —
    nem de quem rolou 3. O campo "Quem falhou" não olhava se a sala tinha sido
    vencida e imprimia, do lado do nome, a consequência da falha: *carrega uma
    maldição ou um ponto de Exaustão pelo resto da incursão*. Ninguém levava
    nada — o motor nunca aplicou —, mas o grupo lia aquilo e contava a maldição
    como recebida. Era um erro só da tela, e é por isso que durou: o banco
    estava certo, e quem conferia o banco não via problema nenhum.
    """
    vencida = _resolucao_de_evento(6, 18, 3)  # 18 passa e já estoura o alvo
    assert vencida.superada and vencida.quem_falhou, "o caso precisa das duas"
    campos = {f.name: f.value for f in E.resultado_sala(vencida).fields}
    tudo = "\n".join(campos.values())

    # Nenhuma palavra de castigo na tela de uma sala vencida.
    for proibida in ("maldição", "Exaustão", "debuff", "leva dano"):
        assert proibida not in tudo, (proibida, tudo)
    quem = campos.get("Quem falhou", "")
    assert "Heroi2" in quem, quem
    assert "não paga nada" in quem, quem
    # Singular com um só: "Heroi2 — não somaram" era o que saía.
    assert "não somou progresso" in quem, quem

    # E a sala PERDIDA cobra do grupo, nao so de quem falhou o dado: a outra
    # metade da mesma regra, que o campo antigo tambem dizia errado.
    perdida = _resolucao_de_evento(99, 18, 3)
    assert not perdida.superada
    quem = next(
        f.value for f in E.resultado_sala(perdida).fields if f.name == "Quem falhou"
    )
    assert "todos que a encararam" in quem, quem
    assert "inclusive quem passou" in quem, quem
    assert "maldição" in quem, quem
    # Dois falhando volta ao plural.
    dois = _resolucao_de_evento(6, 18, 3, 2)
    quem = next(
        f.value for f in E.resultado_sala(dois).fields if f.name == "Quem falhou"
    )
    assert "não somaram progresso" in quem, quem

    print("  sala vencida nao anuncia castigo, e a perdida cobra do grupo: ok")


# ------------------------------------------------------ com banco e canal


async def preparar(salas, tier=4, nivel=8, classe=None):
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass
    config.DB_PATH = BANCO
    config.DB_PATH.unlink(missing_ok=True)
    config.TAMANHO_GRUPO = 5
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    await criar_grupo(conn, nivel=nivel, **({"classe": classe} if classe else {}))
    canal = FakeCanal(CANAL)
    cog = Incursoes(FakeBot(conn, canal))
    montar_conteudo(cog, tamanho="Curta", tier=tier, salas=salas)
    return conn, canal, cog


async def montar_run(conn, canal, cog):
    await cog.entrar.callback(cog, FakeInteraction(canal, JOGADORES[0]), cog.incursoes["t"].tier, "t")
    run = await db.run_do_canal(conn, CANAL)
    msg = await canal.fetch_message(run["mensagem_id"])
    for user_id in JOGADORES[1:]:
        await cog.recrutar(FakeInteraction(canal, user_id, msg), run["id"], "entrar")
    return await db.buscar_run(conn, run["id"])


async def abrir_sala(conn, canal, cog, run, passo=1):
    """Vota na primeira opção e para na sala, sem ninguém rolar ainda."""
    alvo = (await cog._opcoes(run, passo))[0]
    msg = await canal.fetch_message(run["mensagem_id"])
    for user_id in JOGADORES:
        await cog.votar(FakeInteraction(canal, user_id, msg), run["id"], passo, alvo.id)
    return alvo, await db.buscar_run(conn, run["id"])


async def campo_das_rolagens(canal, run):
    """O campo 'Rolaram N/M' do cartão da sala que está no canal."""
    msg = await canal.fetch_message(run["mensagem_id"])
    campos = {f.name: f.value for f in msg.embeds[0].fields}
    nome = next(n for n in campos if n.startswith("Rolaram"))
    return nome, campos[nome]


async def caso_o_cartao_vai_marcando_quem_rolou():
    """A cada rolagem, o nome muda de lista no cartão que está no canal."""
    conn, canal, cog = await preparar(
        [sala(f"S{i}", "Armadilha", cd=IMPOSSIVEL, alvo_progresso=99,
              pericias=["Percepção"]) for i in range(1, 7)]
    )
    run = await montar_run(conn, canal, cog)
    alvo, run = await abrir_sala(conn, canal, cog, run)
    nomes = {
        p["user_id"]: p["nome"] for p in await db.personagens_da_run(conn, run["id"])
    }

    # Recém-aberta: ninguém rolou, e todos estão na lista dos que faltam.
    nome, valor = await campo_das_rolagens(canal, run)
    assert nome == f"Rolaram 0/{len(JOGADORES)}", nome
    for quem in nomes.values():
        assert quem in valor, (quem, valor)
    assert "🎲" not in valor, valor

    # O primeiro rola: o nome dele sai dos que faltam e entra nos que rolaram.
    msg = await canal.fetch_message(run["mensagem_id"])
    primeiro = JOGADORES[0]
    await cog.rolar(FakeInteraction(canal, primeiro, msg), run["id"], alvo.id)
    nome, valor = await campo_das_rolagens(canal, run)
    assert nome == f"Rolaram 1/{len(JOGADORES)}", nome
    rolou, faltam = valor.split("\n")
    assert nomes[primeiro] in rolou, (rolou, nomes[primeiro])
    assert nomes[primeiro] not in faltam, (faltam, nomes[primeiro])
    for outro in JOGADORES[1:]:
        assert nomes[outro] in faltam, (nomes[outro], faltam)

    # Dois: a conta e as duas listas acompanham.
    await cog.rolar(FakeInteraction(canal, JOGADORES[1], msg), run["id"], alvo.id)
    nome, valor = await campo_das_rolagens(canal, run)
    assert nome == f"Rolaram 2/{len(JOGADORES)}", nome
    rolou, faltam = valor.split("\n")
    assert nomes[JOGADORES[1]] in rolou and nomes[JOGADORES[1]] not in faltam, valor

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  o cartão marca cada rolagem com o nome de quem rolou: ok")


async def caso_quem_esta_caido_nao_entra_na_conta():
    """A sala fecha quando os de PÉ rolam, e é essa a conta que o cartão diz."""
    conn, canal, cog = await preparar(
        [sala(f"S{i}", "Armadilha", cd=IMPOSSIVEL, alvo_progresso=99,
              pericias=["Percepção"]) for i in range(1, 7)]
    )
    run = await montar_run(conn, canal, cog)
    caido = JOGADORES[-1]
    await db.inicializar_hp(conn, run["id"])
    await db.definir_hp(conn, run["id"], caido, 0)

    alvo, run = await abrir_sala(conn, canal, cog, run)
    nomes = {
        p["user_id"]: p["nome"] for p in await db.personagens_da_run(conn, run["id"])
    }
    nome, valor = await campo_das_rolagens(canal, run)
    assert nome == f"Rolaram 0/{len(JOGADORES) - 1}", nome
    assert nomes[caido] not in valor, (nomes[caido], valor)

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  quem está caído não é cobrado nem contado: ok")


async def caso_a_sala_deixa_o_painel_da_condicao():
    """A armadilha perdida deixa um painel próprio, com todos os nomes."""
    conn, canal, cog = await preparar(
        [sala(f"S{i}", "Armadilha", cd=IMPOSSIVEL, alvo_progresso=99,
              pericias=["Percepção"]) for i in range(1, 7)]
    )
    run = await montar_run(conn, canal, cog)
    alvo, run = await abrir_sala(conn, canal, cog, run)
    msg = await canal.fetch_message(run["mensagem_id"])
    for user_id in JOGADORES:
        atual = await db.buscar_run(conn, run["id"])
        if atual["status"] != "em_sala":
            break
        await cog.rolar(FakeInteraction(canal, user_id, msg), run["id"], alvo.id)

    carregadas = await db.condicoes_da_run(conn, run["id"])
    debuff = next(iter(next(iter(carregadas.values()))))
    nomes = {
        p["user_id"]: p["nome"] for p in await db.personagens_da_run(conn, run["id"])
    }
    resultados = [
        m for m in canal.mensagens
        if m.embeds and "superada" not in (m.embeds[0].title or "")
        and any(f.name.startswith("Rolagens") for f in m.embeds[0].fields)
    ]
    assert resultados, "esperava o resultado da sala no canal"
    campos = {f.name: f.value for f in resultados[-1].embeds[0].fields}
    painel = next(
        (v for n, v in campos.items() if C.POR_ID[debuff].nome in n), None
    )
    assert painel is not None, (
        f"a {C.POR_ID[debuff].nome} deveria ter campo próprio; vieram {list(campos)}"
    )
    for quem in nomes.values():
        assert quem in painel, (quem, painel)
    # A linha solta antiga não volta: a condição mora no painel.
    assert "Todos ficam com" not in "\n".join(campos.values())

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  a sala perdida deixa a maldição em painel próprio: ok")


async def caso_evento_vencido_nao_deixa_debuff_em_ninguem():
    """A prova no banco: Evento vencido com uma falha no dado, e nada de ruim.

    O caso de cima garante que a TELA não promete castigo; este garante que o
    banco não guarda nenhum. São as duas metades da mesma queixa da mesa — "a
    sala deu sucesso e o Bruno tomou maldição" —, e só uma delas era verdade.

    O dado é roteirizado porque a ordem importa: a sala fecha no instante em
    que o alvo é atingido, então a falha tem de vir ANTES do acerto grande.
    Com o acerto primeiro a sala fecharia com uma rolagem só, e ninguém teria
    falhado — não haveria caso.
    """
    salas = [
        sala(f"E{i}", "Evento", cd=20, alvo_progresso=3, pericias=["Intuição"])
        for i in range(1, 7)
    ]
    conn, canal, cog = await preparar(salas)
    run = await montar_run(conn, canal, cog)
    alvo, run = await abrir_sala(conn, canal, cog, run)

    # 1 falha contra CD 20; 20 passa e estoura o alvo de 3.
    roteiro = [1, 20, 20, 20, 20]
    de_verdade = motor.rolar_d20
    motor.rolar_d20 = lambda *a, **k: roteiro.pop(0) if roteiro else 20
    try:
        msg = await canal.fetch_message(run["mensagem_id"])
        for user_id in JOGADORES:
            atual = await db.buscar_run(conn, run["id"])
            if atual["status"] != "em_sala":
                break
            await cog.rolar(FakeInteraction(canal, user_id, msg), run["id"], alvo.id)
    finally:
        motor.rolar_d20 = de_verdade

    resultados = [
        m for m in canal.mensagens
        if m.embeds and any(f.name == "Rolagens" for f in m.embeds[0].fields)
    ]
    assert resultados, "esperava o resultado da sala no canal"
    embed = resultados[-1].embeds[0]
    campos = {f.name: f.value for f in embed.fields}
    assert "superada" in (embed.title or ""), embed.title
    assert "Quem falhou" in campos, campos
    assert "não paga nada" in campos["Quem falhou"], campos["Quem falhou"]

    # O banco: ninguem carrega nada de ruim. O Evento vencido DA um buff para
    # todos, entao o que se cobra nao e "nenhuma condicao" — e nenhuma ruim.
    carregadas = await db.condicoes_da_run(conn, run["id"])
    ruins = {
        (user_id, cid)
        for user_id, minhas in carregadas.items()
        for cid, stacks in minhas.items()
        if stacks > 0 and C.POR_ID[cid].ruim
    }
    assert not ruins, f"sala vencida deixou condicao ruim: {ruins}"

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  evento vencido nao deixa debuff nem exaustao em ninguem: ok")


async def caso_evento_perdido_cobra_de_quem_passou_tambem():
    """A outra metade: sala perdida cobra de TODOS que a encararam.

    O caso irmão do de cima. Juntos eles são a regra inteira — "a sala é do
    grupo, nos dois sentidos": vencida não cobra de ninguém, perdida cobra de
    todos, e o dado de cada um decide o PROGRESSO, não quem paga.

    O painel da maldição já era testado, mas com CD impossível: todo mundo
    falhava, então `quem_falhou` era o grupo inteiro e trocar "quem encarou"
    por "quem falhou" não mudava nada na tela. Aqui alguém PASSA e a sala se
    perde de todo jeito — é a única forma de a diferença aparecer.
    """
    salas = [
        sala(f"E{i}", "Evento", cd=20, alvo_progresso=99, pericias=["Intuição"])
        for i in range(1, 7)
    ]
    conn, canal, cog = await preparar(salas)
    run = await montar_run(conn, canal, cog)
    alvo, run = await abrir_sala(conn, canal, cog, run)

    # O primeiro passa; os outros falham. O alvo de 99 nao se alcanca, entao a
    # sala se perde mesmo com um acerto grande dentro dela.
    roteiro = [20, 1, 1, 1, 1]
    de_verdade = motor.rolar_d20
    motor.rolar_d20 = lambda *a, **k: roteiro.pop(0) if roteiro else 1
    try:
        msg = await canal.fetch_message(run["mensagem_id"])
        for user_id in JOGADORES:
            atual = await db.buscar_run(conn, run["id"])
            if atual["status"] != "em_sala":
                break
            await cog.rolar(FakeInteraction(canal, user_id, msg), run["id"], alvo.id)
    finally:
        motor.rolar_d20 = de_verdade

    resultados = [
        m for m in canal.mensagens
        if m.embeds and any(f.name == "Rolagens" for f in m.embeds[0].fields)
    ]
    assert resultados, "esperava o resultado da sala no canal"
    embed = resultados[-1].embeds[0]
    campos = {f.name: f.value for f in embed.fields}
    assert "superada" not in (embed.title or ""), embed.title
    # Sem ninguem passando o caso nao prova nada: e a asserção que o protege.
    assert "✅" in campos["Rolagens"], campos["Rolagens"]
    assert "todos que a encararam" in campos["Quem falhou"], campos["Quem falhou"]

    # E no banco: quem passou carrega a maldicao igual aos outros.
    carregadas = await db.condicoes_da_run(conn, run["id"])
    for user_id in JOGADORES:
        minhas = carregadas.get(user_id, {})
        ruins = [c for c, n in minhas.items() if n > 0 and C.POR_ID[c].ruim]
        assert ruins, f"{user_id} encarou a sala perdida e nao pagou nada"

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  evento perdido cobra de todos, inclusive de quem passou: ok")


async def caso_stack_e_por_personagem_e_nao_do_ultimo_do_laco():
    """Quem já carregava a condição sai com ×2; os outros com ×1.

    Era o único número errado da tela: a linha antiga pegava o retorno da
    última chamada de `aplicar_condicao` e dizia aquele número para todos.
    """
    conn, canal, cog = await preparar(
        [sala(f"S{i}", "Armadilha", cd=IMPOSSIVEL, alvo_progresso=99,
              pericias=["Percepção"]) for i in range(1, 7)]
    )
    run = await montar_run(conn, canal, cog)
    # A armadilha sorteia UM debuff para o grupo: fixo aqui para o caso poder
    # dar o mesmo a alguém de antemão.
    X.debuff_da_armadilha = lambda rng=None: "medo"
    marcado = JOGADORES[2]
    await db.aplicar_condicao(conn, run["id"], marcado, "medo")

    alvo, run = await abrir_sala(conn, canal, cog, run)
    msg = await canal.fetch_message(run["mensagem_id"])
    for user_id in JOGADORES:
        atual = await db.buscar_run(conn, run["id"])
        if atual["status"] != "em_sala":
            break
        await cog.rolar(FakeInteraction(canal, user_id, msg), run["id"], alvo.id)

    nomes = {
        p["user_id"]: p["nome"] for p in await db.personagens_da_run(conn, run["id"])
    }
    resultados = [
        m for m in canal.mensagens
        if m.embeds and any(f.name.startswith("Rolagens") for f in m.embeds[0].fields)
    ]
    campos = {f.name: f.value for f in resultados[-1].embeds[0].fields}
    painel = next(v for n, v in campos.items() if "Medo" in n)
    assert f"{nomes[marcado]} ×2" in painel, (nomes[marcado], painel)
    for user_id in JOGADORES:
        if user_id != marcado:
            assert f"{nomes[user_id]} ×" not in painel, (nomes[user_id], painel)
    # E o total de quem empilhou sai com a conta feita.
    assert C.efeito_somado("medo", 2) in painel, painel

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  o stack mostrado é o de cada um: ok")


async def caso_ficha_mostra_a_iniciativa():
    """A ficha diz a iniciativa, e o equipamento mexe nela."""
    conn, canal, cog = await preparar(salas_sem_combate(), nivel=1)
    Ficha(FakeBot(conn, canal))
    dono = JOGADORES[0]
    personagem = await db.personagem_por_nome(conn, 1, dono, f"Heroi{dono}")
    autor = FakeInteraction(canal, dono).user

    campos = {f.name: f.value for f in embed_ficha(personagem, autor).fields}
    combate = campos["Combate"]
    esperado = personagem["saves"]["DES"]
    assert f"Iniciativa **{esperado:+d}**" in combate, (esperado, combate)
    # É a mesma conta que o combate vai rolar.
    assert motor.iniciativa_da_ficha(personagem) == esperado

    # Botas de iniciativa entram no número.
    botas = next(i for i in itens.CATALOGO if i.efeito.get("bonus_iniciativa"))
    await db.lancar_ouro(conn, personagem["id"], botas.custo, "teste")
    assert await db.comprar(conn, personagem["id"], botas.id, botas.custo)
    vestiu, _ = await db.equipar(conn, personagem["id"], botas.id, botas.slot)
    assert vestiu, "as botas deveriam vestir"
    vestido = await db.personagem_por_nome(conn, 1, dono, f"Heroi{dono}")
    com_botas = esperado + botas.efeito["bonus_iniciativa"]
    campos = {f.name: f.value for f in embed_ficha(vestido, autor).fields}
    assert f"Iniciativa **{com_botas:+d}**" in campos["Combate"], campos["Combate"]
    print(f"  a ficha mostra a iniciativa ({esperado:+d}, {com_botas:+d} com botas): ok")

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)


async def caso_os_campos_da_ficha_sao_os_quatro_nomes_limpos():
    """Os títulos da ficha, sem contagem e sem legenda.

    Eram "Tier 1 de 5", "Resistencias", "Proficiencias (2/6)" e
    "Habilidades (1) — ⚡ você aciona · ⚙️ o bot aplica". A cota de perícias
    e a contagem de habilidades são números que o jogador não decide nem usa,
    e o teto do tier é o mesmo para todo mundo — tudo isso era ruído na tela
    que ele mais abre.

    O ⚡ continua marcando a ativa, e a Marca do Caçador é ativa: o jogador
    tem de clicar nela.
    """
    conn, canal, cog = await preparar(
        salas_sem_combate(), nivel=1, classe="patrulheiro"
    )
    Ficha(FakeBot(conn, canal))
    dono = JOGADORES[0]
    personagem = await db.personagem_por_nome(conn, 1, dono, f"Heroi{dono}")
    embed = embed_ficha(personagem, FakeInteraction(canal, dono).user)
    campos = {f.name: f.value for f in embed.fields}

    assert list(campos) == [
        "Combate", "Salvaguardas", "Proficiencias", "Habilidades"
    ], list(campos)
    # "Tier 1", e não "Tier 1 de 5": o teto é o mesmo para todo mundo.
    assert embed.description.endswith("Tier 1"), embed.description

    marca = cl.POR_ID["marca_do_cacador"]
    assert marca.tipo == cl.ATIVA, marca.tipo
    assert marca.escopo == "combate", marca.escopo
    assert f"⚡ **{marca.nome}**" in campos["Habilidades"], campos["Habilidades"]

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  os quatro campos da ficha, sem contagem nem legenda: ok")


async def caso_ver_e_do_dono_e_conferir_e_de_admin():
    """A ficha é do jogador; quem confere a de outro é quem administra.

    `/ficha ver` tinha um parâmetro `membro`, e com ele qualquer um abria a
    ficha de qualquer um — inclusive em PÚBLICO, porque esse caminho
    respondia no canal. Virou `/ficha conferir`, atrás de `manage_guild` e em
    privado: é ferramenta de conferência, não de publicação.
    """
    conn, canal, cog = await preparar(salas_sem_combate(), nivel=1)
    ficha = Ficha(FakeBot(conn, canal))
    dono, outro = JOGADORES[0], JOGADORES[1]

    # `ver` não tem mais por onde apontar para outra pessoa.
    assert {p.name for p in ficha.ver.parameters} == {"personagem"}, [
        p.name for p in ficha.ver.parameters
    ]
    i = FakeInteraction(canal, dono)
    await ficha.ver.callback(ficha, i)
    assert i._mensagem_resposta.id == -1, "/ficha ver tem de sair em privado"
    assert f"Heroi{dono}" in (i.resposta or ""), i.resposta

    # `conferir` é de admin, e mostra a ficha do outro — também em privado.
    assert ficha.conferir.default_permissions is not None
    assert ficha.conferir.default_permissions.manage_guild
    i = FakeInteraction(canal, dono)
    await ficha.conferir.callback(ficha, i, FakeUsuario(outro))
    assert i._mensagem_resposta.id == -1, "/ficha conferir tem de sair em privado"
    assert f"Heroi{outro}" in (i.resposta or ""), i.resposta

    # Nome errado diz quais ele tem, em vez de devolver a ficha errada.
    i = FakeInteraction(canal, dono)
    await ficha.conferir.callback(ficha, i, FakeUsuario(outro), "Ninguem")
    assert "nao tem **Ninguem**" in leu(i), leu(i)
    assert f"Heroi{outro}" in leu(i), leu(i)

    # `listar` tem o mesmo par: o do dono não aponta para ninguém, e o de
    # terceiro é `personagens`, de admin.
    assert {p.name for p in ficha.listar.parameters} == set(), [
        p.name for p in ficha.listar.parameters
    ]
    assert ficha.personagens.default_permissions.manage_guild
    i = FakeInteraction(canal, dono)
    await ficha.personagens.callback(ficha, i, FakeUsuario(outro))
    assert i._mensagem_resposta.id == -1, "/ficha personagens sai em privado"
    # O titulo diz de QUEM e a lista; os personagens vem nos campos.
    listados = i._mensagem_resposta.embeds[0]
    assert str(outro) in (listados.title or ""), listados.title
    assert f"Heroi{outro}" in {f.name for f in listados.fields}, listados.fields

    # `imagem` pede o personagem PRIMEIRO, e pede sempre — a padronização
    # vale mais que poupar o clique de quem tem um personagem só.
    nomes = [p.name for p in ficha.imagem.parameters]
    assert nomes == ["personagem", "link"], nomes
    assert ficha.imagem.parameters[0].required, "o personagem virou obrigatorio"
    assert not ficha.imagem.parameters[1].required, "o link segue opcional"

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  /ficha ver é do dono; /ficha conferir é de admin: ok")


async def main():
    caso_efeito_somado_faz_a_conta()
    caso_painel_diz_quem_ficou_com_quanto()
    caso_painel_de_um_so_nao_fala_do_grupo()
    caso_painel_avisa_o_teto()
    caso_cartao_nomeia_quem_rolou_e_quem_falta()
    caso_o_caminho_diz_passou_ou_falhou()
    caso_sala_vencida_nao_anuncia_castigo()

    await caso_o_cartao_vai_marcando_quem_rolou()
    await caso_quem_esta_caido_nao_entra_na_conta()
    await caso_a_sala_deixa_o_painel_da_condicao()
    await caso_evento_vencido_nao_deixa_debuff_em_ninguem()
    await caso_evento_perdido_cobra_de_quem_passou_tambem()
    await caso_stack_e_por_personagem_e_nao_do_ultimo_do_laco()
    await caso_ficha_mostra_a_iniciativa()
    await caso_os_campos_da_ficha_sao_os_quatro_nomes_limpos()
    await caso_ver_e_do_dono_e_conferir_e_de_admin()
    print("TESTES DE TELAS PASSARAM")


if __name__ == "__main__":
    asyncio.run(main())
