"""Sugere o bando de uma sala de combate, por ambiente, tipo de bicho e dificuldade.

    python tools/sugestor.py --tier 2 --ambiente underdark --dificuldade media
    python tools/sugestor.py --tier 3 --tipo undead --dificuldade dificil --classe mago

A DIFICULDADE NÃO É DECLARADA, É MEDIDA. Sala de combate não tem campo de
dificuldade no formato, e não é descuido: num combate quem decide a
dificuldade são as criaturas. Então aqui "Média" não é um rótulo que o
sugeridor escreve — é uma FAIXA DE TAXA DE VITÓRIA que ele procura, simulando
com o motor do bot, e o número que ele devolve é o que ele mediu.

Como a busca anda: a taxa de vitória cai conforme a quantidade sobe, então
para cada criatura dá para achar a quantidade certa por bisseção, em três
medições em vez de seis. As escolhidas são confirmadas depois com mais
confrontos — a busca usa amostra pequena de propósito, e amostra pequena é boa
para ordenar e ruim para publicar.

O que ele NÃO faz: escolher por você. Ele devolve as composições que caíram na
faixa, com o número medido ao lado, e quem decide o que combina com a ficção
da sala é quem escreve.
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import bestiario, classes, incursoes as I  # noqa: E402
from src.rules import TIER_MAXIMO  # noqa: E402
from tools.simulacao import grupos  # noqa: E402

# A faixa de taxa de vitória de cada dificuldade, para um grupo de 5 no tier
# da sala — hoje MESAS SORTEADAS, e não cinco cópias de uma classe. A faixa
# não mudou com isso (ela é alvo, não medida), mas o que ela significa sim:
# "média" passou a querer dizer 65–80% contra a mesa que vai aparecer, e não
# contra a mesa mais forte que dava para montar.
#
# ESTES NÚMEROS SÃO PROPOSTA E PRECISAM DE CALIBRAÇÃO contra docs/BALANCO.md.
# O método é que não é proposta: a sugestão se verifica simulando a si mesma,
# com o mesmo motor que roda o combate de verdade. Mudar a faixa aqui muda o
# que o sugeridor procura, e nada mais — nenhuma regra do jogo depende dela.
FAIXAS_DE_VITORIA = {
    "facil": (0.85, 0.95),
    "media": (0.65, 0.80),
    "dificil": (0.45, 0.60),
}

# Quantas criaturas diferentes entram na busca. Cada uma custa ~3 simulações
# de bisseção, então este número é o que decide se o botão responde em
# segundos ou em minutos.
CANDIDATAS_NA_BUSCA = 4

# Quantas misturas (uma âncora mais lacaios) entram junto. São as mais
# caras da busca e as que alcançam faixa que criatura sozinha pula.
MISTURAS_NA_BUSCA = 2

# Confrontos por medição. A busca mede barato para ORDENAR; a confirmação mede
# caro para PUBLICAR. Misturar os dois daria um número bonito e instável.
CONFRONTOS_DA_BUSCA = 200
CONFRONTOS_DA_CONFIRMACAO = 400

# Quantas mesas sortear, e com que piso de lutas por mesa.
#
# QUARENTA, e não as doze do padrão, porque o sorteio das mesas é a maior
# fonte de erro da média — e mais confrontos não compravam mesa nenhuma: com
# doze mesas, 200 confrontos dão 12×16 e 600 dão 12×50, e o erro fica igual.
# Medido no mesmo bando com seis sorteios diferentes, pelo MESMO custo de 400
# lutas: doze mesas de 33 espalharam 19 pontos de taxa (56% a 75%), quarenta
# mesas de 10 espalharam 9 (61% a 70%). A faixa "média" tem 15 pontos de
# largura, então 19 de erro não é detalhe: é o bando inteiro mudando de
# dificuldade conforme quem sentou.
#
# O piso cai para dez porque este comando publica a MÉDIA, e o piso de quinze
# existe para proteger o número de UMA mesa (ver `grupos.dividir`).
MESAS_SORTEADAS = 40

# Os tamanhos que a confirmação reporta. Três é a mesa comum e cinco é o
# grupo cheio: a distância entre os dois diz mais que qualquer dos dois.
GRUPOS_CONFIRMADOS = (5, 3)


def janela_de_cr(tier: int, dificuldade: str) -> tuple[float, float]:
    """Por qual faixa de CR procurar, dado o tier e a dificuldade pedida.

    MAIS LARGA que a faixa do tier, de propósito. `FAIXAS_DE_CR` descreve a
    criatura TÍPICA daquele tier, e uma luta difícil legitimamente traz algo
    de cima dela — um chefe não é a criatura típica.

    Sem essa folga o tier 1 não consegue montar luta difícil nenhuma: seis
    criaturas de CR 1, que é o teto da faixa dele, não ameaçam cinco
    jogadores de nível 2. A medição dizia 100% de vitória em toda tentativa,
    e o sugeridor só sabia responder "não achei".
    """
    lo, hi = bestiario.FAIXAS_DE_CR[tier]
    acima = bestiario.FAIXAS_DE_CR.get(tier + 1, (hi, hi))
    abaixo = bestiario.FAIXAS_DE_CR.get(tier - 1, (lo, lo))
    return {
        "facil": (abaixo[0], hi),
        "media": (lo, hi),
        "dificil": (lo, acima[1]),
    }[dificuldade]


def nivel_do_tier(tier: int) -> int:
    """O nível do grupo que joga aquele tier: dois níveis por tier, teto em 10."""
    return max(1, min(10, tier * 2))


def _monstros(nome: str, quantidade: int) -> list:
    """O bando, pelo mesmo caminho que o conteúdo usa para chamar pelo nome."""
    return I.monstros_de_criatura(
        {"nome": nome, "quantidade": quantidade}, "sugestor"
    )


def medir_bando(
    monstros: list, classe: Optional[str], nivel: int, tamanho: int,
    confrontos: int, semente: Any,
) -> Optional[float]:
    """A taxa de vitória daquele bando contra um grupo daquele tamanho.

    **A semente não leva o bando.** Todos os candidatos — e todos os pontos
    da bisseção — enfrentam AS MESMAS mesas, e aí a diferença entre dois
    números é a diferença entre dois bandos.

    Levava, e era o pior defeito deste arquivo: o mesmo bando media 56% ou
    75% conforme o sorteio, e a bisseção abaixo depende de a taxa CAIR quando
    a quantidade sobe. Com mesas próprias para cada ponto, a curva que ela
    bissecava era ruído por cima da curva de verdade — é a mesma lição que
    `tools/calibrar_emboscada.py` tem escrita no corpo: comparar cada
    candidato contra mesas próprias é comparar duas amostras, não dois bandos.
    """
    import simular_combate as sc

    if not monstros:
        return None
    args = SimpleNamespace(classe=classe or None, nivel=nivel, repeticoes=confrontos,
                           coletar_detalhes=False, composicoes=MESAS_SORTEADAS,
                           minimo_por_mesa=grupos.MINIMO_PARA_A_MEDIA)
    bruto = sc.simular(
        monstros, tamanho, args, random.Random(f"{semente}:{tamanho}")
    )
    return bruto["taxa"]


def _melhor_na_escala(
    montar, faixa: tuple[float, float], classe: str, nivel: int,
    semente: Any, menor_valor: int, maior_valor: int,
) -> tuple[Optional[int], Optional[float], str]:
    """O ponto da escala que cai na faixa, e o veredito da busca.

    Devolve (ponto, taxa, veredito), com veredito em: "serve" quando a faixa
    foi alcancada, "fraca" quando nem o bando cheio desce do teto, "forte"
    quando ate um sozinho fica abaixo do piso, "nao_monta" quando a criatura
    nao vira ficha.

    `montar(n)` devolve o bando daquele ponto, e a taxa de vitória CAI
    conforme `n` sobe — mais criaturas, luta mais dura. Por isso isto é
    bisseção e não varredura: três medições em vez de seis.

    A taxa devolvida é a MEDIDA NA BUSCA, com amostra pequena de propósito:
    ela serve para ordenar candidatas, e não para publicar. Quem publica é a
    confirmação, com mais confrontos.
    """
    piso, teto = faixa
    medidas: dict[int, float] = {}

    def taxa(n: int) -> Optional[float]:
        if n not in medidas:
            valor = medir_bando(
                montar(n), classe, nivel, 5, CONFRONTOS_DA_BUSCA, semente,
            )
            if valor is None:
                return None
            medidas[n] = valor
        return medidas[n]

    # Os dois extremos primeiro, e é isto que separa busca de adivinhação: se
    # a escala inteira está acima do teto, a criatura é fraca demais para esta
    # dificuldade; se está abaixo do piso, é forte demais. Nos dois casos não
    # existe quantidade que sirva, e bissecar seria gastar medição para
    # descobrir no fim o que dois tiros dizem no começo.
    mais_fraco, mais_forte = taxa(menor_valor), taxa(maior_valor)
    if mais_fraco is None or mais_forte is None:
        return None, None, "nao_monta"
    if mais_forte > teto:
        return maior_valor, mais_forte, "fraca"
    if mais_fraco < piso:
        return menor_valor, mais_fraco, "forte"

    menor, maior, achado = menor_valor, maior_valor, maior_valor
    while menor <= maior:
        meio = (menor + maior) // 2
        atual = taxa(meio)
        if atual is None:
            return None, None, "nao_monta"
        if atual <= teto:
            achado = meio
            maior = meio - 1
        else:
            menor = meio + 1

    # A bisseção procurou o TETO. Falta olhar o PISO, e isto não é detalhe:
    # a escala é de números inteiros, então ela pode pular a faixa inteira
    # entre duas quantidades — 95% com três criaturas, 43% com quatro. Sem
    # esta conferência o sugeridor chamava os 43% de "serve" e entregava
    # como Média um combate que mata o grupo mais da metade das vezes.
    if medidas[achado] < piso:
        return achado, medidas[achado], "pula"
    return achado, medidas[achado], "serve"


def composicao_de_uma(
    nome: str, faixa, classe: str, nivel: int, semente: Any
) -> Optional[dict[str, Any]]:
    """N criaturas iguais. A composição mais simples, e a mais comum."""
    quantidade, taxa, veredito = _melhor_na_escala(
        lambda q: _monstros(nome, q),
        faixa, classe, nivel, semente, 1, I.MAX_INIMIGOS,
    )
    if quantidade is None:
        return None
    return {
        "bando": [{"nome": nome, "quantidade": quantidade}],
        "taxa_da_busca": taxa,
        "veredito": veredito,
    }


def composicao_com_ancora(
    ancora: str, lacaio: str, faixa, classe: str, nivel: int, semente: Any
) -> Optional[dict[str, Any]]:
    """Uma âncora mais N lacaios.

    Existe porque a escala de uma criatura só é GROSSA: entre cinco e seis
    cópias a taxa pode pular a faixa inteira, e aí não há composição possível
    naquela dificuldade. Trocar parte do bando por uma criatura mais fraca dá
    passos menores — e é também a forma de encontro que o bestiário descreve,
    com `meta.funcao` separando Âncora de Minion.
    """
    def montar(k: int) -> list:
        return _monstros(ancora, 1) + _monstros(lacaio, k)

    quantos, taxa, veredito = _melhor_na_escala(
        montar,
        faixa, classe, nivel, semente, 1, I.MAX_INIMIGOS - 1,
    )
    if quantos is None:
        return None
    return {
        "bando": [
            {"nome": ancora, "quantidade": 1},
            {"nome": lacaio, "quantidade": quantos},
        ],
        "taxa_da_busca": taxa,
        "veredito": veredito,
    }


def _mistura_com(
    por_cr: list[dict[str, Any]], indice: int, faixa, classe: str, nivel: int,
    semente: Any, sorteio: random.Random,
):
    """Uma âncora daquele índice, com lacaios tirados do terço mais fraco."""
    ancora = por_cr[indice]["nome"]
    fracas = [c for c in por_cr[: max(1, len(por_cr) // 3)] if c["nome"] != ancora]
    if not fracas:
        return None
    return composicao_com_ancora(
        ancora, sorteio.choice(fracas)["nome"], faixa, classe, nivel, semente
    )


def procurar_composicoes(
    achadas: list[dict[str, Any]], faixa, classe: str, nivel: int,
    semente: Any, sorteio: random.Random, quantas: int,
) -> tuple[list[dict[str, Any]], int]:
    """Procura, na lista inteira de criaturas, as que alcançam a faixa.

    Isto é BUSCA e não amostragem, e a diferença é o que faz o sugeridor
    acertar. O espaço é uma grade de duas dimensões — qual criatura, e quantas
    — e ele é monótono nas duas: mais criaturas é mais difícil, e criatura de
    CR maior é mais difícil. Grade monótona se busca por bisseção.

    Em cada criatura provada, `_melhor_na_escala` mede os dois extremos antes
    de qualquer outra coisa e devolve um veredito. "fraca" quer dizer que nem
    o bando cheio desce do teto: é preciso ir para CR MAIOR. "forte" quer
    dizer que até uma sozinha fica abaixo do piso: é preciso ir para CR MENOR.
    Só quando a faixa está cercada é que vale bissecar a quantidade.

    Antes isto era palpite — "procure o fácil entre as fracas", depois
    "comece sempre pelas fortes", depois "espalhe pela janela" — e cada
    palpite acertava um tier e errava outro, porque a força relativa muda com
    o tier e com a classe do grupo. Medir dois pontos e deixar o veredito
    apontar a direção custa o mesmo e não depende de adivinhação.
    """
    por_cr = sorted(achadas, key=bestiario.cr_de)
    medicoes = 0
    menor, maior, centro = 0, len(por_cr) - 1, None
    perto: list[dict[str, Any]] = []

    while menor <= maior:
        meio = (menor + maior) // 2
        achada = composicao_de_uma(
            por_cr[meio]["nome"], faixa, classe, nivel, semente
        )
        medicoes += 1
        if achada is None:
            menor = meio + 1
            continue
        if achada["veredito"] == "serve":
            centro = meio
            break
        if achada["veredito"] == "pula":
            # A escala desta criatura salta por cima da faixa. É exatamente
            # para isso que serve a mistura: trocar parte do bando por algo
            # mais fraco dá passos menores dentro da mesma faixa.
            mistura = _mistura_com(
                por_cr, meio, faixa, classe, nivel, semente, sorteio
            )
            medicoes += 1
            if mistura and mistura["veredito"] == "serve":
                return [mistura], medicoes
            perto.append(achada)
            maior = meio - 1
            continue
        perto.append(achada)
        if achada["veredito"] == "fraca":
            menor = meio + 1
        else:
            maior = meio - 1

    if centro is None:
        # A faixa não é alcançável com uma criatura só desta janela. As
        # provadas viram resposta mesmo assim, com o número delas ao lado:
        # dizer "não achei" sem mostrar o que mediu não ajuda ninguém.
        return perto[:quantas], medicoes

    encontradas = []
    for passo in range(len(por_cr)):
        for indice in {centro - passo, centro + passo}:
            if not 0 <= indice < len(por_cr) or len(encontradas) >= quantas:
                continue
            achada = composicao_de_uma(
                por_cr[indice]["nome"], faixa, classe, nivel, semente
            )
            medicoes += 1
            if achada and achada["veredito"] == "serve":
                encontradas.append(achada)
        if len(encontradas) >= quantas:
            break

    # Uma mistura junto: a escala de uma criatura só é grossa, e âncora mais
    # lacaios dá passos menores dentro da mesma faixa.
    if encontradas and len(por_cr) > 1:
        mistura = _mistura_com(por_cr, centro, faixa, classe, nivel, semente, sorteio)
        medicoes += 1
        if mistura and mistura["veredito"] == "serve":
            encontradas.append(mistura)

    return encontradas or perto[:quantas], medicoes


def sugerir(
    tier: int = 2,
    ambiente: Optional[str] = None,
    tipo: Optional[str] = None,
    dificuldade: str = "media",
    classe: Optional[str] = None,
    nivel: Optional[int] = None,
    quantas: int = 3,
    semente: Optional[int] = None,
) -> dict[str, Any]:
    """Composições que caem na faixa daquela dificuldade, com o número medido."""
    if dificuldade not in FAIXAS_DE_VITORIA:
        return {"erro": f"dificuldade '{dificuldade}' não existe. "
                        f"Use {', '.join(FAIXAS_DE_VITORIA)}."}
    if not 1 <= tier <= TIER_MAXIMO:
        return {"erro": f"tier precisa ir de 1 a {TIER_MAXIMO}."}
    # Sem classe o grupo e sorteado, que e o padrao: cinco copias da mesma
    # classe nao e uma mesa que existe. Com classe, o sugeridor vira
    # diagnostico — "que bando serve para um grupo SO de magos?".
    if classe and classes.classe(classe) is None:
        return {"erro": f"classe desconhecida: {classe}."}

    faixa = FAIXAS_DE_VITORIA[dificuldade]
    nivel = nivel or nivel_do_tier(tier)
    semente = semente if isinstance(semente, int) else random.randrange(1, 10**8)

    janela = janela_de_cr(tier, dificuldade)
    achadas = bestiario.candidatas(ambiente, tipo, faixa_cr=janela)
    if not achadas:
        return {
            "erro": "nenhuma criatura do bestiário passa nestes três filtros.",
            "dica": "Afrouxe o tipo de bicho primeiro: ele é o que mais corta.",
            "semente": semente,
        }

    # Amostra semeada: a mesma semente dá as mesmas candidatas, e sementes
    # diferentes dão variedade a quem pedir de novo.
    sorteio = random.Random(f"{semente}:candidatas")

    fichas = {c["nome"]: c for c in achadas}
    buscadas, medicoes = procurar_composicoes(
        achadas, faixa, classe, nivel, semente, sorteio, quantas
    )
    for achada in buscadas:
        for parte in achada["bando"]:
            fichas.setdefault(parte["nome"], {})

    # Perto do meio da faixa primeiro: e o que o autor pediu, e nao o extremo.
    meio = sum(faixa) / 2
    buscadas.sort(
        key=lambda b: (b["veredito"] != "serve", abs(b["taxa_da_busca"] - meio))
    )

    sugestoes = []
    for candidata in buscadas[:quantas]:
        bando = candidata["bando"]
        monstros = []
        for parte in bando:
            monstros.extend(_monstros(parte["nome"], parte["quantidade"]))
        medidas = {
            tamanho: medir_bando(
                monstros, classe, nivel, tamanho,
                CONFRONTOS_DA_CONFIRMACAO, semente,
            )
            for tamanho in GRUPOS_CONFIRMADOS
        }
        taxa = medidas[GRUPOS_CONFIRMADOS[0]]
        sugestoes.append({
            "veredito_da_busca": candidata["veredito"],
            "bando": [
                {
                    **parte,
                    "cr": (fichas.get(parte["nome"]) or {}).get("cr"),
                    "tipo": ((fichas.get(parte["nome"]) or {}).get("meta") or {}).get("tipo"),
                    "funcao": ((fichas.get(parte["nome"]) or {}).get("meta") or {}).get("funcao") or [],
                }
                for parte in bando
            ],
            "taxa": taxa,
            "por_grupo": {str(k): v for k, v in medidas.items()},
            "na_faixa": taxa is not None and faixa[0] <= taxa <= faixa[1],
            "confrontos": CONFRONTOS_DA_CONFIRMACAO,
        })

    # Reordena DEPOIS de medir: a busca ordenou pela amostra pequena, e a
    # confirmacao e que vale. Quem caiu na faixa vem primeiro, e dentro dela
    # quem ficou mais perto do meio.
    meio_da_faixa = sum(faixa) / 2
    sugestoes.sort(
        key=lambda x: (
            not x["na_faixa"],
            abs((x["taxa"] if x["taxa"] is not None else 0) - meio_da_faixa),
        )
    )

    return {
        "tier": tier,
        "ambiente": ambiente,
        "tipo": tipo,
        "dificuldade": dificuldade,
        "faixa": list(faixa),
        "classe": classe or "sorteado",
        "nivel": nivel,
        "semente": semente,
        "janela_de_cr": list(janela),
        "candidatas_no_bestiario": len(achadas),
        "sugestoes": sugestoes,
        "nenhuma_na_faixa": bool(sugestoes) and not any(
            s["na_faixa"] for s in sugestoes
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tier", type=int, default=2)
    parser.add_argument("--ambiente", default=None,
                        help="um de: " + ", ".join(bestiario.AMBIENTES))
    parser.add_argument("--tipo", default=None, help="o meta.tipo do bestiário")
    parser.add_argument("--dificuldade", default="media",
                        choices=sorted(FAIXAS_DE_VITORIA))
    parser.add_argument("--classe", default=None,
                        help="mede contra um grupo de UMA classe; sem isto, sorteado")
    parser.add_argument("--nivel", type=int, default=None)
    parser.add_argument("--quantas", type=int, default=3)
    parser.add_argument("--semente", type=int, default=None)
    args = parser.parse_args()

    r = sugerir(
        tier=args.tier, ambiente=args.ambiente, tipo=args.tipo,
        dificuldade=args.dificuldade, classe=args.classe, nivel=args.nivel,
        quantas=args.quantas, semente=args.semente,
    )
    if "erro" in r:
        print(r["erro"])
        if r.get("dica"):
            print(f"  {r['dica']}")
        return 1

    lo, hi = r["faixa"]
    print(
        f"{r['dificuldade']} no tier {r['tier']}: procurando taxa entre "
        f"{lo:.0%} e {hi:.0%} para um grupo de 5."
    )
    print(
        f"{r['candidatas_no_bestiario']} criatura(s) passam nos filtros; "
        f"grupo simulado: {r['classe']} nível {r['nivel']}; semente {r['semente']}."
    )
    print()
    for s in r["sugestoes"]:
        marca = "  " if s["na_faixa"] else "~ "
        partes = [
            f"{p['quantidade']} × {p['nome']} (CR {p['cr']}, {p['tipo']})"
            for p in s["bando"]
        ]
        print(marca + "  +  ".join(partes))
        for tamanho, taxa in s["por_grupo"].items():
            print(f"      grupo {tamanho}: {taxa:.0%}")
    if r["nenhuma_na_faixa"]:
        print()
        print(
            "Nenhuma caiu DENTRO da faixa — as de cima são as mais próximas, "
            "marcadas com ~. Com filtros apertados pode não existir composição "
            "nessa dificuldade; afrouxe o tipo de bicho ou mude o tier."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
