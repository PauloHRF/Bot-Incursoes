"""O catálogo de habilidades por classe e tier.

`efeito` é o que o motor aplica sozinho hoje:

    bonus_teste    soma em todo teste de perícia
    bonus_pericia  soma nas perícias listadas
    dano_extra     soma no dano de cada golpe
    dano_ferido    soma só contra alvo com metade ou menos do HP
    critico_em     o menor d20 que já é crítico
    ataques        quantos golpes por rodada

Ativas e escolhas ficam sem efeito: aparecem na ficha e no aviso de nível, mas
ainda não mexem em conta nenhuma — elas entram junto com o sistema de usos
(por combate, por descanso, por incursão), numa fatia própria.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

PASSIVA, ATIVA, ESCOLHA = "passiva", "ativa", "escolha"


@dataclass(frozen=True)
class Habilidade:
    """Uma habilidade de tier.

    `efeito` é o que o bot aplica sozinho (passivas). `acao` é o que ele sabe
    executar quando o jogador aciona, e `usos` diz quantas vezes e com que
    frequência — por combate, por descanso ou por incursão.
    """

    id: str
    nome: str
    tipo: str
    texto: str
    efeito: Optional[dict] = None
    usos: Optional[dict] = None
    acao: Optional[dict] = None
    # Dois caminhos da mesma habilidade dividem o mesmo contador de usos.
    recarga_com: Optional[str] = None

    @property
    def automatica(self) -> bool:
        """Se o bot já aplica esta habilidade sem ninguém pedir."""
        return self.efeito is not None

    @property
    def acionavel(self) -> bool:
        """Se o jogador já consegue usar esta habilidade pelo bot."""
        return self.acao is not None

    @property
    def pronta(self) -> bool:
        return self.automatica or self.acionavel

    @property
    def chave_de_uso(self) -> str:
        return self.recarga_com or self.id

    @property
    def escopo(self) -> str:
        return (self.usos or {}).get("por", "combate")

    @property
    def vezes(self) -> int:
        return (self.usos or {}).get("vezes", 1)


# Quantas vezes e de quanto em quanto tempo. O escopo diz quando zera:
#   combate  — a cada sala de combate
#   descanso — a cada sala de Descanso (e no comeco da run)
#   incursao — uma vez por run
def _usos(por: str, vezes: int = 1) -> dict:
    return {"por": por, "vezes": vezes}


MULTIATAQUE = Habilidade(
    "multiataque", "Multiattack", PASSIVA, "Ataca 2x por rodada.", {"ataques": 2}
)


HABILIDADES: dict[str, dict[int, list[Habilidade]]] = {
    "ladino": {
        1: [Habilidade("reliable_talent", "Reliable Talent", PASSIVA,
                       "Soma +5 em todo teste de pericia.", {"bonus_teste": 5})],
        2: [Habilidade("expertise_1", "Expertise", ESCOLHA,
                       "Escolhe 2 pericias com proficiencia; o bonus delas dobra.")],
        3: [Habilidade("uncanny_dodge", "Uncanny Dodge", ATIVA,
                       "1x por combate: corta pela metade o primeiro golpe pesado que sofrer.",
                       usos=_usos("combate"),
                       acao={"tipo": "reacao", "quando": "sofreu_golpe",
                             "reduz": 0.5, "limiar": 1 / 3})],
        4: [Habilidade("expertise_2", "Expertise", ESCOLHA,
                       "Escolhe mais 2 pericias com proficiencia; o bonus delas dobra.")],
        5: [Habilidade("reliable_talent_mais", "Reliable Talent +", PASSIVA,
                       "Soma +10 em todo teste de pericia.", {"bonus_teste": 10})],
    },
    "barbaro": {
        1: [Habilidade("rage", "Rage", ATIVA,
                       "1x por combate: 50% menos dano e +2 de dano por 3 turnos.",
                       usos=_usos("combate"),
                       acao={"tipo": "duracao", "turnos": 3, "alvo": "proprio",
                             "efeitos": {"dano_extra": 2, "reducao_dano": 0.5}})],
        2: [Habilidade("primal_knowledge", "Primal Knowledge", ESCOLHA,
                       "Ganha proficiencia em mais 2 pericias.")],
        3: [MULTIATAQUE,
            Habilidade("reckless_attack", "Reckless Attack", ATIVA,
                       "1x por combate: os ataques do proximo turno tem vantagem.",
                       usos=_usos("combate"),
                       acao={"tipo": "duracao", "turnos": 1, "alvo": "proprio",
                             "efeitos": {"vantagem": True}})],
        4: [Habilidade("relentless", "Relentless", ATIVA,
                       "1x por combate: ao cair a 0 HP fica com 1 HP e ganha 1d12+7 de THP.",
                       usos=_usos("combate"),
                       acao={"tipo": "reacao", "quando": "caiu", "hp": 1,
                             "thp": "1d12+7"})],
        5: [Habilidade("brutal_strike", "Brutal Strike", ATIVA,
                       "1x por incursao: com Reckless Attack ligado, +1d10 de dano e o "
                       "mesmo em THP.",
                       usos=_usos("incursao"),
                       acao={"tipo": "golpes", "quantidade": 1, "dano_bonus": "1d10",
                             "thp_igual_ao_bonus": True, "exige": "reckless_attack"})],
    },
    "guerreiro": {
        1: [Habilidade("second_wind", "Second Wind", ATIVA,
                       "1x por combate: recupera 30% do HP maximo.",
                       usos=_usos("combate"),
                       acao={"tipo": "cura", "fracao": 0.3, "alvo": "proprio"})],
        2: [Habilidade("fighting_style", "Fighting Style", ESCOLHA,
                       "Escolhe um: +1 acerto, +1 CA ou +2 de dano.")],
        3: [MULTIATAQUE,
            Habilidade("action_surge", "Action Surge", ATIVA,
                       "1x por combate: um ataque adicional imediato.",
                       usos=_usos("combate"),
                       acao={"tipo": "golpes", "quantidade": 1})],
        4: [Habilidade("improved_critical", "Improved Critical", PASSIVA,
                       "Critico com 19 ou 20 no dado.", {"critico_em": 19})],
        5: [Habilidade("action_mastery", "Action Mastery", ATIVA,
                       "1x por combate: dois ataques consecutivos.",
                       usos=_usos("combate"),
                       acao={"tipo": "golpes", "quantidade": 2})],
    },
    "monge": {
        1: [Habilidade("flurry_of_blows", "Flurry of Blows", ATIVA,
                       "1x por descanso: um ataque adicional imediato.",
                       usos=_usos("descanso"),
                       acao={"tipo": "golpes", "quantidade": 1})],
        2: [Habilidade("martial_arts", "Martial Arts", PASSIVA,
                       "Ao acertar, o proximo ataque ganha +1 acerto, ate +2; errar zera.",
                       {"sequencia": {"por_acerto": 1, "teto": 2}})],
        3: [MULTIATAQUE,
            Habilidade("stunning_strike", "Stunning Strike", ATIVA,
                       "1x por descanso: um ataque que, se acertar, atordoa por 1 rodada. "
                       "So gasta o uso quando acerta.",
                       usos=_usos("descanso"),
                       acao={"tipo": "golpes", "quantidade": 1, "atordoa": 1})],
        4: [Habilidade("mente_e_corpo", "Mente e Corpo", PASSIVA,
                       "+2 em Acrobacia, Atletismo, Percepcao, Furtividade e Sobrevivencia.",
                       {"bonus_pericia": {"Acrobacia": 2, "Atletismo": 2, "Percepção": 2,
                                          "Furtividade": 2, "Sobrevivência": 2}})],
        5: [Habilidade("perfect_strike", "Perfect Strike", ATIVA,
                       "1x por combate: um ataque que acerta e ja sai critico.",
                       usos=_usos("combate"),
                       acao={"tipo": "golpes", "quantidade": 1,
                             "garantido": True, "critico": True})],
    },
    "patrulheiro": {
        1: [Habilidade("marca_do_cacador", "Marca do Cacador", ATIVA,
                       "1x por combate: marca um inimigo por 3 turnos, com +1d6 de dano nele.",
                       usos=_usos("combate"),
                       acao={"tipo": "duracao", "turnos": 3, "alvo": "inimigo",
                             "efeitos": {"dano_bonus": "1d6"}})],
        2: [Habilidade("predador", "Predador", PASSIVA,
                       "+2 de dano contra inimigos com metade ou menos do HP.",
                       {"dano_ferido": 2})],
        3: [MULTIATAQUE,
            Habilidade("rajada_do_cacador", "Rajada do Cacador", ATIVA,
                       "1x por descanso: um ataque em ate 3 inimigos diferentes.",
                       usos=_usos("descanso"),
                       acao={"tipo": "golpes", "quantidade": 1, "alvos": 3})],
        4: [Habilidade("sobrevivente", "Sobrevivente", PASSIVA,
                       "+2 em Percepcao, Sobrevivencia e Natureza.",
                       {"bonus_pericia": {"Percepção": 2, "Sobrevivência": 2,
                                          "Natureza": 2}}),
            Habilidade("sobrevivente_repeticao", "Sobrevivente — repeticao", ATIVA,
                       "1x por incursao: repete um teste falhado dessas tres pericias.",
                       usos=_usos("incursao"))],
        5: [Habilidade("cacador_supremo", "Cacador Supremo", ATIVA,
                       "1x por descanso: uma presa por 3 turnos, com +2d8 e vantagem.",
                       usos=_usos("descanso"),
                       acao={"tipo": "duracao", "turnos": 3, "alvo": "inimigo",
                             "efeitos": {"dano_bonus": "2d8", "vantagem": True}})],
    },
    "paladino": {
        1: [Habilidade("cura_pelas_maos", "Cura pelas Maos", ATIVA,
                       "1x por descanso: cura um aliado em 30% do HP maximo dele.",
                       usos=_usos("descanso"),
                       acao={"tipo": "cura", "fracao": 0.3, "alvo": "aliado"})],
        2: [Habilidade("golpe_consagrado", "Golpe Consagrado", PASSIVA,
                       "Os ataques causam +2 de dano radiante.", {"dano_extra": 2})],
        3: [Habilidade("golpe_divino", "Golpe Divino", ATIVA,
                       "1x por combate: um ataque com +3d8 de dano radiante.",
                       usos=_usos("combate"),
                       acao={"tipo": "golpes", "quantidade": 1, "dano_bonus": "3d8"})],
        4: [Habilidade("lider_sagrado", "Lider Sagrado", PASSIVA,
                       "+2 em Persuasao, Intuicao, Religiao e Intimidacao.",
                       {"bonus_pericia": {"Persuasão": 2, "Intuição": 2, "Religião": 2,
                                          "Intimidação": 2}}),
            Habilidade("lider_sagrado_repeticao", "Lider Sagrado — repeticao", ATIVA,
                       "1x por incursao: um aliado repete um teste falhado.",
                       usos=_usos("incursao"))],
        5: [Habilidade("avatar_da_luz", "Avatar da Luz", ATIVA,
                       "1x por incursao: 3 turnos com +2 CA, +5 de dano e cura por turno.",
                       usos=_usos("incursao"),
                       acao={"tipo": "duracao", "turnos": 3, "alvo": "proprio",
                             "efeitos": {"ca": 2, "dano_extra": 5,
                                         "cura_por_turno": 0.05}})],
    },
    "xama": {
        1: [Habilidade("tradicao_marcial", "Tradicao xamanica — marcial", ATIVA,
                       "1x por descanso: um ataque com +1d6 de dano; voce ganha 1d6 de THP.",
                       usos=_usos("descanso"), recarga_com="tradicao_xamanica",
                       acao={"tipo": "golpes", "quantidade": 1, "dano_bonus": "1d6",
                             "thp_proprio": "1d6"}),
            Habilidade("tradicao_espiritual", "Tradicao xamanica — espiritual", ATIVA,
                       "1x por descanso: cura um aliado e da 1d6+3 de THP a ele.",
                       usos=_usos("descanso"), recarga_com="tradicao_xamanica",
                       acao={"tipo": "cura", "fracao": 0.3, "alvo": "aliado",
                             "thp_alvo": "1d6+3"})],
        2: [Habilidade("convocacao_totemica", "Convocacao totemica", PASSIVA,
                       "Com 18+ no d20 ganha 2 THP; com THP, o grupo ganha +1 em tudo.",
                       {"totem": {"gatilho": 18, "thp": 2, "aura": 1}})],
        3: [Habilidade("escolha_totemica", "Multiattack ou Cantico Benevolente", ESCOLHA,
                       "Escolhe entre atacar 2x por rodada ou dar 4 THP extra ao curar."),
            Habilidade("danca_totemica", "Danca totemica", ATIVA,
                       "1x por descanso: o grupo ganha 2d6+4 de THP e +1d6+4 no proximo ataque.",
                       usos=_usos("descanso"),
                       acao={"tipo": "grupo", "thp": "2d6+4", "turnos": 1,
                             "efeitos": {"dano_bonus": "1d6+4"}})],
        4: [Habilidade("sintonizacao_ancestral", "Sintonizacao Ancestral", PASSIVA,
                       "+2 em Historia, Natureza, Medicina, Adestrar Animais e Intuicao.",
                       {"bonus_pericia": {"História": 2, "Natureza": 2, "Medicina": 2,
                                          "Adestrar Animais": 2, "Intuição": 2}})],
        5: [Habilidade("expansao_totemica", "Expansao totemica", PASSIVA,
                       "Com THP, o grupo ganha +2 em acertos e +3 em cura e dano.",
                       {"totem": {"gatilho": 18, "thp": 2, "aura": 2, "aura_dano": 3}}),
            Habilidade("guerreiros_ancioes", "Guerreiros ancioes", ATIVA,
                       "1x por incursao: o proximo ataque dos aliados crita com 18+.",
                       usos=_usos("incursao"),
                       acao={"tipo": "grupo", "turnos": 1,
                             "efeitos": {"critico_em": 18}})],
    },
}


# O que o motor entende, e o valor neutro de cada coisa.
NEUTRO: dict = {
    "totem": {},
    "sequencia": {},
    "bonus_teste": 0,
    "bonus_pericia": {},
    "dano_extra": 0,
    "dano_ferido": 0,
    "critico_em": 20,
    "ataques": 1,
}


def juntar(lista: list[Habilidade]) -> dict:
    """Soma numa coisa só o que as passivas da lista fazem.

    Quando duas mexem no mesmo número vale a melhor — é o caso do Reliable
    Talent, que o tier 5 substitui por uma versão mais forte.
    """
    juntos: dict = {
        chave: (dict(valor) if isinstance(valor, dict) else valor)
        for chave, valor in NEUTRO.items()
    }
    for habilidade in lista:
        for chave, valor in (habilidade.efeito or {}).items():
            if chave == "sequencia":
                juntos["sequencia"] = dict(valor)
            elif chave == "totem":
                # Vale a aura mais forte: o tier 5 substitui a do tier 2.
                atual = juntos["totem"]
                if valor.get("aura", 0) >= atual.get("aura", 0):
                    juntos["totem"] = dict(valor)
            elif chave == "bonus_pericia":
                for pericia, bonus in valor.items():
                    atual = juntos["bonus_pericia"].get(pericia, 0)
                    juntos["bonus_pericia"][pericia] = max(atual, bonus)
            elif chave == "critico_em":
                juntos["critico_em"] = min(juntos["critico_em"], valor)
            elif chave in juntos:
                juntos[chave] = max(juntos[chave], valor)
    return juntos
