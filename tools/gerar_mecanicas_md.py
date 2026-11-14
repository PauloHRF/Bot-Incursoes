"""Escreve docs/mecanicas/: um arquivo por mecânica do bot.

    .venv/Scripts/python.exe tools/gerar_mecanicas_md.py

É gerador, e não texto escrito à mão, pelo mesmo motivo de `balanco.py`: todo
número aqui sai do módulo que o usa de verdade. Mexer numa constante e rodar
isto de novo atualiza a documentação na hora, em vez de deixar dois lugares
discordando — já aconteceu duas vezes neste projeto (o `BALANCO.md` afirmando
que a CD não escalava depois que ela passou a escalar, e o texto do Cone of
Cold prometendo 12d8 depois de virar 8d8).

A prosa fica aqui; os números vêm de `src/`. Se um valor aparece escrito no
meio de uma frase, é porque foi interpolado — não confie em nenhum literal
nestes .md.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import (  # noqa: E402
    ameaca,
    bestiario,
    classes as cl,
    config,
    condicoes as cond,
    consequencias as C,
    consumiveis,
    embeds as E,
    habilidades as H,
    incursoes as I,
    itens,
    mercado,
    motor,
    rules,
)

# O gerador do balanço é a fonte dos usos por masmorra: ele os mede, e deixar
# este arquivo copiar os números daria dois documentos divergindo em silêncio.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import balanco  # noqa: E402
from tools.simulacao import medidas  # noqa: E402

PASTA = RAIZ / "docs" / "mecanicas"


# --------------------------------------------------------------- utilitários
def tabela(cabecalho: list[str], linhas: list[list[str]]) -> list[str]:
    saida = ["| " + " | ".join(cabecalho) + " |",
             "|" + "|".join("---" for _ in cabecalho) + "|"]
    saida += ["| " + " | ".join(l) + " |" for l in linhas]
    saida.append("")
    return saida


def num(valor: float, casas: int = 1, enxuto: bool = True) -> str:
    """Número com vírgula decimal, que é como se escreve em português.

    Sem isto o documento mistura os dois: o que o gerador calcula sai com
    ponto e o que está escrito na prosa sai com vírgula, na mesma tabela.

    `enxuto` corta o decimal zerado — bom para "1,0x" virar "1x" na prosa, e
    ruim numa coluna de tabela, onde "15%" ao lado de "15,9%" desalinha.
    """
    texto = f"{valor:.{casas}f}"
    if enxuto and casas and texto.endswith("0" * casas):
        texto = texto.split(".")[0]
    return texto.replace(".", ",")


def pct(fracao: float, casas: int = 1) -> str:
    """Uma fração (0..1) em pontos percentuais, com os decimais preservados."""
    return num(fracao * 100, casas, enxuto=False) + "%"


def lista(itens_: list[str]) -> list[str]:
    return [f"- {i}" for i in itens_] + [""]


def rodape(modulos: list[str]) -> list[str]:
    """De onde saem os números deste arquivo."""
    return [
        "---",
        "",
        "Gerado por `tools/gerar_mecanicas_md.py` a partir de "
        + ", ".join(f"`{m}`" for m in modulos)
        + ". Não edite à mão: rode o gerador.",
        "",
    ]


def cds_dos_bancos() -> dict[str, dict[int, int]]:
    """Quantas salas de cada tipo existem em cada CD, lidas dos bancos.

    A CD de uma sala é conteúdo, não regra, então o número certo é o que está
    escrito nos arquivos — e não uma faixa repetida aqui, que envelheceria na
    próxima recalibragem.
    """
    import json

    contagem: dict[str, dict[int, int]] = {}
    for arquivo in sorted((RAIZ / "data" / "bancos").glob("*.json")):
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
        for sala in dados.get("salas") or []:
            if sala.get("cd"):
                por_cd = contagem.setdefault(sala["tipo"], {})
                por_cd[sala["cd"]] = por_cd.get(sala["cd"], 0) + 1
    return contagem


# ============================================================ tier e progressão
def tier_e_progressao() -> str:
    L = [
        "# Tier e progressão",
        "",
        f"O personagem vai do nível 1 ao {rules.NIVEL_MAXIMO}. Cada tier cobre "
        f"{rules.NIVEIS_POR_TIER} níveis, então são {rules.TIER_MAXIMO} tiers.",
        "",
        "O tier é a unidade de tudo: a tabela da classe, as habilidades novas, "
        "a CD das salas e QUEM mora em cada sala de combate todos leem o "
        "tier, não o nível. O nível existe para dar dois passos dentro de "
        "cada tier.",
        "",
    ]
    def em_todas(tier: int, campo: str) -> str:
        """O valor daquele campo no tier, lido de TODAS as classes.

        Sai do conjunto em vez de uma classe de exemplo: hoje os dois bônus
        são iguais em toda classe, e se um dia deixarem de ser, a tabela
        mostra a faixa em vez de afirmar o número de uma só.
        """
        valores = sorted(
            {getattr(c.numeros(tier), campo) for c in cl.CLASSES.values()}
        )
        if len(valores) == 1:
            return f"+{valores[0]}"
        return f"+{valores[0]}–{valores[-1]}"

    L += tabela(
        ["Tier", "Níveis", "Bônus de proficiência", "Bônus sem proficiência"],
        [
            [
                f"T{t}",
                "–".join(str(n) for n in rules.faixa_do_tier(t)),
                em_todas(t, "bonus_proficiencia"),
                em_todas(t, "bonus_pericia"),
            ]
            for t in range(1, rules.TIER_MAXIMO + 1)
        ],
    )
    L += [
        "Os dois bônus são **iguais em toda classe** — é a progressão da casa, "
        "e não um número de classe. O que muda por classe é HP, CA, acerto, "
        "dano e quantas perícias ela treina: de "
        + "–".join(
            str(v) for v in (
                min(c.numeros(rules.TIER_MAXIMO).pericias for c in cl.CLASSES.values()),
                max(c.numeros(rules.TIER_MAXIMO).pericias for c in cl.CLASSES.values()),
            )
        )
        + " no tier 5 (ver `docs/FICHAS.md`).",
        "",
        "## O que o tier escala",
        "",
        "### A CD das salas",
        "",
        "A CD escrita no banco é a do tier 1. O tier soma um ajuste que segue "
        "o próprio bônus de proficiência, para a chance de passar ficar onde "
        "está em toda a faixa:",
        "",
    ]
    # As faixas saem dos bancos, e nao de literais: ver `cds_dos_bancos`.
    faixas = sorted({cd for por_cd in cds_dos_bancos().values() for cd in por_cd})
    L += tabela(
        ["Tier", "Ajuste de CD"] + [f"CD {cd} no T1" for cd in faixas],
        [
            [
                f"T{t}",
                f"+{rules.AJUSTE_DE_CD_POR_TIER[t]}",
                *(str(rules.cd_no_tier(base, t)) for base in faixas),
            ]
            for t in range(1, rules.TIER_MAXIMO + 1)
        ],
    )
    L += [
        "Sem esse ajuste a sala de tier 5 seria trivial, porque o grupo chega "
        "lá com o bônus muito maior do que quando a CD foi escrita. Com ele, a "
        "taxa de sucesso é idêntica nos cinco tiers.",
        "",
        "### As criaturas NÃO escalam",
        "",
        "A CD escala porque a perícia do personagem cresce devagar. A criatura "
        "não: **a ficha dela vale como está escrita**, e o tier está em QUEM "
        "mora na sala. Cada sala de combate tem uma lista por tier "
        "(`monstros_por_tier`), e a sala escolhe a do tier da incursão — ou a "
        "do maior tier escrito abaixo dele, que é o que faz conteúdo de tier "
        "baixo continuar jogável por grupo alto.",
        "",
        "Antes havia um multiplicador por tier (1,0 · 1,6 · 2,4 · 3,1 · 3,8 "
        "de HP e dano, mais o ajuste da CD em CA e ataque). A conta vinha da "
        "curva de HP da família d8 e parecia certa, mas batia em cima de "
        "fichas já escritas em força cheia de *Monster Manual*: cinco Gárgulas "
        "de 52 HP viravam 416 HP numa sala de tier 2, e as cinco salas de "
        "combate de um banco dizimavam o grupo **sempre** — 0% de vitória com "
        "o grupo de HP cheio. A mesa sentiu isso antes de a conta mostrar, e "
        "passou a evitar combate para chegar inteira ao objetivo.",
        "",
        "O bestiário tem 385 criaturas de CR 0 a 20 (ver `CRIATURAS.md`): se "
        "uma não serve ao tier, o conteúdo usa outra. Faixa de CR por tier, "
        "como `bestiario.tier_do_cr` lê:",
        "",
    ]
    L += tabela(
        ["Tier", "Faixa de CR"],
        [
            [f"T{t}",
             f"{num(baixo)} a {num(alto)}" if alto < 90 else f"{num(baixo)}+"]
            for t, (baixo, alto) in sorted(bestiario.FAIXAS_DE_CR.items())
        ],
    )
    L += [
        "A faixa é ponto de partida, não garantia: ela vem do livro, e o que "
        "vale é a medição contra a mesa deste bot "
        "(`tools/simular_combate.py --tier`). A sala do caminho é calibrada "
        "para **cobrar HP sem ameaçar dizimar** — vitória ≥ 95% e 55% a 75% do "
        "HP restante —, porque quem decide a run é o objetivo.",
        "",
        "## Perícias e resistências",
        "",
        "Não há tabela separada para save. Um save **forte** usa o mesmo bônus "
        "de uma perícia com proficiência, e um save fraco o de uma perícia sem "
        "— o que muda por classe é só quais dois atributos são fortes. "
        "Expertise dobra o bônus de proficiência naquela perícia.",
        "",
        f"Os {len(rules.ATRIBUTOS)} atributos: "
        + ", ".join(rules.ATRIBUTOS) + ".",
        "",
        f"As {len(rules.PERICIAS)} perícias: "
        + ", ".join(rules.PERICIAS) + ".",
        "",
    ]
    return "\n".join(L + rodape(["src/rules.py", "src/classes.py"]))


# ========================================================================= combate
def combate() -> str:
    L = [
        "# Combate",
        "",
        "Resolvido em `src/motor.py`, que é função pura sobre dados simples: "
        "não conhece Discord nem banco. É de propósito — as mecânicas podem "
        "mudar sem tocar na camada de comandos, e o playtest pode ser "
        "simulado (`tools/simular_combate.py`).",
        "",
        "## A ordem",
        "",
        "Iniciativa é **1d20 + o save de DES**, rolada uma vez quando o "
        "combate abre, para todos de uma vez — personagens e criaturas na "
        "mesma lista. Quem está na vez age; quando a lista dá a volta, a "
        "rodada vira.",
        "",
        "## A ação da rodada",
        "",
        "Cada personagem faz **uma** coisa por rodada, e o painel tem os três "
        "botões que ela pode ser: **Atacar**, **Habilidade** e "
        f"**{consumiveis.ICONE} Poção**. Escolher qualquer um gasta a rodada "
        "— quem bebe não ataca.",
        "",
        "Três coisas fogem disso, e as três são a razão de existirem: a "
        "**reação** (dispara sozinha no gatilho, sem consumir a vez), o "
        "**Quickened Spell** do feiticeiro (a magia sai como ação de bônus e "
        "o turno fica livre) e a **Poção da Aceleração** (beber não custa a "
        "ação). Ver `mercado.md` para as poções.",
        "",
        "## Preparar a ação, e mudar de ideia",
        "",
        "Clicar antes da sua vez **guarda** a ação: ela sai quando a "
        "iniciativa chegar em você. Isso é o normal, não a exceção — o painel "
        "é uma mensagem só para o grupo inteiro, e cada um clica quando vê.",
        "",
        "Enquanto a ação está guardada, **clicar de novo troca**. A escolha "
        "anterior sai da mesa e a nova entra, e o que a antiga tinha "
        "reservado volta: o uso da habilidade, a poção que já havia saído da "
        "bolsa. É a mesma devolução de quando a vez não chega "
        "(`_devolver_reservas`), pelo mesmo motivo — a ação não aconteceu.",
        "",
        "Depois de a ação **sair**, não há o que trocar: dano não se desfaz. "
        "Aí o aviso volta a ser o de sempre, dizendo com o que o turno foi "
        "gasto.",
        "",
        "Isso também é como quem foi substituído retoma a vez: a ação que o "
        "grupo escolheu por ele fica guardada como qualquer outra, então ele "
        "aparecer e clicar desfaz a do grupo.",
        "",
        "## O ataque",
        "",
        "**1d20 + acerto** contra a CA do alvo. O acerto e o dano saem da "
        "tabela da classe no tier, com o equipamento do mercado já somado.",
        "",
    ]
    L += lista([
        "**1 natural erra sempre**, qualquer que seja a CA.",
        "**20 natural acerta sempre, e é crítico.** O crítico dobra os dados "
        "de dano, não a constante.",
        "`critico_em` abaixa o d20 que já conta como crítico — Improved "
        "Critical crita com 19.",
        "`ataques` diz quantos golpes por rodada; Multiattack é a passiva que "
        "dá 2.",
    ])
    L += [
        "## A CD das magias do personagem",
        "",
        f"**{cl.BASE_DA_CD} + o acerto da classe no tier.** Uma conta só, "
        "para o jogador não ter de somar nada à mão.",
        "",
        "O acerto varia por classe, então a CD também. A faixa em cada tier:",
        "",
    ]

    def faixa_de_cd(tier: int) -> tuple[str, str]:
        acertos = sorted({c.numeros(tier).acerto for c in cl.CLASSES.values()})
        cds = [cl.BASE_DA_CD + a for a in acertos]
        def intervalo(valores):
            if valores[0] == valores[-1]:
                return str(valores[0])
            return f"{valores[0]}–{valores[-1]}"
        return intervalo(acertos), intervalo(cds)

    L += tabela(
        ["Tier", "Acerto", "CD das magias"],
        [[f"T{t}", f"+{faixa_de_cd(t)[0]}", faixa_de_cd(t)[1]]
         for t in range(1, rules.TIER_MAXIMO + 1)],
    )
    L += [
        "O número de cada classe está em `docs/FICHAS.md`.",
        "",
    ]
    L += [
        "## Os saves das criaturas",
        "",
        "A criatura do bestiário traz os saves escritos. A criatura de sala "
        "escrita à mão em geral não traz, e aí o bot deduz: "
        f"**ataque − {motor.DEFASAGEM_DE_SAVE}**. Os dois caminhos recebem o "
        "ajuste de tier, para o bestiário e o conteúdo escrito à mão não "
        "resistirem de formas diferentes.",
        "",
        "## A área rola um dado só",
        "",
        "O sopro do dragão, a bola de fogo, o estouro que pega a sala "
        "inteira: **a rolagem é uma, e todo mundo debaixo dela enfrenta o "
        "mesmo número**. O que continua por pessoa é o que é da pessoa — o "
        "save, a metade de quem passou, a redução de dano e a vida "
        "temporária.",
        "",
        "Rolando por alvo, a mesma baforada dava cinco números diferentes, e "
        "com cinco alvos a chance de *alguém* tirar perto do máximo virava "
        "quase certa: o efeito ficava mais forte só por haver mais gente para "
        "acertar. A regra vale nas duas direções — criatura contra o grupo "
        "(`motor.usar_habilidade_do_inimigo`) e magia de área contra a sala "
        "(`alvos: \"todos\"`, e o `dano_em_todos` dos Guerreiros Anciões).",
        "",
        "**O multiataque é o contrário.** Quando a habilidade rola *ataque* "
        "em vez de impor save, cada alvo leva um golpe **seu**, com acerto e "
        "dano próprios: ali são vários golpes, não um efeito. O mesmo vale "
        "para o alvo extra do feiticeiro, que é uma segunda conjuração de uma "
        "magia de alvo único.",
        "",
        "## As marcas do painel",
        "",
        "Ao lado do HP, o painel acende o que está **ligado** naquele "
        "personagem — e os dois estados que tiram alguém da rodada:",
        "",
    ]
    L += lista([
        f"{emoji} **{nome}** — {texto}"
        for emoji, nome, texto, _aceso in E.MARCAS + E.ESTADOS
    ] + [
        f"{E.MARCA_ABATIDO} **Abatida** — a criatura caiu, e ela não volta.",
    ])
    L += [
        "Nenhuma dessas marcas repete ícone de condição (`condicoes.md`), "
        "porque as duas famílias dividem a **mesma linha**. Três repetiam, e "
        "o jogador lia a coisa errada sem ter como saber: quem cedeu foram as "
        "marcas, porque as condições são o vocabulário da planilha. "
        "`/incursao buffs` é a legenda do que estiver aceso na hora.",
        "",
        "## Vida temporária (THP)",
        "",
        "A THP absorve dano antes do HP, e **empilha**: receber uma nova soma "
        "na que já havia, em vez de substituir.",
        "",
        "Somar é a regra do Espírito Guardião do xamã — ganhar novos THPs não "
        "substitui os antigos, soma-se a eles — e ela vale para todas as "
        "fontes porque o xamã ganha THP por gatilho de d20: substituindo, o "
        "quarto gatilho da luta não daria nada, e o teto dele ficava em 16 "
        "quando o tier 5 pede 20. A habilidade era inalcançável.",
        "",
        "Quem está caído não ganha THP — voltar a lutar é outra história.",
        "",
        "## Cair",
        "",
        "A 0 de HP o personagem cai: perde a vez enquanto estiver no chão e "
        "deixa de ser sorteado como alvo. **Não há morte no bot.** O que "
        "acaba mal é a incursão: caindo o grupo inteiro, a run encerra em "
        "fracasso — e mesmo assim os pontos de participação entram, porque o "
        "grupo levou a run até o fim.",
        "",
        "**Cura levanta.** Qualquer cura — a apontada em alguém, a que cai no "
        "grupo e a que vem por turno — tira do chão quem está a 0, e ele "
        "volta com o que a cura deu. A conta é a de sempre, de 0 para cima: "
        "nada é somado nem descontado por o alvo estar caído, e a Debilidade "
        "corta essa cura como corta as outras. Quem levanta volta a agir na "
        "própria vez seguinte.",
        "",
        "**E voltar do chão custa 1 ponto de Exaustão.** O preço é de sair do "
        "zero, não da cura: cobra igual nas três, inclusive na regeneração "
        "por turno, que levanta sem ninguém decidir. Curar quem está de pé "
        "não cobra nada.",
        "",
        "A Exaustão **não decai com o combate** — só o descanso tira, um "
        f"ponto por descanso — e com {cond.TETO_EXAUSTAO} pontos o "
        "personagem sai da incursão. Então o custo acumula: cair e voltar "
        "várias vezes numa incursão é o caminho mais rápido para ficar fora "
        "dela, e segurar o aliado de pé vale mais que levantá-lo depois.",
        "",
        "Isso **não** desfaz uma derrota: caindo o grupo inteiro, o combate "
        "encerra antes de a rodada virar, e a cura por turno nem chega a "
        "rodar. Vida temporária segue sendo outra história — quem está no "
        "chão não ganha THP, porque THP não levanta ninguém.",
        "",
        "Fora do combate, quem caiu também volta de pé no Descanso.",
        "",
        "## Descanso",
        "",
        "As duas metades do Descanso não são a mesma conta:",
        "",
    ]
    L += lista([
        "Quem está **de pé** recebe uma cura de "
        + pct(motor.FRACAO_DESCANSO, 0)
        + " do HP máximo, somada ao que ele tem. É cura de verdade, então a "
        "Maldição da Debilidade a corta como corta qualquer outra.",
        "Quem **caiu** é posto em "
        + pct(motor.FRACAO_DESCANSO_CAIDO, 0)
        + " do HP máximo e volta a lutar. Não é cura somada, é um valor "
        "fixado — e por isso nada o reduz.",
    ])
    L += [
        "O Descanso também zera os usos das habilidades de escopo `descanso` "
        "e tira um stack de Exaustão.",
        "",
        "O Descanso **não** cura tudo, de propósito: ele cura uma fatia e "
        "ainda deixa o grupo escolher o que limpar.",
        "",
        "### Onde o descanso acontece",
        "",
        "O descanso é **parada fixa do caminho**, pelo tamanho da incursão, e "
        "não sala sorteada. Ele chega **sem votação**: é sempre a mesma coisa, "
        "e escolher entre três cópias dela não é escolher. Os botões de limpeza "
        "continuam, porque a limpeza é de cada um — e é a única saída da "
        "Exaustão.",
        "",
    ]
    L += tabela(
        ["Tamanho", "Paradas de descanso"],
        [
            [
                nome,
                ", ".join(
                    f"{parada}ª — "
                    + ("descanso fixo" if qual == I.DESCANSO_NORMAL
                       else "a Última Vigília")
                    for parada, qual in sorted(
                        I.DESCANSOS_DO_CAMINHO.get(passos, {}).items()
                    )
                ) or "nenhuma",
            ]
            for nome, passos in I.TAMANHOS.items()
        ],
    )
    L += [
        "## A Última Vigília",
        "",
        "A segunda parada da Longa, depois da sexta sala, não é o descanso "
        "fixo: é uma **escolha**. Falta uma sala para o objetivo, e o grupo "
        f"decide o que gasta para chegar nela. São **{C.TROCAS_POR_DESCANSO} "
        f"trocas** sorteadas de um catálogo de {len(C.CATALOGO_DE_TROCAS)}, "
        "votadas pela maioria como uma sala — a troca vence para o grupo "
        "inteiro, não para quem votou.",
        "",
        "Toda troca cura mais que o descanso fixo e cobra por isso. A moeda "
        "cara é a **Exaustão**: ela não decai com o combate, só sai no "
        f"descanso fixo, e em {cond.TETO_EXAUSTAO} pontos tira o personagem "
        "da incursão — e a vigília acontece quando falta uma sala.",
        "",
    ]
    def o_preco(t) -> str:
        if t.exaustao:
            ponto = "ponto" if t.exaustao == 1 else "pontos"
            return f"{t.exaustao} {ponto} de Exaustão em cada um"
        return "nada"

    def em_troca(t) -> str:
        if t.limpa_debuffs:
            return "tira **todo debuff** do grupo"
        if t.ouro_de_sala:
            return "paga o ouro de **uma sala**"
        if t.buff:
            return "dá **um buff** ao grupo inteiro"
        return "—"

    L += tabela(
        ["Troca", "Cura", "O que cobra", "O que dá além da cura"],
        [
            [
                t.nome,
                (f"{t.cura_pct}%" if t.cura_pct else "—")
                + (f" + {t.thp_pct}% de THP" if t.thp_pct else ""),
                o_preco(t),
                em_troca(t),
            ]
            for t in C.CATALOGO_DE_TROCAS
        ],
    )
    L += [
        "Três delas não cobram: pagam de outro jeito. **Lavar as feridas** "
        "cura pouco e tira todo debuff do grupo (a Exaustão não é debuff e "
        "fica); **revirar o lugar** cura pouco e paga o ouro de uma sala, "
        "porque o grupo procurou em vez de dormir; **velar os mortos** não "
        "cura ninguém e dá ao grupo inteiro um buff da tabela.",
        "",
        "A vigília **conta como descanso** para as habilidades de escopo "
        "`descanso`, e **não** conta como sala superada: descansar não é "
        "vencer nada, e o ouro das salas é por sala vencida.",
        "",
        "## Cura",
        "",
        "**Toda cura do bot é porcentagem do HP máximo, nunca dado.** Um dado "
        "fixo encolhe conforme o grupo sobe de tier: 2d8 é metade da vida no "
        "tier 1 e um arranhão no tier 5. A porcentagem vale igual na faixa "
        "inteira.",
        "",
    ]
    return "\n".join(L + rodape(["src/motor.py", "src/classes.py"]))


# ========================================================================= ameaça
def ameaca_md() -> str:
    grupo = ["guerreiro", "paladino", "clerigo", "ladino", "mago"]
    L = [
        "# Ameaça: quem a criatura escolhe bater",
        "",
        "Sem isto o alvo é sorteado uniformemente, e então não existe tanque: "
        "o mago leva tanta pancada quanto o guerreiro de armadura pesada. A "
        "Ameaça dá a cada personagem um peso nesse sorteio.",
        "",
        "## As quatro partes",
        "",
    ]
    L += lista([
        "**A inicial da classe** — a posição dela na sala virando número. Quem "
        "bate de perto aparece primeiro. Não escala por tier: ameaça é o papel "
        "na sala, não o poder do personagem.",
        "**O que as habilidades ligadas somam**, enquanto duram.",
        "**O que o personagem gerou agindo**, que acumula do primeiro golpe ao "
        "fim do combate e morre com a sala.",
        f"**O bônus de quem está ferido** — `+{ameaca.AMEACA_DE_FERIDO}` abaixo "
        f"de {ameaca.LIMIAR_DE_FERIDO:.0%} do HP, que é a criatura indo "
        "terminar o serviço.",
    ])
    L += ["## Os seis grupos", ""]
    L += [
        "A inicial sai de seis grupos, e não de um número por classe. Eram "
        "três degraus para catorze classes, com sete empatadas no piso: para "
        "a criatura, ladino, mago, bardo, bruxo, druida, feiticeiro e xamã "
        "eram a mesma pessoa. Os seis degraus abrem a janela de 20–30% para "
        "20–38%.",
        "",
    ]
    _piso = min(ameaca.AMEACA_INICIAL.values())
    L += tabela(
        ["Grupo", "Ameaça", "Classes", "Fatia da atenção"],
        [
            [f"G{i}", str(valor),
             ", ".join(cl.CLASSES[c].nome if c in cl.CLASSES else c for c in nomes),
             pct(ameaca.fracoes([valor] + [_piso] * 4)[0])]
            for i, (valor, nomes) in enumerate(ameaca.GRUPOS, start=1)
        ],
    )
    L += [
        f"A fatia é num grupo de cinco onde os outros quatro estão no piso "
        f"({_piso}); o sorteio uniforme seria 20%. Classe sem grupo cai no "
        f"padrão, {ameaca.PADRAO}.",
        "",
        "**Os valores só importam como razão.** A potência normalizada cancela "
        "qualquer fator comum, então `12/10/8/6/4/2` e `6/5/4/3/2/1` dão a "
        "mesma distribuição. O tamanho absoluto da escala existe para dar "
        "resolução ao que é **somado** por cima — o bônus de ferido, o "
        "Reckless Attack, os pontos de ação. Dobrar a escala sem dobrar esses "
        "números os enfraquece em silêncio.",
        "",
    ]
    L += [
        "## Quem está por cair",
        "",
        f"Abaixo de **{ameaca.LIMIAR_DE_FERIDO:.0%} do HP** o personagem leva "
        f"`+{ameaca.AMEACA_DE_FERIDO}` de ameaça: a criatura vai terminar o "
        "serviço.",
        "",
        "São **pontos fixos**, e não uma fração da inicial. Por ser plano, o "
        "bônus empurra muito mais quem tem ameaça baixa — o Ladino sai de "
        f"{pct(ameaca.fracoes([_piso] + [_piso] * 4)[0])} para "
        f"{pct(ameaca.fracoes([_piso + ameaca.AMEACA_DE_FERIDO] + [_piso] * 4)[0])} "
        "da atenção, o Guerreiro de "
        f"{pct(ameaca.fracoes([ameaca.inicial('guerreiro')] + [_piso] * 4)[0])} para "
        f"{pct(ameaca.fracoes([ameaca.inicial('guerreiro') + ameaca.AMEACA_DE_FERIDO] + [_piso] * 4)[0])} "
        "—, e é exatamente isso que se quer: a criatura abandona o tanque "
        "inteiro para ir no mago sangrando. Proporcional faria o contrário, "
        "somando mais em quem já era o alvo.",
        "",
        "Quem está no chão não entra: ele já saiu do sorteio por outro "
        "caminho.",
        "",
        "## Quanto cada ação gera: o HP que ela moveu",
        "",
        "Uma régua só para as três coisas que um personagem faz numa luta, "
        "cada uma medida contra a própria poça:",
        "",
    ]
    L += lista([
        "o **dano** que ele causou, em fração do HP máximo somado dos "
        "inimigos da sala;",
        "a **cura** que ele deu (HP e vida temporária), em fração do HP "
        "máximo do grupo;",
        "o **dano que ele evitou** incapacitando uma criatura — o que ela "
        "daria nas rodadas que perdeu —, também em fração do HP do grupo.",
    ])
    # A tabela sai da MEDIÇÃO gravada, e não de números copiados para cá: um
    # número que chega ao documento por cópia continua lá depois de o código
    # mudar, e ninguém sabe dizer de quando ele é.
    medida = medidas.de("ameaca_por_acao")
    if not medida:
        L += [
            f"A fração vira pontos pela escala, que é "
            f"**{ameaca.ESCALA_DO_HP}** pontos por 100% da poça. **Quanto uma "
            "ação costuma mover ainda não foi medido** — rode "
            "`tools/medir_ameaca.py`.",
            "",
        ]
    else:
        L += [
            f"A fração vira pontos pela escala, que é **{medida['escala']}** "
            "pontos por 100% da poça. Medido na bateria dos cinco tiers com "
            f"os resolvedores reais (`tools/medir_ameaca.py`, "
            f"{medida['acoes']} ações, {medida['quando']}):",
            "",
        ]
        L += tabela(
            ["Ação", "Fração da poça", "Pontos"],
            [
                [rotulo, pct(medida[chave]),
                 str(ameaca.pontos_do_hp(
                     dano=round(medida[chave] * 1000), hp_dos_inimigos=1000))]
                for rotulo, chave in (
                    ("média", "media"), ("boa (p90)", "p90"),
                    ("excepcional (p99)", "p99"),
                )
            ],
        )
        if medidas.esta_velha(medida):
            L += ["> A medição é de um código anterior a este. Rode "
                  "`tools/medir_ameaca.py` para saber se ela continua valendo.",
                  ""]
    L += [
        "**O que conta como controle** é o que tira a vez: atordoamento e "
        "prisão. É a leitura literal de \"não foi dado\" — atrapalhar o "
        "ataque da criatura ou virá-la contra os seus seriam palpites sobre "
        "dano que ainda pode acontecer. E o que ela daria é o dado **dela** "
        "vezes a chance de passar da armadura de quem está na frente, porque "
        "o dano real também erra. Prender um Troll por três rodadas numa mesa "
        "de tier 5 rende uns 13 pontos: mais que a rodada de p90 de quem bate, "
        "e é de propósito — é uma ativa de tier 5, uma vez por descanso.",
        "",
        "Conta o **ganho**, não o prazo: estender uma prisão de uma rodada "
        "para três vale duas, e renovar uma que já ia até lá vale zero.",
        "",
    ]
    L += [
        "**Por que fração, e não o dano cru.** Em números absolutos o tier "
        "alto dominaria: a mesma Fireball tira 90 de uma sala de T1 e 450 de "
        "uma de T5, e o mago de tier 5 teria dez vezes a ameaça do de tier 1 "
        "por fazer exatamente a mesma coisa. Em fração as duas valem igual, e "
        "é isso que permite uma escala só para o jogo todo — o p90 varia "
        + (f"{medida['espalhamento_entre_tiers']:g}x " if medida
           and medida.get("espalhamento_entre_tiers") else "pouco ")
        + "entre tiers, que é ruído de cenário e não tendência.",
        "",
        "**Por que vale uma rodada só.** A regra anterior era valor "
        "*declarado* — a ameaça da própria classe, dobrada em área e cura —, e "
        "ela acumulava o combate inteiro. Acumulando, a conta convergia: "
        "depois de três rodadas as fatias andavam meio ponto e a mira ficava "
        "parada no que a classe decidiu na abertura. A janela de uma rodada "
        "devolve a variação, e com ela o dano pode entrar sem travar ninguém "
        "no teto. O preço, dito de frente: a mira passou a responder ao dado, "
        "e não só à escolha.",
        "",
        "**O overkill fica de fora**, por consequência de medir HP movido: "
        "bater 40 num inimigo de 5 move 5, porque matar o que já ia morrer "
        "não é notável.",
        "",
        "Uma habilidade pode declarar `ameaca_gerada` na ação e pular a conta "
        "inteira. É o gancho para uma provocação de verdade — uma habilidade "
        "cujo ponto é chamar atenção não deveria depender de ter machucado "
        "alguém.",
        "",
        "## A curva",
        "",
        f"A ameaça crua não vale direto no sorteio: ela passa por "
        f"`peso = x ** {ameaca.K}`. Cada ponto novo rende menos que o "
        f"anterior, então ninguém trava o combate stackando ameaça.",
        "",
        "**Não é a fórmula de armadura `x / (x + Y)`**, e a diferença importa "
        "porque os pontos do HP movido são grandes perto da inicial — uma "
        "rodada de p99 soma 20 numa escala que vai de 2 a 12. Aquela fórmula "
        "tem teto em 1, então com a conta crescendo todo mundo encosta no "
        "teto e o sorteio volta a ser quase uniforme:",
        "",
    ]
    L += tabela(
        ["Ameaça crua", "Com a curva de armadura (teto em 1)", "Com a potência"],
        [
            ["100 / 60 / 40", "35,4% / 33,4% / 31,2%",
             " / ".join(pct(f) for f in ameaca.fracoes([100, 60, 40]))],
        ],
    )
    L += [
        "A potência comprime igual embaixo e não satura — ainda é um tanque "
        "depois de uma luta longa.",
        "",
        "`K` é o botão de calibragem, e anda ao contrário do que parece: **K "
        "pequeno achata** (tudo encosta em 1) e **K = 1 é o stack simples**, "
        "somar e dividir.",
        "",
        "## A janela: o que valeu na rodada passada",
        "",
        "A ameaça do HP movido numa rodada vale na rodada **seguinte**, e só "
        "nela. Na rodada R a criatura olha o que foi feito em R-1, fechada.",
        "",
        "É o que tira a iniciativa da conta: todo mundo é visto exatamente "
        "uma vez por cada criatura, não importa a posição na fila. Com uma "
        "janela que incluísse a rodada corrente, quem joga antes da criatura "
        "chamaria atenção na própria rodada e quem joga depois não — e a "
        "posição na iniciativa viraria metade da mecânica.",
        "",
        "A rodada 1 fica só com a posição da classe, o que é justo: ninguém "
        "fez nada ainda. Uma mesa de um personagem por grupo abrindo o "
        "combate:",
        "",
    ]
    L += tabela(
        ["Rodada"] + [cl.CLASSES[c].nome for c in grupo],
        [
            ["1 (só a classe)"]
            + [pct(f) for f in ameaca.fracoes([ameaca.inicial(c) for c in grupo])],
            ["2 (o mago estourou área em 1)"]
            + [
                pct(f)
                for f in ameaca.fracoes([
                    ameaca.inicial(c) + (12 if c == "mago" else 4)
                    for c in grupo
                ])
            ],
            ["3 (e em 2 ele não fez nada)"]
            + [
                pct(f)
                for f in ameaca.fracoes([
                    ameaca.inicial(c) + (0 if c == "mago" else 4)
                    for c in grupo
                ])
            ],
        ],
    )
    L += [
        "O calor esfria sozinho, e é isso que a janela compra: sem ela a "
        "Fireball da rodada 1 travaria o mago no teto pelo resto da luta, "
        "porque nada do que viesse depois conseguiria mais mexer na razão.",
        "",
        "## Onde a conta mora",
        "",
        "Em `run_efeitos`, sem coluna nova: a chave de lá é "
        "`(run, passo, alvo, efeito)`, e a rodada entra no NOME do efeito "
        "(`ameaca_rodada:N`), porque a chave não tem coluna para ela. É o "
        "nome que faz a janela: quem lê pede o da rodada anterior, e só esse "
        "entra. A conta morre com a sala de graça, porque o `passo` faz parte "
        "da chave. A soma é um UPSERT dentro do banco, não em Python, porque "
        "dois jogadores clicando junto leriam o mesmo valor antes de qualquer "
        "um escrever.",
        "",
        "O campo é **separado** do que as habilidades somam. No mesmo campo, a "
        f"marca {E.MARCA_AMEACA} do painel — que quer dizer \"tem algo ligado chamando "
        "atenção\" — apareceria em todo mundo que já agiu, e deixaria de dizer "
        "nada.",
        "",
        "## Imunidade e alcance",
        "",
        "Um fator multiplica o **peso** já curvado, e não a ameaça crua. A "
        "curva é quase reta embaixo, então mexer na ameaça só daria \"modesto\" "
        "ou \"imune\", sem meio-termo. No peso o fator é um botão de verdade, e "
        "0 é imunidade de verdade (o Antilife Shell do druida).",
        "",
        "Quem tem fator hoje, e quanto do peso sobra:",
        "",
    ]
    L += lista([
        f"**{H.POR_ID[hid].nome}** — fator "
        f"{H.POR_ID[hid].acao['efeitos']['ameaca_fator']:g}"
        for hid in ("fly", "invisibility", "antilife_shell", "dimension_door")
        if hid in H.POR_ID
        and (H.POR_ID[hid].acao or {}).get("efeitos", {}).get("ameaca_fator")
        is not None
    ])
    L += [
        "## Uma escolha por vez da criatura",
        "",
        "A criatura sorteia o alvo **uma vez** e descarrega a vez inteira "
        "nele: três garras no mesmo peito. Sorteando por golpe, o multiataque "
        "virava uma máquina de espalhar dano — o tanque com 38% da atenção "
        "levava, em três garras, um golpe e meio, e a Ameaça prometia que a "
        "criatura ia **nele**. A promessa valia para o primeiro golpe só, e o "
        "resto diluía de volta para o uniforme.",
        "",
        "Se o alvo cai no meio da sequência, o resto vai para outro: não se "
        "bate em quem já está no chão, e o golpe não se perde por isso. "
        "Habilidade de área é outra coisa — ali os alvos são vários por "
        "definição, e saem de um sorteio sem reposição.",
        "",
        "Quem caiu e quem está atordoado saem do bolo antes da ameaça — "
        "atordoar duas vezes não faz nada.",
        "",
    ]
    return "\n".join(L + rodape(["src/ameaca.py", "src/motor.py"]))


# ============================================================ incursões e salas
def incursoes_e_salas() -> str:
    L = [
        "# Incursões e salas",
        "",
        "## A forma de uma incursão",
        "",
        "Uma incursão guarda a lore de abertura, a lore de fecho, o tamanho e "
        "a **sala final**. As salas do meio não são escritas nela: são "
        "sorteadas do banco da Organização quando a run começa, então duas "
        "runs da mesma incursão percorrem caminhos diferentes.",
        "",
    ]
    L += tabela(
        ["Tamanho", "Salas", "Paradas", "Descansos no caminho"],
        [
            [
                nome,
                str(passos),
                str(I.paradas_do_caminho(passos)),
                " e ".join(
                    f"a {parada}ª ({'fixo' if qual == I.DESCANSO_NORMAL else 'vigília'})"
                    for parada, qual in sorted(
                        I.DESCANSOS_DO_CAMINHO.get(passos, {}).items()
                    )
                ) or "nenhum",
            ]
            for nome, passos in I.TAMANHOS.items()
        ],
    )
    L += [
        "**Descanso é parada a mais, não sala a menos.** Uma Média tem as "
        "cinco salas dela e para uma vez para descansar, então são seis "
        "paradas; a Longa tem sete salas e nove paradas.",
        "",
        "As paradas de descanso **não são votadas como sala**: elas são fixas "
        "pelo tamanho da incursão, e a sala de Descanso do banco saiu do "
        "sorteio das opções. Ver `combate.md`.",
        "",
        f"A cada parada de sala o grupo vota entre **{I.OPCOES_POR_PASSO} salas** "
        "sorteadas do banco. **Não há prazo:** a run espera indefinidamente, "
        "mas não espera quem falta depois que o resultado já está decidido.",
        "",
        "A apuração, em ordem:",
        "",
        "",
    ]
    L += lista([
        "Uma opção com **mais da metade do grupo** fecha a votação na hora: "
        "não há por que esperar quem ainda não votou.",
        "Todos tendo votado sem maioria absoluta, **vale a mais votada**.",
        "Todos tendo votado com **empate**, ninguém avança: o bot pede que "
        "alguém troque o voto. Trocar é permitido a qualquer momento.",
        "Faltando voto e sem maioria ainda, espera — ainda dá para virar.",
    ])
    L += [
        f"As {len(I.ORGANIZACOES)} Organizações, cada uma com o seu banco de "
        "salas: " + ", ".join(I.ORGANIZACOES) + ".",
        "",
        "## Os tipos de sala",
        "",
    ]
    L += tabela(
        ["Tipo", "Pede teste de perícia?", "O que a falha custa"],
        [
            [tipo,
             "sim" if tipo in I.TIPOS_COM_TESTE else "não",
             motor.CONSEQUENCIA_FALHA.get(tipo, "—")]
            for tipo in I.TIPOS_SALA
        ],
    )
    L += [
        "## A CD de uma sala",
        "",
        "Três coisas num lugar só, e as três são regra do bot e não conteúdo:",
        "",
    ]
    L += lista([
        "A CD escrita no banco é a do tier 1.",
        "O tier soma o ajuste (ver `tier-e-progressao.md`).",
        f"**Armadilha ganha desconto de {I.DESCONTO_CD_ARMADILHA}.**",
    ])
    L += [
        "O desconto da Armadilha é de propósito: passar nela não dá nada, só "
        "evita o dano e o debuff. Sem o desconto ela nunca competiria na "
        "votação contra um Tesouro.",
        "",
        "Com o desconto **e** a regra de que vencer poupa o grupo, a "
        "Armadilha é a sala mais branda do caminho — e é para ser: ela é a "
        "única que não oferece nada em troca do risco.",
        "",
        "As faixas, e o que cada tipo de sala pode receber:",
        "",
    ]
    # Lido dos bancos de verdade, e não escrito aqui: assim a tabela diz o que
    # o conteúdo TEM, e muda sozinha quando uma sala for recalibrada.
    cds = cds_dos_bancos()
    faixas = sorted({cd for por_cd in cds.values() for cd in por_cd})
    L += tabela(
        ["Tipo de sala"] + [f"CD {cd}" for cd in faixas] + ["Total"],
        [
            [tipo]
            + [str(cds[tipo].get(cd, 0) or "—") for cd in faixas]
            + [str(sum(cds[tipo].values()))]
            for tipo in I.TIPOS_SALA if tipo in cds
        ]
        + [
            ["**Todas**"]
            + [f"**{sum(p.get(cd, 0) for p in cds.values())}**" for cd in faixas]
            + [f"**{sum(sum(p.values()) for p in cds.values())}**"]
        ],
    )
    L += [
        "São as salas escritas hoje nos "
        f"{len(I.ORGANIZACOES)} bancos, contadas por CD. As três faixas, "
        f"escritas no tier 1, são {', '.join(str(c) for c in faixas)}.",
        "",
        "A regra em uma linha, para quem escrever sala nova: **Armadilha nunca "
        "é difícil** (já tem desconto, e falhar ali custa dano, não "
        "recompensa) e **Tesouro nunca é fácil** (falhar custa o tesouro, que "
        "é o motivo de entrar). Evento fica no meio.",
        "",
        "## Como se passa numa sala",
        "",
        "Cada personagem rola **a melhor perícia que a sala aceita** — o bot "
        "escolhe, o jogador não precisa procurar.",
        "",
        "O que a sala pede não é um número de acertos: é um `alvo_progresso`, "
        "e o progresso é a **soma das margens**. A margem de uma rolagem é "
        "quanto ela passou da CD, e nunca é negativa:",
        "",
        "```",
        "margem = max(0, d20 + modificador + ajuda - CD)",
        "```",
        "",
        "Então falhar não subtrai, só não contribui — e passar com folga "
        "carrega quem falhou. É o que faz um grupo de cinco atravessar uma "
        "sala em que dois erraram.",
        "",
        "A sala para de aceitar rolagens quando o alvo é atingido **ou** "
        "quando todos já rolaram. Quem some não trava a run.",
        "",
        "Um personagem de fora pode somar na rolagem de outro depois do d20 — "
        "é o Flash of Genius do artífice, e ele entra tanto para passar quanto "
        "para a margem.",
        "",
        "## Combate",
        "",
        f"Uma sala de combate chama até **{I.MAX_INIMIGOS} criaturas por "
        f"tier** (`monstros_por_tier`), por nome do bestiário ou escritas na "
        "própria sala. A mesma sala serve incursões de tiers diferentes, e o "
        "que muda entre eles é QUEM mora nela — nada é multiplicado. Ver "
        "`combate.md`, `bestiario.md` e `tier-e-progressao.md`.",
        "",
        "## Vaga de incursão",
        "",
        f"Um jogador entra numa incursão a cada **{config.INTERVALO_SEMANAS} "
        f"semana(s)**, e a conta é feita **pela segunda-feira**, não por 7 "
        "dias corridos: quem entrou no sábado joga de novo na segunda, e a "
        "semana do grupo inteiro vira junto.",
        "",
        "É o mesmo dia em que a vitrine do mercado vira. Dois calendários no "
        "mesmo jogo seria pedir confusão.",
        "",
        f"O intervalo sai da variável de ambiente `INTERVALO_SEMANAS`; em 0 a "
        "entrada fica sempre liberada, que é o modo de teste.",
        "",
    ]
    return "\n".join(L + rodape(["src/incursoes.py", "src/motor.py", "src/mercado.py"]))


# ===================================================================== consequências
def consequencias_md() -> str:
    L = [
        "# Consequências: o que a sala faz com o grupo",
        "",
        "`src/consequencias.py` é módulo puro: ele **decide, não grava**. "
        "Devolve o nome da condição, o dano ou o prêmio, e quem chama (o cog) "
        "é que persiste — é o único que tem banco.",
        "",
        "## Por tipo de sala",
        "",
        "**A sala é do grupo, nos dois sentidos.** Vencida, não castiga "
        "ninguém — nem quem rolou mal. Perdida, castiga **todos que a "
        "encararam** — inclusive quem rolou bem. O dado de cada um decide o "
        "PROGRESSO da sala; o desfecho dela é do grupo.",
        "",
        "Quem encarou a sala é quem **rolou** nela. Uma sala só se perde "
        "quando todos os de pé rolaram — é a única forma de uma sala perdida "
        "fechar —, e quem está caído não encarou nada: cobrar de quem não "
        "pôde rolar seria cobrar duas vezes pela mesma queda.",
        "",
        "E é **um sorteio só para o grupo inteiro**: é uma armadilha que "
        "disparou, não cinco. O dano continua por cabeça, porque é "
        "porcentagem do máximo de cada um.",
        "",
        "### Armadilha",
        "",
    ]
    L += lista([
        "**Grupo venceu:** desarmada. Ninguém se machuca nela, nem quem "
        "falhou a própria rolagem.",
        f"**Grupo perdeu:** todos que rolaram levam **−{C.DANO_PCT}% do HP "
        "máximo** e o **mesmo** debuff de Armadilha, sorteado uma vez.",
    ])
    L += ["### Evento", ""]
    L += lista([
        f"**Grupo venceu:** um prêmio sorteado. Os {len(cond.BUFFS)} buffs do "
        f"catálogo são sempre candidatos — são o piso. A Cura "
        f"(+{C.CURA_PCT}% do HP) entra no bolo só se alguém estiver "
        f"machucado, e a {C.NOME_DA_GRACA} só se alguém carregar debuff: não "
        "faz sentido oferecer cura a um grupo inteiro nem perdão a um grupo "
        "limpo.",
        "**Grupo perdeu:** todos que rolaram pegam o **mesmo** castigo, "
        "sorteado uma vez: um debuff de Evento, ou um ponto de Exaustão.",
    ])
    L += [
        f"A {C.NOME_DA_GRACA} tira **um stack de um debuff de alguém** do "
        "grupo, sorteado entre todos. Ela não é condição: não tem stack nem "
        "prazo, acontece na hora.",
        "",
    ]
    L += ["### Tesouro", ""]
    L += lista([
        "**Grupo venceu:** o **texto de recompensa escrito na sala** — e não um item "
        "do mercado. Os itens de tesouro vivem na planilha do grupo, não no "
        "bot; a economia do bot é a do mercado (ver `mercado.md`).",
        "**Grupo perdeu:** não leva nada — e tem " + pct(C.CHANCE_DE_MIMICO, 0) + " de "
        "chance de acordar o que fingia ser um baú. Acordando, a sala vira "
        "combate em vez de devolver o grupo à votação, com uma linha por "
        "tier: "
        + "; ".join(
            f"**T{t}** "
            + " + ".join(f"{q} {nome}" for nome, q in elenco)
            for t, elenco in sorted(C.A_EMBOSCADA.items())
        )
        + f". O {C.NOME_DO_MIMICO} é CR 2 e satura — seis deles deixam 85% do "
        "HP de um grupo de tier 3 —, então do tier 3 para cima quem dá o peso "
        "é quem morava com o baú.",
    ])
    L += ["### Combate e Descanso", ""]
    L += lista([
        "**Combate** não tem teste de perícia: resolve na iniciativa. Quem "
        "cai sofre dano e fica fora do resto do combate.",
        "**Descanso** não tem como falhar: cura uma fatia e cada um limpa uma "
        "condição sua. Não é sorteado nem votado — é parada fixa do caminho. "
        "Ver `combate.md`.",
    ])
    L += [
        "## Os debuffs de cada fonte",
        "",
        "O sorteio não é do catálogo inteiro: cada fonte tem a lista dela.",
        "",
    ]
    L += tabela(
        ["Fonte", "Debuffs sorteáveis"],
        [
            ["Armadilha", ", ".join(
                cond.POR_ID[d].nome for d in cond.DEBUFFS_DE_ARMADILHA)],
            ["Evento", ", ".join(
                cond.POR_ID[d].nome for d in cond.DEBUFFS_DE_EVENTO)],
        ],
    )
    com_teto = [c for c in cond.CATALOGO if c.teto]
    L += [
        "## Sair da incursão",
        "",
        "Acumulando stacks até o **teto** de uma condição, o personagem sai da "
        "incursão. O teto é por condição, e só as que têm um tiram alguém:",
        "",
    ]
    L += lista([
        f"**{c.nome}** no {c.teto}º stack"
        + (f", que é {c.hp_maximo_pct * c.teto}% do HP máximo"
           if c.hp_maximo_pct else "")
        for c in com_teto
    ])
    L += [
        "As outras não tiram ninguém, por mais stacks que juntem. É a única "
        "coisa que tira alguém de uma run em andamento — **cair em combate "
        "não tira**. Esvaziando o grupo assim, a run fracassa.",
        "",
        "A ordem importa: quem chegou ao teto sai **antes** do decaimento do "
        "combate. Na outra ordem o decaimento tiraria justamente o stack que "
        "estourou.",
        "",
    ]
    return "\n".join(L + rodape(["src/consequencias.py", "src/condicoes.py"]))


# ========================================================================= condições
def condicoes_md() -> str:
    def efeitos_de(c) -> str:
        partes = []
        if c.ataque:
            partes.append(f"ataque {rules.fmt(c.ataque)}")
        if c.testes:
            partes.append(f"testes {rules.fmt(c.testes)}")
        if c.saves:
            partes.append(f"saves {rules.fmt(c.saves)}")
        if c.iniciativa:
            partes.append(f"iniciativa {rules.fmt(c.iniciativa)}")
        if c.hp_maximo_pct:
            partes.append(f"HP máximo {rules.fmt(c.hp_maximo_pct)}%")
        if c.cura_recebida_pct:
            partes.append(f"cura recebida {rules.fmt(c.cura_recebida_pct)}%")
        if c.pericias:
            partes.append(
                f"{rules.fmt(c.por_pericia)} em {', '.join(c.pericias)}")
        return "; ".join(partes) or "—"

    L = [
        "# Condições: os buffs e debuffs da incursão",
        "",
        "O que uma sala deixa no personagem. O catálogo é transcrição direta "
        "da planilha *Incursões — Buffs/Debuffs*: cada linha dela é um par "
        "espelhado (Benção/Perdição, Coragem/Medo…).",
        "",
        "**Não há escalonamento por tier.** O número escrito vale na faixa "
        "inteira.",
        "",
        "## Prazo",
        "",
        f"**Tudo decai 1 stack por combate**, menos as permanentes "
        f"({', '.join(cond.POR_ID[p].nome for p in cond.PERMANENTES)}), que "
        "ficam até o fim da incursão a não ser que o Descanso — ou uma "
        "habilidade — as tire.",
        "",
        "Os tetos: "
        + ", ".join(
            f"{c.nome} em {c.teto}"
            for c in cond.CATALOGO if c.teto
        )
        + ". O resto não tem teto.",
        "",
        f"## O catálogo ({len(cond.CATALOGO)} condições)",
        "",
        "Os valores são **o que um stack faz**, com o sinal já dentro.",
        "",
    ]
    # Os títulos saem dos tipos que o catálogo tem DE FATO, e não de uma
    # lista escrita aqui: a Exaustão tem tipo próprio, e com a lista fixa ela
    # ficava fora das tabelas enquanto a contagem do topo a incluía.
    TITULO = {"buff": "Buffs", "debuff": "Debuffs", "exaustao": "Exaustão"}
    vistos: list[str] = []
    for c in cond.CATALOGO:
        if c.tipo not in vistos:
            vistos.append(c.tipo)
    for tipo in vistos:
        doe = [c for c in cond.CATALOGO if c.tipo == tipo]
        L += [f"### {TITULO.get(tipo, tipo)} ({len(doe)})", ""]
        L += tabela(
            ["", "Condição", "O que um stack faz", "Fonte", "Decai", "Teto"],
            [
                [c.icone, c.nome, efeitos_de(c), c.fonte or "—",
                 "sim" if c.decai else "não",
                 str(c.teto) if c.teto else "—"]
                for c in doe
            ],
        )
        if tipo == "exaustao":
            L += [
                "A Exaustão é a única condição com tipo próprio, e merece: ela "
                "**não decai com o combate**. Sai no Descanso, ou numa "
                "habilidade que a tire.",
                "",
                "A coluna **Fonte** diz de qual sorteio ela sai, e não por "
                "quantos caminhos ela chega. A Exaustão é a condição com mais "
                "entradas no jogo: o sorteio do Evento perdido, o da Armadilha "
                "perdida, o golpe ou a habilidade de uma criatura que drena, e "
                "**voltar do chão por cura** — que cobra um ponto fixo, sem "
                "sorteio nenhum (ver `combate.md`).",
                "",
            ]
    com_teto = [c for c in cond.CATALOGO if c.teto]
    L += [
        "## O teto tira o personagem da incursão",
        "",
        "Chegar ao teto de uma condição **tira o personagem da run**, e só as "
        "que têm teto fazem isso:",
        "",
    ]
    L += lista([
        f"**{c.nome}** no {c.teto}º stack"
        + (f", que é {c.hp_maximo_pct * c.teto}% do HP máximo"
           if c.hp_maximo_pct else "")
        for c in com_teto
    ])
    L += [
        "Cair em combate **não** tira ninguém da incursão — isto tira. "
        "Esvaziando o grupo assim, a run fracassa.",
        "",
        "Quem chegou ao teto sai **antes** do decaimento do combate: na outra "
        "ordem, o decaimento tiraria justamente o stack que estourou.",
        "",
        "## Grupos de perícia",
        "",
        "Vários buffs e debuffs mexem num grupo de perícias, e não em uma:",
        "",
    ]
    L += tabela(
        ["Grupo", "Perícias"],
        [
            ["Saber", ", ".join(cond.G_SABER)],
            ["Atenção", ", ".join(cond.G_ATENCAO)],
            ["Social", ", ".join(cond.G_SOCIAL)],
            ["Agilidade", ", ".join(cond.G_AGILIDADE)],
            ["Atletismo", ", ".join(cond.G_ATLETISMO)],
        ],
    )
    return "\n".join(L + rodape(["src/condicoes.py"]))


# ====================================================================== habilidades
def forma_do_tier(cid: str, tier: int) -> str:
    """O que aquela classe ganha naquele tier, em duas palavras."""
    lista_ = H.HABILIDADES.get(cid, {}).get(tier) or []
    partes = []
    ativas = [h for h in lista_ if h.tipo == cl.ATIVA]
    passivas = [h for h in lista_ if h.tipo == cl.PASSIVA]
    escolhas = [h for h in lista_ if h.tipo == cl.ESCOLHA]
    if len(ativas) >= 3:
        partes.append(f"{len(ativas)} magias")
    elif ativas:
        partes.append(f"{len(ativas)} ativa" + ("s" if len(ativas) > 1 else ""))
    if passivas:
        partes.append(f"{len(passivas)} passiva" + ("s" if len(passivas) > 1 else ""))
    if escolhas:
        partes.append(f"{len(escolhas)} escolha" + ("s" if len(escolhas) > 1 else ""))
    return " + ".join(partes) or "—"


def usos(escopo: str) -> str:
    """Usos por masmorra Média daquele escopo, com vírgula decimal."""
    return num(balanco.POR_MASMORRA[escopo], 2)


def habilidades_md() -> str:
    por_escopo: dict[str, int] = {}
    ativas = passivas = escolhas = 0
    total = 0
    for tiers in H.HABILIDADES.values():
        for lista_ in tiers.values():
            for h in lista_:
                total += 1
                if h.tipo == cl.ATIVA:
                    ativas += 1
                    por_escopo[h.escopo] = por_escopo.get(h.escopo, 0) + 1
                elif h.tipo == cl.PASSIVA:
                    passivas += 1
                else:
                    escolhas += 1

    L = [
        "# Habilidades: a gramática do catálogo",
        "",
        f"{total} habilidades em {len(H.HABILIDADES)} classes: {passivas} "
        f"passivas, {ativas} ativas e {escolhas} escolhas. O conteúdo de cada "
        "uma está em `docs/FICHAS.md`; aqui está a regra de como elas "
        "funcionam.",
        "",
        "## A forma de cada classe",
        "",
        "Não há uma forma só, e a tabela é gerada do catálogo em vez de "
        "afirmada: as classes de magia ganham **três magias para escolher** "
        "nos tiers ímpares, e as marciais ganham uma habilidade por tier.",
        "",
    ]
    L += tabela(
        ["Classe"] + [f"T{t}" for t in range(1, rules.TIER_MAXIMO + 1)],
        [
            [cl.CLASSES[cid].nome]
            + [forma_do_tier(cid, tier) for tier in range(1, rules.TIER_MAXIMO + 1)]
            for cid in sorted(cl.CLASSES, key=lambda c: cl.CLASSES[c].nome)
        ],
    )
    L += [
        "\"escolha\" é o que destrava: ela não faz nada sozinha, e o que ela "
        "libera aparece como ativa ou passiva depois de o jogador decidir.",
        "",
        "## Os três tipos",
        "",
    ]
    L += lista([
        "**Passiva** — vale sempre, sem clicar. Entra num dicionário de "
        "efeitos que o motor lê.",
        "**Ativa** — o jogador aciona. Tem `usos`, dizendo quantas vezes e com "
        "que frequência zera.",
        "**Escolha** — não faz nada sozinha: destrava outra. "
        "`exige_escolha=(escolha, opção)` é o que prende uma ativa (ou outra "
        "escolha) atrás de uma decisão do jogador.",
    ])
    L += [
        "## Quando os usos zeram",
        "",
    ]
    L += tabela(
        ["Escopo", "Zera", "Ativas com ele", "Usos por masmorra Média"],
        [
            ["`combate`", "a cada sala de combate",
             str(por_escopo.get("combate", 0)), usos("combate")],
            ["`descanso`", "a cada sala de Descanso, e no começo da run",
             str(por_escopo.get("descanso", 0)), usos("descanso")],
            ["`incursao`", "uma vez por run",
             str(por_escopo.get("incursao", 0)), usos("incursao")],
        ],
    )
    vezes = balanco.POR_MASMORRA["combate"] / balanco.POR_MASMORRA["incursao"]
    L += [
        "Os números da direita vêm de `tools/balanco.py`, que é quem os mede — "
        "importados de lá, e não copiados, para os dois documentos não poderem "
        "discordar. É o que torna os escopos comparáveis: uma habilidade `por "
        "incursao` precisa bater **" + num(vezes) + "x mais forte** que uma `por "
        "combate` para valer o mesmo. Ver `docs/BALANCO.md`.",
        "",
        "## Como duas fontes do mesmo bônus se juntam",
        "",
        "A regra da casa é **`max()`**: duas fontes do mesmo bônus não "
        "empilham. Um anel de +2 de acerto e uma passiva de +2 dão +2, não +4.",
        "",
        "Três exceções, e cada uma tem motivo:",
        "",
    ]
    L += tabela(
        ["Chaves", "Como juntam", "Por quê"],
        [
            ["`" + "`, `".join(H.SOMAM) + "`", "**somam**",
             "com os dois em 10%, o Especialista do tier 4 não acrescentava "
             "nada a quem pegou o Curandeiro do tier 2 — uma escolha que não "
             "escolhe"],
            ["`" + "`, `".join(H.DADOS) + "`", "vale o de **maior média**",
             "são dados, e `max()` de string compararia alfabeticamente"],
            ["`critico_em`", "vale o **menor**",
             "critar com 19 é melhor que com 20"],
        ],
    )
    L += [
        "**Chave fora da lista conhecida é descartada em silêncio.** É a "
        "pegadinha do módulo: um efeito novo escrito com o nome errado "
        "simplesmente não acontece, sem erro nenhum. Por isso existem testes "
        "que varrem o catálogo inteiro conferindo os nomes — eles já "
        "pegaram três bugs reais que nenhum teste de comportamento pegava.",
        "",
        f"## As {len(H.NEUTRO)} chaves de efeito",
        "",
        "Um efeito com qualquer uma destas vale sozinho, sem código novo no "
        "cog:",
        "",
        "`" + "`, `".join(sorted(H.NEUTRO)) + "`",
        "",
        "## As ações",
        "",
        "A `acao` de uma ativa diz o que ela faz. O tipo escolhe o "
        "resolvedor:",
        "",
    ]
    L += tabela(
        ["Tipo", "O que é"],
        [
            ["`golpes`", "bate, como o ataque da rodada (é o padrão)"],
            ["`save`", "o alvo rola resistência; `alvos: \"todos\"` é área, "
                       "`metade: true` reduz no sucesso"],
            ["`cura`", "devolve HP, sempre em porcentagem do máximo"],
            ["`grupo`", "buff ou cura no grupo inteiro"],
            ["`duracao`", "liga um efeito com prazo em rodadas"],
            ["`invocar`", "traz um aliado, que entra como combatente comum e "
                          "age na vez dele"],
            ["`forma`", "veste o corpo de outro bicho (Wild Shape, Polymorph)"],
        ],
    )
    L += [
        "## Uma regra que o catálogo não garante sozinho",
        "",
        "**Todo dado que a habilidade rola tem de estar escrito no texto "
        "dela.** Mudar o dado na `acao` e esquecer o texto passa por toda a "
        "suíte, porque a mecânica fica certa e só a promessa ao jogador é que "
        "mente — aconteceu com o Cone of Cold, em quatro lugares. Há um "
        "conferidor para isso em `tests/test_habilidades.py`.",
        "",
    ]
    return "\n".join(L + rodape(["src/habilidades.py", "src/classes.py"]))


# ========================================================================== mercado
def mercado_md() -> str:
    L = [
        "# Mercado",
        "",
        "**Este é o segundo sistema de patrimônio do grupo, e não o mesmo.** A "
        "planilha do Google guarda o que os personagens carregam na campanha; "
        "isto aqui é a economia das Incursões, que começa de zero e vive "
        "dentro do bot. Os dois não se falam, de propósito.",
        "",
        "## O ouro",
        "",
    ]
    L += tabela(
        ["De onde vem", "Quanto", "Quem paga"],
        [
            ["Cada sala superada", f"{mercado.OURO_POR_SALA} × tier",
             "conclusão **e** desistência"],
            ["Sala de **Combate** do caminho",
             f"{mercado.OURO_POR_SALA * mercado.PESO_DO_COMBATE} × tier "
             f"({mercado.PESO_DO_COMBATE}× uma sala)",
             "conclusão **e** desistência"],
            ["Concluir a incursão", f"{mercado.OURO_POR_INCURSAO} × tier",
             "só a conclusão"],
        ],
    )
    L += [
        "**A sala de Combate paga dobrado**, e isso é regra de desenho: ela é "
        "a única que cobra HP, e o HP não volta entre salas. Enquanto ela "
        "pagava igual à de Tesouro, desviar do combate era sempre a jogada "
        "certa — e era isso que a mesa fazia, de propósito, para chegar "
        "inteira ao objetivo. O objetivo fica fora da dobra: ele não é "
        "escolha de ninguém, e quem paga por ele é o bônus de conclusão. O "
        "Tesouro que virou emboscada de Mímico também fica fora — a emboscada "
        "é castigo por falhar no baú.",
        "",
    ]
    L += [
        "**A incursão paga uma vez, no fim.** As salas do caminho não pagam "
        "por si: elas ficam registradas, e o fecho conta quantas foram "
        "superadas. O que muda é qual fecho paga o quê:",
        "",
    ]
    L += lista([
        "**Concluída:** paga as salas superadas **e** o bônus de ter "
        "fechado.",
        "**Abandonada** pelo grupo: paga as salas superadas; o bônus do "
        "fecho fica para trás, e os MEs também. O grupo atravessou o que "
        "atravessou — o que ele não fez foi terminar.",
        "**Fracassada**, com o grupo inteiro no chão: não paga nada, nem o "
        "das salas já atravessadas.",
    ])
    L += [
        "Desistir paga mais que cair, então: é a diferença entre voltar e "
        "ser carregado de volta.",
        "",
        "**Recebe todo mundo que passou pela run**, e não só quem estava de "
        "pé no fim: quem caiu no objetivo e quem foi ejetado por Exaustão no "
        "meio do caminho jogaram a incursão e levam o mesmo que os outros. "
        "Fica de fora quem desistiu **antes** de ela começar.",
        "",
        "Escala por tier porque os preços não escalam: um item lendário custa "
        f"{itens.PRECO_BASE['lendario']} em qualquer tier, e é o ouro que "
        "chega mais rápido lá em cima.",
        "",
        "## A vitrine",
        "",
        f"**{mercado.VAGAS} itens, por personagem, por semana.** Vira na "
        "**segunda-feira**, o mesmo dia da vaga de incursão.",
        "",
        "Nada disso é guardado: a prateleira é **derivada** de (personagem, "
        "semana) por um sorteio semeado. É a mesma escolha que a ficha já faz "
        "ao derivar CA e dano da classe em vez de gravá-los — o que é derivado "
        "não envelhece. Em troca, o bot não precisa de tabela de estoque, nem "
        "de rotina em segundo plano para repor a loja, nem de quem lembre de "
        "rodá-la.",
        "",
        "É **por personagem**: dois jogadores na mesma semana veem vitrines "
        "diferentes.",
        "",
        "## Raridade e preço",
        "",
    ]
    L += tabela(
        ["Raridade", "Preço", "Peso no sorteio"],
        [
            [itens.NOME_DA_RARIDADE[r], str(itens.PRECO_BASE[r]),
             pct(itens.PESO_NA_VITRINE[r] / sum(itens.PESO_NA_VITRINE.values()), 0)]
            for r in itens.RARIDADES
        ],
    )
    L += [
        "O peso é a fatia do sorteio de **uma** vaga. A prateleira é sorteada "
        f"sem repetição nas {mercado.VAGAS} vagas, então a proporção que "
        "aparece numa vitrine não é exatamente essa — é para lá que ela "
        "tende.",
        "",
        "## Os slots",
        "",
        f"**Cada slot manda num número só.** É daí que vem a contenção: não "
        f"existe regra de teto nem limite a conferir em tempo de execução — o "
        f"slot já impede empilhar cinco fontes do mesmo bônus, porque só cabe "
        f"uma armadura. Equipar um tira o que estava no lugar.",
        "",
    ]
    L += tabela(
        ["Slot", "Domina", "Itens no catálogo"],
        [
            [itens.NOME_DO_SLOT[s],
             "`" + "`, `".join(itens.DOMINIO[s]) + "`",
             str(len([i for i in itens.CATALOGO if i.slot == s]))]
            for s in itens.SLOTS
        ],
    )
    L += [
        "`DOMINIO` não é comentário: um teste varre o catálogo e reprova o "
        "item que escapar do domínio do slot dele. Sem isso o domínio seria "
        "uma intenção — e ele já pegou dois itens errados.",
        "",
        "## O que não está à venda",
        "",
        f"`itens.SEM_VITRINE` guarda "
        + (
            "uma peça que EXISTE mas nunca entra"
            if len(itens.SEM_VITRINE) == 1
            else f"{len(itens.SEM_VITRINE)} peças que EXISTEM mas nunca entram"
        )
        + " num sorteio. O bolo da vitrine sai de "
        "`CATALOGO` e `esta_na_vitrine` é quem autoriza a compra, então ficar "
        "de fora do catálogo já fecha as duas portas — não há checagem em "
        "tempo de execução a manter. O domínio dos slots também não vale "
        "para elas: a contenção existe para a economia do mercado, e uma peça "
        "que não é vendida não disputa nada.",
        "",
    ]
    L += tabela(
        ["Peça", "Slot", "O que faz", "Como chega"],
        [
            [p.nome, itens.NOME_DO_SLOT[p.slot],
             ", ".join(f"`{k}` {v}" for k, v in sorted(p.efeito.items())),
             "`/mercado anel_do_mestre` (admin)"]
            for p in itens.SEM_VITRINE
        ],
    )
    L += [
        "O Anel do Mestre é ferramenta de mesa: serve para atravessar uma "
        "incursão **sozinho** e ver as telas, as salas e o chefe funcionando "
        "sem juntar cinco pessoas. `tools/medir_anel_do_gm.py` mede se os "
        "números dele bastam para isso, com o motor de verdade.",
        "",
        "## As poções",
        "",
        f"Prateleira própria, de **{consumiveis.VAGAS} vagas**: as "
        f"{len(consumiveis.FIXAS)} de vida estão **sempre** em cartaz, e a "
        "terceira é sorteada por semana e por personagem, como a de "
        "equipamento. São "
        f"{len(consumiveis.CATALOGO)} poções no catálogo.",
        "",
        f"**Até {consumiveis.TETO_NA_BOLSA} de cada tipo na bolsa.** É a "
        "contenção delas, no lugar do slot: o equipamento é único por "
        "personagem porque o slot impede o stack, e a poção empilha — sem um "
        "teto, ouro guardado viraria estoque e a incursão longa deixaria de "
        "cobrar o HP que ela cobra.",
        "",
        "**Beber é a ação da rodada**: quem bebe não ataca. A única exceção é "
        "a Poção da Aceleração, que não custa a ação — é disso que ela vive, "
        "e não do número de golpes.",
        "",
    ]
    L += tabela(
        ["Família", "O que faz", "X", "Preço", "Gasta a ação"],
        [
            [
                consumiveis.NOME_DA_FAMILIA[f],
                consumiveis.RESUMO_DA_FAMILIA[f],
                " · ".join(str(x) for x in consumiveis.niveis_da_familia(f)) or "—",
                " · ".join(str(p) for p in consumiveis.precos_da_familia(f)),
                "não" if not consumiveis.da_familia(f)[0].gasta_turno else "sim",
            ]
            for f in consumiveis.FAMILIAS
        ],
    )
    L += [
        f"As de prazo (Aceleração, Resistência, Dano) valem "
        f"**{consumiveis.TURNOS} turnos**, e beber a segunda da mesma família "
        "renova a primeira em vez de somar com ela — o efeito é gravado pela "
        "família, como as habilidades.",
        "",
    ]
    L += [
        "O sorteio da vaga que sobra é **por família** e só depois por poção. "
        f"As {len(consumiveis.da_familia(consumiveis.BUFF))} de buff são três "
        "quartos do catálogo: sorteando direto, três de cada quatro semanas "
        "trariam buff e a de Mana apareceria uma vez por ano.",
        "",
        "A de buff empilha uma condição da tabela de buffs (`condicoes.md`), "
        "e o nível são os **stacks** — então o prazo dela é o da tabela, que "
        "decai 1 por combate, e não os "
        f"{consumiveis.TURNOS} turnos das outras. A de Mana devolve um uso "
        "**já gasto** de uma habilidade daquele tier, escolhida por quem "
        "bebe; sem nada gasto, ela não é bebida.",
        "",
    ]
    return "\n".join(
        L + rodape(["src/mercado.py", "src/itens.py", "src/consumiveis.py"])
    )


# ======================================================================== bestiário
def bestiario_md() -> str:
    criaturas = bestiario.carregar()
    L = [
        "# Bestiário",
        "",
        f"{len(criaturas)} criaturas prontas que uma sala pode chamar **só "
        "pelo nome**: a sala que diz apenas \"Lobo\" recebe os números do "
        "livro no lugar das colunas vazias.",
        "",
        "O arquivo `data/bestiario.json` sai de "
        "`tools/importar_bestiario.py`, que lê o Monster Manual no formato do "
        "5etools e padroniza o que o bot entende. Cada entrada já vem no "
        "formato que a sala lê.",
        "",
        "## A busca",
        "",
        "Aceita o nome em português e o original em inglês, com ou sem acento.",
        "",
        "## O que vem de cada criatura",
        "",
    ]
    L += lista([
        "CA, HP e os golpes (nome, ataque, dano)",
        "os saves escritos — e quando faltam, o bot deduz de "
        f"`ataque − {motor.DEFASAGEM_DE_SAVE}`",
        "o CR, que é como o `BALANCO.md` escolhe a criatura típica de cada "
        "tier",
    ])
    L += [
        "**Os números valem como estão escritos.** Nada é multiplicado por "
        "tier: a criatura de 52 HP tem 52 HP em qualquer incursão, e o tier "
        "está em QUEM a sala chama (ver `tier-e-progressao.md`).",
        "",
        "**As fichas em si estão em [../CRIATURAS.md](../CRIATURAS.md)**: as "
        "criaturas uma por uma, com CA, HP, golpes por rodada e habilidade, "
        "agrupadas pela faixa de CR que decide qual tier as encontra. Aqui "
        "está a regra; lá está o conteúdo.",
        "",
    ]
    return "\n".join(L + rodape(["src/bestiario.py", "data/bestiario.json"]))


# =========================================================================== índice
ARQUIVOS = [
    ("tier-e-progressao.md", tier_e_progressao,
     "Níveis, tiers, e tudo que escala com eles: CD de sala e tamanho de criatura."),
    ("combate.md", combate,
     "Iniciativa, ataque, crítico, THP, cair, descanso e a regra da cura."),
    ("ameaca.md", ameaca_md,
     "Quem a criatura escolhe bater: a inicial da classe, o que cada ação gera e a curva."),
    ("incursoes-e-salas.md", incursoes_e_salas,
     "A forma de uma incursão, os tipos de sala, as faixas de CD e a votação."),
    ("consequencias.md", consequencias_md,
     "O que cada tipo de sala faz com o grupo quando ele passa ou falha."),
    ("condicoes.md", condicoes_md,
     "O catálogo de buffs e debuffs, o que um stack faz e quanto tempo dura."),
    ("habilidades.md", habilidades_md,
     "A gramática do catálogo: tipos, usos, escopos e como dois bônus se juntam."),
    ("mercado.md", mercado_md,
     "Ouro, vitrine semanal derivada, raridade, preço e o domínio de cada slot."),
    ("bestiario.md", bestiario_md,
     "As criaturas prontas que uma sala chama pelo nome."),
]


def indice() -> str:
    L = [
        "# Mecânicas",
        "",
        "Um arquivo por mecânica. Tudo aqui é **gerado**:",
        "",
        "```bash",
        ".venv/Scripts/python.exe tools/gerar_mecanicas_md.py",
        "```",
        "",
        "Os números saem dos módulos que os usam de verdade, então mexer numa "
        "constante e rodar o gerador atualiza a documentação na hora. Não "
        "edite estes arquivos à mão — a edição se perde, e pior, ela passa a "
        "discordar do código sem ninguém notar.",
        "",
    ]
    L += tabela(
        ["Arquivo", "O que cobre"],
        [[f"[{nome}]({nome})", desc] for nome, _, desc in ARQUIVOS],
    )
    L += [
        "## Os outros dois documentos",
        "",
    ]
    L += lista([
        "**[../FICHAS.md](../FICHAS.md)** — o conteúdo: os números e as "
        "habilidades de cada uma das 14 classes, tier por tier.",
        "**[../BALANCO.md](../BALANCO.md)** — a medição: dano por rodada, "
        "durabilidade, cura e valor de cada habilidade, para achar o que "
        "está forte ou fraco demais.",
    ])
    L += [
        "A divisão: aqui estão as **regras**, no `FICHAS.md` o **conteúdo** e "
        "no `BALANCO.md` a **medição**.",
        "",
    ]
    return "\n".join(L)


def main() -> None:
    PASTA.mkdir(parents=True, exist_ok=True)
    (PASTA / "README.md").write_text(indice(), encoding="utf-8")
    print(f"{PASTA.relative_to(RAIZ)}/README.md")
    for nome, funcao, _ in ARQUIVOS:
        texto = funcao()
        (PASTA / nome).write_text(texto, encoding="utf-8")
        linhas = texto.count("\n") + 1
        print(f"{PASTA.relative_to(RAIZ)}/{nome}: {linhas} linhas")


if __name__ == "__main__":
    main()
