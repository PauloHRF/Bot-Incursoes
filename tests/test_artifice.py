"""O artífice: a Infusão que dá +1 ao grupo, o Engenho que soma na rolagem, o
Flash of Genius que salva o teste alheio e o Arcane Jolt que escolhe entre
dano e cura dividindo o mesmo uso."""
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
    sala,
    salas_sem_combate,
)

_ABERTAS = []

SACO = {**INDEFESO, "hp": 500, "ataque": 1, "dano": "1d1"}


async def preparar(nivel=9, escolhas=None, quantos=3, monstros=2, salas=None):
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass
    config.DB_PATH = Path(__file__).resolve().parent / "teste_artifice.db"
    config.DB_PATH.unlink(missing_ok=True)
    config.TAMANHO_GRUPO = 5
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    await criar_grupo(conn, nivel=nivel, classe="artifice")
    canal = FakeCanal(CANAL)
    cog = Incursoes(FakeBot(conn, canal))
    incursao, _ = montar_conteudo(
        cog, tamanho="Curta",
        salas=salas if salas is not None else salas_sem_combate(),
        monstro_objetivo=SACO, inimigos_objetivo=monstros,
    )
    run_id = await db.criar_run(conn, GUILD, CANAL, incursao.id, JOGADORES[0])
    for user_id in JOGADORES[:quantos]:
        p = await db.personagem_por_nome(conn, GUILD, user_id, f"Heroi{user_id}")
        await db.adicionar_participante(conn, run_id, user_id, p["id"])
        for escolha, opcao in (escolhas or {}).items():
            await db.definir_escolha(conn, p["id"], escolha, opcao)
    await db.inicializar_hp(conn, run_id)
    return conn, canal, cog, incursao, run_id


async def em_combate(conn, cog, incursao, run_id):
    await db.atualizar_run(
        conn, run_id, status="objetivo", sala_atual="OBJ",
        linha_atual=incursao.passos + 1,
    )
    run = await db.buscar_run(conn, run_id)
    await cog._abrir_combate(run, incursao.objetivo)
    return await db.buscar_run(conn, run_id)


# ------------------------------------------------------------------- a tabela


def caso_tabela_e_identidade():
    artifice = cl.CLASSES["artifice"]
    clerigo = cl.CLASSES["clerigo"]
    # O HP e a CA andam com o clerigo: as duas sao classes de d8, e o artifice
    # leva um ponto de CA a mais pelo escudo.
    for t in range(1, 6):
        meu, dele = artifice.tiers[t], clerigo.tiers[t]
        assert meu.hp == dele.hp, f"T{t}: o HP acompanha o clerigo"
        assert meu.ca == dele.ca + 1, f"T{t}: um ponto de CA a mais (escudo)"
    # O dado de dano e o que os separa: d10 com tres degraus, onde o clerigo
    # tem d8 com dois.
    assert [artifice.tiers[t].dano for t in range(1, 6)] == [
        "1d10", "1d10", "2d10", "2d10", "3d10"
    ]
    assert artifice.saves == ("CON", "INT"), "os saves do livro novo"
    assert "Artífice" not in cl.CLASSES_PENDENTES
    print("  HP e CA seguem o clerigo; o dano e d10 em tres degraus: ok")


def caso_as_cinco_camadas_de_escolha():
    """Toda a classe é escolha, como o clérigo — e uma por tier."""
    por_tier = {}
    for t, h in cl.habilidades("artifice", 9):
        if h.tipo == cl.ESCOLHA:
            por_tier[t] = h.id
    assert por_tier == {1: "ferramenta_t1", 2: "infusao", 3: "engenho_t3"}, por_tier
    # T4 e T5 nao sao escolha: Flash of Genius e Arcane Jolt vem de graca
    ids = {h.id for _t, h in cl.habilidades("artifice", 9)}
    assert "flash_of_genius" in ids and "genio_refinado" in ids
    assert {"arcane_jolt_dano", "arcane_jolt_cura"} <= ids
    # E sem Multiattack: no livro so dois dos cinco arquetipos o ganham, e com
    # ele o d10 levava o artifice a 33 de dano por rodada, acima do barbaro.
    assert "multiataque" not in ids, "o artifice nao bate duas vezes"
    assert cl.efeitos("artifice", 10, {}).get("ataques", 1) == 1
    print("  tres tiers de escolha, sem Multiattack, Flash e Jolt de graca: ok")


def caso_magia_de_ferramenta_destrava_uma():
    com = {h.id for _t, h in cl.habilidades(
        "artifice", 9, {"ferramenta_t1": "thunderwave"}
    )}
    assert "thunderwave" in com
    assert "cure_wounds_art" not in com and "faerie_fire" not in com
    print("  a magia de ferramenta destrava uma e esconde as irmas: ok")


# ------------------------------------------------------------------ a infusao


async def caso_infusao_pega_o_grupo_inteiro():
    """O item fica na planilha do grupo; o que entra no bot é o +1 dele."""
    for opcao, campo, esperado in (
        ("armas", "bonus_ataque", 1),
        ("armaduras", "ca_extra", 1),
        ("municao", "dano_extra", 1),
    ):
        conn, canal, cog, incursao, run_id = await preparar(
            escolhas={"infusao": opcao}
        )
        run = await em_combate(conn, cog, incursao, run_id)
        estado = await cog._estado_combate(run, incursao.objetivo)
        base = cl.numeros("artifice", 9)
        for c in estado.vivos:
            valor = getattr(c, campo)
            if campo == "bonus_ataque":
                assert valor == base.acerto + esperado, (opcao, c.nome, valor)
            else:
                assert valor == esperado, (opcao, c.nome, valor)
    print("  as tres infusoes chegam em todo mundo do grupo: ok")


async def caso_infusao_nao_soma_entre_dois_artifices():
    """Como a aura do xamã: vale a melhor, não a soma."""
    conn, canal, cog, incursao, run_id = await preparar(escolhas={"infusao": "armas"})
    run = await em_combate(conn, cog, incursao, run_id)
    estado = await cog._estado_combate(run, incursao.objetivo)
    base = cl.numeros("artifice", 9).acerto
    # tres artifices, todos com a mesma infusao: ainda e +1
    for c in estado.vivos:
        assert c.bonus_ataque == base + 1, (c.nome, c.bonus_ataque)
    print("  tres artifices com a mesma infusao dao +1, nao +3: ok")


def caso_engenho_usa_as_chaves_que_existem():
    for opcao, chave, valor in (
        ("arma_arcana", "dano_bonus", "1d8"),
        ("sabedoria_alquimica", "bonus_cura_pct", 0.1),
        ("precisao_guiada", "dano_extra", 3),
    ):
        efeitos = cl.efeitos("artifice", 9, {"engenho_t3": opcao})
        assert efeitos[chave] == valor, (opcao, efeitos.get(chave))
    print("  o Engenho entra pelas tres chaves que o motor ja le: ok")


# ------------------------------------------------------------ Flash of Genius


def caso_vale_ajudar_so_quando_vira():
    """A reação dispara sozinha, então o critério é o que a protege."""
    def teste(d20, mod, cd):
        return motor.ResultadoTeste(1, "X", "Atletismo", d20, mod, cd)

    # falhou por 3, e o +5 cobre: vale
    assert motor.vale_ajudar(teste(5, 2, 10), 5)
    # falhou por exatamente 5: vale, porque empatar com a CD e passar
    assert motor.vale_ajudar(teste(5, 0, 10), 5)
    # falhou por 6: o +5 nao cobre, nao queima o uso
    assert not motor.vale_ajudar(teste(4, 0, 10), 5)
    # ja passou: nao mexe
    assert not motor.vale_ajudar(teste(15, 2, 10), 5)
    # bonus zero nunca vale
    assert not motor.vale_ajudar(teste(5, 0, 10), 0)
    print("  o socorro so entra quando vira a falha em sucesso: ok")


def caso_a_ajuda_entra_no_total_e_na_margem():
    r = motor.ResultadoTeste(1, "X", "Atletismo", 5, 2, 10)
    assert not r.passou and r.margem == 0
    r.ajuda = 5
    assert r.total == 12 and r.passou and r.margem == 2, (r.total, r.margem)
    print("  a ajuda conta no total, no veredito e na margem da sala: ok")


async def caso_flash_socorre_o_teste_de_outro():
    """Numa CD alta, ou o Flash salva o teste ou o uso fica intacto.

    O desfecho depende do d20, então o que o teste guarda é o invariante: o
    uso só sai quando a rolagem passa a passar. Nunca os dois, nunca nenhum.
    """
    dificil = [
        sala("S1", "Evento", cd=30, alvo_progresso=1, pericias=["Atletismo"]),
        sala("S2", "Evento", cd=30, alvo_progresso=1, pericias=["Atletismo"]),
        sala("S3", "Evento", cd=30, alvo_progresso=1, pericias=["Atletismo"]),
    ]
    for _ in range(12):
        conn, canal, cog, incursao, run_id = await preparar(salas=dificil)
        await db.atualizar_run(
            conn, run_id, status="em_sala", sala_atual="S1", linha_atual=1
        )
        await db.gravar_opcoes(conn, run_id, 1, ["S1", "S2", "S3"])

        inter = FakeInteraction(canal, JOGADORES[0])
        await cog.rolar(inter, run_id, "S1")
        gastos = await db.usos_da_run(conn, run_id, JOGADORES[0])
        gastou = any(chave[0] == "flash_of_genius" for chave in gastos)
        registros = await db.testes_da_sala(conn, run_id, 1)
        meu = next(r for r in registros if r["user_id"] == JOGADORES[0])
        passou = meu["d20"] + meu["modificador"] >= meu["cd"]

        if gastou:
            assert passou, "gastou o uso e o teste continuou falhando"
            # a resposta privada diz de quem veio a ajuda
            assert "de Heroi" in (inter.resposta or ""), inter.resposta
            # e o canal anuncia o socorro para o grupo
            anuncios = " ".join(str(m.content or "") for m in canal.enviadas)
            assert "socorre" in anuncios, anuncios[-200:]
        else:
            # Nao gastou: ou passou por conta propria, ou falhou longe demais
            # para o +10 cobrir. O meio-termo seria o uso desperdicado.
            falta = meu["cd"] - (meu["d20"] + meu["modificador"])
            assert falta <= 0 or falta > 10, (
                f"falhou por {falta} e o Flash de +10 nao entrou"
            )
    print("  o Flash gasta o uso se e so se o socorro faz o teste passar: ok")


def caso_genio_refinado_sobe_o_bonus():
    efeitos = cl.efeitos("artifice", 9, {})
    assert efeitos["flash_bonus"] == 10, "o tier 5 sobe de 5 para 10"
    # no tier 4 ainda e o da propria habilidade
    cedo = cl.efeitos("artifice", 7, {})
    assert cedo["flash_bonus"] == 0, "antes do tier 5 vale o bonus da acao"
    flash = next(
        h for _t, h in cl.habilidades("artifice", 7) if h.id == "flash_of_genius"
    )
    assert flash.acao["bonus"] == 5
    print("  Genio refinado sobe o Flash de +5 para +10 no tier 5: ok")


# -------------------------------------------------------------- Arcane Jolt


async def caso_arcane_jolt_divide_o_uso():
    """Os dois caminhos são a mesma habilidade, como as tradições do xamã."""
    conn, canal, cog, incursao, run_id = await preparar()
    run = await em_combate(conn, cog, incursao, run_id)
    dono = JOGADORES[0]

    dano, cura = (
        next(h for _t, h in cl.habilidades("artifice", 9) if h.id == hid)
        for hid in ("arcane_jolt_dano", "arcane_jolt_cura")
    )
    assert dano.chave_de_uso == cura.chave_de_uso == "arcane_jolt"

    inter = FakeInteraction(canal, dono)
    await cog.usar_habilidade(inter, run["id"], "OBJ", "arcane_jolt_dano", [0])
    # gastou o contador compartilhado
    gastos = await db.usos_da_run(conn, run_id, dono)
    assert any(chave[0] == "arcane_jolt" for chave in gastos), gastos
    print("  os dois Arcane Jolt dividem o mesmo contador de usos: ok")


async def caso_arcane_jolt_cura_por_dado():
    conn, canal, cog, incursao, run_id = await preparar()
    run = await em_combate(conn, cog, incursao, run_id)
    ferido = JOGADORES[1]
    await db.definir_hp(conn, run["id"], ferido, 10)

    inter = FakeInteraction(canal, JOGADORES[0])
    await cog.usar_habilidade(inter, run["id"], "OBJ", "arcane_jolt_cura", [ferido])
    pessoas = {p["user_id"]: p for p in await db.personagens_da_run(conn, run_id)}
    hp = pessoas[ferido]["hp_atual"]
    assert 12 <= hp <= 22, hp  # 2d6 em cima de 10
    print(f"  Arcane Jolt restaurador cura 2d6 (foi de 10 para {hp}): ok")


async def main():
    try:
        caso_tabela_e_identidade()
        caso_as_cinco_camadas_de_escolha()
        caso_magia_de_ferramenta_destrava_uma()
        await caso_infusao_pega_o_grupo_inteiro()
        await caso_infusao_nao_soma_entre_dois_artifices()
        caso_engenho_usa_as_chaves_que_existem()
        caso_vale_ajudar_so_quando_vira()
        caso_a_ajuda_entra_no_total_e_na_margem()
        await caso_flash_socorre_o_teste_de_outro()
        caso_genio_refinado_sobe_o_bonus()
        await caso_arcane_jolt_divide_o_uso()
        await caso_arcane_jolt_cura_por_dado()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        (Path(__file__).resolve().parent / "teste_artifice.db").unlink(missing_ok=True)


asyncio.run(main())
print("TESTES DO ARTIFICE PASSARAM")
