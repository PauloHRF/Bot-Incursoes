"""Habilidades de classe: o catálogo, as passivas que já valem e o multiataque."""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import (  # noqa: E402
    classes as cl,
    config,
    database as db,
    habilidades as hb,
    motor,
)
from src.cogs.ficha import Ficha, embed_ficha  # noqa: E402
from src.cogs.incursao import Incursoes  # noqa: E402
from src.rules import TIER_MAXIMO, mod_pericia  # noqa: E402
from fakes import (  # noqa: E402
    CANAL,
    INDEFESO,
    JOGADORES,
    FakeBot,
    FakeCanal,
    FakeInteraction,
    criar_grupo,
    montar_conteudo,
    salas_sem_combate,
)

_ABERTAS = []


async def preparar(classe="guerreiro", nivel=8):
    while _ABERTAS:
        try:
            await _ABERTAS.pop().close()
        except Exception:
            pass
    config.DB_PATH = Path(__file__).resolve().parent / "teste_habilidades.db"
    config.DB_PATH.unlink(missing_ok=True)
    config.TAMANHO_GRUPO = 5
    conn = await db.conectar()
    _ABERTAS.append(conn)
    await db.criar_schema(conn)
    await criar_grupo(conn, nivel=nivel, classe=classe)
    canal = FakeCanal(CANAL)
    cog = Incursoes(FakeBot(conn, canal))
    return conn, canal, cog


def inimigo(hp=100, ca=1):
    return motor.Inimigo(0, "Alvo", ca, 0, "1d1", hp, hp)


def caso_texto_bate_com_a_mecanica():
    """Todo dado que a habilidade ROLA tem de estar escrito no texto dela.

    E o erro que nenhum outro teste pega: enfraquecer o Cone of Cold de 12d8
    para 8d8 na `acao` e deixar o texto dizendo 12d8 passa por toda a suite,
    porque a mecanica esta certa — so a promessa ao jogador e que fica
    mentindo. Aconteceu, e e por isso que este caso existe.

    A checagem e de um lado so: o texto pode citar dado que a `acao` nao tem
    (a descricao de uma escolha fala das opcoes), mas nao pode OMITIR nem
    CONTRADIZER o que vai rolar.
    """
    DADO = re.compile(r"[0-9]+d[0-9]+")
    ONDE_ROLA = ("dano", "thp", "cura", "dano_por_rodada", "dano_extra")
    mudas = []
    for classe, tiers in hb.HABILIDADES.items():
        for tier, lista in tiers.items():
            for h in lista:
                acao = h.acao or {}
                if acao.get("tipo") == "invocar":
                    # Invocacao nao: o dado e da CRIATURA, e ela entra na sala
                    # com a ficha dela a vista. Exigir o dado no texto da
                    # magia seria pedir que ele repetisse a carta do bicho.
                    continue
                rolados = [
                    acao[k] for k in ONDE_ROLA
                    if isinstance(acao.get(k), str) and DADO.search(acao[k])
                ]
                escritos = set()
                for texto in (h.texto, *(
                    o.get("texto", "") for o in
                    ((h.escolha or {}).get("opcoes") or [])
                )):
                    escritos |= set(DADO.findall(texto or ""))
                for expressao in rolados:
                    for dado in DADO.findall(expressao):
                        if dado not in escritos:
                            mudas.append(
                                f"{classe} T{tier} {h.id}: rola {dado} "
                                f"({expressao}), o texto nao diz"
                            )
    assert not mudas, "texto nao bate com a mecanica: " + "; ".join(mudas)
    print("  todo dado que a habilidade rola esta escrito no texto: ok")


def caso_catalogo_completo():
    """Toda classe tem habilidade em todos os tiers, e nada fica sem texto."""
    for classe in cl.CLASSES.values():
        for t in range(1, TIER_MAXIMO + 1):
            do_tier = classe.habilidades_do_tier(t)
            assert do_tier, f"{classe.nome} sem habilidade no tier {t}"
            for h in do_tier:
                assert h.nome and h.texto, (classe.nome, t)
                assert h.tipo in (cl.PASSIVA, cl.ATIVA, cl.ESCOLHA), h.tipo
                # so passiva tem efeito automatico
                if h.efeito:
                    assert h.tipo == cl.PASSIVA, (classe.nome, h.nome)

    # ids unicos dentro da classe, para o dia em que virarem registro de uso
    for classe in cl.CLASSES.values():
        ids = [h.id for _t, h in classe.habilidades_ate(TIER_MAXIMO * 2)]
        assert len(ids) == len(set(ids)), (classe.nome, ids)

    # a lista acumula com o nivel
    assert len(cl.habilidades("guerreiro", 1)) == 1
    assert len(cl.habilidades("guerreiro", 10)) > len(cl.habilidades("guerreiro", 3))
    print("  catalogo: toda classe tem habilidade em todo tier: ok")


def caso_efeitos_se_somam():
    """A versão mais forte substitui a fraca, em vez de somar em cima."""
    # Reliable Talent: +5 no tier 1, +10 no tier 5 (nao +15)
    assert cl.efeitos("ladino", 1)["bonus_teste"] == 5
    assert cl.efeitos("ladino", 9)["bonus_teste"] == 10

    # Improved Critical desce o limiar do critico
    assert cl.efeitos("guerreiro", 5)["critico_em"] == 20
    assert cl.efeitos("guerreiro", 7)["critico_em"] == 19

    # Multiattack chega no tier 3 para quem tem
    assert cl.efeitos("guerreiro", 4)["ataques"] == 1
    assert cl.efeitos("guerreiro", 5)["ataques"] == 2
    assert cl.efeitos("paladino", 10)["ataques"] == 1, "Paladino nao tem multiataque"

    # dano extra do Paladino e o condicional do Patrulheiro
    assert cl.efeitos("paladino", 3)["dano_extra"] == 2
    assert cl.efeitos("patrulheiro", 3)["dano_ferido"] == 2
    assert cl.efeitos("patrulheiro", 3)["dano_extra"] == 0

    # classe sem passiva numerica devolve o neutro
    assert cl.efeitos("barbaro", 1) == dict(cl.efeitos("barbaro", 1), **{"ataques": 1})
    print("  efeitos: a passiva mais forte substitui a mais fraca: ok")


def caso_bonus_de_pericia():
    """As passivas de perícia entram no modificador do teste."""
    monge = cl.classe("monge")
    numeros = monge.numeros(7)  # tier 4: Mente e Corpo
    efeitos = cl.efeitos("monge", 7)
    treinadas = ["Acrobacia"]

    # com proficiencia (+10 no tier 4) e mais +2 da passiva
    assert mod_pericia("Acrobacia", numeros, treinadas, None, efeitos) == 12
    # sem proficiencia, o +2 vale igual
    assert mod_pericia("Percepção", numeros, treinadas, None, efeitos) == 7
    # pericia fora da lista da passiva nao ganha nada
    assert mod_pericia("Arcanismo", numeros, treinadas, None, efeitos) == 5

    # o Ladino soma em tudo, nao numa lista
    ladino, ef_ladino = cl.classe("ladino").numeros(1), cl.efeitos("ladino", 1)
    assert mod_pericia("Arcanismo", ladino, [], None, ef_ladino) == 8
    print("  as passivas de pericia entram no modificador: ok")


class Dado:
    """Dado de teste: devolve os valores na ordem, depois o maximo da face."""

    def __init__(self, valores):
        self.valores = list(valores)

    def randint(self, a, b):
        return self.valores.pop(0) if self.valores else b

    def choice(self, seq):
        return seq[0]


def caso_critico_em_dezenove():
    guerreiro = motor.Combatente(1, "G", 20, 40, "1d1", 50, 50, critico_em=19)
    alvo = inimigo()

    golpe = motor.atacar_inimigo(guerreiro, alvo, Dado([19, 1]))
    assert golpe.d20 == 19 and golpe.critico and golpe.acertou
    # sem a passiva, 19 e so um acerto comum
    comum = motor.Combatente(2, "C", 20, 40, "1d1", 50, 50)
    outro = motor.atacar_inimigo(comum, inimigo(), Dado([19, 1]))
    assert outro.d20 == 19 and not outro.critico
    # e o 1 natural continua errando, com passiva ou sem
    erro = motor.atacar_inimigo(guerreiro, inimigo(), Dado([1]))
    assert not erro.acertou
    print("  Improved Critical crita com 19, e o 1 natural ainda erra: ok")


def caso_dano_extra_e_condicional():
    alvo = inimigo(hp=100)
    paladino = motor.Combatente(1, "P", 20, 40, "1d1", 50, 50, dano_extra=2)
    golpe = motor.atacar_inimigo(paladino, alvo, None)
    if golpe.acertou:
        assert golpe.dano >= 3, golpe.dano  # 1d1 + 2

    # Predador so soma contra alvo em metade ou menos do HP
    patrulheiro = motor.Combatente(2, "R", 20, 40, "1d1", 50, 50, dano_ferido=2)
    inteiro = inimigo(hp=100)
    assert not motor.esta_ferido(inteiro)
    ferido = inimigo(hp=100)
    ferido.hp_atual = 50
    assert motor.esta_ferido(ferido)

    # d20 fixo em 10: acerta os dois sem esbarrar no 20 natural, que dobraria
    # os dados de um dos golpes e tiraria a comparacao do lugar.
    sadio = motor.atacar_inimigo(patrulheiro, inteiro, Dado([10]))
    machucado = motor.atacar_inimigo(patrulheiro, ferido, Dado([10]))
    assert sadio.acertou and machucado.acertou
    assert machucado.dano == sadio.dano + 2, (sadio.dano, machucado.dano)
    print("  dano extra do Paladino e o condicional do Patrulheiro: ok")


async def caso_multiataque_na_run():
    """Com Multiattack, um clique gasta o turno com os dois golpes."""
    conn, canal, cog = await preparar(classe="guerreiro", nivel=8)
    incursao, _ = montar_conteudo(
        cog, tamanho="Curta", monstro_objetivo={**INDEFESO, "hp": 500},
        salas=salas_sem_combate(),
    )
    run = await db.criar_run(conn, 1, CANAL, "t", JOGADORES[0])
    # dois participantes: assim a rodada nao fecha no primeiro que ataca
    for user_id in JOGADORES[:2]:
        personagem = await db.personagem_por_nome(conn, 1, user_id, f"Heroi{user_id}")
        await db.adicionar_participante(conn, run, user_id, personagem["id"])
    await db.inicializar_hp(conn, run)
    await db.atualizar_run(conn, run, status="objetivo", sala_atual="OBJ", linha_atual=4)
    atual = await db.buscar_run(conn, run)
    await cog._abrir_combate(atual, incursao.objetivo)

    atual = await db.buscar_run(conn, run)
    passo = cog._passo(atual)
    msg = await canal.fetch_message(atual["mensagem_id"])
    inter = FakeInteraction(canal, JOGADORES[0], msg)
    await cog.atacar(inter, run, "OBJ")

    golpes = await db.ataques_da_rodada(conn, run, passo, 1)
    assert len(golpes) == 2, golpes
    assert [g["indice"] for g in golpes] == [0, 1]
    assert inter.resposta.count("🎲") == 2, inter.resposta

    # e o turno ja foi: o segundo clique e recusado
    repetido = FakeInteraction(canal, JOGADORES[0], msg)
    await cog.atacar(repetido, run, "OBJ")
    assert "já atacou nesta rodada" in repetido.resposta
    assert len(await db.ataques_da_rodada(conn, run, passo, 1)) == 2
    print("  multiataque: dois golpes num clique, e o turno acaba: ok")


async def caso_a_escolha_nao_entra_na_lista_de_habilidades():
    """A ESCOLHA e rotulo de decisao, nao habilidade — e nao polui a lista.

    O jogador via a mesma decisao tres vezes: a linha da ESCOLHA ("Escolhe
    uma: Healing Word, Dissonant Whispers ou Charm Person"), a habilidade
    que ela destravou, e o campo Escolhas. Nenhuma das 38 escolhas do
    catalogo tem efeito ou acao propria, entao a linha delas nao carrega
    nada que o resto ja nao diga.
    """
    conn, canal, cog = await preparar(classe="bardo", nivel=5)
    dono = JOGADORES[0]
    personagem = await db.personagem_por_nome(conn, 1, dono, f"Heroi{dono}")
    # decide a magia do tier 1, para haver uma destravada na lista
    cancao = next(
        h for _t, h in personagem["habilidades"] if h.tipo == cl.ESCOLHA
    )
    opcao = cancao.escolha["opcoes"][0]
    await db.definir_escolha(conn, personagem["id"], cancao.id, opcao["id"])
    personagem = await db.buscar_personagem(conn, personagem["id"])

    campos = {
        f.name: f.value
        for f in embed_ficha(personagem, FakeInteraction(canal, dono).user).fields
    }
    lista = campos[next(n for n in campos if n.startswith("Habilidades"))]

    escolhas = [h for _t, h in personagem["habilidades"] if h.tipo == cl.ESCOLHA]
    assert escolhas, "o bardo do tier 3 tem escolha: sem isso nada e provado"
    for h in escolhas:
        assert h.nome not in lista, (h.nome, lista)

    # mas o que ela destravou esta la
    assert opcao["nome"] in lista, (opcao["nome"], lista)
    # e qual foi a decisao continua visivel, no campo proprio
    assert campos["Escolhas"], campos
    assert opcao["nome"] in campos["Escolhas"], campos["Escolhas"]
    print("  a escolha sai da lista; a habilidade escolhida fica: ok")


async def caso_ficha_mostra_habilidades():
    conn, canal, cog = await preparar(classe="patrulheiro", nivel=5)
    ficha_cog = Ficha(FakeBot(conn, canal))
    dono = JOGADORES[0]
    personagem = await db.personagem_por_nome(conn, 1, dono, f"Heroi{dono}")

    campos = {f.name: f.value for f in embed_ficha(personagem, FakeInteraction(canal, dono).user).fields}
    titulo = next(n for n in campos if n.startswith("Habilidades"))
    assert "Marca do Cacador" in campos[titulo]
    assert "Predador" in campos[titulo]
    assert "Multiattack" in campos[titulo]
    # "(em breve)" e para o que o bot NAO sabe executar, e hoje nao ha nada
    # assim: o marcador testava `automatica`, que e so passiva, e por isso
    # pintava toda ativa e toda escolha de "em breve" mesmo funcionando.
    assert "(em breve)" not in campos[titulo], campos[titulo]
    naoprontas = [
        h.id for classe in cl.CLASSES.values()
        for lista in classe.habilidades.values()
        for h in lista
        if not h.pronta
    ]
    assert not naoprontas, naoprontas

    # e o upar conta o que o tier novo trouxe
    await db.atualizar_personagem(conn, personagem["id"], "nivel", 6)
    inter = FakeInteraction(canal, dono)
    await ficha_cog.upar.callback(ficha_cog, inter)
    assert "Sobrevivente" in inter.resposta, inter.resposta
    print("  a ficha lista as habilidades e o upar anuncia a nova: ok")


async def main():
    try:
        caso_catalogo_completo()
        caso_texto_bate_com_a_mecanica()
        caso_efeitos_se_somam()
        caso_bonus_de_pericia()
        caso_critico_em_dezenove()
        caso_dano_extra_e_condicional()
        await caso_multiataque_na_run()
        await caso_ficha_mostra_habilidades()
        await caso_a_escolha_nao_entra_na_lista_de_habilidades()
    finally:
        for conn in _ABERTAS:
            try:
                await conn.close()
            except Exception:
                pass
        (Path(__file__).resolve().parent / "teste_habilidades.db").unlink(missing_ok=True)


asyncio.run(main())
print("TESTES DE HABILIDADES PASSARAM")
