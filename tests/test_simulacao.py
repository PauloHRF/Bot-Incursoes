"""Cobertura do backend compartilhado, isolamento e comparacoes controladas."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import csv
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import aleatorio, classes, database as db, motor
from src.incursoes import HabilidadeDoMonstro, Monstro, Sala
from tools.simulacao.execucao import Bancada, Ficha, simular_async
from tools.simulacao.comparacao import carregar_builds, carregar_cenarios, comparar
from tools.simulacao.estatisticas import intervalo
from tools.simular_combate import simular

ALVO = Monstro("Alvo", 1, 0, "1d1", 1000)


class Execucao(unittest.IsolatedAsyncioTestCase):
    async def test_todas_as_classes_passam_pelo_motor_real(self):
        for cid in classes.CLASSES:
            with self.subTest(classe=cid):
                # Falha se a bancada tentar abrir o banco configurado do bot.
                with patch.object(db, "conectar", side_effect=AssertionError("banco externo")):
                    r = await simular_async([Monstro("Fragil", 1, 0, "1d1", 1)],
                                            [Ficha(cid, 9)]*3, 1, random.Random(7))
                self.assertTrue(r[0]["inimigos_derrotados"])
                self.assertGreaterEqual(r[0]["dano"], 1)

    async def test_infusao_e_aura_alcancam_outras_classes(self):
        fichas = [Ficha("artifice", 9, {"infusao": "armas"}),
                  Ficha("mago", 9, {"tradicao_arcana": "sabedoria_arcana"}), Ficha("guerreiro", 9)]
        async with Bancada(fichas, [ALVO]) as b:
            await b.iniciar()
            estado = await b.cog._estado(b.run)
            guerreiro = estado.combatente(3)
            self.assertEqual(guerreiro.bonus_ataque, classes.numeros("guerreiro", 9).acerto + 1)
            base = classes.saves("guerreiro", 9, classes.efeitos("guerreiro", 9, fichas[2].escolhas))
            self.assertEqual(guerreiro.saves, {k: v+2 for k, v in base.items()})

    async def test_abertura_do_mago_acontece_uma_vez(self):
        fichas = [Ficha("mago", 9, {"tradicao_arcana": "escudo_arcano"})]
        async with Bancada(fichas, [ALVO]) as b:
            await b.iniciar()
            estado = await b.cog._estado(b.run)
            self.assertEqual(estado.combatente(1).thp, 10)
            await db.definir_thp(b.conn, b.run_id, 1, 0)
            estado = await b.cog._estado(b.run)
            await b.cog._resolver_habilidade(b.run, estado, 1, classes.POR_ID["fireball"], [])
            depois = await b.cog._estado(b.run)
            self.assertEqual(depois.combatente(1).thp, 0)
            self.assertEqual((await b.cog._estado(b.run)).combatente(1).thp, 0)
            self.assertEqual(b.cog.metricas["thp_gerado"], 10)

    async def test_totem_e_aura_do_xama_chegam_ao_grupo(self):
        async with Bancada([Ficha("xama", 9), Ficha("guerreiro", 9)], [ALVO]) as b:
            await b.iniciar()
            antes = await b.cog._estado(b.run)
            acerto = antes.combatente(2).bonus_ataque
            await db.definir_thp(b.conn, b.run_id, 1, 5)
            depois = await b.cog._estado(b.run)
            self.assertEqual(depois.combatente(2).bonus_ataque, acerto + 2)
            self.assertEqual(depois.combatente(2).dano_extra, antes.combatente(2).dano_extra + 2)

    async def test_limite_nao_ganha_rodada_extra(self):
        r = await simular_async([Monstro("Muralha", 99, 0, "1d1", 100000)],
                               [Ficha("guerreiro", 1)], 1, random.Random(3), limite=1)
        self.assertTrue(r[0]["limite_rodadas"])
        self.assertEqual(r[0]["rodadas"], 1)
        self.assertFalse(r[0]["inimigos_derrotados"])

    async def test_inspiracao_conta_recurso_e_reduz_dano_do_save(self):
        especial = HabilidadeDoMonstro(nome="Teste", save="CAR", cd=22, dano="100", metade=True, alvos=1, cada=1)
        inimigo = Monstro("Algoz", 10, 1, "1d1", 1000)
        fichas = [Ficha("bardo", 9, {"inspiracao_t2": "inspira_save"})]*3
        async with Bancada(fichas, [inimigo]) as b:
            await b.iniciar()
            estado = await b.cog._estado(b.run)
            estado.inimigos[0].habilidade = especial
            alvo = estado.combatente(1)
            b.cog.metricas.clear()
            with patch.object(motor, "rolar_d20", return_value=21-alvo.saves["CAR"]), \
                 patch.object(motor, "sortear_alvos", return_value=[alvo]):
                await b.cog._vez_do_inimigo(b.run, estado, estado.inimigos[0], [])
            self.assertEqual(sum(b.cog.reacoes.values()), 1)
            self.assertEqual(b.cog.metricas["recebido"], 50)

    async def test_builds_do_mesmo_candidato_recebem_as_mesmas_sementes(self):
        builds = {"B": {"classe": "guerreiro"}, "A": {"classe": "guerreiro"}}
        salas = {1: [Sala("C", "C", "Combate", "", monstros=[ALVO])]}
        a = await comparar(builds, salas, [1], [3], 2, 99, bases=[("clerigo", "mago")])
        b = await comparar(dict(reversed(list(builds.items()))), salas, [1], [3], 2, 99,
                           bases=[("clerigo", "mago")])
        self.assertEqual(a["resultados"], b["resultados"])
        rows = a["resultados"]
        self.assertEqual(rows[0]["semente"], rows[1]["semente"])
        for k in ("vitorias", "rodadas_media", "hp_restante_pct", "cura_media"):
            self.assertEqual(rows[0][k], rows[1][k])


class Interface(unittest.TestCase):
    def test_estudio_e_threads_reproduzem_sem_alterar_funcoes_globais(self):
        args = SimpleNamespace(classe="druida", nivel=9, repeticoes=3)
        rng_original, iniciativa_original = motor._rng, motor.rolar_iniciativas
        def medir(seed):
            return simular([Monstro("Alvo", 12, 4, "1d6", 60)], 3, args, random.Random(seed))
        esperado = medir(13)
        with ThreadPoolExecutor(max_workers=2) as pool:
            resultados = list(pool.map(medir, [13, 27, 13]))
        self.assertEqual(esperado, resultados[0])
        self.assertEqual(esperado, resultados[2])
        self.assertIs(motor._rng, rng_original)
        self.assertIs(motor.rolar_iniciativas, iniciativa_original)

    def test_contexto_restaurado_apos_excecao(self):
        rng = random.Random(1)
        with aleatorio.usar(rng):
            self.assertIs(motor._rng(None), rng)
            with self.assertRaises(RuntimeError):
                with aleatorio.usar(random.Random(9)):
                    raise RuntimeError("fim")
            self.assertIs(motor._rng(None), rng)
        self.assertIsInstance(motor._rng(None), random.SystemRandom)

    def test_pular_coleta_preserva_vitorias_e_rodadas(self):
        args = SimpleNamespace(classe="xama", nivel=9, repeticoes=3)
        monstros = [Monstro("Alvo", 16, 7, "2d8", 140)]
        completo = simular(monstros, 3, args, random.Random(123))
        args.coletar_detalhes = False
        rapido = simular(monstros, 3, args, random.Random(123))
        for chave, valor in rapido.items():
            self.assertEqual(valor, completo[chave])
        self.assertNotIn("dano", rapido)

    def test_intervalos_e_entradas_invalidas(self):
        self.assertEqual(intervalo(0, 100)[0], 0)
        self.assertGreater(intervalo(0, 100)[1], 0)
        self.assertLess(intervalo(100, 100)[0], 1)
        with self.assertRaises(ValueError):
            Ficha("druida", 1, {"forma_t1": "dragao"})
        with self.assertRaises(ValueError):
            Ficha("guerreiro", 11)

    def test_cli_exporta_e_filtrar_classes_nao_muda_os_confrontos(self):
        with tempfile.TemporaryDirectory() as pasta:
            pasta = Path(pasta)
            cenario = pasta/"cenarios.json"
            cenario.write_text(json.dumps({"1": [{"id": "C", "monstros": [
                {"nome": "Alvo", "ca": 12, "ataque": 3, "dano": "1d6", "hp": 40}
            ]}]}))
            comum = [sys.executable, str(RAIZ/"tools/simular_balanceamento.py"), "--comparar",
                     "--tier", "1", "--grupos", "3", "--base", "clerigo,mago",
                     "--simulacoes", "3", "--seed", "7", "--cenarios", str(cenario)]
            subprocess.run([*comum, "--classes", "guerreiro", "xama", "--relatorio", str(pasta/"a")],
                           check=True, capture_output=True, timeout=30)
            subprocess.run([*comum, "--classe", "guerreiro", "--relatorio", str(pasta/"b")],
                           check=True, capture_output=True, timeout=30)
            def linhas(nome):
                with (pasta/nome/"por_cenario.csv").open(encoding="utf-8-sig") as f:
                    return list(csv.DictReader(f))
            self.assertEqual([r for r in linhas("a") if r["classe"] == "guerreiro"], linhas("b"))
            self.assertTrue((pasta/"a/experimento.json").exists())
            self.assertTrue((pasta/"a/relatorio.md").exists())


if __name__ == "__main__":
    unittest.main()
