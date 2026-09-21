"""Simula o combate contra um monstro para calibrar os números antes do playtest.

    python tools/simular_combate.py data/incursoes/vortice_cripta.json
    python tools/simular_combate.py data/incursoes/vortice_cripta.json --sala L1C
    python tools/simular_combate.py ... --hp-personagem 45 --ca 16 --ataque 6 --dano 1d10+3

Roda milhares de confrontos e mostra taxa de vitória, rodadas e quantos caem, para
grupos de 5, 4, 3 e 2. Não toca no banco nem no bot.
"""
from __future__ import annotations

import argparse
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import motor  # noqa: E402
from src.incursoes import Monstro, carregar  # noqa: E402

LIMITE_RODADAS = 50


def um_combate(monstro: Monstro, grupo: list[motor.Combatente], rng: random.Random):
    estado = motor.EstadoCombate(monstro, monstro.hp, 1, grupo)
    while not estado.encerrado and estado.rodada <= LIMITE_RODADAS:
        for c in list(estado.vivos):
            motor.atacar_monstro(c, estado, rng)
            if estado.monstro_derrotado:
                break
        if estado.monstro_derrotado:
            break
        alvo = motor.sortear_alvo(estado, rng)
        if alvo is not None:
            motor.contra_atacar(estado, alvo, rng)
        estado.rodada += 1
    return estado


def simular(monstro: Monstro, tamanho: int, args, rng: random.Random) -> dict:
    vitorias, rodadas, caidos = 0, [], []
    for _ in range(args.repeticoes):
        grupo = [
            motor.Combatente(
                user_id=i,
                nome=f"P{i}",
                ca=args.ca,
                bonus_ataque=args.ataque,
                dano_arma=args.dano,
                hp_max=args.hp_personagem,
                hp_atual=args.hp_personagem,
            )
            for i in range(tamanho)
        ]
        estado = um_combate(monstro, grupo, rng)
        if estado.monstro_derrotado:
            vitorias += 1
            rodadas.append(estado.rodada)
        caidos.append(len(estado.caidos))
    return {
        "taxa": vitorias / args.repeticoes,
        "rodadas": statistics.mean(rodadas) if rodadas else float("nan"),
        "caidos": statistics.mean(caidos),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Simula combates de uma incursão.")
    parser.add_argument("incursao", type=Path, help="JSON da incursão")
    parser.add_argument("--sala", help="ID da sala de combate (padrão: o objetivo)")
    parser.add_argument("--repeticoes", type=int, default=2000)
    parser.add_argument("--hp-personagem", type=int, default=60)
    parser.add_argument("--ca", type=int, default=17)
    parser.add_argument("--ataque", type=int, default=7)
    parser.add_argument("--dano", default="1d8+4")
    parser.add_argument("--semente", type=int, default=None)
    grupo_monstro = parser.add_argument_group("sobreporem os números do monstro (para calibrar)")
    grupo_monstro.add_argument("--hp-monstro", type=int)
    grupo_monstro.add_argument("--ca-monstro", type=int)
    grupo_monstro.add_argument("--ataque-monstro", type=int)
    grupo_monstro.add_argument("--dano-monstro")
    args = parser.parse_args()

    incursao = carregar(args.incursao)
    sala = incursao.sala(args.sala) if args.sala else incursao.objetivo
    if sala is None:
        print(f"Sala '{args.sala}' não existe nesta incursão.", file=sys.stderr)
        return 1
    if not sala.e_combate:
        print(f"A sala '{sala.id}' é do tipo {sala.tipo}, não Combate.", file=sys.stderr)
        return 1

    base = sala.monstro
    m = Monstro(
        nome=base.nome,
        ca=args.ca_monstro if args.ca_monstro is not None else base.ca,
        ataque=args.ataque_monstro if args.ataque_monstro is not None else base.ataque,
        dano=args.dano_monstro or base.dano,
        hp=args.hp_monstro if args.hp_monstro is not None else base.hp,
    )
    rng = random.Random(args.semente)
    print(f"{incursao.nome} — {sala.nome}")
    print(f"{m.nome}: CA {m.ca}, ataque {m.ataque:+d}, dano {m.dano}, {m.hp} HP")
    print(
        f"Personagens: CA {args.ca}, ataque {args.ataque:+d}, dano {args.dano}, "
        f"{args.hp_personagem} HP  ({args.repeticoes} combates por linha)\n"
    )
    print(f"{'grupo':>6}  {'vitória':>8}  {'rodadas':>8}  {'caídos':>7}")
    for tamanho in (5, 4, 3, 2):
        r = simular(m, tamanho, args, rng)
        print(f"{tamanho:>6}  {r['taxa']:>7.1%}  {r['rodadas']:>8.1f}  {r['caidos']:>7.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
