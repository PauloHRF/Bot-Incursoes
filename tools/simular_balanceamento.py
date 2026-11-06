"""Simulador Monte Carlo de combate para auditoria de balanceamento.

Uso:
    python tools/simular_balanceamento.py
    python tools/simular_balanceamento.py --simulacoes 5000 --tier 5
    python tools/simular_balanceamento.py --classe patrulheiro --tier 3

O teste usa as rolagens e a resolução de ataques do motor real. Cada cenário
forma um grupo de cinco personagens da mesma classe contra uma criatura
sorteada da faixa de CR do tier. Passivas numéricas entram; habilidades ativas,
magias, cura, condições, lendárias e traços especiais dos monstros ficam fora.
Portanto, é uma linha de base comparável, não uma reprodução completa de uma
incursão jogada no Discord.
"""
from __future__ import annotations

import argparse
import csv
import random
import statistics
import sys
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import ameaca, bestiario, classes, motor, rules  # noqa: E402


GRUPO = 5
MAX_RODADAS = 40
CLASSES = tuple(classes.CLASSES)


def monstros_do_tier(tier: int) -> list[dict]:
    """Retorna criaturas reais do bestiário na faixa de CR do tier."""
    minimo, maximo = bestiario.FAIXAS_DE_CR[tier]
    criaturas = [
        c for c in bestiario.carregar()
        if minimo <= bestiario.cr_de(c) <= maximo and c.get("golpes")
    ]
    if not criaturas:
        raise RuntimeError(
            f"Nenhuma criatura com golpes encontrada para o tier {tier}. "
            "Confira data/bestiario.json."
        )
    return criaturas


def montar_grupo(classe_id: str, tier: int) -> list[motor.Combatente]:
    """Monta cinco fichas usando a tabela e as passivas reais da classe."""
    nivel = rules.nivel_do_tier(tier)
    numeros = classes.numeros(classe_id, nivel)
    efeitos = classes.efeitos(classe_id, nivel)

    grupo = []
    for indice in range(GRUPO):
        grupo.append(
            motor.Combatente(
                user_id=indice + 1,
                nome=f"{classe_id}-{indice + 1}",
                ca=numeros.ca + efeitos.get("ca", 0),
                bonus_ataque=numeros.acerto + efeitos.get("acerto", 0),
                dano_arma=numeros.dano,
                hp_max=numeros.hp,
                hp_atual=numeros.hp,
                ataques=efeitos.get("ataques", 1),
                critico_em=efeitos.get("critico_em", 20),
                dano_extra=efeitos.get("dano_extra", 0),
                dano_ferido=efeitos.get("dano_ferido", 0),
                dano_bonus=efeitos.get("dano_bonus", ""),
                reducao_dano=efeitos.get("reducao_dano", 0.0),
                ameaca=ameaca.inicial(classe_id) + efeitos.get("ameaca", 0),
                classe=classe_id,
                saves=classes.saves(classe_id, nivel, efeitos),
            )
        )
    return grupo


def montar_inimigo(dados: dict, indice: int = 0) -> motor.Inimigo:
    """Adapta ataques básicos do bestiário ao modelo de combate do motor."""
    golpes = dados.get("golpes") or []
    quantidade = max(1, int((dados.get("meta") or {}).get("num_acoes") or 1))
    sequencia = golpes[:quantidade] or golpes[:1]
    ataques = [
        SimpleNamespace(
            nome=str(g.get("nome") or dados.get("nome") or "Ataque"),
            ataque=int(g.get("ataque", 0)),
            dano=str(g.get("dano") or "1"),
            efeito=None,
        )
        for g in sequencia
    ]
    primeiro = sequencia[0]
    return motor.Inimigo(
        indice=indice,
        nome=str(dados.get("nome") or "Criatura"),
        ca=int(dados.get("ca") or 10),
        ataque=int(primeiro.get("ataque", 0)),
        dano=str(primeiro.get("dano") or "1"),
        hp_max=max(1, int(dados.get("hp") or 1)),
        hp_atual=max(1, int(dados.get("hp") or 1)),
        saves=dados.get("saves") or {},
        ataques=len(ataques),
        golpes=ataques,
        matilha=bool(dados.get("matilha")),
        regeneracao=int(dados.get("regeneracao") or 0),
    )


def simular_uma_luta(
    classe_id: str, tier: int, rng: random.Random, pool: list[dict]
) -> dict:
    """Executa uma luta completa com a ordem e as funções do motor."""
    grupo = montar_grupo(classe_id, tier)
    inimigo = montar_inimigo(rng.choice(pool))
    estado = motor.EstadoCombate([inimigo], rodada=1, combatentes=grupo)
    dano_grupo = 0
    rodadas = 0

    while not estado.encerrado and rodadas < MAX_RODADAS:
        rodadas += 1

        # Ordem documentada no motor: personagens agem antes das criaturas.
        for personagem in estado.ativos:
            if inimigo.caido:
                break
            for _ in range(max(1, personagem.ataques)):
                if inimigo.caido:
                    break
                golpe = motor.atacar_inimigo(personagem, inimigo, rng)
                dano_grupo += golpe.dano
            # A ameaça é gerada pela ação do personagem, não por cada golpe.
            personagem.ameaca_gerada += ameaca.gerada_por(personagem.classe)

        if estado.encerrado:
            break

        estado.rodada = rodadas
        motor.rodada_dos_inimigos(estado, rng)

        # Efeitos de atordoamento duram uma rodada neste cenário básico.
        for personagem in grupo:
            personagem.atordoado = False

    venceu = inimigo.caido
    hp_restante = sum(max(0, c.hp_atual) for c in grupo)
    hp_total = sum(c.hp_max for c in grupo)
    return {
        "venceu": venceu,
        "rodadas": rodadas,
        "dano_grupo": dano_grupo,
        "hp_restante_pct": 100 * hp_restante / max(1, hp_total),
        "personagens_caidos": sum(c.caido for c in grupo),
        "inimigo": inimigo.nome,
        "limite_atingido": not estado.encerrado,
    }


def medir(classe_id: str, tier: int, simulacoes: int, rng: random.Random) -> dict:
    pool = monstros_do_tier(tier)
    resultados = [
        simular_uma_luta(classe_id, tier, rng, pool)
        for _ in range(simulacoes)
    ]
    return {
        "classe": classe_id,
        "tier": tier,
        "simulacoes": simulacoes,
        "vitoria_pct": round(
            100 * sum(r["venceu"] for r in resultados) / simulacoes, 2
        ),
        "rodadas_media": round(
            statistics.mean(r["rodadas"] for r in resultados), 2
        ),
        "dano_grupo_rodada": round(
            statistics.mean(
                r["dano_grupo"] / max(1, r["rodadas"]) for r in resultados
            ), 2
        ),
        "hp_restante_pct": round(
            statistics.mean(r["hp_restante_pct"] for r in resultados), 2
        ),
        "caidos_media": round(
            statistics.mean(r["personagens_caidos"] for r in resultados), 2
        ),
        "limite_40_rodadas_pct": round(
            100 * sum(r["limite_atingido"] for r in resultados) / simulacoes, 2
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simulacoes", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20261106)
    parser.add_argument("--tier", type=int, choices=range(1, 6))
    parser.add_argument("--classe", choices=CLASSES)
    parser.add_argument("--csv", type=Path, help="Grava os resultados neste CSV.")
    args = parser.parse_args()

    if args.simulacoes < 1:
        parser.error("--simulacoes precisa ser maior que zero")

    tiers = [args.tier] if args.tier else range(1, 6)
    classes_alvo = [args.classe] if args.classe else CLASSES
    rng = random.Random(args.seed)
    resultados = []

    for tier in tiers:
        for classe_id in classes_alvo:
            resultado = medir(classe_id, tier, args.simulacoes, rng)
            resultados.append(resultado)
            print(
                f"T{tier} {classe_id:12} "
                f"vitórias={resultado['vitoria_pct']:6.2f}% "
                f"dano/rod={resultado['dano_grupo_rodada']:7.2f} "
                f"HP restante={resultado['hp_restante_pct']:6.2f}% "
                f"caídos={resultado['caidos_media']:.2f}"
            )

    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", newline="", encoding="utf-8-sig") as arquivo:
            escritor = csv.DictWriter(arquivo, fieldnames=list(resultados[0]))
            escritor.writeheader()
            escritor.writerows(resultados)
        print(f"\nRelatório CSV: {args.csv}")


if __name__ == "__main__":
    main()
