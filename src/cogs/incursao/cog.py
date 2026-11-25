"""O cog das incursões: os comandos de `/incursao`, e o bot subindo.

A run é assíncrona: o estado vive no banco, não na memória, para que o grupo
possa avançar ao longo de dias e o bot possa reiniciar sem perder nada.

Este arquivo é a classe que o bot carrega e os comandos dela — que ficam
juntos porque é assim que o Discord monta o grupo `/incursao`. O resto mora
nos vizinhos, um assunto por arquivo: `recrutamento`, `votacao`, `salas`,
`descanso`, `tela_do_combate`, `substituicao`, `canal` e `views`. As regras do
combate estão em `src/combate`. O cog herda tudo isso, e por isso cada método
continua respondendo pelo nome de antes.
"""
from __future__ import annotations

import asyncio
import json
import logging

from datetime import datetime
from typing import Any, Optional

import discord
from discord import app_commands
from discord.ext import commands

from ... import (
    bestiario,
    config,
    database as db,
    embeds as E,
    envios,
    incursoes,
    mercado,
    motor,
)
from ...combate import Combate
from ...incursoes import (
    arquivo_da_organizacao,
    carregar_bancos_tolerante,
    carregar_todas_tolerante,
    conferir_filtro,
)
from ...rules import tier, TIER_MAXIMO
from ..ficha import sugerir_personagens
from .canal import Canal
from .descanso import Descanso
from .recrutamento import Recrutamento
from .salas import Salas
from .substituicao import Substituicao
from .tela_do_combate import TelaDoCombate
from .views import (
    ViewCombate,
    ViewDescanso,
    ViewRecrutamento,
    ViewSala,
    ViewTrocaDoDescanso,
    ViewVotacao,
)
from .votacao import maioria_de, Votacao

log = logging.getLogger("incursoes.run")

# O arquivo do Estúdio tem poucos KB; isto é folga larga, e o teto existe para
# um anexo errado (uma imagem, um banco inteiro) não ser lido para a memória.
LIMITE_DO_ENVIO = 512 * 1024


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


class Incursoes(
    Canal, Recrutamento, Votacao, Salas, Descanso, TelaDoCombate, Substituicao,
    Combate, commands.Cog,
):
    def __init__(self, bot: commands.Bot):
        # O estado do combate — o bot, as incursões, a fila, o log — é da mesa.
        Combate.__init__(self, bot)
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
        # A retomada dos combates decididos, guardada para o loop nao a soltar.
        self._retomada: Optional[asyncio.Task] = None
        # O que chegou pelo `/incursao enviar`, e o catalogo de `data/` antes
        # de juntar os dois: o envio confere contra o repositorio puro (que e
        # intocavel) e contra o que ja foi enviado (que tem dono).
        self.enviados: list[envios.Enviado] = []
        self.repositorio_incursoes: dict[str, Any] = {}
        self.repositorio_bancos: dict[str, Any] = {}
        # Um envio por vez. Transacao nao isolaria: o bot usa uma conexao so,
        # e dois envios do mesmo autor juntos (o clique duplo) confeririam os
        # dois contra o bot de antes do outro.
        self._fila_de_envio = asyncio.Lock()

    async def cog_load(self) -> None:
        self.enviados = await self._ler_enviados()
        self._carregar_tolerante()
        await self.restaurar_views()
        # Numa tarefa, e so depois de conectar: o `cog_load` roda dentro do
        # `setup_hook`, antes do gateway, e fechar um combate manda mensagem e
        # abre a parada seguinte. Esperar aqui atrasaria a subida do bot.
        self._retomada = asyncio.create_task(self._retomar_quando_pronto())

    async def cog_unload(self) -> None:
        # Descarregar no meio da espera — o teste de fumaça carrega e
        # descarrega os cogs num bot que nunca conecta — cancela a retomada em
        # vez de deixá-la órfã.
        if self._retomada is not None:
            self._retomada.cancel()

    async def _retomar_quando_pronto(self) -> None:
        try:
            await self.bot.wait_until_ready()
        except RuntimeError:
            # So acontece num bot que nao fez login — o teste de fumaca, que
            # carrega os cogs sem conectar. Nao ha Discord onde retomar nada.
            return
        try:
            retomadas = await self.retomar_combates_decididos()
        except Exception:
            # Numa tarefa solta, a exceção sairia só como "Task exception was
            # never retrieved", sem dizer de onde. O bot segue de pé.
            log.exception("a retomada dos combates decididos falhou na subida")
            return
        if retomadas:
            log.warning(
                "combate decidido e run parada, retomados na subida: run(s) %s",
                ", ".join(map(str, retomadas)),
            )

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
        # O repositorio puro, guardado antes de juntar o que veio pelo
        # Discord: e contra ele que o proximo envio confere.
        self.repositorio_incursoes = dict(self.incursoes)
        self.repositorio_bancos = dict(self.bancos)
        self.incursoes, self.bancos, dos_envios = envios.mesclar(
            self.repositorio_incursoes, self.repositorio_bancos, self.enviados
        )
        problemas.extend(dos_envios)
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

    async def _ler_enviados(self) -> list[envios.Enviado]:
        """O que chegou pelo Discord, como esta no banco de dados.

        Linha que nao le (JSON quebrado a mao, por exemplo) fica de fora com
        log: ela nao pode impedir o bot de subir, como o arquivo ruim de
        `data/` tambem nao impede.
        """
        lidos = []
        for linha in await db.conteudo_enviado(self.bot.db):
            try:
                dados = json.loads(linha["dados"])
            except (TypeError, ValueError):
                log.error("conteúdo enviado %s ilegível no banco — ficou de fora",
                          linha["conteudo_id"])
                continue
            lidos.append(envios.Enviado(
                linha["tipo"], linha["organizacao"], linha["conteudo_id"],
                linha["autor_id"], dados,
            ))
        return lidos

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
            # A Ultima Vigilia tambem espera em 'escolhendo', mas a mesa dela
            # NAO esta em `run_mapa`: as trocas saem da semente `run:parada`
            # (`_trocas_da_parada`). Procurando so no mapa, este ramo devolvia
            # None para ela — depois de um restart o cartao ficava no canal
            # com tres botoes mortos, e a run sem saida.
            if incursao.descanso_da_parada(run["linha_atual"]) == incursoes.DESCANSO_DURO:
                trocas = self._trocas_da_parada(run["id"], run["linha_atual"])
                return (
                    ViewTrocaDoDescanso(self, run["id"], run["linha_atual"], trocas)
                    if trocas
                    else None
                )
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

        view = ViewRecrutamento(self, run_id)
        # O grupo, aqui, e so quem abriu — e ele ja vem na interacao. Montar a
        # lista por `_membros` ia a rede buscar esse mesmo membro (sem o intent
        # de membros o cache vem vazio), antes da primeira resposta, que tem 3 s.
        await interaction.response.send_message(
            embed=E.recrutamento(incursao, [interaction.user], interaction.user),
            view=view,
        )
        mensagem = await interaction.original_response()
        await db.atualizar_run(self.bot.db, run_id, mensagem_id=mensagem.id)

    # ------------------------------------------------------------ votação

    # -------------------------------------------------------------- salas

    # ------------------------------------------------------ habilidades

    # ------------------------------------------------------------ descanso

    # ------------------------------------------- o que a sala deixa no grupo

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
        # Adiado DEPOIS de achar a run, para a recusa de cima continuar
        # privada. Daqui em diante `_membros` vai a rede uma vez por jogador
        # (sem o intent de membros o cache vem vazio): cinco idas ao Discord
        # antes da primeira resposta, que tem 3 s.
        await interaction.response.defer(thinking=True)
        incursao = self._incursao_da_run(run)
        sala = await self._sala_corrente(run)
        registros = (
            await db.testes_da_sala(self.bot.db, run["id"], self._passo(run)) if sala else []
        )
        await interaction.edit_original_response(
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

    @grupo.command(
        name="buffs",
        description="O que cada emoji que o grupo carrega agora quer dizer",
    )
    async def buffs(self, interaction: discord.Interaction) -> None:
        """A legenda do que está aceso, e não o catálogo inteiro.

        A pergunta que ele responde nasce de olhar o painel: aparece um
        símbolo na linha de alguém e ninguém sabe o que ele cobra. Um catálogo
        de treze condições mais as marcas de combate não responde isso — manda
        o jogador procurar. Então entra só o que está na tela agora.

        Público, como o `/incursao status`: a dúvida é do grupo, e a resposta
        em privado faria o próximo perguntar de novo.
        """
        run = await self._run_do_contexto(interaction, exigir_participante=False)
        if not run:
            return
        # Adiado depois de achar a run, como o `status`: montar o estado do
        # combate e o trabalho mais pesado de leitura do bot.
        await interaction.response.defer(thinking=True)
        sala = await self._sala_corrente(run)
        estado = (
            await self._estado_combate(run, sala)
            if sala is not None and sala.e_combate
            else None
        )
        await interaction.edit_original_response(
            embed=E.buffs(
                await db.condicoes_da_run(self.bot.db, run["id"]),
                # Nomes de PERSONAGEM: a legenda fala do que cada ficha tem.
                await self._nomes(run),
                estado,
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
            # Adiado so no voto que FECHA: encerrar vai a rede (achar a
            # mensagem do passo e tirar os botoes dela) antes da resposta. O
            # voto que so conta e banco puro, e responde na hora como sempre.
            await interaction.response.defer(thinking=True)
            # A sala onde o grupo parou, LIDA ANTES de encerrar: o encerramento
            # tira os botoes e nao quero depender da ordem para saber onde foi.
            onde = await self._sala_corrente(run)
            passo = self._passo(run)
            await self._encerrar_run(run, "desistiu")
            # As salas vencidas pagam; o fecho, nao. O grupo atravessou o que
            # atravessou — o que ele nao fez foi terminar.
            await self._pagar_as_salas(run)
            incursao = self._incursao_da_run(run)
            await interaction.edit_original_response(
                content=(
                    f"A run #{run['id']} foi abandonada por decisão do grupo "
                    f"({len(votos)}/{total})."
                )
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
        # Adiado antes de encerrar: o encerramento vai a rede (a mensagem do
        # passo perde os botoes) antes de a resposta sair, e o Discord da 3 s.
        await interaction.response.defer(ephemeral=True, thinking=True)

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

        await self._dizer(
            interaction,
            f"Run #{run['id']} encerrada. "
            + ("As salas vencidas pagaram. " if pagar else "Nada foi pago. ")
            + (
                f"A vaga da semana voltou para {devolvidas} jogador(es)."
                if devolver_vaga
                else "A vaga da semana segue gasta."
            ),
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

    @grupo.command(
        name="enviar",
        description="Publica uma dungeon ou salas feitas no Estúdio de Incursões",
    )
    @app_commands.describe(arquivo="O arquivo .json que o Estúdio baixou")
    async def enviar(
        self, interaction: discord.Interaction, arquivo: discord.Attachment
    ) -> None:
        """O autor publica sem passar por ninguém: conferiu, está no ar.

        Vale em todos os servidores do bot. As regras de quem mexe em quê
        estão em `src/envios.py`; aqui fica o que é do Discord — quem pode
        usar, ler o anexo, gravar e responder.
        """
        await interaction.response.defer(ephemeral=True, thinking=True)
        if interaction.guild_id is None:
            await interaction.edit_original_response(
                content="Envie num servidor, no canal que quiser.")
            return
        if not await self._pode_enviar(interaction):
            await interaction.edit_original_response(content=(
                "Só quem tem o cargo de autores, ou administra o servidor, publica "
                "dungeons. Quem administra escolhe o cargo com `/config autores`."
            ))
            return
        if arquivo.size > LIMITE_DO_ENVIO:
            await interaction.edit_original_response(content=(
                f"O arquivo tem {arquivo.size // 1024} KB, e o do Estúdio tem poucos. "
                "Confira se anexou o .json que o Estúdio baixou."
            ))
            return
        try:
            dados = json.loads(await arquivo.read())
        except (UnicodeDecodeError, ValueError):
            await interaction.edit_original_response(content=(
                "Não consegui ler o anexo como JSON. Anexe o arquivo .json que o "
                "Estúdio baixou, sem abrir e salvar em outro programa."
            ))
            return

        async with self._fila_de_envio:
            dungeons, salas = await db.em_uso_pelas_runs(self.bot.db)
            em_uso = envios.EmUso(
                incursoes=frozenset(dungeons),
                salas=frozenset(
                    (self.incursoes[d].organizacao, s)
                    for d, s in salas if d in self.incursoes
                ),
            )
            plano = envios.planejar(
                dados,
                autor_id=interaction.user.id,
                incursoes_do_repositorio=set(self.repositorio_incursoes),
                bancos_do_repositorio=self.repositorio_bancos,
                enviados=self.enviados,
                em_uso=em_uso,
            )
            if plano.aprovado and plano.gravar:
                await db.gravar_conteudo_enviado(self.bot.db, interaction.guild_id, [
                    (e.tipo, e.organizacao, e.id, e.autor_id,
                     json.dumps(e.dados, ensure_ascii=False))
                    for e in plano.gravar
                ])
                self.enviados = await self._ler_enviados()
                self.recarregar_incursoes()
        await interaction.edit_original_response(content=self._resposta_do_envio(plano))

    async def _pode_enviar(self, interaction: discord.Interaction) -> bool:
        permissoes = getattr(interaction.user, "guild_permissions", None)
        if permissoes is not None and permissoes.manage_guild:
            return True
        cargo = await db.cargo_de_autor(self.bot.db, interaction.guild_id)
        return cargo is not None and any(
            r.id == cargo for r in getattr(interaction.user, "roles", ())
        )

    @staticmethod
    def _resposta_do_envio(plano: envios.Plano) -> str:
        """O que o autor lê: o que entrou, ou por que não entrou.

        Recusado, o bot diz TODOS os problemas de uma vez, nas palavras do
        Estúdio — o autor corrige tudo numa ida só, e não um por envio.
        """
        def lista(itens: list[str], limite: int = 12) -> list[str]:
            linhas = [f"- {i}" for i in itens[:limite]]
            if len(itens) > limite:
                linhas.append(f"- …e mais {len(itens) - limite}.")
            return linhas

        if not plano.aprovado:
            linhas = ["**Não publiquei.** O que o bot encontrou:", *lista(plano.problemas)]
            linhas.append("\nCorrija no Estúdio, baixe o arquivo de novo e reenvie.")
            return "\n".join(linhas)[:1900]
        if not plano.gravar:
            return "Nada mudou: o bot já tem este arquivo exatamente assim."
        linhas = ["**Publicado.** Já está no ar, em todos os servidores do bot."]
        if plano.novas:
            linhas += ["", "Novo:", *lista(plano.novas)]
        if plano.atualizadas:
            linhas += ["", "Atualizado:", *lista(plano.atualizadas)]
        if plano.iguais:
            linhas += ["", f"Sem mudança: {len(plano.iguais)} item(ns)."]
        if plano.avisos:
            linhas += ["", "Vale olhar:", *lista(plano.avisos, 5)]
        return "\n".join(linhas)[:1900]

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


    @config_grupo.command(
        name="autores",
        description="Cargo que pode publicar dungeons e salas com /incursao enviar",
    )
    @app_commands.describe(
        cargo="O cargo dos autores. Sem cargo, só quem administra o servidor publica."
    )
    async def config_autores(
        self, interaction: discord.Interaction, cargo: Optional[discord.Role] = None
    ) -> None:
        await db.definir_cargo_de_autor(
            self.bot.db, interaction.guild_id, cargo.id if cargo else None
        )
        if cargo:
            texto = (
                f"Quem tem o cargo {cargo.mention} publica dungeons e salas com "
                "`/incursao enviar`. O que eles publicam vale em todos os "
                "servidores do bot, e entra no ar na hora."
            )
        else:
            texto = "Sem cargo de autores: só quem administra o servidor publica."
        await interaction.response.send_message(texto, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Incursoes(bot))
