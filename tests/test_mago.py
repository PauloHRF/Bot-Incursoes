"""O mago: a tabela de d6, a forma fixa das classes (ativa nos tiers ímpares,
passiva nos pares) e as magias — a que sempre acerta, a que apaga a sala, a que
tira o grupo de alcance e a que faz o save escapar inteiro."""
from __future__ import annotations

import asyncio
import collections
import random
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import ameaca, classes as cl, config, database as db, motor  # noqa: E402
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

SACO = {**INDEFESO, "hp": 500, "ataque": 1, "dano": "1d1"}

DOC = [
    (15, 13, 4, 3, 5, 5, "1d10"),
    (27, 14, 4, 4, 7, 7, "2d10"),
    (39, 15, 5, 4, 8, 8, "2d10"),
    (51, 16, 5, 5, 10, 9, "3d10"),
    (63, 17, 6, 5, 11, 11, "4d10"),
]


async def preparar(nivel=9, escolhas=None, quantos=3, monstros=2):
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass
    config.DB_PATH = Path(__file__).resolve().parent / "teste_mago.db"
    config.DB_PATH.unlink(missing_ok=True)
    config.TAMANHO_GRUPO = 5
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    await criar_grupo(conn, nivel=nivel, classe="mago")
    canal = FakeCanal(CANAL)
    cog = Incursoes(FakeBot(conn, canal))
    incursao, _ = montar_conteudo(
        cog, tamanho="Curta", salas=salas_sem_combate(),
        monstro_objetivo=SACO, inimigos_objetivo=monstros,
    )
    run_id = await db.criar_run(conn, GUILD, CANAL, incursao.id, JOGADORES[0])
    for user_id in JOGADORES[:quantos]:
        p = await db.personagem_por_nome(conn, GUILD, user_id, f"Heroi{user_id}")
        await db.adicionar_participante(conn, run_id, user_id, p["id"])
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


def caso_tabela_de_d6():
    mago = cl.CLASSES["mago"]
    campos = ("hp", "ca", "pericias", "bonus_pericia", "bonus_proficiencia",
              "acerto", "dano")
    for i, linha in enumerate(DOC, start=1):
        for campo, esperado in zip(campos, linha):
            assert getattr(mago.tiers[i], campo) == esperado, (i, campo)

    # O HP segue o padrao exato por dado de vida: d12 sobe 20, d10 sobe 18,
    # d8 sobe 14. O d6 sobe 12.
    saltos = {
        mago.tiers[t + 1].hp - mago.tiers[t].hp for t in range(1, 5)
    }
    assert saltos == {12}, saltos
    assert {
        cl.CLASSES["barbaro"].tiers[2].hp - cl.CLASSES["barbaro"].tiers[1].hp
    } == {20}, "o barbaro de d12 sobe 20"

    # E a CA e a pior do jogo em todo tier
    for t in range(1, 6):
        pior = min(c.tiers[t].ca for c in cl.CLASSES.values())
        assert mago.tiers[t].ca == pior, f"T{t}: o mago tem de ser o mais frouxo"
    assert mago.saves == ("CON", "INT")
    print("  d6 sobe 12 por tier, e a CA e a pior do jogo: ok")


def caso_forma_das_classes():
    """A forma combinada: ativa nos tiers ímpares, passiva nos pares."""
    mago = cl.CLASSES["mago"]
    for t in (1, 3, 5):
        escolhas = [h for h in mago.habilidades[t] if h.tipo == cl.ESCOLHA]
        assert len(escolhas) == 1, f"T{t} tem de ter uma escolha"
        opcoes = escolhas[0].escolha["opcoes"]
        assert len(opcoes) == 3, f"T{t}: tres magias, nao {len(opcoes)}"
        # e cada opcao destrava uma ativa
        destravadas = {
            h.exige_escolha[1] for h in mago.habilidades[t] if h.exige_escolha
        }
        assert destravadas == {o["id"] for o in opcoes}, (t, destravadas)
        for h in mago.habilidades[t]:
            if h.exige_escolha:
                assert h.tipo == cl.ATIVA, f"T{t}/{h.nome} devia ser ativa"
    for t in (2, 4):
        assert len(mago.habilidades[t]) == 1, f"T{t} tem uma habilidade so"
        escolha = mago.habilidades[t][0]
        # passiva escolhida: cada opcao soma numero, nenhuma destrava ativa
        for o in escolha.escolha["opcoes"]:
            assert o.get("efeito"), f"T{t}/{o['id']} nao soma nada"
    print("  tiers 1/3/5 sao ativa com tres magias; 2/4 sao passiva: ok")


def caso_cantrip_e_o_ataque_basico():
    """O mago não tem arma: a coluna de dano é o cantrip dele."""
    from src.habilidades import media_do_dado
    mago = cl.CLASSES["mago"]
    medias = [media_do_dado(mago.tiers[t].dano) for t in range(1, 6)]
    assert medias == [5.5, 11.0, 11.0, 16.5, 22.0], medias
    # sem Multiattack: o cantrip sai uma vez por rodada
    assert cl.efeitos("mago", 10, {}).get("ataques", 1) == 1
    print("  o cantrip vai de 1d10 a 4d10 e sai uma vez por rodada: ok")


# --------------------------------------------------------------- as magias


async def caso_magic_missile_sempre_acerta():
    conn, canal, cog, incursao, run = await preparar(
        escolhas={"magia_mago_t1": "magic_missile"}
    )
    estado = await cog._estado_combate(run, incursao.objetivo)
    alvo = estado.inimigos[0].indice
    antes = estado.inimigos[0].hp_atual

    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.usar_habilidade(inter, run["id"], "OBJ", "magic_missile", [alvo])
    estado = await cog._estado_combate(await db.buscar_run(conn, run["id"]),
                                       incursao.objetivo)
    levou = antes - estado.inimigo(alvo).hp_atual
    assert 6 <= levou <= 15, levou  # 3d4+3
    # nao ha rolagem de save na linha: os dardos nao se resistem
    assert "vs CD" not in inter.resposta, inter.resposta
    print(f"  Magic Missile entra sem save ({levou} de dano): ok")


async def caso_fireball_pega_todos():
    conn, canal, cog, incursao, run = await preparar(
        escolhas={"magia_mago_t3": "fireball"}, monstros=3
    )
    estado = await cog._estado_combate(run, incursao.objetivo)
    antes = {i.indice: i.hp_atual for i in estado.inimigos}

    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.usar_habilidade(inter, run["id"], "OBJ", "fireball")
    estado = await cog._estado_combate(await db.buscar_run(conn, run["id"]),
                                       incursao.objetivo)
    for i in estado.inimigos:
        levou = antes[i.indice] - i.hp_atual
        assert levou >= 4, (i.nome, levou)  # 8d6, metade no sucesso
    assert "CD 19" in inter.resposta
    print("  Fireball cobra save de DES de todos, com metade no sucesso: ok")


async def caso_hold_monster_prende_tres_rodadas():
    conn, canal, cog, incursao, run = await preparar(
        escolhas={"magia_mago_t5": "hold_monster"}
    )
    estado = await cog._estado_combate(run, incursao.objetivo)
    alvo = estado.inimigos[0].indice
    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.usar_habilidade(inter, run["id"], "OBJ", "hold_monster", [alvo])
    ligados = await db.efeitos_ativos(conn, run["id"], cog._passo(run), 0)
    presos = [
        l for l in ligados
        if l["alvo_tipo"] == "inimigo" and l["efeito"] == "atordoado"
    ]
    if presos:
        assert presos[0]["expira"] - estado.rodada == 3, presos[0]
    else:
        assert "resistiu" in inter.resposta, inter.resposta
    print("  Hold Monster prende por tres rodadas quando pega: ok")


async def caso_fly_tira_tres_de_alcance():
    conn, canal, cog, incursao, run = await preparar(
        escolhas={"magia_mago_t3": "fly"}
    )
    # Fly pede alvo, como a cura: o jogador escolhe quem sobe.
    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.usar_habilidade(
        inter, run["id"], "OBJ", "fly", list(JOGADORES[:3])
    )
    estado = await cog._estado_combate(await db.buscar_run(conn, run["id"]),
                                       incursao.objetivo)
    voando = [c for c in estado.vivos if c.ameaca_fator < 1]
    assert len(voando) == 3, [c.nome for c in estado.vivos]
    for c in voando:
        assert c.ameaca_fator == 0.2, (c.nome, c.ameaca_fator)
        assert c.ameaca_total > 0, "a ameaca crua nao muda: o fator pesa o sorteio"
    print("  Fly corta a quinto o peso de tres no sorteio de alvo: ok")


def caso_fly_reduz_sem_zerar():
    """Voando ele é raramente alvo, mas não imune — e o sorteio comprova."""
    rng = random.Random(4)
    tanque = motor.Combatente(1, "Tanque", 15, 5, "1d8", 100, 100, ameaca=6)
    mago = motor.Combatente(2, "Mago", 13, 5, "1d8", 60, 60, ameaca=2)
    sem_voar = ameaca.porcentagens([6, 2])[1]
    mago.ameaca_fator = 0.2
    inimigo = motor.Inimigo(0, "Bicho", 12, 4, "1d4", 50, 50)
    estado = motor.EstadoCombate([inimigo], 1, [tanque, mago])
    n = 20000
    conta = collections.Counter(
        motor.sortear_alvo(estado, rng).nome for _ in range(n)
    )
    fatia = conta["Mago"] / n * 100
    esperado = ameaca.porcentagens([6, 2], [1.0, 0.2])[1]
    assert abs(fatia - esperado) < 1.0, (fatia, esperado)
    # cortou de verdade, e nao virou imunidade
    assert fatia < sem_voar / 3, (fatia, sem_voar)
    assert conta["Mago"] > 0, "o mago nao fica imune"
    print(f"  voando ele leva {fatia:.1f}% (sem voar, {sem_voar:.0f}%): ok")


# ---------------------------------------------------------- as duas passivas


async def caso_escudo_arcano_entra_no_combate():
    conn, canal, cog, incursao, run = await preparar(
        escolhas={"tradicao_arcana": "escudo_arcano"}
    )
    estado = await cog._estado_combate(run, incursao.objetivo)
    # 2 por tier, e o grupo esta no tier 5
    for c in estado.vivos:
        assert c.thp == 10, (c.nome, c.thp)
    print("  Escudo Arcano abre o combate com 10 de THP no tier 5: ok")


async def caso_sabedoria_arcana_pega_o_grupo():
    conn, canal, cog, incursao, run = await preparar(
        escolhas={"tradicao_arcana": "sabedoria_arcana"}
    )
    estado = await cog._estado_combate(run, incursao.objetivo)
    base = cl.saves("mago", 9)
    for c in estado.vivos:
        for atributo, valor in base.items():
            assert c.saves[atributo] == valor + 2, (c.nome, atributo, c.saves)
    print("  Sabedoria Arcana da +2 em todo save do grupo inteiro: ok")


def caso_evocacao_potente_usa_o_dano_bonus():
    efeitos = cl.efeitos("mago", 9, {"tradicao_arcana": "evocacao_potente"})
    assert efeitos["dano_bonus"] == "1d8"
    print("  Evocacao Potente entra pelo dano_bonus que o motor ja le: ok")


# ------------------------------------------------------- o Circle of Power


def caso_save_anula_tira_a_metade():
    """Passar no save passa a escapar inteiro, em vez de levar metade."""
    class Sopro:
        nome, save, cd, dano, metade = "Sopro", "DES", 1, "10d6", True
        atordoa, save_repete, debuff = 0, False, ()

    inimigo = motor.Inimigo(0, "Dragao", 18, 10, "2d10", 200, 200)
    # CD 1: o alvo sempre passa
    normal = motor.Combatente(1, "Normal", 15, 5, "1d8", 200, 200)
    protegido = motor.Combatente(2, "Protegido", 15, 5, "1d8", 200, 200)
    protegido.save_anula = True

    com_metade = motor.impor_save(inimigo, Sopro(), normal, random.Random(1))
    sem_metade = motor.impor_save(inimigo, Sopro(), protegido, random.Random(1))
    assert com_metade.escapou and sem_metade.escapou, "os dois passam no save"
    assert com_metade.dano > 0, "quem nao tem o circulo leva metade"
    assert sem_metade.dano == 0, "quem tem escapa inteiro"
    print(f"  Circle of Power: passar leva 0 em vez de {com_metade.dano}: ok")


async def caso_circle_of_power_liga_no_grupo():
    conn, canal, cog, incursao, run = await preparar(
        escolhas={"magia_mago_t5": "circle_of_power"}
    )
    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.usar_habilidade(inter, run["id"], "OBJ", "circle_of_power")
    estado = await cog._estado_combate(await db.buscar_run(conn, run["id"]),
                                       incursao.objetivo)
    for c in estado.vivos:
        assert c.vantagem, f"{c.nome} devia rolar os saves com vantagem"
        assert c.save_anula, f"{c.nome} devia escapar inteiro ao passar"
    print("  Circle of Power liga vantagem e escape inteiro no grupo: ok")


async def main():
    try:
        caso_tabela_de_d6()
        caso_forma_das_classes()
        caso_cantrip_e_o_ataque_basico()
        await caso_magic_missile_sempre_acerta()
        await caso_fireball_pega_todos()
        await caso_hold_monster_prende_tres_rodadas()
        await caso_fly_tira_tres_de_alcance()
        caso_fly_reduz_sem_zerar()
        await caso_escudo_arcano_entra_no_combate()
        await caso_sabedoria_arcana_pega_o_grupo()
        caso_evocacao_potente_usa_o_dano_bonus()
        caso_save_anula_tira_a_metade()
        await caso_circle_of_power_liga_no_grupo()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        (Path(__file__).resolve().parent / "teste_mago.db").unlink(missing_ok=True)


asyncio.run(main())
print("TESTES DO MAGO PASSARAM")
