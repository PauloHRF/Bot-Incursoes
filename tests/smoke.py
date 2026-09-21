"""Teste de fumaca: regras + persistencia + carregamento dos cogs, sem conectar no Discord."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config, database as db
from src.rules import (
    bonus_proficiencia,
    melhor_pericia,
    mod_pericia,
    modificador,
    normalizar_pericia,
    tier,
)

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

# nomes de pericia aceitam grafia sem acento e caixa diferente
assert normalizar_pericia("investigacao") == "Investigação"
assert normalizar_pericia("PERCEPÇÃO") == "Percepção"
assert normalizar_pericia("  adestrar   animais ") == "Adestrar Animais"
assert normalizar_pericia("Alquimia") is None

# --- persistencia (banco temporario) ---
config.DB_PATH = Path(__file__).resolve().parent / "teste.db"
config.DB_PATH.unlink(missing_ok=True)


async def main():
    conn = await db.conectar()
    await db.criar_schema(conn)

    # um personagem, com atributos, pericias e combate de uma vez so
    vhalor_id = await db.criar_personagem(
        conn, 1, 42, "Vhalor", 5, atributos, ["Furtividade", "Percepção"],
        combate={"ca": 17, "bonus_ataque": 7, "dano_arma": "1d8+4", "hp_max": 54},
    )
    assert vhalor_id
    f = await db.buscar_personagem(conn, vhalor_id)
    assert f["nome"] == "Vhalor" and f["nivel"] == 5
    assert f["pericias"] == ["Furtividade", "Percepção"]
    assert f["atributos"] == atributos
    assert (f["ca"], f["bonus_ataque"], f["dano_arma"], f["hp_max"]) == (17, 7, "1d8+4", 54)

    # sem campos de combate, valem os defaults
    magro_id = await db.criar_personagem(conn, 1, 42, "Sem Arma", 1, atributos, [])
    magro = await db.buscar_personagem(conn, magro_id)
    assert magro["ca"] == 10 and magro["hp_max"] == 10 and magro["dano_arma"] == "1d6"

    # subir de nivel nao apaga nada e muda a proficiencia
    assert await db.atualizar_personagem(conn, vhalor_id, "nivel", 9)
    f = await db.buscar_personagem(conn, vhalor_id)
    assert f["nivel"] == 9 and f["ca"] == 17 and f["pericias"] == ["Furtividade", "Percepção"]
    assert mod_pericia("Furtividade", f["atributos"], f["nivel"], f["pericias"]) == 7

    # o mesmo jogador tem varios personagens, buscaveis por nome
    assert len(await db.listar_personagens(conn, 1, 42)) == 2
    assert (await db.personagem_por_nome(conn, 1, 42, "vhalor"))["id"] == vhalor_id
    assert await db.personagem_por_nome(conn, 1, 42, "Ninguem") is None

    # dois personagens do mesmo jogador nao podem ter o mesmo nome
    assert await db.criar_personagem(conn, 1, 42, "Vhalor", 3, atributos, []) is None
    # mas jogadores diferentes podem repetir nome
    assert await db.criar_personagem(conn, 1, 43, "Vhalor", 3, atributos, []) is not None

    # apagar um nao mexe nos outros
    assert await db.remover_personagem(conn, magro_id)
    assert [p["nome"] for p in await db.listar_personagens(conn, 1, 42)] == ["Vhalor"]

    assert await db.buscar_personagem(conn, 99999) is None
    assert not await db.atualizar_personagem(conn, 99999, "nivel", 3)
    # coluna fora da lista branca nao passa
    try:
        await db.atualizar_personagem(conn, vhalor_id, "guild_id", 7)
    except ValueError:
        pass
    else:
        raise AssertionError("deveria recusar coluna desconhecida")

    # --- incursoes: JSON de exemplo e validacao ---
    from copy import deepcopy
    import json
    from src.incursoes import ErroDeValidacao, carregar, de_dict

    caminho = Path(__file__).resolve().parents[1] / "data" / "incursoes" / "vortice_cripta.json"
    inc = carregar(caminho)
    assert len(inc.linhas) == 3 and all(len(l) == 3 for l in inc.linhas)
    assert inc.objetivo.tipo == "Combate" and inc.objetivo.monstro.hp > 0
    assert inc.organizacao == "Vórtice Oculto"
    assert inc.sala("L2C").tipo == "Tesouro" and inc.sala("L2C").cd == 15
    assert inc.sala("L2C").tem_teste and not inc.sala("L1C").tem_teste
    assert inc.sala("L1C").e_combate and inc.sala("L1C").monstro.ca == 14
    assert [s.id for s in inc.opcoes(2)] == ["L2A", "L2B", "L2C"]
    assert inc.sala("nao_existe") is None
    # o JSON sobrevive a uma ida e volta pelo validador
    assert de_dict(inc.para_dict()).para_dict() == inc.para_dict()

    bom = json.loads(caminho.read_text(encoding="utf-8"))

    def recusa(mutacao, trecho):
        dados = deepcopy(bom)
        mutacao(dados)
        try:
            de_dict(dados)
        except ErroDeValidacao as exc:
            assert any(trecho in p for p in exc.problemas), (trecho, exc.problemas)
        else:
            raise AssertionError(f"deveria ter recusado: {trecho}")

    def vira_evento(d):
        d["objetivo"]["tipo"] = "Evento"
        d["objetivo"]["monstro"] = None

    recusa(vira_evento, "desafio final é sempre Combate")
    recusa(lambda d: d["linhas"][0].pop(), "exatamente 3 salas")
    recusa(lambda d: d["linhas"].pop(), "exatamente 3 linhas")
    recusa(lambda d: d["linhas"][0][0]["pericias"].append("Alquimia"), "não existe")
    recusa(lambda d: d["objetivo"].update(monstro=None), "precisa dos dados do monstro")
    recusa(lambda d: d["objetivo"]["monstro"].update(dano="muito"), "fora do formato")
    recusa(lambda d: d["linhas"][0][0].update(alvo_progresso=0), "alvo_progresso maior que zero")
    recusa(lambda d: d.update(organizacao="Clube do Livro"), "organizacao")
    recusa(lambda d: d.update(id="Vórtice Cripta"), "letras minúsculas")
    recusa(lambda d: d["linhas"][1][0].update(id="L1A"), "aparece 2 vezes")
    recusa(lambda d: d["linhas"][0][0].update(tipo="Puzzle"), "tipo 'Puzzle' inválido")
    recusa(lambda d: d["linhas"][1][1].update(monstro={"nome": "x"}), "só salas de Combate têm monstro")
    # um erro nao esconde os outros: todos saem de uma vez
    quebrado = deepcopy(bom)
    quebrado["organizacao"] = "Clube do Livro"
    quebrado["linhas"][0][0]["pericias"] = ["Alquimia"]
    try:
        de_dict(quebrado)
    except ErroDeValidacao as exc:
        assert len(exc.problemas) >= 2

    # --- todos os cogs do bot carregam e registram seus comandos? ---
    from src.main import COGS, IncursoesBot

    bot = IncursoesBot()
    bot.db = conn  # o setup_hook faria isso ao conectar
    for cog in COGS:
        await bot.load_extension(cog)
    nomes = sorted(c.qualified_name for c in bot.tree.walk_commands())
    for grupo in (
        "ficha registrar", "ficha listar", "incursao entrar", "incursao teste",
        "incursao atacar", "config intervalo", "organizacao placar",
    ):
        assert grupo in nomes, f"comando {grupo} não foi registrado"
    assert "ficha listar" in nomes and "ficha remover" in nomes
    for cog in COGS:
        await bot.unload_extension(cog)
    await bot.close()

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print(f"{len(nomes)} comandos registrados")


asyncio.run(main())
print("TODOS OS TESTES PASSARAM")
