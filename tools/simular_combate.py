"""Mede uma sala com os resolvedores reais do bot, sem rede ou banco do servidor.

    python tools/simular_combate.py data/incursoes/vortice_cripta.json
    python tools/simular_combate.py ... --classe druida --escolha forma_t1=lobo
"""
from __future__ import annotations
import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import classes
from src.rules import tier
from src.incursoes import Monstro, carregar, carregar_banco
from tools.simulacao.execucao import Ficha, simular as executar
from tools.simulacao.estatisticas import resumir
from tools.simulacao import grupos, politica as sb

LIMITE_RODADAS = 50


def mesas(tamanho: int, args, rng: random.Random) -> list[tuple[Ficha, ...]]:
    """As composições a medir, e quantas lutas cada uma leva.

    Sem `args.classe`, a sala é medida contra mesas SORTEADAS — ver
    `tools/simulacao/grupos.py`. Com uma classe, volta ao grupo uniforme, que
    não é mais o padrão e sim o diagnóstico: "esta sala é dura PARA QUEM?".
    """
    classe = getattr(args, "classe", None)
    if classe:
        return [tuple(Ficha(classe, args.nivel, getattr(args, "escolhas", None))
                      for _ in range(tamanho))], args.repeticoes
    quantas, por_mesa = grupos.dividir(
        args.repeticoes,
        getattr(args, "composicoes", None) or grupos.COMPOSICOES_PADRAO,
        getattr(args, "minimo_por_mesa", None) or grupos.MINIMO_POR_COMPOSICAO,
    )
    return grupos.sortear(tamanho, args.nivel, quantas, rng), por_mesa


def simular(monstros: list[Monstro], tamanho: int, args, rng: random.Random) -> dict:
    """API usada pelo Estudio e sugeridor: mesma assinatura e mesmas medidas.

    A taxa que volta é a de TODAS as lutas juntas. `composicoes` traz cada
    mesa com a taxa dela — é onde aparece a que sofre, que a média esconde.
    """
    composicoes, por_mesa = mesas(tamanho, args, rng)
    detalhes = getattr(args, "coletar_detalhes", True)
    todas, por_composicao = [], []
    for mesa in composicoes:
        lutas = executar(monstros, list(mesa), por_mesa, rng, limite=LIMITE_RODADAS,
                         tier=getattr(args, "tier", None), coletar_detalhes=detalhes)
        todas.extend(lutas)
        por_composicao.append({
            "classes": grupos.nomes_da_mesa(mesa),
            "taxa": sum(l["inimigos_derrotados"] for l in lutas) / len(lutas),
            "amostras": len(lutas),
        })
    resumo = resumir(todas)
    # A pagina e o sugeridor usam somente estas medidas. Pular a coleta nao
    # altera a luta nem publica zeros como se fossem dano/cura medidos.
    if not detalhes:
        resumo = {k: resumo[k] for k in (
            "taxa", "rodadas", "caidos", "ic95", "amostras", "vitorias", "limites")}
    resumo["composicoes"] = por_composicao
    return resumo


def main() -> int:
    parser = argparse.ArgumentParser(description="Simula combates de uma incursão.")
    parser.add_argument(
        "incursao", type=Path, help="JSON da incursão, ou o do banco de uma Organização"
    )
    parser.add_argument("--sala", help="ID da sala de combate (padrão: o objetivo)")
    parser.add_argument("--repeticoes", type=int, default=2000)
    parser.add_argument(
        "--classe",
        default=None,
        help="Mede contra um grupo de UMA classe, para diagnóstico. Sem isto o "
             "grupo é sorteado, que é o padrão. Classes: "
             + ", ".join(sorted(classes.CLASSES)),
    )
    parser.add_argument(
        "--composicoes", type=int, default=grupos.COMPOSICOES_PADRAO,
        metavar="N", help=f"quantas mesas sorteadas medir (padrão: {grupos.COMPOSICOES_PADRAO})",
    )
    parser.add_argument("--nivel", type=int, default=8, help="Nivel do grupo (1 a 10)")
    parser.add_argument("--semente", type=int, default=None)
    parser.add_argument(
        "--escolha", action="append", default=[], metavar="ID=OPCAO",
        help="Substitui escolha automatica da ficha; pode repetir. Ex.: --escolha magia_t3=mass_healing_word",
    )
    parser.add_argument(
        "--grupos", type=int, nargs="+", default=[5, 4, 3, 2],
        metavar="N", help="Tamanhos de grupo a medir (padrao: 5 4 3 2)",
    )
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
    if args.repeticoes <= 0:
        parser.error("--repeticoes deve ser maior que zero")
    if not 1 <= args.nivel <= 10:
        parser.error("--nivel deve estar entre 1 e 10")
    if not args.grupos or any(n <= 0 for n in args.grupos):
        parser.error("--grupos deve conter tamanhos positivos")
    if args.composicoes < 1:
        parser.error("--composicoes deve ser maior que zero")
    # --escolha mexe na ficha de UMA classe. Com o grupo sorteado não existe
    # "a ficha": sao doze mesas de classes diferentes, e aplicar a escolha a
    # todas seria inventar magia em quem nao a tem.
    if args.escolha and not args.classe:
        parser.error("--escolha precisa de --classe: o grupo sorteado não tem uma ficha só")
    args.escolhas = None
    if args.classe:
        if classes.classe(args.classe) is None:
            parser.error(f"classe desconhecida: {args.classe}")
        args.escolhas = sb.escolhas_automaticas(args.classe, args.nivel)
        disponiveis = classes.habilidades(args.classe, args.nivel, args.escolhas)
        ids_escolhas = {
            h.id: {opcao["id"] for opcao in (h.escolha or {}).get("opcoes", [])}
            for _, h in disponiveis
            if h.decidivel and (h.escolha or {}).get("tipo") == "opcao"
        }
        for escolha in args.escolha:
            if "=" not in escolha:
                parser.error(f"escolha deve ter formato ID=OPCAO: {escolha}")
            identificador, opcao = escolha.split("=", 1)
            if identificador not in ids_escolhas or opcao not in ids_escolhas[identificador]:
                parser.error(
                    f"escolha invalida: {escolha}. "
                    f"Opcoes disponiveis: {', '.join(sorted(ids_escolhas))}"
                )
            args.escolhas[identificador] = opcao

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
    if args.classe:
        do_grupo = classes.classe(args.classe)
        n = do_grupo.numeros(args.nivel)
        e = classes.efeitos(args.classe, args.nivel, args.escolhas)
        print(
            f"Grupo: {do_grupo.nome} nivel {args.nivel} (tier {tier(args.nivel)}) — "
            f"CA {n.ca}, acerto {n.acerto:+d}, dano {n.dano}, {n.hp} HP"
            + (f", {e['ataques']}x por rodada" if e["ataques"] > 1 else "")
            + (f", critico com {e['critico_em']}+" if e["critico_em"] < 20 else "")
            + f"  ({args.repeticoes} combates por linha)"
        )
        print("DIAGNÓSTICO: cinco da mesma classe não é uma mesa que existe. "
              "Serve para perguntar 'esta sala é dura PARA QUEM?'; para saber "
              "se ela é justa, meça sem --classe.")
        habilidades_disponiveis = classes.habilidades(args.classe, args.nivel, args.escolhas)
        if args.escolhas:
            print("Escolhas da ficha: " + ", ".join(
                f"{id_}={opcao}" for id_, opcao in sorted(args.escolhas.items())
            ))
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
    else:
        mesas_medidas, por_mesa = grupos.dividir(args.repeticoes, args.composicoes)
        print(
            f"Grupo: SORTEADO, nivel {args.nivel} (tier {tier(args.nivel)}) — "
            f"{mesas_medidas} mesas por linha, {por_mesa} combates cada "
            f"({mesas_medidas * por_mesa} no total)"
        )
    print()
    print(f"{'grupo':>6}  {'vitória':>8}  {'rodadas':>8}  {'caídos':>7}  {'cura':>8}  {'recursos':>8}  {'ataques':>8}")
    for tamanho in args.grupos:
        r = simular(monstros, tamanho, args, rng)
        print(f"{tamanho:>6}  {r['taxa']:>7.1%}  {r['rodadas']:>8.1f}  {r['caidos']:>7.1f}  {r['cura']:>8.1f}  {r['recursos']:>8.1f}  {r['ataques_basicos']:>8.1f}")
        # Os extremos ao lado da media: a mesa que sofre some na media, e e
        # justamente ela que diz se a sala mata alguem de verdade.
        if len(r["composicoes"]) > 1:
            ordenadas = sorted(r["composicoes"], key=lambda c: c["taxa"])
            for rotulo, mesa in (("pior", ordenadas[0]), ("melhor", ordenadas[-1])):
                print(f"  mesa {rotulo}: {mesa['taxa']:>6.1%} em {mesa['amostras']} lutas"
                      f" — {', '.join(mesa['classes'])}")
        print(f"  Efeitos indiretos (totais em {r['amostras']} lutas): dano periódico {r['dano_periodico']} | cura passiva {r['cura_passiva']}")
        print(f"  THP: gerado {r['thp_gerado']:.1f}/luta | restante {r['thp_restante']:.1f}/luta")
        print(f"  Quedas: {r['quedas_distintas']:.2f} personagens distintos/luta | {r['caidos']:.2f} caidos no fim")
        print(f"  Incapacitacao (totais): turnos perdidos atordoados {r['turnos_perdidos']} | turnos caidos {r['turnos_caidos']} | turnos de inimigos atordoados {r['turnos_inimigos_atordoados']} | quedas antes de agir {r['quedas_antes_de_agir']}")
        if r["limites"]:
            print(f"  Combates encerrados pelo limite de {LIMITE_RODADAS} rodadas: {r['limites']} ({r['limites'] / r['amostras']:.1%})")

        print("  Reações acionadas (total no grupo):")
        for nome, usos in sorted(r["reacoes"].items()):
            print(f"    {nome}: {usos} acionamentos")
        if not r["reacoes"]:
            print("    nenhuma")
        print("  Recursos gastos por habilidade ativa:")
        for nome, gasto in sorted(r["recursos_habilidade"].items()):
            print(f"    {nome}: {gasto}")
        if not r["recursos_habilidade"]:
            print("    nenhum")
        print("  Habilidades ativas efetivamente usadas (total no grupo):")
        if not r["habilidades"]:
            print("    nenhuma")
        else:
            for nome, dados in sorted(r["habilidades"].items()):
                print(
                    f"    {nome}: {dados['usos']} usos | dano {dados['dano']} | "
                    f"cura {dados['cura']} | THP {dados['thp']} | "
                    f"periodico {dados['periodico']} | recursos {dados['recursos']}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
