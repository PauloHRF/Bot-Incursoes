"""Escreve docs/FICHAS.md: as fichas das classes, tier por tier.

É o documento de CRIAÇÃO DE FICHA do grupo, mas gerado do código em vez de
mantido à mão. Um documento escrito à mão desatualiza no primeiro tier que
alguém mexer, e ninguém percebe; este refaz tudo com um comando:

    .venv/Scripts/python.exe tools/gerar_fichas_md.py

Tudo que sai daqui vem de src/classes.py, src/habilidades.py e src/ameaca.py.
Para mudar o documento, mude a classe — não o arquivo gerado.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import ameaca, classes as cl  # noqa: E402
from src.rules import ATRIBUTOS  # noqa: E402

SAIDA = RAIZ / "docs" / "FICHAS.md"

# Os textos do catálogo são escritos sem acento de propósito — eles saem no
# Discord, em log e em painel, e o bot roda no Windows. Aqui eles viram texto
# de documento, então os acentos voltam. É substituição palavra por palavra,
# nunca por pedaço: trocar 'ca' dentro de 'ataca' estragaria mais do que
# arruma. Palavra que não está na tabela sai como está no código.
ACENTOS = {
    "Alquimica": "Alquímica", "Atuacao": "Atuação", "Bardica": "Bárdica",
    "Cacador": "Caçador", "Cancao": "Canção", "Cantico": "Cântico",
    "Critico": "Crítico", "Dadiva": "Dádiva", "Danca": "Dança",
    "Dominio": "Domínio", "Espirito": "Espírito", "Evocacao": "Evocação",
    "Expansao": "Expansão", "Genio": "Gênio", "Grilhoes": "Grilhões",
    "Guardiao": "Guardião", "Historia": "História", "Infusao": "Infusão",
    "Inspiracao": "Inspiração", "Intimidacao": "Intimidação",
    "Intuicao": "Intuição", "Investigacao": "Investigação",
    "Lider": "Líder", "Maos": "Mãos", "Municao": "Munição",
    "NAO": "NÃO", "Nao": "Não", "Percepcao": "Percepção",
    "Persuasao": "Persuasão", "Precisao": "Precisão",
    "Pressagio": "Presságio", "Proficiencia": "Proficiência",
    "Religiao": "Religião", "Repertorio": "Repertório",
    "Restauracao": "Restauração", "Sintonizacao": "Sintonização",
    "Lanca": "Lança",
    "So": "Só", "Sobrevivencia": "Sobrevivência", "Tradicao": "Tradição",
    "Tres": "Três", "VOCE": "VOCÊ",
    "abencoados": "abençoados", "alguem": "alguém", "ameaca": "ameaça",
    "ancioes": "anciões", "ate": "até", "atencao": "atenção",
    "automatico": "automático", "feitico": "feitiço",
    "bonus": "bônus", "circulo": "círculo", "critico": "crítico",
    "danca": "dança", "demonio": "demônio", "dominio": "domínio",
    "espirito": "espírito", "incursao": "incursão",
    "ja": "já", "lanca": "lança", "maximo": "máximo", "nao": "não",
    "ninguem": "ninguém",
    "pericia": "perícia", "pericias": "perícias",
    "proficiencia": "proficiência", "proprias": "próprias",
    "proprio": "próprio", "proxima": "próxima", "proximas": "próximas",
    "proximo": "próximo", "proximos": "próximos",
    "resistencia": "resistência", "so": "só", "temporaria": "temporária",
    "totemica": "totêmica", "tres": "três", "voce": "você",
    "xamanica": "xamânica",
}

# Frases que uma tabela de palavras não alcança, porque o acento cai num
# verbo colado por hífen ou numa crase.
FRASES = {
    "mira-lo": "mirá-lo",
    "alcanca-lo": "alcançá-lo",
    "da +1": "dá +1",
    "da a ele": "dá a ele",
    "da ao": "dá ao",
    "da +4": "dá +4",
    "esta na forma": "está na forma",
    # Ordinal: o catálogo escreve '1o circulo' porque sai no Discord.
    "1o ": "1º ", "2o ": "2º ", "3o ": "3º ", "4o ": "4º ", "5o ": "5º ",
}

_PALAVRA = re.compile(r"[A-Za-z']+")

ESCOPOS = {"combate": "combate", "descanso": "descanso", "incursao": "incursão"}
ROTULOS = {cl.PASSIVA: "Passiva", cl.ATIVA: "Ativa", cl.ESCOLHA: "Escolha"}


def acentuar(texto: str) -> str:
    """Devolve o texto do catálogo com os acentos que o código não carrega."""
    saida = _PALAVRA.sub(lambda m: ACENTOS.get(m.group(0), m.group(0)), texto or "")
    for crua, boa in FRASES.items():
        saida = saida.replace(crua, boa)
    return saida


def usos_de(habilidade) -> str:
    """'3x por descanso', ou vazio para quem não gasta recurso."""
    if not habilidade.usos:
        return ""
    escopo = ESCOPOS.get(habilidade.escopo, habilidade.escopo)
    return f"{habilidade.vezes}x por {escopo}"


def sem_prefixo_de_uso(texto: str) -> str:
    """Tira o '1x por descanso:' do início do texto — ele já vai no cabeçalho."""
    return re.sub(r"^\d+x por \w+:\s*", "", texto or "").strip()


def frase(texto: str) -> str:
    """Começa com maiúscula. Tirar o prefixo de uso deixa a frase minúscula."""
    limpo = (texto or "").strip()
    return limpo[:1].upper() + limpo[1:] if limpo else limpo


def premios_da_escolha(classe: cl.Classe, escolha) -> dict[str, object]:
    """A habilidade que cada opção destrava, por id de opção."""
    return {
        h.exige_escolha[1]: h
        for lista in classe.habilidades.values()
        for h in lista
        if h.exige_escolha and h.exige_escolha[0] == escolha.id
    }


def linhas_da_opcao(classe: cl.Classe, escolha, opcao: dict) -> list[str]:
    """Uma opção de escolha: o nome, o que ela custa e o que ela faz.

    O texto bom é o da habilidade destravada, quando existe — a opção só traz
    um resumo de menu. Opção que soma número não destrava nada, e aí o resumo
    dela é tudo que há.
    """
    premio = premios_da_escolha(classe, escolha).get(opcao["id"])
    if premio is None:
        return [f"* **{acentuar(opcao['nome'])}** — {acentuar(opcao['texto'])}"]
    if premio.tipo == cl.ESCOLHA:
        # Escolha encadeada (o Taumaturgo do clérigo): o prêmio é outra
        # pergunta. Quem lê a ficha quer o nome da OPÇÃO, não o da pergunta.
        return [
            f"* **{acentuar(opcao['nome'])}** — {acentuar(opcao['texto'])}; "
            "abre uma segunda escolha"
        ]
    uso = usos_de(premio)
    cabeca = f"* **{acentuar(premio.nome)}**"
    if uso:
        cabeca += f" ({uso})"
    return [f"{cabeca} — {acentuar(sem_prefixo_de_uso(premio.texto))}"]


def bloco_da_habilidade(
    classe: cl.Classe, habilidade, divididos: set[str] = frozenset()
) -> list[str]:
    """O título e o corpo de uma habilidade, no formato do documento.

    `divididos` são as chaves de uso que mais de uma habilidade do tier
    compartilha — as duas tradições do xamã, as duas metades do Arcane Jolt.
    Sem o aviso, o documento diria '1x por descanso' duas vezes e o jogador
    leria dois usos onde há um.
    """
    rotulo = ROTULOS.get(habilidade.tipo, habilidade.tipo)
    uso = usos_de(habilidade)
    titulo = f"### **{rotulo} — {acentuar(habilidade.nome)}**"
    linhas = [titulo, ""]
    if uso:
        aviso = (
            " O uso é o mesmo das outras opções deste tier: escolhe uma."
            if habilidade.chave_de_uso in divididos
            else ""
        )
        linhas += [f"**{uso}.**{aviso}", ""]
    linhas += [frase(acentuar(sem_prefixo_de_uso(habilidade.texto))), ""]
    if habilidade.decidivel:
        forma = habilidade.escolha
        if forma["tipo"] == "pericias":
            entre = "com proficiência" if forma["entre"] == "proficientes" else "quaisquer"
            aplica = "dobra o bônus" if forma["aplica"] == "expertise" else "dá proficiência"
            linhas += [
                f"Escolhe {forma['quantidade']} perícias {entre}; {aplica}.",
                "",
            ]
        else:
            for opcao in forma["opcoes"]:
                linhas += linhas_da_opcao(classe, habilidade, opcao)
            linhas.append("")
    return linhas


def bloco_do_tier(classe: cl.Classe, tier: int) -> list[str]:
    """Os números daquele tier, e as habilidades que entram nele."""
    n = classe.tiers[tier]
    linhas = [
        f"## **Tier {tier}**",
        "",
        f"**HP:** {n.hp}  ",
        f"**AC:** {n.ca}  ",
        f"**Skills:** {n.pericias}  ",
        f"**Bônus de Skills:** +{n.bonus_pericia} / +{n.bonus_proficiencia} com Prof.  ",
        f"**Acerto:** +{n.acerto}  ",
        f"**Dano:** {n.dano}",
        "",
    ]
    # Só o que ENTRA neste tier, e nunca o prêmio de uma escolha: ele aparece
    # como opção dentro dela, que é onde o jogador o encontra.
    proprias = [
        h for h in classe.habilidades_do_tier(tier) if not h.exige_escolha
    ]
    chaves = [h.chave_de_uso for h in proprias if h.usos]
    divididos = {c for c in chaves if chaves.count(c) > 1}
    for habilidade in proprias:
        linhas += bloco_da_habilidade(classe, habilidade, divididos)
    linhas += ["---", ""]
    return linhas


def bloco_da_classe(classe: cl.Classe) -> list[str]:
    """Uma classe inteira: o cabeçalho de identidade e os cinco tiers."""
    fortes = cl.saves_fortes(classe.id)
    nomes = " e ".join(ATRIBUTOS.get(s, s) for s in fortes) or "nenhum"
    primeiro, ultimo = classe.tiers[1], classe.tiers[5]
    passo = (ultimo.hp - primeiro.hp) / 4
    passo_texto = f"{passo:g}".replace(".", ",")
    linhas = [
        f"# **{classe.nome.upper()}**",
        "",
        f"*{acentuar(classe.resumo)}*",
        "",
        f"**Vida:** {primeiro.hp} a {ultimo.hp}, +{passo_texto} por tier  ",
        f"**Saves fortes:** {nomes}  ",
        f"**Ameaça inicial:** {ameaca.inicial(classe.id)} — "
        "o peso dele no sorteio de alvo das criaturas",
        "",
        "---",
        "",
    ]
    for tier in range(1, 6):
        linhas += bloco_do_tier(classe, tier)
    return linhas


def cabecalho() -> list[str]:
    """A abertura do documento, e o índice."""
    linhas = [
        "## CRIAÇÃO DE FICHA — as fichas padrão das classes",
        "",
        "O cadastro é **Nome → Classe → Skills**: cada classe tem um número",
        "pré-definido de skills, habilidades, acerto, CA e dano, que sobem",
        "de tier em tier. Um tier são dois níveis, e o teto é o nível 10.",
        "",
        "**Este arquivo é gerado.** Ele sai de `src/classes.py`,",
        "`src/habilidades.py` e `src/ameaca.py`, que são o que o bot executa de",
        "verdade — então o que está aqui é o que acontece na mesa, não o que foi",
        "combinado e esquecido. Para mudar uma ficha, mude a classe e rode:",
        "",
        "```",
        ".venv/Scripts/python.exe tools/gerar_fichas_md.py",
        "```",
        "",
        "Nos tiers 1, 3 e 5 das classes novas o jogador decide entre três",
        "opções, e a escolhida é uma ativa que ele aciona; nos tiers 2 e 4 a",
        "habilidade entra sozinha na conta. As seis primeiras classes vêm de",
        "antes dessa regra e não a seguem.",
        "",
        "### As classes",
        "",
    ]
    for classe in cl.CLASSES.values():
        linhas.append(f"* [{classe.nome}](#{classe.nome.lower()})")
    linhas += ["", "---", ""]
    return linhas


def documento() -> str:
    linhas = cabecalho()
    for classe in cl.CLASSES.values():
        linhas += bloco_da_classe(classe)
    return "\n".join(linhas).rstrip() + "\n"


def main() -> int:
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(documento(), encoding="utf-8")
    quantas = sum(
        1
        for c in cl.CLASSES.values()
        for lista in c.habilidades.values()
        for _h in lista
    )
    print(f"{SAIDA.relative_to(RAIZ)}: {len(cl.CLASSES)} classes, {quantas} habilidades")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
