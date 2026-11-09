"""Simula o combate contra um monstro para calibrar os números antes do playtest.

    python tools/simular_combate.py data/incursoes/vortice_cripta.json
    python tools/simular_combate.py data/incursoes/vortice_cripta.json --sala L1C
    python tools/simular_combate.py ... --hp-personagem 45 --ca 16 --ataque 6 --dano 1d10+3

Roda milhares de confrontos e mostra taxa de vitória, rodadas e quantos caem, para
grupos de 5, 4, 3 e 2. Não toca no banco nem no bot.
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import classes, motor  # noqa: E402
from src.rules import tier  # noqa: E402
from src.incursoes import Monstro, carregar, carregar_banco  # noqa: E402
# Reutiliza o catálogo e os resolvedores de habilidades já auditados no
# simulador de balanceamento. Este arquivo continua sendo a única alteração.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import simular_balanceamento as sb  # noqa: E402


LIMITE_RODADAS = 50



def um_combate(
    monstros: list[Monstro],
    grupo: list[motor.Combatente],
    rng: random.Random,
    classe_id: str,
    nivel: int,
    efeitos_classe: dict,
):
    """Uma sala inteira, usando as ações de classe e a iniciativa do motor."""
    estado = motor.EstadoCombate(
        [
            motor.Inimigo(
                i, m.nome, m.ca, m.ataque, m.dano, m.hp, m.hp,
                ataques=m.ataques,
                saves=dict(m.saves),
                saves_vantagem=list(m.saves_vantagem),
                habilidade=m.habilidade,
                golpes=list(m.golpes),
                matilha=m.matilha,
                regeneracao=m.regeneracao,
            )
            for i, m in enumerate(monstros)
        ],
        1,
        grupo,
    )
    for c in grupo:
        c._nivel_simulador = nivel
        c._efeitos_classe_simulador = efeitos_classe
        c._rodada_simulador = 1
        c._marcas_simulador = []
        c._reckless_ativo_simulador = False
        c._atordoado_ate = 0
    for inimigo in estado.inimigos:
        inimigo._efeitos_simulador = []
        inimigo._atordoado_ate = 0
        inimigo._base_efeitos_simulador = {
            atributo: getattr(inimigo, atributo)
            for atributo in sb._MAPA_EFEITOS.values()
            if hasattr(inimigo, atributo)
        }

    ordem = motor.rolar_iniciativas(estado, rng)
    presos: dict[int, dict] = {}
    dano_grupo = dano_inimigo = cura_total = recursos_gastos = thp_gasto = 0
    ataques_basicos = 0
    habilidades_usadas: dict[str, dict[str, int]] = {}

    def registrar_habilidade(habilidade, dano=0, cura=0, recursos=0):
        nome = habilidade.nome
        item = habilidades_usadas.setdefault(
            nome, {"usos": 0, "dano": 0, "cura": 0, "recursos": 0}
        )
        item["usos"] += 1
        item["dano"] += int(dano)
        item["cura"] += int(cura)
        item["recursos"] += int(recursos)

    while not estado.encerrado and estado.rodada <= LIMITE_RODADAS:
        rodada = estado.rodada
        sb._expirar_efeitos(estado.combatentes + estado.inimigos, rodada)
        for c in estado.combatentes:
            c._rodada_simulador = rodada

        for vez in ordem:
            if estado.encerrado:
                break

            if vez.tipo == motor.INIMIGO:
                inimigo = estado.inimigo(vez.ident)
                if inimigo is None or inimigo.caido:
                    continue
                resultado = motor.turno_do_inimigo(inimigo, estado, rng)
                recursos_gastos += sb._inspirar_save(
                    resultado, estado, inimigo, rodada, rng
                )
                sb._registrar_atordoamentos(resultado.investidas, rodada)
                for investida in resultado.investidas:
                    if investida.atordoou:
                        presos[investida.alvo.user_id] = {
                            "repete": (
                                (investida.save.atributo, investida.save.cd)
                                if investida.repete_save and investida.save
                                else None
                            ),
                            "perdeu": False,
                        }
                recursos_gastos += sb._usar_esquiva_reativa(resultado, estado)
                dano_inimigo += sum(g.dano for g, _ in resultado.golpes)
                dano_inimigo += sum(i.dano for i in resultado.investidas)

                # Reações que disparam quando um personagem cai a 0 HP.
                for c in estado.combatentes:
                    if c.e_invocacao or not c.caido:
                        continue
                    reacao = next(
                        (
                            h for _, h in c._habilidades_simulador
                            if h.acao
                            and h.acao.get("tipo") == "reacao"
                            and h.acao.get("quando") == "caiu"
                            and c._usos_simulador.get(h.chave_de_uso, 0) < h.vezes
                        ),
                        None,
                    )
                    if reacao and sb.registrar_uso(c, reacao):
                        recursos_gastos += 1
                        c.hp_atual = max(1, reacao.acao.get("hp", 1))
                        thp = reacao.acao.get("thp")
                        if thp:
                            motor.ganhar_thp(c, motor.rolar_dano(thp, rng))
                continue

            personagem = estado.combatente(vez.ident)
            if personagem is None or personagem.caido:
                continue
            if personagem.atordoado:
                if personagem.user_id in presos:
                    presos[personagem.user_id]["perdeu"] = True
                continue

            habilidade = sb._escolher_ativa(
                personagem, estado.combatentes, estado, rodada
            )
            usou = False
            acao_usada = {"tipo": "golpes"}
            if habilidade is not None and sb.registrar_uso(personagem, habilidade):
                acumuladores = {
                    "dano": [0], "cura": [0], "recursos": [0], "thp": [0]
                }
                usou = sb._executar_ativa(
                    personagem, estado.combatentes, estado, habilidade, rng,
                    rodada, acumuladores["dano"], acumuladores["cura"],
                    acumuladores["recursos"], acumuladores["thp"],
                )
                dano_grupo += acumuladores["dano"][0]
                cura_total += acumuladores["cura"][0]
                recursos_gastos += acumuladores["recursos"][0]
                thp_gasto += acumuladores["thp"][0]
                if usou:
                    acao_usada = habilidade.acao or acao_usada
                    registrar_habilidade(
                        habilidade, acumuladores["dano"][0],
                        acumuladores["cura"][0], acumuladores["recursos"][0],
                    )
                else:
                    personagem._usos_simulador[habilidade.chave_de_uso] -= 1

            if not usou and not estado.encerrado:
                for _ in range(max(1, personagem.ataques)):
                    alvo = estado.alvo_preferido()
                    if alvo is None:
                        break
                    golpe = motor.atacar_inimigo(personagem, alvo, rng)
                    ataques_basicos += 1
                    if not golpe.acertou:
                        recursos_gastos += sb._inspirar_ataque(
                            estado, personagem, alvo, golpe, rng
                        )
                    dano_grupo += golpe.dano
                    sb._registrar_efeito_do_ataque(
                        personagem, alvo, golpe, rodada
                    )
                    sequencia = efeitos_classe.get("sequencia") or {}
                    if sequencia:
                        personagem._sequencia_simulador = motor.proxima_sequencia(
                            personagem._sequencia_simulador, golpe.acertou,
                            sequencia.get("por_acerto", 1),
                            sequencia.get("teto", 2),
                        )
                        personagem.bonus_ataque = (
                            classes.numeros(classe_id, nivel).acerto
                            + efeitos_classe.get("acerto", 0)
                            + personagem._sequencia_simulador
                        )

            escondido = (
                getattr(personagem, "_furtividade_inicio_simulador", rodada + 1)
                <= rodada
                <= getattr(personagem, "_furtividade_ate_simulador", 0)
            )
            if not escondido:
                personagem.ameaca_gerada += sb.ameaca.gerada_por(
                    personagem.classe, acao_usada
                )

        # Invocações agem uma vez por rodada; elas entram na iniciativa prática
        # logo após a sequência principal, sem criar uma segunda rolagem global.
        for invocado in [
            c for c in estado.combatentes
            if c.e_invocacao and not c.caido
        ]:
            alvo = estado.alvo_preferido()
            if alvo is not None:
                golpe = motor.atacar_inimigo(invocado, alvo, rng)
                dano_grupo += golpe.dano

        if estado.encerrado:
            break

        # Dano periódico e cura passiva são resolvidos ao fim da rodada.
        for alvo in estado.inimigos:
            efeito = getattr(alvo, "_dano_rodada_simulador", None)
            if efeito and not alvo.caido:
                expressao, atributo, cd, restante = efeito
                save = motor.salvar_inimigo(alvo, atributo, cd, rng)
                if not save.passou:
                    dano = motor.rolar_dano(expressao, rng)
                    alvo.hp_atual = max(0, alvo.hp_atual - dano)
                    dano_grupo += dano
                elif getattr(alvo, "_dano_rodada_repete_save", False):
                    alvo._dano_rodada_simulador = None
                    continue
                restante -= 1
                alvo._dano_rodada_simulador = (
                    (expressao, atributo, cd, restante) if restante > 0 else None
                )

        for c in estado.combatentes:
            if c.cura_por_turno and not c.caido:
                cura_total += motor.curar(c, c.cura_por_turno)

        # Um personagem atordoado perde a vez e, quando aplicável, repete o save.
        for user_id, preso in list(presos.items()):
            if preso["repete"] is None or not preso["perdeu"]:
                if preso["repete"] is None and preso["perdeu"]:
                    c = estado.combatente(user_id)
                    if c:
                        c.atordoado = False
                        c._atordoado_ate = rodada
                    presos.pop(user_id)
                continue
            c = estado.combatente(user_id)
            if c is None or c.caido:
                presos.pop(user_id)
                continue
            atributo, cd = preso["repete"]
            if motor.salvar_combatente(c, atributo, cd, rng).passou:
                c.atordoado = False
                c._atordoado_ate = rodada
                presos.pop(user_id)
            else:
                c._atordoado_ate = rodada + 1
            preso["perdeu"] = False

        estado.rodada += 1

    return {
        "inimigos_derrotados": estado.inimigos_derrotados,
        "rodadas": estado.rodada - 1,
        "caidos": len(estado.caidos),
        "dano_grupo": dano_grupo,
        "dano_recebido": dano_inimigo,
        "cura": cura_total,
        "recursos": recursos_gastos,
        "thp_gasto": thp_gasto,
        "hp_restante": sum(max(0, c.hp_atual) for c in grupo),
        "ataques_basicos": ataques_basicos,
        "habilidades_usadas": habilidades_usadas,
    }


def simular(monstros: list[Monstro], tamanho: int, args, rng: random.Random) -> dict:
    ficha_classe = classes.classe(args.classe)
    numeros = ficha_classe.numeros(args.nivel)
    habilidades_ficha, escolhas = sb.habilidades_da_ficha(args.classe, args.nivel)
    efeitos = classes.efeitos(args.classe, args.nivel, escolhas)
    saves = classes.saves(args.classe, args.nivel, efeitos)

    vitorias, rodadas, caidos = 0, [], []
    curas, recursos, danos, recebidos, ataques = [], [], [], [], []
    habilidades_totais: dict[str, dict[str, int]] = {}
    for _ in range(args.repeticoes):
        grupo = []
        for i in range(tamanho):
            c = motor.Combatente(
                user_id=i,
                nome=f"P{i + 1}",
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
                ameaca=sb.ameaca.inicial(args.classe) + efeitos.get("ameaca", 0),
                classe=args.classe,
                saves=saves,
            )
            c._habilidades_simulador = habilidades_ficha
            c._usos_simulador = {}
            c._efeitos_simulador = []
            c._sequencia_simulador = 0
            grupo.append(c)

        resultado = um_combate(
            monstros, grupo, rng, args.classe, args.nivel, efeitos
        )
        if resultado["inimigos_derrotados"]:
            vitorias += 1
        rodadas.append(resultado["rodadas"])
        caidos.append(resultado["caidos"])
        curas.append(resultado["cura"])
        recursos.append(resultado["recursos"])
        danos.append(resultado["dano_grupo"])
        recebidos.append(resultado["dano_recebido"])
        ataques.append(resultado["ataques_basicos"])
        for nome, dados in resultado["habilidades_usadas"].items():
            total = habilidades_totais.setdefault(
                nome, {"usos": 0, "dano": 0, "cura": 0, "recursos": 0}
            )
            for chave in total:
                total[chave] += dados[chave]

    return {
        "taxa": vitorias / args.repeticoes,
        "rodadas": statistics.mean(rodadas) if rodadas else float("nan"),
        "caidos": statistics.mean(caidos),
        "cura": statistics.mean(curas),
        "recursos": statistics.mean(recursos),
        "dano": statistics.mean(danos),
        "recebido": statistics.mean(recebidos),
        "ataques_basicos": statistics.mean(ataques),
        "habilidades": habilidades_totais,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Simula combates de uma incursão.")
    parser.add_argument(
        "incursao", type=Path, help="JSON da incursão, ou o do banco de uma Organização"
    )
    parser.add_argument("--sala", help="ID da sala de combate (padrão: o objetivo)")
    parser.add_argument("--repeticoes", type=int, default=2000)
    parser.add_argument(
        "--classe",
        default="guerreiro",
        help="Classe do grupo simulado (" + ", ".join(sorted(classes.CLASSES)) + ")",
    )
    parser.add_argument("--nivel", type=int, default=8, help="Nivel do grupo (1 a 10)")
    parser.add_argument("--semente", type=int, default=None)
    parser.add_argument(
        "--tier",
        type=int,
        default=None,
        help="de qual tier da sala sao as criaturas (padrao: o do --nivel)",
    )
    grupo_monstro = parser.add_argument_group("sobreporem os números do monstro (para calibrar)")
    grupo_monstro.add_argument("--hp-monstro", type=int)
    grupo_monstro.add_argument("--ca-monstro", type=int)
    grupo_monstro.add_argument("--ataque-monstro", type=int)
    grupo_monstro.add_argument("--dano-monstro")
    args = parser.parse_args()

    # Aceita tanto o JSON de uma incursao quanto o banco de salas de uma
    # Organizacao — as salas de combate do meio do caminho moram no banco.
    bruto = json.loads(args.incursao.read_text(encoding="utf-8"))
    if "objetivo" in bruto:
        conteudo = carregar(args.incursao)
        titulo = conteudo.nome
        sala = conteudo.sala(args.sala) if args.sala else conteudo.objetivo
    else:
        conteudo = carregar_banco(args.incursao)
        titulo = f"Banco: {conteudo.organizacao}"
        if not args.sala:
            print(
                "Este JSON e um banco de salas: diga qual com --sala. Salas de combate: "
                + ", ".join(s.id for s in conteudo.salas if s.e_combate),
                file=sys.stderr,
            )
            return 1
        sala = conteudo.sala(args.sala)
    if sala is None:
        print(f"Sala '{args.sala}' não existe neste arquivo.", file=sys.stderr)
        return 1
    if not sala.e_combate:
        print(f"A sala '{sala.id}' é do tipo {sala.tipo}, não Combate.", file=sys.stderr)
        return 1

    # NADA ESCALA. A sala diz quem cada tier encontra nela
    # (`Sala.monstros_por_tier`) e a ficha vale como esta escrita — e e assim
    # que o bot abre o combate. O tier vem do argumento, senao do nivel dado:
    # medir a lista de um tier contra um grupo de outro e numero bonito e
    # falso, que foi o que esta ferramenta devolveu durante todo o
    # balanceamento do tier 2 (99,6% de vitoria onde a mesa tinha 4,8%).
    tier_medido = args.tier or tier(args.nivel)
    base_das_salas = sala.monstros_do_tier(tier_medido)

    # As sobreposicoes valem para todas as criaturas da sala, para calibrar rapido.
    monstros = [
        Monstro(
            nome=base.nome,
            ca=args.ca_monstro if args.ca_monstro is not None else base.ca,
            ataque=args.ataque_monstro if args.ataque_monstro is not None else base.ataque,
            dano=args.dano_monstro or base.dano,
            hp=args.hp_monstro if args.hp_monstro is not None else base.hp,
            ataques=base.ataques,
            saves=dict(base.saves),
            saves_vantagem=list(base.saves_vantagem),
            habilidade=base.habilidade,
            # Sobrescrever ataque ou dano vale para o golpe basico: a lista sai.
            golpes=[]
            if args.ataque_monstro is not None or args.dano_monstro
            else list(base.golpes),
            matilha=base.matilha,
            regeneracao=base.regeneracao,
        )
        for base in base_das_salas
    ]
    rng = random.Random(args.semente)
    print(f"{titulo} — {sala.nome}")
    if sala.monstros_por_tier:
        escritos = ", ".join(f"T{t}" for t in sorted(sala.monstros_por_tier))
        print(f"criaturas do tier {tier_medido} (a sala tem lista de {escritos})")
    for m in monstros:
        extras = ""
        if m.golpes:
            extras += ", golpes: " + ", ".join(
                f"{g.nome} {g.ataque:+d} {g.dano}" for g in m.golpes
            )
        elif m.ataques > 1:
            extras += f", {m.ataques}x por rodada"
        if m.matilha:
            extras += ", matilha"
        if m.regeneracao:
            extras += f", regenera {m.regeneracao}"
        if m.habilidade:
            h = m.habilidade
            alvo = "1 alvo" if h.alvos == 1 else f"{h.alvos} alvos"
            quando = (
                f"recharge {h.recarga}-6" if h.recarga else f"a cada {h.cada} rodadas"
            )
            extras += (
                f" | {h.nome}: {alvo}, save {h.save} CD {h.cd}"
                + (f", {h.dano}" if h.dano else "")
                + (f", atordoa {h.atordoa}" if h.atordoa else "")
                + (" (save no fim do turno)" if h.save_repete else "")
                + (" (metade no sucesso)" if h.metade else "")
                + f", {quando}"
            )
        print(
            f"{m.nome}: CA {m.ca}, ataque {m.ataque:+d}, dano {m.dano}, {m.hp} HP{extras}"
        )
    do_grupo = classes.classe(args.classe)
    if do_grupo is None:
        print(f"Classe '{args.classe}' nao existe.", file=sys.stderr)
        return 1
    n = do_grupo.numeros(args.nivel)
    _habilidades, escolhas = sb.habilidades_da_ficha(args.classe, args.nivel)
    e = classes.efeitos(args.classe, args.nivel, escolhas)
    print(
        f"Grupo: {do_grupo.nome} nivel {args.nivel} (tier {tier(args.nivel)}) — "
        f"CA {n.ca}, acerto {n.acerto:+d}, dano {n.dano}, {n.hp} HP"
        + (f", {e['ataques']}x por rodada" if e["ataques"] > 1 else "")
        + (f", critico com {e['critico_em']}+" if e["critico_em"] < 20 else "")
        + f"  ({args.repeticoes} combates por linha)"
    )
    habilidades_disponiveis, _ = sb.habilidades_da_ficha(args.classe, args.nivel)
    passivas = [h.nome for _, h in habilidades_disponiveis if not h.acionavel]
    ativas = [h.nome for _, h in habilidades_disponiveis
              if h.acionavel and (h.acao or {}).get("tipo") != "reacao"]
    reativas = [h.nome for _, h in habilidades_disponiveis
                if (h.acao or {}).get("tipo") == "reacao"]
    print()
    print("Habilidades carregadas:")
    print("  Passivas: " + (", ".join(passivas) if passivas else "nenhuma"))
    print("  Ativas: " + (", ".join(ativas) if ativas else "nenhuma"))
    print("  Reações: " + (", ".join(reativas) if reativas else "nenhuma"))
    print()
    print(f"{'grupo':>6}  {'vitória':>8}  {'rodadas':>8}  {'caídos':>7}  {'cura':>8}  {'recursos':>8}  {'ataques':>8}")
    for tamanho in (5, 4, 3, 2):
        r = simular(monstros, tamanho, args, rng)
        print(f"{tamanho:>6}  {r['taxa']:>7.1%}  {r['rodadas']:>8.1f}  {r['caidos']:>7.1f}  {r['cura']:>8.1f}  {r['recursos']:>8.1f}  {r['ataques_basicos']:>8.1f}")
        print("  Habilidades ativas efetivamente usadas (total no grupo):")
        if not r["habilidades"]:
            print("    nenhuma")
        else:
            for nome, dados in sorted(r["habilidades"].items()):
                print(
                    f"    {nome}: {dados['usos']} usos | dano {dados['dano']} | "
                    f"cura {dados['cura']} | recursos {dados['recursos']}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
