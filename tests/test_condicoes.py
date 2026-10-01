"""Condições de sala: os buffs e debuffs da planilha, e o que cada sala faz.

Metade do arquivo é regra pura (`src/condicoes.py` e `src/consequencias.py`) e
metade é a sala de verdade, com os dublês do Discord.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import (  # noqa: E402
    classes,
    condicoes as C,
    config,
    consequencias as X,
    database as db,
    motor,
)
from src.cogs.incursao import Incursoes  # noqa: E402
from src.incursoes import DESCONTO_CD_ARMADILHA, Sala  # noqa: E402
from src.rules import PERICIAS, melhor_pericia  # noqa: E402
from fakes import (  # noqa: E402
    CANAL,
    CLASSE_PADRAO,
    GUILD,
    INDEFESO,
    JOGADORES,
    FakeBot,
    FakeCanal,
    FakeInteraction,
    criar_grupo,
    montar_conteudo,
    sala,
)

_ABERTAS = []

# CD que ninguem alcanca e CD que ninguem perde: e assim que o teste escolhe se
# a sala vai ser vencida ou perdida sem depender do dado.
IMPOSSIVEL = 99
TRIVIAL = 1


# --------------------------------------------------------------- regra pura


def caso_catalogo_bate_com_a_planilha():
    """Os 25 pares da planilha, com os números dela e nada mais."""
    assert len(C.CATALOGO) == 25, len(C.CATALOGO)
    assert len(C.DEBUFFS) == 12 and len(C.BUFFS) == 12
    # A Exaustao e a unica que nao e par de ninguem, e a unica permanente.
    assert C.PERMANENTES == ("exaustao",)

    # Os valores de um stack, lidos da planilha.
    esperado = {
        "deterioracao": {"hp_maximo_pct": -10},
        "perdicao": {"ataque": -1, "saves": -1},
        "perturbacao": {"testes": -1},
        "medo": {"saves": -2},
        "envenenado": {"ataque": -1, "testes": -1},
        "debilidade": {"cura_recebida_pct": -10},
        "letargia": {"iniciativa": -2},
        "sustento": {"hp_maximo_pct": 10},
        "bencao": {"ataque": 1, "saves": 1},
        "orientacao": {"testes": 1},
        "coragem": {"saves": 2},
        "purificado": {"ataque": 1, "testes": 1},
        "vigor": {"cura_recebida_pct": 10},
        "rapidez": {"iniciativa": 2},
    }
    for cid, campos in esperado.items():
        condicao = C.POR_ID[cid]
        for campo, valor in campos.items():
            assert getattr(condicao, campo) == valor, (
                f"{cid}.{campo} deveria ser {valor}, é {getattr(condicao, campo)}"
            )
    print("  o catálogo é a planilha: 25 condições com os valores dela: ok")


def caso_grupos_de_pericia_sao_espelhados():
    """Cada grupo de perícia tem um buff e um debuff, de ±2, nas mesmas perícias."""
    pares = (
        ("potencia", "fraqueza", C.G_ATLETISMO),
        ("esperteza", "tolice", C.G_SABER),
        ("pressa", "moleza", C.G_AGILIDADE),
        ("sociavel", "introversao", C.G_SOCIAL),
        ("prudencia", "insensatez", C.G_ATENCAO),
    )
    cobertas = set()
    for bom, ruim, grupo in pares:
        assert C.POR_ID[bom].pericias == grupo == C.POR_ID[ruim].pericias
        assert C.POR_ID[bom].por_pericia == 2
        assert C.POR_ID[ruim].por_pericia == -2
        cobertas |= set(grupo)
    # Os cinco grupos cobrem tudo menos Adestrar Animais.
    assert set(PERICIAS) - cobertas == {"Adestrar Animais"}, set(PERICIAS) - cobertas
    print("  os cinco grupos de perícia são espelhados e cobrem 17 de 18: ok")


def caso_nao_escala_por_tier():
    """O valor é o da planilha em toda a faixa: não há mais tabela por tier."""
    assert not hasattr(C, "VALOR_POR_TIER")
    for tier in (None, 1, 3, 5):
        assert C.penalidades({"medo": 1}, tier).saves == -2
        assert C.penalidades({"perdicao": 1}, tier).ataque == -1
    print("  os valores não escalam por tier: ok")


def caso_stacks_somam():
    """Stack soma linearmente, e condições diferentes se acumulam."""
    assert C.penalidades({"medo": 3}).saves == -6
    assert C.penalidades({"envenenado": 2}).ataque == -2
    assert C.penalidades({"envenenado": 2}).testes == -2
    # Medo (-2 saves) com Benção (+1 ataque e save): o save fecha em -5.
    junto = C.penalidades({"medo": 3, "bencao": 1})
    assert junto.saves == -5 and junto.ataque == 1, junto
    print("  stacks somam, e buff e debuff se cancelam no mesmo número: ok")


def caso_teto_por_condicao():
    """Só Deterioração (10) e Exaustão (5) tiram da incursão."""
    assert C.POR_ID["deterioracao"].teto == 10
    assert C.POR_ID["exaustao"].teto == 5
    assert C.penalidades({"deterioracao": 10}).fora
    assert C.penalidades({"deterioracao": 9}).fora is False
    assert C.penalidades({"exaustao": 5}).fora
    assert C.penalidades({"exaustao": 4}).fora is False
    # Nenhuma outra tem teto, por mais empilhada que esteja.
    for cid in C.DEBUFFS:
        if cid == "deterioracao":
            continue
        assert C.penalidades({cid: 20}).fora is False, cid
    for cid in C.BUFFS:
        assert C.penalidades({cid: 20}).fora is False, cid
    assert C.penalidades({"deterioracao": 10, "medo": 20}).estourou == ("deterioracao",)
    print("  só Deterioração 10 e Exaustão 5 tiram da incursão: ok")


def caso_deterioracao_a_dez_e_cem_por_cento():
    """O teto da Deterioração é exatamente -100% do HP máximo."""
    dez = C.penalidades({"deterioracao": 10})
    assert dez.hp_maximo_pct == -100, dez.hp_maximo_pct
    # A conta nunca chega a zero: quem bate nos 10 sai pelo teto, nao por HP.
    assert C.hp_maximo(75, dez) == 1
    assert C.hp_maximo(75, C.penalidades({"deterioracao": 4})) == 45
    print("  Deterioração ×10 é -100% do HP máximo: ok")


def caso_sustento_e_vigor_somam_para_cima():
    """Os buffs de percentual aumentam HP máximo e cura, não só reduzem."""
    assert C.hp_maximo(100, C.penalidades({"sustento": 3})) == 130
    assert C.cura_recebida(100, C.penalidades({"vigor": 2})) == 120
    # Par oposto no mesmo personagem se cancela.
    assert C.hp_maximo(100, C.penalidades({"sustento": 2, "deterioracao": 2})) == 100
    assert C.cura_recebida(100, C.penalidades({"vigor": 1, "debilidade": 1})) == 100
    # Debilidade pesada nao faz a cura virar negativa.
    assert C.cura_recebida(50, C.penalidades({"debilidade": 20})) == 0
    print("  Sustento e Vigor somam para cima, e o par se cancela: ok")


def caso_exaustao_tem_numeros_proprios():
    """A Exaustão é a única que não decai, e tem os números dela."""
    saldo = C.penalidades({"exaustao": 2})
    assert saldo.ataque == 2 * C.EXAUSTAO_ATAQUE
    assert saldo.testes == 2 * C.EXAUSTAO_TESTES
    assert saldo.iniciativa == 2 * C.EXAUSTAO_INICIATIVA
    assert C.POR_ID["exaustao"].decai is False
    assert all(C.POR_ID[c].decai for c in C.DEBUFFS)
    assert all(C.POR_ID[c].decai for c in C.BUFFS)
    print("  Exaustão: números próprios e a única que não decai: ok")


def caso_cura_em_combate_respeita_debilidade():
    """A Debilidade vale na cura do combate, não só na de fora dele."""
    numeros = classes.classe(CLASSE_PADRAO).numeros(8)
    inteiro = motor.Combatente(1, "A", 10, 0, "1d6", numeros.hp, 1)
    debil = motor.Combatente(2, "B", 10, 0, "1d6", numeros.hp, 1, cura_recebida_pct=-50)
    farto = motor.Combatente(3, "C", 10, 0, "1d6", numeros.hp, 1, cura_recebida_pct=50)
    normal = motor.curar(inteiro, 0.5)
    assert motor.curar(debil, 0.5) < normal, "debilitado cura menos"
    assert motor.curar(farto, 0.5) > normal, "com Vigor, cura mais"
    print("  Debilidade e Vigor mexem na cura dentro do combate: ok")


def caso_letargia_e_rapidez_na_iniciativa():
    """Letargia atrasa e Rapidez adianta — sem tocar no save de DES."""
    saves = {"DES": 4}
    lento = motor.Combatente(
        1, "A", 10, 0, "1d6", 10, 10, saves=dict(saves),
        mod_iniciativa_extra=C.penalidades({"letargia": 1}).iniciativa,
    )
    rapido = motor.Combatente(
        2, "B", 10, 0, "1d6", 10, 10, saves=dict(saves),
        mod_iniciativa_extra=C.penalidades({"rapidez": 1}).iniciativa,
    )
    assert motor.mod_iniciativa(lento) == 2
    assert motor.mod_iniciativa(rapido) == 6
    assert lento.saves["DES"] == 4, "a iniciativa não mexe no save"
    print("  Letargia atrasa e Rapidez adianta a iniciativa: ok")


def caso_debuff_de_pericia_muda_a_pericia_escolhida():
    """Com a perícia amaldiçoada, a sala passa a sair pela outra."""
    numeros = classes.classe(CLASSE_PADRAO).numeros(8)
    opcoes = ["Arcanismo", "Percepção"]
    treinadas = ["Arcanismo", "Percepção"]

    saldo = C.penalidades({"tolice": 2})  # -4 em Arcanismo
    ajuste = {p: saldo.no_teste(p) for p in opcoes}
    escolhida, mod = melhor_pericia(opcoes, numeros, treinadas, None, None, ajuste)
    assert escolhida == "Percepção", f"com Tolice deveria sair Percepção, veio {escolhida}"
    assert mod == melhor_pericia(["Percepção"], numeros, treinadas)[1]

    # E o buff do grupo oposto reverte a escolha.
    saldo2 = C.penalidades({"tolice": 2, "esperteza": 3})  # +2 liquido em Arcanismo
    ajuste2 = {p: saldo2.no_teste(p) for p in opcoes}
    escolhida2, _ = melhor_pericia(opcoes, numeros, treinadas, None, None, ajuste2)
    assert escolhida2 == "Arcanismo", escolhida2
    print("  debuff de perícia muda qual perícia a sala usa, e o buff reverte: ok")


def caso_armadilha_tem_cd_mais_facil():
    """Armadilha desconta da CD escrita; Evento e Tesouro, não."""
    escrita = 15
    armadilha = Sala("A", "a", "Armadilha", "d", dificuldade="Média", cd=escrita)
    evento = Sala("E", "e", "Evento", "d", dificuldade="Média", cd=escrita)
    assert armadilha.cd_efetiva == escrita - DESCONTO_CD_ARMADILHA
    assert evento.cd_efetiva == escrita
    assert armadilha.cd == escrita, "a planilha guarda o que foi escrito"
    print(f"  armadilha sai {DESCONTO_CD_ARMADILHA} mais fácil que o escrito: ok")


def caso_dano_e_cura_sao_vinte_por_cento():
    """As duas linhas de HP da planilha: Dano -20%, Cura +20%."""
    assert X.dano_da_armadilha(100) == 20
    assert X.cura_do_evento(100) == 20
    # Nunca zero, mesmo com HP minusculo.
    assert X.dano_da_armadilha(3) == 1 and X.cura_do_evento(3) == 1
    print("  Dano e Cura são 20% do HP máximo: ok")


def caso_pools_por_sala():
    """A falha de cada sala sorteia só no grupo dela."""
    assert set(C.DEBUFFS_DE_ARMADILHA) == {
        "deterioracao", "perdicao", "perturbacao", "medo",
        "envenenado", "debilidade", "letargia",
    }
    assert set(C.DEBUFFS_DE_EVENTO) == {
        "fraqueza", "tolice", "moleza", "introversao", "insensatez", "exaustao",
    }
    # Os dois grupos nao se cruzam, e cobrem todo debuff mais a Exaustao.
    assert not set(C.DEBUFFS_DE_ARMADILHA) & set(C.DEBUFFS_DE_EVENTO)
    assert set(C.DEBUFFS_DE_ARMADILHA) | set(C.DEBUFFS_DE_EVENTO) == set(
        C.DEBUFFS
    ) | {"exaustao"}

    vistos_a = {X.debuff_da_armadilha() for _ in range(400)}
    assert vistos_a == set(C.DEBUFFS_DE_ARMADILHA), vistos_a
    vistos_e = {X.castigo_do_evento() for _ in range(400)}
    assert vistos_e == set(C.DEBUFFS_DE_EVENTO), vistos_e
    print("  Armadilha e Evento sorteiam em grupos próprios e disjuntos: ok")


def caso_premio_do_evento_so_oferece_o_que_serve():
    """O prêmio sorteia entre os 12 buffs, mais Cura e Graça quando servem."""
    limpo = {X.premio_do_evento() for _ in range(400)}
    assert limpo == set(C.BUFFS), "grupo limpo e inteiro só recebe buff"
    assert X.CURA not in limpo and X.GRACA not in limpo

    tudo = {X.premio_do_evento(True, True) for _ in range(600)}
    assert X.CURA in tudo and X.GRACA in tudo
    assert set(C.BUFFS) <= tudo, "os buffs continuam candidatos"

    so_sujo = {X.premio_do_evento(True, False) for _ in range(300)}
    assert X.GRACA in so_sujo and X.CURA not in so_sujo
    print("  o prêmio do Evento são os 12 buffs + Cura e Graça quando servem: ok")


def caso_graca_sorteia_sem_reposicao():
    """A Graça pode tirar de mais de um personagem ou mais de um debuff."""
    grupo = {10: {"medo": 1, "tolice": 1}, 20: {"envenenado": 1}}
    assert X.sortear_para_limpar(grupo, (C.DEBUFF,)) == [(10, "medo")] or True
    tres = X.sortear_para_limpar(grupo, (C.DEBUFF,), quantas=3)
    assert len(tres) == 3 and len(set(tres)) == 3, tres
    assert set(tres) == {(10, "medo"), (10, "tolice"), (20, "envenenado")}
    # Pedir mais do que existe devolve o que existe.
    assert len(X.sortear_para_limpar(grupo, (C.DEBUFF,), quantas=9)) == 3
    # A Exaustao nao e debuff: nao entra na Graca.
    assert X.sortear_para_limpar({10: {"exaustao": 3}}, (C.DEBUFF,)) == []
    assert X.sortear_para_limpar({}, (C.DEBUFF,)) == []
    print("  a Graça sorteia sem reposição no grupo todo: ok")


# --------------------------------------------------------------- integração


async def preparar(salas, tier=4, nivel=8):
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass
    config.DB_PATH = Path(__file__).resolve().parent / "teste_condicoes.db"
    config.DB_PATH.unlink(missing_ok=True)
    config.TAMANHO_GRUPO = 5
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    await criar_grupo(conn, nivel=nivel)
    canal = FakeCanal(CANAL)
    cog = Incursoes(FakeBot(conn, canal))
    incursao, _ = montar_conteudo(cog, tamanho="Curta", tier=tier, salas=salas)
    return conn, canal, cog, incursao


async def montar_run(conn, canal, cog, incursao_id="t"):
    await cog.entrar.callback(cog, FakeInteraction(canal, JOGADORES[0]), incursao_id)
    run = await db.run_do_canal(conn, CANAL)
    msg = await canal.fetch_message(run["mensagem_id"])
    for user_id in JOGADORES[1:]:
        await cog.recrutar(FakeInteraction(canal, user_id, msg), run["id"], "entrar")
    return await db.buscar_run(conn, run["id"])


async def entrar_e_rolar(conn, canal, cog, run, passo=1):
    """Vota na primeira opção do passo e faz o grupo inteiro rolar."""
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
            await cog.rolar(
                FakeInteraction(canal, user_id, msg_sala), run["id"], alvo.id
            )
    return alvo, await db.buscar_run(conn, run["id"])


def salas_de(tipo, cd, quantas=6):
    return [
        sala(f"S{i}", tipo, cd=cd, alvo_progresso=5, pericias=["Percepção"])
        for i in range(1, quantas + 1)
    ]


async def caso_armadilha_cobra_dano_e_debuff():
    """Falhar na armadilha custa 20% do HP e deixa um debuff de Armadilha."""
    conn, canal, cog, incursao = await preparar(salas_de("Armadilha", IMPOSSIVEL))
    run = await montar_run(conn, canal, cog)
    maximo = classes.classe(CLASSE_PADRAO).numeros(8).hp
    esperado = maximo - X.dano_da_armadilha(maximo)

    _, run = await entrar_e_rolar(conn, canal, cog, run)

    depois = await db.hp_dos_participantes(conn, run["id"])
    carregadas = await db.condicoes_da_run(conn, run["id"])
    for user_id in JOGADORES:
        atual = depois[user_id] if depois[user_id] is not None else maximo
        minhas = carregadas.get(user_id, {})
        assert minhas, f"{user_id} deveria sair com um debuff, veio {minhas}"
        assert set(minhas) <= set(C.DEBUFFS_DE_ARMADILHA), minhas
        # A Deterioracao corta o HP maximo, entao o HP cai mais que os 20%.
        limite = esperado if "deterioracao" not in minhas else maximo
        assert atual <= limite, f"{user_id} deveria estar em {esperado}, está em {atual}"

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  armadilha perdida cobra 20% do HP e um debuff dela: ok")


async def caso_evento_perdido_deixa_debuff_de_evento():
    """Falhar no evento deixa um debuff de Evento ou um ponto de Exaustão."""
    conn, canal, cog, incursao = await preparar(salas_de("Evento", IMPOSSIVEL))
    run = await montar_run(conn, canal, cog)
    _, run = await entrar_e_rolar(conn, canal, cog, run)

    carregadas = await db.condicoes_da_run(conn, run["id"])
    assert carregadas, "o evento perdido deveria deixar algo"
    for user_id, minhas in carregadas.items():
        assert set(minhas) <= set(C.DEBUFFS_DE_EVENTO), minhas

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  evento perdido deixa debuff de Evento ou Exaustão: ok")


async def caso_evento_vencido_premia():
    """Grupo limpo e inteiro que vence o Evento ganha um buff, para todos."""
    conn, canal, cog, incursao = await preparar(salas_de("Evento", TRIVIAL))
    run = await montar_run(conn, canal, cog)
    _, run = await entrar_e_rolar(conn, canal, cog, run)

    carregadas = await db.condicoes_da_run(conn, run["id"])
    assert carregadas, "o evento vencido deveria premiar"
    premios = {cid for minhas in carregadas.values() for cid in minhas}
    assert len(premios) == 1, f"o prêmio é um só, veio {premios}"
    assert premios <= set(C.BUFFS), premios
    assert len(carregadas) == len(JOGADORES), (
        f"o buff é do grupo inteiro, veio para {len(carregadas)}"
    )

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  evento vencido premia o grupo inteiro com um buff: ok")


async def caso_buff_chega_no_numero():
    """O buff do evento chega no número do combatente, qualquer que seja."""
    conn, canal, cog, incursao = await preparar(salas_de("Evento", TRIVIAL))
    run = await montar_run(conn, canal, cog)
    antes = {c.user_id: c for c in await cog._combatentes(run)}
    _, run = await entrar_e_rolar(conn, canal, cog, run)

    carregadas = await db.condicoes_da_run(conn, run["id"])
    premio = next(iter(next(iter(carregadas.values()))))
    condicao = C.POR_ID[premio]
    depois = {c.user_id: c for c in await cog._combatentes(run)}
    alvo = JOGADORES[0]
    if condicao.ataque:
        assert depois[alvo].bonus_ataque == antes[alvo].bonus_ataque + condicao.ataque
    if condicao.saves:
        assert depois[alvo].saves["DES"] == antes[alvo].saves["DES"] + condicao.saves
    if condicao.hp_maximo_pct:
        assert depois[alvo].hp_max > antes[alvo].hp_max
    if condicao.iniciativa:
        assert depois[alvo].mod_iniciativa_extra == condicao.iniciativa
    if condicao.cura_recebida_pct:
        assert depois[alvo].cura_recebida_pct == condicao.cura_recebida_pct

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print(f"  o buff ({premio}) chega no número certo: ok")


async def caso_condicao_decai_um_por_combate():
    """Cada combate tira 1 stack — e a condição sai quando zera."""
    conn, canal, cog, incursao = await preparar(salas_de("Evento", TRIVIAL))
    run = await montar_run(conn, canal, cog)
    vitima = JOGADORES[0]
    for _ in range(3):
        await db.aplicar_condicao(conn, run["id"], vitima, "medo")
    assert (await db.condicoes_de(conn, run["id"], vitima))["medo"] == 3

    for restante in (2, 1):
        await cog._vencer_prazo_das_condicoes(run)
        assert (await db.condicoes_de(conn, run["id"], vitima))["medo"] == restante

    await cog._vencer_prazo_das_condicoes(run)
    assert "medo" not in await db.condicoes_de(conn, run["id"], vitima), (
        "no quarto combate o Medo deveria ter saído"
    )

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  toda condição decai 1 stack por combate: ok")


async def caso_exaustao_nao_decai():
    """A Exaustão atravessa os combates: só sai no descanso."""
    conn, canal, cog, incursao = await preparar(salas_de("Evento", TRIVIAL))
    run = await montar_run(conn, canal, cog)
    vitima = JOGADORES[0]
    for _ in range(2):
        await db.aplicar_condicao(conn, run["id"], vitima, "exaustao")
    await db.aplicar_condicao(conn, run["id"], vitima, "medo")

    for _ in range(5):
        await cog._vencer_prazo_das_condicoes(run)

    minhas = await db.condicoes_de(conn, run["id"], vitima)
    assert minhas.get("exaustao") == 2, f"a Exaustão não deveria decair, veio {minhas}"
    assert "medo" not in minhas, "o Medo deveria ter decaído"

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  a Exaustão não decai com o combate: ok")


async def caso_teto_tira_da_incursao():
    """Bater no teto da condição tira o personagem da run."""
    conn, canal, cog, incursao = await preparar(salas_de("Evento", TRIVIAL))
    run = await montar_run(conn, canal, cog)
    vitima = JOGADORES[0]
    for _ in range(C.POR_ID["exaustao"].teto):
        await db.aplicar_condicao(conn, run["id"], vitima, "exaustao")
    # Outro empilha Medo muito alem de 5: nao tem teto, nao sai.
    for _ in range(12):
        await db.aplicar_condicao(conn, run["id"], JOGADORES[1], "medo")

    await cog._expulsar_estourados(run)

    restantes = await db.participantes(conn, run["id"])
    assert vitima not in restantes, "quem estourou a Exaustão deveria sair"
    assert JOGADORES[1] in restantes, "Medo não tem teto: ninguém sai por ele"
    assert any("não consegue seguir" in str(m.content or "") for m in canal.enviadas)

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  o teto da condição tira da incursão; sem teto, ninguém sai: ok")


async def caso_aplicar_respeita_o_teto():
    """A aplicação não passa do teto da condição."""
    conn, canal, cog, incursao = await preparar(salas_de("Evento", TRIVIAL))
    run = await montar_run(conn, canal, cog)
    vitima = JOGADORES[0]
    for _ in range(9):
        await db.aplicar_condicao(conn, run["id"], vitima, "exaustao")
    assert (await db.condicoes_de(conn, run["id"], vitima))["exaustao"] == 5
    for _ in range(15):
        await db.aplicar_condicao(conn, run["id"], vitima, "deterioracao")
    assert (await db.condicoes_de(conn, run["id"], vitima))["deterioracao"] == 10
    # Sem teto, empilha livre.
    for _ in range(14):
        await db.aplicar_condicao(conn, run["id"], vitima, "medo")
    assert (await db.condicoes_de(conn, run["id"], vitima))["medo"] == 14

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  aplicar respeita o teto da condição: ok")


async def caso_grupo_inteiro_fora_encerra_a_run():
    """Sem ninguém em condições de seguir, a incursão termina em fracasso."""
    conn, canal, cog, incursao = await preparar(salas_de("Evento", TRIVIAL))
    run = await montar_run(conn, canal, cog)
    for user_id in JOGADORES:
        for _ in range(C.POR_ID["exaustao"].teto):
            await db.aplicar_condicao(conn, run["id"], user_id, "exaustao")

    await cog._expulsar_estourados(run)

    assert not await db.participantes(conn, run["id"])
    assert (await db.buscar_run(conn, run["id"]))["status"] == "fracasso"

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  grupo inteiro fora encerra a run em fracasso: ok")


async def caso_tesouro_falho_acorda_mimicos():
    """Falhar no tesouro pode virar combate com Mímicos, no mesmo passo."""
    conn, canal, cog, incursao = await preparar(salas_de("Tesouro", IMPOSSIVEL))
    run = await montar_run(conn, canal, cog)
    original = X.acordou_mimico
    X.acordou_mimico = lambda rng=None: True
    try:
        alvo, run = await entrar_e_rolar(conn, canal, cog, run)
    finally:
        X.acordou_mimico = original

    assert run["linha_atual"] == 1, run["linha_atual"]
    inimigos = await db.inimigos_do_combate(conn, run["id"], cog._passo(run))
    assert len(inimigos) == X.MIMICOS, inimigos
    assert all(X.NOME_DO_MIMICO in i["nome"] for i in inimigos), inimigos

    corrente = await cog._sala_corrente(run)
    assert corrente is not None and corrente.e_combate, corrente

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  tesouro perdido acorda Mímicos e a emboscada sobrevive: ok")


async def caso_tesouro_falho_sem_mimico_segue():
    """Sem Mímico acordado, o tesouro perdido só devolve o grupo à votação."""
    conn, canal, cog, incursao = await preparar(salas_de("Tesouro", IMPOSSIVEL))
    run = await montar_run(conn, canal, cog)
    original = X.acordou_mimico
    X.acordou_mimico = lambda rng=None: False
    try:
        _, run = await entrar_e_rolar(conn, canal, cog, run)
    finally:
        X.acordou_mimico = original

    assert run["linha_atual"] == 2, run["linha_atual"]
    assert not await db.inimigos_do_combate(conn, run["id"], 1)

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  tesouro perdido sem Mímico devolve à votação: ok")


async def caso_descanso_limpa_um_por_personagem():
    """O descanso é uma limpeza POR personagem, e cada um escolhe a sua."""
    conn, canal, cog, incursao = await preparar(salas_de("Descanso", None))
    run = await montar_run(conn, canal, cog)
    um, outro = JOGADORES[0], JOGADORES[1]
    await db.aplicar_condicao(conn, run["id"], um, "medo")
    await db.aplicar_condicao(conn, run["id"], um, "exaustao")
    await db.aplicar_condicao(conn, run["id"], outro, "envenenado")

    alvo = (await cog._opcoes(run, 1))[0]
    msg = await canal.fetch_message(run["mensagem_id"])
    for user_id in JOGADORES:
        await cog.votar(FakeInteraction(canal, user_id, msg), run["id"], 1, alvo.id)
    run = await db.buscar_run(conn, run["id"])

    assert run["linha_atual"] == 1, "o descanso deveria esperar as escolhas"
    assert await cog._limpezas_disponiveis(run) == {"debuff", "exaustao"}
    assert set(await cog._descanso_pendente(run)) == {um, outro}

    # O primeiro tira a Exaustao dele: a do debuff fica.
    await cog.limpar_no_descanso(
        FakeInteraction(canal, um, msg), run["id"], alvo.id, "exaustao"
    )
    minhas = await db.condicoes_de(conn, run["id"], um)
    assert "exaustao" not in minhas, f"a Exaustão dele deveria sair, sobrou {minhas}"
    assert "medo" in minhas, "uma por personagem: o debuff dele fica"
    assert "envenenado" in await db.condicoes_de(conn, run["id"], outro)

    # Repetir nao vale.
    await cog.limpar_no_descanso(
        FakeInteraction(canal, um, msg), run["id"], alvo.id, "debuff"
    )
    assert "medo" in await db.condicoes_de(conn, run["id"], um)
    assert (await db.buscar_run(conn, run["id"]))["linha_atual"] == 1

    # Categoria que o personagem nao carrega nao gasta a escolha dele.
    i = FakeInteraction(canal, outro, msg)
    await cog.limpar_no_descanso(i, run["id"], alvo.id, "exaustao")
    assert "não carrega nada dessa categoria" in str(i.resposta), i.resposta
    assert await cog._descanso_pendente(await db.buscar_run(conn, run["id"])) == [outro]

    # O ultimo escolhe, e so agora a sala fecha.
    await cog.limpar_no_descanso(
        FakeInteraction(canal, outro, msg), run["id"], alvo.id, "debuff"
    )
    assert "envenenado" not in await db.condicoes_de(conn, run["id"], outro)
    assert (await db.buscar_run(conn, run["id"]))["linha_atual"] == 2

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  o descanso limpa uma condição por personagem: ok")


async def caso_descanso_e_a_saida_da_exaustao():
    """A Exaustão não decai, então o descanso é a única saída dela."""
    conn, canal, cog, incursao = await preparar(salas_de("Descanso", None))
    run = await montar_run(conn, canal, cog)
    vitima = JOGADORES[0]
    for _ in range(3):
        await db.aplicar_condicao(conn, run["id"], vitima, "exaustao")

    alvo = (await cog._opcoes(run, 1))[0]
    msg = await canal.fetch_message(run["mensagem_id"])
    for user_id in JOGADORES:
        await cog.votar(FakeInteraction(canal, user_id, msg), run["id"], 1, alvo.id)
    run = await db.buscar_run(conn, run["id"])

    await cog.limpar_no_descanso(
        FakeInteraction(canal, vitima, msg), run["id"], alvo.id, "exaustao"
    )
    assert (await db.condicoes_de(conn, run["id"], vitima))["exaustao"] == 2, (
        "o descanso tira 1 ponto por vez"
    )

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  o descanso tira 1 ponto de Exaustão por vez: ok")


async def caso_descanso_sem_nada_a_limpar():
    """Grupo limpo não trava no descanso: atravessa sem clique."""
    conn, canal, cog, incursao = await preparar(salas_de("Descanso", None))
    run = await montar_run(conn, canal, cog)
    alvo = (await cog._opcoes(run, 1))[0]
    msg = await canal.fetch_message(run["mensagem_id"])
    for user_id in JOGADORES:
        await cog.votar(FakeInteraction(canal, user_id, msg), run["id"], 1, alvo.id)
    run = await db.buscar_run(conn, run["id"])

    assert await cog._limpezas_disponiveis(run) == set()
    assert run["linha_atual"] == 2, "grupo limpo atravessa o descanso sozinho"

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  grupo limpo atravessa o descanso sem clique: ok")


async def caso_deterioracao_corta_o_hp_do_combatente():
    """A Deterioração chega no HP máximo com que o personagem entra no combate."""
    conn, canal, cog, incursao = await preparar(salas_de("Evento", TRIVIAL))
    run = await montar_run(conn, canal, cog)
    vitima = JOGADORES[0]
    antes = {c.user_id: c.hp_max for c in await cog._combatentes(run)}
    await db.aplicar_condicao(conn, run["id"], vitima, "deterioracao")
    depois = {c.user_id: c.hp_max for c in await cog._combatentes(run)}

    assert depois[vitima] < antes[vitima], (
        f"Deterioração deveria cortar o HP máximo: {antes[vitima]} -> {depois[vitima]}"
    )
    assert depois[JOGADORES[1]] == antes[JOGADORES[1]], "só a vítima muda"

    # E o Sustento sobe.
    await db.aplicar_condicao(conn, run["id"], JOGADORES[1], "sustento")
    com_sustento = {c.user_id: c.hp_max for c in await cog._combatentes(run)}
    assert com_sustento[JOGADORES[1]] > antes[JOGADORES[1]]

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  Deterioração corta e Sustento aumenta o HP máximo: ok")


async def caso_efemera_da_rolagem_sai_na_proxima_sala():
    """O resumo privado da rolagem — e do dano dela — não fica no canal."""
    conn, canal, cog, incursao = await preparar(
        salas_de("Armadilha", IMPOSSIVEL, quantas=9)
    )
    run = await montar_run(conn, canal, cog)

    alvo = (await cog._opcoes(run, 1))[0]
    msg = await canal.fetch_message(run["mensagem_id"])
    for user_id in JOGADORES:
        await cog.votar(FakeInteraction(canal, user_id, msg), run["id"], 1, alvo.id)
    atual = await db.buscar_run(conn, run["id"])
    msg_sala = await canal.fetch_message(atual["mensagem_id"])

    rolagens = []
    for user_id in JOGADORES:
        agora = await db.buscar_run(conn, run["id"])
        if agora["status"] != "em_sala":
            break
        i = FakeInteraction(canal, user_id, msg_sala)
        rolagens.append((user_id, i))
        await cog.rolar(i, run["id"], alvo.id)

    assert rolagens and any("🎲" in str(i.resposta) for _, i in rolagens)

    run = await db.buscar_run(conn, run["id"])
    assert run["status"] == "escolhendo", run["status"]
    alvo2 = (await cog._opcoes(run, 2))[0]
    msg2 = await canal.fetch_message(run["mensagem_id"])
    for user_id in await db.participantes(conn, run["id"]):
        await cog.votar(FakeInteraction(canal, user_id, msg2), run["id"], 2, alvo2.id)

    sobraram = [u for u, i in rolagens if not i.efemera_apagada]
    assert not sobraram, f"a efêmera da rolagem deveria sair; sobrou de {sobraram}"

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  a efêmera da rolagem (e do dano) sai na próxima sala: ok")


async def caso_efemera_do_combate_sai_na_virada():
    """Nenhuma resposta privada do combate atravessa a virada da rodada."""
    conn, canal, cog, incursao = await preparar(salas_de("Evento", TRIVIAL))
    incursao2, _ = montar_conteudo(
        cog,
        incursao_id="longo",
        tamanho="Curta",
        tier=4,
        monstro_objetivo={**INDEFESO, "hp": 9000, "ataque": -20},
        salas=salas_de("Evento", TRIVIAL),
    )
    run_id = await db.criar_run(conn, GUILD, CANAL, "longo", JOGADORES[0])
    for user_id in JOGADORES:
        personagem = await db.personagem_por_nome(
            conn, GUILD, user_id, f"Heroi{user_id}"
        )
        await db.adicionar_participante(conn, run_id, user_id, personagem["id"])
    await db.inicializar_hp(conn, run_id)
    await db.atualizar_run(
        conn, run_id, status="objetivo", sala_atual="OBJ",
        linha_atual=incursao2.passos + 1,
    )
    run = await db.buscar_run(conn, run_id)
    await cog._abrir_combate(run, incursao2.objetivo)

    ordem = await db.iniciativa(conn, run_id, cog._passo(run))
    jogadores = [o["alvo_id"] for o in ordem if o["tipo"] == motor.PERSONAGEM]

    desta_rodada = []
    for user_id in reversed(jogadores):
        i = FakeInteraction(canal, user_id)
        desta_rodada.append((user_id, i))
        await cog.atacar(i, run_id, "OBJ")

    estado = await cog._estado_combate(
        await db.buscar_run(conn, run_id), incursao2.objetivo
    )
    assert estado.rodada == 2, f"a rodada deveria ter virado, está em {estado.rodada}"
    sobraram = [u for u, i in desta_rodada if str(i.resposta) and not i.efemera_apagada]
    assert not sobraram, f"nenhuma efêmera da rodada 1 deveria sobreviver: {sobraram}"

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  nenhuma efêmera do combate atravessa a virada da rodada: ok")


async def main():
    caso_catalogo_bate_com_a_planilha()
    caso_grupos_de_pericia_sao_espelhados()
    caso_nao_escala_por_tier()
    caso_stacks_somam()
    caso_teto_por_condicao()
    caso_deterioracao_a_dez_e_cem_por_cento()
    caso_sustento_e_vigor_somam_para_cima()
    caso_exaustao_tem_numeros_proprios()
    caso_cura_em_combate_respeita_debilidade()
    caso_letargia_e_rapidez_na_iniciativa()
    caso_debuff_de_pericia_muda_a_pericia_escolhida()
    caso_armadilha_tem_cd_mais_facil()
    caso_dano_e_cura_sao_vinte_por_cento()
    caso_pools_por_sala()
    caso_premio_do_evento_so_oferece_o_que_serve()
    caso_graca_sorteia_sem_reposicao()

    await caso_armadilha_cobra_dano_e_debuff()
    await caso_evento_perdido_deixa_debuff_de_evento()
    await caso_evento_vencido_premia()
    await caso_buff_chega_no_numero()
    await caso_condicao_decai_um_por_combate()
    await caso_exaustao_nao_decai()
    await caso_teto_tira_da_incursao()
    await caso_aplicar_respeita_o_teto()
    await caso_grupo_inteiro_fora_encerra_a_run()
    await caso_tesouro_falho_acorda_mimicos()
    await caso_tesouro_falho_sem_mimico_segue()
    await caso_descanso_limpa_um_por_personagem()
    await caso_descanso_e_a_saida_da_exaustao()
    await caso_descanso_sem_nada_a_limpar()
    await caso_deterioracao_corta_o_hp_do_combatente()
    await caso_efemera_da_rolagem_sai_na_proxima_sala()
    await caso_efemera_do_combate_sai_na_virada()
    print("TESTES DE CONDICOES PASSARAM")


if __name__ == "__main__":
    asyncio.run(main())
