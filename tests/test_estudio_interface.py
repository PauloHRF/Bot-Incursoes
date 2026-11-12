"""Regressões da edição de JSON no navegador (dependência opcional).

    pip install playwright
    python -m playwright install chromium
    python tests/test_estudio_interface.py

Usa o servidor e os bancos reais; só as buscas demoradas de combate recebem
respostas controladas. Não exige iniciar o estúdio separadamente.
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
sys.path.insert(0, str(RAIZ / "tools"))
import estudio as E  # noqa: E402

try:
    from playwright.sync_api import expect, sync_playwright
except ImportError:
    sync_playwright = None


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

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.servidor.shutdown()
        cls.servidor.server_close()
        cls.tarefa.join()

    def setUp(self):
        self.context = self.browser.new_context(viewport={"width": 1440, "height": 1000})
        self.page = self.context.new_page()
        self.erros = []
        self.page.on("pageerror", lambda e: self.erros.append(str(e)))
        self.page.goto(self.url)
        expect(self.page.locator(".sala-btn").first).to_be_visible()
        self.inicial = self.conteudo["bancos"][self.page.locator("#fBanco").input_value()]["original"]

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.erros, [])

    def json(self):
        """A sala aberta, como o estudio a tem na memoria.

        Lida e nao digitada: o formulario e dirigido pelos campos (que e o
        que se quer testar), e o objeto serve para CONFERIR o que eles
        fizeram. Era o textarea de JSON que dava as duas coisas de uma vez.
        """
        return self.page.evaluate("JSON.parse(JSON.stringify(sala() || null))")

    def banco(self):
        return self.page.evaluate("JSON.parse(JSON.stringify(banco || null))")

    def escrever(self, campo, valor):
        """Digita num campo do formulario, como o autor faz."""
        self.page.locator(campo).fill(valor)
        self.page.locator(campo).dispatch_event("input")

    def semear(self, dados):
        """Poe dados na sala aberta sem passar pelo formulario.

        So para montar o cenario de campos que o formulario NAO mostra — a
        prova de que editar o nome nao apaga o resto do arquivo precisa que
        exista um resto. O que se testa depois disso continua sendo a UI.
        """
        self.page.evaluate(
            "d => { Object.assign(sala(), d); mostrarEditor(); alterado(); }", dados
        )

    def baixar(self):
        expect(self.page.locator("#btBaixar")).to_be_enabled()
        with self.page.expect_download() as evento:
            self.page.locator("#btBaixar").click()
        return json.loads(Path(evento.value.path()).read_text(encoding="utf-8"))

    def combate(self):
        indice = next(i for i, s in enumerate(self.inicial["salas"]) if s["tipo"] == "Combate")
        self.page.locator(".sala-btn").nth(indice).click()
        self.page.locator("#abaCombate").click()
        return self.inicial["salas"][indice]

    def test_abrir_descanso_e_exportar_preserva_o_arquivo(self):
        indice = next(i for i, s in enumerate(self.inicial["salas"]) if s["tipo"] == "Descanso")
        self.page.locator(".sala-btn").nth(indice).click()
        self.assertEqual(self.json()["tipo"], "Descanso")
        self.assertEqual(self.baixar(), self.inicial)

    def test_editar_no_formulario_nao_apaga_o_resto_da_sala(self):
        """Escrever no formulario mexe no campo escrito, e em mais nada.

        O editor de JSON mostrava a sala inteira, entao o autor via o que
        sobrevivia. O formulario mostra uma parte — e e justamente por isso
        que isto precisa de prova: campo que ele nao desenha (uma extensao
        do arquivo, uma chave que o bot ainda nao le) tem de continuar la
        depois de o autor trocar o nome.
        """
        self.semear({"extensao": {"valor": [1, 2]}})
        self.escrever("#fNome", 'Sala "revisada" <tag>')
        expect(self.page.locator("#dTitulo")).to_have_text('Sala "revisada" <tag>')
        self.escrever("#fDesc", "Texto curto.")
        expect(self.page.locator("#dCorpo")).to_have_text("Texto curto.")

        atual = self.json()
        self.assertEqual(atual["extensao"], {"valor": [1, 2]})
        self.assertEqual(atual["nome"], 'Sala "revisada" <tag>')
        self.assertEqual(atual["id"], self.inicial["salas"][0]["id"])

        # E o que foi escrito acompanha a troca de sala e volta inteiro.
        self.page.locator(".sala-btn").nth(1).click()
        self.escrever("#fNome", "Outra sala alterada")
        expect(self.page.locator(".sala-btn").nth(1)).to_contain_text("Outra sala alterada")
        self.page.locator(".sala-btn").nth(0).click()
        self.assertEqual(self.json()["nome"], 'Sala "revisada" <tag>')
        self.assertEqual(self.json()["extensao"], {"valor": [1, 2]})

        baixado = self.baixar()
        self.assertEqual(baixado["salas"][0]["extensao"], {"valor": [1, 2]})
        self.assertEqual(baixado["salas"][1]["nome"], "Outra sala alterada")

    def test_o_formulario_nao_tem_estado_de_sintaxe_quebrada(self):
        """O estado que este arquivo mais testava deixou de existir.

        Com o editor de JSON, metade de uma chave travava trocar de sala, de
        banco e o download, e o texto quebrado tinha de sobreviver ao reload
        para o autor nao perder o que escrevia. Nada disso existe num
        formulario: cada campo escreve direto no objeto, e nao ha momento em
        que a sala esteja ilegivel.

        Fica como prova de que a troca valeu: baixar continua liberado
        enquanto se escreve, e o rascunho sobrevive ao reload.
        """
        self.escrever("#fNome", "Meio de uma frase")
        expect(self.page.locator("#btBaixar")).to_be_enabled()
        self.page.locator(".sala-btn").nth(1).click()
        expect(self.page.locator("#btBaixar")).to_be_enabled()
        self.page.locator(".sala-btn").nth(0).click()
        self.assertEqual(self.json()["nome"], "Meio de uma frase")

        self.page.reload()
        expect(self.page.locator(".sala-btn").first).to_be_visible()
        self.assertEqual(self.json()["nome"], "Meio de uma frase")
        self.assertEqual(self.baixar()["salas"][0]["nome"], "Meio de uma frase")

    def test_rascunho_por_banco_e_busca(self):
        primeiro = self.page.locator("#fBanco").input_value()
        dados = self.json()
        self.escrever("#fNome", "Rascunho persistido")
        dados["nome"] = "Rascunho persistido"
        outra = self.page.locator("#fBanco option").nth(1).get_attribute("value")
        self.page.locator("#fBanco").select_option(outra)
        self.page.locator("#fBanco").select_option(primeiro)
        expect(self.page.locator("#dTitulo")).to_have_text(dados["nome"])
        self.page.reload()
        expect(self.page.locator("#dTitulo")).to_have_text(dados["nome"])
        self.page.locator("#fBusca").fill(dados["id"].lower())
        expect(self.page.locator(".sala-btn")).to_have_count(1)
        self.assertEqual(self.json(), dados)

    def test_duplicar_criar_excluir_e_restaurar(self):
        quantidade = len(self.inicial["salas"])
        original = self.json()
        self.page.locator("#btDuplicar").click()
        copia = self.json()
        self.assertNotEqual(copia["id"], original["id"])
        self.assertEqual(copia["descricao"], original["descricao"])
        self.page.locator("#btNova").click()
        self.assertNotEqual(self.json()["id"], copia["id"])
        expect(self.page.locator(".sala-btn")).to_have_count(quantidade + 2)
        self.page.once("dialog", lambda d: d.accept())
        self.page.locator("#btExcluir").click()
        expect(self.page.locator(".sala-btn")).to_have_count(quantidade + 1)
        self.page.once("dialog", lambda d: d.accept())
        self.page.locator("#btRecarregar").click()
        self.assertEqual(self.baixar(), self.inicial)

    def test_importar_banco_vazio_e_restaurar_importacao(self):
        dados = {"organizacao": self.inicial["organizacao"], "salas": [], "extra": 7}
        self.page.locator("#fArquivo").set_input_files({"name": "meu-banco.json", "mimeType": "application/json", "buffer": json.dumps(dados).encode()})
        # Sem salas, o formulario some e a lista fica vazia — era o "modo
        # banco" que cobria este caso quando havia um editor de JSON.
        expect(self.page.locator(".sala-btn")).to_have_count(0)
        expect(self.page.locator("#formSala")).to_be_hidden()
        self.assertEqual(self.baixar(), dados)
        self.page.locator("#btNova").click()
        self.assertEqual(self.json()["tipo"], "Evento")
        self.page.reload()
        expect(self.page.locator(".sala-btn")).to_have_count(1)
        self.page.once("dialog", lambda d: d.accept())
        self.page.locator("#btRecarregar").click()
        self.assertEqual(self.baixar(), dados)

    def test_filtro_utiliza_edicoes_e_exporta_json(self):
        dados = self.json()
        self.escrever("#fNome", "Sala do filtro")
        dados["nome"] = "Sala do filtro"
        self.page.locator("#abaFiltro").click()
        self.page.locator("#fIncluir").fill(dados["id"])
        expect(self.page.locator("#tabelaPool tr")).to_have_count(1)
        expect(self.page.locator("#tabelaPool")).to_contain_text(dados["nome"])
        expect(self.page.locator(".ficha").first).to_be_disabled()
        self.context.grant_permissions(["clipboard-read", "clipboard-write"])
        self.page.locator("#btCopiarFiltro").click()
        expect(self.page.locator("#toast")).to_have_text("Filtro JSON copiado.")
        copiado = self.page.evaluate("navigator.clipboard.readText()")
        self.assertEqual(json.loads(copiado), {"filtro": {"incluir": [dados["id"]]}})

    def test_medida_respeita_parametros_e_sinaliza_resultado_antigo(self):
        self.combate()
        expect(self.page.locator("#fAmb option:checked")).to_have_text("Qualquer ambiente")
        expect(self.page.locator("#fBicho option:checked")).to_have_text("Qualquer tipo")
        pedidos = []
        def responder(rota):
            pedido = rota.request.post_data_json; pedidos.append(pedido)
            rota.fulfill(json={"sala": pedido["sala"]["id"], "tier": pedido["tier"], "classe": pedido["classe"], "nivel": pedido["nivel"], "repeticoes": pedido["repeticoes"], "semente": pedido["semente"], "criaturas": [{"nome": "Teste"}], "medidas": [{"grupo": 3, "taxa": .75, "rodadas": 2.5, "caidos": .3}]})
        self.page.route("**/api/simular", responder)
        self.page.locator('[name="grupo"][value="5"]').uncheck()
        self.page.locator("#fSemente").fill("123")
        self.page.locator("#btMedir").click()
        expect(self.page.locator("#barrasMedida")).to_contain_text("75%")
        expect(self.page.locator("#contaMedida")).to_contain_text("Grupo de 3")
        self.assertEqual(pedidos[0]["grupos"], [3])
        self.assertEqual(pedidos[0]["semente"], 123)
        self.page.locator("#fNivel").fill("5")
        expect(self.page.locator("#medidaDesatualizada")).to_be_visible()

    def test_sugestao_aplica_somente_o_tier_da_variante_escolhida(self):
        self.combate()
        self.page.locator("#abaEditar").click()
        tema = self.conteudo["temas"][0]
        antes = self.json()
        self.semear({
            "temas": [tema],
            "monstros_por_tema": {tema: {"1": [{"nome": "Aarakocra"}]}},
            "extra": "preservado",
        })
        self.page.locator("#abaCombate").click()
        self.page.locator("#fTemaSim").select_option(tema)
        self.page.locator(".sugeridor summary").click()
        self.page.route("**/api/sugerir", lambda rota: rota.fulfill(json={"semente": 7, "candidatas_no_bestiario": 1, "sugestoes": [{"bando": [{"nome": "Aarakocra", "quantidade": 2}], "na_faixa": True, "por_grupo": {"5": .9, "3": .7}}]}))
        self.page.locator("#btSugerir").click()
        self.page.locator(".usar-sugestao").click()
        novo = self.json()
        self.assertEqual(novo["monstros_por_tema"][tema]["2"], [{"nome": "Aarakocra", "quantidade": 2}])
        self.assertEqual(novo["monstros_por_tema"][tema]["1"], [{"nome": "Aarakocra"}])
        self.assertEqual(novo["monstros_por_tier"], antes["monstros_por_tier"])
        self.assertEqual(novo["extra"], "preservado")
        self.page.locator("#abaCombate").click()
        expect(self.page.locator(".usar-sugestao")).to_be_disabled()

    def test_abas_teclado_e_mobile_sem_rolagem_horizontal(self):
        self.page.locator("#abaEditar").focus()
        self.page.keyboard.press("ArrowRight")
        expect(self.page.locator("#abaCombate")).to_be_focused()
        expect(self.page.locator("#painelCombate")).to_be_visible()
        self.page.keyboard.press("End")
        expect(self.page.locator("#painelFiltro")).to_be_visible()
        self.page.set_viewport_size({"width": 390, "height": 844})
        self.page.emulate_media(color_scheme="dark")
        for aba in ("Editar", "Combate", "Filtro"):
            self.page.locator("#aba" + aba).click()
            self.assertLessEqual(self.page.evaluate("document.documentElement.scrollWidth"), 390)

    def test_respostas_atrasadas_nao_entram_em_outra_sala(self):
        self.combate()
        pendentes = []
        self.page.route("**/api/sugerir", lambda rota: pendentes.append(rota))
        self.page.locator(".sugeridor summary").click()
        with self.page.expect_request("**/api/sugerir"):
            self.page.locator("#btSugerir").click()
        self.page.locator(".sala-btn").first.click()
        pendentes[0].fulfill(json={"semente": 7, "candidatas_no_bestiario": 1, "sugestoes": [{"bando": [{"nome": "Aarakocra", "quantidade": 2}], "na_faixa": True, "por_grupo": {"3": .7}}]})
        expect(self.page.locator("#toast")).to_have_text("Os parâmetros mudaram. Gere novas sugestões.")
        expect(self.page.locator(".usar-sugestao")).to_have_count(0)
        self.assertEqual(self.baixar(), self.inicial)

    def test_sem_armazenamento_local_ainda_e_possivel_baixar(self):
        self.page.add_init_script("Storage.prototype.setItem = () => { throw new Error('indisponível'); };")
        self.page.reload()
        expect(self.page.locator("#estado")).to_have_text("Baixe o JSON para salvar")
        self.assertEqual(self.baixar(), self.inicial)


# O runner le o codigo de saida, e `unittest` sai com 0 mesmo pulando tudo:
# sem playwright, as doze provas nao rodavam e `todos.py` dizia "tudo verde".
# Ficou invisivel por tempo demais — e, quando enfim rodaram, pegaram dois
# defeitos de primeira. O 3 e o combinado com o runner para "nao rodou".
PULADA = 3

if __name__ == "__main__":
    if sync_playwright is None:
        for linha in (
            "SUITE PULADA: falta o playwright, e as 12 provas da interface",
            "nao rodaram. Instale com:",
            "  pip install -r requirements-estudio.txt",
            "  python -m playwright install chromium",
        ):
            print(linha)
        raise SystemExit(PULADA)
    unittest.main(verbosity=2)
