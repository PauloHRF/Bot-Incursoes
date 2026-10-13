"""A tabela de fichas do grupo: o importador que a traduz e as duas mecânicas
que ela trouxe — a habilidade que rola ataque contra a CA e a criatura que
deixa condição de verdade em quem falha."""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import condicoes, config, database as db, motor  # noqa: E402
from src.cogs.incursao import Incursoes  # noqa: E402
from src.incursoes import ATAQUE, ErroDeValidacao, de_dict  # noqa: E402
from fakes import (  # noqa: E402
    CANAL,
    GUILD,
    JOGADORES,
    LORE_TESTE,
    ORG_PADRAO,
    FakeBot,
    FakeCanal,
    criar_grupo,
    montar_conteudo,
    sala,
    salas_sem_combate,
)

_ABERTAS = []


def _importador():
    """O importador vive em tools/, fora do pacote: carrega pelo caminho."""
    caminho = RAIZ / "tools" / "importar_fichas.py"
    spec = importlib.util.spec_from_file_location("importar_fichas", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


FICHAS = _importador()


class Dado:
    """Todo dado tira o mesmo número (ou a face máxima, se for menor)."""

    def __init__(self, valor):
        self.valor = valor
        self.d20s = 0

    def randint(self, a, b):
        if b == 20:
            self.d20s += 1
        return min(b, self.valor)

    def choice(self, seq):
        return seq[0]

    def sample(self, seq, n):
        return list(seq)[:n]

    def shuffle(self, seq):
        pass


def monstro_de(bruto):
    incursao = de_dict(
        {
            "id": "t", "nome": "T", "organizacao": ORG_PADRAO, "tamanho": "Curta",
            "lore_inicial": LORE_TESTE, "recompensa_mes": 10, "pontos_conclusao": 10,
            "objetivo": sala("OBJ", "Combate", monstros=[bruto]),
        }
    )
    return incursao.objetivo.monstros


def inimigo_de(monstro, indice=0):
    return motor.Inimigo(
        indice, monstro.nome, monstro.ca, monstro.ataque, monstro.dano,
        monstro.hp, monstro.hp,
        ataques=monstro.ataques, saves=dict(monstro.saves),
        habilidade=monstro.habilidade, golpes=list(monstro.golpes),
        matilha=monstro.matilha,
    )


def alvo(ca=1, hp=500, user_id=1):
    return motor.Combatente(user_id, "Heroi", ca, 0, "1d1", hp, hp)


# ---------------------------------------------------------------- o importador


def caso_recarga_vem_de_cada():
    """`cada: "5-6"` é a recarga no d6, não "a cada N rodadas".

    É a diferença mais perigosa das duas tabelas, porque o bot leria `cada`
    como inteiro, não conseguiria, e cairia no default 2 sem reclamar.
    """
    assert FICHAS._recarga("5-6") == 5
    assert FICHAS._recarga("6") == 6
    assert FICHAS._recarga("4-6") == 4
    assert FICHAS._recarga(None) is None
    print("  'cada: 5-6' vira recarga 5, em vez do silencioso 'a cada 2 rodadas': ok")


def caso_debuff_separa_atordoamento():
    """"Atordoado 2" e "Impedido 3" são o atordoa do bot; o resto é condição."""
    ids, atordoa, estranhos = FICHAS._separar_debuffs(["Envenenado", "Atordoado 2"])
    assert ids == ["envenenado"] and atordoa == 2 and not estranhos

    ids, atordoa, estranhos = FICHAS._separar_debuffs(["Impedido 3"])
    assert ids == [] and atordoa == 3, "sem posicionamento, estar preso é perder a vez"

    ids, atordoa, estranhos = FICHAS._separar_debuffs(["Cegueira"])
    assert estranhos == ["Cegueira"], "condição fora do catálogo é reportada"
    print("  o número no debuff vira rodadas atordoado, e o nome vira condição: ok")


def caso_sequencia_honra_num_acoes():
    """`golpes` é o menu da criatura; `num_acoes` é quantos ela dá por rodada.

    A tabela nunca repete nome de golpe, e o bot lê a lista como a sequência.
    Sem expandir, o Minion com duas armas atacaria duas vezes e o chefe de
    três ações atacaria uma.
    """
    mordida, garra = {"nome": "Mordida"}, {"nome": "Garra"}

    # uma arma, três ações: o mesmo golpe três vezes
    assert FICHAS._sequencia([mordida], 3) == [mordida, mordida, mordida]
    # duas armas, uma ação: vale a principal (a outra fica no `fora` da ficha)
    assert FICHAS._sequencia([mordida, garra], 1) == [mordida]
    # o "uma mordida e duas garras" do livro
    assert FICHAS._sequencia([mordida, garra], 3) == [mordida, garra, garra]
    assert FICHAS._sequencia([], 2) == [], "criatura sem golpe não ganha golpe"
    print("  a sequência de golpes sai de num_acoes, não do tamanho da lista: ok")


def caso_cr_em_texto():
    assert FICHAS._cr(0.125) == "1/8" and FICHAS._cr(0.5) == "1/2"
    assert FICHAS._cr(5) == "5" and FICHAS._cr(19) == "19"
    print("  o CR numérico volta ao texto que o resto do bot escreve: ok")


# ------------------------------------------------------- o que o parser aceita


def caso_habilidade_de_ataque():
    """Com save ATK não há atributo nem CD: a criatura rola contra a CA."""
    troll = monstro_de(
        {
            "nome": "Troll",
            "ca": 15, "ataque": 7, "dano": "2d6+4", "hp": 84,
            "habilidade": {
                "nome": "Golpe Poderoso", "save": "ATK", "dano": "4d6", "alvos": 3,
            },
        }
    )[0]
    assert troll.habilidade.e_ataque and troll.habilidade.save == ATAQUE
    assert troll.habilidade.cd == 0, "ataque não tem CD"
    # volta igual do banco
    volta = monstro_de(troll.para_dict())[0]
    assert volta.habilidade.e_ataque and volta.para_dict() == troll.para_dict()
    print("  a habilidade de ataque passa pelo parser e sobrevive ao banco: ok")


def caso_ataque_sem_dano_e_recusado():
    try:
        monstro_de(
            {
                "nome": "Vazio", "ca": 12, "ataque": 3, "dano": "1d6", "hp": 10,
                "habilidade": {"nome": "Nada", "save": "ATK", "alvos": 1},
            }
        )
    except ErroDeValidacao as erro:
        assert any("precisa de dano" in p for p in erro.problemas), erro.problemas
    else:
        raise AssertionError("habilidade de ataque sem dano não faz nada")
    print("  habilidade de ataque sem dano é recusada: ok")


def caso_habilidade_so_com_debuff():
    """A criatura que só envenena é legítima: antes o parser a recusava."""
    cobra = monstro_de(
        {
            "nome": "Cobra", "ca": 12, "ataque": 4, "dano": "1d4+2", "hp": 10,
            "habilidade": {
                "nome": "Peçonha", "save": "CON", "cd": 12, "debuff": ["envenenado"],
            },
        }
    )[0]
    assert cobra.habilidade.debuff == ["envenenado"]
    assert not cobra.habilidade.dano and not cobra.habilidade.atordoa
    print("  habilidade sem dano, só com debuff, é aceita: ok")


def caso_debuff_pelo_nome_ou_pelo_id():
    bicho = monstro_de(
        {
            "nome": "Bicho", "ca": 12, "ataque": 4, "dano": "1d4", "hp": 10,
            "habilidade": {
                "nome": "Bafo", "save": "CON", "cd": 12,
                "debuff": ["Envenenado", "medo", "Envenenado"],
            },
        }
    )[0]
    assert bicho.habilidade.debuff == ["envenenado", "medo"], "nome ou id, sem repetir"
    print("  o debuff entra pelo nome da ficha ou pelo id, sem repetir: ok")


def caso_condicao_desconhecida_e_buff_sao_recusados():
    def tentar(debuff):
        return monstro_de(
            {
                "nome": "Bicho", "ca": 12, "ataque": 4, "dano": "1d4", "hp": 10,
                "habilidade": {
                    "nome": "Bafo", "save": "CON", "cd": 12, "debuff": [debuff],
                },
            }
        )

    try:
        tentar("Cegueira")
    except ErroDeValidacao as erro:
        assert any("não é uma condição" in p for p in erro.problemas), erro.problemas
    else:
        raise AssertionError("errar o nome do debuff sumiria com ele em silêncio")

    try:
        tentar("bencao")
    except ErroDeValidacao as erro:
        assert any("não dá buff" in p for p in erro.problemas), erro.problemas
    else:
        raise AssertionError("criatura não abençoa o grupo")
    print("  condição inventada e buff de criatura são recusados: ok")


# ----------------------------------------------------------------- no combate


def _troll():
    return monstro_de(
        {
            "nome": "Troll",
            "ca": 15, "ataque": 7, "dano": "2d6+4", "hp": 84,
            "habilidade": {
                "nome": "Golpe Poderoso", "save": "ATK", "dano": "4d6", "alvos": 1,
            },
        }
    )[0]


def caso_ataque_acerta_e_erra():
    """O alvo não rola nada: a CA dele decide sozinha."""
    inimigo = inimigo_de(_troll())
    heroi = alvo(ca=1)
    # d20 = 10, +7 = 17 contra CA 1: acerta. 4d6 com todo dado em 6 = 24.
    investida = motor.investir_atacando(inimigo, inimigo.habilidade, heroi, Dado(10))
    assert investida.ataque is not None and investida.save is None
    assert not investida.escapou and investida.dano == 24
    assert heroi.hp_atual == 500 - 24, "o dano sai do HP do alvo"

    # CA 99: 10 + 7 não chega, e nada acontece
    blindado = alvo(ca=99)
    investida = motor.investir_atacando(inimigo, inimigo.habilidade, blindado, Dado(10))
    assert investida.escapou and investida.dano == 0
    assert blindado.hp_atual == 500
    print("  a habilidade de ataque acerta pela CA, e errar não faz nada: ok")


def caso_ataque_pega_vantagem_de_matilha():
    """A habilidade de ataque é um ataque: a Matilha vale nela também."""
    lobo = monstro_de(
        {
            "nome": "Lobo", "ca": 13, "ataque": 4, "dano": "2d4+2", "hp": 11,
            "matilha": "x",
            "habilidade": {
                "nome": "Investida", "save": "ATK", "dano": "2d6", "alvos": 1,
            },
        }
    )[0]
    sozinho = inimigo_de(lobo)
    estado = motor.EstadoCombate([sozinho], 1, [alvo()])
    dado = Dado(10)
    motor.usar_habilidade_do_inimigo(sozinho, estado, dado)
    assert dado.d20s == 1, "sem outro lobo de pé, sem vantagem"

    par = [inimigo_de(lobo, 0), inimigo_de(lobo, 1)]
    estado = motor.EstadoCombate(par, 1, [alvo()])
    dado = Dado(10)
    motor.usar_habilidade_do_inimigo(par[0], estado, dado)
    assert dado.d20s == 2, "com o outro lobo de pé, rola dois d20"
    print("  Táticas de Matilha dão vantagem na habilidade de ataque: ok")


def caso_debuff_so_em_quem_falha():
    cobra = monstro_de(
        {
            "nome": "Cobra", "ca": 12, "ataque": 4, "dano": "1d4+2", "hp": 10,
            "habilidade": {
                "nome": "Peçonha", "save": "CON", "cd": 12, "debuff": ["envenenado"],
            },
        }
    )[0]
    inimigo = inimigo_de(cobra)
    # d20 = 2: falha o CON CD 12
    investida = motor.impor_save(inimigo, inimigo.habilidade, alvo(), Dado(2))
    assert not investida.escapou and investida.debuffs == ["envenenado"]
    # d20 = 18: passa, e não leva nada
    investida = motor.impor_save(inimigo, inimigo.habilidade, alvo(), Dado(18))
    assert investida.escapou and investida.debuffs == []
    print("  o debuff da criatura só pega quem falha no save: ok")


def caso_quem_cai_nao_leva_debuff():
    """Quem o dano derruba já está fora da sala: não carrega condição."""
    bicho = monstro_de(
        {
            "nome": "Bicho", "ca": 12, "ataque": 4, "dano": "1d4", "hp": 10,
            "habilidade": {
                "nome": "Bafo", "save": "CON", "cd": 12, "dano": "10d6",
                "debuff": ["envenenado"],
            },
        }
    )[0]
    fraco = alvo(hp=5)
    investida = motor.impor_save(inimigo_de(bicho), bicho.habilidade, fraco, Dado(2))
    assert fraco.caido and investida.debuffs == []
    print("  quem cai com o dano não leva a condição: ok")


# ------------------------------------------------------- do combate ao banco


async def caso_condicao_da_criatura_fica_na_run():
    """O Envenenado da aranha vai para a mesma tabela que a armadilha usa."""
    config.DB_PATH = Path(__file__).resolve().parent / "teste_fichas.db"
    config.DB_PATH.unlink(missing_ok=True)
    config.TAMANHO_GRUPO = 5
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    await criar_grupo(conn, nivel=8)
    cog = Incursoes(FakeBot(conn, FakeCanal(CANAL)))
    incursao, _ = montar_conteudo(
        cog, tamanho="Curta", salas=salas_sem_combate(),
        monstro_objetivo={
            "nome": "Aranha", "ca": 12, "ataque": 4, "dano": "1d4", "hp": 10,
            "habilidade": {
                "nome": "Peçonha", "save": "CON", "cd": 99, "debuff": ["envenenado"],
            },
        },
    )
    run_id = await db.criar_run(conn, GUILD, CANAL, incursao.id, JOGADORES[0])
    personagem = await db.personagem_por_nome(
        conn, GUILD, JOGADORES[0], f"Heroi{JOGADORES[0]}"
    )
    await db.adicionar_participante(conn, run_id, JOGADORES[0], personagem["id"])
    await db.inicializar_hp(conn, run_id)
    run = await db.buscar_run(conn, run_id)

    heroi = alvo(user_id=JOGADORES[0])
    investida = motor.Investida(
        "Aranha", "Peçonha", heroi, save=None, debuffs=["envenenado"]
    )
    linhas = await cog._guardar_debuffs(run, [investida])
    assert linhas and "Envenenado" in linhas[0]
    carregadas = await db.condicoes_de(conn, run_id, JOGADORES[0])
    assert carregadas.get("envenenado") == 1, "a condição ficou na run"

    # de novo: empilha, como a da armadilha
    await cog._guardar_debuffs(run, [investida])
    carregadas = await db.condicoes_de(conn, run_id, JOGADORES[0])
    assert carregadas.get("envenenado") == 2
    # e pesa igual: a penalidade sai do mesmo catálogo
    saldo = condicoes.penalidades(carregadas)
    esperado = 2 * condicoes.POR_ID["envenenado"].ataque
    assert saldo.ataque == esperado
    print("  a condição da criatura entra na run e pesa como a da armadilha: ok")


async def main():
    try:
        caso_recarga_vem_de_cada()
        caso_debuff_separa_atordoamento()
        caso_sequencia_honra_num_acoes()
        caso_cr_em_texto()
        caso_habilidade_de_ataque()
        caso_ataque_sem_dano_e_recusado()
        caso_habilidade_so_com_debuff()
        caso_debuff_pelo_nome_ou_pelo_id()
        caso_condicao_desconhecida_e_buff_sao_recusados()
        caso_ataque_acerta_e_erra()
        caso_ataque_pega_vantagem_de_matilha()
        caso_debuff_so_em_quem_falha()
        caso_quem_cai_nao_leva_debuff()
        await caso_condicao_da_criatura_fica_na_run()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        (Path(__file__).resolve().parent / "teste_fichas.db").unlink(missing_ok=True)


asyncio.run(main())
print("TESTES DAS FICHAS PASSARAM")
