"""O bruxo: o pacto que dá poucos favores e grandes (tudo 1x por incursão), as
Invocations do tier par, e o demónio conjurado — o primeiro aliado que não é
jogador a entrar num combate deste bot."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import classes as cl, config, database as db, motor  # noqa: E402
from src.cogs.incursao import Incursoes  # noqa: E402
from fakes import (  # noqa: E402
    leu,
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

SACO = {**INDEFESO, "hp": 500, "ataque": 1, "dano": "1d1"}

# O save de uma criatura sem save escrito sai de `ataque - DEFASAGEM`, e
# depois ganha o ajuste do tier. Com ataque -40 ele fica tao abaixo da CD
# que nenhum d20 salva: e assim que um caso exercita o galho de QUEM
# FALHA sem depender de sorte.
SEM_DEFESA = {**SACO, "ataque": -40}

DOC = [
    (19, 14, 4, 3, 5, 5, "1d10"),
    (31, 15, 4, 4, 7, 7, "1d10"),
    (45, 16, 5, 4, 8, 8, "2d10"),
    (59, 17, 5, 5, 10, 9, "2d10"),
    (73, 18, 6, 5, 11, 11, "3d10"),
]


async def preparar(nivel=9, escolhas=None, quantos=3, monstros=2,
                   so_o_primeiro=False, monstro=None):
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass
    config.DB_PATH = Path(__file__).resolve().parent / "teste_bruxo.db"
    config.DB_PATH.unlink(missing_ok=True)
    config.TAMANHO_GRUPO = 5
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    await criar_grupo(conn, nivel=nivel, classe="bruxo")
    canal = FakeCanal(CANAL)
    cog = Incursoes(FakeBot(conn, canal))
    incursao, _ = montar_conteudo(
        cog, tamanho="Curta", salas=salas_sem_combate(),
        monstro_objetivo=monstro or SACO, inimigos_objetivo=monstros,
    )
    run_id = await db.criar_run(conn, GUILD, CANAL, incursao.id, JOGADORES[0])
    for user_id in JOGADORES[:quantos]:
        p = await db.personagem_por_nome(conn, GUILD, user_id, f"Heroi{user_id}")
        await db.adicionar_participante(conn, run_id, user_id, p["id"])
        # `so_o_primeiro` deixa o resto do grupo sem a escolha: e o unico jeito
        # de testar "nao vale para os outros" num grupo todo da mesma classe.
        if so_o_primeiro and user_id != JOGADORES[0]:
            continue
        for escolha, opcao in (escolhas or {}).items():
            await db.definir_escolha(conn, p["id"], escolha, opcao)
    await db.inicializar_hp(conn, run_id)
    await db.atualizar_run(
        conn, run_id, status="objetivo", sala_atual="OBJ",
        linha_atual=incursao.passos + 1,
    )
    run = await db.buscar_run(conn, run_id)
    await cog._abrir_combate(run, incursao.objetivo)
    return conn, canal, cog, incursao, await db.buscar_run(conn, run_id)


# ------------------------------------------------------------------- a tabela


def caso_tabela_e_forma():
    bruxo = cl.CLASSES["bruxo"]
    campos = ("hp", "ca", "pericias", "bonus_pericia", "bonus_proficiencia",
              "acerto", "dano")
    for i, linha in enumerate(DOC, start=1):
        for campo, esperado in zip(campos, linha):
            assert getattr(bruxo.tiers[i], campo) == esperado, (i, campo)
    # d8: o HP e o do clerigo e do artifice
    clerigo = cl.CLASSES["clerigo"]
    assert [bruxo.tiers[t].hp for t in range(1, 6)] == [
        clerigo.tiers[t].hp for t in range(1, 6)
    ]
    # e a CA fica entre o mago (sem armadura) e o clerigo
    for t in range(1, 6):
        assert cl.CLASSES["mago"].tiers[t].ca < bruxo.tiers[t].ca < clerigo.tiers[t].ca + 1
    assert bruxo.saves == ("SAB", "CAR")
    print("  d8 como o clerigo, CA entre o mago e ele, saves SAB e CAR: ok")


def caso_tudo_e_uma_vez_por_incursao():
    """O pacto cobra: cada favor sai uma vez por dungeon, e só."""
    # Da tabela crua, e nao da lista filtrada: aqui interessa TODA ativa que a
    # classe pode destravar, nao so a de uma escolha ja feita.
    ativas = [
        h
        for lista in cl.CLASSES["bruxo"].habilidades.values()
        for h in lista
        if h.tipo == cl.ATIVA
    ]
    assert len(ativas) >= 9, f"uma por opcao dos tres tiers impares, nao {len(ativas)}"
    for h in ativas:
        assert h.escopo == "incursao", (h.nome, h.escopo)
        assert h.vezes == 1, (h.nome, h.vezes)
    # e nenhuma outra classe tem isso: o mago e o clerigo misturam escopos
    do_mago = {
        h.escopo
        for lista in cl.CLASSES["mago"].habilidades.values()
        for h in lista
        if h.tipo == cl.ATIVA
    }
    assert do_mago != {"incursao"}, "o mago nao e 1x por incursao em tudo"
    print(f"  as {len(ativas)} ativas do bruxo sao todas 1x por incursao: ok")


def caso_forma_das_classes():
    bruxo = cl.CLASSES["bruxo"]
    for t in (1, 3, 5):
        escolha = [h for h in bruxo.habilidades[t] if h.tipo == cl.ESCOLHA]
        assert len(escolha) == 1 and len(escolha[0].escolha["opcoes"]) == 3, t
    for t in (2, 4):
        escolha = [h for h in bruxo.habilidades[t] if h.tipo == cl.ESCOLHA]
        assert len(escolha) == 1, t
        for o in escolha[0].escolha["opcoes"]:
            # passiva: soma numero, ou destrava a reacao da Own Luck
            destravadas = {
                h.exige_escolha[1] for h in bruxo.habilidades[t] if h.exige_escolha
            }
            assert o.get("efeito") or o["id"] in destravadas, (t, o["id"])
    print("  tiers 1/3/5 com tres magias; 2/4 com as Invocations: ok")


def caso_devils_sight_virou_pericia():
    """Ver no escuro não tem onde pegar: virou achar o que está escondido."""
    efeitos = cl.efeitos("bruxo", 9, {"invocacao_t2": "devils_sight"})
    assert efeitos["bonus_pericia"]["Percepção"] == 3
    assert efeitos["bonus_pericia"]["Investigação"] == 3
    print("  Devil's Sight virou +3 em Percepcao e Investigacao: ok")


# ----------------------------------------------------------------- as magias


async def caso_hex_marca_o_alvo():
    conn, canal, cog, incursao, run = await preparar(escolhas={"pacto_t1": "hex"})
    estado = await cog._estado_combate(run, incursao.objetivo)
    alvo = estado.inimigos[0].indice

    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.usar_habilidade(inter, run["id"], "OBJ", "hex", [alvo])
    estado = await cog._estado_combate(await db.buscar_run(conn, run["id"]),
                                       incursao.objetivo)
    dono = estado.combatente(JOGADORES[0])
    assert dono.dano_por_alvo.get(alvo) == ("Hex", "1d6"), dono.dano_por_alvo
    print("  Hex marca o inimigo e todo golpe nele leva +1d6: ok")


async def caso_hunger_of_hadar_da_dano_e_tira_a_vez():
    """O dano e a perda de vez vem JUNTOS, em quem falha no save.

    A criatura nao tem `metade`: quem passa leva zero. Com o SACO comum
    os tres passavam o save em ~9% das rodadas e o caso quebrava sozinho,
    porque ele exigia dano de alguem. Com a criatura sem defesa, os tres
    falham sempre e o galho que importa e o que roda.
    """
    conn, canal, cog, incursao, run = await preparar(
        escolhas={"pacto_t3": "hunger_of_hadar"}, monstros=3,
        monstro=SEM_DEFESA,
    )
    estado = await cog._estado_combate(run, incursao.objetivo)
    antes = {i.indice: i.hp_atual for i in estado.inimigos}

    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.usar_habilidade(inter, run["id"], "OBJ", "hunger_of_hadar")
    estado = await cog._estado_combate(await db.buscar_run(conn, run["id"]),
                                       incursao.objetivo)
    levaram = [antes[i.indice] - i.hp_atual for i in estado.inimigos]
    # 6d6: minimo 6, maximo 36. Todos falharam, entao todos levaram.
    assert all(6 <= d <= 36 for d in levaram), levaram
    # e os mesmos perderam a vez: o dano e o atordoamento andam juntos
    assert all(i.atordoado for i in estado.inimigos), [
        (i.nome, i.atordoado) for i in estado.inimigos
    ]
    assert "perde a vez" in leu(inter), leu(inter)
    print("  Hunger of Hadar faz dano E tira a vez no mesmo lance: ok")


async def caso_synaptic_static_atrapalha_o_ataque():
    """Quem falha no save perde 3 de ataque, e a perda chega na rolagem.

    Com a criatura comum isto era um `if/else`: ou alguem foi atrapalhado,
    ou a linha dizia "resistiu". So que resistir aqui NAO e sair ileso — a
    magia tem `metade` —, entao o texto do galho de cima nunca trazia essa
    palavra e o caso quebrava quando os dois passavam no save.
    """
    conn, canal, cog, incursao, run = await preparar(
        escolhas={"pacto_t5": "synaptic_static"}, monstros=2,
        monstro=SEM_DEFESA,
    )
    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.usar_habilidade(inter, run["id"], "OBJ", "synaptic_static")
    estado = await cog._estado_combate(await db.buscar_run(conn, run["id"]),
                                       incursao.objetivo)
    atrapalhados = [i for i in estado.inimigos if i.penalidade_ataque > 0]
    assert len(atrapalhados) == len(estado.inimigos), [
        (i.nome, i.penalidade_ataque) for i in estado.inimigos
    ]
    assert all(i.penalidade_ataque == 3 for i in atrapalhados)
    # e a penalidade chega na rolagem de verdade
    alvo = motor.Combatente(1, "X", 99, 0, "1d1", 50, 50)
    golpe = motor.contra_atacar(atrapalhados[0], alvo)
    assert golpe.bonus == atrapalhados[0].ataque - 3, golpe.bonus
    print("  Synaptic Static desconta 3 do ataque de quem falha: ok")


async def caso_own_luck_so_socorre_o_bruxo():
    """O patrono torce o destino DELE, não o de mais ninguém."""
    conn, canal, cog, incursao, run = await preparar(
        escolhas={"patrono_t4": "own_luck"}, so_o_primeiro=True
    )
    dono = JOGADORES[0]
    # um teste falhado de OUTRO personagem, que nao tem a benesse: a reacao do
    # dono nao pode disparar nele
    resultado = motor.ResultadoTeste(JOGADORES[1], "Outro", "Atletismo", 5, 2, 15)
    await cog._socorrer_o_teste(run, resultado)
    assert resultado.ajuda == 0, "nao socorre o teste alheio"
    # o proprio, falhando por menos de 10: socorre
    meu = motor.ResultadoTeste(dono, "Heroi", "Atletismo", 5, 2, 15)
    await cog._socorrer_o_teste(run, meu)
    assert meu.ajuda == 10 and meu.passou, (meu.ajuda, meu.total)
    print("  Dark One's Own Luck socorre o bruxo e so ele: ok")


# ------------------------------------------------------------- a invocacao


async def caso_demonio_entra_na_luta():
    conn, canal, cog, incursao, run = await preparar(
        escolhas={"pacto_t5": "summon_greater_demon"}
    )
    antes = await cog._estado_combate(run, incursao.objetivo)
    quantos_antes = len(antes.combatentes)

    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.usar_habilidade(inter, run["id"], "OBJ", "summon_greater_demon")
    run = await db.buscar_run(conn, run["id"])
    estado = await cog._estado_combate(run, incursao.objetivo)

    assert len(estado.combatentes) == quantos_antes + 1
    demonio = next(c for c in estado.combatentes if c.e_invocacao)
    assert demonio.dono == JOGADORES[0]
    assert demonio.user_id < 0, "o id e negativo para nao colidir com o Discord"
    assert (demonio.hp_max, demonio.ca, demonio.bonus_ataque) == (45, 15, 8)
    # e entrou na ordem do combate, no fim
    ordem = await db.iniciativa(conn, run["id"], cog._passo(run))
    assert ordem[-1]["alvo_id"] == demonio.user_id, [o["nome"] for o in ordem]
    print("  o demonio entra como combatente de dono, no fim da ordem: ok")


async def caso_demonio_bate_sozinho():
    conn, canal, cog, incursao, run = await preparar(
        escolhas={"pacto_t5": "summon_greater_demon"}, monstros=2
    )
    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.usar_habilidade(inter, run["id"], "OBJ", "summon_greater_demon")
    run = await db.buscar_run(conn, run["id"])
    estado = await cog._estado_combate(run, incursao.objetivo)
    demonio = next(c for c in estado.combatentes if c.e_invocacao)
    # deixa um inimigo mais ferido: e nele que o demonio mira
    ferido = estado.inimigos[1]
    await db.definir_hp_inimigos(
        conn, run["id"], cog._passo(run), {ferido.indice: 20}
    )
    estado = await cog._estado_combate(run, incursao.objetivo)
    demonio = next(c for c in estado.combatentes if c.e_invocacao)
    antes = estado.inimigo(ferido.indice).hp_atual

    await cog._vez_da_invocacao(run, estado, demonio)
    depois = estado.inimigo(ferido.indice).hp_atual
    # ou acertou o mais ferido, ou errou — nunca mirou o outro
    assert depois <= antes
    intocado = estado.inimigo(estado.inimigos[0].indice)
    assert intocado.hp_atual == intocado.hp_max, "o demonio nao mirou o outro"
    print("  o demonio bate sozinho, no inimigo mais ferido: ok")


async def caso_demonio_e_alvo_e_tem_hp_proprio():
    """Ele é um Combatente de verdade: os inimigos miram nele e ele cai."""
    conn, canal, cog, incursao, run = await preparar(
        escolhas={"pacto_t5": "summon_greater_demon"}
    )
    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.usar_habilidade(inter, run["id"], "OBJ", "summon_greater_demon")
    run = await db.buscar_run(conn, run["id"])
    estado = await cog._estado_combate(run, incursao.objetivo)
    demonio = next(c for c in estado.combatentes if c.e_invocacao)

    # a ameaca dele conta no sorteio, como de qualquer um
    assert demonio.ameaca_total == 4, demonio.ameaca_total
    # e o HP dele vai para a tabela de invocacoes, nao para run_participantes
    demonio.hp_atual = 12
    await cog._gravar_hp_do_combatente(run, demonio)
    estado = await cog._estado_combate(run, incursao.objetivo)
    de_novo = next(c for c in estado.combatentes if c.e_invocacao)
    assert de_novo.hp_atual == 12, de_novo.hp_atual
    print("  o demonio e alvo valido e o HP dele persiste no lugar certo: ok")


async def caso_demonio_sai_na_proxima_sala():
    """A tabela é por passo, então ele some sozinho quando o grupo anda."""
    conn, canal, cog, incursao, run = await preparar(
        escolhas={"pacto_t5": "summon_greater_demon"}
    )
    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.usar_habilidade(inter, run["id"], "OBJ", "summon_greater_demon")
    passo = cog._passo(await db.buscar_run(conn, run["id"]))
    assert await db.invocacoes(conn, run["id"], passo), "esta na sala"
    assert not await db.invocacoes(conn, run["id"], passo + 1), "nao na seguinte"
    print("  o demonio nao atravessa a porta: a tabela e por passo: ok")


async def caso_conjurar_de_novo_troca_o_demonio():
    conn, canal, cog, incursao, run = await preparar(
        escolhas={"pacto_t5": "summon_greater_demon"}
    )
    passo = cog._passo(run)
    primeiro = await db.invocar(
        conn, run["id"], passo, JOGADORES[0], "Um", 15, 8, "2d6", 45
    )
    segundo = await db.invocar(
        conn, run["id"], passo, JOGADORES[0], "Dois", 15, 8, "2d6", 45
    )
    vivos = await db.invocacoes(conn, run["id"], passo)
    assert len(vivos) == 1 and vivos[0]["nome"] == "Dois", vivos
    # o id e estavel por dono: o lugar na iniciativa esta ligado a ele
    assert primeiro == segundo, (primeiro, segundo)
    # e dois donos diferentes nao se sobrepoem
    terceiro = await db.invocar(
        conn, run["id"], passo, JOGADORES[1], "Tres", 15, 8, "2d6", 45
    )
    assert terceiro != primeiro, (terceiro, primeiro)
    assert len(await db.invocacoes(conn, run["id"], passo)) == 2
    print("  um por dono, com id estavel; donos diferentes convivem: ok")


async def main():
    try:
        caso_tabela_e_forma()
        caso_tudo_e_uma_vez_por_incursao()
        caso_forma_das_classes()
        caso_devils_sight_virou_pericia()
        await caso_hex_marca_o_alvo()
        await caso_hunger_of_hadar_da_dano_e_tira_a_vez()
        await caso_synaptic_static_atrapalha_o_ataque()
        await caso_own_luck_so_socorre_o_bruxo()
        await caso_demonio_entra_na_luta()
        await caso_demonio_bate_sozinho()
        await caso_demonio_e_alvo_e_tem_hp_proprio()
        await caso_demonio_sai_na_proxima_sala()
        await caso_conjurar_de_novo_troca_o_demonio()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        (Path(__file__).resolve().parent / "teste_bruxo.db").unlink(missing_ok=True)


asyncio.run(main())
print("TESTES DO BRUXO PASSARAM")
