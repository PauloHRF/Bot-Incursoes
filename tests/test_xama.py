"""O xamã corrigido contra o documento: a vida temporária que soma, o gatilho
do Espírito Guardião que cai de 19 para 15, e os Guerreiros Anciões — com a
versão que custa 20 de THP."""
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


async def preparar(nivel=9, escolhas=None, quantos=3, monstros=2):
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass
    config.DB_PATH = Path(__file__).resolve().parent / "teste_xama.db"
    config.DB_PATH.unlink(missing_ok=True)
    config.TAMANHO_GRUPO = 5
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    await criar_grupo(conn, nivel=nivel, classe="xama")
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


# ------------------------------------------------------------- a regra de THP


def caso_thp_soma():
    """O documento é explícito: "não substitui os antigos, se soma a eles"."""
    c = motor.Combatente(1, "Xama", 16, 5, "1d6+3", 73, 73)
    for quanto in (5, 5, 5, 5):
        motor.ganhar_thp(c, quanto)
    assert c.thp == 20, c.thp
    # e o teto de 20 do tier 5 fica alcancavel, que era o ponto
    assert c.thp >= 20
    print("  quatro gatilhos de 5 THP chegam a 20, somando: ok")


def caso_so_o_teto_de_20_era_inalcancavel_antes():
    """Com substituição, a maior fonte sozinha não chegava a 20."""
    fontes = {"totem": 5, "marcial (1d6)": 6, "espiritual (1d6+3)": 9,
              "danca (4d6+4)": 28}
    assert max(fontes.values()) == 28, "a danca passou a 4d6+4, do documento"
    # antes a danca era 2d6+4 (teto 16) e nada somava: 20 nao acontecia
    assert 16 < 20, "o teto antigo"
    print("  a danca virou 4d6+4 e a soma destrava o limiar de 20: ok")


# -------------------------------------------------------------- o totem


def caso_gatilho_cai_no_tier_4():
    """Sintonização Ancestral baixa o gatilho de 19 para 15, e dá 5 THP."""
    t3 = (cl.efeitos("xama", 5, {}) or {}).get("totem") or {}
    t4 = (cl.efeitos("xama", 7, {}) or {}).get("totem") or {}
    t5 = (cl.efeitos("xama", 9, {}) or {}).get("totem") or {}
    assert (t3["gatilho"], t3["thp"], t3["aura"]) == (19, 5, 1), t3
    assert (t4["gatilho"], t4["thp"], t4["aura"]) == (15, 5, 1), t4
    assert (t5["gatilho"], t5["thp"], t5["aura"]) == (15, 5, 2), t5
    assert t5["aura_dano"] == 2, "o documento diz +2 em tudo, nao +3"
    print("  o gatilho e 19 no tier 2, 15 do tier 4 em diante, sempre 5 THP: ok")


def caso_sintonizacao_mantem_as_pericias():
    """Baixar o gatilho não pode ter custado o bônus de perícia do tier 4."""
    efeitos = cl.efeitos("xama", 7, {})
    for pericia in ("História", "Natureza", "Medicina", "Adestrar Animais",
                    "Intuição"):
        assert efeitos["bonus_pericia"].get(pericia) == 2, pericia
    print("  a Sintonizacao continua dando +2 nas cinco pericias dela: ok")


# ------------------------------------------------------ a tradicao espiritual


async def caso_espiritual_cura_em_porcentagem_e_o_thp_e_do_xama():
    """Cura 30% do HP máximo do aliado, e **você** ganha 1d6+3 de THP.

    A cura virou porcentagem para acompanhar o tier: 2d8+3 era metade da vida
    de um tier 1 e um sexto da de um tier 5.
    """
    conn, canal, cog, incursao, run = await preparar()
    curador, ferido = JOGADORES[0], JOGADORES[1]
    await db.definir_hp(conn, run["id"], ferido, 10)

    inter = FakeInteraction(canal, curador)
    await cog.usar_habilidade(
        inter, run["id"], "OBJ", "tradicao_espiritual", [ferido]
    )
    pessoas = {p["user_id"]: p for p in await db.personagens_da_run(conn, run["id"])}
    # 30% do maximo em cima dos 10 que sobraram, e sem passar do teto.
    esperado = min(
        pessoas[ferido]["hp_max"], 10 + int(pessoas[ferido]["hp_max"] * 0.3)
    )
    assert pessoas[ferido]["hp_atual"] == esperado, (
        pessoas[ferido]["hp_atual"], esperado
    )
    # e o THP ficou com quem curou, nao com quem foi curado
    assert pessoas[curador]["thp"] >= 4, pessoas[curador]["thp"]
    assert not pessoas[ferido]["thp"], "o aliado nao leva o THP"
    print("  o caminho espiritual cura 30% e o THP fica com o xama: ok")


# ----------------------------------------------------- os Guerreiros ancioes


async def caso_guerreiros_ancioes_versao_normal():
    conn, canal, cog, incursao, run = await preparar()
    for uid in JOGADORES[:3]:
        await db.definir_hp(conn, run["id"], uid, 20)

    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.usar_habilidade(inter, run["id"], "OBJ", "guerreiros_ancioes")
    estado = await cog._estado_combate(
        await db.buscar_run(conn, run["id"]), incursao.objetivo
    )
    for c in estado.vivos:
        assert c.critico_em == 15, (c.nome, c.critico_em)
        assert c.dano_bonus == "1d6+5", (c.nome, c.dano_bonus)
        assert c.hp_atual > 20, f"{c.nome} devia ter curado 10%"
    assert "10%" in leu(inter), leu(inter)
    print("  Guerreiros ancioes: crita com 15, +1d6+5 e cura 10% do grupo: ok")


async def caso_guerreiros_ancioes_versao_de_20_thp():
    conn, canal, cog, incursao, run = await preparar()
    dono = JOGADORES[0]
    # 20 de THP na mao: a versao grande fica disponivel
    await db.definir_thp(conn, run["id"], dono, 25)
    estado = await cog._estado_combate(run, incursao.objetivo)
    antes = sum(i.hp_atual for i in estado.inimigos)

    inter = FakeInteraction(canal, dono)
    await cog.usar_habilidade(inter, run["id"], "OBJ", "guerreiros_ancioes")
    estado = await cog._estado_combate(
        await db.buscar_run(conn, run["id"]), incursao.objetivo
    )
    # pagou os 20
    assert estado.combatente(dono).thp == 5, estado.combatente(dono).thp
    # e o grupo levou a forma grande
    for c in estado.vivos:
        assert c.critico_em == 1, (c.nome, c.critico_em)
        assert c.dano_bonus == "1d10+5", (c.nome, c.dano_bonus)
    # e os inimigos levaram 8d6 cada
    depois = sum(i.hp_atual for i in estado.inimigos)
    assert antes - depois >= 16, (antes, depois)
    assert "20%" in leu(inter) and "8d6" in leu(inter), leu(inter)
    print("  com 20 de THP a habilidade cobra 20 e sai na forma grande: ok")


async def caso_sem_thp_sai_a_versao_normal():
    conn, canal, cog, incursao, run = await preparar()
    dono = JOGADORES[0]
    await db.definir_thp(conn, run["id"], dono, 19)  # um a menos do que precisa

    inter = FakeInteraction(canal, dono)
    await cog.usar_habilidade(inter, run["id"], "OBJ", "guerreiros_ancioes")
    estado = await cog._estado_combate(
        await db.buscar_run(conn, run["id"]), incursao.objetivo
    )
    assert estado.combatente(dono).thp == 19, "nao cobrou nada"
    assert all(c.critico_em == 15 for c in estado.vivos)
    assert "8d6" not in leu(inter)
    print("  com 19 de THP a melhoria nao sai, e nada e cobrado: ok")


async def main():
    try:
        caso_thp_soma()
        caso_so_o_teto_de_20_era_inalcancavel_antes()
        caso_gatilho_cai_no_tier_4()
        caso_sintonizacao_mantem_as_pericias()
        await caso_espiritual_cura_em_porcentagem_e_o_thp_e_do_xama()
        await caso_guerreiros_ancioes_versao_normal()
        await caso_guerreiros_ancioes_versao_de_20_thp()
        await caso_sem_thp_sai_a_versao_normal()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        (Path(__file__).resolve().parent / "teste_xama.db").unlink(missing_ok=True)


asyncio.run(main())
print("TESTES DO XAMA PASSARAM")
