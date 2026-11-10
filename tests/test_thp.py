"""Vida temporária: absorve dano, não empilha, e as habilidades que a dão."""
from __future__ import annotations

import asyncio
import random
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import (  # noqa: E402
    classes as cl, config, database as db, embeds as E, itens, motor,
)
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

DURADOURO = {**INDEFESO, "hp": 4000}
# Bate uma vez por rodada, forte o bastante para derrubar quem tem pouco HP.
CERTEIRO = {"nome": "Martelo", "ca": 1, "ataque": 40, "dano": "1d1+29", "hp": 4000}
# Nao acerta um GOLPE nem por sorte (`ataque: -20` contra qualquer CA), e mata
# pela HABILIDADE, com save que ninguem passa. E esse `ataque: -20` que faz o
# caso provar o que diz: o unico dano possivel aqui vem da habilidade.
FULMINADOR = {
    "nome": "Fulminador", "ca": 1, "ataque": -20, "dano": "1d1", "hp": 4000,
    "habilidade": {
        "nome": "Palavra Final", "save": "CON", "cd": 99,
        "dano": "1d1+998", "alvos": 1, "cada": 1,
    },
}


async def preparar(
    classe="xama", nivel=8, monstro=DURADOURO, quantos=2, escolhas=None
):
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass
    config.DB_PATH = Path(__file__).resolve().parent / "teste_thp.db"
    config.DB_PATH.unlink(missing_ok=True)
    config.TAMANHO_GRUPO = 5
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    await criar_grupo(conn, nivel=nivel, classe=classe)
    canal = FakeCanal(CANAL)
    cog = Incursoes(FakeBot(conn, canal))
    incursao, _ = montar_conteudo(
        cog, tamanho="Curta", monstro_objetivo=monstro, salas=salas_sem_combate()
    )
    run_id = await db.criar_run(conn, GUILD, CANAL, incursao.id, JOGADORES[0])
    for user_id in JOGADORES[:quantos]:
        personagem = await db.personagem_por_nome(conn, GUILD, user_id, f"Heroi{user_id}")
        await db.adicionar_participante(conn, run_id, user_id, personagem["id"])
        for chave, opcao in (escolhas or {}).items():
            await db.definir_escolha(conn, personagem["id"], chave, opcao)
    await db.inicializar_hp(conn, run_id)
    await db.atualizar_run(
        conn, run_id, status="objetivo", sala_atual="OBJ", linha_atual=incursao.passos + 1
    )
    run = await db.buscar_run(conn, run_id)
    await cog._abrir_combate(run, incursao.objetivo)
    return conn, canal, cog, incursao, await db.buscar_run(conn, run_id)


def caso_thp_absorve_antes_do_hp():
    c = motor.Combatente(1, "C", 15, 0, "1d1", 40, 40)
    assert motor.ganhar_thp(c, 10) == 10 and c.tem_thp

    # o dano come a vida temporaria primeiro
    do_thp, do_hp = motor.absorver(c, 4)
    assert (do_thp, do_hp) == (4, 0) and c.thp == 6 and c.hp_atual == 40
    # e so o que sobra vai para o HP
    do_thp, do_hp = motor.absorver(c, 10)
    assert (do_thp, do_hp) == (6, 4) and c.thp == 0 and c.hp_atual == 36

    # empilha: soma na que ja havia (a regra do Espirito Guardiao)
    motor.ganhar_thp(c, 5)
    motor.ganhar_thp(c, 3)
    assert c.thp == 8
    motor.ganhar_thp(c, 9)
    assert c.thp == 17

    # quem caiu nao ganha vida temporaria
    caido = motor.Combatente(2, "X", 15, 0, "1d1", 40, 0)
    assert motor.ganhar_thp(caido, 10) == 0
    print("  THP absorve o dano antes do HP e empilha: ok")


def caso_golpe_registra_o_absorvido():
    bruto = motor.Inimigo(0, "Bruto", 10, 40, "1d1+9", 100, 100)
    alvo = motor.Combatente(1, "A", 10, 0, "1d1", 50, 50, thp=30)
    golpe = motor.contra_atacar(bruto, alvo, random.Random(1))
    assert golpe.acertou and golpe.absorvido == golpe.dano
    assert alvo.hp_atual == 50, "com THP suficiente, o HP nao e tocado"
    assert alvo.thp == 30 - golpe.dano
    print("  o golpe diz quanto a vida temporaria segurou: ok")


async def caso_tradicao_marcial_da_thp():
    conn, canal, cog, incursao, run = await preparar(classe="xama", nivel=8)
    dono = JOGADORES[0]

    inter = FakeInteraction(canal, dono)
    await cog.usar_habilidade(inter, run["id"], "OBJ", "tradicao_marcial")
    assert "Vida temporaria" in leu(inter), leu(inter)

    estado = await cog._estado_combate(await db.buscar_run(conn, run["id"]), incursao.objetivo)
    assert estado.combatente(dono).tem_thp

    # os dois caminhos dividem o mesmo uso: o outro ja nao esta disponivel
    outro = FakeInteraction(canal, dono)
    await cog.usar_habilidade(outro, run["id"], "OBJ", "tradicao_espiritual")
    assert "nao esta disponivel" in leu(outro), leu(outro)
    print("  Tradicao xamanica: caminho marcial rende THP e gasta o uso dos dois: ok")


async def caso_danca_totemica_cobre_o_grupo():
    conn, canal, cog, incursao, run = await preparar(classe="xama", nivel=8)
    dono = JOGADORES[0]
    # Alguem ferido, para a cura de 1% ter onde entrar.
    ferido = JOGADORES[1]
    await db.definir_hp(conn, run["id"], ferido, 10)

    inter = FakeInteraction(canal, dono)
    await cog.usar_habilidade(inter, run["id"], "OBJ", "danca_totemica")
    assert "vida temporaria para o grupo" in leu(inter), leu(inter)
    # A cura e simbolica, mas sai no texto e entra no HP: 1% com piso de 1 da
    # exatamente 1 de vida em qualquer tier do jogo.
    assert "1%" in leu(inter), leu(inter)
    hp = (await db.hp_dos_participantes(conn, run["id"]))[ferido]
    assert hp == 11, hp

    estado = await cog._estado_combate(await db.buscar_run(conn, run["id"]), incursao.objetivo)
    assert all(c.tem_thp for c in estado.vivos), [c.thp for c in estado.vivos]
    # e o bonus de dano chega mesmo no combatente, nao so na tabela de efeitos
    assert all(c.dano_bonus == "1d6+4" for c in estado.vivos), [
        c.dano_bonus for c in estado.vivos
    ]
    # So a Danca: `run_efeitos` guarda tambem a ameaca que o barbaro gerou ao
    # usar a habilidade, que nao e um buff no grupo.
    ligados = [
        l for l in await db.efeitos_ativos(conn, run["id"], cog._passo(run), 0)
        if l["efeito"] == "danca_totemica"
    ]
    assert len(ligados) == len(estado.vivos), ligados
    print("  Danca totemica cura 1%, da THP e bonus de dano ao grupo: ok")


def caso_a_porcentagem_de_cura_arredonda_certo():
    """0.35 + 0.10 e 0.44999999999999996 em float: truncar mostraria 44%."""
    assert round((0.35 + 0.10) * 100) == 45
    assert int((0.35 + 0.10) * 100) == 44, "a armadilha que o round evita"
    assert round(0.01 * 100) == 1
    print("  a cura de 45% nao aparece como 44% por causa do float: ok")


async def caso_aura_totemica_depende_do_thp():
    conn, canal, cog, incursao, run = await preparar(classe="xama", nivel=8)
    dono, colega = JOGADORES[0], JOGADORES[1]

    base = await cog._estado_combate(run, incursao.objetivo)
    acerto_base = base.combatente(colega).bonus_ataque

    # sem THP no xama, ninguem ganha nada
    assert not base.combatente(dono).tem_thp
    assert acerto_base == cl.classe("xama").numeros(8).acerto

    # com THP, a aura liga para o grupo inteiro
    await db.definir_thp(conn, run["id"], dono, 5)
    com_aura = await cog._estado_combate(
        await db.buscar_run(conn, run["id"]), incursao.objetivo
    )
    assert com_aura.combatente(colega).bonus_ataque == acerto_base + 1
    assert com_aura.combatente(dono).bonus_ataque == acerto_base + 1

    # no tier 5 a aura e mais forte
    for user_id in (dono, colega):
        personagem = await db.personagem_por_nome(conn, GUILD, user_id, f"Heroi{user_id}")
        await db.atualizar_personagem(conn, personagem["id"], "nivel", 10)
    await db.definir_thp(conn, run["id"], dono, 5)
    forte = await cog._estado_combate(
        await db.buscar_run(conn, run["id"]), incursao.objetivo
    )
    assert forte.combatente(colega).bonus_ataque == cl.classe("xama").numeros(10).acerto + 2
    print("  a aura totemica so vale enquanto o xama tem THP: ok")


async def caso_relentless_segura_a_queda():
    conn, canal, cog, incursao, run = await preparar(
        classe="barbaro", nivel=8, monstro=CERTEIRO
    )
    passo = cog._passo(run)
    # deixa os dois na beira da morte: o revide derruba
    for user_id in JOGADORES[:2]:
        await db.definir_hp(conn, run["id"], user_id, 1)

    # o monstro erra com 1 natural, entao damos algumas rodadas
    msg = await canal.fetch_message(run["mensagem_id"])
    salvo = None
    for _ in range(6):
        atual = await db.buscar_run(conn, run["id"])
        if atual["status"] != "objetivo":
            break
        estado = await cog._estado_combate(atual, incursao.objetivo)
        for c in list(estado.vivos):
            await cog.atacar(FakeInteraction(canal, c.user_id, msg), run["id"], "OBJ")
        async with conn.execute(
            "SELECT user_id, thp FROM run_participantes WHERE run_id = ? AND thp > 0",
            (run["id"],),
        ) as cur:
            linha = await cur.fetchone()
        if linha:
            salvo = linha["user_id"]
            break
        for user_id in JOGADORES[:2]:
            await db.definir_hp(conn, run["id"], user_id, 1)

    assert salvo is not None, "Relentless tinha de ter segurado alguem"
    hps = await db.hp_dos_participantes(conn, run["id"])
    assert hps[salvo] >= 1, hps
    # `enviadas`, nao `mensagens`: a narracao da rodada passada e apagada
    # ao virar a rodada. A pergunta aqui e se o grupo foi avisado.
    assert any("Relentless" in (m.content or "") for m in canal.enviadas)

    # e o uso acabou: e 1x por combate
    gastos = await db.usos_da_run(conn, run["id"], salvo)
    assert gastos.get(("relentless", f"combate:{passo}")) == 1, gastos
    print("  Relentless segura a queda uma vez por combate: ok")


async def caso_relentless_segura_a_queda_de_habilidade_tambem():
    """Relentless dispara por chegar a zero — não importa o que levou até lá.

    As reações do turno da criatura recebiam só `feito.golpes`. As habilidades
    dela viram `feito.investidas`, e nunca chegavam lá: o bárbaro se recusava a
    cair quando a criatura **batia** nele e ficava no chão quando ela o matava
    com a habilidade — que é justamente o golpe mais pesado que ela tem.

    O `caso_relentless_segura_a_queda` cobre o golpe comum, e é por isso que o
    bug passou: aquele monstro não tem habilidade nenhuma. Aqui o `ataque: -20`
    do Fulminador garante que nenhum golpe dele acerta, então a única coisa
    capaz de derrubar alguém é a habilidade.

    A esquiva (Uncanny Dodge) continua só contra golpe de propósito: ela corta
    um ataque que se vê vir, não uma explosão em que se falhou a resistência.
    """
    conn, canal, cog, incursao, run = await preparar(
        classe="barbaro", nivel=8, monstro=FULMINADOR
    )
    passo = cog._passo(run)
    for user_id in JOGADORES[:2]:
        await db.definir_hp(conn, run["id"], user_id, 1)

    msg = await canal.fetch_message(run["mensagem_id"])
    estado = await cog._estado_combate(
        await db.buscar_run(conn, run["id"]), incursao.objetivo
    )
    for c in list(estado.vivos):
        await cog.atacar(FakeInteraction(canal, c.user_id, msg), run["id"], "OBJ")

    def no_painel(texto: str) -> bool:
        """O log das rodadas vive nos CAMPOS do painel, nao no conteudo."""
        return any(
            texto in (campo.value or "")
            for mensagem in canal.mensagens
            for embed in (getattr(mensagem, "embeds", []) or [])
            for campo in embed.fields
        )

    # A habilidade saiu, e e dela que o dano veio. Sem esta linha o caso
    # passaria vazio no dia em que a criatura parasse de usar a habilidade.
    assert no_painel("Palavra Final"), (
        "a habilidade da criatura nao resolveu: o caso nao prova nada"
    )
    assert any("Relentless" in (m.content or "") for m in canal.enviadas), (
        "a habilidade derrubou e Relentless nao disparou"
    )
    async with conn.execute(
        "SELECT user_id, hp_atual, thp FROM run_participantes"
        " WHERE run_id = ? AND thp > 0",
        (run["id"],),
    ) as cur:
        salvos = [dict(r) for r in await cur.fetchall()]
    assert len(salvos) == 1, f"esperava um salvo com THP, e vieram {salvos}"
    assert salvos[0]["hp_atual"] >= 1, salvos
    # E gastou o uso: continua sendo 1x por combate.
    gastos = await db.usos_da_run(conn, run["id"], salvos[0]["user_id"])
    assert gastos.get(("relentless", f"combate:{passo}")) == 1, gastos

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  Relentless segura a queda vinda de habilidade tambem: ok")


async def caso_a_armadura_da_thp_a_quem_recebe_a_cura():
    """A Túnica Acolchoada rende THP em QUEM A VESTE, ao ser curado.

    Ela prometia *"+2 de vida temporária ao ser curado"* e não fazia nada em
    quem a vestia: o bônus era lido dos efeitos de **quem curava**. Com a
    túnica no clérigo, o aliado curado é que ganhava os 2.

    E não era alvo trocado, era uma chave com dois significados. O
    `thp_na_cura` é o **Cântico Benevolente** do xamã — *"curar dá +4 de THP
    ao alvo"* —, que sai de quem cura e está certo assim. As armaduras querem
    o oposto, e passaram a ter chave própria, `thp_ao_ser_curado`, lida de
    quem recebe. Cinco armaduras tinham a linha de stat inteira sem efeito.
    """
    conn, canal, cog, incursao, run = await preparar(
        classe="clerigo", nivel=8, escolhas={"magia_t1": "cure_wounds"}
    )
    curador, ferido = JOGADORES[0], JOGADORES[1]
    pids = {
        u: (await db.personagem_por_nome(conn, GUILD, u, f"Heroi{u}"))["id"]
        for u in (curador, ferido)
    }

    async def vestir(user_id, item_id):
        """Veste, e com isso TIRA o que estava no slot: armadura e um slot só."""
        await db.dar_item(conn, pids[user_id], item_id)
        await db.equipar(conn, pids[user_id], item_id, itens.item(item_id).slot)

    async def thp_de(user_id):
        async with conn.execute(
            "SELECT thp FROM run_participantes WHERE run_id = ? AND user_id = ?",
            (run["id"], user_id),
        ) as cur:
            return (await cur.fetchone())["thp"]

    async def curar(alvo, hp_antes=5):
        # O HP entra ANTES de montar o estado: o combatente e lido do banco, e
        # com ele cheio a cura seria zero e o caso nao provaria nada.
        await db.definir_hp(conn, run["id"], alvo, hp_antes)
        await db.definir_thp(conn, run["id"], alvo, 0)
        atual = await db.buscar_run(conn, run["id"])
        estado = await cog._estado_combate(atual, incursao.objetivo)
        quem = await cog._personagem_na_run(atual, curador)
        hab = next(h for _t, h in quem["habilidades"] if h.id == "cure_wounds")
        await cog._resolver_cura(atual, curador, hab, hab.acao, [alvo], estado)
        return await thp_de(alvo)

    # 1) A tunica em QUEM RECEBE: e ela que rende.
    await vestir(ferido, "tunica_acolchoada")
    assert await curar(ferido) == 2, "a tunica nao rendeu em quem a veste"

    # 2) A tunica so em QUEM CURA nao rende nada ao aliado: trocar o gibao
    #    pelo peito do ferido tira a tunica dele (um slot, uma peca).
    await vestir(ferido, "gibao_de_couro")
    await vestir(curador, "tunica_acolchoada")
    assert await curar(ferido) == 0, (
        "a tunica de quem cura voltou a dar THP ao aliado"
    )

    # 3) Curar a si mesmo tambem e ser curado: nao tem o `!= user_id` que o
    #    Cantico tem, porque o texto da armadura nao fala de quem curou.
    assert await curar(curador) == 2, "a tunica nao rendeu na cura em si mesmo"

    # 4) Mas so quando a cura ACONTECE: de HP cheio nao sai THP de graca.
    cheio = (await cog._personagem_na_run(run, curador))["numeros"].hp
    assert await curar(curador, hp_antes=cheio) == 0, (
        "rendeu THP numa cura que nao curou ninguem"
    )

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  a armadura rende THP em quem RECEBE a cura: ok")


async def caso_thp_some_no_proximo_combate():
    conn, canal, cog, incursao, run = await preparar(classe="xama", nivel=8)
    dono = JOGADORES[0]
    await db.definir_thp(conn, run["id"], dono, 12)

    # o combate seguinte (outro passo) comeca sem vida temporaria
    await db.iniciar_combate(conn, run["id"], 99, "OUTRA", [incursao.objetivo.monstros[0]])
    async with conn.execute(
        "SELECT thp FROM run_participantes WHERE run_id = ? AND user_id = ?",
        (run["id"], dono),
    ) as cur:
        assert (await cur.fetchone())["thp"] == 0
    print("  a vida temporaria nao atravessa combates: ok")


def caso_painel_mostra_thp():
    c = motor.Combatente(1, "Vhalor", 15, 0, "1d1", 40, 30, thp=7)
    linha = E._linha_hp(c)
    assert "30/40" in linha and "+7 THP" in linha, linha
    sem = motor.Combatente(2, "Kaelen", 15, 0, "1d1", 40, 30)
    assert "THP" not in E._linha_hp(sem)
    print("  o painel mostra a vida temporaria: ok")


async def main():
    try:
        caso_thp_absorve_antes_do_hp()
        caso_golpe_registra_o_absorvido()
        caso_painel_mostra_thp()
        await caso_tradicao_marcial_da_thp()
        await caso_danca_totemica_cobre_o_grupo()
        caso_a_porcentagem_de_cura_arredonda_certo()
        await caso_aura_totemica_depende_do_thp()
        await caso_relentless_segura_a_queda()
        await caso_relentless_segura_a_queda_de_habilidade_tambem()
        await caso_a_armadura_da_thp_a_quem_recebe_a_cura()
        await caso_thp_some_no_proximo_combate()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        (Path(__file__).resolve().parent / "teste_thp.db").unlink(missing_ok=True)


asyncio.run(main())
print("TESTES DE THP PASSARAM")
