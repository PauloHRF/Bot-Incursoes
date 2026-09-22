"""Intervalo entre incursões: a semana vira na segunda-feira, não a cada 7 dias."""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import aiosqlite  # noqa: E402

from src import config, database as db, motor  # noqa: E402
from src.cogs.incursao import Incursoes  # noqa: E402
from fakes import (  # noqa: E402
    CLASSE_PADRAO,
    CANAL,
    GUILD,
    JOGADORES,
    FakeBot,
    FakeCanal,
    montar_conteudo,
    salas_sem_combate,
)

_ABERTAS = []

# Uma semana de referência: 2026-09-21 é uma segunda-feira.
SEGUNDA = datetime(2026, 9, 21, 0, 0, tzinfo=config.FUSO)
SABADO = datetime(2026, 9, 26, 22, 0, tzinfo=config.FUSO)
SEGUNDA_SEGUINTE = datetime(2026, 9, 28, 9, 0, tzinfo=config.FUSO)


async def preparar():
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass
    config.DB_PATH = Path(__file__).resolve().parent / "teste_semana.db"
    config.DB_PATH.unlink(missing_ok=True)
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    canal = FakeCanal(CANAL)
    cog = Incursoes(FakeBot(conn, canal))
    montar_conteudo(cog, salas=salas_sem_combate())
    return conn, canal, cog


def caso_virada_na_segunda():
    """Quem entra no sábado joga de novo na segunda — não sete dias depois."""
    assert motor.segunda_da_semana(SABADO) == SEGUNDA
    assert motor.segunda_da_semana(SEGUNDA) == SEGUNDA, "segunda 00:00 é o próprio início"

    volta = motor.virada_da_vaga(SABADO, 1)
    assert volta == SEGUNDA + timedelta(weeks=1), volta
    assert not motor.entrada_liberada(SABADO, SABADO + timedelta(hours=1), 1)
    assert motor.entrada_liberada(SABADO, SEGUNDA_SEGUINTE, 1)

    # domingo 23h59 ainda é a mesma semana; a virada é na segunda 00:00
    domingo = datetime(2026, 9, 27, 23, 59, tzinfo=config.FUSO)
    assert not motor.entrada_liberada(SABADO, domingo, 1)
    assert motor.entrada_liberada(SABADO, domingo + timedelta(minutes=1), 1)

    # quem entrou na própria segunda espera a semana inteira
    assert not motor.entrada_liberada(SEGUNDA, SABADO, 1)
    assert motor.entrada_liberada(SEGUNDA, SEGUNDA + timedelta(weeks=1), 1)
    print("  a semana vira na segunda-feira: ok")


def caso_intervalo_de_varias_semanas_e_desligado():
    assert not motor.entrada_liberada(SABADO, SEGUNDA_SEGUINTE, 2)
    assert motor.entrada_liberada(SABADO, SEGUNDA + timedelta(weeks=2), 2)
    # 0 libera geral, para o playtest
    assert motor.entrada_liberada(SABADO, SABADO, 0)
    assert motor.entrada_liberada(None, SABADO, 4), "quem nunca jogou entra sempre"
    print("  intervalo de N semanas e o 0 do playtest: ok")


async def caso_bloqueio_conta_a_semana():
    conn, canal, cog = await preparar()
    dono = JOGADORES[0]
    await db.criar_personagem(conn, GUILD, dono, "Vhalor", CLASSE_PADRAO, [], nivel=5)

    assert await cog._motivo_de_bloqueio(GUILD, dono) is None

    # marca a entrada no passado, ainda dentro da semana corrente
    await db.marcar_ultima_incursao(conn, GUILD, [dono])
    bloqueio = await cog._motivo_de_bloqueio(GUILD, dono)
    assert bloqueio and "segunda-feira" in bloqueio, bloqueio
    assert "vaga volta" in bloqueio, bloqueio

    # a data que o bot promete é a segunda seguinte à entrada
    ultima = await db.ultima_incursao(conn, GUILD, dono)
    esperada = motor.virada_da_vaga(ultima, 1)
    assert esperada.weekday() == 0, esperada
    assert esperada.strftime("%d/%m") in bloqueio, (esperada, bloqueio)

    # uma entrada da semana passada não bloqueia mais
    antiga = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S")
    await conn.execute(
        "UPDATE jogadores SET ultima_incursao = ? WHERE guild_id = ? AND user_id = ?",
        (antiga, GUILD, dono),
    )
    await conn.commit()
    assert await cog._motivo_de_bloqueio(GUILD, dono) is None
    print("  o bloqueio conta a semana, e solta na virada: ok")


async def caso_config_em_semanas():
    conn, canal, cog = await preparar()
    dono = JOGADORES[0]
    await db.criar_personagem(conn, GUILD, dono, "Vhalor", CLASSE_PADRAO, [], nivel=5)
    await db.marcar_ultima_incursao(conn, GUILD, [dono])
    assert await cog._motivo_de_bloqueio(GUILD, dono) is not None

    await db.definir_intervalo(conn, GUILD, 0)
    assert await db.intervalo_semanas(conn, GUILD) == 0
    assert await cog._motivo_de_bloqueio(GUILD, dono) is None, "0 libera o playtest"

    await db.definir_intervalo(conn, GUILD, 3)
    assert await db.intervalo_semanas(conn, GUILD) == 3
    bloqueio = await cog._motivo_de_bloqueio(GUILD, dono)
    assert bloqueio and "3 semanas" in bloqueio, bloqueio
    print("  /config intervalo passou a contar semanas: ok")


async def caso_migracao_de_dias_para_semanas():
    """Banco antigo guardava dias; 7 dias viram 1 semana, e o 0 continua 0."""
    caminho = Path(__file__).resolve().parent / "teste_semana_migracao.db"
    caminho.unlink(missing_ok=True)
    bruto = await aiosqlite.connect(caminho)
    await bruto.executescript(
        "CREATE TABLE config_guilda (guild_id INTEGER PRIMARY KEY,"
        " intervalo_dias INTEGER NOT NULL);"
    )
    await bruto.executemany(
        "INSERT INTO config_guilda (guild_id, intervalo_dias) VALUES (?, ?)",
        [(1, 7), (2, 14), (3, 0), (4, 10)],
    )
    await bruto.commit()
    await bruto.close()

    config.DB_PATH = caminho
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)

    assert await db.intervalo_semanas(conn, 1) == 1
    assert await db.intervalo_semanas(conn, 2) == 2
    assert await db.intervalo_semanas(conn, 3) == 0, "o 0 do playtest tem que sobreviver"
    assert await db.intervalo_semanas(conn, 4) == 2, "10 dias arredondam para 2 semanas"
    assert "intervalo_dias" not in await db._colunas(conn, "config_guilda")
    print("  migração de dias para semanas: ok")


async def main():
    try:
        caso_virada_na_segunda()
        caso_intervalo_de_varias_semanas_e_desligado()
        await caso_bloqueio_conta_a_semana()
        await caso_config_em_semanas()
        await caso_migracao_de_dias_para_semanas()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        aqui = Path(__file__).resolve().parent
        for sobra in ("teste_semana.db", "teste_semana_migracao.db"):
            (aqui / sobra).unlink(missing_ok=True)


asyncio.run(main())
print("TESTES DA SEMANA PASSARAM")
