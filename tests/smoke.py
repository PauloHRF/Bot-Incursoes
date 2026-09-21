"""Teste de fumaca: regras + persistencia + carregamento dos cogs, sem conectar no Discord."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config, database as db
from src.rules import bonus_proficiencia, melhor_pericia, mod_pericia, modificador, tier

# --- regras ---
assert [bonus_proficiencia(n) for n in (1, 4, 5, 9, 13, 17, 20)] == [2, 2, 3, 4, 5, 6, 6]
assert [modificador(v) for v in (8, 10, 14, 15, 20)] == [-1, 0, 2, 2, 5]
assert [tier(n) for n in (1, 4, 5, 10, 11, 16, 17, 20)] == [1, 1, 2, 2, 3, 3, 4, 4]

atributos = {"FOR": 10, "DES": 16, "CON": 14, "INT": 12, "SAB": 13, "CAR": 8}
# Furtividade (DES +3) treinada no nivel 5 -> +3 +3 = +6
assert mod_pericia("Furtividade", atributos, 5, ["Furtividade"]) == 6
# Nao treinada -> so o mod do atributo
assert mod_pericia("Acrobacia", atributos, 5, ["Furtividade"]) == 3
assert melhor_pericia(["Atletismo", "Furtividade"], atributos, 5, ["Furtividade"]) == ("Furtividade", 6)

# --- persistencia (banco temporario) ---
config.DB_PATH = Path(__file__).resolve().parent / "teste.db"
config.DB_PATH.unlink(missing_ok=True)


async def main():
    conn = await db.conectar()
    await db.criar_schema(conn)

    await db.salvar_ficha(conn, 1, 42, "Vhalor", 5, atributos, ["Furtividade", "Percepcao"])
    f = await db.buscar_ficha(conn, 1, 42)
    assert f["nome"] == "Vhalor" and f["nivel"] == 5
    assert f["pericias"] == ["Furtividade", "Percepcao"]
    assert f["atributos"] == atributos
    assert f["ca"] == 10 and f["hp_max"] == 10  # defaults de combate

    # subir de nivel nao apaga nada e muda a proficiencia
    assert await db.atualizar_campo(conn, 1, 42, "nivel", 9)
    assert await db.atualizar_campo(conn, 1, 42, "ca", 17)
    f = await db.buscar_ficha(conn, 1, 42)
    assert f["nivel"] == 9 and f["ca"] == 17 and f["pericias"] == ["Furtividade", "Percepcao"]
    assert mod_pericia("Furtividade", f["atributos"], f["nivel"], f["pericias"]) == 7

    # re-registrar preserva os campos de combate
    await db.salvar_ficha(conn, 1, 42, "Vhalor, o Torto", 9, atributos, ["Furtividade"])
    f = await db.buscar_ficha(conn, 1, 42)
    assert f["ca"] == 17 and f["nome"] == "Vhalor, o Torto"

    assert await db.buscar_ficha(conn, 1, 99) is None
    assert not await db.atualizar_campo(conn, 1, 99, "nivel", 3)

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)

    # --- cogs carregam de verdade? ---
    from src.main import IncursoesBot

    bot = IncursoesBot()
    for cog in ("src.cogs.ficha",):
        await bot.load_extension(cog)
    nomes = sorted(c.qualified_name for c in bot.tree.walk_commands())
    await bot.close()
    print("comandos registrados:", nomes)


asyncio.run(main())
print("TODOS OS TESTES PASSARAM")
