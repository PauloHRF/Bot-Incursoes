"""O documento do formato é testado contra o código que ele descreve.

`docs/formato-das-incursoes.md` é a régua que outras pessoas vão usar para
escrever dungeons. Um formato documentado errado não quebra o bot: desperdiça
o trabalho de quem escreveu confiando nele, e o erro só aparece quando o
arquivo chega. Então o documento não pode ser prosa solta ao lado do código.

Este arquivo cobra três coisas:

- **os exemplos do documento passam no validador do bot.** Todo bloco JSON de
  lá é extraído e validado de verdade, com o mesmo `de_dict`/`banco_de_dict`
  que o bot usa;
- **as listas do documento são as do código.** Organizações, perícias e os
  debuffs que uma criatura pode deixar saem das constantes, e se uma mudar o
  teste aponta o documento;
- **os limites e os padrões documentados são os de verdade.** O número está
  escrito aqui ao lado do nome da constante: mudar o limite no código sem
  mudar o documento fica vermelho.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import condicoes as C, incursoes as I  # noqa: E402
from src.rules import PERICIAS, TIER_MAXIMO  # noqa: E402

DOC = RAIZ / "docs" / "formato-das-incursoes.md"
TEXTO = DOC.read_text(encoding="utf-8")
# O mesmo texto com os espacos normalizados. O documento quebra linha onde a
# prosa pede, e "Guilda dos Mortos" cai com a quebra no meio: procurar o nome
# literal falharia por isso, e cobraria do documento uma linha feia so para o
# teste passar. Quem se adapta e o teste.
PLANO = re.sub(r"\s+", " ", TEXTO)


def _blocos_json() -> list[dict]:
    """Os blocos ```json do documento, convertidos.

    O documento mostra FRAGMENTOS de propósito — `"golpes": [...]` sozinho é
    mais claro para quem lê do que um objeto inteiro em volta —, e um bloco
    pode trazer duas formas da mesma coisa, uma por linha. O extrator lida com
    as três formas em vez de o documento piorar para o teste ficar fácil.

    O exemplo do banco é pulado porque ele tem `"...": "..."` no lugar das
    salas: ele ilustra a forma do arquivo, e não uma sala.
    """
    blocos: list[dict] = []
    cerca = "```json" + chr(10)
    for bruto in re.findall(cerca + r"(.*?)```", TEXTO, re.DOTALL):
        if '"...": "..."' in bruto:
            continue
        texto = bruto.strip()
        if texto.startswith('"'):
            texto = "{" + texto + "}"
        try:
            blocos.append(json.loads(texto))
            continue
        except json.JSONDecodeError:
            pass
        for linha in texto.splitlines():
            linha = linha.strip().rstrip(",")
            if linha:
                blocos.append(json.loads(linha))
    return blocos


CRIATURA_BASE = {"nome": "Base", "ca": 13, "ataque": 4, "hp": 30, "dano": "1d6"}
SALA_BASE = {
    "id": "B0", "nome": "Base", "tipo": "Combate", "descricao": "x",
    "monstros": [dict(CRIATURA_BASE)],
}
INCURSAO_BASE = {
    "id": "base", "nome": "Base", "organizacao": "Vórtice Oculto",
    "lore_inicial": "x", "recompensa_mes": 10, "objetivo": dict(SALA_BASE),
}


def caso_os_exemplos_do_documento_sao_validos():
    """Todo exemplo do documento passa no validador do bot.

    Cada bloco é classificado e validado no lugar onde ele vive de verdade: a
    sala dentro de um banco, a criatura dentro de uma sala de Combate, o
    fragmento de habilidade dentro de uma criatura. Nenhum bloco é pulado em
    silêncio — a conta no fim é o que impede um exemplo novo de entrar no
    documento sem ninguém validar.
    """
    blocos = _blocos_json()
    conferidos = 0

    for bloco in blocos:
        if "filtro" in bloco and "objetivo" not in bloco:
            # O fragmento do filtro, dentro de uma incursao de verdade. E
            # cruzado com o banco do Vortice de propósito: um exemplo de filtro
            # que nao fecha no banco real ensinaria a escrever dungeon travada.
            incursao = I.de_dict({**INCURSAO_BASE, **bloco})
            assert incursao.filtro.temas == ["cripta", "arcano"], incursao.filtro
            assert incursao.filtro.excluir == ["VO12"], incursao.filtro
            banco = I.carregar_banco(RAIZ / "data" / "bancos" / "vortice_oculto.json")
            problemas, _ = I.conferir_filtro(incursao, banco)
            assert not problemas, (
                f"o filtro de exemplo do documento não fecha no banco real: {problemas}"
            )
        elif "objetivo" in bloco:
            # A incursao inteira: e o exemplo que todo mundo vai copiar.
            incursao = I.de_dict(bloco)
            assert incursao.id == "vortice_agulha", incursao.id
            assert incursao.tamanho == "Média" and incursao.tier == 3
            assert incursao.objetivo.tipo == "Combate"
        elif "tipo" in bloco:
            # Uma sala do caminho: validada num banco, com o minimo de tres.
            banco = I.banco_de_dict({
                "organizacao": "Vórtice Oculto",
                "salas": [bloco, {**bloco, "id": "X1"}, {**bloco, "id": "X2"}],
            })
            assert len(banco.salas) == 3
        elif "monstros_por_tema" in bloco:
            # A variante por tema so vale dentro de uma sala que CARREGA esses
            # temas, e o documento promete exatamente isso: por isso a sala de
            # apoio leva os dois temas do exemplo, e nao uma lista qualquer.
            sala = I._sala_de_dict(
                {**SALA_BASE, **bloco, "temas": ["cripta", "natureza"]},
                "doc", (problemas := []),
            )
            assert sala is not None and not problemas, problemas
            assert set(sala.monstros_por_tema) == {"cripta", "natureza"}
            do_tema = sala.monstros_do_tier(2, "cripta")
            assert do_tema and do_tema[0].nome.startswith("Carniçal"), do_tema
            # E o degrau de baixo continua valendo: tema sem variante escrita
            # cai no bando padrao da sala.
            padrao = sala.monstros_do_tier(2, "urbano")
            assert [m.nome for m in padrao] == [
                m.nome for m in sala.monstros_do_tier(2)
            ], padrao
        elif "monstros_por_tier" in bloco:
            sala = I._sala_de_dict(
                {**SALA_BASE, **bloco, "monstros": []}, "doc", (problemas := [])
            )
            assert sala is not None and not problemas, problemas
            assert set(sala.monstros_por_tier) == {2, 4}, sala.monstros_por_tier
        elif "golpes" in bloco:
            feitas = I.monstros_de_criatura({**CRIATURA_BASE, **bloco}, "doc")
            assert feitas, bloco
            # O documento afirma que a lista MANDA: ela sobrescreve o `dano`.
            assert len(feitas[0].golpes) == 2, feitas[0].golpes
            assert feitas[0].dano == feitas[0].golpes[0].dano != CRIATURA_BASE["dano"]
        elif "save" in bloco:
            # O fragmento da habilidade, dentro de uma criatura.
            feitas = I.monstros_de_criatura(
                {**CRIATURA_BASE, "habilidade": bloco}, "doc"
            )
            assert feitas and feitas[0].habilidade is not None, bloco
        elif "nome" in bloco:
            feitas = I.monstros_de_criatura(bloco, "doc")
            assert feitas, f"o exemplo de criatura não validou: {bloco}"
        else:
            raise AssertionError(f"bloco do documento que o teste não sabe conferir: {bloco}")
        conferidos += 1

    assert conferidos == len(blocos) and conferidos >= 7, (
        f"conferidos {conferidos} de {len(blocos)} blocos"
    )
    print(f"  os {conferidos} exemplos do documento passam no validador: ok")


def caso_as_listas_do_documento_sao_as_do_codigo():
    """Organizações, perícias e debuffs: o documento cita os do código."""
    for organizacao in I.ORGANIZACOES:
        assert organizacao in PLANO, f"a Organização '{organizacao}' não está no documento"

    for pericia in PERICIAS:
        assert pericia in PLANO, f"a perícia '{pericia}' não está no documento"
    # E nao cita perícia que nao existe: a lista do documento e EXATA.
    citadas = re.search(r"As 18 perícias: (.+?)\.\n", TEXTO, re.DOTALL)
    assert citadas, "a lista de perícias mudou de forma no documento"
    nomes = {p.strip() for p in citadas.group(1).replace("\n", " ").split(",")}
    assert nomes == set(PERICIAS), (
        f"a lista do documento não é a do código\n  só no doc: {nomes - set(PERICIAS)}"
        f"\n  só no código: {set(PERICIAS) - nomes}"
    )

    # Os debuffs: os ids que uma criatura pode deixar sao os das condicoes
    # RUINS, e nenhuma outra.
    trecho = re.search(
        r"Debuffs que uma criatura pode deixar: (.+?)\. Criatura", TEXTO, re.DOTALL
    )
    assert trecho, "a lista de debuffs mudou de forma no documento"
    do_doc = set(re.findall(r"`([a-z_]+)`", trecho.group(1)))
    do_codigo = {c.id for c in C.CATALOGO if c.ruim}
    assert do_doc == do_codigo, (
        f"a lista de debuffs do documento não é a do código\n"
        f"  só no doc: {do_doc - do_codigo}\n  só no código: {do_codigo - do_doc}"
    )
    # Os temas: a lista do documento e EXATA, pelo mesmo motivo das perícias.
    # Tema a mais no código e ausente do documento é tema que ninguém usa;
    # tema a mais no documento é sala recusada na validação.
    trecho = re.search(r"e \*\*só estes oito\*\*: (.+?)\.\n", TEXTO, re.DOTALL)
    assert trecho, "a lista de temas mudou de forma no documento"
    do_doc = set(re.findall(r"`([a-z]+)`", trecho.group(1)))
    assert do_doc == set(I.TEMAS), (
        f"a lista de temas do documento não é a do código\n"
        f"  só no doc: {do_doc - set(I.TEMAS)}\n  só no código: {set(I.TEMAS) - do_doc}"
    )
    assert len(I.TEMAS) == 8, (
        f"o documento diz 'só estes oito' e o código tem {len(I.TEMAS)}"
    )
    print("  as listas do documento sao as do codigo: ok")


def caso_os_limites_documentados_sao_os_de_verdade():
    """O número documentado está aqui ao lado da constante que ele descreve."""
    documentados = {
        "salas por banco (mínimo)": (3, I.OPCOES_POR_PASSO),
        "criaturas numa sala": (6, I.MAX_INIMIGOS),
        "golpes por rodada": (8, I.MAX_ATAQUES_DO_MONSTRO),
        "alvos de uma habilidade": (6, I.MAX_ALVOS),
        "tier máximo": (5, TIER_MAXIMO),
        "desconto de CD da Armadilha": (3, I.DESCONTO_CD_ARMADILHA),
        # Estes dois são do Discord: o documento promete um teto que o bot
        # cobra, e os dois têm que ser o mesmo número.
        "teto do nome": (256, I.LIMITE_TITULO),
        "teto da descrição e da lore": (4096, I.LIMITE_DESCRICAO),
    }
    for o_que, (no_doc, no_codigo) in documentados.items():
        assert no_doc == no_codigo, (
            f"{o_que}: o documento diz {no_doc} e o código usa {no_codigo}"
        )
        assert str(no_doc) in TEXTO, f"{o_que}: o número {no_doc} não está no documento"

    # Os tamanhos e as paradas da tabela do documento.
    assert I.TAMANHOS == {"Curta": 3, "Média": 5, "Longa": 7}, I.TAMANHOS
    assert I.paradas_do_caminho(3) == 3
    assert I.paradas_do_caminho(5) == 6, "a Média deixou de ter um descanso"
    assert I.paradas_do_caminho(7) == 9, "a Longa deixou de ter dois descansos"
    # A tabela do filtro: quantas salas o pool precisa ter por tamanho. O
    # segundo numero e `passos + OPCOES_POR_PASSO - 1`, e o documento o escreve
    # a mao — se a formula mudar, a tabela mente.
    for tamanho, (terminar, folga) in {
        "Curta": (3, 5), "Média": (5, 7), "Longa": (7, 9)
    }.items():
        assert I.TAMANHOS[tamanho] == terminar, (
            f"{tamanho}: o documento diz que atravessa {terminar} salas"
        )
        assert terminar + I.OPCOES_POR_PASSO - 1 == folga, (
            f"{tamanho}: o documento diz {folga} para três portas sempre, "
            f"e a conta do código dá {terminar + I.OPCOES_POR_PASSO - 1}"
        )
        assert f"| `{tamanho}` | {terminar} | {folga} |" in TEXTO, (
            f"a linha de {tamanho} sumiu ou mudou na tabela do filtro"
        )

    assert "385" in TEXTO, "o documento cita o tamanho do bestiário"
    bestiario = json.loads((RAIZ / "data" / "bestiario.json").read_text(encoding="utf-8"))
    assert len(bestiario["criaturas"]) == 385, (
        f"o bestiário tem {len(bestiario['criaturas'])} criaturas, e o documento diz 385"
    )
    print("  os limites documentados sao os de verdade: ok")


def caso_os_padroes_documentados_sao_os_de_verdade():
    """O que o documento promete como padrão é o que o validador faz.

    Cada um destes já apareceu no documento como "não obrigatório (valor)", e
    é a promessa mais fácil de quebrar sem perceber: mudar um default no
    código não falha teste nenhum até alguém notar o conteúdo diferente.
    """
    minima = {
        "id": "so_o_minimo",
        "nome": "Só o mínimo",
        "organizacao": "Vórtice Oculto",
        "lore_inicial": "Abertura.",
        "recompensa_mes": 10,
        "objetivo": {
            "id": "OBJ", "nome": "Fim", "tipo": "Combate",
            "descricao": "A sala final.",
            "monstros": [{"nome": "Lobo", "ca": 13, "ataque": 4, "hp": 11, "dano": "2d4+2"}],
        },
    }
    incursao = I.de_dict(minima)
    assert incursao.tamanho == "Média", "o padrão de tamanho mudou"
    assert incursao.tier == TIER_MAXIMO, "o padrão de tier mudou"
    assert incursao.pontos_conclusao == 10, "o padrão de pontos_conclusao mudou"
    assert incursao.lore_final is None
    assert incursao.objetivo.pontos_organizacao == 0, "o padrão de pontos_organizacao mudou"

    # A criatura: quantidade 1, um ataque.
    uma = I.monstros_de_criatura(
        {"nome": "Lobo", "ca": 13, "ataque": 4, "hp": 11, "dano": "2d4+2"}
    )
    assert len(uma) == 1 and uma[0].ataques == 1, uma
    # Com quantidade > 1 cada copia ganha numero, como o documento diz.
    tres = I.monstros_de_criatura(
        {"nome": "Lobo", "ca": 13, "ataque": 4, "hp": 11, "dano": "2d4+2", "quantidade": 3}
    )
    assert [m.nome for m in tres] == ["Lobo 1", "Lobo 2", "Lobo 3"], tres

    # A habilidade: `cada` 2 e `alvos` 1.
    com_habilidade = I.monstros_de_criatura(
        {
            "nome": "Coisa", "ca": 13, "ataque": 4, "hp": 30, "dano": "1d6",
            "habilidade": {"nome": "Grito", "save": "SAB", "cd": 12, "atordoa": 1},
        }
    )
    assert com_habilidade, "a criatura com habilidade não validou"
    habilidade = com_habilidade[0].habilidade
    assert habilidade is not None
    assert habilidade.cada == 2, "o padrão de `cada` mudou"
    assert habilidade.alvos == 1, "o padrão de `alvos` mudou"
    print("  os padroes documentados sao os de verdade: ok")


def caso_o_documento_nao_mente_sobre_o_que_e_recusado():
    """As quatro recusas que o documento afirma, cobradas no validador."""
    base = {
        "id": "teste", "nome": "Teste", "organizacao": "Vórtice Oculto",
        "lore_inicial": "Abertura.", "recompensa_mes": 10,
    }
    final = {
        "id": "OBJ", "nome": "Fim", "tipo": "Combate", "descricao": "A sala final.",
        "monstros": [{"nome": "Lobo", "ca": 13, "ataque": 4, "hp": 11, "dano": "2d4+2"}],
    }

    def recusa(dados, o_que):
        try:
            I.de_dict(dados)
        except I.ErroDeValidacao:
            return
        raise AssertionError(f"o documento diz que isto e recusado, e passou: {o_que}")

    # "o objetivo tem de ser do tipo Combate"
    recusa({**base, "objetivo": {**final, "tipo": "Evento", "monstros": []}},
           "objetivo que nao e Combate")
    # "so Combate tem criatura": uma sala de Evento com bicho, dentro de um
    # banco, que e onde sala de caminho mora.
    try:
        I.banco_de_dict({
            "organizacao": "Vórtice Oculto",
            "salas": [
                {
                    "id": f"E{n}", "nome": "Evento com bicho", "tipo": "Evento",
                    "descricao": "x", "dificuldade": "Média", "cd": 12,
                    "alvo_progresso": 5, "pericias": ["Percepção"],
                    "monstros": [{"nome": "Lobo", "ca": 13, "ataque": 4, "hp": 11,
                                  "dano": "2d4+2"}],
                }
                for n in range(3)
            ],
        })
        raise AssertionError("sala de Evento com criatura passou")
    except I.ErroDeValidacao:
        pass
    # "o id usa so minusculas, numeros e _"
    recusa({**base, "id": "Com Maiuscula", "objetivo": final}, "id com espaco e maiuscula")
    # "a Organizacao tem de ser uma das quatro"
    recusa({**base, "organizacao": "Clube do Bolinha", "objetivo": final},
           "Organizacao inventada")
    # "o banco precisa de pelo menos 3 salas"
    try:
        I.banco_de_dict({"organizacao": "Vórtice Oculto", "salas": [
            {"id": "A", "nome": "A", "tipo": "Combate", "descricao": "x",
             "monstros": [{"nome": "Lobo", "ca": 13, "ataque": 4, "hp": 11, "dano": "2d4+2"}]}
        ]})
        raise AssertionError("banco com uma sala só passou")
    except I.ErroDeValidacao:
        pass

    # E a armadilha do `nome`: habilidade sem nome e descartada em SILENCIO,
    # que e justamente o que o documento avisa.
    sem_nome = I.monstros_de_criatura(
        {
            "nome": "Coisa", "ca": 13, "ataque": 4, "hp": 30, "dano": "1d6",
            "habilidade": {"save": "SAB", "cd": 12, "atordoa": 1},
        }
    )
    assert sem_nome and sem_nome[0].habilidade is None, (
        "habilidade sem nome deixou de ser descartada em silencio, e o "
        "documento avisa que ela e"
    )
    print("  o documento nao mente sobre o que e recusado: ok")


def main():
    caso_os_exemplos_do_documento_sao_validos()
    caso_as_listas_do_documento_sao_as_do_codigo()
    caso_os_limites_documentados_sao_os_de_verdade()
    caso_os_padroes_documentados_sao_os_de_verdade()
    caso_o_documento_nao_mente_sobre_o_que_e_recusado()


main()
print("TESTES DO FORMATO PASSARAM")
