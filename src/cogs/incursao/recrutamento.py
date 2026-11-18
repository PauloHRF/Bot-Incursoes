"""O recrutamento: quem entra no grupo, e o começo da incursão.

O `/incursao entrar` abre o recrutamento (o comando mora em `cog.py`); daqui
em diante é o painel de quem entra e sai, o que impede alguém de entrar (o
intervalo de semanas, a run em outro canal, o tier), e o "Começar".
"""


from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import discord

from ... import config, database as db, embeds as E, motor
from ...incursoes import Incursao
from ...rules import tier
from .views import SeletorPersonagemEntrada, ViewRecrutamento


class Recrutamento:
    """Quem entra no grupo, o que impede, e o começo da run."""

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
            #
            # Sao tres motivos no mesmo `rowcount` zero, e a ordem importa: o
            # grupo que encheu COMECA em seguida, entao quem perdeu a ultima
            # vaga tambem encontra a run fora do recrutamento. Lotacao vem
            # antes para ele ler o que de fato o barrou.
            if await db.esta_na_run(self.bot.db, run_id, interaction.user.id):
                motivo = "Você já está no grupo."
            elif (
                len(await db.participantes(self.bot.db, run_id))
                >= config.TAMANHO_GRUPO
            ):
                motivo = "O grupo encheu antes de você: a última vaga foi de outra pessoa."
            else:
                motivo = "A incursão começou antes de você entrar: o grupo já partiu."
            await interaction.response.send_message(motivo, ephemeral=True)
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
        # A run e tomada ANTES de qualquer outra coisa, e depois das recusas
        # acima — que precisam deixa-la em 'recrutando' para o grupo tentar de
        # novo. Dois caminhos chegam aqui (o grupo encheu, ou quem abriu clicou
        # em "Comecar") e os dois conferem o status com `await` no meio: sem a
        # reivindicacao, um clique duplo abria a run duas vezes.
        if not await db.tomar_o_inicio(self.bot.db, run["id"]):
            return
        # Relido depois da trava: quem entrou enquanto este clique esperava ja
        # esta no grupo, e a lista de cima foi lida antes disso.
        participantes = await db.participantes(self.bot.db, run["id"])
        await db.marcar_ultima_incursao(self.bot.db, run["guild_id"], participantes)
        await db.inicializar_hp(self.bot.db, run["id"])

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
