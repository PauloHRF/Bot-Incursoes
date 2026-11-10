"""Regressoes de substituicao, votacao e devolucao de acoes canceladas."""
from __future__ import annotations

import sys
import tempfile
import unittest
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import config, database as db, motor  # noqa: E402
from src.cogs.incursao import Incursoes  # noqa: E402
from fakes import (  # noqa: E402
    CANAL, GUILD, INDEFESO, FakeBot, FakeCanal, FakeInteraction, FakeUsuario,
    criar_grupo, montar_conteudo, salas_sem_combate,
)


async def envelhecer(conn, run_id):
    quando = datetime.now(timezone.utc) - timedelta(minutes=16)
    await conn.execute(
        "UPDATE run_combate SET vez_desde = ? WHERE run_id = ?",
        (quando.strftime("%Y-%m-%d %H:%M:%S"), run_id),
    )
    await conn.commit()


@asynccontextmanager
async def preparar(classe="guerreiro"):
    with tempfile.TemporaryDirectory(prefix="incursoes-reservas-") as pasta:
        config.DB_PATH = Path(pasta) / "teste.db"
        config.TAMANHO_GRUPO = 5
        conn = await db.conectar()
        try:
            await db.criar_schema(conn)
            ids = await criar_grupo(conn, nivel=9, classe=classe)
            canal = FakeCanal(CANAL)
            cog = Incursoes(FakeBot(conn, canal))
            incursao, _ = montar_conteudo(
                cog, tier=5, tamanho="Curta", salas=salas_sem_combate(),
                monstro_objetivo={**INDEFESO, "hp": 1000}, inimigos_objetivo=1,
            )
            run_id = await db.criar_run(conn, GUILD, CANAL, incursao.id, 101)
            for uid in (101, 102, 103):
                await db.adicionar_participante(conn, run_id, uid, ids[uid], tier=5)
            await db.inicializar_hp(conn, run_id)
            await db.atualizar_run(
                conn, run_id, status="objetivo", sala_atual="OBJ",
                linha_atual=incursao.passos + 1,
            )
            await cog._abrir_combate(await db.buscar_run(conn, run_id), incursao.objetivo)
            await envelhecer(conn, run_id)
            yield conn, canal, cog, await db.buscar_run(conn, run_id), ids
        finally:
            await conn.close()


async def pedir(cog, canal, uid, acao=None):
    inter = FakeInteraction(canal, uid)
    await cog.substituir.callback(cog, inter, FakeUsuario(101), acao=acao)
    return inter


class SubstituicaoReservas(unittest.IsolatedAsyncioTestCase):
    async def test_reacoes_nao_sao_acoes_de_substituicao(self):
        async with preparar("barbaro") as (conn, canal, cog, run, _ids):
            personagem = await cog._personagem_na_run(run, 101)
            oferecidas = {h.id for h in cog._habilidades_substituiveis(personagem)}
            self.assertNotIn("relentless", oferecidas)
            inter = await pedir(cog, canal, 102, "relentless")
            self.assertIn("não é uma ação", inter.resposta)
            self.assertIsNone(await db.substituicao_aberta(conn, run["id"], cog._passo(run), 1, 101))
            self.assertEqual(await db.usos_da_run(conn, run["id"], 101), {})

    async def test_pre_requisito_e_igual_ao_do_comando_normal(self):
        async with preparar("barbaro") as (conn, canal, cog, run, _ids):
            normal = FakeInteraction(canal, 101)
            await cog.usar_habilidade(normal, run["id"], "OBJ", "brutal_strike", [])
            inter = await pedir(cog, canal, 102, "brutal_strike")
            self.assertIn("outra habilidade ligada", normal.resposta)
            self.assertEqual(inter.resposta, normal.resposta)
            self.assertEqual(await db.usos_da_run(conn, run["id"], 101), {})
            self.assertIsNone(await db.substituicao_aberta(conn, run["id"], cog._passo(run), 1, 101))

    async def test_habilidade_com_requisito_preenchido_resolve(self):
        async with preparar("barbaro") as (conn, canal, cog, run, _ids):
            passo = cog._passo(run)
            await db.aplicar_efeito(
                conn, run["id"], passo, "personagem", 101, "reckless_attack",
                {"vantagem": True, "ameaca": 3}, 3,
            )
            await pedir(cog, canal, 102, "brutal_strike")
            await pedir(cog, canal, 103)
            turno = await db.turno_de(conn, run["id"], passo, 1, 101)
            self.assertEqual(turno["acao"], "brutal_strike")
            self.assertTrue(turno["resolvida"])
            usos = await db.usos_da_run(conn, run["id"], 101)
            self.assertEqual(usos[("brutal_strike", "incursao")], 1)

    async def test_requisito_e_revalidado_apos_a_votacao(self):
        async with preparar("barbaro") as (conn, canal, cog, run, _ids):
            passo = cog._passo(run)
            await db.aplicar_efeito(
                conn, run["id"], passo, "personagem", 101, "reckless_attack",
                {"vantagem": True, "ameaca": 3}, 3,
            )
            await pedir(cog, canal, 102, "brutal_strike")
            await db.remover_efeito(conn, run["id"], passo, "personagem", 101, "reckless_attack")
            await pedir(cog, canal, 103)
            self.assertIsNone(await db.turno_de(conn, run["id"], passo, 1, 101))
            self.assertEqual(await db.usos_da_run(conn, run["id"], 101), {})
            self.assertTrue(any("outra habilidade ligada" in (m.content or "") for m in canal.enviadas))

    async def test_o_uso_volta_se_o_dono_age_primeiro(self):
        async with preparar() as (conn, canal, cog, run, _ids):
            await db.definir_hp(conn, run["id"], 101, 10)
            await pedir(cog, canal, 102, "second_wind")
            original = db.marcar_turno
            intercalou = False

            async def intercalar(*args, **kwargs):
                nonlocal intercalou
                if kwargs.get("substituto") is not None and not intercalou:
                    intercalou = True
                    await cog.atacar(FakeInteraction(canal, 101), run["id"], "OBJ")
                return await original(*args, **kwargs)

            with patch.object(db, "marcar_turno", side_effect=intercalar):
                await pedir(cog, canal, 103)
            passo = cog._passo(run)
            turno = await db.turno_de(conn, run["id"], passo, 1, 101)
            self.assertTrue(intercalou)
            self.assertEqual(turno["acao"], "ataque")
            self.assertIsNone(turno["substituto"])
            usos = await db.usos_da_run(conn, run["id"], 101)
            self.assertEqual(usos.get(("second_wind", f"combate:{passo}"), 0), 0)
            self.assertEqual((await db.hp_dos_participantes(conn, run["id"]))[101], 10)

    async def test_outra_proposta_precisa_de_novos_votos(self):
        async with preparar() as (conn, canal, cog, run, _ids):
            # O recurso foi gasto em uma rodada anterior, por uma acao real.
            await cog.usar_habilidade(FakeInteraction(canal, 101), run["id"], "OBJ", "action_surge", [])
            for uid in (102, 103):
                await cog.atacar(FakeInteraction(canal, uid), run["id"], "OBJ")
            await envelhecer(conn, run["id"])
            passo = cog._passo(run)
            rodada = (await db.estado_combate(conn, run["id"], passo))["rodada"]
            await db.definir_hp(conn, run["id"], 101, 10)
            await pedir(cog, canal, 102, "action_surge")
            await pedir(cog, canal, 103)
            self.assertIsNone(await db.turno_de(conn, run["id"], passo, rodada, 101))
            await pedir(cog, canal, 102, "second_wind")
            self.assertIsNone(await db.turno_de(conn, run["id"], passo, rodada, 101))
            self.assertEqual(await db.apoios_da_substituicao(conn, run["id"], passo, rodada, 101), {102: True})
            await pedir(cog, canal, 103)
            turno = await db.turno_de(conn, run["id"], passo, rodada, 101)
            self.assertEqual(turno["acao"], "second_wind")
            self.assertTrue(turno["resolvida"])
            self.assertEqual(await db.apoios_da_substituicao(conn, run["id"], passo, rodada, 101), {})

    async def test_atualizacao_descarta_votos_orfaos_sem_apagar_proposta_atual(self):
        async with preparar() as (conn, canal, cog, run, _ids):
            passo = cog._passo(run)
            # Simula um banco anterior a correcao, com votos sem proposta.
            for nome in ("limpar_apoios_ao_tomar_substituicao", "limpar_apoios_ao_abrir_substituicao"):
                await conn.execute(f"DROP TRIGGER {nome}")
            await conn.execute(
                "INSERT INTO run_substituicao_apoio VALUES (?, ?, 1, 101, 103, 1)",
                (run["id"], passo),
            )
            await conn.commit()
            await db.criar_schema(conn)
            await pedir(cog, canal, 102)
            self.assertEqual(await db.apoios_da_substituicao(conn, run["id"], passo, 1, 101), {102: True})
            self.assertIsNone(await db.turno_de(conn, run["id"], passo, 1, 101))
            # Reabrir o banco ou perder a corrida de criar a mesma proposta
            # nao pode apagar os apoios da proposta que continua aberta.
            await db.criar_schema(conn)
            self.assertFalse(await db.abrir_substituicao(conn, run["id"], passo, 1, 101, "ataque", [], 103))
            self.assertEqual(await db.apoios_da_substituicao(conn, run["id"], passo, 1, 101), {102: True})
            await pedir(cog, canal, 103)
            self.assertTrue((await db.turno_de(conn, run["id"], passo, 1, 101))["resolvida"])

    async def test_cancelar_a_run_devolve_as_reservas_uma_vez(self):
        for admin in (True, False):
            with self.subTest(admin=admin):
                async with preparar() as (conn, canal, cog, run, ids):
                    rid, passo = run["id"], cog._passo(run)
                    await db.definir_hp(conn, rid, 102, 10)
                    await db.dar_item(conn, ids[102], "pocao_vida")
                    await db.atualizar_personagem(conn, ids[103], "classe", "mago")
                    await db.definir_escolha(conn, ids[103], "magia_mago_t3", "fireball")
                    await cog.usar_pocao(FakeInteraction(canal, 102), rid, "OBJ", "pocao_vida")
                    await cog.usar_habilidade(FakeInteraction(canal, 103), rid, "OBJ", "fireball", [])
                    if admin:
                        await cog.encerrar.callback(cog, FakeInteraction(canal, 999), pagar=False, devolver_vaga=False)
                    else:
                        for uid in (101, 103):
                            await cog.desistir.callback(cog, FakeInteraction(canal, uid))
                    self.assertEqual((await db.buscar_run(conn, rid))["status"], "encerrada" if admin else "desistiu")
                    self.assertEqual((await db.itens_na_bolsa(conn, ids[102])).get("pocao_vida"), 1)
                    self.assertEqual((await db.hp_dos_participantes(conn, rid))[102], 10)
                    self.assertEqual((await db.usos_da_run(conn, rid, 103)).get(("fireball", "descanso:0"), 0), 0)
                    self.assertEqual(await db.turnos_pendentes(conn, rid, passo), [])
                    await cog._devolver_pendentes(run)
                    self.assertEqual((await db.itens_na_bolsa(conn, ids[102])).get("pocao_vida"), 1)


if __name__ == "__main__":
    unittest.main()
