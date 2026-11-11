"""Backup do banco: cópia consistente, comprimida, e mandada para o Discord.

    .venv/bin/python tools/backup.py             # copia, comprime e envia
    .venv/bin/python tools/backup.py --local     # copia e comprime, sem enviar
    .venv/bin/python tools/backup.py --guilda 1  # envia so os dados dela

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

Com `--guilda` (ou `BACKUP_GUILDA` no `.env`) o arquivo **enviado** leva só os
dados daquela guilda. É para o caso de o canal do backup viver num servidor e
o banco ter mais de um dentro: o canal de um servidor não tem por que receber
as fichas de outro. A cópia **local** continua inteira de propósito — ela é o
cinto de restaurar, e um cinto com metade dos dados é um cinto pior.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
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

# As seis tabelas que carregam `guild_id`. Todas as outras dezenove penduram
# nelas por `run_id` ou `personagem_id` com ON DELETE CASCADE — então apagar
# estas seis leva o resto junto. É por isso que esta lista pode ser curta sem
# deixar órfão: quem garante o resto é o esquema, não esta linha.
TABELAS_DA_GUILDA = (
    "personagens",
    "runs",
    "jogadores",
    "placar_organizacoes",
    "pontos_lancamentos",
    "config_guilda",
)


def copia_consistente(origem: Path, destino: Path) -> None:
    """Retrato do banco vivo, pela API de backup online do SQLite."""
    de = sqlite3.connect(f"file:{origem}?mode=ro", uri=True)
    para = sqlite3.connect(destino)
    try:
        de.backup(para)
    finally:
        para.close()
        de.close()


def deixar_so_a_guilda(caminho: Path, guild_id: int) -> None:
    """Apaga do ARQUIVO DE CÓPIA tudo que não é desta guilda.

    Nunca no banco de verdade: isto roda sobre a cópia que acabou de sair do
    `copia_consistente`.

    Dois detalhes que são a regra inteira, e sem os quais a fatia só PARECE
    uma fatia:

    O `PRAGMA foreign_keys = ON` tem de vir antes de qualquer DELETE. O SQLite
    nasce com as chaves estrangeiras DESLIGADAS, e desligadas ele ignora o
    `ON DELETE CASCADE`: as dezenove tabelas-filhas ficariam cheias de linhas
    de runs que não existem mais.

    O `VACUUM` no fim não é arrumação nem economia de espaço. Sem ele as
    páginas apagadas FICAM dentro do arquivo, na lista de livres, e os dados
    da outra guilda continuam legíveis para quem abrir o `.db` num editor
    hexadecimal. O VACUUM reescreve o banco só com as páginas vivas — é ele
    que faz o arquivo não carregar o que a gente acabou de tirar da vista.
    """
    con = sqlite3.connect(caminho)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        for tabela in TABELAS_DA_GUILDA:
            con.execute(f"DELETE FROM {tabela} WHERE guild_id != ?", (guild_id,))
        # VACUUM nao roda dentro de transacao, e os DELETEs abriram uma.
        con.commit()
        con.execute("VACUUM")
    finally:
        con.close()


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
        "--guilda", type=int, default=0,
        help="manda só os dados desta guilda (padrão: BACKUP_GUILDA do .env, "
             "ou o banco inteiro)",
    )
    parser.add_argument(
        "--quantas-ficam", type=int, default=QUANTAS_FICAM,
        help=f"cópias locais mantidas (padrão: {QUANTAS_FICAM}; 0 = todas)",
    )
    args = parser.parse_args()

    guilda = args.guilda
    if not guilda:
        do_env = os.getenv("BACKUP_GUILDA", "").strip()
        if do_env and not do_env.isdigit():
            # Parar e o certo, e nao seguir sem filtrar: um valor que nao vale
            # mandaria o banco INTEIRO para o canal de uma guilda so, que e
            # exatamente o que esta opcao existe para evitar. Falhar aqui custa
            # um backup; seguir custa os dados do outro servidor.
            print(f"BACKUP_GUILDA nao e um id: {do_env!r}", file=sys.stderr)
            return 1
        guilda = int(do_env or 0)

    banco = Path(config.DB_PATH)
    if not banco.exists():
        print(f"banco nao encontrado: {banco}", file=sys.stderr)
        return 1

    PASTA.mkdir(parents=True, exist_ok=True)
    agora = datetime.now(timezone.utc).astimezone(config.FUSO)
    nome = f"incursoes-{agora:%Y-%m-%d_%H%M}"
    cru = PASTA / f"{nome}.db"
    comprimido = PASTA / f"{nome}.db.gz"
    # A fatia da guilda nao fica no disco: ela existe para ser enviada, e sai
    # no `finally`. Vive numa SUBPASTA porque `limpar_antigas` olha so a pasta
    # de cima — assim uma fatia esquecida por um erro nunca entra na conta da
    # rotacao e nunca empurra um backup de verdade para fora.
    envio = PASTA / "enviando"

    try:
        comeco = time.monotonic()
        copia_consistente(banco, cru)
        contagens = contar(cru)
        comprimir(cru, comprimido)
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

        enviado = comprimido
        if guilda:
            envio.mkdir(parents=True, exist_ok=True)
            fatia = envio / f"{nome}.db"
            shutil.copyfile(cru, fatia)
            deixar_so_a_guilda(fatia, guilda)
            # As contagens passam a ser as da fatia: a mensagem no canal fala
            # do arquivo que esta anexado nela, e nao do banco da maquina.
            contagens = contar(fatia)
            resumo = " · ".join(f"{n} {t}" for t, n in contagens.items())
            enviado = envio / f"{nome}-g{guilda}.db.gz"
            comprimir(fatia, enviado)
            fatia.unlink(missing_ok=True)
            tamanho = enviado.stat().st_size
            print(f"  fatia da guilda {guilda}: {resumo or 'nada'} "
                  f"({tamanho / 1024:.1f} KB)")
            # Fatia vazia e a pior forma de este backup falhar: ele roda, nao
            # da erro, aparece no canal e nao leva dado nenhum. Quem olha o
            # canal ve um arquivo todo dia e dorme tranquilo. Entao grita —
            # e o grito vai tambem na mensagem do Discord, que e onde alguem
            # vai estar olhando.
            # `contagens` vem com as chaves e zeros dentro, e nao vazio:
            # `{'personagens': 0, ...}` e verdadeiro. Quem decide e a SOMA.
            vazia = not any(contagens.values())
            if vazia:
                print(
                    f"  ATENCAO: a fatia saiu VAZIA. O anexo nao protege nada.\n"
                    f"  Ou BACKUP_GUILDA={guilda} nao e a guilda onde se joga,\n"
                    f"  ou ela ainda nao tem dado. A copia local continua inteira."
                )

        texto = (
            f"🗄️ Backup de **{agora:%d/%m/%Y %H:%M}** — "
            f"{tamanho / 1024:.1f} KB" + (f" · {resumo}" if resumo else "")
            # Dito na mensagem porque um dia alguem vai baixar este arquivo com
            # pressa, e tem de saber na hora que ele NAO e o banco inteiro.
            + (f"\n-# só os dados da guilda {guilda}" if guilda else "")
            # E se a fatia saiu vazia, o canal e o unico lugar onde alguem vai
            # reparar. Um arquivo chegando todo dia parece backup funcionando.
            + (
                f"\n⚠️ **Este anexo está vazio** — a guilda {guilda} não tem "
                f"dado nenhum. Ele não protege nada."
                if guilda and vazia else ""
            )
        )
        return _enviar_e_contar(webhook, enviado, texto, comprimido)
    finally:
        cru.unlink(missing_ok=True)
        shutil.rmtree(envio, ignore_errors=True)


def _enviar_e_contar(
    webhook: str, enviado: Path, texto: str, local: Path
) -> int:
    try:
        enviar(webhook, enviado, texto)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as erro:
        # Falha de envio NAO apaga a copia local, e sai com erro para o
        # systemd registrar: o backup existe, só não saiu da maquina. E a copia
        # local e a INTEIRA, nao a fatia — nada se perde aqui.
        print(f"o envio falhou ({erro}); a copia local ficou em {local}",
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
