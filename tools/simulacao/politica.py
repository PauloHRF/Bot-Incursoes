"""Escolhas automaticas explicitas; a execucao fica nos resolvedores do jogo."""
from src import classes, motor, rules

GRUPO = 5


def escolher(habilidades, quem, estado):
    """Prioridade simples e publica. Requisitos e usos chegam filtrados pelo bot."""
    candidatas = []
    grupo = estado.combatentes
    hp_grupo = max(1, sum(c.hp_max for c in grupo))
    for h in habilidades:
        a = h.acao or {}
        tipo = a.get("tipo")
        if tipo == "cura":
            alvos = [quem] if a.get("alvo") == "proprio" else grupo
            falta = sum(c.hp_max - c.hp_atual for c in alvos)
            if falta <= 0:
                continue
            nota = falta / hp_grupo * 100
        elif tipo == "grupo":
            falta = sum(c.hp_max - c.hp_atual for c in grupo)
            melhoria = a.get("melhoria") or {}
            melhora = melhoria.get("custo_thp") and quem.thp >= melhoria["custo_thp"]
            if falta <= 0 and not (a.get("efeitos") or a.get("thp") or melhora):
                continue
            nota = 20 + falta / hp_grupo * 30
            if melhora:
                nota += media_dado(melhoria.get("dano_em_todos", "")) * len(estado.inimigos_vivos)
        elif tipo in ("save", "golpes", "invocar", "forma", "duracao"):
            nota = pontuar_acao(a)
        else:
            continue
        candidatas.append((nota, h.id, h))
    return max(candidatas, key=lambda x: x[:2])[2] if candidatas else None

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
        melhoria = acao.get("melhoria") or {}
        return (
            10 + media_dado(acao.get("thp", "")) * GRUPO
            + 30 * acao.get("cura_fracao", 0)
            + media_dado(melhoria.get("dano_em_todos", "")) * 3
            + 30 * melhoria.get("cura_fracao", 0)
        )
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
