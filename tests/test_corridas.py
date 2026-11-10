"""As corridas: dois cliques no mesmo instante.

O bot roda num loop de eventos, com UMA conexão de banco. Isso dá uma falsa
sensação de segurança: a conexão serializa cada *statement*, e é fácil ler daí
que ela serializa também as sequências. **Não serializa.** Todo `await`
devolve o controle ao loop, e a outra interação roda ali, entre a leitura e a
escrita.

Então "conferir e depois gravar" é duas operações, e entre elas cabe uma run
inteira. Dois cliques no mesmo instante passavam os dois pela conferência:

  - com 100 de ouro, duas compras de 80 eram aprovadas e o saldo ia a **-60**;
  - com quatro na run, duas entradas faziam um grupo de **seis**, que começava.

O conserto dos dois é o mesmo, e não é trava: a condição desce para DENTRO do
`INSERT`, num `SELECT ... WHERE`, que é um statement só e não tem meio. Quem
perde a corrida leva `False` do próprio banco.

Os casos aqui usam `asyncio.gather` porque chamadas sequenciais NÃO provam
nada: a segunda já encontraria a primeira gravada e seria recusada de todo
jeito, mesmo com o bug no lugar.

O último caso é o mesmo buraco esticado: um **menu** que fica no canal. Entre
conferir e agir ali não cabe um `await`, cabem minutos — e um cheque feito
antes de abrir o menu não vale mais quando o botão é clicado.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import (  # noqa: E402
    config, consumiveis as K, database as db, itens, mercado,
)
from src.cogs.mercado import tentar_comprar  # noqa: E402
from src.cogs.incursao import Incursoes  # noqa: E402
from fakes import (  # noqa: E402
    CANAL,
    CLASSE_PADRAO,
    GUILD,
    TREINADAS,
    FakeBot,
    FakeCanal,
    FakeInteraction,
    leu,
    montar_conteudo,
)

BANCO = Path(__file__).resolve().parent / "teste_corridas.db"
SEMANA = "2026-W45"
_ABERTAS = []


class BotDeVariosCanais(FakeBot):
    """O `FakeBot` só conhece um canal, e duas runs vivas pedem dois."""

    def __init__(self, conn, canais):
        super().__init__(conn, canais[0])
        self.canais = {c.id: c for c in canais}

    def get_channel(self, canal_id):
        return self.canais.get(canal_id)


async def preparar(quantos=6, canais=1):
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass
    config.DB_PATH = BANCO
    BANCO.unlink(missing_ok=True)
    config.TAMANHO_GRUPO = 5
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    # Seis jogadores: o teto é cinco, e é com o sexto que a corrida acontece.
    users = list(range(201, 201 + quantos))
    for user_id in users:
        await db.criar_personagem(
            conn, GUILD, user_id, f"Heroi{user_id}", CLASSE_PADRAO,
            list(TREINADAS), nivel=8,
        )
    lista = [FakeCanal(CANAL + i) for i in range(canais)]
    cog = Incursoes(BotDeVariosCanais(conn, lista))
    montar_conteudo(cog, tier=4)
    return conn, (lista[0] if canais == 1 else lista), cog, users


async def _pid(conn, user_id):
    return (await db.listar_personagens(conn, GUILD, user_id))[0]["id"]


async def _fechar(conn):
    await conn.close()
    BANCO.unlink(missing_ok=True)


# ------------------------------------------------------------------ ouro


async def caso_duas_compras_nao_gastam_o_mesmo_ouro():
    """Com 100 de ouro, duas compras de 80 ao mesmo tempo: só uma passa.

    Era o relato mais caro: as duas eram aprovadas e o saldo ficava em -60,
    com os dois itens na bolsa. O personagem saía da loja devendo.
    """
    conn, _canal, _cog, users = await preparar(quantos=1)
    pid = await _pid(conn, users[0])
    await db.lancar_ouro(conn, pid, 100, "semente")

    aprovadas = await asyncio.gather(
        db.comprar(conn, pid, "espada", 80),
        db.comprar(conn, pid, "escudo", 80),
    )
    assert sum(aprovadas) == 1, f"as duas compras passaram: {aprovadas}"
    saldo = await db.ouro(conn, pid)
    assert saldo == 20, f"o saldo tinha de ser 20, e foi {saldo}"
    assert saldo >= 0, "saldo negativo: alguem comprou com ouro que nao tinha"
    bolsa = await db.itens_na_bolsa(conn, pid)
    assert sum(bolsa.values()) == 1, bolsa

    await _fechar(conn)
    print("  duas compras simultaneas nao gastam o mesmo ouro: ok")


async def caso_comprar_sozinho_continua_igual():
    """O conserto não podia quebrar a compra normal — nem deixar comprar fiado.

    A condição foi para dentro do `INSERT`, e é fácil escrever um `WHERE` que
    aceita tudo ou recusa tudo. Este caso é o que separa as duas coisas.
    """
    conn, _canal, _cog, users = await preparar(quantos=1)
    pid = await _pid(conn, users[0])
    await db.lancar_ouro(conn, pid, 50, "semente")

    assert await db.comprar(conn, pid, "corda", 30) is True
    assert await db.ouro(conn, pid) == 20
    assert (await db.itens_na_bolsa(conn, pid)).get("corda") == 1

    # Caro demais: recusa, e nao debita nem poe nada na bolsa.
    assert await db.comprar(conn, pid, "espada", 21) is False
    assert await db.ouro(conn, pid) == 20
    assert "espada" not in await db.itens_na_bolsa(conn, pid)
    # Exatamente o saldo: passa, e zera.
    assert await db.comprar(conn, pid, "tocha", 20) is True
    assert await db.ouro(conn, pid) == 0
    # Preco negativo nunca foi compra: seria ganhar ouro comprando.
    assert await db.comprar(conn, pid, "ouro_de_graca", -10) is False
    assert await db.ouro(conn, pid) == 0

    await _fechar(conn)
    print("  a compra de um so: passa, recusa e zera como antes: ok")


async def caso_duas_compras_nao_passam_do_teto_de_estoque():
    """O ouro foi consertado antes do estoque, e eram dois tetos diferentes.

    Com duas poções na bolsa e teto de três, duas compras no mesmo instante
    rendiam **quatro** — e o ouro era cobrado certo pelas duas, o que fazia o
    problema parecer resolvido. A conferência de quantidade ficava no cog,
    lendo a bolsa com um `await` no meio, e as duas passavam por ela.

    O equipamento tem o mesmo buraco com teto 1: duas cópias de uma peça que
    é única por personagem, sendo que a segunda não faria efeito nenhum — só
    queimaria ouro.

    São duas gravações em tabelas diferentes (o saldo e a bolsa), e por isso
    não há um statement que garanta as duas: cada uma confere a sua no próprio
    `WHERE`, e estourar o teto depois de debitar desfaz o débito.
    """
    conn, _canal, _cog, users = await preparar(quantos=1)
    pid = await _pid(conn, users[0])
    await db.lancar_ouro(conn, pid, 100000, "semente")

    pocao = K.FIXAS[0]
    for _ in range(K.TETO_NA_BOLSA - 1):
        assert (await tentar_comprar(conn, pid, SEMANA, pocao.id))[0] is not None
    saldo_antes = await db.ouro(conn, pid)

    respostas = await asyncio.gather(
        tentar_comprar(conn, pid, SEMANA, pocao.id),
        tentar_comprar(conn, pid, SEMANA, pocao.id),
    )
    quantas = (await db.itens_na_bolsa(conn, pid)).get(pocao.id, 0)
    assert quantas == K.TETO_NA_BOLSA, (
        f"a bolsa passou do teto: {quantas} em {K.TETO_NA_BOLSA}"
    )
    # Uma passou, a outra leu o porque — e nao foi cobrada por isso.
    assert sum(1 for peca, _t in respostas if peca is not None) == 1, respostas
    recusada = next(t for peca, t in respostas if peca is None)
    assert "máximo" in recusada, recusada
    assert await db.ouro(conn, pid) == saldo_antes - pocao.custo, (
        "cobrou as duas compras, e so uma entrou na bolsa"
    )

    # O equipamento: unico por personagem, teto de 1.
    peca = next(p for p in mercado.vitrine(pid, SEMANA) if p.slot in itens.SLOTS)
    saldo_antes = await db.ouro(conn, pid)
    respostas = await asyncio.gather(
        tentar_comprar(conn, pid, SEMANA, peca.id),
        tentar_comprar(conn, pid, SEMANA, peca.id),
    )
    copias = (await db.itens_na_bolsa(conn, pid)).get(peca.id, 0)
    assert copias == 1, f"comprou {copias} copias de uma peca unica"
    assert await db.ouro(conn, pid) == saldo_antes - peca.custo, "cobrou as duas"

    await _fechar(conn)
    print("  duas compras simultaneas nao passam do teto de estoque: ok")


async def caso_o_teto_conta_o_que_esta_vestido():
    """Vestir a peça não libera comprá-la de novo.

    Vestido, o item sai de `personagem_itens` — então um teto que olhasse só a
    bolsa veria zero e venderia a segunda cópia, que é exatamente o que a
    regra do item único existe para impedir.
    """
    conn, _canal, _cog, users = await preparar(quantos=1)
    pid = await _pid(conn, users[0])
    await db.lancar_ouro(conn, pid, 100000, "semente")

    peca = next(p for p in mercado.vitrine(pid, SEMANA) if p.slot in itens.SLOTS)
    assert (await tentar_comprar(conn, pid, SEMANA, peca.id))[0] is not None
    assert await db.equipar(conn, pid, peca.id, peca.slot) == (True, None)
    assert not (await db.itens_na_bolsa(conn, pid)).get(peca.id), "ainda na bolsa"

    saldo = await db.ouro(conn, pid)
    comprada, texto = await tentar_comprar(conn, pid, SEMANA, peca.id)
    assert comprada is None, "vendeu a segunda copia de uma peca vestida"
    assert await db.ouro(conn, pid) == saldo, "cobrou sem vender"

    # E direto no `comprar`, sem passar pelo cog: a conferencia de lá tambem
    # olha o que esta vestido, e por isso ela MASCARA a do statement. Quem
    # decide numa corrida e a do statement, e e ela que este trecho cobra.
    assert await db.comprar(conn, pid, peca.id, peca.custo, limite=1) is False, (
        "o teto do statement nao contou a peca vestida"
    )
    assert await db.ouro(conn, pid) == saldo, "debitou e nao desfez"

    await _fechar(conn)
    print("  o teto conta o que esta vestido, nao so a bolsa: ok")


# -------------------------------------------------------- equipamento


def _tudo_que_ele_tem(bolsa, equipado):
    """O inventário inteiro: a bolsa mais o que está vestido, item por item."""
    tudo = dict(bolsa)
    for item_id in equipado.values():
        tudo[item_id] = tudo.get(item_id, 0) + 1
    return tudo


def caso_a_fila_e_por_personagem():
    """Cada personagem tem a sua fila, e sempre a mesma.

    Uma fila por personagem, e não uma global: o que disputa é o slot de UM
    personagem, e uma fila só para todos poria na fila gente que não disputa
    nada — correto, mas serializando o servidor inteiro por uma troca de
    armadura.

    E tem de ser sempre a **mesma** fila. Devolver uma nova a cada chamada é o
    jeito mais fácil de parecer que isto foi consertado sem consertar nada:
    uma fila que ninguém mais usa não enfileira ninguém.

    O caso é de identidade, e não de tempo, de propósito: medir "um esperou
    pelo outro" com relógio dá teste que falha sozinho em máquina carregada.
    """
    primeira = db._fila_do_personagem(999001)
    assert db._fila_do_personagem(999001) is primeira, "a fila do mesmo mudou"
    assert db._fila_do_personagem(999002) is not primeira, (
        "dois personagens dividindo a mesma fila"
    )
    print("  a fila e por personagem, e e sempre a mesma: ok")


async def caso_duas_trocas_no_mesmo_slot_nao_duplicam_nem_perdem():
    """Duas trocas de armadura no mesmo instante: nada duplica, nada se perde.

    As duas liam o MESMO item anterior no slot: as duas o devolviam para a
    bolsa — duas cópias da armadura velha — e o segundo UPSERT sobrescrevia o
    primeiro, de modo que uma das peças novas saía da bolsa e não chegava ao
    slot. Ela desaparecia da ficha.

    Aqui a condição não cabe num `WHERE` como na compra e na lotação: o valor
    lido de uma tabela vira escrita em **outra**, e SQL não diz isso num
    comando só. Por isso este é o único caso do arquivo que se resolve com
    fila, e não com um statement.

    A asserção que importa é de **conservação**: o inventário inteiro — bolsa
    mais vestido — tem de ser o mesmo antes e depois. Vestir é mover de lugar,
    e mover não cria nem destrói. As duas metades do bug quebram essa
    igualdade, uma somando e a outra subtraindo, e nenhuma versão dele a
    satisfaz por acaso.
    """
    conn, _canal, _cog, users = await preparar(quantos=1)
    pid = await _pid(conn, users[0])
    for item_id in ("couro", "malha", "placas"):
        await db.dar_item(conn, pid, item_id)
    assert await db.equipar(conn, pid, "couro", "armadura") == (True, None)

    antes = _tudo_que_ele_tem(
        await db.itens_na_bolsa(conn, pid), await db.equipamento(conn, pid)
    )
    await asyncio.gather(
        db.equipar(conn, pid, "malha", "armadura"),
        db.equipar(conn, pid, "placas", "armadura"),
    )
    equipado = await db.equipamento(conn, pid)
    bolsa = await db.itens_na_bolsa(conn, pid)
    depois = _tudo_que_ele_tem(bolsa, equipado)

    assert depois == antes, f"o inventario mudou: antes={antes} depois={depois}"
    # O slot continua com UMA peca, que e o que o dominio promete.
    assert equipado.get("armadura") in ("malha", "placas"), equipado
    assert bolsa.get("couro") == 1, f"a armadura velha voltou {bolsa.get('couro')}x"

    await _fechar(conn)
    print("  duas trocas no mesmo slot nao duplicam nem perdem item: ok")


async def caso_equipar_sozinho_continua_trocando():
    """A troca normal, que é o caso de todo dia, não podia mudar."""
    conn, _canal, _cog, users = await preparar(quantos=1)
    pid = await _pid(conn, users[0])
    await db.dar_item(conn, pid, "couro")
    await db.dar_item(conn, pid, "malha")

    # Slot vazio: veste, e nao havia nada para devolver.
    assert await db.equipar(conn, pid, "couro", "armadura") == (True, None)
    assert (await db.equipamento(conn, pid)).get("armadura") == "couro"
    assert "couro" not in await db.itens_na_bolsa(conn, pid)

    # A troca devolve a antiga, e diz qual era — e e esse `anterior` que o
    # mercado usa para escrever "X volta para a bolsa".
    assert await db.equipar(conn, pid, "malha", "armadura") == (True, "couro")
    assert (await db.equipamento(conn, pid)).get("armadura") == "malha"
    assert (await db.itens_na_bolsa(conn, pid)).get("couro") == 1

    # O que nao esta na bolsa nao se veste, e nada muda.
    assert await db.equipar(conn, pid, "placas", "armadura") == (False, None)
    assert (await db.equipamento(conn, pid)).get("armadura") == "malha"

    await _fechar(conn)
    print("  a troca de um so: veste, devolve a antiga e recusa o que falta: ok")


# ------------------------------------------------------------ lotacao


async def _run_com_quatro(conn, canal, cog, users):
    """Abre a run e deixa quatro dentro: a próxima entrada é a última vaga."""
    await cog.entrar.callback(
        cog, FakeInteraction(canal, users[0]), cog.incursoes["t"].tier, "t"
    )
    run = await db.run_do_canal(conn, CANAL)
    msg = await canal.fetch_message(run["mensagem_id"])
    for user_id in users[1:4]:
        await cog.recrutar(FakeInteraction(canal, user_id, msg), run["id"], "entrar")
    assert len(await db.participantes(conn, run["id"])) == 4
    return run, msg


async def caso_o_grupo_nao_passa_do_teto():
    """Duas entradas no mesmo instante na última vaga: entra uma.

    Com quatro dentro, as duas passavam pela conferência do cog — que lê com
    `await` — e o grupo começava com seis. E começava mesmo: a run saía de
    `recrutando` com gente a mais.
    """
    conn, canal, cog, users = await preparar()
    run, msg = await _run_com_quatro(conn, canal, cog, users)

    quinto = FakeInteraction(canal, users[4], msg)
    sexto = FakeInteraction(canal, users[5], msg)
    await asyncio.gather(
        cog.efetivar_entrada(quinto, run["id"], await _pid(conn, users[4])),
        cog.efetivar_entrada(sexto, run["id"], await _pid(conn, users[5])),
    )

    dentro = await db.participantes(conn, run["id"])
    assert len(dentro) == config.TAMANHO_GRUPO, (
        f"o grupo passou do teto: {len(dentro)} em {config.TAMANHO_GRUPO}"
    )
    # Um dos dois leu que a vaga tinha acabado — e nao um "voce entrou" falso.
    recusados = [
        inter for inter in (quinto, sexto) if "encheu antes" in (leu(inter) or "")
    ]
    assert len(recusados) == 1, [leu(quinto), leu(sexto)]
    assert recusados[0].user.id not in set(dentro), "disse que nao entrou, e entrou"

    await _fechar(conn)
    print("  duas entradas na ultima vaga: entra uma, e a outra sabe: ok")


async def caso_quem_perde_a_vaga_nao_ganha_o_ouro():
    """Quem não entrou não pode ficar na lista de quem recebe o ouro da run.

    Os dois INSERTs de `adicionar_participante` saíam sempre, lado a lado.
    Enquanto a entrada não podia falhar, isso não cobrava nada; com a
    conferência de lotação dentro do INSERT, passaria a dar direito ao ouro
    de uma incursão a quem ficou de fora dela.
    """
    conn, canal, cog, users = await preparar()
    run, msg = await _run_com_quatro(conn, canal, cog, users)
    await asyncio.gather(
        cog.efetivar_entrada(
            FakeInteraction(canal, users[4], msg), run["id"], await _pid(conn, users[4])
        ),
        cog.efetivar_entrada(
            FakeInteraction(canal, users[5], msg), run["id"], await _pid(conn, users[5])
        ),
    )
    dentro = set(await db.participantes(conn, run["id"]))
    recebem = {p["user_id"] for p in await db.quem_recebe_da_run(conn, run["id"])}
    assert recebem == dentro, (
        f"a lista do ouro nao bate com o grupo: ouro={recebem} grupo={dentro}"
    )

    await _fechar(conn)
    print("  quem perdeu a vaga nao entra na lista do ouro: ok")


async def caso_entrar_duas_vezes_na_mesma_run_nao_duplica():
    """O mesmo jogador clicando duas vezes continua entrando uma só.

    A recusa agora tem dois motivos — cheio e repetido — e eles saem do mesmo
    `rowcount` zero. Este caso é o que garante que o repetido não passou a ser
    anunciado como "a vaga acabou", que seria mentira.
    """
    conn, canal, cog, users = await preparar()
    await cog.entrar.callback(
        cog, FakeInteraction(canal, users[0]), cog.incursoes["t"].tier, "t"
    )
    run = await db.run_do_canal(conn, CANAL)
    msg = await canal.fetch_message(run["mensagem_id"])
    pid = await _pid(conn, users[1])

    primeira = FakeInteraction(canal, users[1], msg)
    await cog.efetivar_entrada(primeira, run["id"], pid)
    assert len(await db.participantes(conn, run["id"])) == 2

    segunda = FakeInteraction(canal, users[1], msg)
    await cog.efetivar_entrada(segunda, run["id"], pid)
    assert len(await db.participantes(conn, run["id"])) == 2, "entrou duas vezes"
    assert "já está no grupo" in (leu(segunda) or ""), leu(segunda)

    # E dois cliques no mesmo instante tambem: um entra, o outro e o repetido.
    terceiro = await _pid(conn, users[2])
    a = FakeInteraction(canal, users[2], msg)
    b = FakeInteraction(canal, users[2], msg)
    await asyncio.gather(
        cog.efetivar_entrada(a, run["id"], terceiro),
        cog.efetivar_entrada(b, run["id"], terceiro),
    )
    assert len(await db.participantes(conn, run["id"])) == 3, (
        "o mesmo jogador entrou duas vezes clicando junto"
    )

    await _fechar(conn)
    print("  clicar duas vezes entra uma vez, e a frase e a certa: ok")


# ------------------------------------------------------- o menu velho


async def caso_menu_velho_nao_deixa_entrar_em_duas_runs():
    """O menu de escolher personagem fica no canal, e o cheque tem de valer de novo.

    `recrutar` confere o bloqueio — *"você já está na run #N"* — ANTES de
    abrir o menu de personagens. Mas o menu fica no canal depois de aberto, e
    o botão dele chama `efetivar_entrada` direto. Quem abrisse o menu aqui,
    entrasse em outra incursão e voltasse para clicar neste botão entrava nas
    duas: o mesmo jogador em duas runs vivas ao mesmo tempo.

    É o mesmo buraco dos outros casos, com outro tamanho. Lá entre conferir e
    gravar cabia um `await`; aqui cabem minutos. **Todo cheque que abre um
    menu precisa valer outra vez no clique** — entre uma coisa e outra não
    existe prazo.
    """
    conn, (canal_a, canal_b), cog, users = await preparar(canais=2)
    for canal, dono in ((canal_a, users[0]), (canal_b, users[1])):
        await cog.entrar.callback(
            cog, FakeInteraction(canal, dono), cog.incursoes["t"].tier, "t"
        )
    run_a = await db.run_do_canal(conn, canal_a.id)
    run_b = await db.run_do_canal(conn, canal_b.id)
    assert run_a["id"] != run_b["id"]

    intruso = users[2]
    pid = await _pid(conn, intruso)
    msg_a = await canal_a.fetch_message(run_a["mensagem_id"])
    await cog.recrutar(FakeInteraction(canal_a, intruso, msg_a), run_a["id"], "entrar")
    assert await db.esta_na_run(conn, run_a["id"], intruso), "nao entrou na run A"

    # O menu da run B estava aberto de antes: o botao vai direto ao efetivar.
    msg_b = await canal_b.fetch_message(run_b["mensagem_id"])
    tarde = FakeInteraction(canal_b, intruso, msg_b)
    await cog.efetivar_entrada(tarde, run_b["id"], pid)

    assert not await db.esta_na_run(conn, run_b["id"], intruso), (
        "o menu velho colocou o mesmo jogador em duas runs vivas"
    )
    assert f"run #{run_a['id']}" in (leu(tarde) or ""), leu(tarde)
    # E a run em que ele ESTAVA nao foi mexida.
    assert await db.esta_na_run(conn, run_a["id"], intruso)

    await _fechar(conn)
    print("  o menu velho nao deixa entrar em duas runs: ok")


async def caso_quem_esta_livre_continua_entrando():
    """O cheque novo não podia barrar quem está liberado — é o caso comum."""
    conn, (canal_a, canal_b), cog, users = await preparar(canais=2)
    await cog.entrar.callback(
        cog, FakeInteraction(canal_a, users[0]), cog.incursoes["t"].tier, "t"
    )
    run = await db.run_do_canal(conn, canal_a.id)
    msg = await canal_a.fetch_message(run["mensagem_id"])

    livre = FakeInteraction(canal_a, users[1], msg)
    await cog.efetivar_entrada(livre, run["id"], await _pid(conn, users[1]))
    assert await db.esta_na_run(conn, run["id"], users[1]), leu(livre)
    assert "entrou" in (leu(livre) or "").lower(), leu(livre)

    await _fechar(conn)
    print("  quem esta liberado entra pelo menu como antes: ok")


async def main():
    try:
        await caso_duas_compras_nao_gastam_o_mesmo_ouro()
        await caso_comprar_sozinho_continua_igual()
        await caso_duas_compras_nao_passam_do_teto_de_estoque()
        await caso_o_teto_conta_o_que_esta_vestido()
        caso_a_fila_e_por_personagem()
        await caso_duas_trocas_no_mesmo_slot_nao_duplicam_nem_perdem()
        await caso_equipar_sozinho_continua_trocando()
        await caso_o_grupo_nao_passa_do_teto()
        await caso_quem_perde_a_vaga_nao_ganha_o_ouro()
        await caso_entrar_duas_vezes_na_mesma_run_nao_duplica()
        await caso_menu_velho_nao_deixa_entrar_em_duas_runs()
        await caso_quem_esta_livre_continua_entrando()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        BANCO.unlink(missing_ok=True)


asyncio.run(main())
print("TESTES DE CORRIDAS PASSARAM")
