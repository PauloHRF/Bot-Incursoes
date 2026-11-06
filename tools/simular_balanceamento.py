"""Simulador Monte Carlo de combate para auditoria de balanceamento.

Uso:
    python tools/simular_balanceamento.py
    python tools/simular_balanceamento.py --simulacoes 5000 --tier 5
    python tools/simular_balanceamento.py --classe patrulheiro --tier 3
    python tools/simular_balanceamento.py --csv resultados.csv

Usa o catálogo real de classes/habilidades e as primitivas de resolução do
motor. As escolhas de habilidades são automatizadas por uma política
determinística; recursos respeitam o escopo declarado (combate/descanso/
incursão). A simulação não altera o motor nem os dados do bot.
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

from src import ameaca, bestiario, classes, habilidades, motor, rules  # noqa: E402


GRUPO = 5
MAX_RODADAS = 40
CLASSES = tuple(classes.CLASSES)
ESCOPOS = ("combate", "descanso", "incursao")


def media_dado(expressao: str) -> float:
    """Média de uma expressão de dano, sem consumir o RNG da luta."""
    try:
        return sum(
            sinal * (quantidade * (faces + 1) / 2 if faces else quantidade)
            for sinal, quantidade, faces in motor.termos_de_dano(expressao)
        )
    except (TypeError, ValueError):
        return 0.0


def pontuar_acao(acao: dict, efeito: dict | None = None) -> float:
    """Valor aproximado usado apenas para escolher automaticamente uma opção."""
    efeito = efeito or {}
    tipo = acao.get("tipo")
    if tipo == "save":
        dano = media_dado(acao.get("dano", "")) + media_dado(efeito.get("dano_magia", ""))
        alvos = 3 if acao.get("alvos") == "todos" else 1 + efeito.get("alvos_extra", 0)
        return dano * alvos * (1.0 if acao.get("metade") else 0.85) + 7 * bool(acao.get("atordoa"))
    if tipo == "golpes":
        return 12 + media_dado(acao.get("dano_bonus", "")) * 1.5
    if tipo == "duracao":
        extras = acao.get("efeitos") or {}
        return (
            5 * extras.get("ataques", 0)
            + 2.5 * extras.get("dano_extra", 0)
            + 3 * extras.get("ca", 0)
            + 5 * bool(extras.get("vantagem"))
            + 2 * extras.get("ameaca", 0)
            + media_dado(extras.get("dano_bonus", "")) * 1.5
        ) * acao.get("turnos", 1)
    if tipo == "cura":
        return 15 + 20 * acao.get("fracao", 0)
    if tipo == "grupo":
        return 10 + media_dado(acao.get("thp", "")) * GRUPO + 30 * acao.get("cura_fracao", 0)
    if tipo == "forma":
        return 20 + max((media_dado(v) for v in (acao.get("dano") or {}).values()), default=0)
    if tipo == "invocar":
        return 20 + media_dado(acao.get("dano", "")) * 2
    return sum(float(v) for v in efeito.values() if isinstance(v, (int, float)))


def escolhas_automaticas(classe_id: str, nivel: int) -> dict:
    """Escolhe opções reais do catálogo para que habilidades condicionais existam."""
    ficha_classe = classes.classe(classe_id)
    if ficha_classe is None:
        return {}
    escolhas = {}
    teto = min(rules.tier(nivel), max(ficha_classe.habilidades))
    for tier_atual in range(1, teto + 1):
        for habilidade in ficha_classe.habilidades.get(tier_atual, []):
            forma = habilidade.escolha or {}
            if forma.get("tipo") != "opcao":
                continue
            opcoes = forma.get("opcoes") or []
            if not opcoes:
                continue
            candidatos = []
            for opcao in opcoes:
                efeito = opcao.get("efeito") or {}
                filha = next(
                    (
                        h for t in range(1, teto + 1)
                        for h in ficha_classe.habilidades.get(t, [])
                        if h.exige_escolha == (habilidade.id, opcao["id"])
                    ),
                    None,
                )
                acao = (filha.acao or {}) if filha else {}
                nota = pontuar_acao(acao, efeito)
                if not acao and not efeito:
                    texto = (opcao.get("texto") or "").lower()
                    nota = (
                        45 if any(p in texto for p in ("cura", "curar", "dano em todos"))
                        else 20 if any(p in texto for p in ("ataca", "dano", "vida temporaria"))
                        else 8
                    )
                candidatos.append((nota, opcao["id"]))
            escolhas[habilidade.id] = max(candidatos)[1]
    return escolhas


def habilidades_da_ficha(classe_id: str, nivel: int):
    escolhas = escolhas_automaticas(classe_id, nivel)
    return classes.habilidades(classe_id, nivel, escolhas), escolhas


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
    """Monta cinco fichas com números, passivas, escolhas e saves reais."""
    nivel = rules.nivel_do_tier(tier)
    numeros = classes.numeros(classe_id, nivel)
    habilidades_ficha, escolhas = habilidades_da_ficha(classe_id, nivel)
    efeitos = classes.efeitos(classe_id, nivel, escolhas)

    grupo = []
    for indice in range(GRUPO):
        combatente = motor.Combatente(
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
        combatente._habilidades_simulador = habilidades_ficha
        combatente._usos_simulador = {}
        combatente._efeitos_simulador = []
        combatente._sequencia_simulador = 0
        grupo.append(combatente)
    return grupo


def montar_inimigo(dados: dict, indice: int = 0) -> motor.Inimigo:
    """Adapta os golpes básicos do bestiário ao modelo de combate do motor."""
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


def registrar_uso(personagem, habilidade) -> bool:
    """Consome um uso respeitando chave compartilhada e quantidade declarada."""
    chave = habilidade.chave_de_uso
    usados = personagem._usos_simulador.get(chave, 0)
    if usados >= habilidade.vezes:
        return False
    personagem._usos_simulador[chave] = usados + 1
    return True


def _aplicar_efeitos(alvo, efeitos: dict, turnos: int, rodada: int) -> None:
    """Aplica os mesmos campos de efeito que o motor lê durante o combate."""
    mapa = {
        "ca": "ca_extra",
        "dano_arma": "dano_arma",
        "ataques": "ataques",
        "ameaca": "ameaca_extra",
        "dano_extra": "dano_extra",
        "dano_bonus": "dano_bonus",
        "vantagem": "vantagem",
        "reducao_dano": "reducao_dano",
        "ameaca_fator": "ameaca_fator",
        "cura_por_turno": "cura_por_turno",
        "critico_em": "critico_em",
        "veneno_no_golpe": "veneno_no_golpe",
    }
    aplicados = {}
    for chave, valor in efeitos.items():
        atributo = mapa.get(chave)
        if atributo is None:
            continue
        anterior = getattr(alvo, atributo)
        if isinstance(valor, (int, float)) and isinstance(anterior, (int, float)):
            novo = anterior + valor if chave in ("ca", "ameaca", "dano_extra") else valor
        else:
            novo = valor
        setattr(alvo, atributo, novo)
        aplicados[atributo] = anterior
    if aplicados:
        alvo._efeitos_simulador.append((rodada + max(1, turnos), aplicados))


def _expirar_efeitos(combatentes, rodada: int) -> None:
    for personagem in combatentes:
        pendentes = []
        for expira, anteriores in personagem._efeitos_simulador:
            if rodada >= expira:
                for atributo, valor in anteriores.items():
                    setattr(personagem, atributo, valor)
            else:
                pendentes.append((expira, anteriores))
        personagem._efeitos_simulador = pendentes


def _melhor_alvo_cura(grupo):
    vivos_ou_caidos = [c for c in grupo if c.hp_atual < c.hp_max]
    return max(
        vivos_ou_caidos,
        key=lambda c: (c.hp_max - c.hp_atual) / max(1, c.hp_max),
        default=None,
    )


def _usar_cura(personagem, grupo, acao, rng, cura_total):
    alvo = personagem if acao.get("alvo") == "proprio" else _melhor_alvo_cura(grupo)
    if alvo is None:
        return 0
    if acao.get("fracao") is not None:
        curado = motor.curar(alvo, acao["fracao"])
    elif acao.get("dado"):
        curado = motor.curar_quanto(alvo, motor.rolar_dano(acao["dado"], rng))
    else:
        curado = 0
    cura_total[0] += curado
    thp = acao.get("thp_proprio")
    if thp:
        motor.ganhar_thp(personagem, motor.rolar_dano(thp, rng))
    return curado


def estado_rodada_simulador(alvo):
    return getattr(alvo, "_rodada_simulador", 1)


def _usar_grupo(personagem, grupo, acao, rng, cura_total):
    cura = 0
    for alvo in grupo:
        if acao.get("cura_fracao"):
            ganho = motor.curar(alvo, acao["cura_fracao"])
            cura += ganho
            cura_total[0] += ganho
        if acao.get("thp"):
            motor.ganhar_thp(alvo, motor.rolar_dano(acao["thp"], rng))
    efeitos = acao.get("efeitos") or {}
    if efeitos:
        for alvo in grupo:
            _aplicar_efeitos(alvo, efeitos, acao.get("turnos", 1), estado_rodada_simulador(alvo))
    return cura


def _usar_save(personagem, estado, habilidade, acao, rng, dano_total):
    nivel = max(1, getattr(personagem, "_nivel_simulador", 1))
    cd = classes.cd_de_habilidade(personagem.classe, nivel)
    efeitos = getattr(personagem, "_efeitos_classe_simulador", {})
    cd += efeitos.get("cd_magia", 0)
    desvantagem = bool(efeitos.get("save_com_desvantagem"))
    dado_extra = efeitos.get("dano_magia") or ""
    inimigos = estado.inimigos_vivos
    if acao.get("alvos") != "todos":
        inimigos = sorted(inimigos, key=lambda i: i.hp_atual)[:1 + efeitos.get("alvos_extra", 0)]
    for inimigo in list(inimigos):
        if acao.get("sem_save"):
            passou = False
        else:
            passou = motor.salvar_inimigo(
                inimigo, acao.get("save", "CON"), cd, rng,
                desvantagem=desvantagem,
            ).passou
        if acao.get("dano"):
            dano = motor.rolar_dano(acao["dano"], rng)
            if dado_extra:
                dano += motor.rolar_dano(dado_extra, rng)
            sofrido = dano // 2 if passou and acao.get("metade") else (0 if passou else dano)
            inimigo.hp_atual = max(0, inimigo.hp_atual - sofrido)
            dano_total[0] += sofrido
        if not passou and acao.get("atordoa") and not inimigo.caido:
            inimigo.atordoado = True
        if not passou and acao.get("penalidade_ataque"):
            inimigo.penalidade_ataque = max(
                inimigo.penalidade_ataque, acao["penalidade_ataque"]
            )
        if not passou and acao.get("dano_por_rodada") and not inimigo.caido:
            inimigo._dano_rodada_simulador = (
                acao["dano_por_rodada"], acao.get("save", "CON"), cd,
                acao.get("turnos", 3),
            )


def _executar_ativa(personagem, grupo, estado, habilidade, rng, rodada,
                    dano_total, cura_total, recursos):
    acao = habilidade.acao or {}
    tipo = acao.get("tipo")
    if tipo == "reacao":
        return False
    if tipo == "cura":
        if not any(c.hp_atual < c.hp_max for c in grupo):
            return False
        _usar_cura(personagem, grupo, acao, rng, cura_total)
    elif tipo == "grupo":
        if not any(c.hp_atual < c.hp_max or acao.get("thp") for c in grupo):
            return False
        _usar_grupo(personagem, grupo, acao, rng, cura_total)
    elif tipo == "save":
        if not estado.inimigos_vivos:
            return False
        _usar_save(personagem, estado, habilidade, acao, rng, dano_total)
    elif tipo == "duracao":
        alvo_tipo = acao.get("alvo", "proprio")
        if alvo_tipo == "inimigo":
            alvo = estado.alvo_preferido()
            if alvo is None:
                return False
            efeitos = acao.get("efeitos") or {}
            if efeitos.get("dano_bonus"):
                personagem.dano_por_alvo[alvo.indice] = (
                    habilidade.nome, efeitos["dano_bonus"]
                )
            if efeitos.get("vantagem"):
                personagem.vantagem_contra.add(alvo.indice)
            if efeitos.get("ameaca_fator") is not None:
                personagem.ameaca_fator = efeitos["ameaca_fator"]
        elif alvo_tipo == "aliados":
            alvos = sorted(
                [c for c in grupo if not c.caido and c is not personagem],
                key=lambda c: c.ataques * media_dado(c.dano_arma),
                reverse=True,
            )[:acao.get("alvos", 1)]
            if acao.get("inclui_quem_usou"):
                alvos = (alvos + [personagem])[:acao.get("alvos", 1)]
            for alvo in alvos:
                _aplicar_efeitos(alvo, acao.get("efeitos") or {}, acao.get("turnos", 1), rodada)
        else:
            _aplicar_efeitos(personagem, acao.get("efeitos") or {}, acao.get("turnos", 1), rodada)
        if acao.get("acoes"):
            _atacar_com_acao(personagem, estado, acao, rng, dano_total)
    elif tipo == "forma":
        alvo = personagem
        dano = (acao.get("dano") or {}).get(
            min(rules.tier(getattr(personagem, "_nivel_simulador", 1)),
                max((acao.get("dano") or {1: personagem.dano_arma})))
        )
        if dano:
            _aplicar_efeitos(
                alvo,
                {"dano_arma": dano, "ca": acao.get("ca", 0),
                 "ataques": acao.get("ataques", 1)},
                acao.get("turnos", 3), rodada,
            )
        if acao.get("thp_por_tier"):
            motor.ganhar_thp(
                alvo, acao["thp_por_tier"] * rules.tier(personagem._nivel_simulador)
            )
    elif tipo == "invocar":
        invocado = motor.Combatente(
            user_id=100000 + personagem.user_id,
            nome=acao.get("nome", "Invocação"),
            ca=acao.get("ca", 10),
            bonus_ataque=acao.get("ataque", 0),
            dano_arma=acao.get("dano", "1"),
            hp_max=acao.get("hp", 1),
            hp_atual=acao.get("hp", 1),
            ameaca=acao.get("ameaca", 0),
            classe=personagem.classe,
            dono=personagem.user_id,
        )
        invocado._habilidades_simulador = []
        invocado._usos_simulador = {}
        invocado._efeitos_simulador = []
        invocado._sequencia_simulador = 0
        estado.combatentes.append(invocado)
    elif tipo == "golpes":
        _atacar_com_acao(personagem, estado, acao, rng, dano_total)
        if acao.get("thp_proprio"):
            motor.ganhar_thp(personagem, motor.rolar_dano(acao["thp_proprio"], rng))
        if acao.get("bonus_uma_vez") and acao.get("thp_igual_ao_bonus"):
            motor.ganhar_thp(
                personagem, motor.rolar_dano(acao["bonus_uma_vez"], rng)
            )
    else:
        return False
    recursos[0] += 1
    return True


def _atacar_com_acao(personagem, estado, acao, rng, dano_total):
    alvo = estado.alvo_preferido()
    if alvo is None:
        return
    if acao.get("exige") and not getattr(personagem, "_reckless_ativo_simulador", False):
        return
    if acao.get("quantidade") is not None:
        quantidade = max(1, int(acao["quantidade"]))
    else:
        quantidade = max(1, personagem.ataques) * max(1, int(acao.get("acoes", 1)))
    bonus_uma_vez = acao.get("bonus_uma_vez")
    for indice in range(quantidade):
        if alvo.caido:
            alvo = estado.alvo_preferido()
            if alvo is None:
                break
        extra = acao.get("dano_bonus") or ""
        if bonus_uma_vez and indice == 0:
            extra = bonus_uma_vez
        golpe = motor.atacar_inimigo(
            personagem, alvo, rng,
            dano_bonus=extra or None,
            garantido=bool(acao.get("garantido")),
            critico_forcado=bool(acao.get("critico")),
        )
        dano_total[0] += golpe.dano
        if acao.get("atordoa") and golpe.acertou and not alvo.caido:
            alvo.atordoado = True
    if acao.get("furtividade"):
        personagem._furtividade_ate_simulador = (
            estado.rodada + acao["furtividade"]
        )


def _escolher_ativa(personagem, grupo, estado, rodada):
    """Política automática: cura quando necessária; buffs/recursos cedo."""
    candidatas = []
    for _, habilidade in personagem._habilidades_simulador:
        if not habilidade.acionavel or habilidade.acao.get("tipo") == "reacao":
            continue
        if personagem._usos_simulador.get(habilidade.chave_de_uso, 0) >= habilidade.vezes:
            continue
        acao = habilidade.acao or {}
        if acao.get("exige") and not getattr(personagem, "_reckless_ativo_simulador", False):
            continue
        tipo = acao.get("tipo")
        if tipo == "cura":
            feridos = sum(c.hp_max - c.hp_atual for c in grupo)
            if feridos <= 0:
                continue
            nota = feridos / max(1, sum(c.hp_max for c in grupo)) * 100
        elif tipo == "grupo":
            feridos = sum(c.hp_max - c.hp_atual for c in grupo)
            if feridos <= 0 and not acao.get("thp"):
                continue
            nota = 20 + feridos / max(1, sum(c.hp_max for c in grupo)) * 30
        elif tipo in ("save", "golpes", "invocar", "forma"):
            nota = pontuar_acao(acao)
        elif tipo == "duracao":
            nota = pontuar_acao(acao)
            if acao.get("alvo") == "inimigo" and not estado.inimigos_vivos:
                continue
        else:
            continue
        candidatas.append((nota, habilidade))
    if not candidatas:
        return None
    # Habilidade de maior retorno esperado; desempate estável pelo id.
    return max(candidatas, key=lambda par: (par[0], par[1].id))[1]


def simular_uma_luta(classe_id: str, tier: int, rng: random.Random, pool: list[dict]) -> dict:
    """Executa uma luta com as primitivas de combate do motor."""
    grupo = montar_grupo(classe_id, tier)
    nivel = rules.nivel_do_tier(tier)
    _, escolhas = habilidades_da_ficha(classe_id, nivel)
    efeitos_classe = classes.efeitos(classe_id, nivel, escolhas)
    for personagem in grupo:
        personagem._nivel_simulador = nivel
        personagem._efeitos_classe_simulador = efeitos_classe
    inimigo = montar_inimigo(rng.choice(pool))
    estado = motor.EstadoCombate([inimigo], rodada=1, combatentes=grupo)

    dano_grupo = dano_inimigo = cura_total = recursos_gastos = 0
    rodadas = 0
    while not estado.encerrado and rodadas < MAX_RODADAS:
        rodadas += 1
        estado.rodada = rodadas
        _expirar_efeitos(estado.combatentes, rodadas)
        for combatente in estado.combatentes:
            combatente._rodada_simulador = rodadas

        for personagem in list(estado.ativos):
            if estado.encerrado or inimigo.caido:
                break
            if personagem.e_invocacao:
                golpe = motor.atacar_inimigo(personagem, inimigo, rng)
                dano_grupo += golpe.dano
                personagem.ameaca_gerada += ameaca.gerada_por(personagem.classe)
                continue

            habilidade = _escolher_ativa(personagem, estado.combatentes, estado, rodadas)
            usou = False
            if habilidade is not None:
                # Ações com condição de uso só consomem recurso se puderem resolver.
                if registrar_uso(personagem, habilidade):
                    acumuladores = {"dano": [0], "cura": [0], "recursos": [0]}
                    usou = _executar_ativa(
                        personagem, estado.combatentes, estado, habilidade, rng,
                        rodadas, acumuladores["dano"], acumuladores["cura"],
                        acumuladores["recursos"],
                    )
                    dano_grupo += acumuladores["dano"][0]
                    cura_total += acumuladores["cura"][0]
                    recursos_gastos += acumuladores["recursos"][0]
                    if usou:
                        # Atualiza os totais após a execução.
                        pass
                    else:
                        personagem._usos_simulador[habilidade.chave_de_uso] -= 1
            if not usou and not estado.encerrado:
                for _ in range(max(1, personagem.ataques)):
                    alvo = estado.alvo_preferido()
                    if alvo is None:
                        break
                    golpe = motor.atacar_inimigo(personagem, alvo, rng)
                    dano_grupo += golpe.dano
                    sequencia = efeitos_classe.get("sequencia") or {}
                    if sequencia:
                        personagem._sequencia_simulador = motor.proxima_sequencia(
                            personagem._sequencia_simulador, golpe.acertou,
                            sequencia.get("por_acerto", 1), sequencia.get("teto", 2),
                        )
                        personagem.bonus_ataque = (
                            classes.numeros(classe_id, nivel).acerto
                            + efeitos_classe.get("acerto", 0)
                            + personagem._sequencia_simulador
                        )
            acao_ameaca = (habilidade.acao or {}) if usou and habilidade else {"tipo": "golpes"}
            personagem.ameaca_gerada += ameaca.gerada_por(personagem.classe, acao_ameaca)

        if estado.encerrado:
            break

        # Regeneração, multiataques, alvos por ameaça e saves continuam no motor.
        antes = sum(c.hp_atual + c.thp for c in estado.combatentes)
        motor.rodada_dos_inimigos(estado, rng)
        depois = sum(c.hp_atual + c.thp for c in estado.combatentes)
        dano_inimigo += max(0, antes - depois)

        # Reação real do Bárbaro: Relentless impede a queda uma vez por combate.
        for personagem in estado.combatentes:
            if personagem.e_invocacao or not personagem.caido:
                continue
            reacao = next(
                (h for _, h in personagem._habilidades_simulador
                 if h.acao and h.acao.get("tipo") == "reacao"
                 and h.acao.get("quando") == "caiu"
                 and personagem._usos_simulador.get(h.chave_de_uso, 0) < h.vezes),
                None,
            )
            if reacao:
                registrar_uso(personagem, reacao)
                personagem.hp_atual = max(1, reacao.acao.get("hp", 1))
                thp = reacao.acao.get("thp")
                if thp:
                    motor.ganhar_thp(personagem, motor.rolar_dano(thp, rng))

        # Condições temporárias de controle duram o número de turnos declarado.
        for alvo in estado.inimigos:
            if alvo.atordoado:
                alvo.atordoado = False
            efeito = getattr(alvo, "_dano_rodada_simulador", None)
            if efeito and not alvo.caido:
                expressao, atributo, cd, restante = efeito
                save = motor.salvar_inimigo(alvo, atributo, cd, rng)
                if not save.passou:
                    dano = motor.rolar_dano(expressao, rng)
                    alvo.hp_atual = max(0, alvo.hp_atual - dano)
                    dano_grupo += dano
                restante -= 1
                alvo._dano_rodada_simulador = (
                    (expressao, atributo, cd, restante) if restante > 0 else None
                )

        # Furtividade suspende o crescimento de ameaça durante o prazo declarado.
        for personagem in estado.combatentes:
            if getattr(personagem, "_furtividade_ate_simulador", 0) >= rodadas:
                continue
            # A ameaça por ação é acumulada pelo motor de domínio, não por golpe.
            pass

    hp_restante = sum(max(0, c.hp_atual) for c in grupo)
    hp_total = sum(c.hp_max for c in grupo)
    return {
        "venceu": inimigo.caido,
        "rodadas": rodadas,
        "dano_grupo": dano_grupo,
        "dano_recebido": dano_inimigo,
        "cura_total": cura_total,
        "recursos_gastos": recursos_gastos,
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
        "vitoria_pct": round(100 * sum(r["venceu"] for r in resultados) / simulacoes, 2),
        "rodadas_media": round(statistics.mean(r["rodadas"] for r in resultados), 2),
        "dano_grupo_rodada": round(
            statistics.mean(r["dano_grupo"] / max(1, r["rodadas"]) for r in resultados), 2
        ),
        "dano_recebido_medio": round(statistics.mean(r["dano_recebido"] for r in resultados), 2),
        "cura_media": round(statistics.mean(r["cura_total"] for r in resultados), 2),
        "recursos_gastos_media": round(
            statistics.mean(r["recursos_gastos"] for r in resultados), 2
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
                f"cura={resultado['cura_media']:7.2f} "
                f"recursos={resultado['recursos_gastos_media']:5.2f} "
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
