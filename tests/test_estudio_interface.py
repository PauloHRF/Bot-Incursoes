"""Regressões do Estúdio no navegador (dependência opcional).

    pip install -r requirements-estudio.txt
    python -m playwright install chromium
    python tests/test_estudio_interface.py

Usa o servidor e o conteúdo reais; só a simulação recebe respostas
controladas, porque uma luta de verdade leva meio minuto. Não exige iniciar o
estúdio separadamente.

O que estes casos protegem, e que não é óbvio: o Estúdio escreve UMA coisa, a
dungeon, em cinco etapas, e o que sai dele é o arquivo que o bot vai receber.
Por isso o caso principal não para no clique de baixar: ele confere o arquivo
baixado com a mesma régua do bot (`src/pacotes.py`). Uma página que baixa um
arquivo que o bot recusa é a falha que o autor só descobriria no envio.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import threading
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tools"))
import estudio as E  # noqa: E402
from src import incursoes as I, pacotes  # noqa: E402

try:
    from playwright.sync_api import expect, sync_playwright
except ImportError:
    sync_playwright = None

# Uma medida com a forma da de verdade, para a simulação não levar meio minuto.
MEDIDA = {
    "sala": "OBJ", "tema": None, "tier": 3, "classe": "predefinido", "sorteado": False,
    "predefinido": True, "nivel": 6, "repeticoes": 240, "semente": 9,
    "criaturas": [{"nome": "Behir", "ca": 17, "hp": 168}],
    "medidas": [{
        "grupo": 5, "taxa": .7, "rodadas": 4.2, "caidos": 1.1, "lutas": 238, "mesas": 7,
        "composicoes": [{"classes": ["bardo", "mago"], "taxa": .4, "amostras": 34},
                        {"classes": ["guerreiro", "clerigo"], "taxa": .9, "amostras": 34}],
        "pior": {"classes": ["bardo", "mago"], "taxa": .4, "amostras": 34},
        "melhor": {"classes": ["guerreiro", "clerigo"], "taxa": .9, "amostras": 34},
        "azarada": .4, "dificuldade": "media", "rotulo": "Média", "dizima": True,
    }],
}


@unittest.skipUnless(sync_playwright, "instale playwright para testar a interface")
class Interface(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servidor = E.ThreadingHTTPServer(("127.0.0.1", 0), E.Bancada)
        cls.tarefa = threading.Thread(target=cls.servidor.serve_forever, daemon=True)
        cls.tarefa.start()
        cls.url = f"http://127.0.0.1:{cls.servidor.server_port}"
        cls.pw = sync_playwright().start()
        caminho = os.environ.get("ESTUDIO_CHROMIUM") or shutil.which("chromium")
        try:
            cls.browser = cls.pw.chromium.launch(
                **({"executable_path": caminho} if caminho else {}),
            )
        except Exception:
            cls.pw.stop()
            cls.servidor.shutdown()
            cls.servidor.server_close()
            cls.tarefa.join()
            raise
        cls.conteudo = E.conteudo()
        cls.bancos, _ = I.carregar_bancos_tolerante(E.PASTA_BANCOS)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.servidor.shutdown()
        cls.servidor.server_close()
        cls.tarefa.join()

    def setUp(self):
        self.context = self.browser.new_context(viewport={"width": 1366, "height": 900})
        self.page = self.context.new_page()
        self.erros = []
        self.page.on("pageerror", lambda e: self.erros.append(str(e)))
        self.page.on("dialog", lambda d: d.accept())
        self.page.goto(self.url)
        expect(self.page.locator("#listaProntas .cartao").first).to_be_visible()

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.erros, [])

    # ------------------------------------------------------------ apoio

    def escrever(self, campo, valor):
        self.page.locator(campo).fill(valor)

    def etapa(self, nome):
        self.page.locator(f'.passos [data-etapa="{nome}"]').click()
        expect(self.page.locator(f"#etapa{nome}")).to_be_visible()

    def incursao(self):
        """A dungeon aberta, como o estúdio a tem na memória."""
        return self.page.evaluate("JSON.parse(JSON.stringify(inc() || null))")

    def nova_dungeon(self, nome="A Cripta de Teste", tier="3", org="Vórtice Oculto"):
        self.page.locator("#btNova").click()
        expect(self.page.locator("#dNome")).to_be_focused()
        self.escrever("#dNome", nome)
        if org:
            self.page.select_option("#dOrg", org)
        if tier:
            self.page.select_option("#dTier", tier)
        self.escrever("#dLore", "O primeiro parágrafo.\n\nO segundo, que o anúncio não mostra.")

    def chefe_com(self, criatura="Behir", quantas=None):
        self.etapa("Chefe")
        self.escrever("#cSala", "A Sala Final")
        self.escrever("#cDesc", "O chefe espera.")
        self.page.locator("#btCriatura").click()
        self.page.locator("#linhasChefe input[type=text]").last.fill(criatura)
        if quantas:
            self.page.locator("#linhasChefe input[type=number]").last.fill(str(quantas))

    def baixar(self):
        with self.page.expect_download() as evento:
            self.page.locator("#btBaixar").click()
        return evento.value.suggested_filename, json.loads(
            Path(evento.value.path()).read_text(encoding="utf-8"))

    def conferir_como_o_bot(self, dados):
        return pacotes.conferir(dados, self.bancos, ocupadas=set(self.conteudo["incursoes"]))

    # ------------------------------------------------------------ casos

    def test_dungeon_nova_atravessa_as_etapas_e_baixa_o_que_o_bot_aceita(self):
        self.nova_dungeon()
        # O código sai do nome, sem acento, e a prévia mostra o que o bot mostra.
        expect(self.page.locator("#dCodigo")).to_contain_text("a_cripta_de_teste")
        expect(self.page.locator("#previaDungeon h3")).to_have_text("🗺️ A Cripta de Teste (T3)")
        expect(self.page.locator("#previaDungeon")).to_contain_text("O primeiro parágrafo.")
        expect(self.page.locator("#previaDungeon")).not_to_contain_text("O segundo")
        self.page.locator('[data-previa="abertura"]').click()
        expect(self.page.locator("#previaDungeon")).to_contain_text("O segundo")

        self.chefe_com("Behir")
        self.etapa("Revisar")
        expect(self.page.locator("#saidaRevisar")).to_contain_text("Pronta para enviar")
        expect(self.page.locator("#mudancas")).to_contain_text("Dungeon nova")

        nome, dados = self.baixar()
        self.assertEqual(nome, "a_cripta_de_teste.json")
        self.assertEqual(dados["formato"], pacotes.FORMATO)
        self.assertEqual(dados["organizacao"], "Vórtice Oculto")
        self.assertEqual(dados["incursao"]["objetivo"]["monstros"], [{"nome": "Behir"}])
        self.assertNotIn("lore_final", dados["incursao"], "campo vazio foi no arquivo")
        r = self.conferir_como_o_bot(dados)
        self.assertTrue(r.aprovado, r.problemas)

        # Depois do download o código fica: renomear não vira dungeon nova.
        self.etapa("Dungeon")
        self.escrever("#dNome", "Outro Nome")
        self.assertEqual(self.incursao()["id"], "a_cripta_de_teste")
        expect(self.page.locator("#dCodigo")).to_contain_text("fixo")

    def test_o_que_falta_aparece_com_as_palavras_do_bot(self):
        self.nova_dungeon(tier="")
        self.etapa("Chefe")
        expect(self.page.locator("#motivoSimular")).to_contain_text("Escolha o tier")
        expect(self.page.locator("#btSimular")).to_be_disabled()
        self.etapa("Revisar")
        expect(self.page.locator("#saidaRevisar")).to_contain_text("o bot recusa")
        expect(self.page.locator("#saidaRevisar")).to_contain_text("tier")
        # A sala final é "a sala do chefe", e não o nome do campo no arquivo.
        expect(self.page.locator("#saidaRevisar")).to_contain_text("sala do chefe")
        expect(self.page.locator("#saidaRevisar")).not_to_contain_text("objetivo (sala")
        expect(self.page.locator("#btBaixar")).to_have_text("↓ Baixar mesmo assim")

    def test_partir_de_uma_pronta_abre_uma_copia_com_codigo_proprio(self):
        original = self.page.locator("#listaProntas .cartao-nome").first.inner_text()
        self.page.locator("#listaProntas .cartao-abrir").first.click()
        expect(self.page.locator("#dNome")).to_have_value(f"{original} (cópia)")
        copia = self.incursao()
        self.assertNotIn(copia["id"], self.conteudo["incursoes"], "a cópia tomou o código de outra")
        self.escrever("#dRecompensa", "99")
        self.etapa("Revisar")
        expect(self.page.locator("#baseMudou")).to_contain_text(original)
        expect(self.page.locator("#mudancas")).to_contain_text("Recompensa (MEs)")
        expect(self.page.locator("#mudancas")).to_contain_text("→ 99")
        expect(self.page.locator("#saidaRevisar")).to_contain_text("Pronta para enviar")

    def test_criatura_com_ficha_propria_vira_a_do_livro_ao_trocar_o_nome(self):
        """A troca de nome não pode deixar a ficha da criatura anterior.

        O chefe de uma dungeon pronta pode vir com os números escritos. Se o
        autor troca o nome para um do bestiário e a ficha fica, o Behir sai
        com os números do bicho de antes — e nada na tela mostra isso.
        """
        com_ficha = next(i for i, d in self.conteudo["incursoes"].items()
                         if any(len(m) > 2 for m in d["objetivo"].get("monstros", [])))
        self.page.evaluate("id => partirDe(id)", com_ficha)
        self.etapa("Chefe")
        expect(self.page.locator(".ficha-propria").first).to_be_visible()
        antes = len(self.incursao()["objetivo"]["monstros"])
        campo = self.page.locator("#linhasChefe input[type=text]").first
        campo.fill("Behir")
        expect(campo).to_be_focused()
        primeira = self.incursao()["objetivo"]["monstros"][0]
        self.assertEqual(set(primeira) - {"quantidade"}, {"nome"}, primeira)
        self.assertEqual(primeira["nome"], "Behir")
        self.assertEqual(len(self.incursao()["objetivo"]["monstros"]), antes)

    def test_simular_usa_o_tier_da_dungeon_e_avisa_resultado_velho(self):
        pedidos = []

        def responder(rota):
            pedidos.append(rota.request.post_data_json)
            rota.fulfill(json=MEDIDA)

        self.page.route("**/api/simular", responder)
        self.nova_dungeon(tier="3")
        self.chefe_com("Behir")
        self.page.locator("#btSimular").click()
        expect(self.page.locator("#resultado")).to_contain_text("70%")
        expect(self.page.locator("#resultado .veredito")).to_have_text("Média")
        # A pior formação aparece, e a média não esconde a mesa que sofre.
        expect(self.page.locator("#resultado")).to_contain_text("vence só 40%")
        self.assertEqual(pedidos[0]["tier"], 3)
        self.assertNotIn("nivel", pedidos[0], "o nível é do tier, não um campo")
        self.assertEqual(pedidos[0]["grupos"], [5])

        # Mudar SÓ o tier desatualiza: o chefe é lutado no tier da dungeon.
        expect(self.page.locator("#medidaVelha")).to_be_hidden()
        self.etapa("Revisar")
        expect(self.page.locator("#resumo")).to_contain_text("70% de vitórias")
        self.etapa("Dungeon")
        self.page.select_option("#dTier", "4")
        self.etapa("Revisar")
        expect(self.page.locator("#resumo")).to_contain_text("desatualizada")
        self.etapa("Chefe")
        expect(self.page.locator("#medidaVelha")).to_be_visible()

        # E mudar SÓ o bando também.
        self.page.locator("#btSimular").click()
        expect(self.page.locator("#medidaVelha")).to_be_hidden()
        self.assertEqual(pedidos[-1]["tier"], 4)
        self.page.locator("#linhasChefe input[type=number]").first.fill("2")
        expect(self.page.locator("#medidaVelha")).to_be_visible()

    def test_sem_o_motor_o_chefe_diz_antes_do_clique(self):
        recado = "Medir e sugerir precisam de 'aiosqlite'"

        def responder(rota):
            dados = rota.fetch().json()
            dados["falta_para_simular"] = recado
            rota.fulfill(json=dados)

        self.page.route("**/api/conteudo", responder)
        self.page.reload()
        self.nova_dungeon()
        self.chefe_com("Behir")
        expect(self.page.locator("#motivoSimular")).to_contain_text(recado)
        expect(self.page.locator("#btSimular")).to_be_disabled()
        # O resto não depende do motor: a dungeon ainda se baixa.
        self.etapa("Revisar")
        _, dados = self.baixar()
        self.assertTrue(self.conferir_como_o_bot(dados).aprovado)

    def test_rascunho_sobrevive_e_arquivo_baixado_reabre(self):
        self.nova_dungeon(nome="Volta Depois")
        self.chefe_com("Behir")
        self.page.reload()
        expect(self.page.locator("#listaRascunhos")).to_contain_text("Volta Depois")
        self.page.locator("#listaRascunhos .cartao-abrir").first.click()
        expect(self.page.locator("#dNome")).to_have_value("Volta Depois")
        self.etapa("Revisar")
        _, dados = self.baixar()

        # Abrir o arquivo baixado continua de onde parou, com o código fixo.
        self.etapa("Escolher")
        self.page.locator("#fArquivo").set_input_files({
            "name": "volta_depois.json", "mimeType": "application/json",
            "buffer": json.dumps(dados).encode()})
        expect(self.page.locator("#dNome")).to_have_value("Volta Depois")
        self.escrever("#dNome", "Volta Depois, Renomeada")
        self.assertEqual(self.incursao()["id"], "volta_depois")
        # O rascunho do mesmo código foi trocado, e não duplicado.
        self.etapa("Escolher")
        expect(self.page.locator("#listaRascunhos .cartao")).to_have_count(1)

        # Um arquivo de incursão comum abre como cópia, com código próprio.
        existente = next(iter(self.conteudo["incursoes"].values()))
        self.page.locator("#fArquivo").set_input_files({
            "name": "comum.json", "mimeType": "application/json",
            "buffer": json.dumps(existente).encode()})
        expect(self.page.locator("#dNome")).to_have_value(existente["nome"])
        self.assertNotEqual(self.incursao()["id"], existente["id"])

    def test_apagar_rascunho(self):
        self.nova_dungeon(nome="Para Apagar")
        self.etapa("Escolher")
        expect(self.page.locator("#listaRascunhos .cartao")).to_have_count(1)
        self.page.locator("#listaRascunhos .botao.perigo").click()
        expect(self.page.locator("#listaRascunhos .cartao")).to_have_count(0)
        expect(self.page.locator("#semRascunhos")).to_be_visible()
        expect(self.page.locator('.passos [data-etapa="Dungeon"]')).to_be_disabled()

    def test_sem_armazenamento_local_ainda_e_possivel_baixar(self):
        self.page.add_init_script("Storage.prototype.setItem = () => { throw new Error('indisponível'); };")
        self.page.reload()
        expect(self.page.locator("#estado")).to_have_text("Baixe o arquivo para não perder o trabalho")
        self.nova_dungeon()
        self.chefe_com("Behir")
        self.etapa("Revisar")
        _, dados = self.baixar()
        self.assertEqual(dados["incursao"]["nome"], "A Cripta de Teste")

    # ------------------------------------------------------ o caminho

    def test_caminho_escolhe_temas_tira_salas_e_mostra_o_bando_do_tier(self):
        self.nova_dungeon(tier="5")
        self.chefe_com("Behir")
        self.etapa("Caminho")
        expect(self.page.locator("#contaCaminho")).to_contain_text("podem cair")
        # A dungeon de tier 5 do Vórtice luta o bando do tier 4: o caminho diz.
        expect(self.page.locator(".queda").first).to_contain_text("usa o do tier 4")

        self.page.locator('#fichasCaminho [data-valor="agua"]').click()
        expect(self.page.locator("#notaCaminho")).to_contain_text("faltam")
        self.assertEqual(self.incursao()["filtro"], {"temas": ["agua"]})
        self.page.locator('#fichasCaminho [data-valor="agua"]').click()
        expect(self.page.locator("#notaCaminho")).not_to_contain_text("faltam")
        self.assertNotIn("filtro", self.incursao(), "filtro vazio ficou no arquivo")

        primeira = self.page.locator("#tabelaCaminho tr").first
        codigo = primeira.locator("small").inner_text()
        primeira.locator("input[type=checkbox]").uncheck()
        expect(self.page.locator("#tabelaCaminho tr.fora")).to_have_count(1)
        self.assertEqual(self.incursao()["filtro"], {"excluir": [codigo]})

        self.etapa("Revisar")
        expect(self.page.locator("#resumo")).to_contain_text(f"1 tirada(s): {codigo}")
        _, dados = self.baixar()
        self.assertEqual(dados["incursao"]["filtro"], {"excluir": [codigo]})
        self.assertTrue(self.conferir_como_o_bot(dados).aprovado)

    def test_caminho_simula_uma_sala_no_tier_da_dungeon(self):
        pedidos = []

        def responder(rota):
            pedidos.append(rota.request.post_data_json)
            rota.fulfill(json=MEDIDA)

        self.page.route("**/api/simular", responder)
        self.nova_dungeon(tier="4")
        self.etapa("Caminho")
        linha = self.page.locator("#tabelaCaminho tr:has(.simular-caminho)").first
        botao = linha.locator(".simular-caminho")
        codigo = linha.locator("small").inner_text()
        botao.click()
        expect(linha.locator(".medida-curta")).to_contain_text("70%")
        self.assertEqual(pedidos[0]["tier"], 4)
        self.assertEqual(pedidos[0]["sala"]["id"], codigo)

    # ------------------------------------------------- a parte das salas

    def salas(self):
        self.page.locator('.partes [data-parte="Salas"]').click()
        expect(self.page.locator("#parteSalas")).to_be_visible()
        expect(self.page.locator("#parteDungeons")).to_be_hidden()

    def test_parte_de_salas_escreve_sala_nova_e_baixa_o_arquivo_dela(self):
        self.salas()
        self.page.select_option("#sOrg", "Vórtice Oculto")
        self.page.locator("#btNovaSala").click()
        expect(self.page.locator("#sNome")).to_be_focused()
        self.escrever("#sNome", "Cisterna Alagada")
        self.escrever("#sDesc", "A água chega no peito.")
        self.page.locator('#sTemas [data-valor="agua"]').click()
        self.page.select_option("#sTipo", "Combate")
        expect(self.page.locator("#sBlocoTeste")).to_be_hidden()
        # Os tiers que as dungeons do Vórtice usam aparecem marcados.
        usados = self.conteudo["tiers_por_organizacao"]["Vórtice Oculto"]
        expect(self.page.locator(".aba-tier.usado")).to_have_count(len(usados))
        self.page.locator(".aba-tier").nth(3).click()
        self.page.locator("#btCriaturaSala").click()
        self.page.locator("#linhasSala input[type=text]").last.fill("Ogro")
        expect(self.page.locator("#sTiersUsados")).to_contain_text("usa o bando do tier 4")
        expect(self.page.locator("#saidaSalas")).to_contain_text("Prontas para enviar")

        with self.page.expect_download() as evento:
            self.page.locator("#btBaixarSalas").click()
        self.assertEqual(evento.value.suggested_filename, "salas_vortice_oculto.json")
        dados = json.loads(Path(evento.value.path()).read_text(encoding="utf-8"))
        self.assertNotIn("incursao", dados)
        [sala] = dados["salas"]
        self.assertEqual(sala["monstros_por_tier"], {"4": [{"nome": "Ogro"}]})
        self.assertNotIn(sala["id"], {s.id for s in self.bancos["Vórtice Oculto"].salas})
        r = self.conferir_como_o_bot(dados)
        self.assertTrue(r.aprovado, r.problemas)
        self.assertEqual([s.id for s in r.salas], [sala["id"]])

    def test_sala_do_bot_e_so_leitura_e_copiar_cria_uma_nova(self):
        self.salas()
        self.page.select_option("#sOrg", "Guilda dos Mortos")
        self.page.locator("#listaDoBot .sala-item").first.click()
        expect(self.page.locator("#salaDoBot")).to_be_visible()
        expect(self.page.locator("#editorSala")).to_be_hidden()
        original = self.page.locator("#botNome").inner_text()
        self.page.locator("#btCopiarSala").click()
        expect(self.page.locator("#editorSala")).to_be_visible()
        expect(self.page.locator("#sNome")).to_have_value(f"{original} (cópia)")
        nova = self.page.evaluate("JSON.parse(JSON.stringify(salaAtual()))")
        self.assertNotIn(nova["id"], {s["id"] for s in self.conteudo["bancos"]["Guilda dos Mortos"]["original"]["salas"]})
        expect(self.page.locator("#listaNovas .sala-item")).to_have_count(1)

    def test_a_dungeon_conta_com_as_salas_do_autor_e_avisa_a_ordem(self):
        """As salas novas não vão no arquivo da dungeon, e ela depende delas.

        O caminho as conta, marcadas como "suas", e a revisão diz que o
        arquivo de salas tem de ir antes — sem ele, o bot recusa a dungeon.
        """
        novas = [{"id": f"VO-N{n}", "nome": f"Poça {n}", "tipo": "Evento", "descricao": "Água.",
                  "temas": ["agua"], "dificuldade": "Média", "cd": 13, "alvo_progresso": 3,
                  "pericias": ["Atletismo"]} for n in range(1, 4)]
        self.page.evaluate("s => { salasLocais['Vórtice Oculto'] = s; guardar(); }", novas)
        self.nova_dungeon(tier="2")
        self.chefe_com("Behir")
        self.etapa("Caminho")
        self.page.locator('#fichasCaminho [data-valor="agua"]').click()
        expect(self.page.locator(".marca-nova")).to_have_count(3)
        expect(self.page.locator("#notaCaminho")).not_to_contain_text("faltam")
        self.etapa("Revisar")
        expect(self.page.locator("#saidaRevisar")).to_contain_text("ANTES desta dungeon")
        _, dados = self.baixar()
        self.assertEqual(dados["salas"], [], "sala nova foi no arquivo da dungeon")

    def test_cada_arquivo_abre_na_sua_parte(self):
        so_salas = pacotes.novo("Vórtice Oculto", None, [{
            "id": "VO-ABRE", "nome": "Aberta", "tipo": "Evento", "descricao": "x",
            "dificuldade": "Média", "cd": 13, "alvo_progresso": 3, "pericias": ["Atletismo"]}])
        arquivo = {"name": "salas.json", "mimeType": "application/json",
                   "buffer": json.dumps(so_salas).encode()}
        self.page.locator("#fArquivo").set_input_files(arquivo)
        expect(self.page.locator("#toast")).to_contain_text("Abra-o na parte Salas")
        self.salas()
        self.page.locator("#fArquivoSalas").set_input_files(arquivo)
        expect(self.page.locator("#listaNovas")).to_contain_text("Aberta")
        expect(self.page.locator("#sOrg")).to_have_value("Vórtice Oculto")
        # E o arquivo de dungeon não entra pela parte de salas.
        dungeon = pacotes.novo("Vórtice Oculto", next(iter(self.conteudo["incursoes"].values())))
        self.page.locator("#fArquivoSalas").set_input_files({
            "name": "dungeon.json", "mimeType": "application/json",
            "buffer": json.dumps(dungeon).encode()})
        expect(self.page.locator("#toast")).to_contain_text("Abra-o na parte Dungeons")


# O runner lê o código de saída, e `unittest` sai com 0 mesmo pulando tudo:
# sem playwright, as provas da interface não rodavam e `todos.py` dizia "tudo
# verde". Ficou invisível por tempo demais — e, quando enfim rodaram, pegaram
# dois defeitos de primeira. O 3 é o combinado com o runner para "não rodou".
PULADA = 3

if __name__ == "__main__":
    if sync_playwright is None:
        for linha in (
            "SUITE PULADA: falta o playwright, e as provas da interface",
            "nao rodaram. Instale com:",
            "  pip install -r requirements-estudio.txt",
            "  python -m playwright install chromium",
        ):
            print(linha)
        raise SystemExit(PULADA)
    unittest.main(verbosity=2)
