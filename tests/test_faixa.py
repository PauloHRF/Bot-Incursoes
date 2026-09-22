"""A faixa com os retratos do grupo lado a lado na abertura da run."""
from __future__ import annotations

import asyncio
import sys
from io import BytesIO
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from PIL import Image  # noqa: E402

from src import config, database as db, embeds as E, retratos  # noqa: E402
from src.cogs.incursao import Incursoes  # noqa: E402
from fakes import (  # noqa: E402
    CANAL,
    GUILD,
    JOGADORES,
    FakeBot,
    FakeCanal,
    FakeInteraction,
    FakeUsuario,
    criar_grupo,
    montar_conteudo,
    salas_sem_combate,
)

_ABERTAS = []

LINK = "https://exemplo.invalid/retrato.png"


def png(cor=(200, 30, 30), tamanho=(400, 600)) -> bytes:
    """Um PNG de verdade, para o teste não depender de rede."""
    buffer = BytesIO()
    Image.new("RGB", tamanho, cor).save(buffer, format="PNG")
    return buffer.getvalue()


def _devolver(valor):
    """Coroutine pronta, para trocar retratos.baixar sem ir à rede."""

    async def coro():
        return valor

    return coro()


def _baixa_fake(urls):
    return _devolver([png() if u else None for u in urls])


async def preparar():
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass
    config.DB_PATH = Path(__file__).resolve().parent / "teste_faixa.db"
    config.DB_PATH.unlink(missing_ok=True)
    config.TAMANHO_GRUPO = 5
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    canal = FakeCanal(CANAL)
    cog = Incursoes(FakeBot(conn, canal))
    montar_conteudo(cog, salas=salas_sem_combate())
    return conn, canal, cog


def caso_montagem_lado_a_lado():
    """Cinco tiles em fila, do mesmo tamanho, independente do que entrou."""
    itens = [
        ("Vhalor", png()),
        ("Kaelen", png((30, 120, 200), (800, 300))),  # paisagem, vira quadrado
        ("Nome Muito Comprido Que Nao Cabe", png((20, 160, 90), (300, 300))),
        ("Sem retrato", None),
        ("Link quebrado", b"isto nao e uma imagem"),
    ]
    dados = retratos.montar_faixa(itens)
    assert dados, "deveria sair um PNG"
    with Image.open(BytesIO(dados)) as faixa:
        assert faixa.width == retratos.LARGURA_TILE * len(itens), faixa.size
        assert faixa.height == retratos.ALTURA_RETRATO + retratos.ALTURA_NOME, faixa.size
        # o primeiro tile é o retrato vermelho; o quarto é o vazio, bem mais escuro
        assert faixa.getpixel((100, 100))[0] > 120, "o retrato deveria estar colado"
        vazio = faixa.getpixel((3 * retratos.LARGURA_TILE + 12, 12))  # canto, fora da inicial
        assert sum(vazio) < 200, vazio

    # um grupo grande não estica a imagem sem limite
    muitos = [(f"P{i}", None) for i in range(12)]
    with Image.open(BytesIO(retratos.montar_faixa(muitos))) as cortada:
        assert cortada.width == retratos.LARGURA_TILE * retratos.MAX_RETRATOS

    assert retratos.montar_faixa([]) is None
    print("  faixa: tiles do mesmo tamanho, em fila: ok")


def caso_link_para_rede_interna_e_recusado():
    """O link vem de um jogador: o bot não pode virar sonda da rede de quem hospeda."""
    for ruim in (
        "http://127.0.0.1:8080/x.png",
        "http://localhost/x.png",
        "http://192.168.0.10/x.png",
        "http://10.0.0.5/x.png",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/x.png",
        "https://",
        "nao-e-url",
    ):
        assert not retratos.endereco_publico(ruim), ruim
    assert retratos.endereco_publico("https://93.184.216.34/retrato.png")
    print("  endereço interno recusado antes de baixar: ok")


async def caso_abertura_com_um_embed_e_uma_imagem():
    conn, canal, _ = await preparar()
    await criar_grupo(conn)
    personagens = []
    for i, user_id in enumerate(JOGADORES):
        p = await db.personagem_por_nome(conn, GUILD, user_id, f"Heroi{user_id}")
        if i < 2:
            await db.atualizar_personagem(conn, p["id"], "imagem", LINK)
            p = await db.buscar_personagem(conn, p["id"])
        personagens.append(p)
    membros = [FakeUsuario(p["user_id"]) for p in personagens]

    original = retratos.baixar
    retratos.baixar = _baixa_fake
    try:
        cartoes, arquivo = await E.abertura_do_grupo(personagens, membros)
    finally:
        retratos.baixar = original

    assert len(cartoes) == 1, "com a faixa, o grupo cabe num embed só"
    assert arquivo is not None and arquivo.filename == retratos.ARQUIVO
    assert cartoes[0].image.url == f"attachment://{retratos.ARQUIVO}"
    for p in personagens:
        assert p["nome"] in cartoes[0].description
    # a ordem do texto é a mesma dos retratos
    posicoes = [cartoes[0].description.index(p["nome"]) for p in personagens]
    assert posicoes == sorted(posicoes)
    print("  abertura: um embed com o grupo e a faixa anexada: ok")


async def caso_sem_retrato_e_sem_pillow():
    conn, canal, _ = await preparar()
    await criar_grupo(conn)
    personagens = [
        await db.personagem_por_nome(conn, GUILD, u, f"Heroi{u}") for u in JOGADORES
    ]
    membros = [FakeUsuario(p["user_id"]) for p in personagens]

    # ninguém pôs retrato: o grupo sai em texto, sem anexo inútil
    cartoes, arquivo = await E.abertura_do_grupo(personagens, membros)
    assert arquivo is None and len(cartoes) == 1
    assert cartoes[0].image.url is None

    # sem Pillow, volta o plano B: um card por personagem, com a miniatura
    alvo = personagens[0]
    await db.atualizar_personagem(conn, alvo["id"], "imagem", LINK)
    personagens[0] = await db.buscar_personagem(conn, alvo["id"])
    guardada = retratos.Image
    retratos.Image = None
    try:
        assert not retratos.disponivel()
        cartoes, arquivo = await E.abertura_do_grupo(personagens, membros)
    finally:
        retratos.Image = guardada
    assert arquivo is None
    assert len(cartoes) == len(personagens)
    assert cartoes[0].thumbnail.url == LINK
    print("  sem retrato e sem Pillow, a abertura não quebra: ok")


async def caso_run_abre_com_o_anexo():
    """A run inteira: a faixa chega junto com a lore, numa mensagem só."""
    conn, canal, cog = await preparar()
    await criar_grupo(conn)
    for user_id in JOGADORES[:3]:
        p = await db.personagem_por_nome(conn, GUILD, user_id, f"Heroi{user_id}")
        await db.atualizar_personagem(conn, p["id"], "imagem", LINK)

    original = retratos.baixar
    retratos.baixar = _baixa_fake
    try:
        antes = len(canal.mensagens)
        await cog.entrar.callback(cog, FakeInteraction(canal, JOGADORES[0]), "t")
        run = await db.run_do_canal(conn, CANAL)
        msg = await canal.fetch_message(run["mensagem_id"])
        for user_id in JOGADORES[1:]:
            await cog.recrutar(FakeInteraction(canal, user_id, msg), run["id"], "entrar")
    finally:
        retratos.baixar = original

    assert (await db.buscar_run(conn, run["id"]))["status"] == "escolhendo"
    aberturas = [
        m for m in canal.mensagens[antes:] if any(e.title == "🎒 O grupo" for e in m.embeds)
    ]
    assert len(aberturas) == 1, "lore e grupo continuam na mesma mensagem"
    abertura = aberturas[0]
    assert len(abertura.embeds) == 2, [e.title for e in abertura.embeds]
    assert abertura.arquivo is not None, "a faixa precisa ir anexada na mesma mensagem"
    assert abertura.arquivo.filename == retratos.ARQUIVO
    print("  a run abre com lore, grupo e faixa numa mensagem: ok")


async def main():
    try:
        caso_montagem_lado_a_lado()
        caso_link_para_rede_interna_e_recusado()
        await caso_abertura_com_um_embed_e_uma_imagem()
        await caso_sem_retrato_e_sem_pillow()
        await caso_run_abre_com_o_anexo()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        (Path(__file__).resolve().parent / "teste_faixa.db").unlink(missing_ok=True)


asyncio.run(main())
print("TESTES DA FAIXA DE RETRATOS PASSARAM")
