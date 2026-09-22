"""Cadastro por classe: /ficha registrar, as proficiencias e o /ficha upar."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import classes as cl, config, database as db  # noqa: E402
from src.cogs.ficha import LIMITE_PERSONAGENS, Ficha, SeletorPericias  # noqa: E402
from src.rules import NIVEL_MAXIMO, tier  # noqa: E402
from fakes import (  # noqa: E402
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
        if inter.view_enviada is not None or tarefa.done():
            break
    view = inter.view_enviada
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
    assert cl.classe("mago") is None, "classe ainda nao escrita nao pode ser escolhida"
    assert "Mago" in cl.CLASSES_PENDENTES
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
        if inter.view_enviada is not None or tarefa.done():
            break
    view = inter.view_enviada
    assert isinstance(view, SeletorPericias)
    assert view.menu.max_values == cl.CLASSES["barbaro"].numeros(1).pericias == 3
    assert view.menu.min_values == 0, "da para deixar para escolher depois"
    view.menu._values = ["Atletismo", "Intimidação"]
    await view._escolher(FakeInteraction(canal, dono))
    await tarefa

    salvo = await db.personagem_por_nome(conn, GUILD, dono, "Grog")
    assert sorted(salvo["pericias"]) == ["Atletismo", "Intimidação"]
    assert salvo["pericias_permitidas"] == 3
    print("  o menu de proficiencias respeita o limite da classe: ok")


async def caso_classe_pendente_e_recusada():
    conn, canal, ficha = await preparar()
    inter = FakeInteraction(canal, JOGADORES[0])
    await ficha.registrar.callback(ficha, inter, "Elminster", Escolha("mago", "Mago"))
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
    assert cheio.view_enviada is None, "nem chega a abrir o menu de pericias"
    print("  nome repetido e limite de personagens barram o cadastro: ok")


async def caso_upar_sobe_um_nivel():
    conn, canal, ficha = await preparar()
    dono = JOGADORES[0]
    pid = await db.criar_personagem(conn, GUILD, dono, "Vhalor", "ladino", ["Furtividade"])

    # nivel 1 -> 2: mesmo tier, os numeros nao mudam
    inter = FakeInteraction(canal, dono)
    await ficha.upar.callback(ficha, inter)
    assert (await db.buscar_personagem(conn, pid))["nivel"] == 2
    assert "nivel 2" in inter.resposta and "nivel 3" in inter.resposta, inter.resposta

    # nivel 2 -> 3: vira o tier e os numeros sobem
    virada = FakeInteraction(canal, dono)
    await ficha.upar.callback(ficha, virada)
    atualizado = await db.buscar_personagem(conn, pid)
    assert atualizado["nivel"] == 3 and tier(3) == 2
    assert "Subiu de tier" in virada.resposta, virada.resposta
    t1, t2 = cl.CLASSES["ladino"].numeros(2), cl.CLASSES["ladino"].numeros(3)
    assert atualizado["hp_max"] == t2.hp != t1.hp
    assert atualizado["dano_arma"] == t2.dano
    print("  upar sobe um nivel e os numeros acompanham o tier: ok")


async def caso_upar_avisa_pericia_nova_e_para_no_teto():
    conn, canal, ficha = await preparar()
    dono = JOGADORES[0]
    # Monge ganha a 6a pericia no tier 3 (nivel 5)
    pid = await db.criar_personagem(
        conn, GUILD, dono, "Kaelen", "monge", ["Acrobacia", "Atletismo"], nivel=4
    )
    inter = FakeInteraction(canal, dono)
    await ficha.upar.callback(ficha, inter)
    assert "/ficha pericias" in inter.resposta, inter.resposta

    # empurra ate o teto e confirma que o comando para por ali
    await db.atualizar_personagem(conn, pid, "nivel", NIVEL_MAXIMO)
    teto = FakeInteraction(canal, dono)
    await ficha.upar.callback(ficha, teto)
    assert "nivel maximo" in teto.resposta
    assert (await db.buscar_personagem(conn, pid))["nivel"] == NIVEL_MAXIMO
    print(f"  upar avisa a pericia nova e para no nivel {NIVEL_MAXIMO}: ok")


async def main():
    try:
        caso_tabela_das_classes()
        await caso_registro_por_classe()
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
