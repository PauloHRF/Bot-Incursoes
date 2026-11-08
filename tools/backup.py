"""Backup do banco: cópia consistente, comprimida, e mandada para o Discord.

    .venv/bin/python tools/backup.py            # copia, comprime e envia
    .venv/bin/python tools/backup.py --local    # copia e comprime, sem enviar

**Não para o bot.** A cópia sai pela API de backup online do SQLite
(`Connection.backup`), que tira um retrato consistente de um banco aberto e
sendo escrito. Um `cp` do arquivo vivo pode pegar uma escrita no meio e
devolver um banco corrompido justamente no dia em que ele for preciso.

O destino é um **webhook** do Discord, e não o próprio bot, por três razões:
o backup funciona com o bot parado (que é exatamente quando se quer um, antes
de uma atualização), dá para rodar na mão e ver o resultado na hora, e o
webhook só sabe escrever num canal — não lê nada e não administra nada.

Sem `BACKUP_WEBHOOK` no `.env` ele só guarda a cópia local, avisa e sai bem:
um servidor sem webhook configurado não é um erro, é um servidor que ainda
não configurou o envio.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import config  # noqa: E402

PASTA = RAIZ / "data" / "backups"
# Quantas cópias locais ficam. Elas são o segundo cinto: dão para restaurar
# sem baixar nada, e cobrem o caso de o envio ter falhado sem ninguém ver.
QUANTAS_FICAM = 14
TEMPO_LIMITE = 60

# As tabelas que contam a história do grupo, e que a mensagem cita para o
# backup se ler de longe: um arquivo que diz "0 personagens" é um aviso.
CONTAGENS = ("personagens", "runs", "pontos_lancamentos")

# O Discord fica atrás do Cloudflare, e ele RECUSA o User-Agent padrão do
# `urllib` ("Python-urllib/3.x") com **403, código 1010** — antes de a
# requisição chegar à API. A mensagem não diz nada de User-Agent, então o 403
# parece ser do webhook: eu perdi um tempo achando que a URL estava errada.
#
# O formato é o que a documentação do Discord pede de um cliente de API:
# `DiscordBot ($url, $versao)`.
USER_AGENT = "DiscordBot (https://github.com/PauloHRF/Bot-Incursoes, 2.0)"


def copia_consistente(origem: Path, destino: Path) -> None:
    """Retrato do banco vivo, pela API de backup online do SQLite."""
    de = sqlite3.connect(f"file:{origem}?mode=ro", uri=True)
    para = sqlite3.connect(destino)
    try:
        de.backup(para)
    finally:
        para.close()
        de.close()


def contar(caminho: Path) -> dict[str, int]:
    con = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True)
    try:
        existem = {
            r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        return {
            t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in CONTAGENS if t in existem
        }
    finally:
        con.close()


def comprimir(origem: Path, destino: Path) -> None:
    # mtime=0: o .gz de dois backups iguais sai byte a byte igual, e dá para
    # ver que nada mudou sem abrir.
    with open(origem, "rb") as entrada:
        with gzip.GzipFile(destino, "wb", compresslevel=9, mtime=0) as saida:
            while bloco := entrada.read(1 << 20):
                saida.write(bloco)


def enviar(webhook: str, arquivo: Path, texto: str) -> None:
    """POST multipart na mão: urllib é da biblioteca padrão, requests não."""
    limite = f"----backup{uuid.uuid4().hex}"
    corpo = bytearray()

    def campo(nome: str, valor: str) -> None:
        corpo.extend(
            f"--{limite}\r\nContent-Disposition: form-data; name=\"{nome}\""
            f"\r\n\r\n{valor}\r\n".encode()
        )

    # `allowed_mentions` vazio: o backup não marca ninguém de madrugada.
    campo("payload_json", json.dumps(
        {"content": texto, "allowed_mentions": {"parse": []}}
    ))
    corpo.extend(
        f"--{limite}\r\nContent-Disposition: form-data; name=\"files[0]\";"
        f" filename=\"{arquivo.name}\"\r\n"
        f"Content-Type: application/gzip\r\n\r\n".encode()
    )
    corpo.extend(arquivo.read_bytes())
    corpo.extend(f"\r\n--{limite}--\r\n".encode())

    pedido = urllib.request.Request(
        webhook,
        data=bytes(corpo),
        headers={
            "Content-Type": f"multipart/form-data; boundary={limite}",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    with urllib.request.urlopen(pedido, timeout=TEMPO_LIMITE) as resposta:
        resposta.read()


def limpar_antigas(pasta: Path, quantas: int) -> list[Path]:
    """Apaga as cópias mais velhas, mantendo as `quantas` mais novas."""
    todas = sorted(pasta.glob("incursoes-*.db.gz"))
    sobrando = todas[:-quantas] if quantas > 0 else []
    for velha in sobrando:
        velha.unlink(missing_ok=True)
    return sobrando


def main() -> int:
    parser = argparse.ArgumentParser(description="Backup do banco do bot.")
    parser.add_argument(
        "--local", action="store_true",
        help="só guarda a cópia local, sem mandar para o Discord",
    )
    parser.add_argument(
        "--quantas-ficam", type=int, default=QUANTAS_FICAM,
        help=f"cópias locais mantidas (padrão: {QUANTAS_FICAM}; 0 = todas)",
    )
    args = parser.parse_args()

    banco = Path(config.DB_PATH)
    if not banco.exists():
        print(f"banco nao encontrado: {banco}", file=sys.stderr)
        return 1

    PASTA.mkdir(parents=True, exist_ok=True)
    agora = datetime.now(timezone.utc).astimezone(config.FUSO)
    nome = f"incursoes-{agora:%Y-%m-%d_%H%M}"
    cru = PASTA / f"{nome}.db"
    comprimido = PASTA / f"{nome}.db.gz"

    comeco = time.monotonic()
    copia_consistente(banco, cru)
    contagens = contar(cru)
    comprimir(cru, comprimido)
    cru.unlink(missing_ok=True)
    demorou = time.monotonic() - comeco

    tamanho = comprimido.stat().st_size
    resumo = " · ".join(f"{n} {t}" for t, n in contagens.items())
    print(
        f"{comprimido.name}: {tamanho / 1024:.1f} KB "
        f"(de {banco.stat().st_size / 1024:.1f} KB) em {demorou:.1f}s"
    )
    if resumo:
        print(f"  {resumo}")
    apagadas = limpar_antigas(PASTA, args.quantas_ficam)
    if apagadas:
        print(f"  {len(apagadas)} copia(s) antiga(s) apagada(s)")

    if args.local:
        return 0
    webhook = os.getenv("BACKUP_WEBHOOK", "").strip()
    if not webhook:
        print("  BACKUP_WEBHOOK nao esta no .env: a copia ficou so aqui")
        return 0
    texto = (
        f"🗄️ Backup de **{agora:%d/%m/%Y %H:%M}** — "
        f"{tamanho / 1024:.1f} KB" + (f" · {resumo}" if resumo else "")
    )
    try:
        enviar(webhook, comprimido, texto)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as erro:
        # Falha de envio NAO apaga a copia local, e sai com erro para o
        # systemd registrar: o backup existe, só não saiu da maquina.
        print(f"o envio falhou ({erro}); a copia local ficou em {comprimido}",
              file=sys.stderr)
        # O que o código do erro costuma querer dizer. Sem isto, 401 e 404 (a
        # URL) e 403 (o Cloudflare) são a mesma linha vermelha, e a primeira
        # coisa que se faz é desconfiar da URL — que nos dois últimos casos
        # está certa.
        codigo = getattr(erro, "code", None)
        pistas = {
            401: "a URL do webhook esta errada (BACKUP_WEBHOOK no .env)",
            404: "o webhook nao existe mais: refaca ele no canal",
            403: "o Cloudflare recusou a requisicao, nao o Discord",
            413: "o arquivo passou do limite de upload do canal",
            429: "limite de requisicoes; o backup de amanha tenta de novo",
        }
        if codigo in pistas:
            print(f"  ({codigo}: {pistas[codigo]})", file=sys.stderr)
        return 2
    print("  enviado ao canal do Discord")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
