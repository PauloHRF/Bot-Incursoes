"""Ameaça: a curva de retorno decrescente, o sorteio pesado por ela e a
habilidade que chama atenção enquanto está ligada."""
from __future__ import annotations

import asyncio
import collections
import random
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import (  # noqa: E402
    ameaca,
    classes as cl,
    config,
    database as db,
    embeds as E,
    motor,
)
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


def combatente(nome, ameaca_base, extra=0, hp=100, user_id=1):
    return motor.Combatente(
        user_id, nome, 15, 5, "1d8", hp, hp, ameaca=ameaca_base, ameaca_extra=extra
    )


# ------------------------------------------------------------------- a curva


def caso_curva_amortece():
    """Cada ponto de ameaça vale menos que o anterior — é o ponto da curva."""
    assert ameaca.peso(0) == 0
    anterior = 0.0
    ganhos = []
    for x in range(0, 31, 3):
        atual = ameaca.peso(x)
        assert atual >= anterior, "a curva nunca desce"
        ganhos.append(atual - anterior)
        anterior = atual
    subidas = ganhos[1:]
    assert subidas == sorted(subidas, reverse=True), "cada degrau rende menos"
    # E ela NAO tem teto, de proposito. A curva de armadura, x/(x+Y), tinha
    # teto em 1 — e por isso saturava: com a ameaca acumulando, todo mundo
    # encostava la e o sorteio voltava a ser quase uniforme. Ver o cabecalho
    # de src/ameaca.py.
    assert ameaca.peso(10**9) > ameaca.peso(10**6), "a curva nao tem teto"
    print("  a curva sobe sempre, sem teto, e cada ponto novo rende menos: ok")


def caso_fracoes_somam_um():
    for ameacas in ([6, 5, 3, 2, 2], [1], [0, 0, 7], [99, 1]):
        soma = sum(ameaca.fracoes(ameacas))
        assert abs(soma - 1) < 1e-9, (ameacas, soma)
    assert ameaca.fracoes([]) == []
    print("  as frações somam 1, qualquer que seja o grupo: ok")


def caso_sem_ameaca_e_uniforme():
    """Ninguém com ameaça: a criatura não tem motivo para preferir alguém."""
    assert ameaca.fracoes([0, 0, 0]) == [1 / 3] * 3
    print("  grupo todo em zero cai no sorteio uniforme: ok")


def caso_ameaca_negativa_nao_quebra():
    assert ameaca.peso(-5) == 0
    assert abs(sum(ameaca.fracoes([-5, 3])) - 1) < 1e-9
    assert combatente("X", 2, extra=-10).ameaca_total == 0, "o total não fica negativo"
    print("  ameaça negativa é tratada como zero: ok")


def caso_stack_rende_menos_que_o_simples():
    """O amortecimento tem de aparecer na comparação com somar e dividir."""
    xs = [14, 3, 2]
    curva = ameaca.porcentagens(xs)[0]
    simples = xs[0] / sum(xs) * 100
    assert curva < simples, (curva, simples)
    # e o primeiro +3 vale mais que o terceiro. Degraus do MESMO tamanho:
    # a versao antiga comparava 5->8 (um +3) com 8->14 (dois +3), e dois
    # degraus pequenos podem somar mais que um — ela passava por sorte.
    degraus = [ameaca.porcentagens([x, 3, 2])[0] for x in (5, 8, 11, 14)]
    primeiro = degraus[1] - degraus[0]
    terceiro = degraus[3] - degraus[2]
    assert primeiro > terceiro, (primeiro, terceiro)
    print("  stackar ameaça rende menos que o stack simples, e vai rendendo menos: ok")


def caso_ordem_preservada():
    """Mais ameaça é sempre mais atenção: a curva não inverte ninguém."""
    fatias = ameaca.porcentagens([6, 5, 3, 2, 2])
    assert fatias == sorted(fatias, reverse=True)
    assert fatias[3] == fatias[4], "ameaça igual, atenção igual"
    print("  quem tem mais ameaça leva mais atenção, sempre: ok")


# ------------------------------------------------------------------ a classe


def caso_ameaca_por_classe():
    assert ameaca.inicial("guerreiro") > ameaca.inicial("ladino")
    assert ameaca.inicial("paladino") > ameaca.inicial("xama")
    assert ameaca.inicial("GUERREIRO") == ameaca.inicial("guerreiro"), "sem caixa"
    assert ameaca.inicial(None) == ameaca.PADRAO
    assert ameaca.inicial("classe inventada") == ameaca.PADRAO
    print("  a linha de frente atrai mais que o apoio, e classe nova fica no meio: ok")


def caso_toda_classe_prevista_tem_ameaca():
    """Classe sem ameaça cairia no padrão em silêncio — melhor garantir aqui."""
    faltam = [
        c for c in cl.CLASSES_PREVISTAS
        if cl.classe(c) is None or cl.classe(c).id not in ameaca.AMEACA_INICIAL
    ]
    nao_mapeadas = [
        c for c in cl.CLASSES_PREVISTAS
        if cl.classe(c) is not None and cl.classe(c).id not in ameaca.AMEACA_INICIAL
    ]
    assert not nao_mapeadas, f"sem ameaça definida: {nao_mapeadas}"
    print(f"  as {len(cl.CLASSES_PREVISTAS)} classes previstas têm ameaça definida: ok")


def caso_os_seis_grupos_sao_seis_degraus():
    """Os grupos existem para a criatura DISTINGUIR as classes.

    Antes eram tres degraus para catorze classes, e sete delas empatadas no
    piso: ladino, mago, bardo, bruxo, druida, feiticeiro e xama eram a mesma
    pessoa para a criatura. Agora sao seis valores distintos, um por grupo, e
    cada degrau vale uns dois pontos e meio de atencao.
    """
    valores = [valor for valor, _nomes in ameaca.GRUPOS]
    assert len(set(valores)) == 6, valores
    assert valores == sorted(valores, reverse=True), "do mais exposto ao menos"
    # Nenhuma classe em dois grupos, e nenhum grupo vazio.
    todas = [c for _v, nomes in ameaca.GRUPOS for c in nomes]
    assert len(todas) == len(set(todas)), todas
    assert all(nomes for _v, nomes in ameaca.GRUPOS)
    # O padrao de classe desconhecida cai DENTRO da escala, e nao fora dela.
    assert min(valores) <= ameaca.PADRAO <= max(valores), ameaca.PADRAO
    # E os degraus sao sentidos: cada grupo puxa mais que o de baixo.
    piso = [min(valores)] * 4
    fatias = [ameaca.porcentagens([v] + piso)[0] for v in valores]
    for alto, baixo in zip(fatias, fatias[1:]):
        assert alto - baixo >= 2.0, (alto, baixo, fatias)
    print("  seis grupos, seis degraus de uns 2,5 pontos cada: "
          + " ".join(f"{f:.0f}%" for f in fatias) + ": ok")


def caso_a_escala_vale_como_razao():
    """Dobrar todos os valores nao muda nada — e e por isso que o `+3` importa.

    `peso = x ** 0.5` normalizado cancela qualquer fator comum, entao
    `12/10/8/6/4/2` e `6/5/4/3/2/1` sao a MESMA distribuicao. O tamanho
    absoluto da escala existe para dar resolucao ao que e somado por cima (o
    bonus de ferido, o Reckless, os pontos de acao) — dobrar a escala sem
    dobrar esses numeros os enfraquece em silencio.
    """
    valores = [valor for valor, _nomes in ameaca.GRUPOS]
    cheia = ameaca.porcentagens(valores)
    metade = ameaca.porcentagens([v / 2 for v in valores])
    for a, b in zip(cheia, metade):
        assert abs(a - b) < 1e-9, (a, b)
    # Ja o bonus somado muda de peso com a escala: na metade ele vale MAIS.
    piso = min(valores)
    na_escala = (ameaca.porcentagens([piso + ameaca.AMEACA_DE_FERIDO] + [piso] * 4)[0]
                 - ameaca.porcentagens([piso] * 5)[0])
    na_metade = (ameaca.porcentagens([piso / 2 + ameaca.AMEACA_DE_FERIDO] + [piso / 2] * 4)[0]
                 - ameaca.porcentagens([piso / 2] * 5)[0])
    assert na_metade > na_escala, (na_escala, na_metade)
    print("  a escala vale como razao; o que soma por cima e que sente o tamanho: ok")


def caso_ferido_chama_mais_atencao():
    """Quem esta por cair puxa a criatura — e puxa MAIS se era o apoio.

    O bonus e plano de proposito: somar 3 numa ameaca 2 quase dobra o peso
    dela, e somar 3 numa ameaca 12 quase nao aparece. E assim que a criatura
    abandona o tanque inteiro para ir no mago sangrando, que e o que se quer
    de um "terminar o servico".
    """
    assert ameaca.de_ferido(100, 100) == 0, "inteiro nao ganha nada"
    assert ameaca.de_ferido(31, 100) == 0, "acima do limiar, nada"
    assert ameaca.de_ferido(30, 100) == ameaca.AMEACA_DE_FERIDO, "no limiar, entra"
    assert ameaca.de_ferido(1, 100) == ameaca.AMEACA_DE_FERIDO
    assert ameaca.de_ferido(0, 100) == 0, "no chao sai do sorteio por outro caminho"
    assert ameaca.de_ferido(10, 0) == 0, "sem HP maximo nao da divisao"

    # No combatente: o campo nao existe, o bonus sai do HP.
    tanque = combatente("Tanque", ameaca.inicial("guerreiro"), hp=100)
    apoio = combatente("Apoio", ameaca.inicial("ladino"), hp=100, user_id=2)
    inteiros = ameaca.porcentagens(ameaca.de_quem([tanque, apoio]))
    apoio.hp_atual = 20
    ferido = ameaca.porcentagens(ameaca.de_quem([tanque, apoio]))
    assert ferido[1] > inteiros[1] + 4, (inteiros, ferido)

    # E o empurrao e MAIOR no apoio que no tanque: o bonus e plano.
    apoio.hp_atual = 100
    tanque.hp_atual = 20
    tanque_ferido = ameaca.porcentagens(ameaca.de_quem([tanque, apoio]))
    ganho_do_apoio = ferido[1] - inteiros[1]
    ganho_do_tanque = tanque_ferido[0] - inteiros[0]
    assert ganho_do_apoio > ganho_do_tanque, (ganho_do_apoio, ganho_do_tanque)
    print(f"  ferido chama mais atencao, e o apoio mais que o tanque "
          f"(+{ganho_do_apoio:.0f} contra +{ganho_do_tanque:.0f} pontos): ok")


def caso_multiataque_descarrega_no_mesmo_alvo():
    """Tres garras no mesmo peito, e nao uma em cada.

    Sorteando por golpe, o multiataque virava uma maquina de espalhar dano: o
    tanque com 38% da atencao levava, em tres garras, um golpe e meio — e a
    Ameaca prometia que a criatura ia NELE. Agora a criatura escolhe uma vez
    por vez dela.
    """
    rng = random.Random(3)
    tanque = combatente("Tanque", 12, hp=500, user_id=1)
    apoio = combatente("Apoio", 2, hp=500, user_id=2)
    bicho = motor.Inimigo(0, "Bicho", 12, 40, "1d4", 50, 50, ataques=3)
    estado = motor.EstadoCombate([bicho], 1, [tanque, apoio])

    espalhou = 0
    for _ in range(300):
        # Vida cheia a cada rodada: o que se mede e a ESCOLHA do alvo, e sem
        # isto os dois morrem nas primeiras rodadas e o resto nao mede nada.
        tanque.hp_atual = tanque.hp_max
        apoio.hp_atual = apoio.hp_max
        vez = motor.turno_do_inimigo(bicho, estado, rng)
        assert len(vez.golpes) == 3, vez.golpes
        if len({alvo.nome for _golpe, alvo in vez.golpes}) > 1:
            espalhou += 1
    assert espalhou == 0, f"{espalhou} vezes a criatura dividiu a vez"

    # Mas se o alvo CAI no meio da sequencia, o resto vai para outro: nao se
    # bate em quem esta no chao.
    frangote = combatente("Frangote", 12, hp=1, user_id=3)
    sobrevivente = combatente("Sobrevivente", 2, hp=500, user_id=4)
    estado = motor.EstadoCombate([bicho], 1, [frangote, sobrevivente])
    vez = motor.turno_do_inimigo(bicho, estado, random.Random(1))
    assert frangote.caido, "o primeiro golpe derrubou"
    alvos = [alvo.nome for _golpe, alvo in vez.golpes]
    assert alvos.count("Frangote") == 1, alvos
    assert "Sobrevivente" in alvos, alvos
    print("  o multiataque descarrega no mesmo alvo, e troca so se ele cai: ok")


# ----------------------------------------------------------------- o sorteio


def caso_sorteio_bate_com_a_formula():
    """O sorteio real tem de reproduzir a distribuição que a fórmula promete."""
    rng = random.Random(7)
    nomes = ["A", "B", "C", "D", "E"]
    xs = [6, 5, 3, 2, 2]
    n = 60000
    contagem = collections.Counter(ameaca.sortear(nomes, xs, rng) for _ in range(n))
    esperado = dict(zip(nomes, ameaca.porcentagens(xs)))
    for nome in nomes:
        obtido = contagem[nome] / n * 100
        assert abs(obtido - esperado[nome]) < 1.0, (nome, obtido, esperado[nome])
    print("  em 60 mil sorteios a distribuição bate com a fórmula: ok")


def caso_sorteio_sem_reposicao():
    rng = random.Random(3)
    nomes = ["A", "B", "C", "D", "E"]
    xs = [6, 5, 3, 2, 2]
    for _ in range(200):
        tres = ameaca.sortear_varios(nomes, xs, 3, rng)
        assert len(tres) == 3 and len(set(tres)) == 3, tres
    # pedindo mais que o grupo, todos entram uma vez
    todos = ameaca.sortear_varios(nomes, xs, 9, rng)
    assert sorted(todos) == sorted(nomes)
    assert ameaca.sortear_varios(nomes, xs, 0, rng) == []
    assert ameaca.sortear([], [], rng) is None
    print("  vários alvos saem sem repetir, e pedir demais devolve o grupo: ok")


def caso_motor_pesa_pela_ameaca():
    """O alvo do inimigo sai pelo peso, não uniforme."""
    rng = random.Random(11)
    tanque = combatente("Tanque", 6, user_id=1)
    apoio = combatente("Apoio", 2, user_id=2)
    inimigo = motor.Inimigo(0, "Bicho", 12, 4, "1d4", 50, 50)
    estado = motor.EstadoCombate([inimigo], 1, [tanque, apoio])
    n = 20000
    contagem = collections.Counter(
        motor.sortear_alvo(estado, rng).nome for _ in range(n)
    )
    esperado = ameaca.porcentagens([6, 2])[0]
    obtido = contagem["Tanque"] / n * 100
    assert abs(obtido - esperado) < 1.5, (obtido, esperado)
    assert contagem["Apoio"] > 0, "o apoio nunca fica imune"
    print(f"  o inimigo mira o tanque em {obtido:.0f}% dos golpes (uniforme seria 50%): ok")


def caso_painel_mostra_a_fatia_com_o_fator():
    """O painel promete o numero que DECIDE, e o fator decide junto.

    Sem o fator a linha mentia exatamente para quem gastou uma acao se
    protegendo: o mago com Fly lia 25% e era sorteado com 6%. A fatia da tela
    tem de ser a mesma que `sortear_alvo` usa.
    """
    tanque = combatente("Tanque", 6, user_id=1)
    mago = combatente("Mago", 2, user_id=2)
    clerigo = combatente("Clerigo", 3, user_id=3)
    mesa = [tanque, mago, clerigo]
    mago.ameaca_fator = 0.2  # voando

    linha = E.linha_de_ameaca(mesa)
    reais = ameaca.porcentagens(ameaca.de_quem(mesa), ameaca.fatores_de(mesa))
    for quem, fatia in zip(mesa, reais):
        assert f"{quem.nome} {fatia:.0f}%" in linha, (quem.nome, fatia, linha)
    # E a fatia dele ficou de fato pequena: sem o fator daria uns 25%.
    assert reais[1] < 10, reais
    sem_fator = ameaca.porcentagens(ameaca.de_quem(mesa))
    assert sem_fator[1] > 20, sem_fator
    print("  a fatia do painel e a mesma que o sorteio usa, fator incluido: ok")


def caso_caido_sai_do_bolo():
    rng = random.Random(5)
    tanque = combatente("Tanque", 6, user_id=1)
    tanque.hp_atual = 0
    apoio = combatente("Apoio", 2, user_id=2)
    inimigo = motor.Inimigo(0, "Bicho", 12, 4, "1d4", 50, 50)
    estado = motor.EstadoCombate([inimigo], 1, [tanque, apoio])
    for _ in range(50):
        assert motor.sortear_alvo(estado, rng) is apoio, "quem caiu não é alvo"
    print("  quem está no chão sai do sorteio, com ameaça alta ou não: ok")


def caso_atordoado_ainda_tem_prioridade_sobre_ameaca():
    """A regra do atordoamento vem antes: atordoar duas vezes não faz nada."""
    rng = random.Random(9)
    tanque = combatente("Tanque", 6, user_id=1)
    tanque.atordoado = True
    apoio = combatente("Apoio", 2, user_id=2)
    inimigo = motor.Inimigo(0, "Bicho", 12, 4, "1d4", 50, 50)
    estado = motor.EstadoCombate([inimigo], 1, [tanque, apoio])
    for _ in range(50):
        assert motor.sortear_alvos(estado, 1, rng) == [apoio]
    print("  o atordoado continua fora da mira, mesmo com mais ameaça: ok")


# ------------------------------------------------------- a habilidade ligada


def caso_habilidade_soma_na_ameaca():
    quem = combatente("Barbaro", 5)
    assert quem.ameaca_total == 5
    quem.ameaca_extra += 3  # o que _aplicar_ligado faz
    assert quem.ameaca_total == 8
    antes = ameaca.porcentagens([5, 3, 2])[0]
    depois = ameaca.porcentagens([8, 3, 2])[0]
    assert depois > antes + 3, "o +3 move a atenção de forma sentida"
    print(f"  ameaça 3 leva o bárbaro de {antes:.0f}% para {depois:.0f}% da atenção: ok")


def caso_reckless_attack_da_ameaca():
    """O exemplo do grupo: atacar descuidado chama atenção.

    O caso afirma o EFEITO, e não o número: o que o Reckless promete é mover
    a mira de forma sentida, e quanto de ameaça isso custa depende da escala
    dos grupos. Preso ao literal, o caso quebrava em toda recalibragem e
    deixava passar o contrário — o mesmo `+3` valendo metade depois de a
    escala dobrar.
    """
    barbaro = cl.classe("barbaro")
    reckless = next(
        h for _, h in barbaro.habilidades_ate(20) if h.id == "reckless_attack"
    )
    extra = reckless.acao["efeitos"]["ameaca"]
    base = ameaca.inicial("barbaro")
    piso = [ameaca.inicial("ladino")] * 4
    antes = ameaca.porcentagens([base] + piso)[0]
    depois = ameaca.porcentagens([base + extra] + piso)[0]
    assert depois - antes >= 4.5, (antes, depois, extra)
    assert reckless.acao["efeitos"]["vantagem"] is True, "e continua dando vantagem"
    assert reckless.acao["turnos"] == 1, "a ameaça extra dura o turno e sai"
    print(f"  Reckless Attack leva o bárbaro de {antes:.0f}% a {depois:.0f}% "
          f"da atenção (+{extra} de ameaça): ok")


async def caso_combatente_nasce_com_a_ameaca_da_classe():
    config.DB_PATH = Path(__file__).resolve().parent / "teste_ameaca.db"
    config.DB_PATH.unlink(missing_ok=True)
    config.TAMANHO_GRUPO = 5
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    await criar_grupo(conn, nivel=8)
    cog = Incursoes(FakeBot(conn, FakeCanal(CANAL)))
    run_id = await db.criar_run(conn, GUILD, CANAL, "qualquer", JOGADORES[0])
    for uid in JOGADORES[:3]:
        p = await db.personagem_por_nome(conn, GUILD, uid, f"Heroi{uid}")
        await db.adicionar_participante(conn, run_id, uid, p["id"])
    await db.inicializar_hp(conn, run_id)
    run = await db.buscar_run(conn, run_id)

    combatentes = await cog._combatentes(run)
    assert combatentes, "o grupo entrou"
    personagens = {p["user_id"]: p for p in await db.personagens_da_run(conn, run_id)}
    for c in combatentes:
        esperada = ameaca.inicial(personagens[c.user_id]["classe"])
        assert c.ameaca == esperada, (c.nome, c.ameaca, esperada)
        assert c.ameaca_extra == 0, "nada ligado ainda"
    print("  o combatente nasce com a ameaça da classe dele: ok")


def caso_cada_acao_gera_ameaca():
    """A regra: cada acao gera a ameaca da propria classe, dobrada em area e cura."""
    for classe in cl.CLASSES:
        assert ameaca.gerada_por(classe) == ameaca.inicial(classe), classe

    um_alvo = {"tipo": "save", "save": "DES", "alvos": 1, "dano": "4d8"}
    todos = {"tipo": "save", "save": "DES", "alvos": "todos", "dano": "8d6"}
    assert ameaca.gerada_por("clerigo", um_alvo) == ameaca.inicial("clerigo")
    assert ameaca.gerada_por("clerigo", todos) == 2 * ameaca.inicial("clerigo")
    assert ameaca.gerada_por("clerigo", {"tipo": "cura"}) == 2 * ameaca.inicial("clerigo")
    assert ameaca.gerada_por("bardo", {"tipo": "grupo"}) == 2 * ameaca.inicial("bardo")

    # Ser proporcional a classe e o que mantem o tanque: o guerreiro gera por
    # golpe o triplo do que o mago gera, igual a razao das iniciais.
    assert ameaca.gerada_por("guerreiro") == 3 * ameaca.gerada_por("mago")

    # E por isso as razoes quase nao mudam quando todos batem rodada apos
    # rodada. Somar um valor fixo igual para todos diluiria a inicial.
    grupo = ["guerreiro", "ladino", "mago"]
    crua = [ameaca.inicial(c) for c in grupo]
    abertura = ameaca.porcentagens(crua)[0]
    for _ in range(5):
        crua = [x + ameaca.gerada_por(c) for x, c in zip(crua, grupo)]
    assert abs(ameaca.porcentagens(crua)[0] - abertura) < 0.5, (crua, abertura)

    # Uma habilidade pode declarar e pular a regra inteira, classe e tudo —
    # o gancho da provocacao.
    assert ameaca.gerada_por("mago", {"tipo": "cura", "ameaca_gerada": 9}) == 9
    assert ameaca.gerada_por("guerreiro", {"ameaca_gerada": 0}) == 0

    # Classe desconhecida cai no PADRAO, e nao em zero.
    assert ameaca.gerada_por(None) == ameaca.PADRAO
    print("  cada acao gera a ameaca da classe, dobrada em area e cura: ok")


async def caso_ameaca_acumula_no_combate():
    """Agindo, o personagem vai chamando atencao — e a conta morre com a sala."""
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass
    config.DB_PATH = Path(__file__).resolve().parent / "teste_ameaca.db"
    config.DB_PATH.unlink(missing_ok=True)
    config.TAMANHO_GRUPO = 5
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    await criar_grupo(conn, nivel=8, classe="guerreiro")
    canal = FakeCanal(CANAL)
    cog = Incursoes(FakeBot(conn, canal))
    # Um saco de pancada com HP alto: o combate precisa durar as rodadas.
    incursao, _ = montar_conteudo(
        cog, tamanho="Curta", monstro_objetivo={**INDEFESO, "hp": 4000},
        inimigos_objetivo=1, salas=salas_sem_combate(),
    )
    run_id = await db.criar_run(conn, GUILD, CANAL, incursao.id, JOGADORES[0])
    for user_id in JOGADORES[:2]:
        personagem = await db.personagem_por_nome(conn, GUILD, user_id, f"Heroi{user_id}")
        await db.adicionar_participante(conn, run_id, user_id, personagem["id"])
    await db.inicializar_hp(conn, run_id)
    await db.atualizar_run(
        conn, run_id, status="objetivo", sala_atual="OBJ",
        linha_atual=incursao.passos + 1,
    )
    run = await db.buscar_run(conn, run_id)
    await cog._abrir_combate(run, incursao.objetivo)
    run = await db.buscar_run(conn, run_id)
    passo = cog._passo(run)
    dono = JOGADORES[0]

    inicial = (await cog._estado_combate(run, incursao.objetivo)).combatente(dono)
    assert inicial.ameaca_gerada == 0, "nada gerado antes de agir"

    # Duas rodadas de ataque: todos batem, para a iniciativa dar a volta.
    msg = await canal.fetch_message(run["mensagem_id"])
    for _ in range(2):
        for user_id in JOGADORES[:2]:
            await cog.atacar(FakeInteraction(canal, user_id, msg), run["id"], "OBJ")

    run = await db.buscar_run(conn, run_id)
    depois = (await cog._estado_combate(run, incursao.objetivo)).combatente(dono)
    por_golpe = ameaca.gerada_por("guerreiro")
    assert depois.ameaca_gerada == 2 * por_golpe, (depois.ameaca_gerada, por_golpe)
    assert depois.ameaca_total > inicial.ameaca_total, "ele chamou mais atencao"
    # E a acumulacao NAO vaza para o `ameaca_extra`, que e o que acende a
    # marca do painel. Se vazasse, a marca apareceria em todo mundo que agiu.
    assert depois.ameaca_extra == 0, "a marca e para habilidade ligada, nao para ter agido"

    # E a conta morre com a sala: a chave em `run_efeitos` tem o `passo`.
    assert await db.efeitos_ativos(conn, run_id, passo + 1, 1) == []
    print(f"  a ameaca acumula agindo ({inicial.ameaca_total} -> "
          f"{depois.ameaca_total}) e morre com a sala: ok")


async def main():
    try:
        caso_curva_amortece()
        caso_fracoes_somam_um()
        caso_sem_ameaca_e_uniforme()
        caso_ameaca_negativa_nao_quebra()
        caso_stack_rende_menos_que_o_simples()
        caso_ordem_preservada()
        caso_ameaca_por_classe()
        caso_toda_classe_prevista_tem_ameaca()
        caso_os_seis_grupos_sao_seis_degraus()
        caso_a_escala_vale_como_razao()
        caso_ferido_chama_mais_atencao()
        caso_multiataque_descarrega_no_mesmo_alvo()
        caso_sorteio_bate_com_a_formula()
        caso_sorteio_sem_reposicao()
        caso_motor_pesa_pela_ameaca()
        caso_painel_mostra_a_fatia_com_o_fator()
        caso_caido_sai_do_bolo()
        caso_atordoado_ainda_tem_prioridade_sobre_ameaca()
        caso_habilidade_soma_na_ameaca()
        caso_reckless_attack_da_ameaca()
        caso_cada_acao_gera_ameaca()
        await caso_combatente_nasce_com_a_ameaca_da_classe()
        await caso_ameaca_acumula_no_combate()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        (Path(__file__).resolve().parent / "teste_ameaca.db").unlink(missing_ok=True)


asyncio.run(main())
print("TESTES DA AMEAÇA PASSARAM")
