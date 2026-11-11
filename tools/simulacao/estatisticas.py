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
