"""Resolução de regras da run, sem nenhuma dependência do Discord.

Tudo aqui é função pura sobre dados simples, para que as mecânicas possam mudar
sem tocar na camada de comandos — e para que o playtest possa ser simulado.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Any, Optional

from .incursoes import Monstro, Sala
from .rules import PESO_TIER, melhor_pericia, tier

EXPR_DANO = re.compile(r"^\s*(\d+)d(\d+)\s*(?:([+-])\s*(\d+))?\s*$", re.IGNORECASE)


def _rng(rng: Optional[random.Random]) -> random.Random:
    return rng or random.SystemRandom()


def rolar_d20(rng: Optional[random.Random] = None) -> int:
    return _rng(rng).randint(1, 20)


def rolar_dano(expressao: str, rng: Optional[random.Random] = None) -> int:
    """Rola uma expressão como '2d6+3'. Nunca devolve menos que 1."""
    m = EXPR_DANO.match(expressao)
    if not m:
        raise ValueError(f"expressão de dano inválida: {expressao!r}")
    quantidade, faces, sinal, bonus = m.group(1), m.group(2), m.group(3), m.group(4)
    gerador = _rng(rng)
    total = sum(gerador.randint(1, int(faces)) for _ in range(int(quantidade)))
    if bonus:
        total += int(bonus) if sinal == "+" else -int(bonus)
    return max(1, total)


@dataclass
class ResultadoTeste:
    """Uma rolagem de perícia de um personagem contra a CD da sala."""

    user_id: int
    personagem: str
    pericia: str
    d20: int
    modificador: int
    cd: int

    @property
    def total(self) -> int:
        return self.d20 + self.modificador

    @property
    def passou(self) -> bool:
        return self.total >= self.cd

    @property
    def margem(self) -> int:
        """Progresso que este personagem contribui. Nunca negativo."""
        return max(0, self.total - self.cd)


def testar(ficha: dict[str, Any], sala: Sala, rng: Optional[random.Random] = None) -> ResultadoTeste:
    """Rola o teste da sala usando a melhor perícia da ficha entre as listadas."""
    if not sala.tem_teste or sala.cd is None:
        raise ValueError(f"a sala {sala.id} ({sala.tipo}) não é resolvida por teste de perícia")
    pericia, modificador = melhor_pericia(
        sala.pericias, ficha["atributos"], ficha["nivel"], ficha["pericias"]
    )
    return ResultadoTeste(
        user_id=ficha["user_id"],
        personagem=ficha["nome"],
        pericia=pericia,
        d20=rolar_d20(rng),
        modificador=modificador,
        cd=sala.cd,
    )


# Consequência individual de falhar, por tipo de sala (tabela do documento de design).
CONSEQUENCIA_FALHA = {
    "Armadilha": "sofre uma penalidade leve — dano superficial ou material gasto",
    "Evento": "não contribui para a descoberta, mas sai ileso",
    "Tesouro": "não leva o item extra",
    "Combate": "sofre dano e fica fora do resto do combate",
}


@dataclass
class ResolucaoSala:
    """Estado de uma sala depois que o grupo rolou."""

    sala: Sala
    resultados: list[ResultadoTeste]
    total_participantes: int

    @property
    def progresso(self) -> int:
        return sum(r.margem for r in self.resultados)

    @property
    def alvo(self) -> int:
        return self.sala.alvo_progresso or 0

    @property
    def superada(self) -> bool:
        return self.progresso >= self.alvo

    @property
    def todos_rolaram(self) -> bool:
        return len(self.resultados) >= self.total_participantes

    @property
    def encerrada(self) -> bool:
        """A sala para de aceitar rolagens quando o alvo é atingido ou todos rolaram."""
        return self.superada or self.todos_rolaram

    @property
    def quem_falhou(self) -> list[ResultadoTeste]:
        return [r for r in self.resultados if not r.passou]

    @property
    def quem_passou(self) -> list[ResultadoTeste]:
        return [r for r in self.resultados if r.passou]


def escalar_monstro(monstro: Monstro, tiers_do_grupo: list[int]) -> Monstro:
    """Ajusta o monstro à composição do grupo.

    Hoje devolve o monstro como está: a regra de escala do chefe ainda não foi
    definida. Este é o único ponto a mudar quando ela for — a soma de pesos por
    tier já vem calculada em `peso_do_grupo`.
    """
    return monstro


def peso_do_grupo(niveis: list[int]) -> int:
    """Soma dos pesos por tier dos participantes (fórmula do objetivo principal)."""
    return sum(PESO_TIER[tier(n)] for n in niveis)


@dataclass
class Combatente:
    user_id: int
    nome: str
    ca: int
    bonus_ataque: int
    dano_arma: str
    hp_max: int
    hp_atual: int

    @property
    def caido(self) -> bool:
        return self.hp_atual <= 0


@dataclass
class GolpeAtaque:
    atacante: str
    alvo: str
    d20: int
    bonus: int
    ca_alvo: int
    dano: int = 0

    @property
    def total(self) -> int:
        return self.d20 + self.bonus

    @property
    def acertou(self) -> bool:
        return self.total >= self.ca_alvo


def atacar(
    atacante_nome: str,
    bonus: int,
    dano: str,
    alvo_nome: str,
    ca_alvo: int,
    rng: Optional[random.Random] = None,
) -> GolpeAtaque:
    """Uma rolagem de ataque: d20 + bônus contra a CA. Acertou, rola o dano."""
    golpe = GolpeAtaque(atacante_nome, alvo_nome, rolar_d20(rng), bonus, ca_alvo)
    if golpe.acertou:
        golpe.dano = rolar_dano(dano, rng)
    return golpe


def progresso_da_run(linha_atual: int, total_linhas: int = 3) -> str:
    """Barra textual do avanço pelas linhas, para o embed de status."""
    cheias = max(0, min(linha_atual, total_linhas))
    return "▰" * cheias + "▱" * (total_linhas - cheias)


def barra(valor: int, maximo: int, casas: int = 10) -> str:
    """Barra proporcional para progresso de sala ou HP."""
    if maximo <= 0:
        return "▱" * casas
    cheias = max(0, min(casas, round(casas * valor / maximo)))
    return "▰" * cheias + "▱" * (casas - cheias)
