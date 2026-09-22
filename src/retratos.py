"""Faixa com os retratos do grupo lado a lado.

O Discord empilha embeds na vertical, então a única forma de pôr os retratos
lado a lado é montar uma imagem só e anexar. Isso depende de Pillow: sem ela,
quem chama cai no plano B (um card por personagem) em vez de quebrar.
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from io import BytesIO
from typing import Optional, Sequence
from urllib.parse import urlparse

try:  # Pillow é opcional: o bot roda sem ela, só sem a faixa.
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover - depende do ambiente
    Image = ImageDraw = ImageFont = None  # type: ignore[assignment]

ARQUIVO = "grupo.png"

LARGURA_TILE = 200
ALTURA_RETRATO = 200
ALTURA_NOME = 44
MAX_RETRATOS = 6

MAX_BYTES = 8 * 1024 * 1024
TIMEOUT = 8

FUNDO = (26, 28, 33)
MOLDURA = (70, 76, 88)
TEXTO = (233, 235, 240)
VAZIO = (44, 48, 56)

# A primeira que existir na máquina; no fim sobra a bitmap embutida da Pillow.
FONTES = ("DejaVuSans.ttf", "arial.ttf", "segoeui.ttf", "Verdana.ttf")


def disponivel() -> bool:
    """Se dá para montar a faixa neste ambiente."""
    return Image is not None


# ------------------------------------------------------------------ desenho


def _fonte(tamanho: int):
    for nome in FONTES:
        try:
            return ImageFont.truetype(nome, tamanho)
        except OSError:
            continue
    try:
        return ImageFont.load_default(tamanho)
    except TypeError:  # Pillow < 10.1 não aceita tamanho na fonte padrão
        return ImageFont.load_default()


def _centrar(desenho, texto: str, fonte, caixa, cor) -> None:
    x0, y0, x1, y1 = caixa
    esq, topo, dir_, base = desenho.textbbox((0, 0), texto, font=fonte)
    desenho.text(
        (x0 + (x1 - x0 - (dir_ - esq)) / 2 - esq, y0 + (y1 - y0 - (base - topo)) / 2 - topo),
        texto,
        font=fonte,
        fill=cor,
    )


def _encurtar(desenho, texto: str, fonte, largura: int) -> str:
    if desenho.textlength(texto, font=fonte) <= largura:
        return texto
    while texto and desenho.textlength(texto + "…", font=fonte) > largura:
        texto = texto[:-1]
    return (texto + "…") if texto else "…"


def _quadrado(imagem):
    """Recorte quadrado, puxado para cima: o rosto costuma ficar no terço de cima."""
    largura, altura = imagem.size
    lado = min(largura, altura)
    esquerda = (largura - lado) // 2
    topo = max(0, min((altura - lado) // 3, altura - lado))
    recorte = imagem.crop((esquerda, topo, esquerda + lado, topo + lado))
    return recorte.resize((LARGURA_TILE, ALTURA_RETRATO), Image.LANCZOS)


def _tile(nome: str, dados: Optional[bytes]):
    tile = Image.new("RGB", (LARGURA_TILE, ALTURA_RETRATO + ALTURA_NOME), FUNDO)
    retrato = None
    if dados:
        try:
            with Image.open(BytesIO(dados)) as bruta:
                retrato = _quadrado(bruta.convert("RGB"))
        except Exception:
            retrato = None  # link quebrado ou arquivo estranho: vai a inicial

    desenho = ImageDraw.Draw(tile)
    if retrato is not None:
        tile.paste(retrato, (0, 0))
    else:
        desenho.rectangle((0, 0, LARGURA_TILE, ALTURA_RETRATO), fill=VAZIO)
        inicial = (nome.strip() or "?")[0].upper()
        _centrar(desenho, inicial, _fonte(96), (0, 0, LARGURA_TILE, ALTURA_RETRATO), MOLDURA)

    fonte = _fonte(22)
    _centrar(
        desenho,
        _encurtar(desenho, nome.strip(), fonte, LARGURA_TILE - 12),
        fonte,
        (0, ALTURA_RETRATO, LARGURA_TILE, ALTURA_RETRATO + ALTURA_NOME),
        TEXTO,
    )
    desenho.rectangle(
        (0, 0, LARGURA_TILE - 1, ALTURA_RETRATO + ALTURA_NOME - 1), outline=MOLDURA
    )
    return tile


def montar_faixa(itens: Sequence[tuple[str, Optional[bytes]]]) -> Optional[bytes]:
    """PNG com um tile por personagem, em fila. None se não dá para montar."""
    if not disponivel() or not itens:
        return None
    tiles = [_tile(nome, dados) for nome, dados in list(itens)[:MAX_RETRATOS]]
    faixa = Image.new(
        "RGB", (LARGURA_TILE * len(tiles), ALTURA_RETRATO + ALTURA_NOME), FUNDO
    )
    for i, tile in enumerate(tiles):
        faixa.paste(tile, (i * LARGURA_TILE, 0))
    buffer = BytesIO()
    faixa.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


# ------------------------------------------------------------------ download


def endereco_publico(url: str) -> bool:
    """Recusa link que aponta para a própria máquina ou para a rede local.

    O link vem de um jogador: sem isto, a ficha viraria um jeito de fazer o bot
    bater em serviços internos de quem hospeda.
    """
    host = urlparse(url).hostname
    if not host:
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
    return True


async def _baixar_um(sessao, loop, url: Optional[str]) -> Optional[bytes]:
    if not url:
        return None
    try:
        if not await loop.run_in_executor(None, endereco_publico, url):
            return None
        async with sessao.get(url) as resposta:
            if resposta.status != 200:
                return None
            if not (resposta.headers.get("Content-Type") or "").lower().startswith("image/"):
                return None
            dados = await resposta.content.read(MAX_BYTES + 1)
            return dados if 0 < len(dados) <= MAX_BYTES else None
    except Exception:
        # Retrato é enfeite: nada aqui pode impedir a incursão de começar.
        return None


async def baixar(urls: Sequence[Optional[str]]) -> list[Optional[bytes]]:
    """Baixa os retratos em paralelo; o que falhar volta None."""
    import aiohttp

    loop = asyncio.get_running_loop()
    tempo = aiohttp.ClientTimeout(total=TIMEOUT)
    async with aiohttp.ClientSession(timeout=tempo) as sessao:
        return list(await asyncio.gather(*(_baixar_um(sessao, loop, u) for u in urls)))


async def faixa(itens: Sequence[tuple[str, Optional[str]]]) -> Optional[bytes]:
    """Baixa os retratos e devolve o PNG do grupo, ou None."""
    if not disponivel() or not itens:
        return None
    dados = await baixar([url for _, url in itens])
    if not any(dados):
        # Todos os links falharam: uma faixa só de iniciais não vale o anexo.
        return None
    return montar_faixa([(nome, d) for (nome, _), d in zip(itens, dados)])
