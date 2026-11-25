"""O arquivo do Estúdio: a dungeon e as salas novas, conferidas pela régua do bot.

O que estes casos protegem, e que não é óbvio:

1. **O arquivo se declara.** Uma incursão solta e um banco também parecem
   arquivo de conteúdo; quem decide que é do Estúdio é a chave `formato`, e
   uma versão mais nova do que quem lê é recusada em vez de lida pela metade.
2. **O tier é obrigatório aqui.** No arquivo da incursão a falta dele vale 5,
   "aberta a todos" — no arquivo de quem escreve agora, isso seria uma
   dungeon de tier 5 por esquecimento.
3. **As salas novas contam no filtro.** Uma dungeon que traz as próprias salas
   não pode ser recusada por falta delas.
4. **Nada no arquivo toma o lugar do que já existe.** Código de dungeon
   ocupado e id de sala que o banco já usa são recusados.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import incursoes as I, pacotes as P  # noqa: E402

ORG = "Vórtice Oculto"
CRIATURA = {"nome": "Coisa", "ca": 13, "ataque": 4, "dano": "1d6", "hp": 12}


def sala(sala_id, tipo="Evento", temas=None, **extra):
    base = {"id": sala_id, "nome": f"Sala {sala_id}", "tipo": tipo, "descricao": "Uma porta."}
    if tipo == "Combate":
        base["monstros"] = [dict(CRIATURA)]
    else:
        base.update(dificuldade="Média", cd=13, alvo_progresso=3, pericias=["Investigação"])
    if temas:
        base["temas"] = temas
    base.update(extra)
    return base


def banco(quantas=8, temas=None):
    return I.banco_de_dict({
        "organizacao": ORG,
        "salas": [sala(f"VO{n:02d}", temas=temas) for n in range(1, quantas + 1)],
    })


def dungeon(**extra):
    base = {
        "id": "minha_dungeon", "nome": "Minha Dungeon", "organizacao": ORG,
        "tamanho": "Curta", "tier": 2, "lore_inicial": "Era uma vez.",
        "recompensa_mes": 10,
        "objetivo": {"id": "OBJ", "nome": "O Fim", "tipo": "Combate",
                     "descricao": "O chefe.", "monstros": [dict(CRIATURA)]},
    }
    base.update(extra)
    return base


def conferir(pacote, bancos=None, ocupadas=()):
    return P.conferir(pacote, {ORG: banco()} if bancos is None else bancos, ocupadas)


def caso_um_arquivo_certo_passa():
    r = conferir(P.novo(ORG, dungeon()))
    assert r.aprovado, r.problemas
    assert r.incursao.id == "minha_dungeon" and r.salas == []
    print("  uma dungeon certa passa: ok")


def caso_o_arquivo_se_declara():
    assert not conferir(dungeon()).aprovado, "incursão solta passou por arquivo do Estúdio"
    assert not conferir({"organizacao": ORG, "salas": []}).aprovado
    mais_nova = {**P.novo(ORG, dungeon()), "versao": P.VERSAO + 1}
    r = conferir(mais_nova)
    assert r.problemas and "versão" in r.problemas[0], r.problemas
    sem_versao = {k: v for k, v in P.novo(ORG, dungeon()).items() if k != "versao"}
    assert not conferir(sem_versao).aprovado
    print("  o arquivo se declara pelo formato e pela versão: ok")


def caso_o_tier_e_obrigatorio_no_arquivo_do_estudio():
    sem = dungeon()
    del sem["tier"]
    # Sozinha, a incursão sem tier é válida (vale 5): a regra é deste arquivo.
    I.de_dict(sem)
    r = conferir(P.novo(ORG, sem))
    assert any("tier" in p for p in r.problemas), r.problemas
    r = conferir(P.novo(ORG, dungeon(tier=None)))
    assert any("tier" in p for p in r.problemas), r.problemas
    print("  o tier é obrigatório no arquivo do Estúdio: ok")


def caso_os_problemas_da_dungeon_sao_os_do_bot():
    r = conferir(P.novo(ORG, dungeon(nome="", lore_inicial="")))
    assert "A incursão precisa de um nome." in r.problemas, r.problemas
    assert any("lore" in p for p in r.problemas), r.problemas
    # A sala final é "a sala do chefe" para quem escreve, e não o nome do campo.
    sem_texto = dungeon()
    sem_texto["objetivo"]["descricao"] = ""
    r = conferir(P.novo(ORG, sem_texto))
    assert any(p.startswith("sala do chefe:") for p in r.problemas), r.problemas
    assert not any("objetivo (sala" in p for p in r.problemas), r.problemas
    print("  os problemas da dungeon vêm do validador do bot: ok")


def caso_a_organizacao_do_arquivo_e_a_da_dungeon():
    r = conferir(P.novo("Guilda dos Mortos", dungeon()),
                 bancos={ORG: banco(), "Guilda dos Mortos": banco()})
    assert any("mas o arquivo é de" in p for p in r.problemas), r.problemas
    assert not conferir(P.novo("Ninguém", dungeon())).aprovado
    print("  a Organização do arquivo é a da dungeon: ok")


def caso_codigo_ocupado_e_recusado():
    r = conferir(P.novo(ORG, dungeon()), ocupadas={"minha_dungeon"})
    assert any("minha_dungeon" in p for p in r.problemas), r.problemas
    print("  código de dungeon ocupado é recusado: ok")


def caso_sem_banco_da_organizacao_e_recusado():
    r = conferir(P.novo(ORG, dungeon()), bancos={})
    assert any("banco de salas" in p for p in r.problemas), r.problemas
    print("  dungeon sem banco da Organização é recusada: ok")


def caso_as_salas_novas_contam_no_filtro():
    # O banco tem 8 salas sem o tema; a Curta precisa de 3 com ele.
    filtrada = dungeon(filtro={"temas": ["cripta"]})
    bancos = {ORG: banco(temas=["agua"])}
    r = conferir(P.novo(ORG, filtrada), bancos)
    assert not r.aprovado, "o filtro sem sala nenhuma passou"
    novas = [sala(f"NV{n}", temas=["cripta"]) for n in range(1, 4)]
    r = conferir(P.novo(ORG, filtrada, novas), bancos)
    assert r.aprovado, r.problemas
    assert [s.id for s in r.salas] == ["NV1", "NV2", "NV3"]
    print("  as salas novas entram na conta do filtro: ok")


def caso_sala_do_arquivo_nao_toma_id_nem_repete():
    r = conferir(P.novo(ORG, dungeon(), [sala("VO01")]))
    assert any("VO01" in p and "já existe" in p for p in r.problemas), r.problemas
    r = conferir(P.novo(ORG, dungeon(), [sala("NV1"), sala("NV1")]))
    assert any("duas vezes" in p for p in r.problemas), r.problemas
    r = conferir(P.novo(ORG, dungeon(), [sala("NV1", tipo="Combate", monstros=[])]))
    assert any(p.startswith("sala NV1:") for p in r.problemas), r.problemas
    print("  sala do arquivo não repete nem toma id do banco: ok")


def caso_arquivo_so_de_salas_e_vazio():
    r = conferir(P.novo(ORG, None, [sala("NV1")]))
    assert r.aprovado and r.incursao is None, r.problemas
    r = conferir(P.novo(ORG))
    assert not r.aprovado, "arquivo sem dungeon e sem sala passou"
    print("  arquivo só de salas passa, e vazio não: ok")


for caso in (
    caso_um_arquivo_certo_passa,
    caso_o_arquivo_se_declara,
    caso_o_tier_e_obrigatorio_no_arquivo_do_estudio,
    caso_os_problemas_da_dungeon_sao_os_do_bot,
    caso_a_organizacao_do_arquivo_e_a_da_dungeon,
    caso_codigo_ocupado_e_recusado,
    caso_sem_banco_da_organizacao_e_recusado,
    caso_as_salas_novas_contam_no_filtro,
    caso_sala_do_arquivo_nao_toma_id_nem_repete,
    caso_arquivo_so_de_salas_e_vazio,
):
    caso()

print("TESTES DO ARQUIVO DO ESTUDIO PASSARAM")
