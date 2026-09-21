"""Dublês mínimos do Discord para testar o cog sem rede."""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import copy  # noqa: E402

import discord  # noqa: E402

from src import database as db  # noqa: E402
from src.incursoes import banco_de_dict, de_dict  # noqa: E402

GUILD = 1
CANAL = 99
JOGADORES = [101, 102, 103, 104, 105]

ATRIBUTOS = {"FOR": 14, "DES": 16, "CON": 14, "INT": 12, "SAB": 13, "CAR": 10}
TREINADAS = ["Acrobacia", "Arcanismo", "Investigação", "Percepção", "Prestidigitação",
             "Furtividade", "Atletismo", "Religião", "Intuição", "História"]


# ----------------------------------------------------------------- dublês


class _FakeAvatar:
    url = "https://exemplo.invalid/avatar.png"


class FakeUsuario:
    def __init__(self, user_id: int):
        self.id = user_id
        self.display_name = f"Jogador{user_id}"
        self.mention = f"<@{user_id}>"
        self.display_avatar = _FakeAvatar()


class FakeMensagem:
    def __init__(self, canal, mensagem_id: int, **kw):
        self.id = mensagem_id
        self.canal = canal
        self.embeds = [kw["embed"]] if kw.get("embed") else []
        self.view = kw.get("view")
        self.content = kw.get("content")

    async def edit(self, **kw):
        if "embed" in kw:
            self.embeds = [kw["embed"]] if kw["embed"] else []
        if "view" in kw:
            self.view = kw["view"]
        return self


class FakeCanal:
    def __init__(self, canal_id: int):
        self.id = canal_id
        self.mensagens: list[FakeMensagem] = []
        self._proximo_id = 1000

    async def send(self, content=None, *, embed=None, view=None, file=discord.utils.MISSING):
        self._proximo_id += 1
        msg = FakeMensagem(self, self._proximo_id, content=content, embed=embed, view=view)
        self.mensagens.append(msg)
        return msg

    async def fetch_message(self, mensagem_id: int):
        for m in self.mensagens:
            if m.id == mensagem_id:
                return m
        raise discord.NotFound(_RespostaFalsa(), "mensagem sumiu")

    def ultimo_embed(self):
        for m in reversed(self.mensagens):
            if m.embeds:
                return m.embeds[0]
        return None


class _RespostaFalsa:
    status = 404
    reason = "Not Found"


class FakeResposta:
    def __init__(self, interacao):
        self.interacao = interacao

    async def send_message(self, content=None, *, embed=None, view=None, ephemeral=False,
                           file=discord.utils.MISSING):
        self.interacao.resposta = content or (embed.title if embed else None)
        self.interacao.view_enviada = view
        if ephemeral:
            self.interacao._mensagem_resposta = FakeMensagem(
                self.interacao.canal, -1, content=content, embed=embed, view=view
            )
        else:
            self.interacao._mensagem_resposta = await self.interacao.canal.send(
                content, embed=embed, view=view
            )

    async def defer(self, **kw):
        self.interacao.adiado = True


class FakeInteraction:
    def __init__(self, canal: FakeCanal, user_id: int, mensagem: FakeMensagem | None = None):
        self.canal = canal
        self.user = FakeUsuario(user_id)
        self.channel = canal
        self.channel_id = canal.id
        self.guild_id = GUILD
        self.message = mensagem
        self.response = FakeResposta(self)
        self.resposta = None
        self.view_enviada = None
        self.adiado = False
        self._mensagem_resposta = None

    async def original_response(self):
        return self._mensagem_resposta

    async def edit_original_response(self, **kw):
        alvo = self.message or self._mensagem_resposta
        if alvo:
            await alvo.edit(**kw)
        return alvo


class FakeBot:
    def __init__(self, conn, canal: FakeCanal):
        self.db = conn
        self.canal = canal
        self.views_registradas = []

    def get_channel(self, canal_id):
        return self.canal if canal_id == self.canal.id else None

    def get_guild(self, guild_id):
        return None

    def get_user(self, user_id):
        return FakeUsuario(user_id)

    async def fetch_user(self, user_id):
        return FakeUsuario(user_id)

    def add_view(self, view, *, message_id=None):
        self.views_registradas.append((view, message_id))


# Monstro que todo mundo acerta e que morre num golpe.
INDEFESO = {"nome": "Saco de Pancada", "ca": 1, "ataque": -20, "dano": "1d1", "hp": 1}
# Monstro que todo mundo acerta, mas aguenta varias rodadas sem revidar.
DURAO = {"nome": "Saco Grande", "ca": 1, "ataque": -20, "dano": "1d1", "hp": 120}
# Monstro que ninguem acerta e que mata um personagem por rodada.
IMBATIVEL = {"nome": "Ceifador", "ca": 40, "ataque": 40, "dano": "1d1+998", "hp": 999}

ORG_PADRAO = "Vórtice Oculto"

# Dois paragrafos: o recrutamento mostra so o primeiro, a abertura mostra tudo.
LORE_TESTE = (
    "Gancho da lore, que o recrutamento mostra.\n\n"
    "Segundo parágrafo, que só aparece quando a run começa."
)


def sala(sala_id, tipo, **extra):
    """Monta o dicionário de uma sala, com defaults coerentes por tipo."""
    base = {
        "id": sala_id,
        "nome": f"Sala {sala_id}",
        "tipo": tipo,
        "descricao": f"Descrição da sala {sala_id}.",
        "pericias": [],
        "dificuldade": None,
        "cd": None,
        "alvo_progresso": None,
        "imagem": None,
        "monstro": None,
        "recompensa": None,
        "pontos_organizacao": 0,
    }
    if tipo in ("Armadilha", "Evento", "Tesouro"):
        base.update(dificuldade="Fácil", cd=10, alvo_progresso=5, pericias=["Percepção"])
    base.update(extra)
    return base


def salas_sem_combate(quantas=6, tipo="Evento", pontos=0):
    """Banco previsível: só salas resolvidas por teste de perícia."""
    return [sala(f"E{i}", tipo, pontos_organizacao=pontos) for i in range(1, quantas + 1)]


def salas_de_combate(monstro=INDEFESO, quantas=4, pontos=0):
    return [
        sala(f"C{i}", "Combate", monstro=copy.deepcopy(monstro), pontos_organizacao=pontos)
        for i in range(1, quantas + 1)
    ]


def montar_conteudo(
    cog,
    *,
    incursao_id="t",
    organizacao=ORG_PADRAO,
    tamanho="Curta",
    monstro_objetivo=INDEFESO,
    salas=None,
    pontos_conclusao=10,
    pontos_objetivo=0,
    lore_final="Epílogo de teste.",
):
    """Registra no cog uma incursão e o banco de salas da Organização dela."""
    incursao = de_dict(
        {
            "id": incursao_id,
            "nome": f"Incursão {incursao_id}",
            "organizacao": organizacao,
            "tamanho": tamanho,
            "lore_inicial": LORE_TESTE,
            "lore_final": lore_final,
            "imagem_capa": None,
            "recompensa_mes": 10,
            "pontos_conclusao": pontos_conclusao,
            "objetivo": sala(
                "OBJ",
                "Combate",
                monstro=copy.deepcopy(monstro_objetivo),
                pontos_organizacao=pontos_objetivo,
            ),
        }
    )
    banco = banco_de_dict(
        {"organizacao": organizacao, "salas": salas if salas is not None else salas_sem_combate()}
    )
    cog.incursoes[incursao.id] = incursao
    cog.bancos[banco.organizacao] = banco
    return incursao, banco


async def opcoes_ids(cog, conn, run_id, passo):
    """Os ids das salas sorteadas para aquele passo."""
    return await db.opcoes_do_passo(conn, run_id, passo)


async def criar_grupo(
    conn, nivel=8, hp_max=40, ca=18, bonus_ataque=8, dano="1d6+3", nomes=None
):
    """Cria um personagem para cada jogador de teste. Devolve {user_id: personagem_id}."""
    ids = {}
    for user_id in JOGADORES:
        nome = (nomes or {}).get(user_id, f"Heroi{user_id}")
        ids[user_id] = await db.criar_personagem(
            conn, GUILD, user_id, nome, nivel, ATRIBUTOS, TREINADAS,
            combate={
                "ca": ca,
                "bonus_ataque": bonus_ataque,
                "dano_arma": dano,
                "hp_max": hp_max,
            },
        )
    return ids
