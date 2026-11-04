"""As poções: o catálogo, a prateleira da semana, a compra e o beber em combate.

Três regras aqui são de desenho e não de código, e é por isso que cada uma tem
um caso só dela:

- **Beber é a ação da rodada**, menos a Aceleração. Se um dia o custo da ação
  sumir sem ninguém decidir, `caso_beber_gasta_o_turno` cai.
- **Teto de 3 por tipo na bolsa.** É o que impede a incursão de virar guerra
  de atrito com estoque.
- **A poção sai da bolsa ao ser escolhida e volta se não for bebida.** Sem
  isso, perder a vez (caído, atordoado) queimava o item.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import (  # noqa: E402
    classes as cl,
    condicoes,
    config,
    consumiveis as K,
    database as db,
    itens,
    motor,
)
from src.cogs.incursao import Incursoes, SeletorPocao, SeletorRecarga  # noqa: E402
from src.cogs.mercado import Mercado, tentar_comprar  # noqa: E402
from fakes import (  # noqa: E402
    menu_de,
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

# Saco de pancada que aguenta o combate inteiro: os casos querem medir a
# poção, não ganhar a luta.
DURADOURO = {**INDEFESO, "hp": 4000}
# Uma criatura que BATE, para medir a resistência. Golpe fixo de 3 (1d1+2) e
# ataque alto, para acertar sempre e o número ser conferível.
BATEDOR = {
    "nome": "Marretador", "ca": 1, "ataque": 20, "dano": "1d1+2", "hp": 4000,
}
SEMANA = "2026-W45"


async def preparar(classe="guerreiro", nivel=8, monstro=DURADOURO, inimigos=1):
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass
    config.DB_PATH = Path(__file__).resolve().parent / "teste_pocoes.db"
    config.DB_PATH.unlink(missing_ok=True)
    config.TAMANHO_GRUPO = 5
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    ids = await criar_grupo(conn, nivel=nivel, classe=classe)
    canal = FakeCanal(CANAL)
    bot = FakeBot(conn, canal)
    cog = Incursoes(bot)
    cog.loja = Mercado(bot)
    incursao, _ = montar_conteudo(
        cog, tamanho="Curta", monstro_objetivo=monstro, inimigos_objetivo=inimigos,
        salas=salas_sem_combate(),
    )
    return conn, canal, cog, incursao, ids


async def abrir_combate(conn, canal, cog, incursao, quantos=2):
    """Põe o grupo direto no objetivo, com o painel de combate aberto."""
    run_id = await db.criar_run(conn, GUILD, CANAL, incursao.id, JOGADORES[0])
    for user_id in JOGADORES[:quantos]:
        personagem = await db.personagem_por_nome(conn, GUILD, user_id, f"Heroi{user_id}")
        await db.adicionar_participante(conn, run_id, user_id, personagem["id"])
    await db.inicializar_hp(conn, run_id)
    await db.atualizar_run(
        conn, run_id, status="objetivo", sala_atual="OBJ", linha_atual=incursao.passos + 1
    )
    run = await db.buscar_run(conn, run_id)
    await cog._abrir_combate(run, incursao.objetivo)
    return await db.buscar_run(conn, run_id)


async def guardar(conn, personagem_id: int, pocao_id: str, quantas: int = 1) -> None:
    """Põe poções na bolsa sem passar pela loja."""
    for _ in range(quantas):
        await db.devolver_item(conn, personagem_id, pocao_id)


async def beber(cog, canal, run, user_id, pocao_id, escolhida=None, msg=None):
    inter = FakeInteraction(canal, user_id, msg)
    await cog.usar_pocao(
        inter, run["id"], run["sala_atual"], pocao_id, escolhida=escolhida
    )
    return inter


# ============================================================== o catálogo


def caso_catalogo_das_pocoes():
    """Id único, preço positivo, e uma ação que o combate sabe resolver."""
    assert len(K.POR_ID) == len(K.CATALOGO), "id repetido no catálogo"
    conhecidas = ("cura", "duracao", "condicao", "recarga")
    for pocao in K.CATALOGO:
        assert pocao.id.startswith("pocao_"), pocao.id
        assert pocao.custo > 0, pocao.id
        assert pocao.texto, pocao.id
        assert pocao.familia in K.FAMILIAS, pocao.id
        assert pocao.acao.get("tipo") in conhecidas, pocao.acao
        # A ficha sintética é o contrato com `_resolver_habilidade`.
        ficha = K.habilidade_de(pocao)
        assert ficha.nome == pocao.nome and ficha.acao["tipo"] == pocao.acao["tipo"]

    # As de prazo gravam o efeito pela FAMÍLIA: a segunda renova a primeira em
    # vez de somar. Sem isto, três Acelerações de graça davam +6 golpes.
    de_prazo = [p for p in K.CATALOGO if p.acao["tipo"] == "duracao"]
    assert de_prazo, "nenhuma poção de prazo no catálogo"
    for pocao in de_prazo:
        assert K.habilidade_de(pocao).id == pocao.chave_do_efeito
        assert K.nome_do_efeito(pocao.chave_do_efeito), pocao.chave_do_efeito

    # Só a Aceleração não custa a ação da rodada.
    livres = {p.familia for p in K.CATALOGO if not p.gasta_turno}
    assert livres == {K.ACELERACAO}, livres
    print(f"  {len(K.CATALOGO)} poções, ação conhecida e efeito por família: ok")


def caso_todo_buff_tem_pocao_e_artigo():
    """Cada buff da tabela tem poção nos três níveis, e com o artigo certo.

    O artigo é escrito à mão porque gênero em português não sai da
    terminação: "Benção" e "Coragem" são femininas e não acabam em A. Sem esta
    cobrança, um buff novo entraria em cartaz como "Poção do Benção".
    """
    for cid in condicoes.BUFFS:
        assert cid in K.ARTIGO_DO_BUFF, f"buff {cid} sem artigo em ARTIGO_DO_BUFF"
        for x in K.NIVEIS:
            pocao = K.item(f"pocao_{cid}_{x}")
            assert pocao is not None, f"falta poção de {cid} nível {x}"
            assert pocao.acao == {"tipo": "condicao", "condicao": cid, "stacks": x}
    # E nada sobrando: artigo de buff que não existe mais na tabela.
    assert set(K.ARTIGO_DO_BUFF) == set(condicoes.BUFFS), (
        set(K.ARTIGO_DO_BUFF) ^ set(condicoes.BUFFS)
    )
    esperado = len(condicoes.BUFFS) * len(K.NIVEIS)
    assert len(K.da_familia(K.BUFF)) == esperado
    print(f"  {len(condicoes.BUFFS)} buffs × {len(K.NIVEIS)} níveis, com artigo: ok")


def caso_a_prateleira_tem_as_duas_de_vida_e_uma_sorteada():
    """As fixas sempre; a terceira é derivada de (personagem, semana)."""
    prateleira = K.vitrine(1, SEMANA)
    assert len(prateleira) == K.VAGAS == 3, prateleira
    assert [p.id for p in prateleira[:2]] == [p.id for p in K.FIXAS]
    # Derivada: a mesma dupla devolve a mesma prateleira, sempre.
    assert [p.id for p in K.vitrine(1, SEMANA)] == [p.id for p in prateleira]
    # E muda por personagem e por semana.
    de_outro = {p.id for p in K.vitrine(2, SEMANA)}
    de_outra_semana = {p.id for p in K.vitrine(1, "2026-W46")}
    assert de_outro != {p.id for p in prateleira} or de_outra_semana != {
        p.id for p in prateleira
    }, "a vaga sorteada não mudou nem de personagem nem de semana"

    # O sorteio é por FAMÍLIA, e não por poção: as 36 de buff são três quartos
    # do bolo, e sorteando direto a de Mana sairia uma vez por ano.
    familias = {}
    for pid in range(200):
        sorteada = K.vitrine(pid, SEMANA)[2]
        familias[sorteada.familia] = familias.get(sorteada.familia, 0) + 1
    assert set(familias) == set(K.FAMILIAS) - {K.VIDA}, familias
    assert min(familias.values()) >= 20, familias
    print(f"  prateleira de 3, famílias equilibradas em 200 sorteios: {familias}: ok")


# ================================================================= a compra


async def caso_comprar_pocao_respeita_o_teto():
    conn, _canal, _cog, _incursao, ids = await preparar()
    heroi = ids[JOGADORES[0]]
    await db.lancar_ouro(conn, heroi, 1000, "Teste")

    pocao = K.FIXAS[0]
    for esperado in (1, 2, 3):
        peca, texto = await tentar_comprar(conn, heroi, SEMANA, pocao.id)
        assert peca is not None, texto
        bolsa = await db.itens_na_bolsa(conn, heroi)
        assert bolsa[pocao.id] == esperado, bolsa

    # A quarta não entra, e não cobra.
    antes = await db.ouro(conn, heroi)
    peca, texto = await tentar_comprar(conn, heroi, SEMANA, pocao.id)
    assert peca is None and "máximo" in texto, texto
    assert await db.ouro(conn, heroi) == antes, "cobrou sem vender"
    assert (await db.itens_na_bolsa(conn, heroi))[pocao.id] == K.TETO_NA_BOLSA

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print(f"  compra empilha até {K.TETO_NA_BOLSA} e recusa a seguinte: ok")


async def caso_pocao_fora_de_cartaz_nao_vende():
    """A prateleira de HOJE manda, como no equipamento.

    O id pode vir de uma mensagem da semana passada, que o Discord mantém
    clicável — então a compra reconfere em vez de confiar no botão.
    """
    conn, _canal, _cog, _incursao, ids = await preparar()
    heroi = ids[JOGADORES[0]]
    await db.lancar_ouro(conn, heroi, 1000, "Teste")

    em_cartaz = {p.id for p in K.vitrine(heroi, SEMANA)}
    fora = next(p for p in K.CATALOGO if p.id not in em_cartaz)
    peca, texto = await tentar_comprar(conn, heroi, SEMANA, fora.id)
    assert peca is None and "vitrine desta semana" in texto, texto
    assert not await db.itens_na_bolsa(conn, heroi)

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  poção fora da prateleira da semana não vende: ok")


async def caso_pocao_nao_se_veste():
    """Equipar uma poção recusa com a frase certa, e não a põe em slot nenhum."""
    conn, canal, _cog, _incursao, ids = await preparar()
    heroi = ids[JOGADORES[0]]
    await guardar(conn, heroi, "pocao_vida")

    loja = Mercado(FakeBot(conn, canal))
    inter = FakeInteraction(canal, JOGADORES[0])
    await loja.equipar.callback(loja, inter, "pocao_vida")
    assert "não se veste" in leu(inter), leu(inter)
    assert not await db.equipamento(conn, heroi)
    # E o autocomplete de vestir não oferece poção.
    sugeridas = await loja._sugerir_bolsa(inter, "")
    assert all(not K.e_pocao(s.value) for s in sugeridas), sugeridas

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  poção não entra em slot, e não aparece no equipar: ok")


# ============================================================ beber na luta


async def caso_a_pocao_de_vida_cura_e_sai_da_bolsa():
    conn, canal, cog, incursao, ids = await preparar(classe="guerreiro", nivel=8)
    run = await abrir_combate(conn, canal, cog, incursao)
    dono, heroi = JOGADORES[0], ids[JOGADORES[0]]
    await guardar(conn, heroi, "pocao_vida_menor", 2)
    await db.definir_hp(conn, run["id"], dono, 10)

    inter = await beber(cog, canal, run, dono, "pocao_vida_menor")
    assert inter.adiado, "a interação não foi adiada"

    maximo = cl.classe("guerreiro").numeros(8).hp
    hp = (await db.hp_dos_participantes(conn, run["id"]))[dono]
    assert hp == 10 + int(maximo * 0.3), (hp, maximo)
    # Uma saiu da bolsa, a outra ficou.
    assert (await db.itens_na_bolsa(conn, heroi))["pocao_vida_menor"] == 1

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  a Poção de Vida Menor cura 30% e gasta uma unidade: ok")


async def caso_beber_gasta_o_turno():
    """Quem bebe não ataca — e a Aceleração é a exceção que deixa atacar."""
    conn, canal, cog, incursao, ids = await preparar(classe="guerreiro", nivel=8)
    run = await abrir_combate(conn, canal, cog, incursao)
    dono, heroi = JOGADORES[0], ids[JOGADORES[0]]
    await guardar(conn, heroi, "pocao_vida", 1)
    await guardar(conn, heroi, "pocao_aceleracao_2", 1)
    await db.definir_hp(conn, run["id"], dono, 10)

    await beber(cog, canal, run, dono, "pocao_vida")
    estado = await cog._estado_combate(run, incursao.objetivo)
    gasto = await db.acao_do_turno(
        conn, run["id"], cog._passo(run), estado.rodada, dono
    )
    assert gasto == "pocao_vida", gasto

    # Com o turno gasto, o menu mostra só o que não custa a ação.
    inter = FakeInteraction(canal, dono)
    await cog.abrir_pocoes(inter, run["id"], run["sala_atual"])
    vista = menu_de(inter)
    assert isinstance(vista, SeletorPocao), leu(inter)
    assert [o.value for o in vista.menu.options] == ["pocao_aceleracao_2"], (
        [o.value for o in vista.menu.options]
    )

    # E sem nada de graça na bolsa, a recusa explica a regra.
    await db.consumir_item(conn, heroi, "pocao_aceleracao_2")
    await guardar(conn, heroi, "pocao_vida")
    so_pagas = FakeInteraction(canal, dono)
    await cog.abrir_pocoes(so_pagas, run["id"], run["sala_atual"])
    assert "Aceleração" in leu(so_pagas), leu(so_pagas)
    assert menu_de(so_pagas) is None

    # Chamada direto, sem passar pelo menu, a poção que custa a ação é
    # recusada com o turno gasto — e fica na bolsa.
    #
    # A trava é DUPLA, e a sabotagem mostrou isso: tirando a checagem de
    # `acao_do_turno`, a poção ainda não é bebida (a marcação do turno é um
    # `INSERT OR IGNORE` que falha e devolve o item), mas a recusa passa a vir
    # com a mensagem genérica do ataque. Ou seja: quem garante a correção é a
    # marcação atômica, e quem garante a mensagem certa é a checagem. Este
    # caso cobra as duas.
    teimoso = await beber(cog, canal, run, dono, "pocao_vida")
    assert "já bebeu **Poção de Vida**" in leu(teimoso), leu(teimoso)
    assert (await db.itens_na_bolsa(conn, heroi))["pocao_vida"] == 1, (
        "a poção foi bebida com o turno já gasto"
    )
    await guardar(conn, heroi, "pocao_aceleracao_2")

    # A Aceleração passa mesmo com o turno gasto: ela não custa a ação.
    antes = await db.itens_na_bolsa(conn, heroi)
    await beber(cog, canal, run, dono, "pocao_aceleracao_2")
    depois = await db.itens_na_bolsa(conn, heroi)
    assert "pocao_aceleracao_2" not in depois, depois
    assert antes["pocao_aceleracao_2"] == 1

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  beber gasta o turno, e a Aceleração não: ok")


async def caso_a_aceleracao_soma_golpes():
    """+X golpes POR RODADA, somando no que a classe já dá.

    `ataques` seria absoluto ("passa a atacar 2x") e não daria nada a um
    guerreiro que já tem Multiattack — por isso o efeito é `ataques_extra`.
    """
    conn, canal, cog, incursao, ids = await preparar(classe="guerreiro", nivel=8)
    run = await abrir_combate(conn, canal, cog, incursao)
    dono, heroi = JOGADORES[0], ids[JOGADORES[0]]
    await guardar(conn, heroi, "pocao_aceleracao_2")

    antes = (await cog._estado_combate(run, incursao.objetivo)).combatente(dono).ataques
    await beber(cog, canal, run, dono, "pocao_aceleracao_2")
    depois = (await cog._estado_combate(run, incursao.objetivo)).combatente(dono).ataques
    assert depois == antes + 2, (antes, depois)

    # Beber a segunda RENOVA em vez de somar: o efeito é gravado pela família.
    await guardar(conn, heroi, "pocao_aceleracao_1")
    await beber(cog, canal, run, dono, "pocao_aceleracao_1")
    agora = (await cog._estado_combate(run, incursao.objetivo)).combatente(dono).ataques
    assert agora == antes + 1, (antes, agora, "duas poções somaram")

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  a Aceleração soma golpes e a segunda renova a primeira: ok")


async def caso_a_resistencia_corta_o_dano():
    """Corte plano, depois da fração — e pode zerar o golpe pequeno."""
    conn, canal, cog, incursao, ids = await preparar(
        classe="guerreiro", nivel=8, monstro=BATEDOR
    )
    run = await abrir_combate(conn, canal, cog, incursao)
    dono, heroi = JOGADORES[0], ids[JOGADORES[0]]
    await guardar(conn, heroi, "pocao_resistencia_2")
    await beber(cog, canal, run, dono, "pocao_resistencia_2")

    estado = await cog._estado_combate(run, incursao.objetivo)
    quem = estado.combatente(dono)
    assert quem.reducao_plana == 2 * K.REDUCAO_POR_X, quem.reducao_plana
    # O golpe do Marretador é 3 fixo, e o corte é 4: sobra zero.
    assert motor.reduzido(quem, 3) == 0
    # A ordem importa: fração primeiro, corte depois.
    quem.reducao_dano = 0.5
    assert motor.reduzido(quem, 20) == 6, motor.reduzido(quem, 20)

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  a Resistência corta depois da fração e zera golpe pequeno: ok")


async def caso_a_pocao_de_dano_soma_no_golpe():
    conn, canal, cog, incursao, ids = await preparar(classe="guerreiro", nivel=8)
    run = await abrir_combate(conn, canal, cog, incursao)
    dono, heroi = JOGADORES[0], ids[JOGADORES[0]]
    await guardar(conn, heroi, "pocao_dano_3")

    antes = (await cog._estado_combate(run, incursao.objetivo)).combatente(dono).dano_extra
    await beber(cog, canal, run, dono, "pocao_dano_3")
    depois = (await cog._estado_combate(run, incursao.objetivo)).combatente(dono).dano_extra
    assert depois == antes + 3, (antes, depois)

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  a Poção do Dano soma no dano de cada golpe: ok")


async def caso_a_pocao_de_buff_empilha_a_condicao():
    """X stacks da condição da tabela, pelo mesmo caminho do prêmio de Evento."""
    conn, canal, cog, incursao, ids = await preparar(classe="guerreiro", nivel=8)
    run = await abrir_combate(conn, canal, cog, incursao)
    dono, heroi = JOGADORES[0], ids[JOGADORES[0]]
    await guardar(conn, heroi, "pocao_bencao_2")

    inter = await beber(cog, canal, run, dono, "pocao_bencao_2")
    assert (await db.condicoes_de(conn, run["id"], dono)).get("bencao") == 2, (
        await db.condicoes_de(conn, run["id"], dono)
    )
    assert "Benção" in leu(inter) or "Benção" in "".join(
        getattr(m, "content", "") or "" for m in canal.enviadas
    )

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  a Poção da Benção 2 deixa 2 stacks de Benção: ok")


async def caso_a_pocao_de_mana_devolve_um_uso():
    conn, canal, cog, incursao, ids = await preparar(classe="guerreiro", nivel=8)
    run = await abrir_combate(conn, canal, cog, incursao)
    dono, heroi = JOGADORES[0], ids[JOGADORES[0]]
    await guardar(conn, heroi, "pocao_mana_1", 2)

    # Sem nada gasto ela não é bebida: a poção fica na bolsa.
    inter = await beber(cog, canal, run, dono, "pocao_mana_1")
    assert "não gastou nenhuma habilidade" in leu(inter), leu(inter)
    assert (await db.itens_na_bolsa(conn, heroi))["pocao_mana_1"] == 2

    # Gasta o Second Wind (tier 1 do guerreiro) e bebe para tê-lo de volta.
    await db.definir_hp(conn, run["id"], dono, 10)
    alvo = FakeInteraction(canal, dono)
    await cog.usar_habilidade(alvo, run["id"], run["sala_atual"], "second_wind")
    personagem = await cog._personagem_na_run(run, dono)
    assert await cog._recarregaveis(run, personagem, 1), "o uso não foi gasto"

    # A rodada vira: usar a habilidade gastou o turno, e beber também gasta —
    # na mesma rodada a poção seria (corretamente) recusada.
    estado = await cog._estado_combate(run, incursao.objetivo)
    await db.atualizar_rodada(
        conn, run["id"], cog._passo(run), estado.rodada + 1
    )

    # O menu da escolha aparece antes de a poção sair da bolsa.
    escolha = await beber(cog, canal, run, dono, "pocao_mana_1")
    vista = menu_de(escolha)
    assert vista is not None and isinstance(vista, SeletorRecarga), vista
    assert [o.value for o in vista.menu.options] == ["second_wind"]
    assert (await db.itens_na_bolsa(conn, heroi))["pocao_mana_1"] == 2

    # Escolha que não está mais gasta (menu velho, ou outra poção já devolveu
    # aquele uso): recusa ANTES de a poção sair da bolsa.
    velha = await beber(
        cog, canal, run, dono, "pocao_mana_1", escolhida="action_surge"
    )
    assert "não está gasta" in leu(velha), leu(velha)
    assert (await db.itens_na_bolsa(conn, heroi))["pocao_mana_1"] == 2

    inter = await beber(
        cog, canal, run, dono, "pocao_mana_1", escolhida="second_wind"
    )
    # A frase do SUCESSO, e não só o nome da habilidade: a recusa de turno
    # gasto também diz "Second Wind", e esta asserção já passou por engano
    # com ela.
    assert "volta a ter um uso" in leu(inter), leu(inter)
    assert not await cog._recarregaveis(run, personagem, 1)
    assert (await db.itens_na_bolsa(conn, heroi))["pocao_mana_1"] == 1

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  a Poção de Mana devolve o uso escolhido, e só o que foi gasto: ok")


async def caso_perder_a_vez_devolve_a_pocao():
    """Caído ou atordoado antes da vez: a poção escolhida volta para a bolsa.

    Ela sai da bolsa na escolha — é isso que impede dois cliques de beberem a
    mesma. Então quem não chega a beber tem de receber de volta, senão perder
    a vez queimava o item.
    """
    conn, canal, cog, incursao, ids = await preparar(classe="guerreiro", nivel=8)
    run = await abrir_combate(conn, canal, cog, incursao)
    dono, heroi = JOGADORES[0], ids[JOGADORES[0]]
    await guardar(conn, heroi, "pocao_vida")
    await db.definir_hp(conn, run["id"], dono, 10)

    estado = await cog._estado_combate(run, incursao.objetivo)
    passo = cog._passo(run)
    # Escolhe a poção: ela sai da bolsa e a ação fica guardada para a vez.
    await db.consumir_item(conn, heroi, "pocao_vida")
    await db.marcar_turno(
        conn, run["id"], passo, estado.rodada, dono, "pocao_vida", resolvida=False
    )
    assert "pocao_vida" not in await db.itens_na_bolsa(conn, heroi)

    turno = await db.turno_de(conn, run["id"], passo, estado.rodada, dono)
    await cog._perder_a_vez(run, estado, estado.combatente(dono), turno)

    assert (await db.itens_na_bolsa(conn, heroi))["pocao_vida"] == 1, (
        "a poção não voltou para a bolsa"
    )
    # E o HP não mudou: ela não foi bebida.
    assert (await db.hp_dos_participantes(conn, run["id"]))[dono] == 10

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  perder a vez devolve a poção para a bolsa: ok")


async def caso_a_bebida_sai_no_canal_uma_vez_so():
    """O grupo vê quem bebeu o quê — e vê UMA vez.

    As quatro famílias de ação passam por resolvedores diferentes, e cada um
    anuncia por `_anunciar_habilidade`, que guarda a frase publicada para ela
    não sair de novo em privado. É a mesma regra das habilidades
    (`test_ativas.caso_a_habilidade_aparece_uma_vez_so`): a pública conta a
    história para a mesa, e a efêmera é fechada sem repetir.

    As duas ações novas (a de buff e a de Mana) nasceram mudas, e este caso é
    o que cobra o anúncio delas.
    """
    conn, canal, cog, incursao, ids = await preparar(classe="guerreiro", nivel=8)
    run = await abrir_combate(conn, canal, cog, incursao)
    dono, heroi = JOGADORES[0], ids[JOGADORES[0]]

    # Uma de cada família de ação: cura, prazo, condição e recarga.
    await db.definir_hp(conn, run["id"], dono, 10)
    alvo = FakeInteraction(canal, dono)
    await cog.usar_habilidade(alvo, run["id"], run["sala_atual"], "second_wind")
    estado = await cog._estado_combate(run, incursao.objetivo)
    rodada = estado.rodada

    def publicas(pedaco: str) -> list[str]:
        return [
            m.content for m in canal.enviadas
            if pedaco in (getattr(m, "content", None) or "")
        ]

    # `repete` diz se a frase privada acrescenta algo à pública. A de prazo
    # acrescenta: a pública diz quem bebeu o quê, e a privada diz até quando
    # vale ("até a rodada 5"). Vale para toda habilidade de duração, não só
    # para a poção — é o formato que `_resolver_duracao` usa.
    for pocao_id, escolhida, repete in (
        ("pocao_vida", None, False),
        ("pocao_aceleracao_1", None, True),
        ("pocao_bencao_1", None, False),
        ("pocao_mana_1", "second_wind", False),
    ):
        await guardar(conn, heroi, pocao_id)
        # Cada poção numa rodada própria: beber gasta a ação (menos a de
        # Aceleração), e o caso aqui é a visibilidade, não a economia.
        rodada += 1
        await db.atualizar_rodada(conn, run["id"], cog._passo(run), rodada)
        nome = K.item(pocao_id).nome
        inter = await beber(cog, canal, run, dono, pocao_id, escolhida=escolhida)
        achadas = publicas(nome)
        assert len(achadas) == 1, (nome, achadas)
        if repete:
            assert "turno(s)" in inter.resposta, (nome, inter.resposta)
        else:
            # A mesma frase não sai duas vezes: a privada é apagada.
            assert not inter.resposta, (nome, inter.resposta)
            assert inter.efemera_apagada or inter.resposta == "", nome

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  cada poção sai no canal uma vez, e não repete em privado: ok")


async def caso_sem_pocao_o_botao_avisa():
    conn, canal, cog, incursao, _ids = await preparar(classe="guerreiro", nivel=8)
    run = await abrir_combate(conn, canal, cog, incursao)

    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.abrir_pocoes(inter, run["id"], run["sala_atual"])
    assert "não tem poção" in leu(inter), leu(inter)
    assert menu_de(inter) is None

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  bolsa vazia: o botão explica em vez de abrir menu vazio: ok")


async def caso_o_menu_lista_o_que_a_bolsa_tem():
    conn, canal, cog, incursao, ids = await preparar(classe="guerreiro", nivel=8)
    run = await abrir_combate(conn, canal, cog, incursao)
    heroi = ids[JOGADORES[0]]
    await guardar(conn, heroi, "pocao_vida", 2)
    await guardar(conn, heroi, "pocao_dano_1")
    # Equipamento na bolsa não é poção, e não entra no menu de beber.
    await db.devolver_item(conn, heroi, "gibao_de_couro")

    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.abrir_pocoes(inter, run["id"], run["sala_atual"])
    vista = menu_de(inter)
    assert isinstance(vista, SeletorPocao), vista
    valores = [o.value for o in vista.menu.options]
    assert set(valores) == {"pocao_vida", "pocao_dano_1"}, valores
    rotulos = {o.value: o.label for o in vista.menu.options}
    assert "×2" in rotulos["pocao_vida"], rotulos

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  o menu lista só poções, com a quantidade: ok")


async def main() -> None:
    try:
        caso_catalogo_das_pocoes()
        caso_todo_buff_tem_pocao_e_artigo()
        caso_a_prateleira_tem_as_duas_de_vida_e_uma_sorteada()
        await caso_comprar_pocao_respeita_o_teto()
        await caso_pocao_fora_de_cartaz_nao_vende()
        await caso_pocao_nao_se_veste()
        await caso_a_pocao_de_vida_cura_e_sai_da_bolsa()
        await caso_beber_gasta_o_turno()
        await caso_a_aceleracao_soma_golpes()
        await caso_a_resistencia_corta_o_dano()
        await caso_a_pocao_de_dano_soma_no_golpe()
        await caso_a_pocao_de_buff_empilha_a_condicao()
        await caso_a_pocao_de_mana_devolve_um_uso()
        await caso_perder_a_vez_devolve_a_pocao()
        await caso_a_bebida_sai_no_canal_uma_vez_so()
        await caso_sem_pocao_o_botao_avisa()
        await caso_o_menu_lista_o_que_a_bolsa_tem()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        config.DB_PATH.unlink(missing_ok=True)
    print("TESTES DAS POCOES PASSARAM")


asyncio.run(main())
