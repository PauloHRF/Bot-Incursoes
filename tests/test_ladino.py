"""O Ladino: Marca Fatal, a explosão na terceira marca e a Furtividade."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import (  # noqa: E402
    classes as cl,
    config,
    database as db,
    habilidades as hb,
)
from src.cogs.incursao import Incursoes  # noqa: E402
from fakes import (  # noqa: E402
    CANAL,
    GUILD,
    JOGADORES,
    FakeBot,
    FakeCanal,
    FakeInteraction,
    criar_grupo,
    iniciativa_de_verdade,
    montar_conteudo,
    salas_sem_combate,
)

_ABERTAS = []
BANCO = Path(__file__).resolve().parent / "teste_ladino.db"

# Aguenta o combate inteiro sem machucar ninguém: o caso é sobre as marcas,
# não sobre sobreviver. HP alto para a explosão nunca derrubá-lo.
BONECO = {"nome": "Boneco", "ca": 1, "ataque": -20, "dano": "1d1", "hp": 9000}


def ordem_fixa(*quem):
    """Fixa a ordem do combate: ("p", user_id) ou ("i", indice)."""
    from src import motor

    def rolar(estado, rng=None):
        ordem = []
        for posicao, (tipo, ident) in enumerate(quem):
            if tipo == "p":
                nome = estado.combatente(ident).nome
                ordem.append(
                    motor.Iniciativa(motor.PERSONAGEM, ident, nome, 20 - posicao, 0)
                )
            else:
                nome = estado.inimigo(ident).nome
                ordem.append(
                    motor.Iniciativa(motor.INIMIGO, ident, nome, 20 - posicao, 0)
                )
        return ordem

    motor.rolar_iniciativas = rolar


async def preparar(nivel=3, quantos=1, inimigos=1):
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
    await criar_grupo(conn, nivel=nivel, classe="ladino")
    canal = FakeCanal(CANAL)
    cog = Incursoes(FakeBot(conn, canal))
    incursao, _ = montar_conteudo(
        cog, tamanho="Curta", monstro_objetivo=BONECO,
        inimigos_objetivo=inimigos, salas=salas_sem_combate(),
    )
    run_id = await db.criar_run(conn, GUILD, CANAL, incursao.id, JOGADORES[0])
    for user_id in JOGADORES[:quantos]:
        personagem = await db.personagem_por_nome(
            conn, GUILD, user_id, f"Heroi{user_id}"
        )
        await db.adicionar_participante(conn, run_id, user_id, personagem["id"])
    await db.inicializar_hp(conn, run_id)
    run = await db.buscar_run(conn, run_id)
    await db.atualizar_run(conn, run_id, status="objetivo", sala_atual=incursao.objetivo.id)
    run = await db.buscar_run(conn, run_id)
    await cog._abrir_combate(run, incursao.objetivo)
    return conn, canal, cog, incursao, await db.buscar_run(conn, run_id)


async def marcas_em(cog, run, incursao, indice=0):
    """Quantas Marcas Fatais o inimigo carrega agora."""
    estado = await cog._estado_combate(run, incursao.objetivo)
    vivas = await cog._marcas_de(run, estado.rodada)
    return (vivas.get(indice, {}).get("valor") or {}).get("marcas", 0)


def caso_a_ficha_bate_com_o_documento():
    """Os números e as habilidades do Ladino, tier por tier.

    É a ficha que o grupo escreveu: HP de 17 a 73 subindo 14 por tier, 6
    perícias em todos, e as cinco habilidades na ordem. Um teste de
    conteúdo, para o rework não se desfazer sem ninguém notar.
    """
    c = cl.CLASSES["ladino"]
    esperado = {
        1: (17, 15, 5, "2d6+3"),
        2: (31, 16, 6, "3d6+4"),
        3: (45, 16, 7, "4d6+4"),
        4: (59, 17, 8, "5d6+5"),
        5: (73, 18, 10, "6d6+5"),
    }
    for t, (hp, ca, acerto, dano) in esperado.items():
        n = c.numeros(t * 2 - 1)
        assert (n.hp, n.ca, n.acerto, n.dano) == (hp, ca, acerto, dano), (t, n)
        assert n.pericias == 6, (t, n.pericias)

    ordem = [
        [h.id for h in c.habilidades_do_tier(t)] for t in range(1, 6)
    ]
    assert ordem == [
        ["reliable_talent"], ["marca_fatal"], ["furtividade"],
        ["expertise_2"], ["marca_fatal_mais"],
    ], ordem

    # O dado da explosão sai da tabela da ficha dele.
    assert hb.DANO_DA_MARCA == {1: "1d6", 2: "1d6", 3: "2d6", 4: "2d6", 5: "3d6"}
    assert hb.MARCAS_PARA_EXPLODIR == 3 and hb.TURNOS_DA_MARCA == 3
    print("  a ficha do Ladino bate com o documento: ok")


async def caso_a_marca_empilha_e_explode_na_terceira():
    """Acertar marca; a terceira marca explode na hora, sem rolar acerto."""
    ordem_fixa(("p", JOGADORES[0]), ("i", 0))
    conn, canal, cog, incursao, run = await preparar(nivel=3)
    msg = await canal.fetch_message(run["mensagem_id"])

    # Ataca até as três marcas fecharem. A CA do boneco é 1, então só o 1
    # natural erra — e ele sai, de vez em quando. O caso é sobre a marca, e
    # não sobre a rolagem de acerto: errar não marca, e só isso.
    vistas = []
    for _ in range(20):
        inter = FakeInteraction(canal, JOGADORES[0], msg)
        await cog.atacar(inter, run["id"], "OBJ")
        linha = str(inter.resposta)
        if "Marca Fatal" in linha or "explodem" in linha:
            vistas.append(linha)
        if any("explodem" in v for v in vistas):
            break

    assert len(vistas) >= 3, vistas
    assert "Marca Fatal ×1" in vistas[0], vistas[0]
    assert "Marca Fatal ×2" in vistas[1], vistas[1]
    assert "explodem" in vistas[2], vistas[2]
    # E a explosão não rola acerto: ela sai no mesmo golpe que fechou as três.
    assert "3×1d6" in vistas[2], vistas[2]
    # Depois de explodir o inimigo fica limpo, e o ciclo recomeça.
    assert await marcas_em(cog, await db.buscar_run(conn, run["id"]), incursao) == 0

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  a marca empilha e explode na terceira: ok")


async def caso_a_marca_cai_sozinha_depois_de_tres_turnos():
    """Passar 3 turnos sem marcar o mesmo inimigo perde as marcas dele.

    E marcar de novo devolve o prazo INTEIRO: não cai para 2, volta para 3.
    É o que o documento pede, e é `aplicar_efeito` que faz — ele renova em
    vez de empilhar.
    """
    ordem_fixa(("p", JOGADORES[0]), ("i", 0))
    conn, canal, cog, incursao, run = await preparar(nivel=3)
    msg = await canal.fetch_message(run["mensagem_id"])
    passo = cog._passo(run)

    inter = FakeInteraction(canal, JOGADORES[0], msg)
    await cog.atacar(inter, run["id"], "OBJ")
    run = await db.buscar_run(conn, run["id"])
    estado = await cog._estado_combate(run, incursao.objetivo)
    marcas = await cog._marcas_de(run, estado.rodada)
    primeiro_prazo = marcas[0]["expira"]
    assert primeiro_prazo == 1 + hb.TURNOS_DA_MARCA, primeiro_prazo

    # Marcar de novo numa rodada seguinte devolve o prazo inteiro, contado de
    # lá. Ataca até ACERTAR: com CA 1 só o 1 natural erra, e errar não marca
    # — então um erro deixaria o prazo onde estava, e o caso acusaria falso.
    marcas = {}
    for _ in range(20):
        inter = FakeInteraction(canal, JOGADORES[0], msg)
        await cog.atacar(inter, run["id"], "OBJ")
        run = await db.buscar_run(conn, run["id"])
        estado = await cog._estado_combate(run, incursao.objetivo)
        marcas = await cog._marcas_de(run, estado.rodada)
        if marcas and marcas[0]["expira"] > primeiro_prazo:
            break
    assert marcas, "a marca sumiu antes de renovar"
    assert marcas[0]["expira"] > primeiro_prazo, (marcas[0]["expira"], primeiro_prazo)

    # E sem acerto novo elas vencem: `efeitos_ativos` nao as devolve mais.
    adiante = marcas[0]["expira"]
    vencidas = await cog._marcas_de(run, adiante)
    assert not vencidas, vencidas

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  a marca cai sozinha depois de 3 turnos, e marcar devolve o prazo: ok")


async def caso_a_explosao_cresce_com_o_tier():
    """O dado da explosão é o do tier do LADINO, não o do grupo."""
    for nivel, dado in ((3, "1d6"), (5, "2d6"), (9, "3d6")):
        ordem_fixa(("p", JOGADORES[0]), ("i", 0))
        conn, canal, cog, incursao, run = await preparar(nivel=nivel)
        msg = await canal.fetch_message(run["mensagem_id"])
        visto = ""
        for _ in range(20):
            inter = FakeInteraction(canal, JOGADORES[0], msg)
            await cog.atacar(inter, run["id"], "OBJ")
            if "explodem" in str(inter.resposta):
                visto = str(inter.resposta)
                break
        assert f"3×{dado}" in visto, (nivel, visto)
        await conn.close()
        config.DB_PATH.unlink(missing_ok=True)
    print("  a explosão cresce com o tier do Ladino: ok")


async def caso_a_furtividade_congela_a_ameaca():
    """Depois do ataque da Furtividade, a ameaça para de subir por 3 turnos.

    O ataque que ABRE a habilidade conta ameaça normalmente — a ficha diz
    "realiza um ataque e depois entra em Stealth". Os turnos seguintes é que
    saem de graça.
    """
    ordem_fixa(("p", JOGADORES[0]), ("i", 0))
    conn, canal, cog, incursao, run = await preparar(nivel=5)
    msg = await canal.fetch_message(run["mensagem_id"])
    passo = cog._passo(run)
    dono = JOGADORES[0]

    async def ameaca_de():
        """A ameaça acumulada, lida de onde o bot a lê: do combatente.

        Ela mora em `run_efeitos` com o efeito 'ameaca_gerada', e quem monta
        o estado soma em `ameaca_gerada` do combatente.
        """
        atual = await db.buscar_run(conn, run["id"])
        estado = await cog._estado_combate(atual, incursao.objetivo)
        quem = estado.combatente(dono)
        return quem.ameaca_gerada if quem else 0

    # um ataque normal: a ameaça sobe
    inter = FakeInteraction(canal, dono, msg)
    await cog.atacar(inter, run["id"], "OBJ")
    subiu = await ameaca_de()
    assert subiu > 0, subiu

    # a Furtividade: o ataque dela também conta, e o Stealth começa depois
    inter = FakeInteraction(canal, dono, msg)
    await cog.usar_habilidade(inter, run["id"], "OBJ", "furtividade")
    com_a_ativa = await ameaca_de()
    assert com_a_ativa > subiu, (subiu, com_a_ativa)
    assert await cog._escondido(run, dono, 99) is False, "o stealth tem prazo"

    # e os ataques seguintes não somam mais nada
    for _ in range(2):
        inter = FakeInteraction(canal, dono, msg)
        await cog.atacar(inter, run["id"], "OBJ")
    assert await ameaca_de() == com_a_ativa, (
        f"a ameaça subiu durante o Stealth: {await ameaca_de()} vs {com_a_ativa}"
    )

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  a Furtividade congela a ameaça por 3 turnos: ok")


async def caso_a_marca_passa_do_inimigo_que_cai():
    """Tier 5: o inimigo que cai antes da explosão não leva as marcas.

    A escolha é por mensagem PÚBLICA com botão, e não efêmera — o Discord
    só manda efêmera para quem acabou de interagir, e o inimigo marcado cai
    no golpe de qualquer um. Quem clica é conferido: as marcas são do
    ladino.
    """
    ordem_fixa(("p", JOGADORES[0]), ("i", 0))
    conn, canal, cog, incursao, run = await preparar(nivel=9, inimigos=2)
    passo = cog._passo(run)
    dono = JOGADORES[0]

    # Dois inimigos de verdade: um marcado que cai, e um para onde as marcas
    # vão. Precisam existir no BANCO — `transferir_marcas` remonta o estado
    # de lá, e um inimigo só de memória não seria achado.
    estado = await cog._estado_combate(run, incursao.objetivo)
    assert len(estado.inimigos) == 2, estado.inimigos
    marcado, sobra = estado.inimigos[0], estado.inimigos[1]
    await db.aplicar_efeito(
        conn, run["id"], passo, "inimigo", marcado.indice,
        cog.EFEITO_DA_MARCA, {"marcas": 2}, estado.rodada + 3, dono=dono,
    )
    await db.definir_hp_inimigos(conn, run["id"], passo, {marcado.indice: 0})
    estado = await cog._estado_combate(run, incursao.objetivo)
    prazo = estado.rodada + 3

    await cog._marcas_orfas(run, estado)
    # A marca saiu do morto, e o convite foi ao canal.
    assert not await cog._marcas_de(run, estado.rodada), "a marca ficou no morto"
    convites = [
        m for m in canal.enviadas
        if "sem explodir" in (m.content or "")
    ]
    assert len(convites) == 1, [m.content for m in canal.enviadas][-3:]
    view = convites[0].view
    assert view is not None and view.children, "o convite veio sem botao"

    # Outro jogador não escolhe o destino das marcas de alguém.
    intruso = FakeInteraction(canal, JOGADORES[1])
    await cog.transferir_marcas(intruso, run["id"], dono, sobra.indice, 2, prazo)
    assert "não são suas" in str(intruso.resposta), intruso.resposta
    assert not await cog._marcas_de(run, estado.rodada)

    # O ladino escolhe, e elas chegam com o prazo que faltava.
    inter = FakeInteraction(canal, dono)
    await cog.transferir_marcas(inter, run["id"], dono, sobra.indice, 2, prazo)
    agora = await cog._marcas_de(run, estado.rodada)
    assert sobra.indice in agora, agora
    assert (agora[sobra.indice]["valor"] or {}).get("marcas") == 2, agora
    assert agora[sobra.indice]["expira"] == prazo, agora

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  as marcas passam do inimigo que cai, e so o dono escolhe: ok")


async def main():
    try:
        caso_a_ficha_bate_com_o_documento()
        await caso_a_marca_empilha_e_explode_na_terceira()
        await caso_a_marca_cai_sozinha_depois_de_tres_turnos()
        await caso_a_explosao_cresce_com_o_tier()
        await caso_a_furtividade_congela_a_ameaca()
        await caso_a_marca_passa_do_inimigo_que_cai()
    finally:
        iniciativa_de_verdade(False)
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        BANCO.unlink(missing_ok=True)


asyncio.run(main())
print("TESTES DO LADINO PASSARAM")
