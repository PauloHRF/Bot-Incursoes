"""Runs de incursão: recrutamento, votação por linha, salas e testes de perícia.

A run é assíncrona: o estado vive no banco, não na memória, para que o grupo
possa avançar ao longo de dias e o bot possa reiniciar sem perder nada.
"""
from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime
from typing import Any, Optional

import discord
from discord import app_commands
from discord.ext import commands

from .. import (
    ameaca,
    bestiario,
    incursoes,
    classes as cl,
    condicoes,
    config,
    consequencias,
    consumiveis,
    database as db,
    embeds as E,
    habilidades,
    mercado,
    motor,
)
from ..incursoes import (
    BancoDeSalas,
    Incursao,
    Sala,
    arquivo_da_organizacao,
    carregar_bancos_tolerante,
    carregar_todas_tolerante,
    conferir_filtro,
    monstros_de_criatura,
    salas_sorteaveis,
)
from ..motor import Combatente, EstadoCombate, ResolucaoSala, ResultadoTeste
from ..rules import TIER_MAXIMO, fmt, tier
from .ficha import sugerir_personagens

log = logging.getLogger("incursoes.run")


def emboscada_de(sala: Sala, tier: Optional[int] = None) -> Sala:
    """O Tesouro que virou combate, quando a falha acorda os Mímicos.

    Função pura e determinística de propósito: a mesma sala e o mesmo tier
    sempre devolvem a mesma emboscada, então remontá-la depois de um restart
    dá no mesmo. Vem com `monstros` vazio se o bestiário não tiver Mímico.

    Quem entra sai de `consequencias.A_EMBOSCADA`, que tem uma linha medida
    por tier — o Mímico é CR 2 e sozinho não pesa num grupo de tier alto.
    """
    do_livro = bestiario.buscar(consequencias.NOME_DO_MIMICO)
    monstros = []
    if do_livro is not None:
        monstros = [
            m
            for nome, quantas in consequencias.emboscada_do_tier(tier)
            for m in monstros_de_criatura(
                {"nome": nome, "quantidade": quantas}, f"{sala.id}: emboscada"
            )
        ]
    return Sala(
        id=sala.id,
        nome=f"{sala.nome} — a emboscada",
        tipo="Combate",
        descricao=(
            "O baú abriu antes de alguém encostar nele, e o que estava dentro "
            "era o próprio baú."
        ),
        imagem=sala.imagem,
        monstros=monstros,
    )

# Teto de um efeito que so acaba quando o alvo passa no save: nao e para chegar
# la — e so uma trava para nada ficar preso o combate inteiro.
PRAZO_ATE_PASSAR = 20

# Quantas rodadas seguidas o combate pode correr sozinho quando ninguem
# pode agir (grupo inteiro atordoado) antes de o bot avisar.
MAX_RODADAS_SOZINHAS = 10

# A recusa de quem esta no chao, nos tres caminhos de acao (ataque, habilidade,
# pocao). Dizia "fica fora do resto deste combate", de quando uma queda so se
# desfazia no descanso — hoje a cura levanta, e a vez perdida no chao volta se
# alguem levantar o personagem na mesma rodada (ver `resolver_atrasados`).
AVISO_CAIDO = (
    "Você está caído — espere alguém te levantar com uma cura. "
    "A rodada só é perdida se ninguém levantar você nela."
)


def maioria_de(total: int) -> int:
    """Quantos votos fecham a votacao: mais da metade do grupo."""
    return total // 2 + 1


def _texto_digitado(interaction: discord.Interaction, campo: str) -> str:
    """O que já está preenchido em OUTRO campo do comando, no autocomplete.

    O Discord manda, a cada tecla, o que o jogador escolheu até ali. É com
    isso que a lista de alvos sabe qual ação foi escolhida — sem ler o campo
    `acao`, ela teria de oferecer inimigos e aliados ao mesmo tempo.
    """
    valor = getattr(getattr(interaction, "namespace", None), campo, None)
    return "" if valor is None else str(valor)


def _id_digitado(interaction: discord.Interaction, campo: str) -> Optional[int]:
    """O id de um campo de jogador já preenchido, no autocomplete.

    Tolerante de propósito: no autocomplete o campo pode chegar como objeto de
    usuário ou como o id cru, e qualquer um dos dois serve.
    """
    valor = getattr(getattr(interaction, "namespace", None), campo, None)
    if valor is None:
        return None
    try:
        return int(getattr(valor, "id", valor))
    except (TypeError, ValueError):
        return None


def _resolucao(sala: Sala, registros: list[dict[str, Any]], total: int) -> ResolucaoSala:
    resultados = [
        ResultadoTeste(
            user_id=r["user_id"],
            personagem=r["personagem"],
            pericia=r["pericia"],
            d20=r["d20"],
            modificador=r["modificador"],
            cd=r["cd"],
        )
        for r in registros
    ]
    return ResolucaoSala(sala=sala, resultados=resultados, total_participantes=total)


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


class ViewVotacao(discord.ui.View):
    def __init__(self, cog: "Incursoes", run_id: int, linha: int, opcoes: list[Sala]):
        super().__init__(timeout=None)
        for i, sala in enumerate(opcoes):
            self.add_item(BotaoVoto(cog, run_id, linha, i, sala))


class ViewTrocaDoDescanso(discord.ui.View):
    """As trocas do descanso duro. Uma por botao, votadas pela maioria.

    Reusa o caminho do voto de sala: as trocas sorteadas ficam em `run_mapa`
    como as salas, o voto em `run_votos`, e a maioria fecha. Nada de tabela
    nova — o que muda e o que o id significa.
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


class ViewSala(discord.ui.View):
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


class ViewDescanso(discord.ui.View):
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


class ViewMarcaOrfa(discord.ui.View):
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


class ViewCombate(discord.ui.View):
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


class SeletorHabilidade(discord.ui.View):
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


class SeletorPocao(discord.ui.View):
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


class SeletorRecarga(discord.ui.View):
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


class SeletorAlvoHabilidade(discord.ui.View):
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


class SeletorPersonagemEntrada(discord.ui.View):
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


class ViewRecrutamento(discord.ui.View):
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


def nome_do_efeito(efeito_id: str) -> str:
    """O nome que o jogador conhece, a partir do id gravado no efeito.

    Os efeitos sao gravados com `habilidade.id`, que serve ao banco e nao a
    quem le: o resumo do golpe tem de dizer "Marca do Cacador" e nao
    "marca_do_cacador".

    Funcao de modulo porque quem precisa dela e `_aplicar_ligado`, que e
    estatica — e porque ela nao olha para o estado de ninguem.
    """
    habilidade = habilidades.POR_ID.get(efeito_id)
    if habilidade:
        return habilidade.nome
    # A poção grava o efeito pela FAMÍLIA ("pocao_aceleracao"), para a segunda
    # renovar a primeira em vez de somar com ela — então o nome sai da família.
    da_pocao = consumiveis.nome_do_efeito(efeito_id)
    if da_pocao:
        return da_pocao
    return efeito_id.replace('_', ' ')


class Incursoes(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.incursoes: dict[str, Incursao] = {}
        self.bancos: dict[str, BancoDeSalas] = {}
        # Limpeza do canal, tudo em memoria: um restart perde as referencias e
        # deixa a mensagem antiga no lugar, o que e melhor que gravar no banco
        # coisa que so vale por 15 minutos (o prazo do token de interacao).
        self._efemeras: dict[int, list[discord.Interaction]] = {}
        self._chamadas: dict[int, Any] = {}
        # O ultimo anuncio publico de habilidade, por run: e com ele que
        # `_avancar` sabe que nao deve repetir a mesma frase em privado.
        self._publicado: dict[int, str] = {}
        # As mensagens de habilidade usada que estao no canal. Elas contam
        # a historia do combate enquanto ele rola, e viram ruido depois que
        # ele acaba — o painel ja guarda o desfecho.
        self._usadas: dict[int, list[Any]] = {}
        # O que o ultimo descanso deu a cada um, enquanto a sala do descanso
        # esta aberta. {run_id: {user_id: motor.Recuperacao}}
        self._recuperacao: dict[int, dict[int, Any]] = {}
        # O log da rodada no painel, e a fila de cada run: um restart perde o
        # log (o combate continua do banco) e recria as travas.
        self._registros: dict[int, dict[str, Any]] = {}
        self._travas: dict[int, asyncio.Lock] = {}
        self._encerrados: set[tuple[int, int]] = set()

    async def cog_load(self) -> None:
        self._carregar_tolerante()
        await self.restaurar_views()

    def recarregar_incursoes(self) -> list[str]:
        """Relê o disco e devolve os problemas dos arquivos que ficaram de fora.

        Tolerante por arquivo de propósito: antes, um JSON quebrado abortava o
        carregamento inteiro e o bot subia sem NENHUMA incursão. A vírgula
        errada de um colaborador tirava o catálogo do ar, e não só a dungeon
        dele. Agora o arquivo ruim fica de fora sozinho — e aparece no log e na
        resposta do `/incursao recarregar`, para não ficar de fora em silêncio.
        """
        pasta = config.RAIZ / "data" / "incursoes"
        bancos = config.RAIZ / "data" / "bancos"
        # Sala que chama criatura pelo nome le o bestiario: ele relê junto.
        bestiario.recarregar()
        problemas: list[str] = []
        if pasta.is_dir():
            self.incursoes, ruins = carregar_todas_tolerante(pasta)
            problemas.extend(ruins)
        else:
            self.incursoes = {}
        if bancos.is_dir():
            self.bancos, ruins = carregar_bancos_tolerante(bancos)
            problemas.extend(ruins)
        else:
            self.bancos = {}
        for problema in problemas:
            log.error("arquivo de conteúdo ficou de fora — %s", problema)
        sem_caminho: list[str] = []
        for inc in self.incursoes.values():
            banco = self.bancos.get(inc.organizacao)
            if banco is None:
                log.warning(
                    "a incursão '%s' é de %s, mas não há banco de salas dessa Organização"
                    " (esperado em data/bancos/%s.json)",
                    inc.id,
                    inc.organizacao,
                    arquivo_da_organizacao(inc.organizacao),
                )
                continue
            # A conferencia CRUZADA, que nenhum dos dois validadores de arquivo
            # consegue fazer sozinho. Ela roda aqui porque este e o caminho do
            # arquivo copiado a mao, que nao passou pelo validar_conteudo.
            cruzados, avisos = conferir_filtro(inc, banco)
            for aviso in avisos:
                log.warning("a incursão '%s' — %s", inc.id, aviso)
            if cruzados:
                # Sai do catalogo. Uma dungeon cujo filtro deixa sala de menos
                # nao falha ao carregar: ela falha na PARADA 4, com o grupo
                # dentro. Melhor nao aparecer na lista do que prender cinco
                # pessoas num caminho sem saida.
                sem_caminho.append(inc.id)
                for problema in cruzados:
                    log.error("a incursão '%s' ficou de fora — %s", inc.id, problema)
                    problemas.append(f"{inc.id}: {problema}")
        for incursao_id in sem_caminho:
            self.incursoes.pop(incursao_id, None)
        # O log do total vem DEPOIS das retiradas, senão ele anuncia uma
        # incursão que o bot acabou de tirar do catálogo.
        log.info(
            "%d incursão(ões) e %d banco(s) carregados: %s",
            len(self.incursoes),
            len(self.bancos),
            ", ".join(self.incursoes),
        )
        return problemas

    def _carregar_tolerante(self) -> None:
        """No boot, nada do conteúdo pode impedir o bot de subir.

        A tolerância de verdade é por arquivo, dentro de `recarregar_incursoes`.
        Este `except` é a última rede: ele pega a falha que não é de um arquivo
        só — bestiário ilegível, pasta sem permissão — e que levaria o bot
        inteiro junto.
        """
        try:
            self.recarregar_incursoes()
        except Exception:
            log.exception("falha ao carregar as incursões; subindo sem nenhuma")
            self.incursoes = {}
            self.bancos = {}

    async def restaurar_views(self) -> None:
        """Reativa os botões das runs que ficaram abertas antes de um restart."""
        for run in await db.runs_vivas(self.bot.db):
            view = await self._view_do_estado(run)
            if view and run["mensagem_id"]:
                self.bot.add_view(view, message_id=run["mensagem_id"])

    async def _view_do_estado(self, run: dict[str, Any]) -> Optional[discord.ui.View]:
        incursao = self.incursoes.get(run["incursao_id"])
        if not incursao:
            return None
        if run["status"] == "recrutando":
            return ViewRecrutamento(self, run["id"])
        if run["status"] == "escolhendo":
            opcoes = await self._opcoes(run, run["linha_atual"])
            return ViewVotacao(self, run["id"], run["linha_atual"], opcoes) if opcoes else None
        if run["status"] in ("em_sala", "objetivo") and run["sala_atual"]:
            sala = await self._sala_corrente(run)
            if sala and sala.tem_teste:
                return ViewSala(self, run["id"], sala.id)
            if sala and sala.tipo == "Descanso":
                # O descanso fica aberto ate alguem escolher o que limpar.
                return ViewDescanso(
                    self, run["id"], sala.id, await self._limpezas_disponiveis(run)
                )
            if sala and sala.e_combate:
                estado = await self._estado_combate(run, sala)
                return ViewCombate(
                    self, run["id"], sala.id, estado.inimigos if estado else None
                )
        return None

    # ------------------------------------------------------------ apoio

    async def _canal(self, run: dict[str, Any]) -> Optional[discord.abc.Messageable]:
        canal = self.bot.get_channel(run["canal_id"])
        if canal is None:
            try:
                canal = await self.bot.fetch_channel(run["canal_id"])
            except discord.HTTPException:
                log.warning("canal %s da run %s sumiu", run["canal_id"], run["id"])
                return None
        return canal

    async def _limpar_botoes(self, run: dict[str, Any]) -> None:
        """Tira os botões da mensagem atual quando aquela etapa se encerra."""
        if not run.get("mensagem_id"):
            return
        canal = await self._canal(run)
        if not canal:
            return
        try:
            mensagem = await canal.fetch_message(run["mensagem_id"])
            await mensagem.edit(view=None)
        except discord.HTTPException:
            pass

    async def _encerrar_run(self, run: dict[str, Any], status: str) -> None:
        """Fecha a run e tira os botões da etapa que ficou pendente.

        Sem isso, uma votação ou um combate abertos no momento do encerramento
        continuariam clicáveis depois que a run acabou.
        """
        # Desistencia e encerramento manual tambem cancelam acoes guardadas.
        # A reivindicacao das pendentes torna a devolucao unica, mesmo quando
        # o fecho do combate ja passou por ela.
        await self._devolver_pendentes(run)
        await self._limpar_botoes(await db.buscar_run(self.bot.db, run["id"]))
        await db.atualizar_run(self.bot.db, run["id"], status=status, votacao_expira_em=None)
        # O que era de memoria e so desta run sai com ela: um bot que fica
        # ligado por semanas acumularia uma entrada por run encerrada.
        self._recuperacao.pop(run["id"], None)
        self._registros.pop(run["id"], None)

    async def _membros(self, run: dict[str, Any]) -> list[discord.abc.User]:
        return [
            await self._membro(run, user_id)
            for user_id in await db.participantes(self.bot.db, run["id"])
        ]

    async def _membro(self, run: dict[str, Any], user_id: int):
        """O membro do servidor, ou o usuário, para menção e apelido."""
        guilda = self.bot.get_guild(run["guild_id"])
        membro = guilda.get_member(user_id) if guilda else None
        if membro is None and guilda is not None:
            # Sem o intent de membros o cache vem vazio; buscar traz o apelido do servidor.
            try:
                membro = await guilda.fetch_member(user_id)
            except discord.HTTPException:
                membro = None
        return membro or await self.bot.fetch_user(user_id)

    async def _nomes(self, run: dict[str, Any]) -> dict[int, str]:
        """{user_id: nome do PERSONAGEM} na run.

        A condição é do personagem, não da conta: quem joga com dois não se
        reconhece pelo apelido do Discord, e a mesma pessoa pode estar numa
        run com uma ficha e em outra com a outra. Onde a frase fala de efeito,
        é este nome que entra — o apelido serve para MARCAR alguém, que é
        outra coisa (ver `_chamar`).
        """
        return {
            p["user_id"]: p["nome"]
            for p in await db.personagens_da_run(self.bot.db, run["id"])
        }

    def _incursao_da_run(self, run: dict[str, Any]) -> Optional[Incursao]:
        return self.incursoes.get(run["incursao_id"])

    def _sala(self, incursao: Incursao, sala_id: Optional[str]) -> Optional[Sala]:
        """A sala pelo id: a final da incursão ou uma do banco da Organização."""
        if not sala_id:
            return None
        if sala_id == incursao.objetivo.id:
            return incursao.objetivo
        # A parada do descanso duro nao vem de banco: ela e a mesma em toda
        # Organizacao, porque o que decide ali sao as TROCAS.
        if sala_id == incursoes.ID_DO_DESCANSO_DURO:
            return incursoes.sala_do_descanso_duro()
        banco = self.bancos.get(incursao.organizacao)
        return banco.sala(sala_id) if banco else None

    async def _sala_corrente(self, run: dict[str, Any]) -> Optional[Sala]:
        """A sala em que o grupo está, contando o Tesouro que virou emboscada.

        A emboscada de Mímicos não existe no banco, então não dá para achá-la
        por id. O que a identifica é persistente: existe linha de combate aberta
        neste passo e a sala escrita não é de Combate. Assim ela sobrevive a um
        restart sem tabela nova — e o passo avançar basta para esquecê-la.
        """
        incursao = self._incursao_da_run(run)
        if incursao is None:
            return None
        sala = self._sala(incursao, run["sala_atual"])
        if sala is None or sala.e_combate:
            return sala
        if await db.estado_combate(self.bot.db, run["id"], self._passo(run)):
            return emboscada_de(sala, self._tier_da_run(run))
        return sala

    async def _opcoes(self, run: dict[str, Any], passo: int) -> list[Sala]:
        """As salas sorteadas para aquele passo desta run."""
        incursao = self._incursao_da_run(run)
        if not incursao:
            return []
        ids = await db.opcoes_do_passo(self.bot.db, run["id"], passo)
        return [s for s in (self._sala(incursao, i) for i in ids) if s]

    async def _sortear_opcoes(self, run: dict[str, Any], passo: int) -> list[str]:
        """Sorteia e grava as salas daquele passo, fora as que o grupo já atravessou."""
        incursao = self._incursao_da_run(run)
        banco = self.bancos.get(incursao.organizacao) if incursao else None
        if not banco:
            return []
        visitadas = await db.salas_visitadas(self.bot.db, run["id"])
        # `salas_sorteaveis` tira o Descanso: ele deixou de ser sorteado e
        # virou parada fixa. Depois o filtro da incursao corta por tema ou por
        # lista — vazio, ele devolve o banco inteiro, que e o que toda
        # incursao escrita antes do filtro faz.
        #
        # A conferencia cruzada (`conferir_filtro`) ja barrou, na validacao, o
        # filtro que deixa sala de menos. Aqui nao ha rede: se o pool acabar,
        # `sortear_passo` levanta, e e por isso que a conferencia existe.
        sorteaveis = incursao.filtro.aplicar(salas_sorteaveis(banco))
        opcoes = motor.sortear_passo(sorteaveis, visitadas)
        await db.gravar_opcoes(self.bot.db, run["id"], passo, opcoes)
        return opcoes

    async def _run_do_contexto(
        self, interaction: discord.Interaction, exigir_participante: bool = True
    ) -> Optional[dict[str, Any]]:
        run = await db.run_do_canal(self.bot.db, interaction.channel_id)
        if not run:
            await interaction.response.send_message(
                "Não há incursão em andamento neste canal. Comece uma com `/incursao entrar`.",
                ephemeral=True,
            )
            return None
        if exigir_participante and not await db.esta_na_run(self.bot.db, run["id"], interaction.user.id):
            await interaction.response.send_message("Você não faz parte desta run.", ephemeral=True)
            return None
        return run

    # ------------------------------------------------------- recrutamento

    grupo = app_commands.Group(name="incursao", description="Incursões da sua Organização")

    # O Discord corta o nome de uma opcao em 100 caracteres, e corta no meio
    # da palavra. Melhor cortar o NOME DA ORGANIZACAO, que vem por ultimo,
    # do que deixar o tier cair fora da tela por causa de um nome longo.
    LIMITE_DA_OPCAO = 100

    @staticmethod
    def _e_do_tier(incursao, tier_pedido: int) -> bool:
        """Se esta incursao entra no filtro daquele tier.

        A de tier livre entra em TODOS os filtros: ela aceita qualquer
        personagem, e esconde-la de quem filtrou por um tier seria esconder
        a unica que ele com certeza pode jogar.
        """
        return incursao.aberta_a_todos or incursao.tier == tier_pedido

    async def _sugerir_incursoes(
        self, interaction: discord.Interaction, atual: str
    ) -> list[app_commands.Choice[str]]:
        """A lista que aparece ao digitar o comando: nome, tier e Organizacao.

        O tier entra aqui e nao so no cartao da run: a escolha acontece
        NESTA lista, e e o tier que decide se o personagem pode entrar. Sem
        ele o jogador escolhia no escuro e descobria no erro.
        """
        termo = atual.lower()
        # O tier que o jogador ja preencheu no MESMO comando: o Discord manda
        # os outros campos em `interaction.namespace`, e e so por aqui que o
        # filtro pode valer — a lista e montada antes de o comando rodar.
        tier_pedido = getattr(interaction.namespace, "tier", None)
        opcoes = []
        for inc in self.incursoes.values():
            if tier_pedido and not self._e_do_tier(inc, tier_pedido):
                continue
            if termo not in inc.id.lower() and termo not in inc.nome.lower():
                continue
            rotulo = E.titulo_da_incursao(inc)
            sobra = self.LIMITE_DA_OPCAO - len(rotulo) - len(" — ")
            if sobra > 1:
                rotulo += f" — {inc.organizacao[:sobra]}"
            opcoes.append(
                app_commands.Choice(name=rotulo[: self.LIMITE_DA_OPCAO], value=inc.id)
            )
        return opcoes[:25]

    async def _sugerir_tiers(
        self, interaction: discord.Interaction, atual: str
    ) -> list[app_commands.Choice[int]]:
        """Os tiers que TÊM incursão carregada, e quantas cada um tem.

        Uma lista fixa de 1 a 5 ofereceria tier vazio — hoje não há conteúdo
        de tier 3 nem de 5 —, e o jogador só descobriria isso no campo
        seguinte, com o autocompletar do id vindo vazio e sem explicação.

        A de tier livre conta em TODOS, porque ela é jogável em todos.
        """
        quantas: dict[int, int] = {}
        for inc in self.incursoes.values():
            for t in range(1, TIER_MAXIMO + 1):
                if self._e_do_tier(inc, t):
                    quantas[t] = quantas.get(t, 0) + 1
        termo = atual.strip()
        return [
            # "incursão"/"incursões" escrito por extenso: o plural troca o
            # ã por õ e nao sai de somar um sufixo ("incursãoes").
            app_commands.Choice(
                name=f"Tier {t} — {n} " + ("incursão" if n == 1 else "incursões"),
                value=t,
            )
            for t, n in sorted(quantas.items())
            if not termo or str(t).startswith(termo)
        ][:25]

    @grupo.command(name="listar", description="Mostra as incursões disponíveis")
    @app_commands.describe(tier_pedido="Só as incursões deste tier (vazio: todas)")
    @app_commands.rename(tier_pedido="tier")
    @app_commands.autocomplete(tier_pedido=_sugerir_tiers)
    async def listar(
        self,
        interaction: discord.Interaction,
        tier_pedido: Optional[app_commands.Range[int, 1, TIER_MAXIMO]] = None,
    ) -> None:
        """A vitrine das incursões, para o jogador escolher.

        Sem o `id` e sem a contagem de salas e de MEs: o id é coisa de
        arquivo — o jogador escolhe na lista do `/incursao entrar` e nunca o
        digita —, e quantas salas a run tem não muda a escolha dele, muda a
        conta de quem escreve conteúdo.
        """
        if not self.incursoes:
            await interaction.response.send_message(
                "Nenhuma incursão carregada. Importe uma planilha com "
                "`tools/importar_planilha.py` e reinicie o bot.",
                ephemeral=True,
            )
            return
        escolhidas = [
            inc for inc in self.incursoes.values()
            if tier_pedido is None or self._e_do_tier(inc, tier_pedido)
        ]
        if not escolhidas:
            await interaction.response.send_message(
                f"Nenhuma incursão de tier {tier_pedido}. Use `/incursao listar` "
                f"sem filtro para ver todas.",
                ephemeral=True,
            )
            return
        e = discord.Embed(
            title=(
                f"Incursões de tier {tier_pedido}" if tier_pedido
                else "Incursões disponíveis"
            ),
            color=E.COR_INCURSAO,
        )
        for inc in escolhidas:
            salas_no_banco = (
                len(self.bancos[inc.organizacao].salas)
                if inc.organizacao in self.bancos else 0
            )
            e.add_field(
                name=E.titulo_da_incursao(inc),
                value=(
                    f"{inc.organizacao} — {inc.tamanho.lower()}\n"
                    + E.exigencia_de_tier(inc)
                    + ("" if salas_no_banco else "\n⚠️ sem banco de salas carregado")
                ),
                inline=False,
            )
        await interaction.response.send_message(embed=e, ephemeral=True)

    async def _sugerir_personagens(
        self, interaction: discord.Interaction, atual: str
    ) -> list[app_commands.Choice[str]]:
        return await sugerir_personagens(self.bot.db, interaction, atual)

    @grupo.command(name="entrar", description="Abre o recrutamento de uma incursão neste canal")
    @app_commands.describe(
        tier_pedido="O tier da incursão — filtra a lista do campo seguinte",
        incursao_id="Qual incursão (só as do tier escolhido aparecem)",
        personagem="Com qual personagem voce entra (opcional se voce so tem um)",
    )
    # O parametro se chama `tier_pedido` no Python e `tier` no Discord: o nome
    # curto sombrearia a funcao `tier()` de rules, que este comando usa para
    # saber o tier do PERSONAGEM — e o erro sairia como "'int' object is not
    # callable", que nao aponta para nada.
    @app_commands.rename(tier_pedido="tier")
    @app_commands.autocomplete(
        tier_pedido=_sugerir_tiers,
        incursao_id=_sugerir_incursoes,
        personagem=_sugerir_personagens,
    )
    async def entrar(
        self,
        interaction: discord.Interaction,
        tier_pedido: app_commands.Range[int, 1, TIER_MAXIMO],
        incursao_id: str,
        personagem: Optional[str] = None,
    ) -> None:
        """O tier vem ANTES do id porque ele filtra a lista do id.

        O Discord pede os campos na ordem da assinatura e monta o
        autocomplete com o que ja foi preenchido, entao o filtro só funciona
        nesta ordem — com o id na frente, a lista sairia inteira.
        """
        incursao = self.incursoes.get(incursao_id)
        if not incursao:
            do_tier = [
                i for i in self.incursoes.values()
                if self._e_do_tier(i, tier_pedido)
            ]
            if not do_tier:
                await interaction.response.send_message(
                    f"Não há incursão de tier {tier_pedido} carregada. "
                    f"Veja `/incursao listar`.",
                    ephemeral=True,
                )
                return
            await interaction.response.send_message(
                f"Não conheço a incursão `{incursao_id}`. Veja `/incursao listar`.",
                ephemeral=True,
            )
            return
        # O id pode nao ser o do tier filtrado: o jogador escolhe na lista, mas
        # nada impede digitar outro id a mao depois de filtrar.
        if not self._e_do_tier(incursao, tier_pedido):
            await interaction.response.send_message(
                f"**{incursao.nome}** não é de tier {tier_pedido} — ela é "
                f"{E.exigencia_de_tier(incursao).split('—')[0].strip()}.",
                ephemeral=True,
            )
            return
        if await db.run_do_canal(self.bot.db, interaction.channel_id):
            await interaction.response.send_message(
                "Já existe uma incursão em andamento neste canal. Use `/incursao status`.",
                ephemeral=True,
            )
            return

        bloqueio = await self._motivo_de_bloqueio(interaction.guild_id, interaction.user.id)
        if bloqueio:
            await interaction.response.send_message(bloqueio, ephemeral=True)
            return

        meus = await db.listar_personagens(
            self.bot.db, interaction.guild_id, interaction.user.id
        )
        elegiveis = self._elegiveis(incursao, meus)
        if personagem:
            escolhido = await db.personagem_por_nome(
                self.bot.db, interaction.guild_id, interaction.user.id, personagem
            )
            if not escolhido:
                await interaction.response.send_message(
                    f"Voce nao tem nenhum personagem chamado **{personagem}**. "
                    f"Os seus sao: {', '.join(p['nome'] for p in meus)}.",
                    ephemeral=True,
                )
                return
            if not motor.pode_encarar(escolhido["nivel"], incursao.tier):
                await interaction.response.send_message(
                    self._fora_do_tier(incursao, [escolhido]), ephemeral=True
                )
                return
        elif not elegiveis:
            await interaction.response.send_message(
                self._fora_do_tier(incursao, meus), ephemeral=True
            )
            return
        elif len(elegiveis) == 1:
            escolhido = elegiveis[0]
        else:
            await interaction.response.send_message(
                "Voce tem mais de um personagem para esta incursão: "
                f"{', '.join(p['nome'] for p in elegiveis)}. "
                "Diga qual no campo `personagem`.",
                ephemeral=True,
            )
            return

        run_id = await db.criar_run(
            self.bot.db, interaction.guild_id, interaction.channel_id, incursao.id, interaction.user.id
        )
        await db.adicionar_participante(
            self.bot.db, run_id, interaction.user.id, escolhido["id"],
            tier=tier(escolhido["nivel"]),
        )

        run = await db.buscar_run(self.bot.db, run_id)
        view = ViewRecrutamento(self, run_id)
        await interaction.response.send_message(
            embed=E.recrutamento(incursao, await self._membros(run), interaction.user), view=view
        )
        mensagem = await interaction.original_response()
        await db.atualizar_run(self.bot.db, run_id, mensagem_id=mensagem.id)

    @staticmethod
    def _elegiveis(incursao: Incursao, personagens: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Só os personagens que cabem no tier da incursão."""
        return [p for p in personagens if motor.pode_encarar(p["nivel"], incursao.tier)]

    @staticmethod
    def _fora_do_tier(incursao: Incursao, personagens: list[dict[str, Any]]) -> str:
        """Explica por que nenhum daqueles personagens pode entrar."""
        quem = ", ".join(
            f"**{p['nome']}** (tier {tier(p['nivel'])})" for p in personagens
        )
        return (
            f"**{incursao.nome}** é de tier {incursao.tier}: entra quem for tier "
            f"{incursao.tier} ou menos. "
            f"Seus personagens estão acima disso: {quem}."
        )

    async def _motivo_de_bloqueio(self, guild_id: int, user_id: int) -> Optional[str]:
        """Texto do impedimento para entrar numa run, ou None se estiver liberado."""
        personagens = await db.listar_personagens(self.bot.db, guild_id, user_id)
        if not personagens:
            return (
                "Você ainda não tem personagem. Cadastre um com `/ficha registrar` antes de entrar."
            )
        outra = await db.run_viva_do_jogador(self.bot.db, guild_id, user_id)
        if outra:
            return f"Você já está na run #{outra['id']}. Termine ou desista dela antes."
        semanas = await db.intervalo_semanas(self.bot.db, guild_id)
        ultima = await db.ultima_incursao(self.bot.db, guild_id, user_id)
        agora = datetime.now(config.FUSO)
        if not motor.entrada_liberada(ultima, agora, semanas):
            volta = motor.virada_da_vaga(ultima, semanas)
            quantas = "semana" if semanas == 1 else f"{semanas} semanas"
            return (
                f"Você já entrou numa incursão nesta {quantas} "
                f"(em {ultima:%d/%m}). O intervalo vira na segunda-feira: "
                f"sua vaga volta em **{volta:%d/%m}**."
            )
        return None

    async def _atualizar_recrutamento(self, run: dict[str, Any]) -> None:
        """Redesenha a mensagem de recrutamento com o grupo atual."""
        incursao = self._incursao_da_run(run)
        canal = await self._canal(run)
        if not (incursao and canal and run["mensagem_id"]):
            return
        criador = self.bot.get_user(run["criador_id"])
        membros = await self._membros(run)
        try:
            mensagem = await canal.fetch_message(run["mensagem_id"])
            await mensagem.edit(
                embed=E.recrutamento(incursao, membros, criador or membros[0]),
                view=ViewRecrutamento(self, run["id"]),
            )
        except discord.HTTPException:
            pass

    async def efetivar_entrada(
        self, interaction: discord.Interaction, run_id: int, personagem_id: int
    ) -> None:
        """Coloca o jogador na run com o personagem escolhido."""
        run = await db.buscar_run(self.bot.db, run_id)
        if not run or run["status"] != "recrutando":
            await interaction.response.send_message(
                "Este recrutamento já foi encerrado.", ephemeral=True
            )
            return

        personagem = await db.buscar_personagem(self.bot.db, personagem_id)
        if not personagem or personagem["user_id"] != interaction.user.id:
            await interaction.response.send_message(
                "Esse personagem não é seu.", ephemeral=True
            )
            return
        if await db.esta_na_run(self.bot.db, run_id, interaction.user.id):
            await interaction.response.send_message(
                "Você já está no grupo.", ephemeral=True
            )
            return
        # O MESMO bloqueio que o `recrutar` confere antes de abrir o menu, e
        # nao uma formalidade: o menu de escolher personagem fica no canal
        # depois de aberto, e o botao dele chama esta funcao direto. Quem
        # abrisse o menu aqui, entrasse em outra incursao e depois voltasse
        # para clicar neste botao entrava nas duas — o mesmo personagem em
        # duas runs vivas. Qualquer cheque que abre um menu precisa valer de
        # novo no clique: entre uma coisa e outra nao existe prazo.
        #
        # Vem DEPOIS do `esta_na_run` desta run, senao ele mesmo responderia
        # "voce ja esta na run #N" apontando para esta, que nao e o aviso.
        bloqueio = await self._motivo_de_bloqueio(
            run["guild_id"], interaction.user.id
        )
        if bloqueio:
            await interaction.response.send_message(bloqueio, ephemeral=True)
            return
        if len(await db.participantes(self.bot.db, run_id)) >= config.TAMANHO_GRUPO:
            await interaction.response.send_message("O grupo já está cheio.", ephemeral=True)
            return

        # Ultima checagem: o menu pode estar velho, e o nivel pode ter subido nesse meio-tempo.
        incursao = self._incursao_da_run(run)
        if incursao and not motor.pode_encarar(personagem["nivel"], incursao.tier):
            await interaction.response.send_message(
                self._fora_do_tier(incursao, [personagem]), ephemeral=True
            )
            return

        if not await db.adicionar_participante(
            self.bot.db, run_id, interaction.user.id, personagem_id,
            tier=tier(personagem["nivel"]),
        ):
            # Quem decide a lotacao e o INSERT, que a confere no proprio
            # statement. A conferencia de cima continua ali porque da a frase
            # na hora no caso comum, mas ela le e decide com um `await` no
            # meio: dois cliques no mesmo instante passavam os dois por ela.
            # Aqui so se traduz o "nao deu" em motivo.
            await interaction.response.send_message(
                "Você já está no grupo."
                if await db.esta_na_run(self.bot.db, run_id, interaction.user.id)
                else "O grupo encheu antes de você: a última vaga foi de outra pessoa.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            f"Voce entrou com **{personagem['nome']}** (tier {tier(personagem['nivel'])}).",
            ephemeral=True,
        )

        run = await db.buscar_run(self.bot.db, run_id)
        await self._atualizar_recrutamento(run)
        if len(await db.participantes(self.bot.db, run_id)) >= config.TAMANHO_GRUPO:
            await self._iniciar(run)

    async def recrutar(self, interaction: discord.Interaction, run_id: int, acao: str) -> None:
        run = await db.buscar_run(self.bot.db, run_id)
        if not run or run["status"] != "recrutando":
            await interaction.response.send_message(
                "Este recrutamento já foi encerrado.", ephemeral=True
            )
            return
        incursao = self._incursao_da_run(run)
        if not incursao:
            await interaction.response.send_message(
                f"A incursão `{run['incursao_id']}` não está mais carregada.", ephemeral=True
            )
            return

        if acao == "entrar":
            if await db.esta_na_run(self.bot.db, run_id, interaction.user.id):
                await interaction.response.send_message("Você já está no grupo.", ephemeral=True)
                return
            membros_atuais = await db.participantes(self.bot.db, run_id)
            if len(membros_atuais) >= config.TAMANHO_GRUPO:
                await interaction.response.send_message("O grupo já está cheio.", ephemeral=True)
                return
            bloqueio = await self._motivo_de_bloqueio(run["guild_id"], interaction.user.id)
            if bloqueio:
                await interaction.response.send_message(bloqueio, ephemeral=True)
                return

            personagens = await db.listar_personagens(
                self.bot.db, run["guild_id"], interaction.user.id
            )
            elegiveis = self._elegiveis(incursao, personagens)
            if not elegiveis:
                await interaction.response.send_message(
                    self._fora_do_tier(incursao, personagens), ephemeral=True
                )
                return
            if len(elegiveis) == 1:
                await self.efetivar_entrada(interaction, run_id, elegiveis[0]["id"])
            else:
                await interaction.response.send_message(
                    "Escolha com qual personagem entrar:",
                    view=SeletorPersonagemEntrada(self, run_id, elegiveis),
                    ephemeral=True,
                )
            return

        elif acao == "sair":
            if interaction.user.id == run["criador_id"]:
                await interaction.response.send_message(
                    "Quem abriu a incursão não pode sair. Use `/incursao desistir` para cancelar.",
                    ephemeral=True,
                )
                return
            if not await db.remover_participante(self.bot.db, run_id, interaction.user.id):
                await interaction.response.send_message("Você não está no grupo.", ephemeral=True)
                return
            # Saiu antes de a incursao comecar: nao joga, nao recebe. Quem e
            # ejetado no MEIO da run continua na lista de quem recebe.
            await db.tirar_o_direito_ao_ouro(self.bot.db, run_id, interaction.user.id)

        elif acao == "comecar":
            if interaction.user.id != run["criador_id"]:
                await interaction.response.send_message(
                    "Só quem abriu a incursão pode começar antes do grupo encher.", ephemeral=True
                )
                return
            await interaction.response.defer()
            await self._iniciar(run)
            return

        await interaction.response.defer()
        membros = await self._membros(run)
        criador = self.bot.get_user(run["criador_id"]) or interaction.user
        await interaction.edit_original_response(
            embed=E.recrutamento(incursao, membros, criador), view=ViewRecrutamento(self, run_id)
        )

    async def _iniciar(self, run: dict[str, Any]) -> None:
        participantes = await db.participantes(self.bot.db, run["id"])
        if not participantes:
            return
        incursao = self._incursao_da_run(run)
        canal = await self._canal(run)
        if not incursao:
            return

        banco = self.bancos.get(incursao.organizacao)
        if not banco:
            if canal:
                await canal.send(
                    f"Não há banco de salas de **{incursao.organizacao}** carregado, "
                    "então não dá para sortear o caminho. Avise quem administra o bot."
                )
            return
        await db.marcar_ultima_incursao(self.bot.db, run["guild_id"], participantes)
        await db.inicializar_hp(self.bot.db, run["id"])
        await db.atualizar_run(self.bot.db, run["id"], status="escolhendo", linha_atual=1)

        if canal:
            if run["mensagem_id"]:
                try:
                    mensagem = await canal.fetch_message(run["mensagem_id"])
                    await mensagem.edit(view=None)
                except discord.HTTPException:
                    pass
            # Lore e o grupo na mesma mensagem, com os retratos lado a lado.
            personagens = await db.personagens_da_run(self.bot.db, run["id"])
            membros = [await self._membro(run, p["user_id"]) for p in personagens]
            cartoes, faixa = await E.abertura_do_grupo(personagens, membros)
            await canal.send(
                embeds=[E.lore_abertura(incursao, len(participantes)), *cartoes[:9]],
                file=faixa or discord.utils.MISSING,
            )
        await self._abrir_votacao(await db.buscar_run(self.bot.db, run["id"]), 1)

    # ------------------------------------------------------------ votação

    async def _abrir_votacao(self, run: dict[str, Any], linha: int) -> None:
        """Abre a parada `linha`: a votação das salas, ou o descanso dela.

        Descanso deixou de ser sorteado. Ele era sala do banco como as outras,
        então um grupo atravessava uma Longa inteira sem nenhum e outro pegava
        dois — e o que a sala do caminho cobra é HP, que não volta entre salas.
        Agora ele é parada FIXA, pelo tamanho da incursão
        (`incursoes.DESCANSOS_DO_CAMINHO`), e parada a mais, não sala a menos.

        O normal nem passa por votação: ele é sempre o mesmo, e escolher entre
        três cópias da mesma coisa não é escolha. O duro é votado, porque ali
        há o que decidir.
        """
        incursao = self._incursao_da_run(run)
        canal = await self._canal(run)
        if not (incursao and canal):
            return
        # A sala que o grupo acabou de atravessar sai do canal. No primeiro
        # passo nao ha sala anterior: o que esta la e o recrutamento, que fica.
        if linha > 1:
            await self._apagar_passo_anterior(run)

        descanso = incursao.descanso_da_parada(linha)
        if descanso == incursoes.DESCANSO_NORMAL:
            await db.atualizar_run(
                self.bot.db, run["id"], status="escolhendo", linha_atual=linha,
                sala_atual=None, votacao_expira_em=None,
            )
            atual = await db.buscar_run(self.bot.db, run["id"])
            sala = self._sala_de_descanso(incursao)
            if sala is None:
                await canal.send(
                    "O banco desta Organização não tem sala de Descanso, e o "
                    "caminho pede uma aqui. O grupo segue sem descansar."
                )
                await self._seguir_do_descanso(atual, linha)
                return
            await self._entrar_na_sala(atual, sala)
            return
        if descanso == incursoes.DESCANSO_DURO:
            await db.atualizar_run(
                self.bot.db, run["id"], status="escolhendo", linha_atual=linha,
                sala_atual=None, votacao_expira_em=None,
            )
            await self._abrir_descanso_duro(
                await db.buscar_run(self.bot.db, run["id"]), linha
            )
            return

        opcoes = await self._opcoes(run, linha)
        if not opcoes:
            try:
                await self._sortear_opcoes(run, linha)
            except ValueError as exc:
                await canal.send(f"Não consegui sortear as salas deste passo: {exc}.")
                return
            opcoes = await self._opcoes(run, linha)
        if not opcoes:
            await canal.send(
                "Não achei as salas sorteadas para este passo. O banco da Organização mudou?"
            )
            return
        total = len(await db.participantes_de_pe(self.bot.db, run["id"]))
        votos = await db.votos_da_linha(self.bot.db, run["id"], linha)
        view = ViewVotacao(self, run["id"], linha, opcoes)
        mensagem = await canal.send(
            f"🗳️ {await self._chamar(run)} — escolham por onde seguir.",
            embed=E.votacao(incursao, linha, opcoes, votos, total, incursao.paradas),
            view=view,
        )
        await db.atualizar_run(
            self.bot.db,
            run["id"],
            status="escolhendo",
            linha_atual=linha,
            sala_atual=None,
            mensagem_id=mensagem.id,
            votacao_expira_em=None,
        )

    async def votar(
        self, interaction: discord.Interaction, run_id: int, linha: int, sala_id: str
    ) -> None:
        run = await db.buscar_run(self.bot.db, run_id)
        if not run or run["status"] != "escolhendo" or run["linha_atual"] != linha:
            await interaction.response.send_message("Esta votação já foi encerrada.", ephemeral=True)
            return
        if not await db.esta_na_run(self.bot.db, run_id, interaction.user.id):
            await interaction.response.send_message("Você não faz parte desta run.", ephemeral=True)
            return
        if not await db.esta_de_pe(self.bot.db, run_id, interaction.user.id):
            await interaction.response.send_message(
                "Você está caído — quem está no chão não escolhe o caminho.",
                ephemeral=True,
            )
            return

        await db.registrar_voto(self.bot.db, run_id, linha, interaction.user.id, sala_id)
        incursao = self._incursao_da_run(run)
        sala = self._sala(incursao, sala_id)
        await interaction.response.send_message(
            f"Voto registrado: **{sala.nome if sala else sala_id}**.", ephemeral=True
        )
        # O aviso so vale enquanto a votacao esta aberta: some quando o grupo entra.
        self._guardar_efemera(run_id, interaction)

        votos = await db.votos_da_linha(self.bot.db, run_id, linha)
        total = len(await db.participantes_de_pe(self.bot.db, run_id))
        opcoes = await self._opcoes(run, linha)

        if interaction.message is not None:
            try:
                await interaction.message.edit(
                    embed=E.votacao(incursao, linha, opcoes, votos, total, incursao.paradas),
                    view=ViewVotacao(self, run_id, linha, opcoes),
                )
            except discord.HTTPException:
                pass

        await self._fechar_votacao(run, linha)

    async def _fechar_votacao(self, run: dict[str, Any], linha: int) -> None:
        """Fecha a votacao assim que uma sala tem a maioria do grupo.

        Nao ha prazo: a run espera indefinidamente, mas nao espera quem falta
        depois que o resultado ja esta decidido.
        """
        run = await db.buscar_run(self.bot.db, run["id"])
        if not run or run["status"] != "escolhendo" or run["linha_atual"] != linha:
            return
        incursao = self._incursao_da_run(run)
        canal = await self._canal(run)
        if not (incursao and canal):
            return

        votos = await db.votos_da_linha(self.bot.db, run["id"], linha)
        contagem: dict[str, int] = {}
        for opcao in votos.values():
            contagem[opcao] = contagem.get(opcao, 0) + 1

        if not contagem:
            return  # ninguem votou ainda: a votacao segue aberta

        total = len(await db.participantes_de_pe(self.bot.db, run["id"]))
        maioria = maioria_de(total)
        maximo = max(contagem.values())
        empatadas = [sala_id for sala_id, n in contagem.items() if n == maximo]
        decidida = len(empatadas) == 1

        if decidida and maximo >= maioria:
            # Maioria fechada: nao ha por que esperar quem ainda nao votou.
            escolhida_id = empatadas[0]
        elif len(votos) >= total and decidida:
            # Todos votaram sem maioria absoluta: vale a mais votada.
            escolhida_id = empatadas[0]
        elif len(votos) >= total:
            await canal.send(
                "Empate na votação, com todo mundo já tendo votado. Ninguém avança "
                "enquanto o grupo não desempatar — clique em outra opção para trocar seu voto."
            )
            return
        else:
            return  # ainda da para virar: espera mais votos

        # A sala e tomada ANTES de qualquer mensagem: o que vem depois tem
        # `await` de rede no meio, e e por ali que o segundo clique passava.
        if not await db.tomar_a_sala(
            self.bot.db, run["id"], linha, escolhida_id
        ):
            return  # outro clique levou esta sala; este nao abre nada

        faltaram = total - len(votos)
        if faltaram > 0:
            nome = self._sala(incursao, escolhida_id).nome
            await canal.send(
                f"**{nome}** fechou com {maximo} de {total} votos — maioria formada, "
                f"o grupo não espera os {faltaram} que faltam."
            )

        await self._limpar_botoes(run)
        await self._entrar_na_sala(
            await db.buscar_run(self.bot.db, run["id"]),
            self._sala(incursao, escolhida_id),
        )

    # -------------------------------------------------------------- salas

    async def _entrar_na_sala(self, run: dict[str, Any], sala: Sala) -> None:
        # A votacao cumpriu o papel dela: o grupo ja escolheu. Sai do canal, e
        # somem com ela os "voto registrado" de cada um.
        await self._apagar_passo_anterior(run)
        await self._limpar_efemeras(run["id"])
        canal = await self._canal(run)
        if not canal:
            return
        # Atravessar a sala a tira do sorteio: ela nao volta a ser oferecida.
        await db.registrar_visita(self.bot.db, run["id"], self._passo(run), sala.id)

        if sala.tipo == "Descanso":
            await db.atualizar_run(self.bot.db, run["id"], status="em_sala", sala_atual=sala.id)
            # O contador de descansos e o que zera as habilidades por descanso.
            await db.contar_descanso(self.bot.db, run["id"])
            combatentes = await self._combatentes(run)
            feito = motor.aplicar_descanso(combatentes)
            await db.definir_hp_varios(
                self.bot.db, run["id"], {c.user_id: c.hp_atual for c in combatentes}
            )
            # O que o descanso deu fica guardado pelo tempo da sala: o cartao
            # e reescrito a cada limpeza, e so aqui se sabe o "antes".
            self._recuperacao[run["id"]] = feito
            mudancas = await self._linhas_do_descanso(run)
            # Alem de curar, o descanso deixa cada um limpar UMA condicao sua.
            # A sala fecha quando todos escolherem — e quem nao carrega nada ja
            # entra marcado, entao grupo limpo nao precisa clicar.
            disponiveis = await self._limpezas_disponiveis(run)
            faltam = await self._descanso_pendente(run)
            mensagem = await canal.send(
                embed=E.descanso(
                    sala, mudancas, disponiveis, faltam=len(faltam)
                ),
                view=(
                    ViewDescanso(self, run["id"], sala.id, disponiveis)
                    if faltam
                    else None
                ),
            )
            # O descanso tambem e a sala do passo: sai do canal na proxima escolha.
            await db.atualizar_run(self.bot.db, run["id"], mensagem_id=mensagem.id)
            if faltam:
                await canal.send(
                    f"🏕️ {await self._chamar(run, faltam)} — o descanso deixa cada "
                    f"um limpar **uma** condição sua."
                )
                return
            await self._concluir_sala(
                await db.buscar_run(self.bot.db, run["id"]), sala, None
            )
            return

        incursao = self._incursao_da_run(run)
        await db.atualizar_run(
            self.bot.db,
            run["id"],
            status="em_sala",
            sala_atual=sala.id,
            votacao_expira_em=None,
        )

        if sala.e_combate:
            # O painel do combate ja traz descricao, monstro e HP: uma mensagem so.
            await self._abrir_combate(await db.buscar_run(self.bot.db, run["id"]), sala)
            return

        # Só a sala de teste cobra nome de alguém: numa sem teste isto seriam
        # duas leituras de banco para um campo que o cartão não desenha.
        faltam_rolar: list[str] = []
        if sala.tem_teste:
            _, faltam_rolar = await self._quem_rolou(run, [])
        embed, arquivo = E.sala_aberta(
            sala, run["linha_atual"], (), faltam_rolar,
            incursao.paradas if incursao else None,
            # O tier, senao o cartao mostra a CD do tier 1 e `motor.testar`
            # cobra a do tier da run: o grupo via um numero e rolava contra
            # outro.
            tier=self._tier_da_run(run),
            tema=self._tema_da_sala(run, sala),
        )
        view = ViewSala(self, run["id"], sala.id) if sala.tem_teste else None
        chamada = (
            f"🎲 {await self._chamar(run)} — hora de rolar." if sala.tem_teste else None
        )
        mensagem = await canal.send(
            chamada, embed=embed, view=view, file=arquivo or discord.utils.MISSING
        )
        await db.atualizar_run(self.bot.db, run["id"], mensagem_id=mensagem.id)

    async def _marcar_sala_superada(self, run: dict[str, Any], sala: Sala) -> None:
        """Registra a sala vencida. Nao paga ninguem: o ouro sai no fecho.

        Antes cada sala pagava na hora, e uma run que acabasse com o grupo
        todo no chao deixava o ouro das salas do caminho na bolsa de quem
        tinha chegado ali. Agora a incursao paga de uma vez, e so se for
        concluida — fracasso nao rende nada.

        Os dois caminhos de "sala superada", o combate e o teste, podem
        chamar sem combinar entre si: a marca e por passo, e marcar duas
        vezes marca a mesma linha.
        """
        await db.marcar_sala_superada(
            self.bot.db, run["id"], self._passo(run), sala.id
        )

    async def _pagar_as_salas(self, run: dict[str, Any]) -> int:
        """O ouro das salas que o grupo venceu, no fecho da run.

        Vai para TODOS que passaram pela run, e nao so para quem estava de
        pe no fim: quem caiu no objetivo e quem foi ejetado por Exaustao no
        meio do caminho jogaram a incursao e levam o mesmo que os outros.

        O valor sai das salas superadas e nao de quem estava em qual: e o
        grupo que atravessou, nao cada um por si. A de Combate conta por
        duas, porque e a unica que cobra HP.

        Duas salas ficam de fora da dobra. O objetivo, porque ele nao e
        escolha de ninguem: a dobra existe para a sala de Combate competir
        na votacao com a de Tesouro, e o objetivo e obrigatorio — quem paga
        por ele e o bonus de conclusao. E o Tesouro que virou emboscada de
        Mimico, que continua contando como Tesouro: a emboscada e castigo
        por falhar no bau, e nao da para pagar dobrado por ter falhado.

        Separado do fecho porque a desistencia paga isto e nao paga aquele:
        o grupo atravessou as salas, so nao terminou a incursao.
        """
        tier = self._tier_da_run(run) or 1
        ids = await db.ids_das_salas_superadas(self.bot.db, run["id"])
        superadas = len(ids)
        # A de Combate paga dobrado: é a única que cobra HP, e o HP não volta
        # entre salas. Pagando igual à de Tesouro, evitar combate era sempre
        # a melhor jogada.
        incursao = self._incursao_da_run(run)
        do_caminho = (
            (self._sala(incursao, i) for i in ids if i != incursao.objetivo.id)
            if incursao
            else ()
        )
        de_combate = sum(1 for s in do_caminho if s and s.e_combate)
        quanto = mercado.ouro_das_salas(tier, superadas, de_combate)
        motivo = f"Salas superadas ({superadas})"
        if de_combate:
            motivo = f"Salas superadas ({superadas}, {de_combate} de combate)"
        pagos = 0
        for p in await db.quem_recebe_da_run(self.bot.db, run["id"]):
            if await db.lancar_ouro(
                self.bot.db, p["id"], quanto, motivo,
                run_id=run["id"], chave="salas",
            ):
                pagos += 1
        return pagos

    async def _pagar_o_fecho(self, run: dict[str, Any]) -> int:
        """O bonus de ter CONCLUIDO a incursao. So a vitoria paga."""
        quanto = mercado.ouro_da_incursao(self._tier_da_run(run) or 1)
        pagos = 0
        for p in await db.quem_recebe_da_run(self.bot.db, run["id"]):
            if await db.lancar_ouro(
                self.bot.db, p["id"], quanto, "Incursao concluida",
                run_id=run["id"], chave="conclusao",
            ):
                pagos += 1
        return pagos

    async def _creditar(
        self, run: dict[str, Any], pontos: int, motivo: str, chave: str
    ) -> bool:
        """Credita pontos à Organização da incursão. Ignora repetição e valor zero."""
        incursao = self._incursao_da_run(run)
        if not incursao or pontos <= 0:
            return False
        return await db.lancar_pontos(
            self.bot.db,
            run["guild_id"],
            incursao.organizacao,
            pontos,
            motivo,
            run_id=run["id"],
            chave=chave,
        )

    async def _balanco(self, run: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
        """Os lançamentos da run e o total da Organização, para o embed de desfecho."""
        incursao = self._incursao_da_run(run)
        if not incursao:
            return [], 0
        lancamentos = await db.pontos_da_run(self.bot.db, run["id"])
        placar = await db.placar(self.bot.db, run["guild_id"])
        return lancamentos, placar.get(incursao.organizacao, 0)

    def _passo(self, run: dict[str, Any]) -> int:
        """O passo atual do caminho. O objetivo fica um depois do último."""
        incursao = self._incursao_da_run(run)
        if run["status"] == "objetivo" and incursao:
            return incursao.paradas + 1
        return run["linha_atual"]

    def _tier_da_run(self, run: dict[str, Any]) -> Optional[int]:
        """O tier da incursão — é ele que dimensiona debuff, buff e maldição."""
        incursao = self._incursao_da_run(run)
        return incursao.tier if incursao else None

    async def _saldo(self, run: dict[str, Any], user_id: int) -> condicoes.Penalidades:
        """O que este personagem carrega de condição, já somado."""
        return condicoes.penalidades(
            await db.condicoes_de(self.bot.db, run["id"], user_id),
            self._tier_da_run(run),
        )

    async def _combatentes(
        self, run: dict[str, Any], efeitos_ligados: Optional[list[dict]] = None
    ) -> list[Combatente]:
        """Monta os combatentes juntando a ficha de cada um com o HP atual da run."""
        personagens = await db.personagens_da_run(self.bot.db, run["id"])
        tier_atual = self._tier_da_run(run)
        carregadas = await db.condicoes_da_run(self.bot.db, run["id"])
        combatentes = []
        for p in personagens:
            # As passivas da classe entram como numero: multiataque, critico
            # mais facil e dano extra saem daqui.
            efeitos = p.get("efeitos") or {}
            # E por cima delas, o que as salas deixaram: debuff, maldicao,
            # exaustao e buff. Camada propria porque sao somas com sinal, e
            # habilidades.juntar consolida com max().
            saldo = condicoes.penalidades(carregadas.get(p["user_id"], {}), tier_atual)
            hp_max = condicoes.hp_maximo(p["hp_max"], saldo)
            atual = hp_max if p["hp_atual"] is None else min(p["hp_atual"], hp_max)
            combatentes.append(
                Combatente(
                    user_id=p["user_id"],
                    nome=p["nome"],
                    ca=p["ca"],
                    bonus_ataque=p["bonus_ataque"] + saldo.ataque,
                    dano_arma=p["dano_arma"],
                    hp_max=hp_max,
                    hp_atual=atual,
                    thp=p.get("thp") or 0,
                    ataques=efeitos.get("ataques", 1),
                    critico_em=efeitos.get("critico_em", 20),
                    dano_extra=efeitos.get("dano_extra", 0),
                    dano_ferido=efeitos.get("dano_ferido", 0),
                    # Ataques Abencoados, do clerigo: dado a mais em todo golpe.
                    dano_bonus=efeitos.get("dano_bonus", ""),
                    saves={
                        atributo: valor + saldo.saves
                        for atributo, valor in (p.get("saves") or {}).items()
                    },
                    # A Exaustao tira e as botas do mercado somam, no mesmo
                    # lugar: nenhum dos dois e save de DES.
                    mod_iniciativa_extra=(
                        saldo.iniciativa + efeitos.get("bonus_iniciativa", 0)
                    ),
                    cura_recebida_pct=saldo.cura_recebida_pct,
                    # A classe diz onde ele fica na sala; as passivas somam.
                    # O que esta ligado e o que ele gerou agindo entram depois,
                    # em `_aplicar_ligado`, cada um no seu campo.
                    ameaca=ameaca.inicial(p.get("classe")) + efeitos.get("ameaca", 0),
                    classe=str(p.get("classe") or ""),
                )
            )
        for ligado in efeitos_ligados or []:
            self._aplicar_ligado(combatentes, ligado)
        self._aplicar_aura_totemica(combatentes, personagens)
        self._aplicar_infusoes(combatentes, personagens)
        self._aplicar_aura_de_save(combatentes, personagens)
        # Os aliados conjurados entram como combatentes comuns, com dono: assim
        # herdam ameaca, HP, iniciativa e painel sem nada de novo. O que os
        # separa e `dono`, que faz a vez deles ser resolvida sozinha.
        for conjurado in await db.invocacoes(self.bot.db, run["id"], self._passo(run)):
            combatentes.append(
                Combatente(
                    user_id=conjurado["user_id"],
                    nome=conjurado["nome"],
                    ca=conjurado["ca"],
                    bonus_ataque=conjurado["ataque"],
                    dano_arma=conjurado["dano"],
                    hp_max=conjurado["hp_max"],
                    hp_atual=conjurado["hp_atual"],
                    ameaca=conjurado["ameaca"],
                    dono=conjurado["dono"],
                )
            )
        return combatentes

    @staticmethod
    def _aplicar_infusoes(
        combatentes: list[Combatente], personagens: list[dict[str, Any]]
    ) -> None:
        """O equipamento que o artífice infundiu, no grupo inteiro.

        No livro ele replica itens mágicos e os distribui; aqui os itens ficam
        na planilha do grupo, então o que entra no bot é o que o item faz — um
        ponto a mais para todos, no acerto, na CA ou no dano. Como a aura do
        xamã, vale a melhor quando há mais de um artífice.

        O lado dos testes de perícia não entra aqui: é o Flash of Genius que
        cuida dele, e de um jeito melhor, porque chega depois da rolagem.
        """
        melhor: dict[str, int] = {}
        for p in personagens:
            infusao = ((p.get("efeitos") or {}).get("infusao")) or {}
            for onde, quanto in infusao.items():
                melhor[onde] = max(melhor.get(onde, 0), quanto)
        if not melhor:
            return
        for c in combatentes:
            c.bonus_ataque += melhor.get("acerto", 0)
            c.ca_extra += melhor.get("ca", 0)
            c.dano_extra += melhor.get("dano", 0)

    @staticmethod
    def _aplicar_aura_de_save(
        combatentes: list[Combatente], personagens: list[dict[str, Any]]
    ) -> None:
        """Sabedoria Arcana: o grupo inteiro resiste melhor às criaturas.

        Como a Infusão e a aura do xamã, vale a melhor e não a soma. Entra em
        todos os atributos, porque a criatura escolhe qual save cobra.
        """
        melhor = max(
            (((p.get("efeitos") or {}).get("aura_save") or 0) for p in personagens),
            default=0,
        )
        if melhor <= 0:
            return
        for c in combatentes:
            c.saves = {atributo: valor + melhor for atributo, valor in c.saves.items()}

    async def _aplicar_aberturas(self, run: dict[str, Any]) -> None:
        """O que vale "ao abrir o combate": a cura do bichinho e o escudo.

        **Roda uma vez por combate, e grava.** As duas moravam em
        `_combatentes`, que e o remontador de estado: ele corre a cada clique
        e a cada redesenho do painel, entao as duas eram reaplicadas sem fim.
        A do druida nao acumulava no banco, mas era recolocada em cima do HP
        gravado toda vez — o druida tinha +9 permanente que voltava depois de
        cada golpe recebido. O THP do mago era pior: `ganhar_thp` SOMA em vez
        de substituir, e ele e gravado.

        **A cura do bichinho e do GRUPO.** O bicho lambe as feridas de quem
        esta na sala, nao so as do druida — era a intencao da habilidade, e o
        codigo cuidava so de quem a tinha.

        As outras duas opcoes do Wild Companion (dano e teste) sao numero puro
        e entram pelas chaves que ja existiam, sem passar por aqui.
        """
        tier = max(1, self._tier_da_run(run) or 1)
        personagens = await db.personagens_da_run(self.bot.db, run["id"])
        combatentes = await self._combatentes(run)
        por_user = {c.user_id: c for c in combatentes}

        # A maior cura do grupo, e nao a soma: dois druidas com o bichinho nao
        # curam em dobro, pelo mesmo motivo que duas passivas iguais nao somam.
        cura = max(
            (((p.get("efeitos") or {}).get("bichinho_cura")) or 0 for p in personagens),
            default=0,
        )
        hps: dict[int, int] = {}
        if cura:
            for c in combatentes:
                if c.caido:
                    continue
                if motor.curar_quanto(c, cura * tier):
                    hps[c.user_id] = c.hp_atual
        if hps:
            await db.definir_hp_varios(self.bot.db, run["id"], hps)

        thps: dict[int, int] = {}
        for p in personagens:
            por_tier = ((p.get("efeitos") or {}).get("escudo_arcano")) or 0
            quem = por_user.get(p["user_id"])
            if por_tier and quem is not None:
                motor.ganhar_thp(quem, por_tier * tier)
                thps[quem.user_id] = quem.thp
        if thps:
            await db.definir_thp_varios(self.bot.db, run["id"], thps)

    @staticmethod
    def _aplicar_aura_totemica(
        combatentes: list[Combatente], personagens: list[dict[str, Any]]
    ) -> None:
        """Enquanto o xama tem THP, o grupo inteiro leva um bonus.

        A aura vem da Convocacao totemica; o tier 5 a substitui por uma
        versao mais forte.
        """
        melhor = {}
        for p in personagens:
            totem = ((p.get("efeitos") or {}).get("totem")) or {}
            if not totem.get("aura"):
                continue
            dono = next((c for c in combatentes if c.user_id == p["user_id"]), None)
            if dono is None or not dono.tem_thp:
                continue
            if totem.get("aura", 0) >= melhor.get("aura", 0):
                melhor = totem
        if not melhor:
            return
        for c in combatentes:
            c.bonus_ataque += melhor.get("aura", 0)
            c.dano_extra += melhor.get("aura_dano", melhor.get("aura", 0))

    @staticmethod
    def _aplicar_ligado(combatentes: list[Combatente], ligado: dict) -> None:
        """Passa um efeito com prazo para o combatente a que ele pertence."""
        valor = ligado["valor"] or {}
        if ligado["alvo_tipo"] == "personagem":
            quem = next(
                (c for c in combatentes if c.user_id == ligado["alvo_id"]), None
            )
            if quem is None:
                return
            quem.dano_extra += valor.get("dano_extra", 0)
            quem.ca_extra += valor.get("ca", 0)
            # A acumulacao chega pelo mesmo `run_efeitos` que as habilidades,
            # mas vai para outro campo: a marca do painel e para quem tem algo
            # LIGADO chamando atencao, nao para quem simplesmente agiu.
            if ligado["efeito"] == "ameaca_gerada":
                quem.ameaca_gerada += valor.get("ameaca", 0)
            else:
                quem.ameaca_extra += valor.get("ameaca", 0)
            quem.reducao_dano = max(quem.reducao_dano, valor.get("reducao_dano", 0.0))
            # Poção de Resistência: corte plano, depois da fração acima. Vale
            # o maior, como a fração — duas fontes não somam proteção.
            quem.reducao_plana = max(
                quem.reducao_plana, valor.get("reducao_plana", 0)
            )
            quem.cura_por_turno = max(
                quem.cura_por_turno, valor.get("cura_por_turno", 0.0)
            )
            quem.vantagem = quem.vantagem or bool(valor.get("vantagem"))
            # Buff curto de grupo: o critico mais facil e o dado de dano a
            # mais. Sem isto a Danca totemica e os Guerreiros ancioes
            # gravavam o efeito e ele nao chegava a valer em golpe nenhum.
            if valor.get("critico_em"):
                quem.critico_em = min(quem.critico_em, valor["critico_em"])
            if valor.get("dano_bonus"):
                quem.dano_bonus = valor["dano_bonus"]
                quem.rotulo_dano_bonus = nome_do_efeito(ligado["efeito"])
            # Haste e afins: o segundo golpe por duracao.
            if valor.get("ataques"):
                quem.ataques = max(quem.ataques, valor["ataques"])
            # Poção da Aceleração: golpe A MAIS, e por isso soma em vez de
            # valer o maior. `ataques` é absoluto ("passa a atacar 2x") e não
            # serviria — num guerreiro de Multiattack ele não daria nada.
            if valor.get("ataques_extra"):
                quem.ataques += valor["ataques_extra"]
            # Fly: multiplica o peso dele no sorteio de alvo. Vale o menor
            # fator, que e o mais protegido.
            if valor.get("ameaca_fator") is not None:
                quem.ameaca_fator = min(
                    quem.ameaca_fator, float(valor["ameaca_fator"])
                )
            # Circle of Power: passar no save passa a escapar inteiro.
            if valor.get("save_anula"):
                quem.save_anula = True
            # Wild Shape: o corpo dele passa a ser de outro bicho. O dado de
            # arma e substituido, nao somado — e a forma que bate, nao ele.
            if valor.get("dano_arma"):
                quem.dano_arma = valor["dano_arma"]
                quem.forma = valor.get("forma", "")
            if valor.get("veneno_no_golpe"):
                quem.veneno_no_golpe = max(
                    quem.veneno_no_golpe, valor["veneno_no_golpe"]
                )
            # A sequencia do Martial Arts nao entra aqui: ela e contada golpe a
            # golpe dentro do turno, em atacar().
            return

        # Efeito posto num inimigo: quem ganha e o dono da marca.
        dono = next((c for c in combatentes if c.user_id == ligado["dono"]), None)
        if dono is None:
            return
        if valor.get("dano_bonus"):
            # (rotulo, expressao): o resumo do golpe diz "Marca do Cacador
            # 1d6 -> 4", e para isso precisa do NOME de quem marcou.
            dono.dano_por_alvo[ligado["alvo_id"]] = (
                nome_do_efeito(ligado["efeito"]),
                valor["dano_bonus"],
            )
        if valor.get("vantagem"):
            dono.vantagem_contra.add(ligado["alvo_id"])

    async def _estado_combate(
        self, run: dict[str, Any], sala: Sala
    ) -> Optional[EstadoCombate]:
        passo = self._passo(run)
        linha = await db.estado_combate(self.bot.db, run["id"], passo)
        if not linha:
            return None
        # Os numeros vem do banco, nao do conteudo: se o inimigo for escalado, e
        # esse que vale pelo resto do combate.
        inimigos = [
            motor.Inimigo(
                indice=r["indice"],
                nome=r["nome"],
                ca=r["ca"],
                ataque=r["ataque"],
                dano=r["dano"],
                hp_max=r["hp_max"],
                hp_atual=r["hp_atual"],
                ataques=r.get("ataques") or 1,
                carregada=bool(r.get("carregada", 1)),
                saves=r.get("saves") or {},
                saves_vantagem=r.get("saves_vantagem") or [],
                habilidade=r.get("habilidade"),
                golpes=r.get("golpes") or [],
                matilha=bool(r.get("matilha")),
                regeneracao=r.get("regeneracao") or 0,
            )
            for r in await db.inimigos_do_combate(self.bot.db, run["id"], passo)
        ]
        if not inimigos:
            return None
        ligados = await db.efeitos_ativos(
            self.bot.db, run["id"], passo, linha["rodada"] - 1
        )
        for ligado in ligados:
            if ligado["alvo_tipo"] != "inimigo":
                continue
            alvo = next((i for i in inimigos if i.indice == ligado["alvo_id"]), None)
            if alvo is None:
                continue
            if ligado["efeito"] == "atordoado":
                alvo.atordoado = True
            # Synaptic Static: a criatura atrapalhada erra mais enquanto dura.
            penalidade = (ligado["valor"] or {}).get("penalidade_ataque") or 0
            if penalidade:
                alvo.penalidade_ataque = max(alvo.penalidade_ataque, penalidade)
        combatentes = await self._combatentes(run, ligados)
        for ligado in ligados:
            if ligado["alvo_tipo"] == "personagem" and ligado["efeito"] == "atordoado":
                quem = next(
                    (c for c in combatentes if c.user_id == ligado["alvo_id"]), None
                )
                if quem:
                    quem.atordoado = True
        return EstadoCombate(
            inimigos=inimigos,
            rodada=linha["rodada"],
            combatentes=combatentes,
        )

    async def _preparar_combate(self, run: dict[str, Any], sala: Sala):
        """Inicializa estado, passivas de abertura e iniciativa sem renderizar."""
        # A sala diz QUEM mora nela em cada tier, e a ficha de cada criatura
        # vale como esta escrita. Nada e esticado por multiplicador: se a
        # criatura nao serve ao tier, o conteudo usa outra.
        #
        # Antes daqui saia `escalar_monstro(m, tier)`, que multiplicava HP e
        # dano em cima de criaturas ja escritas em forca cheia de Monster
        # Manual. Cinco Gargulas de 52 HP viravam 416 numa sala de tier 2, e
        # as cinco salas de combate de um dos bancos dizimavam o grupo
        # SEMPRE — 0% de vitoria com o grupo de HP cheio.
        #
        # O tier e o da INCURSAO, o mesmo que dimensiona CD, debuff e ouro:
        # um tier por run, para o cartao da sala nunca mostrar uma criatura
        # e o combate abrir com outra. Incursao aberta a todos vale
        # TIER_MAXIMO, e ai a sala cai no maior tier que ela tem escrito.
        inimigos = sala.monstros_do_tier(
            self._tier_da_run(run), self._tema_da_sala(run, sala)
        )
        await db.iniciar_combate(self.bot.db, run["id"], self._passo(run), sala.id, inimigos)

        # O que vale "ao abrir o combate" acontece AQUI, uma vez, e vai para o
        # banco. Estava em `_combatentes`, que e o remontador de estado — ele
        # roda a cada clique, a cada redesenho do painel, a cada leitura. Na
        # pratica a cura do bichinho era recolocada depois de cada dano (o
        # druida tinha +9 permanente que voltava sozinho), e o THP do mago
        # empilhava, porque `ganhar_thp` SOMA em vez de substituir.
        await self._aplicar_aberturas(run)

        estado = await self._estado_combate(run, sala)
        ordem = await self._garantir_iniciativa(run, estado) if estado else []
        return estado, ordem

    async def _abrir_combate(self, run: dict[str, Any], sala: Sala) -> None:
        canal = await self._canal(run)
        if not canal:
            return
        estado, ordem = await self._preparar_combate(run, sala)
        incursao = self._incursao_da_run(run)
        e_objetivo = bool(incursao and sala.id == incursao.objetivo.id)
        embed, arquivo = E.combate(
            sala,
            estado,
            ordem=ordem,
            vez=0,
            e_objetivo=e_objetivo,
            recompensa=sala.recompensa if e_objetivo else None,
            condicoes_do_grupo=await db.condicoes_da_run(self.bot.db, run["id"]),
        )
        de_pe = [c.user_id for c in estado.ativos] if estado else None
        mensagem = await canal.send(
            f"⚔️ {await self._chamar(run, de_pe)} — combate! Escolham ataque **ou** "
            f"habilidade: as ações saem uma de cada vez, na ordem da iniciativa.",
            embed=embed,
            view=ViewCombate(self, run["id"], sala.id, estado.inimigos if estado else None),
            file=arquivo or discord.utils.MISSING,
        )
        await db.atualizar_run(self.bot.db, run["id"], mensagem_id=mensagem.id)
        # Quem rolou acima de todo o grupo age antes de alguém clicar.
        await self._avancar(await db.buscar_run(self.bot.db, run["id"]), sala)

    async def _garantir_iniciativa(
        self, run: dict[str, Any], estado: EstadoCombate
    ) -> list[dict[str, Any]]:
        """A ordem do combate: rola na primeira vez e depois só lê do banco.

        Um combate aberto antes de existir a iniciativa rola na hora em que
        alguém mexe nele, e segue dali.
        """
        passo = self._passo(run)
        ordem = await db.iniciativa(self.bot.db, run["id"], passo)
        if not ordem:
            await db.gravar_iniciativa(
                self.bot.db, run["id"], passo, motor.rolar_iniciativas(estado)
            )
            ordem = await db.iniciativa(self.bot.db, run["id"], passo)
        return ordem

    async def _atualizar_painel(
        self,
        run: dict[str, Any],
        sala: Sala,
        estado,
        encerrado: bool = False,
    ) -> None:
        """Reescreve o painel do combate no lugar, sem postar mensagem nova."""
        canal = await self._canal(run)
        atual = await db.buscar_run(self.bot.db, run["id"])
        if not canal or not atual or not atual["mensagem_id"]:
            return
        embed, _ = await self._embed_do_painel(atual, sala, estado, encerrado)
        view = (
            None if encerrado else ViewCombate(self, run["id"], sala.id, estado.inimigos)
        )
        try:
            mensagem = await canal.fetch_message(atual["mensagem_id"])
            await mensagem.edit(embed=embed, view=view)
        except discord.HTTPException:
            pass

    async def _embed_do_painel(
        self, run: dict[str, Any], sala: Sala, estado, encerrado: bool = False
    ):
        """O painel com a ordem da iniciativa, de quem é a vez e o log da rodada."""
        passo = self._passo(run)
        linha = await db.estado_combate(self.bot.db, run["id"], passo)
        incursao = self._incursao_da_run(run)
        registro = self._registros.get(run["id"]) or {}
        return E.combate(
            sala,
            estado,
            ordem=await db.iniciativa(self.bot.db, run["id"], passo),
            vez=linha["vez"] if linha else 0,
            turnos=await db.turnos_da_rodada(
                self.bot.db, run["id"], passo, estado.rodada
            ),
            registro=registro.get("linhas"),
            anterior=registro.get("anterior"),
            e_objetivo=bool(incursao and sala.id == incursao.objetivo.id),
            encerrado=encerrado,
            condicoes_do_grupo=await db.condicoes_da_run(self.bot.db, run["id"]),
        )

    async def _niveis(self, run: dict[str, Any]) -> list[int]:
        return [p["nivel"] for p in await db.personagens_da_run(self.bot.db, run["id"])]

    async def atacar(
        self,
        interaction: discord.Interaction,
        run_id: int,
        sala_id: str,
        alvo_indice: Optional[int] = None,
    ) -> None:
        """Escolhe o ataque da rodada. Ele sai quando a iniciativa chegar em você."""
        self._guardar_efemera(run_id, interaction)
        # Avisa o Discord na hora que a resposta vem depois: isto troca os
        # 3 segundos que ele da para a primeira resposta por 15 minutos. Sem
        # isto, um combate grande numa maquina modesta estoura o prazo e o
        # jogador ve "esta interacao falhou" (erro 10062). Dai em diante
        # toda resposta tem de sair pelo `_dizer`.
        #
        # `thinking=True` NAO e enfeite, e o que faz o `ephemeral` valer.
        # Num clique de botao o defer simples e DEFERRED_MESSAGE_UPDATE —
        # "vou editar a mensagem do botao" — e o ephemeral e ignorado em
        # silencio. Dai `delete_original_response` apagava o PAINEL do
        # combate, que e a mensagem onde os botoes moram.
        await interaction.response.defer(ephemeral=True, thinking=True)
        run = await db.buscar_run(self.bot.db, run_id)
        if not run or run["status"] not in ("em_sala", "objetivo") or run["sala_atual"] != sala_id:
            await self._dizer(interaction, "Este combate já terminou.")
            return
        if not await db.esta_na_run(self.bot.db, run_id, interaction.user.id):
            await self._dizer(interaction, "Você não faz parte desta run.")
            return

        incursao = self._incursao_da_run(run)
        sala = await self._sala_corrente(run)
        estado = await self._estado_combate(run, sala)
        if estado is None:
            await self._dizer(interaction, "Este combate já terminou.")
            return

        atacante = estado.combatente(interaction.user.id)
        if atacante is None:
            await self._dizer(interaction, 
                "Você não tem ficha cadastrada. Use `/ficha registrar`.")
            return
        if atacante.caido:
            await self._dizer(interaction, AVISO_CAIDO)
            return
        if atacante.atordoado:
            await self._dizer(interaction, 
                "Você está atordoado e perde esta rodada.")
            return

        alvo = estado.alvo_preferido(alvo_indice)
        if alvo is None:
            await self._dizer(interaction, 
                "Esse inimigo já caiu — escolha outro alvo.")
            return

        passo = self._passo(run)
        gasto = await db.acao_do_turno(
            self.bot.db, run_id, passo, estado.rodada, interaction.user.id
        )
        if gasto or not await db.marcar_turno(
            self.bot.db, run_id, passo, estado.rodada, interaction.user.id, "ataque",
            alvos=[alvo.indice] if alvo_indice is not None else [],
            resolvida=False,
        ):
            await self._dizer(interaction, 
                self._turno_gasto(gasto or "ataque"))
            return
        await self._avancar(run, sala, interaction)

    async def _resolver_ataque(
        self, run: dict[str, Any], estado: EstadoCombate, user_id: int, alvos: list[int]
    ) -> str:
        """O ataque do turno, quando a vez chega. Devolve o resumo para o jogador."""
        atacante = estado.combatente(user_id)
        passo = self._passo(run)
        # O alvo escolhido pode ter caído enquanto a ação esperava: vai no próximo.
        alvo = (estado.alvo_preferido(alvos[0]) if alvos else None) or estado.alvo_preferido()
        if atacante is None or alvo is None:
            return "Nenhum inimigo de pé para atacar."

        # Multiataque gasta o turno inteiro de uma vez: se o alvo cair no meio,
        # o golpe seguinte vai para o proximo inimigo de pe.
        golpes: list[tuple[motor.GolpeAtaque, Any]] = []
        # O indice continua de onde parou: uma habilidade pode ter gravado
        # golpes antes do turno, e dois golpes nao podem dividir a mesma chave.
        indice = await db.proximo_indice_de_ataque(
            self.bot.db, run["id"], passo, estado.rodada, user_id
        )
        personagem = await self._personagem_na_run(run, user_id)
        sequencia = ((personagem or {}).get("efeitos") or {}).get("sequencia") or {}
        pilha = await self._pilha_de_sequencia(run, user_id, passo)
        for _ in range(max(1, atacante.ataques)):
            atual = estado.alvo_preferido(alvo.indice) or estado.alvo_preferido()
            if atual is None:
                break
            # A sequencia ja conta dentro do turno: o segundo golpe usa o do primeiro.
            golpe = motor.atacar_inimigo(atacante, atual, None, bonus_extra=pilha)
            if sequencia:
                pilha = motor.proxima_sequencia(
                    pilha,
                    golpe.acertou,
                    sequencia.get("por_acerto", 1),
                    sequencia.get("teto", 2),
                )
            golpes.append((golpe, atual))
            await db.registrar_ataque(
                self.bot.db, run["id"], passo, estado.rodada, user_id,
                golpe.d20, golpe.bonus, golpe.ca_alvo, golpe.dano, atual.indice, indice,
            )
            indice += 1

        # Inspiracao no ataque: o golpe que errou por pouco passa a acertar,
        # antes de o HP ir para o banco.
        await self._inspirar_o_golpe(run, estado, atacante, golpes)
        # A Marca Fatal entra DEPOIS da Inspiracao — ela vira erro em acerto,
        # e acerto marca — e ANTES de gravar o HP, para a explosao ir no
        # mesmo write.
        marcas = await self._marcar_fatal(run, estado, atacante, user_id, golpes)
        await db.definir_hp_inimigos(
            self.bot.db,
            run["id"],
            passo,
            {inimigo.indice: inimigo.hp_atual for _golpe, inimigo in golpes},
        )
        # A forma de aranha envenena quem ela acerta: o equivalente do lado do
        # inimigo e o ataque dele piorar, que e o que `penalidade_ataque` faz.
        if atacante is not None and atacante.veneno_no_golpe:
            for golpe, inimigo in golpes:
                if not golpe.acertou or inimigo.caido:
                    continue
                inimigo.penalidade_ataque = max(
                    inimigo.penalidade_ataque, atacante.veneno_no_golpe
                )
                await db.aplicar_efeito(
                    self.bot.db, run["id"], passo, "inimigo", inimigo.indice,
                    "veneno_da_aranha",
                    {"penalidade_ataque": atacante.veneno_no_golpe},
                    estado.rodada + 2, dono=user_id,
                )
        if personagem:
            await self._totem_do_golpe(run, personagem, atacante, golpes)
            await self._bencao_do_patrono(run, personagem, atacante, golpes)
        if sequencia:
            await self._guardar_sequencia(run, user_id, passo, pilha)
        self._registrar(
            run, estado.rodada, [E.linha_golpe(g) for g, _i in golpes] + marcas
        )
        resumo = E.resumo_do_golpe([(g, i.nome) for g, i in golpes])
        return resumo + ("\n" + "\n".join(marcas) if marcas else "")

    def _trava(self, run_id: int) -> asyncio.Lock:
        """Uma fila por run: dois cliques ao mesmo tempo não resolvem a vez duas vezes."""
        return self._travas.setdefault(run_id, asyncio.Lock())

    def _registrar(self, run: dict[str, Any], rodada: int, linhas: list[str]) -> None:
        """Guarda no log da rodada o que acabou de acontecer, para o painel.

        Fica em memória: um restart perde o log, não o combate.
        """
        registro = self._registros.setdefault(
            run["id"], {"rodada": rodada, "linhas": [], "anterior": None}
        )
        if registro["rodada"] != rodada:
            registro["anterior"] = (registro["rodada"], registro["linhas"])
            registro["rodada"], registro["linhas"] = rodada, []
        registro["linhas"].extend(linhas)

    async def _avancar(
        self,
        run: dict[str, Any],
        sala: Sala,
        interaction: Optional[discord.Interaction] = None,
    ) -> None:
        """Anda a iniciativa até precisar de alguém que ainda não escolheu.

        Uma de cada vez, na ordem: a criatura age sozinha quando chega a vez
        dela; o personagem que já escolheu tem a ação resolvida; quem está caído
        ou atordoado perde a vez. Para no primeiro personagem sem ação escolhida.
        Passando do último, a rodada vira e a fila recomeça do topo.

        Quem clicou (`interaction`) recebe o resultado se a vez dele chegou
        agora, ou o aviso de que a ação ficou guardada.
        """
        respondido = False

        async def responder(texto: str) -> None:
            nonlocal respondido
            if interaction is None or respondido:
                return
            respondido = True
            # Se esta exata frase ja foi para o canal, nao repete em
            # privado: quem clicou via a propria habilidade duas vezes.
            # Mas a interacao foi adiada e PRECISA ser fechada, senao o
            # Discord deixa o "pensando..." pendurado para sempre.
            if texto == self._publicado.get(run["id"]):
                try:
                    await interaction.delete_original_response()
                except discord.HTTPException:
                    pass
                return
            await self._dizer(interaction, texto)
            # Registra na hora de mandar, nao antes: parte destas respostas sai
            # depois da trava, e a rodada pode ter virado no meio. Registrada
            # antes, ela seria removida da lista por _limpar_efemeras sem ter
            # chegado a existir — e ficaria no canal para sempre.
            self._guardar_efemera(run["id"], interaction)

        async def resolver_atrasados(estado, ordem, vez) -> bool:
            """Faz agir quem está de pé e cuja vez já passou. True se agiu.

            A vez de quem está no chão é consumida no topo da rodada, e a fila
            não volta — então a cura que chegava depois devolvia o personagem
            ao combate sem devolver a rodada dele. Ele clicava, lia "sai
            quando a iniciativa chegar em você" (uma promessa que a fila já
            não podia cumprir) e a ação era descartada na virada, levando
            dentro dela o uso da habilidade ou a poção, que `_perder_a_vez`
            nunca teve a chance de devolver.

            Então **a vez perdida no chão não é gasta**: levantado na mesma
            rodada, ele age na hora. Fora da ordem de propósito — devolver o
            ponteiro faria a criatura entre ele e a cura agir duas vezes.
            """
            passo = self._passo(run)
            for posicao in ordem[:vez]:
                if posicao["tipo"] != motor.PERSONAGEM:
                    continue
                user_id = posicao["alvo_id"]
                quem = estado.combatente(user_id)
                # `caido`/`atordoado` aqui é precaução, não regra testada:
                # quando a fila passa por alguém nesse estado, `_perder_a_vez`
                # já marca a ação dele como resolvida, então não sobra turno
                # pendente para este laço achar. A guarda fica para o caso de
                # essa invariante mudar.
                if quem is None or quem.caido or quem.atordoado:
                    continue
                turno = await db.turno_de(
                    self.bot.db, run["id"], passo, estado.rodada, user_id
                )
                if not turno or turno["resolvida"]:
                    continue
                # Reivindica ANTES de resolver: ver `db.resolver_turno`.
                if not await db.resolver_turno(
                    self.bot.db, run["id"], passo, estado.rodada, user_id
                ):
                    continue
                texto = await self._resolver_turno(run, estado, user_id, turno)
                if interaction is not None and interaction.user.id == user_id:
                    await responder(texto)
                return True
            return False

        esperando: Optional[str] = None
        ativo = True
        # O fim do combate roda fora da trava: vencer pode abrir o combate do
        # objetivo, que entra de novo aqui, e a trava nao e reentrante.
        encerrar = None
        async with self._trava(run["id"]):
            viradas = 0
            while True:
                run = await db.buscar_run(self.bot.db, run["id"])
                if (
                    not run
                    or run["status"] not in ("em_sala", "objetivo")
                    or run["sala_atual"] != sala.id
                ):
                    ativo = False
                    break
                estado = await self._estado_combate(run, sala)
                if estado is None:
                    ativo = False
                    break
                passo = self._passo(run)
                if estado.encerrado:
                    ativo = False
                    # Quem chegar aqui depois nao encerra o mesmo combate de novo.
                    if self._tomar_o_fecho_do_combate(run["id"], passo):
                        encerrar = (run, estado)
                    break
                ordem = await self._garantir_iniciativa(run, estado)
                vez = (await db.estado_combate(self.bot.db, run["id"], passo))["vez"]

                # Antes de andar a fila: quem a fila já deixou atrás e voltou
                # a ficar de pé age agora. Uma por volta do laço, para o
                # estado ser lido de novo — a ação pode encerrar o combate.
                if await resolver_atrasados(estado, ordem, vez):
                    continue

                if vez >= len(ordem):
                    viradas += 1
                    if viradas > MAX_RODADAS_SOZINHAS:
                        # Nunca deve acontecer; se acontecer, o grupo precisa
                        # saber por que o painel parou.
                        canal = await self._canal(run)
                        if canal:
                            await canal.send(
                                f"⏳ O grupo inteiro segue preso depois de "
                                f"{MAX_RODADAS_SOZINHAS} rodadas. O combate espera "
                                f"alguem se soltar — se travar de vez, "
                                f"`/incursao desistir` encerra a run."
                            )
                        break
                    await self._virar_rodada(run, sala, estado)
                    continue

                ator = ordem[vez]
                if ator["tipo"] == motor.INIMIGO:
                    inimigo = estado.inimigo(ator["alvo_id"])
                    if inimigo is not None and not inimigo.caido:
                        await self._vez_do_inimigo(run, estado, inimigo, ordem[:vez])
                    await db.definir_vez(self.bot.db, run["id"], passo, vez + 1)
                    continue

                user_id = ator["alvo_id"]
                combatente = estado.combatente(user_id)
                # Aliado conjurado: ninguem clica por ele. Age sozinho, como a
                # criatura, e a vez anda.
                if combatente is not None and combatente.e_invocacao:
                    if not combatente.caido and not combatente.atordoado:
                        await self._vez_da_invocacao(run, estado, combatente)
                    await db.definir_vez(self.bot.db, run["id"], passo, vez + 1)
                    continue
                turno = await db.turno_de(
                    self.bot.db, run["id"], passo, estado.rodada, user_id
                )
                if combatente is None or combatente.caido or combatente.atordoado:
                    await self._perder_a_vez(run, estado, combatente, turno)
                    await db.definir_vez(self.bot.db, run["id"], passo, vez + 1)
                    continue
                if turno is None:
                    # Combate de antes da iniciativa: o golpe gravado ja valeu.
                    if await db.acao_do_turno(
                        self.bot.db, run["id"], passo, estado.rodada, user_id
                    ):
                        await db.definir_vez(self.bot.db, run["id"], passo, vez + 1)
                        continue
                    esperando = ator["nome"]
                    break
                if not turno["resolvida"] and await db.resolver_turno(
                    # Reivindica ANTES de resolver: ver `db.resolver_turno`.
                    self.bot.db, run["id"], passo, estado.rodada, user_id
                ):
                    texto = await self._resolver_turno(run, estado, user_id, turno)
                    if interaction is not None and interaction.user.id == user_id:
                        await responder(texto)
                await db.definir_vez(self.bot.db, run["id"], passo, vez + 1)

            if ativo:
                await self._atualizar_painel(run, sala, estado)
        if encerrar:
            await responder("O combate acabou antes da sua vez.")
            await self._encerrar_combate(encerrar[0], sala, encerrar[1])
            return
        if esperando:
            await responder(
                f"Ação guardada: sai quando a iniciativa chegar em você. "
                f"Agora é a vez de **{esperando}**."
            )
        else:
            await responder("Ação guardada.")

    async def _perder_a_vez(
        self, run: dict[str, Any], estado: EstadoCombate, combatente, turno
    ) -> None:
        """Caído ou atordoado na hora da vez: a ação guardada não sai.

        O uso de uma habilidade escolhida volta — ela não chegou a acontecer.
        """
        if combatente is not None and combatente.atordoado and not combatente.caido:
            self._registrar(run, estado.rodada, [f"💫 {combatente.nome} está atordoado e perde a vez"])
        if not turno or turno["resolvida"]:
            return
        passo = self._passo(run)
        if not await db.resolver_turno(
            self.bot.db, run["id"], passo, estado.rodada, turno["user_id"]
        ):
            # Alguem ja reivindicou esta acao: devolver aqui tambem devolveria
            # a reserva duas vezes.
            return
        await self._devolver_reservas(run, turno, passo)

    async def _devolver_reservas(
        self, run: dict[str, Any], turno: dict, passo: int
    ) -> None:
        """Devolve o que a ação guardada tinha reservado: o item ou o uso.

        A poção sai da bolsa na **escolha**, e a habilidade gasta o uso na
        escolha — as duas são reservadas antes de a vez chegar, para dois
        cliques no mesmo instante não gastarem a mesma coisa. Quando a vez não
        chega, a reserva tem de voltar.

        Dois caminhos chamam aqui, e são os dois jeitos de a vez não chegar:
        `_perder_a_vez` (caiu ou foi atordoado) e `_devolver_pendentes` (o
        combate ou a run acabou antes).
        """
        pocao = consumiveis.item(turno["acao"])
        if pocao is not None:
            personagem = await self._personagem_na_run(run, turno["user_id"])
            if personagem is not None:
                await db.devolver_item(self.bot.db, personagem["id"], pocao.id)
            return
        habilidade = cl.POR_ID.get(turno["acao"])
        if habilidade is not None:
            await db.devolver_uso(
                self.bot.db, run["id"], turno["user_id"], habilidade.chave_de_uso,
                self._chave_de_recarga(habilidade, run, passo),
            )

    async def _devolver_pendentes(self, run: dict[str, Any]) -> None:
        """O combate acabou antes da vez de alguém: a reserva volta.

        Vencer antes do turno de quem já tinha escolhido queimava a escolha: a
        Poção de Vida desaparecia da bolsa e a Fireball ficava gasta, sem
        nenhuma das duas ter acontecido. É a mesma devolução de
        `_perder_a_vez`, pelo mesmo motivo — a ação não aconteceu —, e o
        combate que termina é só o terceiro jeito de a vez não chegar.
        """
        passo = self._passo(run)
        for turno in await db.turnos_pendentes(self.bot.db, run["id"], passo):
            if not await db.resolver_turno(
                self.bot.db, run["id"], passo, turno["rodada"], turno["user_id"]
            ):
                continue
            await self._devolver_reservas(run, turno, passo)

    async def _resolver_turno(
        self, run: dict[str, Any], estado: EstadoCombate, user_id: int, turno: dict
    ) -> str:
        """Faz a ação que o personagem escolheu, agora que a vez chegou."""
        if turno["acao"] == "ataque":
            texto = await self._resolver_ataque(run, estado, user_id, turno["alvos"])
            await self._gerar_ameaca(run, estado, user_id, None)
            await self._marcas_orfas(run, estado)
            return texto
        # A poção guardada na vez: ela já saiu da bolsa quando foi escolhida,
        # então aqui ela só precisa valer. O id dela não está entre as
        # habilidades do personagem — é do catálogo de consumíveis.
        pocao = consumiveis.item(turno["acao"])
        if pocao is not None:
            texto = await self._resolver_habilidade(
                run, estado, user_id, consumiveis.habilidade_de(pocao), turno["alvos"]
            )
            await self._gerar_ameaca(run, estado, user_id, pocao.acao)
            return texto

        personagem = await self._personagem_na_run(run, user_id)
        habilidade = next(
            (
                h for _t, h in (personagem or {}).get("habilidades") or []
                if h.id == turno["acao"]
            ),
            None,
        )
        if habilidade is None:
            return "Essa habilidade nao esta mais disponivel."
        texto = await self._resolver_habilidade(
            run, estado, user_id, habilidade, turno["alvos"]
        )
        await self._gerar_ameaca(run, estado, user_id, habilidade.acao)
        await self._marcas_orfas(run, estado)
        self._registrar(run, estado.rodada, [f"✨ {estado.combatente(user_id).nome} usa **{habilidade.nome}**"])
        return texto

    # A ameaca gerada vale pelo combate inteiro, e nao por um numero de
    # rodadas. O prazo grande diz isso: quem apaga a conta e a troca de sala,
    # porque o `passo` faz parte da chave em `run_efeitos`.
    PRAZO_DO_COMBATE = 10 ** 6

    EFEITO_DA_MARCA = "marca_fatal"
    EFEITO_DA_FURTIVIDADE = "furtividade"
    ID_DA_MARCA_FATAL = "marca_fatal"
    # Gravado no ladino quando a explosao sai: ela sai UMA vez por combate, e
    # dali em diante ele para de marcar. Mora em `run_efeitos` com o prazo do
    # combate, como a ameaca gerada — quem apaga e a troca de sala.
    EFEITO_MARCA_GASTA = "marca_fatal_gasta"

    async def _marcacao_gasta(self, run: dict[str, Any], user_id: int) -> bool:
        """A explosao deste combate ja saiu?

        `rodada=0` de proposito: a chave vale o combate inteiro, entao a
        pergunta nao e "vale nesta rodada" e sim "existe" — e 0 pede tudo que
        ainda nao venceu.
        """
        return any(
            e["alvo_tipo"] == "personagem"
            and e["alvo_id"] == user_id
            and e["efeito"] == self.EFEITO_MARCA_GASTA
            for e in await db.efeitos_ativos(
                self.bot.db, run["id"], self._passo(run), 0
            )
        )

    async def _marcacao_aberta(self, run: dict[str, Any], user_id: int) -> bool:
        """A Marca Fatal esta aberta neste combate para este personagem?

        A habilidade era passiva, e o que a ligava era `efeitos["marca_fatal"]`:
        o ladino marcava desde o primeiro golpe, sem decidir nada. Agora ela e
        uma chave — ele gasta a acao uma vez por combate para abrir, e dali em
        diante todo acerto marca, como antes.

        **O registro do uso E o interruptor**, e nao um estado novo:
        `gastar_uso` grava sob `combate:{passo}`, entao a chave nasce quando a
        ativa e usada, vale pelo combate inteiro e morre com ele — e ja esta
        gravada quando o golpe da propria ativa resolve, porque `usar_habilidade`
        gasta o uso antes de resolver. Por isso o ataque que abre tambem marca.

        So quem tem a habilidade consegue gastar o uso dela, entao isto tambem
        responde "este personagem e um ladino do tier 2 ou mais".
        """
        habilidade = habilidades.POR_ID.get(self.ID_DA_MARCA_FATAL)
        if habilidade is None:
            return False
        gastos = await db.usos_da_run(self.bot.db, run["id"], user_id)
        chave = self._chave_de_recarga(habilidade, run, self._passo(run))
        if gastos.get((habilidade.chave_de_uso, chave), 0) <= 0:
            return False
        # A torneira fecha sozinha na explosao: ela sai UMA vez por combate.
        return not await self._marcacao_gasta(run, user_id)

    async def _fechar_marcacao(self, run: dict[str, Any], user_id: int, estado) -> None:
        """Grava que a explosao deste ladino ja saiu, e limpa o que sobrou.

        Chamado pela propria explosao. O prazo e o do combate inteiro, como a
        ameaca gerada: quem apaga e a troca de sala, porque o `passo` faz
        parte da chave em `run_efeitos`.
        """
        passo = self._passo(run)
        await db.aplicar_efeito(
            self.bot.db, run["id"], passo, "personagem", user_id,
            self.EFEITO_MARCA_GASTA, {}, self.PRAZO_DO_COMBATE, dono=user_id,
        )
        # As marcas que ficaram em outro inimigo morrem com a marcacao: sem
        # ela aberta nao ha terceira marca, e elas so enfeitariam o painel.
        for indice, marca in (await self._marcas_de(run, estado.rodada)).items():
            if marca["dono"] == user_id:
                await db.remover_efeito(
                    self.bot.db, run["id"], passo, "inimigo", indice,
                    self.EFEITO_DA_MARCA,
                )

    async def _marcas_de(self, run: dict[str, Any], rodada: int) -> dict[int, dict]:
        """As Marcas Fatais vivas, por índice de inimigo."""
        return {
            e["alvo_id"]: e
            for e in await db.efeitos_ativos(
                self.bot.db, run["id"], self._passo(run), rodada
            )
            if e["alvo_tipo"] == "inimigo" and e["efeito"] == self.EFEITO_DA_MARCA
        }

    async def _marcar_fatal(
        self, run: dict[str, Any], estado, atacante, user_id: int, golpes: list
    ) -> list[str]:
        """Com a marcação aberta, todo acerto marca; a terceira explode.

        As regras da ficha, e como elas se encaixam:

        - **a marcação não vem de graça**: o ladino gasta a ativa do tier 2
          uma vez por combate para abri-la (`_marcacao_aberta`). O golpe
          dessa própria ativa já marca, porque o uso é gravado antes de o
          golpe resolver;
        - acertar aplica 1 marca, e **devolve o prazo inteiro** às que já
          estão lá — não decrementa para 2, volta para 3;
        - na terceira marca elas explodem na hora, sem rolar acerto;
        - passar 3 turnos sem marcar o mesmo inimigo perde as marcas dele,
          e disso quem cuida é `limpar_efeitos_vencidos`, que já roda ao
          virar a rodada.

        O dado sai do tier do LADINO, e não do grupo: é a ficha dele que
        cresce. Chamado dos dois caminhos de ataque — o do turno e o da
        ativa —, porque "sempre que acerta um ataque" vale para os dois.

        Não altera o HP no banco: o estrago entra em `inimigo.hp_atual`, e
        quem chama grava junto com o dano dos golpes.
        """
        if atacante is None or not golpes:
            return []
        if not await self._marcacao_aberta(run, user_id):
            return []
        personagem = await self._personagem_na_run(run, user_id)
        dado = habilidades.DANO_DA_MARCA[tier((personagem or {}).get("nivel") or 1)]
        vivas = await self._marcas_de(run, estado.rodada)
        # Conta local porque um multiataque marca duas vezes no mesmo turno,
        # e a segunda precisa ver a primeira.
        quantas = {i: (e["valor"] or {}).get("marcas", 0) for i, e in vivas.items()}
        passo, linhas = self._passo(run), []
        for golpe, inimigo in golpes:
            if not golpe.acertou or inimigo.caido:
                continue
            marcas = quantas.get(inimigo.indice, 0) + 1
            if marcas >= habilidades.MARCAS_PARA_EXPLODIR:
                dano = sum(motor.rolar_dano(dado) for _ in range(marcas))
                inimigo.hp_atual = max(0, inimigo.hp_atual - dano)
                await db.remover_efeito(
                    self.bot.db, run["id"], passo, "inimigo", inimigo.indice,
                    self.EFEITO_DA_MARCA,
                )
                caiu = " — e **cai**" if inimigo.caido else ""
                linhas.append(
                    f"🎯 As **{marcas}** Marcas Fatais explodem em "
                    f"**{inimigo.nome}**: **{dano}** de dano ({marcas}×{dado})"
                    f"{caiu}"
                )
                # A explosão sai UMA vez por combate, e fecha a torneira: o
                # ciclo não recomeça. E as marcas que ficaram em OUTRO inimigo
                # saem com ela — sem marcação aberta elas nunca mais crescem,
                # e o 🎯 no nome dele passaria a prometer uma explosão que não
                # vem.
                #
                # O `break` é precaução e não regra testada: o ladino tem UM
                # golpe, então hoje não há golpe seguinte neste turno para
                # marcar. Se um dia ele ganhar Multiataque, é o `break` que
                # impede o segundo golpe de abrir a pilha de novo.
                await self._fechar_marcacao(run, user_id, estado)
                linhas.append(
                    "🎯 A Marca Fatal se fecha: foi a explosão deste combate."
                )
                break
            quantas[inimigo.indice] = marcas
            await db.aplicar_efeito(
                self.bot.db, run["id"], passo, "inimigo", inimigo.indice,
                self.EFEITO_DA_MARCA, {"marcas": marcas},
                estado.rodada + habilidades.TURNOS_DA_MARCA, dono=user_id,
            )
            linhas.append(
                f"🎯 **{inimigo.nome}** fica com **Marca Fatal ×{marcas}**"
            )
        return linhas

    async def _marcas_orfas(self, run: dict[str, Any], estado) -> None:
        """O inimigo marcado caiu. No tier 5 as marcas não vão com ele.

        Roda no fecho do turno, que é por onde TODA ação de jogador passa:
        o inimigo pode cair no golpe de qualquer um, e não só do ladino.

        Abaixo do tier 5 as marcas se perdem com o inimigo — é o que o
        documento diz, e a transferência é justamente o que o tier 5 traz.
        """
        if estado is None:
            return
        passo = self._passo(run)
        for indice, marca in (await self._marcas_de(run, estado.rodada)).items():
            inimigo = estado.inimigo(indice)
            if inimigo is None or not inimigo.caido:
                continue
            # Sai do morto de um jeito ou de outro: ou ela passa, ou se perde.
            await db.remover_efeito(
                self.bot.db, run["id"], passo, "inimigo", indice,
                self.EFEITO_DA_MARCA,
            )
            dono = marca["dono"]
            quantas = (marca["valor"] or {}).get("marcas", 0)
            sobraram = [i for i in estado.inimigos_vivos if i.indice != indice]
            personagem = (
                await self._personagem_na_run(run, dono) if dono else None
            )
            transfere = ((personagem or {}).get("efeitos") or {}).get(
                "marca_fatal_transfere"
            )
            if not (transfere and sobraram and quantas):
                continue
            canal = await self._canal(run)
            if canal is None:
                continue
            await canal.send(
                f"🎯 <@{dono}> — **{inimigo.nome}** caiu com "
                f"**{quantas}** Marca(s) Fatal(is) ainda sem explodir. "
                f"Para quem elas passam?",
                view=ViewMarcaOrfa(
                    self, run["id"], dono, quantas, marca["expira"], sobraram
                ),
            )

    async def transferir_marcas(
        self, interaction: discord.Interaction, run_id: int, dono: int,
        indice: int, marcas: int, expira: int,
    ) -> None:
        """Move as marcas do inimigo que caiu para o que o ladino escolheu.

        O prazo vai como estava — `expira` é número de rodada, absoluto —,
        que é o "mantendo sua duração restante" do documento.
        """
        if interaction.user.id != dono:
            await interaction.response.send_message(
                "Estas marcas não são suas.", ephemeral=True
            )
            return
        run = await db.buscar_run(self.bot.db, run_id)
        if not run or run["status"] not in ("em_sala", "objetivo"):
            await interaction.response.send_message(
                "Este combate já acabou.", ephemeral=True
            )
            return
        sala = await self._sala_corrente(run)
        estado = await self._estado_combate(run, sala) if sala else None
        alvo = estado.inimigo(indice) if estado else None
        if alvo is None or alvo.caido:
            await interaction.response.send_message(
                "Esse inimigo já caiu — escolha outro.", ephemeral=True
            )
            return
        await db.aplicar_efeito(
            self.bot.db, run_id, self._passo(run), "inimigo", indice,
            self.EFEITO_DA_MARCA, {"marcas": marcas}, expira, dono=dono,
        )
        await interaction.response.edit_message(
            content=(
                f"🎯 As **{marcas}** Marca(s) Fatal(is) passam para "
                f"**{alvo.nome}**, com o prazo que faltava."
            ),
            view=None,
        )
        self._registrar(
            run, estado.rodada,
            [f"🎯 As marcas passam para **{alvo.nome}** (×{marcas})"],
        )

    async def _escondido(self, run: dict[str, Any], user_id: int, rodada: int) -> bool:
        """O ladino está em Stealth nesta rodada?

        O `desde` existe porque o ataque que ABRE a Furtividade conta ameaça
        normalmente — a ficha diz "realiza um ataque e depois entra em
        Stealth". Sem ele, o próprio golpe que liga a habilidade já sairia
        de graça.
        """
        for e in await db.efeitos_ativos(
            self.bot.db, run["id"], self._passo(run), rodada
        ):
            if (
                e["alvo_tipo"] == "personagem"
                and e["alvo_id"] == user_id
                and e["efeito"] == self.EFEITO_DA_FURTIVIDADE
                and rodada >= (e["valor"] or {}).get("desde", 0)
            ):
                return True
        return False

    async def _gerar_ameaca(
        self, run: dict[str, Any], estado: EstadoCombate, user_id: int, acao
    ) -> None:
        """O que o personagem acabou de fazer chama atencao da criatura.

        Mora aqui, no `_resolver_turno`, e nao em cada resolvedor: este e o
        gargalo por onde o ataque e a habilidade passam os dois, e o uso FORA
        de combate nao passa — que e o certo, nao ha criatura para chamar.
        """
        quem = estado.combatente(user_id)
        if quem is None or quem.e_invocacao:
            return
        # Furtividade: a ameaca para de SUBIR, e nao e zerada. O que ele
        # acumulou continua valendo, e segue podendo cair por outros efeitos.
        if await self._escondido(run, user_id, estado.rodada):
            return
        await db.somar_ameaca_gerada(
            self.bot.db, run["id"], self._passo(run), user_id,
            ameaca.gerada_por(quem.classe, acao), self.PRAZO_DO_COMBATE,
        )

    async def _vez_do_inimigo(
        self,
        run: dict[str, Any],
        estado: EstadoCombate,
        inimigo: motor.Inimigo,
        antes: list[dict[str, Any]],
    ) -> None:
        """A criatura age: ataca ou conjura, e o que ela fez vai para o log."""
        if inimigo.atordoado:
            self._registrar(run, estado.rodada, [f"💫 {inimigo.nome} está atordoado e perde a vez"])
            return
        feito = motor.turno_do_inimigo(inimigo, estado, None)
        if feito.regenerou:
            await db.definir_hp_inimigos(
                self.bot.db, run["id"], self._passo(run), {inimigo.indice: inimigo.hp_atual}
            )
        # Inspiracao no save: antes de gravar qualquer coisa. Mexer aqui evita
        # escrever no banco o dano, o atordoamento e a condicao que o bardo
        # acabou de impedir — e so depois apaga-los.
        await self._inspirar_o_save(run, estado, feito)
        for atingido in feito.atingidos:
            await self._gravar_hp_do_combatente(run, atingido)
        if inimigo.habilidade:
            await db.definir_carga_inimigos(
                self.bot.db, run["id"], self._passo(run), {inimigo.indice: inimigo.carregada}
            )
        # Quem ja passou da vez nesta rodada perde a da proxima; quem ainda
        # nao agiu perde a desta.
        ja_agiram = {a["alvo_id"] for a in antes if a["tipo"] == motor.PERSONAGEM}
        await self._guardar_atordoamentos(run, estado, feito.investidas, ja_agiram)
        pegaram = await self._guardar_debuffs(run, feito.investidas)
        await self._reacoes_do_revide(run, estado, feito.golpes, feito.investidas)
        linhas = []
        if feito.regenerou:
            linhas.append(f"🩹 **{inimigo.nome}** regenera **{feito.regenerou}** HP")
        linhas += [
            E.texto_da_investida(investida)
            for investida in feito.investidas
            if not investida.do_golpe
        ]
        for posicao, (golpe, atingido) in enumerate(feito.golpes):
            arma = f" · {golpe.arma}" if golpe.arma else ""
            linhas.append(
                f"↩️ **{golpe.atacante}**{arma} · "
                f"{E.texto_do_contra_ataque(golpe, atingido.nome)}"
            )
            # O teste que o golpe impos sai logo abaixo dele.
            if posicao in feito.efeitos_dos_golpes:
                linhas.append(E.texto_da_investida(feito.efeitos_dos_golpes[posicao]))
        linhas += [f"🧪 {texto}" for texto in pegaram]
        self._registrar(run, estado.rodada, linhas)

    async def _virar_rodada(self, run: dict[str, Any], sala: Sala, estado) -> None:
        """Passou do último da iniciativa: efeitos viram e a fila volta ao topo."""
        estado.rodada += 1
        await db.atualizar_rodada(self.bot.db, run["id"], self._passo(run), estado.rodada)
        await self._virar_efeitos(run, estado)
        self._registrar(run, estado.rodada, [])
        await self._limpar_efemeras(run["id"])
        await self._apagar_chamada(run["id"])
        await self._apagar_usadas(run["id"])
        # O painel e editado no lugar, e edicao nao notifica ninguem: a chamada
        # da rodada vai numa mensagem propria, para todos que podem agir.
        seguinte = await self._estado_combate(run, sala)
        canal = await self._canal(run)
        if canal and seguinte is not None and not seguinte.encerrado and seguinte.ativos:
            self._chamadas[run["id"]] = await canal.send(
                f"⚔️ **Rodada {seguinte.rodada}** — "
                f"{await self._chamar(run, [c.user_id for c in seguinte.ativos])} "
                f"— escolham a ação; ela sai na ordem da iniciativa."
            )

    def _tomar_o_fecho_do_combate(self, run_id: int, passo: int) -> bool:
        """Reivindica o direito de encerrar ESTE combate. Uma vez por combate.

        **Dois caminhos** chegam ao fim de um combate: a iniciativa, em
        `_avancar`, e a magia que resolve na hora — o Quickened Spell, que
        sai fora da vez e por isso nao passa por lá. Os dois podem chegar no
        mesmo instante, e `_encerrar_combate` paga o ouro da sala e abre a
        parada seguinte: rodar duas vezes pagaria duas vezes.

        **E sincrono de propósito.** Entre o `in` e o `add` nao existe
        `await`, entao o loop de eventos nao tem onde entrar e a reivindicacao
        e indivisivel sem trava nenhuma. Um `async def` aqui abriria
        exatamente o buraco que ele existe para fechar.
        """
        if (run_id, passo) in self._encerrados:
            return False
        self._encerrados.add((run_id, passo))
        return True

    async def _encerrar_combate(self, run: dict[str, Any], sala: Sala, estado) -> None:
        """Um dos lados caiu: fecha o painel e segue a run (ou a encerra)."""
        # Antes de tudo: quem escolheu e nao chegou a agir recebe de volta o
        # que a escolha reservou. Vale vencendo e perdendo — a acao nao
        # aconteceu nos dois casos.
        await self._devolver_pendentes(run)
        await self._atualizar_painel(run, sala, estado, encerrado=True)
        await self._limpar_efemeras(run["id"])
        await self._apagar_chamada(run["id"])
        await self._apagar_usadas(run["id"])
        self._registros.pop(run["id"], None)
        if estado.inimigos_derrotados:
            await self._apos_combate_vencido(run, sala, estado)
            return
        canal = await self._canal(run)
        await self._encerrar_run(run, "fracasso")
        incursao = self._incursao_da_run(run)
        # Mesmo derrotado, o grupo levou a run ate o fim: a participacao conta.
        await self._creditar(
            run, config.PONTOS_PARTICIPACAO, "Participação na incursão", "participacao"
        )
        if canal:
            lancamentos, total = await self._balanco(run)
            await canal.send(
                embed=E.run_fracassada(
                    incursao, lancamentos, total,
                    await self._caminho(run), sala,
                    await db.ouro_da_run(self.bot.db, run["id"]),
                )
            )

    async def _dizer(
        self, interaction: discord.Interaction, texto: str, *, view=None
    ) -> None:
        """Resposta privada que funciona antes e depois do `defer`.

        O Discord da 3 SEGUNDOS para a primeira resposta a uma interacao.
        Passando disso o token morre e qualquer resposta devolve
        `10062 Unknown interaction` — o jogador ve "esta interacao falhou".
        Tres segundos bastavam na maquina de desenvolvimento e nao bastam no
        servidor, que e um oitavo de OCPU compartilhado.

        A saida e `defer()` no inicio do comando, que troca os 3 segundos por
        15 minutos. Mas depois dele `response.send_message` passa a ser erro:
        a resposta ja foi dada. Este ajudante escolhe sozinho.

        Edita a resposta original em vez de mandar followup de proposito:
        `_limpar_efemeras` apaga as efemeras com `delete_original_response`,
        que so alcanca a original. Com followup elas ficariam orfas no canal.

        `view` existe porque nem toda resposta destes comandos e texto: a
        habilidade que pede alvo abre um menu. Tudo que responde depois do
        `defer` tem de passar por aqui — responder direto levanta
        `InteractionResponded` dentro do callback, e o jogador fica com o
        "pensando..." pendurado para sempre.
        """
        if interaction.response.is_done():
            await interaction.edit_original_response(content=texto, view=view)
        else:
            await interaction.response.send_message(
                texto, view=view, ephemeral=True
            )

    def _guardar_efemera(self, run_id: int, interaction: discord.Interaction) -> None:
        """Marca uma resposta privada para sumir quando a rodada virar."""
        self._efemeras.setdefault(run_id, []).append(interaction)

    async def _limpar_efemeras(self, run_id: int) -> None:
        """Apaga as respostas privadas da rodada que acabou.

        Cada uma so pode ser apagada pela propria interacao, e o token dela
        vale 15 minutos — o que passou disso simplesmente fica.
        """
        for interaction in self._efemeras.pop(run_id, []):
            try:
                await interaction.delete_original_response()
            except (discord.HTTPException, AttributeError):
                pass

    async def _apagar_usadas(self, run_id: int) -> None:
        """Tira do canal os anuncios de habilidade da rodada que acabou.

        Enquanto a rodada corre eles sao a narracao: quem conjurou o que,
        e em quem. Virada a rodada viram historico, e o painel — que fica
        e e editado no lugar — ja guarda o estado de agora.

        Roda no virar da rodada E no fim do combate: a segunda chamada
        pega o que foi usado na ultima rodada, que nao chega a virar.
        """
        self._publicado.pop(run_id, None)
        for mensagem in self._usadas.pop(run_id, []):
            try:
                await mensagem.delete()
            except (discord.HTTPException, AttributeError):
                pass

    async def _apagar_chamada(self, run_id: int) -> None:
        """Tira do canal a marcacao da rodada anterior."""
        mensagem = self._chamadas.pop(run_id, None)
        if mensagem is None:
            return
        try:
            await mensagem.delete()
        except (discord.HTTPException, AttributeError):
            pass

    async def _apagar_passo_anterior(self, run: dict[str, Any]) -> None:
        """Apaga a mensagem do passo que acabou: a votacao, ou a sala.

        O canal fica com um cartao so — o do momento. O caminho inteiro volta
        no fim da run, no resumo.
        """
        atual = await db.buscar_run(self.bot.db, run["id"]) or run
        if not atual.get("mensagem_id"):
            return
        canal = await self._canal(atual)
        if canal is None:
            return
        try:
            mensagem = await canal.fetch_message(atual["mensagem_id"])
            await mensagem.delete()
        except (discord.HTTPException, AttributeError):
            pass
        await db.atualizar_run(self.bot.db, run["id"], mensagem_id=None)

    async def _caminho(self, run: dict[str, Any]) -> list[tuple[Sala, bool]]:
        """As salas por onde o grupo passou, com o desfecho de cada uma.

        Devolve pares `(sala, venceu)`: o cartao do fim mostrava a
        DIFICULDADE de cada sala, que e o numero de quem escreve conteudo —
        quem leu a run quer saber se passou ou se se deu mal ali.
        """
        incursao = self._incursao_da_run(run)
        if not incursao:
            return []
        pares = await db.visitadas_com_desfecho(self.bot.db, run["id"])
        caminho = [(self._sala(incursao, sala_id), venceu) for sala_id, venceu in pares]
        return [(s, venceu) for s, venceu in caminho if s is not None]

    async def _chamar(
        self, run: dict[str, Any], user_ids: Optional[list[int]] = None
    ) -> str:
        """Marca quem precisa agir agora. Sem lista, marca o grupo inteiro.

        Vai no `content` da mensagem, e nao no embed: e o texto solto que faz o
        Discord notificar.
        """
        if user_ids is None:
            user_ids = await db.participantes(self.bot.db, run["id"])
        return " ".join(f"<@{user_id}>" for user_id in user_ids)

    def _turno_gasto(self, acao: str) -> str:
        """O aviso de quem ja agiu, dizendo com o que gastou o turno."""
        if acao == "ataque":
            return "Você já atacou nesta rodada — é um ataque **ou** uma habilidade."
        pocao = consumiveis.item(acao)
        if pocao is not None:
            return (
                f"Você já bebeu **{pocao.nome}** nesta rodada — beber é a ação "
                f"do turno. Só a Poção da Aceleração não custa a ação."
            )
        habilidade = cl.POR_ID.get(acao)
        nome = habilidade.nome if habilidade else acao
        return (
            f"Você já usou **{nome}** nesta rodada — é uma habilidade **ou** um ataque."
        )

    # ------------------------------------------------------ habilidades

    @staticmethod
    def _chave_de_recarga(habilidade, run: dict[str, Any], passo: int) -> str:
        """Quando esta habilidade zera: por combate, por descanso ou por run."""
        if habilidade.escopo == "combate":
            return f"combate:{passo}"
        if habilidade.escopo == "descanso":
            return f"descanso:{run['descansos']}"
        return "incursao"

    async def _aviso_de_requisito(self, run, estado, user_id: int, habilidade) -> Optional[str]:
        """O requisito de uma ativa vale no painel e na substituicao."""
        exigida = (habilidade.acao or {}).get("exige")
        if not exigida or estado is None:
            return None
        ligados = await db.efeitos_ativos(
            self.bot.db, run["id"], self._passo(run), estado.rodada - 1
        )
        if any(
            e["efeito"] == exigida and e["alvo_id"] == user_id
            and e["alvo_tipo"] == "personagem"
            for e in ligados
        ):
            return None
        return f"**{habilidade.nome}** so vale com a outra habilidade ligada."

    async def _habilidades_disponiveis(
        self, run: dict[str, Any], personagem: dict[str, Any], passo: int
    ) -> list[tuple]:
        """As ativas que o bot ja executa e que ainda tem uso. (hab, restantes)."""
        gastos = await db.usos_da_run(self.bot.db, run["id"], personagem["user_id"])
        disponiveis = []
        for _tier, habilidade in personagem.get("habilidades") or []:
            if not habilidade.acionavel:
                continue
            if (habilidade.acao or {}).get("tipo") == "reacao":
                continue  # dispara sozinha quando o gatilho acontece
            chave = self._chave_de_recarga(habilidade, run, passo)
            restantes = habilidade.vezes - gastos.get((habilidade.chave_de_uso, chave), 0)
            if restantes > 0:
                disponiveis.append((habilidade, restantes))
        return disponiveis

    async def _personagem_na_run(
        self, run: dict[str, Any], user_id: int
    ) -> Optional[dict[str, Any]]:
        for p in await db.personagens_da_run(self.bot.db, run["id"]):
            if p["user_id"] == user_id:
                return p
        return None

    async def abrir_habilidades(
        self, interaction: discord.Interaction, run_id: int, sala_id: str
    ) -> None:
        """Mostra, so para quem clicou, o que ele pode usar agora."""
        self._guardar_efemera(run_id, interaction)
        run = await db.buscar_run(self.bot.db, run_id)
        if not run or run["status"] not in ("em_sala", "objetivo"):
            await interaction.response.send_message("Esta sala ja terminou.", ephemeral=True)
            return
        personagem = await self._personagem_na_run(run, interaction.user.id)
        if personagem is None:
            await interaction.response.send_message(
                "Voce nao faz parte desta run.", ephemeral=True
            )
            return

        # Em combate, quem ja agiu nao abre o menu: o turno e um so.
        incursao = self._incursao_da_run(run)
        sala = await self._sala_corrente(run)
        if sala is not None and sala.e_combate:
            estado = await self._estado_combate(run, sala)
            if estado is not None:
                gasto = await db.acao_do_turno(
                    self.bot.db, run_id, self._passo(run), estado.rodada,
                    interaction.user.id,
                )
                if gasto:
                    await interaction.response.send_message(
                        self._turno_gasto(gasto), ephemeral=True
                    )
                    return

        disponiveis = await self._habilidades_disponiveis(
            run, personagem, self._passo(run)
        )
        if not disponiveis:
            await interaction.response.send_message(
                "Voce nao tem habilidade para usar agora. Veja `/ficha ver`: as ativas "
                "marcadas *(em breve)* ainda nao estao prontas, e as outras podem ter "
                "acabado os usos.",
                ephemeral=True,
            )
            return

        opcoes = [
            (h.id, h.nome, f"{restantes} uso(s) — {h.texto}")
            for h, restantes in disponiveis
        ]
        await interaction.response.send_message(
            "O que voce usa?",
            view=SeletorHabilidade(self, run_id, sala_id, opcoes),
            ephemeral=True,
        )

    async def _dizer_ou_apagar(
        self, run: dict[str, Any], interaction: discord.Interaction, texto: str
    ) -> None:
        """A resposta privada — ou nenhuma, quando a frase já foi ao canal.

        É a mesma regra de `_avancar`, para quem resolve FORA da fila da
        iniciativa: se esta exata frase acabou de ser publicada, repeti-la em
        privado mostra a própria ação duas vezes na tela. A interação adiada
        ainda precisa ser fechada, senão o Discord deixa o "pensando..."
        pendurado para sempre.
        """
        if texto == self._publicado.get(run["id"]):
            try:
                await interaction.delete_original_response()
            except discord.HTTPException:
                pass
            return
        await self._dizer(interaction, texto)

    async def _pocoes_na_bolsa(self, personagem: dict[str, Any]) -> list[tuple]:
        """As poções que este personagem carrega: (poção, quantas).

        A bolsa é do PERSONAGEM e não da run: o que ele comprou no mercado
        continua com ele de uma incursão para a outra, e o que ele bebeu não
        volta no fim. É o mesmo lugar onde o equipamento espera para ser
        vestido (`personagem_itens`), só que com quantidade.
        """
        bolsa = await db.itens_na_bolsa(self.bot.db, personagem["id"])
        achadas = []
        for item_id, quantos in sorted(bolsa.items()):
            pocao = consumiveis.item(item_id)
            if pocao is not None and quantos > 0:
                achadas.append((pocao, quantos))
        return achadas

    async def abrir_pocoes(
        self, interaction: discord.Interaction, run_id: int, sala_id: str
    ) -> None:
        """Mostra, só para quem clicou, o que ele tem para beber agora."""
        self._guardar_efemera(run_id, interaction)
        run = await db.buscar_run(self.bot.db, run_id)
        if not run or run["status"] not in ("em_sala", "objetivo"):
            await interaction.response.send_message("Esta sala já terminou.", ephemeral=True)
            return
        personagem = await self._personagem_na_run(run, interaction.user.id)
        if personagem is None:
            await interaction.response.send_message(
                "Você não faz parte desta run.", ephemeral=True
            )
            return

        carregadas = await self._pocoes_na_bolsa(personagem)
        if not carregadas:
            await interaction.response.send_message(
                "Sua bolsa não tem poção nenhuma. Compre no `/mercado vitrine`.",
                ephemeral=True,
            )
            return

        # Com o turno gasto só sobra o que não custa ação: a Aceleração. Em vez
        # de recusar o botão inteiro, o menu mostra o que ainda dá — quem já
        # atacou pode beber a Aceleração e ganhar os golpes da próxima rodada.
        sala = await self._sala_corrente(run)
        gasto = None
        if sala is not None and sala.e_combate:
            estado = await self._estado_combate(run, sala)
            if estado is not None:
                gasto = await db.acao_do_turno(
                    self.bot.db, run_id, self._passo(run), estado.rodada,
                    interaction.user.id,
                )
        if gasto:
            carregadas = [(p, q) for p, q in carregadas if not p.gasta_turno]
            if not carregadas:
                await interaction.response.send_message(
                    f"{self._turno_gasto(gasto)} Só a Poção da Aceleração não "
                    f"custa a ação da rodada.",
                    ephemeral=True,
                )
                return

        opcoes = [(p.id, p.nome, q, p.texto) for p, q in carregadas]
        await interaction.response.send_message(
            "O que você bebe?",
            view=SeletorPocao(self, run_id, sala_id, opcoes),
            ephemeral=True,
        )

    async def usar_pocao(
        self,
        interaction: discord.Interaction,
        run_id: int,
        sala_id: str,
        pocao_id: str,
        escolhida: Optional[str] = None,
    ) -> None:
        """Bebe uma poção da bolsa.

        Beber é a ação da rodada, como atacar — a Poção da Aceleração é a
        única que não custa a ação, e é disso que ela vive. A poção sai da
        bolsa antes de a ação ser marcada, e volta para ela se a marcação
        falhar: assim dois cliques no mesmo instante não bebem duas.
        """
        self._guardar_efemera(run_id, interaction)
        # Como em `usar_habilidade`: o defer com `thinking=True` é o que faz o
        # ephemeral valer num clique de botão.
        await interaction.response.defer(ephemeral=True, thinking=True)
        run = await db.buscar_run(self.bot.db, run_id)
        if not run or run["status"] not in ("em_sala", "objetivo"):
            await self._dizer(interaction, "Esta sala já terminou.")
            return
        personagem = await self._personagem_na_run(run, interaction.user.id)
        if personagem is None:
            await self._dizer(interaction, "Você não faz parte desta run.")
            return
        pocao = consumiveis.item(pocao_id)
        if pocao is None:
            await self._dizer(interaction, "Essa poção não existe.")
            return

        passo = self._passo(run)
        sala = await self._sala_corrente(run)
        estado = await self._estado_combate(run, sala) if sala and sala.e_combate else None

        quem = estado.combatente(interaction.user.id) if estado else None
        if estado is not None and (quem is None or quem.caido):
            await self._dizer(interaction, AVISO_CAIDO)
            return
        if quem is not None and quem.atordoado:
            await self._dizer(interaction, "Você está atordoado e perde esta rodada.")
            return

        # A de Mana precisa saber QUAL uso devolver, e a escolha é um id de
        # habilidade — que não cabe em `run_turnos.alvos`, que é lista de
        # inteiros. Então ela é escolhida (e conferida) antes de a poção sair
        # da bolsa: menu velho não queima item.
        if pocao.acao.get("tipo") == "recarga":
            candidatas = await self._recarregaveis(
                run, personagem, pocao.acao["tier"]
            )
            if not candidatas:
                await self._dizer(
                    interaction,
                    f"Você não gastou nenhuma habilidade de tier "
                    f"{pocao.acao['tier']} nesta incursão. A poção fica na "
                    f"bolsa.",
                )
                return
            if escolhida is None:
                await self._dizer(
                    interaction,
                    f"{consumiveis.rotulo(pocao)} — qual uso ela devolve?",
                    view=SeletorRecarga(
                        self, run_id, sala_id, pocao.id,
                        [
                            (h.id, h.nome, f"{usados} uso(s) gasto(s)")
                            for h, usados in candidatas
                        ],
                    ),
                )
                return
            if escolhida not in {h.id for h, _usados in candidatas}:
                # O menu pode ter envelhecido: outra poção já devolveu aquele
                # uso, ou a habilidade nem está mais gasta.
                dela = next(
                    (
                        h.nome for _t, h in personagem.get("habilidades") or []
                        if h.id == escolhida
                    ),
                    escolhida,
                )
                await self._dizer(
                    interaction,
                    f"**{dela}** não está gasta agora. A poção fica na bolsa.",
                )
                return

        if estado is not None and pocao.gasta_turno:
            gasto = await db.acao_do_turno(
                self.bot.db, run_id, passo, estado.rodada, interaction.user.id
            )
            if gasto:
                await self._dizer(interaction, self._turno_gasto(gasto))
                return

        # A poção sai da bolsa aqui: daqui para a frente ela foi bebida, ou
        # volta explicitamente.
        if not await db.consumir_item(self.bot.db, personagem["id"], pocao.id):
            await self._dizer(
                interaction, f"Você não tem mais **{pocao.nome}** na bolsa."
            )
            return

        habilidade = consumiveis.habilidade_de(pocao)
        if pocao.acao.get("tipo") == "recarga":
            # Resolve na hora, e ainda assim gasta o turno: devolver um uso não
            # tem lugar na iniciativa — não acerta ninguém, não cura ninguém.
            if estado is not None and not await db.marcar_turno(
                self.bot.db, run_id, passo, estado.rodada, interaction.user.id,
                pocao.id, resolvida=True,
            ):
                await db.devolver_item(self.bot.db, personagem["id"], pocao.id)
                await self._dizer(interaction, self._turno_gasto("ataque"))
                return
            texto = await self._resolver_recarga(
                run, interaction.user.id, habilidade, pocao.acao, escolhida
            )
            await self._dizer_ou_apagar(run, interaction, texto)
            if estado is not None:
                # `_avancar`, e nao so redesenhar o painel: a Mana GASTA o
                # turno, e quem gasta o turno tem de empurrar a fila. Com os
                # outros jogadores ja tendo escolhido, beber Mana deixava
                # todos com acao guardada e ninguem para resolve-las: o
                # combate parava, e nao havia botao que o destravasse.
                #
                # Sem a `interaction`: o texto da pocao ja foi dito acima, e
                # `_avancar` tentaria responder a mesma interacao de novo.
                await self._avancar(run, sala)
            return

        # Fora de combate (e na Aceleração, que não custa a ação) resolve na
        # hora; o resto espera a iniciativa, como o ataque e as habilidades.
        if estado is None or not pocao.gasta_turno:
            texto = await self._resolver_habilidade(
                run, estado, interaction.user.id, habilidade, []
            )
            await self._dizer_ou_apagar(run, interaction, texto)
            if estado is not None:
                await self._atualizar_painel(run, sala, estado)
            return

        if not await db.marcar_turno(
            self.bot.db, run_id, passo, estado.rodada, interaction.user.id,
            pocao.id, resolvida=False,
        ):
            await db.devolver_item(self.bot.db, personagem["id"], pocao.id)
            await self._dizer(interaction, self._turno_gasto("ataque"))
            return
        await self._avancar(run, sala, interaction)

    async def usar_habilidade(
        self,
        interaction: discord.Interaction,
        run_id: int,
        sala_id: str,
        habilidade_id: str,
        alvos: Optional[list[int]] = None,
    ) -> None:
        """Gasta um uso e escolhe a habilidade, pedindo alvo se precisar.

        Em combate ela sai na vez do personagem, como o ataque; fora dele,
        na hora.
        """
        self._guardar_efemera(run_id, interaction)
        # Avisa o Discord na hora que a resposta vem depois: isto troca os
        # 3 segundos que ele da para a primeira resposta por 15 minutos. Sem
        # isto, um combate grande numa maquina modesta estoura o prazo e o
        # jogador ve "esta interacao falhou" (erro 10062). Dai em diante
        # toda resposta tem de sair pelo `_dizer`.
        #
        # `thinking=True` NAO e enfeite, e o que faz o `ephemeral` valer.
        # Num clique de botao o defer simples e DEFERRED_MESSAGE_UPDATE —
        # "vou editar a mensagem do botao" — e o ephemeral e ignorado em
        # silencio. Dai `delete_original_response` apagava o PAINEL do
        # combate, que e a mensagem onde os botoes moram.
        await interaction.response.defer(ephemeral=True, thinking=True)
        run = await db.buscar_run(self.bot.db, run_id)
        if not run or run["status"] not in ("em_sala", "objetivo"):
            await self._dizer(interaction, "Esta sala ja terminou.")
            return
        personagem = await self._personagem_na_run(run, interaction.user.id)
        if personagem is None:
            await self._dizer(interaction, 
                "Voce nao faz parte desta run.")
            return

        passo = self._passo(run)
        disponiveis = await self._habilidades_disponiveis(run, personagem, passo)
        habilidade = next((h for h, _r in disponiveis if h.id == habilidade_id), None)
        if habilidade is None:
            await self._dizer(interaction, 
                "Essa habilidade nao esta disponivel agora.")
            return

        incursao = self._incursao_da_run(run)
        sala = await self._sala_corrente(run)
        estado = await self._estado_combate(run, sala) if sala and sala.e_combate else None
        acao = habilidade.acao or {}

        # Quem usa precisa estar de pe quando a habilidade e de combate.
        atacante = estado.combatente(interaction.user.id) if estado else None
        if estado is not None and (atacante is None or atacante.caido):
            await self._dizer(interaction, AVISO_CAIDO)
            return
        if atacante is not None and atacante.atordoado:
            await self._dizer(interaction, 
                "Você está atordoado e perde esta rodada.")
            return

        aviso = await self._aviso_de_requisito(run, estado, interaction.user.id, habilidade)
        if aviso:
            await self._dizer(interaction, aviso)
            return

        # So a cura funciona fora do combate: o resto mexe em rodada e inimigo.
        if acao.get("tipo") != "cura" and estado is None:
            await self._dizer(interaction, 
                "Essa habilidade so vale em combate.")
            return

        # Em combate o personagem age uma vez por rodada: ou ataca, ou usa uma
        # habilidade. Reacao nao passa por aqui — dispara sozinha.
        if estado is not None:
            gasto = await db.acao_do_turno(
                self.bot.db, run_id, passo, estado.rodada, interaction.user.id
            )
            if gasto:
                await self._dizer(interaction, 
                    self._turno_gasto(gasto))
                return

        # Falta escolher em quem: abre o segundo menu antes de gastar o uso.
        if alvos is None:
            pedido = await self._pedir_alvo(interaction, run, sala_id, habilidade, estado)
            if pedido is not False:
                return
            alvos = []

        if not await db.gastar_uso(
            self.bot.db,
            run_id,
            interaction.user.id,
            habilidade.chave_de_uso,
            self._chave_de_recarga(habilidade, run, passo),
            habilidade.vezes,
        ):
            await self._dizer(interaction, 
                "Os usos desta habilidade ja acabaram.")
            return

        if estado is None:
            texto = await self._resolver_habilidade(
                run, None, interaction.user.id, habilidade, alvos
            )
            await self._dizer(interaction, texto)
            return

        # Quickened Spell: o feiticeiro lanca a magia como acao de bonus, e o
        # turno fica livre para atacar depois. A magia resolve na hora, em vez
        # de esperar a vez na iniciativa — senao ela nao seria "rapida".
        personagem = await self._personagem_na_run(run, interaction.user.id)
        if ((personagem or {}).get("efeitos") or {}).get("magia_rapida"):
            texto = await self._resolver_habilidade(
                run, estado, interaction.user.id, habilidade, alvos or []
            )
            await self._dizer(interaction, texto)
            self._guardar_efemera(run_id, interaction)
            # A magia rapida resolve AQUI e nao passa por `_avancar`, que e o
            # unico lugar que repara no fim do combate. Matando o ultimo
            # inimigo com ela, a run ficava em `objetivo` sem inimigo vivo:
            # atacar respondia "esse inimigo ja caiu, escolha outro alvo" e
            # nao havia outro para escolher. A incursao nao tinha saida.
            #
            # O estado e relido do banco, como `_avancar` faz: a magia pode ter
            # mexido em mais do que o objeto em maos sabe.
            atual = await db.buscar_run(self.bot.db, run_id) or run
            depois = await self._estado_combate(atual, sala)
            if depois is not None and depois.encerrado:
                if self._tomar_o_fecho_do_combate(run_id, passo):
                    await self._encerrar_combate(atual, sala, depois)
                return
            await self._atualizar_painel(atual, sala, depois or estado)
            return

        if not await db.marcar_turno(
            self.bot.db, run_id, passo, estado.rodada, interaction.user.id,
            habilidade.id, alvos=alvos, resolvida=False,
        ):
            await db.devolver_uso(
                self.bot.db, run_id, interaction.user.id, habilidade.chave_de_uso,
                self._chave_de_recarga(habilidade, run, passo),
            )
            await self._dizer(interaction, 
                self._turno_gasto("ataque"))
            return
        await self._avancar(run, sala, interaction)

    async def _resolver_habilidade(
        self, run: dict[str, Any], estado, user_id: int, habilidade, alvos: list[int]
    ) -> str:
        """Faz a habilidade valer. Devolve o que o jogador vê."""
        acao = habilidade.acao or {}
        if acao.get("tipo") == "cura":
            return await self._resolver_cura(run, user_id, habilidade, acao, alvos, estado)
        if acao.get("tipo") == "grupo":
            return await self._resolver_grupo(run, estado, habilidade, acao, user_id)
        if acao.get("tipo") == "duracao":
            return await self._resolver_duracao(run, user_id, estado, habilidade, acao, alvos)
        if acao.get("tipo") == "condicao":
            return await self._resolver_condicao(run, user_id, habilidade, acao)
        if acao.get("tipo") == "save":
            return await self._resolver_save(run, user_id, estado, habilidade, acao, alvos)
        if acao.get("tipo") == "invocar":
            return await self._resolver_invocar(run, user_id, estado, habilidade, acao)
        if acao.get("tipo") == "forma":
            return await self._resolver_forma(
                run, user_id, estado, habilidade, acao,
                alvos[0] if (alvos and acao.get("alvo") == "aliado") else None,
            )
        return await self._resolver_golpes(run, user_id, estado, habilidade, acao, alvos)

    async def _resolver_forma(
        self, run: dict[str, Any], user_id: int, estado, habilidade, acao,
        alvo_id: Optional[int] = None,
    ) -> str:
        """Wild Shape: o druida veste o corpo de outro bicho.

        Os números da forma vêm por tier, como o resto da tabela: dado fixo
        quebraria o tier 1 ou seria inútil no 5. A vida temporária é o corpo da
        besta — quando ela acaba, o druida volta a sangrar no HP dele.
        """
        passo = self._passo(run)
        tier_atual = max(1, self._tier_da_run(run))
        # O Wild Shape do druida cai nele; o Polymorph do feiticeiro cai num
        # aliado. A conta e a mesma: muda so quem veste o corpo.
        quem = estado.combatente(alvo_id if alvo_id is not None else user_id)
        if quem is None:
            return "Alvo invalido."

        dano = acao["dano"][min(tier_atual, max(acao["dano"]))]
        efeitos = {"dano_arma": dano, "forma": acao["nome"]}
        if acao.get("ca"):
            efeitos["ca"] = acao["ca"]
        if acao.get("ataques"):
            efeitos["ataques"] = acao["ataques"]
        if acao.get("veneno_no_golpe"):
            efeitos["veneno_no_golpe"] = acao["veneno_no_golpe"]
        if acao.get("ameaca"):
            efeitos["ameaca"] = acao["ameaca"]
        await db.aplicar_efeito(
            self.bot.db, run["id"], passo, "personagem", quem.user_id,
            habilidade.id, efeitos, estado.rodada + acao.get("turnos", 3),
        )

        # Forma Lunar: a passiva do tier 4 dobra o corpo que a forma empresta.
        dele = await self._personagem_na_run(run, user_id)
        dobra = 2 if ((dele or {}).get("efeitos") or {}).get("forma_lunar") else 1
        temporaria = acao.get("thp_por_tier", 0) * tier_atual * dobra
        if temporaria:
            motor.ganhar_thp(quem, temporaria)
            await db.definir_thp(self.bot.db, run["id"], quem.user_id, quem.thp)

        pedacos = [f"dano {dano}"]
        if acao.get("ataques", 1) > 1:
            pedacos.append(f"{acao['ataques']} golpes por rodada")
        if acao.get("ca"):
            pedacos.append(f"+{acao['ca']} de CA")
        if acao.get("ameaca"):
            pedacos.append(f"+{acao['ameaca']} de ameaca")
        if temporaria:
            pedacos.append(f"{temporaria} de vida temporaria")
        texto = (
            f"\U0001f43e **{habilidade.nome}**: {quem.nome} vira "
            f"**{acao['nome']}** — {', '.join(pedacos)}. "
            f"Por {acao.get('turnos', 3)} rodadas."
        )
        await self._anunciar_habilidade(run, texto)
        if acao.get("ataca_ao_transformar"):
            # O ataque usa o corpo que acabou de entrar, com todos os seus
            # efeitos. Reutiliza o ataque normal, incluindo o veneno da aranha.
            self._aplicar_ligado(estado.combatentes, {
                "alvo_tipo": "personagem", "alvo_id": quem.user_id,
                "efeito": habilidade.id, "valor": efeitos,
            })
            ataque = await self._resolver_ataque(run, estado, quem.user_id, [])
            texto += "\n" + ataque
        return texto

    async def _resolver_invocar(
        self, run: dict[str, Any], user_id: int, estado, habilidade, acao
    ) -> str:
        """Traz um aliado conjurado para a sala.

        Ele entra como combatente de dono, no fim da ordem da rodada, e vive
        até o grupo trocar de sala — a tabela é por passo, então ele some
        sozinho. Conjurar de novo troca o aliado: o pacto dá um por vez.
        """
        passo = self._passo(run)
        falso = await db.invocar(
            self.bot.db, run["id"], passo, user_id,
            acao["nome"], acao["ca"], acao["ataque"], acao["dano"],
            acao["hp"], acao.get("ameaca", 0),
        )
        rolagem = motor.rolar_iniciativa(
            motor.PERSONAGEM, falso, acao["nome"], acao.get("iniciativa", 0)
        )
        await db.acrescentar_iniciativa(
            self.bot.db, run["id"], passo, motor.PERSONAGEM, falso,
            acao["nome"], rolagem.d20, rolagem.modificador,
        )
        quem = estado.combatente(user_id)
        texto = (
            f"✨ **{habilidade.nome}**: {quem.nome if quem else 'Alguem'} "
            f"invoca **{acao['nome']}** — {acao['hp']} HP, CA {acao['ca']}, "
            f"ataque {fmt(acao['ataque'])} com {acao['dano']}. Ele luta "
            f"sozinho, no fim da ordem."
        )
        await self._anunciar_habilidade(run, texto)
        return texto

    async def _resolver_save(
        self, run: dict[str, Any], user_id: int, estado, habilidade, acao, alvos
    ) -> str:
        """A habilidade que força teste de resistência nas criaturas.

        É o caminho inverso do combate: até aqui só criatura cobrava save de
        personagem. A CD sai da classe de quem usou (8 + acerto), e `alvos`
        pode ser um escolhido ou "todos".
        """
        passo = self._passo(run)
        quem = await self._personagem_na_run(run, user_id)
        cd = cl.cd_de_habilidade((quem or {}).get("classe"), (quem or {}).get("nivel", 1))
        # O Metamagic do feiticeiro torce as magias DELE, para sempre: a CD
        # sobe, o dano soma um dado, a magia pega um alvo a mais, e a criatura
        # resiste com desvantagem. Vem das passivas dele, nao da acao.
        meta = (quem or {}).get("efeitos") or {}
        cd += meta.get("cd_magia", 0)
        desvantagem = bool(meta.get("save_com_desvantagem"))
        dado_extra = meta.get("dano_magia") or ""

        if acao.get("alvos") == "todos":
            mirados = list(estado.inimigos_vivos)
        else:
            quantos = 1 + meta.get("alvos_extra", 0)
            escolhidos = [
                i for i in estado.inimigos_vivos if i.indice in set(alvos or ())
            ]
            # Twinned Spell: a magia de um alvo pega o seguinte tambem. Sem
            # escolha explicita, pega o mais ferido, que e onde o dano fecha.
            if len(escolhidos) < quantos:
                sobram = sorted(
                    (i for i in estado.inimigos_vivos if i not in escolhidos),
                    key=lambda i: i.hp_atual,
                )
                escolhidos += sobram[: quantos - len(escolhidos)]
            mirados = escolhidos[:quantos]
        if not mirados:
            return "Nao ha inimigo de pe para a habilidade."

        # UM dado para a sala inteira, quando a magia e uma AREA. A bola de
        # fogo cai uma vez: o que muda de criatura para criatura e quem
        # resistiu, nao quanto fogo veio. Rolando por alvo, a mesma magia dava
        # um numero para cada goblin, e quanto mais goblins houvesse maior a
        # chance de ALGUM levar perto do maximo — a magia ficava mais forte so
        # por haver mais gente embaixo dela.
        #
        # O alvo extra do feiticeiro e outra coisa: ali uma magia de alvo unico
        # pega um segundo alvo, e cada um leva um lancamento SEU, com dado
        # proprio, como o multiataque da criatura.
        dado_da_area: int | None = None
        if acao.get("alvos") == "todos" and acao.get("dano"):
            dado_da_area = motor.rolar_dano(acao["dano"])
            if dado_extra:
                dado_da_area += motor.rolar_dano(dado_extra)

        linhas: list[str] = []
        caidos: list[str] = []
        for inimigo in mirados:
            # Guiding Bolt nao e resistivel: o dano entra, o save nao e rolado.
            if acao.get("sem_save"):
                passou, rolagem = False, ""
            else:
                save = motor.salvar_inimigo(
                    inimigo, acao["save"], cd, desvantagem=desvantagem
                )
                passou = save.passou
                marca = " (desvantagem)" if desvantagem else ""
                rolagem = (
                    f"🎲 {save.d20} {fmt(save.modificador)} = "
                    f"**{save.total}**{marca}"
                )

            sofridos: list[str] = []
            if acao.get("dano"):
                cheio = dado_da_area
                if cheio is None:
                    cheio = motor.rolar_dano(acao["dano"])
                    # Empowered Spell: um dado a mais em toda magia dele.
                    if dado_extra:
                        cheio += motor.rolar_dano(dado_extra)
                levou = cheio if not passou else (cheio // 2 if acao.get("metade") else 0)
                if levou:
                    inimigo.hp_atual = max(0, inimigo.hp_atual - levou)
                    sofridos.append(f"**{levou}** de dano")
            if not passou and acao.get("atordoa") and not inimigo.caido:
                inimigo.atordoado = True
                await db.aplicar_efeito(
                    self.bot.db, run["id"], passo, "inimigo", inimigo.indice,
                    "atordoado", {"por": habilidade.nome},
                    estado.rodada + acao["atordoa"], dono=user_id,
                )
                sofridos.append("**perde a vez**")
            if not passou and acao.get("vira_contra") and not inimigo.caido:
                sofridos.append(
                    await self._virar_contra_os_seus(run, estado, inimigo, habilidade)
                )
            if not passou and acao.get("dano_por_rodada") and not inimigo.caido:
                await db.aplicar_efeito(
                    self.bot.db, run["id"], passo, "inimigo", inimigo.indice,
                    f"{habilidade.id}:corrente",
                    {"dano_por_rodada": acao["dano_por_rodada"],
                     "save": acao["save"], "cd": cd},
                    estado.rodada + acao.get("turnos", 3), dono=user_id,
                )
                sofridos.append(f"**acorrentado** ({acao['dano_por_rodada']}/rodada)")
            if not passou and acao.get("penalidade_ataque") and not inimigo.caido:
                inimigo.penalidade_ataque = max(
                    inimigo.penalidade_ataque, acao["penalidade_ataque"]
                )
                await db.aplicar_efeito(
                    self.bot.db, run["id"], passo, "inimigo", inimigo.indice,
                    f"{habilidade.id}:atrapalhado",
                    {"penalidade_ataque": acao["penalidade_ataque"]},
                    estado.rodada + acao.get("turnos", 1), dono=user_id,
                )
                sofridos.append(f"**-{acao['penalidade_ataque']} de ataque**")
            if not passou and acao.get("vantagem_do_grupo"):
                await self._vantagem_do_grupo(
                    run, estado, inimigo, habilidade, acao.get("turnos", 1)
                )
                sofridos.append("**o grupo ataca ele com vantagem**")

            if inimigo.caido:
                caidos.append(inimigo.nome)
            resultado = ", ".join(p for p in sofridos if p) or "resistiu"
            meio = f" · {rolagem} vs CD {cd}" if rolagem else ""
            linhas.append(f"{inimigo.nome}{meio} → {resultado}")

        await db.definir_hp_inimigos(
            self.bot.db, run["id"], passo,
            {i.indice: i.hp_atual for i in estado.inimigos},
        )
        cabeca = f"✨ **{habilidade.nome}** (CD {cd})"
        texto = cabeca + "\n" + "\n".join(f"· {l}" for l in linhas)
        if caidos:
            texto += f"\n💀 caem: {', '.join(caidos)}"
        await self._anunciar_habilidade(run, texto)
        return texto

    async def _virar_contra_os_seus(
        self, run: dict[str, Any], estado, dominado, habilidade
    ) -> str:
        """Dominate Person: a criatura ataca outra criatura dela."""
        outros = [i for i in estado.inimigos_vivos if i is not dominado]
        if not outros:
            return "**mas nao tem em quem bater**"
        vitima = motor.sortear_um(outros)
        golpe = motor.atacar(
            dominado.nome, dominado.ataque, dominado.dano, vitima.nome, vitima.ca
        )
        if not golpe.acertou:
            return f"**vira contra {vitima.nome}** e erra"
        vitima.hp_atual = max(0, vitima.hp_atual - golpe.dano)
        await db.definir_hp_inimigos(
            self.bot.db, run["id"], self._passo(run),
            {i.indice: i.hp_atual for i in estado.inimigos},
        )
        return f"**acerta {vitima.nome}** com **{golpe.dano}** de dano"

    async def _vantagem_do_grupo(
        self, run: dict[str, Any], estado, inimigo, habilidade, turnos: int
    ) -> None:
        """Guiding Bolt: todo mundo do grupo ataca aquele inimigo com vantagem.

        A Marca do Caçador só beneficia o dono; esta é do grupo, então entra
        um efeito por pessoa, cada um dono do seu.
        """
        passo = self._passo(run)
        expira = estado.rodada + max(1, turnos)
        for c in estado.vivos:
            await db.aplicar_efeito(
                self.bot.db, run["id"], passo, "inimigo", inimigo.indice,
                f"{habilidade.id}:{c.user_id}", {"vantagem": True}, expira,
                dono=c.user_id,
            )

    async def _alvos_possiveis(self, run, habilidade, estado):
        """As opções de alvo de uma habilidade: `[(valor, nome, detalhe)]`.

        **`None` quer dizer que ela não escolhe alvo**: o buff de grupo, o que
        vale só em quem usa, a invocação, e a que pega todos. Lista vazia quer
        dizer que escolhe e não há ninguém — que é outra coisa.

        Vive separada do menu porque DUAS coisas precisam desta lista: o menu
        de quem clicou, e o autocomplete de `/incursao substituir`. Elas têm de
        ser a mesma lista, senão o grupo poderia propor para o ausente um alvo
        que ele mesmo não poderia escolher.
        """
        acao = habilidade.acao or {}
        # Quem so mexe em si mesmo (Rage, Reckless Attack, Avatar da Luz) ou no
        # grupo inteiro nao tem alvo a escolher — perguntar num combate de
        # quatro criaturas so atrapalha.
        # Quem nao mira ninguem: o buff de grupo, o que vale so em si, e a
        # invocacao, que traz o aliado e nao escolhe inimigo.
        if (
            acao.get("tipo") in ("grupo", "invocar")
            or (acao.get("tipo") == "forma" and acao.get("alvo") != "aliado")
            or acao.get("alvo") == "proprio"
        ):
            return None
        if acao.get("alvo") in ("aliado", "aliados") or acao.get("tipo") == "cura":
            if acao.get("tipo") == "cura" and acao.get("alvo") != "aliado":
                return None
            return [
                (str(p["user_id"]), p["nome"], f"{p['hp_atual']}/{p['hp_max']} HP")
                for p in await db.personagens_da_run(self.bot.db, run["id"])
            ]
        # Habilidade que pega todos nao tem alvo a escolher (Flame Strike,
        # Hypnotic Pattern): `alvos` vem como "todos", nao como numero.
        quantos = acao.get("alvos", 1)
        if quantos == "todos":
            return None
        vivos = estado.inimigos_vivos if estado else []
        if len(vivos) <= 1 and quantos <= 1:
            return None
        return [
            (str(i.indice), i.nome, f"{motor.barra(i.hp_atual, i.hp_max, 8)} · CA {i.ca}")
            for i in vivos
        ]

    async def _pedir_alvo(
        self, interaction: discord.Interaction, run, sala_id, habilidade, estado
    ):
        """Abre o menu de alvo se a habilidade precisa de um. False = nao precisa."""
        acao = habilidade.acao or {}
        opcoes = await self._alvos_possiveis(run, habilidade, estado)
        if opcoes is None:
            return False
        if not opcoes:
            await self._dizer(interaction, "Nao ha alvo possivel agora.")
            return True
        await self._dizer(
            interaction,
            f"**{habilidade.nome}** — escolha o alvo:",
            view=SeletorAlvoHabilidade(
                self, run["id"], sala_id, habilidade.id, opcoes,
                acao.get("alvos", 1)
            ),
        )
        return True

    @staticmethod
    def _quanto_cura(alvo, acao: dict, bonus_pct: float = 0.0) -> int:
        """Cura o alvo e devolve quanto entrou de HP.

        Toda cura do jogo é fração do HP máximo — não há mais caminho por
        dado. O bônus de quem cura (o Curandeiro, o anel do santuário) é
        fração também, e soma ANTES de curar, numa conta só: em duas etapas o
        teto do HP engoliria a segunda quando a primeira já tivesse enchido a
        barra, e o bônus simplesmente desapareceria.
        """
        return motor.curar(alvo, acao["fracao"] + max(0.0, bonus_pct or 0.0))

    async def _cobrar_o_retorno(self, run: dict[str, Any], quem) -> str:
        """Voltar do chão custa 1 ponto de Exaustão. Devolve a linha do aviso.

        O preço é de SAIR DO ZERO, e não da cura: cobra igual venha de uma
        magia apontada em alguém, da cura que cai no grupo ou da regeneração
        por turno. Quem decide levantar paga, e quem é levantado sem ninguém
        decidir paga também — o corpo não sabe a diferença.

        A Exaustão **não decai com o combate**: só o descanso tira, um ponto
        por descanso. Cinco quedas numa incursão tiram o personagem dela, e
        é de propósito que o custo seja alto.

        O combatente em memória não é recalculado: a penalidade entra no
        saldo na próxima vez que o estado for montado, como acontece com
        toda condição aplicada no meio do combate.
        """
        stacks = await db.aplicar_condicao(
            self.bot.db, run["id"], quem.user_id, condicoes.EXAUSTAO
        )
        return (
            f"**{quem.nome}** volta do chão e fica com "
            f"{condicoes.rotulo(condicoes.EXAUSTAO, stacks)}"
        )

    async def _limpar_atordoamento(self, run: dict[str, Any], alvo) -> None:
        """Tira o atordoamento de quem recebeu cura (Restauração, do clérigo)."""
        if not getattr(alvo, "atordoado", False):
            return
        alvo.atordoado = False
        await db.remover_efeito(
            self.bot.db, run["id"], self._passo(run), "personagem",
            alvo.user_id, "atordoado",
        )

    async def _resolver_condicao(
        self, run: dict[str, Any], user_id: int, habilidade, acao
    ) -> str:
        """A Poção de buff: stacks de uma condição da tabela, em quem bebeu.

        Entra pelo MESMO caminho que o prêmio de um Evento vencido, então o
        prazo dela é o da tabela de condições — decai 1 por combate — e não os
        3 turnos das outras poções. A Poção da Benção 3 é "+3 agora, +2 no
        combate seguinte, +1 no outro": vale menos por rodada e muito mais por
        incursão, o que é a troca que a tabela de buffs já faz.

        O número só chega ao combatente quando o estado é remontado, como toda
        condição aplicada no meio do combate (ver `_cobrar_o_retorno`).
        """
        cid = acao["condicao"]
        stacks = await db.aplicar_condicao(
            self.bot.db, run["id"], user_id, cid, acao.get("stacks", 1)
        )
        # Anuncia e devolve A MESMA frase, que é a convenção dos outros
        # resolvedores: é a igualdade exata que faz `_avancar` apagar o eco
        # privado em vez de mostrar a mesma coisa duas vezes para quem bebeu.
        quem = await self._personagem_na_run(run, user_id)
        texto = (
            f"{consumiveis.ICONE} **{(quem or {}).get('nome', 'Alguém')}** bebe "
            f"**{habilidade.nome}** e fica com {condicoes.rotulo(cid, stacks)}."
        )
        await self._anunciar_habilidade(run, texto)
        return texto

    async def _resolver_recarga(
        self, run: dict[str, Any], user_id: int, habilidade, acao, escolhida: str
    ) -> str:
        """A Poção de Mana: devolve um uso gasto de uma habilidade do tier.

        Devolve um uso em vez de dar "mais um uso" porque o contador é de
        gastos (`run_usos`), e o teto dele é a tabela da classe. Então a poção
        desfaz um gasto — e não pode desfazer o que não aconteceu, por isso
        quem bebe escolhe entre as que ele JÁ gastou.
        """
        personagem = await self._personagem_na_run(run, user_id)
        passo = self._passo(run)
        escolha = next(
            (
                h for _t, h in (personagem or {}).get("habilidades") or []
                if h.id == escolhida
            ),
            None,
        )
        if escolha is None:
            return "Essa habilidade não é sua."
        await db.devolver_uso(
            self.bot.db, run["id"], user_id, escolha.chave_de_uso,
            self._chave_de_recarga(escolha, run, passo),
        )
        texto = (
            f"{consumiveis.ICONE} **{(personagem or {}).get('nome', 'Alguém')}** "
            f"bebe **{habilidade.nome}**: **{escolha.nome}** volta a ter um uso."
        )
        await self._anunciar_habilidade(run, texto)
        return texto

    async def _recarregaveis(
        self, run: dict[str, Any], personagem: dict[str, Any], tier: int
    ) -> list[tuple]:
        """As habilidades daquele tier que este personagem já gastou.

        São as candidatas da Poção de Mana. Fora a lista, a poção não tem o
        que fazer — e aí ela não é bebida, para não queimar o item à toa.
        """
        gastos = await db.usos_da_run(self.bot.db, run["id"], personagem["user_id"])
        passo = self._passo(run)
        saida = []
        for tier_dela, habilidade in personagem.get("habilidades") or []:
            if tier_dela != tier or not habilidade.acionavel:
                continue
            chave = self._chave_de_recarga(habilidade, run, passo)
            usados = gastos.get((habilidade.chave_de_uso, chave), 0)
            if usados > 0:
                saida.append((habilidade, usados))
        return saida

    async def _resolver_cura(
        self, run: dict[str, Any], user_id: int, habilidade, acao, alvos, estado
    ) -> str:
        """Cura a si mesmo ou a um aliado, dentro ou fora do combate."""
        combatentes = estado.combatentes if estado else await self._combatentes(run)
        alvo_id = alvos[0] if alvos else user_id
        alvo = next((c for c in combatentes if c.user_id == alvo_id), None)
        if alvo is None:
            return "Alvo invalido."

        quem_curou = await self._personagem_na_run(run, user_id)
        dele = ((quem_curou or {}).get("efeitos") or {})
        estava_caido = alvo.caido
        curado = self._quanto_cura(alvo, acao, dele.get("bonus_cura_pct"))
        await db.definir_hp(self.bot.db, run["id"], alvo.user_id, alvo.hp_atual)
        retorno = (
            await self._cobrar_o_retorno(run, alvo)
            if estava_caido and not alvo.caido
            else ""
        )
        # Restauracao, do clerigo: a cura tira o atordoamento de quem recebe.
        if curado and dele.get("cura_limpa_controle"):
            await self._limpar_atordoamento(run, alvo)
        temporario = 0
        quanto_thp = motor.rolar_dano(acao["thp_alvo"]) if acao.get("thp_alvo") else 0
        # O xama ganha THP ao usar o caminho espiritual, mesmo curando outro.
        if acao.get("thp_proprio"):
            proprio = next((c for c in combatentes if c.user_id == user_id), None)
            if proprio is not None:
                motor.ganhar_thp(proprio, motor.rolar_dano(acao["thp_proprio"]))
                await db.definir_thp(
                    self.bot.db, run["id"], proprio.user_id, proprio.thp
                )
        # Cantico Benevolente: a escolha do Xama soma THP em cima da cura.
        # Sai de QUEM CURA, e so quando cura OUTRO: e o que o texto promete.
        extra_cantico = dele.get("thp_na_cura", 0)
        if extra_cantico and alvo.user_id != user_id:
            quanto_thp += extra_cantico
        # A armadura: "+N de vida temporaria AO SER CURADO". Sai de quem
        # RECEBE, e e o oposto do de cima. As duas coisas dividiam a chave
        # `thp_na_cura`, lida so do lado de quem cura — entao a Tunica
        # Acolchoada nao fazia nada em quem a vestia, e dava o THP ao aliado
        # de quem estivesse com ela. Cinco armaduras tinham a linha de stat
        # inteira sem efeito.
        #
        # Duas diferencas em relacao ao Cantico, e as duas vem do texto:
        #   sem o `!= user_id`, porque ser curado e ser curado — curar a si
        #     mesmo tambem conta;
        #   dentro do `if curado`, porque "ao ser curado" exige ter sido
        #     curado. Sem isso, curar um aliado de HP cheio renderia THP de
        #     graca. O Cantico fica fora deste `if` como sempre esteve: o
        #     texto dele cobra CURAR, e nao curar alguma coisa.
        if curado:
            quem_recebeu = await self._personagem_na_run(run, alvo.user_id)
            quanto_thp += ((quem_recebeu or {}).get("efeitos") or {}).get(
                "thp_ao_ser_curado", 0
            )
        if quanto_thp:
            temporario = motor.ganhar_thp(alvo, quanto_thp)
            await db.definir_thp(self.bot.db, run["id"], alvo.user_id, alvo.thp)
        if curado:
            extra = f" e fica com **{temporario}** de THP" if temporario else ""
            cobranca = f"\n\u00b7 {retorno}." if retorno else ""
            texto = (
                f"\u2728 **{habilidade.nome}**: {alvo.nome} recupera **{curado}** de HP "
                f"({alvo.hp_atual}/{alvo.hp_max}){extra}.{cobranca}"
            )
        else:
            texto = (
                f"\u2728 **{habilidade.nome}**: {alvo.nome} nao recupera nada "
                "(ja esta cheio, ou caido)."
            )
        await self._anunciar_habilidade(run, texto)
        return texto

    async def _resolver_grupo(self, run, estado, habilidade, acao, user_id: int) -> str:
        """Habilidade que cai no grupo inteiro: THP, cura e um buff curto.

        `melhoria` \u00e9 a vers\u00e3o car\u00edssima dos Guerreiros Anci\u00f5es: quem usa paga
        THP e, por esse pre\u00e7o, o grupo leva a forma melhor e os inimigos levam
        dano. Sem THP suficiente, sai a vers\u00e3o normal.
        """
        passo = self._passo(run)
        acao, pago = self._versao_da_habilidade(acao, estado, user_id)
        linhas: list[str] = []

        # A CURA primeiro, e o THP depois. Duas razoes: ela alcanca quem esta
        # caido (e `estado.vivos` nao), e quem ela levanta entra no THP junto
        # com o resto — a habilidade cai no grupo, e depois de cair o grupo
        # ja inclui quem voltou.
        texto_da_cura = None
        # Fora do `if` para o THP da armadura poder consultar quem foi curado
        # sem depender de a habilidade ter cura.
        curados: dict[int, int] = {}
        if acao.get("cura_fracao"):
            # O bonus de quem cura (Curandeiro, Especialista em cura, o anel
            # do santuario) vale aqui como na cura de um so.
            quem_curou = await self._personagem_na_run(run, user_id)
            bonus = ((quem_curou or {}).get("efeitos") or {}).get("bonus_cura_pct")
            como = {"fracao": acao["cura_fracao"]}
            levantados = []
            # `combatentes` e nao `vivos`: a cura em grupo levanta os caidos,
            # como a cura de alvo escolhido.
            for c in estado.combatentes:
                estava_caido = c.caido
                if self._quanto_cura(c, como, bonus):
                    curados[c.user_id] = c.hp_atual
                if estava_caido and not c.caido:
                    levantados.append(c)
            if curados:
                await db.definir_hp_varios(self.bot.db, run["id"], curados)
            for c in levantados:
                linhas.append(await self._cobrar_o_retorno(run, c))
            total = acao["cura_fracao"] + max(0.0, bonus or 0.0)
            # `round`, e nao `int`: 0.35 + 0.10 da 0.44999999999999996 em
            # float, e truncar mostraria "44%" numa cura de 45%.
            texto_da_cura = f"**{round(total * 100)}%** do HP maximo de volta"

        quanto = motor.rolar_dano(acao["thp"]) if acao.get("thp") else 0
        # A armadura de quem FOI curado ("+N de vida temporaria ao ser
        # curado") vale aqui como na cura de um alvo so: a cura em grupo e
        # cura. Uma leitura so para todos, em vez de uma por cabeca.
        da_armadura: dict[int, int] = {}
        if curados:
            for p in await db.personagens_da_run(self.bot.db, run["id"]):
                extra = (p.get("efeitos") or {}).get("thp_ao_ser_curado", 0)
                if extra and p["user_id"] in curados:
                    da_armadura[p["user_id"]] = extra
        novos: dict[int, int] = {}
        for c in estado.vivos:
            ganho = quanto + da_armadura.get(c.user_id, 0)
            if ganho:
                motor.ganhar_thp(c, ganho)
            novos[c.user_id] = c.thp
        if quanto:
            linhas.append(f"**{quanto}** de vida temporaria para o grupo")
        if da_armadura:
            linhas.append(
                "e a armadura de "
                + ", ".join(
                    f"**{c.nome}**"
                    for c in estado.vivos
                    if c.user_id in da_armadura
                )
                + " rende THP em cima da cura"
            )
        if texto_da_cura:
            linhas.append(texto_da_cura)

        if pago:
            novos[pago[0]] = pago[1]
        if novos:
            await db.definir_thp_varios(self.bot.db, run["id"], novos)

        if acao.get("dano_em_todos"):
            caiu = []
            # Uma rolagem para a sala, pelo mesmo motivo de _resolver_save: o
            # estouro e um, e cobrar um dado por cabeca faria dele uma coisa
            # mais forte em sala cheia.
            levou = motor.rolar_dano(acao["dano_em_todos"])
            for inimigo in list(estado.inimigos_vivos):
                inimigo.hp_atual = max(0, inimigo.hp_atual - levou)
                if inimigo.caido:
                    caiu.append(inimigo.nome)
            await db.definir_hp_inimigos(
                self.bot.db, run["id"], passo,
                {i.indice: i.hp_atual for i in estado.inimigos},
            )
            linhas.append(f"**{levou}** em todos os inimigos")
            if caiu:
                linhas.append(f"caem: {', '.join(caiu)}")

        if acao.get("efeitos"):
            expira = estado.rodada + acao.get("turnos", 1)
            for c in estado.vivos:
                await db.aplicar_efeito(
                    self.bot.db, run["id"], passo, "personagem", c.user_id,
                    habilidade.id, acao["efeitos"], expira,
                )
            linhas.append("e um bonus nos proximos ataques")

        corpo = "; ".join(linhas) or "o grupo inteiro leva o bonus"
        marca = " \u2b50" if pago else ""
        texto = f"\u2728 **{habilidade.nome}**{marca}: {corpo}."
        await self._anunciar_habilidade(run, texto)
        return texto

    @staticmethod
    def _versao_da_habilidade(
        acao: dict, estado, user_id: int
    ) -> tuple[dict, Optional[tuple[int, int]]]:
        """Escolhe entre a a\u00e7\u00e3o normal e a `melhoria` que custa THP.

        Devolve (a\u00e7\u00e3o a usar, (user_id, THP que sobrou) se pagou). Quem paga \u00e9
        quem usou, e s\u00f3 se tiver o THP inteiro \u2014 a melhoria n\u00e3o sai pela
        metade. \u00c9 o que deixa o xam\u00e3 trocar 20 de vida tempor\u00e1ria pela forma
        grande dos Guerreiros Anci\u00f5es.
        """
        melhoria = acao.get("melhoria") or {}
        custo = melhoria.get("custo_thp", 0)
        dono = next((c for c in estado.vivos if c.user_id == user_id), None)
        if not custo or dono is None or dono.thp < custo:
            return {k: v for k, v in acao.items() if k != "melhoria"}, None
        dono.thp -= custo
        juntas = {k: v for k, v in acao.items() if k != "melhoria"}
        juntas.update(melhoria)
        juntas.pop("custo_thp", None)
        return juntas, (dono.user_id, dono.thp)

    async def _resolver_duracao(
        self, run, user_id: int, estado, habilidade, acao, alvos
    ) -> str:
        """Liga um efeito com prazo em quem usou, ou no inimigo escolhido.

        Com `acoes` ou `quantidade` na ação, ela **também ataca**, na mesma
        rodada e já com o efeito valendo: era um turno inteiro parado para
        ligar um buff de 3 turnos, e na prática o buff rendia dois.
        """
        passo = self._passo(run)
        expira = estado.rodada + acao.get("turnos", 1)
        # Os alvos dos golpes, quando a ação carrega golpes. Vazio = quem o
        # motor escolher (o primeiro inimigo de pé), que é o certo para um
        # buff no próprio: a fúria não aponta ninguém.
        alvos_do_golpe: list[int] = []
        if acao.get("alvo") == "inimigo":
            # O escolhido pode ter caido enquanto a acao esperava a vez.
            alvo = (estado.alvo_preferido(alvos[0]) if alvos else None) or estado.alvo_preferido()
            if alvo is None:
                return "Nao ha inimigo de pe para a habilidade."
            await db.aplicar_efeito(
                self.bot.db, run["id"], passo, "inimigo", alvo.indice,
                habilidade.id, acao["efeitos"], expira, dono=user_id,
            )
            # A marca vale JA no golpe desta rodada. O que o banco guarda só
            # chega ao combatente quando o estado é remontado, e remontar
            # aqui custaria caro — então a marca é espelhada na memória, do
            # mesmo jeito que `_aplicar_ligado` faria.
            quem_marca = estado.combatente(user_id)
            if quem_marca is not None:
                if acao["efeitos"].get("dano_bonus"):
                    quem_marca.dano_por_alvo[alvo.indice] = (
                        habilidade.nome, acao["efeitos"]["dano_bonus"]
                    )
                if acao["efeitos"].get("vantagem"):
                    quem_marca.vantagem_contra.add(alvo.indice)
            alvo_nome = alvo.nome
            alvos_do_golpe = [alvo.indice]
        elif acao.get("alvo") == "aliados":
            # Fly: pega varios do grupo, nao so quem lancou. Sem escolha vale
            # quem esta de pe, do mais exposto para o menos — o que o mago
            # faria: tirar de alcance quem esta levando pancada.
            quantos = acao.get("alvos", 1)
            escolhidos = [c for c in estado.vivos if c.user_id in set(alvos or ())]
            # Dimension Door leva quem lancou junto, sempre em primeiro — e
            # antes de completar, para nao gastar vaga com outro no lugar dele.
            if acao.get("inclui_quem_usou"):
                proprio = estado.combatente(user_id)
                if proprio is not None and proprio not in escolhidos:
                    escolhidos = [proprio] + escolhidos
            # Escolha parcial COMPLETA, nao trunca: o menu aceita submeter um
            # alvo so, e quem pede dois nao pode entregar um em silencio. Sem
            # escolha nenhuma vale do mais exposto para o menos — o que o mago
            # faria: tirar de alcance quem esta levando pancada.
            if len(escolhidos) < quantos:
                sobram = sorted(
                    (c for c in estado.vivos if c not in escolhidos),
                    key=lambda c: -c.ameaca_total,
                )
                escolhidos += sobram[: quantos - len(escolhidos)]
            if not escolhidos:
                return "Nao ha ninguem de pe para a habilidade."
            for quem_recebe in escolhidos[:quantos]:
                await db.aplicar_efeito(
                    self.bot.db, run["id"], passo, "personagem",
                    quem_recebe.user_id, habilidade.id, acao["efeitos"], expira,
                )
            alvo_nome = ", ".join(c.nome for c in escolhidos[:quantos])
        else:
            await db.aplicar_efeito(
                self.bot.db, run["id"], passo, "personagem", user_id,
                habilidade.id, acao["efeitos"], expira,
            )
            alvo_nome = None

        quem = estado.combatente(user_id)
        turnos = acao.get("turnos", 1)
        alvo_texto = f" em **{alvo_nome}**" if alvo_nome else ""
        cabeca = (
            f"✨ **{habilidade.nome}**{alvo_texto} — vale por "
            f"{turnos} turno(s), ate a rodada {expira - 1}."
        )

        # Ligar e bater na MESMA rodada. Duas coisas têm de acontecer antes
        # dos golpes:
        #
        # 1. o efeito precisa estar valendo NA MEMÓRIA. O que vai ao banco só
        #    chega ao combatente quando o estado é remontado, e remontar aqui
        #    custaria caro — então `_aplicar_ligado` recebe uma linha montada
        #    à mão, e é ela que põe o +2 da fúria no golpe desta rodada;
        # 2. o anúncio separado NÃO sai. O texto devolvido daqui já vai ao
        #    canal inteiro, e `_anunciar_habilidade` diria a mesma coisa duas
        #    vezes — é a mesma razão pela qual as duas marcas do patrulheiro
        #    nunca passaram por ele.
        if acao.get("acoes") or acao.get("quantidade"):
            if acao.get("alvo") not in ("inimigo", "aliados"):
                self._aplicar_ligado(
                    estado.combatentes,
                    {
                        "alvo_tipo": "personagem",
                        "alvo_id": user_id,
                        "efeito": habilidade.id,
                        "valor": acao["efeitos"],
                    },
                )
            golpes = await self._resolver_golpes(
                run, user_id, estado, habilidade, acao, alvos_do_golpe,
                cabeca=False,
            )
            return f"{cabeca}\n{golpes}"

        await self._anunciar_habilidade(
            run, f"✨ {quem.nome if quem else 'Alguem'} usa **{habilidade.nome}**{alvo_texto}."
        )
        return cabeca

    async def _pilha_de_sequencia(
        self, run: dict[str, Any], user_id: int, passo: int
    ) -> int:
        """Martial Arts: quantos acertos seguidos o personagem ja emendou."""
        for ligado in await db.efeitos_ativos(self.bot.db, run["id"], passo, 0):
            if (
                ligado["alvo_tipo"] == "personagem"
                and ligado["alvo_id"] == user_id
                and ligado["efeito"] == "martial_arts"
            ):
                return ligado["valor"].get("pilha", 0)
        return 0

    async def _guardar_sequencia(
        self, run: dict[str, Any], user_id: int, passo: int, pilha: int
    ) -> None:
        # Prazo alto de proposito: a sequencia so morre junto com o combate.
        await db.aplicar_efeito(
            self.bot.db, run["id"], passo, "personagem", user_id,
            "martial_arts", {"pilha": pilha}, 9999,
        )

    async def _totem_do_golpe(
        self, run: dict[str, Any], personagem: dict[str, Any], combatente, golpes
    ) -> None:
        """Convocacao totemica: 18+ no d20 rende THP a quem tem a passiva."""
        totem = ((personagem.get("efeitos") or {}).get("totem")) or {}
        if not totem.get("thp"):
            return
        if not any(g.d20 >= totem.get("gatilho", 18) for g, _alvo in golpes):
            return
        motor.ganhar_thp(combatente, totem["thp"])
        await db.definir_thp(self.bot.db, run["id"], combatente.user_id, combatente.thp)

    async def _resolver_golpes(
        self, run, user_id: int, estado, habilidade, acao, alvos,
        cabeca: bool = True,
    ) -> str:
        """Os golpes de uma ativa, no lugar do ataque do turno."""
        passo = self._passo(run)
        atacante = estado.combatente(user_id)
        escolhidos = [i for i in (estado.inimigo(v) for v in alvos) if i and not i.caido]
        if not escolhidos:
            vivo = estado.alvo_preferido()
            escolhidos = [vivo] if vivo else []
        if not escolhidos or atacante is None:
            return "Nao ha inimigo de pe para atacar."

        golpes = []
        indice = await db.proximo_indice_de_ataque(
            self.bot.db, run["id"], passo, estado.rodada, user_id
        )
        # `quantidade` conta GOLPES e `acoes` conta ACOES. A diferenca importa
        # para quem tem Multiattack: uma acao dele sao dois golpes, entao o
        # Action Surge com "quantidade: 1" trocava os dois golpes do turno por
        # um — usar era pior que nao usar. Com `acoes` a conta sai certa
        # sozinha, e continua certa quando o Multiattack mudar.
        # `golpes_extras` sao golpes POR CIMA da acao, e nao no lugar dela: e
        # o Flurry of Blows, que no livro sao dois desarmados de bonus somados
        # a acao de ataque. Sem isso ele so sabia dizer "duas acoes EM VEZ do
        # turno", que para quem tem Multiattack chegava a ser menos golpes.
        por_alvo = acao.get("quantidade")
        if por_alvo is None:
            por_alvo = (
                max(1, acao.get("acoes", 1)) * max(1, atacante.ataques)
                + max(0, acao.get("golpes_extras", 0))
            )
        # Alvo unico: se ele cair no meio, os golpes que faltam vao para o
        # proximo de pe, como o ataque comum do turno ja faz. Com varios alvos
        # escolhidos (a Rajada do Cacador) cada um leva o seu, e trocar seria
        # bater duas vezes no mesmo.
        reapontar = len(escolhidos) == 1
        for alvo in escolhidos:
            for _ in range(por_alvo):
                if alvo.caido and reapontar:
                    proximo = estado.alvo_preferido()
                    if proximo is None:
                        break
                    alvo = proximo
                if alvo.caido:
                    break
                golpe = motor.atacar_inimigo(
                    atacante,
                    alvo,
                    None,
                    dano_bonus=acao.get("dano_bonus"),
                    rotulo_bonus=habilidade.nome,
                    garantido=acao.get("garantido", False),
                    critico_forcado=acao.get("critico", False),
                )
                golpes.append((golpe, alvo))
                await db.registrar_ataque(
                    self.bot.db, run["id"], passo, estado.rodada, user_id,
                    golpe.d20, golpe.bonus, golpe.ca_alvo, golpe.dano, alvo.indice,
                    indice, "habilidade",
                )
                indice += 1

        # Bonus de uma vez so (o Brutal Strike): entra no primeiro golpe que
        # acerta, e nao em cada um. `dano_bonus` e por golpe e dobraria num
        # turno de dois ataques; este e o d10 que a habilidade promete, um.
        extra = 0
        if acao.get("bonus_uma_vez"):
            for golpe, inimigo in golpes:
                if not golpe.acertou:
                    continue
                extra = motor.rolar_dano(acao["bonus_uma_vez"])
                golpe.dano += extra
                inimigo.hp_atual = max(0, inimigo.hp_atual - extra)
                break

        marcas = await self._marcar_fatal(run, estado, atacante, user_id, golpes)
        await db.definir_hp_inimigos(
            self.bot.db, run["id"], passo,
            {inimigo.indice: inimigo.hp_atual for _g, inimigo in golpes},
        )
        # Furtividade: o ataque acima contou ameaca normalmente, e o Stealth
        # comeca na rodada SEGUINTE — `desde`. A ficha diz "realiza um ataque
        # e depois entra em Stealth", e sem isso o proprio golpe que liga a
        # habilidade sairia de graca.
        if acao.get("furtividade"):
            turnos = int(acao["furtividade"])
            await db.aplicar_efeito(
                self.bot.db, run["id"], passo, "personagem", user_id,
                self.EFEITO_DA_FURTIVIDADE, {"desde": estado.rodada + 1},
                estado.rodada + 1 + turnos, dono=user_id,
            )
        ganho = 0
        if acao.get("thp_proprio"):
            ganho = motor.ganhar_thp(atacante, motor.rolar_dano(acao["thp_proprio"]))
        if acao.get("thp_igual_ao_bonus") and extra:
            # Brutal Strike: a vida temporaria e EXATAMENTE o d10 que saiu no
            # golpe, e nao uma fracao do dano total — "o mesmo em THP".
            ganho = motor.ganhar_thp(atacante, extra)
        if ganho:
            await db.definir_thp(self.bot.db, run["id"], atacante.user_id, atacante.thp)
        personagem = await self._personagem_na_run(run, user_id)
        if personagem:
            await self._totem_do_golpe(run, personagem, atacante, golpes)

        if acao.get("atordoa"):
            certeiro = next(((g, i) for g, i in golpes if g.acertou), None)
            if certeiro:
                # Quem ja agiu nesta rodada perde a vez da proxima; quem ainda
                # vai agir, a desta.
                ordem = await db.iniciativa(self.bot.db, run["id"], passo)
                vez = (await db.estado_combate(self.bot.db, run["id"], passo))["vez"]
                ja_agiu = any(
                    a["tipo"] == motor.INIMIGO and a["alvo_id"] == certeiro[1].indice
                    for a in ordem[:vez]
                )
                await db.aplicar_efeito(
                    self.bot.db, run["id"], passo, "inimigo", certeiro[1].indice,
                    "atordoado", {},
                    estado.rodada + acao["atordoa"] + (1 if ja_agiu else 0),
                )
                await self._anunciar_habilidade(
                    run,
                    f"\u2728 **{habilidade.nome}**: {certeiro[1].nome} fica "
                    "atordoado e perde a proxima vez.",
                )
            else:
                # So gasta o recurso quando acerta.
                await db.devolver_uso(
                    self.bot.db, run["id"], user_id,
                    habilidade.chave_de_uso,
                    self._chave_de_recarga(habilidade, run, passo),
                )

        self._registrar(run, estado.rodada, [E.linha_golpe(g) for g, _i in golpes])
        resumo = E.resumo_do_golpe([(g, i.nome) for g, i in golpes])
        if ganho:
            resumo += f"\nVida temporaria: **{atacante.thp}**."
        await self._anunciar_habilidade(
            run, f"\u2728 {atacante.nome} usa **{habilidade.nome}**."
        )
        # Sem cabe\u00e7a quando quem chamou j\u00e1 escreveu a dele: a marca do
        # Patrulheiro anuncia o alvo e o prazo, e repetir o nome logo embaixo
        # n\u00e3o acrescenta nada.
        if not cabeca:
            return resumo
        return f"\u2728 **{habilidade.nome}**\n{resumo}"

    async def _bencao_do_patrono(
        self, run: dict[str, Any], personagem: dict[str, Any], combatente, golpes
    ) -> None:
        """Dark One's Blessing: derrubar um inimigo rende vida temporária.

        O gatilho é a queda, não o acerto — por isso roda depois de o dano já
        ter entrado no HP, olhando quem ficou no chão nesta sequência.
        """
        por_tier = ((personagem.get("efeitos") or {}).get("thp_ao_derrubar")) or 0
        if not por_tier or combatente is None:
            return
        derrubados = sum(1 for _golpe, inimigo in golpes if inimigo.caido)
        if not derrubados:
            return
        quanto = por_tier * max(1, self._tier_da_run(run))
        motor.ganhar_thp(combatente, quanto)
        await db.definir_thp(
            self.bot.db, run["id"], combatente.user_id, combatente.thp
        )
        self._registrar(
            run, 0,
            [f"🩸 **{combatente.nome}** drena o que caiu: **+{quanto}** de THP"],
        )

    async def _gravar_hp_do_combatente(self, run: dict[str, Any], quem) -> None:
        """Grava o HP de quem levou dano, no lugar certo.

        O aliado conjurado não tem linha em `run_participantes` — ele vive na
        tabela de invocações, dentro do passo. Sem este desvio, o inimigo que
        batesse nele gravaria num lugar que não existe.
        """
        if quem.e_invocacao:
            await db.definir_hp_invocacao(
                self.bot.db, run["id"], self._passo(run), quem.user_id, quem.hp_atual
            )
            return
        await db.definir_hp(self.bot.db, run["id"], quem.user_id, quem.hp_atual)
        await db.definir_thp(self.bot.db, run["id"], quem.user_id, quem.thp)

    async def _vez_da_invocacao(self, run: dict[str, Any], estado, aliado) -> None:
        """A vez do aliado conjurado: ele bate no inimigo mais machucado.

        Sem tática: o bot não joga por ninguém. Mirar o mais ferido é a única
        escolha que não precisa de opinião — fecha combate mais rápido e não
        desperdiça o golpe num alvo que já ia cair de qualquer forma.
        """
        alvo = min(
            estado.inimigos_vivos, key=lambda i: i.hp_atual, default=None
        )
        if alvo is None:
            return
        golpe = motor.atacar(
            aliado.nome, aliado.bonus_ataque, aliado.dano_arma, alvo.nome, alvo.ca
        )
        if golpe.acertou:
            alvo.hp_atual = max(0, alvo.hp_atual - golpe.dano)
            await db.definir_hp_inimigos(
                self.bot.db, run["id"], self._passo(run),
                {i.indice: i.hp_atual for i in estado.inimigos},
            )
        self._registrar(
            run, estado.rodada,
            [f"👹 **{aliado.nome}** · {E.texto_do_contra_ataque(golpe, alvo.nome)}"],
        )

    async def _inspiracao_de(self, run: dict[str, Any], onde: str):
        """Quem no grupo socorre aquele tipo de falha, e com que dado.

        Devolve (personagem, habilidade, dado) do primeiro que serve, ou
        (None, None, ""). `onde` é "ataque", "save" ou "pericia": a escolha do
        tier 2 do bardo decide qual rolagem a Inspiração dele alcança.
        """
        for p in await db.personagens_da_run(self.bot.db, run["id"]):
            habilidade, acao = self._reacao_de(p, "falhou_teste")
            if habilidade is None or acao.get("inspira") != onde:
                continue
            dado = self._dado_de_inspiracao(p, acao)
            if dado:
                return p, habilidade, dado
        return None, None, ""

    async def _inspirar_o_golpe(
        self, run: dict[str, Any], estado, atacante, golpes
    ) -> None:
        """Inspiração no ataque: o golpe que errou por pouco passa a acertar.

        Roda depois de a sequência resolver, e refaz só o que mudou — o d20 do
        golpe sobe, e se agora alcança a CA o dano é rolado e descontado. Quem
        chama grava o HP dos inimigos em seguida.
        """
        passo = self._passo(run)
        for golpe, inimigo in golpes:
            if golpe.acertou or atacante is None:
                continue
            # O 1 natural erra por maior que seja o total: nao ha o que
            # socorrer, e gastar o dado nele seria perder a carga por nada.
            if golpe.falha_critica:
                continue
            p, habilidade, dado = await self._inspiracao_de(run, "ataque")
            if p is None:
                return
            falta = golpe.ca_alvo - golpe.total
            if not motor.pode_virar(falta, dado):
                continue
            if not await db.gastar_uso(
                self.bot.db, run["id"], p["user_id"], habilidade.chave_de_uso,
                self._chave_de_recarga(habilidade, run, passo), habilidade.vezes,
            ):
                return
            ajuda = motor.rolar_dano(dado)
            golpe.bonus += ajuda
            # O dano sai do motor, pela mesma conta do golpe normal: a arma, o
            # dano_ferido e todos os dados a mais. Recalcular aqui fazia o
            # golpe socorrido dar um quarto do golpe que acertou sozinho.
            if not motor.refazer_o_golpe(atacante, inimigo, golpe):
                self._registrar(
                    run, estado.rodada,
                    [f"🎵 **{habilidade.nome}**: {p['nome']} sopra **+{ajuda}** "
                     f"no golpe de {golpe.atacante} — e nao basta"],
                )
                continue
            self._registrar(
                run, estado.rodada,
                [f"🎵 **{habilidade.nome}**: {p['nome']} sopra **+{ajuda}** no "
                 f"golpe de {golpe.atacante} — acerta por **{golpe.dano}**"],
            )

    async def _inspirar_o_save(self, run: dict[str, Any], estado, feito) -> None:
        """Inspiração no save: quem falhou por pouco passa a resistir.

        O motor refaz o dano a partir da vida anterior a acao da criatura,
        respeitando metade no sucesso, vida temporaria e os outros golpes.
        """
        passo = self._passo(run)
        for investida in feito.investidas:
            if investida.save is None or investida.save.passou:
                continue
            p, habilidade, dado = await self._inspiracao_de(run, "save")
            if p is None:
                return
            falta = investida.save.cd - investida.save.total
            if not motor.pode_virar(falta, dado):
                continue
            if not await db.gastar_uso(
                self.bot.db, run["id"], p["user_id"], habilidade.chave_de_uso,
                self._chave_de_recarga(habilidade, run, passo), habilidade.vezes,
            ):
                return
            ajuda = motor.rolar_dano(dado)
            if ajuda < falta:
                self._registrar(
                    run, estado.rodada,
                    [f"🎵 **{habilidade.nome}**: {p['nome']} sopra **+{ajuda}** "
                     f"no save de {investida.alvo.nome} — e nao basta"],
                )
                continue
            alvo = investida.alvo
            dano_anterior = investida.dano
            motor.refazer_o_save(feito, investida, ajuda)
            evitado = dano_anterior - investida.dano
            self._registrar(
                run, estado.rodada,
                [f"🎵 **{habilidade.nome}**: {p['nome']} sopra **+{ajuda}** no "
                 f"save de {alvo.nome} — resiste, e evita **{evitado}** de dano"],
            )

    async def _socorrer_o_teste(self, run: dict[str, Any], resultado) -> None:
        """Flash of Genius: quem tem a reação salva o teste falhado de alguém.

        Dispara sozinho, como as outras reações do bot, e só quando o bônus
        vira a falha em sucesso — não queima o uso num teste que já passou nem
        num que falhou longe demais. Serve qualquer um do grupo, inclusive
        quem tem a habilidade.
        """
        passo = self._passo(run)
        for p in await db.personagens_da_run(self.bot.db, run["id"]):
            habilidade, acao = self._reacao_de(p, "falhou_teste")
            if habilidade is None:
                continue
            # A Dark One's Own Luck do bruxo é o patrono torcendo o destino
            # DELE: não socorre o teste de mais ninguém.
            if acao.get("so_em_si") and p["user_id"] != resultado.user_id:
                continue
            # A Inspiracao Bardica socorre com DADO, nao com numero: entra se
            # o teto do dado cobriria a falha, e so depois rola. As outras
            # cinco reacoes de socorro somam um numero fixo e nunca falham.
            dado = self._dado_de_inspiracao(p, acao)
            if dado:
                if (
                    acao.get("inspira") != "pericia"
                    or not motor.pode_virar(resultado.cd - resultado.total, dado)
                ):
                    continue
                bonus = motor.rolar_dano(dado)
            else:
                # O tier 5 sobe o bonus de 5 para 10, por passiva.
                bonus = (
                    ((p.get("efeitos") or {}).get("flash_bonus"))
                    or acao.get("bonus", 0)
                )
                if not motor.vale_ajudar(resultado, bonus):
                    continue
            if not await db.gastar_uso(
                self.bot.db, run["id"], p["user_id"], habilidade.chave_de_uso,
                self._chave_de_recarga(habilidade, run, passo), habilidade.vezes,
            ):
                continue
            resultado.ajuda = bonus
            resultado.quem_ajudou = p["nome"]
            # Com dado, o socorro pode nao bastar: o teto cobria, a rolagem
            # nao. O uso sai de qualquer forma, como na mesa.
            fecho = "o teste passa" if resultado.passou else "e nao basta"
            await self._anunciar_habilidade(
                run,
                f"✨ **{habilidade.nome}**: {p['nome']} socorre "
                f"{resultado.personagem} com **+{bonus}** — {fecho}.",
            )
            return

    @staticmethod
    def _dado_de_inspiracao(personagem: dict[str, Any], acao: dict) -> str:
        """O dado da Inspiração daquele bardo, ou "" se a reação é de número.

        O dado base é o da habilidade; a passiva do tier 4 o substitui por um
        maior. Quem não tem Inspiração (o artífice, o paladino) devolve vazio
        e segue pelo caminho do bônus fixo.
        """
        if not acao.get("inspira"):
            return ""
        melhor = ((personagem.get("efeitos") or {}).get("dado_inspiracao")) or ""
        return melhor or acao.get("dado", "")

    @staticmethod
    def _reacao_de(personagem: dict[str, Any], quando: str):
        """A reacao daquele gatilho, se o personagem tiver alguma."""
        for _tier, habilidade in personagem.get("habilidades") or []:
            acao = habilidade.acao or {}
            if acao.get("tipo") == "reacao" and acao.get("quando") == quando:
                return habilidade, acao
        return None, None

    async def _reacoes_do_revide(
        self, run: dict[str, Any], estado, golpes, investidas=()
    ) -> None:
        """As reacoes que o turno do inimigo dispara, na ordem em que importam.

        A esquiva vem antes da queda: cortar o golpe pela metade pode evitar
        que a segunda reacao precise acontecer.

        **A esquiva vale so contra GOLPE**, e isso e de propósito: Uncanny
        Dodge corta um ataque que o ladino ve vir, nao uma explosao em que ele
        falhou a resistencia.

        **A queda vale contra tudo.** Relentless dispara por chegar a zero, e
        nao importa o que levou ate lá. Aqui so os golpes chegavam, entao o
        barbaro se recusava a cair quando a criatura BATIA nele e ficava no
        chao quando ela o matava com a habilidade — que e justamente o golpe
        mais pesado que ela tem.

        As investidas `do_golpe` ficam de fora porque o dano delas ja veio no
        golpe que as disparou: elas estao representadas em `golpes`. Hoje esse
        filtro nao MUDA nada — a deduplicacao abaixo ja descartaria essas
        entradas, porque o golpe que as trouxe vem antes na lista —, e esta
        aqui para dizer a intencao e para o dia em que uma das duas coisas sair
        de cena. Nao ha caso cobrindo ele: cobrir pediria uma reacao de queda
        com mais de um uso, e nenhuma existe.
        """
        await self._esquivas(run, golpes)
        # Um alvo por reacao, mesmo aparecendo duas vezes: criatura com dois
        # ataques entrega dois golpes no mesmo personagem, e uma reacao de
        # varios usos dispararia duas vezes por uma unica queda.
        caiu = []
        vistos: set[int] = set()
        candidatos = list(golpes) + [
            (investida, investida.alvo)
            for investida in investidas
            if investida.dano and not investida.do_golpe
        ]
        for origem, atingido in candidatos:
            if atingido.user_id in vistos:
                continue
            vistos.add(atingido.user_id)
            caiu.append((origem, atingido))
        await self._reacoes_ao_cair(run, caiu)

    async def _esquivas(self, run: dict[str, Any], revides) -> None:
        """Uncanny Dodge: corta o golpe pesado pela metade, devolvendo o HP."""
        passo = self._passo(run)
        for golpe, atingido in revides:
            if not golpe.acertou or golpe.dano <= 0:
                continue
            personagem = await self._personagem_na_run(run, atingido.user_id)
            if not personagem:
                continue
            habilidade, acao = self._reacao_de(personagem, "sofreu_golpe")
            if habilidade is None:
                continue
            # O golpe ja entrou no HP: a conta e feita sobre como estava antes.
            antes = motor.Combatente(
                atingido.user_id, atingido.nome, atingido.ca, 0, "1d1",
                atingido.hp_max, min(atingido.hp_max, atingido.hp_atual + golpe.dano),
                thp=atingido.thp,
            )
            if not motor.vale_esquivar(antes, golpe.dano, acao.get("limiar", 1 / 3)):
                continue
            if not await db.gastar_uso(
                self.bot.db, run["id"], atingido.user_id, habilidade.chave_de_uso,
                self._chave_de_recarga(habilidade, run, passo), habilidade.vezes,
            ):
                continue
            devolvido = golpe.dano - int(golpe.dano * acao.get("reduz", 0.5))
            golpe.dano -= devolvido
            atingido.hp_atual = min(atingido.hp_max, atingido.hp_atual + devolvido)
            await db.definir_hp(
                self.bot.db, run["id"], atingido.user_id, atingido.hp_atual
            )
            await self._anunciar_habilidade(
                run,
                f"\u2728 **{habilidade.nome}**: {atingido.nome} desvia e segura "
                f"{devolvido} de dano.",
            )

    async def _reacoes_ao_cair(self, run: dict[str, Any], revides) -> None:
        """Relentless e afins: quem caiu nesta rodada pode nao cair de verdade."""
        passo = self._passo(run)
        for _golpe, atingido in revides:
            if not atingido.caido:
                continue
            personagem = await self._personagem_na_run(run, atingido.user_id)
            if not personagem:
                continue
            habilidade, acao = self._reacao_de(personagem, "caiu")
            if habilidade is None:
                continue
            if not await db.gastar_uso(
                self.bot.db, run["id"], atingido.user_id, habilidade.chave_de_uso,
                self._chave_de_recarga(habilidade, run, passo), habilidade.vezes,
            ):
                continue
            atingido.hp_atual = acao.get("hp", 1)
            motor.ganhar_thp(atingido, motor.rolar_dano(acao["thp"]))
            await db.definir_hp(
                self.bot.db, run["id"], atingido.user_id, atingido.hp_atual
            )
            await db.definir_thp(self.bot.db, run["id"], atingido.user_id, atingido.thp)
            await self._anunciar_habilidade(
                run,
                f"\u2728 **{habilidade.nome}**: {atingido.nome} se recusa a cair "
                f"— fica com {atingido.hp_atual} HP e {atingido.thp} de THP.",
            )

    async def _guardar_debuffs(
        self, run: dict[str, Any], investidas: list
    ) -> list[str]:
        """Grava as condições que as criaturas aplicaram, e diz o que cada um pegou.

        São as mesmas condições da armadilha, na mesma tabela: o Envenenado que
        a aranha deixa sai da sala com o grupo e decai por combate como
        qualquer outro. Quem caiu no combate não leva nada — já está fora.
        """
        linhas: list[str] = []
        for investida in investidas:
            if not investida.debuffs or investida.alvo.caido:
                continue
            for cid in investida.debuffs:
                stacks = await db.aplicar_condicao(
                    self.bot.db, run["id"], investida.alvo.user_id, cid
                )
                linhas.append(
                    f"**{investida.alvo.nome}** fica com "
                    f"{condicoes.rotulo(cid, stacks)} — "
                    f"{condicoes.descricao(cid, stacks=stacks)}"
                )
        return linhas

    async def _guardar_atordoamentos(
        self, run: dict[str, Any], estado, investidas: list, ja_agiram: set[int]
    ) -> None:
        """Grava quem ficou atordoado: perde a proxima vez que teria.

        Quem ainda nao agiu nesta rodada perde a vez desta; quem ja passou,
        a da rodada seguinte — por isso o "+ 1" para esses.
        """
        passo = self._passo(run)
        for investida in investidas:
            if not investida.atordoou:
                continue
            ja_agiu = investida.alvo.user_id in ja_agiram
            # "desde" e a rodada antes da primeira que ele perde: o save de
            # quem se livra sozinho so vem depois de perder uma vez.
            valor = {
                "por": investida.habilidade,
                "desde": estado.rodada if ja_agiu else estado.rodada - 1,
            }
            prazo = estado.rodada + max(1, investida.atordoa_por) + (1 if ja_agiu else 0)
            if investida.repete_save:
                # "refaz o save no final do turno": o prazo e so um teto, quem
                # decide e o proprio alvo, rodada a rodada, em _virar_efeitos.
                valor["save"] = investida.save.atributo
                valor["cd"] = investida.save.cd
                prazo = estado.rodada + PRAZO_ATE_PASSAR
            await db.aplicar_efeito(
                self.bot.db,
                run["id"],
                passo,
                "personagem",
                investida.alvo.user_id,
                "atordoado",
                valor,
                prazo,
            )

    async def _virar_efeitos(self, run: dict[str, Any], estado) -> None:
        """No fim da rodada: cura de quem tem cura por turno, e prazos vencidos."""
        passo = self._passo(run)
        curas = {}
        levantados = []
        # `combatentes` e nao `vivos`: a cura por turno levanta caido como as
        # outras. Grupo INTEIRO no chao nao chega aqui — o laco do `_avancar`
        # ve `estado.encerrado` antes de virar a rodada e encerra o combate —,
        # entao a regeneracao socorre quem caiu, mas nao desfaz uma derrota.
        for c in estado.combatentes:
            if c.cura_por_turno:
                estava_caido = c.caido
                ganho = motor.curar(c, c.cura_por_turno)
                if ganho:
                    curas[c.user_id] = c.hp_atual
                if estava_caido and not c.caido:
                    levantados.append(c)
        if curas:
            await db.definir_hp_varios(self.bot.db, run["id"], curas)
        # A regeneracao levanta sem ninguem decidir, e cobra igual: a linha
        # entra no registro da rodada para o grupo ver o preco.
        for c in levantados:
            self._registrar(run, estado.rodada, [await self._cobrar_o_retorno(run, c)])
        await self._sangrar_acorrentados(run, estado)
        await self._refazer_saves(run, estado)
        await db.limpar_efeitos_vencidos(self.bot.db, run["id"], passo, estado.rodada)

    async def _sangrar_acorrentados(self, run: dict[str, Any], estado) -> None:
        """Grilhões Planares: a criatura presa sangra todo fim de rodada.

        Na mesa ela andaria para fugir do efeito; aqui não há posição, então o
        escape é o save: a cada rodada ela refaz o teste e, passando, a
        corrente arrebenta. Sem isso a magia seria dano garantido e viraria a
        mais forte de alvo único do jogo.
        """
        passo = self._passo(run)
        ligados = await db.efeitos_ativos(self.bot.db, run["id"], passo, estado.rodada)
        linhas: list[str] = []
        mexeu = False
        for ligado in ligados:
            valor = ligado.get("valor") or {}
            if ligado["alvo_tipo"] != "inimigo" or not valor.get("dano_por_rodada"):
                continue
            alvo = estado.inimigo(ligado["alvo_id"])
            if alvo is None or alvo.caido:
                continue
            livre = motor.salvar_inimigo(alvo, valor.get("save", "DES"), valor["cd"])
            if livre.passou:
                await db.remover_efeito(
                    self.bot.db, run["id"], passo, "inimigo",
                    ligado["alvo_id"], ligado["efeito"],
                )
                linhas.append(f"⛓️ **{alvo.nome}** arrebenta a corrente")
                continue
            levou = motor.rolar_dano(valor["dano_por_rodada"])
            alvo.hp_atual = max(0, alvo.hp_atual - levou)
            mexeu = True
            caiu = " e cai" if alvo.caido else ""
            linhas.append(f"⛓️ **{alvo.nome}** sangra **{levou}** na corrente{caiu}")
        if mexeu:
            await db.definir_hp_inimigos(
                self.bot.db, run["id"], passo,
                {i.indice: i.hp_atual for i in estado.inimigos},
            )
        if linhas:
            self._registrar(run, estado.rodada, linhas)

    async def _refazer_saves(self, run: dict[str, Any], estado) -> None:
        """Quem esta preso por um efeito de 'save no fim do turno' rola de novo.

        So depois de perder uma vez: o efeito posto no fim da rodada N custa a
        rodada N+1, e a chance de escapar vem no fim dela.
        """
        passo = self._passo(run)
        ligados = await db.efeitos_ativos(self.bot.db, run["id"], passo, estado.rodada - 1)
        for ligado in ligados:
            valor = ligado.get("valor") or {}
            if ligado["alvo_tipo"] != "personagem" or not valor.get("save"):
                continue
            if estado.rodada - 1 <= valor.get("desde", 0):
                continue  # ainda nao perdeu a vez que o efeito custa
            alvo = estado.combatente(ligado["alvo_id"])
            if alvo is None or alvo.caido:
                continue
            resultado = motor.salvar_combatente(alvo, valor["save"], valor["cd"])
            if not resultado.passou:
                continue
            await db.remover_efeito(
                self.bot.db, run["id"], passo, "personagem", ligado["alvo_id"],
                ligado["efeito"],
            )
            alvo.atordoado = False
            await self._anunciar_habilidade(
                run,
                f"🧿 **{alvo.nome}** se livra de "
                f"**{valor.get('por', 'efeito')}** "
                f"({valor['save']} {resultado.total} vs CD {valor['cd']}).",
            )

    async def _anunciar_habilidade(self, run: dict[str, Any], texto: str) -> None:
        """O grupo ve que alguem usou uma habilidade, sem detalhe de rolagem.

        Guarda o que publicou: a mesma frase ia sair DE NOVO em privado
        para quem clicou, e o jogador via a habilidade dele duas vezes na
        tela. Quem compara e `_avancar`.
        """
        canal = await self._canal(run)
        if canal:
            try:
                mensagem = await canal.send(texto)
            except discord.HTTPException:
                return
            self._publicado[run["id"]] = texto
            self._usadas.setdefault(run["id"], []).append(mensagem)

    async def _apos_combate_vencido(
        self, run: dict[str, Any], sala: Sala, estado=None
    ) -> None:
        incursao = self._incursao_da_run(run)
        if sala.pontos_organizacao:
            await self._creditar(
                run,
                sala.pontos_organizacao,
                f"Sala superada: {sala.nome}",
                f"sala:{self._passo(run)}:{sala.id}",
            )
        await self._marcar_sala_superada(run, sala)

        canal = await self._canal(run)
        if sala.id == incursao.objetivo.id:
            await self._encerrar_run(run, "sucesso")
            await self._creditar(
                run, config.PONTOS_PARTICIPACAO, "Participação na incursão", "participacao"
            )
            await self._creditar(
                run, incursao.pontos_conclusao, "Objetivo cumprido", "conclusao"
            )
            # A vitoria paga as duas partes: as salas atravessadas e o
            # bonus de ter fechado a incursao.
            await self._pagar_as_salas(run)
            await self._pagar_o_fecho(run)
            if canal:
                # Desfecho num embed so: vitoria, como o grupo saiu, MEs e pontos.
                lancamentos, total = await self._balanco(run)
                await canal.send(
                    embed=E.run_concluida(
                        incursao, await self._membros(run), estado, lancamentos, total,
                        await self._caminho(run),
                        await db.ouro_da_run(self.bot.db, run["id"]),
                    )
                )
                if incursao.lore_final:
                    await canal.send(embed=E.lore_fecho(incursao))
            return

        if canal and estado is not None:
            await canal.send(embed=E.combate_vencido(sala, estado))

        # Antes de decair: quem a criatura levou ao teto sai agora. Na outra
        # ordem o decaimento tiraria o stack que estourou, e o teto de uma
        # condicao que decai nunca pegaria ninguem.
        await self._expulsar_estourados(run)

        # Um combate a menos no prazo dos debuffs e dos buffs. As maldicoes e a
        # Exaustao tem prazo NULL e nao sao tocadas: duram a incursao.
        await self._vencer_prazo_das_condicoes(run)

        await self._seguir_do_descanso(
            await db.buscar_run(self.bot.db, run["id"]), run["linha_atual"]
        )

    async def _vencer_prazo_das_condicoes(self, run: dict[str, Any]) -> None:
        """Fecha um combate: toda condição perde 1 stack, menos a Exaustão."""
        acabaram = await db.decair_condicoes(self.bot.db, run["id"])
        if not acabaram:
            return
        canal = await self._canal(run)
        if not canal:
            return
        nomes = await self._nomes(run)
        linhas = [
            f"{condicoes.rotulo(cid)} passa em "
            f"**{nomes.get(user_id) or f'<@{user_id}>'}**"
            for user_id, cid in acabaram
        ]
        await canal.send("⏳ " + "; ".join(linhas) + ".")

    async def rolar(self, interaction: discord.Interaction, run_id: int, sala_id: str) -> None:
        run = await db.buscar_run(self.bot.db, run_id)
        if not run or run["status"] != "em_sala" or run["sala_atual"] != sala_id:
            await interaction.response.send_message("Esta sala já foi resolvida.", ephemeral=True)
            return
        # A sala pode estar FECHADA com a run ainda nela: a emboscada do
        # Mimico reusa o id e o status da sala do Tesouro, e o combate corre
        # dentro dela. Um botao antigo na tela de alguem ainda mandava a
        # rolagem, e ela reabria o fecho da sala — a votacao do passo
        # seguinte aparecia no meio do combate.
        if await db.sala_fechada(self.bot.db, run_id, self._passo(run)):
            await interaction.response.send_message(
                "Esta sala já foi resolvida.", ephemeral=True
            )
            return
        if not await db.esta_na_run(self.bot.db, run_id, interaction.user.id):
            await interaction.response.send_message("Você não faz parte desta run.", ephemeral=True)
            return

        incursao = self._incursao_da_run(run)
        sala = await self._sala_corrente(run)
        if sala is None or sala.e_combate:
            # O baú acordou entre o clique e a chegada: não há mais teste aqui.
            await interaction.response.send_message(
                "Esta sala virou combate — não há teste para rolar.", ephemeral=True
            )
            return
        if not await db.esta_de_pe(self.bot.db, run_id, interaction.user.id):
            await interaction.response.send_message(
                "Você está caído — quem está no chão não encara a sala. Espere o Descanso.",
                ephemeral=True,
            )
            return
        personagem = await db.personagem_da_run(self.bot.db, run_id, interaction.user.id)
        if not personagem:
            await interaction.response.send_message(
                "Não achei o personagem com que você entrou nesta run.", ephemeral=True
            )
            return

        personagem["user_id"] = interaction.user.id
        resultado = motor.testar(
            personagem, sala,
            saldo=await self._saldo(run, interaction.user.id),
            tier=self._tier_da_run(run),
        )
        # Flash of Genius: alguem do grupo socorre a falha antes de ela virar
        # consequencia. Entra no `modificador` gravado, para a margem e o
        # progresso da sala contarem com a ajuda.
        await self._socorrer_o_teste(run, resultado)
        novo = await db.registrar_teste(
            self.bot.db,
            run_id,
            self._passo(run),
            sala_id,
            interaction.user.id,
            resultado.personagem,
            resultado.pericia,
            resultado.d20,
            resultado.modificador + resultado.ajuda,
            resultado.cd,
        )
        if not novo:
            await interaction.response.send_message(
                "Você já rolou nesta sala — cada um rola uma vez.", ephemeral=True
            )
            return

        # O resumo privado da rolagem — e do dano que ela custou — sai do
        # canal quando a SALA fecha, nao quando a proxima abre: entre uma
        # coisa e outra ha uma votacao inteira.
        self._guardar_efemera(run_id, interaction)
        veredito = (
            f"passou por **{resultado.margem}** de margem"
            if resultado.passou
            else f"falhou por **{resultado.cd - resultado.total}**"
        )
        socorro = (
            f" (+{resultado.ajuda} de {resultado.quem_ajudou})"
            if resultado.ajuda
            else ""
        )
        await interaction.response.send_message(
            f"🎲 **{resultado.d20}** {resultado.modificador:+d}{socorro} = "
            f"**{resultado.total}** em {resultado.pericia} (CD {resultado.cd}) "
            f"— {veredito}.",
            ephemeral=True,
        )

        registros = await db.testes_da_sala(self.bot.db, run_id, self._passo(run))
        total = len(await db.participantes_de_pe(self.bot.db, run_id))
        resolucao = _resolucao(sala, registros, total)

        if resolucao.encerrada:
            await self._concluir_sala(run, sala, resolucao)
        else:
            ja_rolaram, faltam_rolar = await self._quem_rolou(run, registros)
            embed, _ = E.sala_aberta(
                sala, run["linha_atual"], ja_rolaram, faltam_rolar,
                incursao.paradas, tier=self._tier_da_run(run),
                tema=self._tema_da_sala(run, sala),
            )
            if interaction.message is not None:
                try:
                    await interaction.message.edit(embed=embed, view=ViewSala(self, run_id, sala_id))
                except discord.HTTPException:
                    pass

    async def _concluir_sala(
        self, run: dict[str, Any], sala: Sala, resolucao: Optional[ResolucaoSala]
    ) -> None:
        """Fecha a sala e segue a run. Roda uma vez por sala, nunca duas.

        Duas rolagens que resolvam a sala juntas chegavam as duas aqui, e as
        duas seguiam para o passo seguinte — que, no fim do caminho, e o
        combate do objetivo: o painel saia duplicado.
        """
        if not await db.tomar_o_fecho_da_sala(
            self.bot.db, run["id"], self._passo(run), sala.id
        ):
            return
        canal = await self._canal(run)
        if not canal:
            return

        await self._limpar_botoes(await db.buscar_run(self.bot.db, run["id"]))
        # As rolagens privadas do teste saem junto com a sala. Antes elas
        # so sumiam quando a PROXIMA abria, e entre uma coisa e outra ha
        # uma votacao inteira — o jogador ficava com o resultado de uma
        # sala que ja acabou pendurado na tela.
        await self._limpar_efemeras(run["id"])

        desfecho = None
        if resolucao is not None:
            desfecho = await self._consequencias_da_sala(run, sala, resolucao)
            await canal.send(embed=E.resultado_sala(resolucao, desfecho))
            if resolucao.superada and sala.pontos_organizacao:
                await self._creditar(
                    run, sala.pontos_organizacao, f"Sala superada: {sala.nome}", f"sala:{self._passo(run)}:{sala.id}"
                )
            if resolucao.superada:
                await self._marcar_sala_superada(run, sala)
            await self._expulsar_estourados(run)

        if sala.tipo == "Descanso":
            # Pelo TIPO, e nao por `resolucao is None`: sala sem rolagem e o
            # que o descanso tem de particular hoje, nao uma regra geral.
            await canal.send(
                embed=E.descanso_fechado(
                    sala, await self._linhas_do_descanso(run)
                )
            )

        # Mímico acordado no baú: a sala vira combate em vez de devolver à votação.
        if desfecho is not None and desfecho.mimicos:
            await self._soltar_mimicos(run, sala)
            return

        await self._seguir_do_descanso(run, run["linha_atual"])

    # ------------------------------------------------------------ descanso

    async def _seguir_do_descanso(self, run: dict[str, Any], parada: int) -> None:
        """Fecha a parada e abre a seguinte — ou o objetivo, se era a última.

        Conta PARADAS e não salas: com o descanso virando parada a mais, a
        Média tem seis e a Longa nove. Estava escrito em dois lugares com
        `passos` no lugar de `paradas`, e os dois passariam direto para o
        objetivo no meio do caminho.
        """
        incursao = self._incursao_da_run(run)
        if not incursao:
            return
        if parada < incursao.paradas:
            await self._abrir_votacao(run, parada + 1)
        else:
            await self._chegar_ao_objetivo(run)

    def _sala_de_descanso(self, incursao: Incursao) -> Optional[Sala]:
        """A sala de Descanso do banco da Organização, que o caminho usa.

        O descanso fixo reusa a sala que o banco já tem — a Cela do Coveiro da
        Guilda, a Adega Falsa das Sombras — em vez de inventar uma genérica:
        a ficção é de cada Organização, e ela já estava escrita.
        """
        banco = self.bancos.get(incursao.organizacao)
        if not banco:
            return None
        return next((s for s in banco.salas if s.tipo == "Descanso"), None)

    def _tema_da_sala(self, run: dict[str, Any], sala: Sala) -> Optional[str]:
        """O tema que vale para esta sala nesta run, ou None.

        Só entra em jogo o tema que a sala TEM e a incursão PEDIU no filtro.
        Com mais de um candidato a escolha é sorteada — e semeada por
        `run:sala`, do mesmo jeito que `_trocas_da_parada`: o mesmo par dá
        sempre o mesmo tema, então redesenhar o cartão ou reiniciar o bot não
        troca o bando no meio do combate, e nada precisa ser gravado.

        O cartão da sala e a abertura do combate chamam os dois daqui, pela
        mesma razão que o tier: senão a sala mostraria uma criatura e o
        combate abriria com outra.
        """
        incursao = self._incursao_da_run(run)
        if incursao is None:
            return None
        return sala.tema_em_jogo(
            incursao.filtro.temas, random.Random(f"{run['id']}:{sala.id}")
        )

    def _trocas_da_parada(self, run_id: int, parada: int) -> list:
        """As três trocas desta parada — sempre as mesmas três.

        Derivadas da semente `run:parada` em vez de gravadas: assim o mapa da
        run continua sendo o mapa das SALAS, e redesenhar o cartão, ou reabri-lo
        depois de um restart, devolve a mesma mesa.
        """
        return consequencias.trocas_oferecidas(
            rng=random.Random(f"{run_id}:{parada}")
        )

    async def _abrir_descanso_duro(self, run: dict[str, Any], parada: int) -> None:
        """O descanso da Longa depois da sexta sala: três trocas, uma escolha.

        Reusa o caminho do voto de sala inteiro: as trocas sorteadas ficam em
        `run_mapa` como as salas ficariam, o voto em `run_votos`, e a maioria
        fecha. O que muda é o que o id guardado significa — e por isso não há
        tabela nova nem um segundo jeito de votar.
        """
        incursao = self._incursao_da_run(run)
        canal = await self._canal(run)
        if not (incursao and canal):
            return
        sala = incursoes.sala_do_descanso_duro()
        trocas = self._trocas_da_parada(run["id"], parada)
        if not trocas:
            await canal.send(
                "Não achei as trocas deste descanso. O grupo segue sem descansar."
            )
            await self._seguir_do_descanso(run, parada)
            return

        total = len(await db.participantes_de_pe(self.bot.db, run["id"]))
        votos = await db.votos_da_linha(self.bot.db, run["id"], parada)
        mensagem = await canal.send(
            f"🌙 {await self._chamar(run)} — falta uma sala. O que o grupo "
            f"gasta para chegar nela?",
            embed=E.descanso_duro(
                sala, trocas, votos, total, parada, incursao.paradas
            ),
            view=ViewTrocaDoDescanso(self, run["id"], parada, trocas),
        )
        # A run fica em 'escolhendo', como numa votacao de sala: e esse o
        # estado que `tomar_a_sala` exige para fechar a parada uma unica vez.
        await db.atualizar_run(
            self.bot.db, run["id"], status="escolhendo", sala_atual=None,
            linha_atual=parada, mensagem_id=mensagem.id,
        )

    async def votar_troca(
        self, interaction: discord.Interaction, run_id: int, parada: int, troca_id: str
    ) -> None:
        """Um voto na troca do descanso duro. A maioria fecha, como na sala."""
        run = await db.buscar_run(self.bot.db, run_id)
        if not run or run["linha_atual"] != parada or run["status"] != "escolhendo":
            await interaction.response.send_message(
                "Este descanso já passou.", ephemeral=True
            )
            return
        if not await db.esta_na_run(self.bot.db, run_id, interaction.user.id):
            await interaction.response.send_message(
                "Você não faz parte desta run.", ephemeral=True
            )
            return
        if not await db.esta_de_pe(self.bot.db, run_id, interaction.user.id):
            await interaction.response.send_message(
                "Você está caído — quem está no chão não decide o descanso.",
                ephemeral=True,
            )
            return
        oferecidas = {t.id for t in self._trocas_da_parada(run_id, parada)}
        troca = consequencias.TROCA_POR_ID.get(troca_id)
        if troca is None or troca_id not in oferecidas:
            await interaction.response.send_message(
                "Essa troca não está na mesa deste descanso.", ephemeral=True
            )
            return

        await db.registrar_voto(
            self.bot.db, run_id, parada, interaction.user.id, troca_id
        )
        await interaction.response.send_message(
            f"Voto em **{troca.nome}** registrado.", ephemeral=True
        )
        self._guardar_efemera(run_id, interaction)

        votos = await db.votos_da_linha(self.bot.db, run_id, parada)
        total = len(await db.participantes_de_pe(self.bot.db, run_id))
        contagem: dict[str, int] = {}
        for escolhida in votos.values():
            contagem[escolhida] = contagem.get(escolhida, 0) + 1
        vencedora, quantos = max(
            contagem.items(), key=lambda par: par[1], default=("", 0)
        )
        if quantos < maioria_de(total):
            await self._redesenhar_descanso_duro(run, parada, votos, total)
            return
        # So UM clique fecha a parada: `tomar_a_sala` e o mesmo atomico que a
        # votacao de sala usa, e sem ele cinco cliques simultaneos aplicariam
        # a troca cinco vezes.
        if not await db.tomar_a_sala(
            self.bot.db, run_id, parada, incursoes.ID_DO_DESCANSO_DURO
        ):
            return
        await self._resolver_descanso_duro(
            await db.buscar_run(self.bot.db, run_id), parada,
            consequencias.TROCA_POR_ID[vencedora],
        )

    async def _redesenhar_descanso_duro(
        self, run: dict[str, Any], parada: int, votos: dict, total: int
    ) -> None:
        """Reescreve o cartao com a contagem de votos de agora."""
        incursao = self._incursao_da_run(run)
        canal = await self._canal(run)
        if not (incursao and canal and run.get("mensagem_id")):
            return
        trocas = self._trocas_da_parada(run["id"], parada)
        try:
            mensagem = await canal.fetch_message(run["mensagem_id"])
            await mensagem.edit(
                embed=E.descanso_duro(
                    incursoes.sala_do_descanso_duro(), trocas, votos, total,
                    parada, incursao.paradas,
                ),
                view=ViewTrocaDoDescanso(self, run["id"], parada, trocas),
            )
        except discord.HTTPException:
            pass

    async def _resolver_descanso_duro(
        self, run: dict[str, Any], parada: int, troca
    ) -> None:
        """Aplica a troca escolhida no grupo inteiro, e segue o caminho."""
        canal = await self._canal(run)
        tier = max(1, self._tier_da_run(run) or 1)
        await db.registrar_visita(
            self.bot.db, run["id"], parada, incursoes.ID_DO_DESCANSO_DURO
        )
        await self._limpar_botoes(run)
        await self._limpar_efemeras(run["id"])
        combatentes = await self._combatentes(run)
        linhas: list[str] = []

        hps: dict[int, int] = {}
        thps: dict[int, int] = {}
        for c in combatentes:
            nota = []
            if troca.cura_pct:
                # `curar_quanto` ja levanta quem caiu e ja aplica a Debilidade
                # e o Vigor: a cura da vigilia e cura como qualquer outra, e
                # nao o valor fixado que o descanso normal usa nos caidos.
                quanto = motor.curar_quanto(
                    c, max(1, (c.hp_max * troca.cura_pct) // 100)
                )
                if quanto:
                    hps[c.user_id] = c.hp_atual
                    nota.append(f"+{quanto} de HP")
            if troca.thp_pct:
                ganho = max(1, (c.hp_max * troca.thp_pct) // 100)
                motor.ganhar_thp(c, ganho)
                thps[c.user_id] = c.thp
                nota.append(f"+{ganho} de vida temporária")
            if nota:
                linhas.append(f"• **{c.nome}** {', '.join(nota)}")
        if hps:
            await db.definir_hp_varios(self.bot.db, run["id"], hps)
        if thps:
            await db.definir_thp_varios(self.bot.db, run["id"], thps)

        if troca.exaustao:
            for c in combatentes:
                for _ in range(troca.exaustao):
                    await db.aplicar_condicao(
                        self.bot.db, run["id"], c.user_id, condicoes.EXAUSTAO
                    )
            linhas.append(
                f"🫩 Todos levam **{troca.exaustao} ponto(s) de Exaustão** — "
                f"ela não decai com o combate, e só o descanso normal a tira."
            )
        if troca.limpa_debuffs:
            carregadas = await db.condicoes_da_run(self.bot.db, run["id"])
            limpos = 0
            for user_id, minhas in carregadas.items():
                for cid in consequencias.a_limpar(minhas, (condicoes.DEBUFF,)):
                    while await db.reduzir_condicao(
                        self.bot.db, run["id"], user_id, cid
                    ):
                        pass
                    limpos += 1
            linhas.append(
                f"✨ **{limpos} debuff(s)** saem do grupo."
                if limpos
                else "✨ Não havia debuff nenhum para lavar."
            )
        if troca.ouro_de_sala:
            quanto = mercado.ouro_da_sala(tier)
            pagos = 0
            for p in await db.quem_recebe_da_run(self.bot.db, run["id"]):
                if await db.lancar_ouro(
                    self.bot.db, p["id"], quanto, "Revirou o lugar",
                    run_id=run["id"], chave=f"troca:{parada}",
                ):
                    pagos += 1
            linhas.append(f"💰 **+{quanto}** de ouro para {pagos} personagem(ns).")
        if troca.buff:
            # Sem debuff nem machucado declarados, `premio_do_evento` sorteia
            # so entre os 12 buffs — que e o que a troca promete.
            premio = consequencias.premio_do_evento()
            ganho = consequencias.CondicaoAplicada(premio)
            for c in combatentes:
                ganho.stacks[c.nome] = await db.aplicar_condicao(
                    self.bot.db, run["id"], c.user_id, premio
                )
            nome, valor = E.painel_da_condicao(ganho)
            linhas.append(f"**{nome}**")
            linhas.append(valor)

        # O descanso duro tambem recarrega as habilidades por descanso: ele e
        # descanso, por mais caro que seja.
        # NAO e "sala superada": `_pagar_as_salas` paga por superada, e
        # descansar nao e vencer nada — o normal tambem nao e marcado.
        await db.contar_descanso(self.bot.db, run["id"])
        if canal:
            await canal.send(embed=E.descanso_duro_feito(troca, linhas))
        await self._expulsar_estourados(await db.buscar_run(self.bot.db, run["id"]))
        await self._seguir_do_descanso(
            await db.buscar_run(self.bot.db, run["id"]), parada
        )


    # O descanso tira uma coisa: um stack de debuff, ou um ponto de Exaustao.
    # A Exaustao tem botao proprio porque e a unica que nao decai com o
    # combate — o descanso e a unica saida dela.
    TIPOS_DE_LIMPEZA = {
        "debuff": (condicoes.DEBUFF,),
        "exaustao": (condicoes.EXAUSTAO,),
    }

    @staticmethod
    def _limpezas_de(carregadas: dict[str, int]) -> set[str]:
        """Quais das três limpezas servem para quem carrega isto."""
        return {
            chave
            for chave, tipos in Incursoes.TIPOS_DE_LIMPEZA.items()
            if consequencias.a_limpar(carregadas, tipos)
        }

    async def _limpezas_disponiveis(self, run: dict[str, Any]) -> set[str]:
        """A união do que o grupo carrega — é o que decide quais botões existem.

        Os botões são os mesmos para todos porque a mensagem é uma só; cada
        clique age sobre as condições de quem clicou.
        """
        carregadas = await db.condicoes_da_run(self.bot.db, run["id"])
        disponiveis: set[str] = set()
        for condicoes_do_jogador in carregadas.values():
            disponiveis |= self._limpezas_de(condicoes_do_jogador)
        return disponiveis

    async def _descanso_pendente(self, run: dict[str, Any]) -> list[int]:
        """Quem ainda não escolheu no descanso deste passo.

        Quem não carrega nada não precisa clicar: entra marcado, para um grupo
        limpo não ter de dar cinco cliques à toa.
        """
        passo = self._passo(run)
        carregadas = await db.condicoes_da_run(self.bot.db, run["id"])
        pendentes = []
        for user_id in await db.participantes(self.bot.db, run["id"]):
            if not self._limpezas_de(carregadas.get(user_id, {})):
                await db.marcar_descanso(self.bot.db, run["id"], passo, user_id)
                continue
            pendentes.append(user_id)
        ja = await db.quem_descansou(self.bot.db, run["id"], passo)
        return [u for u in pendentes if u not in ja]

    async def limpar_no_descanso(
        self, interaction: discord.Interaction, run_id: int, sala_id: str, chave: str
    ) -> None:
        """Cada personagem limpa UMA condição sua. A sala fecha quando todos escolhem."""
        run = await db.buscar_run(self.bot.db, run_id)
        if not run or run["status"] != "em_sala" or run["sala_atual"] != sala_id:
            await interaction.response.send_message(
                "Este descanso já terminou.", ephemeral=True
            )
            return
        user_id = interaction.user.id
        if not await db.esta_na_run(self.bot.db, run_id, user_id):
            await interaction.response.send_message(
                "Você não faz parte desta run.", ephemeral=True
            )
            return
        passo = self._passo(run)
        if user_id in await db.quem_descansou(self.bot.db, run_id, passo):
            await interaction.response.send_message(
                "Você já escolheu neste descanso — é uma por personagem.",
                ephemeral=True,
            )
            return

        minhas = await db.condicoes_de(self.bot.db, run_id, user_id)
        tipos = self.TIPOS_DE_LIMPEZA.get(chave)
        if tipos:
            candidatas = consequencias.a_limpar(minhas, tipos)
            if not candidatas:
                # Nao gasta a escolha: o botao existe por causa de outra pessoa.
                await interaction.response.send_message(
                    "Você não carrega nada dessa categoria — escolha outra.",
                    ephemeral=True,
                )
                return
            cid = candidatas[0]
            sobrou = await db.reduzir_condicao(self.bot.db, run_id, user_id, cid)
            resto = f" (ainda ×{sobrou})" if sobrou else ""
            publico = (
                f"o descanso tira {condicoes.rotulo(cid)} de "
                f"**{await self._nome_na_run(run, user_id)}**{resto}"
            )
            privado = f"O descanso tira {condicoes.rotulo(cid)} de você{resto}."
        else:
            publico = f"**{await self._nome_na_run(run, user_id)}** descansa sem limpar nada"
            privado = "Você segue sem limpar nada."

        await db.marcar_descanso(self.bot.db, run_id, passo, user_id)
        await interaction.response.send_message(privado, ephemeral=True)
        self._guardar_efemera(run_id, interaction)
        canal = await self._canal(run)
        if canal:
            await canal.send(f"🏕️ {publico}.")

        if await self._descanso_pendente(run):
            await self._atualizar_descanso(run, sala_id)
            return
        incursao = self._incursao_da_run(run)
        await self._concluir_sala(run, self._sala(incursao, sala_id), None)

    async def _atualizar_descanso(self, run: dict[str, Any], sala_id: str) -> None:
        """Reescreve o cartão do descanso com quem ainda falta escolher."""
        incursao = self._incursao_da_run(run)
        sala = self._sala(incursao, sala_id)
        atual = await db.buscar_run(self.bot.db, run["id"]) or run
        canal = await self._canal(atual)
        if not (canal and sala and atual.get("mensagem_id")):
            return
        disponiveis = await self._limpezas_disponiveis(atual)
        faltam = await self._descanso_pendente(atual)
        try:
            mensagem = await canal.fetch_message(atual["mensagem_id"])
            await mensagem.edit(
                embed=E.descanso(
                    sala,
                    await self._linhas_do_descanso(atual),
                    disponiveis,
                    faltam=len(faltam),
                ),
                view=ViewDescanso(self, run["id"], sala_id, disponiveis),
            )
        except discord.HTTPException:
            pass

    async def _linhas_do_descanso(self, run: dict[str, Any]) -> list[str]:
        """Uma linha por personagem do grupo, com o HP lido do banco agora.

        Do banco a cada desenho, e nao de uma lista guardada na abertura:
        limpar Exaustao ou Debilitacao devolve HP MAXIMO, entao o "50/60"
        da abertura vira "50/70" no meio do descanso. Lista guardada
        mostraria o numero velho.

        E o grupo INTEIRO, nao so quem mudou: quem le o cartao quer saber
        como o grupo vai entrar na proxima sala, e "nao apareci" nao
        responde isso.
        """
        feito = self._recuperacao.get(run["id"], {})
        linhas = []
        for c in await self._combatentes(run):
            r = feito.get(c.user_id)
            if r is not None and r.voltou:
                nota = f" — de pé outra vez (+{r.ganho})"
            elif r is not None and r.ganho:
                nota = f" — o descanso deu **{r.ganho}**"
            elif c.hp_atual >= c.hp_max:
                nota = " — inteiro"
            else:
                # Cheio de Debilitacao, ou a fracao arredondou para nada.
                nota = " — o descanso não rendeu nada"
            linhas.append(f"• **{c.nome}** {c.hp_atual}/{c.hp_max}{nota}")
        return linhas

    async def _nome_na_run(self, run: dict[str, Any], user_id: int) -> str:
        personagem = await db.personagem_da_run(self.bot.db, run["id"], user_id)
        return (personagem or {}).get("nome") or f"<@{user_id}>"

    async def _quem_rolou(
        self, run: dict[str, Any], registros: list[dict[str, Any]]
    ) -> tuple[list[str], list[str]]:
        """Quem ja rolou nesta sala e quem ainda falta, por nome de personagem.

        Quem caiu depois de rolar continua na primeira lista e sai da segunda:
        a sala fecha quando os de pe rolarem, e e essa a conta que o cartao
        mostra.
        """
        ja = {r["user_id"] for r in registros}
        nomes = {
            p["user_id"]: p["nome"]
            for p in await db.personagens_da_run(self.bot.db, run["id"])
        }
        faltam = [
            nomes.get(user_id, f"<@{user_id}>")
            for user_id in await db.participantes_de_pe(self.bot.db, run["id"])
            if user_id not in ja
        ]
        return [r["personagem"] for r in registros], faltam

    # ------------------------------------------- o que a sala deixa no grupo

    async def _consequencias_da_sala(
        self, run: dict[str, Any], sala: Sala, resolucao: ResolucaoSala
    ) -> consequencias.Desfecho:
        """Aplica o que a sala faz com o grupo e devolve o texto do embed.

        O que cada tipo faz está em `src/consequencias.py`; aqui só persiste.

        **A sala é do grupo, nos dois sentidos.** Vencida, não castiga
        ninguém — nem quem rolou mal. Perdida, castiga todos que a
        encararam — inclusive quem rolou bem. O dado de cada um decide o
        PROGRESSO da sala; o desfecho dela é do grupo.

        As duas metades vieram do mesmo relato da mesa: punir quem tirou 3
        numa sala que o grupo venceu, e deixar limpo quem tirou 18 numa sala
        que o grupo perdeu, apontavam o dado em vez da decisão.
        """
        desfecho = consequencias.Desfecho()
        if sala.tipo == "Armadilha" and resolucao.superada:
            desfecho.linhas.append(
                "O grupo desarma a armadilha — ninguém se machuca nela."
            )
        elif sala.tipo == "Armadilha" and resolucao.quem_falhou:
            await self._castigo_de_armadilha(run, sala, resolucao, desfecho)
        elif sala.tipo == "Evento":
            if resolucao.superada:
                await self._premio_de_evento(run, desfecho)
            elif resolucao.quem_falhou:
                await self._castigo_de_evento(run, resolucao, desfecho)
        elif sala.tipo == "Tesouro" and not resolucao.superada:
            # `acordou_mimico` hoje responde SEMPRE que sim, e a chamada fica
            # para a decisao continuar num lugar so: voltar a sortear e mexer
            # na CHANCE_DE_MIMICO, e nao reescrever esta sala.
            #
            # O sorteio saiu porque falhar num Tesouro era a unica falha do
            # caminho que podia nao custar nada: em dois terços das vezes o
            # grupo "saia sem nada, mas inteiro" — e sair sem nada nao e
            # castigo quando o tesouro so existia se voce passasse.
            if consequencias.acordou_mimico():
                desfecho.mimicos = True
                desfecho.linhas.append(
                    "O baú não era um baú. **Mímicos** se descolam da parede."
                )
            else:
                desfecho.linhas.append("O grupo sai sem nada — mas sai inteiro.")
        return desfecho

    @staticmethod
    def _quem_encarou(resolucao: ResolucaoSala) -> list[ResultadoTeste]:
        """Quem enfrentou a sala: todos que rolaram, passando ou falhando.

        Sala perdida cobra do GRUPO, e não de quem tirou o dado mais baixo.
        A outra metade da regra está em `_consequencias_da_sala`: sala
        vencida não cobra de ninguém. Vencer protege todos, perder custa a
        todos — e o resultado da sala deixa de depender de quem rolou mal.

        É quem ROLOU, e não quem está na run: uma sala só se perde quando
        todos os de pé rolaram (é a única forma de uma sala perdida fechar),
        e quem está caído não encarou nada. Cobrar de quem não pôde rolar
        seria cobrar duas vezes pela mesma queda.
        """
        return list(resolucao.resultados)

    async def _castigo_de_armadilha(
        self,
        run: dict[str, Any],
        sala: Sala,
        resolucao: ResolucaoSala,
        desfecho: consequencias.Desfecho,
    ) -> None:
        """A armadilha que o grupo não desarmou: -20% do HP e um debuff.

        Cai em todos que encararam a sala, e não só em quem falhou a própria
        rolagem — ver `_quem_encarou`.

        **Um sorteio só para o grupo inteiro**: é uma armadilha que
        disparou, não cinco. Cinco debuffs diferentes do mesmo alçapão não
        contariam a mesma história, e a linha do desfecho fica legível.

        O dano continua por cabeça, porque é porcentagem: 20% do máximo de
        cada um, e quem tem mais HP perde mais.
        """
        combatentes = {c.user_id: c for c in await self._combatentes(run)}
        encararam = self._quem_encarou(resolucao)
        if not encararam:
            return
        debuff = consequencias.debuff_da_armadilha()
        hps: dict[int, int] = {}
        nomes: list[str] = []
        caiu = consequencias.CondicaoAplicada(debuff)
        for quem in encararam:
            combatente = combatentes.get(quem.user_id)
            if combatente is None:
                continue
            dano = consequencias.dano_da_armadilha(combatente.hp_max)
            combatente.hp_atual = max(0, combatente.hp_atual - dano)
            hps[quem.user_id] = combatente.hp_atual
            caiu.stacks[quem.personagem] = await db.aplicar_condicao(
                self.bot.db, run["id"], quem.user_id, debuff
            )
            nomes.append(f"**{quem.personagem}** (-{dano})")
        if hps:
            await db.definir_hp_varios(self.bot.db, run["id"], hps)
        if nomes:
            desfecho.linhas.append(
                "A armadilha pega o grupo: " + ", ".join(nomes) + "."
            )
            desfecho.condicao = caiu

    async def _premio_de_evento(
        self, run: dict[str, Any], desfecho: consequencias.Desfecho
    ) -> None:
        """O Evento vencido dá uma coisa só: um buff, a Cura ou a Graça."""
        carregadas = await db.condicoes_da_run(self.bot.db, run["id"])
        combatentes = await self._combatentes(run)
        machucados = [c for c in combatentes if c.hp_atual < c.hp_max]
        sujos = consequencias.sortear_para_limpar(carregadas, (condicoes.DEBUFF,))
        premio = consequencias.premio_do_evento(
            tem_debuff=bool(sujos), tem_machucado=bool(machucados)
        )

        # Cura: +20% do HP máximo no personagem com menos vida do grupo.
        if premio == consequencias.CURA and machucados:
            alvo = min(machucados, key=lambda c: c.hp_atual)
            bruta = consequencias.cura_do_evento(alvo.hp_max)
            ganho = min(alvo.hp_max - alvo.hp_atual, motor.cura_liquida(alvo, bruta))
            alvo.hp_atual += ganho
            await db.definir_hp(self.bot.db, run["id"], alvo.user_id, alvo.hp_atual)
            desfecho.linhas.append(
                f"✨ **Cura**: **{alvo.nome}** recupera **{ganho}** de HP "
                f"({alvo.hp_atual}/{alvo.hp_max})."
            )
            return

        # Graça: tira um debuff de alguém do grupo, sorteado entre todos.
        if premio == consequencias.GRACA:
            escolhidos = consequencias.sortear_para_limpar(
                carregadas, (condicoes.DEBUFF,)
            )
            if escolhidos:
                partes = []
                for user_id, cid in escolhidos:
                    await db.reduzir_condicao(self.bot.db, run["id"], user_id, cid)
                    nome = next(
                        (c.nome for c in combatentes if c.user_id == user_id), "alguém"
                    )
                    partes.append(f"{condicoes.rotulo(cid)} de **{nome}**")
                desfecho.linhas.append(
                    f"✨ **{consequencias.NOME_DA_GRACA}** tira "
                    + ", ".join(partes)
                    + "."
                )
                return

        # Sobrou buff, que é o piso do Evento: vale para o grupo inteiro.
        if premio not in condicoes.BUFFS:
            premio = condicoes.BUFFS[0]
        ganho = consequencias.CondicaoAplicada(premio)
        for c in combatentes:
            ganho.stacks[c.nome] = await db.aplicar_condicao(
                self.bot.db, run["id"], c.user_id, premio
            )
        desfecho.linhas.append("✨ O evento corre bem, e o grupo sai melhor dele.")
        desfecho.condicao = ganho

    async def _castigo_de_evento(
        self,
        run: dict[str, Any],
        resolucao: ResolucaoSala,
        desfecho: consequencias.Desfecho,
    ) -> None:
        """O Evento que deu errado: um debuff de Evento, ou Exaustão.

        Cai em todos que encararam a sala, e num sorteio só: o Evento é um
        acontecimento da sala, e aconteceu para o grupo inteiro.
        """
        encararam = self._quem_encarou(resolucao)
        if not encararam:
            return
        castigo = consequencias.castigo_do_evento()
        unidades = consequencias.unidades_do_castigo(castigo)
        caiu = consequencias.CondicaoAplicada(castigo)
        for quem in encararam:
            caiu.stacks[quem.personagem] = await db.aplicar_condicao(
                self.bot.db, run["id"], quem.user_id, castigo, unidades
            )
        desfecho.linhas.append("O evento sai pela culatra para o grupo.")
        desfecho.condicao = caiu

    async def _expulsar_estourados(self, run: dict[str, Any]) -> None:
        """Quem bateu no teto de uma condição sai da incursão.

        O teto é por condição, como na planilha: Deterioração em 10 (que é
        -100% do HP máximo) e Exaustão em 5. As outras não tiram ninguém.
        Esvaziando o grupo, a run fracassa.
        """
        tier_atual = self._tier_da_run(run)
        carregadas = await db.condicoes_da_run(self.bot.db, run["id"])
        canal = await self._canal(run)
        saiu = False
        for user_id, condicoes_do_jogador in sorted(carregadas.items()):
            saldo = condicoes.penalidades(condicoes_do_jogador, tier_atual)
            if not saldo.fora:
                continue
            personagem = await db.personagem_da_run(self.bot.db, run["id"], user_id)
            nome = (personagem or {}).get("nome", f"<@{user_id}>")
            if not await db.remover_participante(self.bot.db, run["id"], user_id):
                continue
            saiu = True
            motivos = ", ".join(condicoes.POR_ID[c].nome for c in saldo.estourou)
            if canal:
                await canal.send(
                    f"<@{user_id}> — **{nome}** não consegue seguir: {motivos} chegou "
                    f"ao limite. O personagem sai da incursão."
                )
        if saiu and not await db.participantes(self.bot.db, run["id"]):
            # Sem ninguem de pe a run termina aqui. Nao ha combate, entao nao ha
            # estado para o embed de derrota: fecha com uma linha e os pontos de
            # participacao, que o grupo levou ate onde deu.
            await self._encerrar_run(run, "fracasso")
            await self._creditar(
                run, config.PONTOS_PARTICIPACAO, "Participação na incursão", "participacao"
            )
            if canal:
                await canal.send(
                    "A incursão termina aqui: não sobrou ninguém em condições de "
                    "seguir."
                )

    async def _soltar_mimicos(self, run: dict[str, Any], sala: Sala) -> None:
        """A falha no Tesouro acordou o baú: a sala vira um combate.

        Os números dos Mímicos ficam gravados em `run_inimigos` por
        `_abrir_combate`, então o combate se remonta sozinho depois de um
        restart — a emboscada não precisa existir no banco de salas.
        """
        emboscada = emboscada_de(sala, self._tier_da_run(run))
        if not emboscada.monstros:
            # Sem Mímico no bestiário não há emboscada: segue o fluxo normal.
            log.warning("Mímico não encontrado no bestiário; emboscada cancelada")
            incursao = self._incursao_da_run(run)
            passo = run["linha_atual"]
            if incursao and passo < incursao.paradas:
                await self._abrir_votacao(run, passo + 1)
            else:
                await self._chegar_ao_objetivo(run)
            return
        await self._abrir_combate(run, emboscada)

    async def _chegar_ao_objetivo(self, run: dict[str, Any]) -> None:
        incursao = self._incursao_da_run(run)
        canal = await self._canal(run)
        if not (incursao and canal):
            return

        # A ultima sala do caminho sai do canal quando o objetivo abre.
        await self._apagar_passo_anterior(run)
        await db.atualizar_run(
            self.bot.db,
            run["id"],
            status="objetivo",
            sala_atual=incursao.objetivo.id,
            votacao_expira_em=None,
        )
        await self._abrir_combate(
            await db.buscar_run(self.bot.db, run["id"]), incursao.objetivo
        )

    # ---------------------------------------------------------- comandos

    # Havia um `/incursao votar <1-3>` aqui, "para o caso de os botões
    # falharem". Saiu: a votação acontece nos botões do cartão da sala, e um
    # comando de reserva para a mesma coisa só aparecia na lista do /help
    # fazendo o jogador se perguntar qual dos dois é o certo. O `self.votar`
    # continua — é o que os botões chamam.

    @grupo.command(name="status", description="Estado atual da run neste canal")
    async def status(self, interaction: discord.Interaction) -> None:
        run = await self._run_do_contexto(interaction, exigir_participante=False)
        if not run:
            return
        incursao = self._incursao_da_run(run)
        sala = await self._sala_corrente(run)
        registros = (
            await db.testes_da_sala(self.bot.db, run["id"], self._passo(run)) if sala else []
        )
        await interaction.response.send_message(
            embed=E.status(
                run,
                incursao,
                await self._membros(run),
                sala,
                len(registros),
                await db.condicoes_da_run(self.bot.db, run["id"]),
                # Nomes de PERSONAGEM: o campo fala do que cada ficha carrega.
                await self._nomes(run),
            )
        )

    @grupo.command(name="desistir", description="Propõe abandonar a incursão (precisa de maioria)")
    async def desistir(self, interaction: discord.Interaction) -> None:
        run = await self._run_do_contexto(interaction)
        if not run:
            return
        # A desistencia reusa a tabela de votos com linha = -1.
        await db.registrar_voto(self.bot.db, run["id"], -1, interaction.user.id, "desistir")
        votos = await db.votos_da_linha(self.bot.db, run["id"], -1)
        total = len(await db.participantes(self.bot.db, run["id"]))
        necessarios = maioria_de(total)

        if len(votos) >= necessarios:
            # A sala onde o grupo parou, LIDA ANTES de encerrar: o encerramento
            # tira os botoes e nao quero depender da ordem para saber onde foi.
            onde = await self._sala_corrente(run)
            passo = self._passo(run)
            await self._encerrar_run(run, "desistiu")
            # As salas vencidas pagam; o fecho, nao. O grupo atravessou o que
            # atravessou — o que ele nao fez foi terminar.
            await self._pagar_as_salas(run)
            incursao = self._incursao_da_run(run)
            await interaction.response.send_message(
                f"A run #{run['id']} foi abandonada por decisão do grupo "
                f"({len(votos)}/{total})."
            )
            canal = await self._canal(run)
            if not (canal and incursao):
                return
            lancamentos, total_org = await self._balanco(run)
            await canal.send(
                embed=E.run_desistida(
                    incursao,
                    onde=onde,
                    passo=passo,
                    lancamentos=lancamentos,
                    total_org=total_org,
                    caminho=await self._caminho(run),
                    ouro=await db.ouro_da_run(self.bot.db, run["id"]),
                    perdido=mercado.ouro_da_incursao(self._tier_da_run(run) or 1),
                )
            )
            return

        await interaction.response.send_message(
            f"{interaction.user.display_name} quer desistir "
            f"({len(votos)}/{necessarios} necessários). Quem concordar, use `/incursao desistir`."
        )

    # ------------------------------- agir no lugar de quem nao agiu

    async def _de_quem_e_a_vez(self, run, estado) -> Optional[int]:
        """O jogador que a fila está esperando, ou None.

        É a mesma leitura que `_avancar` faz para parar: `ordem[vez]`, quando o
        ator é um personagem de pé, não atordoado, não invocado, e sem ação
        escolhida nesta rodada. Fora disso ninguém está sendo esperado — a
        criatura age sozinha, e quem está caído perde a vez sozinho.
        """
        passo = self._passo(run)
        ordem = await self._garantir_iniciativa(run, estado)
        combate = await db.estado_combate(self.bot.db, run["id"], passo)
        vez = (combate or {}).get("vez", 0)
        if vez >= len(ordem):
            return None
        ator = ordem[vez]
        if ator["tipo"] != motor.PERSONAGEM:
            return None
        user_id = ator["alvo_id"]
        quem = estado.combatente(user_id)
        if quem is None or quem.caido or quem.atordoado or quem.e_invocacao:
            return None
        if await db.acao_do_turno(
            self.bot.db, run["id"], passo, estado.rodada, user_id
        ):
            return None
        return user_id

    @staticmethod
    def _nome_no_combate(estado, user_id: int) -> str:
        quem = estado.combatente(user_id)
        return quem.nome if quem is not None else f"<@{user_id}>"

    @staticmethod
    def _habilidades_substituiveis(personagem) -> list:
        """As habilidades que o grupo pode usar pelo ausente.

        **Poção não entra**, e é decisão de regra, não de implementação: ela
        foi comprada com o ouro daquele personagem e sai da bolsa dele para
        nunca voltar. Uso de habilidade volta no descanso.

        So entram ativas de turno: reacoes disparam pelo proprio gatilho.
        Quem confere se ainda ha uso e `gastar_uso`, na hora de resolver,
        porque entre propor e resolver passa uma votacao.
        """
        return [
            habilidade
            for _tier, habilidade in (personagem or {}).get("habilidades") or []
            if habilidade.acionavel and (habilidade.acao or {}).get("tipo") != "reacao"
        ]

    async def _contexto_da_substituicao(self, run):
        """(estado, sala, de quem é a vez) do combate aberto, ou None."""
        # `_sala_corrente`, e nao `_sala`: ela acha tambem a emboscada de
        # Mimicos, que nao existe no banco de salas e e combate como qualquer
        # outro — travar nela travaria igual.
        sala = await self._sala_corrente(run)
        if sala is None or not sala.e_combate:
            return None
        estado = await self._estado_combate(run, sala)
        if estado is None or estado.encerrado:
            return None
        return estado, sala, await self._de_quem_e_a_vez(run, estado)

    @grupo.command(
        name="substituir",
        description="Age no lugar de quem travou o combate (precisa da maioria dos outros)",
    )
    @app_commands.describe(
        jogador="Quem está com a vez e não agiu",
        acao="O que ele faz: atacar, ou uma habilidade dele. Padrão: atacar",
        alvo="Em quem. Padrão: o que o combate escolheria sozinho",
    )
    async def substituir(
        self,
        interaction: discord.Interaction,
        jogador: discord.Member,
        acao: Optional[str] = None,
        alvo: Optional[str] = None,
    ) -> None:
        """Propõe — e concorda com — agir no lugar de quem não age.

        **O comando É o voto**, como no `/incursao desistir`: quem chama
        primeiro abre a proposta e já concorda com ela, e os outros chamam de
        novo, só com o `jogador`, para concordar. A maioria dos outros fecha.

        "Os outros" é o grupo de pé menos o ausente: ele não vota sobre a
        própria vez. E ele pode agir pelo painel enquanto a votação corre — o
        clique dele cancela a proposta, porque quem voltou voltou ao controle.
        """
        run = await self._run_do_contexto(interaction)
        if not run:
            return
        contexto = await self._contexto_da_substituicao(run)
        if contexto is None:
            await interaction.response.send_message(
                "Isto só vale num combate aberto.", ephemeral=True
            )
            return
        estado, sala, esperado = contexto
        passo = self._passo(run)
        de_pe = await db.participantes_de_pe(self.bot.db, run["id"])

        if interaction.user.id not in de_pe:
            await interaction.response.send_message(
                "Só quem está de pé no combate decide isso.", ephemeral=True
            )
            return
        if jogador.id == interaction.user.id:
            await interaction.response.send_message(
                "Para agir por você mesmo, use os botões do painel.", ephemeral=True
            )
            return
        if esperado is None or esperado != jogador.id:
            quem = (
                f"**{self._nome_no_combate(estado, esperado)}**"
                if esperado is not None
                else "ninguém"
            )
            await interaction.response.send_message(
                f"A vez não está travada em {jogador.display_name}: o combate "
                f"está esperando {quem}.",
                ephemeral=True,
            )
            return

        # O relogio: 15 minutos na primeira ausencia, e nenhum enquanto ela
        # continuar. Ver `motor.pode_propor_substituicao`.
        desde = await db.vez_aberta_desde(self.bot.db, run["id"], passo)
        agora = datetime.now(config.FUSO)
        ja = await db.turno_foi_substituido(self.bot.db, run["id"], passo, jogador.id)
        if desde is not None and not motor.pode_propor_substituicao(desde, agora, ja):
            falta = motor.falta_para_substituir(desde, agora)
            await interaction.response.send_message(
                f"A vez de **{jogador.display_name}** abriu agora há pouco. "
                f"Faltam **{int(falta.total_seconds() // 60) + 1} min** para o "
                f"grupo poder agir no lugar dele.",
                ephemeral=True,
            )
            return

        aberta = await db.substituicao_aberta(
            self.bot.db, run["id"], passo, estado.rodada, jogador.id
        )
        if aberta is None:
            escolhido, aviso = await self._acao_proposta(
                run, estado, jogador.id, acao, alvo
            )
            if escolhido is None:
                await interaction.response.send_message(aviso, ephemeral=True)
                return
            if not await db.abrir_substituicao(
                self.bot.db, run["id"], passo, estado.rodada, jogador.id,
                escolhido[0], escolhido[1], interaction.user.id,
            ):
                await interaction.response.send_message(
                    "Alguém propôs no mesmo instante. Chame de novo para concordar "
                    "com a proposta que está na mesa.",
                    ephemeral=True,
                )
                return
            aberta = await db.substituicao_aberta(
                self.bot.db, run["id"], passo, estado.rodada, jogador.id
            )

        await db.apoiar_substituicao(
            self.bot.db, run["id"], passo, estado.rodada, jogador.id,
            interaction.user.id, True,
        )
        apoios = await db.apoios_da_substituicao(
            self.bot.db, run["id"], passo, estado.rodada, jogador.id
        )
        # So quem esta de pe conta: quem caiu depois de concordar nao decide
        # mais a vez de ninguem.
        de_acordo = [u for u, sim in apoios.items() if sim and u in de_pe]
        necessarios = motor.maioria_dos_outros(len(de_pe))
        nome = self._nome_no_combate(estado, jogador.id)
        descricao = await self._texto_da_acao(run, estado, jogador.id, aberta)

        if len(de_acordo) < necessarios:
            await interaction.response.send_message(
                f"⏳ O grupo quer agir no lugar de **{nome}**: {descricao}.\n"
                f"**{len(de_acordo)}/{necessarios}** de acordo. Quem concordar, "
                f"use `/incursao substituir jogador:{jogador.display_name}`.\n"
                f"-# {nome} ainda pode agir pelo painel, e o clique dele cancela isto."
            )
            return

        # A maioria fechou. A reivindicacao decide quem resolve: dois acordos
        # no mesmo instante fechariam a mesma proposta duas vezes, e a vez do
        # ausente seria gasta duas vezes.
        if not await db.tomar_a_substituicao(
            self.bot.db, run["id"], passo, estado.rodada, jogador.id
        ):
            await interaction.response.send_message(
                "Esta proposta já foi resolvida.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            f"✅ O grupo age no lugar de **{nome}** ({len(de_acordo)}/{necessarios}): "
            f"{descricao}."
        )
        await self._resolver_substituicao(run, sala, estado, jogador.id, aberta)

    async def _resolver_substituicao(self, run, sala, estado, alvo_id: int, proposta):
        """Grava a ação como a vez do ausente e deixa a iniciativa andar."""
        passo = self._passo(run)
        habilidade = None
        if proposta["acao"] != "ataque":
            personagem = await self._personagem_na_run(run, alvo_id)
            habilidade = next(
                (
                    h for h in self._habilidades_substituiveis(personagem)
                    if h.id == proposta["acao"]
                ),
                None,
            )
            if habilidade is not None:
                aviso = await self._aviso_de_requisito(run, estado, alvo_id, habilidade)
                if aviso:
                    canal = await self._canal(run)
                    if canal:
                        await canal.send(aviso + " A vez continua aberta.")
                    return
            # O uso e gasto AQUI, e nao ao propor: entre propor e resolver passa
            # uma votacao, e proposta recusada nao pode custar o uso de ninguem.
            # Se ele acabou nesse meio-tempo, o grupo e avisado e a vez continua
            # aberta — mudar a acao por conta propria seria resolver outra coisa
            # que ninguem votou.
            if habilidade is None or not await db.gastar_uso(
                self.bot.db, run["id"], alvo_id, habilidade.chave_de_uso,
                self._chave_de_recarga(habilidade, run, passo), habilidade.vezes,
            ):
                canal = await self._canal(run)
                if canal:
                    await canal.send(
                        "A habilidade escolhida já não tem uso. A vez continua "
                        "aberta: o grupo pode propor outra coisa."
                    )
                return
        if not await db.marcar_turno(
            self.bot.db, run["id"], passo, estado.rodada, alvo_id,
            proposta["acao"], alvos=proposta["alvos"], resolvida=False,
            substituto=proposta["proposto_por"],
        ):
            # Ele agiu no intervalo: a acao dele vale, e a do grupo nao.
            if habilidade is not None:
                await db.devolver_uso(
                    self.bot.db, run["id"], alvo_id, habilidade.chave_de_uso,
                    self._chave_de_recarga(habilidade, run, passo),
                )
            return
        await self._avancar(run, sala)

    async def _acao_proposta(self, run, estado, alvo_id: int, acao, alvo):
        """Valida o par (ação, alvo) proposto. Devolve ((ação, alvos), aviso)."""
        personagem = await self._personagem_na_run(run, alvo_id)
        if acao in (None, "", "ataque"):
            alvos: list[int] = []
            if alvo:
                indices = {str(i.indice) for i in estado.inimigos_vivos}
                if alvo not in indices:
                    return None, "Esse alvo não está de pé no combate."
                alvos = [int(alvo)]
            return ("ataque", alvos), ""
        habilidade = next(
            (h for h in self._habilidades_substituiveis(personagem) if h.id == acao),
            None,
        )
        if habilidade is None:
            return None, (
                f"`{acao}` não é uma ação que o grupo possa usar por ele. "
                f"Poção não entra: ela é do ouro dele."
            )
        aviso = await self._aviso_de_requisito(run, estado, alvo_id, habilidade)
        if aviso:
            return None, aviso
        opcoes = await self._alvos_possiveis(run, habilidade, estado)
        if opcoes is None:
            return (habilidade.id, []), ""
        if not opcoes:
            return None, "Não há alvo possível para essa habilidade agora."
        validos = {valor for valor, _n, _d in opcoes}
        if alvo is None:
            return None, (
                f"**{habilidade.nome}** precisa de alvo: escolha um no campo `alvo`."
            )
        if alvo not in validos:
            return None, "Esse alvo não serve para essa habilidade."
        return (habilidade.id, [int(alvo)]), ""

    async def _texto_da_acao(self, run, estado, alvo_id: int, proposta) -> str:
        """A proposta em uma linha, para o grupo saber no que está votando."""
        if proposta["acao"] == "ataque":
            if proposta["alvos"]:
                inimigo = estado.inimigo(proposta["alvos"][0])
                return f"atacar **{inimigo.nome if inimigo else 'o alvo'}**"
            return "atacar"
        personagem = await self._personagem_na_run(run, alvo_id)
        habilidade = next(
            (
                h for h in self._habilidades_substituiveis(personagem)
                if h.id == proposta["acao"]
            ),
            None,
        )
        return f"usar **{habilidade.nome if habilidade else proposta['acao']}**"

    @substituir.autocomplete("acao")
    async def _acoes_do_ausente(self, interaction: discord.Interaction, atual: str):
        """Atacar, mais as habilidades do ausente. Poção não entra."""
        opcoes = [app_commands.Choice(name="Atacar", value="ataque")]
        run = await db.run_do_canal(self.bot.db, interaction.channel_id)
        alvo_id = _id_digitado(interaction, "jogador")
        if run and alvo_id:
            personagem = await self._personagem_na_run(run, alvo_id)
            for habilidade in self._habilidades_substituiveis(personagem):
                opcoes.append(
                    app_commands.Choice(name=habilidade.nome, value=habilidade.id)
                )
        procura = (atual or "").lower()
        return [o for o in opcoes if procura in o.name.lower()][:25]

    @substituir.autocomplete("alvo")
    async def _alvos_do_ausente(self, interaction: discord.Interaction, atual: str):
        """Os mesmos alvos que o ausente teria para a ação escolhida."""
        run = await db.run_do_canal(self.bot.db, interaction.channel_id)
        if not run:
            return []
        contexto = await self._contexto_da_substituicao(run)
        if contexto is None:
            return []
        estado, _sala, _esperado = contexto
        escolhida = _texto_digitado(interaction, "acao") or "ataque"
        alvo_id = _id_digitado(interaction, "jogador")
        if escolhida in ("", "ataque"):
            opcoes = [
                (str(i.indice), i.nome, motor.barra(i.hp_atual, i.hp_max, 8))
                for i in estado.inimigos_vivos
            ]
        else:
            personagem = await self._personagem_na_run(run, alvo_id) if alvo_id else None
            habilidade = next(
                (
                    h for h in self._habilidades_substituiveis(personagem)
                    if h.id == escolhida
                ),
                None,
            )
            if habilidade is None:
                return []
            opcoes = await self._alvos_possiveis(run, habilidade, estado) or []
        procura = (atual or "").lower()
        return [
            app_commands.Choice(name=f"{nome} · {detalhe}", value=valor)
            for valor, nome, detalhe in opcoes
            if procura in nome.lower()
        ][:25]

    @grupo.command(
        name="encerrar",
        description="(admin) Encerra a incursão deste canal, pagando ou não as salas",
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(
        pagar="Sim: o grupo leva o ouro das salas vencidas e os pontos de participação",
        devolver_vaga="Sim: a semana não é cobrada, e o grupo pode entrar em outra",
    )
    async def encerrar(
        self, interaction: discord.Interaction, pagar: bool, devolver_vaga: bool
    ) -> None:
        """Encerra a run do canal sem votação, e decide o que ela deixa.

        O `/incursao desistir` é do grupo e precisa de maioria. Este é para
        quando não há grupo para votar: a sessão morreu, a run ficou presa, ou
        ela foi aberta por engano.

        **Os dois parâmetros são obrigatórios de propósito.** A ação não tem
        volta, e cada um deles move ouro ou a semana de cinco pessoas: um
        padrão silencioso decidiria isso no lugar de quem administra. É a
        mesma razão por que o comando não aceita id de run — ele age no canal
        onde a run está, que é onde o grupo vai ler o desfecho.
        """
        # Sem exigir participante: quem administra encerra a run do canal mesmo
        # sem estar nela, que e justamente o caso de limpar uma run presa.
        run = await self._run_do_contexto(interaction, exigir_participante=False)
        if not run:
            return

        # Lidos ANTES de encerrar: o encerramento tira os botoes e muda o
        # status, e o cartao fala de onde o grupo PAROU.
        onde = await self._sala_corrente(run)
        passo = self._passo(run)
        incursao = self._incursao_da_run(run)
        caminho = await self._caminho(run)
        quem_passou = [
            p["user_id"] for p in await db.quem_recebe_da_run(self.bot.db, run["id"])
        ]

        await self._encerrar_run(run, "encerrada")
        if pagar:
            await self._pagar_as_salas(run)
            await self._creditar(
                run, config.PONTOS_PARTICIPACAO,
                "Participação na incursão", "participacao",
            )
        devolvidas = 0
        if devolver_vaga:
            devolvidas = await db.devolver_a_vaga(
                self.bot.db, run["guild_id"], quem_passou
            )

        await interaction.response.send_message(
            f"Run #{run['id']} encerrada. "
            + ("As salas vencidas pagaram. " if pagar else "Nada foi pago. ")
            + (
                f"A vaga da semana voltou para {devolvidas} jogador(es)."
                if devolver_vaga
                else "A vaga da semana segue gasta."
            ),
            ephemeral=True,
        )
        canal = await self._canal(run)
        if not (canal and incursao):
            return
        lancamentos, total_org = await self._balanco(run)
        await canal.send(
            embed=E.run_encerrada(
                incursao,
                onde=onde,
                passo=passo,
                lancamentos=lancamentos,
                total_org=total_org,
                caminho=caminho,
                ouro=await db.ouro_da_run(self.bot.db, run["id"]),
                pagou=pagar,
                vaga_devolvida=devolver_vaga,
            )
        )

    @grupo.command(name="recarregar", description="(admin) Relê as incursões do disco")
    @app_commands.default_permissions(manage_guild=True)
    async def recarregar(self, interaction: discord.Interaction) -> None:
        try:
            problemas = self.recarregar_incursoes()
        except Exception as exc:  # JSON invalido nao pode derrubar o bot
            await interaction.response.send_message(f"Falhou: {exc}", ephemeral=True)
            return
        linhas = [
            f"{len(self.incursoes)} incursão(ões) e {len(self.bancos)} banco(s) de salas: "
            f"{', '.join(self.incursoes) or 'nenhuma'}."
        ]
        if problemas:
            # O arquivo ruim nao derruba mais o carregamento, entao ele PRECISA
            # aparecer aqui: tolerancia silenciosa e conteudo sumindo sem aviso.
            linhas.append(
                f"\n**{len(problemas)} arquivo(s) ficaram de fora.** O resto carregou:"
            )
            linhas.extend(f"- {p}" for p in problemas[:10])
            if len(problemas) > 10:
                linhas.append(f"- …e mais {len(problemas) - 10}.")
        await interaction.response.send_message(
            "\n".join(linhas)[:1900], ephemeral=True
        )

    config_grupo = app_commands.Group(
        name="config", description="Ajustes do bot (admin)", default_permissions=discord.Permissions(manage_guild=True)
    )

    @config_grupo.command(
        name="intervalo",
        description="Semanas entre incursões do mesmo jogador (a semana vira na segunda)",
    )
    async def config_intervalo(
        self, interaction: discord.Interaction, semanas: app_commands.Range[int, 0, 52]
    ) -> None:
        await db.definir_intervalo(self.bot.db, interaction.guild_id, semanas)
        if semanas == 0:
            texto = "Intervalo desligado: cada jogador pode entrar quantas vezes quiser."
        else:
            texto = (
                f"Intervalo ajustado para **{semanas} semana(s)**, contadas da "
                "segunda-feira: quem entrar no sábado joga de novo na segunda."
            )
        await interaction.response.send_message(texto, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Incursoes(bot))
