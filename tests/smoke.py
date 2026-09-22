"""Teste de fumaca: regras + persistencia + carregamento dos cogs, sem conectar no Discord."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import classes, config, database as db
from src.rules import (
    NIVEL_MAXIMO,
    TIER_MAXIMO,
    melhor_pericia,
    mod_pericia,
    normalizar_pericia,
    tier,
)

# --- regras ---
assert NIVEL_MAXIMO == TIER_MAXIMO * 2
# toda classe jogavel tem tabela ate o ultimo tier
assert classes.tier_maximo_com_tabela() == TIER_MAXIMO
for c in classes.CLASSES.values():
    assert set(c.tiers) == set(range(1, TIER_MAXIMO + 1)), c.nome
    assert c.numeros(NIVEL_MAXIMO) is c.tiers[TIER_MAXIMO]
assert [tier(n) for n in (1, 2, 3, 4, 5, 9, 10, 99)] == [1, 1, 2, 2, 3, 5, 5, 5]

# O bonus de pericia vem da classe, nao de atributo: +3, ou +5 com proficiencia.
numeros = classes.classe("ladino").numeros(1)
assert mod_pericia("Furtividade", numeros, ["Furtividade"]) == 5
assert mod_pericia("Acrobacia", numeros, ["Furtividade"]) == 3
assert melhor_pericia(["Atletismo", "Furtividade"], numeros, ["Furtividade"]) == ("Furtividade", 5)
# a expertise soma por cima
assert mod_pericia("Acrobacia", numeros, [], {"Acrobacia": 4}) == 7

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
        conn, 1, 42, "Vhalor", "ladino", ["Furtividade", "Percepção"], nivel=5
    )
    assert vhalor_id
    f = await db.buscar_personagem(conn, vhalor_id)
    assert f["nome"] == "Vhalor" and f["nivel"] == 5
    assert f["pericias"] == ["Furtividade", "Percepção"]
    # os numeros de combate saem da tabela do Ladino no tier 3 (nivel 5-6)
    assert (f["ca"], f["bonus_ataque"], f["dano_arma"], f["hp_max"]) == (16, 7, "4d6+4", 45)

    # quem comeca no nivel 1 pega o tier 1 da propria classe
    magro_id = await db.criar_personagem(conn, 1, 42, "Sem Arma", "monge", [])
    magro = await db.buscar_personagem(conn, magro_id)
    assert (magro["ca"], magro["hp_max"], magro["dano_arma"]) == (16, 17, "1d6+3")
    assert magro["nivel"] == 1, "todo personagem nasce no nivel 1"

    # subir de nivel nao apaga nada e os numeros acompanham o tier
    assert await db.atualizar_personagem(conn, vhalor_id, "nivel", 9)
    f = await db.buscar_personagem(conn, vhalor_id)
    assert f["nivel"] == 9 and f["pericias"] == ["Furtividade", "Percepção"]
    assert (f["ca"], f["bonus_ataque"], f["dano_arma"], f["hp_max"]) == (18, 10, "6d6+5", 73)
    assert mod_pericia("Furtividade", f["numeros"], f["pericias"]) == 11

    # o mesmo jogador tem varios personagens, buscaveis por nome
    assert len(await db.listar_personagens(conn, 1, 42)) == 2
    assert (await db.personagem_por_nome(conn, 1, 42, "vhalor"))["id"] == vhalor_id
    assert await db.personagem_por_nome(conn, 1, 42, "Ninguem") is None

    # dois personagens do mesmo jogador nao podem ter o mesmo nome
    assert await db.criar_personagem(conn, 1, 42, "Vhalor", "monge", []) is None
    # mas jogadores diferentes podem repetir nome
    assert await db.criar_personagem(conn, 1, 43, "Vhalor", "monge", []) is not None

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

    # --- incursoes e bancos: JSON de exemplo e validacao ---
    from copy import deepcopy
    import json
    from src.incursoes import (
        ErroDeValidacao,
        TAMANHOS,
        banco_de_dict,
        carregar,
        carregar_banco,
        de_dict,
    )

    raiz = Path(__file__).resolve().parents[1]
    inc = carregar(raiz / "data" / "incursoes" / "vortice_cripta.json")
    assert inc.organizacao == "Vórtice Oculto"
    assert inc.tamanho in TAMANHOS and inc.passos == TAMANHOS[inc.tamanho]
    assert inc.lore_inicial and inc.lore_final, "a incursão de exemplo precisa das duas lores"
    assert inc.objetivo.tipo == "Combate" and inc.objetivo.monstros
    assert all(m.hp > 0 for m in inc.objetivo.monstros)
    # o JSON sobrevive a uma ida e volta pelo validador
    assert de_dict(inc.para_dict()).para_dict() == inc.para_dict()

    banco = carregar_banco(raiz / "data" / "bancos" / "vortice_oculto.json")
    assert banco.organizacao == "Vórtice Oculto"
    assert len(banco.salas) >= 3
    assert banco.sala(banco.salas[0].id) is banco.salas[0]
    assert banco.sala("nao_existe") is None
    assert any(s.e_combate for s in banco.salas), "o banco de exemplo tem salas de combate"
    assert any(s.tem_teste for s in banco.salas)
    assert banco_de_dict(banco.para_dict()).para_dict() == banco.para_dict()

    bom = json.loads((raiz / "data" / "incursoes" / "vortice_cripta.json").read_text(encoding="utf-8"))
    bom_banco = json.loads((raiz / "data" / "bancos" / "vortice_oculto.json").read_text(encoding="utf-8"))

    def recusa(dados, mutacao, trecho, monta=de_dict):
        copia = deepcopy(dados)
        mutacao(copia)
        try:
            monta(copia)
        except ErroDeValidacao as exc:
            assert any(trecho in p for p in exc.problemas), (trecho, exc.problemas)
        else:
            raise AssertionError(f"deveria ter recusado: {trecho}")

    def vira_evento(d):
        d["objetivo"]["tipo"] = "Evento"
        d["objetivo"]["monstros"] = []

    recusa(bom, vira_evento, "desafio final é sempre Combate")
    recusa(bom, lambda d: d.update(tamanho="Gigante"), "tamanho")
    recusa(bom, lambda d: d.update(lore_inicial="", descricao=""), "lore de abertura")
    recusa(bom, lambda d: d["objetivo"].update(monstros=[]), "precisa de pelo menos uma criatura")
    recusa(bom, lambda d: d["objetivo"]["monstros"][0].update(dano="muito"), "fora do formato")
    recusa(bom, lambda d: d.update(organizacao="Clube do Livro"), "organizacao")
    recusa(bom, lambda d: d.update(id="Vórtice Cripta"), "letras minúsculas")
    recusa(bom, lambda d: d.update(pontos_conclusao=-5), "não pode ser negativo")

    recusa(bom_banco, lambda d: d.update(salas=d["salas"][:2]), "pelo menos", banco_de_dict)
    recusa(bom_banco, lambda d: d["salas"][0]["pericias"].append("Alquimia"), "não existe", banco_de_dict)
    recusa(bom_banco, lambda d: d["salas"].append(deepcopy(d["salas"][0])), "aparece 2 vezes", banco_de_dict)
    recusa(bom_banco, lambda d: d["salas"][0].update(tipo="Puzzle"), "inválido", banco_de_dict)
    recusa(bom_banco, lambda d: d.update(organizacao="Clube do Livro"), "organizacao", banco_de_dict)

    # um erro nao esconde os outros: todos saem de uma vez
    quebrado = deepcopy(bom)
    quebrado["organizacao"] = "Clube do Livro"
    quebrado["tamanho"] = "Gigante"
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
