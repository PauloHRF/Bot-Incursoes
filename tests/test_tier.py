"""Tier da incursão: quem está abaixo entra, quem está acima fica de fora."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import classes as cl, config, database as db, embeds as E, motor  # noqa: E402
from src.cogs.incursao import Incursoes, SeletorPersonagemEntrada  # noqa: E402
from src.rules import TIER_MAXIMO, faixa_do_tier, tier  # noqa: E402
from fakes import (  # noqa: E402
    menu_de,
    CLASSE_PADRAO,
    CANAL,
    GUILD,
    JOGADORES,
    TREINADAS,
    FakeBot,
    FakeCanal,
    FakeInteraction,
    leu,
    montar_conteudo,
    salas_sem_combate,
)

_ABERTAS = []


async def preparar(tier_incursao=None):
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass
    config.DB_PATH = Path(__file__).resolve().parent / "teste_tier.db"
    config.DB_PATH.unlink(missing_ok=True)
    config.TAMANHO_GRUPO = 5
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    canal = FakeCanal(CANAL)
    cog = Incursoes(FakeBot(conn, canal))
    incursao, _ = montar_conteudo(cog, tier=tier_incursao, salas=salas_sem_combate())
    return conn, canal, cog, incursao


async def heroi(conn, user_id, nome, nivel):
    return await db.criar_personagem(
        conn, GUILD, user_id, nome, CLASSE_PADRAO, TREINADAS, nivel=nivel
    )


def caso_tier_a_cada_dois_niveis():
    """A conta do tier e a faixa de níveis que ele cobre."""
    assert [tier(n) for n in (1, 2, 3, 4, 5, 6, 7, 8)] == [1, 1, 2, 2, 3, 3, 4, 4]
    assert tier(19) == tier(20) == TIER_MAXIMO
    assert faixa_do_tier(1) == (1, 2) and faixa_do_tier(4) == (7, 8)
    # nivel fora da tabela nao estoura: fica preso nas pontas
    assert tier(0) == 1 and tier(99) == TIER_MAXIMO
    print("  tier: um a cada 2 níveis, 1-2 = tier 1: ok")


def caso_so_sobe_quem_esta_abaixo():
    """Abaixo do tier da incursão pode; acima, não."""
    for nivel in (1, 2, 5, 6, 7, 8):  # tier 1 ate 4
        assert motor.pode_encarar(nivel, 4), nivel
    for nivel in (9, 10, 11, 20):  # tier 5 em diante
        assert not motor.pode_encarar(nivel, 4), nivel
    # uma incursão de tier 1 só aceita quem está começando
    assert motor.pode_encarar(2, 1) and not motor.pode_encarar(3, 1)
    # o tier maximo é a incursão aberta a todo mundo
    assert all(motor.pode_encarar(n, TIER_MAXIMO) for n in range(1, 21))
    print("  quem está acima do tier não encara a incursão: ok")


async def caso_entrar_recusa_quem_esta_acima():
    conn, canal, cog, incursao = await preparar(tier_incursao=3)  # ate o nivel 6
    dono = JOGADORES[0]
    await heroi(conn, dono, "Veterano", 12)

    inter = FakeInteraction(canal, dono)
    await cog.entrar.callback(cog, inter, cog.incursoes["t"].tier, "t")
    assert "tier 3" in inter.resposta and "tier 5" in inter.resposta, inter.resposta
    assert "Veterano" in inter.resposta
    assert await db.run_do_canal(conn, CANAL) is None, "não podia ter aberto a run"
    print("  /incursao entrar barra o personagem acima do tier: ok")


async def caso_entrar_escolhe_o_que_cabe():
    """Com vários personagens, o bot leva o único que cabe no tier."""
    conn, canal, cog, incursao = await preparar(tier_incursao=2)  # ate o nivel 4
    dono = JOGADORES[0]
    await heroi(conn, dono, "Veterano", 12)
    novato = await heroi(conn, dono, "Novato", 3)

    inter = FakeInteraction(canal, dono)
    await cog.entrar.callback(cog, inter, cog.incursoes["t"].tier, "t")
    run = await db.run_do_canal(conn, CANAL)
    assert run is not None, "com um personagem elegível, a run abre"
    escolhidos = await db.personagens_da_run(conn, run["id"])
    assert [p["id"] for p in escolhidos] == [novato], escolhidos

    # pedir o veterano pelo nome continua sendo recusado
    conn, canal, cog, incursao = await preparar(tier_incursao=2)
    await heroi(conn, dono, "Veterano", 12)
    await heroi(conn, dono, "Novato", 3)
    pedido = FakeInteraction(canal, dono)
    await cog.entrar.callback(cog, pedido, cog.incursoes["t"].tier, "t", personagem="Veterano")
    assert "Veterano" in pedido.resposta and "tier 2" in pedido.resposta
    assert await db.run_do_canal(conn, CANAL) is None
    print("  entrar leva o personagem que cabe, e recusa o pedido fora do tier: ok")


async def caso_botao_entrar_respeita_o_tier():
    conn, canal, cog, incursao = await preparar(tier_incursao=3)  # ate o nivel 6
    anfitriao, visitante, misto = JOGADORES[0], JOGADORES[1], JOGADORES[2]
    await heroi(conn, anfitriao, "Anfitriao", 5)
    await heroi(conn, visitante, "Grandao", 14)
    await heroi(conn, misto, "Um", 2)
    await heroi(conn, misto, "Dois", 6)
    await heroi(conn, misto, "Alto", 20)

    await cog.entrar.callback(cog, FakeInteraction(canal, anfitriao), cog.incursoes["t"].tier, "t")
    run = await db.run_do_canal(conn, CANAL)
    msg = await canal.fetch_message(run["mensagem_id"])

    # so tem personagem acima do tier: nao entra
    barrado = FakeInteraction(canal, visitante, msg)
    await cog.recrutar(barrado, run["id"], "entrar")
    assert "tier 3" in barrado.resposta and "Grandao" in barrado.resposta
    assert not await db.esta_na_run(conn, run["id"], visitante)

    # tem tres personagens, mas o menu so oferece os dois que cabem
    escolha = FakeInteraction(canal, misto, msg)
    await cog.recrutar(escolha, run["id"], "entrar")
    view = menu_de(escolha)
    assert isinstance(view, SeletorPersonagemEntrada)
    rotulos = {o.label for o in view.menu.options}
    assert rotulos == {"Um", "Dois"}, rotulos
    print("  o botão Entrar filtra o menu pelo tier: ok")


async def caso_menu_velho_nao_fura_a_regra():
    """O menu fica aberto por minutos: a checagem se repete na hora de efetivar."""
    conn, canal, cog, incursao = await preparar(tier_incursao=3)
    anfitriao, esperto = JOGADORES[0], JOGADORES[1]
    await heroi(conn, anfitriao, "Anfitriao", 5)
    pequeno = await heroi(conn, esperto, "Pequeno", 4)
    await heroi(conn, esperto, "Outro", 6)

    await cog.entrar.callback(cog, FakeInteraction(canal, anfitriao), cog.incursoes["t"].tier, "t")
    run = await db.run_do_canal(conn, CANAL)

    # o personagem sobe de nivel depois que o menu ja estava na tela
    await db.atualizar_personagem(conn, pequeno, "nivel", 15)
    tarde = FakeInteraction(canal, esperto)
    await cog.efetivar_entrada(tarde, run["id"], pequeno)
    assert "tier 3" in tarde.resposta, tarde.resposta
    assert not await db.esta_na_run(conn, run["id"], esperto)
    print("  menu velho não fura a regra do tier: ok")


async def caso_incursao_sem_tier_e_aberta():
    conn, canal, cog, incursao = await preparar()  # sem tier na planilha
    assert incursao.tier == TIER_MAXIMO and incursao.aberta_a_todos
    dono = JOGADORES[0]
    await heroi(conn, dono, "Lenda", 20)

    inter = FakeInteraction(canal, dono)
    await cog.entrar.callback(cog, inter, cog.incursoes["t"].tier, "t")
    run = await db.run_do_canal(conn, CANAL)
    assert run is not None and await db.esta_na_run(conn, run["id"], dono)

    # e o recrutamento diz isso, em vez de deixar o grupo adivinhar
    texto = E.exigencia_de_tier(incursao)
    assert "livre" in texto, texto
    print("  incursão sem tier declarado fica aberta a todos: ok")


async def caso_recrutamento_mostra_o_tier():
    conn, canal, cog, incursao = await preparar(tier_incursao=4)
    dono = JOGADORES[0]
    await heroi(conn, dono, "Heroi", 7)
    await cog.entrar.callback(cog, FakeInteraction(canal, dono), cog.incursoes["t"].tier, "t")
    run = await db.run_do_canal(conn, CANAL)
    msg = await canal.fetch_message(run["mensagem_id"])
    campos = {f.name: f.value for f in msg.embeds[0].fields}
    assert "Quem pode entrar" in campos, campos
    assert "Tier 4" in campos["Quem pode entrar"]
    assert "tier 4 ou menos" in campos["Quem pode entrar"]

    # e a listagem tambem, para escolher antes de abrir
    listagem = FakeInteraction(canal, dono)
    await cog.listar.callback(cog, listagem)
    valores = " ".join(f.value for f in listagem._mensagem_resposta.embeds[0].fields)
    assert "Tier 4" in valores, valores
    print("  recrutamento e listagem dizem o tier: ok")



def caso_o_ajuste_de_cd_segue_o_bonus_de_proficiencia():
    """A CD da sala sobe no mesmo passo em que o personagem melhora.

    É isso que faz a chance de superar a sala ficar igual nos cinco tiers.
    `AJUSTE_DE_CD_POR_TIER` é escrito à mão em `rules.py` por clareza, e este
    caso o amarra à sua origem — se o bônus de proficiência das classes mudar
    e o ajuste não, a dificuldade por tier deixa de ser plana e ninguém
    perceberia.
    """
    from src.rules import AJUSTE_DE_CD_POR_TIER, cd_no_tier

    for classe in cl.CLASSES.values():
        base = classe.tiers[1].bonus_proficiencia
        crescimento = {t: classe.tiers[t].bonus_proficiencia - base for t in range(1, 6)}
        assert crescimento == AJUSTE_DE_CD_POR_TIER, (classe.nome, crescimento)

    assert cd_no_tier(15, 1) == 15
    assert cd_no_tier(15, 5) == 21
    # Sem tier devolve a base, para conteúdo antigo não estourar.
    assert cd_no_tier(15, None) == 15
    # E fora da faixa prende no teto, em vez de estourar.
    assert cd_no_tier(15, 99) == cd_no_tier(15, 5)
    print("  o ajuste de CD por tier segue o bonus de proficiencia: ok")


async def caso_o_filtro_de_tier_estreita_a_lista_e_o_entrar():
    """O tier vem antes do id, e é ele que decide o que o jogador vê.

    O `/incursao entrar` pedia o id direto, e a lista do autocomplete trazia
    todas — inclusive as que o personagem nem pode jogar. Agora o tier é o
    primeiro campo e filtra o seguinte; `/incursao listar` aceita o mesmo
    filtro, e nenhum dos dois mostra mais o id do arquivo.
    """
    conn, canal, cog, incursao = await preparar(tier_incursao=2)
    # Uma segunda incursão, de outro tier, para o filtro ter o que esconder.
    montar_conteudo(cog, incursao_id="t4", tier=4, salas=salas_sem_combate())
    assert {i.tier for i in cog.incursoes.values()} == {2, 4}

    # O autocomplete lê o tier que já está preenchido no mesmo comando.
    async def sugeridas(tier_digitado):
        inter = FakeInteraction(canal, JOGADORES[0], **{"tier": tier_digitado})
        return {c.value for c in await cog._sugerir_incursoes(inter, "")}

    assert await sugeridas(2) == {"t"}, await sugeridas(2)
    assert await sugeridas(4) == {"t4"}, await sugeridas(4)
    assert await sugeridas(1) == set(), await sugeridas(1)
    # Sem tier digitado, a lista é inteira — é o caso de quem só navega.
    assert await sugeridas(None) == {"t", "t4"}

    # Entrar com o tier errado é recusado, e a resposta diz qual é o certo.
    await heroi(conn, JOGADORES[0], "Veterano", 3)
    errado = FakeInteraction(canal, JOGADORES[0])
    await cog.entrar.callback(cog, errado, 4, "t", personagem="Veterano")
    assert "não é de tier 4" in leu(errado), leu(errado)
    assert not await db.run_do_canal(conn, CANAL), "abriu run com o tier errado"

    # Tier sem incursão nenhuma avisa isso, em vez de "não conheço o id".
    vazio = FakeInteraction(canal, JOGADORES[0])
    await cog.entrar.callback(cog, vazio, 1, "t", personagem="Veterano")
    assert "tier 1" in leu(vazio), leu(vazio)

    # E com o tier certo a run abre.
    ok = FakeInteraction(canal, JOGADORES[0])
    await cog.entrar.callback(cog, ok, 2, "t", personagem="Veterano")
    assert await db.run_do_canal(conn, CANAL), leu(ok)

    print("  o tier filtra a lista e barra o entrar fora dele: ok")


async def caso_o_listar_filtra_e_nao_mostra_o_id():
    """A vitrine das incursões: filtro por tier, sem id e sem contagem."""
    conn, canal, cog, incursao = await preparar(tier_incursao=2)
    montar_conteudo(cog, incursao_id="t4", tier=4, salas=salas_sem_combate())

    def campos(inter):
        return {f.name: f.value for f in inter._mensagem_resposta.embeds[0].fields}

    tudo = FakeInteraction(canal, JOGADORES[0])
    await cog.listar.callback(cog, tudo)
    assert len(campos(tudo)) == 2, campos(tudo)

    so2 = FakeInteraction(canal, JOGADORES[0])
    await cog.listar.callback(cog, so2, 2)
    nomes = campos(so2)
    assert len(nomes) == 1, nomes
    assert "tier 2" in (so2._mensagem_resposta.embeds[0].title or "").lower()

    # O id do arquivo não aparece — o jogador escolhe na lista do `entrar`.
    texto = " ".join(list(nomes) + list(nomes.values()))
    assert "`t`" not in texto and "t4" not in texto, texto
    # Nem quantas salas a run tem, nem os MEs: não mudam a escolha dele.
    assert "salas + objetivo" not in texto and "MEs" not in texto, texto

    # Tier sem nada avisa, em vez de mostrar um embed vazio.
    vazio = FakeInteraction(canal, JOGADORES[0])
    await cog.listar.callback(cog, vazio, 5)
    assert "tier 5" in leu(vazio), leu(vazio)

    print("  o listar filtra por tier e esconde o id e a contagem: ok")


async def caso_o_tier_tem_autocompletar_com_o_que_existe():
    """A lista do tier oferece só os tiers que TÊM incursão, e quantas.

    Uma lista fixa de 1 a 5 ofereceria tier vazio — hoje não há conteúdo de
    tier 3 nem de 5 —, e o jogador só descobriria isso no campo seguinte, com
    o autocompletar do id vindo vazio e sem explicação nenhuma.
    """
    conn, canal, cog, incursao = await preparar(tier_incursao=2)
    montar_conteudo(cog, incursao_id="t2b", tier=2, salas=salas_sem_combate())
    montar_conteudo(cog, incursao_id="t4", tier=4, salas=salas_sem_combate())

    async def sugeridos(digitado=""):
        inter = FakeInteraction(canal, JOGADORES[0])
        return await cog._sugerir_tiers(inter, digitado)

    opcoes = await sugeridos()
    assert [o.value for o in opcoes] == [2, 4], [o.value for o in opcoes]
    # O valor é NÚMERO: é ele que chega ao comando, que pede um int.
    assert all(isinstance(o.value, int) for o in opcoes), opcoes
    # E o rótulo conta quantas, com o plural certo.
    rotulos = {o.value: o.name for o in opcoes}
    assert rotulos[2] == "Tier 2 — 2 incursões", rotulos[2]
    assert rotulos[4] == "Tier 4 — 1 incursão", rotulos[4]

    # Digitar estreita.
    assert [o.value for o in await sugeridos("4")] == [4]
    assert await sugeridos("3") == []

    # A de tier livre conta em TODOS, porque é jogável em todos.
    montar_conteudo(cog, incursao_id="livre", tier=TIER_MAXIMO,
                    salas=salas_sem_combate())
    todos = {o.value: o.name for o in await sugeridos()}
    assert sorted(todos) == [1, 2, 3, 4, 5], sorted(todos)
    assert todos[3] == "Tier 3 — 1 incursão", todos[3]
    assert todos[2] == "Tier 2 — 3 incursões", todos[2]

    print("  o tier se autocompleta com o que existe, e conta quantas: ok")


async def main():
    try:
        caso_tier_a_cada_dois_niveis()
        caso_o_ajuste_de_cd_segue_o_bonus_de_proficiencia()
        caso_so_sobe_quem_esta_abaixo()
        await caso_entrar_recusa_quem_esta_acima()
        await caso_entrar_escolhe_o_que_cabe()
        await caso_botao_entrar_respeita_o_tier()
        await caso_menu_velho_nao_fura_a_regra()
        await caso_incursao_sem_tier_e_aberta()
        await caso_recrutamento_mostra_o_tier()
        await caso_o_filtro_de_tier_estreita_a_lista_e_o_entrar()
        await caso_o_listar_filtra_e_nao_mostra_o_id()
        await caso_o_tier_tem_autocompletar_com_o_que_existe()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        (Path(__file__).resolve().parent / "teste_tier.db").unlink(missing_ok=True)


asyncio.run(main())
print("TESTES DE TIER PASSARAM")
