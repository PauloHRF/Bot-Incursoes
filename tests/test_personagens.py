"""Varios personagens por jogador: escolha ao entrar, limites e migracao do banco."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import aiosqlite  # noqa: E402

from src import classes, config, database as db  # noqa: E402
from src.cogs.ficha import Ficha  # noqa: E402
from src.cogs.incursao import Incursoes, SeletorPersonagemEntrada  # noqa: E402
from src.rules import tier  # noqa: E402
from fakes import (  # noqa: E402
    CLASSE_PADRAO,
    CANAL,
    GUILD,
    JOGADORES,
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
    """A ficha sem classe nao tem como virar ficha nova: o banco e limpo."""
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
        "INSERT INTO runs (guild_id, canal_id, incursao_id, criador_id, status)"
        " VALUES (?, ?, 't', ?, 'em_sala')",
        (GUILD, CANAL, JOGADORES[0]),
    )
    await bruto.commit()
    await bruto.close()

    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)

    # as fichas antigas somem: sem classe, nao da para derivar os numeros novos
    assert await db.listar_personagens(conn, GUILD, JOGADORES[0]) == []
    assert "classe" in await db._colunas(conn, "personagens")
    assert "forca" not in await db._colunas(conn, "personagens")
    assert not await db._tabela_existe(conn, "personagens_v1")

    # e a run que dependia delas e encerrada, em vez de ficar sem grupo
    async with conn.execute("SELECT status FROM runs") as cur:
        assert [r["status"] for r in await cur.fetchall()] == ["desistiu"]

    # o cadastro novo funciona no banco migrado
    novo_id = await db.criar_personagem(
        conn, GUILD, JOGADORES[0], "Kaelen", CLASSE_PADRAO, ["Atletismo"]
    )
    assert novo_id
    kaelen = await db.buscar_personagem(conn, novo_id)
    assert kaelen["nivel"] == 1 and kaelen["classe"] == CLASSE_PADRAO

    # subir o bot de novo nao apaga o que acabou de ser criado
    await db.criar_schema(conn)
    assert len(await db.listar_personagens(conn, GUILD, JOGADORES[0])) == 1
    print("  fichas sem classe sao apagadas na migracao: ok")


async def caso_entrar_escolhendo_personagem():
    """Com mais de um personagem, o comando exige dizer qual."""
    conn, canal, cog = await preparar()
    await criar_grupo(conn)
    dono = JOGADORES[0]
    await db.criar_personagem(
        conn, GUILD, dono, "Kaelen", "monge", ["Arcanismo"], nivel=3
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
    assert escolhido["nome"] == "Kaelen"
    # o HP vem da tabela do Monge no tier 2, nao do Heroi (Guerreiro nivel 8)
    assert escolhido["hp_max"] == classes.classe("monge").numeros(3).hp
    print("  /incursao entrar escolhe o personagem: ok")


async def caso_botao_entrar_com_varios():
    """O botão Entrar abre um seletor quando o jogador tem mais de um personagem."""
    conn, canal, cog = await preparar()
    await criar_grupo(conn)
    convidado = JOGADORES[1]
    kaelen = await db.criar_personagem(
        conn, GUILD, convidado, "Kaelen", "monge", ["Arcanismo"], nivel=3
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
    await criar_grupo(conn)
    dono = JOGADORES[0]
    await db.criar_personagem(conn, GUILD, dono, "Frangote", "monge", [])
    fraco = classes.classe("monge").numeros(1)
    forte = classes.classe(CLASSE_PADRAO).numeros(8)

    await cog.entrar.callback(cog, FakeInteraction(canal, dono), "t", personagem="Frangote")
    run = await db.run_do_canal(conn, CANAL)
    msg = await canal.fetch_message(run["mensagem_id"])
    for user_id in JOGADORES[1:]:
        await cog.recrutar(FakeInteraction(canal, user_id, msg), run["id"], "entrar")

    # o HP inicial veio da ficha do Frangote, nao do Heroi
    hps = await db.hp_dos_participantes(conn, run["id"])
    assert hps[dono] == fraco.hp, hps
    assert hps[JOGADORES[1]] == forte.hp

    combatentes = await cog._combatentes(await db.buscar_run(conn, run["id"]))
    dele = next(c for c in combatentes if c.user_id == dono)
    assert dele.nome == "Frangote" and dele.ca == fraco.ca and dele.hp_max == fraco.hp

    # e o nivel que entra na conta do objetivo e o do Frangote
    niveis = await cog._niveis(await db.buscar_run(conn, run["id"]))
    assert 1 in niveis, niveis
    print("  a run usa a ficha do personagem escolhido: ok")


async def caso_intervalo_e_por_jogador():
    """Trocar de personagem não contorna o intervalo entre incursões."""
    conn, canal, cog = await preparar()
    await criar_grupo(conn)
    dono = JOGADORES[0]
    await db.criar_personagem(conn, GUILD, dono, "Reserva", CLASSE_PADRAO, [], nivel=4)

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

    primeiro = await db.criar_personagem(
        conn, GUILD, dono, "Vhalor", CLASSE_PADRAO, ["Atletismo"], nivel=5
    )
    # com um so, nao precisa dizer qual
    um = FakeInteraction(canal, dono)
    assert (await ficha_cog._resolver(um, None))["id"] == primeiro

    await db.criar_personagem(conn, GUILD, dono, "Kaelen", CLASSE_PADRAO, [], nivel=3)
    # com dois, precisa
    dois = FakeInteraction(canal, dono)
    assert await ficha_cog._resolver(dois, None) is None
    assert "mais de um personagem" in dois.resposta

    por_nome = FakeInteraction(canal, dono)
    assert (await ficha_cog._resolver(por_nome, "kaelen"))["nome"] == "Kaelen"

    inexistente = FakeInteraction(canal, dono)
    assert await ficha_cog._resolver(inexistente, "Zed") is None
    assert "nenhum personagem chamado" in inexistente.resposta

    # upar um nao mexe no outro
    alvo = FakeInteraction(canal, dono)
    await ficha_cog.upar.callback(ficha_cog, alvo, personagem="Kaelen")
    kaelen = await db.personagem_por_nome(conn, GUILD, dono, "Kaelen")
    vhalor = await db.personagem_por_nome(conn, GUILD, dono, "Vhalor")
    assert tier(kaelen["nivel"]) == 3, "Kaelen subiu um tier"
    assert vhalor["nivel"] == 5, "o outro personagem nao se mexeu"
    print("  comandos de ficha resolvem o personagem: ok")


async def caso_retrato_do_personagem():
    """O link do retrato é guardado, aparece na ficha e na abertura da run."""
    from src.cogs.ficha import Ficha, embed_ficha
    from src.embeds import url_de_imagem

    conn, canal, cog = await preparar()
    ficha_cog = Ficha(FakeBot(conn, canal))
    await criar_grupo(conn)
    dono = JOGADORES[0]
    personagem = await db.personagem_por_nome(conn, GUILD, dono, f"Heroi{dono}")

    # so http(s) entra
    assert url_de_imagem("https://exemplo.invalid/vhalor.png")
    assert url_de_imagem("http://exemplo.invalid/a.jpg")
    assert url_de_imagem("  https://exemplo.invalid/b.png  ")
    assert url_de_imagem("ftp://exemplo.invalid/x.png") is None
    assert url_de_imagem("C:/Users/eu/retrato.png") is None
    assert url_de_imagem("attachment://retrato.png") is None
    assert url_de_imagem("https://exemplo.invalid/com espaco.png") is None
    assert url_de_imagem("https://" + "x" * 600) is None
    assert url_de_imagem(None) is None and url_de_imagem("") is None

    # ficha sem retrato nao tem thumbnail
    assert embed_ficha(personagem, FakeInteraction(canal, dono).user).thumbnail.url is None

    link = "https://exemplo.invalid/vhalor.png"
    inter = FakeInteraction(canal, dono)
    await ficha_cog.imagem.callback(ficha_cog, inter, link)
    assert "rosto" in inter.resposta

    salvo = await db.buscar_personagem(conn, personagem["id"])
    assert salvo["imagem"] == link
    assert embed_ficha(salvo, inter.user).thumbnail.url == link

    # link invalido nao apaga o que ja estava
    ruim = FakeInteraction(canal, dono)
    await ficha_cog.imagem.callback(ficha_cog, ruim, "javascript:alert(1)")
    assert "http" in ruim.resposta
    assert (await db.buscar_personagem(conn, personagem["id"]))["imagem"] == link

    # a abertura da run traz um cartao por personagem, na mesma mensagem
    antes = len(canal.mensagens)
    await cog.entrar.callback(cog, FakeInteraction(canal, dono), "t")
    run = await db.run_do_canal(conn, CANAL)
    msg = await canal.fetch_message(run["mensagem_id"])
    for user_id in JOGADORES[1:]:
        await cog.recrutar(FakeInteraction(canal, user_id, msg), run["id"], "entrar")
    run = await db.buscar_run(conn, run["id"])
    assert run["status"] == "escolhendo"
    aberturas = [
        m for m in canal.mensagens[antes:]
        if any(e.title == "🎒 O grupo" for e in m.embeds)
    ]
    assert len(aberturas) == 1, "lore e grupo deveriam vir numa mensagem só"
    grupo = next(e for e in aberturas[0].embeds if e.title == "🎒 O grupo")
    for user_id in JOGADORES:
        assert f"Heroi{user_id}" in grupo.description, user_id
    # o link do teste nao resolve, entao a run abre sem a faixa, e nao quebrada
    assert grupo.image.url is None

    # tirar o retrato deixa o campo vazio
    limpa = FakeInteraction(canal, dono)
    await ficha_cog.imagem.callback(ficha_cog, limpa, None)
    assert "tirou" in limpa.resposta
    assert (await db.buscar_personagem(conn, personagem["id"]))["imagem"] is None
    print("  retrato: guardado, na ficha e na abertura da run: ok")


async def main():
    try:
        await caso_migracao_do_banco_antigo()
        await caso_entrar_escolhendo_personagem()
        await caso_botao_entrar_com_varios()
        await caso_personagem_escolhido_e_o_que_joga()
        await caso_intervalo_e_por_jogador()
        await caso_comandos_de_ficha()
        await caso_retrato_do_personagem()
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
