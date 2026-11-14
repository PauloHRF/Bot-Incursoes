"""O sugeridor de combates: a dificuldade é medida, não declarada.

Sala de combate não tem campo de dificuldade no formato, e isso não é
descuido: num combate quem decide a dificuldade são as criaturas. O sugeridor
então não ESCREVE um rótulo — ele procura uma composição cuja taxa de vitória
medida caia na faixa pedida, e devolve o número que mediu.

O que estes casos protegem:

1. **A busca anda na direção certa.** O espaço (qual criatura × quantas) é
   monótono nos dois eixos, e o veredito de cada medição diz para que lado ir.
   A maior parte dos casos aqui troca o simulador por uma tabela, porque o que
   se quer provar é a LÓGICA da busca — provar isso com milhares de confrontos
   seria lento e, pior, instável.
2. **O veredito é medido nos extremos antes de bissecar.** Sem isso a busca
   gasta três medições para descobrir no fim o que duas dizem no começo.
3. **O sugeridor não mente quando não acha.** Ele devolve o que mediu, com o
   número ao lado, em vez de um rótulo inventado ou de um silêncio.
"""
from __future__ import annotations

import random
import sys
from types import SimpleNamespace
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tools"))

from src import bestiario, incursoes as I  # noqa: E402

import sugestor as S  # noqa: E402
from tools.simulacao import grupos  # noqa: E402


# ---------------------------------------------------- simulador de mentira


class SimuladorFalso:
    """Troca `medir_bando` por uma tabela, para testar a BUSCA e não o motor.

    Recebe uma função `taxa(nome, quantidade)` e conta quantas medições a
    busca pediu — é assim que se cobra que a bisseção seja bisseção.
    """

    def __init__(self, taxa):
        self.taxa = taxa
        self.chamadas: list[tuple[str, int]] = []
        self._verdadeiro = None

    def __enter__(self):
        self._verdadeiro = S.medir_bando

        def falso(monstros, classe, nivel, tamanho, confrontos, semente):
            # O bando chega pelas CRIATURAS, e nao por uma chave de texto: a
            # busca deixou de passar o bando na semente (ela agora pareia as
            # mesas), e o duble le o que ela de fato mede.
            blocos: list[list] = []
            for m in monstros:
                if not blocos or blocos[-1][0] != m.nome:
                    blocos.append([m.nome, 0])
                blocos[-1][1] += 1
            nome = "+".join(n for n, _ in blocos)
            quantidade = blocos[-1][1]
            self.chamadas.append((nome, quantidade))
            return self.taxa(nome, quantidade)

        S.medir_bando = falso
        # `_monstros` consulta o bestiario de verdade; aqui so precisa
        # devolver criaturas com nome, que e o que o duble acima le.
        self._monstros = S._monstros
        S._monstros = lambda nome, q: [
            SimpleNamespace(nome=nome) for _ in range(max(1, q))
        ]
        return self

    def __exit__(self, *_):
        S.medir_bando = self._verdadeiro
        S._monstros = self._monstros


def taxa_por_quantidade(tabela):
    """Taxa que só depende de quantas criaturas são."""
    return lambda nome, q: tabela[q]


# ------------------------------------------------------------- a janela


def caso_a_janela_de_cr_se_estende_na_direcao_da_dificuldade():
    """Fácil alcança para baixo, difícil para cima, média fica no tier."""
    for tier in (2, 3, 4):
        lo, hi = bestiario.FAIXAS_DE_CR[tier]
        assert S.janela_de_cr(tier, "media") == (lo, hi)

        facil = S.janela_de_cr(tier, "facil")
        assert facil[0] < lo and facil[1] == hi, facil

        dificil = S.janela_de_cr(tier, "dificil")
        assert dificil[0] == lo and dificil[1] > hi, dificil
    print("  a janela de CR se estende na direção da dificuldade: ok")


def caso_a_janela_dos_extremos_nao_estoura():
    """Tier 1 não tem tier 0, nem o 5 tem o 6: as pontas se viram."""
    for dificuldade in ("facil", "media", "dificil"):
        for tier in (1, I.TIER_MAXIMO):
            lo, hi = S.janela_de_cr(tier, dificuldade)
            assert lo <= hi, (tier, dificuldade, lo, hi)
    print("  a janela não estoura nos tiers das pontas: ok")


def caso_o_nivel_segue_o_tier():
    assert S.nivel_do_tier(1) == 2 and S.nivel_do_tier(3) == 6
    assert S.nivel_do_tier(5) == 10, "o nível para em 10"
    print("  o nível do grupo simulado segue o tier: ok")


# ----------------------------------------------- candidatas do bestiário


def caso_criatura_sem_ambiente_entra_em_qualquer_ambiente():
    """A lista vazia é significado, e não dado faltando.

    O livro não prende a bioma quem não é nativo de bioma — demônio, golem,
    celestial. Sem esta regra, uma cripta ou um templo não acharia quase nada.
    """
    com_ambiente = bestiario.candidatas(ambiente="forest", tier=2)
    assert com_ambiente, "nenhuma criatura de floresta no tier 2"
    nenhures = [c for c in com_ambiente if bestiario.de_lugar_nenhum(c)]
    assert nenhures, "as criaturas de lugar nenhum ficaram de fora da floresta"

    # E quem TEM ambiente so entra no ambiente dela.
    for criatura in com_ambiente:
        seus = bestiario.ambientes_de(criatura)
        assert not seus or "forest" in seus, criatura["nome"]
    print(f"  {len(nenhures)} criaturas de lugar nenhum entram em qualquer ambiente: ok")


def caso_os_tres_filtros_sao_independentes():
    todas = bestiario.candidatas()
    assert len(todas) == 385, len(todas)
    so_tier = bestiario.candidatas(tier=2)
    so_tipo = bestiario.candidatas(tipo="undead")
    juntos = bestiario.candidatas(tipo="undead", tier=2)
    assert len(juntos) <= min(len(so_tier), len(so_tipo))
    assert all((c.get("meta") or {}).get("tipo") == "undead" for c in juntos)
    print("  os três filtros são independentes e se acumulam: ok")


def caso_a_faixa_de_cr_manda_sobre_o_tier():
    """Quem chama pode pedir a própria janela: um chefe vem de cima do tier.

    Cobra os LIMITES, e não só "veio mais coisa": ignorar `faixa_cr` por
    completo também devolveria mais criaturas — devolveria o bestiário
    inteiro — e um teste de contagem diria que está tudo bem.
    """
    do_tier = bestiario.candidatas(tier=1)
    larga = bestiario.candidatas(faixa_cr=(0.0, 4.0))
    assert len(larga) > len(do_tier)
    assert all(0.0 <= bestiario.cr_de(c) <= 4.0 for c in larga), (
        "entrou criatura fora da faixa pedida"
    )
    acima = [c["nome"] for c in bestiario.carregar() if bestiario.cr_de(c) > 4.0]
    assert acima, "o bestiário não tem criatura acima de CR 4 para o teste cobrar"
    nomes = {c["nome"] for c in larga}
    assert not (nomes & set(acima)), "a faixa foi ignorada: veio CR acima de 4"

    estreita = bestiario.candidatas(faixa_cr=(3.0, 3.0))
    assert estreita and all(bestiario.cr_de(c) == 3.0 for c in estreita)
    print("  a faixa de CR explícita manda sobre a do tier: ok")


# ----------------------------------------------------------- a bisseção


def caso_a_bissecao_acha_a_menor_quantidade_que_cabe():
    # Taxa cai conforme a quantidade sobe; a faixa 65-80 cabe em 4.
    tabela = {1: 1.00, 2: 0.95, 3: 0.88, 4: 0.75, 5: 0.50, 6: 0.20}
    with SimuladorFalso(taxa_por_quantidade(tabela)) as falso:
        achada = S.composicao_de_uma("X", (0.65, 0.80), "guerreiro", 4, 1)
    assert achada["bando"] == [{"nome": "X", "quantidade": 4}], achada
    assert achada["veredito"] == "serve"
    assert len(falso.chamadas) <= 5, (
        f"bisseção virou varredura: {len(falso.chamadas)} medições"
    )
    print(f"  a bisseção achou a quantidade certa em {len(falso.chamadas)} medições: ok")


def caso_a_bissecao_nao_e_varredura():
    """Numa escala larga, bisseção e varredura deixam de empatar.

    De 1 a 6 as duas gastam o mesmo tanto de medições, e o teste da quantidade
    não distinguia uma da outra. Com 1 a 20, a bisseção gasta ~5 e a varredura
    gasta dezenas.
    """
    def montar(n):
        return [object()] * n

    chamadas = []
    verdadeiro = S.medir_bando

    def falso(monstros, classe, nivel, tamanho, confrontos, semente):
        n = len(monstros)
        chamadas.append(n)
        return max(0.0, 1.0 - n * 0.05)

    S.medir_bando = falso
    try:
        achado, taxa, veredito = S._melhor_na_escala(
            montar, (0.45, 0.60), "guerreiro", 4, 1, 1, 20
        )
    finally:
        S.medir_bando = verdadeiro

    assert veredito == "serve" and achado == 8, (achado, taxa, veredito)
    assert len(set(chamadas)) <= 8, (
        f"mediu {len(set(chamadas))} pontos de 20: isso é varredura, não bisseção"
    )
    print(f"  a bisseção achou em {len(set(chamadas))} medições de 20 pontos: ok")


def caso_o_veredito_fraca_sai_sem_bissecar():
    """Nem o bando cheio desce do teto: não há quantidade que sirva."""
    tabela = {q: 0.99 for q in range(1, 7)}
    with SimuladorFalso(taxa_por_quantidade(tabela)) as falso:
        achada = S.composicao_de_uma("X", (0.45, 0.60), "guerreiro", 4, 1)
    assert achada["veredito"] == "fraca", achada
    assert len(falso.chamadas) == 2, (
        f"os dois extremos bastam para saber; mediu {len(falso.chamadas)}"
    )
    print("  'fraca' sai medindo só os dois extremos: ok")


def caso_o_veredito_forte_sai_sem_bissecar():
    """Até uma sozinha já fica abaixo do piso."""
    tabela = {q: 0.05 for q in range(1, 7)}
    with SimuladorFalso(taxa_por_quantidade(tabela)) as falso:
        achada = S.composicao_de_uma("X", (0.45, 0.60), "guerreiro", 4, 1)
    assert achada["veredito"] == "forte", achada
    assert len(falso.chamadas) == 2, len(falso.chamadas)
    print("  'forte' sai medindo só os dois extremos: ok")


def caso_a_busca_anda_para_o_lado_que_o_veredito_aponta():
    """O coração do sugeridor: 'fraca' pede CR maior, 'forte' pede CR menor.

    As criaturas estão ordenadas por CR, e só a do meio serve. A busca tem que
    chegar nela sem provar a lista inteira.
    """
    criaturas = [
        {"nome": f"C{i:02d}", "cr": str(i), "meta": {"tipo": "beast"}}
        for i in range(1, 16)
    ]
    # O alvo fica LONGE do meio de propósito: com ele no meio, a primeira
    # prova da bisseção já acerta e a direção nunca é exercida — foi assim
    # que uma versão com os lados trocados passou no teste.
    alvo = "C02"

    def taxa(nome, q):
        base = nome.split("+")[0]
        if base == alvo:
            return 0.52
        # Mais forte que o alvo: abaixo do piso. Mais fraca: acima do teto.
        return 0.05 if base > alvo else 0.99

    with SimuladorFalso(taxa) as falso:
        achadas, _ = S.procurar_composicoes(
            criaturas, (0.45, 0.60), "guerreiro", 4, 1, random.Random(1), 1
        )
    provadas = [n for n, _ in falso.chamadas]
    assert achadas and achadas[0]["veredito"] == "serve", achadas
    assert achadas[0]["bando"][0]["nome"] == alvo, achadas[0]["bando"]
    assert len(set(provadas)) <= 6, (
        f"a busca provou {len(set(provadas))} de {len(criaturas)}: isso é varredura"
    )
    print(f"  a busca achou {alvo} provando {len(set(provadas))} de {len(criaturas)}: ok")


def caso_a_escala_que_pula_a_faixa_nao_vira_serve():
    """O bug que isto tranca, e ele entregava combate errado.

    A bisseção procura o TETO: a menor quantidade cuja taxa cai abaixo dele.
    Mas a escala é de inteiros, e pode saltar a faixa inteira entre duas
    quantidades — 95% com três criaturas, 43% com quatro. Sem olhar o PISO
    depois, o sugeridor chamava os 43% de "serve" e entregava como Média um
    combate que mata o grupo mais da metade das vezes.
    """
    tabela = {1: 1.00, 2: 0.98, 3: 0.95, 4: 0.43, 5: 0.20, 6: 0.05}
    with SimuladorFalso(taxa_por_quantidade(tabela)):
        achada = S.composicao_de_uma("X", (0.65, 0.80), "guerreiro", 4, 1)
    assert achada["veredito"] == "pula", achada
    assert achada["taxa_da_busca"] == 0.43

    # E com uma escala que NAO pula, a mesma faixa serve.
    macia = {1: 1.00, 2: 0.90, 3: 0.78, 4: 0.60, 5: 0.30, 6: 0.10}
    with SimuladorFalso(taxa_por_quantidade(macia)):
        achada = S.composicao_de_uma("X", (0.65, 0.80), "guerreiro", 4, 1)
    assert achada["veredito"] == "serve" and achada["taxa_da_busca"] == 0.78
    print("  escala que pula a faixa não vira 'serve': ok")


def caso_quando_a_escala_pula_a_busca_tenta_a_mistura():
    """Âncora mais lacaios dá passos menores: é o remédio para a escala grossa."""
    criaturas = [{"nome": f"C{i}", "cr": "2", "meta": {}} for i in range(1, 6)]

    def taxa(nome, q):
        # Sozinha, qualquer uma pula a faixa. Com lacaio ("+" na chave), cai nela.
        if "+" in nome:
            return 0.72
        return 0.95 if q <= 2 else 0.30

    with SimuladorFalso(taxa):
        achadas, _ = S.procurar_composicoes(
            criaturas, (0.65, 0.80), "guerreiro", 4, 1, random.Random(1), 1
        )
    assert achadas and achadas[0]["veredito"] == "serve", achadas
    assert len(achadas[0]["bando"]) == 2, (
        f"a saída tinha que ser uma mistura: {achadas[0]['bando']}"
    )
    print("  escala grossa faz a busca tentar a mistura: ok")


def caso_sem_nenhuma_na_faixa_devolve_o_que_mediu():
    """Dizer 'não achei' sem mostrar o número não ajuda quem escreve."""
    criaturas = [{"nome": f"C{i}", "cr": "1", "meta": {}} for i in range(1, 6)]
    with SimuladorFalso(lambda nome, q: 0.99):
        achadas, _ = S.procurar_composicoes(
            criaturas, (0.45, 0.60), "guerreiro", 4, 1, random.Random(1), 2
        )
    assert achadas, "a busca não devolveu nada, nem o que mediu"
    assert all(a["veredito"] != "serve" for a in achadas)
    print("  sem nada na faixa, devolve o que mediu: ok")


# --------------------------------------------------------- de ponta a ponta


def caso_sugerir_recusa_pedido_torto():
    assert "erro" in S.sugerir(dificuldade="impossivel")
    assert "erro" in S.sugerir(tier=9)
    assert "erro" in S.sugerir(classe="padeiro")
    vazio = S.sugerir(tier=1, tipo="celestial", ambiente="underwater")
    assert "erro" in vazio and vazio.get("dica"), vazio
    print("  sugerir recusa dificuldade, tier, classe e filtro impossível: ok")


def caso_sugerir_mede_de_verdade():
    """Amostra curta com o motor real: contrato e rotulo, sem calibrar balanceamento."""
    anterior = S.CONFRONTOS_DA_BUSCA, S.CONFRONTOS_DA_CONFIRMACAO
    S.CONFRONTOS_DA_BUSCA, S.CONFRONTOS_DA_CONFIRMACAO = 5, 10
    try:
        r = S.sugerir(tier=2, dificuldade="media", semente=7, quantas=1)
    finally:
        S.CONFRONTOS_DA_BUSCA, S.CONFRONTOS_DA_CONFIRMACAO = anterior

    assert "erro" not in r, r
    assert r["semente"] == 7 and r["sugestoes"], r
    # Contra MESAS SORTEADAS, como o estúdio mede. Se o sugeridor calibrasse
    # contra cinco cópias de uma classe, a dificuldade que ele promete e o
    # número que a bancada mostra seriam réguas diferentes — e a faixa
    # "média" valeria só para quem jogasse com cinco guerreiros.
    assert r["classe"] == "sorteado", r["classe"]
    lo, hi = r["faixa"]
    for s in r["sugestoes"]:
        assert s["bando"] and all(p["quantidade"] >= 1 for p in s["bando"])
        assert 0.0 <= s["taxa"] <= 1.0
        # O rotulo nao pode discordar do numero: e a promessa do sugeridor.
        assert s["na_faixa"] == (lo <= s["taxa"] <= hi), s
        assert str(S.GRUPOS_CONFIRMADOS[0]) in s["por_grupo"]
    print(f"  a sugestão veio medida: {r['sugestoes'][0]['taxa']:.0%}: ok")


def caso_a_mesma_semente_da_a_mesma_sugestao():
    anterior = S.CONFRONTOS_DA_BUSCA, S.CONFRONTOS_DA_CONFIRMACAO
    S.CONFRONTOS_DA_BUSCA, S.CONFRONTOS_DA_CONFIRMACAO = 5, 10
    try:
        a = S.sugerir(tier=2, dificuldade="media", semente=99, quantas=1)
        b = S.sugerir(tier=2, dificuldade="media", semente=99, quantas=1)
    finally:
        S.CONFRONTOS_DA_BUSCA, S.CONFRONTOS_DA_CONFIRMACAO = anterior
    assert a["sugestoes"] == b["sugestoes"], "a mesma semente deu sugestão diferente"
    print("  a mesma semente dá a mesma sugestão: ok")


def caso_a_semente_das_mesas_nao_leva_o_bando():
    """Dois bandos diferentes enfrentam AS MESMAS mesas.

    E o que faz a diferenca entre dois numeros ser a diferenca entre dois
    bandos. Levando o bando na semente, o mesmo elenco media 56% ou 75%
    conforme o sorteio — e a bissecao, que depende de a taxa CAIR quando a
    quantidade sobe, bissecava ruido por cima da curva de verdade.

    O tamanho do grupo continua separando, e deve: medir mesa de cinco e de
    tres sao duas perguntas, nao duas amostras da mesma.
    """
    import simular_combate as sc

    vistos = []
    verdadeiro = sc.simular

    def espiao(monstros, tamanho, args, rng):
        vistos.append((rng.random(), getattr(args, "composicoes", None),
                       getattr(args, "minimo_por_mesa", None)))
        return {"taxa": 0.5}

    sc.simular = espiao
    try:
        um = [SimpleNamespace(nome="A")]
        outro = [SimpleNamespace(nome="B") for _ in range(4)]
        S.medir_bando(um, None, 6, 5, 200, 7)
        S.medir_bando(outro, None, 6, 5, 200, 7)
        S.medir_bando(um, None, 6, 3, 200, 7)
    finally:
        sc.simular = verdadeiro

    assert vistos[0][0] == vistos[1][0], "bandos diferentes sortearam mesas diferentes"
    assert vistos[0][0] != vistos[2][0], "o tamanho do grupo tem de separar"

    # E pede as quarenta mesas, nao as doze do padrao: mais confrontos nao
    # compram mesa nenhuma, e e o numero de MESAS que manda no erro da media.
    for _semente, composicoes, minimo in vistos:
        assert composicoes == S.MESAS_SORTEADAS == 40, composicoes
        assert minimo == grupos.MINIMO_PARA_A_MEDIA, minimo
    mesas, por_mesa = grupos.dividir(
        S.CONFRONTOS_DA_CONFIRMACAO, S.MESAS_SORTEADAS, grupos.MINIMO_PARA_A_MEDIA
    )
    assert mesas == 40, (mesas, por_mesa)
    print(f"  as mesas sao as mesmas para todo bando, e sao {mesas}: ok")


def caso_as_faixas_estao_declaradas_como_proposta():
    """Elas não são regra de jogo, e o código tem que dizer isso.

    Nenhuma regra depende delas: mudar a faixa muda o que o sugeridor procura,
    e mais nada. O dia em que alguém calibrar contra o BALANCO.md, é aqui que
    mexe.
    """
    assert set(S.FAIXAS_DE_VITORIA) == {"facil", "media", "dificil"}
    for nome, (lo, hi) in S.FAIXAS_DE_VITORIA.items():
        assert 0.0 < lo < hi <= 1.0, (nome, lo, hi)
    faixas = [S.FAIXAS_DE_VITORIA[n] for n in ("dificil", "media", "facil")]
    assert faixas == sorted(faixas), "as faixas se cruzaram: difícil tem que ser menor"
    fonte = (RAIZ / "tools" / "sugestor.py").read_text(encoding="utf-8")
    assert "CALIBRAÇÃO" in fonte.upper(), (
        "sumiu o aviso de que as faixas são proposta e precisam de calibração"
    )
    print("  as faixas são crescentes e declaradas como proposta: ok")


for caso in (
    caso_a_janela_de_cr_se_estende_na_direcao_da_dificuldade,
    caso_a_janela_dos_extremos_nao_estoura,
    caso_o_nivel_segue_o_tier,
    caso_criatura_sem_ambiente_entra_em_qualquer_ambiente,
    caso_os_tres_filtros_sao_independentes,
    caso_a_faixa_de_cr_manda_sobre_o_tier,
    caso_a_bissecao_acha_a_menor_quantidade_que_cabe,
    caso_a_bissecao_nao_e_varredura,
    caso_o_veredito_fraca_sai_sem_bissecar,
    caso_o_veredito_forte_sai_sem_bissecar,
    caso_a_busca_anda_para_o_lado_que_o_veredito_aponta,
    caso_a_escala_que_pula_a_faixa_nao_vira_serve,
    caso_quando_a_escala_pula_a_busca_tenta_a_mistura,
    caso_sem_nenhuma_na_faixa_devolve_o_que_mediu,
    caso_sugerir_recusa_pedido_torto,
    caso_sugerir_mede_de_verdade,
    caso_a_mesma_semente_da_a_mesma_sugestao,
    caso_a_semente_das_mesas_nao_leva_o_bando,
    caso_as_faixas_estao_declaradas_como_proposta,
):
    caso()

print("TESTES DO SUGESTOR PASSARAM")
