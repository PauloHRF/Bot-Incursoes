"""O druida: o único com um trade de verdade — fora da forma é o pior atacante
do jogo, virado bicho bate como um marcial, e enquanto está virado não conjura.
Mais o bichinho, o bando conjurado e a esfera que ninguém atravessa."""
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
from src.habilidades import media_do_dado  # noqa: E402
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
    (19, 15, 4, 3, 5, 5, "1d8"),
    (31, 16, 4, 4, 7, 7, "1d8"),
    (45, 17, 5, 4, 8, 8, "2d8"),
    (59, 18, 5, 5, 10, 9, "2d8"),
    (73, 19, 6, 5, 11, 11, "2d8"),
]


async def preparar(nivel=9, escolhas=None, quantos=3, monstros=2):
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass
    config.DB_PATH = Path(__file__).resolve().parent / "teste_druida.db"
    config.DB_PATH.unlink(missing_ok=True)
    config.TAMANHO_GRUPO = 5
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    await criar_grupo(conn, nivel=nivel, classe="druida")
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


def _formas():
    return {
        h.id: h.acao
        for lista in cl.CLASSES["druida"].habilidades.values()
        for h in lista
        if (h.acao or {}).get("tipo") == "forma"
    }


# ------------------------------------------------------------------- a tabela


def caso_tabela_e_o_trade():
    druida = cl.CLASSES["druida"]
    campos = ("hp", "ca", "pericias", "bonus_pericia", "bonus_proficiencia",
              "acerto", "dano")
    for i, linha in enumerate(DOC, start=1):
        for campo, esperado in zip(campos, linha):
            assert getattr(druida.tiers[i], campo) == esperado, (i, campo)

    # fora da forma ele e o pior atacante do jogo, empatado com o clerigo
    base = media_do_dado(druida.tiers[5].dano)
    piores = sorted(
        media_do_dado(c.tiers[5].dano) * cl.efeitos(cid, 10, {}).get("ataques", 1)
        for cid, c in cl.CLASSES.items()
    )
    assert base == piores[0], f"o druida base deveria ser o pior, nao {base}"
    print(f"  d8, CA 15-19, e o pior dano base do jogo ({base:.0f}/rodada): ok")


def caso_a_forma_dobra_o_dano_e_escala():
    """Dado fixo quebraria o tier 1 ou seria inútil no 5 — então escala."""
    druida = cl.CLASSES["druida"]
    formas = _formas()
    assert set(formas) == {"forma_urso", "forma_lobo", "forma_aranha"}
    for fid, acao in formas.items():
        assert set(acao["dano"]) == {1, 2, 3, 4, 5}, (fid, acao["dano"])
        anterior = 0.0
        for t in range(1, 6):
            base = media_do_dado(druida.tiers[t].dano)
            na_forma = media_do_dado(acao["dano"][t]) * acao.get("ataques", 1)
            assert na_forma > base, f"{fid} T{t}: a forma tem de valer a pena"
            assert na_forma >= anterior, f"{fid} T{t}: a forma nunca piora"
            anterior = na_forma
    # e no topo ela chega ao nivel de um marcial medio, nao acima
    melhor = max(
        media_do_dado(a["dano"][5]) * a.get("ataques", 1) for a in formas.values()
    )
    patrulheiro = media_do_dado(cl.CLASSES["patrulheiro"].tiers[5].dano) * 2
    assert melhor <= patrulheiro, (melhor, patrulheiro)
    print(f"  a forma vai de 6,5 a {melhor:.0f} e nao passa do patrulheiro: ok")


def caso_forma_das_classes():
    druida = cl.CLASSES["druida"]
    for t in (1, 3, 5):
        escolha = [h for h in druida.habilidades[t] if h.tipo == cl.ESCOLHA]
        assert len(escolha) == 1 and len(escolha[0].escolha["opcoes"]) == 3, t
    for t in (2, 4):
        assert len([h for h in druida.habilidades[t] if h.tipo == cl.ESCOLHA]) == 1, t
    print("  tiers 1/3/5 com tres opcoes; 2/4 com a passiva: ok")


# ------------------------------------------------------------- o Wild Shape


async def caso_urso_troca_o_corpo():
    conn, canal, cog, incursao, run = await preparar(escolhas={"forma_t1": "urso"})
    estado = await cog._estado_combate(run, incursao.objetivo)
    antes = estado.combatente(JOGADORES[0])
    assert antes.dano_arma == "2d8", antes.dano_arma
    assert not antes.forma

    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.usar_habilidade(inter, run["id"], "OBJ", "forma_urso")
    estado = await cog._estado_combate(await db.buscar_run(conn, run["id"]),
                                       incursao.objetivo)
    urso = estado.combatente(JOGADORES[0])
    # o dado de arma e SUBSTITUIDO, nao somado: e a forma que bate
    assert urso.dano_arma == "2d10+5", urso.dano_arma
    assert urso.forma == "Urso"
    assert urso.ca_extra == 3, urso.ca_extra
    # e a vida temporaria e o corpo da besta: 3 por tier, no tier 5
    assert urso.thp == 15, urso.thp
    print("  o urso troca o dado de arma, soma CA e empresta 15 de THP: ok")


async def caso_lobo_morde_duas_vezes():
    conn, canal, cog, incursao, run = await preparar(escolhas={"forma_t1": "lobo"})
    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.usar_habilidade(inter, run["id"], "OBJ", "forma_lobo")
    estado = await cog._estado_combate(await db.buscar_run(conn, run["id"]),
                                       incursao.objetivo)
    lobo = estado.combatente(JOGADORES[0])
    assert lobo.ataques == 2, lobo.ataques
    assert lobo.dano_arma == "1d10+4" and lobo.ca_extra == 0
    assert lobo.thp == 10, lobo.thp  # 2 por tier
    print("  o lobo morde duas vezes, sem CA extra e com menos THP: ok")


async def caso_forma_lunar_dobra_o_thp():
    conn, canal, cog, incursao, run = await preparar(
        escolhas={"forma_t1": "urso", "natureza_t4": "forma_lunar"}
    )
    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.usar_habilidade(inter, run["id"], "OBJ", "forma_urso")
    estado = await cog._estado_combate(await db.buscar_run(conn, run["id"]),
                                       incursao.objetivo)
    assert estado.combatente(JOGADORES[0]).thp == 30, "15 dobra para 30"
    print("  Forma Lunar dobra o corpo que a forma empresta (15 -> 30): ok")


async def caso_aranha_envenena_quem_acerta():
    conn, canal, cog, incursao, run = await preparar(
        escolhas={"forma_t1": "aranha"}, monstros=1
    )
    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.usar_habilidade(inter, run["id"], "OBJ", "forma_aranha")
    run = await db.buscar_run(conn, run["id"])
    estado = await cog._estado_combate(run, incursao.objetivo)
    aranha = estado.combatente(JOGADORES[0])
    assert aranha.veneno_no_golpe == 2, aranha.veneno_no_golpe

    # transformar gastou o turno: a mordida vem na rodada seguinte
    await db.atualizar_rodada(conn, run["id"], cog._passo(run), estado.rodada + 1)
    run = await db.buscar_run(conn, run["id"])
    estado = await cog._estado_combate(run, incursao.objetivo)
    assert estado.combatente(JOGADORES[0]).veneno_no_golpe == 2, "a forma durou"

    # o saco de pancada tem CA 1: o golpe acerta e o veneno entra
    alvo = estado.inimigos[0].indice
    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.atacar(inter, run["id"], "OBJ", alvo)
    estado = await cog._estado_combate(await db.buscar_run(conn, run["id"]),
                                       incursao.objetivo)
    inimigo = estado.inimigo(alvo)
    assert inimigo.penalidade_ataque == 2, inimigo.penalidade_ataque
    # e a penalidade chega na rolagem de verdade
    golpe = motor.contra_atacar(
        inimigo, motor.Combatente(1, "X", 99, 0, "1d1", 50, 50)
    )
    assert golpe.bonus == inimigo.ataque - 2, golpe.bonus
    print("  a mordida da aranha tira 2 do ataque de quem ela acerta: ok")


# ----------------------------------------------------------- o bichinho


async def caso_bichinho_cura_ao_abrir():
    conn, canal, cog, incursao, run = await preparar(
        escolhas={"bichinho_t2": "bichinho_curandeiro"}
    )
    ferido = JOGADORES[1]
    await db.definir_hp(conn, run["id"], ferido, 20)
    estado = await cog._estado_combate(await db.buscar_run(conn, run["id"]),
                                       incursao.objetivo)
    # 3 por tier, no tier 5: 15 de cura ao montar o combate
    assert estado.combatente(ferido).hp_atual == 35, estado.combatente(ferido).hp_atual
    print("  o bichinho curandeiro lambe 15 de ferida ao abrir o combate: ok")


def caso_as_outras_duas_opcoes_do_bichinho():
    morde = cl.efeitos("druida", 9, {"bichinho_t2": "bichinho_mordedor"})
    assert morde["dano_extra"] == 2
    vigia = cl.efeitos("druida", 9, {"bichinho_t2": "bichinho_vigilante"})
    assert vigia["bonus_teste"] == 3
    print("  morde junto soma dano, avisa do perigo soma no teste: ok")


# --------------------------------------------------------------- as magias


async def caso_aura_of_vitality_regenera_o_grupo():
    conn, canal, cog, incursao, run = await preparar(
        escolhas={"magia_druida_t3": "aura_of_vitality"}
    )
    for uid in JOGADORES[:3]:
        await db.definir_hp(conn, run["id"], uid, 30)
    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.usar_habilidade(inter, run["id"], "OBJ", "aura_of_vitality")
    estado = await cog._estado_combate(await db.buscar_run(conn, run["id"]),
                                       incursao.objetivo)
    for c in estado.vivos:
        assert c.cura_por_turno == 0.1, (c.nome, c.cura_por_turno)
    print("  Aura of Vitality liga 10% de regeneracao por rodada no grupo: ok")


async def caso_conjure_animals_traz_o_bando():
    conn, canal, cog, incursao, run = await preparar(
        escolhas={"magia_druida_t3": "conjure_animals"}
    )
    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.usar_habilidade(inter, run["id"], "OBJ", "conjure_animals")
    estado = await cog._estado_combate(await db.buscar_run(conn, run["id"]),
                                       incursao.objetivo)
    bando = next((c for c in estado.combatentes if c.e_invocacao), None)
    assert bando is not None and bando.nome == "Bando selvagem"
    assert bando.hp_max == 35 and bando.dono == JOGADORES[0]
    print("  Conjure Animals usa o aliado conjurado que o bruxo trouxe: ok")


async def caso_antilife_shell_tira_ele_da_mira():
    conn, canal, cog, incursao, run = await preparar(
        escolhas={"magia_druida_t5": "antilife_shell"}
    )
    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.usar_habilidade(inter, run["id"], "OBJ", "antilife_shell")
    estado = await cog._estado_combate(await db.buscar_run(conn, run["id"]),
                                       incursao.objetivo)
    protegido = estado.combatente(JOGADORES[0])
    assert protegido.ameaca_fator == 0.0, protegido.ameaca_fator

    # com fator 0 ele sai da mira de verdade, e os outros absorvem
    rng = random.Random(3)
    conta = collections.Counter(
        motor.sortear_alvo(estado, rng).nome for _ in range(5000)
    )
    assert conta[protegido.nome] == 0, conta
    assert sum(conta.values()) == 5000, "os outros continuam sendo alvo"
    print("  Antilife Shell tira ele da mira por completo, e o grupo absorve: ok")


def caso_antilife_shell_nao_quebra_se_todos_tiverem():
    """Grupo inteiro protegido: a curva cai no uniforme, não em divisão por zero."""
    fatias = ameaca.fracoes([6, 3, 2], [0.0, 0.0, 0.0])
    assert fatias == [1 / 3] * 3, fatias
    print("  grupo todo protegido cai no uniforme, sem dividir por zero: ok")


async def main():
    try:
        caso_tabela_e_o_trade()
        caso_a_forma_dobra_o_dano_e_escala()
        caso_forma_das_classes()
        await caso_urso_troca_o_corpo()
        await caso_lobo_morde_duas_vezes()
        await caso_forma_lunar_dobra_o_thp()
        await caso_aranha_envenena_quem_acerta()
        await caso_bichinho_cura_ao_abrir()
        caso_as_outras_duas_opcoes_do_bichinho()
        await caso_aura_of_vitality_regenera_o_grupo()
        await caso_conjure_animals_traz_o_bando()
        await caso_antilife_shell_tira_ele_da_mira()
        caso_antilife_shell_nao_quebra_se_todos_tiverem()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        (Path(__file__).resolve().parent / "teste_druida.db").unlink(missing_ok=True)


asyncio.run(main())
print("TESTES DO DRUIDA PASSARAM")
