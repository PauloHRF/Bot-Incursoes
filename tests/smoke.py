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

    # --- a sala lista criaturas POR TIER, e nada escala ---
    #
    # Antes a ficha do banco era a do tier 1 e o combate a multiplicava pelo
    # tier do grupo (x3,1 no tier 4), em cima de criaturas ja escritas em
    # forca cheia de Monster Manual: as cinco salas de combate de um banco
    # dizimavam o grupo sempre. Agora cada sala diz quem cada tier encontra, e
    # estas asserções impedem um banco novo de voltar a sair sem isso.
    for arquivo in sorted((raiz / "data" / "bancos").glob("*.json")):
        de_combate = [s for s in carregar_banco(arquivo).salas if s.e_combate]
        assert de_combate, arquivo.name
        for sala in de_combate:
            assert sala.monstros_por_tier, f"{arquivo.name}/{sala.id} sem lista por tier"
            for t in range(1, TIER_MAXIMO + 1):
                quem = sala.monstros_do_tier(t)
                assert quem, f"{arquivo.name}/{sala.id} nao tem criatura no tier {t}"
                assert all(m.hp > 0 for m in quem), (arquivo.name, sala.id, t)
            # Sem tier a sala devolve o menor escrito, que e o piso dela.
            assert sala.monstros_do_tier() == sala.monstros_do_tier(
                min(sala.monstros_por_tier)
            ), f"{arquivo.name}/{sala.id}: o piso nao e o menor tier escrito"

    def tier_invalido(d):
        for sala in d["salas"]:
            if sala.get("monstros_por_tier"):
                sala["monstros_por_tier"]["9"] = [{"nome": "Lobo"}]
                return
        raise AssertionError("o banco de exemplo perdeu a lista por tier")

    recusa(bom_banco, tier_invalido, "monstros_por_tier", banco_de_dict)
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

    # --- em que guildas os comandos sao registrados ---
    #
    # `guildas_de` e pura de proposito: e ela que tem regra, e um id de guilda
    # errado no .env custa os comandos de um servidor inteiro.
    assert config.guildas_de("") == ()
    assert config.guildas_de("123") == (123,)
    assert config.guildas_de(" 123 , 456 ") == (123, 456), "espaco e virgula"
    assert config.guildas_de("123,456") == (123, 456)
    assert config.guildas_de("123;456") == (123, 456), "ponto e virgula tambem"
    assert config.guildas_de("123,123") == (123,), "guilda repetida sincroniza uma vez"
    assert config.guildas_de("456,123") == (456, 123), "a ordem do .env e mantida"
    for lixo in ("0", "abc", "-5", "12.5", ","):
        assert config.guildas_de(lixo) == (), f"{lixo!r} nao e id de guilda"
    assert config.guildas_de("123,abc,,456") == (123, 456), "lixo no meio nao derruba"

    # E o bot usa ESSA lista para decidir o caminho: uma guilda por POST, ou um
    # POST global. Sincronizar de verdade pede rede, entao o teste troca o
    # `tree` por um dublê e olha para onde o bot mandou.
    from src.main import IncursoesBot as _Bot

    class TreeFalsa:
        def __init__(self):
            self.copiadas = []
            self.sincronizadas = []

        def copy_global_to(self, guild):
            self.copiadas.append(guild.id)

        async def sync(self, guild=None):
            self.sincronizadas.append(guild.id if guild else None)
            return []

    async def para_onde(ids):
        bot = _Bot()
        falsa = TreeFalsa()
        # `bot.tree` e propriedade de leitura: o atributo por tras tem o nome
        # mangled da classe que o cria (`BotBase.__tree`).
        bot._BotBase__tree = falsa
        original = config.GUILD_IDS
        config.GUILD_IDS = ids
        try:
            await bot._sincronizar()
        finally:
            config.GUILD_IDS = original
            await bot.close()
        return falsa

    falsa = await para_onde((111, 222))
    assert falsa.sincronizadas == [111, 222], falsa.sincronizadas
    assert falsa.copiadas == [111, 222], (
        "cada guilda precisa receber a copia dos comandos globais antes do sync"
    )

    falsa = await para_onde(())
    assert falsa.sincronizadas == [None], (
        f"sem guilda no .env o registro e global, veio {falsa.sincronizadas}"
    )
    assert falsa.copiadas == [], "o sync global nao copia para guilda nenhuma"
    print("GUILD_IDS: registra por guilda, ou global sem nenhuma")

    # --- todos os cogs do bot carregam e registram seus comandos? ---
    from src.main import COGS, IncursoesBot

    bot = IncursoesBot()
    bot.db = conn  # o setup_hook faria isso ao conectar
    for cog in COGS:
        await bot.load_extension(cog)
    nomes = sorted(c.qualified_name for c in bot.tree.walk_commands())
    for grupo in (
        "ficha registrar", "ficha listar", "ficha upar", "incursao entrar",
        "mercado vitrine", "mercado equipar",
        "config intervalo", "organizacao placar",
        # O remover voltou, mas so para admin: sem ele o limite de 25
        # personagens por jogador virava parede sem saida.
        "ficha remover", "ficha alterar",
    ):
        assert grupo in nomes, f"comando {grupo} não foi registrado"
    # O que saiu de propósito: combate é por botão (o painel tem Atacar,
    # Habilidade e Rolar teste), a bolsa absorveu o ouro, e trocar de
    # equipamento no mesmo slot dispensa desequipar.
    for fora in (
        "ficha pericias", "incursao atacar",
        "incursao habilidade", "incursao sala", "incursao teste",
        "mercado ouro", "mercado desequipar",
    ):
        assert fora not in nomes, f"comando {fora} deveria ter saido"
    for cog in COGS:
        await bot.unload_extension(cog)
    await bot.close()

    await conn.close()
    config.DB_PATH.unlink(missing_ok=True)
    print(f"{len(nomes)} comandos registrados")

    # --- e a linha que LE o .env? ---
    #
    # O parser acima e puro e bem coberto, mas quem decide o que ele recebe e
    # uma linha de modulo. Uma sabotagem que trocava essa linha por
    # `.split(",")[0]` — um id so, silenciosamente — passava por tudo: o teste
    # chamava `guildas_de` direto e sobrescrevia `GUILD_IDS` na mao. O jeito de
    # testar a linha e recarregar o modulo com um ambiente posto.
    #
    # Os dois valores vao EXPLICITOS no ambiente, nunca ausentes: `load_dotenv`
    # nao sobrescreve o que ja esta no ambiente, mas preenche o que falta — com
    # a variavel ausente, o teste passaria a depender do .env desta maquina.
    import importlib
    import os

    guardado = {k: os.environ.get(k) for k in ("GUILD_IDS", "GUILD_ID")}
    db_path = config.DB_PATH
    try:
        os.environ["GUILD_IDS"] = "111,222"
        os.environ["GUILD_ID"] = "999"
        assert importlib.reload(config).GUILD_IDS == (111, 222), (
            "GUILD_IDS do .env tem de virar a lista inteira, e ganhar do singular"
        )
        os.environ["GUILD_IDS"] = ""
        os.environ["GUILD_ID"] = "333"
        assert importlib.reload(config).GUILD_IDS == (333,), (
            "sem GUILD_IDS, o GUILD_ID antigo ainda vale"
        )
    finally:
        for chave, valor in guardado.items():
            if valor is None:
                os.environ.pop(chave, None)
            else:
                os.environ[chave] = valor
        importlib.reload(config)
        config.DB_PATH = db_path
    print("GUILD_IDS: a linha que le o .env faz a lista e aceita o nome antigo")



asyncio.run(main())
print("TODOS OS TESTES PASSARAM")
