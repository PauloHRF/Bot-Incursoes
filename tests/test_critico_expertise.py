"""Criticos no combate e bonus avulsos por pericia (expertise)."""
from __future__ import annotations

import asyncio
import random
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import config, database as db, embeds as E, motor  # noqa: E402
from src.cogs.ficha import Ficha, embed_ficha  # noqa: E402
from src.cogs.incursao import Incursoes  # noqa: E402
from src.incursoes import Monstro, Sala  # noqa: E402
from src.rules import melhor_pericia, mod_pericia  # noqa: E402
from fakes import (  # noqa: E402
    ATRIBUTOS,
    CANAL,
    GUILD,
    INDEFESO,
    JOGADORES,
    FakeBot,
    FakeCanal,
    FakeInteraction,
    criar_grupo,
    incursao_teste,
)

_ABERTAS = []


class DadoFixo:
    """Devolve os d20 que eu mandar; o resto do dado continua aleatório."""

    def __init__(self, sequencia):
        self.sequencia = list(sequencia)
        self._acaso = random.Random(1)

    def randint(self, a, b):
        if (a, b) == (1, 20) and self.sequencia:
            return self.sequencia.pop(0)
        return self._acaso.randint(a, b)

    def choice(self, seq):
        return self._acaso.choice(seq)


async def preparar():
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass
    config.DB_PATH = Path(__file__).resolve().parent / "teste_critico.db"
    config.DB_PATH.unlink(missing_ok=True)
    config.TAMANHO_GRUPO = 5
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    canal = FakeCanal(CANAL)
    cog = Incursoes(FakeBot(conn, canal))
    cog.incursoes = {"t": incursao_teste("t", INDEFESO)}
    return conn, canal, cog


def caso_vinte_e_um_naturais():
    """20 acerta mesmo contra CA absurda; 1 erra mesmo com bônus absurdo."""
    vinte = motor.atacar("A", 0, "1d6", "B", ca_alvo=99, rng=DadoFixo([20]))
    assert vinte.acertou and vinte.critico and not vinte.falha_critica
    assert vinte.dano > 0

    um = motor.atacar("A", 50, "1d6", "B", ca_alvo=5, rng=DadoFixo([1]))
    assert not um.acertou and um.falha_critica and not um.critico
    assert um.dano == 0

    # no meio da tabela vale a conta normal: 10+5=15 nao alcanca CA 16
    perto = motor.atacar("A", 5, "1d6", "B", ca_alvo=16, rng=DadoFixo([10]))
    assert not perto.acertou and not perto.critico and not perto.falha_critica
    # e 15 empatado com a CA 15 acerta, sem ser critico
    empate = motor.atacar("A", 5, "1d6", "B", ca_alvo=15, rng=DadoFixo([10]))
    assert empate.acertou and not empate.critico
    print("  20 acerta sempre, 1 erra sempre: ok")


def caso_dano_critico_dobra_os_dados():
    """O crítico dobra os dados e mantém o modificador uma vez só."""
    r = random.Random(7)
    normais = [motor.rolar_dano("2d6+3", r) for _ in range(3000)]
    criticos = [motor.rolar_dano("2d6+3", r, critico=True) for _ in range(3000)]
    assert min(normais) == 5 and max(normais) == 15, (min(normais), max(normais))
    assert min(criticos) == 7 and max(criticos) == 27, (min(criticos), max(criticos))

    # um dado sem modificador dobra limpo
    so_dados = [motor.rolar_dano("1d8", r, critico=True) for _ in range(2000)]
    assert min(so_dados) == 2 and max(so_dados) == 16

    # o piso de 1 continua valendo num dano negativo
    assert motor.rolar_dano("1d4-10", r, critico=True) == 1
    print("  crítico dobra os dados, não o modificador: ok")


def caso_marcacao_visual():
    """As linhas de combate ganham emoji de crítico e de erro crítico."""
    critico = motor.GolpeAtaque("Vhalor", "Chefe", d20=20, bonus=7, ca_alvo=16, dano=21)
    falha = motor.GolpeAtaque("Kaelen", "Chefe", d20=1, bonus=7, ca_alvo=16)
    acerto = motor.GolpeAtaque("Brannak", "Chefe", d20=14, bonus=7, ca_alvo=16, dano=9)
    erro = motor.GolpeAtaque("Tass", "Chefe", d20=3, bonus=7, ca_alvo=16)

    assert E.EMOJI_CRITICO in E.linha_golpe(critico)
    assert "CRITICO" in E.linha_golpe(critico) and "21" in E.linha_golpe(critico)
    assert E.EMOJI_FALHA_CRITICA in E.linha_golpe(falha)
    assert E.EMOJI_CRITICO not in E.linha_golpe(acerto) and "9" in E.linha_golpe(acerto)
    assert "errou" in E.linha_golpe(erro)
    print("  emoji de crítico e de erro crítico: ok")


def caso_critico_sobrevive_ao_banco():
    """O golpe reconstruído dos registros continua sendo crítico."""
    original = motor.atacar("A", 3, "1d8+2", "B", ca_alvo=15, rng=DadoFixo([20]))
    # e assim que o cog remonta o golpe ao fechar a rodada
    remontado = motor.GolpeAtaque(
        atacante="A",
        alvo="B",
        d20=original.d20,
        bonus=original.bonus,
        ca_alvo=original.ca_alvo,
        dano=original.dano,
    )
    assert remontado.critico and remontado.acertou
    assert E.EMOJI_CRITICO in E.linha_golpe(remontado)
    print("  crítico continua marcado depois de ir e voltar do banco: ok")


def caso_bonus_entra_no_modificador():
    atributos = {"FOR": 10, "DES": 16, "CON": 14, "INT": 12, "SAB": 13, "CAR": 8}
    treinadas = ["Furtividade"]

    # DES +3, proficiencia +3 no nivel 8 -> +6
    assert mod_pericia("Furtividade", atributos, 8, treinadas) == 6
    # com +2 de expertise -> +8
    assert mod_pericia("Furtividade", atributos, 8, treinadas, {"Furtividade": 2}) == 8
    # pericia nao treinada tambem aceita bonus: DES +3 e mais +4
    assert mod_pericia("Acrobacia", atributos, 8, treinadas, {"Acrobacia": 4}) == 7
    # bonus negativo desce o modificador
    assert mod_pericia("Furtividade", atributos, 8, treinadas, {"Furtividade": -2}) == 4
    # bonus de outra pericia nao vaza
    assert mod_pericia("Furtividade", atributos, 8, treinadas, {"Atletismo": 9}) == 6

    # o bonus pode mudar qual pericia e a melhor da sala
    assert melhor_pericia(["Atletismo", "Furtividade"], atributos, 8, treinadas)[0] == "Furtividade"
    assert melhor_pericia(
        ["Atletismo", "Furtividade"], atributos, 8, treinadas, {"Atletismo": 10}
    ) == ("Atletismo", 10)
    print("  bônus entra no modificador e pode virar a melhor perícia: ok")


async def caso_expertise_persistida():
    conn, canal, cog = await preparar()
    ficha_cog = Ficha(FakeBot(conn, canal))
    dono = JOGADORES[0]
    pid = await db.criar_personagem(
        conn, GUILD, dono, "Vhalor", 8, ATRIBUTOS, ["Furtividade"]
    )

    class Escolha:
        def __init__(self, value):
            self.value = value
            self.name = value

    inter = FakeInteraction(canal, dono)
    await ficha_cog.expertise.callback(ficha_cog, inter, Escolha("Furtividade"), 3)
    assert "Furtividade" in inter.resposta

    p = await db.buscar_personagem(conn, pid)
    assert p["bonus_pericias"] == {"Furtividade": 3}, p["bonus_pericias"]
    assert mod_pericia("Furtividade", p["atributos"], p["nivel"], p["pericias"], p["bonus_pericias"]) == 9

    # a ficha mostra a expertise
    campos = {f.name: f.value for f in embed_ficha(p, inter.user).fields}
    assert "Expertises" in campos and "+3" in campos["Expertises"]

    # um segundo bonus convive com o primeiro
    await ficha_cog.expertise.callback(
        ficha_cog, FakeInteraction(canal, dono), Escolha("Arcanismo"), 2
    )
    p = await db.buscar_personagem(conn, pid)
    assert p["bonus_pericias"] == {"Furtividade": 3, "Arcanismo": 2}

    # zero remove
    await ficha_cog.expertise.callback(
        ficha_cog, FakeInteraction(canal, dono), Escolha("Furtividade"), 0
    )
    p = await db.buscar_personagem(conn, pid)
    assert p["bonus_pericias"] == {"Arcanismo": 2}

    # o bonus e de um personagem so
    outro = await db.criar_personagem(conn, GUILD, dono, "Kaelen", 3, ATRIBUTOS, [])
    assert (await db.buscar_personagem(conn, outro))["bonus_pericias"] == {}
    print("  expertise gravada, somada e removida com 0: ok")


async def caso_expertise_vale_na_run():
    """O teste de perícia da sala usa o bônus do personagem."""
    conn, canal, cog = await preparar()
    await criar_grupo(conn)
    dono = JOGADORES[0]
    personagem = await db.personagem_por_nome(conn, GUILD, dono, f"Heroi{dono}")
    await db.definir_bonus_pericia(conn, personagem["id"], "Percepção", 7)

    sala = Sala(
        id="X",
        nome="Sala",
        tipo="Evento",
        descricao="teste",
        dificuldade="Fácil",
        cd=10,
        alvo_progresso=5,
        pericias=["Percepção"],
    )
    com_bonus = await db.buscar_personagem(conn, personagem["id"])
    com_bonus["user_id"] = dono
    resultado = motor.testar(com_bonus, sala, DadoFixo([10]))
    sem_bonus = mod_pericia("Percepção", com_bonus["atributos"], com_bonus["nivel"], com_bonus["pericias"])
    assert resultado.modificador == sem_bonus + 7, (resultado.modificador, sem_bonus)
    print("  expertise vale no teste de perícia da sala: ok")


async def main():
    try:
        caso_vinte_e_um_naturais()
        caso_dano_critico_dobra_os_dados()
        caso_marcacao_visual()
        caso_critico_sobrevive_ao_banco()
        caso_bonus_entra_no_modificador()
        await caso_expertise_persistida()
        await caso_expertise_vale_na_run()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        (Path(__file__).resolve().parent / "teste_critico.db").unlink(missing_ok=True)


asyncio.run(main())
print("TESTES DE CRITICO E EXPERTISE PASSARAM")
