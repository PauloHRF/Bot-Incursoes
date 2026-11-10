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
import random
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


# ------------------------------------- 3a. o filtro e a conferência cruzada


def banco_etiquetado():
    """Oito salas com tema, mais a de Descanso que não é sorteada."""
    salas = [
        sala_crua(id="T01", temas=["arcano", "escuridao"]),
        sala_crua(id="T02", temas=["arcano", "agua"]),
        sala_crua(id="T03", temas=["fortaleza"]),
        sala_crua(id="T04", temas=["cripta"]),
        sala_crua(id="T05", temas=["cripta", "sagrado"]),
        sala_crua(id="T06", temas=["natureza"]),
        sala_crua(id="T07", temas=["urbano"]),
        sala_crua(id="T08", temas=["arcano"]),
        sala_crua(
            id="T99", tipo="Descanso", temas=["cripta"], dificuldade=None,
            cd=None, alvo_progresso=None, pericias=[],
        ),
    ]
    return I.banco_de_dict(banco_cru(salas=salas))


def caso_o_descanso_nunca_entra_no_pool():
    """Nem pelo tema: ele é cenário da parada fixa, não sala do caminho."""
    banco = banco_etiquetado()
    assert all(s.tipo != "Descanso" for s in I.salas_sorteaveis(banco))
    pool = I.FiltroDeSalas(temas=["cripta"]).aplicar(I.salas_sorteaveis(banco))
    assert [s.id for s in pool] == ["T04", "T05"], [s.id for s in pool]
    print("  a sala de Descanso não entra no pool nem pelo tema: ok")


def caso_o_filtro_segue_as_tres_etapas():
    salas = I.salas_sorteaveis(banco_etiquetado())

    vazio = I.FiltroDeSalas().aplicar(salas)
    assert len(vazio) == 8, "filtro vazio é o banco inteiro"

    por_tema = I.FiltroDeSalas(temas=["arcano"]).aplicar(salas)
    assert [s.id for s in por_tema] == ["T01", "T02", "T08"]

    # `incluir` É o pool, e manda sobre o tema.
    so_essas = I.FiltroDeSalas(incluir=["T03", "T06"]).aplicar(salas)
    assert [s.id for s in so_essas] == ["T03", "T06"]

    # `excluir` vem por último, inclusive sobre `incluir`.
    menos_uma = I.FiltroDeSalas(incluir=["T03", "T06"], excluir=["T06"]).aplicar(salas)
    assert [s.id for s in menos_uma] == ["T03"]
    tirando = I.FiltroDeSalas(temas=["arcano"], excluir=["T02"]).aplicar(salas)
    assert [s.id for s in tirando] == ["T01", "T08"]
    print("  o filtro segue tema, incluir e excluir nessa ordem: ok")


def caso_incluir_e_temas_juntos_sao_recusados():
    problemas = recusa(incursao_crua(filtro={"temas": ["cripta"], "incluir": ["T01"]}))
    assert any("É o pool" in p for p in problemas), problemas
    print("  'incluir' junto com 'temas' é recusado: ok")


def caso_campo_desconhecido_no_filtro_e_recusado():
    """Digitar 'incluem' muda o caminho da dungeon inteira em silêncio."""
    problemas = recusa(incursao_crua(filtro={"incluem": ["T01"]}))
    assert any("incluem" in p for p in problemas), problemas
    print("  campo desconhecido no filtro é recusado: ok")


def caso_pool_pequeno_demais_e_problema_e_o_apertado_e_aviso():
    banco = banco_etiquetado()

    # Longa atravessa 7, e 'cripta' deixa 2: nao tem como terminar.
    longa = I.de_dict(incursao_crua(tamanho="Longa", filtro={"temas": ["cripta"]}))
    problemas, _ = I.conferir_filtro(longa, banco)
    assert problemas and "faltam 5 para a run poder terminar" in problemas[0], problemas

    # Curta atravessa 3 e quer 5 para tres portas: 'arcano' deixa 3.
    curta = I.de_dict(incursao_crua(tamanho="Curta", filtro={"temas": ["arcano"]}))
    problemas, avisos = I.conferir_filtro(curta, banco)
    assert not problemas, problemas
    assert avisos and "dá para terminar" in avisos[0], avisos

    # Sem filtro, as oito sorteaveis cobrem a Curta com folga.
    solta = I.de_dict(incursao_crua(tamanho="Curta"))
    assert I.conferir_filtro(solta, banco) == ([], [])
    print("  pool curto é problema, pool apertado é aviso: ok")


def caso_incluir_com_id_que_nao_existe_e_problema():
    banco = banco_etiquetado()
    inc = I.de_dict(
        incursao_crua(tamanho="Curta", filtro={"incluir": ["T01", "T02", "T77", "T03"]})
    )
    problemas, _ = I.conferir_filtro(inc, banco)
    assert any("T77" in p for p in problemas), problemas
    assert not any("T01" in p for p in problemas), problemas
    print("  id inexistente em 'incluir' é problema: ok")


def caso_excluir_id_que_nao_existe_e_so_aviso():
    banco = banco_etiquetado()
    inc = I.de_dict(incursao_crua(tamanho="Curta", filtro={"excluir": ["T77"]}))
    problemas, avisos = I.conferir_filtro(inc, banco)
    assert not problemas, problemas
    assert any("T77" in a for a in avisos), avisos
    print("  id inexistente em 'excluir' é só aviso: ok")


def caso_filtro_que_nao_filtra_e_avisado():
    """Banco sem tema escrito: o filtro parece funcionar e não tira nada."""
    sem_tema = I.banco_de_dict(
        banco_cru(salas=[sala_crua(id=f"T{n:02d}") for n in range(1, 6)])
    )
    inc = I.de_dict(incursao_crua(tamanho="Curta", filtro={"temas": ["cripta"]}))
    problemas, avisos = I.conferir_filtro(inc, sem_tema)
    assert not problemas, problemas
    assert any("não está tirando nada" in a for a in avisos), avisos

    # E com o banco etiquetado o aviso some: senao ele viraria ruido de sempre.
    _, avisos = I.conferir_filtro(inc, banco_etiquetado())
    assert not any("não está tirando nada" in a for a in avisos), avisos
    print("  filtro que não filtra, por falta de etiqueta, é avisado: ok")


def caso_o_filtro_sobrevive_ao_para_dict():
    inc = I.de_dict(
        incursao_crua(filtro={"temas": ["cripta"], "excluir": ["T02"]})
    )
    voltou = I.de_dict(inc.para_dict())
    assert voltou.filtro.temas == ["cripta"] and voltou.filtro.excluir == ["T02"]
    # Incursao sem filtro nao ganha o campo: o JSON nao cria ruido sozinho.
    assert "filtro" not in I.de_dict(incursao_crua()).para_dict()
    print("  o filtro sobrevive ao para_dict, e o vazio não aparece: ok")


# ------------------------------------------------ 3c. combate por tema


CRIATURA = {"ca": 13, "ataque": 4, "dano": "1d6", "hp": 12}


def sala_com_variantes(**extra):
    base = sala_crua(
        id="C01", tipo="Combate", dificuldade=None, cd=None,
        alvo_progresso=None, pericias=[],
        temas=["arcano", "natureza", "cripta"],
        monstros_por_tier={"2": [dict(CRIATURA, nome="Grick")]},
        monstros_por_tema={
            "cripta": {"2": [dict(CRIATURA, nome="Ghoul")]},
            "natureza": {"2": [dict(CRIATURA, nome="Aranha")]},
        },
    )
    base.update(extra)
    return base


def _sala_valida(bruta):
    banco = I.banco_de_dict(banco_cru(salas=[bruta]))
    return banco.salas[0]


def caso_a_variante_do_tema_troca_o_bando():
    sala = _sala_valida(sala_com_variantes())
    nomes = lambda tema: [m.nome for m in sala.monstros_do_tier(2, tema)]
    assert nomes(None) == ["Grick"], nomes(None)
    assert nomes("cripta") == ["Ghoul"], nomes("cripta")
    assert nomes("natureza") == ["Aranha"], nomes("natureza")
    # Tema que a sala carrega mas nao tem variante cai no bando padrao.
    assert nomes("arcano") == ["Grick"], nomes("arcano")
    print("  a variante do tema troca o bando, e sem variante cai no padrão: ok")


def caso_a_variante_do_tema_tem_a_mesma_queda_por_tier():
    """Dentro da variante vale a mesma regra: exato, senão o maior abaixo."""
    sala = _sala_valida(
        sala_com_variantes(
            monstros_por_tema={
                "cripta": {
                    "2": [dict(CRIATURA, nome="Ghoul")],
                    "4": [dict(CRIATURA, nome="Múmia")],
                }
            }
        )
    )
    nomes = lambda tier: [m.nome for m in sala.monstros_do_tier(tier, "cripta")]
    assert nomes(2) == ["Ghoul"] and nomes(4) == ["Múmia"]
    assert nomes(3) == ["Ghoul"], "tier 3 tinha que cair no maior escrito abaixo"
    assert nomes(5) == ["Múmia"], nomes(5)
    print("  a variante por tema cai por tier como o resto: ok")


def caso_variante_de_tema_que_a_sala_nao_carrega_e_recusada():
    """Senão o combate escrito morre calado: esse tema nunca entra em jogo."""
    problemas = recusa(
        banco_cru(
            salas=[
                sala_com_variantes(
                    temas=["arcano"],
                    monstros_por_tema={
                        "cripta": {"2": [dict(CRIATURA, nome="Ghoul")]}
                    },
                )
            ]
        ),
        I.banco_de_dict,
    )
    assert any("nunca seria usada" in p for p in problemas), problemas
    print("  variante de um tema que a sala não carrega é recusada: ok")


def caso_tema_inventado_em_monstros_por_tema_e_recusado():
    problemas = recusa(
        banco_cru(
            salas=[
                sala_com_variantes(
                    monstros_por_tema={
                        "vulcanico": {"2": [dict(CRIATURA, nome="Ghoul")]}
                    }
                )
            ]
        ),
        I.banco_de_dict,
    )
    assert any("vulcanico" in p for p in problemas), problemas
    print("  tema inventado em monstros_por_tema é recusado: ok")


def caso_o_tema_em_jogo_e_a_interseccao():
    sala = _sala_valida(sala_com_variantes())
    assert sala.tema_em_jogo([]) is None, "sem filtro não há tema em jogo"
    assert sala.tema_em_jogo(["urbano"]) is None, "tema que a sala não tem não vale"
    assert sala.tema_em_jogo(["cripta"]) == "cripta"
    assert sala.tema_em_jogo(["cripta", "urbano"]) == "cripta"

    sem_tema = _sala_valida(
        sala_com_variantes(temas=[], monstros_por_tema={})
    )
    assert sem_tema.tema_em_jogo(["cripta"]) is None, (
        "sala sem tema entra no filtro, mas não ganha tema em jogo"
    )
    print("  o tema em jogo é a intersecção sala × filtro: ok")


def caso_a_escolha_entre_temas_e_estavel_na_mesma_run():
    """A mesma sala, na mesma run, tem que dar sempre o mesmo tema.

    Senão o bando mudaria a cada redesenho do cartão e a cada restart — e o
    cartão mostraria uma criatura enquanto o combate abriria com outra.
    """
    sala = _sala_valida(sala_com_variantes())
    pedidos = ["cripta", "natureza"]
    escolhas = {
        sala.tema_em_jogo(pedidos, random.Random(f"7:{sala.id}")) for _ in range(40)
    }
    assert len(escolhas) == 1, f"a escolha oscilou na mesma run: {escolhas}"

    # E runs diferentes podem cair em temas diferentes: a semente é o par.
    por_run = {
        sala.tema_em_jogo(pedidos, random.Random(f"{n}:{sala.id}")) for n in range(60)
    }
    assert por_run == {"cripta", "natureza"}, por_run
    print("  a escolha de tema é estável na run e varia entre runs: ok")


def caso_o_cartao_da_sala_mostra_o_bando_do_tema():
    """O cartão e o combate têm que mostrar o MESMO bando.

    O cartão é desenhado antes de `iniciar_combate`, e os dois leem a sala por
    caminhos diferentes. Se só um deles soubesse do tema, o grupo veria uma
    criatura no cartão e lutaria contra outra.
    """
    from src import embeds as E

    sala = _sala_valida(sala_com_variantes())

    def texto_do_cartao(**kwargs):
        embed, _ = E.sala_aberta(sala, 1, tier=2, **kwargs)
        return " ".join(f"{c.name} {c.value}" for c in embed.fields)

    assert "Ghoul" in texto_do_cartao(tema="cripta")
    assert "Aranha" in texto_do_cartao(tema="natureza")
    assert "Grick" in texto_do_cartao(), "sem tema o cartão mostra o bando padrão"
    assert "Ghoul" not in texto_do_cartao()
    print("  o cartão da sala mostra o bando do tema: ok")


def caso_a_variante_sobrevive_ao_para_dict():
    sala = _sala_valida(sala_com_variantes())
    voltou = _sala_valida(sala.para_dict())
    assert [m.nome for m in voltou.monstros_do_tier(2, "cripta")] == ["Ghoul"]
    # Sala sem variante nao ganha o campo vazio no arquivo.
    simples = _sala_valida(
        sala_crua(
            id="C02", tipo="Combate", dificuldade=None, cd=None,
            alvo_progresso=None, pericias=[],
            monstros=[dict(CRIATURA, nome="Grick")],
        )
    )
    assert "monstros_por_tema" not in simples.para_dict()
    print("  a variante sobrevive ao para_dict, e o vazio não aparece: ok")


# --------------------------------------------- 3b. a sala de Descanso do banco


def _avisos_do_banco(salas):
    sys.path.insert(0, str(RAIZ / "tools"))
    import validar_conteudo as V

    bruto = banco_cru(salas=salas)
    return V.avisos(Path("banco.json"), bruto)


def caso_banco_sem_descanso_e_avisado():
    """A sala de Descanso NÃO é sorteada, e nem por isso é dispensável.

    `_sala_de_descanso` lê a sala de Descanso do banco para usar como cenário
    da parada fixa — a Cela do Coveiro da Guilda, a Adega Falsa das Sombras.
    Banco sem nenhuma faz o grupo chegar na parada e seguir SEM DESCANSAR,
    perdendo a única cura garantida da Média.

    Este caso existe porque o aviso já esteve invertido: ele dizia que a sala
    de Descanso era conteúdo morto e mandava tirar.
    """
    recados = _avisos_do_banco([sala_crua(id=f"T{n:02d}") for n in range(1, 4)])
    assert any("não tem sala de Descanso" in r for r in recados), (
        f"banco sem Descanso tem que ser avisado: {recados}"
    )


def caso_banco_com_uma_sala_de_descanso_passa_calado():
    com_descanso = [sala_crua(id=f"T{n:02d}") for n in range(1, 4)] + [
        sala_crua(
            id="T04", tipo="Descanso", dificuldade=None, cd=None,
            alvo_progresso=None, pericias=[],
        )
    ]
    recados = _avisos_do_banco(com_descanso)
    assert not any("Descanso" in r for r in recados), (
        f"uma sala de Descanso é exatamente o certo, e não pode virar aviso: {recados}"
    )


def caso_banco_com_duas_salas_de_descanso_e_avisado():
    """Só a primeira é usada; a segunda fica no arquivo sem aparecer."""
    descanso = dict(
        tipo="Descanso", dificuldade=None, cd=None, alvo_progresso=None, pericias=[]
    )
    salas = [sala_crua(id=f"T{n:02d}") for n in range(1, 4)] + [
        sala_crua(id="T04", **descanso),
        sala_crua(id="T05", **descanso),
    ]
    recados = _avisos_do_banco(salas)
    assert any("2 salas de Descanso" in r for r in recados), recados
    print("  a sala de Descanso do banco: falta avisa, sobra avisa, uma cala: ok")


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
    caso_o_descanso_nunca_entra_no_pool,
    caso_o_filtro_segue_as_tres_etapas,
    caso_incluir_e_temas_juntos_sao_recusados,
    caso_campo_desconhecido_no_filtro_e_recusado,
    caso_pool_pequeno_demais_e_problema_e_o_apertado_e_aviso,
    caso_incluir_com_id_que_nao_existe_e_problema,
    caso_excluir_id_que_nao_existe_e_so_aviso,
    caso_filtro_que_nao_filtra_e_avisado,
    caso_o_filtro_sobrevive_ao_para_dict,
    caso_a_variante_do_tema_troca_o_bando,
    caso_a_variante_do_tema_tem_a_mesma_queda_por_tier,
    caso_variante_de_tema_que_a_sala_nao_carrega_e_recusada,
    caso_tema_inventado_em_monstros_por_tema_e_recusado,
    caso_o_tema_em_jogo_e_a_interseccao,
    caso_a_escolha_entre_temas_e_estavel_na_mesma_run,
    caso_o_cartao_da_sala_mostra_o_bando_do_tema,
    caso_a_variante_sobrevive_ao_para_dict,
    caso_banco_sem_descanso_e_avisado,
    caso_banco_com_uma_sala_de_descanso_passa_calado,
    caso_banco_com_duas_salas_de_descanso_e_avisado,
    caso_a_planilha_sem_a_coluna_de_tema_continua_importando,
    caso_a_planilha_com_tema_separa_por_ponto_e_virgula,
    caso_o_bestiario_tem_ambiente,
    caso_o_vocabulario_de_ambiente_e_fechado,
    caso_de_lugar_nenhum_e_quem_o_livro_nao_prende,
):
    caso()

print("TESTES DE CONTEUDO PASSARAM")
