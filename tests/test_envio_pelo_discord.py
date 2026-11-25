"""O `/incursao enviar` e o `/config autores`, de ponta a ponta com o banco.

O que estes casos protegem, e que não é óbvio:

1. **Publicar não passa por ninguém, mas não é para qualquer um.** Só quem
   administra o servidor, ou tem o cargo que o admin escolheu.
2. **Recusado, nada entra.** E a resposta traz TODOS os problemas, para o
   autor corrigir numa ida só.
3. **O que foi enviado sobrevive ao restart.** O conteúdo mora no banco de
   dados, e um bot novo o lê e junta ao repositório.
4. **A run em andamento não vê a dungeon mudar debaixo dela.**
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import config, database as db, pacotes  # noqa: E402
from src.cogs.incursao import Incursoes  # noqa: E402
from fakes import CANAL, GUILD, FakeBot, FakeCanal, FakeInteraction, leu  # noqa: E402

BANCO = Path(__file__).resolve().parent / "teste_envio.db"
ORG = "Vórtice Oculto"
CRIATURA = {"nome": "Coisa", "ca": 13, "ataque": 4, "dano": "1d6", "hp": 12}
AUTORA, OUTRO, CARGO = 501, 502, 777
_ABERTAS = []


def sala(sala_id, **extra):
    base = {"id": sala_id, "nome": f"Sala {sala_id}", "tipo": "Evento",
            "descricao": "Uma porta.", "dificuldade": "Média", "cd": 13,
            "alvo_progresso": 3, "pericias": ["Investigação"], "temas": ["arcano"]}
    base.update(extra)
    return base


def dungeon(dungeon_id="pelo_discord", **extra):
    base = {"id": dungeon_id, "nome": "Pelo Discord", "organizacao": ORG,
            "tamanho": "Curta", "tier": 2, "lore_inicial": "Chegou pelo Discord.",
            "recompensa_mes": 10,
            "objetivo": {"id": "OBJ", "nome": "Fim", "tipo": "Combate",
                         "descricao": "O chefe.", "monstros": [dict(CRIATURA)]}}
    base.update(extra)
    return base


class Anexo:
    """O `discord.Attachment` no que o comando usa: tamanho e conteúdo."""

    def __init__(self, dados=None, bruto: bytes | None = None):
        self._bytes = bruto if bruto is not None else json.dumps(dados).encode()
        self.size = len(self._bytes)
        self.filename = "dungeon.json"

    async def read(self) -> bytes:
        return self._bytes


async def preparar():
    while _ABERTAS:
        await _ABERTAS.pop().close()
    config.DB_PATH = BANCO
    BANCO.unlink(missing_ok=True)
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    canal = FakeCanal(CANAL)
    cog = Incursoes(FakeBot(conn, canal))
    cog.recarregar_incursoes()  # o repositório de verdade, de data/
    return conn, canal, cog


async def enviar(cog, canal, user_id, pacote=None, *, bruto=None, admin=True, cargos=()):
    inter = FakeInteraction(canal, user_id)
    inter.user.guild_permissions = SimpleNamespace(manage_guild=admin)
    inter.user.roles = [SimpleNamespace(id=c) for c in cargos]
    await cog.enviar.callback(cog, inter, Anexo(pacote, bruto))
    return leu(inter)


async def caso_sem_cargo_nao_publica():
    conn, canal, cog = await preparar()
    lido = await enviar(cog, canal, AUTORA, pacotes.novo(ORG, dungeon()), admin=False)
    assert "cargo de autores" in lido, lido
    assert await db.conteudo_enviado(conn) == []
    assert "pelo_discord" not in cog.incursoes
    print("  sem o cargo, ninguém publica: ok")


async def caso_o_cargo_escolhido_publica():
    conn, canal, cog = await preparar()
    admin = FakeInteraction(canal, 1)
    await cog.config_autores.callback(
        cog, admin, SimpleNamespace(id=CARGO, mention=f"<@&{CARGO}>"))
    assert await db.cargo_de_autor(conn, GUILD) == CARGO
    assert f"<@&{CARGO}>" in leu(admin)

    lido = await enviar(cog, canal, AUTORA, pacotes.novo(ORG, dungeon(), [sala("VO-T1")]),
                        admin=False, cargos=[CARGO])
    assert lido.startswith("**Publicado.**"), lido
    assert "a dungeon 'pelo_discord'" in lido and "a sala 'VO-T1'" in lido, lido
    linhas = await db.conteudo_enviado(conn)
    assert {(l["tipo"], l["conteudo_id"], l["autor_id"], l["guild_id"]) for l in linhas} == {
        ("incursao", "pelo_discord", AUTORA, GUILD), ("sala", "VO-T1", AUTORA, GUILD)}
    # Entra no catálogo na hora, sem /incursao recarregar.
    assert cog.incursoes["pelo_discord"].nome == "Pelo Discord"
    assert cog.bancos[ORG].sala("VO-T1") is not None
    # E tirar o cargo volta a deixar só quem administra.
    await cog.config_autores.callback(cog, FakeInteraction(canal, 1), None)
    assert await db.cargo_de_autor(conn, GUILD) is None
    lido = await enviar(cog, canal, AUTORA, pacotes.novo(ORG, None, [sala("VO-T2")]),
                        admin=False, cargos=[CARGO])
    assert "cargo de autores" in lido, lido
    print("  o cargo escolhido publica, e entra no catálogo na hora: ok")


async def caso_recusado_diz_tudo_e_nada_entra():
    conn, canal, cog = await preparar()
    torta = dungeon(tier=None, lore_inicial="")
    lido = await enviar(cog, canal, AUTORA, pacotes.novo(ORG, torta, [sala("VO-T1")]))
    assert lido.startswith("**Não publiquei.**"), lido
    assert "tier" in lido and "lore" in lido, lido
    assert await db.conteudo_enviado(conn) == [], "a sala entrou com a dungeon recusada"
    print("  recusado, diz todos os problemas e nada entra: ok")


async def caso_so_o_dono_atualiza():
    conn, canal, cog = await preparar()
    await enviar(cog, canal, AUTORA, pacotes.novo(ORG, dungeon()))
    lido = await enviar(cog, canal, OUTRO, pacotes.novo(ORG, dungeon(nome="Tomada")))
    assert "outra pessoa" in lido, lido
    assert cog.incursoes["pelo_discord"].nome == "Pelo Discord"
    lido = await enviar(cog, canal, AUTORA, pacotes.novo(ORG, dungeon(nome="Segunda versão")))
    assert "Atualizado" in lido, lido
    assert cog.incursoes["pelo_discord"].nome == "Segunda versão"
    [linha] = await db.conteudo_enviado(conn)
    assert linha["autor_id"] == AUTORA
    lido = await enviar(cog, canal, AUTORA, pacotes.novo(ORG, dungeon(nome="Segunda versão")))
    assert lido.startswith("Nada mudou"), lido
    print("  só o dono atualiza, e reenviar igual não muda nada: ok")


async def caso_a_run_em_andamento_nao_ve_a_mudanca():
    conn, canal, cog = await preparar()
    await enviar(cog, canal, AUTORA, pacotes.novo(ORG, dungeon(), [sala("VO-T1")]))
    run_id = await db.criar_run(conn, GUILD, CANAL, "pelo_discord", AUTORA)
    await db.gravar_opcoes(conn, run_id, 1, ["VO-T1", "VO01"])
    lido = await enviar(cog, canal, AUTORA, pacotes.novo(ORG, dungeon(nome="Mudou")))
    assert "run em andamento" in lido, lido
    assert cog.incursoes["pelo_discord"].nome == "Pelo Discord"
    lido = await enviar(cog, canal, AUTORA, pacotes.novo(ORG, None, [sala("VO-T1", nome="Mudou")]))
    assert "run em andamento" in lido, lido
    # O que é só novo passa com a run andando.
    lido = await enviar(cog, canal, AUTORA, pacotes.novo(ORG, None, [sala("VO-T2")]))
    assert lido.startswith("**Publicado.**"), lido
    # Acabou a run, a mudança passa.
    await db.atualizar_run(conn, run_id, status="concluida")
    lido = await enviar(cog, canal, AUTORA, pacotes.novo(ORG, dungeon(nome="Mudou")))
    assert "Atualizado" in lido, lido
    print("  a run em andamento não vê a dungeon mudar: ok")


async def caso_o_enviado_sobrevive_ao_restart():
    conn, canal, cog = await preparar()
    await enviar(cog, canal, AUTORA, pacotes.novo(ORG, dungeon(), [sala("VO-T1")]))
    # Pela subida de verdade (`cog_load`), e não chamando as partes dela: se a
    # leitura do banco saísse da subida, tudo que os autores publicaram
    # sumiria a cada restart — e só este caso olha a subida.
    bot = FakeBot(conn, canal)

    async def sem_login():
        raise RuntimeError("o bot do teste nunca conecta")

    bot.wait_until_ready = sem_login
    novo = Incursoes(bot)
    await novo.cog_load()
    try:
        assert novo.incursoes["pelo_discord"].nome == "Pelo Discord"
        assert novo.bancos[ORG].sala("VO-T1") is not None
        # E o repositório guardado à parte não leva o que veio pelo Discord.
        assert "pelo_discord" not in novo.repositorio_incursoes
        assert novo.repositorio_bancos[ORG].sala("VO-T1") is None
    finally:
        await novo.cog_unload()
    print("  o enviado sobrevive ao restart: ok")


async def caso_anexo_torto_tem_resposta():
    conn, canal, cog = await preparar()
    assert "Não consegui ler" in await enviar(cog, canal, AUTORA, bruto=b"isto nao e json")
    grande = Anexo(bruto=b" " * 600_000)
    inter = FakeInteraction(canal, AUTORA)
    inter.user.guild_permissions = SimpleNamespace(manage_guild=True)
    await cog.enviar.callback(cog, inter, grande)
    assert "KB" in leu(inter), leu(inter)
    assert "Estúdio" in await enviar(cog, canal, AUTORA, dungeon())
    print("  anexo torto tem resposta, e não exceção: ok")


async def principal():
    # No `finally`, e não depois do último caso: a conexão aberta segura o
    # processo, e um caso que falha deixava a suíte PARADA em vez de vermelha
    # — a sabotagem da permissão ficou dez minutos esperando.
    try:
        for caso in (
            caso_sem_cargo_nao_publica,
            caso_o_cargo_escolhido_publica,
            caso_recusado_diz_tudo_e_nada_entra,
            caso_so_o_dono_atualiza,
            caso_a_run_em_andamento_nao_ve_a_mudanca,
            caso_o_enviado_sobrevive_ao_restart,
            caso_anexo_torto_tem_resposta,
        ):
            await caso()
    finally:
        while _ABERTAS:
            try:
                await _ABERTAS.pop().close()
            except Exception:
                pass
        BANCO.unlink(missing_ok=True)
    print("TESTES DO ENVIO PELO DISCORD PASSARAM")


asyncio.run(principal())
