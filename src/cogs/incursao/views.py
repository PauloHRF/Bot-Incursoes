"""Os botões e menus das incursões: o que o jogador clica no canal.

Cada view só sabe montar os componentes e chamar o cog quando alguém clica —
a regra do que o clique faz mora no cog e em `src/combate`. Todas herdam
`ViewDoBot`, que avisa o jogador quando um clique quebra.
"""


from __future__ import annotations

from typing import Any, Optional

import discord

from ... import consumiveis, embeds as E, motor
from ...falhas import ViewDoBot
from ...incursoes import Sala
from ...rules import tier


class BotaoVoto(discord.ui.Button):
    def __init__(self, cog: "Incursoes", run_id: int, linha: int, indice: int, sala: Sala):
        super().__init__(
            label=str(indice + 1),
            emoji=E.EMOJI_TIPO.get(sala.tipo),
            style=discord.ButtonStyle.primary,
            custom_id=f"inc:voto:{run_id}:{linha}:{sala.id}",
        )
        self.cog = cog
        self.run_id = run_id
        self.linha = linha
        self.sala_id = sala.id

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.cog.votar(interaction, self.run_id, self.linha, self.sala_id)


class ViewVotacao(ViewDoBot):
    def __init__(self, cog: "Incursoes", run_id: int, linha: int, opcoes: list[Sala]):
        super().__init__(timeout=None)
        for i, sala in enumerate(opcoes):
            self.add_item(BotaoVoto(cog, run_id, linha, i, sala))


class ViewTrocaDoDescanso(ViewDoBot):
    """As trocas do descanso duro. Uma por botao, votadas pela maioria.

    Reusa o caminho do voto de sala: o voto fica em `run_votos`, e a maioria
    fecha. Nada de tabela nova — o que muda e o que o id significa.

    As trocas da mesa NAO sao gravadas: saem da semente `run:parada`, em
    `_trocas_da_parada`. Quem remonta este cartao depois de um restart
    (`_view_do_estado`) tem de pedir a mesa la, e nao em `run_mapa`.
    """

    def __init__(self, cog: "Incursoes", run_id: int, parada: int, trocas: list):
        super().__init__(timeout=None)
        for i, troca in enumerate(trocas):
            botao = discord.ui.Button(
                label=troca.nome[:80],
                emoji=E.EMOJI_OPCAO[i] if i < len(E.EMOJI_OPCAO) else None,
                style=discord.ButtonStyle.primary,
                custom_id=f"inc:troca:{run_id}:{parada}:{troca.id}",
            )
            botao.callback = self._fazer(parada, troca.id)
            self.add_item(botao)
        self.cog = cog
        self.run_id = run_id

    def _fazer(self, parada: int, troca_id: str):
        async def votar(interaction: discord.Interaction) -> None:
            await self.cog.votar_troca(interaction, self.run_id, parada, troca_id)
        return votar


class ViewSala(ViewDoBot):
    def __init__(self, cog: "Incursoes", run_id: int, sala_id: str):
        super().__init__(timeout=None)
        self.cog = cog
        self.run_id = run_id
        self.sala_id = sala_id
        botao = discord.ui.Button(
            label="Rolar teste",
            emoji="🎲",
            style=discord.ButtonStyle.success,
            custom_id=f"inc:rolar:{run_id}:{sala_id}",
        )
        botao.callback = self._rolar
        self.add_item(botao)

    async def _rolar(self, interaction: discord.Interaction) -> None:
        await self.cog.rolar(interaction, self.run_id, self.sala_id)


class ViewDescanso(ViewDoBot):
    """O descanso cura e deixa **cada um** limpar uma condição sua.

    Os botões são a união do que o grupo carrega, porque a mensagem é uma só;
    cada clique age sobre as condições de quem clicou, e vale uma por
    personagem. Quem não carrega nada não precisa clicar. O "Seguir" existe para
    quem carrega algo e prefere não gastar — sem ele, um jogador ausente
    travaria a sala.

    A sala fecha quando todos escolheram, como a de teste fecha quando todos
    rolaram; o estado vive em `run_descansos`, então um restart devolve os
    botões a quem ainda falta.
    """

    OPCOES = (
        ("debuff", "Tirar um debuff meu", "🧪"),
        ("exaustao", "Tirar 1 de Exaustão", "🥵"),
    )

    def __init__(
        self, cog: "Incursoes", run_id: int, sala_id: str, disponiveis: set[str]
    ):
        super().__init__(timeout=None)
        self.cog = cog
        self.run_id = run_id
        self.sala_id = sala_id
        for chave, rotulo, emoji in self.OPCOES:
            if chave not in disponiveis:
                continue
            botao = discord.ui.Button(
                label=rotulo,
                emoji=emoji,
                style=discord.ButtonStyle.primary,
                custom_id=f"inc:limpar:{run_id}:{sala_id}:{chave}",
            )
            botao.callback = self._fazer(chave)
            self.add_item(botao)
        seguir = discord.ui.Button(
            label="Seguir",
            emoji="➡️",
            style=discord.ButtonStyle.secondary,
            custom_id=f"inc:limpar:{run_id}:{sala_id}:nada",
        )
        seguir.callback = self._fazer("nada")
        self.add_item(seguir)

    def _fazer(self, chave: str):
        async def callback(interaction: discord.Interaction) -> None:
            await self.cog.limpar_no_descanso(
                interaction, self.run_id, self.sala_id, chave
            )

        return callback


class ViewMarcaOrfa(ViewDoBot):
    """Para onde vão as marcas do inimigo que caiu antes de elas explodirem.

    Mensagem **pública** com botões, e não efêmera. O Discord só manda
    efêmera para quem acabou de interagir, e o inimigo marcado cai na vez
    de QUALQUER jogador — muitas vezes não na do ladino. Quem clica é
    conferido no callback, como o descanso já faz.

    O combate **não espera** por este clique: o grupo segue, e as marcas
    ficam pendentes. Sem resposta até o fim do combate elas se perdem com
    ele, e um restart também as perde — esta mensagem não é o cartão do
    passo, então `restaurar_views` não a reativa.
    """

    def __init__(
        self, cog: "Incursoes", run_id: int, dono: int, marcas: int,
        expira: int, inimigos: list,
    ):
        super().__init__(timeout=None)
        self.cog = cog
        self.run_id = run_id
        self.dono = dono
        for inimigo in inimigos[:5]:
            botao = discord.ui.Button(
                label=f"{inimigo.nome[:80]} {motor.barra(inimigo.hp_atual, inimigo.hp_max, 8)}",
                emoji="🎯",
                style=discord.ButtonStyle.primary,
                custom_id=f"inc:marca:{run_id}:{dono}:{inimigo.indice}",
            )
            botao.callback = self._fazer(inimigo.indice, marcas, expira)
            self.add_item(botao)

    def _fazer(self, indice: int, marcas: int, expira: int):
        async def callback(interaction: discord.Interaction) -> None:
            await self.cog.transferir_marcas(
                interaction, self.run_id, self.dono, indice, marcas, expira
            )

        return callback


class ViewCombate(ViewDoBot):
    """Botao de atacar; com mais de um inimigo de pe, vira escolha de alvo."""

    def __init__(
        self,
        cog: "Incursoes",
        run_id: int,
        sala_id: str,
        inimigos: Optional[list[motor.Inimigo]] = None,
    ):
        super().__init__(timeout=None)
        self.cog = cog
        self.run_id = run_id
        self.sala_id = sala_id
        vivos = [i for i in (inimigos or []) if not i.caido]
        if len(vivos) > 1:
            menu = discord.ui.Select(
                placeholder="Atacar quem?",
                custom_id=f"inc:alvo:{run_id}:{sala_id}",
                options=[
                    discord.SelectOption(
                        label=i.nome[:100],
                        value=str(i.indice),
                        description=f"{motor.barra(i.hp_atual, i.hp_max, 8)} · CA {i.ca}",
                    )
                    for i in vivos[:25]
                ],
            )
            menu.callback = self._escolher_alvo
            self.menu = menu
            self.add_item(menu)
            self._botao_habilidade()
            self._botao_pocao()
            return
        botao = discord.ui.Button(
            label="Atacar",
            emoji="⚔️",
            style=discord.ButtonStyle.danger,
            custom_id=f"inc:atacar:{run_id}:{sala_id}",
        )
        botao.callback = self._atacar
        self.add_item(botao)
        self._botao_habilidade()
        self._botao_pocao()

    def _botao_habilidade(self) -> None:
        botao = discord.ui.Button(
            label="Habilidade",
            emoji="✨",
            style=discord.ButtonStyle.secondary,
            custom_id=f"inc:hab:{self.run_id}:{self.sala_id}",
        )
        botao.callback = self._habilidade
        self.add_item(botao)

    def _botao_pocao(self) -> None:
        """O botão existe sempre, mesmo com a bolsa vazia.

        Esconder o botão de quem não tem poção pareceria mais limpo, mas o
        painel é UMA mensagem para o grupo inteiro: o botão aparece conforme a
        bolsa de quem for montado o painel, e não de quem clica. Então ele
        está sempre lá, e quem não tem poção leva a recusa em privado.
        """
        botao = discord.ui.Button(
            label="Poção",
            emoji=consumiveis.ICONE,
            style=discord.ButtonStyle.success,
            custom_id=f"inc:pocao:{self.run_id}:{self.sala_id}",
        )
        botao.callback = self._pocao
        self.add_item(botao)

    async def _atacar(self, interaction: discord.Interaction) -> None:
        await self.cog.atacar(interaction, self.run_id, self.sala_id)

    async def _habilidade(self, interaction: discord.Interaction) -> None:
        await self.cog.abrir_habilidades(interaction, self.run_id, self.sala_id)

    async def _pocao(self, interaction: discord.Interaction) -> None:
        await self.cog.abrir_pocoes(interaction, self.run_id, self.sala_id)

    async def _escolher_alvo(self, interaction: discord.Interaction) -> None:
        await self.cog.atacar(
            interaction, self.run_id, self.sala_id, int(self.menu.values[0])
        )


class SeletorHabilidade(ViewDoBot):
    """As ativas que o jogador pode usar agora, so para quem clicou."""

    def __init__(self, cog: "Incursoes", run_id: int, sala_id: str, opcoes: list[tuple]):
        super().__init__(timeout=120)
        self.cog = cog
        self.run_id = run_id
        self.sala_id = sala_id
        menu = discord.ui.Select(
            placeholder="Qual habilidade?",
            options=[
                discord.SelectOption(label=nome, value=hid, description=descricao[:100])
                for hid, nome, descricao in opcoes[:25]
            ],
        )
        menu.callback = self._escolher
        self.menu = menu
        self.add_item(menu)

    async def _escolher(self, interaction: discord.Interaction) -> None:
        self.stop()
        await self.cog.usar_habilidade(
            interaction, self.run_id, self.sala_id, self.menu.values[0]
        )


class SeletorPocao(ViewDoBot):
    """O que a bolsa tem para beber agora, só para quem clicou."""

    def __init__(self, cog: "Incursoes", run_id: int, sala_id: str, opcoes: list[tuple]):
        super().__init__(timeout=120)
        self.cog = cog
        self.run_id = run_id
        self.sala_id = sala_id
        menu = discord.ui.Select(
            placeholder="Qual poção?",
            options=[
                discord.SelectOption(
                    label=f"{nome} ×{quantos}", value=pid,
                    description=descricao[:100], emoji=consumiveis.ICONE,
                )
                for pid, nome, quantos, descricao in opcoes[:25]
            ],
        )
        menu.callback = self._escolher
        self.menu = menu
        self.add_item(menu)

    async def _escolher(self, interaction: discord.Interaction) -> None:
        self.stop()
        await self.cog.usar_pocao(
            interaction, self.run_id, self.sala_id, self.menu.values[0]
        )


class SeletorRecarga(ViewDoBot):
    """Qual uso a Poção de Mana devolve, entre os que já foram gastos."""

    def __init__(
        self, cog: "Incursoes", run_id: int, sala_id: str, pocao_id: str,
        opcoes: list[tuple],
    ):
        super().__init__(timeout=120)
        self.cog = cog
        self.run_id = run_id
        self.sala_id = sala_id
        self.pocao_id = pocao_id
        menu = discord.ui.Select(
            placeholder="Devolver uso de qual habilidade?",
            options=[
                discord.SelectOption(label=nome, value=hid, description=descricao[:100])
                for hid, nome, descricao in opcoes[:25]
            ],
        )
        menu.callback = self._escolher
        self.menu = menu
        self.add_item(menu)

    async def _escolher(self, interaction: discord.Interaction) -> None:
        self.stop()
        await self.cog.usar_pocao(
            interaction, self.run_id, self.sala_id, self.pocao_id,
            escolhida=self.menu.values[0],
        )


class SeletorAlvoHabilidade(ViewDoBot):
    """Em quem a habilidade cai: um inimigo, varios, ou um aliado."""

    def __init__(
        self,
        cog: "Incursoes",
        run_id: int,
        sala_id: str,
        habilidade_id: str,
        opcoes: list[tuple],
        maximo: int = 1,
    ):
        super().__init__(timeout=120)
        self.cog = cog
        self.run_id = run_id
        self.sala_id = sala_id
        self.habilidade_id = habilidade_id
        menu = discord.ui.Select(
            placeholder="Em quem?" if maximo == 1 else f"Em quem? (ate {maximo})",
            min_values=1,
            max_values=min(maximo, len(opcoes)),
            options=[
                discord.SelectOption(label=nome, value=valor, description=descricao[:100])
                for valor, nome, descricao in opcoes[:25]
            ],
        )
        menu.callback = self._escolher
        self.menu = menu
        self.add_item(menu)

    async def _escolher(self, interaction: discord.Interaction) -> None:
        self.stop()
        await self.cog.usar_habilidade(
            interaction,
            self.run_id,
            self.sala_id,
            self.habilidade_id,
            [int(v) for v in self.menu.values],
        )


class SeletorPersonagemEntrada(ViewDoBot):
    """Escolha de qual personagem levar para a run, mostrada só a quem clicou."""

    def __init__(self, cog: "Incursoes", run_id: int, personagens: list[dict[str, Any]]):
        super().__init__(timeout=180)
        self.cog = cog
        self.run_id = run_id
        menu = discord.ui.Select(
            placeholder="Com qual personagem voce entra?",
            options=[
                discord.SelectOption(
                    label=p["nome"],
                    value=str(p["id"]),
                    description=(
                        f"Tier {tier(p['nivel'])} · "
                        f"CA {p['ca']} · HP {p['hp_max']}"
                    ),
                )
                for p in personagens[:25]
            ],
        )
        menu.callback = self._escolher
        self.menu = menu
        self.add_item(menu)

    async def _escolher(self, interaction: discord.Interaction) -> None:
        self.stop()
        await self.cog.efetivar_entrada(interaction, self.run_id, int(self.menu.values[0]))


class ViewRecrutamento(ViewDoBot):
    def __init__(self, cog: "Incursoes", run_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.run_id = run_id
        for rotulo, emoji, estilo, acao in (
            ("Entrar", "➕", discord.ButtonStyle.success, "entrar"),
            ("Sair", "➖", discord.ButtonStyle.secondary, "sair"),
            ("Começar", "▶️", discord.ButtonStyle.primary, "comecar"),
        ):
            botao = discord.ui.Button(
                label=rotulo, emoji=emoji, style=estilo, custom_id=f"inc:recrut:{run_id}:{acao}"
            )
            botao.callback = self._acao(acao)
            self.add_item(botao)

    def _acao(self, acao: str):
        async def callback(interaction: discord.Interaction) -> None:
            await self.cog.recrutar(interaction, self.run_id, acao)

        return callback
