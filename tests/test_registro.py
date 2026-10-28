"""Cadastro por classe: /ficha registrar, as proficiencias e o /ficha upar."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import classes as cl, config, database as db  # noqa: E402
from src.rules import PERICIAS  # noqa: E402
from src.cogs.ficha import LIMITE_PERSONAGENS, Ficha, SeletorPericias  # noqa: E402
from src.rules import NIVEL_MAXIMO, TIER_MAXIMO, chave_comparacao, tier  # noqa: E402
from fakes import (  # noqa: E402
    resolver_fluxo,
    leu,
    pericias_cheias,
    menu_de,
    CANAL,
    CLASSE_PADRAO,
    GUILD,
    JOGADORES,
    FakeBot,
    FakeCanal,
    FakeInteraction,
)

_ABERTAS = []


class Escolha:
    """O dublê de app_commands.Choice."""

    def __init__(self, value, name=None):
        self.value = value
        self.name = name or value


async def preparar():
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass
    config.DB_PATH = Path(__file__).resolve().parent / "teste_registro.db"
    config.DB_PATH.unlink(missing_ok=True)
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    canal = FakeCanal(CANAL)
    return conn, canal, Ficha(FakeBot(conn, canal))


async def registrar(ficha, canal, dono, nome, classe=CLASSE_PADRAO, pericias=(), **kw):
    """Roda /ficha registrar e resolve o menu de proficiencias que vem depois."""
    inter = FakeInteraction(canal, dono)
    tarefa = asyncio.create_task(
        ficha.registrar.callback(ficha, inter, nome, Escolha(classe), **kw)
    )
    # a corrotina passa pelo banco, que roda noutra thread: sleep(0) nao basta
    for _ in range(250):
        await asyncio.sleep(0.02)
        if menu_de(inter) is not None or tarefa.done():
            break
    view = menu_de(inter)
    if view is not None and not tarefa.done():
        view.menu._values = list(pericias)
        await view._escolher(FakeInteraction(canal, dono))
    await tarefa
    return inter


def caso_tabela_das_classes():
    """Toda classe jogavel tem numeros coerentes em todos os tiers."""
    for classe in cl.CLASSES.values():
        anterior = None
        for t in sorted(classe.tiers):
            n = classe.tiers[t]
            assert n.hp > 0 and n.ca > 0 and n.pericias > 0, (classe.nome, t)
            assert n.bonus_proficiencia > n.bonus_pericia, (classe.nome, t)
            assert "d" in n.dano, (classe.nome, t, n.dano)
            if anterior:
                # a progressao nunca anda para tras
                assert n.hp > anterior.hp, (classe.nome, t)
                assert n.ca >= anterior.ca and n.acerto >= anterior.acerto, (classe.nome, t)
                assert n.pericias >= anterior.pericias, (classe.nome, t)
            anterior = n

    # o nome, o id e a grafia sem acento levam a mesma classe
    assert cl.classe("Xamã") is cl.classe("xama") is cl.classe("xama")
    assert cl.classe("LADINO") is cl.CLASSES["ladino"]
    # Da lista de pendentes, e nao de um nome fixo: cada classe nova que
    # entra tirava este teste do ar.
    for nome in cl.CLASSES_PENDENTES:
        assert cl.classe(nome) is None, f"{nome} nao tem tabela e nao pode entrar"
    assert len(cl.CLASSES) + len(cl.CLASSES_PENDENTES) == len(cl.CLASSES_PREVISTAS)
    print(f"  {len(cl.CLASSES)} classes com tabela, {len(cl.CLASSES_PENDENTES)} previstas: ok")


async def caso_registro_por_classe():
    conn, canal, ficha = await preparar()
    dono = JOGADORES[0]
    antes = len(canal.mensagens)

    inter = await registrar(
        ficha, canal, dono, "Vhalor", "ladino", ["Furtividade", "Acrobacia"]
    )
    assert "Ladino" in inter.resposta and "nivel 1" in inter.resposta

    salvo = await db.personagem_por_nome(conn, GUILD, dono, "Vhalor")
    assert salvo is not None
    assert salvo["classe"] == "ladino"
    assert salvo["nivel"] == 1, "todo personagem comeca no nivel 1"
    assert sorted(salvo["pericias"]) == ["Acrobacia", "Furtividade"]

    # os numeros nao foram digitados: vieram da tabela do Ladino no tier 1
    t1 = cl.CLASSES["ladino"].numeros(1)
    assert (salvo["ca"], salvo["bonus_ataque"], salvo["dano_arma"], salvo["hp_max"]) == (
        t1.ca, t1.acerto, t1.dano, t1.hp,
    )

    # o canal fica sabendo
    publicas = [m for m in canal.mensagens[antes:] if "registrou" in (m.content or "")]
    assert len(publicas) == 1 and "Ladino" in publicas[0].content
    print("  registrar por classe deriva todos os numeros: ok")


async def caso_menu_limita_as_proficiencias():
    conn, canal, ficha = await preparar()
    dono = JOGADORES[0]

    # o Barbaro escolhe 3; o Ladino, 6
    inter = FakeInteraction(canal, dono)
    tarefa = asyncio.create_task(
        ficha.registrar.callback(ficha, inter, "Grog", Escolha("barbaro"))
    )
    for _ in range(250):
        await asyncio.sleep(0.02)
        if menu_de(inter) is not None or tarefa.done():
            break
    view = menu_de(inter)
    assert isinstance(view, SeletorPericias)
    cota = cl.CLASSES["barbaro"].numeros(1).pericias
    assert view.menu.max_values == cota == 3
    # EXATAMENTE a cota, nao "ate": o menu que aceitava menos deixava o
    # personagem nascer com 2 proficiencias de 3, e as perdidas nao
    # voltavam — nada no bot pedia de novo.
    assert view.menu.min_values == cota, (
        "o menu nao pode aceitar menos que a cota"
    )
    view.menu._values = ["Atletismo", "Intimidação", "Sobrevivência"]
    await view._escolher(FakeInteraction(canal, dono))
    await tarefa

    salvo = await db.personagem_por_nome(conn, GUILD, dono, "Grog")
    assert sorted(salvo["pericias"]) == sorted(
        ["Atletismo", "Intimidação", "Sobrevivência"]
    ), salvo["pericias"]
    assert salvo["pericias_permitidas"] == 3
    print("  o menu de proficiencias respeita o limite da classe: ok")


async def caso_classe_pendente_e_recusada():
    conn, canal, ficha = await preparar()
    inter = FakeInteraction(canal, JOGADORES[0])
    # A primeira que ainda nao tem tabela. Acabando as pendentes, serve
    # qualquer nome que nao exista: a recusa e a mesma.
    pendente = cl.CLASSES_PENDENTES[0] if cl.CLASSES_PENDENTES else "Necromante"
    await ficha.registrar.callback(
        ficha, inter, "Elminster",
        Escolha(chave_comparacao(pendente).replace(" ", "_"), pendente),
    )
    assert "ainda nao esta pronta" in inter.resposta, inter.resposta
    assert "Ladino" in inter.resposta, "a recusa lista o que da para jogar"
    assert await db.listar_personagens(conn, GUILD, JOGADORES[0]) == []
    print("  classe sem tabela e recusada com a lista do que existe: ok")


async def caso_nome_repetido_e_limite():
    conn, canal, ficha = await preparar()
    dono = JOGADORES[0]
    await registrar(ficha, canal, dono, "Vhalor", "monge", ["Acrobacia"])

    repetido = FakeInteraction(canal, dono)
    await ficha.registrar.callback(ficha, repetido, "vhalor", Escolha("monge"))
    assert "ja tem um personagem" in repetido.resposta
    assert len(await db.listar_personagens(conn, GUILD, dono)) == 1

    outro = JOGADORES[1]
    for i in range(LIMITE_PERSONAGENS):
        await db.criar_personagem(conn, GUILD, outro, f"P{i}", CLASSE_PADRAO, [])
    cheio = FakeInteraction(canal, outro)
    await ficha.registrar.callback(ficha, cheio, "Mais um", Escolha("monge"))
    assert str(LIMITE_PERSONAGENS) in cheio.resposta
    assert menu_de(cheio) is None, "nem chega a abrir o menu de pericias"
    print("  nome repetido e limite de personagens barram o cadastro: ok")


async def caso_upar_sobe_um_nivel():
    conn, canal, ficha = await preparar()
    dono = JOGADORES[0]
    pid = await db.criar_personagem(
        conn, GUILD, dono, "Vhalor", "ladino",
        pericias_cheias("ladino"),
    )

    # O upar anda de tier em tier, e o nivel so sobe depois da ultima
    # decisao: o Ladino decide a Expertise no tier 2, entao ate ela
    # chegar ele continua no tier 1.
    inter = FakeInteraction(canal, dono)
    await ficha.upar.callback(ficha, inter)
    no_meio = await db.buscar_personagem(conn, pid)
    assert tier(no_meio["nivel"]) == 1, "subiu antes de decidir"
    assert "Decida agora" in leu(inter) and "Expertise" in leu(inter)
    assert menu_de(inter) is not None
    assert not any("tier 2" in (m.content or "") for m in canal.mensagens), (
        "o canal soube antes de a subida acontecer"
    )

    # decidindo, o nivel sobe E o canal fica sabendo
    menu_de(inter).menu._values = ["Furtividade", "Acrobacia"]
    gravando = FakeInteraction(canal, dono)
    await menu_de(inter)._escolher(gravando)
    atualizado = await db.buscar_personagem(conn, pid)
    assert tier(atualizado["nivel"]) == 2, atualizado["nivel"]
    assert atualizado["escolhas"] == {
        "expertise_1": ["Furtividade", "Acrobacia"]
    }
    assert atualizado["pendencias"] == []
    assert any("tier 2" in (m.content or "") for m in canal.mensagens), "o canal soube"

    t1, t2 = cl.CLASSES["ladino"].numeros(1), cl.CLASSES["ladino"].numeros(3)
    assert atualizado["hp_max"] == t2.hp != t1.hp
    assert atualizado["dano_arma"] == t2.dano

    # e o voltar desfaz, para quem upou sem querer
    volta = FakeInteraction(canal, dono)
    await ficha.voltar.callback(ficha, volta)
    de_volta = await db.buscar_personagem(conn, pid)
    assert tier(de_volta["nivel"]) == 1
    assert de_volta["hp_max"] == t1.hp
    assert "tier 1" in volta.resposta, volta.resposta

    # no tier 1 nao da para descer mais
    fundo = FakeInteraction(canal, dono)
    await ficha.voltar.callback(ficha, fundo)
    assert "nao da para descer" in fundo.resposta, fundo.resposta
    print("  upar sobe um tier e voltar desfaz: ok")


async def caso_upar_avisa_pericia_nova_e_para_no_teto():
    conn, canal, ficha = await preparar()
    dono = JOGADORES[0]
    # Monge ganha a 6a pericia no tier 3 (nivel 5)
    pid = await db.criar_personagem(
        conn, GUILD, dono, "Kaelen", "monge", ["Acrobacia", "Atletismo"], nivel=4
    )
    inter = FakeInteraction(canal, dono)
    await ficha.upar.callback(ficha, inter)
    assert "proficiencia" in inter.resposta, inter.resposta
    # E o menu das vagas novas abre junto, por followup: `/ficha pericias`
    # saiu, e sem isto as proficiencias do tier novo nao teriam onde entrar.
    assert inter.view_do_seguimento is not None, inter.seguimento
    menu = inter.view_do_seguimento.menu
    assert menu.max_values == 6, menu.max_values

    # e o que o jogador escolher no menu e gravado na hora
    menu._values = ["Acrobacia", "Atletismo", "Furtividade", "Percepção"]
    gravando = FakeInteraction(canal, dono)
    await inter.view_do_seguimento._escolher(gravando)
    salvo = await db.buscar_personagem(conn, pid)
    assert "Furtividade" in salvo["pericias"], salvo["pericias"]

    # empurra ate o teto e confirma que o comando para por ali
    await db.atualizar_personagem(conn, pid, "nivel", NIVEL_MAXIMO)
    teto = FakeInteraction(canal, dono)
    await ficha.upar.callback(ficha, teto)
    assert "tier maximo" in teto.resposta, teto.resposta
    assert tier((await db.buscar_personagem(conn, pid))["nivel"]) == TIER_MAXIMO
    print(f"  upar abre o menu da pericia nova e para no tier {TIER_MAXIMO}: ok")




async def caso_a_escolha_do_tier_1_abre_no_registro():
    """A decisão do tier 1 é do registro, não da primeira subida.

    Antes ela ficava pendente e só aparecia ao virar tier 2, junto com a do
    tier 2 — o jogador escolhia a magia de tier 1 sempre um tier atrasado.
    """
    conn, canal, ficha = await preparar()
    inter = await registrar(
        ficha, canal, JOGADORES[0], "Novato", "clerigo", ["Religião"]
    )
    personagem = await db.personagem_por_nome(conn, GUILD, JOGADORES[0], "Novato")
    assert personagem is not None, "nao registrou"

    pendentes = {h.id for _t, h in personagem["pendencias"]}
    assert "magia_t1" in pendentes, pendentes
    # E o menu dela saiu de verdade: a resposta da interacao ja tinha sido
    # gasta no seletor de pericias, entao a decisao vai por followup.
    assert inter.seguimento and "Decida agora" in inter.seguimento, inter.seguimento
    print("  a escolha do tier 1 abre no registro: ok")


async def caso_classe_sem_escolha_no_tier_1_nao_abre_nada():
    """Quem não decide nada no tier 1 não leva menu nenhum no registro."""
    conn, canal, ficha = await preparar()
    # O ladino decide no tier 2 (Expertise), nao no 1.
    inter = await registrar(
        ficha, canal, JOGADORES[1], "Gatuno", "ladino", ["Furtividade"]
    )
    personagem = await db.personagem_por_nome(conn, GUILD, JOGADORES[1], "Gatuno")
    assert personagem is not None
    assert not personagem["pendencias"], personagem["pendencias"]
    assert inter.seguimento is None, inter.seguimento
    print("  classe sem decisao no tier 1 nao abre menu no registro: ok")


async def caso_alterar_refaz_a_decisao_do_tier():
    """O /ficha alterar esquece a decisao do tier atual, sem mexer no nivel.

    O /ficha voltar ja fazia isso pelo caminho longo: descer um tier, perder
    os numeros, e subir de novo. Aqui o nivel fica onde esta.
    """
    conn, canal, ficha = await preparar()
    dono = JOGADORES[0]
    pid = await db.criar_personagem(
        conn, GUILD, dono, "Vhalor", "ladino",
        pericias_cheias("ladino"),
    )

    # sobe para o tier 2 e decide a Expertise
    subir = FakeInteraction(canal, dono)
    await ficha.upar.callback(ficha, subir)
    menu_de(subir).menu._values = ["Furtividade"]
    await menu_de(subir)._escolher(FakeInteraction(canal, dono))
    antes = await db.buscar_personagem(conn, pid)
    assert antes["escolhas"] == {"expertise_1": ["Furtividade"]}
    assert tier(antes["nivel"]) == 2

    # nunca jogou no tier 2: da para refazer
    inter = FakeInteraction(canal, dono)
    await ficha.alterar.callback(ficha, inter)

    # O menu abre, mas NADA foi apagado ainda: fechar aqui deixaria a
    # ficha como estava. Apagar antes de perguntar era o desenho velho,
    # e ele criava um estado sem decisao nenhuma se o jogador desistisse.
    assert "Decida agora" in leu(inter), leu(inter)
    assert menu_de(inter) is not None, "o menu da decisao nao abriu"
    no_meio = await db.buscar_personagem(conn, pid)
    assert no_meio["escolhas"] == {"expertise_1": ["Furtividade"]}, (
        no_meio["escolhas"]
    )

    # e respondendo, a decisao velha e trocada pela nova
    menu_de(inter).menu._values = ["Acrobacia"]
    await menu_de(inter)._escolher(FakeInteraction(canal, dono))
    depois = await db.buscar_personagem(conn, pid)
    assert depois["escolhas"] == {"expertise_1": ["Acrobacia"]}, depois["escolhas"]
    assert tier(depois["nivel"]) == 2, "o alterar nao pode mexer no nivel"
    assert not depois["pendencias"], depois["pendencias"]
    print("  o alterar troca a decisao sem apagar antes de perguntar: ok")


async def caso_alterar_trava_depois_de_jogar_naquele_tier():
    """Jogou uma incursao no tier, a decisao daquele tier esta fechada."""
    conn, canal, ficha = await preparar()
    dono = JOGADORES[0]
    pid = await db.criar_personagem(
        conn, GUILD, dono, "Vhalor", "ladino",
        pericias_cheias("ladino"),
    )
    subir = FakeInteraction(canal, dono)
    await ficha.upar.callback(ficha, subir)
    menu_de(subir).menu._values = ["Furtividade"]
    await menu_de(subir)._escolher(FakeInteraction(canal, dono))

    # uma run no tier 2, que e onde ele esta
    run_id = await db.criar_run(conn, GUILD, CANAL, "t", dono)
    await db.adicionar_participante(conn, run_id, dono, pid, tier=2)
    assert await db.tiers_jogados(conn, pid) == {2}

    inter = FakeInteraction(canal, dono)
    await ficha.alterar.callback(ficha, inter)
    assert "ja entrou numa incursao" in inter.resposta, inter.resposta
    intacto = await db.buscar_personagem(conn, pid)
    assert intacto["escolhas"] == {"expertise_1": ["Furtividade"]}, intacto["escolhas"]
    print("  jogou no tier, a decisao daquele tier nao se desfaz: ok")


async def caso_a_run_sem_tier_nao_trava():
    """Run antiga, anterior a coluna `tier`, nao tranca nada.

    O NULL ali nao e "jogou no tier nenhum": e "nao da para saber". Chutar
    trancaria um tier que talvez nunca tenha sido jogado.
    """
    conn, canal, ficha = await preparar()
    dono = JOGADORES[0]
    pid = await db.criar_personagem(
        conn, GUILD, dono, "Vhalor", "ladino",
        pericias_cheias("ladino"),
    )
    subir = FakeInteraction(canal, dono)
    await ficha.upar.callback(ficha, subir)
    menu_de(subir).menu._values = ["Furtividade"]
    await menu_de(subir)._escolher(FakeInteraction(canal, dono))

    run_id = await db.criar_run(conn, GUILD, CANAL, "t", dono)
    await db.adicionar_participante(conn, run_id, dono, pid)  # sem tier
    assert await db.tiers_jogados(conn, pid) == set()

    inter = FakeInteraction(canal, dono)
    await ficha.alterar.callback(ficha, inter)
    # Nao travou: o menu abriu. (O alterar nao apaga antes de
    # perguntar, entao a decisao velha continua la ate a nova chegar.)
    assert menu_de(inter) is not None, leu(inter)
    print("  run sem tier gravado nao tranca o alterar: ok")


async def caso_remover_apaga_a_ficha_de_outro():
    """O /ficha remover e do mestre, e alcanca a ficha de qualquer jogador."""
    conn, canal, ficha = await preparar()
    dono, mestre = JOGADORES[0], JOGADORES[1]
    pid = await db.criar_personagem(
        conn, GUILD, dono, "Vhalor", "ladino",
        pericias_cheias("ladino"),
    )

    inter = FakeInteraction(canal, mestre)
    await ficha.remover.callback(ficha, inter, str(pid))

    assert await db.buscar_personagem(conn, pid) is None, "a ficha nao foi apagada"
    assert "Vhalor" in inter.resposta, inter.resposta
    # o comando e so para admin: a permissao vem declarada, nao checada a mao
    assert ficha.remover.default_permissions.manage_guild, (
        "o remover tem de exigir manage_guild"
    )
    print("  o mestre apaga a ficha de outro jogador: ok")


async def caso_remover_respeita_run_viva():
    """Ninguem perde a ficha no meio de uma incursao."""
    conn, canal, ficha = await preparar()
    dono, mestre = JOGADORES[0], JOGADORES[1]
    pid = await db.criar_personagem(
        conn, GUILD, dono, "Vhalor", "ladino",
        pericias_cheias("ladino"),
    )
    run_id = await db.criar_run(conn, GUILD, CANAL, "t", dono)
    await db.adicionar_participante(conn, run_id, dono, pid, tier=1)

    inter = FakeInteraction(canal, mestre)
    await ficha.remover.callback(ficha, inter, str(pid))

    assert "esta na run" in inter.resposta, inter.resposta
    assert await db.buscar_personagem(conn, pid) is not None, "apagou mesmo assim"
    print("  a ficha de quem esta numa run viva nao e apagada: ok")


async def caso_alterar_abre_as_pericias_no_tier_que_as_da():
    """Num tier que abriu vaga de proficiencia, o alterar deixa refaze-las.

    Sem isto o jogador ficava preso na escolha do dia do registro: as
    decisoes dava para refazer, as pericias nao. O Mago ganha pericia no
    tier 3 (de 4 para 5).
    """
    conn, canal, ficha = await preparar()
    dono = JOGADORES[0]
    pid = await db.criar_personagem(
        conn, GUILD, dono, "Zarth", "mago", ["Arcanismo", "Historia"]
    )
    # sobe ate o tier 3, resolvendo o que aparecer pelo caminho
    for _ in range(2):
        subir = FakeInteraction(canal, dono)
        await ficha.upar.callback(ficha, subir)
        await resolver_fluxo(canal, dono, subir)
    personagem = await db.buscar_personagem(conn, pid)
    assert tier(personagem["nivel"]) == 3, personagem["nivel"]

    # o tier 3 do mago da pericia: de 4 para 5
    numeros = cl.CLASSES["mago"]
    assert numeros.numeros(5).pericias > numeros.numeros(3).pericias

    inter = FakeInteraction(canal, dono)
    await ficha.alterar.callback(ficha, inter)

    # O alterar pergunta as DECISOES primeiro e as pericias depois, numa
    # cadeia so. Percorrendo ate o fim, o menu de pericias tem de
    # aparecer com a cota do tier.
    cota = numeros.numeros(5).pericias
    vistos = []
    atual = inter
    for _ in range(8):
        view = menu_de(atual)
        if view is None:
            break
        vistos.append(view.menu.max_values)
        quantas = max(1, view.menu.min_values or 1)
        view.menu._values = [o.value for o in view.menu.options[:quantas]]
        seguinte = FakeInteraction(canal, dono)
        await view._escolher(seguinte)
        atual = seguinte
    assert cota in vistos, (cota, vistos)

    # e o que o menu gravou e a cota CHEIA: nao da para sair com menos
    depois = await db.buscar_personagem(conn, pid)
    proprias = [
        x for x in depois["pericias"]
        if x not in (depois.get("pericias_extras") or [])
    ]
    assert len(proprias) == cota, (proprias, cota)
    print("  o alterar abre as pericias no tier que as da: ok")


async def caso_alterar_nao_abre_pericia_em_tier_que_nao_da():
    """Tier sem vaga nova nao oferece pericia — so o que ele de fato deu.

    O Guerreiro tem 3 proficiencias em todos os tiers: a cota nunca cresce.
    """
    conn, canal, ficha = await preparar()
    dono = JOGADORES[0]
    pid = await db.criar_personagem(
        conn, GUILD, dono, "Bram", "guerreiro", ["Atletismo"]
    )
    subir = FakeInteraction(canal, dono)
    await ficha.upar.callback(ficha, subir)
    if menu_de(subir) is not None:
        opcoes = [o.value for o in menu_de(subir).menu.options]
        menu_de(subir).menu._values = [opcoes[0]]
        await menu_de(subir)._escolher(FakeInteraction(canal, dono))

    guerreiro = cl.CLASSES["guerreiro"]
    assert guerreiro.numeros(3).pericias == guerreiro.numeros(1).pericias

    inter = FakeInteraction(canal, dono)
    await ficha.alterar.callback(ficha, inter)
    assert inter.view_do_seguimento is None, (
        "o tier 2 do guerreiro nao da pericia: o menu nao devia abrir"
    )
    print("  tier sem vaga de pericia nao oferece pericia: ok")


async def main():
    try:
        caso_tabela_das_classes()
        await caso_registro_por_classe()
        await caso_a_escolha_do_tier_1_abre_no_registro()
        await caso_classe_sem_escolha_no_tier_1_nao_abre_nada()
        await caso_alterar_refaz_a_decisao_do_tier()
        await caso_alterar_trava_depois_de_jogar_naquele_tier()
        await caso_a_run_sem_tier_nao_trava()
        await caso_remover_apaga_a_ficha_de_outro()
        await caso_remover_respeita_run_viva()
        await caso_alterar_abre_as_pericias_no_tier_que_as_da()
        await caso_alterar_nao_abre_pericia_em_tier_que_nao_da()
        await caso_menu_limita_as_proficiencias()
        await caso_classe_pendente_e_recusada()
        await caso_nome_repetido_e_limite()
        await caso_upar_sobe_um_nivel()
        await caso_upar_avisa_pericia_nova_e_para_no_teto()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        (Path(__file__).resolve().parent / "teste_registro.db").unlink(missing_ok=True)


asyncio.run(main())
print("TESTES DE REGISTRO PASSARAM")
