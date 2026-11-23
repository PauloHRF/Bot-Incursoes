"""Agregacao das mesmas medidas para os dois comandos e o Estudio."""
from collections import Counter
import math
import statistics


def intervalo(vitorias, amostras):
    """Wilson de 95%, em fracao; nao mede incerteza sobre builds/encontros."""
    if amostras < 1 or not 0 <= vitorias <= amostras:
        raise ValueError("Informe amostras positivas e vitorias entre zero e o total.")
    p, z = vitorias / amostras, 1.95996398454
    d = 1 + z * z / amostras
    centro = (p + z * z / (2 * amostras)) / d
    erro = z * math.sqrt(p * (1 - p) / amostras + z * z / (4 * amostras**2)) / d
    return min(p, max(0., centro - erro)), max(p, min(1., centro + erro))


def mesa_azarada(composicoes) -> float:
    """A taxa da PIOR formação medida: "o grupo que mais sofreu tirou isto".

    É o mínimo, e isso mudou de resposta junto com o método. Enquanto as
    mesas eram SORTEADAS o mínimo não servia: ele estima o pior da população,
    que não tem fundo, então sortear mais mesas só o empurrava para baixo e
    dois mínimos de amostras de tamanhos diferentes não se comparavam — a
    mesma emboscada "piorou" de 93% para 80% só por ter sido medida com mais
    mesas. O décimo percentil resolvia isso porque estimava a mesma coisa em
    qualquer tamanho de amostra.

    Com o catálogo de formações FIXO (`grupos.json`) não há amostragem: as
    formações são a população inteira, sempre as mesmas, e o mínimo passa a
    ser exatamente o que se quer — a pior das que existem, comparável entre
    duas medições porque o catálogo não muda.

    E o percentil passou a MENTIR. `statistics.quantiles` é *exclusive*: ele
    estima o percentil de uma população a partir de uma amostra, e extrapola
    para fora dos dados quando o decil pedido fica abaixo de `1/(n+1)`. Com
    doze ou quarenta mesas, 0,1 ficava dentro. Com QUATRO formações, 0,1 <
    0,2 e ele extrapolava abaixo da pior: formações em 100/100/100/30% viravam
    "pior mesa: -5%", e 100/100/100/0% viravam **-50%**. Uma taxa de vitória
    negativa, na tela do autor e no veredito da emboscada.

    O nome fica por continuidade (ele aparece no Estúdio e no calibrador), mas
    leia "a pior formação", não "uma em dez": com catálogo fixo não existe
    frequência de encontrar essa mesa no jogo.
    """
    taxas = [c["taxa"] for c in composicoes]
    return min(taxas) if taxas else 1.0


def resumir(resultados):
    if not resultados:
        raise ValueError("Nenhum combate para resumir.")
    n = len(resultados)
    vitorias = sum(r["inimigos_derrotados"] for r in resultados)
    def media(chave):
        return statistics.mean(r[chave] for r in resultados)
    def total(chave):
        return sum(r[chave] for r in resultados)
    habilidades, reacoes, recursos = {}, Counter(), Counter()
    for r in resultados:
        reacoes.update(r["reacoes"])
        for nome, valores in r["habilidades_usadas"].items():
            item = habilidades.setdefault(nome, Counter())
            item.update(valores)
            recursos[nome] += valores["recursos"]
        recursos.update(r["reacoes"])
    lo, hi = intervalo(vitorias, n)
    return {
        "taxa": vitorias / n, "ic95": [lo, hi], "amostras": n, "vitorias": vitorias,
        "rodadas": media("rodadas"), "caidos": media("caidos"),
        "cura": media("cura"), "recursos": media("recursos"), "dano": media("dano"),
        "recebido": media("recebido"), "ataques_basicos": media("ataques_basicos"),
        "thp_gerado": media("thp_gerado"), "thp_restante": media("thp_restante"),
        "thp_gasto": media("thp_gasto"), "quedas_distintas": media("personagens_derrubados"),
        "turnos_caidos": total("turnos_caidos"),
        "turnos_inimigos_atordoados": total("turnos_inimigos_atordoados"),
        "limites": total("limite_rodadas"), "habilidades": habilidades,
        "dano_periodico": total("dano_periodico"), "cura_passiva": total("cura_passiva"),
        "turnos_perdidos": total("turnos_perdidos"), "quedas_antes_de_agir": total("quedas_antes_de_agir"),
        "reacoes": dict(reacoes), "recursos_habilidade": dict(recursos),
        "hp_restante_pct": statistics.mean(100*r["hp_restante"]/r["hp_inicial"] for r in resultados),
    }
