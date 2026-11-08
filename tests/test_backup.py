"""O backup: cópia consistente de um banco VIVO, comprimida e restaurável.

O que importa aqui não é o envio — é que o arquivo guardado volte a ser um
banco inteiro. Um backup que não restaura é pior que nenhum: ele dá a
impressão de que o problema está resolvido.
"""
from __future__ import annotations

import asyncio
import gzip
import importlib.util
import shutil
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import config, database as db  # noqa: E402
from fakes import GUILD, JOGADORES, criar_grupo  # noqa: E402

BANCO = Path(__file__).resolve().parent / "teste_backup.db"
_ABERTAS = []


def _modulo():
    """O script vive em tools/, fora do pacote: carrega pelo caminho."""
    caminho = RAIZ / "tools" / "backup.py"
    spec = importlib.util.spec_from_file_location("backup_do_bot", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


BACKUP = _modulo()


async def preparar():
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass
    config.DB_PATH = BANCO
    BANCO.unlink(missing_ok=True)
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    await criar_grupo(conn, nivel=3)
    return conn


def restaurar(comprimido: Path, destino: Path) -> sqlite3.Connection:
    with gzip.open(comprimido, "rb") as entrada, open(destino, "wb") as saida:
        shutil.copyfileobj(entrada, saida)
    return sqlite3.connect(destino)


async def caso_a_copia_sai_de_um_banco_aberto_e_restaura():
    """A cópia é tirada com o banco ABERTO, e o que volta é um banco inteiro.

    O caso prova o que importa no dia de restaurar: o `.gz` guardado volta a
    ser um banco com `integrity_check` ok e os mesmos dados, tirado sem fechar
    a conexão do bot.

    **O que ele NÃO prova**, e está aqui escrito para ninguém achar que prova:
    que a API de backup online seja melhor que um `cp`. Trocar
    `copia_consistente` por um `shutil.copyfile` deixa este caso VERDE —
    porque num banco quieto as duas coisas dão o mesmo arquivo. A diferença
    só aparece quando o `cp` pega uma transação no meio, e forçar isso depende
    de quando o SQLite derrama o cache no arquivo: daria um caso que passa ou
    falha por sorte, que é pior que caso nenhum. A escolha da API online é
    argumento, não regra coberta.
    """
    conn = await preparar()
    pasta = BANCO.parent / "backup_do_teste"
    shutil.rmtree(pasta, ignore_errors=True)
    pasta.mkdir(parents=True)

    # Escreve DEPOIS de abrir a conexão e sem fechá-la: é esse o estado em que
    # o backup roda de verdade.
    await db.lancar_ouro(
        conn,
        (await db.listar_personagens(conn, GUILD, JOGADORES[0]))[0]["id"],
        123, "antes do backup",
    )
    antes = BACKUP.contar(BANCO)
    assert antes["personagens"] == len(JOGADORES), antes

    cru = pasta / "copia.db"
    BACKUP.copia_consistente(BANCO, cru)
    comprimido = pasta / "copia.db.gz"
    BACKUP.comprimir(cru, comprimido)

    # Comprimir vale a pena: é o que faz o tamanho não ser problema.
    assert comprimido.stat().st_size < cru.stat().st_size, (
        comprimido.stat().st_size, cru.stat().st_size
    )

    volta = restaurar(comprimido, pasta / "restaurado.db")
    try:
        assert volta.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        for tabela, quantas in antes.items():
            agora = volta.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
            assert agora == quantas, (tabela, quantas, agora)
        # E o que foi escrito com a conexão aberta está lá.
        assert volta.execute(
            "SELECT COUNT(*) FROM ouro_lancamentos WHERE motivo = 'antes do backup'"
        ).fetchone()[0] == 1
    finally:
        volta.close()

    await conn.close()
    shutil.rmtree(pasta, ignore_errors=True)
    BANCO.unlink(missing_ok=True)
    print("  a copia sai de um banco aberto e volta inteira: ok")


def caso_a_rotacao_mantem_so_as_mais_novas():
    """14 cópias no disco, e as velhas saem — senão o disco enche sozinho."""
    pasta = BANCO.parent / "rotacao_do_teste"
    shutil.rmtree(pasta, ignore_errors=True)
    pasta.mkdir(parents=True)
    # Os nomes têm a data dentro, então a ordem alfabética É a cronológica.
    nomes = [f"incursoes-2026-11-{dia:02d}_0400.db.gz" for dia in range(1, 21)]
    for nome in nomes:
        (pasta / nome).write_bytes(b"x")
    # Um arquivo que não é backup não entra na conta nem é apagado.
    (pasta / "leia-me.txt").write_text("nao sou backup", encoding="utf-8")

    apagadas = BACKUP.limpar_antigas(pasta, 14)
    ficaram = sorted(p.name for p in pasta.glob("incursoes-*.db.gz"))
    assert len(ficaram) == 14, ficaram
    assert ficaram == nomes[-14:], ficaram
    assert len(apagadas) == 6, apagadas
    assert (pasta / "leia-me.txt").exists(), "apagou o que nao era backup"

    # 0 quer dizer "guarda todas", e não "apaga todas".
    assert BACKUP.limpar_antigas(pasta, 0) == []
    assert len(list(pasta.glob("incursoes-*.db.gz"))) == 14

    shutil.rmtree(pasta, ignore_errors=True)
    print("  a rotacao mantem as 14 mais novas, e so backups: ok")


def caso_o_envio_leva_user_agent_e_o_arquivo():
    """O POST do webhook tem de levar User-Agent, e o arquivo dentro dele.

    Este caso nasceu de um 403 em produção. O Discord fica atrás do
    Cloudflare, e ele RECUSA o User-Agent padrão do `urllib`
    ("Python-urllib/3.x") com 403 código 1010 — antes de chegar à API. A
    mensagem não fala de User-Agent, então o 403 parece ser do webhook, e a
    primeira coisa que se faz é desconfiar da URL, que estava certa.

    O envio não tinha caso nenhum: a suíte cobria "sem webhook, guarda local",
    que é justamente o ramo que NÃO envia. O dublê abaixo não fala com a rede
    — ele guarda a requisição que o `enviar` montou e o teste olha para ela.
    """
    pasta = BANCO.parent / "envio_do_teste"
    shutil.rmtree(pasta, ignore_errors=True)
    pasta.mkdir(parents=True)
    arquivo = pasta / "incursoes-2026-11-08_0400.db.gz"
    arquivo.write_bytes(b"conteudo-do-backup")

    pedidos = []

    class RespostaFalsa:
        def read(self):
            return b""

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    def urlopen_falso(pedido, timeout=None):
        pedidos.append(pedido)
        return RespostaFalsa()

    original = BACKUP.urllib.request.urlopen
    BACKUP.urllib.request.urlopen = urlopen_falso
    try:
        BACKUP.enviar(
            "https://discord.com/api/webhooks/1/abc", arquivo, "texto do backup"
        )
    finally:
        BACKUP.urllib.request.urlopen = original

    assert len(pedidos) == 1, pedidos
    pedido = pedidos[0]

    # O User-Agent, que é o conserto deste caso. `get_header` normaliza o nome.
    agente = pedido.get_header("User-agent") or ""
    assert agente, "sem User-Agent o Cloudflare devolve 403 antes da API"
    assert "Python-urllib" not in agente, (
        f"o User-Agent padrao do urllib e recusado com 403: {agente!r}"
    )

    assert pedido.method == "POST"
    tipo = pedido.get_header("Content-type") or ""
    assert tipo.startswith("multipart/form-data; boundary="), tipo
    limite = tipo.split("boundary=", 1)[1]

    corpo = pedido.data
    assert limite.encode() in corpo, "o corpo tem de usar o boundary declarado"
    assert arquivo.read_bytes() in corpo, "o arquivo nao foi para dentro do POST"
    assert arquivo.name.encode() in corpo, "o nome do arquivo vai no filename"
    assert b"texto do backup" in corpo, "o resumo vai no payload_json"
    # O backup nao marca ninguem de madrugada.
    assert b'"allowed_mentions": {"parse": []}' in corpo, corpo[:400]

    shutil.rmtree(pasta, ignore_errors=True)
    print("  o envio leva User-Agent, o arquivo e o resumo: ok")


async def caso_sem_webhook_guarda_local_e_sai_bem():
    """Servidor sem webhook configurado não é erro — é envio não configurado.

    O script sai com 0 e deixa a cópia: quem acabou de instalar consegue
    provar que o backup funciona antes de criar o webhook.
    """
    conn = await preparar()
    pasta = BANCO.parent / "sem_webhook"
    shutil.rmtree(pasta, ignore_errors=True)
    BACKUP.PASTA = pasta
    BACKUP.os.environ.pop("BACKUP_WEBHOOK", None)
    BACKUP.sys.argv = ["backup.py"]

    assert BACKUP.main() == 0
    guardadas = list(pasta.glob("incursoes-*.db.gz"))
    assert len(guardadas) == 1, guardadas

    # E o arquivo guardado restaura, que é a única coisa que importa dele.
    volta = restaurar(guardadas[0], pasta / "restaurado.db")
    try:
        assert volta.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        volta.close()

    # Banco inexistente é erro de verdade, e sai com 1.
    await conn.close()
    BANCO.unlink(missing_ok=True)
    assert BACKUP.main() == 1

    shutil.rmtree(pasta, ignore_errors=True)
    print("  sem webhook, guarda local e sai bem; sem banco, sai com erro: ok")


async def main():
    try:
        await caso_a_copia_sai_de_um_banco_aberto_e_restaura()
        caso_a_rotacao_mantem_so_as_mais_novas()
        caso_o_envio_leva_user_agent_e_o_arquivo()
        await caso_sem_webhook_guarda_local_e_sai_bem()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        BANCO.unlink(missing_ok=True)


asyncio.run(main())
print("TESTES DO BACKUP PASSARAM")
