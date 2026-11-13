"""O Ladino: Marca Fatal, a explosão na terceira marca e a Furtividade."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import (  # noqa: E402
    ameaca,
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
# O mesmo boneco com HP de sala de verdade, para os casos que medem AMEAÇA: a
# ameaça gerada é fração do HP da sala, e contra 9000 tudo arredonda para zero.
BONECO_DE_SALA = {**BONECO, "hp": 400}


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


async def preparar(nivel=3, quantos=1, inimigos=1, monstro=None):
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
        cog, tamanho="Curta", monstro_objetivo=monstro or BONECO,
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


def tudo_lido(canal, falas=()):
    """Tudo que o jogador leu: as efêmeras dos cliques mais o canal.

    O ataque comum responde em PRIVADO; a ativa anuncia no CANAL e apaga a
    efêmera de quem clicou. Os dois caminhos marcam, então nenhum caso de
    marca pode depender de por qual porta o texto saiu — e procurar o trecho
    no monte também não depende de quem falou por último.
    """
    return "\n".join([*falas, *(m.content or "" for m in canal.enviadas)])


async def abrir_marcacao(
    conn, canal, cog, incursao, run, dono=JOGADORES[0], alvos=None
):
    """Gasta a ativa do tier 2, que é o que abre a marcação do combate.

    Virou passo obrigatório de todo caso de marca: sem isso o ladino ataca e
    não marca nada. Devolve (o que o jogador viu, a run depois, a rodada em
    que a ativa agiu) — a rodada porque o golpe dela já pode ter marcado, e
    o prazo da marca é contado de onde ela caiu.
    """
    rodada = (await cog._estado_combate(run, incursao.objetivo)).rodada
    msg = await canal.fetch_message(run["mensagem_id"])
    inter = FakeInteraction(canal, dono, msg)
    # Com mais de um inimigo a ativa pergunta o alvo antes de gastar o uso:
    # sem `alvos` ela para no menu e a marcacao nao abre.
    await cog.usar_habilidade(
        inter, run["id"], "OBJ", "marca_fatal",
        **({"alvos": alvos} if alvos is not None else {}),
    )
    atual = await db.buscar_run(conn, run["id"])
    assert await cog._marcacao_aberta(atual, dono), (
        f"a ativa não abriu a marcação: {inter.resposta}"
    )
    return str(inter.resposta), atual, rodada


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

    # A Marca Fatal é ATIVA, 1x por combate, e dá um golpe: era passiva, e o
    # ladino marcava do primeiro ataque sem decidir nada.
    marca = hb.POR_ID["marca_fatal"]
    assert marca.tipo == cl.ATIVA, marca.tipo
    assert (marca.escopo, marca.vezes) == ("combate", 1), (marca.escopo, marca.vezes)
    assert marca.acao == {"tipo": "golpes", "quantidade": 1}, marca.acao
    # E a marcação não vem mais de graça pela ficha: nenhum tier do ladino
    # entrega a chave `marca_fatal` como efeito passivo.
    for nivel in (3, 5, 7, 9):
        assert "marca_fatal" not in cl.efeitos("ladino", nivel, {}), nivel
    assert cl.efeitos("ladino", 9, {}).get("marca_fatal_transfere"), (
        "o tier 5 continua passando as marcas do inimigo que cai"
    )
    print("  a ficha do Ladino bate com o documento: ok")


async def caso_atacar_sem_a_ativa_nao_marca():
    """A marcação não vem de graça: sem gastar a ativa, nenhum acerto marca.

    É a mudança inteira. Antes a Marca Fatal era passiva e o ladino marcava
    desde o primeiro golpe, sem decidir nada; agora ele gasta a ação uma vez
    por combate para abrir a torneira.
    """
    ordem_fixa(("p", JOGADORES[0]), ("i", 0))
    conn, canal, cog, incursao, run = await preparar(nivel=3)
    msg = await canal.fetch_message(run["mensagem_id"])
    dono = JOGADORES[0]
    assert not await cog._marcacao_aberta(run, dono), "nasceu aberta"

    # Cinco acertos sem a ativa: com CA 1, quase todos acertam — e nenhum marca.
    for _ in range(5):
        inter = FakeInteraction(canal, dono, msg)
        await cog.atacar(inter, run["id"], "OBJ")
        assert "Marca Fatal" not in str(inter.resposta), inter.resposta
        run = await db.buscar_run(conn, run["id"])
    assert await marcas_em(cog, run, incursao) == 0, "marcou sem a ativa"

    # Agora abre. Dali em diante o acerto volta a marcar, como a passiva fazia.
    _, run, _ = await abrir_marcacao(conn, canal, cog, incursao, run)
    msg = await canal.fetch_message(run["mensagem_id"])
    for _ in range(20):
        if await marcas_em(cog, run, incursao) > 0:
            break
        inter = FakeInteraction(canal, dono, msg)
        await cog.atacar(inter, run["id"], "OBJ")
        run = await db.buscar_run(conn, run["id"])
    assert await marcas_em(cog, run, incursao) > 0, "não marcou nem com a ativa"

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  sem a ativa ninguém marca; com ela, todo acerto marca: ok")


async def caso_o_uso_e_o_interruptor_e_vale_pelo_combate():
    """Quem liga a marcação é o REGISTRO DO USO, e ele é por combate.

    Sem estado novo: `gastar_uso` grava sob `combate:{passo}`, então a chave
    nasce com a ativa, vale pelo combate inteiro e morre na troca de sala.
    E ela está gravada antes de o golpe da ativa resolver — por isso o
    ataque que abre também marca.
    """
    ordem_fixa(("p", JOGADORES[0]), ("i", 0))
    conn, canal, cog, incursao, run = await preparar(nivel=3)
    dono, passo = JOGADORES[0], cog._passo(run)
    _, run, _ = await abrir_marcacao(conn, canal, cog, incursao, run)

    gastos = await db.usos_da_run(conn, run["id"], dono)
    assert gastos.get(("marca_fatal", f"combate:{passo}")) == 1, gastos
    assert await cog._marcacao_aberta(run, dono) is True

    # Um uso só: a segunda tentativa é recusada, e a marcação segue aberta.
    msg = await canal.fetch_message(run["mensagem_id"])
    inter = FakeInteraction(canal, dono, msg)
    await cog.usar_habilidade(inter, run["id"], "OBJ", "marca_fatal")
    run = await db.buscar_run(conn, run["id"])
    assert await cog._marcacao_aberta(run, dono) is True

    # E ninguém mais do grupo marca por tabela: a chave é de quem gastou.
    assert await cog._marcacao_aberta(run, JOGADORES[1]) is False

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  o uso é o interruptor, vale por combate e é de quem gastou: ok")


async def caso_a_marca_empilha_e_explode_na_terceira():
    """Com a marcação aberta, acertar marca; a terceira explode na hora."""
    ordem_fixa(("p", JOGADORES[0]), ("i", 0))
    conn, canal, cog, incursao, run = await preparar(nivel=3)
    _, run, _ = await abrir_marcacao(conn, canal, cog, incursao, run)
    msg = await canal.fetch_message(run["mensagem_id"])

    # Ataca até as três marcas fecharem, lendo a PILHA e não o texto: o
    # anúncio sai no canal e o inimigo fala depois dele, então procurar a
    # linha "×1" na resposta do clique seria frágil.
    #
    # A CA do boneco é 1, então só o 1 natural erra — e ele sai, de vez em
    # quando. O caso é sobre a marca, e não sobre a rolagem de acerto:
    # errar não marca, e só isso. O golpe da própria ativa já marca, então
    # o primeiro valor lido pode ser 1.
    pilha = [await marcas_em(cog, run, incursao)]
    falas = []
    for _ in range(20):
        inter = FakeInteraction(canal, JOGADORES[0], msg)
        await cog.atacar(inter, run["id"], "OBJ")
        falas.append(str(inter.resposta))
        run = await db.buscar_run(conn, run["id"])
        pilha.append(await marcas_em(cog, run, incursao))
        if "explodem" in tudo_lido(canal, falas):
            break

    # A pilha subiu de 1 em 1 até a terceira, e a explosão a zerou.
    assert 1 in pilha and 2 in pilha, pilha
    assert pilha.index(1) < pilha.index(2), pilha
    assert pilha[-1] == 0, pilha
    assert max(pilha) < hb.MARCAS_PARA_EXPLODIR, (
        f"a terceira marca deveria explodir em vez de ficar: {pilha}"
    )

    lido = tudo_lido(canal, falas)
    assert "explodem" in lido, "a explosão não foi anunciada em lugar nenhum"
    # E a explosão não rola acerto: ela sai no mesmo golpe que fechou as três.
    assert "3×1d6" in lido, lido[-400:]

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  a marca empilha e explode na terceira: ok")


async def caso_a_explosao_sai_uma_vez_e_fecha_a_marcacao():
    """A explosão é uma por combate: depois dela o ladino para de marcar.

    Antes o ciclo recomeçava — o inimigo ficava limpo e as três marcas
    subiam de novo, quantas vezes o combate durasse. Agora a ativa é uma
    janela: abre, empilha, estoura, fecha.

    Dois inimigos para provar a outra metade: as marcas que sobraram em
    OUTRO inimigo saem com a marcação. Sem ela aberta elas nunca chegariam
    à terceira, e o 🎯 no nome dele prometeria uma explosão que não vem.
    """
    ordem_fixa(("p", JOGADORES[0]), ("i", 0), ("i", 1))
    conn, canal, cog, incursao, run = await preparar(nivel=3, inimigos=2)
    _, run, _ = await abrir_marcacao(conn, canal, cog, incursao, run, alvos=[0])
    msg = await canal.fetch_message(run["mensagem_id"])

    async def marcas(indice):
        return await marcas_em(cog, await db.buscar_run(conn, run["id"]), incursao, indice)

    async def bater(indice):
        inter = FakeInteraction(canal, JOGADORES[0], msg)
        await cog.atacar(inter, run["id"], "OBJ", alvo_indice=indice)
        return str(inter.resposta)

    # O primeiro inimigo até ×2, sem fechar as três.
    for _ in range(20):
        if await marcas(0) >= 2:
            break
        await bater(0)
    assert await marcas(0) == 2, await marcas(0)

    # Só então uma marca no SEGUNDO, para o prazo dela estar VIVO quando a
    # explosão sair: marcada antes, ela venceria sozinha nos 3 turnos e o caso
    # daria a limpeza por provada sem que ninguém limpasse nada.
    for _ in range(20):
        if await marcas(1):
            break
        await bater(1)
    assert await marcas(1) == 1, await marcas(1)
    run = await db.buscar_run(conn, run["id"])
    estado = await cog._estado_combate(run, incursao.objetivo)
    prazo_do_outro = (await cog._marcas_de(run, estado.rodada))[1]["expira"]
    assert prazo_do_outro > estado.rodada + 1, (
        f"a marca do outro vence antes da explosão ({prazo_do_outro} vs "
        f"rodada {estado.rodada}): o caso não provaria a limpeza"
    )

    # E o golpe que fecha as três.
    falas = []
    for _ in range(20):
        if "explodem" in tudo_lido(canal, falas):
            break
        falas.append(await bater(0))
    lido = tudo_lido(canal, falas)
    assert "explodem" in lido, "a explosão não saiu"
    assert "se fecha" in lido, lido[-300:]

    # A torneira fechou, e a marca do outro inimigo foi com ela.
    run = await db.buscar_run(conn, run["id"])
    assert await cog._marcacao_aberta(run, JOGADORES[0]) is False
    assert await cog._marcacao_gasta(run, JOGADORES[0]) is True
    assert await marcas(1) == 0, f"a marca do outro inimigo ficou: {await marcas(1)}"

    # Dez acertos depois: nenhuma marca nova, nenhuma segunda explosão.
    quantas_explosoes = tudo_lido(canal, falas).count("explodem")
    for _ in range(10):
        falas.append(await bater(0))
    depois = tudo_lido(canal, falas)
    assert await marcas(0) == 0, f"voltou a marcar: {await marcas(0)}"
    assert await marcas(1) == 0, f"voltou a marcar o outro: {await marcas(1)}"
    assert depois.count("explodem") == quantas_explosoes, (
        "saiu uma segunda explosão no mesmo combate"
    )

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  a explosão sai uma vez e fecha a marcação do combate: ok")


async def caso_a_marca_cai_sozinha_depois_de_tres_turnos():
    """Passar 3 turnos sem marcar o mesmo inimigo perde as marcas dele.

    E marcar de novo devolve o prazo INTEIRO: não cai para 2, volta para 3.
    É o que o documento pede, e é `aplicar_efeito` que faz — ele renova em
    vez de empilhar.
    """
    ordem_fixa(("p", JOGADORES[0]), ("i", 0))
    conn, canal, cog, incursao, run = await preparar(nivel=3)
    aberta, run, rodada_do_abrir = await abrir_marcacao(
        conn, canal, cog, incursao, run
    )
    msg = await canal.fetch_message(run["mensagem_id"])
    passo = cog._passo(run)

    # O golpe da própria ativa já pode ter marcado. Se não marcou — só o 1
    # natural erra, e ele sai de vez em quando —, ataca até ACERTAR: errar não
    # marca, e uma rolagem em vinte deixava este caso vermelho com um
    # KeyError, que não é a falha que ele existe para apontar.
    estado = await cog._estado_combate(run, incursao.objetivo)
    marcas = await cog._marcas_de(run, estado.rodada)
    marcou_na_rodada = rodada_do_abrir if marcas else None
    while not marcas:
        # A rodada de ANTES do golpe: atacar sozinho vira a rodada, e o prazo
        # da marca é contado de quando ela caiu, não de depois da virada.
        marcou_na_rodada = (
            await cog._estado_combate(run, incursao.objetivo)
        ).rodada
        if marcou_na_rodada > rodada_do_abrir + 20:
            break
        inter = FakeInteraction(canal, JOGADORES[0], msg)
        await cog.atacar(inter, run["id"], "OBJ")
        run = await db.buscar_run(conn, run["id"])
        estado = await cog._estado_combate(run, incursao.objetivo)
        marcas = await cog._marcas_de(run, estado.rodada)
    assert marcas, "vinte ataques sem marcar: não é azar, é regra quebrada"
    primeiro_prazo = marcas[0]["expira"]
    assert primeiro_prazo == marcou_na_rodada + hb.TURNOS_DA_MARCA, (
        primeiro_prazo, marcou_na_rodada
    )

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
        _, run, _ = await abrir_marcacao(conn, canal, cog, incursao, run)
        msg = await canal.fetch_message(run["mensagem_id"])
        falas = []
        for _ in range(20):
            if "explodem" in tudo_lido(canal, falas):
                break
            inter = FakeInteraction(canal, JOGADORES[0], msg)
            await cog.atacar(inter, run["id"], "OBJ")
            falas.append(str(inter.resposta))
        lido = tudo_lido(canal, falas)
        assert f"3×{dado}" in lido, (nivel, lido[-400:])
        await conn.close()
        config.DB_PATH.unlink(missing_ok=True)
    print("  a explosão cresce com o tier do Ladino: ok")


async def caso_a_furtividade_congela_a_ameaca():
    """Depois do ataque da Furtividade, a ameaça para de subir por 3 turnos.

    O ataque que ABRE a habilidade conta ameaça normalmente — a ficha diz
    "realiza um ataque e depois entra em Stealth". Os turnos seguintes é que
    saem de graça.

    O caso lê a conta DA RODADA, do banco, e não o `ameaca_gerada` do
    combatente: a conta de uma rodada só chega ao combatente na rodada
    seguinte (é a janela), e o que se mede aqui é se ela foi ESCRITA.
    """
    ordem_fixa(("p", JOGADORES[0]), ("i", 0))
    # Um boneco de tamanho de sala, e não o de 9000 HP dos outros casos: a
    # ameaça é FRAÇÃO da poça, e contra 9000 um golpe de ladino move 0,2% e
    # arredonda para zero ponto — o caso mediria zero contra zero.
    conn, canal, cog, incursao, run = await preparar(nivel=5, monstro=BONECO_DE_SALA)
    msg = await canal.fetch_message(run["mensagem_id"])
    passo = cog._passo(run)
    dono = JOGADORES[0]

    async def rodada_agora() -> int:
        atual = await db.buscar_run(conn, run["id"])
        estado = await cog._estado_combate(atual, incursao.objetivo)
        return estado.rodada

    async def conta_da(rodada: int) -> int:
        """O que a conta daquela rodada guardou para ele."""
        efeitos = await db.efeitos_ativos(conn, run["id"], passo, rodada - 1)
        return sum(
            (e["valor"] or {}).get("ameaca", 0)
            for e in efeitos
            if e["alvo_tipo"] == "personagem"
            and e["alvo_id"] == dono
            and e["efeito"] == ameaca.efeito_da_rodada(rodada)
        )

    # um ataque normal: a conta da rodada dele sobe
    primeira = await rodada_agora()
    await cog.atacar(FakeInteraction(canal, dono, msg), run["id"], "OBJ")
    assert await conta_da(primeira) > 0, primeira

    # a Furtividade: o ataque dela também conta, e o Stealth começa depois
    da_ativa = await rodada_agora()
    await cog.usar_habilidade(FakeInteraction(canal, dono, msg), run["id"], "OBJ", "furtividade")
    assert await conta_da(da_ativa) > 0, "o ataque que abre o Stealth conta"
    assert await cog._escondido(run, dono, 99) is False, "o stealth tem prazo"

    # e os ataques seguintes não escrevem conta nenhuma
    for _ in range(2):
        escondido = await rodada_agora()
        await cog.atacar(FakeInteraction(canal, dono, msg), run["id"], "OBJ")
        assert await conta_da(escondido) == 0, (
            f"a ameaça subiu na rodada {escondido}, durante o Stealth"
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
        await caso_atacar_sem_a_ativa_nao_marca()
        await caso_o_uso_e_o_interruptor_e_vale_pelo_combate()
        await caso_a_marca_empilha_e_explode_na_terceira()
        await caso_a_explosao_sai_uma_vez_e_fecha_a_marcacao()
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
