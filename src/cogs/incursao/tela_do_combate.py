"""O combate no canal: o painel, os menus, as poções e o fim da luta.

As regras do combate moram em `src/combate`, e falam com o grupo pelas
portas que estão aqui (`src.combate.PORTAS`): o painel que se edita no
lugar, a resposta a quem clicou, a chamada da rodada, a pergunta da marca
órfã. Também ficam aqui os menus de habilidade e de poção, a poção em si (o
menu da Poção de Mana é uma view no meio da regra), e o fecho do combate —
que é a run andando: paga a sala, abre o objetivo, encerra a incursão.
"""


from __future__ import annotations

import logging

from typing import Any, Optional

import discord

from ... import condicoes, config, consumiveis, database as db, embeds as E
from ...combate.acoes import AVISO_CAIDO
from ...combate.fluxo import MAX_RODADAS_SOZINHAS
from ...combate.mesa import Clique
from ...incursoes import Sala
from .views import (
    SeletorAlvoHabilidade,
    SeletorHabilidade,
    SeletorPocao,
    SeletorRecarga,
    ViewCombate,
    ViewMarcaOrfa,
)

log = logging.getLogger("incursoes.run")


class TelaDoCombate:
    """Painel, menus, poções e o fecho do combate; as portas do `Combate`."""

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

    async def _responder_no_clique(
        self, run: dict[str, Any], interaction: Clique, texto: str
    ) -> None:
        """A resposta privada de quem clicou, quando a vez dele saiu.

        Se esta exata frase ja foi para o canal, nao repete em privado: quem
        clicou via a propria habilidade duas vezes. Mas a interacao foi
        adiada e PRECISA ser fechada, senao o Discord deixa o "pensando..."
        pendurado para sempre.
        """
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

    async def _avisar_fila_presa(self, run: dict[str, Any]) -> None:
        """O grupo inteiro preso rodada após rodada: o canal precisa saber."""
        canal = await self._canal(run)
        if canal:
            await canal.send(
                f"⏳ O grupo inteiro segue preso depois de "
                f"{MAX_RODADAS_SOZINHAS} rodadas. O combate espera "
                f"alguem se soltar — se travar de vez, "
                f"`/incursao desistir` encerra a run."
            )

    async def _perguntar_pela_marca(
        self, run: dict[str, Any], dono: int, inimigo, quantas: int, expira: int,
        sobraram: list,
    ) -> None:
        """Pergunta ao ladino do tier 5 para quem passam as marcas do morto."""
        canal = await self._canal(run)
        if canal is None:
            return
        await canal.send(
            f"🎯 <@{dono}> — **{inimigo.nome}** caiu com "
            f"**{quantas}** Marca(s) Fatal(is) ainda sem explodir. "
            f"Para quem elas passam?",
            view=ViewMarcaOrfa(
                self, run["id"], dono, quantas, expira, sobraram
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

    async def _chamar_a_rodada(self, run: dict[str, Any], sala: Sala) -> None:
        """A rodada virou: o canal se limpa da que acabou e chama a nova.

        Saem as respostas privadas, a chamada e os anúncios de habilidade da
        rodada que acabou; entra uma chamada nova, para todos que podem agir.
        """
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

    async def _encerrar_combate(self, run: dict[str, Any], sala: Sala, estado) -> None:
        """Um dos lados caiu: fecha o painel e segue a run (ou a encerra).

        **Se o fecho quebrar no meio, a reivindicação volta.** Ela é de
        memória (`_tomar_o_fecho_do_combate`), e ficava tomada: o combate
        decidido não podia mais ser fechado por ninguém neste processo, e a
        run parava em `em_sala` com um lado inteiro no chão. Devolvida, o
        próximo clique — ou a retomada da subida do bot — fecha o que faltou.

        Refazer o fecho é seguro porque quase tudo nele já é idempotente
        (pontos e ouro têm chave, a sala superada é uma marca), e a única
        parte que não era — o decaimento das condições — é reivindicada no
        banco, por passo.
        """
        try:
            await self._fechar_o_combate(run, sala, estado)
        except Exception:
            self._encerrados.discard((run["id"], self._passo(run)))
            raise

    async def retomar_combates_decididos(self) -> list[int]:
        """Fecha os combates que se decidiram e cuja run não andou. Devolve as runs.

        É a outra metade de `_encerrar_combate` devolver a reivindicação: um
        fecho que parou no meio — o bot reiniciou durante ele, ou o Discord
        recusou o cartão do passo seguinte — deixava a run em `em_sala` com um
        lado inteiro no chão, e o painel, que perde os botões antes do resto
        do fecho, não tinha mais onde clicar. Nem um restart soltava: os
        botões voltavam para uma mensagem que já não tinha botão nenhum.

        Roda na subida do bot (`cog_load`), e não espera clique: quem decide
        que o combate acabou é o banco, e o banco já diz. Uma run que falhar
        de novo fica registrada no log e não segura as outras.
        """
        retomadas: list[int] = []
        for run in await db.runs_vivas(self.bot.db):
            if run["status"] not in ("em_sala", "objetivo") or not run["sala_atual"]:
                continue
            sala = await self._sala_corrente(run)
            if sala is None or not sala.e_combate:
                continue
            estado = await self._estado_combate(run, sala)
            if estado is None or not estado.encerrado:
                continue
            try:
                await self._avancar(run, sala)
            except Exception:
                log.exception(
                    "a run %s tem um combate decidido e o fecho falhou de novo",
                    run["id"],
                )
                continue
            retomadas.append(run["id"])
        return retomadas

    async def _fechar_o_combate(self, run: dict[str, Any], sala: Sala, estado) -> None:
        # Antes de tudo: quem escolheu e nao chegou a agir recebe de volta o
        # que a escolha reservou. Vale vencendo e perdendo — a acao nao
        # aconteceu nos dois casos.
        await self._devolver_pendentes(run)
        # A pilha do Martial Arts morre AQUI, explicitamente. Ela já morria
        # pela chave (`run_efeitos` tem o `passo`, e cada sala é um passo),
        # mas desde que a pilha perdeu o teto o prazo dela deixou de ser um
        # detalhe e virou o único freio: um monge que emendou oito acertos
        # carrega +8, e isso não pode atravessar porta nenhuma por acidente
        # de encanamento.
        await db.limpar_efeito(
            self.bot.db, run["id"], self._passo(run), "martial_arts"
        )
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

    async def abrir_habilidades(
        self, interaction: discord.Interaction, run_id: int, sala_id: str
    ) -> None:
        """Mostra, so para quem clicou, o que ele pode usar agora."""
        self._guardar_efemera(run_id, interaction)
        # Adiado antes de qualquer leitura: `_estado_combate` monta a sala
        # inteira, e no servidor (um oitavo de OCPU) isso disputa os 3 s que o
        # Discord da para a primeira resposta. O `thinking=True` e o que faz o
        # `ephemeral` valer num clique de botao — ver `atacar`.
        await interaction.response.defer(ephemeral=True, thinking=True)
        run = await db.buscar_run(self.bot.db, run_id)
        if not run or run["status"] not in ("em_sala", "objetivo"):
            await self._dizer(interaction, "Esta sala ja terminou.")
            return
        personagem = await self._personagem_na_run(run, interaction.user.id)
        if personagem is None:
            await self._dizer(interaction,
                "Voce nao faz parte desta run."
            )
            return

        # Em combate, quem ja agiu nao abre o menu: o turno e um so. Quem
        # apenas PREPAROU abre — o menu e por onde ele troca a escolha.
        incursao = self._incursao_da_run(run)
        sala = await self._sala_corrente(run)
        if sala is not None and sala.e_combate:
            estado = await self._estado_combate(run, sala)
            if estado is not None:
                gasto = await self._turno_ja_resolvido(
                    run_id, self._passo(run), estado.rodada, interaction.user.id,
                )
                if gasto:
                    await self._dizer(interaction,
                        self._turno_gasto(gasto)
                    )
                    return

        disponiveis = await self._habilidades_disponiveis(
            run, personagem, self._passo(run)
        )
        if not disponiveis:
            await self._dizer(interaction,
                "Voce nao tem habilidade para usar agora. Veja `/ficha ver`: as ativas "
                "marcadas *(em breve)* ainda nao estao prontas, e as outras podem ter "
                "acabado os usos."
            )
            return

        opcoes = [
            (h.id, h.nome, f"{restantes} uso(s) — {h.texto}")
            for h, restantes in disponiveis
        ]
        await self._dizer(interaction,
            "O que voce usa?",
            view=SeletorHabilidade(self, run_id, sala_id, opcoes)
        )

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
        # Adiado antes de qualquer leitura: `_estado_combate` monta a sala
        # inteira, e no servidor (um oitavo de OCPU) isso disputa os 3 s que o
        # Discord da para a primeira resposta. O `thinking=True` e o que faz o
        # `ephemeral` valer num clique de botao — ver `atacar`.
        await interaction.response.defer(ephemeral=True, thinking=True)
        run = await db.buscar_run(self.bot.db, run_id)
        if not run or run["status"] not in ("em_sala", "objetivo"):
            await self._dizer(interaction, "Esta sala já terminou.")
            return
        personagem = await self._personagem_na_run(run, interaction.user.id)
        if personagem is None:
            await self._dizer(interaction,
                "Você não faz parte desta run."
            )
            return

        carregadas = await self._pocoes_na_bolsa(personagem)
        if not carregadas:
            await self._dizer(interaction,
                "Sua bolsa não tem poção nenhuma. Compre no `/mercado vitrine`."
            )
            return

        # Com o turno gasto só sobra o que não custa ação: a Aceleração. Em vez
        # de recusar o botão inteiro, o menu mostra o que ainda dá — quem já
        # atacou pode beber a Aceleração e ganhar os golpes da próxima rodada.
        # Quem só preparou vê a bolsa inteira: beber troca o que ele preparou.
        sala = await self._sala_corrente(run)
        gasto = None
        if sala is not None and sala.e_combate:
            estado = await self._estado_combate(run, sala)
            if estado is not None:
                gasto = await self._turno_ja_resolvido(
                    run_id, self._passo(run), estado.rodada, interaction.user.id,
                )
        if gasto:
            carregadas = [(p, q) for p, q in carregadas if not p.gasta_turno]
            if not carregadas:
                await self._dizer(interaction,
                    f"{self._turno_gasto(gasto)} Só a Poção da Aceleração não "
                    f"custa a ação da rodada."
                )
                return

        opcoes = [(p.id, p.nome, q, p.texto) for p, q in carregadas]
        await self._dizer(interaction,
            "O que você bebe?",
            view=SeletorPocao(self, run_id, sala_id, opcoes)
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
            gasto = await self._turno_ja_resolvido(
                run_id, passo, estado.rodada, interaction.user.id
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
            trocada = None
            if estado is not None:
                trocada = await self._trocar_acao_guardada(
                    run, passo, estado.rodada, interaction.user.id
                )
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
            if trocada:
                texto = f"🔁 {trocada} saiu da vez. {texto}"
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

        trocada = await self._trocar_acao_guardada(
            run, passo, estado.rodada, interaction.user.id
        )
        if not await db.marcar_turno(
            self.bot.db, run_id, passo, estado.rodada, interaction.user.id,
            pocao.id, resolvida=False,
        ):
            await db.devolver_item(self.bot.db, personagem["id"], pocao.id)
            await self._dizer(interaction, self._turno_gasto("ataque"))
            return
        await self._avancar(run, sala, interaction, trocada)

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
            # Aviso, e nao passo do jogo: recusado, a run segue mesmo assim.
            await self._avisar_no_canal(canal, embed=E.combate_vencido(sala, estado))

        # Antes de decair: quem a criatura levou ao teto sai agora. Na outra
        # ordem o decaimento tiraria o stack que estourou, e o teto de uma
        # condicao que decai nunca pegaria ninguem.
        if await self._expulsar_estourados(run):
            return

        # Um combate a menos no prazo dos debuffs e dos buffs. As maldicoes e a
        # Exaustao tem prazo NULL e nao sao tocadas: duram a incursao.
        #
        # Reivindicado por passo, e so ele: e a unica parte deste fecho que
        # nao pode rodar duas vezes, e o fecho pode ser retomado
        # (`retomar_combates_decididos`).
        if await db.tomar_o_decaimento(self.bot.db, run["id"], self._passo(run)):
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
        await self._avisar_no_canal(canal, "⏳ " + "; ".join(linhas) + ".")
