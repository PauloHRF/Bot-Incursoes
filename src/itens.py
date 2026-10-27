"""O catálogo de itens do mercado, e a regra que impede o stack.

Este é o segundo sistema de patrimônio do grupo, e não o mesmo: a planilha do
Google guarda o que os personagens carregam na campanha, e isto aqui é a
economia das Incursões, que começa de zero e vive dentro do bot.

**Cada slot manda num número só.** É daí que vem a contenção: não existe
regra de teto, nem limite a conferir em tempo de execução — o slot já impede
empilhar cinco fontes do mesmo bônus, porque só cabe uma armadura. `DOMINIO`
diz o que cada slot pode mexer, e `fora_do_dominio` é o que transforma isso
em regra de verdade: um teste varre o catálogo e reprova o item que escapar.
Sem isso o domínio seria um comentário, e comentário não segura ninguém.

Os efeitos são os MESMOS que as passivas de classe usam (habilidades.NEUTRO),
então um item que dá +1 de CA entra pelo caminho do Fighting Style: nada de
máquina nova, e a ficha, o combate e o painel passam a contar com ele de
graça.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Os cinco lugares do corpo. A ordem é a de leitura na ficha.
SLOTS = ("armadura", "arma", "bota", "capa", "anel")

NOME_DO_SLOT = {
    "armadura": "Armadura",
    "arma": "Arma",
    "bota": "Botas",
    "capa": "Capacete/capa",
    "anel": "Anel",
}

# O que cada slot pode mexer, e nada além disso. A primeira chave de cada
# tupla é a razão de o slot existir; as outras são o tempero das raridades
# altas, escolhido para não invadir o slot do vizinho.
DOMINIO: dict[str, tuple[str, ...]] = {
    # Proteção: a CA, e o corpo que a cura encontra.
    "armadura": ("ca", "thp_na_cura"),
    # Ofensa: acertar e doer. O crítico é tempero porque é raro de sair.
    "arma": ("acerto", "dano_extra", "dano_bonus", "critico_em"),
    # Prontidão: chegar antes e saber das coisas.
    "bota": ("bonus_iniciativa", "bonus_teste"),
    # Resistência: aguentar o que a sala cobra.
    "capa": ("bonus_save", "bonus_save_atributo"),
    # O curinga, e o único que mexe em quem a criatura escolhe bater.
    #
    # `ameaca_fator` NAO entra aqui, e a tentação é grande: ele é o que o Fly e
    # o Antilife Shell usam para tirar alguém da mira. Mas ele é campo de
    # Combatente preenchido pelo caminho de duração, não chave de efeito — num
    # item ele seria descartado em silêncio por `juntar_efeito`. E mesmo que
    # entrasse, a consolidação é por `max()`, e num fator o melhor é o MENOR:
    # 0,33 perderia para o 1,0 neutro. Sair da mira é coisa de magia com prazo,
    # não de anel que não sai do dedo.
    "anel": ("ameaca", "bonus_cura_pct", "dano_ferido", "thp_ao_derrubar"),
}

# Quanto cada raridade custa, e quanto ela aparece na vitrine. O peso é
# relativo: num sorteio de seis vagas, o lendário sai em pouco mais de uma
# semana a cada dez.
RARIDADES = ("comum", "incomum", "raro", "lendario")
NOME_DA_RARIDADE = {
    "comum": "Comum",
    "incomum": "Incomum",
    "raro": "Raro",
    "lendario": "Lendário",
}
PRECO_BASE = {"comum": 80, "incomum": 180, "raro": 400, "lendario": 900}
PESO_NA_VITRINE = {"comum": 50, "incomum": 30, "raro": 15, "lendario": 5}


@dataclass(frozen=True)
class Item:
    """Uma peça do catálogo.

    `efeito` fala a língua de `habilidades.NEUTRO`, e só pode tocar as chaves
    que `DOMINIO` dá ao slot dele. `preco` sai da raridade quando não é dito.
    """

    id: str
    nome: str
    slot: str
    raridade: str
    texto: str
    efeito: dict = field(default_factory=dict)
    preco: Optional[int] = None

    @property
    def custo(self) -> int:
        return self.preco if self.preco is not None else PRECO_BASE[self.raridade]

    @property
    def peso(self) -> int:
        return PESO_NA_VITRINE[self.raridade]


def _i(
    id: str, nome: str, slot: str, raridade: str, texto: str,
    efeito: dict, preco: Optional[int] = None,
) -> Item:
    return Item(id, nome, slot, raridade, texto, efeito, preco)


# ---------------------------------------------------------------- o catálogo
#
# Sete peças por slot: duas comuns, duas incomuns, duas raras e uma lendária.
# Os números são de propósito tímidos — a CA nunca passa de +2 vinda de item,
# porque +2 já é o que o melhor domínio de clérigo dá, e cinco slots somando
# fariam o equipamento valer mais que a classe. Está tudo aqui num lugar só:
# para recalibrar, mexa nos números e rode os testes.

CATALOGO: tuple[Item, ...] = (
    # ------------------------------------------------------------- armadura
    _i("gibao_de_couro", "Gibão de couro batido", "armadura", "comum",
       "Couro curtido duas vezes. +1 de CA.", {"ca": 1}),
    _i("tunica_acolchoada", "Túnica acolchoada", "armadura", "comum",
       "Pouca proteção, muita gentileza: +2 de vida temporária ao ser curado.",
       {"thp_na_cura": 2}),
    _i("cota_de_malha_ana", "Cota de malha anã", "armadura", "incomum",
       "+1 de CA, e +3 de vida temporária ao ser curado.",
       {"ca": 1, "thp_na_cura": 3}),
    _i("brunea_do_vigia", "Brunea do vigia", "armadura", "incomum",
       "Feita para turno de guarda. +1 de CA e +4 de vida temporária ao ser curado.",
       {"ca": 1, "thp_na_cura": 4}),
    _i("peitoral_de_serpe", "Peitoral de escamas de serpe", "armadura", "raro",
       "+2 de CA.", {"ca": 2}),
    _i("couraca_do_fosso", "Couraça do fosso", "armadura", "raro",
       "+2 de CA, e +3 de vida temporária ao ser curado.",
       {"ca": 2, "thp_na_cura": 3}),
    _i("egide_do_portao", "Égide do Portão", "armadura", "lendario",
       "A placa que ficou de pé quando o portão caiu. +2 de CA e +6 de vida "
       "temporária ao ser curado.",
       {"ca": 2, "thp_na_cura": 6}),

    # ----------------------------------------------------------------- arma
    _i("lamina_afiada", "Lâmina bem afiada", "arma", "comum",
       "+1 de acerto.", {"acerto": 1}),
    _i("maca_pesada", "Maça pesada", "arma", "comum",
       "Lenta e sincera: +2 de dano por golpe.", {"dano_extra": 2}),
    _i("espada_do_arsenal", "Espada do arsenal", "arma", "incomum",
       "+1 de acerto e +2 de dano por golpe.", {"acerto": 1, "dano_extra": 2}),
    _i("machado_dentado", "Machado dentado", "arma", "incomum",
       "+4 de dano por golpe. Nada de sutileza.", {"dano_extra": 4}),
    _i("florete_do_duelista", "Florete do duelista", "arma", "raro",
       "+1 de acerto, e crítico já com 19 no dado.",
       {"acerto": 1, "critico_em": 19}),
    _i("martelo_runico", "Martelo rúnico", "arma", "raro",
       "+1d6 de dano em todo golpe que acerta.",
       {"acerto": 1, "dano_bonus": "1d6"}),
    _i("lanca_do_juramento", "Lança do juramento", "arma", "lendario",
       "+2 de acerto, +1d8 em todo golpe, e crítico com 19.",
       {"acerto": 2, "dano_bonus": "1d8", "critico_em": 19}),

    # ----------------------------------------------------------------- bota
    _i("botas_de_marcha", "Botas de marcha", "bota", "comum",
       "+2 na iniciativa.", {"bonus_iniciativa": 2}),
    _i("sandalias_do_batedor", "Sandálias do batedor", "bota", "comum",
       "+1 em todo teste de perícia.", {"bonus_teste": 1}),
    _i("botas_do_mensageiro", "Botas do mensageiro", "bota", "incomum",
       "+3 na iniciativa e +1 em todo teste de perícia.",
       {"bonus_iniciativa": 3, "bonus_teste": 1}),
    _i("coturnos_de_placa", "Coturnos de placa", "bota", "incomum",
       "+2 na iniciativa e +2 em todo teste de perícia.",
       {"bonus_iniciativa": 2, "bonus_teste": 2}),
    _i("botas_sem_rastro", "Botas sem rastro", "bota", "raro",
       "+4 na iniciativa e +2 em todo teste de perícia.",
       {"bonus_iniciativa": 4, "bonus_teste": 2}),
    _i("grevas_do_vento", "Grevas do vento", "bota", "raro",
       "+5 na iniciativa.", {"bonus_iniciativa": 5}),
    _i("passos_do_primeiro", "Passos do Primeiro", "bota", "lendario",
       "Quem as calça chega antes de a porta abrir. +6 na iniciativa e +3 em "
       "todo teste de perícia.",
       {"bonus_iniciativa": 6, "bonus_teste": 3}),

    # ----------------------------------------------------------------- capa
    _i("capa_de_viagem", "Capa de viagem", "capa", "comum",
       "+1 em todo teste de resistência.", {"bonus_save": 1}),
    _i("elmo_amassado", "Elmo amassado", "capa", "comum",
       "+2 nos saves de Constituição.", {"bonus_save_atributo": {"CON": 2}}),
    _i("capuz_do_eremita", "Capuz do eremita", "capa", "incomum",
       "+1 em todo save, e +2 nos de Sabedoria.",
       {"bonus_save": 1, "bonus_save_atributo": {"SAB": 2}}),
    _i("elmo_de_visor", "Elmo de visor", "capa", "incomum",
       "+1 em todo save, e +2 nos de Destreza.",
       {"bonus_save": 1, "bonus_save_atributo": {"DES": 2}}),
    _i("manto_estrelado", "Manto estrelado", "capa", "raro",
       "+2 em todo teste de resistência.", {"bonus_save": 2}),
    _i("coroa_de_ferro", "Coroa de ferro", "capa", "raro",
       "+2 em todo save, e +2 nos de Carisma.",
       {"bonus_save": 2, "bonus_save_atributo": {"CAR": 2}}),
    _i("manto_do_concilio", "Manto do Concílio", "capa", "lendario",
       "Nada que a sala cobre pega quem o veste de surpresa. +3 em todo teste "
       "de resistência.", {"bonus_save": 3}),

    # ----------------------------------------------------------------- anel
    _i("anel_de_lata", "Anel de lata", "anel", "comum",
       "Chama atenção à toa: +2 de ameaça.", {"ameaca": 2}),
    _i("anel_do_curativo", "Anel do curativo", "anel", "comum",
       "As curas dele curam 5% do HP maximo a mais.",
       {"bonus_cura_pct": 0.05}),
    _i("anel_do_provocador", "Anel do provocador", "anel", "incomum",
       "+4 de ameaça: as criaturas vêm atrás de quem o usa.", {"ameaca": 4}),
    _i("anel_do_carrasco", "Anel do carrasco", "anel", "incomum",
       "+4 de dano contra quem está com metade ou menos do HP.",
       {"dano_ferido": 4}),
    _i("anel_do_coveiro", "Anel do coveiro", "anel", "raro",
       "Ao derrubar um inimigo, ganha vida temporária — 2 por tier.",
       {"thp_ao_derrubar": 2}),
    _i("anel_do_santuario", "Anel do santuário", "anel", "raro",
       "As curas dele curam 15% do HP maximo a mais.",
       {"bonus_cura_pct": 0.15}),
    _i("anel_do_para_raios", "Anel do para-raios", "anel", "lendario",
       "+8 de ameaça. Quem o veste decide onde a pancada cai — nele.",
       {"ameaca": 8}),
)

POR_ID: dict[str, Item] = {i.id: i for i in CATALOGO}


def item(id: Optional[str]) -> Optional[Item]:
    """O item daquele id, ou None. Id solto no banco não derruba a ficha."""
    return POR_ID.get(str(id or ""))


def do_slot(slot: str) -> list[Item]:
    return [i for i in CATALOGO if i.slot == slot]


# Como cada chave de efeito vira texto para o jogador. O catalogo tambem tem
# um `texto` com a prosa da peca ("Couro curtido duas vezes"), mas a vitrine
# mostra so o que a peca FAZ: na hora de comparar cinco pecas e decidir uma
# compra, a prosa atrapalha mais do que ajuda.
#
# Sair daqui, e nao do `texto`, tem uma vantagem que a prosa nao tem: o numero
# mostrado e o numero que o motor aplica. Nao da para a descricao dizer +1 e o
# efeito valer +2, que e o tipo de divergencia que ninguem percebe.
ROTULO_DO_EFEITO = {
    "ca": lambda v: f"{v:+d} de CA",
    "acerto": lambda v: f"{v:+d} de acerto",
    "dano_extra": lambda v: f"{v:+d} de dano",
    "dano_bonus": lambda v: f"+{v} de dano",
    "dano_ferido": lambda v: f"{v:+d} contra alvo ferido",
    "critico_em": lambda v: f"crítico em {v}",
    "bonus_iniciativa": lambda v: f"{v:+d} de iniciativa",
    "bonus_teste": lambda v: f"{v:+d} em testes de perícia",
    "bonus_save": lambda v: f"{v:+d} em resistências",
    "bonus_save_atributo": lambda v: " · ".join(
        f"{n:+d} em resistência de {a}" for a, n in sorted(v.items())
    ),
    "thp_na_cura": lambda v: f"{v:+d} de vida temporária ao ser curado",
    "thp_ao_derrubar": lambda v: f"{v:+d} de vida temporária ao derrubar",
    "bonus_cura_pct": lambda v: f"+{v:.0%} de cura",
    "ameaca": lambda v: f"{v:+d} de ameaça",
}


def status(peca: "Item") -> str:
    """O que a peça faz, em texto, lido do efeito dela."""
    partes = [
        ROTULO_DO_EFEITO[chave](valor)
        for chave, valor in (peca.efeito or {}).items()
        if chave in ROTULO_DO_EFEITO
    ]
    return " · ".join(partes) or "sem efeito"


def fora_do_dominio(peca: Item) -> set[str]:
    """As chaves que aquele item mexe e que o slot dele não deveria mexer.

    Vazio é o esperado. Não vazio é um item que furou a contenção dos slots —
    o teste do catálogo falha, e é essa falha que mantém a regra viva depois
    que ninguém mais lembrar dela.
    """
    return set(peca.efeito) - set(DOMINIO.get(peca.slot, ()))


def juntar_equipamento(efeitos: dict, ids) -> dict:
    """Dobra o equipamento DENTRO dos efeitos da classe, e devolve o mesmo dicionário.

    Não monta um acumulado próprio para somar depois: isso daria duas
    consolidações, e a segunda não saberia que a primeira já tinha escolhido
    pelo maior. Com os efeitos da classe como base, um item de +1 de CA e o
    Protetor de +2 resolvem como duas passivas resolveriam — vale o melhor,
    não a soma. Item desconhecido no banco é ignorado em silêncio, porque id
    velho não pode derrubar a ficha.
    """
    from . import habilidades as H

    for id_do_item in ids or ():
        peca = item(id_do_item)
        if peca is not None:
            H.juntar_efeito(efeitos, peca.efeito)
    return efeitos


__all__ = [
    "CATALOGO", "DOMINIO", "Item", "NOME_DA_RARIDADE", "NOME_DO_SLOT",
    "PESO_NA_VITRINE", "POR_ID", "PRECO_BASE", "RARIDADES", "SLOTS",
    "do_slot", "fora_do_dominio", "item", "juntar_equipamento",
]
