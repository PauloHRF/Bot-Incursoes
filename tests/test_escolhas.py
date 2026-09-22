"""Escolhas de tier: Fighting Style, Expertise, Primal Knowledge e a do Xamã."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import classes as cl, config, database as db  # noqa: E402
from src.cogs.ficha import (  # noqa: E402
    Ficha,
    SeletorEscolha,
    SeletorOpcao,
    SeletorPericiasDaEscolha,
    embed_ficha,
)
from src.rules import mod_pericia  # noqa: E402
from fakes import (  # noqa: E402
    CANAL,
    GUILD,
    JOGADORES,
    FakeBot,
    FakeCanal,
    FakeInteraction,
)

_ABERTAS = []


async def preparar():
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass
    config.DB_PATH = Path(__file__).resolve().parent / "teste_escolhas.db"
    config.DB_PATH.unlink(missing_ok=True)
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    canal = FakeCanal(CANAL)
    return conn, canal, Ficha(FakeBot(conn, canal))


async def escolher(cog, canal, dono, personagem_id, habilidade_id, valores):
    """Vai do menu de decisões até gravar, como o jogador faria."""
    abrindo = FakeInteraction(canal, dono)
    await cog.abrir_escolha(abrindo, personagem_id, habilidade_id)
    view = abrindo.view_enviada
    assert view is not None, abrindo.resposta
    view.menu._values = list(valores)
    gravando = FakeInteraction(canal, dono)
    await view._escolher(gravando)
    return gravando


def caso_catalogo_das_escolhas():
    """Toda ESCOLHA do documento sabe dizer o que o jogador decide."""
    decidiveis = []
    for classe in cl.CLASSES.values():
        for _t, h in classe.habilidades_ate(10):
            if h.tipo != cl.ESCOLHA:
                continue
            assert h.decidivel, f"{classe.nome}/{h.nome} sem forma de escolha"
            forma = h.escolha
            assert forma["tipo"] in ("opcao", "pericias"), forma
            if forma["tipo"] == "opcao":
                assert len(forma["opcoes"]) >= 2
                for o in forma["opcoes"]:
                    assert o["id"] and o["nome"] and o["texto"]
                    assert o["efeito"], o
            else:
                assert forma["quantidade"] >= 1
                assert forma["entre"] in ("proficientes", "todas")
                assert forma["aplica"] in ("expertise", "proficiencia")
            decidiveis.append(h.id)
    assert set(decidiveis) == {
        "fighting_style", "expertise_1", "expertise_2",
        "primal_knowledge", "escolha_totemica",
    }, decidiveis
    print(f"  as {len(decidiveis)} escolhas do documento estao no catalogo: ok")


def caso_pendencias_por_nivel():
    # o Guerreiro decide no tier 2 (nivel 3)
    assert cl.escolhas_pendentes("guerreiro", 2, {}) == []
    assert [h.id for _t, h in cl.escolhas_pendentes("guerreiro", 3, {})] == [
        "fighting_style"
    ]
    # decidido, sai da lista
    assert cl.escolhas_pendentes("guerreiro", 3, {"fighting_style": "pesado"}) == []
    # o Ladino decide duas vezes: tier 2 e tier 4
    assert len(cl.escolhas_pendentes("ladino", 8, {})) == 2
    print("  a pendencia aparece no tier certo e some quando decidida: ok")


async def caso_fighting_style_muda_os_numeros():
    conn, canal, cog = await preparar()
    dono = JOGADORES[0]
    pid = await db.criar_personagem(
        conn, GUILD, dono, "Grom", "guerreiro", ["Atletismo"], nivel=4
    )
    base = await db.buscar_personagem(conn, pid)
    assert [h.id for _t, h in base["pendencias"]] == ["fighting_style"]
    ca_base, acerto_base = base["ca"], base["bonus_ataque"]

    inter = await escolher(cog, canal, dono, pid, "fighting_style", ["defensivo"])
    assert "Defensivo" in inter.resposta

    depois = await db.buscar_personagem(conn, pid)
    assert depois["ca"] == ca_base + 1
    assert depois["bonus_ataque"] == acerto_base, "o defensivo nao mexe no acerto"
    assert depois["pendencias"] == []
    assert depois["escolhas"] == {"fighting_style": "defensivo"}

    # e a ficha mostra a decisao
    campos = {f.name: f.value for f in embed_ficha(depois, FakeInteraction(canal, dono).user).fields}
    assert "Defensivo" in campos["Escolhas"]
    assert f"CA **{ca_base + 1}**" in campos["Combate"], campos["Combate"]
    print("  Fighting Style muda CA ou acerto de verdade: ok")


async def caso_expertise_dobra_a_proficiencia():
    conn, canal, cog = await preparar()
    dono = JOGADORES[0]
    pid = await db.criar_personagem(
        conn, GUILD, dono, "Sombra", "ladino",
        ["Furtividade", "Acrobacia", "Percepção"], nivel=4,
    )
    antes = await db.buscar_personagem(conn, pid)
    sem = mod_pericia("Furtividade", antes["numeros"], antes["pericias"], None, antes["efeitos"])

    inter = await escolher(
        cog, canal, dono, pid, "expertise_1", ["Furtividade", "Acrobacia"]
    )
    assert "Furtividade" in inter.resposta

    depois = await db.buscar_personagem(conn, pid)
    com = mod_pericia(
        "Furtividade", depois["numeros"], depois["pericias"], None, depois["efeitos"]
    )
    assert com == sem + depois["numeros"].bonus_proficiencia, (sem, com)
    # quem ficou de fora nao muda
    fora = mod_pericia(
        "Percepção", depois["numeros"], depois["pericias"], None, depois["efeitos"]
    )
    assert fora == sem
    print("  Expertise dobra a proficiencia das pericias escolhidas: ok")


async def caso_expertise_so_oferece_o_que_tem_proficiencia():
    conn, canal, cog = await preparar()
    dono = JOGADORES[0]
    pid = await db.criar_personagem(
        conn, GUILD, dono, "Sombra", "ladino", ["Furtividade", "Acrobacia"], nivel=4
    )
    abrindo = FakeInteraction(canal, dono)
    await cog.abrir_escolha(abrindo, pid, "expertise_1")
    view = abrindo.view_enviada
    assert isinstance(view, SeletorPericiasDaEscolha)
    assert {o.label for o in view.menu.options} == {"Furtividade", "Acrobacia"}

    # sem nenhuma proficiencia, o bot manda escolher as pericias antes
    vazio = await db.criar_personagem(conn, GUILD, dono, "Cru", "ladino", [], nivel=4)
    inter = FakeInteraction(canal, dono)
    await cog.abrir_escolha(inter, vazio, "expertise_1")
    assert "proficiencias primeiro" in inter.resposta, inter.resposta
    print("  Expertise so oferece pericia com proficiencia: ok")


async def caso_primal_knowledge_da_proficiencia_extra():
    conn, canal, cog = await preparar()
    dono = JOGADORES[0]
    pid = await db.criar_personagem(
        conn, GUILD, dono, "Grog", "barbaro", ["Atletismo", "Intimidação", "Percepção"],
        nivel=4,
    )
    antes = await db.buscar_personagem(conn, pid)
    assert len(antes["pericias"]) == 3

    abrindo = FakeInteraction(canal, dono)
    await cog.abrir_escolha(abrindo, pid, "primal_knowledge")
    oferecidas = {o.label for o in abrindo.view_enviada.menu.options}
    assert "Atletismo" not in oferecidas, "nao oferece o que ele ja tem"
    assert "Natureza" in oferecidas

    await escolher(cog, canal, dono, pid, "primal_knowledge", ["Natureza", "Sobrevivência"])
    depois = await db.buscar_personagem(conn, pid)
    assert set(depois["pericias"]) == {
        "Atletismo", "Intimidação", "Percepção", "Natureza", "Sobrevivência"
    }
    assert depois["pericias_extras"] == ["Natureza", "Sobrevivência"]
    # as extras nao consomem a cota da classe (Barbaro tem 3)
    assert depois["numeros"].pericias == 3
    print("  Primal Knowledge da proficiencia fora da cota: ok")


async def caso_escolha_do_xama_liga_o_multiataque():
    conn, canal, cog = await preparar()
    dono = JOGADORES[0]
    pid = await db.criar_personagem(
        conn, GUILD, dono, "Vuk", "xama", ["Natureza"], nivel=6
    )
    antes = await db.buscar_personagem(conn, pid)
    assert antes["efeitos"]["ataques"] == 1

    await escolher(cog, canal, dono, pid, "escolha_totemica", ["multiataque"])
    depois = await db.buscar_personagem(conn, pid)
    assert depois["efeitos"]["ataques"] == 2

    # o outro caminho da THP na cura, em vez do ataque extra
    outro = await db.criar_personagem(
        conn, GUILD, dono, "Vuk2", "xama", ["Natureza"], nivel=6
    )
    await escolher(cog, canal, dono, outro, "escolha_totemica", ["cantico"])
    cantor = await db.buscar_personagem(conn, outro)
    assert cantor["efeitos"]["ataques"] == 1
    assert cantor["efeitos"]["thp_na_cura"] == 4
    print("  a escolha do Xama liga multiataque ou cantico: ok")


async def caso_upar_avisa_e_o_menu_lista():
    conn, canal, cog = await preparar()
    dono = JOGADORES[0]
    pid = await db.criar_personagem(
        conn, GUILD, dono, "Grom", "guerreiro", ["Atletismo"], nivel=2
    )
    inter = FakeInteraction(canal, dono)
    await cog.upar.callback(cog, inter)
    assert "Decisao pendente" in inter.resposta, inter.resposta
    assert "Fighting Style" in inter.resposta
    assert "/ficha escolhas" in inter.resposta

    # o comando lista a pendencia
    lista = FakeInteraction(canal, dono)
    await cog.escolhas.callback(cog, lista)
    assert isinstance(lista.view_enviada, SeletorEscolha)
    assert {o.value for o in lista.view_enviada.menu.options} == {"fighting_style"}

    # decidido, o comando diz que nao ha mais nada
    await escolher(cog, canal, dono, pid, "fighting_style", ["pesado"])
    vazio = FakeInteraction(canal, dono)
    await cog.escolhas.callback(cog, vazio)
    assert "nenhuma decisao pendente" in vazio.resposta
    print("  upar avisa a decisao e /ficha escolhas resolve: ok")


async def caso_escolha_de_outro_e_recusada():
    conn, canal, cog = await preparar()
    dono, intruso = JOGADORES[0], JOGADORES[1]
    pid = await db.criar_personagem(
        conn, GUILD, dono, "Grom", "guerreiro", ["Atletismo"], nivel=4
    )
    inter = FakeInteraction(canal, intruso)
    await cog.abrir_escolha(inter, pid, "fighting_style")
    assert "nao e seu" in inter.resposta
    assert (await db.buscar_personagem(conn, pid))["escolhas"] == {}
    print("  ninguem decide a ficha dos outros: ok")


async def main():
    try:
        caso_catalogo_das_escolhas()
        caso_pendencias_por_nivel()
        await caso_fighting_style_muda_os_numeros()
        await caso_expertise_dobra_a_proficiencia()
        await caso_expertise_so_oferece_o_que_tem_proficiencia()
        await caso_primal_knowledge_da_proficiencia_extra()
        await caso_escolha_do_xama_liga_o_multiataque()
        await caso_upar_avisa_e_o_menu_lista()
        await caso_escolha_de_outro_e_recusada()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        (Path(__file__).resolve().parent / "teste_escolhas.db").unlink(missing_ok=True)


asyncio.run(main())
print("TESTES DE ESCOLHAS PASSARAM")
