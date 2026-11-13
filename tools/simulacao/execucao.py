"""Combate real do cog em SQLite descartavel, sem rede ou mensagens.

Nao ha uma segunda implementacao de habilidades. A fila, os recursos,
passivas, reacoes, condicoes e a iniciativa pertencem a Incursoes.
"""
from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass
import random
from types import SimpleNamespace

from src import aleatorio, classes, database as db, incursoes as I, itens, rules
from src.cogs.incursao import Incursoes
from .memoria import Memoria
from . import politica


@dataclass
class Ficha:
    classe: str
    nivel: int
    escolhas: dict | None = None
    equipamento: tuple[str, ...] = ()

    def __post_init__(self):
        if self.classe not in classes.CLASSES:
            raise ValueError(f"Classe desconhecida: {self.classe}")
        if not 1 <= self.nivel <= 10:
            raise ValueError("Nivel deve estar entre 1 e 10.")
        if self.escolhas is not None and not isinstance(self.escolhas, dict):
            raise ValueError("Escolhas deve ser um objeto com IDs e opcoes.")
        slots = set()
        for item_id in self.equipamento:
            peca = itens.item(item_id)
            if peca is None or peca.slot in slots:
                raise ValueError(f"Equipamento desconhecido ou slot repetido: {item_id}")
            slots.add(peca.slot)
        automaticas = politica.escolhas_automaticas(self.classe, self.nivel)
        tabela = classes.CLASSES[self.classe].habilidades
        opcoes = {h.id: h.escolha for t, hs in tabela.items() if t <= rules.tier(self.nivel)
                  for h in hs if h.escolha}
        for chave, valor in (self.escolhas or {}).items():
            forma = opcoes.get(chave)
            if not forma:
                raise ValueError(f"Escolha indisponivel para {self.classe}: {chave}")
            if forma.get("tipo") == "opcao" and valor not in {o["id"] for o in forma["opcoes"]}:
                raise ValueError(f"Opcao invalida: {chave}={valor}")
        self.escolhas = {**automaticas, **(self.escolhas or {})}


class _Interacao:
    def __init__(self, uid):
        self.user = SimpleNamespace(id=uid)
        self.response = self

    async def defer(self, **kw): pass
    async def delete_original_response(self): pass


class _LimiteDeRodadas(Exception):
    pass


class _Combate(Incursoes):
    def __init__(self, conn):
        super().__init__(SimpleNamespace(db=conn))
        self.final = None
        self.metricas = Counter()
        self.habilidades = {}
        self.reacoes = Counter()
        self.quedas = set()
        self.agiram = set()
        self.profundidade = 0
        self.limite_atingido = False

    async def _avancar(self, run, sala, interaction=None, trocada=None):
        try:
            return await super()._avancar(run, sala, interaction, trocada)
        except _LimiteDeRodadas:
            self.limite_atingido = True

    async def _virar_rodada(self, run, sala, estado):
        if estado.rodada >= self.limite:
            raise _LimiteDeRodadas
        return await super()._virar_rodada(run, sala, estado)

    async def _canal(self, run): return None
    async def _atualizar_painel(self, *a, **kw): pass
    async def _anunciar_habilidade(self, *a, **kw): pass
    async def _dizer(self, *a, **kw): pass
    def _registrar(self, *a, **kw): pass

    async def _abrir_combate(self, run, sala):
        await self._preparar_combate(run, sala)
        await self._avancar(run, sala)

    async def _aplicar_aberturas(self, run):
        return await self._medir(run, lambda: super(_Combate, self)._aplicar_aberturas(run), passiva=True)

    def _versao_da_habilidade(self, acao, estado, uid):
        antes = sum(c.thp for c in estado.combatentes)
        versao, pago = super()._versao_da_habilidade(acao, estado, uid)
        if pago:
            self.metricas["thp_gasto"] += antes - sum(c.thp for c in estado.combatentes)
        return versao, pago

    async def _encerrar_combate(self, run, sala, estado):
        self.final = estado
        await self._devolver_pendentes(run)
        await db.atualizar_run(self.bot.db, run["id"], status="sucesso" if estado.inimigos_derrotados else "fracasso")

    async def _estado(self, run):
        return await self._estado_combate(run, self.incursoes[run["incursao_id"]].objetivo)

    async def _medir(self, run, operacao, acao=None, inimigo=False, passiva=False):
        if self.profundidade or not self.coletar_detalhes:
            return await operacao()
        antes = await self._estado(run)
        gastos_antes = {uid: await db.usos_da_run(self.bot.db, run["id"], uid)
                       for uid, reativas in self.reativas.items() if reativas}
        self.profundidade += 1
        try:
            resposta = await operacao()
        finally:
            self.profundidade -= 1
        depois = await self._estado(run)
        hp_antes = {c.user_id: (c.hp_atual, c.thp) for c in antes.combatentes}
        hp_depois = {c.user_id: (c.hp_atual, c.thp) for c in depois.combatentes}
        cura = thp = recebido = 0
        for uid, (hp, temporario) in hp_depois.items():
            anterior, thp_anterior = hp_antes.get(uid, (hp, 0))
            cura += max(0, hp - anterior)
            thp += max(0, temporario - thp_anterior)
            if inimigo:
                recebido += max(0, anterior - hp) + max(0, thp_anterior - temporario)
            if hp <= 0 and uid not in self.quedas and uid in self.fichas:
                self.quedas.add(uid)
                if uid not in self.agiram:
                    self.metricas["quedas_antes_de_agir"] += 1
        dano = sum(max(0, a.hp_atual - b.hp_atual) for a, b in zip(antes.inimigos, depois.inimigos))
        self.metricas.update(cura=cura, thp_gerado=thp, recebido=recebido, dano=dano)
        if passiva:
            self.metricas.update(cura_passiva=cura, dano_periodico=dano)
        if acao:
            item = self.habilidades.setdefault(acao.nome, dict(usos=0, dano=0, cura=0, recursos=0, thp=0, periodico=0))
            item.update(usos=item["usos"] + 1, dano=item["dano"] + dano,
                        cura=item["cura"] + cura, recursos=item["recursos"] + 1, thp=item["thp"] + thp)
        for uid, reativas in self.reativas.items():
            if not reativas:
                continue
            depois_usos = await db.usos_da_run(self.bot.db, run["id"], uid)
            for h in reativas:
                delta = sum(v - gastos_antes[uid].get(k, 0) for k, v in depois_usos.items() if k[0] == h.chave_de_uso)
                if delta > 0:
                    self.reacoes[h.nome] += delta
        return resposta

    async def _resolver_turno(self, run, estado, uid, turno):
        if not self.coletar_detalhes:
            return await super()._resolver_turno(run, estado, uid, turno)
        self.agiram.add(uid)
        acao = classes.POR_ID.get(turno["acao"])
        antes = await db.proximo_indice_de_ataque(self.bot.db, run["id"], self._passo(run), estado.rodada, uid)
        resposta = await self._medir(run, lambda: super(_Combate, self)._resolver_turno(run, estado, uid, turno), acao)
        if turno["acao"] == "ataque":
            depois = await db.proximo_indice_de_ataque(self.bot.db, run["id"], self._passo(run), estado.rodada, uid)
            self.metricas["ataques_basicos"] += depois - antes
        return resposta

    async def _resolver_habilidade(self, run, estado, uid, habilidade, alvos):
        return await self._medir(run, lambda: super(_Combate, self)._resolver_habilidade(run, estado, uid, habilidade, alvos), habilidade)

    async def _vez_do_inimigo(self, run, estado, inimigo, antes):
        if inimigo.atordoado:
            self.metricas["turnos_inimigos_atordoados"] += 1
        return await self._medir(run, lambda: super(_Combate, self)._vez_do_inimigo(run, estado, inimigo, antes), inimigo=True)

    async def _vez_da_invocacao(self, run, estado, aliado):
        return await self._medir(run, lambda: super(_Combate, self)._vez_da_invocacao(run, estado, aliado))

    async def _reacoes_do_revide(self, run, estado, golpes, investidas=()):
        for c in estado.combatentes:
            if c.caido and not c.e_invocacao and c.user_id not in self.quedas:
                self.quedas.add(c.user_id)
                if c.user_id not in self.agiram:
                    self.metricas["quedas_antes_de_agir"] += 1
        return await super()._reacoes_do_revide(run, estado, golpes, investidas)

    async def _virar_efeitos(self, run, estado):
        return await self._medir(run, lambda: super(_Combate, self)._virar_efeitos(run, estado), passiva=True)

    async def _perder_a_vez(self, run, estado, quem, turno):
        if quem is not None:
            self.metricas["turnos_caidos" if quem.caido else "turnos_perdidos"] += 1
        return await super()._perder_a_vez(run, estado, quem, turno)


class Bancada:
    """Uma composicao fixa; cada luta cria uma run limpa no banco em memoria."""
    def __init__(self, fichas, monstros, *, limite=50, tier=None, coletar_detalhes=True):
        if not fichas or len(fichas) > 6:
            raise ValueError("Use de 1 a 6 personagens.")
        if not monstros or limite < 1:
            raise ValueError("Informe inimigos e um limite de rodadas positivo.")
        self.fichas, self.monstros, self.limite = list(fichas), list(monstros), limite
        self.tier = tier or max(rules.tier(f.nivel) for f in fichas)
        self.coletar_detalhes = coletar_detalhes
        self.conn = Memoria()
        self.ids = []

    async def __aenter__(self):
        try:
            await db.criar_schema(self.conn)
            for i, ficha in enumerate(self.fichas, 1):
                pid = await db.criar_personagem(self.conn, 1, i, f"P{i}", ficha.classe, [], nivel=ficha.nivel)
                self.ids.append(pid)
                for chave, opcao in ficha.escolhas.items():
                    await db.definir_escolha(self.conn, pid, chave, opcao)
                for item_id in ficha.equipamento:
                    peca = itens.item(item_id)
                    await db.devolver_item(self.conn, pid, item_id)
                    vestiu, _ = await db.equipar(self.conn, pid, item_id, peca.slot)
                    if not vestiu:
                        raise RuntimeError(f"O equipamento nao foi aplicado: {item_id}")
            return self
        except BaseException:
            await self.conn.close()
            raise

    async def __aexit__(self, *exc):
        await self.conn.close()

    async def iniciar(self):
        self.cog = _Combate(self.conn)
        self.cog.coletar_detalhes = self.coletar_detalhes
        self.cog.limite = self.limite
        self.cog.fichas = dict(enumerate(self.fichas, 1))
        self.cog.reativas = {uid: [h for _, h in classes.habilidades(f.classe, f.nivel, f.escolhas)
                                  if (h.acao or {}).get("tipo") == "reacao"]
                            for uid, f in self.cog.fichas.items()}
        self.sala = I.Sala("OBJ", "Simulacao", "Combate", "", monstros=self.monstros)
        self.incursao = I.Incursao(id="simulacao", nome="Simulacao", organizacao=I.ORGANIZACOES[0],
                                  lore_inicial="", recompensa_mes=0, objetivo=self.sala,
                                  tier=self.tier, tamanho="Curta")
        self.cog.incursoes[self.incursao.id] = self.incursao
        self.run_id = await db.criar_run(self.conn, 1, 1, self.incursao.id, 1)
        for i, pid in enumerate(self.ids, 1):
            entrou = await db.adicionar_participante(self.conn, self.run_id, i, pid,
                                                    tier=self.tier, limite=len(self.fichas))
            if not entrou:
                raise RuntimeError("A ficha nao entrou no grupo da simulacao.")
        await db.inicializar_hp(self.conn, self.run_id)
        self.hp_inicial = sum(p["hp_max"] for p in await db.personagens_da_run(self.conn, self.run_id))
        await db.atualizar_run(self.conn, self.run_id, status="objetivo", sala_atual="OBJ", linha_atual=self.incursao.paradas + 1)
        self.run = await db.buscar_run(self.conn, self.run_id)
        await self.cog._abrir_combate(self.run, self.sala)

    async def escolher(self, run, estado, uid):
        personagem = await self.cog._personagem_na_run(run, uid)
        disponiveis = await self.cog._habilidades_disponiveis(run, personagem, self.cog._passo(run))
        permitidas = [h for h, _ in disponiveis
                      if not await self.cog._aviso_de_requisito(run, estado, uid, h)]
        h = politica.escolher(permitidas, estado.combatente(uid), estado)
        if not h:
            return None, []
        opcoes = await self.cog._alvos_possiveis(run, h, estado)
        if not opcoes:
            return h, []
        acao = h.acao or {}
        quantos = acao.get("alvos", 1)
        quantos = quantos if isinstance(quantos, int) else len(opcoes)
        if acao.get("tipo") == "cura" or acao.get("alvo") in ("aliado", "aliados"):
            validos = {int(v) for v, _, _ in opcoes}
            alvos = [c for c in estado.combatentes if c.user_id in validos]
            alvos.sort(key=(lambda c: (c.hp_atual / max(1, c.hp_max), c.user_id))
                       if acao.get("tipo") == "cura" else
                       (lambda c: -politica.media_dado(c.dano_arma) * c.ataques))
            return h, [c.user_id for c in alvos[:quantos]]
        return h, [int(v) for v, _, _ in opcoes[:quantos]]

    async def lutar(self, rng):
        with aleatorio.usar(rng):
            await self.iniciar()
            escolhas = 0
            while self.cog.final is None and not self.cog.limite_atingido:
                self.run = await db.buscar_run(self.conn, self.run_id)
                estado = await self.cog._estado_combate(self.run, self.sala)
                if estado.rodada > self.limite:
                    break
                uid = await self.cog._de_quem_e_a_vez(self.run, estado)
                if uid is None:
                    await self.cog._avancar(self.run, self.sala)
                else:
                    h, alvos = await self.escolher(self.run, estado, uid)
                    await self.agir(uid, h.id if h else None, alvos)
                escolhas += 1
                if escolhas > (self.limite + 1) * len(self.fichas) * 30:
                    raise RuntimeError("A fila do combate nao avancou.")
            estado = self.cog.final or await self.cog._estado_combate(self.run, self.sala)
            resultado = await self.resultado(estado)
            await self.conn.execute("DELETE FROM runs WHERE id = ?", (self.run_id,))
            await self.conn.commit()
            return resultado

    async def agir(self, uid, habilidade=None, alvos=None):
        """Mesmo caminho dos botoes, util para politicas e regressoes dirigidas."""
        inter = _Interacao(uid)
        if habilidade:
            await self.cog.usar_habilidade(inter, self.run_id, "OBJ", habilidade, alvos or [])
        else:
            await self.cog.atacar(inter, self.run_id, "OBJ")

    async def resultado(self, estado):
        jogadores = [c for c in estado.combatentes if not c.e_invocacao]
        usos = list(self.cog.habilidades.values())
        return {
            "inimigos_derrotados": estado.inimigos_derrotados,
            "rodadas": min(estado.rodada, self.limite),
            "caidos": len(self.fichas) - sum(not c.caido for c in jogadores),
            "personagens_derrubados": len(self.cog.quedas),
            "hp_restante": sum(c.hp_atual for c in jogadores),
            "hp_inicial": self.hp_inicial,
            "thp_restante": sum(c.thp for c in jogadores),
            "limite_rodadas": self.cog.final is None,
            **{k: self.cog.metricas[k] for k in ("cura", "thp_gerado", "thp_gasto", "recebido", "dano", "ataques_basicos",
               "turnos_caidos", "turnos_perdidos", "turnos_inimigos_atordoados", "quedas_antes_de_agir", "cura_passiva", "dano_periodico")},
            "recursos": sum(u["recursos"] for u in usos) + sum(self.cog.reacoes.values()),
            "habilidades_usadas": self.cog.habilidades,
            "reacoes": dict(self.cog.reacoes),
            "estado": estado,
        }


async def simular_async(monstros, fichas, repeticoes, rng, *, limite=50, tier=None, estados=False, coletar_detalhes=True):
    if repeticoes < 1:
        raise ValueError("Repeticoes deve ser maior que zero.")
    async with Bancada(fichas, monstros, limite=limite, tier=tier, coletar_detalhes=coletar_detalhes) as bancada:
        resultados = []
        for _ in range(repeticoes):
            resultado = await bancada.lutar(random.Random(rng.getrandbits(128)))
            if not estados:
                resultado.pop("estado")
            resultados.append(resultado)
        return resultados


def simular(monstros, fichas, repeticoes, rng, **kw):
    return asyncio.run(simular_async(monstros, fichas, repeticoes, rng, **kw))
