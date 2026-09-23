"""Gera a planilha do banco de salas de uma Organização, já preenchida.

    python tools/gerar_modelo_banco.py "Vórtice Oculto"
    python tools/gerar_modelo_banco.py "Vórtice Oculto" minha_planilha.xlsx

O banco alimenta o sorteio: a cada passo da run o bot tira 3 salas daqui e o
grupo vota numa. Quanto mais salas, menos repetição entre runs.
"""
from __future__ import annotations

import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.incursoes import (  # noqa: E402
    OPCOES_POR_PASSO,
    ORGANIZACOES,
    TIPOS_SALA,
    arquivo_da_organizacao,
)
from src.rules import ATRIBUTOS, PERICIAS  # noqa: E402

FONTE = "Arial"
cab_fonte = Font(name=FONTE, size=10, bold=True, color="FFFFFF")
cab_fill = PatternFill("solid", fgColor="2F3B52")
corpo = Font(name=FONTE, size=10)
corpo_bold = Font(name=FONTE, size=10, bold=True)
calculado = Font(name=FONTE, size=10, color="808080", italic=True)
fill_calculado = PatternFill("solid", fgColor="F2F2F2")
borda = Border(*[Side(style="thin", color="D0D0D0")] * 4)
topo = Alignment(vertical="top", wrap_text=True)

CABECALHOS = [
    ("sala_id", 10, "Identificador único da sala dentro deste banco."),
    ("nome", 26, "Nome da sala mostrado no embed."),
    ("tipo", 14, "Combate, Descanso, Armadilha, Evento ou Tesouro."),
    ("dificuldade", 13, "Fácil, Média ou Difícil. Vazio em Descanso e Combate."),
    ("cd", 7, "CALCULADO a partir da dificuldade (aba Dificuldades)."),
    ("alvo_progresso", 15, "CALCULADO: soma de margens que o grupo precisa atingir."),
    ("pericias", 30, "Perícias aceitas, separadas por ';'. Vazio em Descanso e Combate."),
    ("descricao", 62, "Texto do embed da sala."),
    ("imagem", 26, "Caminho em assets/ ou URL da imagem da sala."),
    ("monstro_nome", 22, "Só em salas de Combate. Criatura com multiataque, saves ou "
     "habilidade vai na aba 'Monstros', que tem todas as colunas."),
    ("monstro_quantidade", 12, "Quantas criaturas iguais. Vazio ou 1 = uma. Máximo 6 por sala, "
     "contando as da aba 'Monstros'."),
    ("monstro_ca", 11, "Classe de Armadura do monstro."),
    ("monstro_ataque", 15, "Bônus de ataque do monstro (ex.: 6)."),
    ("monstro_dano", 14, "Dado de dano do monstro (ex.: 2d6+3)."),
    ("monstro_hp", 11, "Pontos de vida do monstro."),
    ("recompensa", 32, "Bônus da sala (texto livre). Opcional."),
    ("pontos_organizacao", 18, "Pontos de Organizacao se a sala for superada. 0 ou vazio = nenhum."),
]

# Banco de exemplo do Vórtice Oculto: 12 salas, variadas o bastante para uma
# run longa (7 passos x 3 opções) não repetir quase nada.
SALAS = [
    ("VO01", "Portal Instável", "Armadilha", "Média", "Acrobacia; Arcanismo",
     "Um arco de pedra pulsa e, a cada batida, cospe estilhaços de realidade pelo corredor. "
     "Passar exige ler o ritmo — ou ser muito rápido.",
     "", "", "", "", "", "", "Um fragmento de selo para quem passa ileso.", 1),
    ("VO02", "Biblioteca Submersa", "Evento", "Média", "Investigação; Arcanismo; História",
     "Água escura cobre as prateleiras até a altura do peito. Os livros que boiam ainda estão "
     "secos, e isso é o mais perturbador da sala.",
     "", "", "", "", "", "", "Revela a CA do próximo inimigo.", 2),
    ("VO03", "Sentinelas de Pedra", "Combate", "", "",
     "Duas estátuas ladeiam a porta interna. Elas não se mexem enquanto ninguém olha para o "
     "que carregam — e o que carregam é o que o grupo veio buscar.",
     "", "Sentinela de Basalto", 14, 5, "1d10+3", 26, "", 1),
    ("VO04", "Corredor dos Ecos", "Armadilha", "Difícil", "Percepção; Acrobacia; Furtividade",
     "Cada passo volta multiplicado, e junto com o eco vem alguma coisa que anda no "
     "contratempo. O chão é feito de placas que afundam sob peso.",
     "", "", "", "", "", "", "", 1),
    ("VO05", "Acampamento Abandonado", "Descanso", "", "",
     "Uma expedição anterior montou barraca aqui e não voltou. As brasas ainda estão mornas, "
     "a comida intacta. O grupo descansa — desconfiado, mas descansa.",
     "", "", "", "", "", "", "O grupo recupera o fôlego.", 0),
    ("VO06", "Cofre Selado", "Tesouro", "Média", "Prestidigitação; Arcanismo",
     "Um cofre de ferro fundido, sem fechadura visível, só um sulco em espiral onde deveria "
     "estar. Quem entender a espiral leva o que tem dentro.",
     "", "", "", "", "", "", "Materiais raros para quem passar no teste.", 3),
    ("VO07", "Ninho de Aberrações", "Combate", "", "",
     "O vazamento chegou aqui primeiro. O que nasceu do outro lado do selo aprendeu a usar "
     "os corredores — e aprendeu que comida desce por eles.",
     "", "Cria do Vazio", 15, 6, "2d6+2", 34, "", 2),
    ("VO08", "Ritual Interrompido", "Evento", "Difícil", "Religião; Arcanismo; Intuição",
     "Alguém tentou fechar a fenda daqui e parou no meio. As velas ainda queimam. Terminar o "
     "ritual enfraquece o que espera adiante; errar acorda o resto.",
     "", "", "", "", "", "", "O chefe começa o confronto final com 10 de HP a menos.", 2),
    ("VO09", "Passagem Estreita", "Armadilha", "Fácil", "Acrobacia; Atletismo; Furtividade",
     "A fenda na parede é apertada e cortante, e alguma coisa já ficou presa aqui antes de o "
     "grupo chegar.",
     "", "", "", "", "", "", "", 1),
    ("VO10", "Sala dos Espelhos Tortos", "Evento", "Média", "Intuição; Percepção; Enganação",
     "Os reflexos atrasam meio segundo e sorriem quando ninguém sorriu. Um deles aponta para "
     "a saída certa. Um deles mente.",
     "", "", "", "", "", "", "Atalho: a próxima sala começa com metade do progresso feito.", 2),
    ("VO11", "Guardião Adormecido", "Combate", "", "",
     "A coisa ocupa o corredor inteiro e respira devagar, como quem dorme há séculos. Dá para "
     "tentar passar em silêncio. Nunca dá certo.",
     "", "Coisa do Umbral", 16, 6, "2d8+3", 40, "", 2),
    ("VO12", "Poço de Oferendas", "Tesouro", "Difícil", "Religião; Investigação",
     "Moedas, dentes e anéis cobrem o fundo raso. Cada objeto foi deixado por alguém pedindo "
     "passagem — e a maioria não conseguiu.",
     "", "", "", "", "", "", "Um item mágico menor, a critério do GM.", 3),
]

# Salas em que a mesma criatura aparece repetida (sala_id -> quantidade).
QUANTIDADES = {"VO03": 2}

# Criaturas extras, para salas com um bando misto. Vao na aba 'Monstros' e se
# somam ao monstro_* da linha da sala.
MONSTROS_EXTRAS = [
    ("VO11", "Larva do Umbral", 3, 12, 3, "1d6", 9),
]

DIFICULDADES = [("Fácil", 10, 5), ("Média", 15, 10), ("Difícil", 20, 15)]


def leia_me(organizacao: str) -> list[tuple[str, bool]]:
    return [
        (f"Banco de salas — {organizacao}", True),
        ("", False),
        ("Para que serve", True),
        ("As salas do meio da dungeon nao sao escritas na incursao: sao sorteadas daqui.", False),
        (f"A cada passo o bot tira {OPCOES_POR_PASSO} salas deste banco e o grupo vota numa.", False),
        ("Cada Organizacao tem o seu banco, entao o tema das salas acompanha quem manda.", False),
        ("", False),
        ("Quantas salas escrever", True),
        (f"O minimo e {OPCOES_POR_PASSO} (um passo). Uma dungeon longa tem 7 passos, entao", False),
        ("21 salas cobrem uma run inteira sem repetir nenhuma. Com menos que isso o bot", False),
        ("reembaralha e pode repetir uma sala em passos diferentes — nunca no mesmo passo.", False),
        ("", False),
        ("Como usar", True),
        ("1. Preencha a aba 'Salas'. Uma linha por sala, sala_id unico.", False),
        ("2. Converta:  python tools/importar_banco.py <esta planilha>", False),
        ("3. No Discord, /incursao recarregar para o bot reler sem reiniciar.", False),
        ("", False),
        ("Legenda de cores", True),
        ("Fundo branco = voce preenche. Fundo cinza = formula, nao edite.", False),
        ("", False),
        ("Tipos de sala", True),
        ("Combate usa CA/ataque/HP e nao leva dificuldade nem pericia.", False),
        ("Descanso nao tem teste: cura o grupo.", False),
        ("Armadilha, Evento e Tesouro sao resolvidos por teste de pericia.", False),
    ]


def gerar(organizacao: str, destino: Path) -> Path:
    wb = Workbook()
    wb.remove(wb.active)

    ws = wb.create_sheet("Leia-me")
    ws.column_dimensions["A"].width = 100
    for i, (texto, destaque) in enumerate(leia_me(organizacao), start=1):
        c = ws.cell(row=i, column=1, value=texto)
        c.font = corpo_bold if destaque else corpo
    ws.sheet_view.showGridLines = False

    ws = wb.create_sheet("Banco")
    ws.column_dimensions["A"].width = 18
    ws.column_dimensions["B"].width = 60
    ws.cell(row=1, column=1, value="organizacao").font = corpo_bold
    ws.cell(row=1, column=2, value=organizacao).font = corpo
    ws.cell(
        row=2, column=1, value="A qual Organizacao este banco pertence. Nao apague esta aba."
    ).font = calculado

    ws = wb.create_sheet("Salas")
    for i, (titulo, largura, ajuda) in enumerate(CABECALHOS, start=1):
        c = ws.cell(row=1, column=i, value=titulo)
        c.font = cab_fonte
        c.fill = cab_fill
        c.alignment = Alignment(vertical="center", horizontal="center", wrap_text=True)
        if ajuda:
            c.comment = Comment(ajuda, "Incursoes 2.0", height=90, width=280)
        ws.column_dimensions[get_column_letter(i)].width = largura
    ws.row_dimensions[1].height = 28
    ws.freeze_panes = "A2"

    for i, sala in enumerate(SALAS, start=2):
        (sala_id, nome, tipo, dif, pericias, descricao, imagem,
         m_nome, m_ca, m_atk, m_dano, m_hp, recompensa, pontos) = sala
        valores = [sala_id, nome, tipo, dif, None, None, pericias, descricao, imagem,
                   m_nome, QUANTIDADES.get(sala_id), m_ca, m_atk, m_dano, m_hp,
                   recompensa, pontos]
        for col, valor in enumerate(valores, start=1):
            c = ws.cell(row=i, column=col, value=valor)
            c.font = corpo
            c.alignment = topo
            c.border = borda
        ws.cell(row=i, column=5).value = (
            f'=IF($D{i}="","",INDEX(Dificuldades!$B$2:$B$4,MATCH($D{i},Dificuldades!$A$2:$A$4,0)))'
        )
        ws.cell(row=i, column=6).value = (
            f'=IF($D{i}="","",INDEX(Dificuldades!$C$2:$C$4,MATCH($D{i},Dificuldades!$A$2:$A$4,0)))'
        )
        for col in (5, 6):
            c = ws.cell(row=i, column=col)
            c.font = calculado
            c.fill = fill_calculado
            c.alignment = Alignment(vertical="top", horizontal="center")
        ws.row_dimensions[i].height = 58

    ultima = len(SALAS) + 1
    dv_tipo = DataValidation(
        type="list", formula1=f'"{",".join(TIPOS_SALA)}"', allow_blank=False
    )
    ws.add_data_validation(dv_tipo)
    dv_tipo.add(f"C2:C{ultima + 50}")
    dv_dif = DataValidation(type="list", formula1="=Dificuldades!$A$2:$A$4", allow_blank=True)
    ws.add_data_validation(dv_dif)
    dv_dif.add(f"D2:D{ultima + 50}")

    ws = wb.create_sheet("Monstros")
    cabecalho_monstros = (
        ("sala_id", 10, "De qual sala desta planilha esta criatura e."),
        ("nome", 22, "Nome da criatura."),
        ("quantidade", 12, "Quantas iguais. Vazio ou 1 = uma."),
        ("ca", 8, "Classe de Armadura."),
        ("ataque", 10, "Bonus de ataque (ex.: 4)."),
        ("dano", 12, "Dado de dano (ex.: 1d6+2)."),
        ("hp", 8, "Pontos de vida de cada uma."),
        ("ataques", 9, "Golpes por rodada (multiataque). Vazio ou 1 = um."),
        ("saves", 22, "Resistencias da criatura: 'FOR +5, CON +5'. O que faltar o bot"
         " deduz do bonus de ataque."),
        ("saves_vantagem", 16, "Atributos em que ela resiste com vantagem: 'FOR, CON'."),
        ("habilidade", 20, "Nome da acao especial. Vazio = a criatura so ataca."),
        ("habilidade_texto", 40, "Descricao mostrada ao grupo. Opcional."),
        ("habilidade_save", 14, "Atributo que os alvos rolam: FOR, DES, CON, INT, SAB ou CAR."),
        ("habilidade_cd", 13, "CD do teste de resistencia (ex.: 13)."),
        ("habilidade_dano", 14, "Dano de quem falhar (ex.: 3d6). Vazio = so o efeito."),
        ("habilidade_alvos", 15, "Quantos personagens ela pega de uma vez. Vazio = 1."),
        ("habilidade_atordoa", 17, "Rodadas de atordoamento em quem falhar. Vazio ou 0 = nenhuma."),
        ("habilidade_cada", 14, "De quantas em quantas rodadas ela usa. Vazio = 2"
         " (rodadas 2, 4, 6...). Na rodada que usa, ela nao ataca."),
    )
    for i, (titulo, largura, ajuda) in enumerate(cabecalho_monstros, start=1):
        c = ws.cell(row=1, column=i, value=titulo)
        c.font = cab_fonte
        c.fill = cab_fill
        c.alignment = Alignment(vertical="center", horizontal="center", wrap_text=True)
        c.comment = Comment(ajuda, "Incursoes 2.0", height=80, width=260)
        ws.column_dimensions[get_column_letter(i)].width = largura
    ws.cell(row=1, column=1).comment = Comment(
        "Criaturas EXTRAS de uma sala, para um bando misto. O que estiver aqui se soma"
        " ao monstro_* da linha da sala, ate 6 criaturas por sala."
        " Deixe a aba vazia se cada sala tiver so um tipo de criatura."
        " Criatura com multiataque, resistencias ou acao especial vem sempre por"
        " aqui: a linha da sala so tem as colunas basicas.",
        "Incursoes 2.0",
        height=120,
        width=300,
    )
    for i, linha in enumerate(MONSTROS_EXTRAS, start=2):
        for col, valor in enumerate(linha, start=1):
            c = ws.cell(row=i, column=col, value=valor)
            c.font = corpo
            c.border = borda
    ws.freeze_panes = "A2"

    ws = wb.create_sheet("Dificuldades")
    for i, (titulo, largura) in enumerate((("dificuldade", 14), ("cd", 8), ("alvo_progresso", 16)), start=1):
        c = ws.cell(row=1, column=i, value=titulo)
        c.font = cab_fonte
        c.fill = cab_fill
        ws.column_dimensions[get_column_letter(i)].width = largura
    for i, (nome, cd, alvo) in enumerate(DIFICULDADES, start=2):
        for col, valor in enumerate((nome, cd, alvo), start=1):
            c = ws.cell(row=i, column=col, value=valor)
            c.font = corpo
            c.border = borda
    ws.cell(
        row=len(DIFICULDADES) + 3,
        column=1,
        value="Mudar aqui recalcula a CD e o alvo de todas as salas do banco.",
    ).font = calculado

    ws = wb.create_sheet("Pericias")
    for i, (titulo, largura) in enumerate((("perícia", 24), ("atributo", 18)), start=1):
        c = ws.cell(row=1, column=i, value=titulo)
        c.font = cab_fonte
        c.fill = cab_fill
        ws.column_dimensions[get_column_letter(i)].width = largura
    for i, (pericia, sigla) in enumerate(sorted(PERICIAS.items()), start=2):
        ws.cell(row=i, column=1, value=pericia).font = corpo
        ws.cell(row=i, column=2, value=f"{ATRIBUTOS[sigla]} ({sigla})").font = corpo

    destino.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destino)
    return destino


def main() -> int:
    if len(sys.argv) < 2:
        print("Uso: python tools/gerar_modelo_banco.py <Organizacao> [destino.xlsx]")
        print("Organizacoes: " + ", ".join(ORGANIZACOES))
        return 1
    organizacao = sys.argv[1]
    if organizacao not in ORGANIZACOES:
        print(f"'{organizacao}' nao e uma Organizacao. Use uma de: {', '.join(ORGANIZACOES)}")
        return 1
    alvo = (
        Path(sys.argv[2])
        if len(sys.argv) > 2
        else Path("data/planilhas") / f"banco_{arquivo_da_organizacao(organizacao)}.xlsx"
    )
    print("planilha gerada:", gerar(organizacao, alvo))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
