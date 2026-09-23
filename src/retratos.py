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
from urllib.parse import urljoin, urlparse

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
MAX_REDIRECIONAMENTOS = 3
PEDACO = 64 * 1024

# Sem User-Agent de navegador, muito site responde 403 a um bot — e aí o retrato
# que aparece na ficha (onde quem busca é o Discord) some na faixa da incursão.
CABECALHOS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}

# Content-Type que não diz nada: quem decide é a Pillow, ao abrir os bytes.
TIPOS_TOLERADOS = ("application/octet-stream", "binary/octet-stream")

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


async def _buscar(sessao, loop, url: Optional[str]) -> tuple[Optional[bytes], str]:
    """Baixa um retrato. Devolve (bytes, motivo); com bytes, o motivo é 'ok'.

    O Discord mostra na ficha qualquer imagem que os servidores *dele* consigam
    buscar; a faixa da incursão depende de **este** bot conseguir baixar. É por
    isso que existe o motivo: sem ele o jogador só vê a inicial e não sabe por quê.
    """
    if not url:
        return None, "sem link"
    visitadas = 0
    atual = url
    try:
        while True:
            if not await loop.run_in_executor(None, endereco_publico, atual):
                return None, "o endereço não é público"
            # Os redirecionamentos são seguidos na mão para que cada salto passe
            # pela mesma checagem — senão um link público poderia saltar para a
            # rede interna de quem hospeda o bot.
            async with sessao.get(atual, headers=CABECALHOS, allow_redirects=False) as r:
                if r.status in (301, 302, 303, 307, 308):
                    destino = r.headers.get("Location")
                    visitadas += 1
                    if not destino or visitadas > MAX_REDIRECIONAMENTOS:
                        return None, "redirecionamento demais"
                    atual = urljoin(atual, destino)
                    continue
                if r.status != 200:
                    return None, f"o site respondeu {r.status}"
                tipo = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                # Content-Type não decide sozinho: muito site serve imagem como
                # octet-stream, e quem valida de verdade é a Pillow ao abrir.
                if tipo and not (tipo.startswith("image/") or tipo in TIPOS_TOLERADOS):
                    return None, f"o link não é uma imagem ({tipo})"
                # Ler em pedaços até o fim: um `read(n)` só devolve o que já
                # chegou, e um PNG cortado no meio não abre como imagem.
                dados = bytearray()
                async for pedaco in r.content.iter_chunked(PEDACO):
                    dados += pedaco
                    if len(dados) > MAX_BYTES:
                        return None, f"passa de {MAX_BYTES // (1024 * 1024)} MB"
                dados = bytes(dados)
                if not dados:
                    return None, "veio vazio"
                if not _abre(dados):
                    return None, "o arquivo não abre como imagem"
                return dados, "ok"
    except asyncio.TimeoutError:
        return None, f"não respondeu em {TIMEOUT}s"
    except Exception as erro:
        # Retrato é enfeite: nada aqui pode impedir a incursão de começar.
        return None, f"falhou ({type(erro).__name__})"


def _abre(dados: bytes) -> bool:
    """Se a Pillow reconhece os bytes como imagem. Sem Pillow, confia no site."""
    if Image is None:
        return True
    try:
        with Image.open(BytesIO(dados)) as imagem:
            imagem.verify()
        return True
    except Exception:
        return False


async def diagnosticar(url: Optional[str]) -> tuple[bool, str]:
    """Tenta baixar um retrato e diz por que não deu, para avisar o jogador."""
    import aiohttp

    loop = asyncio.get_running_loop()
    tempo = aiohttp.ClientTimeout(total=TIMEOUT)
    try:
        async with aiohttp.ClientSession(timeout=tempo) as sessao:
            dados, motivo = await _buscar(sessao, loop, url)
    except Exception as erro:  # pragma: no cover - rede indisponível
        return False, f"falhou ({type(erro).__name__})"
    return dados is not None, motivo


async def baixar(urls: Sequence[Optional[str]]) -> list[Optional[bytes]]:
    """Baixa os retratos em paralelo; o que falhar volta None."""
    import aiohttp

    loop = asyncio.get_running_loop()
    tempo = aiohttp.ClientTimeout(total=TIMEOUT)
    async with aiohttp.ClientSession(timeout=tempo) as sessao:
        resultados = await asyncio.gather(
            *(_buscar(sessao, loop, u) for u in urls)
        )
    return [dados for dados, _motivo in resultados]


async def faixa(itens: Sequence[tuple[str, Optional[str]]]) -> Optional[bytes]:
    """Baixa os retratos e devolve o PNG do grupo, ou None."""
    if not disponivel() or not itens:
        return None
    dados = await baixar([url for _, url in itens])
    if not any(dados):
        # Todos os links falharam: uma faixa só de iniciais não vale o anexo.
        return None
    return montar_faixa([(nome, d) for (nome, _), d in zip(itens, dados)])
