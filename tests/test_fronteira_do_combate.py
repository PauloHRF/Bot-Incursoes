"""A fronteira entre as regras do combate e o cog do Discord.

As regras estão saindo de `src/cogs/incursao.py` em fatias, para dentro de
`src/combate/`: primeiro os resolvedores de habilidade, depois o fluxo do
combate. O que este arquivo cobra é a FORMA dessa separação, que nenhum teste
de jogo vê:

- cada módulo só pede ao cog o que declarou em `DA_MESA`, nem mais nem menos —
  é a lista que a simulação vai ter de oferecer quando deixar de herdar o cog,
  e ela não pode crescer calada. O que um módulo do combate usa do outro não
  entra: isso fica dentro de `src/combate`;
- os módulos não falam com o Discord nem importam o cog, senão a separação é
  só de arquivo;
- cada método existe num lugar só. Um de mesmo nome deixado no cog passaria
  por cima do módulo sem erro nenhum, e as duas cópias divergiriam;
- quem sobrescreve um método continua sendo ouvido. É por isso que o cog
  HERDA as classes do combate em vez de guardar objetos com elas: a simulação
  mede o combate sobrescrevendo métodos que são chamados de dentro dos
  módulos (`_versao_da_habilidade`, por `_resolver_grupo`) e de dentro do cog
  (`_resolver_turno`, por `_avancar`).
"""
from __future__ import annotations

import ast
import asyncio
import random
import sys
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src import aleatorio, classes, database as db  # noqa: E402
from src.combate import fluxo, resolvedores  # noqa: E402
from src.cogs.incursao import Incursoes  # noqa: E402

PASTA = RAIZ / "src" / "combate"
# modulo -> (arquivo, classe)
MODULOS = {
    resolvedores: (PASTA / "resolvedores.py", resolvedores.Resolvedores),
    fluxo: (PASTA / "fluxo.py", fluxo.Fluxo),
}


def _no_da_classe(arquivo: Path, nome: str) -> ast.ClassDef:
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    return next(n for n in arvore.body if isinstance(n, ast.ClassDef) and n.name == nome)


def _definidos(no: ast.ClassDef) -> set[str]:
    nomes = set()
    for item in no.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            nomes.add(item.name)
        elif isinstance(item, ast.Assign):
            nomes.update(t.id for t in item.targets if isinstance(t, ast.Name))
    return nomes


def _do_combate() -> set[str]:
    """Tudo o que alguma classe de `src/combate` define."""
    saida = set()
    for arquivo, classe in MODULOS.values():
        saida |= _definidos(_no_da_classe(arquivo, classe.__name__))
    return saida


def caso_cada_modulo_so_pede_o_que_declarou():
    do_combate = _do_combate()
    for modulo, (arquivo, classe) in MODULOS.items():
        no = _no_da_classe(arquivo, classe.__name__)
        usados = {
            n.attr for n in ast.walk(no)
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
            and n.value.id == "self"
        }
        pedidos = usados - do_combate
        nome = arquivo.name
        a_mais = pedidos - set(modulo.DA_MESA)
        assert not a_mais, (
            f"{nome} passou a usar do cog {sorted(a_mais)} sem declarar em DA_MESA"
        )
        sobra = set(modulo.DA_MESA) - pedidos
        assert not sobra, f"{nome}: DA_MESA declara {sorted(sobra)}, que ele nao pede mais ao cog"
        print(f"  {nome} pede ao cog so as {len(modulo.DA_MESA)} coisas que declarou: ok")


def caso_o_cog_oferece_o_que_os_modulos_pedem():
    cog = Incursoes(SimpleNamespace(db=None))
    do_combate = _do_combate()
    pedidos = set()
    for modulo in MODULOS:
        pedidos |= set(modulo.DA_MESA)
    faltam = sorted(n for n in pedidos if not hasattr(cog, n))
    assert not faltam, f"o cog nao tem o que o combate pede: {faltam}"
    # O que se pede ao cog tem de ser DO cog. Se um modulo do combate passou a
    # definir, o nome saiu da lista de quem pede e ficou esquecido nela.
    dentro = sorted(pedidos & do_combate)
    assert not dentro, f"DA_MESA pede ao cog {dentro}, que ja mora em src/combate"
    print(f"  o cog tem as {len(pedidos)} coisas que o combate pede, e so o cog as tem: ok")


def caso_os_modulos_nao_falam_com_o_discord():
    for arquivo, _classe in MODULOS.values():
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        importados = []
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                importados += [a.name for a in no.names]
            elif isinstance(no, ast.ImportFrom):
                importados.append(("." * no.level) + (no.module or ""))
        proibidos = [m for m in importados if m.split(".")[0] == "discord" or "cogs" in m]
        assert not proibidos, f"{arquivo.name} importa {proibidos}"
    print("  os modulos do combate nao importam o discord nem o cog: ok")


def caso_cada_metodo_mora_num_lugar_so():
    vistos: dict[str, str] = {}
    for arquivo, classe in MODULOS.values():
        assert issubclass(Incursoes, classe), classe
        metodos = {n for n in _definidos(_no_da_classe(arquivo, classe.__name__))
                   if callable(getattr(classe, n))}
        repetidos = sorted(n for n in metodos if n in vars(Incursoes))
        assert not repetidos, (
            f"o cog redefine {repetidos}: a copia dele passa por cima da de {arquivo.name}"
        )
        em_dois = sorted(n for n in metodos if n in vistos)
        assert not em_dois, f"{em_dois} esta em {arquivo.name} e em {vistos[em_dois[0]]}"
        for nome in metodos:
            vistos[nome] = arquivo.name
            # O cog ainda responde pelo nome de antes, que testes e simulacao usam.
            assert getattr(Incursoes, nome) is getattr(classe, nome), nome
    print(f"  os {len(vistos)} metodos do combate moram num lugar so, e o cog os herda: ok")


async def caso_as_sobrescritas_sao_ouvidas():
    """A bancada mede o combate por sobrescrita — de dentro e de fora dos módulos.

    `_versao_da_habilidade` é chamada de dentro dos resolvedores; é por ela que
    a bancada sabe quanto THP a melhoria do xamã cobrou. `_resolver_turno` é
    chamada pelo `_avancar` do cog; é por ela que a bancada sabe que habilidade
    saiu.
    """
    from src.incursoes import Monstro
    from tools.simulacao.execucao import Bancada, Ficha

    habilidade = classes.POR_ID["guerreiros_ancioes"]
    custo = habilidade.acao["melhoria"]["custo_thp"]
    with aleatorio.usar(random.Random(1)):
        async with Bancada([Ficha("xama", 10)], [Monstro("Alvo", 1, 0, "1d1", 1000)]) as b:
            await b.iniciar()
            await db.definir_thp(b.conn, b.run_id, 1, custo + 5)
            await b.agir(1, habilidade.id)
            gasto = b.cog.metricas["thp_gasto"]
            usadas = dict(b.cog.habilidades)
    assert gasto == custo, (
        f"a bancada mediu {gasto} de THP gasto, e a melhoria cobra {custo}: a "
        "sobrescrita de `_versao_da_habilidade` deixou de ser chamada por dentro"
    )
    assert usadas.get(habilidade.nome, {}).get("usos") == 1, (
        f"a bancada nao viu {habilidade.nome} sair ({usadas}): a sobrescrita de "
        "`_resolver_turno` deixou de ser chamada pelo cog"
    )
    print(f"  as sobrescritas da bancada sao ouvidas ({gasto} de THP, {habilidade.nome}): ok")


def main():
    caso_cada_modulo_so_pede_o_que_declarou()
    caso_o_cog_oferece_o_que_os_modulos_pedem()
    caso_os_modulos_nao_falam_com_o_discord()
    caso_cada_metodo_mora_num_lugar_so()
    asyncio.run(caso_as_sobrescritas_sao_ouvidas())
    print("TESTES DA FRONTEIRA DO COMBATE PASSARAM")


if __name__ == "__main__":
    main()
