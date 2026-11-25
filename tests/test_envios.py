"""O envio pelo Discord: quem mexe em quê, e o que entra no catálogo.

O que estes casos protegem, e que não é óbvio:

1. **O repositório é intocável.** Nem com o mesmo código: dungeon e sala de
   `data/` não mudam por envio.
2. **Cada autor mexe só no que ele mesmo enviou.** O segundo autor que usa o
   código do primeiro é recusado — senão o envio dele apagaria o trabalho do
   outro sem ninguém ver.
3. **O que uma run em andamento usa não muda**, e o que é só novo passa
   sempre. Reenviar igual não conta como mudança, e por isso não esbarra na
   run.
4. **Envio só acrescenta.** A sala que ficou fora do arquivo reenviado
   continua no bot.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import envios as V, incursoes as I, pacotes as P  # noqa: E402

ORG = "Vórtice Oculto"
CRIATURA = {"nome": "Coisa", "ca": 13, "ataque": 4, "dano": "1d6", "hp": 12}
AUTORA, OUTRO = 111, 222


def sala(sala_id, temas=None, **extra):
    base = {"id": sala_id, "nome": f"Sala {sala_id}", "tipo": "Evento",
            "descricao": "Uma porta.", "dificuldade": "Média", "cd": 13,
            "alvo_progresso": 3, "pericias": ["Investigação"]}
    if temas:
        base["temas"] = temas
    base.update(extra)
    return base


def dungeon(dungeon_id="nova", **extra):
    base = {"id": dungeon_id, "nome": f"Dungeon {dungeon_id}", "organizacao": ORG,
            "tamanho": "Curta", "tier": 2, "lore_inicial": "Era uma vez.",
            "recompensa_mes": 10,
            "objetivo": {"id": "OBJ", "nome": "Fim", "tipo": "Combate",
                         "descricao": "O chefe.", "monstros": [dict(CRIATURA)]}}
    base.update(extra)
    return base


# Com tema: sala sem tema entra em qualquer filtro, e o caso da dungeon de
# água passaria com elas.
BANCOS = {ORG: I.banco_de_dict({"organizacao": ORG,
                                "salas": [sala(f"VO{n:02d}", temas=["arcano"])
                                          for n in range(1, 7)]})}
REPOSITORIO = {"do_repo"}


def planejar(pacote, autor=AUTORA, enviados=(), em_uso=V.EmUso()):
    return V.planejar(pacote, autor_id=autor, incursoes_do_repositorio=REPOSITORIO,
                      bancos_do_repositorio=BANCOS, enviados=list(enviados), em_uso=em_uso)


def gravados(plano):
    return [(e.tipo, e.id) for e in plano.gravar]


def caso_um_envio_novo_entra():
    p = planejar(P.novo(ORG, dungeon(), [sala("VO-A1")]))
    assert p.aprovado, p.problemas
    assert gravados(p) == [("sala", "VO-A1"), ("incursao", "nova")], gravados(p)
    assert p.novas and not p.atualizadas
    assert all(e.autor_id == AUTORA and e.organizacao == ORG for e in p.gravar)
    print("  um envio novo entra, com dono e Organização: ok")


def caso_o_repositorio_e_intocavel():
    p = planejar(P.novo(ORG, dungeon("do_repo")))
    assert not p.aprovado and any("repositório" in x for x in p.problemas), p.problemas
    assert not p.gravar
    p = planejar(P.novo(ORG, None, [sala("VO01")]))
    assert not p.aprovado and any("VO01" in x for x in p.problemas), p.problemas
    print("  dungeon e sala do repositório não mudam por envio: ok")


def caso_so_o_dono_atualiza():
    ja = [V.Enviado("incursao", ORG, "nova", OUTRO, dungeon()),
          V.Enviado("sala", ORG, "VO-A1", OUTRO, sala("VO-A1"))]
    p = planejar(P.novo(ORG, dungeon(nome="Minha versão")), enviados=ja)
    assert not p.aprovado and any("outra pessoa" in x for x in p.problemas), p.problemas
    p = planejar(P.novo(ORG, None, [sala("VO-A1", nome="Outra")]), enviados=ja)
    assert not p.aprovado and any("outra pessoa" in x for x in p.problemas), p.problemas
    # E o dono atualiza: a sala dele não conta como código repetido.
    meus = [V.Enviado(e.tipo, e.organizacao, e.id, AUTORA, e.dados) for e in ja]
    p = planejar(P.novo(ORG, dungeon(nome="Minha versão"), [sala("VO-A1", nome="Nova")]),
                 enviados=meus)
    assert p.aprovado, p.problemas
    assert sorted(gravados(p)) == [("incursao", "nova"), ("sala", "VO-A1")]
    assert len(p.atualizadas) == 2 and not p.novas, (p.novas, p.atualizadas)
    print("  só quem enviou atualiza o que enviou: ok")


def caso_o_que_a_run_usa_nao_muda():
    meus = [V.Enviado("incursao", ORG, "nova", AUTORA, dungeon()),
            V.Enviado("sala", ORG, "VO-A1", AUTORA, sala("VO-A1"))]
    em_uso = V.EmUso(incursoes=frozenset({"nova"}), salas=frozenset({(ORG, "VO-A1")}))
    p = planejar(P.novo(ORG, dungeon(nome="Mudou")), enviados=meus, em_uso=em_uso)
    assert not p.aprovado and any("run em andamento" in x for x in p.problemas), p.problemas
    p = planejar(P.novo(ORG, None, [sala("VO-A1", nome="Mudou")]), enviados=meus, em_uso=em_uso)
    assert not p.aprovado and any("run em andamento" in x for x in p.problemas), p.problemas
    # O que é só novo passa, mesmo com a run andando.
    p = planejar(P.novo(ORG, None, [sala("VO-A2")]), enviados=meus, em_uso=em_uso)
    assert p.aprovado and gravados(p) == [("sala", "VO-A2")], p.problemas
    # E reenviar igual não é mudança: nada a gravar, nada a recusar.
    p = planejar(P.novo(ORG, dungeon(), [sala("VO-A1")]), enviados=meus, em_uso=em_uso)
    assert p.aprovado and not p.gravar and len(p.iguais) == 2, (p.problemas, p.iguais)
    print("  o que a run usa não muda, e o novo passa: ok")


def caso_um_problema_nao_grava_metade():
    meus = [V.Enviado("sala", ORG, "VO-A1", AUTORA, sala("VO-A1"))]
    em_uso = V.EmUso(salas=frozenset({(ORG, "VO-A1")}))
    p = planejar(P.novo(ORG, None, [sala("VO-A2"), sala("VO-A1", nome="Mudou")]),
                 enviados=meus, em_uso=em_uso)
    assert not p.aprovado and not p.gravar, "gravou a sala nova e recusou a outra"
    print("  com um problema, nada do arquivo entra: ok")


def caso_a_sala_fora_do_reenvio_continua():
    meus = [V.Enviado("sala", ORG, "VO-A1", AUTORA, sala("VO-A1"))]
    p = planejar(P.novo(ORG, None, [sala("VO-A2")]), enviados=meus)
    assert p.aprovado and gravados(p) == [("sala", "VO-A2")], p.problemas
    _, bancos, _ = V.mesclar({}, BANCOS, meus + p.gravar)
    assert {"VO-A1", "VO-A2"} <= {s.id for s in bancos[ORG].salas}
    print("  a sala que ficou fora do reenvio continua no bot: ok")


def caso_a_dungeon_conta_com_as_salas_enviadas_antes():
    filtrada = dungeon(filtro={"temas": ["agua"]})
    p = planejar(P.novo(ORG, filtrada))
    assert not p.aprovado, "a dungeon de água passou sem sala de água"
    antes = [V.Enviado("sala", ORG, f"VO-N{n}", OUTRO, sala(f"VO-N{n}", temas=["agua"]))
             for n in range(1, 4)]
    p = planejar(P.novo(ORG, filtrada), enviados=antes)
    assert p.aprovado, p.problemas
    print("  a dungeon conta com as salas enviadas antes, de qualquer autor: ok")


def caso_o_catalogo_junta_e_o_repositorio_ganha():
    repo = {"do_repo": I.de_dict(dungeon("do_repo"))}
    enviados = [
        V.Enviado("incursao", ORG, "nova", AUTORA, dungeon()),
        V.Enviado("incursao", ORG, "do_repo", AUTORA, dungeon("do_repo", nome="Impostora")),
        V.Enviado("sala", ORG, "VO-A1", AUTORA, sala("VO-A1")),
        V.Enviado("sala", ORG, "VO01", AUTORA, sala("VO01", nome="Impostora")),
        V.Enviado("sala", ORG, "VO-TORTA", AUTORA, {"id": "VO-TORTA"}),
    ]
    incursoes, bancos, problemas = V.mesclar(repo, BANCOS, enviados)
    assert set(incursoes) == {"do_repo", "nova"}
    assert incursoes["do_repo"].nome == "Dungeon do_repo", "o enviado tomou o lugar do repositório"
    ids = [s.id for s in bancos[ORG].salas]
    assert ids.count("VO01") == 1 and bancos[ORG].sala("VO01").nome == "Sala VO01"
    assert "VO-A1" in ids and "VO-TORTA" not in ids
    assert len(problemas) == 3, problemas
    # O repositório que entrou não foi alterado no lugar.
    assert "VO-A1" not in {s.id for s in BANCOS[ORG].salas}
    print("  o catálogo junta o enviado e o repositório ganha: ok")


for caso in (
    caso_um_envio_novo_entra,
    caso_o_repositorio_e_intocavel,
    caso_so_o_dono_atualiza,
    caso_o_que_a_run_usa_nao_muda,
    caso_um_problema_nao_grava_metade,
    caso_a_sala_fora_do_reenvio_continua,
    caso_a_dungeon_conta_com_as_salas_enviadas_antes,
    caso_o_catalogo_junta_e_o_repositorio_ganha,
):
    caso()

print("TESTES DO ENVIO PASSARAM")
