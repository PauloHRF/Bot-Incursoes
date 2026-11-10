"""Abrir um banco que já existia: a migração do schema.

Este arquivo nasceu de um bot derrubado em produção. A coluna `vez_desde` foi
declarada `NOT NULL DEFAULT (datetime('now'))`, que é válido num `CREATE
TABLE` e **inválido** num `ALTER TABLE ... ADD COLUMN` — o SQLite recusa
default não-constante com *"Cannot add a column with non-constant default"*. O
`criar_schema` roda antes de o bot conectar, então ele nem subiu.

Nenhum dos testes viu isso, e a razão é estrutural: **todos nascem de um banco
vazio**. Num arquivo novo o `CREATE TABLE` carrega o default sem reclamar, e o
ramo da migração — que só roda quando a coluna falta — nunca era executado. A
suíte inteira provava o schema novo, e ninguém provava a passagem de um para o
outro.

Então aqui o banco é construído na forma ANTIGA, com dados dentro, e o teste é
que `criar_schema` abra esse arquivo. Duas coisas são cobradas:

- a migração não estoura, e o que havia no banco continua lá;
- o banco migrado tem a MESMA forma de um banco novo. Essa segunda é a que
  pega a armadilha de verdade: um `NOT NULL` que só existe no arquivo novo
  passa despercebido para sempre, porque os testes só olham o arquivo novo.
"""
from __future__ import annotations

import asyncio
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import config, database as db  # noqa: E402

NOVO = Path(__file__).resolve().parent / "teste_migracao_novo.db"
ANTIGO = Path(__file__).resolve().parent / "teste_migracao_antigo.db"

# As tabelas como eram ANTES de o grupo poder agir no lugar de quem nao age:
# `run_combate` sem `vez_desde`, `run_turnos` sem `substituto`.
FORMA_ANTIGA = {
    "run_combate": """
        CREATE TABLE run_combate (
            run_id  INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
            passo   INTEGER NOT NULL,
            sala_id TEXT    NOT NULL,
            rodada  INTEGER NOT NULL DEFAULT 1,
            vez     INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (run_id, passo)
        )""",
    "run_turnos": """
        CREATE TABLE run_turnos (
            run_id    INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
            passo     INTEGER NOT NULL,
            rodada    INTEGER NOT NULL,
            user_id   INTEGER NOT NULL,
            acao      TEXT    NOT NULL DEFAULT 'ataque',
            alvos     TEXT    NOT NULL DEFAULT '[]',
            resolvida INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (run_id, passo, rodada, user_id)
        )""",
}


# No Windows o arquivo so pode ser apagado quando ninguem o mantem aberto, e
# uma conexao viva no `finally` virava PermissionError — que, com o thread do
# aiosqlite de pe, pendura o processo em vez de falhar.
_ABERTAS = []


async def _abrir(caminho: Path):
    config.DB_PATH = caminho
    conn = await db.conectar()
    _ABERTAS.append(conn)
    return conn


async def _fechar_tudo() -> None:
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass


async def _criar_do_zero(caminho: Path):
    await _fechar_tudo()
    caminho.unlink(missing_ok=True)
    conn = await _abrir(caminho)
    await db.criar_schema(conn)
    return conn


def _colunas_cruas(caminho: Path, tabela: str) -> list[tuple]:
    """(nome, tipo, notnull, default) de cada coluna, lido do arquivo."""
    cru = sqlite3.connect(caminho)
    try:
        return [
            (linha[1], linha[2], linha[3], linha[4])
            for linha in cru.execute(f"PRAGMA table_info({tabela})")
        ]
    finally:
        cru.close()


def _voltar_no_tempo(caminho: Path) -> None:
    """Recria as tabelas na forma antiga, preservando o resto do banco."""
    cru = sqlite3.connect(caminho)
    try:
        for tabela, criacao in FORMA_ANTIGA.items():
            cru.execute(f"ALTER TABLE {tabela} RENAME TO {tabela}_fora")
            cru.execute(criacao)
            cru.execute(f"DROP TABLE {tabela}_fora")
        cru.commit()
    finally:
        cru.close()


def _povoar_como_a_versao_antiga(caminho: Path) -> None:
    """Uma run com combate aberto e um turno guardado, como o bot antigo deixaria."""
    cru = sqlite3.connect(caminho)
    try:
        cru.execute(
            "INSERT INTO runs (guild_id, canal_id, incursao_id, criador_id, status)"
            " VALUES (1, 99, 'cripta', 101, 'objetivo')"
        )
        cru.execute(
            "INSERT INTO run_combate (run_id, passo, sala_id, rodada, vez)"
            " VALUES (1, 4, 'OBJ', 2, 1)"
        )
        cru.execute(
            "INSERT INTO run_turnos (run_id, passo, rodada, user_id, acao, resolvida)"
            " VALUES (1, 4, 2, 101, 'ataque', 0)"
        )
        cru.commit()
    finally:
        cru.close()


async def caso_um_banco_antigo_abre_e_mantem_o_que_tinha():
    """O bot sobe sobre um banco que já existia, e o combate aberto sobrevive.

    O `criar_schema` roda antes de conectar ao Discord: um erro aqui não
    degrada nada, derruba tudo.
    """
    conn = await _criar_do_zero(ANTIGO)
    await _fechar_tudo()
    _voltar_no_tempo(ANTIGO)
    _povoar_como_a_versao_antiga(ANTIGO)
    assert "vez_desde" not in {c[0] for c in _colunas_cruas(ANTIGO, "run_combate")}
    assert "substituto" not in {c[0] for c in _colunas_cruas(ANTIGO, "run_turnos")}

    conn = await _abrir(ANTIGO)
    # A migracao em si. Sem o conserto, aqui vem
    # "Cannot add a column with non-constant default".
    await db.criar_schema(conn)

    # O que estava no banco continua lá, e o combate segue na rodada 2.
    combate = await db.estado_combate(conn, 1, 4)
    assert combate and combate["rodada"] == 2 and combate["vez"] == 1, combate
    turno = await db.turno_de(conn, 1, 4, 2, 101)
    assert turno and not turno["resolvida"], turno
    # A acao guardada continua sendo DELE: `substituto` nasce NULL, e e isso
    # que "foi o proprio jogador" quer dizer.
    assert turno["substituto"] is None, turno
    assert await db.turno_foi_substituido(conn, 1, 4, 101) is False

    # E o relogio da vez foi preenchido, em vez de ficar nulo: a vez em curso
    # passa a contar os 15 minutos a partir da migracao, que e o unico
    # instante que um banco antigo sabe.
    assert await db.vez_aberta_desde(conn, 1, 4) is not None, (
        "a coluna entrou vazia, e o relogio da substituicao nao teria de onde contar"
    )

    await _fechar_tudo()
    print("  um banco antigo abre, e o combate aberto sobrevive: ok")


async def caso_o_banco_migrado_tem_a_forma_do_banco_novo():
    """Migrado e novo têm de ser indistinguíveis, coluna por coluna.

    É esta a asserção que pega a armadilha. Um `NOT NULL` ou um default que só
    existe no arquivo criado de zero não aparece em teste nenhum — os testes
    todos criam de zero —, e a diferença só se manifesta no banco de quem já
    jogava. Comparar as duas formas transforma isso em falha local.
    """
    conn = await _criar_do_zero(NOVO)
    await _fechar_tudo()

    conn = await _criar_do_zero(ANTIGO)
    await _fechar_tudo()
    _voltar_no_tempo(ANTIGO)
    conn = await _abrir(ANTIGO)
    await db.criar_schema(conn)
    await _fechar_tudo()

    for tabela in FORMA_ANTIGA:
        assert _colunas_cruas(NOVO, tabela) == _colunas_cruas(ANTIGO, tabela), (
            f"{tabela}: o banco migrado ficou diferente do banco novo\n"
            f"  novo:    {_colunas_cruas(NOVO, tabela)}\n"
            f"  migrado: {_colunas_cruas(ANTIGO, tabela)}"
        )
    print("  o banco migrado tem a mesma forma do banco novo: ok")


async def caso_abrir_duas_vezes_nao_muda_nada():
    """Subir o bot de novo não migra de novo: a migração é idempotente."""
    conn = await _criar_do_zero(ANTIGO)
    await _fechar_tudo()
    _voltar_no_tempo(ANTIGO)
    _povoar_como_a_versao_antiga(ANTIGO)

    conn = await _abrir(ANTIGO)
    await db.criar_schema(conn)
    primeira = await db.vez_aberta_desde(conn, 1, 4)
    forma = _colunas_cruas(ANTIGO, "run_combate")
    # Segunda subida, no mesmo arquivo.
    await db.criar_schema(conn)
    assert _colunas_cruas(ANTIGO, "run_combate") == forma
    assert await db.vez_aberta_desde(conn, 1, 4) == primeira, (
        "a segunda subida reiniciou o relogio da vez de quem estava jogando"
    )
    await _fechar_tudo()
    print("  abrir o mesmo banco duas vezes nao migra de novo: ok")


async def main():
    try:
        await caso_um_banco_antigo_abre_e_mantem_o_que_tinha()
        await caso_o_banco_migrado_tem_a_forma_do_banco_novo()
        await caso_abrir_duas_vezes_nao_muda_nada()
    finally:
        await _fechar_tudo()
        for arquivo in (NOVO, ANTIGO):
            try:
                arquivo.unlink(missing_ok=True)
            except OSError:
                pass


asyncio.run(main())
print("TESTES DE MIGRACAO PASSARAM")
