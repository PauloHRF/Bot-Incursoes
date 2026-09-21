"""/help e o aviso publico quando alguem mexe na ficha."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import config, database as db  # noqa: E402
from src.cogs.ajuda import Ajuda, coletar  # noqa: E402
from src.cogs.ficha import Ficha  # noqa: E402
from fakes import (  # noqa: E402
    ATRIBUTOS,
    CANAL,
    GUILD,
    JOGADORES,
    FakeBot,
    FakeCanal,
    FakeInteraction,
)

_ABERTAS = []


class Escolha:
    def __init__(self, value):
        self.value = value
        self.name = value


async def preparar():
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass
    config.DB_PATH = Path(__file__).resolve().parent / "teste_ajuda.db"
    config.DB_PATH.unlink(missing_ok=True)
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    canal = FakeCanal(CANAL)
    return conn, canal, Ficha(FakeBot(conn, canal))


async def _arvore_completa(conn):
    """Sobe o bot de verdade para ter a arvore de comandos que o /help le."""
    from src.main import COGS, IncursoesBot

    bot = IncursoesBot()
    bot.db = conn
    for cog in COGS:
        await bot.load_extension(cog)
    return bot


async def caso_help_lista_tudo():
    conn, canal, _ = await preparar()
    bot = await _arvore_completa(conn)

    grupos = coletar(bot.tree)
    todos = [c for lista in grupos.values() for c in lista]
    nomes = {c[0].split(" ")[0] + " " + c[0].split(" ")[1] if " " in c[0] else c[0] for c in todos}

    # os grupos todos aparecem
    assert set(grupos) >= {"ficha", "incursao", "organizacao", "config", "help"}, set(grupos)
    # nenhum grupo entra como se fosse comando
    assert all(desc for _, desc, _ in todos), "todo comando precisa de descricao"

    achatado = " ".join(c[0] for c in todos)
    for esperado in (
        "/ficha registrar", "/ficha expertise", "/ficha imagem",
        "/incursao entrar", "/incursao atacar",
        "/organizacao placar", "/config intervalo", "/help",
    ):
        assert esperado in achatado, esperado

    # os de admin vem marcados, e os comuns nao
    por_nome = {c[0]: c for c in todos}
    admins = {c[0] for c in todos if c[2]}
    assert any("config intervalo" in a for a in admins), admins
    assert any("organizacao ajustar" in a for a in admins), admins
    assert any("incursao recarregar" in a for a in admins), admins
    assert not any("ficha registrar" in a for a in admins)
    assert not any("organizacao placar" in a for a in admins)

    # comando com muitos campos vira linha curta
    registrar = next(c for c in todos if c[0].startswith("/ficha registrar"))
    assert "campos)" in registrar[0], registrar[0]
    assert len(registrar[0]) < 60, "a assinatura longa precisa sair encurtada"

    for cog in list(bot.extensions):
        await bot.unload_extension(cog)
    await bot.close()
    print(f"  /help lista {len(todos)} comandos, com admin marcado: ok")


async def caso_help_responde_e_filtra():
    conn, canal, _ = await preparar()
    bot = await _arvore_completa(conn)
    ajuda = bot.get_cog("Ajuda")

    inter = FakeInteraction(canal, JOGADORES[0])
    await ajuda.help.callback(ajuda, inter)
    embed = inter._mensagem_resposta.embeds[0]
    assert embed.title == "Comandos do bot"
    campos = {f.name: f.value for f in embed.fields}
    assert any("ficha" in nome for nome in campos)
    # nenhum campo passa do limite do Discord
    for valor in campos.values():
        assert len(valor) <= 1024, len(valor)
    assert "🔒" in " ".join(campos.values())

    # filtro por grupo
    so_ficha = FakeInteraction(canal, JOGADORES[0])
    await ajuda.help.callback(ajuda, so_ficha, comando="ficha")
    campos = {f.name for f in so_ficha._mensagem_resposta.embeds[0].fields}
    assert len(campos) == 1 and "ficha" in next(iter(campos))

    # filtro que nao acha nada
    nada = FakeInteraction(canal, JOGADORES[0])
    await ajuda.help.callback(ajuda, nada, comando="xilofone")
    assert "Nenhum comando parecido" in nada.resposta

    for cog in list(bot.extensions):
        await bot.unload_extension(cog)
    await bot.close()
    print("  /help responde, filtra e respeita o limite do embed: ok")


async def caso_registrar_avisa_o_canal():
    """Registrar posta no canal, para o grupo ver o personagem novo."""
    conn, canal, ficha = await preparar()
    dono = JOGADORES[0]

    inter = FakeInteraction(canal, dono)
    antes = len(canal.mensagens)
    await ficha._anunciar(inter, "teste")
    assert len(canal.mensagens) == antes + 1

    # o fluxo real: cria o personagem e anuncia com a ficha
    pid = await db.criar_personagem(conn, GUILD, dono, "Vhalor", 5, ATRIBUTOS, ["Atletismo"])
    personagem = await db.buscar_personagem(conn, pid)
    from src.cogs.ficha import embed_ficha

    aviso = FakeInteraction(canal, dono)
    await ficha._anunciar(
        aviso,
        f"📜 {aviso.user.mention} registrou **{personagem['nome']}**",
        embed=embed_ficha(personagem, aviso.user),
    )
    ultima = canal.mensagens[-1]
    assert "registrou" in ultima.content and "Vhalor" in ultima.content
    assert ultima.embeds and ultima.embeds[0].title == "Vhalor"
    print("  registrar avisa o canal com a ficha: ok")


async def caso_atualizacoes_sao_publicas():
    """Nivel, atributo, combate, expertise e remover respondem sem ephemeral."""
    conn, canal, ficha = await preparar()
    dono = JOGADORES[0]
    await db.criar_personagem(
        conn, GUILD, dono, "Vhalor", 5, ATRIBUTOS, ["Atletismo"],
        combate={"ca": 15, "bonus_ataque": 5, "dano_arma": "1d8+3", "hp_max": 40},
    )

    def publica(interacao):
        # o dublê registra a mensagem no canal quando nao e ephemeral
        return interacao._mensagem_resposta is not None and interacao._mensagem_resposta.id != -1

    nivel = FakeInteraction(canal, dono)
    await ficha.nivel.callback(ficha, nivel, 9)
    assert publica(nivel), "o aviso de nivel deveria ser publico"
    assert "5" in nivel.resposta and "9" in nivel.resposta

    atributo = FakeInteraction(canal, dono)
    await ficha.atributo.callback(ficha, atributo, Escolha("FOR"), 18)
    assert publica(atributo) and "18" in atributo.resposta

    combate = FakeInteraction(canal, dono)
    await ficha.combate.callback(ficha, combate, 18, 7, "1d12+4", 60)
    assert publica(combate) and "Vhalor" in combate.resposta

    expertise = FakeInteraction(canal, dono)
    await ficha.expertise.callback(ficha, expertise, Escolha("Atletismo"), 3)
    assert publica(expertise) and "Atletismo" in expertise.resposta

    # ver continua privado
    ver = FakeInteraction(canal, dono)
    await ficha.ver.callback(ficha, ver)
    assert not publica(ver), "/ficha ver deveria continuar privado"

    remover = FakeInteraction(canal, dono)
    await ficha.remover.callback(ficha, remover, "Vhalor")
    assert publica(remover) and "apagou" in remover.resposta
    assert await db.personagem_por_nome(conn, GUILD, dono, "Vhalor") is None
    print("  atualizacoes da ficha aparecem no canal: ok")


async def main():
    try:
        await caso_help_lista_tudo()
        await caso_help_responde_e_filtra()
        await caso_registrar_avisa_o_canal()
        await caso_atualizacoes_sao_publicas()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        (Path(__file__).resolve().parent / "teste_ajuda.db").unlink(missing_ok=True)


asyncio.run(main())
print("TESTES DE AJUDA E FEEDBACK PASSARAM")
