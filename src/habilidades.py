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
                           {"id": "taumaturgo", "nome": "Taumaturgo",
                            "texto": "Proficiencia em 2 pericias, à escolha"},
                           {"id": "curandeiro", "nome": "Curandeiro",
                            "texto": "As curas dele curam 1d6 a mais",
                            "efeito": {"bonus_cura": "1d6"}},
                       ]}),
            # Escolha encadeada: a primeira do bot. O dominio decide o QUE ele
            # ganha, e so o Taumaturgo precisa de uma segunda pergunta — quais
            # duas pericias. O `exige_escolha` que destrava magia de clerigo
            # serve igual aqui, e o menu da ficha ja abre a proxima pendencia
            # sozinho depois de gravar a primeira.
            Habilidade("saber_taumaturgo", "Saber do Taumaturgo", ESCOLHA,
                       "Escolhe as 2 pericias em que o dominio deu "
                       "proficiencia.",
                       escolha={"tipo": "pericias", "quantidade": 2,
                                "entre": "todas", "aplica": "proficiencia"},
                       exige_escolha=("dominio_t2", "taumaturgo"))],
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
            # No livro a aura tambem corta o movimento de quem esta dentro.
            # Aqui nao entra, e por decisao: a traducao seria mexer na ordem
            # da iniciativa no meio do combate, e `posicao` e a chave da ordem
            # E o ponteiro da vez (ver `acrescentar_iniciativa`). Reordenar
            # custaria reescrever todas as linhas e consertar o `vez`, por um
            # -2 que move a criatura um slot. A magia fica so no estouro.
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
                       ]})],
        # Sem Multiattack de proposito: no livro, so o Armorer e o Battle
        # Smith ganham Extra Attack — os outros tres arquetipos nao. Como o
        # que montamos e a classe, e nao um arquetipo, o segundo golpe nao vem
        # de base. Com ele e o d10, o artifice fechava em 33 de dano por
        # rodada no tier 5: o maior do jogo, acima do barbaro.
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
    # A forma combinada para toda classe nova: ativa com tres magias nos
    # tiers impares, passiva nos pares. O livro e base, nao autoridade — o que
    # manda e o arquetipo no sentido popular, e o do Mago e o Fireball.
    #
    # Nada de slot nem de lista preparada: a escolha do tier e permanente,
    # como no clerigo. A coluna de dano da tabela E o cantrip dele, entao Fire
    # Bolt e Ray of Frost nao aparecem aqui — sao o ataque basico.
    "mago": {
        1: [Habilidade("magia_mago_t1", "Magia de 1o circulo", ESCOLHA,
                       "Escolhe uma: Magic Missile, Sleep ou Thunderwave.",
                       escolha={"tipo": "opcao", "opcoes": [
                           {"id": "magic_missile", "nome": "Magic Missile",
                            "texto": "3d4+3 garantido, sem save"},
                           {"id": "sleep", "nome": "Sleep",
                            "texto": "Os inimigos que falharem perdem a vez"},
                           {"id": "thunderwave_mago", "nome": "Thunderwave",
                            "texto": "2d8 em todos, metade em quem resistir"},
                       ]}),
            Habilidade("magic_missile", "Magic Missile", ATIVA,
                       "1x por descanso: 3d4+3 num inimigo. Nao tem save — os "
                       "dardos sempre acertam.",
                       usos=_usos("descanso"),
                       acao={"tipo": "save", "save": "DES", "alvos": 1,
                             "dano": "3d4+3", "sem_save": True},
                       exige_escolha=("magia_mago_t1", "magic_missile")),
            Habilidade("sleep", "Sleep", ATIVA,
                       "1x por descanso: todos os inimigos fazem save de SAB; "
                       "quem falha perde a proxima vez.",
                       usos=_usos("descanso"),
                       acao={"tipo": "save", "save": "SAB", "alvos": "todos",
                             "atordoa": 1},
                       exige_escolha=("magia_mago_t1", "sleep")),
            Habilidade("thunderwave_mago", "Thunderwave", ATIVA,
                       "1x por descanso: todos os inimigos fazem save de CON; "
                       "quem falha leva 2d8, quem passa leva metade.",
                       usos=_usos("descanso"),
                       acao={"tipo": "save", "save": "CON", "alvos": "todos",
                             "dano": "2d8", "metade": True},
                       exige_escolha=("magia_mago_t1", "thunderwave_mago"))],
        # Scholar: passiva, nao escolha. Era Expertise numa pericia de saber
        # a escolher — mais forte numa (+4 a +6) e nada nas outras cinco —,
        # mas o tier 2 e automatico por regra, e o mago era a unica classe com
        # escolha no T2 E no T4.
        #
        # A forma e a das outras quatro passivas tematicas de pericia do bot
        # (Mente e Corpo, Sobrevivente, Lider Sagrado, Guerreiros Ancioes):
        # um numero no grupo de pericias que a classe representa. Aquelas
        # somam +2 em 3 a 5 pericias, e todas no tier 4 — esta soma +3 em 6 e
        # chega no tier 2, entao e a mais forte das cinco. Fica anotado para
        # a passada de balanceamento.
        2: [Habilidade("scholar", "Scholar", PASSIVA,
                       "+3 em Arcanismo, Historia, Investigacao, Medicina, "
                       "Natureza e Religiao: ele estudou todas.",
                       {"bonus_pericia": {"Arcanismo": 3, "História": 3,
                                          "Investigação": 3, "Medicina": 3,
                                          "Natureza": 3, "Religião": 3}})],
        3: [Habilidade("magia_mago_t3", "Magia de 3o circulo", ESCOLHA,
                       "Escolhe uma: Fireball, Hypnotic Pattern ou Fly.",
                       escolha={"tipo": "opcao", "opcoes": [
                           {"id": "fireball", "nome": "Fireball",
                            "texto": "8d6 em todos, metade em quem resistir"},
                           {"id": "hypnotic_pattern_mago", "nome": "Hypnotic Pattern",
                            "texto": "Os inimigos que falharem perdem a vez"},
                           {"id": "fly", "nome": "Fly",
                            "texto": "Tres aliados saem de alcance por 3 rodadas"},
                       ]}),
            Habilidade("fireball", "Fireball", ATIVA,
                       "1x por descanso: todos os inimigos fazem save de DES; "
                       "quem falha leva 8d6, quem passa leva metade.",
                       usos=_usos("descanso"),
                       acao={"tipo": "save", "save": "DES", "alvos": "todos",
                             "dano": "8d6", "metade": True},
                       exige_escolha=("magia_mago_t3", "fireball")),
            Habilidade("hypnotic_pattern_mago", "Hypnotic Pattern", ATIVA,
                       "1x por descanso: todos os inimigos fazem save de SAB; "
                       "quem falha perde a proxima vez.",
                       usos=_usos("descanso"),
                       acao={"tipo": "save", "save": "SAB", "alvos": "todos",
                             "atordoa": 1},
                       exige_escolha=("magia_mago_t3", "hypnotic_pattern_mago")),
            # Voar e posicional, e o bot nao tem posicao. O que sobra do que
            # voar faz e sair de alcance: o peso dos tres no sorteio de alvo
            # cai a um quinto. E fator, e nao troca de ameaca, porque a curva
            # x/(x+10) e quase reta embaixo: mexer na ameaca crua so daria
            # "modesto" (13% -> 9%) ou "imune" (peso 0), sem meio-termo.
            Habilidade("fly", "Fly", ATIVA,
                       "1x por descanso: tres aliados sobem fora de alcance "
                       "por 3 rodadas — os inimigos quase deixam de mira-los.",
                       usos=_usos("descanso"),
                       acao={"tipo": "duracao", "turnos": 3, "alvo": "aliados",
                             "alvos": 3, "efeitos": {"ameaca_fator": 0.2}},
                       exige_escolha=("magia_mago_t3", "fly"))],
        4: [Habilidade("tradicao_arcana", "Tradicao arcana", ESCOLHA,
                       "Escolhe uma: Evocacao Potente, Escudo Arcano ou "
                       "Sabedoria Arcana.",
                       escolha={"tipo": "opcao", "opcoes": [
                           {"id": "evocacao_potente", "nome": "Evocacao Potente",
                            "texto": "+1d8 de dano em tudo que ele lanca",
                            "efeito": {"dano_bonus": "1d8"}},
                           {"id": "escudo_arcano", "nome": "Escudo Arcano",
                            "texto": "THP igual a 2x o tier, e recarrega a cada magia",
                            "efeito": {"escudo_arcano": 2}},
                           {"id": "sabedoria_arcana", "nome": "Sabedoria Arcana",
                            "texto": "+2 nos saves do grupo inteiro",
                            "efeito": {"aura_save": 2}},
                       ]})],
        5: [Habilidade("magia_mago_t5", "Magia de 5o circulo", ESCOLHA,
                       "Escolhe uma: Cone of Cold, Hold Monster ou Circle of Power.",
                       escolha={"tipo": "opcao", "opcoes": [
                           {"id": "cone_of_cold", "nome": "Cone of Cold",
                            "texto": "12d8 em todos, metade em quem resistir"},
                           {"id": "hold_monster", "nome": "Hold Monster",
                            "texto": "Um inimigo perde tres vezes seguidas"},
                           {"id": "circle_of_power", "nome": "Circle of Power",
                            "texto": "O grupo resiste melhor e escapa inteiro"},
                       ]}),
            Habilidade("cone_of_cold", "Cone of Cold", ATIVA,
                       "1x por descanso: todos os inimigos fazem save de CON; "
                       "quem falha leva 12d8, quem passa leva metade.",
                       usos=_usos("descanso"),
                       acao={"tipo": "save", "save": "CON", "alvos": "todos",
                             "dano": "12d8", "metade": True},
                       exige_escolha=("magia_mago_t5", "cone_of_cold")),
            Habilidade("hold_monster", "Hold Monster", ATIVA,
                       "1x por descanso: um inimigo faz save de SAB; falhando, "
                       "perde tres vezes seguidas.",
                       usos=_usos("descanso"),
                       acao={"tipo": "save", "save": "SAB", "alvos": 1,
                             "atordoa": 3},
                       exige_escolha=("magia_mago_t5", "hold_monster")),
            Habilidade("circle_of_power", "Circle of Power", ATIVA,
                       "1x por descanso: por 3 rodadas o grupo rola os saves "
                       "com vantagem e, passando, nao leva nem metade.",
                       usos=_usos("descanso"),
                       acao={"tipo": "grupo", "turnos": 3,
                             "efeitos": {"vantagem": True, "save_anula": True}},
                       exige_escolha=("magia_mago_t5", "circle_of_power"))],
    },
    # O bruxo trocou algo por poder, e o pacto cobra: TODA magia dele e 1x por
    # incursao, o escopo mais raro do bot. Numa Media isso da 1 lance contra os
    # ~1,4 do mago e os ~3 de quem tem "por combate" — entao cada uma bate mais
    # forte que a do mago no mesmo tier. Poucos favores, grandes.
    #
    # As passivas dos tiers pares sao Eldritch Invocations, que e a assinatura
    # da classe: conhecimento proibido que fica ligado para sempre.
    "bruxo": {
        1: [Habilidade("pacto_t1", "Dadiva do pacto", ESCOLHA,
                       "Escolhe uma: Hex, Arms of Hadar ou Charm Person.",
                       escolha={"tipo": "opcao", "opcoes": [
                           {"id": "hex", "nome": "Hex",
                            "texto": "Marca um inimigo: +1d6 de dano nele"},
                           {"id": "arms_of_hadar", "nome": "Arms of Hadar",
                            "texto": "2d6 em todos, save de FOR"},
                           {"id": "charm_person", "nome": "Charm Person",
                            "texto": "Um inimigo perde a proxima vez"},
                       ]}),
            # Hex e a magia do bruxo: a marca que faz todo golpe no alvo doer
            # mais. Mesmo caminho da Marca do Cacador do patrulheiro.
            Habilidade("hex", "Hex", ATIVA,
                       "1x por incursao: marca um inimigo por 3 rodadas; todo "
                       "golpe nele causa +1d6 de dano.",
                       usos=_usos("incursao"),
                       acao={"tipo": "duracao", "turnos": 3, "alvo": "inimigo",
                             "efeitos": {"dano_bonus": "1d6"}},
                       exige_escolha=("pacto_t1", "hex")),
            Habilidade("arms_of_hadar", "Arms of Hadar", ATIVA,
                       "1x por incursao: todos os inimigos fazem save de FOR; "
                       "quem falha leva 2d6, quem passa leva metade.",
                       usos=_usos("incursao"),
                       acao={"tipo": "save", "save": "FOR", "alvos": "todos",
                             "dano": "2d6", "metade": True},
                       exige_escolha=("pacto_t1", "arms_of_hadar")),
            Habilidade("charm_person", "Charm Person", ATIVA,
                       "1x por incursao: um inimigo faz save de SAB; falhando, "
                       "perde a proxima vez.",
                       usos=_usos("incursao"),
                       acao={"tipo": "save", "save": "SAB", "alvos": 1,
                             "atordoa": 1},
                       exige_escolha=("pacto_t1", "charm_person"))],
        2: [Habilidade("invocacao_t2", "Eldritch Invocation", ESCOLHA,
                       "Conhecimento proibido que fica ligado. Escolhe uma: "
                       "Agonizing Blast, Fiendish Vigor ou Devil's Sight.",
                       escolha={"tipo": "opcao", "opcoes": [
                           {"id": "agonizing_blast", "nome": "Agonizing Blast",
                            "texto": "+3 de dano em todo Eldritch Blast",
                            "efeito": {"dano_extra": 3}},
                           {"id": "fiendish_vigor", "nome": "Fiendish Vigor",
                            "texto": "Abre o combate com vida temporaria",
                            "efeito": {"escudo_arcano": 2}},
                           # Ver no escuro nao tem onde pegar: o bot nao tem
                           # luz, visao nem escuridao. O que sobra da ficcao e
                           # "percebe o que esta escondido", e a sala e metade
                           # do jogo aqui.
                           {"id": "devils_sight", "nome": "Devil's Sight",
                            "texto": "+3 em Percepcao e Investigacao",
                            "efeito": {"bonus_pericia": {"Percepção": 3,
                                                         "Investigação": 3}}},
                       ]})],
        3: [Habilidade("pacto_t3", "Favor do patrono", ESCOLHA,
                       "Escolhe uma: Hunger of Hadar, Healing Light ou "
                       "Hypnotic Pattern.",
                       escolha={"tipo": "opcao", "opcoes": [
                           {"id": "hunger_of_hadar", "nome": "Hunger of Hadar",
                            "texto": "6d6 em todos E os que falharem perdem a vez"},
                           {"id": "healing_light", "nome": "Healing Light",
                            "texto": "Cura 6d6 de um aliado"},
                           {"id": "hypnotic_pattern_bruxo", "nome": "Hypnotic Pattern",
                            "texto": "Os inimigos que falharem perdem a vez"},
                       ]}),
            # O vazio do Great Old One: dano E controle no mesmo lance, que e o
            # que justifica gastar o unico uso da incursao nele.
            Habilidade("hunger_of_hadar", "Hunger of Hadar", ATIVA,
                       "1x por incursao: todos os inimigos fazem save de DES; "
                       "quem falha leva 6d6 e perde a proxima vez.",
                       usos=_usos("incursao"),
                       acao={"tipo": "save", "save": "DES", "alvos": "todos",
                             "dano": "6d6", "atordoa": 1},
                       exige_escolha=("pacto_t3", "hunger_of_hadar")),
            Habilidade("healing_light", "Healing Light", ATIVA,
                       "1x por incursao: cura 6d6 de um aliado.",
                       usos=_usos("incursao"),
                       acao={"tipo": "cura", "dado": "6d6", "alvo": "aliado"},
                       exige_escolha=("pacto_t3", "healing_light")),
            Habilidade("hypnotic_pattern_bruxo", "Hypnotic Pattern", ATIVA,
                       "1x por incursao: todos os inimigos fazem save de SAB; "
                       "quem falha perde as duas proximas vezes.",
                       usos=_usos("incursao"),
                       acao={"tipo": "save", "save": "SAB", "alvos": "todos",
                             "atordoa": 2},
                       exige_escolha=("pacto_t3", "hypnotic_pattern_bruxo"))],
        4: [Habilidade("patrono_t4", "Benesse do patrono", ESCOLHA,
                       "Escolhe uma: Dark One's Own Luck, Dark One's Blessing "
                       "ou Radiant Soul.",
                       escolha={"tipo": "opcao", "opcoes": [
                           # Nao soma numero: destrava a reacao logo abaixo.
                           {"id": "own_luck", "nome": "Dark One's Own Luck",
                            "texto": "O patrono torce o destino num teste seu"},
                           {"id": "dark_blessing", "nome": "Dark One's Blessing",
                            "texto": "Vida temporaria ao derrubar um inimigo",
                            "efeito": {"thp_ao_derrubar": 2}},
                           {"id": "radiant_soul", "nome": "Radiant Soul",
                            "texto": "+1d8 de dano em tudo que ele lanca",
                            "efeito": {"dano_bonus": "1d8"}},
                       ]}),
            # A Own Luck e reacao, nao numero: usa a maquina do Flash of Genius
            # do artifice, so que o patrono socorre o proprio bruxo.
            Habilidade("own_luck", "Dark One's Own Luck", ATIVA,
                       "1x por incursao: quando VOCE falha o teste da sala, o "
                       "patrono soma +10 — e so dispara se o +10 fizer passar.",
                       usos=_usos("incursao"),
                       acao={"tipo": "reacao", "quando": "falhou_teste",
                             "bonus": 10, "so_em_si": True},
                       exige_escolha=("patrono_t4", "own_luck"))],
        5: [Habilidade("pacto_t5", "Grande favor", ESCOLHA,
                       "Escolhe uma: Hold Monster, Synaptic Static ou "
                       "Summon Greater Demon.",
                       escolha={"tipo": "opcao", "opcoes": [
                           {"id": "hold_monster_bruxo", "nome": "Hold Monster",
                            "texto": "Um inimigo perde tres vezes seguidas"},
                           {"id": "synaptic_static", "nome": "Synaptic Static",
                            "texto": "8d6 em todos, e eles passam a errar mais"},
                           {"id": "summon_greater_demon", "nome": "Summon Greater Demon",
                            "texto": "Um demonio entra na luta e bate sozinho"},
                       ]}),
            Habilidade("hold_monster_bruxo", "Hold Monster", ATIVA,
                       "1x por incursao: um inimigo faz save de SAB; falhando, "
                       "perde tres vezes seguidas.",
                       usos=_usos("incursao"),
                       acao={"tipo": "save", "save": "SAB", "alvos": 1,
                             "atordoa": 3},
                       exige_escolha=("pacto_t5", "hold_monster_bruxo")),
            # O -1d6 do livro vira -3 no ataque da criatura: o bot nao rola
            # dado de penalidade, e -3 e a media de 1d6 arredondada.
            Habilidade("synaptic_static", "Synaptic Static", ATIVA,
                       "1x por incursao: todos os inimigos fazem save de INT; "
                       "quem falha leva 8d6 e perde 3 de ataque por 3 rodadas.",
                       usos=_usos("incursao"),
                       acao={"tipo": "save", "save": "INT", "alvos": "todos",
                             "dano": "8d6", "metade": True, "turnos": 3,
                             "penalidade_ataque": 3},
                       exige_escolha=("pacto_t5", "synaptic_static")),
            Habilidade("summon_greater_demon", "Summon Greater Demon", ATIVA,
                       "1x por incursao: um demonio entra na sala com HP "
                       "proprio, age na vez dele e bate no inimigo mais "
                       "ferido. Sai quando o grupo troca de sala.",
                       usos=_usos("incursao"),
                       acao={"tipo": "invocar", "nome": "Demonio do pacto",
                             "ca": 15, "ataque": 8, "dano": "2d6+4", "hp": 45,
                             "ameaca": 4, "iniciativa": 2},
                       exige_escolha=("pacto_t5", "summon_greater_demon"))],
    },
    # O druida e a unica classe com um trade de verdade: o livro diz que ele
    # NAO conjura transformado. Entao o dano base dele e o pior do jogo (9 por
    # rodada no tier 5, empatado com o clerigo) e a forma e que bate. Virar
    # urso e escolher: poder agora, versatilidade depois.
    #
    # Os numeros da forma vem por tier, como o resto da tabela: dado fixo
    # quebraria o tier 1 (onde a base e 1d8) ou seria inutil no 5.
    "druida": {
        1: [Habilidade("forma_t1", "Wild Shape", ESCOLHA,
                       "A forma que ele veste. Escolhe uma: Urso, Lobo ou Aranha.",
                       escolha={"tipo": "opcao", "opcoes": [
                           {"id": "urso", "nome": "Urso",
                            "texto": "Aguenta: +3 de CA e muita vida temporaria"},
                           {"id": "lobo", "nome": "Lobo",
                            "texto": "Morde duas vezes por rodada"},
                           {"id": "aranha", "nome": "Aranha",
                            "texto": "Cada mordida atrapalha o ataque do alvo"},
                       ]}),
            Habilidade("forma_urso", "Wild Shape — Urso", ATIVA,
                       "1x por descanso: vira urso por 3 rodadas. +3 de CA, "
                       "vida temporaria igual a 3x o tier, e o dado da forma.",
                       usos=_usos("descanso"),
                       acao={"tipo": "forma", "nome": "Urso", "turnos": 3,
                             "ca": 3, "ataques": 1, "thp_por_tier": 3,
                             "dano": {1: "1d8+2", 2: "1d10+2", 3: "2d8+3",
                                      4: "2d10+3", 5: "2d10+5"}},
                       exige_escolha=("forma_t1", "urso")),
            Habilidade("forma_lobo", "Wild Shape — Lobo", ATIVA,
                       "1x por descanso: vira lobo por 3 rodadas. Dois golpes "
                       "por rodada e vida temporaria igual a 2x o tier.",
                       usos=_usos("descanso"),
                       acao={"tipo": "forma", "nome": "Lobo", "turnos": 3,
                             "ataques": 2, "thp_por_tier": 2,
                             "dano": {1: "1d4+2", 2: "1d6+2", 3: "1d8+3",
                                      4: "1d8+4", 5: "1d10+4"}},
                       exige_escolha=("forma_t1", "lobo")),
            # Condicao do catalogo e do lado do jogador (run_condicoes e por
            # user_id); do lado do inimigo o equivalente de Envenenado e o
            # ataque dele piorar, que e o `penalidade_ataque`.
            Habilidade("forma_aranha", "Wild Shape — Aranha", ATIVA,
                       "1x por descanso: vira aranha por 3 rodadas. Cada golpe "
                       "que acerta tira 2 do ataque do alvo por 2 rodadas.",
                       usos=_usos("descanso"),
                       acao={"tipo": "forma", "nome": "Aranha", "turnos": 3,
                             "ataques": 1, "thp_por_tier": 2,
                             "veneno_no_golpe": 2,
                             "dano": {1: "1d8+2", 2: "1d10+2", 3: "2d8+3",
                                      4: "2d8+5", 5: "2d10+4"}},
                       exige_escolha=("forma_t1", "aranha"))],
        # Wild Companion do livro: o espirito que assume forma de animal e o
        # acompanha. Passiva, nao combatente — ele ajuda, nao luta.
        2: [Habilidade("bichinho_t2", "Companheiro selvagem", ESCOLHA,
                       "Um espirito animal o acompanha. Escolhe o que ele faz: "
                       "cura, morde junto, ou avisa do perigo.",
                       escolha={"tipo": "opcao", "opcoes": [
                           {"id": "bichinho_curandeiro", "nome": "Lambe as feridas",
                            "texto": "Cura 3 por tier ao abrir o combate",
                            "efeito": {"bichinho_cura": 3}},
                           {"id": "bichinho_mordedor", "nome": "Morde junto",
                            "texto": "+2 de dano em todo golpe dele",
                            "efeito": {"dano_extra": 2}},
                           {"id": "bichinho_vigilante", "nome": "Avisa do perigo",
                            "texto": "+3 em todo teste de pericia",
                            "efeito": {"bonus_teste": 3}},
                       ]})],
        3: [Habilidade("magia_druida_t3", "Magia de circulo", ESCOLHA,
                       "Escolhe uma: Aura of Vitality, Call Lightning ou "
                       "Conjure Animals.",
                       escolha={"tipo": "opcao", "opcoes": [
                           {"id": "aura_of_vitality", "nome": "Aura of Vitality",
                            "texto": "O grupo regenera 10% do HP por rodada"},
                           {"id": "call_lightning", "nome": "Call Lightning",
                            "texto": "6d10 em todos, metade no sucesso"},
                           {"id": "conjure_animals", "nome": "Conjure Animals",
                            "texto": "Um bando entra na luta e bate sozinho"},
                       ]}),
            Habilidade("aura_of_vitality", "Aura of Vitality", ATIVA,
                       "1x por descanso: por 3 rodadas o grupo inteiro recupera "
                       "10% do HP maximo a cada rodada.",
                       usos=_usos("descanso"),
                       acao={"tipo": "grupo", "turnos": 3,
                             "efeitos": {"cura_por_turno": 0.1}},
                       exige_escolha=("magia_druida_t3", "aura_of_vitality")),
            Habilidade("call_lightning", "Call Lightning", ATIVA,
                       "1x por descanso: todos os inimigos fazem save de DES; "
                       "quem falha leva 6d10, quem passa leva metade.",
                       usos=_usos("descanso"),
                       acao={"tipo": "save", "save": "DES", "alvos": "todos",
                             "dano": "6d10", "metade": True},
                       exige_escolha=("magia_druida_t3", "call_lightning")),
            Habilidade("conjure_animals", "Conjure Animals", ATIVA,
                       "1x por descanso: um bando de bichos entra na sala, age "
                       "na vez dele e bate no inimigo mais ferido.",
                       usos=_usos("descanso"),
                       acao={"tipo": "invocar", "nome": "Bando selvagem",
                             "ca": 13, "ataque": 7, "dano": "2d6+3", "hp": 35,
                             "ameaca": 3, "iniciativa": 2},
                       exige_escolha=("magia_druida_t3", "conjure_animals"))],
        4: [Habilidade("natureza_t4", "Dadiva da natureza", ESCOLHA,
                       "Escolhe uma: Forma Lunar, Pressagio ou Golpe Primal.",
                       escolha={"tipo": "opcao", "opcoes": [
                           {"id": "forma_lunar", "nome": "Forma Lunar",
                            "texto": "A forma da o dobro de vida temporaria",
                            "efeito": {"forma_lunar": 1}},
                           {"id": "pressagio", "nome": "Pressagio",
                            "texto": "Socorre o teste falhado de um aliado"},
                           {"id": "golpe_primal", "nome": "Golpe Primal",
                            "texto": "+1d8 de dano em todo golpe dele",
                            "efeito": {"dano_bonus": "1d8"}},
                       ]}),
            Habilidade("pressagio", "Pressagio", ATIVA,
                       "1x por descanso: quando alguem do grupo falha o teste "
                       "da sala, soma +5 — e so dispara se o +5 fizer passar.",
                       usos=_usos("descanso"),
                       acao={"tipo": "reacao", "quando": "falhou_teste",
                             "bonus": 5},
                       exige_escolha=("natureza_t4", "pressagio"))],
        5: [Habilidade("magia_druida_t5", "Magia maior", ESCOLHA,
                       "Escolhe uma: Antilife Shell, Conjure Elemental ou "
                       "Mass Cure Wounds.",
                       escolha={"tipo": "opcao", "opcoes": [
                           {"id": "antilife_shell", "nome": "Antilife Shell",
                            "texto": "Dois aliados saem do alcance dos inimigos"},
                           {"id": "conjure_elemental", "nome": "Conjure Elemental",
                            "texto": "Um elemental de 70 HP entra na luta"},
                           {"id": "mass_cure_wounds_druida", "nome": "Mass Cure Wounds",
                            "texto": "O grupo inteiro cura 5d8+5"},
                       ]}),
            # Voar precisou de fator porque a curva nao tinha meio-termo; aqui
            # o extremo e o certo: no livro a esfera impede a criatura viva de
            # entrar, e todo ataque de criatura neste bot e corpo a corpo.
            #
            # Fator ZERO nao e invulnerabilidade: o sorteio de alvo tira do
            # bolo quem ja foi escolhido e renormaliza o que sobra (ver
            # `ameaca.sortear_varios`). Enquanto houver alguem fora da esfera,
            # a criatura bate nele; quando os dois protegidos sao tudo que
            # resta, o peso zera para todos e o sorteio volta ao uniforme —
            # eles levam pancada. A esfera desvia a atencao, nao apaga o alvo.
            Habilidade("antilife_shell", "Antilife Shell", ATIVA,
                       "1x por descanso: dois aliados ficam 2 rodadas fora do "
                       "alcance — as criaturas batem em quem sobrou, e so neles "
                       "se nao houver mais ninguem.",
                       usos=_usos("descanso"),
                       acao={"tipo": "duracao", "turnos": 2, "alvo": "aliados",
                             "alvos": 2,
                             "efeitos": {"ameaca_fator": 0.0}},
                       exige_escolha=("magia_druida_t5", "antilife_shell")),
            Habilidade("conjure_elemental", "Conjure Elemental", ATIVA,
                       "1x por descanso: um elemental entra na sala com 70 HP, "
                       "age na vez dele e bate no inimigo mais ferido.",
                       usos=_usos("descanso"),
                       acao={"tipo": "invocar", "nome": "Elemental",
                             "ca": 16, "ataque": 9, "dano": "2d8+5", "hp": 70,
                             "ameaca": 5, "iniciativa": 2},
                       exige_escolha=("magia_druida_t5", "conjure_elemental")),
            Habilidade("mass_cure_wounds_druida", "Mass Cure Wounds", ATIVA,
                       "1x por descanso: o grupo inteiro cura 5d8+5.",
                       usos=_usos("descanso"),
                       acao={"tipo": "grupo", "cura_dado": "5d8+5"},
                       exige_escolha=("magia_druida_t5", "mass_cure_wounds_druida"))],
    },
    # Mesmo corpo do mago, de proposito: os dois sao d6 e conjuram. O que os
    # separa e o METAMAGIC, que e a assinatura do feiticeiro — ele torce as
    # proprias magias, e aqui isso vale sempre, sem a contabilidade de Sorcery
    # Points. O mago tem mais magias; o feiticeiro tem magias melhores.
    "feiticeiro": {
        1: [Habilidade("magia_feit_t1", "Fagulha inata", ESCOLHA,
                       "Escolhe uma: Chromatic Orb, Burning Hands ou "
                       "Dissonant Whispers.",
                       escolha={"tipo": "opcao", "opcoes": [
                           {"id": "chromatic_orb", "nome": "Chromatic Orb",
                            "texto": "4d8 num alvo, sem save"},
                           {"id": "burning_hands", "nome": "Burning Hands",
                            "texto": "3d6 em todos, metade no sucesso"},
                           {"id": "dissonant_whispers", "nome": "Dissonant Whispers",
                            "texto": "3d6 num alvo, e ele perde a vez"},
                       ]}),
            Habilidade("chromatic_orb", "Chromatic Orb", ATIVA,
                       "1x por descanso: 4d8 num inimigo. Nao tem save — a "
                       "esfera acerta.",
                       usos=_usos("descanso"),
                       acao={"tipo": "save", "save": "DES", "alvos": 1,
                             "dano": "4d8", "sem_save": True},
                       exige_escolha=("magia_feit_t1", "chromatic_orb")),
            Habilidade("burning_hands", "Burning Hands", ATIVA,
                       "1x por descanso: todos os inimigos fazem save de DES; "
                       "quem falha leva 3d6, quem passa leva metade.",
                       usos=_usos("descanso"),
                       acao={"tipo": "save", "save": "DES", "alvos": "todos",
                             "dano": "3d6", "metade": True},
                       exige_escolha=("magia_feit_t1", "burning_hands")),
            Habilidade("dissonant_whispers", "Dissonant Whispers", ATIVA,
                       "1x por descanso: um inimigo faz save de SAB; falhando, "
                       "leva 3d6 e perde a proxima vez.",
                       usos=_usos("descanso"),
                       acao={"tipo": "save", "save": "SAB", "alvos": 1,
                             "dano": "3d6", "atordoa": 1},
                       exige_escolha=("magia_feit_t1", "dissonant_whispers"))],
        # Metamagic como passiva permanente: no livro cada uso custa Sorcery
        # Point, e o bot nao tem pool. Vale sempre — a identidade sobrevive,
        # a contabilidade nao.
        2: [Habilidade("metamagia_t2", "Metamagia", ESCOLHA,
                       "Ele torce as proprias magias, para sempre. Escolhe uma: "
                       "Empowered, Twinned ou Heightened.",
                       escolha={"tipo": "opcao", "opcoes": [
                           {"id": "empowered", "nome": "Empowered Spell",
                            "texto": "+1d8 de dano em toda magia dele",
                            "efeito": {"dano_magia": "1d8"}},
                           {"id": "twinned", "nome": "Twinned Spell",
                            "texto": "As magias de um alvo pegam dois",
                            "efeito": {"alvos_extra": 1}},
                           {"id": "heightened", "nome": "Heightened Spell",
                            "texto": "A criatura resiste com desvantagem",
                            "efeito": {"save_com_desvantagem": True}},
                       ]})],
        3: [Habilidade("magia_feit_t3", "Magia da origem", ESCOLHA,
                       "Escolhe uma: Fireball, Haste ou Grilhoes Planares.",
                       escolha={"tipo": "opcao", "opcoes": [
                           {"id": "fireball_feit", "nome": "Fireball",
                            "texto": "8d6 em todos, metade no sucesso"},
                           {"id": "haste", "nome": "Haste",
                            "texto": "Um aliado ataca 2x e ganha +2 de CA"},
                           {"id": "grilhoes_planares", "nome": "Grilhoes Planares",
                            "texto": "4d8 e o alvo sangra 2d8 por rodada"},
                       ]}),
            Habilidade("fireball_feit", "Fireball", ATIVA,
                       "1x por descanso: todos os inimigos fazem save de DES; "
                       "quem falha leva 8d6, quem passa leva metade.",
                       usos=_usos("descanso"),
                       acao={"tipo": "save", "save": "DES", "alvos": "todos",
                             "dano": "8d6", "metade": True},
                       exige_escolha=("magia_feit_t3", "fireball_feit")),
            Habilidade("haste", "Haste", ATIVA,
                       "1x por descanso: um aliado ataca duas vezes por rodada "
                       "e ganha +2 de CA, por 3 rodadas.",
                       usos=_usos("descanso"),
                       acao={"tipo": "duracao", "turnos": 3, "alvo": "aliados",
                             "alvos": 1, "efeitos": {"ataques": 2, "ca": 2}},
                       exige_escolha=("magia_feit_t3", "haste")),
            # A magia da casa. O texto diz que a criatura sangra se terminar o
            # turno onde comecou — e aqui nao existe posicao, entao isso seria
            # dano garantido. O escape virou o save: a cada rodada ela refaz o
            # teste e, passando, arrebenta a corrente.
            Habilidade("grilhoes_planares", "Grilhoes Planares", ATIVA,
                       "1x por descanso: um inimigo faz save de DES e leva 4d8 "
                       "(metade no sucesso). Falhando, fica acorrentado: sangra "
                       "2d8 no fim de cada rodada e refaz o save para escapar.",
                       usos=_usos("descanso"),
                       acao={"tipo": "save", "save": "DES", "alvos": 1,
                             "dano": "4d8", "metade": True, "turnos": 3,
                             "dano_por_rodada": "2d8"},
                       exige_escolha=("magia_feit_t3", "grilhoes_planares"))],
        4: [Habilidade("metamagia_t4", "Segunda metamagia", ESCOLHA,
                       "Mais um jeito de torcer as magias. Escolhe uma: "
                       "Quickened, Empowered, Twinned ou Heightened.",
                       escolha={"tipo": "opcao", "opcoes": [
                           {"id": "quickened", "nome": "Quickened Spell",
                            "texto": "Lanca a magia E ataca no mesmo turno",
                            "efeito": {"magia_rapida": 1}},
                           {"id": "empowered_2", "nome": "Empowered Spell",
                            "texto": "+1d8 de dano em toda magia dele",
                            "efeito": {"dano_magia": "1d8"}},
                           {"id": "twinned_2", "nome": "Twinned Spell",
                            "texto": "As magias de um alvo pegam dois",
                            "efeito": {"alvos_extra": 1}},
                           {"id": "heightened_2", "nome": "Heightened Spell",
                            "texto": "A criatura resiste com desvantagem",
                            "efeito": {"save_com_desvantagem": True}},
                       ]})],
        5: [Habilidade("magia_feit_t5", "Magia maior", ESCOLHA,
                       "Escolhe uma: Polymorph, Cone of Cold ou Dimension Door.",
                       escolha={"tipo": "opcao", "opcoes": [
                           {"id": "polymorph", "nome": "Polymorph",
                            "texto": "Um aliado vira uma fera e bate como ela"},
                           {"id": "cone_of_cold_feit", "nome": "Cone of Cold",
                            "texto": "12d8 em todos, metade no sucesso"},
                           {"id": "dimension_door", "nome": "Dimension Door",
                            "texto": "Ele e um aliado saem da mira"},
                       ]}),
            # Polymorph num ALIADO: e a forma do druida emprestada a outro.
            Habilidade("polymorph", "Polymorph", ATIVA,
                       "1x por descanso: um aliado vira uma fera por 3 rodadas "
                       "— bate com o dado dela, +2 de CA e vida temporaria.",
                       usos=_usos("descanso"),
                       acao={"tipo": "forma", "nome": "Fera", "turnos": 3,
                             "alvo": "aliado", "ca": 2, "ataques": 1,
                             "thp_por_tier": 3,
                             "dano": {1: "1d10+2", 2: "2d8+3", 3: "2d10+4",
                                      4: "2d12+5", 5: "3d10+5"}},
                       exige_escolha=("magia_feit_t5", "polymorph")),
            Habilidade("cone_of_cold_feit", "Cone of Cold", ATIVA,
                       "1x por descanso: todos os inimigos fazem save de CON; "
                       "quem falha leva 12d8, quem passa leva metade.",
                       usos=_usos("descanso"),
                       acao={"tipo": "save", "save": "CON", "alvos": "todos",
                             "dano": "12d8", "metade": True},
                       exige_escolha=("magia_feit_t5", "cone_of_cold_feit")),
            # Teleporte nao tem onde pegar; o que sobra dele e "sair de onde
            # estava". Mesmo caminho do Antilife Shell, em duas pessoas.
            Habilidade("dimension_door", "Dimension Door", ATIVA,
                       "1x por descanso: ele e um aliado desaparecem por 2 "
                       "rodadas — nenhuma criatura consegue mira-los.",
                       usos=_usos("descanso"),
                       acao={"tipo": "duracao", "turnos": 2, "alvo": "aliados",
                             "alvos": 2, "inclui_quem_usou": True,
                             "efeitos": {"ameaca_fator": 0.0}},
                       exige_escolha=("magia_feit_t5", "dimension_door"))],
    },
    # O bardo e o dono do socorro. Cinco habilidades de outras classes ja usam
    # a maquina dele (Sobrevivente, Lider Sagrado, Flash of Genius, Own Luck,
    # Pressagio), todas com numero fixo e UM uso. A versao dele e a melhor:
    # DADO, varios usos, e o jogador escolhe em que tipo de rolagem ela entra.
    #
    # Com dado o socorro pode nao bastar — entra quando o teto cobriria, e so
    # depois rola. E o que acontece na mesa, e e o que torna o dado um dado.
    "bardo": {
        1: [Habilidade("magia_bardo_t1", "Cancao de abertura", ESCOLHA,
                       "Escolhe uma: Healing Word, Dissonant Whispers ou "
                       "Charm Person.",
                       escolha={"tipo": "opcao", "opcoes": [
                           {"id": "healing_word", "nome": "Healing Word",
                            "texto": "Cura 2d4+3 de um aliado"},
                           {"id": "dissonant_whispers_bardo", "nome": "Dissonant Whispers",
                            "texto": "3d6 num alvo, e ele perde a vez"},
                           {"id": "charm_person_bardo", "nome": "Charm Person",
                            "texto": "Um inimigo perde as duas proximas vezes"},
                       ]}),
            Habilidade("healing_word", "Healing Word", ATIVA,
                       "1x por descanso: cura 2d4+3 de um aliado.",
                       usos=_usos("descanso"),
                       acao={"tipo": "cura", "dado": "2d4+3", "alvo": "aliado"},
                       exige_escolha=("magia_bardo_t1", "healing_word")),
            Habilidade("dissonant_whispers_bardo", "Dissonant Whispers", ATIVA,
                       "1x por descanso: um inimigo faz save de SAB; falhando, "
                       "leva 3d6 e perde a proxima vez.",
                       usos=_usos("descanso"),
                       acao={"tipo": "save", "save": "SAB", "alvos": 1,
                             "dano": "3d6", "atordoa": 1},
                       exige_escolha=("magia_bardo_t1", "dissonant_whispers_bardo")),
            Habilidade("charm_person_bardo", "Charm Person", ATIVA,
                       "1x por descanso: um inimigo faz save de SAB; falhando, "
                       "perde as duas proximas vezes.",
                       usos=_usos("descanso"),
                       acao={"tipo": "save", "save": "SAB", "alvos": 1,
                             "atordoa": 2},
                       exige_escolha=("magia_bardo_t1", "charm_person_bardo"))],
        # A Inspiracao e passiva porque dispara sozinha: o bardo nao clica, ela
        # entra quando alguem falha. A escolha e ONDE ela alcanca.
        2: [Habilidade("inspiracao_t2", "Inspiracao Bardica", ESCOLHA,
                       "O dado que ele sopra em quem falha. Escolhe em que "
                       "rolagem ele entra: ataque, resistencia ou pericia.",
                       escolha={"tipo": "opcao", "opcoes": [
                           {"id": "inspira_ataque", "nome": "No ataque",
                            "texto": "O golpe de um aliado que errou por pouco acerta"},
                           {"id": "inspira_save", "nome": "Na resistencia",
                            "texto": "O save falhado de um aliado passa a resistir"},
                           {"id": "inspira_pericia", "nome": "Na pericia",
                            "texto": "O teste de sala falhado de um aliado passa"},
                       ]}),
            Habilidade("inspira_ataque", "Inspiracao — no ataque", ATIVA,
                       "3x por descanso: quando um aliado erra o golpe por "
                       "pouco, o dado dele sobe no acerto.",
                       usos=_usos("descanso", 3),
                       acao={"tipo": "reacao", "quando": "falhou_teste",
                             "inspira": "ataque", "dado": "1d6"},
                       exige_escolha=("inspiracao_t2", "inspira_ataque")),
            Habilidade("inspira_save", "Inspiracao — na resistencia", ATIVA,
                       "3x por descanso: quando um aliado falha o save de uma "
                       "criatura por pouco, o dado o faz resistir.",
                       usos=_usos("descanso", 3),
                       acao={"tipo": "reacao", "quando": "falhou_teste",
                             "inspira": "save", "dado": "1d6"},
                       exige_escolha=("inspiracao_t2", "inspira_save")),
            Habilidade("inspira_pericia", "Inspiracao — na pericia", ATIVA,
                       "3x por descanso: quando alguem falha o teste da sala "
                       "por pouco, o dado o faz passar.",
                       usos=_usos("descanso", 3),
                       acao={"tipo": "reacao", "quando": "falhou_teste",
                             "inspira": "pericia", "dado": "1d6"},
                       exige_escolha=("inspiracao_t2", "inspira_pericia"))],
        3: [Habilidade("magia_bardo_t3", "Cancao da faculdade", ESCOLHA,
                       "Escolhe uma: Hypnotic Pattern, Aid ou Invisibility.",
                       escolha={"tipo": "opcao", "opcoes": [
                           {"id": "hypnotic_pattern_bardo", "nome": "Hypnotic Pattern",
                            "texto": "Os inimigos que falharem perdem a vez"},
                           {"id": "aid", "nome": "Aid",
                            "texto": "O grupo ganha vida temporaria e cura"},
                           {"id": "invisibility", "nome": "Invisibility",
                            "texto": "Um aliado sai da mira por 3 rodadas"},
                       ]}),
            Habilidade("hypnotic_pattern_bardo", "Hypnotic Pattern", ATIVA,
                       "1x por descanso: todos os inimigos fazem save de SAB; "
                       "quem falha perde as duas proximas vezes.",
                       usos=_usos("descanso"),
                       acao={"tipo": "save", "save": "SAB", "alvos": "todos",
                             "atordoa": 2},
                       exige_escolha=("magia_bardo_t3", "hypnotic_pattern_bardo")),
            Habilidade("aid", "Aid", ATIVA,
                       "1x por descanso: o grupo inteiro ganha 3d8 de vida "
                       "temporaria e cura o mesmo.",
                       usos=_usos("descanso"),
                       acao={"tipo": "grupo", "thp": "3d8", "cura_dado": "3d8"},
                       exige_escolha=("magia_bardo_t3", "aid")),
            # Invisibilidade e furtividade, e o bot nao tem nem uma nem outra.
            # O que sobra dela e "nao te acham": mesmo caminho do Fly e do
            # Antilife Shell, com o fator de ameaca.
            Habilidade("invisibility", "Invisibility", ATIVA,
                       "1x por descanso: um aliado desaparece por 3 rodadas — "
                       "os inimigos quase deixam de mira-lo.",
                       usos=_usos("descanso"),
                       acao={"tipo": "duracao", "turnos": 3, "alvo": "aliados",
                             "alvos": 1, "efeitos": {"ameaca_fator": 0.1}},
                       exige_escolha=("magia_bardo_t3", "invisibility"))],
        # Duas coisas no tier: o dado cresce de graca, e ele escolhe uma
        # passiva de pericia. O bardo do livro e metade recurso, metade saber.
        4: [Habilidade("inspiracao_maior", "Inspiracao maior", PASSIVA,
                       "O dado da Inspiracao dele passa de d6 para d10.",
                       {"dado_inspiracao": "1d10"}),
            Habilidade("saber_t4", "Repertorio", ESCOLHA,
                       "Escolhe uma: Expertise, Jack of All Trades ou "
                       "Versatilidade.",
                       escolha={"tipo": "opcao", "opcoes": [
                           {"id": "expertise_bardo", "nome": "Expertise",
                            "texto": "Dobra o bonus de Atuacao e Persuasao",
                            "efeito": {"expertise": ["Atuação", "Persuasão"]}},
                           # Ele e razoavel em TUDO: o unico bonus do bot que
                           # vale so no que o personagem nao treinou.
                           {"id": "jack_of_all_trades", "nome": "Jack of All Trades",
                            "texto": "+3 nos testes que ele NAO treinou",
                            "efeito": {"bonus_sem_treino": 3}},
                           {"id": "versatilidade", "nome": "Versatilidade",
                            "texto": "+2 em todo teste de pericia",
                            "efeito": {"bonus_teste": 2}},
                       ]})],
        5: [Habilidade("magia_bardo_t5", "Cancao maior", ESCOLHA,
                       "Escolhe uma: Mass Cure Wounds, Animate Objects ou "
                       "Otto's Irresistible Dance.",
                       escolha={"tipo": "opcao", "opcoes": [
                           {"id": "mass_cure_wounds_bardo", "nome": "Mass Cure Wounds",
                            "texto": "O grupo inteiro cura 5d8+5"},
                           {"id": "animate_objects", "nome": "Animate Objects",
                            "texto": "Objetos animados entram na luta"},
                           {"id": "ottos_dance", "nome": "Otto's Irresistible Dance",
                            "texto": "Um inimigo danca: perde a vez e erra mais"},
                       ]}),
            Habilidade("mass_cure_wounds_bardo", "Mass Cure Wounds", ATIVA,
                       "1x por descanso: o grupo inteiro cura 5d8+5.",
                       usos=_usos("descanso"),
                       acao={"tipo": "grupo", "cura_dado": "5d8+5"},
                       exige_escolha=("magia_bardo_t5", "mass_cure_wounds_bardo")),
            Habilidade("animate_objects", "Animate Objects", ATIVA,
                       "1x por descanso: objetos animados entram na sala, agem "
                       "na vez deles e batem no inimigo mais ferido.",
                       usos=_usos("descanso"),
                       acao={"tipo": "invocar", "nome": "Objetos animados",
                             "ca": 14, "ataque": 8, "dano": "3d6+2", "hp": 50,
                             "ameaca": 3, "iniciativa": 1},
                       exige_escolha=("magia_bardo_t5", "animate_objects")),
            Habilidade("ottos_dance", "Otto's Irresistible Dance", ATIVA,
                       "1x por descanso: um inimigo faz save de SAB; falhando, "
                       "danca por 3 rodadas — perde a vez e tira 5 do ataque.",
                       usos=_usos("descanso"),
                       acao={"tipo": "save", "save": "SAB", "alvos": 1,
                             "atordoa": 3, "turnos": 3,
                             "penalidade_ataque": 5},
                       exige_escolha=("magia_bardo_t5", "ottos_dance"))],
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
    # Escudo Arcano do mago: THP por tier, que recarrega a cada magia.
    "escudo_arcano": 0,
    # Sabedoria Arcana do mago: quanto o grupo inteiro soma nos saves.
    "aura_save": 0,
    # Dark One's Blessing: THP por tier ao derrubar um inimigo.
    "thp_ao_derrubar": 0,
    # Companheiro selvagem do druida: cura por tier ao abrir o combate.
    "bichinho_cura": 0,
    # Forma Lunar: dobra a vida temporaria que o Wild Shape da.
    "forma_lunar": 0,
    # Metamagia do feiticeiro. Dados entram em DADOS (comparados pela media);
    # os outros sao numero ou bandeira.
    "dano_magia": "",
    "alvos_extra": 0,
    "save_com_desvantagem": False,
    "cd_magia": 0,
    "magia_rapida": 0,
    # Inspiracao Bardica: o dado que o tier 4 substitui pelo maior.
    "dado_inspiracao": "",
    # Jack of All Trades: vale SO nas pericias que o personagem nao treinou.
    "bonus_sem_treino": 0,
}

# Chaves cujo valor e uma expressao de dano, e nao um inteiro.
DADOS = ("dano_bonus", "bonus_cura", "dano_magia", "dado_inspiracao")


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
