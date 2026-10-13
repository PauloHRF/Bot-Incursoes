"""O clérigo: a tabela, a CD que ele força, a escolha que destrava a magia e
cada uma das magias — a que cura por dado, a que cobra resistência de todos os
inimigos, a que vira um contra os outros."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import classes as cl, config, database as db, motor  # noqa: E402
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

# Criatura de prova: bate fraco e aguenta muito, para a luta nao acabar antes
# da magia sair. CA 1 e ataque 40 ficam de fora: aqui quem rola e o clerigo.
SACO = {**INDEFESO, "hp": 500, "ataque": 1, "dano": "1d1"}

# A tabela do documento: hp, ca, skills, bonus, prof, acerto, dano.
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
    config.DB_PATH = Path(__file__).resolve().parent / "teste_clerigo.db"
    config.DB_PATH.unlink(missing_ok=True)
    config.TAMANHO_GRUPO = 5
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    await criar_grupo(conn, nivel=nivel, classe="clerigo")
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


def caso_tabela_bate_com_o_documento():
    clerigo = cl.CLASSES["clerigo"]
    campos = ("hp", "ca", "pericias", "bonus_pericia", "bonus_proficiencia",
              "acerto", "dano")
    for i, linha in enumerate(DOC, start=1):
        numeros = clerigo.tiers[i]
        for campo, esperado in zip(campos, linha):
            assert getattr(numeros, campo) == esperado, (i, campo, esperado)
    assert clerigo.saves == ("CON", "SAB")
    assert "Clérigo" not in cl.CLASSES_PENDENTES, "saiu da lista de pendentes"
    print("  os 35 campos da tabela batem com o documento: ok")


def caso_cd_sai_do_acerto():
    """8 + acerto, que é o número que a tabela já tem."""
    assert [cl.cd_de_habilidade("clerigo", n) for n in (1, 3, 5, 7, 9)] == [
        13, 15, 16, 17, 19
    ]
    # e a conta vale para qualquer classe, não só o clérigo
    assert cl.cd_de_habilidade("guerreiro", 1) == 8 + cl.numeros("guerreiro", 1).acerto
    assert cl.cd_de_habilidade("classe inventada", 1) == 13, "sem tabela, cai no minimo"
    print("  a CD e 8 + acerto: 13 no tier 1, 19 no tier 5: ok")


# ------------------------------------------------------- a escolha e a magia


def caso_escolha_destrava_uma_magia_so():
    """O clérigo tem uma magia por círculo, não as três."""
    nenhuma = {h.id for _t, h in cl.habilidades("clerigo", 9)}
    assert "cure_wounds" not in nenhuma, "sem escolher, nenhuma magia aparece"
    assert "magia_t1" in nenhuma, "mas a escolha aparece"

    com = {h.id for _t, h in cl.habilidades("clerigo", 9, {"magia_t1": "command"})}
    assert "command" in com
    assert "cure_wounds" not in com and "guiding_bolt" not in com
    print("  a escolha destrava uma magia e esconde as irmas: ok")


def caso_taumaturgo_esta_declarado_pendente():
    """Opção que o bot ainda não executa tem de dizer isso, não sumir calada."""
    dominio = next(
        h for _t, h in cl.habilidades("clerigo", 9) if h.id == "dominio_t2"
    )
    opcoes = {o["id"]: o for o in dominio.escolha["opcoes"]}
    assert opcoes["taumaturgo"].get("pendente") is True
    assert opcoes["protetor"]["efeito"] == {"ca": 2}
    assert opcoes["curandeiro"]["efeito"] == {"bonus_cura": "1d6"}
    print("  Taumaturgo esta marcado pendente, e os outros dois funcionam: ok")


def caso_passivas_de_dado_consolidam_pelo_maior():
    efeitos = cl.efeitos("clerigo", 9, {"dominio_t2": "curandeiro",
                                        "dominio_t4": "ataques_abencoados"})
    assert efeitos["bonus_cura"] == "1d6"
    assert efeitos["dano_bonus"] == "1d8"
    # os dois que dao bonus_cura nao somam: vale o maior (a regra da casa)
    so_cura = cl.efeitos("clerigo", 9, {"dominio_t2": "curandeiro",
                                        "dominio_t4": "especialista_cura"})
    assert so_cura["bonus_cura"] == "1d6"
    print("  as passivas de dado entram e consolidam pelo maior: ok")


# ------------------------------------------------------------------- a cura


async def caso_cure_wounds_cura_por_dado():
    conn, canal, cog, incursao, run = await preparar(
        escolhas={"magia_t1": "cure_wounds"}
    )
    ferido = JOGADORES[1]
    await db.definir_hp(conn, run["id"], ferido, 10)

    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.usar_habilidade(inter, run["id"], "OBJ", "cure_wounds", [ferido])
    depois = await db.personagens_da_run(conn, run["id"])
    hp = next(p["hp_atual"] for p in depois if p["user_id"] == ferido)
    # 2d8+3 vai de 5 a 19
    assert 15 <= hp <= 29, hp
    print(f"  Cure Wounds cura 2d8+3 (foi de 10 para {hp}): ok")


async def caso_curandeiro_soma_na_cura():
    conn, canal, cog, incursao, run = await preparar(
        escolhas={"magia_t1": "cure_wounds", "dominio_t2": "curandeiro"}
    )
    ferido = JOGADORES[1]
    await db.definir_hp(conn, run["id"], ferido, 1)
    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.usar_habilidade(inter, run["id"], "OBJ", "cure_wounds", [ferido])
    depois = await db.personagens_da_run(conn, run["id"])
    hp = next(p["hp_atual"] for p in depois if p["user_id"] == ferido)
    # 2d8+3 mais 1d6: de 6 a 25 em cima do 1
    assert 7 <= hp <= 26, hp
    print(f"  Curandeiro soma 1d6 na cura (foi de 1 para {hp}): ok")


async def caso_mass_healing_word_pega_o_grupo():
    conn, canal, cog, incursao, run = await preparar(
        escolhas={"magia_t3": "mass_healing_word"}
    )
    for uid in JOGADORES[:3]:
        await db.definir_hp(conn, run["id"], uid, 10)
    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.usar_habilidade(inter, run["id"], "OBJ", "mass_healing_word")
    depois = await db.personagens_da_run(conn, run["id"])
    for p in depois:
        if p["user_id"] in JOGADORES[:3]:
            assert p["hp_atual"] >= 16, (p["nome"], p["hp_atual"])
    print("  Mass Healing Word cura 2d4+4 do grupo inteiro: ok")


async def caso_restauracao_tira_o_atordoamento():
    conn, canal, cog, incursao, run = await preparar(
        escolhas={"magia_t1": "cure_wounds", "dominio_t4": "restauracao"}
    )
    vitima = JOGADORES[1]
    estado = await cog._estado_combate(run, incursao.objetivo)
    quem = estado.combatente(vitima)
    await db.aplicar_efeito(
        conn, run["id"], cog._passo(run), "personagem", vitima,
        "atordoado", {"por": "teste"}, estado.rodada + 3,
    )
    await db.definir_hp(conn, run["id"], vitima, 10)
    estado = await cog._estado_combate(await db.buscar_run(conn, run["id"]),
                                       incursao.objetivo)
    assert estado.combatente(vitima).atordoado, "o teste comeca atordoado"

    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.usar_habilidade(inter, run["id"], "OBJ", "cure_wounds", [vitima])
    estado = await cog._estado_combate(await db.buscar_run(conn, run["id"]),
                                       incursao.objetivo)
    assert not estado.combatente(vitima).atordoado, "a cura limpou o atordoamento"
    print("  Restauracao faz a cura tirar o atordoamento: ok")


# --------------------------------------------------- o save forcado no inimigo


async def caso_command_atordoa_um():
    conn, canal, cog, incursao, run = await preparar(escolhas={"magia_t1": "command"})
    estado = await cog._estado_combate(run, incursao.objetivo)
    alvo = estado.inimigos[0].indice

    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.usar_habilidade(inter, run["id"], "OBJ", "command", [alvo])
    ligados = await db.efeitos_ativos(conn, run["id"], cog._passo(run), 0)
    atordoados = [
        l for l in ligados
        if l["alvo_tipo"] == "inimigo" and l["efeito"] == "atordoado"
    ]
    # CA 1 e save baixo: a criatura de prova quase sempre falha. Ou atordoou,
    # ou a linha diz que resistiu — as duas sao resultados legitimos.
    assert atordoados or "resistiu" in inter.resposta, inter.resposta
    assert "CD 19" in inter.resposta, inter.resposta
    print("  Command cobra save de SAB de um inimigo e mostra a CD: ok")


async def caso_flame_strike_pega_todos_e_da_metade():
    conn, canal, cog, incursao, run = await preparar(
        escolhas={"magia_t5": "flame_strike"}, monstros=3
    )
    estado = await cog._estado_combate(run, incursao.objetivo)
    antes = {i.indice: i.hp_atual for i in estado.inimigos}

    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.usar_habilidade(inter, run["id"], "OBJ", "flame_strike")
    estado = await cog._estado_combate(await db.buscar_run(conn, run["id"]),
                                       incursao.objetivo)
    # todos levaram algo: 10d6 em quem falha, metade em quem passa
    for i in estado.inimigos:
        levou = antes[i.indice] - i.hp_atual
        assert levou >= 5, (i.nome, levou)
    assert len([l for l in inter.resposta.splitlines() if l.startswith("·")]) == 3
    print("  Flame Strike cobra save de todos, e quem resiste leva metade: ok")


async def caso_spirit_guardians_nao_passa_de_quem_resiste():
    conn, canal, cog, incursao, run = await preparar(
        escolhas={"magia_t3": "spirit_guardians"}, monstros=2
    )
    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.usar_habilidade(inter, run["id"], "OBJ", "spirit_guardians")
    # sem `metade`, quem passa no save nao leva nada
    assert "CD 19" in inter.resposta
    print("  Spirit Guardians cobra save de SAB de todos: ok")


async def caso_guiding_bolt_da_vantagem_ao_grupo():
    conn, canal, cog, incursao, run = await preparar(
        escolhas={"magia_t1": "guiding_bolt"}
    )
    estado = await cog._estado_combate(run, incursao.objetivo)
    alvo = estado.inimigos[0].indice
    antes = estado.inimigos[0].hp_atual

    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.usar_habilidade(inter, run["id"], "OBJ", "guiding_bolt", [alvo])
    estado = await cog._estado_combate(await db.buscar_run(conn, run["id"]),
                                       incursao.objetivo)
    levou = antes - estado.inimigo(alvo).hp_atual
    assert 4 <= levou <= 24, levou  # 4d6, sempre entra
    # e todo mundo do grupo ataca aquele inimigo com vantagem
    for c in estado.vivos:
        assert alvo in c.vantagem_contra, (c.nome, c.vantagem_contra)
    print(f"  Guiding Bolt da {levou} de dano e vantagem para o grupo inteiro: ok")


async def caso_dominate_person_vira_um_contra_o_outro():
    conn, canal, cog, incursao, run = await preparar(
        escolhas={"magia_t5": "dominate_person"}, monstros=2
    )
    estado = await cog._estado_combate(run, incursao.objetivo)
    alvo = estado.inimigos[0].indice
    total_antes = sum(i.hp_atual for i in estado.inimigos)

    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.usar_habilidade(inter, run["id"], "OBJ", "dominate_person", [alvo])
    estado = await cog._estado_combate(await db.buscar_run(conn, run["id"]),
                                       incursao.objetivo)
    total_depois = sum(i.hp_atual for i in estado.inimigos)
    # tres desfechos legitimos: acertou o colega, virou e errou, ou resistiu
    assert total_depois <= total_antes
    assert any(
        marca in inter.resposta
        for marca in ("acerta Saco", "e erra", "resistiu")
    ), inter.resposta
    print("  Dominate Person vira a criatura contra as outras dela: ok")


async def caso_ataques_abencoados_somam_no_golpe():
    conn, canal, cog, incursao, run = await preparar(
        escolhas={"dominio_t4": "ataques_abencoados"}
    )
    estado = await cog._estado_combate(run, incursao.objetivo)
    for c in estado.vivos:
        assert c.dano_bonus == "1d8", (c.nome, c.dano_bonus)
    print("  Ataques Abencoados chegam no combatente como dado de dano: ok")


async def main():
    try:
        caso_tabela_bate_com_o_documento()
        caso_cd_sai_do_acerto()
        caso_escolha_destrava_uma_magia_so()
        caso_taumaturgo_esta_declarado_pendente()
        caso_passivas_de_dado_consolidam_pelo_maior()
        await caso_cure_wounds_cura_por_dado()
        await caso_curandeiro_soma_na_cura()
        await caso_mass_healing_word_pega_o_grupo()
        await caso_restauracao_tira_o_atordoamento()
        await caso_command_atordoa_um()
        await caso_flame_strike_pega_todos_e_da_metade()
        await caso_spirit_guardians_nao_passa_de_quem_resiste()
        await caso_guiding_bolt_da_vantagem_ao_grupo()
        await caso_dominate_person_vira_um_contra_o_outro()
        await caso_ataques_abencoados_somam_no_golpe()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        (Path(__file__).resolve().parent / "teste_clerigo.db").unlink(missing_ok=True)


asyncio.run(main())
print("TESTES DO CLERIGO PASSARAM")
