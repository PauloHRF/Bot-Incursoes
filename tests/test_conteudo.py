"""Conteúdo escrito por outras pessoas: carregamento, tema e tamanho de texto.

As três regras nascem da mesma pergunta — o que acontece quando quem escreve a
dungeon não é quem administra o bot:

1. **Um arquivo ruim não pode zerar o catálogo.** `carregar_todas` aborta no
   primeiro inválido, e o boot segurava a exceção subindo o bot *sem nenhuma
   incursão*: a vírgula errada de um colaborador tirava todas as dungeons do
   ar, e não só a dele.
2. **Tema é lista fechada.** Tema digitado errado tira a sala do sorteio em
   silêncio, que é exatamente o acidente das salas de Descanso escritas à mão.
3. **Texto tem teto.** `descricao` e a lore vão direto para o `description=`
   do embed, sem corte. Acima de 4096 o Discord recusa a mensagem inteira, e a
   sala quebraria na hora em que o grupo abre a porta.

Mais o bestiário: `meta.ambientes` existe, e a lista vazia é significado e não
falta.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import bestiario, incursoes as I  # noqa: E402


# ----------------------------------------------------------- fábricas


def sala_crua(**extra):
    """Uma sala de Evento válida: nada aqui depende do bestiário."""
    base = {
        "id": "T01",
        "nome": "Sala de Teste",
        "tipo": "Evento",
        "descricao": "Uma porta, e atrás dela outra porta.",
        "dificuldade": "Média",
        "cd": 13,
        "alvo_progresso": 3,
        "pericias": ["Investigação"],
    }
    base.update(extra)
    return base


def banco_cru(salas=None, **extra):
    """Um banco válido. Completa até OPCOES_POR_PASSO para o caso testar o que quer.

    Sem isso, todo caso que quer olhar UMA sala esbarraria primeiro em "o banco
    precisa de pelo menos 3 salas", que não é o assunto de nenhum deles.
    """
    salas = list(salas or [sala_crua(id=f"T{n:02d}") for n in range(1, 5)])
    enchimento = 0
    while len(salas) < I.OPCOES_POR_PASSO:
        enchimento += 1
        salas.append(sala_crua(id=f"ZZ{enchimento:02d}"))
    base = {"organizacao": "Vórtice Oculto", "salas": salas}
    base.update(extra)
    return base


def objetivo_cru(**extra):
    """O desafio final é sempre Combate, então ele precisa de criatura."""
    base = sala_crua(
        id="OBJ",
        nome="O Fim",
        tipo="Combate",
        dificuldade=None,
        cd=None,
        alvo_progresso=None,
        pericias=[],
        monstros=[
            {"nome": "Coisa", "ca": 13, "ataque": 4, "dano": "1d8+2", "hp": 20}
        ],
    )
    base.update(extra)
    return base


def incursao_crua(**extra):
    base = {
        "id": "teste_um",
        "nome": "A Incursão de Teste",
        "organizacao": "Vórtice Oculto",
        "tamanho": "Curta",
        "lore_inicial": "O grupo entra.",
        "recompensa_mes": 10,
        "objetivo": objetivo_cru(),
    }
    base.update(extra)
    return base


def recusa(dados, converter=I.de_dict) -> list[str]:
    """Os problemas que a validação apontou. Lista vazia quer dizer que passou."""
    try:
        converter(dados)
    except I.ErroDeValidacao as erro:
        return list(erro.problemas)
    return []


# ----------------------------------------------- 1. carregamento tolerante


def caso_arquivo_quebrado_nao_derruba_os_outros():
    with tempfile.TemporaryDirectory() as pasta:
        p = Path(pasta)
        (p / "boa.json").write_text(
            json.dumps(incursao_crua(id="boa")), encoding="utf-8"
        )
        # Duas formas de estar quebrado, e as duas têm que ser pulagas do mesmo
        # jeito: sintaxe de JSON e conteúdo que não passa na validação.
        (p / "virgula.json").write_text('{"id": "x",,}', encoding="utf-8")
        (p / "sem_org.json").write_text(
            json.dumps(incursao_crua(id="ruim", organizacao="Clube do Bolinha")),
            encoding="utf-8",
        )

        carregadas, problemas = I.carregar_todas_tolerante(p)

        assert list(carregadas) == ["boa"], (
            f"a incursão boa tinha que sobreviver aos vizinhos ruins; veio {list(carregadas)}"
        )
        juntos = " | ".join(problemas)
        assert "virgula.json" in juntos and "sem_org.json" in juntos, (
            f"os dois arquivos ruins têm que ser nomeados; veio: {juntos}"
        )
        assert "boa.json" not in juntos
    print("  arquivo quebrado fica de fora sozinho: ok")


def caso_a_versao_estrita_continua_levantando():
    """Ferramenta e teste querem a que para tudo; só o bot quer a tolerante."""
    with tempfile.TemporaryDirectory() as pasta:
        p = Path(pasta)
        (p / "boa.json").write_text(json.dumps(incursao_crua()), encoding="utf-8")
        (p / "ruim.json").write_text('{"id": "x",,}', encoding="utf-8")
        try:
            I.carregar_todas(p)
        except Exception:
            pass
        else:
            raise AssertionError(
                "carregar_todas engoliu um arquivo inválido: quem valida perdeu a régua dura"
            )
    print("  a versão estrita continua abortando: ok")


def caso_banco_quebrado_tambem_e_pulado():
    with tempfile.TemporaryDirectory() as pasta:
        p = Path(pasta)
        (p / "bom.json").write_text(json.dumps(banco_cru()), encoding="utf-8")
        (p / "ruim.json").write_text(
            json.dumps(banco_cru(organizacao="Clube do Bolinha")), encoding="utf-8"
        )
        bancos, problemas = I.carregar_bancos_tolerante(p)
        assert list(bancos) == ["Vórtice Oculto"], list(bancos)
        assert problemas and "ruim.json" in problemas[0], problemas
    print("  banco quebrado fica de fora sozinho: ok")


def caso_pasta_sem_nada_nao_e_problema():
    with tempfile.TemporaryDirectory() as pasta:
        carregadas, problemas = I.carregar_todas_tolerante(Path(pasta))
        assert carregadas == {} and problemas == []
    print("  pasta vazia não inventa problema: ok")


# ------------------------------------------------------------- 2. tema


def caso_tema_entra_normalizado():
    banco = I.banco_de_dict(
        banco_cru(
            salas=[
                sala_crua(id="T01", temas=["Arcano", "AGUA"]),
                sala_crua(id="T02", temas="cripta, Sagrado"),
                sala_crua(id="T03", temas=["arcano", "arcano"]),
                sala_crua(id="T04"),
            ]
        )
    )
    porid = {s.id: s for s in banco.salas}
    assert porid["T01"].temas == ["arcano", "agua"], porid["T01"].temas
    assert porid["T02"].temas == ["cripta", "sagrado"], (
        f"texto separado por vírgula é o que sai da planilha; veio {porid['T02'].temas}"
    )
    assert porid["T03"].temas == ["arcano"], "tema repetido tinha que colapsar"
    assert porid["T04"].temas == [], "sala sem o campo não pode inventar tema"
    print("  tema entra normalizado, sem repetir: ok")


def caso_tema_desconhecido_e_recusado():
    problemas = recusa(
        banco_cru(salas=[sala_crua(temas=["arcano", "vulcanico"])]), I.banco_de_dict
    )
    assert any("vulcanico" in p for p in problemas), (
        f"tema inventado tem que ser recusado, senão a sala some em silêncio: {problemas}"
    )
    assert not any("arcano'" in p for p in problemas), (
        f"o tema bom não pode ser acusado junto: {problemas}"
    )
    print("  tema desconhecido é recusado pelo nome: ok")


def caso_sala_sem_tema_serve_a_qualquer_filtro():
    sala = I.Sala(id="X", nome="X", tipo="Evento", descricao="x")
    assert sala.serve_ao_tema(["cripta"]), (
        "sala sem tema é o conteúdo escrito antes do tema existir: ela não pode sumir"
    )
    assert sala.serve_ao_tema([])
    print("  sala sem tema entra em qualquer filtro: ok")


def caso_o_filtro_e_ou_e_nao_e():
    sala = I.Sala(id="X", nome="X", tipo="Evento", descricao="x", temas=["arcano"])
    assert sala.serve_ao_tema(["cripta", "arcano"]), (
        "ter QUALQUER um dos temas pedidos basta; exigir todos esvaziaria o pool"
    )
    assert not sala.serve_ao_tema(["cripta"])
    assert sala.serve_ao_tema([]), "filtro vazio é o banco inteiro"
    print("  o filtro de tema é OU e não E: ok")


def caso_tema_sobrevive_ao_para_dict():
    banco = I.banco_de_dict(banco_cru(salas=[sala_crua(temas=["cripta", "agua"])]))
    voltou = I.banco_de_dict(banco.para_dict())
    assert voltou.salas[0].temas == ["cripta", "agua"], (
        "o tema tem que voltar inteiro na ida e volta, senão a planilha o apaga"
    )
    print("  tema sobrevive ao para_dict: ok")


# ------------------------------------------------------- 3. tamanho de texto


def caso_descricao_acima_do_teto_do_discord_e_recusada():
    no_teto = "a" * I.LIMITE_DESCRICAO
    passou = recusa(banco_cru(salas=[sala_crua(descricao=no_teto)]), I.banco_de_dict)
    assert passou == [], f"exatamente no teto tem que passar: {passou}"

    estourou = recusa(
        banco_cru(salas=[sala_crua(descricao=no_teto + "a")]), I.banco_de_dict
    )
    assert any(str(I.LIMITE_DESCRICAO) in p for p in estourou), (
        f"um caractere acima do teto do Discord tem que ser recusado: {estourou}"
    )
    print("  descrição acima de 4096 é recusada: ok")


def caso_nome_acima_do_titulo_e_recusado():
    estourou = recusa(
        banco_cru(salas=[sala_crua(nome="n" * (I.LIMITE_TITULO + 1))]), I.banco_de_dict
    )
    assert any(str(I.LIMITE_TITULO) in p for p in estourou), estourou
    print("  nome acima de 256 é recusado: ok")


def caso_lore_acima_do_teto_e_recusada():
    grande = "l" * (I.LIMITE_DESCRICAO + 1)
    assert any(
        "lore de abertura" in p for p in recusa(incursao_crua(lore_inicial=grande))
    ), "a lore de abertura vai direto para description= e não é cortada"
    assert any(
        "lore de fecho" in p for p in recusa(incursao_crua(lore_final=grande))
    ), "a lore de fecho vai para o mesmo lugar"
    assert recusa(incursao_crua(lore_final=None)) == [], (
        "lore de fecho é opcional: ausente não pode virar problema"
    )
    print("  lore acima de 4096 é recusada nas duas pontas: ok")


def caso_o_conteudo_de_hoje_passa_nos_limites():
    """A regra é nova; o conteúdo escrito até aqui não pode ter virado inválido."""
    I.carregar_todas(RAIZ / "data" / "incursoes")
    I.carregar_bancos(RAIZ / "data" / "bancos")
    print("  o conteúdo de hoje continua válido: ok")


# --------------------------------------------------------- 4. planilha


# O cabeçalho das planilhas escritas ANTES do tema existir, escrito à mão de
# propósito. Derivar de `importar_banco.COLUNAS` faria o teste se mover junto
# com o código: se alguém tornasse 'temas' obrigatória, a planilha "antiga"
# deste teste ganharia a coluna sozinha e a incompatibilidade passaria batida.
# Esta lista é um fóssil, e é esse o valor dela.
CABECALHO_ANTIGO = (
    "sala_id", "nome", "tipo", "dificuldade", "cd", "alvo_progresso", "pericias",
    "descricao", "imagem", "monstro_nome", "monstro_quantidade", "monstro_ca",
    "monstro_ataque", "monstro_dano", "monstro_hp", "recompensa", "pontos_organizacao",
)


def _planilha_de_salas(com_temas: bool, temas: str = ""):
    """Uma aba 'Salas' mínima, com e sem a coluna que entrou depois."""
    from openpyxl import Workbook

    colunas = list(CABECALHO_ANTIGO)
    if com_temas:
        colunas.insert(colunas.index("pericias") + 1, "temas")

    wb = Workbook()
    ws = wb.active
    ws.title = "Salas"
    ws.append(colunas)
    linha = {
        "sala_id": "T01", "nome": "Sala", "tipo": "Evento",
        "dificuldade": "Média", "cd": 13, "alvo_progresso": 3,
        "pericias": "Investigação", "descricao": "Uma porta.",
        "pontos_organizacao": 1,
    }
    if com_temas:
        linha["temas"] = temas
    ws.append([linha.get(c) for c in colunas])
    return wb


def caso_a_planilha_sem_a_coluna_de_tema_continua_importando():
    """A promessa de compatibilidade: coluna nova não invalida planilha velha."""
    sys.path.insert(0, str(RAIZ / "tools"))
    import importar_banco as IB

    salas = IB.ler_salas(_planilha_de_salas(False), {"media": (13, 3)})
    assert len(salas) == 1 and salas[0]["temas"] == [], (
        f"planilha feita antes do tema tem que importar sem tema: {salas}"
    )
    print("  planilha sem a coluna de tema continua importando: ok")


def caso_a_planilha_com_tema_separa_por_ponto_e_virgula():
    sys.path.insert(0, str(RAIZ / "tools"))
    import importar_banco as IB

    salas = IB.ler_salas(
        _planilha_de_salas(True, "arcano; agua"), {"media": (13, 3)}
    )
    assert salas[0]["temas"] == ["arcano", "agua"], salas[0]["temas"]

    # A planilha ensina ';' e quem digita usa ',': os dois têm que valer.
    salas = IB.ler_salas(_planilha_de_salas(True, "cripta, sagrado"), {"media": (13, 3)})
    assert salas[0]["temas"] == ["cripta", "sagrado"], salas[0]["temas"]
    print("  a coluna de tema aceita ';' e ',': ok")


# ------------------------------------------------------------ 5. ambiente


def caso_o_bestiario_tem_ambiente():
    criaturas = bestiario.carregar()
    assert len(criaturas) == 385, len(criaturas)

    sem_campo = [
        c["nome"] for c in criaturas
        if "ambientes" not in (c.get("meta") or {})
    ]
    assert not sem_campo, (
        f"{len(sem_campo)} criatura(s) ficaram sem o campo: {sem_campo[:5]}"
    )

    com = [c for c in criaturas if bestiario.ambientes_de(c)]
    nenhures = [c for c in criaturas if bestiario.de_lugar_nenhum(c)]
    assert len(com) == 315, len(com)
    assert len(nenhures) == 70, len(nenhures)
    print(f"  {len(com)} criaturas com ambiente, {len(nenhures)} de lugar nenhum: ok")


def caso_o_vocabulario_de_ambiente_e_fechado():
    vistos = {
        a for c in bestiario.carregar() for a in bestiario.ambientes_de(c)
    }
    fora = vistos - set(bestiario.AMBIENTES)
    assert not fora, f"ambiente fora da lista fechada: {sorted(fora)}"
    assert vistos == set(bestiario.AMBIENTES), (
        f"a lista declara ambiente que ninguém usa: {sorted(set(bestiario.AMBIENTES) - vistos)}"
    )
    print(f"  os {len(vistos)} ambientes batem com a lista fechada: ok")


def caso_de_lugar_nenhum_e_quem_o_livro_nao_prende():
    """A lista vazia é significado: demônio e golem não são nativos de bioma."""
    por_tipo: dict[str, int] = {}
    for criatura in bestiario.carregar():
        if bestiario.de_lugar_nenhum(criatura):
            tipo = (criatura.get("meta") or {}).get("tipo") or "?"
            por_tipo[tipo] = por_tipo.get(tipo, 0) + 1
    assert por_tipo.get("fiend", 0) >= 25, por_tipo
    assert por_tipo.get("construct", 0) >= 10, por_tipo
    assert por_tipo.get("beast", 0) == 0, (
        f"bicho de bioma não pode cair no balde de lugar nenhum: {por_tipo}"
    )
    print("  o balde 'de lugar nenhum' é demônio e golem, não bicho: ok")


for caso in (
    caso_arquivo_quebrado_nao_derruba_os_outros,
    caso_a_versao_estrita_continua_levantando,
    caso_banco_quebrado_tambem_e_pulado,
    caso_pasta_sem_nada_nao_e_problema,
    caso_tema_entra_normalizado,
    caso_tema_desconhecido_e_recusado,
    caso_sala_sem_tema_serve_a_qualquer_filtro,
    caso_o_filtro_e_ou_e_nao_e,
    caso_tema_sobrevive_ao_para_dict,
    caso_descricao_acima_do_teto_do_discord_e_recusada,
    caso_nome_acima_do_titulo_e_recusado,
    caso_lore_acima_do_teto_e_recusada,
    caso_o_conteudo_de_hoje_passa_nos_limites,
    caso_a_planilha_sem_a_coluna_de_tema_continua_importando,
    caso_a_planilha_com_tema_separa_por_ponto_e_virgula,
    caso_o_bestiario_tem_ambiente,
    caso_o_vocabulario_de_ambiente_e_fechado,
    caso_de_lugar_nenhum_e_quem_o_livro_nao_prende,
):
    caso()

print("TESTES DE CONTEUDO PASSARAM")
