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
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import config, database as db  # noqa: E402
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
_ABERTAS = []


async def preparar(quantos=6):
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
    canal = FakeCanal(CANAL)
    cog = Incursoes(FakeBot(conn, canal))
    montar_conteudo(cog, tier=4)
    return conn, canal, cog, users


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


async def main():
    try:
        await caso_duas_compras_nao_gastam_o_mesmo_ouro()
        await caso_comprar_sozinho_continua_igual()
        await caso_o_grupo_nao_passa_do_teto()
        await caso_quem_perde_a_vaga_nao_ganha_o_ouro()
        await caso_entrar_duas_vezes_na_mesma_run_nao_duplica()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        BANCO.unlink(missing_ok=True)


asyncio.run(main())
print("TESTES DE CORRIDAS PASSARAM")
