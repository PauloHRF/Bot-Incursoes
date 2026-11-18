"""A fronteira entre as regras do combate e o cog do Discord.

As regras saíram de `src/cogs/incursao.py` em fatias, para dentro de
`src/combate/`: a mesa (onde a run está, quem joga, a fila), os botões de
ação, o fluxo do combate e os resolvedores das habilidades. Juntos eles são o
`Combate`, que não fala com o Discord: tudo o que ele precisa dizer, diz por
uma PORTA que quem o herda implementa — o cog com mensagem, a bancada da
simulação calada.

O que este arquivo cobra é a FORMA dessa separação, que nenhum teste de jogo
vê:

- cada módulo só pede de fora o que declarou em `DA_MESA`, nem mais nem
  menos, e `PORTAS` é a soma delas. O que um módulo do combate usa do outro
  não entra: isso fica dentro de `src/combate`;
- o cog implementa todas as portas, e a bancada também — ela herda o
  `Combate`, e não o cog;
- os módulos não falam com o Discord nem importam o cog, senão a separação é
  só de arquivo;
- cada método existe num lugar só. Um de mesmo nome deixado no cog passaria
  por cima do módulo sem erro nenhum, e as duas cópias divergiriam;
- quem sobrescreve um método continua sendo ouvido. É por isso que se herda o
  `Combate` em vez de guardar um objeto com ele: a bancada mede o combate
  sobrescrevendo métodos chamados de dentro dele (`_versao_da_habilidade`,
  por `_resolver_grupo`; `_resolver_turno`, pelo `_avancar`).
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
from src import combate  # noqa: E402
from src.combate import PORTAS, Combate, acoes, fluxo, mesa, resolvedores  # noqa: E402
from src.cogs.incursao import Incursoes  # noqa: E402
from tools.simulacao.execucao import _Combate as Bancada  # noqa: E402

PASTA = RAIZ / "src" / "combate"
# modulo -> (arquivo, classe)
MODULOS = {
    mesa: (PASTA / "mesa.py", mesa.Mesa),
    acoes: (PASTA / "acoes.py", acoes.Acoes),
    fluxo: (PASTA / "fluxo.py", fluxo.Fluxo),
    resolvedores: (PASTA / "resolvedores.py", resolvedores.Resolvedores),
}


def _no_da_classe(arquivo: Path, nome: str) -> ast.ClassDef:
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    return next(n for n in arvore.body if isinstance(n, ast.ClassDef) and n.name == nome)


def _definidos(no: ast.ClassDef) -> set[str]:
    """Métodos, constantes da classe, e o que algum método grava em `self`."""
    nomes = set()
    for item in no.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            nomes.add(item.name)
        elif isinstance(item, ast.Assign):
            nomes.update(t.id for t in item.targets if isinstance(t, ast.Name))
    for n in ast.walk(no):
        if (isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store)
                and isinstance(n.value, ast.Name) and n.value.id == "self"):
            nomes.add(n.attr)
    return nomes


def _metodos(no: ast.ClassDef) -> set[str]:
    return {i.name for i in no.body if isinstance(i, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _do_combate() -> set[str]:
    """Tudo o que alguma classe de `src/combate` define."""
    saida = set()
    for arquivo, classe in MODULOS.values():
        saida |= _definidos(_no_da_classe(arquivo, classe.__name__))
    return saida


def caso_cada_modulo_so_pede_o_que_declarou():
    do_combate = _do_combate()
    todos = set()
    for modulo, (arquivo, classe) in MODULOS.items():
        no = _no_da_classe(arquivo, classe.__name__)
        usados = {
            n.attr for n in ast.walk(no)
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
            and n.value.id == "self"
        }
        pedidos = usados - do_combate
        todos |= pedidos
        nome = arquivo.name
        a_mais = pedidos - set(modulo.DA_MESA)
        assert not a_mais, (
            f"{nome} passou a usar de fora {sorted(a_mais)} sem declarar em DA_MESA"
        )
        sobra = set(modulo.DA_MESA) - pedidos
        assert not sobra, f"{nome}: DA_MESA declara {sorted(sobra)}, que ele nao pede mais"
        print(f"  {nome} pede de fora so as {len(modulo.DA_MESA)} portas que declarou: ok")
    assert set(PORTAS) == todos, (set(PORTAS) ^ todos)
    print(f"  PORTAS e a soma delas: {len(PORTAS)} portas, todas de saida: ok")


def caso_o_cog_e_a_bancada_implementam_as_portas():
    do_combate = _do_combate()
    dentro = sorted(set(PORTAS) & do_combate)
    assert not dentro, f"PORTAS pede {dentro}, que ja mora em src/combate"
    # Implementada na PROPRIA classe: herdada de outro lugar nao conta, porque
    # o combate nao define porta nenhuma — se nao esta ali, o primeiro caminho
    # que a usar levanta AttributeError no meio da fila.
    sem_no_cog = sorted(p for p in PORTAS if p not in vars(Incursoes))
    assert not sem_no_cog, f"o cog nao implementa as portas {sem_no_cog}"
    sem_na_bancada = sorted(p for p in PORTAS if p not in vars(Bancada))
    assert not sem_na_bancada, f"a bancada da simulacao nao implementa as portas {sem_na_bancada}"
    print(f"  o cog e a bancada implementam as {len(PORTAS)} portas: ok")


def caso_a_bancada_nao_herda_o_cog():
    assert issubclass(Bancada, Combate)
    assert not issubclass(Bancada, Incursoes), "a bancada voltou a herdar o cog do Discord"
    execucao = RAIZ / "tools" / "simulacao" / "execucao.py"
    arvore = ast.parse(execucao.read_text(encoding="utf-8"))
    importados = [no.module or "" for no in ast.walk(arvore) if isinstance(no, ast.ImportFrom)]
    importados += [a.name for no in ast.walk(arvore) if isinstance(no, ast.Import) for a in no.names]
    do_discord = [m for m in importados if "cogs" in m or m.split(".")[0] == "discord"]
    assert not do_discord, f"a bancada importa {do_discord}"
    print("  a bancada herda o Combate, e nao o cog nem o discord: ok")


def caso_os_modulos_nao_falam_com_o_discord():
    arquivos = [arquivo for arquivo, _c in MODULOS.values()] + [PASTA / "__init__.py"]
    for arquivo in arquivos:
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
        assert issubclass(Combate, classe) and issubclass(Incursoes, classe), classe
        metodos = _metodos(_no_da_classe(arquivo, classe.__name__))
        repetidos = sorted(n for n in metodos - {"__init__"} if n in vars(Incursoes))
        assert not repetidos, (
            f"o cog redefine {repetidos}: a copia dele passa por cima da de {arquivo.name}"
        )
        em_dois = sorted(n for n in metodos if n in vistos)
        assert not em_dois, f"{em_dois} esta em {arquivo.name} e em {vistos[em_dois[0]]}"
        for nome in metodos:
            vistos[nome] = arquivo.name
            if nome != "__init__":
                # O cog responde pelo nome de antes, que testes e simulacao usam.
                assert getattr(Incursoes, nome) is getattr(classe, nome), nome
    print(f"  os {len(vistos)} metodos do combate moram num lugar so, e o cog os herda: ok")


async def caso_as_sobrescritas_sao_ouvidas():
    """A bancada mede o combate por sobrescrita — de dentro do combate.

    `_versao_da_habilidade` é chamada pelos resolvedores; é por ela que a
    bancada sabe quanto THP a melhoria do xamã cobrou. `_resolver_turno` é
    chamada pelo `_avancar`; é por ela que a bancada sabe que habilidade saiu.
    """
    from src.incursoes import Monstro
    from tools.simulacao.execucao import Bancada as Mesa, Ficha

    habilidade = classes.POR_ID["guerreiros_ancioes"]
    custo = habilidade.acao["melhoria"]["custo_thp"]
    with aleatorio.usar(random.Random(1)):
        async with Mesa([Ficha("xama", 10)], [Monstro("Alvo", 1, 0, "1d1", 1000)]) as b:
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
        "`_resolver_turno` deixou de ser chamada pelo `_avancar`"
    )
    print(f"  as sobrescritas da bancada sao ouvidas ({gasto} de THP, {habilidade.nome}): ok")


def caso_o_combate_sobe_sem_o_cog():
    """`Combate(bot)` monta o estado que a fila e o log usam, sem Discord."""
    c = Combate(SimpleNamespace(db=None))
    assert c.incursoes == {} and c.bancos == {}
    assert c._trava(1) is c._trava(1), "a trava da run tem de ser a mesma a cada pedido"
    c._registrar({"id": 1}, 1, ["linha"])
    assert c._registros[1]["linhas"] == ["linha"]
    assert combate.Combate is Combate
    print("  o Combate sobe sozinho, com a trava e o log da mesa: ok")


def main():
    caso_cada_modulo_so_pede_o_que_declarou()
    caso_o_cog_e_a_bancada_implementam_as_portas()
    caso_a_bancada_nao_herda_o_cog()
    caso_os_modulos_nao_falam_com_o_discord()
    caso_cada_metodo_mora_num_lugar_so()
    caso_o_combate_sobe_sem_o_cog()
    asyncio.run(caso_as_sobrescritas_sao_ouvidas())
    print("TESTES DA FRONTEIRA DO COMBATE PASSARAM")


if __name__ == "__main__":
    main()
