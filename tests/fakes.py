"""Dublês mínimos do Discord para testar o cog sem rede."""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import copy  # noqa: E402

import discord  # noqa: E402

from src import database as db  # noqa: E402
from src.incursoes import de_dict  # noqa: E402

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
# Monstro que ninguém acerta e que mata um personagem por rodada.
IMBATIVEL = {"nome": "Ceifador", "ca": 40, "ataque": 40, "dano": "1d1+998", "hp": 999}


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


def incursao_teste(
    incursao_id: str,
    monstro_objetivo: dict,
    monstro_meio: dict | None = None,
    pontos_conclusao: int = 10,
    pontos_por_sala: dict[str, int] | None = None,
):
    linha1 = [
        sala("A1", "Combate", monstro=copy.deepcopy(monstro_meio)) if monstro_meio
        else sala("A1", "Evento"),
        sala("A2", "Evento"),
        sala("A3", "Descanso"),
    ]
    dados = {
        "id": incursao_id,
        "nome": f"Incursão {incursao_id}",
        "organizacao": "Vórtice Oculto",
        "descricao": "Incursão sintética de teste.",
        "imagem_capa": None,
        "recompensa_mes": 10,
        "pontos_conclusao": pontos_conclusao,
        "linhas": [
            linha1,
            [sala("B1", "Evento"), sala("B2", "Descanso"), sala("B3", "Tesouro")],
            [sala("C1", "Evento"), sala("C2", "Armadilha"), sala("C3", "Descanso")],
        ],
        "objetivo": sala("OBJ", "Combate", monstro=copy.deepcopy(monstro_objetivo)),
    }
    for linha in dados["linhas"]:
        for s in linha:
            s["pontos_organizacao"] = (pontos_por_sala or {}).get(s["id"], 0)
    dados["objetivo"]["pontos_organizacao"] = (pontos_por_sala or {}).get("OBJ", 0)
    return de_dict(dados)


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
