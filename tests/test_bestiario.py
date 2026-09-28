"""O bestiário: criatura pelo nome, golpes diferentes, teste no golpe, metade
do dano no sucesso, Táticas de Matilha e Regeneração."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import bestiario, config, database as db, motor  # noqa: E402
from src.cogs.incursao import Incursoes  # noqa: E402
from src.incursoes import ErroDeValidacao, de_dict  # noqa: E402
from fakes import (  # noqa: E402
    CANAL,
    GUILD,
    JOGADORES,
    LORE_TESTE,
    ORG_PADRAO,
    FakeBot,
    FakeCanal,
    atacar_ate_cair,
    criar_grupo,
    montar_conteudo,
    sala,
    salas_sem_combate,
)

_ABERTAS = []


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


def monstro_de(bruto: dict):
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
        saves_vantagem=list(monstro.saves_vantagem), habilidade=monstro.habilidade,
        golpes=list(monstro.golpes), matilha=monstro.matilha,
        regeneracao=monstro.regeneracao,
    )


def alvo(ca=1, hp=500):
    return motor.Combatente(1, "Heroi", ca, 0, "1d1", hp, hp)


def caso_busca_por_nome():
    lobo = bestiario.buscar("Lobo")
    assert lobo and lobo["nome_en"] == "Wolf"
    assert bestiario.buscar("wolf") is lobo, "o nome em inglês também vale"
    assert bestiario.buscar("CARNICAL")["nome"] == "Carniçal", "sem acento e sem caixa"
    assert bestiario.buscar("Criatura Inventada") is None
    print("  acha a criatura em português, em inglês e sem acento: ok")


def caso_sala_so_com_nome():
    lobos = monstro_de({"nome": "Wolf", "quantidade": 3})
    assert [m.nome for m in lobos] == ["Lobo 1", "Lobo 2", "Lobo 3"]
    lobo = lobos[0]
    assert (lobo.ca, lobo.hp, lobo.ataque) == (13, 11, 4)
    assert lobo.matilha and lobo.saves["DES"] == 2, "save que falta sai do atributo"

    # volta igual do JSON, com os golpes e o teste da garra
    carnical = monstro_de({"nome": "Carniçal"})[0]
    assert carnical.golpes[0].efeito.atordoa == 1
    volta = monstro_de(carnical.para_dict())[0]
    assert volta.para_dict() == carnical.para_dict()

    # criatura que não está no livro e não traz os números
    try:
        monstro_de({"nome": "Criatura Inventada"})
    except ErroDeValidacao as erro:
        assert any("bestiário" in p for p in erro.problemas), erro.problemas
    else:
        raise AssertionError("sem números e fora do bestiário, a sala é recusada")
    print("  a sala que só diz o nome recebe os números do livro: ok")


def caso_golpes_diferentes():
    dragao = monstro_de({"nome": "Dragão Vermelho Jovem"})[0]
    inimigo = inimigo_de(dragao)
    inimigo.habilidade = None  # só os golpes, sem o sopro
    estado = motor.EstadoCombate([inimigo], 1, [alvo()])
    vez = motor.turno_do_inimigo(inimigo, estado, Dado(10))
    assert [g.arma for g, _ in vez.golpes] == ["Mordida", "Garra", "Garra"]
    assert [g.bonus for g, _ in vez.golpes] == [10, 10, 10]
    # mordida 2d10+6+1d6, garra 2d6+6, com todo dado tirando o máximo até 10
    assert [g.dano for g, _ in vez.golpes] == [32, 18, 18]
    print("  o dragão morde e arranha duas vezes, cada golpe com seu dano: ok")


def caso_teste_no_golpe():
    carnical = monstro_de({"nome": "Carniçal"})[0]
    heroi = alvo()
    estado = motor.EstadoCombate([inimigo_de(carnical)], 1, [heroi])
    # d20 = 5: acerta CA 1 e falha o CON CD 10
    vez = motor.turno_do_inimigo(estado.inimigos[0], estado, Dado(5))
    assert vez.golpes[0][0].acertou
    investida = vez.efeitos_dos_golpes[0]
    assert investida.do_golpe and investida.atordoou and investida.repete_save
    assert heroi.atordoado

    # errou o golpe: não há teste
    armadura = alvo(ca=99)
    estado = motor.EstadoCombate([inimigo_de(carnical)], 1, [armadura])
    vez = motor.turno_do_inimigo(estado.inimigos[0], estado, Dado(5))
    assert not vez.golpes[0][0].acertou and not vez.investidas
    assert not armadura.atordoado
    print("  a garra do carniçal só paralisa quando acerta: ok")


def caso_metade_no_sucesso():
    aranha = monstro_de({"nome": "Aranha Gigante"})[0]
    efeito = aranha.golpes[0].efeito
    assert efeito.metade and efeito.dano == "2d8" and not efeito.atordoa
    heroi = alvo()
    inimigo = inimigo_de(aranha)
    # d20 = 15 passa no CON CD 11: o veneno (2d8 = 16) cai pela metade
    investida = motor.impor_save(inimigo, efeito, heroi, Dado(15))
    assert investida.escapou and investida.dano == 8
    # quem falha leva inteiro
    investida = motor.impor_save(inimigo, efeito, alvo(), Dado(2))
    assert not investida.escapou and investida.dano == 4
    print("  sucesso no save leva metade do dano: ok")


def caso_matilha():
    lobos = monstro_de({"nome": "Lobo", "quantidade": 2})
    sozinho = inimigo_de(lobos[0])
    dado = Dado(10)
    motor.turno_do_inimigo(sozinho, motor.EstadoCombate([sozinho], 1, [alvo()]), dado)
    assert dado.d20s == 1, "sem outro lobo de pé, sem vantagem"

    par = [inimigo_de(lobos[0], 0), inimigo_de(lobos[1], 1)]
    dado = Dado(10)
    motor.turno_do_inimigo(par[0], motor.EstadoCombate(par, 1, [alvo()]), dado)
    assert dado.d20s == 2, "com o outro lobo de pé, rola dois d20"
    print("  Táticas de Matilha dão vantagem com um aliado de pé: ok")


def caso_regeneracao():
    troll = inimigo_de(monstro_de({"nome": "Troll"})[0])
    assert troll.regeneracao == 10
    troll.hp_atual = 50
    vez = motor.turno_do_inimigo(troll, motor.EstadoCombate([troll], 1, [alvo()]), Dado(10))
    assert vez.regenerou == 10 and troll.hp_atual == 60
    troll.hp_atual = troll.hp_max - 3
    vez = motor.turno_do_inimigo(troll, motor.EstadoCombate([troll], 1, [alvo()]), Dado(10))
    assert vez.regenerou == 3, "não passa do HP máximo"
    troll.hp_atual = 0
    vez = motor.turno_do_inimigo(troll, motor.EstadoCombate([troll], 1, [alvo()]), Dado(10))
    assert vez.regenerou == 0 and troll.hp_atual == 0, "caído não regenera"
    print("  a regeneração cura no começo da vez, até o máximo: ok")


async def caso_combate_com_criatura_do_livro():
    config.DB_PATH = Path(__file__).resolve().parent / "teste_bestiario.db"
    config.DB_PATH.unlink(missing_ok=True)
    config.TAMANHO_GRUPO = 5
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    await criar_grupo(conn, nivel=8)
    canal = FakeCanal(CANAL)
    cog = Incursoes(FakeBot(conn, canal))
    incursao, _ = montar_conteudo(
        cog, tamanho="Curta", monstro_objetivo={"nome": "Carniçal", "quantidade": 2},
        salas=salas_sem_combate(),
    )
    run_id = await db.criar_run(conn, GUILD, CANAL, incursao.id, JOGADORES[0])
    for user_id in JOGADORES[:2]:
        personagem = await db.personagem_por_nome(conn, GUILD, user_id, f"Heroi{user_id}")
        await db.adicionar_participante(conn, run_id, user_id, personagem["id"])
    await db.inicializar_hp(conn, run_id)
    await db.atualizar_run(
        conn, run_id, status="objetivo", sala_atual="OBJ", linha_atual=incursao.passos + 1
    )
    run = await db.buscar_run(conn, run_id)
    await cog._abrir_combate(run, incursao.objetivo)

    # o banco guarda os golpes com o teste, e o estado volta inteiro dele
    estado = await cog._estado_combate(run, incursao.objetivo)
    garra = estado.inimigos[0].golpes[0]
    assert garra.nome == "Garras" and garra.efeito.save == "CON"

    await atacar_ate_cair(conn, canal, cog, run_id, "OBJ", limite=60)
    final = await db.buscar_run(conn, run_id)
    assert final["status"] != "objetivo", "o combate chegou ao fim"
    print("  combate inteiro contra criaturas do bestiário: ok")


async def main():
    try:
        caso_busca_por_nome()
        caso_sala_so_com_nome()
        caso_golpes_diferentes()
        caso_teste_no_golpe()
        caso_metade_no_sucesso()
        caso_matilha()
        caso_regeneracao()
        await caso_combate_com_criatura_do_livro()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        (Path(__file__).resolve().parent / "teste_bestiario.db").unlink(missing_ok=True)


asyncio.run(main())
print("TESTES DO BESTIÁRIO PASSARAM")
