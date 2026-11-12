"""Regressões da bancada no navegador (dependência opcional).

    pip install -r requirements-estudio.txt
    python -m playwright install chromium
    python tests/test_estudio_interface.py

Usa o servidor e os bancos reais; só as buscas demoradas de combate recebem
respostas controladas. Não exige iniciar o estúdio separadamente.

O que estes casos protegem, e que não é óbvio: o estúdio é dividido em quatro
LUGARES — escrever sala de teste, montar combate, montar a dungeon e
inspecionar o banco. A divisão não é enfeite: cada lugar esconde campo que não
é dele, e o que cola um no outro (o tema da sala vazando para o filtro da
dungeon, a sala sumindo da lista ao trocar de tipo) é o que quebra calado.
"""
from __future__ import annotations

import json
import os
import re
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
        self.salas = self.inicial["salas"]
        # Os dois lugares de escrita, pela MESMA família que o servidor manda
        # para a página: o teste e a tela leem a divisão da mesma fonte.
        self.combates = [i for i, s in enumerate(self.salas) if self.lugar_de(s) == "Combate"]
        self.teste = [i for i, s in enumerate(self.salas) if self.lugar_de(s) == "Teste"]

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.erros, [])

    @staticmethod
    def lugar_de(sala):
        return "Combate" if E.FAMILIA_DO_TIPO[sala["tipo"]] == "combate" else "Teste"

    def abrir(self, indice):
        """Abre a sala de índice `indice` NO BANCO, indo ao lugar dela.

        Cada lugar lista só a família dele, então a posição na lista não é
        mais a posição no arquivo — e é essa separação que se quer testar.
        """
        sala = self.salas[indice]
        lugar = self.lugar_de(sala)
        irmas = self.combates if lugar == "Combate" else self.teste
        self.page.locator("#lugar" + lugar).click()
        self.page.locator(".sala-btn").nth(irmas.index(indice)).click()
        return sala

    def json(self):
        """A sala aberta, como o estúdio a tem na memória.

        Lida e não digitada: o formulário é dirigido pelos campos (que é o
        que se quer testar), e o objeto serve para CONFERIR o que eles
        fizeram.
        """
        return self.page.evaluate("JSON.parse(JSON.stringify(sala() || null))")

    def opcoes(self, campo):
        return self.page.locator(campo).evaluate("n => [...n.options].map(o => o.value)")

    def escrever(self, campo, valor):
        """Digita num campo do formulário, como o autor faz."""
        self.page.locator(campo).fill(valor)
        self.page.locator(campo).dispatch_event("input")

    def semear(self, dados):
        """Põe dados na sala aberta sem passar pelo formulário.

        Só para montar o cenário de campos que o formulário NÃO mostra — a
        prova de que editar o nome não apaga o resto do arquivo precisa que
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

    # ------------------------------------------------- os quatro lugares

    def test_cada_lugar_mostra_so_o_que_se_escreve_nele(self):
        """A separação que o estúdio promete, cobrada campo a campo.

        Antes era uma lista só com tudo dentro e três abas por cima: quem ia
        escrever um Evento rolava por cinco combates para achar a sala, e o
        formulário trazia os dois conjuntos de campos de uma vez.
        """
        expect(self.page.locator("#contaTeste")).to_have_text(str(len(self.teste)))
        expect(self.page.locator("#contaCombate")).to_have_text(str(len(self.combates)))
        expect(self.page.locator("#contaTudo")).to_have_text(str(len(self.salas)))

        expect(self.page.locator(".sala-btn")).to_have_count(len(self.teste))
        expect(self.page.locator("#blocoTeste")).to_be_visible()
        expect(self.page.locator("#blocoCriaturas")).to_be_hidden()
        expect(self.page.locator("#painelCombate")).to_be_hidden()
        self.assertNotIn("Combate", self.opcoes("#fTipo"))

        self.page.locator("#lugarCombate").click()
        expect(self.page.locator(".sala-btn")).to_have_count(len(self.combates))
        expect(self.page.locator("#blocoCriaturas")).to_be_visible()
        expect(self.page.locator("#blocoTeste")).to_be_hidden()
        expect(self.page.locator("#btMedir")).to_be_enabled()
        self.assertEqual(self.opcoes("#fTipo"), ["Combate"])

        # E voltar reencontra a sala onde ela foi deixada, não a primeira.
        esperado = self.abrir(self.teste[1])
        self.page.locator("#lugarDungeon").click()
        self.page.locator("#lugarTeste").click()
        self.assertEqual(self.json()["id"], esperado["id"])

    def test_abrir_descanso_mostra_o_tipo_que_a_sala_tem(self):
        """O select não pode mostrar um tipo que a sala não tem.

        Descanso não é oferecido para sala nova — é parada fixa, e o banco
        quer uma só. Mas a sala que JÁ é Descanso tem de aparecer como tal: o
        select montado sem ela caía na primeira opção e dizia "Armadilha"
        sobre um Descanso, calado, com o arquivo intacto por baixo.
        """
        indice = next(i for i, s in enumerate(self.salas) if s["tipo"] == "Descanso")
        self.abrir(indice)
        self.assertEqual(self.json()["tipo"], "Descanso")
        self.assertEqual(self.page.locator("#fTipo").input_value(), "Descanso")
        expect(self.page.locator("#blocoTeste")).to_be_hidden()
        expect(self.page.locator("#blocoCriaturas")).to_be_hidden()
        self.assertEqual(self.baixar(), self.inicial)

    def test_virar_combate_leva_a_sala_para_o_outro_lugar(self):
        """Trocar de família é mudar de lugar, e tem de ser visível.

        Com o tipo num select solto, virar Combate deixava a sala fora da
        lista que o autor estava olhando — ela "sumia" sem ter sumido.
        """
        self.abrir(self.teste[0])
        self.page.locator("#btVirar").click()
        expect(self.page.locator("#lugarCombate")).to_have_attribute("aria-selected", "true")
        expect(self.page.locator(".sala-btn")).to_have_count(len(self.combates) + 1)
        virada = self.json()
        self.assertEqual(virada["tipo"], "Combate")
        self.assertIsNone(virada["cd"])
        self.assertEqual(virada["pericias"], [])
        expect(self.page.locator("#blocoCriaturas")).to_be_visible()

        self.page.locator("#btVirar").click()
        expect(self.page.locator("#lugarTeste")).to_have_attribute("aria-selected", "true")
        expect(self.page.locator(".sala-btn")).to_have_count(len(self.teste))
        self.assertEqual(self.json()["tipo"], self.conteudo["sala_nova"]["teste"])

    def test_inspecionar_lista_o_banco_inteiro_e_abre_a_sala(self):
        self.page.locator("#lugarInspecao").click()
        expect(self.page.locator("#tabelaInspecao tr")).to_have_count(len(self.salas))
        expect(self.page.locator("#saidaBanco")).to_be_visible()

        # A CD da Armadilha aparece com o desconto que a mesa rola de fato.
        armadilha = next(s for s in self.salas if s["tipo"] == "Armadilha" and s.get("cd"))
        desconto = E.I.DESCONTO_CD_ARMADILHA
        expect(self.page.locator("#tabelaInspecao")).to_contain_text(
            f"CD {armadilha['cd']} → {max(1, armadilha['cd'] - desconto)}"
        )

        # Filtrar por tipo encolhe a tabela, e abrir leva ao lugar da sala.
        self.page.locator("#fichasTipos .ficha", has_text="Combate").click()
        expect(self.page.locator("#tabelaInspecao tr")).to_have_count(len(self.combates))
        self.page.locator("#tabelaInspecao .abrir-sala").first.click()
        expect(self.page.locator("#lugarCombate")).to_have_attribute("aria-selected", "true")
        self.assertEqual(self.json()["id"], self.salas[self.combates[0]]["id"])

    def test_o_tema_da_sala_nao_entra_no_filtro_da_dungeon(self):
        """Dois conjuntos de fichas, duas coisas diferentes.

        Os temas da sala, as perícias dela e os temas da dungeon usam a mesma
        ficha na tela. Lendo `.ficha` da página inteira, o filtro da dungeon
        saía com o tema da sala ABERTA dentro — e com as perícias, que nem
        tema são, viravam `null` no pedido e o pool voltava vazio.
        """
        self.context.grant_permissions(["clipboard-read", "clipboard-write"])
        self.page.locator('#fichasSala .ficha[aria-pressed="false"]').first.click()
        self.page.locator('#fichasPericias .ficha[aria-pressed="false"]').first.click()

        self.page.locator("#lugarDungeon").click()
        self.page.locator("#btCopiarFiltro").click()
        expect(self.page.locator("#toast")).to_have_text("Filtro JSON copiado.")
        self.assertEqual(
            json.loads(self.page.evaluate("navigator.clipboard.readText()")), {"filtro": {}}
        )

        # E a ficha que É do filtro entra.
        ficha = self.page.locator("#fichasFiltro .ficha").first
        tema = ficha.get_attribute("data-tema")
        ficha.click()
        self.page.locator("#btCopiarFiltro").click()
        copiado = json.loads(self.page.evaluate("navigator.clipboard.readText()"))
        self.assertEqual(copiado, {"filtro": {"temas": [tema]}})

    def test_partir_de_uma_incursao_carrega_o_filtro_dela(self):
        """Montar dungeon quase nunca começa do zero.

        O que a incursão usa hoje entra nos campos para o autor ver o pool
        que ela monta — e mexer a partir dali, em vez de reescrever de
        memória um JSON que já está em data/. Só as da Organização aberta:
        filtro de outra aponta para IDs que este banco não tem, e o pool
        sairia vazio sem dizer por quê.
        """
        self.page.locator("#lugarDungeon").click()
        daqui = {
            i["id"] for i in self.conteudo["incursoes"].values()
            if i["organizacao"] == self.inicial["organizacao"]
        }
        self.assertTrue(daqui, "o banco de teste não tem incursão nenhuma")
        self.assertEqual(set(self.opcoes("#fIncursao")) - {""}, daqui)

        tema = self.conteudo["temas"][0]
        escrita = {"temas": [tema], "excluir": ["NAO_EXISTE"]}
        self.page.evaluate(
            "d => { C.incursoes[d.id] = d; listarIncursoes(); }",
            {"id": "prova", "nome": "Prova", "organizacao": self.inicial["organizacao"],
             "tamanho": "Longa", "filtro": escrita},
        )
        self.page.locator("#fIncursao").select_option("prova")
        expect(self.page.locator("#toast")).to_contain_text("Prova")
        self.assertEqual(self.page.locator("#fTam").input_value(), "Longa")
        self.assertEqual(self.page.evaluate("filtro()"), escrita)
        expect(self.page.locator("#notaTamanho")).to_contain_text(
            str(self.conteudo["tamanhos"]["Longa"]["paradas"])
        )

    def test_filtro_utiliza_edicoes_e_exporta_json(self):
        dados = self.abrir(self.teste[0])
        self.escrever("#fNome", "Sala do filtro")
        self.page.locator("#lugarDungeon").click()
        self.page.locator("#fIncluir").fill(dados["id"])
        expect(self.page.locator("#tabelaPool tr")).to_have_count(1)
        expect(self.page.locator("#tabelaPool")).to_contain_text("Sala do filtro")
        expect(self.page.locator("#fichasFiltro .ficha").first).to_be_disabled()
        self.context.grant_permissions(["clipboard-read", "clipboard-write"])
        self.page.locator("#btCopiarFiltro").click()
        copiado = self.page.evaluate("navigator.clipboard.readText()")
        self.assertEqual(json.loads(copiado), {"filtro": {"incluir": [dados["id"]]}})

    # ------------------------------------------------------- o formulário

    def test_editar_no_formulario_nao_apaga_o_resto_da_sala(self):
        """Escrever no formulário mexe no campo escrito, e em mais nada.

        O editor de JSON mostrava a sala inteira, então o autor via o que
        sobrevivia. O formulário mostra uma parte — e é por isso que isto
        precisa de prova: campo que ele não desenha (uma extensão do arquivo,
        uma chave que o bot ainda não lê) tem de continuar lá depois de o
        autor trocar o nome.
        """
        primeira, segunda = self.teste[0], self.teste[1]
        self.abrir(primeira)
        self.semear({"extensao": {"valor": [1, 2]}})
        self.escrever("#fNome", 'Sala "revisada" <tag>')
        expect(self.page.locator("#dTitulo")).to_have_text('Sala "revisada" <tag>')
        self.escrever("#fDesc", "Texto curto.")
        expect(self.page.locator("#dCorpo")).to_have_text("Texto curto.")

        atual = self.json()
        self.assertEqual(atual["extensao"], {"valor": [1, 2]})
        self.assertEqual(atual["nome"], 'Sala "revisada" <tag>')
        self.assertEqual(atual["id"], self.salas[primeira]["id"])

        # E o que foi escrito acompanha a troca de sala e volta inteiro.
        self.abrir(segunda)
        self.escrever("#fNome", "Outra sala alterada")
        expect(self.page.locator(".sala-btn").nth(1)).to_contain_text("Outra sala alterada")
        self.abrir(primeira)
        self.assertEqual(self.json()["nome"], 'Sala "revisada" <tag>')
        self.assertEqual(self.json()["extensao"], {"valor": [1, 2]})

        baixado = self.baixar()
        self.assertEqual(baixado["salas"][primeira]["extensao"], {"valor": [1, 2]})
        self.assertEqual(baixado["salas"][segunda]["nome"], "Outra sala alterada")

    def test_o_formulario_nao_tem_estado_de_sintaxe_quebrada(self):
        """O estado que este arquivo mais testava deixou de existir.

        Com o editor de JSON, metade de uma chave travava trocar de sala, de
        banco e o download. Nada disso existe num formulário: cada campo
        escreve direto no objeto, e não há momento em que a sala esteja
        ilegível. Fica como prova de que a troca valeu.
        """
        self.escrever("#fNome", "Meio de uma frase")
        expect(self.page.locator("#btBaixar")).to_be_enabled()
        self.abrir(self.teste[1])
        expect(self.page.locator("#btBaixar")).to_be_enabled()
        self.abrir(self.teste[0])
        self.assertEqual(self.json()["nome"], "Meio de uma frase")

        self.page.reload()
        expect(self.page.locator(".sala-btn").first).to_be_visible()
        self.assertEqual(self.json()["nome"], "Meio de uma frase")
        self.assertEqual(self.baixar()["salas"][self.teste[0]]["nome"], "Meio de uma frase")

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
        original = self.json()
        self.page.locator("#btDuplicar").click()
        copia = self.json()
        self.assertNotEqual(copia["id"], original["id"])
        self.assertEqual(copia["descricao"], original["descricao"])
        self.page.locator("#btNova").click()
        self.assertNotEqual(self.json()["id"], copia["id"])
        self.assertEqual(self.json()["tipo"], self.conteudo["sala_nova"]["teste"])
        expect(self.page.locator(".sala-btn")).to_have_count(len(self.teste) + 2)
        # A nova é de teste: a conta do outro lugar não pode ter andado.
        expect(self.page.locator("#contaCombate")).to_have_text(str(len(self.combates)))
        self.page.once("dialog", lambda d: d.accept())
        self.page.locator("#btExcluir").click()
        expect(self.page.locator(".sala-btn")).to_have_count(len(self.teste) + 1)
        self.page.once("dialog", lambda d: d.accept())
        self.page.locator("#btRecarregar").click()
        self.assertEqual(self.baixar(), self.inicial)

    def test_importar_banco_vazio_e_restaurar_importacao(self):
        dados = {"organizacao": self.inicial["organizacao"], "salas": [], "extra": 7}
        self.page.locator("#fArquivo").set_input_files({"name": "meu-banco.json", "mimeType": "application/json", "buffer": json.dumps(dados).encode()})
        expect(self.page.locator(".sala-btn")).to_have_count(0)
        expect(self.page.locator("#formSala")).to_be_hidden()
        self.assertEqual(self.baixar(), dados)
        self.page.locator("#btNova").click()
        self.assertEqual(self.json()["tipo"], self.conteudo["sala_nova"]["teste"])
        self.page.reload()
        expect(self.page.locator(".sala-btn")).to_have_count(1)
        self.page.once("dialog", lambda d: d.accept())
        self.page.locator("#btRecarregar").click()
        self.assertEqual(self.baixar(), dados)

    # --------------------------------------------------- medir e sugerir

    def test_medida_respeita_parametros_e_sinaliza_resultado_antigo(self):
        self.abrir(self.combates[0])
        expect(self.page.locator("#fAmb option:checked")).to_have_text("Qualquer ambiente")
        expect(self.page.locator("#fBicho option:checked")).to_have_text("Qualquer tipo")
        pedidos = []
        def responder(rota):
            pedido = rota.request.post_data_json; pedidos.append(pedido)
            rota.fulfill(json={"sala": pedido["sala"]["id"], "tier": pedido["tier"], "classe": "sorteado", "sorteado": True, "nivel": pedido["nivel"], "repeticoes": pedido["repeticoes"], "semente": pedido["semente"], "criaturas": [{"nome": "Teste"}], "medidas": [{"grupo": 3, "taxa": .75, "rodadas": 2.5, "caidos": .3, "mesas": 12, "lutas": 240, "pior": {"classes": ["bardo", "mago", "monge"], "taxa": .41, "amostras": 20}, "melhor": {"classes": ["clerigo", "guerreiro", "paladino"], "taxa": .94, "amostras": 20}}]})
        self.page.route("**/api/simular", responder)
        self.page.locator('[name="grupo"][value="5"]').uncheck()
        self.page.locator("#fSemente").fill("123")
        self.page.locator("#btMedir").click()
        expect(self.page.locator("#barrasMedida")).to_contain_text("75%")
        expect(self.page.locator("#contaMedida")).to_contain_text("Grupo de 3")
        self.assertEqual(pedidos[0]["grupos"], [3])
        self.assertEqual(pedidos[0]["semente"], 123)
        # O grupo sorteado é o PADRÃO: ninguém escolheu classe nenhuma.
        self.assertEqual(pedidos[0]["classe"], "")
        self.page.locator("#fNivel").fill("5")
        expect(self.page.locator("#medidaDesatualizada")).to_be_visible()

    def test_a_medida_mostra_a_pior_mesa_e_nao_so_a_media(self):
        """A média responde "a sala é justa?" e esconde a outra pergunta.

        Um grupo que vence 75% das vezes na média pode ter uma composição em
        41% dentro dele — a diferença entre "difícil" e "a mesa morre". Com
        só a barra na tela, as duas salas se parecem.
        """
        self.abrir(self.combates[0])
        self.assertEqual(self.page.locator("#fClasse").input_value(), "")
        # Os padrões do formulário têm de passar na própria validação dele:
        # um `step` que não fecha com o `min` reprova o campo, e `medir`
        # desiste sem dizer nada — o botão vira enfeite.
        for campo in ("#fReps", "#fNivel"):
            self.assertTrue(self.page.locator(campo).evaluate("n => n.checkValidity()"), campo)
        medida = {"grupo": 5, "taxa": .75, "rodadas": 3.0, "caidos": .5, "mesas": 12,
                  "lutas": 240,
                  "pior": {"classes": ["bardo", "mago", "mago", "monge", "xama"],
                           "taxa": .41, "amostras": 20},
                  "melhor": {"classes": ["clerigo", "druida", "guerreiro", "ladino",
                                         "paladino"], "taxa": .94, "amostras": 20}}
        self.page.route("**/api/simular", lambda rota: rota.fulfill(json={
            "sala": "X", "tier": 2, "classe": "sorteado", "sorteado": True, "nivel": 4,
            "repeticoes": 240, "semente": 9, "criaturas": [{"nome": "Teste"}],
            "medidas": [medida]}))
        self.page.locator("#btMedir").click()
        barras = self.page.locator("#barrasMedida")
        expect(barras).to_contain_text("75%")
        expect(barras).to_contain_text("pior 41%")
        expect(barras).to_contain_text("mago, mago")
        expect(barras).to_contain_text("20 lutas")
        expect(barras).to_contain_text("melhor 94%")
        expect(self.page.locator("#contaMedida")).to_contain_text("12 mesas")

    def test_o_limite_de_criaturas_e_por_bando_e_nao_a_soma_da_sala(self):
        """Seis no tier 1 e dois no tier 2 é sala válida.

        O bot cobra o máximo POR TIER, porque é um tier por incursão. O
        estúdio somava os tiers e pintava de vermelho um arquivo que ele
        mesmo aprova na conferência ao lado — mandando o autor apagar
        criatura que não sobrava.
        """
        indice = next(
            i for i in self.combates
            if len(self.salas[i].get("monstros_por_tier") or {}) > 1
        )
        self.abrir(indice)
        expect(self.page.locator("#saidaSala")).to_contain_text("Sala conferida.")
        recado = self.page.locator("#recadoCriaturas")
        expect(recado).not_to_have_class(re.compile("invalido"))
        self.assertNotIn("máximo", recado.inner_text())

        # E um bando que estoura de verdade continua sendo acusado.
        quantas = self.page.locator("#linhasCriaturas input[type=number]").first
        quantas.fill(str(self.conteudo["limites"]["inimigos"] + 3))
        expect(recado).to_have_class(re.compile("invalido"))
        expect(recado).to_contain_text("máximo")

    def test_sugestao_aplica_somente_o_tier_da_variante_escolhida(self):
        self.abrir(self.combates[0])
        tema = self.conteudo["temas"][0]
        antes = self.json()
        self.semear({
            "temas": [tema],
            "monstros_por_tema": {tema: {"1": [{"nome": "Aarakocra"}]}},
            "extra": "preservado",
        })
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
        # A sala mudou: a sugestão medida na sala de antes não vale mais.
        expect(self.page.locator(".usar-sugestao")).to_be_disabled()

    def test_respostas_atrasadas_nao_entram_em_outra_sala(self):
        self.abrir(self.combates[0])
        pendentes = []
        self.page.route("**/api/sugerir", lambda rota: pendentes.append(rota))
        self.page.locator(".sugeridor summary").click()
        with self.page.expect_request("**/api/sugerir"):
            self.page.locator("#btSugerir").click()
        # Mudar de lugar é mudar de sala: a resposta que volta é de outra.
        self.page.locator("#lugarTeste").click()
        pendentes[0].fulfill(json={"semente": 7, "candidatas_no_bestiario": 1, "sugestoes": [{"bando": [{"nome": "Aarakocra", "quantidade": 2}], "na_faixa": True, "por_grupo": {"3": .7}}]})
        expect(self.page.locator("#toast")).to_have_text("Os parâmetros mudaram. Gere novas sugestões.")
        expect(self.page.locator(".usar-sugestao")).to_have_count(0)
        self.assertEqual(self.baixar(), self.inicial)

    # -------------------------------------------------------------- geral

    def test_lugares_pelo_teclado_e_mobile_sem_rolagem_horizontal(self):
        self.page.locator("#lugarTeste").focus()
        self.page.keyboard.press("ArrowRight")
        expect(self.page.locator("#lugarCombate")).to_be_focused()
        expect(self.page.locator("#painelCombate")).to_be_visible()
        self.page.keyboard.press("End")
        expect(self.page.locator("#painelInspecao")).to_be_visible()
        self.page.set_viewport_size({"width": 390, "height": 844})
        self.page.emulate_media(color_scheme="dark")
        for lugar in ("Teste", "Combate", "Dungeon", "Inspecao"):
            self.page.locator("#lugar" + lugar).click()
            self.assertLessEqual(self.page.evaluate("document.documentElement.scrollWidth"), 390)

    def test_sem_o_motor_a_bancada_diz_em_vez_de_esperar_o_clique(self):
        """Quem abre o estúdio fora do ambiente do bot escreve tudo e só

        descobre no clique de "Medir combate" — e o que chegava era o
        ModuleNotFoundError cru. O resto da bancada funciona sem o motor, e é
        por isso que o aviso tem de estar na tela ANTES: nada mais quebra
        para avisar por ele.
        """
        recado = "Medir e sugerir precisam de 'aiosqlite'"

        def responder(rota):
            dados = rota.fetch().json()
            dados["falta_para_simular"] = recado
            rota.fulfill(json=dados)

        self.page.route("**/api/conteudo", responder)
        self.page.reload()
        # A bancada abre inteira: escrever e exportar não dependem do motor.
        expect(self.page.locator(".sala-btn").first).to_be_visible()
        expect(self.page.locator("#btBaixar")).to_be_enabled()

        self.page.locator("#lugarCombate").click()
        expect(self.page.locator("#avisoCombate")).to_contain_text(recado)
        expect(self.page.locator("#btMedir")).to_be_disabled()
        expect(self.page.locator("#btSugerir")).to_be_disabled()

    def test_sem_armazenamento_local_ainda_e_possivel_baixar(self):
        self.page.add_init_script("Storage.prototype.setItem = () => { throw new Error('indisponível'); };")
        self.page.reload()
        expect(self.page.locator("#estado")).to_have_text("Baixe o JSON para salvar")
        self.assertEqual(self.baixar(), self.inicial)


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
