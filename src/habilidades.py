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
    id: str
    nome: str
    tipo: str
    texto: str
    efeito: Optional[dict] = None

    @property
    def automatica(self) -> bool:
        """Se o bot já aplica esta habilidade sem ninguém pedir."""
        return self.efeito is not None


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
                       "1x por combate: reduz pela metade o dano de um golpe sofrido.")],
        4: [Habilidade("expertise_2", "Expertise", ESCOLHA,
                       "Escolhe mais 2 pericias com proficiencia; o bonus delas dobra.")],
        5: [Habilidade("reliable_talent_mais", "Reliable Talent +", PASSIVA,
                       "Soma +10 em todo teste de pericia.", {"bonus_teste": 10})],
    },
    "barbaro": {
        1: [Habilidade("rage", "Rage", ATIVA,
                       "1x por combate: 50% menos dano fisico e +2 de dano por 3 turnos.")],
        2: [Habilidade("primal_knowledge", "Primal Knowledge", ESCOLHA,
                       "Ganha proficiencia em mais 2 pericias.")],
        3: [MULTIATAQUE,
            Habilidade("reckless_attack", "Reckless Attack", ATIVA,
                       "1x por combate: os ataques do proximo turno tem vantagem.")],
        4: [Habilidade("relentless", "Relentless", ATIVA,
                       "1x por combate: ao cair a 0 HP fica com 1 HP e ganha 1d12+7 de THP.")],
        5: [Habilidade("brutal_strike", "Brutal Strike", ATIVA,
                       "1x por incursao: com Reckless Attack, +1d10 de dano e o mesmo em THP.")],
    },
    "guerreiro": {
        1: [Habilidade("second_wind", "Second Wind", ATIVA,
                       "1x por combate: recupera 30% do HP maximo.")],
        2: [Habilidade("fighting_style", "Fighting Style", ESCOLHA,
                       "Escolhe um: +1 acerto, +1 CA ou +2 de dano.")],
        3: [MULTIATAQUE,
            Habilidade("action_surge", "Action Surge", ATIVA,
                       "1x por combate: realiza uma acao adicional imediatamente.")],
        4: [Habilidade("improved_critical", "Improved Critical", PASSIVA,
                       "Critico com 19 ou 20 no dado.", {"critico_em": 19})],
        5: [Habilidade("action_mastery", "Action Mastery", ATIVA,
                       "1x por combate: realiza duas acoes consecutivas.")],
    },
    "monge": {
        1: [Habilidade("flurry_of_blows", "Flurry of Blows", ATIVA,
                       "1x por descanso: apos atacar, ataca de novo imediatamente.")],
        2: [Habilidade("martial_arts", "Martial Arts", PASSIVA,
                       "Ao acertar, o proximo ataque ganha +1 acerto, ate +2; errar zera.")],
        3: [MULTIATAQUE,
            Habilidade("stunning_strike", "Stunning Strike", ATIVA,
                       "1x por descanso: ao acertar, atordoa o inimigo por 1 rodada.")],
        4: [Habilidade("mente_e_corpo", "Mente e Corpo", PASSIVA,
                       "+2 em Acrobacia, Atletismo, Percepcao, Furtividade e Sobrevivencia.",
                       {"bonus_pericia": {"Acrobacia": 2, "Atletismo": 2, "Percepção": 2,
                                          "Furtividade": 2, "Sobrevivência": 2}})],
        5: [Habilidade("perfect_strike", "Perfect Strike", ATIVA,
                       "1x por combate: o proximo ataque acerta e e critico.")],
    },
    "patrulheiro": {
        1: [Habilidade("marca_do_cacador", "Marca do Cacador", ATIVA,
                       "1x por combate: marca um inimigo por 3 turnos, com +1d6 de dano nele.")],
        2: [Habilidade("predador", "Predador", PASSIVA,
                       "+2 de dano contra inimigos com metade ou menos do HP.",
                       {"dano_ferido": 2})],
        3: [MULTIATAQUE,
            Habilidade("rajada_do_cacador", "Rajada do Cacador", ATIVA,
                       "1x por descanso: ataca ate 3 inimigos diferentes.")],
        4: [Habilidade("sobrevivente", "Sobrevivente", PASSIVA,
                       "+2 em Percepcao, Sobrevivencia e Natureza.",
                       {"bonus_pericia": {"Percepção": 2, "Sobrevivência": 2,
                                          "Natureza": 2}}),
            Habilidade("sobrevivente_repeticao", "Sobrevivente — repeticao", ATIVA,
                       "1x por incursao: repete um teste falhado dessas tres pericias.")],
        5: [Habilidade("cacador_supremo", "Cacador Supremo", ATIVA,
                       "1x por descanso: uma presa por 3 turnos, com +2d8 e vantagem.")],
    },
    "paladino": {
        1: [Habilidade("cura_pelas_maos", "Cura pelas Maos", ATIVA,
                       "1x por descanso: cura um aliado em 30% do HP maximo dele.")],
        2: [Habilidade("golpe_consagrado", "Golpe Consagrado", PASSIVA,
                       "Os ataques causam +2 de dano radiante.", {"dano_extra": 2})],
        3: [Habilidade("golpe_divino", "Golpe Divino", ATIVA,
                       "1x por combate: um acerto causa +3d8 de dano radiante.")],
        4: [Habilidade("lider_sagrado", "Lider Sagrado", PASSIVA,
                       "+2 em Persuasao, Intuicao, Religiao e Intimidacao.",
                       {"bonus_pericia": {"Persuasão": 2, "Intuição": 2, "Religião": 2,
                                          "Intimidação": 2}}),
            Habilidade("lider_sagrado_repeticao", "Lider Sagrado — repeticao", ATIVA,
                       "1x por incursao: um aliado repete um teste falhado.")],
        5: [Habilidade("avatar_da_luz", "Avatar da Luz", ATIVA,
                       "1x por incursao: 3 turnos com +2 CA, +5 de dano e cura por turno.")],
    },
    "xama": {
        1: [Habilidade("tradicao_xamanica", "Tradicao xamanica", ATIVA,
                       "1x por descanso: caminho marcial (+1d6 e THP) ou espiritual (cura).")],
        2: [Habilidade("convocacao_totemica", "Convocacao totemica", PASSIVA,
                       "Com 18+ no d20 ganha 2 THP; com THP, o grupo ganha +1 em tudo.")],
        3: [Habilidade("escolha_totemica", "Multiattack ou Cantico Benevolente", ESCOLHA,
                       "Escolhe entre atacar 2x por rodada ou dar 4 THP extra ao curar."),
            Habilidade("danca_totemica", "Danca totemica", ATIVA,
                       "1x por descanso: o grupo ganha 2d6+4 de THP e +1d6+4 no proximo ataque.")],
        4: [Habilidade("sintonizacao_ancestral", "Sintonizacao Ancestral", PASSIVA,
                       "+2 em Historia, Natureza, Medicina, Adestrar Animais e Intuicao.",
                       {"bonus_pericia": {"História": 2, "Natureza": 2, "Medicina": 2,
                                          "Adestrar Animais": 2, "Intuição": 2}})],
        5: [Habilidade("expansao_totemica", "Expansao totemica", PASSIVA,
                       "Com THP, o grupo ganha +2 em acertos e +3 em cura e dano."),
            Habilidade("guerreiros_ancioes", "Guerreiros ancioes", ATIVA,
                       "1x por incursao: o proximo ataque dos aliados crita com 18+.")],
    },
}


# O que o motor entende, e o valor neutro de cada coisa.
NEUTRO: dict = {
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
            if chave == "bonus_pericia":
                for pericia, bonus in valor.items():
                    atual = juntos["bonus_pericia"].get(pericia, 0)
                    juntos["bonus_pericia"][pericia] = max(atual, bonus)
            elif chave == "critico_em":
                juntos["critico_em"] = min(juntos["critico_em"], valor)
            elif chave in juntos:
                juntos[chave] = max(juntos[chave], valor)
    return juntos
