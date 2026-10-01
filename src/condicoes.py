"""O que uma sala deixa no personagem: os buffs e debuffs da incursão.

Módulo puro — não conhece Discord nem banco. Recebe o que o personagem carrega
(um dicionário `{condição: stacks}`) e devolve os números já somados em
`Penalidades`.

O catálogo é transcrição direta da planilha *Incursões — Buffs/Debuffs*: cada
linha dela é um par espelhado (Benção/Perdição, Coragem/Medo…), e os valores
abaixo são **o que um stack faz**, com o sinal já dentro. Não há escalonamento
por tier: o número escrito vale em toda a faixa.

Prazo: **tudo decai 1 stack por combate**, menos a Exaustão, que fica até o fim
da incursão a não ser que o descanso (ou uma habilidade) a tire.

Duas linhas da planilha não viram condição porque não têm stack nem prazo —
são efeito na hora, e vivem em `src/consequencias.py`:
  - **Cura** (+20% de HP) e **Dano** (-20% de HP), que mexem no HP atual;
  - **Graça**, que remove debuffs em vez de somar número.

Por que isto não passa por `habilidades.juntar`: lá os efeitos são consolidados
com `max()`, porque duas passivas da mesma classe nunca somam — vale a mais
forte. Um `-2` seria engolido por esse `max`. Então as condições são uma camada
à parte, aplicada por cima do que a classe já deu.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .rules import PERICIAS

DEBUFF = "debuff"
BUFF = "buff"
EXAUSTAO = "exaustao"

# De qual sala a condição vem (a coluna "Sala" da planilha).
ARMADILHA = "Armadilha"
EVENTO = "Evento"

# Os cinco grupos de perícia que a planilha trata em bloco. Os nomes são os da
# edição brasileira, como em rules.PERICIAS.
G_ATLETISMO = ("Atletismo",)
G_SABER = ("Arcanismo", "História", "Investigação", "Natureza", "Religião")
G_AGILIDADE = ("Acrobacia", "Prestidigitação", "Furtividade")
G_SOCIAL = ("Enganação", "Intimidação", "Atuação", "Persuasão")
G_ATENCAO = ("Intuição", "Medicina", "Percepção", "Sobrevivência")

# A Exaustão não decai com o combate: os números dela e o teto vêm da planilha.
EXAUSTAO_ATAQUE = -2
EXAUSTAO_TESTES = -2
EXAUSTAO_INICIATIVA = -5
TETO_EXAUSTAO = 5

# Deterioração a 10 stacks é -100% do HP máximo: a planilha tira o personagem.
TETO_DETERIORACAO = 10


@dataclass(frozen=True)
class Condicao:
    """Uma linha da planilha: o que UM stack faz, com o sinal já dentro."""

    id: str
    nome: str
    tipo: str
    icone: str
    texto: str
    # Os números de um stack.
    saves: int = 0
    ataque: int = 0
    testes: int = 0
    iniciativa: int = 0
    pericias: tuple[str, ...] = ()
    por_pericia: int = 0
    hp_maximo_pct: int = 0
    cura_recebida_pct: int = 0
    # De qual sala ela sai, quando sai de uma. Buff não tem fonte própria: o
    # Evento vencido sorteia entre todos.
    fonte: str = ""
    # Decai 1 stack por combate? Só a Exaustão não.
    decai: bool = True
    # Com estes stacks o personagem sai da incursão. None = nunca tira.
    teto: Optional[int] = None

    @property
    def ruim(self) -> bool:
        return self.tipo in (DEBUFF, EXAUSTAO)


CATALOGO: tuple[Condicao, ...] = (
    # ============================================================= DEBUFFS
    # ---------------------------------------------------- vindos da Armadilha
    Condicao(
        "deterioracao", "Deterioração", DEBUFF, "\N{DROP OF BLOOD}",
        "-10% do HP máximo.",
        hp_maximo_pct=-10, fonte=ARMADILHA, teto=TETO_DETERIORACAO,
    ),
    Condicao(
        "perdicao", "Perdição", DEBUFF, "\N{SKULL}",
        "-1 em ataques e saves.",
        ataque=-1, saves=-1, fonte=ARMADILHA,
    ),
    Condicao(
        "perturbacao", "Perturbação", DEBUFF, "\N{DIZZY SYMBOL}",
        "-1 nos testes de perícia.",
        testes=-1, fonte=ARMADILHA,
    ),
    Condicao(
        "medo", "Medo", DEBUFF, "\N{FEARFUL FACE}",
        "-2 em todo save.",
        saves=-2, fonte=ARMADILHA,
    ),
    Condicao(
        "envenenado", "Envenenado", DEBUFF, "\N{NAUSEATED FACE}",
        "-1 nos ataques e nos testes de perícia.",
        ataque=-1, testes=-1, fonte=ARMADILHA,
    ),
    Condicao(
        "debilidade", "Debilidade", DEBUFF, "\N{BROKEN HEART}",
        "-10% de tudo que recebe de cura.",
        cura_recebida_pct=-10, fonte=ARMADILHA,
    ),
    Condicao(
        "letargia", "Letargia", DEBUFF, "\N{SNAIL}",
        "-2 de iniciativa.",
        iniciativa=-2, fonte=ARMADILHA,
    ),
    # ------------------------------------------------------ vindos do Evento
    Condicao(
        "fraqueza", "Fraqueza", DEBUFF, "\N{WILTED FLOWER}",
        "-2 em Atletismo.",
        pericias=G_ATLETISMO, por_pericia=-2, fonte=EVENTO,
    ),
    Condicao(
        "tolice", "Tolice", DEBUFF, "\N{CLOWN FACE}",
        "-2 em Arcanismo, História, Investigação, Natureza e Religião.",
        pericias=G_SABER, por_pericia=-2, fonte=EVENTO,
    ),
    Condicao(
        "moleza", "Moleza", DEBUFF, "\N{SLOTH}",
        "-2 em Acrobacia, Prestidigitação e Furtividade.",
        pericias=G_AGILIDADE, por_pericia=-2, fonte=EVENTO,
    ),
    Condicao(
        "introversao", "Introversão", DEBUFF, "\N{UPSIDE-DOWN FACE}",
        "-2 em Enganação, Intimidação, Atuação e Persuasão.",
        pericias=G_SOCIAL, por_pericia=-2, fonte=EVENTO,
    ),
    Condicao(
        "insensatez", "Insensatez", DEBUFF, "\N{FOG}",
        "-2 em Intuição, Medicina, Percepção e Sobrevivência.",
        pericias=G_ATENCAO, por_pericia=-2, fonte=EVENTO,
    ),
    # ----------------------------------------------------------- a Exaustão
    Condicao(
        "exaustao", "Exaustão", EXAUSTAO, "\N{OVERHEATED FACE}",
        f"{EXAUSTAO_ATAQUE} nos ataques, {EXAUSTAO_TESTES} nos testes e "
        f"{EXAUSTAO_INICIATIVA} de iniciativa, por ponto. "
        f"Não passa com o combate: sai no descanso. "
        f"Com {TETO_EXAUSTAO} pontos o personagem sai da incursão.",
        ataque=EXAUSTAO_ATAQUE,
        testes=EXAUSTAO_TESTES,
        iniciativa=EXAUSTAO_INICIATIVA,
        fonte=EVENTO, decai=False, teto=TETO_EXAUSTAO,
    ),
    # =============================================================== BUFFS
    # O espelho de cada debuff. Não têm fonte própria: o Evento vencido
    # sorteia entre todos eles (mais a Cura e a Graça, que são instantâneas).
    Condicao(
        "sustento", "Sustento", BUFF, "\N{GREEN HEART}",
        "+10% do HP máximo.",
        hp_maximo_pct=10,
    ),
    Condicao(
        "bencao", "Benção", BUFF, "\N{SPARKLES}",
        "+1 em ataques e saves.",
        ataque=1, saves=1,
    ),
    Condicao(
        "orientacao", "Orientação", BUFF, "\N{COMPASS}",
        "+1 nos testes de perícia.",
        testes=1,
    ),
    Condicao(
        "coragem", "Coragem", BUFF, "\N{LION FACE}",
        "+2 em todo save.",
        saves=2,
    ),
    Condicao(
        "purificado", "Purificado", BUFF, "\N{DROPLET}",
        "+1 nos ataques e nos testes de perícia.",
        ataque=1, testes=1,
    ),
    Condicao(
        "vigor", "Vigor", BUFF, "\N{HERB}",
        "+10% de tudo que recebe de cura.",
        cura_recebida_pct=10,
    ),
    Condicao(
        "rapidez", "Rapidez", BUFF, "\N{HIGH VOLTAGE SIGN}",
        "+2 de iniciativa.",
        iniciativa=2,
    ),
    Condicao(
        "potencia", "Potência", BUFF, "\N{FLEXED BICEPS}",
        "+2 em Atletismo.",
        pericias=G_ATLETISMO, por_pericia=2,
    ),
    Condicao(
        "esperteza", "Esperteza", BUFF, "\N{OPEN BOOK}",
        "+2 em Arcanismo, História, Investigação, Natureza e Religião.",
        pericias=G_SABER, por_pericia=2,
    ),
    Condicao(
        "pressa", "Pressa", BUFF, "\N{DASH SYMBOL}",
        "+2 em Acrobacia, Prestidigitação e Furtividade.",
        pericias=G_AGILIDADE, por_pericia=2,
    ),
    Condicao(
        "sociavel", "Sociável", BUFF, "\N{SPEECH BALLOON}",
        "+2 em Enganação, Intimidação, Atuação e Persuasão.",
        pericias=G_SOCIAL, por_pericia=2,
    ),
    Condicao(
        "prudencia", "Prudência", BUFF, "\N{EYES}",
        "+2 em Intuição, Medicina, Percepção e Sobrevivência.",
        pericias=G_ATENCAO, por_pericia=2,
    ),
)

POR_ID: dict[str, Condicao] = {c.id: c for c in CATALOGO}

DEBUFFS = tuple(c.id for c in CATALOGO if c.tipo == DEBUFF)
BUFFS = tuple(c.id for c in CATALOGO if c.tipo == BUFF)
# O que a falha de cada sala pode deixar. A Armadilha também cobra o Dano, que
# é instantâneo e não entra aqui (ver consequencias.DANO_PCT).
DEBUFFS_DE_ARMADILHA = tuple(
    c.id for c in CATALOGO if c.tipo == DEBUFF and c.fonte == ARMADILHA
)
DEBUFFS_DE_EVENTO = tuple(
    c.id for c in CATALOGO if c.ruim and c.fonte == EVENTO
)
# As que não passam sozinhas: só saem no descanso ou por habilidade.
PERMANENTES = tuple(c.id for c in CATALOGO if not c.decai)


@dataclass
class Penalidades:
    """O saldo de todas as condições de um personagem, já somado.

    Os valores saem com o sinal que o catálogo deu: debuff vem negativo, buff
    vem positivo. Quem consome só precisa somar.
    """

    ataque: int = 0
    saves: int = 0
    testes: int = 0
    iniciativa: int = 0
    pericias: dict[str, int] = field(default_factory=dict)
    hp_maximo_pct: int = 0
    cura_recebida_pct: int = 0
    # Alguma condição bateu no teto dela: o personagem sai da incursão.
    fora: bool = False
    estourou: tuple[str, ...] = ()

    def no_teste(self, pericia: str) -> int:
        """O que entra num teste desta perícia: o geral mais o dela."""
        return self.testes + self.pericias.get(pericia, 0)


def penalidades(condicoes: dict[str, int], tier: Optional[int] = None) -> Penalidades:
    """Soma tudo que o personagem carrega. `condicoes` é {id: stacks}.

    `tier` é aceito e ignorado: os valores da planilha são fixos. O parâmetro
    fica porque quem chama tem o tier na mão e um dia pode voltar a pesar.
    """
    saldo = Penalidades()
    estourou = []
    for cid, stacks in sorted(condicoes.items()):
        condicao = POR_ID.get(cid)
        if condicao is None or stacks <= 0:
            continue
        if condicao.teto is not None and stacks >= condicao.teto:
            estourou.append(cid)
        saldo.ataque += condicao.ataque * stacks
        saldo.saves += condicao.saves * stacks
        saldo.testes += condicao.testes * stacks
        saldo.iniciativa += condicao.iniciativa * stacks
        saldo.hp_maximo_pct += condicao.hp_maximo_pct * stacks
        saldo.cura_recebida_pct += condicao.cura_recebida_pct * stacks
        for pericia in condicao.pericias:
            saldo.pericias[pericia] = (
                saldo.pericias.get(pericia, 0) + condicao.por_pericia * stacks
            )
    saldo.estourou = tuple(estourou)
    saldo.fora = bool(estourou)
    return saldo


def hp_maximo(base: int, saldo: Penalidades) -> int:
    """O HP máximo depois de Deterioração e Sustento.

    Nunca menos que 1: quem chega a -100% já saiu da incursão pelo teto da
    Deterioração, não por HP zerado.
    """
    if saldo.hp_maximo_pct == 0:
        return base
    return max(1, base + (base * saldo.hp_maximo_pct) // 100)


def cura_recebida(bruta: int, saldo: Penalidades) -> int:
    """Quanto de uma cura chega de fato, depois de Debilidade e Vigor."""
    if saldo.cura_recebida_pct == 0 or bruta <= 0:
        return bruta
    return max(0, bruta + (bruta * max(-100, saldo.cura_recebida_pct)) // 100)


def descricao(cid: str, tier: Optional[int] = None, stacks: int = 1) -> str:
    """A linha que o jogador lê. `tier` é aceito e ignorado."""
    condicao = POR_ID[cid]
    if stacks <= 1:
        return condicao.texto
    return f"{condicao.texto} (×{stacks})"


def rotulo(cid: str, stacks: int = 1) -> str:
    """Nome com o ícone e, quando empilhado, a contagem: '😨 Medo ×2'."""
    condicao = POR_ID[cid]
    sufixo = f" ×{stacks}" if stacks > 1 else ""
    return f"{condicao.icone} {condicao.nome}{sufixo}"


def _checar_catalogo() -> None:
    """O catálogo tem de fechar com rules.PERICIAS e não repetir id."""
    vistos = set()
    for condicao in CATALOGO:
        if condicao.id in vistos:
            raise ValueError(f"condição repetida no catálogo: {condicao.id}")
        vistos.add(condicao.id)
        for pericia in condicao.pericias:
            if pericia not in PERICIAS:
                raise ValueError(
                    f"{condicao.id}: {pericia!r} não é uma perícia conhecida."
                )
        if condicao.pericias and not condicao.por_pericia:
            raise ValueError(f"{condicao.id}: tem perícias mas não diz quanto vale.")


_checar_catalogo()
