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

from src import classes, motor  # noqa: E402
from src.rules import tier  # noqa: E402
from src.incursoes import Monstro, carregar  # noqa: E402

LIMITE_RODADAS = 50


def um_combate(monstros: list[Monstro], grupo: list[motor.Combatente], rng: random.Random):
    """Uma sala inteira: o grupo foca o primeiro de pé, e cada inimigo revida."""
    estado = motor.EstadoCombate(
        [
            motor.Inimigo(i, m.nome, m.ca, m.ataque, m.dano, m.hp, m.hp)
            for i, m in enumerate(monstros)
        ],
        1,
        grupo,
    )
    while not estado.encerrado and estado.rodada <= LIMITE_RODADAS:
        for c in list(estado.vivos):
            for _ in range(max(1, c.ataques)):
                alvo = estado.alvo_preferido()
                if alvo is None:
                    break
                motor.atacar_inimigo(c, alvo, rng)
        if estado.inimigos_derrotados:
            break
        motor.rodada_dos_inimigos(estado, rng)
        estado.rodada += 1
    return estado


def simular(monstros: list[Monstro], tamanho: int, args, rng: random.Random) -> dict:
    numeros = classes.classe(args.classe).numeros(args.nivel)
    efeitos = classes.efeitos(args.classe, args.nivel)
    vitorias, rodadas, caidos = 0, [], []
    for _ in range(args.repeticoes):
        grupo = [
            motor.Combatente(
                user_id=i,
                nome=f"P{i}",
                ca=numeros.ca,
                bonus_ataque=numeros.acerto,
                dano_arma=numeros.dano,
                hp_max=numeros.hp,
                hp_atual=numeros.hp,
                ataques=efeitos["ataques"],
                critico_em=efeitos["critico_em"],
                dano_extra=efeitos["dano_extra"],
                dano_ferido=efeitos["dano_ferido"],
            )
            for i in range(tamanho)
        ]
        estado = um_combate(monstros, grupo, rng)
        if estado.inimigos_derrotados:
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
    parser.add_argument(
        "--classe",
        default="guerreiro",
        help="Classe do grupo simulado (" + ", ".join(sorted(classes.CLASSES)) + ")",
    )
    parser.add_argument("--nivel", type=int, default=8, help="Nivel do grupo (1 a 10)")
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

    # As sobreposicoes valem para todas as criaturas da sala, para calibrar rapido.
    monstros = [
        Monstro(
            nome=base.nome,
            ca=args.ca_monstro if args.ca_monstro is not None else base.ca,
            ataque=args.ataque_monstro if args.ataque_monstro is not None else base.ataque,
            dano=args.dano_monstro or base.dano,
            hp=args.hp_monstro if args.hp_monstro is not None else base.hp,
        )
        for base in sala.monstros
    ]
    rng = random.Random(args.semente)
    print(f"{incursao.nome} — {sala.nome}")
    for m in monstros:
        print(f"{m.nome}: CA {m.ca}, ataque {m.ataque:+d}, dano {m.dano}, {m.hp} HP")
    do_grupo = classes.classe(args.classe)
    if do_grupo is None:
        print(f"Classe '{args.classe}' nao existe.", file=sys.stderr)
        return 1
    n = do_grupo.numeros(args.nivel)
    e = classes.efeitos(args.classe, args.nivel)
    print(
        f"Grupo: {do_grupo.nome} nivel {args.nivel} (tier {tier(args.nivel)}) — "
        f"CA {n.ca}, acerto {n.acerto:+d}, dano {n.dano}, {n.hp} HP"
        + (f", {e['ataques']}x por rodada" if e["ataques"] > 1 else "")
        + (f", critico com {e['critico_em']}+" if e["critico_em"] < 20 else "")
        + f"  ({args.repeticoes} combates por linha)"
    )
    print()
    print(f"{'grupo':>6}  {'vitória':>8}  {'rodadas':>8}  {'caídos':>7}")
    for tamanho in (5, 4, 3, 2):
        r = simular(monstros, tamanho, args, rng)
        print(f"{tamanho:>6}  {r['taxa']:>7.1%}  {r['rodadas']:>8.1f}  {r['caidos']:>7.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
