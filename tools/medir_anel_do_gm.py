"""Mede se o Anel do Mestre basta para atravessar uma incursão SOZINHO.

    .venv/Scripts/python.exe tools/medir_anel_do_gm.py

O anel existe para o Mestre ver as telas sem juntar cinco pessoas, então a
pergunta aqui é uma só: **um personagem de um atravessa?** Mede as duas
coisas que uma incursão cobra, com o motor de verdade e nada de conta à mão:

- **as salas de teste**, onde sozinho não há com quem dividir o progresso: um
  único d20 tem de produzir o `alvo_progresso` inteiro contra a CD do tier;
- **os combates**, contra os chefes escritos e contra a criatura de referência
  de cada tier, com o grupo de UM.

Rodar de novo depois de mexer num número do anel diz na hora o que mudou.
"""
from __future__ import annotations

import glob
import json
import random
import statistics as st
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tools"))

from src import bestiario, classes as cl, itens, motor, rules  # noqa: E402
from src.incursoes import Monstro, carregar  # noqa: E402
import simular_combate  # noqa: E402

REPETICOES = 400
LIMITE_RODADAS = 60
RNG = random.Random(20261104)
CLASSE = "guerreiro"


def combatente_com_anel(tier: int, com_anel: bool = True) -> motor.Combatente:
    """O personagem solo do tier, vestindo (ou não) o anel.

    Passa pelo mesmo caminho da ficha: `classes.efeitos` mais
    `itens.juntar_equipamento`, que consolida por `max()` como as passivas.
    """
    nivel = rules.nivel_do_tier(tier)
    numeros = cl.numeros(CLASSE, nivel)
    efeitos = cl.efeitos(CLASSE, nivel, {})
    if com_anel:
        itens.juntar_equipamento(efeitos, [itens.ID_DO_ANEL_DO_GM])
    quem = motor.Combatente(
        user_id=1,
        nome="Mestre",
        ca=numeros.ca + efeitos.get("ca", 0),
        bonus_ataque=numeros.acerto + efeitos.get("acerto", 0),
        dano_arma=numeros.dano,
        hp_max=numeros.hp,
        hp_atual=numeros.hp,
        ataques=efeitos.get("ataques", 1),
        critico_em=efeitos.get("critico_em", 20),
        dano_extra=efeitos.get("dano_extra", 0),
        dano_ferido=efeitos.get("dano_ferido", 0),
        saves=cl.saves(CLASSE, nivel, efeitos),
    )
    # O Escudo Arcano abre o combate com vida temporária, multiplicada pelo
    # tier — é o cog que faz isso, e aqui a conta é a mesma.
    escudo = efeitos.get("escudo_arcano", 0)
    if escudo:
        motor.ganhar_thp(quem, escudo * max(1, tier))
    return quem


# ------------------------------------------------------------- as salas
def salas_de_teste() -> list[dict]:
    """Toda sala com teste dos bancos das Organizações."""
    achadas = []
    for arquivo in sorted(glob.glob(str(RAIZ / "data/bancos/*.json"))):
        for sala in json.load(open(arquivo, encoding="utf-8"))["salas"]:
            if sala.get("cd") and sala.get("alvo_progresso"):
                achadas.append(sala)
    return achadas


def passa_sozinho(tier: int, com_anel: bool) -> tuple[float, int, int]:
    """Fatia das salas que um personagem só vence, no tier.

    A margem de UMA rolagem tem de bater o `alvo_progresso` inteiro: é essa a
    diferença entre jogar sozinho e jogar com cinco.
    """
    nivel = rules.nivel_do_tier(tier)
    numeros = cl.numeros(CLASSE, nivel)
    efeitos = cl.efeitos(CLASSE, nivel, {})
    if com_anel:
        itens.juntar_equipamento(efeitos, [itens.ID_DO_ANEL_DO_GM])
    # A melhor perícia possível: treinada e com o bônus do anel por cima.
    pericias = sorted(rules.PERICIAS)[: numeros.pericias]
    mod = max(
        rules.mod_pericia(p, numeros, pericias, {}, efeitos) for p in pericias
    )
    vitorias = total = 0
    pior = 99
    for sala in salas_de_teste():
        desconto = 0
        cd = sala["cd"] + rules.cd_no_tier(0, tier) - desconto
        alvo = sala["alvo_progresso"]
        total += 1
        # Sem azar nenhum: o 1 natural é o caso que decide se dá para contar
        # com a sala ou se ela depende de sorte.
        if 1 + mod - cd >= alvo:
            vitorias += 1
        pior = min(pior, 1 + mod - cd - alvo)
    return (vitorias / total if total else 0.0), mod, pior


# ---------------------------------------------------------- os combates
#
# O combate NAO e reimplementado aqui: e o mesmo `um_combate` de
# `tools/simular_combate.py`, com iniciativa, atordoamento e habilidade de
# criatura. O grupo e de um.
#
# Ele nao conhece o `thp_ao_derrubar` (quem aplica e o cog, ao fechar o
# turno), entao a medida sai CONSERVADORA: na mesa o anel sustenta um pouco
# mais que isto. Para a pergunta "basta?", errar para o lado pessimista e o
# lado certo.
def medir_combates(monstros, tier, com_anel) -> dict:
    vitorias, rodadas, hp = 0, [], []
    for _ in range(REPETICOES):
        quem = combatente_com_anel(tier, com_anel)
        estado = simular_combate.um_combate(monstros, [quem], RNG)
        if estado.inimigos_derrotados:
            vitorias += 1
            rodadas.append(estado.rodada)
            hp.append(max(0, quem.hp_atual) / quem.hp_max)
    return {
        "taxa": vitorias / REPETICOES,
        "rodadas": st.mean(rodadas) if rodadas else float("nan"),
        "hp": st.mean(hp) if hp else 0.0,
    }


def criatura_de_referencia(tier: int) -> list[Monstro]:
    """A criatura típica do tier, do bestiário — a mesma que o balanço usa."""
    faixa = bestiario.FAIXAS_DE_CR[tier]
    candidatas = [
        c for c in bestiario.carregar()
        if faixa[0] <= bestiario.cr_de(c) <= faixa[1]
    ]
    mediana = sorted(candidatas, key=lambda c: c["hp"])[len(candidatas) // 2]
    # Tres delas: e o que uma sala do caminho costuma por na frente do grupo.
    return [
        Monstro(
            nome=mediana["nome"], ca=mediana["ca"],
            ataque=mediana.get("ataque", 0), dano=mediana.get("dano", "1d6"),
            hp=mediana["hp"],
        )
        for _ in range(3)
    ]


def main() -> int:
    anel = itens.POR_ID[itens.ID_DO_ANEL_DO_GM]
    print(f"# {anel.nome}\n")
    print("Efeitos:", ", ".join(f"{k}={v}" for k, v in sorted(anel.efeito.items())))
    print(f"Fora da vitrine: {not itens.a_venda(anel.id)}\n")

    print("## As salas de teste, sozinho")
    print("(a margem de UMA rolagem tem de dar o alvo_progresso inteiro)\n")
    print("| tier | mod. de perícia | salas vencidas | folga no 1 natural |")
    print("|---|---|---|---|")
    for tier in range(1, 6):
        taxa, mod, pior = passa_sozinho(tier, True)
        sem, mod_sem, _ = passa_sozinho(tier, False)
        print(f"| {tier} | {mod:+d} (sem o anel: {mod_sem:+d}) | "
              f"{taxa:.0%} (sem: {sem:.0%}) | {pior:+d} |")

    print("\n## Os combates, grupo de UM")
    print(f"({REPETICOES} por linha, com o motor de verdade)\n")
    print("| tier | criatura | vitória | rodadas | HP no fim |")
    print("|---|---|---|---|---|")
    for tier in range(1, 6):
        monstros = criatura_de_referencia(tier)
        r = medir_combates(monstros, tier, True)
        s = medir_combates(monstros, tier, False)
        nome = f"{len(monstros)}× {monstros[0].nome}"
        print(f"| {tier} | {nome} | {r['taxa']:.0%} (sem o anel: {s['taxa']:.0%}) | "
              f"{r['rodadas']:.1f} | {r['hp']:.0%} |")

    print("\n## Os chefes escritos, grupo de UM\n")
    print("| incursão | tier | chefe | vitória | rodadas | HP no fim |")
    print("|---|---|---|---|---|---|")
    for arquivo in sorted(glob.glob(str(RAIZ / "data/incursoes/*.json"))):
        incursao = carregar(Path(arquivo))
        tier = incursao.tier or 1
        objetivo = incursao.objetivo
        monstros = objetivo.monstros_do_tier(tier)
        if not monstros:
            continue
        r = medir_combates(monstros, tier, True)
        contagem: dict[str, int] = {}
        for m in monstros:
            contagem[m.nome] = contagem.get(m.nome, 0) + 1
        quem = ", ".join(
            f"{n}× {nome}" if n > 1 else nome for nome, n in contagem.items()
        )
        print(f"| {incursao.nome} | {tier} | {quem} | {r['taxa']:.0%} | "
              f"{r['rodadas']:.1f} | {r['hp']:.0%} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
