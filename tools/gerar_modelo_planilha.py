"""Gera a planilha modelo de uma incursão, preenchida com um exemplo jogável.

    python tools/gerar_modelo_planilha.py [destino.xlsx]

O GM edita a planilha e converte para JSON com tools/importar_planilha.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.comments import Comment
from openpyxl.worksheet.datavalidation import DataValidation

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.rules import PERICIAS, ATRIBUTOS  # noqa: E402

FONTE = "Arial"
AZUL = "2F3B52"
CINZA_CLARO = "F2F2F2"
AMARELO = "FFF2CC"

cab_fonte = Font(name=FONTE, size=10, bold=True, color="FFFFFF")
cab_fill = PatternFill("solid", fgColor=AZUL)
corpo = Font(name=FONTE, size=10)
corpo_bold = Font(name=FONTE, size=10, bold=True)
calculado = Font(name=FONTE, size=10, color="808080", italic=True)
fill_calculado = PatternFill("solid", fgColor=CINZA_CLARO)
fill_destaque = PatternFill("solid", fgColor=AMARELO)
borda = Border(*[Side(style="thin", color="D0D0D0")] * 4)
topo = Alignment(vertical="top", wrap_text=True)

# --- metadados da incursão de exemplo ---
META = [
    ("id", "vortice_cripta", "Identificador curto e único, sem espaço. Vira o nome do arquivo JSON."),
    ("nome", "A Cripta do Vórtice", "Nome exibido aos jogadores."),
    ("organizacao", "Vórtice Oculto", "Uma das quatro: Vórtice Oculto, Aliança das Sombras, Guilda dos Mortos, Sentinelas do Alvorecer."),
    ("descricao", "Um selo antigo cedeu sob a cidade e algo do outro lado começou a vazar. A Organização quer o Olho recuperado antes que a fenda se alargue.", "Texto de abertura da run."),
    ("imagem_capa", "assets/vortice_cripta/capa.png", "Caminho local (dentro de assets/) ou URL. Opcional."),
    ("recompensa_mes", 10, "MEs por participante ao completar o objetivo."),
]

CABECALHOS = [
    ("sala_id", 10, "Identificador único da sala."),
    ("linha", 10, "1, 2 ou 3 — ou 'Objetivo' para a sala final."),
    ("nome", 26, "Nome da sala mostrado no embed."),
    ("tipo", 14, "Combate, Descanso, Armadilha, Evento ou Tesouro."),
    ("dificuldade", 13, "Fácil, Média ou Difícil. Vazio em Descanso e Combate."),
    ("cd", 7, "CALCULADO a partir da dificuldade (aba Dificuldades)."),
    ("alvo_progresso", 15, "CALCULADO: soma de margens que o grupo precisa atingir."),
    ("pericias", 30, "Perícias aceitas, separadas por ';'. Vazio em Descanso e Combate."),
    ("descricao", 62, "Texto do embed da sala."),
    ("imagem", 30, "Caminho em assets/ ou URL da imagem da sala."),
    ("monstro_nome", 22, "Só em salas de Combate."),
    ("monstro_ca", 11, "Classe de Armadura do monstro."),
    ("monstro_ataque", 15, "Bônus de ataque do monstro (ex.: 6)."),
    ("monstro_dano", 14, "Dado de dano do monstro (ex.: 2d6+3)."),
    ("monstro_hp", 11, "Pontos de vida do monstro."),
    ("recompensa", 34, "Bônus da sala (texto livre). Opcional."),
]

SALAS = [
    ("L1A", 1, "Portal Instável", "Armadilha", "Média",
     "Acrobacia; Arcanismo",
     "A escada termina num arco de pedra que ainda pulsa. A cada batida, o ar se dobra e cospe estilhaços de realidade pelo corredor. Passar exige ler o ritmo — ou ser muito rápido.",
     "assets/vortice_cripta/portal.png", "", "", "", "", "", "Quem passa ileso encontra um fragmento do selo."),
    ("L1B", 1, "Biblioteca Submersa", "Evento", "Média",
     "Investigação; Arcanismo; História",
     "Água escura cobre as prateleiras até a altura do peito. Os livros que boiam ainda estão secos, e isso é o mais perturbador da sala. Algum deles diz onde o Olho foi guardado.",
     "assets/vortice_cripta/biblioteca.png", "", "", "", "", "", "Revela a CA do chefe antes do confronto final."),
    ("L1C", 1, "Sentinelas de Pedra", "Combate", "",
     "",
     "Duas estátuas ladeiam a porta interna. Elas não se mexem enquanto ninguém olha para o que carregam — e o que carregam é o que o grupo veio buscar.",
     "assets/vortice_cripta/sentinelas.png", "Sentinela de Basalto", 14, 5, "1d10+3", 26, ""),
    ("L2A", 2, "Corredor dos Ecos", "Armadilha", "Difícil",
     "Percepção; Acrobacia; Furtividade",
     "Cada passo volta multiplicado, e junto com o eco vem alguma coisa que anda no contratempo. O chão está coberto de placas que afundam sob peso.",
     "assets/vortice_cripta/corredor.png", "", "", "", "", "", ""),
    ("L2B", 2, "Acampamento Abandonado", "Descanso", "",
     "",
     "Uma expedição anterior montou barraca aqui e não voltou. As brasas ainda estão mornas, a comida intacta. O grupo descansa — desconfiado, mas descansa.",
     "assets/vortice_cripta/acampamento.png", "", "", "", "", "", "Cada personagem caído volta com metade do HP máximo."),
    ("L2C", 2, "Cofre Selado", "Tesouro", "Média",
     "Prestidigitação; Arcanismo",
     "Um cofre de ferro fundido, sem fechadura visível, só um sulco em espiral onde deveria estar. Quem entender a espiral leva o que tem dentro.",
     "assets/vortice_cripta/cofre.png", "", "", "", "", "", "Materiais raros para quem passar no teste."),
    ("L3A", 3, "Ninho de Aberrações", "Combate", "",
     "",
     "O vazamento chegou aqui primeiro. O que nasceu do outro lado do selo aprendeu a usar os corredores — e aprendeu que comida desce por eles.",
     "assets/vortice_cripta/ninho.png", "Cria do Vazio", 15, 6, "2d6+2", 34, ""),
    ("L3B", 3, "Ritual Interrompido", "Evento", "Difícil",
     "Religião; Arcanismo; Intuição",
     "Alguém tentou fechar a fenda daqui e parou no meio. As velas ainda queimam. Terminar o ritual enfraquece o que espera adiante; errar acorda o resto.",
     "assets/vortice_cripta/ritual.png", "", "", "", "", "", "O chefe começa o combate final com 10 de HP a menos."),
    ("L3C", 3, "Passagem Estreita", "Armadilha", "Fácil",
     "Acrobacia; Atletismo; Furtividade",
     "A fenda na parede é a única entrada para a câmara final. É apertada, cortante, e alguma coisa já ficou presa aqui antes do grupo chegar.",
     "assets/vortice_cripta/passagem.png", "", "", "", "", "", ""),
    ("OBJ", "Objetivo", "O Olho do Vórtice", "Combate", "",
     "",
     "A câmara é uma esfera perfeita e o Olho flutua no centro dela, aberto. O que o guarda não tem nome porque nada que o viu voltou para dar um.",
     "assets/vortice_cripta/olho.png", "Guardião do Selo", 16, 7, "2d8+4", 58, "10 MEs por participante + pontos com o Vórtice Oculto"),
]

DIFICULDADES = [("Fácil", 10, 5), ("Média", 15, 10), ("Difícil", 20, 15)]

LEIA_ME = [
    ("Planilha de incursão — Incursões 2.0", True),
    ("", False),
    ("Como usar", True),
    ("1. Preencha a aba 'Incursao' com os dados gerais e a aba 'Salas' com as 10 salas.", False),
    ("2. São exatamente 9 salas de conteúdo (3 por linha) mais 1 sala de Objetivo.", False),
    ("3. A sala de Objetivo é sempre do tipo Combate e precisa dos campos de monstro preenchidos.", False),
    ("   Salas de Combate não usam dificuldade nem perícia: a mecânica é CA / ataque / HP.", False),
    ("4. Converta para JSON:  python tools/importar_planilha.py <esta planilha>", False),
    ("   O importador valida tudo e recusa a planilha se algo estiver faltando.", False),
    ("", False),
    ("Legenda de cores (aba Salas)", True),
    ("Fundo branco  = você preenche.", False),
    ("Fundo cinza   = calculado por fórmula a partir da dificuldade. Não edite.", False),
    ("Fundo amarelo = a sala de Objetivo, com regras próprias.", False),
    ("", False),
    ("Regras de progressão", True),
    ("Toda sala de uma linha leva a qualquer sala da linha seguinte: o grupo escolhe 1 das 3", False),
    ("opções por linha, três vezes, e então enfrenta o Objetivo. Não há volta nem pulo de linha.", False),
    ("", False),
    ("Testes de perícia", True),
    ("Cada jogador rola d20 + o modificador da melhor perícia que tiver entre as listadas.", False),
    ("Quem passa da CD contribui a margem (rolagem + mod − CD) como progresso; quem falha", False),
    ("contribui 0 e sofre a consequência individual do tipo da sala. A sala é superada quando", False),
    ("a soma das margens do grupo atinge o alvo_progresso.", False),
    ("", False),
    ("Combate não usa esse sistema: é d20 + bônus de ataque contra a CA do monstro, dano", False),
    ("subtraído do HP dele, e contra-ataque do monstro contra a CA de um personagem.", False),
    ("", False),
    ("Perícias válidas: veja a aba 'Pericias'. Pode escrever com ou sem acento.", False),
]


def estilizar_cabecalho(ws, colunas):
    for i, (titulo, largura, ajuda) in enumerate(colunas, start=1):
        c = ws.cell(row=1, column=i, value=titulo)
        c.font = cab_fonte
        c.fill = cab_fill
        c.alignment = Alignment(vertical="center", horizontal="center", wrap_text=True)
        if ajuda:
            c.comment = Comment(ajuda, "Incursoes 2.0", height=90, width=280)
        ws.column_dimensions[get_column_letter(i)].width = largura
    ws.row_dimensions[1].height = 28
    ws.freeze_panes = "A2"


def aba_leia_me(wb):
    ws = wb.create_sheet("Leia-me")
    ws.column_dimensions["A"].width = 100
    for i, (texto, destaque) in enumerate(LEIA_ME, start=1):
        c = ws.cell(row=i, column=1, value=texto)
        c.font = corpo_bold if destaque else corpo
    ws.sheet_view.showGridLines = False
    return ws


def aba_incursao(wb):
    ws = wb.create_sheet("Incursao")
    estilizar_cabecalho(ws, [("campo", 18, ""), ("valor", 70, ""), ("o que é", 62, "")])
    for i, (campo, valor, ajuda) in enumerate(META, start=2):
        ws.cell(row=i, column=1, value=campo).font = corpo_bold
        v = ws.cell(row=i, column=2, value=valor)
        v.font = corpo
        v.alignment = topo
        a = ws.cell(row=i, column=3, value=ajuda)
        a.font = calculado
        a.alignment = topo
        ws.row_dimensions[i].height = 30
    return ws


def aba_salas(wb):
    ws = wb.create_sheet("Salas")
    estilizar_cabecalho(ws, CABECALHOS)

    for i, sala in enumerate(SALAS, start=2):
        (sala_id, linha, nome, tipo, dif, pericias, descricao, imagem,
         m_nome, m_ca, m_atk, m_dano, m_hp, recompensa) = sala

        valores = [sala_id, linha, nome, tipo, dif, None, None, pericias, descricao,
                   imagem, m_nome, m_ca, m_atk, m_dano, m_hp, recompensa]
        for col, valor in enumerate(valores, start=1):
            c = ws.cell(row=i, column=col, value=valor)
            c.font = corpo
            c.alignment = topo
            c.border = borda

        # cd e alvo_progresso saem da aba Dificuldades — o GM calibra num lugar só.
        ws.cell(row=i, column=6).value = (
            f'=IF($E{i}="","",INDEX(Dificuldades!$B$2:$B$4,MATCH($E{i},Dificuldades!$A$2:$A$4,0)))'
        )
        ws.cell(row=i, column=7).value = (
            f'=IF($E{i}="","",INDEX(Dificuldades!$C$2:$C$4,MATCH($E{i},Dificuldades!$A$2:$A$4,0)))'
        )
        for col in (6, 7):
            c = ws.cell(row=i, column=col)
            c.font = calculado
            c.fill = fill_calculado
            c.alignment = Alignment(vertical="top", horizontal="center")

        if sala_id == "OBJ":
            for col in range(1, len(CABECALHOS) + 1):
                if col not in (6, 7):
                    ws.cell(row=i, column=col).fill = fill_destaque

        ws.row_dimensions[i].height = 62

    ultima = len(SALAS) + 1
    dv_tipo = DataValidation(
        type="list", formula1='"Combate,Descanso,Armadilha,Evento,Tesouro"', allow_blank=False
    )
    dv_tipo.error = "Tipo inválido."
    ws.add_data_validation(dv_tipo)
    dv_tipo.add(f"D2:D{ultima}")

    dv_dif = DataValidation(type="list", formula1="=Dificuldades!$A$2:$A$4", allow_blank=True)
    dv_dif.error = "Use Fácil, Média ou Difícil (ou deixe vazio em Descanso)."
    ws.add_data_validation(dv_dif)
    dv_dif.add(f"E2:E{ultima}")

    dv_linha = DataValidation(type="list", formula1='"1,2,3,Objetivo"', allow_blank=False)
    ws.add_data_validation(dv_linha)
    dv_linha.add(f"B2:B{ultima}")

    return ws


def aba_dificuldades(wb):
    ws = wb.create_sheet("Dificuldades")
    estilizar_cabecalho(ws, [("dificuldade", 14, ""), ("cd", 8, ""), ("alvo_progresso", 16, "")])
    for i, (nome, cd, alvo) in enumerate(DIFICULDADES, start=2):
        for col, valor in enumerate((nome, cd, alvo), start=1):
            c = ws.cell(row=i, column=col, value=valor)
            c.font = corpo
            c.border = borda
            if col > 1:
                c.alignment = Alignment(horizontal="center")
    nota = ws.cell(
        row=len(DIFICULDADES) + 3,
        column=1,
        value="Valores de partida do documento de design, a calibrar no playtest. "
        "Mudar aqui recalcula a CD e o alvo de todas as salas.",
    )
    nota.font = calculado
    return ws


def aba_pericias(wb):
    ws = wb.create_sheet("Pericias")
    estilizar_cabecalho(ws, [("perícia", 24, ""), ("atributo", 18, "")])
    for i, (pericia, sigla) in enumerate(sorted(PERICIAS.items()), start=2):
        ws.cell(row=i, column=1, value=pericia).font = corpo
        ws.cell(row=i, column=2, value=f"{ATRIBUTOS[sigla]} ({sigla})").font = corpo
    nota = ws.cell(
        row=len(PERICIAS) + 3,
        column=1,
        value="Nomes aceitos na coluna 'pericias' da aba Salas, separados por ';'. Acento é opcional.",
    )
    nota.font = calculado
    return ws


def gerar(destino: Path) -> Path:
    wb = Workbook()
    wb.remove(wb.active)
    aba_leia_me(wb)
    aba_incursao(wb)
    aba_salas(wb)
    aba_dificuldades(wb)
    aba_pericias(wb)
    destino.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destino)
    return destino


if __name__ == "__main__":
    alvo = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/planilhas/incursao_exemplo.xlsx")
    print("planilha gerada:", gerar(alvo))
