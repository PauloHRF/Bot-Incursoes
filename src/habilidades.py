"""O catálogo de habilidades por classe e tier.

`efeito` é o que o motor aplica sozinho hoje:

    bonus_teste    soma em todo teste de perícia
    bonus_pericia  soma nas perícias listadas
    bonus_save     soma em todo teste de resistência
    bonus_save_atributo  soma nos saves dos atributos listados
    dano_extra     soma no dano de cada golpe
    dano_ferido    soma só contra alvo com metade ou menos do HP
    critico_em     o menor d20 que já é crítico
    ataques        quantos golpes por rodada
    ameaca         soma na Ameaça: o peso dele no sorteio de alvo (src/ameaca.py)

Ativas e escolhas ficam sem efeito: aparecem na ficha e no aviso de nível, mas
ainda não mexem em conta nenhuma — elas entram junto com o sistema de usos
(por combate, por descanso, por incursão), numa fatia própria.
"""
from __future__ import annotations

import re
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
    # O que o jogador decide ao chegar no tier (ESCOLHA).
    escolha: Optional[dict] = None
    # Dois caminhos da mesma habilidade dividem o mesmo contador de usos.
    recarga_com: Optional[str] = None
    # (id da escolha, id da opção): a habilidade só existe para quem escolheu
    # aquela opção. É como o clérigo tem uma magia por círculo em vez de três
    # — a escolha não soma número, ela destrava a ativa.
    exige_escolha: Optional[tuple[str, str]] = None

    @property
    def automatica(self) -> bool:
        """Se o bot já aplica esta habilidade sem ninguém pedir."""
        return self.efeito is not None

    @property
    def decidivel(self) -> bool:
        """Se o bot sabe conduzir a escolha desta habilidade."""
        return self.escolha is not None

    @property
    def acionavel(self) -> bool:
        """Se o jogador já consegue usar esta habilidade pelo bot."""
        return self.acao is not None

    @property
    def pronta(self) -> bool:
        return self.automatica or self.acionavel or self.decidivel

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
                       "Escolhe 2 pericias com proficiencia; o bonus delas dobra.",
                       escolha={"tipo": "pericias", "quantidade": 2,
                                "entre": "proficientes", "aplica": "expertise"})],
        3: [Habilidade("uncanny_dodge", "Uncanny Dodge", ATIVA,
                       "1x por combate: corta pela metade o primeiro golpe pesado que sofrer.",
                       usos=_usos("combate"),
                       acao={"tipo": "reacao", "quando": "sofreu_golpe",
                             "reduz": 0.5, "limiar": 1 / 3})],
        4: [Habilidade("expertise_2", "Expertise", ESCOLHA,
                       "Escolhe mais 2 pericias com proficiencia; o bonus delas dobra.",
                       escolha={"tipo": "pericias", "quantidade": 2,
                                "entre": "proficientes", "aplica": "expertise"})],
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
                       "Ganha proficiencia em mais 2 pericias.",
                       escolha={"tipo": "pericias", "quantidade": 2,
                                "entre": "todas", "aplica": "proficiencia"})],
        3: [MULTIATAQUE,
            Habilidade("reckless_attack", "Reckless Attack", ATIVA,
                       "1x por combate: os ataques do proximo turno tem vantagem, "
                       "e voce ganha ameaca 3 — atacar descuidado chama atencao.",
                       usos=_usos("combate"),
                       acao={"tipo": "duracao", "turnos": 1, "alvo": "proprio",
                             "efeitos": {"vantagem": True, "ameaca": 3}})],
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
                       "Escolhe um: +1 acerto, +1 CA ou +2 de dano.",
                       escolha={"tipo": "opcao", "opcoes": [
                           {"id": "ofensivo", "nome": "Ofensivo",
                            "texto": "+1 de acerto", "efeito": {"acerto": 1}},
                           {"id": "defensivo", "nome": "Defensivo",
                            "texto": "+1 de CA", "efeito": {"ca": 1}},
                           {"id": "pesado", "nome": "Heavy",
                            "texto": "+2 de dano", "efeito": {"dano_extra": 2}},
                       ]})],
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
            # Era "repete um teste falhado", que o bot nao sabe fazer: a
            # rolagem ja virou consequencia quando daria para repetir. Vira o
            # mesmo socorro, que chega na hora certa e da no mesmo.
            Habilidade("sobrevivente_socorro", "Sobrevivente — socorro", ATIVA,
                       "1x por incursao: quando alguem falha o teste da sala, "
                       "soma +5 — e so dispara se o +5 fizer passar.",
                       usos=_usos("incursao"),
                       acao={"tipo": "reacao", "quando": "falhou_teste",
                             "bonus": 5})],
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
            # A nota de revisao do documento diz "melhor dar +5 para um aliado
            # que o paladino queira", e e o que entra: o mesmo socorro do
            # Flash of Genius, que o artifice trouxe.
            Habilidade("lider_sagrado_socorro", "Lider Sagrado — socorro", ATIVA,
                       "1x por incursao: quando um aliado falha o teste da sala, "
                       "soma +5 — e so dispara se o +5 fizer passar.",
                       usos=_usos("incursao"),
                       acao={"tipo": "reacao", "quando": "falhou_teste",
                             "bonus": 5})],
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
                       "1x por descanso: cura 2d8+3 de um aliado; voce ganha 1d6+3 de THP.",
                       usos=_usos("descanso"), recarga_com="tradicao_xamanica",
                       acao={"tipo": "cura", "dado": "2d8+3", "alvo": "aliado",
                             "thp_proprio": "1d6+3"})],
        2: [Habilidade("espirito_guardiao", "Espirito Guardiao", PASSIVA,
                       "Com 19+ no d20 ganha 5 THP; com THP, o grupo ganha +1 em tudo.",
                       {"totem": {"gatilho": 19, "thp": 5, "aura": 1}})],
        3: [Habilidade("escolha_totemica", "Multiattack ou Cantico Benevolente", ESCOLHA,
                       "Escolhe entre atacar 2x por rodada ou dar 4 THP extra ao curar.",
                       escolha={"tipo": "opcao", "opcoes": [
                           {"id": "multiataque", "nome": "Multiattack",
                            "texto": "Ataca 2x por rodada", "efeito": {"ataques": 2}},
                           {"id": "cantico", "nome": "Cantico Benevolente",
                            "texto": "Curar da +4 de THP ao alvo",
                            "efeito": {"thp_na_cura": 4}},
                       ]}),
            Habilidade("danca_totemica", "Danca totemica", ATIVA,
                       "1x por descanso: o grupo ganha 4d6+4 de THP e +1d6+4 no proximo ataque.",
                       usos=_usos("descanso"),
                       acao={"tipo": "grupo", "thp": "4d6+4", "turnos": 1,
                             "efeitos": {"dano_bonus": "1d6+4"}})],
        # O gatilho do Espirito Guardiao cai de 19 para 15: a Sintonizacao
        # substitui o totem inteiro, porque `juntar_efeito` guarda o de maior
        # aura e as duas tem aura 1 — a de 15 e a ultima a entrar e vence.
        4: [Habilidade("sintonizacao_ancestral", "Sintonizacao Ancestral", PASSIVA,
                       "Com 15+ no d20 ganha 5 THP. E +2 em Historia, Natureza, "
                       "Medicina, Adestrar Animais e Intuicao.",
                       {"totem": {"gatilho": 15, "thp": 5, "aura": 1},
                        "bonus_pericia": {"História": 2, "Natureza": 2, "Medicina": 2,
                                          "Adestrar Animais": 2, "Intuição": 2}})],
        5: [Habilidade("expansao_totemica", "Expansao totemica", PASSIVA,
                       "Com THP, o grupo ganha +2 em acertos, testes, cura e dano.",
                       {"totem": {"gatilho": 15, "thp": 5, "aura": 2, "aura_dano": 2}}),
            Habilidade("guerreiros_ancioes", "Guerreiros ancioes", ATIVA,
                       "1x por incursao: os proximos dois ataques dos aliados levam "
                       "+1d6+5 de dano e critam com 15+, e o grupo cura 10% do HP. "
                       "Com 20+ de THP, gasta 20 e vira 1d10+5, critico automatico, "
                       "20% de cura e 8d6 em todos os inimigos.",
                       usos=_usos("incursao"),
                       acao={"tipo": "grupo", "turnos": 2, "cura_fracao": 0.1,
                             "efeitos": {"dano_bonus": "1d6+5", "critico_em": 15},
                             "melhoria": {
                                 "custo_thp": 20, "cura_fracao": 0.2,
                                 "dano_em_todos": "8d6",
                                 "efeitos": {"dano_bonus": "1d10+5",
                                             "critico_em": 1}}})],
    },
    # O clerigo escolhe em todos os tiers: a magia nos impares, o dominio nos
    # pares. A escolha de magia nao soma numero — ela destrava a ativa, por
    # `exige_escolha`. A CD dos saves que ele forca sai de
    # classes.cd_de_habilidade (8 + acerto): 13 no tier 1, 19 no tier 5.
    "clerigo": {
        1: [Habilidade("magia_t1", "Magia de 1o circulo", ESCOLHA,
                       "Escolhe uma: Cure Wounds, Command ou Guiding Bolt.",
                       escolha={"tipo": "opcao", "opcoes": [
                           {"id": "cure_wounds", "nome": "Cure Wounds",
                            "texto": "Cura 2d8+3 de um aliado"},
                           {"id": "command", "nome": "Command",
                            "texto": "Um inimigo perde a proxima vez"},
                           {"id": "guiding_bolt", "nome": "Guiding Bolt",
                            "texto": "4d6 e o grupo ataca ele com vantagem"},
                       ]}),
            Habilidade("cure_wounds", "Cure Wounds", ATIVA,
                       "1x por descanso: cura 2d8+3 de um aliado.",
                       usos=_usos("descanso"),
                       acao={"tipo": "cura", "dado": "2d8+3", "alvo": "aliado"},
                       exige_escolha=("magia_t1", "cure_wounds")),
            Habilidade("command", "Command", ATIVA,
                       "1x por descanso: um inimigo faz save de SAB; falhando, "
                       "perde a proxima vez.",
                       usos=_usos("descanso"),
                       acao={"tipo": "save", "save": "SAB", "alvos": 1, "atordoa": 1},
                       exige_escolha=("magia_t1", "command")),
            Habilidade("guiding_bolt", "Guiding Bolt", ATIVA,
                       "1x por descanso: 4d6 de dano num inimigo; o grupo ataca "
                       "ele com vantagem na proxima rodada.",
                       usos=_usos("descanso"),
                       acao={"tipo": "save", "save": "DES", "alvos": 1,
                             "dano": "4d6", "sem_save": True, "turnos": 1,
                             "vantagem_do_grupo": True},
                       exige_escolha=("magia_t1", "guiding_bolt"))],
        2: [Habilidade("dominio_t2", "Dominio divino", ESCOLHA,
                       "Escolhe um: Protetor, Taumaturgo ou Curandeiro.",
                       escolha={"tipo": "opcao", "opcoes": [
                           {"id": "protetor", "nome": "Protetor",
                            "texto": "+2 de CA", "efeito": {"ca": 2}},
                           # Pede escolha encadeada (o dominio, e depois quais
                           # duas pericias), que o bot ainda nao sabe pedir.
                           {"id": "taumaturgo", "nome": "Taumaturgo",
                            "texto": "Proficiencia em 2 pericias",
                            "pendente": True},
                           {"id": "curandeiro", "nome": "Curandeiro",
                            "texto": "As curas dele curam 1d6 a mais",
                            "efeito": {"bonus_cura": "1d6"}},
                       ]})],
        3: [Habilidade("magia_t3", "Magia de 2o circulo", ESCOLHA,
                       "Escolhe uma: Spirit Guardians, Mass Healing Word ou "
                       "Hypnotic Pattern.",
                       escolha={"tipo": "opcao", "opcoes": [
                           {"id": "spirit_guardians", "nome": "Spirit Guardians",
                            "texto": "3d8 em todos os inimigos que falharem"},
                           {"id": "mass_healing_word", "nome": "Mass Healing Word",
                            "texto": "O grupo inteiro cura 2d4+4"},
                           {"id": "hypnotic_pattern", "nome": "Hypnotic Pattern",
                            "texto": "Os inimigos que falharem perdem a vez"},
                       ]}),
            Habilidade("spirit_guardians", "Spirit Guardians", ATIVA,
                       "1x por incursao: todos os inimigos fazem save de SAB; "
                       "quem falha leva 3d8.",
                       usos=_usos("incursao"),
                       acao={"tipo": "save", "save": "SAB", "alvos": "todos",
                             "dano": "3d8"},
                       exige_escolha=("magia_t3", "spirit_guardians")),
            Habilidade("mass_healing_word", "Mass Healing Word", ATIVA,
                       "1x por descanso: o grupo inteiro cura 2d4+4.",
                       usos=_usos("descanso"),
                       acao={"tipo": "grupo", "cura_dado": "2d4+4"},
                       exige_escolha=("magia_t3", "mass_healing_word")),
            Habilidade("hypnotic_pattern", "Hypnotic Pattern", ATIVA,
                       "1x por incursao: todos os inimigos fazem save de SAB; "
                       "quem falha perde a proxima vez.",
                       usos=_usos("incursao"),
                       acao={"tipo": "save", "save": "SAB", "alvos": "todos",
                             "atordoa": 1},
                       exige_escolha=("magia_t3", "hypnotic_pattern"))],
        4: [Habilidade("dominio_t4", "Dominio maior", ESCOLHA,
                       "Escolhe um: Ataques abencoados, Especialista em cura "
                       "ou Restauracao.",
                       escolha={"tipo": "opcao", "opcoes": [
                           {"id": "ataques_abencoados", "nome": "Ataques abencoados",
                            "texto": "+1d8 de dano nos ataques",
                            "efeito": {"dano_bonus": "1d8"}},
                           {"id": "especialista_cura", "nome": "Especialista em cura",
                            "texto": "As curas dele curam 1d6 a mais",
                            "efeito": {"bonus_cura": "1d6"}},
                           {"id": "restauracao", "nome": "Restauracao",
                            "texto": "As curas dele tiram o atordoamento",
                            "efeito": {"cura_limpa_controle": True}},
                       ]})],
        5: [Habilidade("magia_t5", "Magia de 3o circulo", ESCOLHA,
                       "Escolhe uma: Flame Strike, Mass Cure Wounds ou "
                       "Dominate Person.",
                       escolha={"tipo": "opcao", "opcoes": [
                           {"id": "flame_strike", "nome": "Flame Strike",
                            "texto": "10d6 em todos, metade em quem resistir"},
                           {"id": "mass_cure_wounds", "nome": "Mass Cure Wounds",
                            "texto": "O grupo inteiro cura 5d8+5"},
                           {"id": "dominate_person", "nome": "Dominate Person",
                            "texto": "Um inimigo ataca outro"},
                       ]}),
            Habilidade("flame_strike", "Flame Strike", ATIVA,
                       "1x por incursao: todos os inimigos fazem save de DES; "
                       "quem falha leva 10d6, quem passa leva metade.",
                       usos=_usos("incursao"),
                       acao={"tipo": "save", "save": "DES", "alvos": "todos",
                             "dano": "10d6", "metade": True},
                       exige_escolha=("magia_t5", "flame_strike")),
            Habilidade("mass_cure_wounds", "Mass Cure Wounds", ATIVA,
                       "1x por descanso: o grupo inteiro cura 5d8+5.",
                       usos=_usos("descanso"),
                       acao={"tipo": "grupo", "cura_dado": "5d8+5"},
                       exige_escolha=("magia_t5", "mass_cure_wounds")),
            Habilidade("dominate_person", "Dominate Person", ATIVA,
                       "1x por descanso: um inimigo faz save de SAB; falhando, "
                       "ataca outra criatura dele.",
                       usos=_usos("descanso"),
                       acao={"tipo": "save", "save": "SAB", "alvos": 1,
                             "vira_contra": True},
                       exige_escolha=("magia_t5", "dominate_person"))],
    },
    # O artifice sem itens e o artifice emprestando numero. Os itens ficam na
    # planilha do grupo, entao as cinco habilidades de classe que sao itens no
    # livro (Replicate, Tinker, Adept, Spell-Storing, Soul of Artifice) viram
    # uma coisa so: a Infusao, que e o bonus que o item daria. O resto puxa de
    # quatro subclasses, porque o fio comum de todas e o mesmo — "some um
    # bonus numa rolagem": Alchemical Savant, Arcane Firearm, Arcane Jolt,
    # Guided Precision e o Flash of Genius da classe.
    "artifice": {
        1: [Habilidade("ferramenta_t1", "Magia de ferramenta", ESCOLHA,
                       "Escolhe uma: Cure Wounds, Thunderwave ou Faerie Fire.",
                       escolha={"tipo": "opcao", "opcoes": [
                           {"id": "cure_wounds_art", "nome": "Cure Wounds",
                            "texto": "Cura 2d8+3 de um aliado"},
                           {"id": "thunderwave", "nome": "Thunderwave",
                            "texto": "2d8 em todos os inimigos que falharem"},
                           {"id": "faerie_fire", "nome": "Faerie Fire",
                            "texto": "O grupo ataca o alvo com vantagem"},
                       ]}),
            Habilidade("cure_wounds_art", "Cure Wounds", ATIVA,
                       "1x por descanso: cura 2d8+3 de um aliado.",
                       usos=_usos("descanso"),
                       acao={"tipo": "cura", "dado": "2d8+3", "alvo": "aliado"},
                       exige_escolha=("ferramenta_t1", "cure_wounds_art")),
            Habilidade("thunderwave", "Thunderwave", ATIVA,
                       "1x por descanso: todos os inimigos fazem save de CON; "
                       "quem falha leva 2d8, quem passa leva metade.",
                       usos=_usos("descanso"),
                       acao={"tipo": "save", "save": "CON", "alvos": "todos",
                             "dano": "2d8", "metade": True},
                       exige_escolha=("ferramenta_t1", "thunderwave")),
            Habilidade("faerie_fire", "Faerie Fire", ATIVA,
                       "1x por descanso: um inimigo fica delineado; o grupo "
                       "ataca ele com vantagem na proxima rodada.",
                       usos=_usos("descanso"),
                       acao={"tipo": "save", "save": "DES", "alvos": 1,
                             "turnos": 1, "vantagem_do_grupo": True},
                       exige_escolha=("ferramenta_t1", "faerie_fire"))],
        # Replicate Magic Item: no livro ele faz itens e distribui. Aqui o item
        # mora na planilha do grupo, entao entra o que o item faz — o +1 que
        # todos passam a ter. Vale a melhor infusao, como a aura do xama.
        2: [Habilidade("infusao", "Infusao", ESCOLHA,
                       "O equipamento que ele infunde da +1 ao grupo inteiro. "
                       "Escolhe onde: acerto, CA ou dano.",
                       escolha={"tipo": "opcao", "opcoes": [
                           {"id": "armas", "nome": "Armas infundidas",
                            "texto": "+1 de acerto para o grupo inteiro",
                            "efeito": {"infusao": {"acerto": 1}}},
                           {"id": "armaduras", "nome": "Armaduras infundidas",
                            "texto": "+1 de CA para o grupo inteiro",
                            "efeito": {"infusao": {"ca": 1}}},
                           {"id": "municao", "nome": "Municao infundida",
                            "texto": "+1 de dano para o grupo inteiro",
                            "efeito": {"infusao": {"dano": 1}}},
                       ]})],
        # O "+bonus numa rolagem" de cada subclasse, um por opcao.
        3: [Habilidade("engenho_t3", "Engenho", ESCOLHA,
                       "Escolhe um: Arma Arcana, Sabedoria Alquimica ou "
                       "Precisao Guiada.",
                       escolha={"tipo": "opcao", "opcoes": [
                           {"id": "arma_arcana", "nome": "Arma Arcana",
                            "texto": "+1d8 de dano em todo golpe dele",
                            "efeito": {"dano_bonus": "1d8"}},
                           {"id": "sabedoria_alquimica", "nome": "Sabedoria Alquimica",
                            "texto": "As curas dele curam 1d6 a mais",
                            "efeito": {"bonus_cura": "1d6"}},
                           {"id": "precisao_guiada", "nome": "Precisao Guiada",
                            "texto": "+3 de dano em todo golpe dele",
                            "efeito": {"dano_extra": 3}},
                       ]}),
            MULTIATAQUE],
        # Flash of Genius, a assinatura da classe. Reacao automatica, como a
        # esquiva do ladino, e com o mesmo cuidado: so entra quando vira o
        # veredito, para nao queimar o uso de graca.
        4: [Habilidade("flash_of_genius", "Flash of Genius", ATIVA,
                       "1x por descanso: quando alguem do grupo falha o teste "
                       "da sala, soma +5 — e so dispara se o +5 fizer passar.",
                       usos=_usos("descanso"),
                       acao={"tipo": "reacao", "quando": "falhou_teste",
                             "bonus": 5})],
        # Arcane Jolt: os dois caminhos dividem o contador, como as duas
        # tradicoes do xama.
        5: [Habilidade("arcane_jolt_dano", "Arcane Jolt — destrutivo", ATIVA,
                       "1x por combate: um golpe com +2d6 de dano.",
                       usos=_usos("combate"), recarga_com="arcane_jolt",
                       acao={"tipo": "golpes", "quantidade": 1,
                             "dano_bonus": "2d6"}),
            Habilidade("arcane_jolt_cura", "Arcane Jolt — restaurador", ATIVA,
                       "1x por combate: cura 2d6 de um aliado.",
                       usos=_usos("combate"), recarga_com="arcane_jolt",
                       acao={"tipo": "cura", "dado": "2d6", "alvo": "aliado"}),
            Habilidade("genio_refinado", "Genio refinado", PASSIVA,
                       "O Flash of Genius dele soma +10 em vez de +5.",
                       {"flash_bonus": 10})],
    },
}


# Toda habilidade pelo id, para quem so tem o id na mao (o turno gravado, por
# exemplo) e precisa do nome.
POR_ID: dict[str, Habilidade] = {
    h.id: h
    for tabela in HABILIDADES.values()
    for lista in tabela.values()
    for h in lista
}


# O que o motor entende, e o valor neutro de cada coisa.
NEUTRO: dict = {
    "totem": {},
    "acerto": 0,
    "ca": 0,
    "thp_na_cura": 0,
    "expertise": [],
    "sequencia": {},
    "bonus_teste": 0,
    "bonus_pericia": {},
    "bonus_save": 0,
    "bonus_save_atributo": {},
    "dano_extra": 0,
    "dano_ferido": 0,
    "critico_em": 20,
    "ataques": 1,
    "ameaca": 0,
    # Dados, nao numeros: entram como expressao ('1d8') e sao comparados pela
    # media, porque max() de texto compararia caractere por caractere.
    "dano_bonus": "",
    "bonus_cura": "",
    "cura_limpa_controle": False,
    # Quanto o Flash of Genius soma. O tier 5 do artifice sobe de 5 para 10.
    "flash_bonus": 0,
    # O que o artifice infunde no equipamento do grupo: {onde: quanto}.
    "infusao": {},
}

# Chaves cujo valor e uma expressao de dano, e nao um inteiro.
DADOS = ("dano_bonus", "bonus_cura")


def media_do_dado(expressao: str) -> float:
    """A media de uma expressao como '2d6+3', para comparar dois dados.

    Nao rola nada: cada NdF vale N*(F+1)/2 e o resto soma como esta.
    """
    total = 0.0
    for termo in re.findall(r"[+-]?[^+-]+", expressao or ""):
        termo = termo.strip()
        if not termo:
            continue
        sinal = -1 if termo.startswith("-") else 1
        corpo = termo.lstrip("+-").strip()
        if "d" in corpo.lower():
            quantas, _, faces = corpo.lower().partition("d")
            total += sinal * int(quantas or 1) * (int(faces) + 1) / 2
        else:
            total += sinal * int(corpo)
    return total


def juntar_efeito(juntos: dict, efeito: dict) -> None:
    """Soma um efeito no acumulado, respeitando a regra de cada chave."""
    for chave, valor in (efeito or {}).items():
        if chave in ("bonus_pericia", "bonus_save_atributo", "infusao"):
            for nome, bonus in valor.items():
                atual = juntos[chave].get(nome, 0)
                juntos[chave][nome] = max(atual, bonus)
        elif chave == "expertise":
            juntos["expertise"] = sorted(set(juntos["expertise"]) | set(valor))
        elif chave == "sequencia":
            juntos["sequencia"] = dict(valor)
        elif chave == "totem":
            atual = juntos["totem"]
            if valor.get("aura", 0) >= atual.get("aura", 0):
                juntos["totem"] = dict(valor)
        elif chave == "critico_em":
            juntos["critico_em"] = min(juntos["critico_em"], valor)
        elif chave in DADOS:
            atual = juntos.get(chave) or ""
            if media_do_dado(valor) >= media_do_dado(atual):
                juntos[chave] = valor
        elif chave in juntos:
            juntos[chave] = max(juntos[chave], valor)


def juntar(lista: list[Habilidade]) -> dict:
    """Soma numa coisa só o que as passivas da lista fazem.

    Quando duas mexem no mesmo número vale a melhor — é o caso do Reliable
    Talent, que o tier 5 substitui por uma versão mais forte.
    """
    juntos: dict = {
        chave: (
            dict(valor) if isinstance(valor, dict)
            else (list(valor) if isinstance(valor, list) else valor)
        )
        for chave, valor in NEUTRO.items()
    }
    for habilidade in lista:
        juntar_efeito(juntos, habilidade.efeito or {})
    return juntos
