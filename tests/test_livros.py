"""O banco de criaturas dos livros 2024 do 5etools: o que o bot lê de
`data/criaturas/` e as regras do conversor (`tools/importar_livro.py`).

As regras de conversão são de desenho, decididas com o dono em 26/11/2026: a
tabela fixa de condição, a CD de 12 + ataque para a condição que o livro impõe
sem teste, o "e usa X" do Multiattack como habilidade. Cada caso daqui cobra
uma delas com uma criatura de mentira no formato do livro, para não depender
do arquivo baixado.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import bestiario  # noqa: E402
from src.incursoes import _monstros_de_dict  # noqa: E402
from src.rules import chave_comparacao  # noqa: E402


def _conversor():
    """O conversor vive em tools/, fora do pacote: carrega pelo caminho."""
    caminho = RAIZ / "tools" / "importar_livro.py"
    spec = importlib.util.spec_from_file_location("importar_livro", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


L = _conversor()


def criatura(nome="Teste", cr="3", acoes=(), **resto):
    """Uma criatura mínima no formato 2024 do 5etools."""
    base = {
        "name": nome, "source": "TST", "type": "fiend", "cr": cr, "ac": [14],
        "hp": {"average": 40, "formula": "9d8"},
        "str": 14, "dex": 12, "con": 14, "int": 10, "wis": 10, "cha": 10,
        "action": [{"name": n, "entries": [e]} for n, e in acoes],
    }
    base.update(resto)
    return base


SLAM = ("Slam", "{@atkr m} {@hit 4}, reach 5 ft. {@h}4 ({@damage 1d4 + 2}) Bludgeoning damage.")


# ------------------------------------------------------------ o banco no bot

def caso_os_livros_entram_na_busca():
    todas = bestiario.carregar()
    do_mm = bestiario.carregar(livros=None)
    livros = sorted(bestiario.PASTA_DOS_LIVROS.glob("*.json"))
    assert livros, "nenhum livro em data/criaturas/"
    assert len(todas) > len(do_mm) == 385, (len(todas), len(do_mm))
    bestiario.recarregar()
    ceifador = bestiario.buscar("Diabo Ceifador")
    assert ceifador and ceifador["nome_en"] == "Harvester Devil"
    assert bestiario.buscar("harvester devil") is ceifador, "o nome em inglês também vale"
    assert not any(c["nome_en"] == "Harvester Devil" for c in do_mm)
    print(f"  os {len(livros)} livro(s) somam {len(todas) - len(do_mm)} criaturas à busca: ok")


def caso_nenhum_nome_se_repete_no_bestiario_inteiro():
    """A busca é por nome: dois iguais e o último indexado ganharia calado."""
    donos: dict[str, str] = {}
    repetidos = []
    for c in bestiario.carregar():
        nomes = {chave_comparacao(n) for n in (c.get("nome"), c.get("nome_en"), c.get("id")) if n}
        for chave in nomes:
            if chave in donos and donos[chave] != c["nome_en"]:
                repetidos.append(f"{chave}: {donos[chave]} e {c['nome_en']}")
            donos[chave] = c["nome_en"]
    assert not repetidos, repetidos[:5]
    print("  nenhum nome repete entre o Monster Manual e os livros: ok")


def caso_toda_criatura_dos_livros_fecha_no_leitor_das_salas():
    for arquivo in sorted(bestiario.PASTA_DOS_LIVROS.glob("*.json")):
        criaturas = bestiario.carregar(arquivo=Path("nao-existe"), livros=arquivo.parent)
        for c in criaturas:
            problemas: list[str] = []
            _monstros_de_dict(dict(c), c["nome_en"], problemas)
            assert not problemas, (c["nome_en"], problemas)
            meta = c["meta"]
            assert meta.get("fonte"), f"{c['nome_en']} sem o livro de origem"
            assert meta["tier"] == bestiario.tier_do_cr(bestiario.cr_de(c)), c["nome_en"]
            assert meta["num_acoes"] == len(c["golpes"]), c["nome_en"]
    print("  toda criatura dos livros passa pelo leitor das salas: ok")


# ------------------------------------------------------------ o conversor

def caso_o_multiataque_que_usa_uma_acao_vira_golpes_mais_habilidade():
    entrada, _ = L.converter(criatura(acoes=[
        ("Multiattack", "The icon makes two Slam attacks and uses Fiery Eruption."),
        SLAM,
        ("Fiery Eruption", "{@actSave dex} {@dc 11}, each creature in a 5-foot "
         "{@variantrule Emanation [Area of Effect]|XPHB|Emanation} originating from the icon. "
         "{@actSaveFail} 7 ({@damage 2d6}) Fire damage."),
    ]), "tst")
    assert [g["nome"] for g in entrada["golpes"]] == ["Pancada", "Pancada"]
    h = entrada["habilidade"]
    assert (h["save"], h["cd"], h["dano"], h["alvos"], h["cada"]) == ("DES", 11, "2d6", 3, 2), h
    assert "metade" not in h, "sem {@actSaveSuccess} não há metade"
    print("  'faz dois golpes e usa X' vira dois golpes e X como habilidade: ok")


def caso_alternativa_no_multiataque_vale_a_primeira_arma():
    entrada, _ = L.converter(criatura(acoes=[
        ("Multiattack", "The beast makes three attacks, using Bite or Claws in any combination."),
        ("Bite", "{@atkr m} {@hit 9}, reach 5 ft. {@h}23 ({@damage 4d8 + 5}) Piercing damage."),
        ("Claws (Land Form Only)", "{@atkr m} {@hit 9}, reach 5 ft. {@h}18 ({@damage 3d8 + 5}) "
         "Slashing damage."),
    ]), "tst")
    assert [g["dano"] for g in entrada["golpes"]] == ["4d8+5"] * 3, entrada["golpes"]
    print("  'três ataques, usando A ou B' são três de A: ok")


def caso_condicao_sem_teste_ganha_cd_de_doze_mais_o_ataque():
    entrada, avisos = L.converter(criatura(acoes=[
        ("Brain-Rending Bite", "{@atkr m} {@hit 3}, reach 5 ft. {@h}3 ({@damage 1d4 + 1}) "
         "Piercing damage plus 3 ({@damage 1d6}) Psychic damage, and the target has the "
         "{@condition Frightened|XPHB} condition until the start of the head's next turn."),
    ]), "tst")
    golpe = entrada["golpes"][0]
    assert golpe["dano"] == "1d4+1+1d6", golpe
    efeito = golpe["efeito"]
    assert (efeito["save"], efeito["cd"], efeito["debuff"]) == ("SAB", 3 + 12, ["medo"]), efeito
    assert any("sem teste" in a for a in avisos), avisos
    print("  condição sem teste no livro vira SAB CD 12 + ataque no bot: ok")


def caso_a_tabela_de_condicoes():
    # A tabela inteira, como ele aprovou: trocar uma linha é decisão de
    # desenho, e tem de aparecer aqui em vermelho antes de mudar o conteúdo.
    assert L.CONDICOES == {
        "frightened": "medo", "poisoned": "envenenado", "blinded": "perdicao",
        "exhaustion": "exaustao",
        "paralyzed": L.VEZ, "stunned": L.VEZ, "incapacitated": L.VEZ,
        "restrained": L.VEZ, "unconscious": L.VEZ, "petrified": L.VEZ,
        "charmed": L.VEZ,
    }, L.CONDICOES
    debuffs, rodadas, repete = L.condicoes_do_trecho(
        "The target has the {@condition Paralyzed|XPHB} condition and repeats the save at "
        "the end of each of its turns, ending the effect on itself on a success.", [], "x")
    assert (debuffs, rodadas, repete) == ([], L.RODADAS_COM_REPETE, True)
    debuffs, rodadas, repete = L.condicoes_do_trecho(
        "The target has the {@condition Stunned|XPHB} condition until the end of the devil's "
        "next turn.", [], "x")
    assert (debuffs, rodadas, repete) == ([], 1, False)
    debuffs, _, _ = L.condicoes_do_trecho(
        "The target's {@variantrule Hit Points|XPHB|Hit Point} maximum decreases by an amount "
        "equal to the Necrotic damage taken, and it has the {@condition Poisoned|XPHB} "
        "condition. It also gains 1 {@condition Exhaustion|XPHB} level.", [], "x")
    assert sorted(debuffs) == ["deterioracao", "envenenado", "exaustao"], debuffs
    debuffs, rodadas, _ = L.condicoes_do_trecho(
        "The target has the {@condition Prone|XPHB} condition. If the target is already "
        "{@condition Frightened|XPHB}, it takes an extra 7 ({@damage 2d6}) Psychic damage.",
        [], "x")
    assert (debuffs, rodadas) == ([], 0), "derrubado não faz nada, e 'se já estiver' não conta"
    print("  a tabela de condições de 26/11 (perde a vez, debuffs, o que não conta): ok")


def caso_dano_extra_condicional_fica_de_fora():
    entrada, avisos = L.converter(criatura(acoes=[
        ("Flail", "{@atkr m} {@hit 6}, reach 5 ft. {@h}8 ({@damage 1d8 + 4}) Bludgeoning "
         "damage—plus 7 ({@damage 2d6}) Necrotic damage if the commander is Bloodied—and "
         "the target has Disadvantage on its next attack roll."),
    ]), "tst")
    assert entrada["golpes"][0]["dano"] == "1d8+4", entrada["golpes"][0]
    assert any("condicional" in a for a in avisos), avisos
    print("  dano extra 'se estiver Sangrando' não entra no golpe: ok")


def caso_ataque_com_recarga_vira_habilidade_de_ataque():
    entrada, _ = L.converter(criatura(cr="10", acoes=[
        ("Multiattack", "The priest makes two Shadow Blast attacks."),
        ("Shadow Blast", "{@atkr m,r} {@hit 10}, reach 10 ft. {@h}17 ({@damage 2d10 + 6}) "
         "Psychic damage."),
        ("Dark Reckoning {@recharge 5}", "{@atkr r} {@hit 10}, range 120 ft. {@h}33 "
         "({@damage 6d10}) Necrotic damage, and the target is cursed."),
    ]), "tst")
    assert len(entrada["golpes"]) == 2
    assert all(g["dano"] == "2d10+6" for g in entrada["golpes"])
    h = entrada["habilidade"]
    assert (h["save"], h["dano"], h["recarga"]) == ("ATK", "6d10", 5), h
    print("  ataque com recarga sai da sequência e vira habilidade de ATK: ok")


def caso_acao_bonus_so_entra_sem_acao_especial():
    utterance = {"name": "Utterance of Unmaking", "entries": [
        "{@actSave con} {@dc 18}, each creature in a 20-foot "
        "{@variantrule Emanation [Area of Effect]|XPHB|Emanation} originating from the devil. "
        "{@actSaveFail} 22 ({@damage 4d10}) Force damage. {@actSaveSuccess} Half damage."]}
    entrada, avisos = L.converter(criatura(acoes=[SLAM], bonus=[utterance]), "tst")
    assert entrada["habilidade"]["dano"] == "4d10" and entrada["habilidade"]["metade"]
    assert any("ação bônus" in a for a in avisos), avisos

    eruption = ("Fiery Eruption", "{@actSave dex} {@dc 11}, one creature. "
                "{@actSaveFail} 7 ({@damage 2d6}) Fire damage.")
    entrada, _ = L.converter(criatura(acoes=[SLAM, eruption], bonus=[utterance]), "tst")
    assert entrada["habilidade"]["nome"] == "Erupção Ígnea", "a ação vem antes da bônus"
    print("  a ação bônus só vira habilidade quando não há ação especial: ok")


def caso_o_que_fica_fora_do_banco():
    casos = {
        "reimpressão": criatura(_copy={"name": "Ankheg", "source": "XMM"}),
        "sem CR": criatura(cr="None", acoes=[SLAM]),
        "invocação": criatura(acoes=[SLAM], hp={"special": "5 + 5 per spell level"}),
        "repetida do MM": criatura(nome="Drow Priestess of Lolth", acoes=[SLAM]),
        "sem ataque": criatura(acoes=[("Gaze", "It looks around.")]),
    }
    for motivo, m in casos.items():
        entrada, _ = L.converter(m, "tst")
        assert entrada is None, f"{motivo} não podia entrar"
    entrada, _ = L.converter(criatura(acoes=[SLAM]), "tst")
    assert entrada is not None
    print("  reimpressão, sem CR, invocação, a Drow do MM e sem ataque ficam de fora: ok")


def caso_personagem_nomeado_mantem_o_nome():
    entrada, avisos = L.converter(criatura(nome="Fiendish Icon", acoes=[SLAM]), "tst")
    assert entrada["nome"] == "Ícone Infernal", "genérica é traduzida"
    entrada, avisos = L.converter(
        criatura(nome="Fiendish Icon", acoes=[SLAM], isNamedCreature=True), "tst")
    assert entrada["nome"] == "Fiendish Icon", "nomeada fica como o livro escreve"
    assert entrada["meta"]["nomeada"] is True
    assert "nome sem tradução" not in avisos
    print("  genérica traduzida, personagem com nome intacto: ok")


def main():
    caso_os_livros_entram_na_busca()
    caso_nenhum_nome_se_repete_no_bestiario_inteiro()
    caso_toda_criatura_dos_livros_fecha_no_leitor_das_salas()
    caso_o_multiataque_que_usa_uma_acao_vira_golpes_mais_habilidade()
    caso_alternativa_no_multiataque_vale_a_primeira_arma()
    caso_condicao_sem_teste_ganha_cd_de_doze_mais_o_ataque()
    caso_a_tabela_de_condicoes()
    caso_dano_extra_condicional_fica_de_fora()
    caso_ataque_com_recarga_vira_habilidade_de_ataque()
    caso_acao_bonus_so_entra_sem_acao_especial()
    caso_o_que_fica_fora_do_banco()
    caso_personagem_nomeado_mantem_o_nome()


main()
print("TESTES DOS LIVROS PASSARAM")
