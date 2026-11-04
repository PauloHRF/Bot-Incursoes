"""As poções do mercado: o que elas fazem e quanto custam.

Módulo puro, como `itens.py` — e separado dele de propósito. O equipamento é
**permanente e único por slot**, e é o slot que impede o stack; a poção é
**gasta no uso e empilha na bolsa**, e o que a contém é o teto por tipo
(`TETO_NA_BOLSA`). São duas regras de contenção diferentes, e misturar as duas
num catálogo só faria `fora_do_dominio` ter de aprender exceções.

**A poção não inventa mecânica nenhuma.** Cada uma tem uma `acao` na mesma
língua das ativas de classe (`habilidades.Habilidade.acao`), então a Poção de
Vida é o Second Wind do guerreiro com outro nome, e quem a resolve no combate é
o mesmo `_resolver_habilidade` que resolve o resto. `habilidade_de` monta a
ficha sintética que esse caminho espera.

Duas coisas valem dizer sobre o desenho:

**Beber é a ação da rodada** — quem bebe não ataca. A exceção é a Poção da
Aceleração, que existe justamente para isso: ela é de graça e deixa o turno
livre, como o Quickened Spell do feiticeiro. É isso que a torna especial, e não
o número de golpes.

**O efeito com prazo é gravado pela FAMÍLIA, não pelo id da poção** (ver
`chave_do_efeito`). `aplicar_efeito` é INSERT OR REPLACE na chave, então beber
a segunda Aceleração renova a primeira em vez de somar com ela — a mesma regra
que vale para as habilidades. Sem isso, três poções de graça no mesmo turno
dariam +6 golpes.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Iterable, Optional

from . import condicoes, habilidades

# Quantas unidades da MESMA poção cabem na bolsa. O teto é o que segura a
# guerra de atrito: sem ele, ouro guardado virava estoque, e uma incursão
# longa deixava de cobrar o HP que ela cobra.
TETO_NA_BOLSA = 3

# Por quantos turnos vale a poção de prazo. Três é o mesmo prazo das ativas de
# classe (Rage, Reckless Attack): o combate médio dura de 4 a 6 rodadas, então
# três turnos é "mais da metade da luta" sem ser "a luta inteira".
TURNOS = 3

# Quanto cada X reduz de dano, por ponto de X. Dois por X, como pedido: a
# Resistência 3 corta 6 de cada golpe, que é um golpe pequeno inteiro no tier
# 1 e cerca de um terço de um grande no tier 4.
REDUCAO_POR_X = 2

# Os preços são FIXOS, como os do equipamento, e não escalam por tier: é o
# ganho por sala que acompanha o personagem (ver `mercado.ouro_da_sala`). Na
# prática a poção é caríssima no tier 1 — uma incursão Média paga 50 — e
# barata no tier 4, que paga 200. É o mesmo desenho do gibão de 80.
PRECO_VIDA_MENOR = 40
PRECO_VIDA = 80
# A escada do X: dobra do 1 para o 2 e quase dobra do 2 para o 3, porque o
# efeito também cresce assim.
PRECO_POR_X = {1: 50, 2: 100, 3: 180}
# A de mana custa mais porque devolve um RECURSO, e não um número: um uso de
# tier 3 pode ser a cura que levanta o grupo.
PRECO_MANA_POR_X = {1: 80, 2: 160, 3: 280}

# Os X que existem. Não é faixa aberta: cada um tem preço e texto escritos.
NIVEIS = (1, 2, 3)

# As famílias, na ordem em que aparecem na vitrine.
VIDA, ACELERACAO, RESISTENCIA, DANO, MANA, BUFF = (
    "vida", "aceleracao", "resistencia", "dano", "mana", "buff"
)
FAMILIAS = (VIDA, ACELERACAO, RESISTENCIA, DANO, MANA, BUFF)

# Como a família se chama em texto. Serve ao painel do combate, que lê o id do
# efeito gravado (`chave_do_efeito`) e precisa dizer "Poção da Aceleração" em
# vez de "pocao_aceleracao".
NOME_DA_FAMILIA = {
    VIDA: "Poção de Vida",
    ACELERACAO: "Poção da Aceleração",
    RESISTENCIA: "Poção de Resistência",
    DANO: "Poção do Dano",
    MANA: "Poção de Mana",
    BUFF: "Poção de buff",
}

# O que a família faz, numa linha, com o X por extenso. O `texto` de cada
# poção fala do nível DELA ("+1 de dano"), e para explicar a família inteira
# isso engana — então o resumo é escrito aqui, e é ele que a documentação usa.
RESUMO_DA_FAMILIA = {
    VIDA: "Recupera 30% (Menor) ou 50% do HP máximo de quem bebe.",
    ACELERACAO: "+X golpes por rodada, e beber não gasta a ação da rodada.",
    RESISTENCIA: "Corta 2X do dano de cada golpe recebido, depois da resistência.",
    DANO: "+X de dano em cada golpe.",
    MANA: "Devolve um uso já gasto de uma habilidade de tier X.",
    BUFF: "X stacks de um buff da tabela — uma poção para cada um dos 12.",
}

# O prefixo de toda chave de efeito de poção, para quem precisa reconhecer uma
# sem importar o catálogo inteiro.
PREFIXO_DO_EFEITO = "pocao_"



def nome_do_efeito(chave: str) -> Optional[str]:
    """O nome da poção por trás de uma chave de `run_efeitos`, ou None."""
    if not chave.startswith(PREFIXO_DO_EFEITO):
        return None
    return NOME_DA_FAMILIA.get(chave[len(PREFIXO_DO_EFEITO):])


# O alambique, e não o frasco: 🧪 já quer dizer "pegou um debuff" no log do
# combate, e é o botão de tirar debuff no Descanso. Dois significados para o
# mesmo ícone na mesma tela confundem.
ICONE = "\N{ALEMBIC}\N{VARIATION SELECTOR-16}"

# O artigo de cada buff, escrito à mão. Gênero em português não sai da
# terminação — "Benção" e "Coragem" são femininas e não acabam em A —, e a
# heurística dava "Poção do Benção". `test_pocoes.py` cobra uma entrada aqui
# para cada buff do catálogo de condições, então um buff novo não entra em
# cartaz com o artigo errado.
ARTIGO_DO_BUFF = {
    "sustento": "do", "bencao": "da", "orientacao": "da", "coragem": "da",
    "purificado": "do", "vigor": "do", "rapidez": "da", "potencia": "da",
    "esperteza": "da", "pressa": "da", "sociavel": "do", "prudencia": "da",
}


def nome_da_pocao_de_buff(buff, x: int) -> str:
    """'Poção da Benção 2'. O artigo vem de `ARTIGO_DO_BUFF`."""
    return f"Poção {ARTIGO_DO_BUFF.get(buff.id, 'do')} {buff.nome} {x}"


@dataclass(frozen=True)
class Consumivel:
    """Uma poção do catálogo.

    `acao` é lida pelo mesmo resolvedor das ativas de classe. `familia` agrupa
    para a vitrine sortear por família, e `x` é o nível (0 nas de vida, que não
    têm X).
    """

    id: str
    nome: str
    texto: str
    preco: int
    acao: dict
    familia: str
    x: int = 0
    # Beber gasta a ação da rodada. A Aceleração é a única que não.
    gasta_turno: bool = True

    @property
    def custo(self) -> int:
        return self.preco

    @property
    def chave_do_efeito(self) -> str:
        """Sob que nome o efeito com prazo é gravado em `run_efeitos`.

        A FAMÍLIA, e não o id: beber a segunda poção da mesma família renova a
        primeira em vez de empilhar com ela.
        """
        return f"{PREFIXO_DO_EFEITO}{self.familia}"


def _vida(id: str, nome: str, pct: int, preco: int) -> Consumivel:
    return Consumivel(
        id, nome,
        f"Recupera {pct}% do HP máximo de quem bebe.",
        preco,
        {"tipo": "cura", "fracao": pct / 100, "alvo": "proprio"},
        VIDA,
    )


CATALOGO: tuple[Consumivel, ...] = (
    # ------------------------------------------------------------- as fixas
    # Estas duas estão SEMPRE na prateleira (ver `FIXAS`): são o chão do
    # mercado de consumíveis, e é por elas que o grupo pode decidir encarar
    # uma sala de combate sabendo com o que conta.
    _vida("pocao_vida_menor", "Poção de Vida Menor", 30, PRECO_VIDA_MENOR),
    _vida("pocao_vida", "Poção de Vida", 50, PRECO_VIDA),

    # --------------------------------------------------------- a aceleração
    # A única que não gasta o turno: bebe e bate na mesma rodada. Os golpes a
    # mais somam no que a classe já dá, então um guerreiro de Multiattack com
    # a Aceleração 2 sai com quatro golpes.
    *(
        Consumivel(
            f"pocao_aceleracao_{x}", f"Poção da Aceleração {x}",
            f"Bebe e age no mesmo turno: beber não gasta a ação. "
            f"+{x} golpe(s) por rodada durante {TURNOS} turnos.",
            PRECO_POR_X[x],
            {"tipo": "duracao", "turnos": TURNOS, "alvo": "proprio",
             "efeitos": {"ataques_extra": x}},
            ACELERACAO, x, gasta_turno=False,
        )
        for x in NIVEIS
    ),

    # -------------------------------------------------------- a resistência
    # Corte PLANO, e depois da redução por fração (a do Rage): é o que segura
    # sala de muitos golpes pequenos, onde cortar 50% de 5 não muda nada e
    # tirar 4 de cada golpe muda tudo.
    *(
        Consumivel(
            f"pocao_resistencia_{x}", f"Poção de Resistência {x}",
            f"Reduz em {REDUCAO_POR_X * x} o dano de cada golpe recebido, "
            f"depois da resistência, durante {TURNOS} turnos.",
            PRECO_POR_X[x],
            {"tipo": "duracao", "turnos": TURNOS, "alvo": "proprio",
             "efeitos": {"reducao_plana": REDUCAO_POR_X * x}},
            RESISTENCIA, x,
        )
        for x in NIVEIS
    ),

    # --------------------------------------------------------------- o dano
    *(
        Consumivel(
            f"pocao_dano_{x}", f"Poção do Dano {x}",
            f"+{x} de dano em cada golpe durante {TURNOS} turnos.",
            PRECO_POR_X[x],
            {"tipo": "duracao", "turnos": TURNOS, "alvo": "proprio",
             "efeitos": {"dano_extra": x}},
            DANO, x,
        )
        for x in NIVEIS
    ),

    # --------------------------------------------------------------- a mana
    # Devolve um uso GASTO de uma habilidade daquele tier. Quem bebe escolhe
    # qual, porque duas magias do mesmo tier não são a mesma coisa.
    *(
        Consumivel(
            f"pocao_mana_{x}", f"Poção de Mana {x}",
            f"Devolve um uso de uma habilidade de tier {x} que você já gastou "
            f"nesta incursão.",
            PRECO_MANA_POR_X[x],
            {"tipo": "recarga", "tier": x},
            MANA, x,
        )
        for x in NIVEIS
    ),

    # -------------------------------------------------------------- o buff
    # Uma poção por buff da tabela, e o X são os STACKS. O buff decai 1 por
    # combate, então a Poção da Benção 3 é "+3 em ataques e saves agora, +2 no
    # combate seguinte, +1 no outro" — prazo diferente das de 3 turnos, e de
    # propósito: é a tabela de condições que manda nele, não a poção.
    *(
        Consumivel(
            f"pocao_{buff.id}_{x}", nome_da_pocao_de_buff(buff, x),
            f"{x} stack{'s' if x > 1 else ''} de {buff.nome}: {buff.texto}",
            PRECO_POR_X[x],
            {"tipo": "condicao", "condicao": buff.id, "stacks": x},
            BUFF, x,
        )
        for buff in condicoes.CATALOGO
        if buff.tipo == condicoes.BUFF
        for x in NIVEIS
    ),
)

POR_ID: dict[str, Consumivel] = {c.id: c for c in CATALOGO}

# As que estão sempre na prateleira.
FIXAS: tuple[Consumivel, ...] = tuple(c for c in CATALOGO if c.familia == VIDA)
# As que disputam a vaga que sobra.
SORTEAVEIS: tuple[Consumivel, ...] = tuple(c for c in CATALOGO if c.familia != VIDA)

# Quantas vagas a prateleira de poções tem.
VAGAS = len(FIXAS) + 1


def item(id: Optional[str]) -> Optional[Consumivel]:
    """A poção daquele id, ou None. Id solto no banco não derruba a ficha."""
    return POR_ID.get(str(id or ""))


def e_pocao(id: Optional[str]) -> bool:
    return str(id or "") in POR_ID


def da_familia(familia: str) -> list[Consumivel]:
    return [c for c in CATALOGO if c.familia == familia]
def niveis_da_familia(familia: str) -> list[int]:
    """Os X que aquela família tem, sem repetir. Vazio na de vida."""
    return sorted({c.x for c in da_familia(familia) if c.x})


def precos_da_familia(familia: str) -> list[int]:
    """Os preços daquela família, do mais barato ao mais caro, sem repetir."""
    return sorted({c.custo for c in da_familia(familia)})


def vitrine(
    personagem_id: int, semana: str, sorteaveis: Optional[Iterable[Consumivel]] = None
) -> list[Consumivel]:
    """As poções à venda para aquele personagem naquela semana.

    As duas de vida, sempre, mais uma sorteada. Derivada de (personagem,
    semana) como a vitrine de equipamento, pela mesma razão: o que é derivado
    não envelhece, e recarregar a mensagem não embaralha a loja.

    O sorteio é por FAMÍLIA primeiro, e só depois por poção dentro dela. As
    36 poções de buff são três quartos do bolo — sorteando direto, três de
    cada quatro semanas trariam buff e a Poção de Mana apareceria uma vez por
    ano. Por família cada uma das cinco tem a mesma chance.
    """
    bolo = list(sorteaveis if sorteaveis is not None else SORTEAVEIS)
    escolhidas = list(FIXAS)
    if not bolo:
        return escolhidas
    gerador = random.Random(f"pocoes:{personagem_id}:{semana}")
    familias = sorted({c.familia for c in bolo})
    familia = familias[gerador.randint(0, len(familias) - 1)]
    candidatas = [c for c in bolo if c.familia == familia]
    escolhidas.append(candidatas[gerador.randint(0, len(candidatas) - 1)])
    return escolhidas


def esta_na_vitrine(personagem_id: int, semana: str, pocao_id: str) -> bool:
    """Se aquela poção está à venda para aquele personagem nesta semana."""
    return any(c.id == pocao_id for c in vitrine(personagem_id, semana))


def habilidade_de(pocao: Consumivel) -> habilidades.Habilidade:
    """A ficha sintética que o resolvedor de habilidades espera.

    O combate não precisa saber que poção existe: ele recebe algo com `id`,
    `nome` e `acao`, que é o contrato de `_resolver_habilidade`. O id é o da
    poção quando o efeito é instantâneo, e o da FAMÍLIA quando ele tem prazo —
    é esse id que vira a chave em `run_efeitos`.
    """
    com_prazo = pocao.acao.get("tipo") == "duracao"
    return habilidades.Habilidade(
        id=pocao.chave_do_efeito if com_prazo else pocao.id,
        nome=pocao.nome,
        tipo=habilidades.ATIVA,
        texto=pocao.texto,
        acao=dict(pocao.acao),
    )


def rotulo(pocao: Consumivel) -> str:
    """Nome com o ícone, para a vitrine e a bolsa."""
    return f"{ICONE} {pocao.nome}"


__all__ = [
    "CATALOGO", "Consumivel", "FAMILIAS", "FIXAS", "ICONE", "NIVEIS", "POR_ID",
    "REDUCAO_POR_X", "SORTEAVEIS", "TETO_NA_BOLSA", "TURNOS", "VAGAS",
    "da_familia", "e_pocao", "esta_na_vitrine", "habilidade_de", "item",
    "rotulo", "vitrine",
]
