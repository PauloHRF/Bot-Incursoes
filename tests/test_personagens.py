"""Varios personagens por jogador: escolha ao entrar, limites e migracao do banco."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import aiosqlite  # noqa: E402

from src import config, database as db  # noqa: E402
from src.cogs.ficha import Ficha  # noqa: E402
from src.cogs.incursao import Incursoes, SeletorPersonagemEntrada  # noqa: E402
from fakes import (  # noqa: E402
    ATRIBUTOS,
    CANAL,
    GUILD,
    INDEFESO,
    JOGADORES,
    TREINADAS,
    FakeBot,
    FakeCanal,
    FakeInteraction,
    criar_grupo,
    montar_conteudo,
    salas_sem_combate,
)

_ABERTAS = []

# Schema anterior: um personagem por jogador, com PK (guild_id, user_id).
SCHEMA_V1 = """
CREATE TABLE personagens (
    guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, nome TEXT NOT NULL,
    nivel INTEGER NOT NULL, forca INTEGER NOT NULL, destreza INTEGER NOT NULL,
    constituicao INTEGER NOT NULL, inteligencia INTEGER NOT NULL,
    sabedoria INTEGER NOT NULL, carisma INTEGER NOT NULL,
    pericias TEXT NOT NULL DEFAULT '[]', ca INTEGER NOT NULL DEFAULT 10,
    bonus_ataque INTEGER NOT NULL DEFAULT 0, dano_arma TEXT NOT NULL DEFAULT '1d6',
    hp_max INTEGER NOT NULL DEFAULT 10, ultima_incursao TEXT,
    atualizado_em TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (guild_id, user_id)
);
CREATE TABLE runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL, canal_id INTEGER NOT NULL,
    incursao_id TEXT NOT NULL, criador_id INTEGER NOT NULL, status TEXT NOT NULL,
    linha_atual INTEGER NOT NULL DEFAULT 0, sala_atual TEXT, mensagem_id INTEGER,
    votacao_expira_em TEXT, criada_em TEXT NOT NULL DEFAULT (datetime('now')),
    atualizada_em TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE run_participantes (
    run_id INTEGER NOT NULL, user_id INTEGER NOT NULL, hp_atual INTEGER,
    PRIMARY KEY (run_id, user_id)
);
"""


async def preparar(nome_db="teste_personagens.db"):
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass
    config.DB_PATH = Path(__file__).resolve().parent / nome_db
    config.DB_PATH.unlink(missing_ok=True)
    config.TAMANHO_GRUPO = 5
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    canal = FakeCanal(CANAL)
    cog = Incursoes(FakeBot(conn, canal))
    montar_conteudo(cog, salas=salas_sem_combate())
    return conn, canal, cog


async def caso_migracao_do_banco_antigo():
    """Cada ficha do schema antigo vira o primeiro personagem daquele jogador."""
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass
    caminho = Path(__file__).resolve().parent / "teste_migracao.db"
    caminho.unlink(missing_ok=True)
    config.DB_PATH = caminho

    bruto = await aiosqlite.connect(caminho)
    bruto.row_factory = aiosqlite.Row
    await bruto.executescript(SCHEMA_V1)
    await bruto.execute(
        "INSERT INTO personagens (guild_id,user_id,nome,nivel,forca,destreza,constituicao,"
        "inteligencia,sabedoria,carisma,pericias,ca,bonus_ataque,dano_arma,hp_max,ultima_incursao)"
        " VALUES (?,?,'Vhalor',8,10,16,14,12,13,8,?,17,7,'1d8+4',54,'2026-09-15 10:00:00')",
        (GUILD, JOGADORES[0], json.dumps(["Furtividade", "Percepcao"], ensure_ascii=False)),
    )
    await bruto.execute(
        "INSERT INTO personagens (guild_id,user_id,nome,nivel,forca,destreza,constituicao,"
        "inteligencia,sabedoria,carisma,pericias) VALUES (?,?,'Brannak',5,16,10,15,8,12,10,'[]')",
        (GUILD, JOGADORES[1]),
    )
    await bruto.commit()
    await bruto.close()

    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)

    vhalor = await db.personagem_por_nome(conn, GUILD, JOGADORES[0], "Vhalor")
    assert vhalor, "a ficha antiga sumiu na migração"
    assert (vhalor["ca"], vhalor["bonus_ataque"], vhalor["dano_arma"], vhalor["hp_max"]) == (
        17, 7, "1d8+4", 54,
    )
    # os nomes sem acento sao normalizados na leitura
    assert vhalor["pericias"] == ["Furtividade", "Percepção"]

    # o relogio do intervalo foi para a tabela de jogadores
    dias = await db.dias_desde_ultima_incursao(conn, GUILD, JOGADORES[0])
    assert dias is not None and dias > 5, dias
    assert await db.dias_desde_ultima_incursao(conn, GUILD, JOGADORES[1]) is None

    # agora o mesmo jogador pode ter um segundo personagem
    assert await db.criar_personagem(conn, GUILD, JOGADORES[0], "Kaelen", 3, ATRIBUTOS, [])
    assert len(await db.listar_personagens(conn, GUILD, JOGADORES[0])) == 2

    # subir o bot de novo nao duplica nada nem deixa a tabela antiga para tras
    await db.criar_schema(conn)
    assert len(await db.listar_personagens(conn, GUILD, JOGADORES[0])) == 2
    assert not await db._tabela_existe(conn, "personagens_v1")
    assert "personagem_id" in await db._colunas(conn, "run_participantes")

    print("  banco antigo migra sem perder ficha: ok")


async def caso_entrar_escolhendo_personagem():
    """Com mais de um personagem, o comando exige dizer qual."""
    conn, canal, cog = await preparar()
    await criar_grupo(conn)
    dono = JOGADORES[0]
    await db.criar_personagem(
        conn, GUILD, dono, "Kaelen", 3, ATRIBUTOS, ["Arcanismo"],
        combate={"ca": 12, "bonus_ataque": 4, "dano_arma": "1d4+1", "hp_max": 18},
    )

    # sem dizer qual, o bot pede para escolher e nao cria run
    vago = FakeInteraction(canal, dono)
    await cog.entrar.callback(cog, vago, "t")
    assert "mais de um personagem" in vago.resposta, vago.resposta
    assert await db.run_do_canal(conn, CANAL) is None

    # nome inexistente e recusado
    errado = FakeInteraction(canal, dono)
    await cog.entrar.callback(cog, errado, "t", personagem="Ninguem")
    assert "nao tem nenhum personagem" in errado.resposta

    # com o nome certo, entra com aquele personagem
    ok = FakeInteraction(canal, dono)
    await cog.entrar.callback(cog, ok, "t", personagem="Kaelen")
    run = await db.run_do_canal(conn, CANAL)
    assert run is not None
    escolhido = await db.personagem_da_run(conn, run["id"], dono)
    assert escolhido["nome"] == "Kaelen" and escolhido["hp_max"] == 18
    print("  /incursao entrar escolhe o personagem: ok")


async def caso_botao_entrar_com_varios():
    """O botão Entrar abre um seletor quando o jogador tem mais de um personagem."""
    conn, canal, cog = await preparar()
    await criar_grupo(conn)
    convidado = JOGADORES[1]
    kaelen = await db.criar_personagem(
        conn, GUILD, convidado, "Kaelen", 3, ATRIBUTOS, ["Arcanismo"],
        combate={"ca": 12, "bonus_ataque": 4, "dano_arma": "1d4+1", "hp_max": 18},
    )

    await cog.entrar.callback(cog, FakeInteraction(canal, JOGADORES[0]), "t")
    run = await db.run_do_canal(conn, CANAL)
    msg = await canal.fetch_message(run["mensagem_id"])

    # quem tem um so entra direto
    solo = FakeInteraction(canal, JOGADORES[2], msg)
    await cog.recrutar(solo, run["id"], "entrar")
    assert await db.esta_na_run(conn, run["id"], JOGADORES[2])
    assert "Voce entrou com" in solo.resposta

    # quem tem dois recebe o seletor e ainda nao entrou
    escolhendo = FakeInteraction(canal, convidado, msg)
    await cog.recrutar(escolhendo, run["id"], "entrar")
    assert isinstance(escolhendo.view_enviada, SeletorPersonagemEntrada)
    assert not await db.esta_na_run(conn, run["id"], convidado)

    # ao escolher, entra com o personagem indicado
    confirmando = FakeInteraction(canal, convidado, msg)
    await cog.efetivar_entrada(confirmando, run["id"], kaelen)
    assert await db.esta_na_run(conn, run["id"], convidado)
    assert (await db.personagem_da_run(conn, run["id"], convidado))["nome"] == "Kaelen"

    # personagem de outra pessoa e recusado
    intruso = FakeInteraction(canal, JOGADORES[3], msg)
    await cog.efetivar_entrada(intruso, run["id"], kaelen)
    assert "não é seu" in intruso.resposta
    assert not await db.esta_na_run(conn, run["id"], JOGADORES[3])
    print("  botão Entrar com seletor de personagem: ok")


async def caso_personagem_escolhido_e_o_que_joga():
    """A run usa a ficha do personagem escolhido, não de outro do mesmo jogador."""
    conn, canal, cog = await preparar()
    await criar_grupo(conn, hp_max=40)
    dono = JOGADORES[0]
    frangote = await db.criar_personagem(
        conn, GUILD, dono, "Frangote", 1, ATRIBUTOS, [],
        combate={"ca": 8, "bonus_ataque": 0, "dano_arma": "1d4", "hp_max": 7},
    )

    await cog.entrar.callback(cog, FakeInteraction(canal, dono), "t", personagem="Frangote")
    run = await db.run_do_canal(conn, CANAL)
    msg = await canal.fetch_message(run["mensagem_id"])
    for user_id in JOGADORES[1:]:
        await cog.recrutar(FakeInteraction(canal, user_id, msg), run["id"], "entrar")

    # o HP inicial veio da ficha do Frangote, nao do Heroi
    hps = await db.hp_dos_participantes(conn, run["id"])
    assert hps[dono] == 7, hps
    assert hps[JOGADORES[1]] == 40

    combatentes = await cog._combatentes(await db.buscar_run(conn, run["id"]))
    dele = next(c for c in combatentes if c.user_id == dono)
    assert dele.nome == "Frangote" and dele.ca == 8 and dele.hp_max == 7

    # e o nivel que entra na conta do objetivo e o do Frangote
    niveis = await cog._niveis(await db.buscar_run(conn, run["id"]))
    assert 1 in niveis, niveis
    print("  a run usa a ficha do personagem escolhido: ok")


async def caso_intervalo_e_por_jogador():
    """Trocar de personagem não contorna o intervalo entre incursões."""
    conn, canal, cog = await preparar()
    await criar_grupo(conn)
    dono = JOGADORES[0]
    await db.criar_personagem(conn, GUILD, dono, "Reserva", 4, ATRIBUTOS, [])

    await cog.entrar.callback(cog, FakeInteraction(canal, dono), "t", personagem=f"Heroi{dono}")
    run = await db.run_do_canal(conn, CANAL)
    msg = await canal.fetch_message(run["mensagem_id"])
    for user_id in JOGADORES[1:]:
        await cog.recrutar(FakeInteraction(canal, user_id, msg), run["id"], "entrar")
    await db.atualizar_run(conn, run["id"], status="sucesso")

    bloqueio = await cog._motivo_de_bloqueio(GUILD, dono)
    assert bloqueio and "intervalo" in bloqueio.lower(), bloqueio

    # o bloqueio vale para o jogador, com qualquer personagem
    nova = FakeInteraction(canal, dono)
    await cog.entrar.callback(cog, nova, "t", personagem="Reserva")
    assert "intervalo" in nova.resposta.lower(), nova.resposta
    assert await db.run_do_canal(conn, CANAL) is None
    print("  intervalo continua sendo por jogador: ok")


async def caso_comandos_de_ficha():
    """Os comandos de ficha resolvem qual personagem mexer."""
    conn, canal, cog = await preparar()
    ficha_cog = Ficha(FakeBot(conn, canal))
    dono = JOGADORES[0]

    # sem personagem nenhum
    vazio = FakeInteraction(canal, dono)
    assert await ficha_cog._resolver(vazio, None) is None
    assert "ainda nao tem personagem" in vazio.resposta

    primeiro = await db.criar_personagem(conn, GUILD, dono, "Vhalor", 5, ATRIBUTOS, ["Atletismo"])
    # com um so, nao precisa dizer qual
    um = FakeInteraction(canal, dono)
    assert (await ficha_cog._resolver(um, None))["id"] == primeiro

    await db.criar_personagem(conn, GUILD, dono, "Kaelen", 3, ATRIBUTOS, [])
    # com dois, precisa
    dois = FakeInteraction(canal, dono)
    assert await ficha_cog._resolver(dois, None) is None
    assert "mais de um personagem" in dois.resposta

    por_nome = FakeInteraction(canal, dono)
    assert (await ficha_cog._resolver(por_nome, "kaelen"))["nome"] == "Kaelen"

    inexistente = FakeInteraction(canal, dono)
    assert await ficha_cog._resolver(inexistente, "Zed") is None
    assert "nenhum personagem chamado" in inexistente.resposta

    # atualizar o nivel de um nao mexe no outro
    alvo = FakeInteraction(canal, dono)
    await ficha_cog.nivel.callback(ficha_cog, alvo, 12, personagem="Kaelen")
    assert (await db.personagem_por_nome(conn, GUILD, dono, "Kaelen"))["nivel"] == 12
    assert (await db.personagem_por_nome(conn, GUILD, dono, "Vhalor"))["nivel"] == 5
    print("  comandos de ficha resolvem o personagem: ok")


async def main():
    try:
        await caso_migracao_do_banco_antigo()
        await caso_entrar_escolhendo_personagem()
        await caso_botao_entrar_com_varios()
        await caso_personagem_escolhido_e_o_que_joga()
        await caso_intervalo_e_por_jogador()
        await caso_comandos_de_ficha()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        for sobra in ("teste_personagens.db", "teste_migracao.db"):
            (Path(__file__).resolve().parent / sobra).unlink(missing_ok=True)


asyncio.run(main())
print("TESTES DE PERSONAGENS PASSARAM")
