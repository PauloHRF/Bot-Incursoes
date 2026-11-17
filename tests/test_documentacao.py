"""A documentação acompanha o código — e quando não acompanha, fica vermelho.

O README é escrito à mão, e foi envelhecendo calado: listava cinco comandos que
tinham saído, dava sete classes como "previstas" quando as 14 já jogavam,
contava dez incursões quando havia quinze, e mandava o jogador para um
`/incursao habilidade` que não existia mais. Nada disso quebrava teste nenhum.

O que dá para conferir contra o código é conferido aqui:

- a tabela de comandos do README contra a árvore que o bot registra;
- nenhum documento manda rodar comando que não existe;
- o catálogo de incursões do README contra `data/incursoes/`;
- as docs geradas (`FICHAS.md`, `docs/mecanicas/`) contra o que o gerador
  produz hoje. O `CRIATURAS.md` já tem o seu, em `test_bestiario.py`.

O resto do README é texto, e texto não tem teste. Mas o que tem número que o
código sabe, o código confere.
"""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tools"))

from discord import app_commands  # noqa: E402

from src import config, database as db, incursoes as I  # noqa: E402

README = RAIZ / "README.md"
BANCO = Path(__file__).resolve().parent / "teste_documentacao.db"


async def _comandos() -> dict[str, bool]:
    """{"/grupo nome": é de admin} — o que o bot registra de verdade."""
    from src.main import COGS, IncursoesBot

    config.DB_PATH = BANCO
    BANCO.unlink(missing_ok=True)
    bot = IncursoesBot()
    bot.db = await db.conectar()
    await db.criar_schema(bot.db)
    try:
        for cog in COGS:
            await bot.load_extension(cog)
        saida = {}
        for c in bot.tree.walk_commands():
            if isinstance(c, app_commands.Group):
                continue
            permissoes = c.default_permissions or (
                c.parent.default_permissions if c.parent else None
            )
            saida["/" + c.qualified_name] = bool(permissoes and permissoes.manage_guild)
        for cog in COGS:
            await bot.unload_extension(cog)
        return saida
    finally:
        await bot.db.close()
        await bot.close()
        BANCO.unlink(missing_ok=True)


def _tabela(texto: str, cabecalho: str) -> list[list[str]]:
    """As linhas de uma tabela Markdown, a partir do cabeçalho, sem o separador."""
    linhas = texto.splitlines()
    inicio = next(i for i, l in enumerate(linhas) if l.startswith(cabecalho))
    saida = []
    for linha in linhas[inicio + 2:]:
        if not linha.startswith("|"):
            break
        saida.append([c.strip() for c in linha.strip().strip("|").split("|")])
    return saida


def caso_a_tabela_de_comandos_e_a_do_bot(comandos: dict[str, bool]):
    """Cada comando registrado tem linha, nenhuma linha é de comando que saiu,
    e o `(admin)` da linha diz a verdade sobre a permissão."""
    linhas = _tabela(README.read_text(encoding="utf-8"), "| Comando | Função |")
    no_readme: dict[str, bool] = {}
    for comando, funcao in linhas:
        # O nome vai até o primeiro parâmetro: `/help [comando]` e
        # `/ficha ver [personagem]` têm uma e duas palavras de nome.
        partes = comando.strip("`").split()
        nome = " ".join(p for p in partes if not p.startswith(("<", "[")))
        no_readme[nome] = funcao.startswith("(admin)")

    faltam = sorted(set(comandos) - set(no_readme))
    sobram = sorted(set(no_readme) - set(comandos))
    assert not faltam, f"comandos do bot sem linha no README: {faltam}"
    assert not sobram, f"o README lista comandos que nao existem: {sobram}"
    errados = sorted(
        nome for nome in comandos if comandos[nome] != no_readme[nome]
    )
    assert not errados, (
        "o (admin) do README nao bate com a permissao do comando: "
        + ", ".join(f"{n} ({'admin' if comandos[n] else 'de todos'})" for n in errados)
    )
    print(f"  a tabela do README tem os {len(comandos)} comandos do bot, e so eles: ok")


def caso_nenhum_documento_cita_comando_que_saiu(comandos: dict[str, bool]):
    """O README e os docs não mandam ninguém rodar comando que não existe.

    O par do teste de mesmo espírito em `test_ajuda_feedback.py`, que olha o
    que o BOT diz. Este olha o que a documentação diz — e era ali que estavam
    os seis: a tabela e o `/incursao habilidade` das ativas.
    """
    padrao = re.compile(r"/(?:ficha|incursao|mercado|organizacao|config) \w+")
    arquivos = [README, RAIZ / "deploy" / "README.md", *sorted((RAIZ / "docs").rglob("*.md"))]
    mortos = []
    for arquivo in arquivos:
        for numero, linha in enumerate(arquivo.read_text(encoding="utf-8").splitlines(), 1):
            for citado in padrao.findall(linha):
                if citado not in comandos:
                    mortos.append(f"{arquivo.relative_to(RAIZ)}:{numero}: {citado}")
    assert not mortos, "documentacao citando comando que nao existe:\n" + "\n".join(mortos)
    print(f"  nenhum dos {len(arquivos)} documentos cita comando que saiu: ok")


def caso_o_catalogo_de_incursoes_e_o_de_data():
    """Toda incursão de `data/incursoes/` está na tabela do README, e com o
    tier, o tamanho e a Organização que o arquivo dela diz."""
    escritas, ruins = I.carregar_todas_tolerante(RAIZ / "data" / "incursoes")
    assert not ruins, ruins
    no_arquivo = {
        inc.nome: (str(inc.tier), inc.tamanho, inc.organizacao)
        for inc in escritas.values()
    }
    linhas = _tabela(
        README.read_text(encoding="utf-8"), "| Incursão | Tier | Tamanho | Organização |"
    )
    no_readme = {nome.strip("*"): (tier, tamanho, org) for nome, tier, tamanho, org, *_ in linhas}

    faltam = sorted(set(no_arquivo) - set(no_readme))
    sobram = sorted(set(no_readme) - set(no_arquivo))
    assert not faltam, f"incursoes sem linha no catalogo do README: {faltam}"
    assert not sobram, f"o catalogo do README lista incursao que nao existe: {sobram}"
    errados = [
        f"{nome}: README {no_readme[nome]}, arquivo {no_arquivo[nome]}"
        for nome in no_arquivo
        if no_readme[nome] != no_arquivo[nome]
    ]
    assert not errados, "o catalogo do README nao bate com o arquivo:\n" + "\n".join(errados)
    print(f"  o catalogo do README tem as {len(no_arquivo)} incursoes, como o arquivo diz: ok")


def caso_as_docs_geradas_estao_em_dia():
    """`FICHAS.md` e `docs/mecanicas/` são o que os geradores produzem hoje.

    São as docs que o README aponta como a verdade sobre classes e regras —
    e só podem ser apontadas assim enquanto um teste garantir que não ficaram
    para trás.
    """
    import gerar_fichas_md as fichas
    import gerar_mecanicas_md as mecanicas

    atrasadas = []
    if (RAIZ / "docs" / "FICHAS.md").read_text(encoding="utf-8") != fichas.documento():
        atrasadas.append("docs/FICHAS.md (rode tools/gerar_fichas_md.py)")
    pasta = RAIZ / "docs" / "mecanicas"
    paginas = [("README.md", mecanicas.indice)] + [
        (nome, funcao) for nome, funcao, _ in mecanicas.ARQUIVOS
    ]
    for nome, funcao in paginas:
        if (pasta / nome).read_text(encoding="utf-8") != funcao():
            atrasadas.append(f"docs/mecanicas/{nome} (rode tools/gerar_mecanicas_md.py)")
    assert not atrasadas, "docs geradas que ficaram para tras:\n" + "\n".join(atrasadas)
    print(f"  FICHAS.md e as {len(paginas)} paginas de mecanicas estao em dia: ok")


async def main():
    comandos = await _comandos()
    caso_a_tabela_de_comandos_e_a_do_bot(comandos)
    caso_nenhum_documento_cita_comando_que_saiu(comandos)
    caso_o_catalogo_de_incursoes_e_o_de_data()
    caso_as_docs_geradas_estao_em_dia()


asyncio.run(main())
print("TESTES DA DOCUMENTACAO PASSARAM")
