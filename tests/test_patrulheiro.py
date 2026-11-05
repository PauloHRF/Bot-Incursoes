"""O Patrulheiro: a marca que vale já no golpe da mesma rodada."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import classes as cl, config, database as db, motor  # noqa: E402
from src.cogs.incursao import Incursoes  # noqa: E402
from fakes import (  # noqa: E402
    CANAL,
    GUILD,
    JOGADORES,
    FakeBot,
    FakeCanal,
    FakeInteraction,
    criar_grupo,
    iniciativa_de_verdade,
    montar_conteudo,
    salas_sem_combate,
)

_ABERTAS = []
BANCO = Path(__file__).resolve().parent / "teste_patrulheiro.db"

# Não machuca e não morre: o caso é sobre o dano que SAI, não sobre o combate.
BONECO = {"nome": "Boneco", "ca": 1, "ataque": -20, "dano": "1d1", "hp": 9000}


def ordem_fixa(*quem):
    def rolar(estado, rng=None):
        ordem = []
        for posicao, (tipo, ident) in enumerate(quem):
            if tipo == "p":
                nome = estado.combatente(ident).nome
                ordem.append(
                    motor.Iniciativa(motor.PERSONAGEM, ident, nome, 20 - posicao, 0)
                )
            else:
                nome = estado.inimigo(ident).nome
                ordem.append(
                    motor.Iniciativa(motor.INIMIGO, ident, nome, 20 - posicao, 0)
                )
        return ordem

    motor.rolar_iniciativas = rolar


async def preparar(nivel=5):
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass
    config.DB_PATH = BANCO
    config.DB_PATH.unlink(missing_ok=True)
    config.TAMANHO_GRUPO = 5
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    await criar_grupo(conn, nivel=nivel, classe="patrulheiro")
    canal = FakeCanal(CANAL)
    cog = Incursoes(FakeBot(conn, canal))
    incursao, _ = montar_conteudo(
        cog, tamanho="Curta", monstro_objetivo=BONECO, salas=salas_sem_combate()
    )
    run_id = await db.criar_run(conn, GUILD, CANAL, incursao.id, JOGADORES[0])
    personagem = await db.personagem_por_nome(
        conn, GUILD, JOGADORES[0], f"Heroi{JOGADORES[0]}"
    )
    await db.adicionar_participante(conn, run_id, JOGADORES[0], personagem["id"])
    await db.inicializar_hp(conn, run_id)
    await db.atualizar_run(
        conn, run_id, status="objetivo", sala_atual=incursao.objetivo.id
    )
    run = await db.buscar_run(conn, run_id)
    await cog._abrir_combate(run, incursao.objetivo)
    return conn, canal, cog, incursao, await db.buscar_run(conn, run_id)


def caso_as_duas_marcas_carregam_os_golpes():
    """As duas marcas do Patrulheiro trazem o turno de ataques com elas.

    `acoes: 1` e não `quantidade: 1`: com Multiattack o turno dele são DOIS
    golpes, e `quantidade` trocaria os dois por um — marcar sairia pior que
    atacar, e a habilidade não seria usada.
    """
    c = cl.CLASSES["patrulheiro"]
    for tier, hid in ((1, "marca_do_cacador"), (5, "cacador_supremo")):
        h = next(x for x in c.habilidades_do_tier(tier) if x.id == hid)
        assert h.acao.get("acoes") == 1, (hid, h.acao)
        assert "quantidade" not in h.acao, (hid, h.acao)
        assert h.acao["alvo"] == "inimigo", h.acao
    print("  as duas marcas carregam o turno de ataques: ok")


async def caso_a_marca_rende_no_golpe_da_mesma_rodada():
    """Marca e bate na mesma rodada, e o dado da marca já entra nos golpes."""
    for nivel, hid, nome, dado in (
        (5, "marca_do_cacador", "Marca do Cacador", "1d6"),
        (9, "cacador_supremo", "Cacador Supremo", "2d8"),
    ):
        ordem_fixa(("p", JOGADORES[0]), ("i", 0))
        conn, canal, cog, incursao, run = await preparar(nivel=nivel)
        msg = await canal.fetch_message(run["mensagem_id"])

        inter = FakeInteraction(canal, JOGADORES[0], msg)
        await cog.usar_habilidade(inter, run["id"], "OBJ", hid)
        texto = str(inter.resposta)

        # A marca foi anunciada com alvo e prazo...
        assert nome in texto and "vale por" in texto, texto
        # ...e os golpes saíram na MESMA resposta, com o dado da marca.
        assert texto.count("acertou") + texto.count("CRITICO") >= 1, texto
        # A prova é a marca aparecer como PARCELA do dano, e não a string
        # exata do dado: no crítico o log dobra os dados (`2d8` sai `4d8`),
        # e fixar o texto deixava o caso vermelho uma vez em vinte, por sorte.
        assert f"⤷ {nome} " in texto, texto
        if "CRITICO" not in texto:
            assert f"{nome} {dado}" in texto, texto
        # O nome não sai duas vezes: quem chamou já escreveu a cabeça.
        assert texto.count(f"**{nome}**") == 1, texto

        # Com Multiattack são DOIS golpes, e não um.
        atacante = (await cog._estado_combate(
            await db.buscar_run(conn, run["id"]), incursao.objetivo
        )).combatente(JOGADORES[0])
        if atacante.ataques > 1:
            assert texto.count("🎲") >= atacante.ataques, (atacante.ataques, texto)

        await conn.close()
        config.DB_PATH.unlink(missing_ok=True)
    print("  a marca rende no golpe da mesma rodada: ok")


async def caso_a_marca_segue_valendo_nas_rodadas_seguintes():
    """O prazo não encurtou: a marca continua rendendo no turno seguinte."""
    ordem_fixa(("p", JOGADORES[0]), ("i", 0))
    conn, canal, cog, incursao, run = await preparar(nivel=5)
    msg = await canal.fetch_message(run["mensagem_id"])

    inter = FakeInteraction(canal, JOGADORES[0], msg)
    await cog.usar_habilidade(inter, run["id"], "OBJ", "marca_do_cacador")

    # Rodada seguinte, ataque comum: o dado da marca ainda aparece.
    inter = FakeInteraction(canal, JOGADORES[0], msg)
    await cog.atacar(inter, run["id"], "OBJ")
    depois = str(inter.resposta)
    assert "Marca do Cacador 1d6" in depois, depois

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print("  a marca segue valendo nas rodadas seguintes: ok")


async def main():
    try:
        caso_as_duas_marcas_carregam_os_golpes()
        await caso_a_marca_rende_no_golpe_da_mesma_rodada()
        await caso_a_marca_segue_valendo_nas_rodadas_seguintes()
    finally:
        iniciativa_de_verdade(False)
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        BANCO.unlink(missing_ok=True)


asyncio.run(main())
print("TESTES DO PATRULHEIRO PASSARAM")
