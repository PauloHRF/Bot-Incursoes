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

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tools"))

from src import bestiario, incursoes as I  # noqa: E402
from src.rules import TIER_MAXIMO  # noqa: E402

import estudio as E  # noqa: E402


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
    r = E.simular({"sala": sala_de_combate(), "tier": 1, "nivel": 2,
                   "repeticoes": 10**9, "grupos": [2]})
    assert r["repeticoes"] == E.REPETICOES_MAXIMO, r["repeticoes"]
    r = E.simular({"sala": sala_de_combate(), "tier": 1, "nivel": 2,
                   "repeticoes": "muitas", "grupos": [2]})
    assert r["repeticoes"] == E.REPETICOES_PADRAO
    print("  as repetições têm teto e padrão: ok")


# --------------------------------------------------------------- página


def caso_a_pagina_so_chama_rota_que_existe():
    """Anti-deriva: a página e o servidor são escritos em arquivos diferentes."""
    assert E.PAGINA.exists(), f"a página não está em {E.PAGINA}"
    html = E.PAGINA.read_text(encoding="utf-8")
    chamadas = set(re.findall(r'api\("(/api/[a-z]+)"', html))
    assert chamadas, "a página não chama o servidor: ela ficaria sem dado nenhum"
    fora = chamadas - set(E.ROTAS)
    assert not fora, f"a página chama rota que não existe: {sorted(fora)}"
    print(f"  as {len(chamadas)} rotas que a página chama existem: ok")


def caso_a_pagina_nao_copia_as_listas_do_codigo():
    """Se a página listasse os temas, eles envelheceriam calados."""
    html = E.PAGINA.read_text(encoding="utf-8")
    codigo = html.split("<script>")[-1]
    copiados = [t for t in I.TEMAS if f'"{t}"' in codigo]
    assert not copiados, (
        f"a página tem tema escrito no JavaScript: {copiados}. "
        f"Eles têm que vir de /api/conteudo."
    )
    print("  a página não tem lista do código copiada dentro: ok")


for caso in (
    caso_o_conteudo_vem_do_codigo,
    caso_os_minimos_por_tamanho_saem_da_conta_do_sorteio,
    caso_o_conteudo_le_o_disco_e_tolera_arquivo_ruim,
    caso_conferir_reconhece_os_tres_tipos,
    caso_a_sala_sozinha_nao_leva_bronca_do_banco,
    caso_conferir_devolve_os_problemas_de_verdade,
    caso_o_pool_usa_as_salas_em_edicao,
    caso_o_pool_traz_o_veredito_do_bot,
    caso_o_pool_recusa_pedido_torto,
    caso_simular_mede_a_sala_de_combate,
    caso_a_mesma_semente_da_o_mesmo_numero,
    caso_mudar_a_lista_de_grupos_nao_mexe_nos_outros,
    caso_sala_de_teste_nao_e_medida_por_simulacao,
    caso_simular_recusa_o_que_nao_dá_para_medir,
    caso_as_repeticoes_tem_teto,
    caso_a_pagina_so_chama_rota_que_existe,
    caso_a_pagina_nao_copia_as_listas_do_codigo,
):
    caso()

print("TESTES DO ESTUDIO PASSARAM")
