"""O backup: cópia consistente de um banco VIVO, comprimida e restaurável.

O que importa aqui não é o envio — é que o arquivo guardado volte a ser um
banco inteiro. Um backup que não restaura é pior que nenhum: ele dá a
impressão de que o problema está resolvido.
"""
from __future__ import annotations

import asyncio
import contextlib
import io
import gzip
import importlib.util
import shutil
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import config, database as db  # noqa: E402
from fakes import (  # noqa: E402
    CANAL, CLASSE_PADRAO, GUILD, JOGADORES, TREINADAS, criar_grupo,
)

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


OUTRA = 777  # a outra guilda: o servidor de testes do dono
INTRUSO = "ZarpadorDaOutraGuilda"


async def _povoar_duas_guildas(conn):
    """Dados nas duas guildas, e nas tabelas-filhas das duas.

    Interessa encher também o que NÃO tem `guild_id` (itens, ouro, salas
    visitadas): é ali que um filtro malfeito deixa órfão.
    """
    # O grupo da nossa guilda ja veio do `preparar()`.
    nosso = (await db.listar_personagens(conn, GUILD, JOGADORES[0]))[0]["id"]
    nossa_run = await db.criar_run(conn, GUILD, CANAL, "cripta", JOGADORES[0])
    await db.adicionar_participante(conn, nossa_run, JOGADORES[0], nosso)
    await db.registrar_visita(conn, nossa_run, 1, "SALA_A")
    await db.lancar_ouro(conn, nosso, 50, "nossa", run_id=nossa_run)
    await db.lancar_pontos(conn, GUILD, "Guarda", 3, "nossa", run_id=nossa_run)
    await db.dar_item(conn, nosso, "corda")

    intruso = await db.criar_personagem(
        conn, OUTRA, 9001, INTRUSO, CLASSE_PADRAO, list(TREINADAS), nivel=5
    )
    outra_run = await db.criar_run(conn, OUTRA, 199, "cripta", 9001)
    await db.adicionar_participante(conn, outra_run, 9001, intruso)
    await db.registrar_visita(conn, outra_run, 1, "SALA_Z")
    await db.lancar_ouro(conn, intruso, 999, "da outra", run_id=outra_run)
    await db.lancar_pontos(conn, OUTRA, "Culto", 7, "da outra", run_id=outra_run)
    await db.dar_item(conn, intruso, "adaga")
    await conn.execute(
        "INSERT INTO jogadores (guild_id, user_id, ultima_incursao)"
        " VALUES (?, ?, ?)", (OUTRA, 9001, "cripta"),
    )
    await conn.execute(
        "INSERT INTO config_guilda (guild_id, intervalo_semanas) VALUES (?, ?)",
        (OUTRA, 9),
    )
    await conn.commit()
    return {"nossa_run": nossa_run, "outra_run": outra_run, "intruso": intruso}


async def caso_a_fatia_leva_so_uma_guilda_e_sem_rastro():
    """A fatia de uma guilda não leva NADA da outra — nem nas páginas livres.

    Duas regras moram aqui, e as duas são fáceis de perder sem perceber:

    As dezenove tabelas que não têm `guild_id` penduram em `runs` e
    `personagens` com ON DELETE CASCADE. Elas só saem se as chaves
    estrangeiras estiverem LIGADAS — e o SQLite nasce com elas desligadas. Com
    o pragma esquecido, a fatia fica com o ouro e os itens de personagens que
    não existem mais nela: um banco que não bate consigo mesmo.

    E apagar não é remover. As páginas apagadas ficam no arquivo, na lista de
    livres, com o conteúdo intacto; o nome do personagem da outra guilda se lê
    com um editor hexadecimal. É o `VACUUM` que reescreve o banco só com as
    páginas vivas. Por isso o caso procura o nome nos BYTES do arquivo, e não
    num SELECT: o SELECT já estaria limpo com a regra pela metade.
    """
    conn = await preparar()
    criados = await _povoar_duas_guildas(conn)
    pasta = BANCO.parent / "fatia_do_teste"
    shutil.rmtree(pasta, ignore_errors=True)
    pasta.mkdir(parents=True)

    inteiro = BACKUP.contar(BANCO)
    assert inteiro["personagens"] == len(JOGADORES) + 1, inteiro

    copia = pasta / "copia.db"
    BACKUP.copia_consistente(BANCO, copia)
    BACKUP.deixar_so_a_guilda(copia, GUILD)

    # As contagens que a mensagem do canal vai citar passam a ser as da fatia.
    assert BACKUP.contar(copia) == {
        "personagens": len(JOGADORES), "runs": 1, "pontos_lancamentos": 1
    }, BACKUP.contar(copia)

    volta = sqlite3.connect(copia)
    try:
        assert volta.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

        # As tabelas com `guild_id` saem do PRÓPRIO esquema, e não da lista do
        # backup. Se o caso lesse a lista, apagar uma tabela dela deixaria o
        # caso verde: ele deixaria de olhar justamente a que foi esquecida.
        # Assim ele também cobra a lista de uma tabela nova, no dia em que
        # alguém criar uma com `guild_id` e não lembrar deste arquivo.
        todas = [
            t for (t,) in volta.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        ]
        com_guilda = [
            t for t in todas
            if any(
                coluna[1] == "guild_id"
                for coluna in volta.execute(f"PRAGMA table_info({t})")
            )
        ]
        assert sorted(com_guilda) == sorted(BACKUP.TABELAS_DA_GUILDA), (
            "o esquema tem tabela com guild_id fora de TABELAS_DA_GUILDA",
            sorted(com_guilda), sorted(BACKUP.TABELAS_DA_GUILDA),
        )
        for tabela in com_guilda:
            sobrou = volta.execute(
                f"SELECT COUNT(*) FROM {tabela} WHERE guild_id != ?", (GUILD,)
            ).fetchone()[0]
            assert sobrou == 0, (tabela, sobrou)

        # E as filhas foram com elas, pelo CASCADE: nada aponta para a run nem
        # para o personagem da outra guilda.
        orfas = {
            "run_participantes": ("run_id", criados["outra_run"]),
            "run_salas": ("run_id", criados["outra_run"]),
            "ouro_lancamentos": ("personagem_id", criados["intruso"]),
            "personagem_itens": ("personagem_id", criados["intruso"]),
        }
        for tabela, (coluna, valor) in orfas.items():
            quantas = volta.execute(
                f"SELECT COUNT(*) FROM {tabela} WHERE {coluna} = ?", (valor,)
            ).fetchone()[0]
            assert quantas == 0, (tabela, quantas)

        # O que é nosso ficou inteiro: a fatia não é só "menor", é certa.
        assert volta.execute(
            "SELECT COUNT(*) FROM run_salas WHERE run_id = ?",
            (criados["nossa_run"],),
        ).fetchone()[0] == 1
        assert volta.execute(
            "SELECT COUNT(*) FROM personagem_itens WHERE item_id = 'corda'"
        ).fetchone()[0] == 1
        assert volta.execute(
            "SELECT SUM(ouro) FROM ouro_lancamentos"
        ).fetchone()[0] == 50
    finally:
        volta.close()

    # A prova do VACUUM: o nome nao esta nem nos bytes crus do arquivo.
    assert INTRUSO.encode() not in copia.read_bytes(), (
        "o nome da outra guilda continua legivel no arquivo: faltou o VACUUM"
    )

    await conn.close()
    shutil.rmtree(pasta, ignore_errors=True)
    BANCO.unlink(missing_ok=True)
    print("  a fatia leva so uma guilda, sem orfao e sem rastro: ok")


async def caso_a_fatia_vazia_grita_em_vez_de_passar_batido():
    """Fatia vazia é a pior forma de este backup falhar, e ela ACONTECEU.

    Em produção o `BACKUP_GUILDA` apontava para a guilda certa — e essa guilda
    ainda não tinha ninguém. O backup rodava todo dia, não dava erro, chegava
    no canal com 4,6 KB e não protegia nada. Quem olhasse o canal veria um
    arquivo chegando e dormiria tranquilo.

    Então o aviso tem de sair nos DOIS lugares: no log, que é onde o systemd
    guarda, e na mensagem do canal, que é onde alguém realmente olha.
    """
    conn = await preparar()
    await _povoar_duas_guildas(conn)
    pasta = BANCO.parent / "fatia_vazia"
    shutil.rmtree(pasta, ignore_errors=True)
    BACKUP.PASTA = pasta
    BACKUP.os.environ["BACKUP_WEBHOOK"] = "https://discord.com/api/webhooks/1/abc"
    # Uma guilda que existe no .env e nao existe no banco: o caso real.
    vazia = 999999999999999999
    BACKUP.os.environ["BACKUP_GUILDA"] = str(vazia)
    BACKUP.sys.argv = ["backup.py"]

    pedidos = []

    class RespostaFalsa:
        def read(self):
            return b""

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    original = BACKUP.urllib.request.urlopen
    BACKUP.urllib.request.urlopen = lambda p, timeout=None: (
        pedidos.append(p) or RespostaFalsa()
    )
    saida = io.StringIO()
    try:
        with contextlib.redirect_stdout(saida):
            assert BACKUP.main() == 0
    finally:
        BACKUP.urllib.request.urlopen = original
        BACKUP.os.environ.pop("BACKUP_GUILDA", None)
        BACKUP.os.environ.pop("BACKUP_WEBHOOK", None)

    impresso = saida.getvalue()
    assert "VAZIA" in impresso, f"o log nao avisou: {impresso}"
    assert str(vazia) in impresso, "o aviso nao diz qual guilda"

    corpo = pedidos[0].data
    # S\u00f3 peda\u00e7os ASCII: o `json.dumps` do payload escapa o acento, ent\u00e3o
    # procurar "est\u00e1 vazio" com acento nunca casaria com o corpo.
    assert b"anexo" in corpo and b"vazio" in corpo, (
        "a mensagem do canal nao avisou que o anexo esta vazio"
    )

    # E o alarme NAO toca quando a fatia tem dado: aviso que grita sempre
    # vira ruido, e ruido e ignorado.
    pedidos.clear()
    BACKUP.os.environ["BACKUP_WEBHOOK"] = "https://discord.com/api/webhooks/1/abc"
    BACKUP.os.environ["BACKUP_GUILDA"] = str(GUILD)
    BACKUP.urllib.request.urlopen = lambda p, timeout=None: (
        pedidos.append(p) or RespostaFalsa()
    )
    saida = io.StringIO()
    try:
        with contextlib.redirect_stdout(saida):
            assert BACKUP.main() == 0
    finally:
        BACKUP.urllib.request.urlopen = original
        BACKUP.os.environ.pop("BACKUP_GUILDA", None)
        BACKUP.os.environ.pop("BACKUP_WEBHOOK", None)
    assert "VAZIA" not in saida.getvalue(), "o alarme tocou com a fatia cheia"
    assert b"vazio" not in pedidos[0].data, "a mensagem avisou vazio sem estar"

    await conn.close()
    shutil.rmtree(pasta, ignore_errors=True)
    BANCO.unlink(missing_ok=True)
    print("  a fatia vazia grita no log e no canal, e so quando e vazia: ok")


async def caso_main_envia_a_fatia_e_guarda_o_inteiro():
    """Com `--guilda`, o que SAI é a fatia e o que FICA é o banco inteiro.

    A cópia local é o cinto de restaurar, e é de propósito que ela não é
    filtrada: perder o canal custa um download, perder a máquina custa tudo.
    Quem é filtrado é o anexo — o canal de um servidor não recebe as fichas
    de outro.
    """
    conn = await preparar()
    await _povoar_duas_guildas(conn)
    pasta = BANCO.parent / "envio_da_fatia"
    shutil.rmtree(pasta, ignore_errors=True)
    BACKUP.PASTA = pasta
    BACKUP.os.environ["BACKUP_WEBHOOK"] = "https://discord.com/api/webhooks/1/abc"
    BACKUP.os.environ["BACKUP_GUILDA"] = str(GUILD)
    BACKUP.sys.argv = ["backup.py"]

    pedidos = []

    class RespostaFalsa:
        def read(self):
            return b""

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    original = BACKUP.urllib.request.urlopen
    BACKUP.urllib.request.urlopen = lambda p, timeout=None: (
        pedidos.append(p) or RespostaFalsa()
    )
    try:
        assert BACKUP.main() == 0
    finally:
        BACKUP.urllib.request.urlopen = original
        BACKUP.os.environ.pop("BACKUP_GUILDA", None)
        BACKUP.os.environ.pop("BACKUP_WEBHOOK", None)

    # A copia local: uma so, com o nome de sempre, e com as DUAS guildas.
    guardadas = list(pasta.glob("incursoes-*.db.gz"))
    assert len(guardadas) == 1, guardadas
    inteiro = restaurar(guardadas[0], pasta / "local.db")
    try:
        assert sorted(
            g for (g,) in inteiro.execute("SELECT DISTINCT guild_id FROM personagens")
        ) == [GUILD, OUTRA]
    finally:
        inteiro.close()

    # O anexo: o nome diz a guilda, e dentro dele so ela.
    assert len(pedidos) == 1, pedidos
    corpo = pedidos[0].data
    assert f"-g{GUILD}.db.gz".encode() in corpo, "o nome do anexo nao diz a guilda"
    # Sem o "só": o `json.dumps` do payload escapa o acento (`s\\u00f3`).
    assert f"os dados da guilda {GUILD}".encode() in corpo, (
        "a mensagem tem de avisar que o arquivo NAO e o banco inteiro"
    )
    # E as contagens da mensagem sao as do ANEXO, nao as do banco da maquina:
    # sao 5 personagens na fatia e 6 no banco. Uma mensagem que cita o banco
    # inteiro ao lado de um arquivo filtrado ensina a ler o numero errado.
    assert f"{len(JOGADORES)} personagens".encode() in corpo, corpo[:400]
    assert f"{len(JOGADORES) + 1} personagens".encode() not in corpo, (
        "a mensagem contou o banco inteiro, e o anexo e so a fatia"
    )
    anexo = pasta / "anexo.db.gz"
    comeco = corpo.index(b"\x1f\x8b")  # o cabecalho do gzip
    anexo.write_bytes(corpo[comeco:corpo.rindex(b"\r\n--")])
    fatia = restaurar(anexo, pasta / "fatia.db")
    try:
        assert [
            g for (g,) in fatia.execute("SELECT DISTINCT guild_id FROM personagens")
        ] == [GUILD]
        assert INTRUSO.encode() not in anexo.read_bytes()
    finally:
        fatia.close()

    # E a fatia nao ficou no disco: a pasta de envio sai junto.
    assert not (pasta / "enviando").exists(), "a fatia ficou guardada"

    await conn.close()
    shutil.rmtree(pasta, ignore_errors=True)
    BANCO.unlink(missing_ok=True)
    print("  main() envia a fatia e guarda o banco inteiro: ok")


async def caso_backup_guilda_invalido_nao_envia_nada():
    """`BACKUP_GUILDA` com lixo PARA o backup, e não manda o banco inteiro.

    Seguir sem filtrar seria o pior dos dois: o canal de um servidor
    receberia, calado, as fichas do outro. Falhar custa um backup; seguir
    custa os dados.
    """
    conn = await preparar()
    pasta = BANCO.parent / "guilda_invalida"
    shutil.rmtree(pasta, ignore_errors=True)
    BACKUP.PASTA = pasta
    BACKUP.os.environ["BACKUP_WEBHOOK"] = "https://discord.com/api/webhooks/1/abc"
    BACKUP.os.environ["BACKUP_GUILDA"] = "o-id-do-servidor"
    BACKUP.sys.argv = ["backup.py"]

    pedidos = []

    class RespostaFalsa:
        def read(self):
            return b""

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    # Um dublê que FUNCIONA, de propósito: se ele estourasse, o caso ficaria
    # vermelho por estar quebrado e não por o backup ter enviado o banco.
    original = BACKUP.urllib.request.urlopen
    BACKUP.urllib.request.urlopen = lambda p, timeout=None: (
        pedidos.append(p) or RespostaFalsa()
    )
    try:
        assert BACKUP.main() == 1, "lixo em BACKUP_GUILDA tem de parar o backup"
    finally:
        BACKUP.urllib.request.urlopen = original
        BACKUP.os.environ.pop("BACKUP_GUILDA", None)
        BACKUP.os.environ.pop("BACKUP_WEBHOOK", None)

    assert pedidos == [], "mandou o banco mesmo sem saber qual guilda filtrar"

    await conn.close()
    shutil.rmtree(pasta, ignore_errors=True)
    BANCO.unlink(missing_ok=True)
    print("  BACKUP_GUILDA invalido para o backup e nao envia nada: ok")


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
        await caso_a_fatia_leva_so_uma_guilda_e_sem_rastro()
        await caso_main_envia_a_fatia_e_guarda_o_inteiro()
        await caso_backup_guilda_invalido_nao_envia_nada()
        await caso_a_fatia_vazia_grita_em_vez_de_passar_batido()
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
