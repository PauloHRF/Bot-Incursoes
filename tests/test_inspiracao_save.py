"""Regressoes da Inspiracao no simulador, usando dano e saves do motor real."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import random
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import aleatorio, database as db, incursoes as I, motor  # noqa: E402
from tools.simulacao.execucao import Bancada, Ficha  # noqa: E402


@asynccontextmanager
async def bancada_bardica():
    fichas = [Ficha("bardo", 9, {"inspiracao_t2": "inspira_save"}) for _ in range(5)]
    with aleatorio.usar(random.Random(7)):
        async with Bancada(fichas, [I.Monstro("Alvo", 1, 0, "1d1", 1000)]) as bancada:
            await bancada.iniciar()
            yield bancada


def monstro(dados):
    base = {"ataque": 1, "dano": "1d1", **dados}
    monstros = I.monstros_de_criatura(base)
    assert monstros, base
    return motor.Inimigo(0, **{
        "nome": monstros[0].nome, "ca": monstros[0].ca, "ataque": monstros[0].ataque,
        "dano": monstros[0].dano, "hp_max": monstros[0].hp, "hp_atual": monstros[0].hp,
        "ataques": monstros[0].ataques, "golpes": monstros[0].golpes,
        "habilidade": monstros[0].habilidade,
    })


async def inspirar(bancada, estado, vez):
    # Cada cenario comeca sem usos: soma as reservas do proprio bot.
    await bancada.cog._inspirar_o_save(bancada.run, estado, vez)
    gastos = 0
    for uid in range(1, 6):
        gastos += sum((await db.usos_da_run(bancada.conn, bancada.run_id, uid)).values())
    return gastos


async def caso_simulador_recalcula_o_save():
    casos = [
        # HP, THP, dano, metade, anula, reducao, corte, HP final, THP final, dano final
        (10, 0, 100, True, False, 0, 0, 0, 0, 50),
        (10, 0, 100, False, False, 0, 0, 10, 0, 0),
        (50, 0, 21, True, False, 0, 0, 40, 0, 10),
        (50, 0, 20, False, False, 0, 0, 50, 0, 0),
        (50, 15, 20, True, False, 0, 0, 50, 5, 10),
        (10, 5, 100, False, False, 0, 0, 10, 5, 0),
        (10, 5, 100, True, True, 0, 0, 10, 5, 0),
        (50, 0, 21, True, False, 0.5, 2, 47, 0, 3),
    ]
    for hp, thp, dano, metade, anula, reducao, corte, hp_final, thp_final, dano_final in casos:
        async with bancada_bardica() as bancada:
            grupo = (await bancada.cog._estado(bancada.run)).combatentes
            alvo = grupo[1]
            alvo.hp_atual, alvo.thp = hp, thp
            alvo.save_anula = anula
            alvo.reducao_dano, alvo.reducao_plana = reducao, corte
            inimigo = monstro({
                "nome": "Algoz", "ca": 10, "hp": 100,
                "golpes": [{"nome": "Golpe", "ataque": 1, "dano": "1"}],
                "habilidade": {"nome": "Teste", "save": "CAR", "cd": 22,
                               "dano": str(dano), "metade": metade, "alvos": 1, "cada": 1},
            })
            estado = motor.EstadoCombate([inimigo], 1, grupo)
            with patch.object(motor, "rolar_d20", return_value=22-alvo.saves["CAR"]-1), \
                 patch.object(motor, "sortear_alvos", return_value=[alvo]):
                vez = motor.turno_do_inimigo(inimigo, estado)
            gastos = await inspirar(bancada, estado, vez)
            assert gastos == 1, gastos
            investida = vez.investidas[0]
            assert investida.save.passou, investida.save
            assert investida.dano == dano_final, (dano, investida.dano, dano_final)
            assert (alvo.hp_atual, alvo.thp) == (hp_final, thp_final), (
                hp, thp, dano, metade, alvo.hp_atual, alvo.thp
            )
    print("  simulador: dano letal, metade arredondada para baixo, THP e reducoes: ok")


async def caso_efeito_de_golpe_preserva_os_outros_ataques():
    for segundo_dano, metade, hp_final in [(10, False, 6), (10, True, 3),
                                           (100, False, 0), (100, True, 0)]:
        async with bancada_bardica() as bancada:
            grupo = (await bancada.cog._estado(bancada.run)).combatentes
            alvo = grupo[1]
            alvo.hp_atual = 20
            inimigo = monstro({
                "nome": "Algoz", "ca": 10, "hp": 100, "meta": {"num_acoes": 2},
                "golpes": [
                    {"nome": "Garra", "ataque": 100, "dano": "4",
                     "efeito": {"nome": "Veneno", "save": "CAR", "cd": 22,
                                "dano": "6", "metade": metade}},
                    {"nome": "Mordida", "ataque": 100, "dano": str(segundo_dano)},
                ],
            })
            estado = motor.EstadoCombate([inimigo], 1, grupo)
            with patch.object(motor, "rolar_d20", return_value=10), \
                 patch.object(motor, "sortear_alvo", return_value=alvo):
                vez = motor.turno_do_inimigo(inimigo, estado)
            assert alvo.caido, alvo.hp_atual
            assert len(vez.golpes) == 2 and len(vez.investidas) == 1, vez
            assert await inspirar(bancada, estado, vez) == 1
            assert alvo.hp_atual == hp_final, (segundo_dano, metade, alvo.hp_atual)
            assert [g.dano for g, _ in vez.golpes] == [4, segundo_dano], vez.golpes
    print("  socorrer o efeito do golpe preserva ataques anteriores e posteriores: ok")


async def caso_dois_saves_na_mesma_vez():
    async with bancada_bardica() as bancada:
        grupo = (await bancada.cog._estado(bancada.run)).combatentes
        alvo = grupo[1]
        alvo.hp_atual, alvo.thp = 20, 10
        inimigo = monstro({
            "nome": "Algoz", "ca": 10, "hp": 100, "meta": {"num_acoes": 2},
            "golpes": [
                {"nome": "Garra", "ataque": 100, "dano": "1",
                 "efeito": {"nome": "Veneno", "save": "CAR", "cd": 22, "dano": str(dano)}}
                for dano in (6, 8)
            ],
        })
        estado = motor.EstadoCombate([inimigo], 1, grupo)
        with patch.object(motor, "rolar_d20", return_value=10), \
             patch.object(motor, "sortear_alvo", return_value=alvo):
            vez = motor.turno_do_inimigo(inimigo, estado)
        assert await inspirar(bancada, estado, vez) == 2
        assert (alvo.hp_atual, alvo.thp) == (20, 8), (alvo.hp_atual, alvo.thp)
        assert all(i.save.passou and i.dano == i.absorvido == 0 for i in vez.investidas)
        assert [g.absorvido for g, _ in vez.golpes] == [1, 1]
        print("  dois saves socorridos preservam o THP e os golpes basicos: ok")


def caso_bonus_insuficiente_e_controle():
    alvo = motor.Combatente(1, "Alvo", 10, 0, "1", 50, 50)
    inimigo = motor.Inimigo(0, "Algoz", 10, 0, "1", 100, 100)
    efeito = SimpleNamespace(nome="Grito", save="CAR", cd=12, dano="7", metade=False,
                             atordoa=1, save_repete=True, debuff=["Debilidade"])
    with patch.object(motor, "rolar_d20", return_value=10):
        investida = motor.impor_save(inimigo, efeito, alvo)
    vez = motor.RodadaInimiga(investidas=[investida], vida_inicial={1: (50, 0)})
    assert not motor.refazer_o_save(vez, investida, 1)
    assert (alvo.hp_atual, investida.dano, investida.save.total) == (43, 7, 10)
    assert alvo.atordoado and investida.atordoou and investida.repete_save
    assert investida.debuffs == ["Debilidade"]
    assert motor.refazer_o_save(vez, investida, 2)
    assert (alvo.hp_atual, investida.dano, investida.save.total) == (50, 0, 12)
    assert investida.save.d20 == 10
    assert not alvo.atordoado and not investida.atordoou and not investida.repete_save
    assert not investida.debuffs
    # Nao devolve a mesma vida duas vezes nem soma o bonus de novo.
    assert not motor.refazer_o_save(vez, investida, 2)
    assert (alvo.hp_atual, investida.save.total) == (50, 12)
    print("  bonus insuficiente nao altera o efeito; sucesso limpa controle sem duplicar cura: ok")


async def main():
    await caso_simulador_recalcula_o_save()
    await caso_efeito_de_golpe_preserva_os_outros_ataques()
    await caso_dois_saves_na_mesma_vez()
    caso_bonus_insuficiente_e_controle()
    print("TESTES DA INSPIRACAO NO SAVE PASSARAM")


if __name__ == "__main__":
    asyncio.run(main())
