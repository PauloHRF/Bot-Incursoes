"""O canal da run: falar com o grupo, chamar quem joga, limpar o que passou.

A resposta privada de quem clicou, as menções, o caminho da run por escrito,
a limpeza das respostas e dos anúncios da rodada que acabou, e o fim da run —
tudo o que os outros assuntos usam para falar no canal.
"""


from __future__ import annotations

import logging

from typing import Any, Optional

import discord

from ... import database as db
from ...incursoes import Sala

log = logging.getLogger("incursoes.run")


class Canal:
    """Mensagens, menções e limpeza do canal, e o fim da run."""

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
        self._publicado.pop(run["id"], None)
        # As mensagens e interacoes guardadas para limpar o canal: com a run
        # encerrada ninguem mais as limpa, e elas so ocupariam memoria.
        self._efemeras.pop(run["id"], None)
        self._usadas.pop(run["id"], None)
        self._chamadas.pop(run["id"], None)
        # Os fechos de combate reivindicados e a fila da run. Sair daqui e
        # seguro porque o status ja mudou, logo acima: todo caminho que fecha
        # combate ou entra na fila confere o status antes, e recusa run que
        # nao esta viva — nenhum deles volta a reivindicar o que sai aqui.
        self._encerrados = {
            chave for chave in self._encerrados if chave[0] != run["id"]
        }
        trava = self._travas.get(run["id"])
        if trava is not None and not trava.locked():
            # Ocupada, ela e de quem ainda esta terminando a ultima volta da
            # fila; esse sai sozinho pela conferencia de status, e a trava
            # fica para a proxima limpeza nao ter de adivinhar.
            self._travas.pop(run["id"], None)

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

    async def _avisar_no_canal(self, canal, *args, **kw) -> Optional[Any]:
        """Manda um aviso que não decide nada — e não deixa a falha dele parar a run.

        O fecho de um combate manda cartões no meio do caminho entre o último
        golpe e a parada seguinte: o resumo do combate, as condições que
        passaram, quem saiu da incursão. Se um deles fosse recusado (um embed
        acima do limite, uma queda do Discord), a exceção abortava o fecho ali
        — antes do decaimento, antes de abrir a parada seguinte — e a run
        ficava parada por causa de um enfeite. O que muda o jogo já foi para o
        banco antes de cada um destes envios; o aviso perdido vai para o log.
        """
        try:
            return await canal.send(*args, **kw)
        except discord.HTTPException as erro:
            log.warning(
                "um aviso nao saiu no canal %s, e a run segue: %s",
                getattr(canal, "id", "?"), erro,
            )
            return None

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

    async def _nome_na_run(self, run: dict[str, Any], user_id: int) -> str:
        personagem = await db.personagem_da_run(self.bot.db, run["id"], user_id)
        return (personagem or {}).get("nome") or f"<@{user_id}>"
