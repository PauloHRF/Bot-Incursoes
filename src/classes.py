"""As classes jogáveis e os números de cada tier.

A ficha deixou de ter atributos digitados: o jogador escolhe uma classe e as
perícias em que tem proficiência, e todo o resto — HP, CA, acerto, dano e os
bônus de perícia — sai da tabela da classe no tier atual.

As habilidades de cada tier estão em src/habilidades.py e são penduradas aqui
na carga. As passivas que são número puro já valem; as ativas e as escolhas
aparecem na ficha mas ainda não mexem em conta nenhuma.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .habilidades import (
    ATIVA,
    ESCOLHA,
    HABILIDADES,
    PASSIVA,
    Habilidade,
    juntar,
    juntar_efeito,
)
from .rules import TIER_MAXIMO, chave_comparacao, tier

# As 14 classes do grupo. Só as que têm tabela aqui podem ser escolhidas; as
# outras aparecem como "ainda não disponível" em vez de sumirem da lista.
CLASSES_PREVISTAS = (
    "Bárbaro",
    "Guerreiro",
    "Clérigo",
    "Mago",
    "Feiticeiro",
    "Bruxo",
    "Druida",
    "Monge",
    "Patrulheiro",
    "Paladino",
    "Bardo",
    "Artífice",
    "Xamã",
    "Ladino",
)


@dataclass(frozen=True)
class NumerosDoTier:
    """O que uma classe tem num tier."""

    hp: int
    ca: int
    pericias: int  # quantas proficiências o jogador escolhe
    bonus_pericia: int  # em perícia sem proficiência
    bonus_proficiencia: int  # em perícia com proficiência
    acerto: int
    dano: str


@dataclass(frozen=True)
class Classe:
    id: str
    nome: str
    resumo: str
    tiers: dict[int, NumerosDoTier]
    habilidades: dict[int, list[Habilidade]] = field(default_factory=dict)

    def numeros(self, nivel: int) -> NumerosDoTier:
        """Os números da classe no nível pedido, pelo tier correspondente."""
        alvo = min(tier(nivel), max(self.tiers))
        return self.tiers[alvo]

    def habilidades_ate(self, nivel: int) -> list[tuple[int, Habilidade]]:
        """Tudo que o personagem já tem, do tier 1 até o dele."""
        teto = min(tier(nivel), max(self.tiers))
        return [
            (t, h) for t in range(1, teto + 1) for h in self.habilidades.get(t, [])
        ]

    def habilidades_do_tier(self, tier_alvo: int) -> list[Habilidade]:
        return list(self.habilidades.get(tier_alvo, []))


__all__ = [
    "ATIVA", "CLASSES", "CLASSES_PENDENTES", "CLASSES_PREVISTAS", "Classe",
    "ESCOLHA", "Habilidade", "NumerosDoTier", "PASSIVA", "classe", "efeitos",
    "habilidades", "numeros", "tier_maximo_com_tabela",
]


def _tabela(linhas: list[tuple]) -> dict[int, NumerosDoTier]:
    return {i: NumerosDoTier(*linha) for i, linha in enumerate(linhas, start=1)}


# Cada linha e um tier:  hp, ca, pericias, bonus, prof, acerto, dano
CLASSES: dict[str, Classe] = {
    c.id: c
    for c in (
        Classe(
            "ladino",
            "Ladino",
            "Muitas perícias e o maior dado de dano por acerto.",
            _tabela([
                (17, 15, 6, 3, 5, 5, "2d6+3"),
                (31, 16, 6, 4, 7, 6, "3d6+4"),
                (45, 16, 6, 4, 8, 7, "4d6+4"),
                (59, 17, 6, 5, 10, 8, "5d6+5"),
                (73, 18, 6, 5, 11, 10, "6d6+5"),
            ]),
        ),
        Classe(
            "barbaro",
            "Bárbaro",
            "O mais duro de derrubar, com o dado de dano mais alto.",
            _tabela([
                (23, 15, 3, 3, 5, 5, "1d12+3"),
                (43, 16, 3, 4, 7, 7, "1d12+6"),
                (63, 17, 3, 4, 8, 8, "1d12+7"),
                (83, 18, 3, 5, 10, 9, "1d12+7"),
                (103, 19, 3, 5, 11, 11, "1d12+9"),
            ]),
        ),
        Classe(
            "guerreiro",
            "Guerreiro",
            "A melhor CA e o acerto mais constante.",
            _tabela([
                (21, 17, 3, 3, 5, 6, "1d10+3"),
                (39, 18, 3, 4, 7, 7, "1d10+6"),
                (57, 19, 3, 4, 8, 8, "1d10+6"),
                (75, 20, 3, 5, 10, 9, "1d10+8"),
                (93, 21, 3, 5, 11, 11, "1d10+10"),
            ]),
        ),
        Classe(
            "monge",
            "Monge",
            "Muitas perícias e ataques rápidos.",
            _tabela([
                (17, 16, 5, 3, 5, 5, "1d6+3"),
                (31, 17, 5, 4, 7, 7, "1d6+4"),
                (45, 18, 6, 4, 8, 8, "1d8+4"),
                (59, 19, 6, 5, 10, 9, "1d8+5"),
                (73, 20, 7, 5, 11, 11, "1d10+5"),
            ]),
        ),
        Classe(
            "patrulheiro",
            "Patrulheiro",
            "O melhor acerto e perícias de exploração.",
            _tabela([
                (19, 16, 6, 3, 5, 6, "1d8+3"),
                (35, 17, 6, 4, 7, 9, "1d8+4"),
                (51, 18, 7, 4, 8, 10, "1d8+4"),
                (67, 19, 7, 5, 10, 11, "1d8+5"),
                (83, 20, 8, 5, 11, 11, "1d8+5"),
            ]),
        ),
        Classe(
            "paladino",
            "Paladino",
            "Linha de frente que cura e protege o grupo.",
            _tabela([
                (21, 17, 3, 3, 5, 6, "1d8+4"),
                (39, 18, 3, 4, 7, 7, "1d8+6"),
                (57, 19, 4, 4, 8, 8, "1d8+6"),
                (75, 20, 4, 5, 10, 9, "1d8+6"),
                (93, 21, 5, 5, 11, 11, "1d8+7"),
            ]),
        ),
        Classe(
            "xama",
            "Xamã",
            "Apoio: fortalece o grupo enquanto luta.",
            _tabela([
                (17, 16, 5, 3, 5, 5, "1d6+3"),
                (31, 17, 5, 4, 7, 7, "1d6+3"),
                (45, 18, 6, 4, 8, 8, "1d6+4"),
                (59, 19, 6, 5, 10, 9, "1d8+5"),
                (73, 20, 7, 5, 11, 11, "1d10+5"),
            ]),
        ),
    )
}

# As habilidades vivem em habilidades.py e sao penduradas na classe aqui.
for _id, _tabela_hab in HABILIDADES.items():
    object.__setattr__(CLASSES[_id], "habilidades", _tabela_hab)

CLASSES_PENDENTES = tuple(
    nome
    for nome in CLASSES_PREVISTAS
    if chave_comparacao(nome) not in {chave_comparacao(c.nome) for c in CLASSES.values()}
)

_INDICE = {}
for _classe in CLASSES.values():
    _INDICE[chave_comparacao(_classe.nome)] = _classe
    _INDICE[_classe.id] = _classe


def classe(identificador: Optional[str]) -> Optional[Classe]:
    """Aceita o id ('xama'), o nome ('Xamã') ou a grafia sem acento."""
    if not identificador:
        return None
    return _INDICE.get(chave_comparacao(str(identificador)))


def numeros(identificador: Optional[str], nivel: int) -> Optional[NumerosDoTier]:
    alvo = classe(identificador)
    return alvo.numeros(nivel) if alvo else None


def habilidades(identificador: Optional[str], nivel: int) -> list[tuple[int, Habilidade]]:
    """As habilidades que o personagem já tem, com o tier de cada uma."""
    alvo = classe(identificador)
    return alvo.habilidades_ate(nivel) if alvo else []


def efeitos(
    identificador: Optional[str], nivel: int, escolhas: Optional[dict] = None
) -> dict:
    """O que as passivas e as escolhas do personagem somam, pronto para o motor.

    `escolhas` é o que o jogador decidiu em cada tier: {habilidade_id: valor}.
    """
    lista = [h for _tier, h in habilidades(identificador, nivel)]
    juntos = juntar(lista)
    for habilidade in lista:
        decidido = (escolhas or {}).get(habilidade.id)
        if not decidido or not habilidade.decidivel:
            continue
        juntar_escolha(juntos, habilidade, decidido)
    return juntos


def juntar_escolha(juntos: dict, habilidade: Habilidade, decidido) -> None:
    """Aplica uma escolha já feita sobre os efeitos acumulados."""
    forma = habilidade.escolha or {}
    if forma.get("tipo") == "opcao":
        opcao = next(
            (o for o in forma.get("opcoes", []) if o["id"] == decidido), None
        )
        if opcao:
            juntar_efeito(juntos, opcao.get("efeito") or {})
        return
    if forma.get("aplica") == "expertise":
        juntos["expertise"] = sorted(set(juntos["expertise"]) | set(decidido or []))


def escolhas_pendentes(
    identificador: Optional[str], nivel: int, feitas: Optional[dict] = None
) -> list[tuple[int, Habilidade]]:
    """As decisões que o personagem já podia ter tomado e ainda não tomou."""
    feitas = feitas or {}
    return [
        (t, h)
        for t, h in habilidades(identificador, nivel)
        if h.decidivel and not feitas.get(h.id)
    ]


def pericias_extras(identificador: Optional[str], nivel: int, escolhas: dict) -> list[str]:
    """Proficiências ganhas por escolha (Primal Knowledge), fora a cota da classe."""
    extras: list[str] = []
    for _tier, habilidade in habilidades(identificador, nivel):
        forma = habilidade.escolha or {}
        if forma.get("aplica") != "proficiencia":
            continue
        for pericia in (escolhas or {}).get(habilidade.id) or []:
            if pericia not in extras:
                extras.append(pericia)
    return extras


def tier_maximo_com_tabela() -> int:
    """Até que tier as tabelas vão hoje — o teto de nível sai daqui."""
    return min(TIER_MAXIMO, min(max(c.tiers) for c in CLASSES.values()))
