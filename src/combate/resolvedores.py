"""As habilidades valendo: o que cada uma faz quando sai no combate.

Era o miolo de `src/cogs/incursao.py` — o golpe, a cura, o save forçado, o
buff com prazo, a forma animal, a invocação, a poção — e saiu de lá sem mudar
uma linha. É a primeira fatia da extração das regras do cog; a referência
gravada (`tests/test_referencia_combate.py`) é o que prova que nada mudou.

**O cog continua com os mesmos nomes.** `Incursoes` herda desta classe, então
`cog._resolver_save(...)` é o mesmo método de antes, chamado do mesmo jeito.
Herdar, e não guardar um objeto de resolvedores dentro do cog, é o que deixa
valer o que já se apoia nesses nomes: os testes chamam vários deles direto, e
a simulação (`tools/simulacao/execucao.py`) sobrescreve `_resolver_habilidade`
e `_versao_da_habilidade` para medir o combate. Com um objeto à parte, a
chamada de dentro — `_resolver_grupo` pedindo a versão da habilidade — pularia
a sobrescrita, e o THP gasto que a bancada mede zeraria calado.

**O que eles pedem do cog.** Só o canal: o anúncio do que foi usado, para o
grupo ver (`DA_MESA`). O passo, o tier, a ficha montada e o log da rodada vêm
da mesa (`mesa.py`); o ataque comum e a Marca Fatal, do fluxo.
"""
from __future__ import annotations

from typing import Any, Optional

from .. import (
    classes as cl,
    condicoes,
    consumiveis,
    database as db,
    embeds as E,
    motor,
)
from ..rules import fmt

# O que os resolvedores pedem de quem herda o combate: as portas de saída.
DA_MESA = {
    "_anunciar_habilidade": "o canal: o grupo vê o que foi usado",
}


class Resolvedores:
    """Cada tipo de ação de habilidade, e os ajudantes que só elas usam.

    A porta é `_resolver_habilidade`, que escolhe pelo `tipo` da ação. Todo
    resolvedor devolve o texto que o jogador vê, e anuncia no canal a mesma
    frase quando ela é para o grupo: é a igualdade exata que faz `_avancar`
    não repetir em privado o que já saiu em público.
    """

    # O prazo de quem vale pelo combate inteiro, e nao por um numero de
    # rodadas: quem apaga a conta e a troca de sala, porque o `passo` faz
    # parte da chave em `run_efeitos`. A ameaca gerada NAO usa mais este
    # prazo — ela tem janela de uma rodada (ver `somar_ameaca_da_rodada`).
    PRAZO_DO_COMBATE = 10 ** 6

    # A chave de uso da Heightened Spell. Nao e uma habilidade do catalogo —
    # e uma metamagia passiva que passou a ter conta —, entao ela precisa de
    # uma chave propria em `run_usos`.
    CHAVE_DA_HEIGHTENED = "heightened_spell"

    # O Stealth do ladino, que `_resolver_golpes` liga e o cog le.
    EFEITO_DA_FURTIVIDADE = "furtividade"

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
        # Heightened Spell: UMA por descanso, e gasta sozinha na primeira
        # magia de save que sair. Ela era passiva ligada para sempre — toda
        # magia do feiticeiro saía com a criatura resistindo em desvantagem.
        #
        # Gasta AQUI, e não na hora de lançar: `_resolver_save` é o único
        # caminho em que a desvantagem pesa, então ela nunca é desperdiçada
        # num lançamento que não força save. Quem não tem a metamagia nem
        # chega a consultar o uso.
        desvantagem = bool(meta.get("save_com_desvantagem")) and await db.gastar_uso(
            self.bot.db, run["id"], user_id, self.CHAVE_DA_HEIGHTENED,
            f"descanso:{run['descansos']}", 1,
        )
        dado_extra = meta.get("dano_magia") or ""

        if acao.get("alvos") == "todos":
            mirados = list(estado.inimigos_vivos)
        else:
            # Quantos a MAGIA pega, mais o alvo extra do feiticeiro. O número
            # da ação era ignorado aqui: `alvos: 2` mirava um só, e nenhuma
            # magia tinha dois até o Synaptic Static passar a ter. O menu já
            # lia o número certo (`_alvos_possiveis`), então o jogador
            # escolhia dois e via um levar.
            declarados = acao.get("alvos", 1)
            quantos = (declarados if isinstance(declarados, int) else 1)
            quantos = max(1, quantos) + meta.get("alvos_extra", 0)
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
            texto += f"\n{E.MARCA_ABATIDO} caem: {', '.join(caidos)}"
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
        # `ate_morrer`: a marca vale enquanto a criatura estiver de pé, e não
        # por um número de rodadas. É o Hex — a maldição é sobre AQUELA
        # criatura, e não tem por que soltar antes de ela cair. Com prazo em
        # rodadas o jogador marcava tarde de propósito, para a marca não
        # vencer antes do alvo.
        #
        # Não precisa de limpeza: o efeito mora em `run_efeitos` com o índice
        # daquele inimigo e o `passo` da sala, então ele morre com o combate
        # e não alcança criatura nenhuma depois.
        expira = (
            self.PRAZO_DO_COMBATE if acao.get("ate_morrer")
            else estado.rodada + acao.get("turnos", 1)
        )
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
        prazo = (
            "vale enquanto ele estiver de pé" if acao.get("ate_morrer")
            else f"vale por {turnos} turno(s), ate a rodada {expira - 1}"
        )
        cabeca = f"✨ **{habilidade.nome}**{alvo_texto} — {prazo}."

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
