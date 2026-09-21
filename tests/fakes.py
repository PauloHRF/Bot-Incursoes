"""Dublês mínimos do Discord para testar o cog sem rede."""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import discord  # noqa: E402

GUILD = 1
CANAL = 99
JOGADORES = [101, 102, 103, 104, 105]

ATRIBUTOS = {"FOR": 14, "DES": 16, "CON": 14, "INT": 12, "SAB": 13, "CAR": 10}
TREINADAS = ["Acrobacia", "Arcanismo", "Investigação", "Percepção", "Prestidigitação",
             "Furtividade", "Atletismo", "Religião", "Intuição", "História"]


# ----------------------------------------------------------------- dublês


class FakeUsuario:
    def __init__(self, user_id: int):
        self.id = user_id
        self.display_name = f"Jogador{user_id}"
        self.mention = f"<@{user_id}>"


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
        self.interacao._mensagem_resposta = await self.interacao.canal.send(
            content, embed=embed, view=view
        ) if not ephemeral else FakeMensagem(self.interacao.canal, -1, content=content, embed=embed)

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
