"""O estúdio: a bancada de quem escreve dungeon.

O que estes casos protegem, e que não é óbvio:

1. **A página não pode ter cópia das listas.** Tema, tipo de sala e limite
   mudam no código; uma lista copiada no JavaScript envelheceria calada. Por
   isso `conteudo()` entrega as do código, e aqui se cobra que sejam as
   mesmas.
2. **Uma sala sozinha não é cobrada das regras do banco.** Quem escreve abre
   uma sala antes de ela ter vizinhas; reprovar por falta de sala de Descanso
   ou de mínimo de salas seria reprovar conteúdo correto.
3. **A medida é reprodutível.** Dois autores comparando números precisam ver o
   mesmo número, então a semente manda e aparece na resposta.
4. **O estúdio não promete o que não sabe.** Sala de teste não é medida por
   simulação, e a "chance da dungeon inteira" não existe aqui.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import threading
from contextlib import closing
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tools"))

from src import bestiario, incursoes as I  # noqa: E402
from src.rules import TIER_MAXIMO  # noqa: E402

import estudio as E  # noqa: E402
from tools.simulacao import regua  # noqa: E402


CRIATURA = {"nome": "Coisa", "ca": 13, "ataque": 4, "dano": "1d6", "hp": 12}


def sala_de_teste(**extra):
    base = {
        "id": "T01", "nome": "Sala", "tipo": "Evento",
        "descricao": "Uma porta.", "dificuldade": "Média", "cd": 13,
        "alvo_progresso": 3, "pericias": ["Investigação"],
    }
    base.update(extra)
    return base


def sala_de_combate(**extra):
    base = sala_de_teste(
        id="C01", tipo="Combate", dificuldade=None, cd=None,
        alvo_progresso=None, pericias=[], monstros=[dict(CRIATURA)],
    )
    base.update(extra)
    return base


# ------------------------------------------------------------- conteudo


def caso_o_conteudo_vem_do_codigo():
    c = E.conteudo()
    assert c["temas"] == list(I.TEMAS), "a página receberia uma lista de temas velha"
    assert c["tipos"] == list(I.TIPOS_SALA)
    assert c["organizacoes"] == list(I.ORGANIZACOES)
    assert c["ambientes"] == list(bestiario.AMBIENTES)
    assert c["limites"]["titulo"] == I.LIMITE_TITULO
    assert c["limites"]["descricao"] == I.LIMITE_DESCRICAO
    assert c["limites"]["inimigos"] == I.MAX_INIMIGOS
    assert c["limites"]["tier_maximo"] == TIER_MAXIMO
    print("  o conteúdo da página vem do código, não de cópia: ok")


def caso_cada_tipo_de_sala_tem_familia_e_resumo():
    """A bancada é dividida em lugares pela FAMÍLIA do tipo.

    Quem escreve um Evento não precisa ver a tabela de criaturas, e quem monta
    um Combate não precisa da CD — por isso são lugares diferentes, e por isso
    cada tipo precisa dizer de qual família é. Tipo novo em TIPOS_SALA sem
    família não teria lugar na tela: viraria sala que ninguém abre. Aqui ele
    derruba o teste antes de derrubar o estúdio do colaborador.
    """
    c = E.conteudo()
    por_id = {t["id"]: t for t in c["tipos_de_sala"]}
    assert list(por_id) == list(I.TIPOS_SALA), list(por_id)
    assert {t["familia"] for t in c["tipos_de_sala"]} == {"teste", "combate", "parada"}, (
        "família nova: a página só tem lugar para teste, combate e parada"
    )
    for tipo, t in por_id.items():
        assert t["resumo"].strip(), f"{tipo} não diz ao autor o que a sala faz"

    # O desconto da CD sai da REGRA, e não de um número repetido na página.
    armadilha = I.sala_de_dict(sala_de_teste(tipo="Armadilha"))
    assert por_id["Armadilha"]["desconto_cd"] == armadilha.cd - armadilha.cd_efetiva(1)
    assert por_id["Evento"]["desconto_cd"] == 0

    # E a sala que nasce em cada lugar é um tipo daquele lugar.
    for familia, tipo in c["sala_nova"].items():
        assert por_id[tipo]["familia"] == familia, (familia, tipo)
    assert set(c["sala_nova"]) == {"teste", "combate"}, (
        "o botão '+ Nova' existe em dois lugares e precisa de um tipo para cada"
    )
    print("  cada tipo de sala tem família, resumo e desconto: ok")


def caso_os_minimos_por_tamanho_saem_da_conta_do_sorteio():
    """`folga` é o que o pool precisa para oferecer 3 portas em toda parada."""
    c = E.conteudo()
    for nome, passos in I.TAMANHOS.items():
        t = c["tamanhos"][nome]
        assert t["salas"] == passos and t["terminar"] == passos
        assert t["folga"] == passos + I.OPCOES_POR_PASSO - 1, (nome, t)
        assert t["paradas"] == I.paradas_do_caminho(passos)
    print("  os mínimos por tamanho saem da conta do sorteio: ok")


def caso_o_conteudo_le_o_disco_e_tolera_arquivo_ruim():
    c = E.conteudo()
    assert set(c["bancos"]) == set(I.ORGANIZACOES), list(c["bancos"])
    assert c["incursoes"], "nenhuma incursão foi lida de data/"
    assert c["problemas"] == [], c["problemas"]
    print(f"  leu {len(c['bancos'])} bancos e {len(c['incursoes'])} incursões: ok")


def caso_o_editor_recebe_o_json_original_sem_expandir_criaturas():
    """Abrir e baixar não pode reescrever referências nem perder extensões."""
    dados = {
        "organizacao": "Vórtice Oculto", "nota_do_autor": {"versao": 7},
        "salas": [sala_de_combate(id=f"C{n}", monstros=[
            {"nome": "Aarakocra", "quantidade": 2},
        ], anotacao="preservar") for n in range(3)],
    }
    with tempfile.TemporaryDirectory() as pasta:
        caminho = Path(pasta) / "nome_do_autor.json"
        caminho.write_text(json.dumps(dados), encoding="utf-8")
        (Path(pasta) / "quebrado.json").write_text("{", encoding="utf-8")
        with patch.object(E, "PASTA_BANCOS", Path(pasta)):
            r = E._bancos()
    banco = r["bancos"][dados["organizacao"]]
    assert banco["original"] == dados
    assert banco["arquivo"] == "nome_do_autor.json"
    assert banco["salas"][0]["monstros"][0]["hp"] > 0
    assert any("quebrado.json" in p for p in r["problemas"])
    print("  o editor preserva o JSON original e o nome do arquivo: ok")


# ------------------------------------------------------------- conferir


def caso_conferir_reconhece_os_tres_tipos():
    assert E.conferir({"dados": sala_de_teste()})["tipo"] == "sala"
    banco = {"organizacao": "Vórtice Oculto",
             "salas": [sala_de_teste(id=f"T{n:02d}") for n in range(1, 4)]}
    assert E.conferir({"dados": banco})["tipo"] == "banco"
    incursao = {
        "id": "t", "nome": "T", "organizacao": "Vórtice Oculto",
        "lore_inicial": "x", "recompensa_mes": 10,
        "objetivo": sala_de_combate(id="OBJ"),
    }
    assert E.conferir({"dados": incursao})["tipo"] == "incursao"
    print("  conferir reconhece sala, banco e incursão: ok")


def caso_a_sala_sozinha_nao_leva_bronca_do_banco():
    """A regressão que isto tranca: a sala solta vinha com o aviso do banco.

    Quem escreve abre UMA sala antes de ela ter vizinhas. Cobrar ali a sala de
    Descanso, que é regra do banco, seria reprovar conteúdo correto por causa
    de salas que ainda não existem.
    """
    r = E.conferir({"dados": sala_de_teste()})
    assert r["problemas"] == [], r
    assert r["avisos"] == [], (
        f"a sala sozinha levou aviso que é do banco: {r['avisos']}"
    )

    # E os avisos QUE SÃO dela continuam saindo.
    longa = E.conferir({"dados": sala_de_teste(descricao="x" * 700)})
    assert any("700 caracteres" in a for a in longa["avisos"]), longa
    print("  a sala sozinha leva só os avisos dela: ok")


def caso_conferir_devolve_os_problemas_de_verdade():
    r = E.conferir({"dados": sala_de_teste(temas=["vulcanico"])})
    assert any("vulcanico" in p for p in r["problemas"]), r
    assert E.conferir({"dados": "não é objeto"})["problemas"], "payload torto passou"
    print("  conferir devolve os problemas do validador: ok")


# ----------------------------------------------------------------- pool


def banco_em_edicao(salas):
    return {"organizacao": "Vórtice Oculto", "tamanho": "Curta", "salas": salas}


def caso_o_pool_usa_as_salas_em_edicao():
    """O autor precisa ver o efeito de sala que ele ainda não salvou.

    É a razão de o estúdio existir em vez de o autor rodar o validador depois
    de copiar o arquivo para data/.
    """
    salas = [sala_de_teste(id=f"T{n:02d}", temas=["cripta"]) for n in range(1, 4)]
    salas += [sala_de_teste(id=f"U{n:02d}", temas=["urbano"]) for n in range(1, 4)]
    r = E.pool({**banco_em_edicao(salas), "filtro": {"temas": ["cripta"]}})
    assert [s["id"] for s in r["pool"]] == ["T01", "T02", "T03"], r["pool"]
    assert r["sorteaveis"] == 6 and r["terminar"] == 3 and r["folga"] == 5
    print("  o pool enxerga as salas em edição: ok")


def caso_o_pool_traz_o_veredito_do_bot():
    salas = [sala_de_teste(id=f"T{n:02d}", temas=["cripta"]) for n in range(1, 4)]
    salas += [sala_de_teste(id=f"U{n:02d}", temas=["urbano"]) for n in range(1, 4)]

    # Curta atravessa 3 e quer 5 para tres portas: 'cripta' deixa 3.
    r = E.pool({**banco_em_edicao(salas), "filtro": {"temas": ["cripta"]}})
    assert not r["problemas"] and r["avisos"], r

    # Longa atravessa 7, e o banco inteiro tem 6.
    r = E.pool({**banco_em_edicao(salas), "tamanho": "Longa", "filtro": {}})
    assert any("terminar" in p for p in r["problemas"]), r
    print("  o pool traz problema e aviso do conferir_filtro: ok")


def caso_o_pool_recusa_pedido_torto():
    salas = [sala_de_teste(id=f"T{n:02d}") for n in range(1, 4)]
    assert "erro" in E.pool({**banco_em_edicao(salas), "tamanho": "Gigante"})
    assert "erro" in E.pool({"organizacao": "Clube do Bolinha", "tamanho": "Curta"})
    torto = E.pool({**banco_em_edicao(salas), "filtro": {"incluem": ["T01"]}})
    assert "erro" in torto and torto["problemas"], torto
    print("  o pool recusa tamanho, organização e filtro tortos: ok")


# -------------------------------------------------------------- simular


def caso_simular_mede_a_sala_de_combate():
    r = E.simular({"sala": sala_de_combate(), "tier": 1, "nivel": 2,
                   "repeticoes": 60, "grupos": [5, 3]})
    assert "erro" not in r, r
    assert [m["grupo"] for m in r["medidas"]] == [5, 3]
    assert all(0.0 <= m["taxa"] <= 1.0 for m in r["medidas"]), r["medidas"]
    assert r["criaturas"][0]["nome"].startswith("Coisa")
    print(f"  a sala foi medida: grupo 5 = {r['medidas'][0]['taxa']:.0%}: ok")


def caso_a_medida_vem_de_mesas_sorteadas_com_os_extremos():
    """A sala é medida contra VÁRIAS mesas, e a página recebe os extremos.

    Cinco cópias da mesma classe não é uma mesa que existe, e o número que
    ela dava mudava conforme a classe escolhida. A média responde "a sala é
    justa?"; a pior mesa responde "existe grupo que ela mata?" — e é essa que
    some na média, então ela sai do servidor pronta em vez de a página ter de
    saber o que procurar.
    """
    r = E.simular({"sala": sala_de_combate(monstros=[dict(CRIATURA, quantidade=3)]),
                   "tier": 1, "nivel": 4, "repeticoes": 90, "grupos": [3]})
    assert r["sorteado"] is True and r["classe"] == "sorteado", r["classe"]
    medida = r["medidas"][0]
    assert medida["mesas"] > 1, medida
    assert medida["pior"]["taxa"] <= r["medidas"][0]["taxa"] <= medida["melhor"]["taxa"]
    assert len(set(medida["pior"]["classes"])) > 1, (
        "a pior mesa saiu com uma classe só: o grupo voltou a ser uniforme"
    )
    assert medida["pior"]["amostras"] >= 1 and medida["lutas"] >= medida["mesas"]

    # E a classe continua aceita, como DIAGNÓSTICO: "dura para quem?".
    d = E.simular({"sala": sala_de_combate(), "tier": 1, "nivel": 2,
                   "repeticoes": 30, "grupos": [3], "classe": "mago"})
    assert d["sorteado"] is False and d["classe"] == "mago"
    assert d["medidas"][0]["mesas"] == 1 and d["medidas"][0]["pior"] is None
    assert "erro" in E.simular({"sala": sala_de_combate(), "classe": "padeiro"})
    print(f"  a sala foi medida contra {medida['mesas']} mesas sorteadas: ok")


def caso_a_medida_sai_com_veredito():
    """Medir e mostrar a porcentagem e metade do trabalho.

    A outra metade e dizer o que ela QUER DIZER: a bancada media 62% e
    deixava o autor adivinhar se era o que ele queria. A regua
    (`tools/simulacao/regua.py`) e a mesma do sugeridor e do calibrador da
    emboscada — ter faixas em tres lugares era o jeito de elas divergirem.
    """
    r = E.simular({"sala": sala_de_combate(monstros=[dict(CRIATURA, quantidade=3)]),
                   "tier": 1, "nivel": 4, "repeticoes": 90, "grupos": [3]})
    medida = r["medidas"][0]
    assert "rotulo" in medida and medida["rotulo"], medida
    assert medida["dificuldade"] == regua.dificuldade_de(medida["taxa"]), medida
    assert isinstance(medida["dizima"], bool)

    # O veredito da mesa azarada vem do PERCENTIL, e nao da pior mesa: o
    # minimo afunda conforme a amostra cresce, entao ele nomeia quem sofreu
    # mas nao decide nada.
    assert medida["azarada"] is None or medida["azarada"] >= medida["pior"]["taxa"]
    assert medida["dizima"] == (
        medida["azarada"] is not None and medida["azarada"] < regua.PIOR_MESA_MINIMA
    ), medida

    # E a regua nao inventa faixa para quem caiu no buraco entre duas: 82% nao
    # e "quase facil", e uma sala que nao foi mirada.
    assert regua.dificuldade_de(0.82) is None
    assert regua.dificuldade_de(0.72) == "media"
    assert regua.veredito(0.72, 0.5)["dizima"] is True
    assert regua.veredito(0.72, 0.9)["dizima"] is False
    print(f"  a medida sai com veredito ({medida['rotulo']}): ok")


def caso_a_mesma_semente_da_o_mesmo_numero():
    """Dois autores comparando números precisam ver o mesmo número."""
    pedido = {"sala": sala_de_combate(), "tier": 1, "nivel": 2,
              "repeticoes": 80, "grupos": [4], "semente": 12345}
    a = E.simular(dict(pedido))
    b = E.simular(dict(pedido))
    assert a["medidas"] == b["medidas"], (a["medidas"], b["medidas"])
    assert a["semente"] == 12345

    outra = E.simular({**pedido, "semente": 999})
    assert outra["semente"] == 999
    print("  a mesma semente dá o mesmo número: ok")


def caso_mudar_a_lista_de_grupos_nao_mexe_nos_outros():
    """Cada tamanho tem rng próprio, derivado da semente."""
    pedido = {"sala": sala_de_combate(), "tier": 1, "nivel": 2,
              "repeticoes": 80, "semente": 7}
    so_quatro = E.simular({**pedido, "grupos": [4]})["medidas"][0]
    com_cinco = E.simular({**pedido, "grupos": [5, 4]})["medidas"][1]
    assert so_quatro == com_cinco, (so_quatro, com_cinco)
    print("  tirar um tamanho da lista não move o número dos outros: ok")


def caso_a_bancada_abre_sem_o_motor_e_diz_o_que_falta():
    """Escrever não pode exigir o que só medir precisa.

    O estúdio sobe com a biblioteca padrão: ler banco, validar sala e montar
    filtro não tocam no motor. Medir toca — e o motor guarda o estado da run
    em SQLite, por `aiosqlite`. Quem abre o estúdio fora do ambiente do bot vê
    tudo funcionar, escreve a sala inteira, e só no clique de "Medir combate"
    recebe um `ModuleNotFoundError` cru, que não diz a ninguém o que fazer.

    A regressão que isto tranca: a falta tem de chegar na página pelo
    `conteudo`, e as duas rotas que dependem do motor têm de recusar com o
    mesmo recado em vez de estourar.
    """
    recado = "falta a dependência da medição"
    with patch.object(E, "_falta_para_simular", return_value=recado):
        c = E.conteudo()
        assert c["falta_para_simular"] == recado
        assert c["bancos"] and c["temas"], "o resto da página parou de vir junto"
        assert E.simular({"sala": sala_de_combate(), "tier": 1})["erro"] == recado
        assert E.sugerir({"tier": 1, "dificuldade": "media"})["erro"] == recado

    # E o recado traz o COMANDO, não um conselho: "abra pelo ambiente do bot"
    # supõe que quem leu saiba qual é e como escrevê-lo no shell dele.
    with patch.object(E, "_python_do_bot", return_value=Path("D:/bot/.venv/py.exe")):
        aponta = E._recado_de_dependencia("aiosqlite")
    assert "aiosqlite" in aponta and "py.exe" in aponta, aponta
    with patch.object(E, "_python_do_bot", return_value=None):
        sem_venv = E._recado_de_dependencia("aiosqlite")
    assert "requirements.txt" in sem_venv, sem_venv

    assert E._falta_para_simular() == "", (
        "o motor não importa neste Python — rode os testes pelo ambiente do bot"
    )
    assert E.conteudo()["falta_para_simular"] == ""
    print("  a bancada abre sem o motor e diz o que falta: ok")


def caso_sala_de_teste_nao_e_medida_por_simulacao():
    """Armadilha, Evento e Tesouro são conta fechada: d20 + perícia vs CD."""
    r = E.simular({"sala": sala_de_teste(), "tier": 2})
    assert "erro" in r and "conta fechada" in r["erro"], r
    print("  sala de teste não é medida por amostra, e o estúdio diz por quê: ok")


def caso_simular_recusa_o_que_nao_dá_para_medir():
    assert "erro" in E.simular({})
    assert "erro" in E.simular({"sala": sala_de_combate(temas=["vulcanico"])})
    assert "erro" in E.simular({"sala": sala_de_combate(), "classe": "padeiro"})
    sem_tier = E.simular({
        "sala": sala_de_combate(monstros=[], monstros_por_tier={"4": [dict(CRIATURA)]}),
        "tier": 1,
    })
    assert "erro" not in sem_tier, (
        "tier 1 abaixo do menor escrito tem que cair no piso, não falhar"
    )
    print("  simular recusa o que não dá para medir: ok")


def caso_as_repeticoes_tem_teto():
    """A bancada é local, mas um número enorme trava a página do autor."""
    import simular_combate as sc
    # Este caso confere os limites da API; os outros casos medem lutas reais.
    # A resposta de mentira tem a MESMA forma da de verdade — inclusive as
    # composições —, senão ela deixa de ser um substituto e vira outra coisa.
    def medir(monstros, tamanho, args, rng):
        return {"taxa": 1.0, "rodadas": 1.0, "caidos": 0.0, "amostras": args.repeticoes,
                "composicoes": [{"classes": ["mago"], "taxa": 1.0, "amostras": 1}]}
    with patch.object(sc, "simular", side_effect=medir) as chamada:
        r = E.simular({"sala": sala_de_combate(), "tier": 1, "nivel": 2,
                       "repeticoes": 10**9, "grupos": [2]})
        assert r["repeticoes"] == E.REPETICOES_MAXIMO, r["repeticoes"]
        r = E.simular({"sala": sala_de_combate(), "tier": 1, "nivel": 2,
                       "repeticoes": "muitas", "grupos": [2]})
        assert r["repeticoes"] == E.REPETICOES_PADRAO
        assert chamada.call_args.args[2].repeticoes == E.REPETICOES_PADRAO
    print("  as repetições têm teto e padrão: ok")


# --------------------------------------------------------------- página


def _fonte_da_interface() -> str:
    """Todo arquivo que o navegador carrega, junto num texto só.

    Varre a PASTA e não um arquivo escolhido a dedo. A interface já foi um
    HTML único e hoje são três; os guardas abaixo valiam para o arquivo que
    por acaso guardava o JavaScript, e um `fetch` colado de volta no HTML
    passaria por eles. Varrendo a pasta, o guarda sobrevive à próxima divisão.
    """
    partes = [
        caminho.read_text(encoding="utf-8")
        for caminho in sorted(E.PAGINA.parent.iterdir())
        if caminho.suffix in (".html", ".js")
    ]
    assert len(partes) >= 2, f"só achei {len(partes)} arquivo(s) de interface"
    return chr(10).join(partes)


def caso_a_pagina_so_chama_rota_que_existe():
    """Anti-deriva: a página e o servidor são escritos em arquivos diferentes."""
    assert E.PAGINA.exists(), f"a página não está em {E.PAGINA}"
    codigo = _fonte_da_interface()
    chamadas = set(re.findall(r'api\("(/api/[a-z]+)"', codigo))
    chamadas |= set(re.findall(r'fetch\("(/api/[a-z]+)"', codigo))
    assert chamadas, "a página não chama o servidor: ela ficaria sem dado nenhum"
    fora = chamadas - set(E.ROTAS)
    assert not fora, f"a página chama rota que não existe: {sorted(fora)}"
    print(f"  as {len(chamadas)} rotas que a página chama existem: ok")


def caso_a_pagina_nao_copia_as_listas_do_codigo():
    """Se a página listasse os temas, eles envelheceriam calados."""
    codigo = _fonte_da_interface()
    copiados = [t for t in I.TEMAS if f'"{t}"' in codigo]
    assert not copiados, (
        f"a página tem tema escrito no JavaScript: {copiados}. "
        f"Eles têm que vir de /api/conteudo."
    )
    print("  a página não tem lista do código copiada dentro: ok")


def caso_o_servidor_entrega_os_arquivos_da_interface():
    with E.ThreadingHTTPServer(("127.0.0.1", 0), E.Bancada) as servidor:
        tarefa = threading.Thread(target=servidor.serve_forever, daemon=True)
        tarefa.start()
        try:
            for rota, arquivo, tipo in (
                ("/", "index.html", "text/html"),
                ("/estudio.js", "estudio.js", "text/javascript"),
                ("/estudio.css", "estudio.css", "text/css"),
            ):
                with closing(HTTPConnection(*servidor.server_address)) as conexao:
                    conexao.request("GET", rota)
                    resposta = conexao.getresponse()
                    assert resposta.status == 200
                    assert resposta.getheader("Content-Type").startswith(tipo)
                    assert resposta.read() == E.PAGINA.with_name(arquivo).read_bytes()
            with closing(HTTPConnection(*servidor.server_address)) as conexao:
                conexao.request("GET", "/../estudio.py")
                resposta = conexao.getresponse()
                assert resposta.status == 404
                resposta.read()
        finally:
            servidor.shutdown()
            tarefa.join()
    print("  a interface carrega pelo servidor sem expor outros arquivos: ok")


for caso in (
    caso_o_conteudo_vem_do_codigo,
    caso_cada_tipo_de_sala_tem_familia_e_resumo,
    caso_os_minimos_por_tamanho_saem_da_conta_do_sorteio,
    caso_o_conteudo_le_o_disco_e_tolera_arquivo_ruim,
    caso_o_editor_recebe_o_json_original_sem_expandir_criaturas,
    caso_conferir_reconhece_os_tres_tipos,
    caso_a_sala_sozinha_nao_leva_bronca_do_banco,
    caso_conferir_devolve_os_problemas_de_verdade,
    caso_o_pool_usa_as_salas_em_edicao,
    caso_o_pool_traz_o_veredito_do_bot,
    caso_o_pool_recusa_pedido_torto,
    caso_simular_mede_a_sala_de_combate,
    caso_a_medida_vem_de_mesas_sorteadas_com_os_extremos,
    caso_a_medida_sai_com_veredito,
    caso_a_mesma_semente_da_o_mesmo_numero,
    caso_mudar_a_lista_de_grupos_nao_mexe_nos_outros,
    caso_a_bancada_abre_sem_o_motor_e_diz_o_que_falta,
    caso_sala_de_teste_nao_e_medida_por_simulacao,
    caso_simular_recusa_o_que_nao_dá_para_medir,
    caso_as_repeticoes_tem_teto,
    caso_a_pagina_so_chama_rota_que_existe,
    caso_a_pagina_nao_copia_as_listas_do_codigo,
    caso_o_servidor_entrega_os_arquivos_da_interface,
):
    caso()

print("TESTES DO ESTUDIO PASSARAM")
