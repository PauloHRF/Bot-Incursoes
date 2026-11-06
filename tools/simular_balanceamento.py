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


def _efeito_do_golpe(dados: dict):
    efeito = dados.get("efeito")
    if not efeito:
        return None
    return SimpleNamespace(
        nome=efeito.get("nome") or dados.get("nome") or "Efeito do golpe",
        save=efeito.get("save", "CON"),
        cd=int(efeito.get("cd", 10)),
        dano=efeito.get("dano"),
        metade=bool(efeito.get("metade")),
        atordoa=int(efeito.get("atordoa") or 0),
        debuff=list(efeito.get("debuff") or []),
        save_repete=bool(efeito.get("save_repete")),
    )


def _habilidade_do_monstro(dados: dict):
    habilidade = dados.get("habilidade")
    if not habilidade:
        return None
    recarga = int(habilidade.get("recarga") or 0)
    cada = int(habilidade.get("cada") or 2)
    return SimpleNamespace(
        nome=habilidade.get("nome") or "Habilidade especial",
        alvos=max(1, int(habilidade.get("alvos") or 1)),
        save=habilidade.get("save", "CON"),
        cd=int(habilidade.get("cd") or 10),
        dano=habilidade.get("dano"),
        metade=bool(habilidade.get("metade")),
        atordoa=int(habilidade.get("atordoa") or 0),
        debuff=list(habilidade.get("debuff") or []),
        cada=int(habilidade.get("cada") or 2),
        recarga=recarga or None,
        e_ataque=habilidade.get("save") == "ATK",
        disponivel=lambda rodada: cada > 0 and rodada % cada == 0,
        recarregou=lambda rng: (
            True if not recarga else bool(rng and rng.randint(1, 6) >= recarga)
        ),
    )


def montar_inimigo(dados: dict, indice: int = 0) -> motor.Inimigo:
    """Adapta golpes, efeitos e habilidade especial ao modelo real do motor."""
    golpes = dados.get("golpes") or []
    quantidade = max(1, int((dados.get("meta") or {}).get("num_acoes") or 1))
    sequencia = golpes[:quantidade] or golpes[:1]
    ataques = [
        SimpleNamespace(
            nome=str(g.get("nome") or dados.get("nome") or "Ataque"),
            ataque=int(g.get("ataque", 0)),
            dano=str(g.get("dano") or "1"),
            efeito=_efeito_do_golpe(g),
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
        saves_vantagem=dados.get("saves_vantagem") or [],
        ataques=len(ataques),
        golpes=ataques,
        habilidade=_habilidade_do_monstro(dados),
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


_MAPA_EFEITOS = {
    "ca": "ca_extra", "dano_arma": "dano_arma", "ataques": "ataques",
    "ameaca": "ameaca_extra", "dano_extra": "dano_extra",
    "dano_bonus": "dano_bonus", "vantagem": "vantagem",
    "reducao_dano": "reducao_dano", "ameaca_fator": "ameaca_fator",
    "cura_por_turno": "cura_por_turno", "critico_em": "critico_em",
    "veneno_no_golpe": "veneno_no_golpe",
    "penalidade_ataque": "penalidade_ataque",
}
_EFEITOS_ADITIVOS = {"ca", "ameaca", "dano_extra", "penalidade_ataque"}


def _recalcular_efeitos(alvo) -> None:
    """Recalcula efeitos ativos a partir da ficha-base, sem snapshots obsoletos."""
    base = getattr(alvo, "_base_efeitos_simulador", None)
    if base is None:
        base = {
            atributo: getattr(alvo, atributo)
            for atributo in _MAPA_EFEITOS.values() if hasattr(alvo, atributo)
        }
        alvo._base_efeitos_simulador = base
    atuais = dict(base)
    for _expira, efeitos in getattr(alvo, "_efeitos_simulador", []):
        for chave, valor in efeitos.items():
            atributo = _MAPA_EFEITOS.get(chave)
            if atributo not in atuais:
                continue
            atuais[atributo] = (
                atuais[atributo] + valor if chave in _EFEITOS_ADITIVOS else valor
            )
    for atributo, valor in atuais.items():
        setattr(alvo, atributo, valor)


def _aplicar_efeitos(alvo, efeitos: dict, turnos: int, rodada: int) -> None:
    if not efeitos:
        return
    if not hasattr(alvo, "_efeitos_simulador"):
        alvo._efeitos_simulador = []
    _recalcular_efeitos(alvo)
    alvo._efeitos_simulador.append((rodada + max(1, int(turnos)), dict(efeitos)))
    _recalcular_efeitos(alvo)


def _expirar_efeitos(combatentes, rodada: int) -> None:
    for alvo in combatentes:
        efeitos = getattr(alvo, "_efeitos_simulador", [])
        alvo._efeitos_simulador = [
            (expira, valores) for expira, valores in efeitos if rodada < expira
        ]
        _recalcular_efeitos(alvo)
        alvo.atordoado = rodada <= getattr(alvo, "_atordoado_ate", rodada - 1)
        if getattr(alvo, "_reckless_ate_simulador", 0) < rodada:
            alvo._reckless_ativo_simulador = False
        marcas = getattr(alvo, "_marcas_simulador", [])
        alvo._marcas_simulador = [m for m in marcas if rodada < m[0]]
        if hasattr(alvo, "dano_por_alvo"):
            alvo.dano_por_alvo = {}
            alvo.vantagem_contra = set()
            for _expira, indice, dano, vantagem in alvo._marcas_simulador:
                if dano:
                    alvo.dano_por_alvo[indice] = dano
                if vantagem:
                    alvo.vantagem_contra.add(indice)


def _atordoar(alvo, turnos: int, rodada: int) -> None:
    if alvo.caido:
        return
    if alvo.atordoado and getattr(alvo, "_atordoado_ate", 0) > 0:
        return
    duracao = max(1, int(turnos or 1))
    # O jogador recebe o efeito na fase inimiga e perde os próximos turnos;
    # o monstro recebe na fase dos jogadores e perde a vez desta rodada.
    fim = rodada + duracao if isinstance(alvo, motor.Combatente) else rodada + duracao - 1
    alvo._atordoado_ate = max(getattr(alvo, "_atordoado_ate", rodada), fim)
    alvo.atordoado = True


def _registrar_atordoamentos(investidas, rodada: int) -> None:
    for investida in investidas:
        if getattr(investida, "atordoou", False):
            _atordoar(investida.alvo, getattr(investida, "atordoa_por", 1), rodada)


def _registrar_marca(personagem, alvo, habilidade, efeitos, rodada: int) -> None:
    if not hasattr(personagem, "_marcas_simulador"):
        personagem._marcas_simulador = []
    personagem._marcas_simulador.append((
        rodada + max(1, int(efeitos.get("turnos", 1))),
        alvo.indice,
        (habilidade.nome, efeitos["dano_bonus"]) if efeitos.get("dano_bonus") else None,
        bool(efeitos.get("vantagem")),
    ))
    _expirar_efeitos([personagem], rodada)


def _melhor_alvo_cura(grupo, excluir=None):
    candidatos = [c for c in grupo if c is not excluir and c.hp_atual < c.hp_max]
    return max(candidatos, key=lambda c: (c.caido, (c.hp_max-c.hp_atual)/max(1,c.hp_max)), default=None)


def _melhor_alvo_forma(personagem, grupo):
    aliados = [c for c in grupo if c is not personagem and not c.caido]
    return min(aliados, key=lambda c: (c.hp_atual+c.thp)/max(1,c.hp_max),
               default=personagem if not personagem.caido else None)


def _usar_cura(personagem, grupo, acao, rng, cura_total):
    alvo = personagem if acao.get("alvo") == "proprio" else _melhor_alvo_cura(grupo, excluir=personagem)
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


def _usar_grupo(personagem, grupo, estado, acao, rng, cura_total, dano_total, thp_gasto):
    cura = 0
    melhoria = acao.get("melhoria") or {}
    aprimorada = bool(melhoria.get("custo_thp") and personagem.thp >= int(melhoria["custo_thp"]))
    cura_fracao = melhoria.get("cura_fracao") if aprimorada else acao.get("cura_fracao")
    efeitos = melhoria.get("efeitos") if aprimorada else (acao.get("efeitos") or {})
    if aprimorada:
        custo = int(melhoria["custo_thp"])
        personagem.thp -= custo
        thp_gasto[0] += custo
        dano_area = melhoria.get("dano_em_todos")
        if dano_area:
            for inimigo in estado.inimigos_vivos:
                dano = motor.rolar_dano(dano_area, rng)
                inimigo.hp_atual = max(0, inimigo.hp_atual-dano)
                dano_total[0] += dano
    for alvo in grupo:
        if cura_fracao:
            ganho = motor.curar(alvo, cura_fracao)
            cura += ganho
            cura_total[0] += ganho
        if acao.get("thp"):
            motor.ganhar_thp(alvo, motor.rolar_dano(acao["thp"], rng))
    if efeitos:
        for alvo in grupo:
            _aplicar_efeitos(alvo, efeitos, acao.get("turnos", 1), estado_rodada_simulador(alvo))
    return cura


def _usar_save(personagem, estado, habilidade, acao, rng, dano_total, rodada):
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
            _atordoar(inimigo, acao.get("atordoa", 1), rodada)
        if not passou and acao.get("vantagem_do_grupo"):
            for aliado in estado.combatentes:
                if not aliado.caido:
                    _registrar_marca(aliado, inimigo, habilidade,
                        {"turnos": acao.get("turnos", 1), "vantagem": True}, rodada)
        if not passou and acao.get("penalidade_ataque"):
            _aplicar_efeitos(
                inimigo, {"penalidade_ataque": acao["penalidade_ataque"]},
                acao.get("turnos", 1), rodada,
            )
        if not passou and acao.get("dano_por_rodada") and not inimigo.caido:
            inimigo._dano_rodada_simulador = (
                acao["dano_por_rodada"], acao.get("save", "CON"), cd,
                acao.get("turnos", 3),
            )
            inimigo._dano_rodada_repete_save = bool(acao.get("save_repete", True))
            inimigo._dano_rodada_repete_save = bool(acao.get("save_repete"))


def _executar_ativa(personagem, grupo, estado, habilidade, rng, rodada,
                    dano_total, cura_total, recursos, thp_gasto):
    acao = habilidade.acao or {}
    tipo = acao.get("tipo")
    if tipo == "reacao":
        return False
    if tipo == "cura":
        pode = (personagem.hp_atual < personagem.hp_max if acao.get("alvo") == "proprio"
                else _melhor_alvo_cura(grupo, excluir=personagem) is not None)
        if not pode:
            return False
        _usar_cura(personagem, grupo, acao, rng, cura_total)
    elif tipo == "grupo":
        melhoria = acao.get("melhoria") or {}
        pode_melhorar = melhoria.get("custo_thp") and personagem.thp >= int(melhoria["custo_thp"])
        if not any(c.hp_atual < c.hp_max for c in grupo) and not acao.get("thp") and not acao.get("efeitos") and not pode_melhorar:
            return False
        _usar_grupo(personagem, grupo, estado, acao, rng, cura_total, dano_total, thp_gasto)
    elif tipo == "save":
        if not estado.inimigos_vivos or (acao.get("vira_contra") and len(estado.inimigos_vivos) < 2):
            return False
        _usar_save(personagem, estado, habilidade, acao, rng, dano_total, rodada)
    elif tipo == "duracao":
        alvo_tipo = acao.get("alvo", "proprio")
        if alvo_tipo == "inimigo":
            alvo = estado.alvo_preferido()
            if alvo is None:
                return False
            efeitos = acao.get("efeitos") or {}
            _registrar_marca(personagem, alvo, habilidade,
                {**efeitos, "turnos": acao.get("turnos", 1)}, rodada)
            if efeitos.get("ameaca_fator") is not None:
                _aplicar_efeitos(personagem, {"ameaca_fator": efeitos["ameaca_fator"]},
                                 acao.get("turnos", 1), rodada)
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
            efeitos_acao = acao.get("efeitos") or {}
            duracao = acao.get("turnos", 1)
            if efeitos_acao.get("vantagem") and efeitos_acao.get("ameaca"):
                duracao += 1
            _aplicar_efeitos(personagem, efeitos_acao, duracao, rodada)
        if (acao.get("efeitos") or {}).get("vantagem") and (acao.get("efeitos") or {}).get("ameaca"):
            personagem._reckless_ativo_simulador = True
            personagem._reckless_ate_simulador = rodada + 1
        if acao.get("acoes"):
            _atacar_com_acao(personagem, estado, acao, rng, dano_total)
    elif tipo == "forma":
        alvo = _melhor_alvo_forma(personagem, grupo) if acao.get("alvo") == "aliado" else personagem
        if alvo is None:
            return False
        tabela = acao.get("dano") or {}
        tier_atual = rules.tier(getattr(personagem, "_nivel_simulador", 1))
        tier_dano = min(tier_atual, max(tabela)) if tabela else None
        dano = tabela.get(tier_dano) if tier_dano is not None else None
        efeitos_forma = {"ca": acao.get("ca", 0), "ataques": acao.get("ataques", 1)}
        if dano:
            efeitos_forma["dano_arma"] = dano
        _aplicar_efeitos(alvo, efeitos_forma, acao.get("turnos", 3), rodada)
        alvo.forma = acao.get("nome", "Forma")
        if acao.get("thp_por_tier"):
            motor.ganhar_thp(alvo, acao["thp_por_tier"] * tier_atual)
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


def _registrar_efeito_do_ataque(personagem, alvo, golpe, rodada):
    if golpe.acertou and personagem.veneno_no_golpe and not alvo.caido:
        _aplicar_efeitos(alvo, {"penalidade_ataque": personagem.veneno_no_golpe}, 2, rodada)


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
        _registrar_efeito_do_ataque(personagem, alvo, golpe, estado.rodada)
        if acao.get("atordoa") and golpe.acertou and not alvo.caido:
            _atordoar(alvo, acao.get("atordoa", 1), estado.rodada)
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
            if feridos <= 0 and not acao.get("thp") and not acao.get("efeitos") and not acao.get("melhoria"):
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

    dano_grupo = dano_inimigo = cura_total = recursos_gastos = thp_gasto_total = 0
    inimigo._efeitos_simulador = []
    inimigo._atordoado_ate = 0
    inimigo._base_efeitos_simulador = {
        atributo: getattr(inimigo, atributo)
        for atributo in _MAPA_EFEITOS.values() if hasattr(inimigo, atributo)
    }
    rodadas = 0
    while not estado.encerrado and rodadas < MAX_RODADAS:
        rodadas += 1
        estado.rodada = rodadas
        _expirar_efeitos(estado.combatentes + estado.inimigos, rodadas)
        for combatente in estado.combatentes:
            combatente._rodada_simulador = rodadas
            if combatente.cura_por_turno and not combatente.caido:
                cura_total += motor.curar(combatente, combatente.cura_por_turno)

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
                    acumuladores = {"dano": [0], "cura": [0], "recursos": [0], "thp": [0]}
                    usou = _executar_ativa(
                        personagem, estado.combatentes, estado, habilidade, rng,
                        rodadas, acumuladores["dano"], acumuladores["cura"],
                        acumuladores["recursos"], acumuladores["thp"],
                    )
                    dano_grupo += acumuladores["dano"][0]
                    cura_total += acumuladores["cura"][0]
                    recursos_gastos += acumuladores["recursos"][0]
                    thp_gasto_total += acumuladores["thp"][0]
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
                    _registrar_efeito_do_ataque(personagem, alvo, golpe, rodadas)
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

        # Cada criatura usa o resolvedor do motor; a reação é checada logo
        # depois da ação da criatura que derrubou o personagem.
        for inimigo_turno in list(estado.inimigos_vivos):
            if estado.encerrado:
                break
            antes = sum(c.hp_atual + c.thp for c in estado.combatentes)
            vez = motor.turno_do_inimigo(inimigo_turno, estado, rng)
            _registrar_atordoamentos(vez.investidas, rodadas)
            depois = sum(c.hp_atual + c.thp for c in estado.combatentes)
            dano_inimigo += max(0, antes - depois)
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
                if reacao and registrar_uso(personagem, reacao):
                    personagem.hp_atual = max(1, reacao.acao.get("hp", 1))
                    thp = reacao.acao.get("thp")
                    if thp:
                        motor.ganhar_thp(personagem, motor.rolar_dano(thp, rng))

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
        "thp_gasto": thp_gasto_total,
        "thp_restante": sum(c.thp for c in grupo),
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
        "thp_gasto_medio": round(statistics.mean(r["thp_gasto"] for r in resultados), 2),
        "thp_restante_medio": round(statistics.mean(r["thp_restante"] for r in resultados), 2),
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
