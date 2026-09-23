"""Testes de resistencia: a tabela do documento, a ficha e a rolagem."""
from __future__ import annotations

import asyncio
import random
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import classes as cl, config, database as db, motor  # noqa: E402
from src.cogs.ficha import embed_ficha  # noqa: E402
from src.habilidades import ATIVA, PASSIVA, Habilidade, juntar  # noqa: E402
from src.rules import ATRIBUTOS, TIER_MAXIMO, mod_save  # noqa: E402
from fakes import CANAL, GUILD, JOGADORES, FakeCanal, FakeInteraction  # noqa: E402

# Os dois numeros do documento "Saves", tier a tier.
FORTE = {1: 5, 2: 7, 3: 8, 4: 10, 5: 11}
FRACO = {1: 3, 2: 4, 3: 4, 4: 5, 5: 5}

_ABERTAS = []


async def preparar():
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass
    config.DB_PATH = Path(__file__).resolve().parent / "teste_saves.db"
    config.DB_PATH.unlink(missing_ok=True)
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    return conn, FakeCanal(CANAL)


def caso_tabela_do_documento():
    """Save forte e fraco sao os numeros que a classe ja tem para pericia."""
    for classe in cl.CLASSES.values():
        for tier_da, numeros in classe.tiers.items():
            assert numeros.bonus_proficiencia == FORTE[tier_da], (classe.nome, tier_da)
            assert numeros.bonus_pericia == FRACO[tier_da], (classe.nome, tier_da)
    print("  os dois numeros do documento saem da tabela da classe: ok")


def caso_catalogo_dos_saves():
    """Cada classe do documento tem exatamente dois saves fortes, validos."""
    for identificador, fortes in cl.SAVES_FORTES.items():
        assert len(fortes) == 2, (identificador, fortes)
        assert len(set(fortes)) == 2, f"{identificador} repetiu um atributo"
        for atributo in fortes:
            assert atributo in ATRIBUTOS, (identificador, atributo)
    # as 14 previstas estao todas definidas, mesmo as sem tabela de numeros
    assert "mago" in cl.SAVES_FORTES and "mago" not in cl.CLASSES
    for nome in cl.CLASSES_PREVISTAS:
        assert cl.saves_fortes(nome), f"{nome} sem save definido"
    # e toda classe jogavel carrega os dela
    assert all(c.saves for c in cl.CLASSES.values())
    print(f"  as {len(cl.SAVES_FORTES)} classes estao no catalogo de saves: ok")


def caso_modificador_por_classe():
    ladino = cl.CLASSES["ladino"]
    assert ladino.saves == ("DES", "INT")
    numeros = ladino.numeros(1)
    assert mod_save("DES", numeros, ladino.saves) == FORTE[1]
    assert mod_save("FOR", numeros, ladino.saves) == FRACO[1]
    # e sobe junto com o tier
    assert mod_save("DES", ladino.numeros(9), ladino.saves) == FORTE[TIER_MAXIMO]

    # a ficha inteira de uma vez
    valores = cl.saves("barbaro", 5)
    assert set(valores) == set(ATRIBUTOS)
    assert valores["FOR"] == valores["CON"] == FORTE[3]
    assert valores["CAR"] == FRACO[3]
    print("  cada classe resiste melhor nos dois atributos do documento: ok")


def caso_classe_sem_tabela_e_sem_save():
    """Classe sem numeros ainda responde pelos saves; sem save, fica fraca."""
    # Mago ainda nao tem tabela de numeros, mas ja tem os saves
    assert cl.saves_fortes("Mago") == ("CON", "INT")
    assert cl.saves("mago", 1) == {}, "sem tabela de numeros nao ha modificador"
    # Xama, Bardo e Bruxo entraram depois do documento
    assert cl.saves_fortes("xama") == ("SAB", "CAR")
    assert cl.saves_fortes("Bardo") == ("DES", "CAR")
    assert cl.saves_fortes("bruxo") == ("SAB", "CAR")
    assert cl.saves("xama", 1)["SAB"] == FORTE[1]
    # e uma classe que nao existe nao quebra nada
    assert cl.saves_fortes("necromante") == ()
    assert cl.saves("necromante", 1) == {}
    numeros = cl.CLASSES["ladino"].numeros(1)
    assert mod_save("FOR", numeros, ()) == FRACO[1]
    print("  classe sem tabela ou sem save nao quebra a conta: ok")


def caso_efeito_soma_no_save():
    """Uma habilidade pode somar no save: geral ou so em alguns atributos."""
    aura = Habilidade("aura", "Aura", PASSIVA, "+2 em todo save", {"bonus_save": 2})
    firme = Habilidade("firme", "Firme", PASSIVA, "+3 em CON",
                       {"bonus_save_atributo": {"CON": 3}})
    efeitos = juntar([aura, firme])
    numeros = cl.CLASSES["guerreiro"].numeros(1)
    fortes = cl.CLASSES["guerreiro"].saves
    assert mod_save("CON", numeros, fortes, efeitos) == FORTE[1] + 2 + 3
    assert mod_save("CAR", numeros, fortes, efeitos) == FRACO[1] + 2
    # sem habilidade nenhuma, o neutro nao mexe em nada
    assert mod_save("CAR", numeros, fortes, juntar([])) == FRACO[1]
    print("  habilidade que soma no save entra no modificador: ok")


def caso_rolagem():
    rng = random.Random(7)
    resultado = motor.salvar("Grom", "CON", 5, 12, rng)
    assert 1 <= resultado.d20 <= 20
    assert resultado.total == resultado.d20 + 5
    assert resultado.passou == (resultado.total >= 12)

    # na CD exata, passa
    exato = motor.ResultadoSave("Grom", "CON", 7, 5, 12)
    assert exato.passou
    assert not motor.ResultadoSave("Grom", "CON", 6, 5, 12).passou
    # nem 1 nem 20 naturais decidem um save sozinhos
    assert not motor.ResultadoSave("Grom", "CON", 20, 0, 25).passou
    assert motor.ResultadoSave("Grom", "CON", 1, 30, 12).passou

    # vantagem nunca sai pior: mesma semente, dois dados
    justo = motor.salvar("Grom", "CON", 0, 99, random.Random(3))
    melhor = motor.salvar("Grom", "CON", 0, 99, random.Random(3), vantagem=True)
    assert melhor.d20 >= justo.d20
    print("  a rolagem do save soma o modificador e compara com a CD: ok")


def caso_save_da_criatura():
    padrao = motor.Inimigo(0, "Lobo", 13, 6, "1d8+2", 20, 20)
    assert padrao.save("DES") == 6 - motor.DEFASAGEM_DE_SAVE
    # com a planilha preenchida, vale o que ela diz
    chefe = motor.Inimigo(
        0, "Durao", 17, 9, "2d8+4", 120, 120, saves={"CON": 9, "SAB": 2}
    )
    assert chefe.save("CON") == 9
    assert chefe.save("SAB") == 2
    assert chefe.save("DES") == 9 - motor.DEFASAGEM_DE_SAVE

    rolado = motor.salvar_inimigo(chefe, "CON", 15, random.Random(1))
    assert rolado.quem == "Durao" and rolado.modificador == 9
    print("  a criatura resiste pela planilha, ou pelo padrao provisorio: ok")


async def caso_ficha_traz_os_saves():
    conn, canal = await preparar()
    dono = JOGADORES[0]
    pid = await db.criar_personagem(
        conn, GUILD, dono, "Sombra", "ladino", ["Furtividade"], nivel=3
    )
    personagem = await db.buscar_personagem(conn, pid)
    assert personagem["saves_fortes"] == ("DES", "INT")
    assert personagem["saves"]["DES"] == FORTE[2]
    assert personagem["saves"]["FOR"] == FRACO[2]

    campos = {
        f.name: f.value
        for f in embed_ficha(personagem, FakeInteraction(canal, dono).user).fields
    }
    assert "Resistencias" in campos, list(campos)
    assert f"DES **+{FORTE[2]}**" in campos["Resistencias"], campos["Resistencias"]
    assert f"FOR +{FRACO[2]}" in campos["Resistencias"]

    # e o combatente leva os saves para o combate
    combatente = motor.Combatente(
        dono, personagem["nome"], personagem["ca"], personagem["bonus_ataque"],
        personagem["dano_arma"], personagem["hp_max"], personagem["hp_max"],
        saves=personagem["saves"],
    )
    resultado = motor.salvar_combatente(combatente, "DES", 15, random.Random(2))
    assert resultado.modificador == FORTE[2]
    # quem entrar em combate sem saves na ficha resiste com 0, sem estourar
    cru = motor.Combatente(1, "Cru", 10, 0, "1d4", 10, 10)
    assert motor.salvar_combatente(cru, "DES", 10, random.Random(2)).modificador == 0
    print("  a ficha mostra as resistencias e o combate as recebe: ok")


async def main():
    try:
        caso_tabela_do_documento()
        caso_catalogo_dos_saves()
        caso_modificador_por_classe()
        caso_classe_sem_tabela_e_sem_save()
        caso_efeito_soma_no_save()
        caso_rolagem()
        caso_save_da_criatura()
        await caso_ficha_traz_os_saves()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        (Path(__file__).resolve().parent / "teste_saves.db").unlink(missing_ok=True)


asyncio.run(main())
print("TESTES DE SAVES PASSARAM")
