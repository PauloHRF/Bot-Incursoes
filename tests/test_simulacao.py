"""Cobertura do backend compartilhado, isolamento e comparacoes controladas."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import csv
import inspect
import json
from pathlib import Path
import random
import statistics
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
from tools.simulacao import grupos
from tools.simulacao.execucao import Bancada, Ficha, simular_async
from tools.simulacao.memoria import Memoria
from tools.simulacao.comparacao import carregar_builds, carregar_cenarios, comparar
from tools.simulacao import medidas, medidor
from tools.simulacao import estatisticas
from tools.simulacao.estatisticas import intervalo
from tools.simular_combate import simular

ALVO = Monstro("Alvo", 1, 0, "1d1", 1000)


class FichasEmMemoria(unittest.IsolatedAsyncioTestCase):
    async def test_cache_nao_altera_lutas_nem_o_rng(self):
        """Mesma execução com/sem cache, incluindo métricas e estado final."""
        for nivel in (2, 6, 10):
            for nome in classes.CLASSES:
                with self.subTest(classe=nome, nivel=nivel):
                    mesa = [Ficha(nome, nivel), Ficha("guerreiro", nivel)]
                    monstros = [Monstro("Teste", 14, 7, "2d8+3", 180)]
                    parametros = dict(limite=6, estados=True)
                    quente = await simular_async(monstros, mesa, 1, random.Random(81), **parametros)
                    with patch("tools.simulacao.execucao.Memoria", side_effect=lambda: Memoria(cache_fichas=False)):
                        frio = await simular_async(monstros, mesa, 1, random.Random(81), **parametros)
                    self.assertEqual(quente, frio)

    async def test_ficha_em_cache_segue_hp_escolhas_e_equipamento(self):
        async with Bancada([Ficha("guerreiro", 6)], [ALVO]) as b:
            await b.iniciar()
            antes = (await db.personagens_da_run(b.conn, b.run_id))[0]
            await db.definir_thp(b.conn, b.run_id, 1, 7)
            await b.conn.execute("UPDATE run_participantes SET hp_atual = 3 WHERE run_id = ?", (b.run_id,))
            atual = (await db.personagens_da_run(b.conn, b.run_id))[0]
            self.assertEqual(atual["hp_atual"], 3)
            self.assertEqual(atual["thp"], 7)
            self.assertEqual(atual["efeitos"], antes["efeitos"])
            entradas = len(b.conn._cache_fichas)
            await db.definir_thp(b.conn, b.run_id, 1, 8)
            await db.personagens_da_run(b.conn, b.run_id)
            self.assertEqual(len(b.conn._cache_fichas), entradas)
            await db.definir_escolha(b.conn, b.ids[0], "fighting_style", "defensivo")
            defensivo = (await db.personagens_da_run(b.conn, b.run_id))[0]
            self.assertEqual(defensivo["ca"], antes["ca"] + 1)
            await b.conn.execute("UPDATE personagens SET nivel = 10 WHERE id = ?", (b.ids[0],))
            await b.conn.commit()
            depois = (await db.personagens_da_run(b.conn, b.run_id))[0]
            async with b.conn.execute("SELECT * FROM personagens WHERE id = ?", (b.ids[0],)) as cur:
                row = await cur.fetchone()
            esperado = db._desserializar(row)
            self.assertEqual(depois["hp_atual"], 3)
            self.assertEqual(depois["thp"], 8)
            self.assertEqual(depois["hp_max"], esperado["hp_max"])
            self.assertNotEqual(depois["hp_max"], antes["hp_max"])
            self.assertEqual(depois["efeitos"], esperado["efeitos"])
            # Alterar o dicionário recebido não altera leituras seguintes.
            depois["efeitos"]["bonus_save_atributo"]["CON"] = 999
            depois["saves"]["CON"] = 999
            depois["pericias"].append("Inventada")
            outra = (await db.personagens_da_run(b.conn, b.run_id))[0]
            self.assertEqual(outra["efeitos"], esperado["efeitos"])
            self.assertEqual(outra["saves"], esperado["saves"])
            self.assertNotIn("Inventada", outra["pericias"])
            # O equipamento também faz parte da chave, sem invalidar por HP.
            com_item = db._ler_ficha(b.conn, row, ("manto_estrelado",))
            self.assertEqual(com_item, db._desserializar(row, ("manto_estrelado",)))
            self.assertEqual(com_item["saves"], {k: v + 2 for k, v in esperado["saves"].items()})
            self.assertEqual(db._ler_ficha(b.conn, row)["saves"], esperado["saves"])


def _grupo_age_primeiro(estado, rng=None):
    """A iniciativa sem sorteio: o grupo inteiro, e depois as criaturas.

    Para o caso que confere o que o combate deu ANTES de alguém agir. O ALVO
    não tem como errar sempre nem como bater zero — o dano mínimo é 1 e o 20
    natural acerta qualquer CA —, então, ganhando a iniciativa, ele tirava 1 ou
    2 de THP do mago antes da conferência em cerca de 3% das rodadas da suíte.
    """
    quem = [(motor.PERSONAGEM, c.user_id, c.nome) for c in estado.combatentes]
    quem += [(motor.INIMIGO, i.indice, i.nome) for i in estado.inimigos]
    return [
        motor.Iniciativa(tipo, ident, nome, len(quem) - posicao, 0)
        for posicao, (tipo, ident, nome) in enumerate(quem)
    ]


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
            # O mago age primeiro: a fila para nele, e o ALVO nao chega a bater
            # antes de o THP da abertura ser conferido.
            with patch.object(motor, "rolar_iniciativas", _grupo_age_primeiro):
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


class Mesas(unittest.TestCase):
    """Quem senta na mesa quando uma sala é medida.

    A medida era contra cinco cópias da mesma classe — uma mesa que nunca vai
    existir. Pior: o número dependia de QUAL classe, então quem escolhia a
    classe escolhia a resposta sem saber. Agora a sala enfrenta várias mesas
    fixas, e o que volta é a média com os extremos ao lado.
    """

    def test_sem_classe_nenhuma_mesa_e_cinco_copias_da_mesma(self):
        args = SimpleNamespace(nivel=8, repeticoes=240, coletar_detalhes=False)
        r = simular([Monstro("Alvo", 15, 6, "2d6", 52)], 5, args, random.Random(5))
        mesas = r["composicoes"]
        self.assertEqual(len(mesas), grupos.COMPOSICOES_PADRAO)
        iguais = [m["classes"] for m in mesas if len(set(m["classes"])) == 1]
        self.assertEqual(iguais, [], f"voltou a mesa de uma classe só: {iguais}")
        self.assertGreater(len({tuple(m["classes"]) for m in mesas}), 1)
        # As lutas de todas as mesas somam a amostra, e a média sai delas.
        self.assertEqual(sum(m["amostras"] for m in mesas), r["amostras"])

    def test_a_composicao_muda_o_resultado_e_a_media_esconde(self):
        """A razão de os extremos virem junto com a média.

        Mesas diferentes passam por aperto diferente na MESMA sala. Uma média
        de 70% pode ser "todo mundo em 70%" ou "metade em 95% e metade em
        45%", e são salas diferentes para quem joga. Sem a pior mesa na tela,
        as duas se parecem.
        """
        args = SimpleNamespace(nivel=4, repeticoes=240, coletar_detalhes=False)
        r = simular([Monstro("Alvo", 16, 8, "3d8+4", 120)], 3, args, random.Random(3))
        taxas = [m["taxa"] for m in r["composicoes"]]
        # As formações de referência têm desempenhos diferentes no encontro.
        self.assertGreater(max(taxas) - min(taxas), 0.10, taxas)
        self.assertLessEqual(min(taxas), r["taxa"])
        self.assertGreaterEqual(max(taxas), r["taxa"])

    def test_as_formacoes_nao_mudam_com_a_semente(self):
        """A semente controla as rolagens, mantendo as classes e suas funções."""
        args = SimpleNamespace(nivel=8, repeticoes=90, coletar_detalhes=False)
        monstros = [Monstro("Alvo", 14, 5, "1d8", 40)]
        a = simular(monstros, 4, args, random.Random(21))
        b = simular(monstros, 4, args, random.Random(21))
        self.assertEqual(a["composicoes"], b["composicoes"])
        outra = simular(monstros, 4, args, random.Random(22))
        self.assertEqual(
            [m["classes"] for m in a["composicoes"]],
            [m["classes"] for m in outra["composicoes"]],
        )

    def test_com_classe_volta_ao_grupo_uniforme_para_diagnostico(self):
        """"Esta sala é dura PARA QUEM?" continua sendo uma pergunta válida."""
        args = SimpleNamespace(classe="mago", nivel=8, repeticoes=20, coletar_detalhes=False)
        r = simular([Monstro("Alvo", 14, 5, "1d8", 40)], 4, args, random.Random(5))
        self.assertEqual(r["composicoes"], [{"classes": ["mago"] * 4,
                                             "taxa": r["taxa"], "amostras": 20}])

    def test_a_pior_formacao_e_um_numero_que_alguem_tirou(self):
        """E nao uma extrapolacao abaixo de todas elas.

        Isto era o decimo percentil, de quando as mesas eram SORTEADAS: ali o
        minimo nao servia, porque estimava o pior da populacao e afundava
        conforme a amostra crescia. Com o catalogo de formacoes FIXO nao ha
        amostragem, e o percentil passou a mentir — `statistics.quantiles` e
        *exclusive* e extrapola para fora dos dados quando o decil pedido fica
        abaixo de `1/(n+1)`. Com QUATRO formacoes, 0,1 < 0,2.

        O caso usa quatro, que e o tamanho que a ferramenta de fato mede. Os
        antigos usavam doze e oitenta, justamente os tamanhos onde a
        extrapolacao nao morde — e foi por isso que a suite ficou verde com
        taxa de vitoria NEGATIVA na tela.
        """
        def azarada(*taxas):
            return estatisticas.mesa_azarada([{"taxa": t} for t in taxas])

        # Sempre uma das formacoes, nunca abaixo de todas.
        for taxas in ((1.0, 0.9, 0.8, 0.6), (0.95, 0.95, 0.95, 0.40),
                      (1.0, 1.0, 1.0, 0.30), (0.9, 0.85, 0.8, 0.75)):
            valor = azarada(*taxas)
            self.assertIn(valor, taxas, taxas)
            self.assertEqual(valor, min(taxas), taxas)

        # E o caso que o percentil estragava: tres vitorias limpas e uma
        # derrota limpa davam -50%.
        self.assertEqual(azarada(1.0, 1.0, 1.0, 0.0), 0.0)
        for taxas in ((1.0, 1.0, 1.0, 0.0), (1.0, 0.99, 0.98, 0.10)):
            self.assertGreaterEqual(azarada(*taxas), 0.0, taxas)

        # Uma formacao so: ela mesma. Nenhuma: nada a reprovar.
        self.assertEqual(azarada(0.42), 0.42)
        self.assertEqual(estatisticas.mesa_azarada([]), 1.0)

    def test_amostra_pequena_mede_menos_mesas_e_nao_mesas_piores(self):
        """Doze mesas de oito lutas não medem composição nenhuma.

        Uma taxa vinda de oito combates é ruído com três dígitos; dizer "esta
        mesa venceu 38%" a partir dela é inventar. Então a amostra curta corta
        o número de mesas, nunca o número de lutas por mesa.
        """
        mesas, por = grupos.dividir(100, 12)
        self.assertGreaterEqual(por, grupos.MINIMO_POR_COMPOSICAO)
        self.assertLessEqual(mesas * por, 100)
        # Com folga sobrando, cabe o catalogo inteiro e as lutas se dividem
        # entre as formacoes que existem. O numero nao fica escrito aqui: ele
        # muda quando uma formacao entra ou sai do catalogo.
        self.assertEqual(
            grupos.dividir(1200, 12),
            (grupos.COMPOSICOES_PADRAO, 1200 // grupos.COMPOSICOES_PADRAO),
        )
        with self.assertRaises(ValueError):
            grupos.dividir(0, 12)

    def test_formacoes_tem_funcoes_e_escolhas_validas_em_todos_os_niveis(self):
        for tamanho in range(2, 7):
            for nivel in range(1, 11):
                for mesa in grupos.fixas(tamanho, nivel):
                    with self.subTest(tamanho=tamanho, nivel=nivel, classes=grupos.nomes_da_mesa(mesa)):
                        self.assertEqual(len({f.classe for f in mesa}), tamanho)
                        self.assertIn(mesa[0].classe, grupos.FRENTE)
                        self.assertIn(mesa[1].classe, grupos.CURA)
                        if mesa[0].classe == "druida":
                            self.assertEqual(mesa[0].escolhas["forma_t1"], "urso")
                        if nivel >= 5 and mesa[1].classe == "clerigo":
                            self.assertEqual(mesa[1].escolhas["magia_t3"], "mass_healing_word")
        self.assertEqual({f.classe for m in grupos.fixas(5, 10) for f in m}, set(classes.CLASSES))

    def test_o_catalogo_recusa_formacao_com_as_vagas_trocadas(self):
        """A frente na primeira vaga e a cura na segunda: o catalogo confere.

        Com quatro formacoes a ordem dava para olhar a olho; com sete, nao. E
        uma formacao sem frente ou sem cura nao mede a sala: mede o acidente.
        O erro tem de dizer QUAL formacao, porque o json nao diz qual vaga e
        qual - a ordem das classes e que diz.
        """
        bom = json.loads(grupos.ARQUIVO.read_text(encoding="utf-8"))
        for vaga, errada in ((0, "mago"), (1, "ladino")):
            torto = json.loads(json.dumps(bom))
            alvo = torto["grupos"][1]
            self.assertNotIn(errada, alvo["classes"])  # senao cai na repetida
            alvo["classes"][vaga] = errada
            with tempfile.TemporaryDirectory() as pasta:
                arquivo = Path(pasta) / "grupos.json"
                arquivo.write_text(json.dumps(torto), encoding="utf-8")
                grupos.catalogo.cache_clear()
                try:
                    with patch.object(grupos, "ARQUIVO", arquivo):
                        with self.assertRaises(ValueError) as erro:
                            grupos.catalogo()
                finally:
                    grupos.catalogo.cache_clear()
            self.assertIn(alvo["id"], str(erro.exception))
            self.assertIn(errada, str(erro.exception))

    def test_pedir_mais_formacoes_nao_repete_os_mesmos_grupos(self):
        mesas, por = grupos.dividir(400, 40, grupos.MINIMO_PARA_A_MEDIA)
        self.assertEqual(mesas, grupos.COMPOSICOES_PADRAO)
        # Pedir quarenta formacoes nao inventa formacao: o teto e o catalogo,
        # e as lutas se dividem igualmente entre o que existe. O resto da
        # divisao fica de fora em vez de engordar uma mesa.
        self.assertEqual(por, 400 // grupos.COMPOSICOES_PADRAO)
        self.assertLessEqual(mesas * por, 400)
        self.assertGreater(mesas * por, 400 - grupos.COMPOSICOES_PADRAO)
        self.assertEqual(len(grupos.fixas(5, 8, 40)), mesas)

    def test_cada_formacao_tem_rolagens_independentes_das_outras(self):
        from tools import simular_combate as sc
        original = sc.executar
        vistos = {}

        def executar(monstros, mesa, repeticoes, rng, **kw):
            vistos[tuple(f.classe for f in mesa)] = rng.getstate()
            return original(monstros, mesa, repeticoes, rng, **kw)

        args = SimpleNamespace(nivel=4, repeticoes=60, coletar_detalhes=False)
        with patch.object(sc, "executar", side_effect=executar):
            sc.simular([Monstro("Frágil", 1, 0, "1", 1)], 3, args, random.Random(8))
            quatro = dict(vistos); vistos.clear()
            args.composicoes = 2
            sc.simular([Monstro("Frágil", 1, 0, "1", 1)], 3, args, random.Random(8))
        self.assertEqual(len(vistos), 2)
        self.assertEqual(vistos, {k: quatro[k] for k in vistos})


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


class Medidas(unittest.TestCase):
    """Onde as medicoes ficam guardadas, para os documentos citarem."""

    def test_medicao_gravada_traz_data_e_codigo(self):
        """Numero medido que chega ao documento por copia nao tem validade.

        Aconteceu: o BALANCO.md ganhou `media, p90 = 5, 10` digitados a mao,
        dentro de um documento que e gerado justamente para nao ter numero
        copiado. Quem mede grava, com a data e o hash do codigo; quem gera
        documento le, e diz "nao medido" quando nao ha medicao.
        """
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "medidas.json"
            with patch.object(medidas, "ARQUIVO", arquivo):
                self.assertEqual(medidas.ler(), {})
                self.assertIsNone(medidas.de("nao_medido"))
                registro = medidas.gravar("teste", {"p90": 0.17})
                self.assertEqual(registro["p90"], 0.17)
                self.assertEqual(len(registro["sha256_modelo"]), 64)
                self.assertIn("-", registro["quando"])
                self.assertEqual(medidas.de("teste")["p90"], 0.17)
                # Medicao de outro codigo nao e "errada": e "ninguem conferiu
                # que ela continua valendo", e o minimo e dizer isso.
                self.assertFalse(medidas.esta_velha(medidas.de("teste")))
                self.assertTrue(
                    medidas.esta_velha({"sha256_modelo": "de outro codigo"})
                )
                # Arquivo corrompido nao derruba quem gera documento.
                arquivo.write_text("{isto nao e json", encoding="utf-8")
                self.assertEqual(medidas.ler(), {})


class Medidor(unittest.TestCase):
    """A semente de uma medicao, montada num lugar so."""

    def test_catalogo_de_formacoes_faz_parte_da_identidade_da_medicao(self):
        antes = medidor.hash_do_modelo()
        original = Path.read_bytes
        with patch.object(Path, "read_bytes", lambda p: original(p) + b"\n" if p == grupos.ARQUIVO else original(p)):
            self.assertNotEqual(medidor.hash_do_modelo(), antes)

    def test_o_bando_nunca_entra_na_semente(self):
        """E o que faz a diferenca entre dois numeros ser a diferenca entre
        dois bandos.

        Dois comandos montavam a semente errado, e os dois tinham a regra
        escrita por perto: o sugeridor punha o bando, e o `--varrer` do
        calibrador punha a quantidade. A regra nao cabe num comentario — cabe
        numa funcao, e e esta.
        """
        self.assertEqual(
            medidor.semente_de(7, 3, 5).random(),
            medidor.semente_de(7, 3, 5).random(),
        )
        # O tier e o tamanho separam, porque sao perguntas diferentes.
        self.assertNotEqual(
            medidor.semente_de(7, 3, 5).random(),
            medidor.semente_de(7, 3, 3).random(),
        )
        self.assertNotEqual(
            medidor.semente_de(7, 3, 5).random(),
            medidor.semente_de(7, 4, 5).random(),
        )
        # E a assinatura nao tem por onde o bando entrar.
        parametros = set(inspect.signature(medidor.semente_de).parameters)
        self.assertEqual(parametros, {"semente", "tier", "tamanho"})

    def test_bando_de_recusa_nome_fora_do_bestiario(self):
        """Medir um bando menor que o pedido devolveria um numero que nao e
        resposta da pergunta que foi feita."""
        bando = medidor.bando_de([("Mímico", 2)])
        self.assertEqual(len(bando), 2)
        with self.assertRaises(ValueError):
            medidor.bando_de([("Criatura Que Nao Existe", 1)])

    def test_o_hash_do_modelo_muda_com_o_codigo(self):
        """A identidade do codigo que mediu: numero sem ela e afirmacao sem data."""
        igual = medidor.hash_do_modelo()
        self.assertEqual(igual, medidor.hash_do_modelo())
        self.assertEqual(len(igual), 64)


if __name__ == "__main__":
    unittest.main()
