"""A bancada de quem escreve dungeon. Roda na máquina do autor.

    python tools/estudio.py
    python tools/estudio.py --porta 8765 --sem-navegador

Para entregar a outros autores, `tools/empacotar_estudio.py` gera um ZIP
Windows com Python e dependências. Quem recebe extrai e abre pelo atalho.

Sobe um servidor em 127.0.0.1 e abre a página. Ali dá para escrever sala,
montar o filtro da dungeon vendo o pool que ele deixa, medir a sala contra o
grupo e exportar o JSON pronto para mandar.

RODE PELO MESMO PYTHON DO BOT. Escrever, conferir e exportar só usam a
biblioteca padrão; medir e sugerir rodam o motor, que guarda o estado da run
em SQLite por `aiosqlite`. Num Python sem ele tudo funciona menos esses dois
botões — e eles são os que custam mais caro para alcançar, então o estúdio
avisa ao subir e na própria página (ver `_falta_para_simular`).

POR QUE ISTO VIVE NESTE REPOSITÓRIO: a página chama `src.incursoes` e
`src.motor` — a validação e o combate aqui são os MESMOS do bot. Um estúdio em
outro projeto seria uma segunda cópia das regras, e duas réguas sempre acabam
discordando.

POR QUE SÓ EM 127.0.0.1: esta página não tem login e roda simulação, que é
rajada de CPU. Ela é a bancada de UMA pessoa, na máquina dela. Expor isso numa
rede seria dar um botão de queimar CPU para quem passar — por isso o endereço
é fixo no laço local e não há opção de mudar.

O QUE ELE NÃO FAZ, e não finge fazer: a "chance de vitória da dungeon
inteira". HP, mana e poção atravessam as salas sem resetar, e o caminho é
sorteado com os jogadores escolhendo — um número só, sem dizer qual política
de escolha foi usada, seria mentira com número em cima. Aqui a medida é por
sala.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import random
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import bestiario, incursoes as I, pacotes  # noqa: E402
from src.rules import ATRIBUTOS, PERICIAS, TIER_MAXIMO, nivel_maximo_do_tier  # noqa: E402
from src import classes, config  # noqa: E402
from tools.simulacao import regua  # noqa: E402
from tools.simulacao.estatisticas import mesa_azarada  # noqa: E402
import validar_conteudo as V  # noqa: E402

PAGINA = Path(__file__).resolve().parent / "estudio" / "index.html"
PASTA_BANCOS = RAIZ / "data" / "bancos"
PASTA_INCURSOES = RAIZ / "data" / "incursoes"

# Confrontos por tamanho de grupo. O custo depende da duracao e das regras
# acionadas na luta; o autor pode reduzir a amostra ou aumentar para confirmar.
REPETICOES_PADRAO = 800
REPETICOES_MAXIMO = 20000
# O grupo do jogo e CINCO (`config.TAMANHO_GRUPO`), e e esse que se mede.
# Media com quatro, tres e dois saia junto e nao respondia pergunta nenhuma
# que o autor faca: a sala e escrita para a mesa que existe, e as formacoes de
# referencia tem seis classes cada — medir "as cinco primeiras" e medir a
# mesa, medir "as duas primeiras" e medir uma dupla que nunca vai entrar
# numa dungeon. O seis fica disponivel para quem jogar com mesa cheia.
TAMANHO_MINIMO = config.TAMANHO_GRUPO
TAMANHO_MAXIMO = 6
GRUPOS_PADRAO = (TAMANHO_MINIMO,)


# --------------------------------------------------------------- leitura


def _bancos() -> dict[str, Any]:
    """Os bancos do disco, tolerando o arquivo quebrado como o bot faz."""
    bancos, problemas = I.carregar_bancos_tolerante(PASTA_BANCOS)
    originais = {}
    for arquivo in sorted(PASTA_BANCOS.glob("*.json")):
        try:
            dados = json.loads(arquivo.read_text(encoding="utf-8"))
            validado = I.banco_de_dict(dados)
        except (OSError, ValueError, I.ErroDeValidacao):
            continue
        originais[validado.organizacao] = (arquivo.name, dados)
    return {
        "bancos": {
            nome: {
                "organizacao": nome,
                "arquivo": originais.get(nome, (f"{I.arquivo_da_organizacao(nome)}.json",))[0],
                "salas": [s.para_dict() for s in banco.salas],
                # O editor preserva referencias ao bestiario, campos extras e
                # escolhas do autor; para_dict expandiria cada criatura.
                "original": originais[nome][1] if nome in originais else banco.para_dict(),
            }
            for nome, banco in sorted(bancos.items())
        },
        "problemas": problemas,
    }


def _incursoes() -> dict[str, dict[str, Any]]:
    """As incursões do disco como estão escritas, por id.

    Cruas, e não por `para_dict`: o Estúdio abre uma CÓPIA delas para o autor
    partir de algo pronto, e `para_dict` expandiria cada criatura chamada pelo
    nome na ficha inteira — a cópia viria com números que deixam de
    acompanhar o bestiário. Só entram as que o bot aceita: partir de um
    arquivo quebrado seria começar com problema que o autor não fez.
    """
    saida: dict[str, dict[str, Any]] = {}
    for arquivo in sorted(PASTA_INCURSOES.glob("*.json")):
        try:
            dados = json.loads(arquivo.read_text(encoding="utf-8"))
            incursao = I.de_dict(dados)
        except (OSError, ValueError, I.ErroDeValidacao):
            continue
        saida[incursao.id] = dados
    return saida


def _tipos_de_bicho() -> list[dict[str, Any]]:
    """Os `meta.tipo` do bestiário, com quantas criaturas cada um tem."""
    contagem: dict[str, int] = {}
    for criatura in bestiario.carregar():
        tipo = (criatura.get("meta") or {}).get("tipo")
        if tipo:
            contagem[tipo] = contagem.get(tipo, 0) + 1
    return [
        {"id": tipo, "quantas": quantas}
        for tipo, quantas in sorted(contagem.items(), key=lambda p: -p[1])
    ]


# A que família cada tipo de sala pertence — o que o autor FAZ ao escrever uma.
#
# É esta divisão que separa a bancada em lugares: quem escreve um Evento não
# precisa ver a tabela de criaturas, e quem monta um Combate não precisa da CD.
# Ela mora aqui, e não na página, pelo mesmo motivo das outras listas: tipo
# novo em TIPOS_SALA tem que aparecer em ALGUM lugar da tela, e uma cópia no
# JavaScript o deixaria de fora calada. Sem o `.get`, de propósito — tipo sem
# família derruba `conteudo()` na cara de quem o criou, e o teste pega antes.
FAMILIA_DO_TIPO = {
    "Combate": "combate",
    "Descanso": "parada",
    "Armadilha": "teste",
    "Evento": "teste",
    "Tesouro": "teste",
}

# Com que tipo nasce uma sala nova em cada família. Evento, e não o primeiro
# tipo da lista: ele é o de folha em branco — passar dá prêmio, falhar cobra —
# enquanto Armadilha e Tesouro já trazem uma intenção junto.
SALA_NOVA = {"teste": "Evento", "combate": "Combate"}


def _tipos_de_sala() -> list[dict[str, Any]]:
    """Cada tipo com a família dele e o que a sala cobra do grupo.

    Os NÚMEROS saem das constantes, e não escritos à mão na página: a tela
    prometer 20% de dano depois de DANO_PCT virar 35 é exatamente a deriva
    silenciosa que o resto deste arquivo existe para evitar.
    """
    from src import consequencias as K

    resumo = {
        "Combate": (
            f"O tier escolhe quem aparece. No máximo {I.MAX_INIMIGOS} criaturas no "
            "bando, cada uma pelo nome do bestiário."
        ),
        "Evento": (
            f"Passar dá um buff, Cura (+{K.CURA_PCT}% do HP) ou Graça. Falhar deixa "
            f"{K.UNIDADES_DO_CASTIGO} unidades de um debuff."
        ),
        "Armadilha": (
            f"A CD escrita cai {I.DESCONTO_CD_ARMADILHA} na mesa — é a sala mais "
            f"fácil do caminho. Falhar custa {K.DANO_PCT}% do HP máximo e um debuff."
        ),
        "Tesouro": (
            "Falhar acorda os Mímicos, sempre: a emboscada do tier vira combate no "
            "mesmo turno."
        ),
        "Descanso": (
            "Parada fixa do caminho, sem teste. Não é sorteada: a incursão a põe "
            "onde o tamanho manda."
        ),
    }
    return [
        {
            "id": tipo,
            "familia": FAMILIA_DO_TIPO[tipo],
            "resumo": resumo[tipo],
            # Quanto este tipo abate da CD escrita (`Sala.cd_efetiva`). Vai
            # por tipo, e não como "a Armadilha desconta", para a página
            # mostrar o número certo sem saber de qual tipo ele é.
            "desconto_cd": I.DESCONTO_CD_ARMADILHA if tipo == "Armadilha" else 0,
        }
        for tipo in I.TIPOS_SALA
    ]


def _faixas_de_combate() -> dict[str, list[float]]:
    """As faixas de taxa de vitória que o sugeridor procura."""
    import sugestor

    return {nome: list(faixa) for nome, faixa in sugestor.FAIXAS_DE_VITORIA.items()}


def _python_do_bot() -> Path | None:
    """O interpretador do `.venv` deste repositório, se houver um."""
    for relativo in ("Scripts/python.exe", "bin/python"):
        caminho = RAIZ / ".venv" / relativo
        if caminho.exists():
            return caminho
    return None


def _recado_de_dependencia(falta: str) -> str:
    """O que dizer a quem abriu o estúdio pelo Python errado.

    Com o COMANDO, e não com um conselho: "abra pelo ambiente do bot" supõe
    que a pessoa saiba qual é e como escrevê-lo no shell dela. O caminho sai
    com os separadores do sistema justamente por isso — no `cmd.exe` uma
    barra no começo do comando não é caminho, é opção.
    """
    if (venv := _python_do_bot()) is not None:
        como = f'Use: "{venv}" {Path("tools") / "estudio.py"}'
    else:
        como = "Instale as dependências do bot: pip install -r requirements.txt"
    return (
        f"Medir e sugerir precisam de '{falta}', que não existe neste Python "
        f"({sys.executable}). {como}"
    )


def _falta_para_simular() -> str:
    """O que impede a medição de rodar, ou "" quando ela roda.

    O estúdio abre, lê os bancos, valida sala e monta o filtro só com a
    biblioteca padrão — é a bancada de quem escreve conteúdo, não de quem
    hospeda o bot. MEDIR é a exceção: ela roda o motor, e o motor guarda o
    estado da run no mesmo SQLite do bot, por `aiosqlite`.

    Descobrir isso ao clicar em "Medir combate", depois de escrever a sala
    inteira, é tarde — e o que chegava na tela era o ModuleNotFoundError cru,
    que não diz a ninguém o que fazer. Acontece com quem roda
    `python tools/estudio.py` fora do ambiente do bot: tudo funciona, menos
    o único botão que custa caro para alcançar.
    """
    try:
        import simular_combate  # noqa: F401
    except ImportError as erro:
        return _recado_de_dependencia(
            getattr(erro, "name", None) or "uma dependência do bot"
        )
    return ""


def conteudo() -> dict[str, Any]:
    """Tudo que a página precisa saber para desenhar os campos.

    Vem do código, e não repetido no JavaScript: tema, tipo de sala e limite
    mudam aqui dentro, e uma lista copiada na página envelheceria calada.
    """
    _, ruins = I.carregar_todas_tolerante(PASTA_INCURSOES)
    do_disco = _bancos()
    return {
        "temas": list(I.TEMAS),
        "tipos": list(I.TIPOS_SALA),
        # Os mesmos tipos, com a família e o que cada um cobra do grupo. A
        # página divide os lugares por `familia` em vez de ter a sua lista.
        "tipos_de_sala": _tipos_de_sala(),
        "sala_nova": dict(SALA_NOVA),
        "organizacoes": list(I.ORGANIZACOES),
        "dificuldades": list(I.DIFICULDADES),
        "pericias": list(PERICIAS),
        "atributos": list(ATRIBUTOS),
        "classes": sorted(classes.CLASSES),
        "tamanhos": {
            nome: {
                "salas": passos,
                "terminar": passos,
                "folga": passos + I.OPCOES_POR_PASSO - 1,
                "paradas": I.paradas_do_caminho(passos),
            }
            for nome, passos in I.TAMANHOS.items()
        },
        "limites": {
            "titulo": I.LIMITE_TITULO,
            "descricao": I.LIMITE_DESCRICAO,
            "campo": I.LIMITE_CAMPO,
            "inimigos": I.MAX_INIMIGOS,
            "opcoes_por_passo": I.OPCOES_POR_PASSO,
            "tier_maximo": TIER_MAXIMO,
            "desconto_armadilha": I.DESCONTO_CD_ARMADILHA,
            # O texto legal mas longo demais para um celular: aviso, e não
            # recusa. Os números moram no validador, que é quem avisa.
            "aviso_titulo": V.AVISO_TITULO,
            "aviso_descricao": V.AVISO_DESCRICAO_SALA,
            "aviso_lore": V.AVISO_LORE,
            "chamada": I.LIMITE_CHAMADA,
        },
        # Até que nível cada tier aceita: é o que a dungeon diz a quem entra.
        "nivel_maximo_do_tier": {
            str(t): nivel_maximo_do_tier(t) for t in range(1, TIER_MAXIMO + 1)
        },
        # O arquivo que a página baixa: o bot lê o mesmo.
        "formato": {"nome": pacotes.FORMATO, "versao": pacotes.VERSAO},
        "ambientes": list(bestiario.AMBIENTES),
        # Os tipos de bicho com quantas criaturas cada um tem: sem o número, o
        # autor não sabe que 'ooze' corta o bestiário para quatro.
        "tipos_de_bicho": _tipos_de_bicho(),
        # Os nomes das 385, para o campo de criatura oferecer o que existe em
        # vez de aceitar o que foi digitado. Sao ~8 KB e vao uma vez so: a
        # alternativa, uma rota de busca por tecla, custaria uma ida ao
        # servidor por letra para escolher entre 385 nomes.
        "criaturas": sorted(
            c["nome"] for c in bestiario.carregar() if c.get("nome")
        ),
        "dificuldades_de_combate": _faixas_de_combate(),
        # Como cada faixa se escreve: a régua do resultado usa os nomes dela.
        "rotulos_de_combate": dict(regua.ROTULOS),
        # Vazio quando a medição roda. Cheio, a página avisa no painel de
        # Combate em vez de deixar o autor descobrir no clique.
        "falta_para_simular": _falta_para_simular(),
        "bancos": do_disco["bancos"],
        "incursoes": _incursoes(),
        # Os tiers em que cada Organização tem dungeon: uma sala de combate
        # nova cai em todas elas, e o editor marca quais tiers pedem bando.
        "tiers_por_organizacao": _tiers_por_organizacao(),
        "problemas": do_disco["problemas"] + ruins,
    }


def _tiers_por_organizacao() -> dict[str, list[int]]:
    usados: dict[str, set[int]] = {org: set() for org in I.ORGANIZACOES}
    for dados in _incursoes().values():
        incursao = I.de_dict(dados)
        usados.setdefault(incursao.organizacao, set()).add(incursao.tier)
    return {org: sorted(tiers) for org, tiers in usados.items()}


def _salas_do_autor(
    brutas: Any, existentes: set[str]
) -> tuple[list[I.Sala], list[str]]:
    """As salas novas do autor, que ainda não estão no bot, para entrar na conta.

    Elas vão num arquivo próprio e chegam ao bot ANTES da dungeon que conta
    com elas; enquanto isso, o Estúdio as soma ao banco para o autor ver o
    caminho que a dungeon vai ter. Sala com problema fica fora da conta, com
    aviso — somá-la daria ao autor um caminho que o bot não vai montar.
    """
    salas: list[I.Sala] = []
    avisos: list[str] = []
    if not isinstance(brutas, list):
        return salas, avisos
    for bruta in brutas:
        if not isinstance(bruta, dict):
            continue
        rotulo = str(bruta.get("id") or "?")
        try:
            sala = I.sala_de_dict(bruta)
        except I.ErroDeValidacao:
            avisos.append(
                f"sua sala {rotulo} tem problema e ficou fora da conta. "
                f"Corrija na parte Salas."
            )
            continue
        if sala.id in existentes:
            avisos.append(
                f"sua sala {rotulo} usa um código que o banco já tem e ficou "
                f"fora da conta."
            )
            continue
        existentes.add(sala.id)
        salas.append(sala)
    return salas, avisos


def _tier_do_bando(sala: I.Sala, tier: int) -> Optional[int]:
    """Qual tier escrito a sala usa quando a dungeon é daquele tier.

    Pergunta à própria sala (`monstros_do_tier`) e acha de qual lista veio a
    resposta, em vez de repetir aqui a regra da queda — uma cópia dela
    envelheceria calada. None quando a sala só tem a lista solta.
    """
    escolhidos = sala.monstros_do_tier(tier)
    for escrito, lista in sala.monstros_por_tier.items():
        if lista is escolhidos:
            return escrito
    return None


# ------------------------------------------------------------ conferir


def _tipo_do_payload(dados: dict[str, Any]) -> str:
    if pacotes.e_pacote(dados):
        return "pacote"
    if isinstance(dados.get("salas"), list):
        return "banco"
    if "objetivo" in dados:
        return "incursao"
    return "sala"


def conferir(payload: dict[str, Any]) -> dict[str, Any]:
    """Valida o que o autor está escrevendo, com o validador do bot.

    Aceita os três: uma sala solta, um banco e uma incursão. A sala solta não
    é cobrada das regras do BANCO (mínimo de salas, id único), que não são
    dela.
    """
    dados = payload.get("dados")
    if not isinstance(dados, dict):
        return {"problemas": ["não veio nenhum objeto para conferir."], "avisos": []}

    tipo = _tipo_do_payload(dados)
    if tipo == "pacote":
        return conferir_pacote(dados, payload.get("salas_do_autor"))
    conversor = {
        "banco": I.banco_de_dict,
        "incursao": I.de_dict,
        "sala": I.sala_de_dict,
    }[tipo]
    try:
        conversor(dados)
    except I.ErroDeValidacao as erro:
        return {"tipo": tipo, "problemas": list(erro.problemas), "avisos": []}
    return {"tipo": tipo, "problemas": [], "avisos": _avisos(tipo, dados)}


def conferir_pacote(dados: dict[str, Any], do_autor: Any = None) -> dict[str, Any]:
    """O arquivo do Estúdio, pela MESMA conferência que o bot vai usar.

    Contra os bancos e as dungeons do disco: o código de uma dungeon do
    repositório não pode ser tomado por um arquivo novo — e o Estúdio é onde
    o autor tem de saber disso, e não no envio.

    `do_autor` são as salas novas que ele escreveu e ainda não enviou: elas
    vão num arquivo próprio, ANTES da dungeon, e entram aqui como se já
    estivessem no bot — com o aviso de que a dungeon depende delas, porque
    enviada antes delas a dungeon é recusada.
    """
    bancos, _ = I.carregar_bancos_tolerante(PASTA_BANCOS)
    organizacao = I._INDICE_ORGS.get(
        I.chave_comparacao(str(dados.get("organizacao") or ""))
    )
    avisos_extras: list[str] = []
    extras: list[I.Sala] = []
    if organizacao in bancos and isinstance(dados.get("incursao"), dict):
        banco = bancos[organizacao]
        extras, avisos_extras = _salas_do_autor(do_autor, {s.id for s in banco.salas})
        if extras:
            bancos = {**bancos, organizacao: I.BancoDeSalas(
                organizacao=organizacao, salas=banco.salas + extras)}
    r = pacotes.conferir(dados, bancos, ocupadas=set(_incursoes()))
    avisos = list(r.avisos) + avisos_extras
    caminho = None
    if r.incursao is not None and organizacao in bancos:
        deixadas = r.incursao.filtro.aplicar(I.salas_sorteaveis(bancos[organizacao]))
        caminho = len(deixadas)
        usadas = sorted({s.id for s in deixadas} & {s.id for s in extras})
        if usadas:
            avisos.append(
                f"esta dungeon conta com {len(usadas)} sala(s) suas que ainda não "
                f"estão no bot ({', '.join(usadas)}). Envie o arquivo de salas de "
                f"{organizacao} ANTES desta dungeon, senão o bot a recusa."
            )
    bruta = dados.get("incursao")
    if isinstance(bruta, dict):
        avisos[:0] = V.avisos(Path("incursao.json"), bruta)
        if isinstance(bruta.get("objetivo"), dict):
            avisos.extend(V.avisos_da_sala({**bruta["objetivo"], "id": "do chefe"}))
    for sala in dados.get("salas") or []:
        if isinstance(sala, dict):
            avisos.extend(V.avisos_da_sala(sala))
    return {"tipo": "pacote", "problemas": r.problemas, "avisos": avisos,
            "caminho": caminho}


def _avisos(tipo: str, dados: dict[str, Any]) -> list[str]:
    """O que passa no bot e ainda assim não faz o que o autor espera."""
    if tipo == "incursao":
        saida = V.avisos(Path("incursao.json"), dados)
        _, cruzados = V.cruzar_com_o_banco(dados)
        return saida + cruzados
    if tipo == "banco":
        return V.avisos(Path("banco.json"), dados)
    # Uma sala solta leva só os avisos DELA. Passá-la por `avisos` dentro de
    # um banco de mentira cobraria a sala de Descanso de uma sala sozinha.
    return V.avisos_da_sala(dados)


# ---------------------------------------------------------------- pool


def pool(payload: dict[str, Any]) -> dict[str, Any]:
    """O filtro aplicado ao banco, com a conta e o veredito do bot.

    `salas` pode vir no payload para o autor ver o efeito de salas que ele
    ainda não salvou — é a razão de o estúdio existir em vez de o autor rodar
    o validador depois de copiar o arquivo.
    """
    organizacao = str(payload.get("organizacao") or "").strip()
    tamanho = str(payload.get("tamanho") or "Média").strip()
    if tamanho not in I.TAMANHOS:
        return {"erro": f"tamanho '{tamanho}' não existe."}

    brutas = payload.get("salas")
    if brutas is None:
        bancos, _ = I.carregar_bancos_tolerante(PASTA_BANCOS)
        banco = bancos.get(organizacao)
        if banco is None:
            return {"erro": f"não há banco de '{organizacao}' em data/bancos."}
    else:
        try:
            banco = I.banco_de_dict(
                {"organizacao": organizacao, "salas": brutas}
            )
        except I.ErroDeValidacao as erro:
            return {"erro": "o banco em edição não está válido.",
                    "problemas": list(erro.problemas)}

    problemas: list[str] = []
    filtro = I._filtro_de_dict(payload.get("filtro"), problemas)
    if problemas:
        return {"erro": "o filtro não está válido.", "problemas": problemas}

    extras, avisos_extras = _salas_do_autor(
        payload.get("extras"), {s.id for s in banco.salas}
    )
    if extras:
        banco = I.BancoDeSalas(organizacao=banco.organizacao,
                               salas=banco.salas + extras)
    novas = {s.id for s in extras}
    tier = payload.get("tier")
    tier = tier if isinstance(tier, int) and 1 <= tier <= TIER_MAXIMO else None

    def resumo(s: I.Sala) -> dict[str, Any]:
        saida = {"id": s.id, "nome": s.nome, "tipo": s.tipo, "temas": s.temas,
                 "nova": s.id in novas, "combate": s.e_combate}
        if s.e_combate and tier:
            saida["tier_do_bando"] = _tier_do_bando(s, tier)
        return saida

    incursao = SimpleNamespace(filtro=filtro, tamanho=tamanho,
                               passos=I.TAMANHOS[tamanho])
    cruzados, avisos = I.conferir_filtro(incursao, banco)
    sorteaveis = I.salas_sorteaveis(banco)
    deixadas = filtro.aplicar(sorteaveis)
    # As que o tema deixa, ANTES de tirar as excluídas: a página mostra as
    # tiradas desmarcadas, para o autor poder pôr de volta.
    candidatas = dataclasses.replace(filtro, excluir=[]).aplicar(sorteaveis)
    passos = I.TAMANHOS[tamanho]
    return {
        "pool": [resumo(s) for s in deixadas],
        "candidatas": [resumo(s) for s in candidatas],
        "sorteaveis": len(sorteaveis),
        "no_banco": len(banco.salas),
        "terminar": passos,
        "folga": passos + I.OPCOES_POR_PASSO - 1,
        "problemas": cruzados,
        "avisos": avisos + avisos_extras,
    }


# -------------------------------------------------------------- simular


def _inteiro(valor: Any, padrao: int, menor: int, maior: int) -> int:
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return padrao
    return max(menor, min(maior, numero))


def simular(payload: dict[str, Any]) -> dict[str, Any]:
    """Mede a sala de combate com o motor do bot, contra formações fixas.

    A semente vai na resposta para dois autores comparando números verem o
    mesmo número — e para o próprio autor: sem fixá-la, editar o bando e
    remedir mistura a diferença do bando com a diferença das rolagens.

    Cada medida sai com um VEREDITO (`tools/simulacao/regua.py`), e não só com
    a porcentagem. Medir e deixar o autor adivinhar se 62% é o que ele queria
    era metade do trabalho: a régua é a outra metade, e ela já existia no
    sugeridor e no calibrador da emboscada.
    """
    if falta := _falta_para_simular():
        return {"erro": falta}
    import simular_combate as sc

    bruta = payload.get("sala")
    if not isinstance(bruta, dict):
        return {"erro": "não veio sala para medir."}
    try:
        sala = I.sala_de_dict(bruta)
    except I.ErroDeValidacao as erro:
        return {"erro": "a sala não está válida.", "problemas": list(erro.problemas)}
    if not sala.e_combate:
        return {
            "erro": "só sala de Combate é medida por simulação. "
                    "Armadilha, Evento e Tesouro resolvem por d20 + perícia "
                    "contra a CD, que é conta fechada e não precisa de amostra."
        }

    tier = _inteiro(payload.get("tier"), 2, 1, TIER_MAXIMO)
    tema = payload.get("tema") or None
    monstros = sala.monstros_do_tier(tier, tema)
    if not monstros:
        return {"erro": f"a sala não tem criatura escrita para o tier {tier}."}

    # Sem classe, a sala é medida contra mesas PREDEFINIDAS — ver
    # `tools/simulacao/grupos.py`. Com classe, o estúdio volta ao grupo
    # uniforme, que agora é o diagnóstico e não o padrão.
    classe = str(payload.get("classe") or "")
    if classe and classes.classe(classe) is None:
        return {"erro": f"classe desconhecida: {classe}."}
    nivel = _inteiro(payload.get("nivel"), min(10, tier * 2), 1, 10)
    repeticoes = _inteiro(payload.get("repeticoes"), REPETICOES_PADRAO, 50,
                          REPETICOES_MAXIMO)
    semente = payload.get("semente")
    if not isinstance(semente, int):
        semente = random.randrange(1, 10**8)

    # Um tamanho fora da faixa e RECUSADO, nao corrigido de mansinho: medir
    # cinco e devolver a medida rotulada de tres seria pior que nao medir.
    pedidos = payload.get("grupos") or list(GRUPOS_PADRAO)
    if not isinstance(pedidos, list) or not all(
            isinstance(g, int) and not isinstance(g, bool) for g in pedidos):
        return {"erro": "grupos precisa ser uma lista de números."}
    fora = sorted({g for g in pedidos if not TAMANHO_MINIMO <= g <= TAMANHO_MAXIMO})
    if fora:
        return {"erro": f"grupo de {', '.join(str(g) for g in fora)} não se "
                        f"mede: a medição é de {TAMANHO_MINIMO} a "
                        f"{TAMANHO_MAXIMO} jogadores."}
    grupos = list(dict.fromkeys(pedidos))

    args = SimpleNamespace(classe=classe or None, nivel=nivel, repeticoes=repeticoes,
                           tier=tier, coletar_detalhes=False)
    pedido = _pedido(payload)
    try:
        medidas = _medidas(sc, monstros, grupos, args, semente, _registrar(pedido))
    except Cancelado:
        return {"cancelado": True}
    finally:
        _encerrar(pedido)
    return {
        "sala": sala.id,
        "tema": tema,
        "tier": tier,
        "classe": classe or "predefinido",
        "sorteado": False,
        "predefinido": not classe,
        "nivel": nivel,
        "repeticoes": repeticoes,
        "semente": semente,
        "criaturas": [{"nome": m.nome, "ca": m.ca, "hp": m.hp} for m in monstros],
        "medidas": medidas,
    }


def _medidas(sc, monstros, grupos, args, semente, aviso=None) -> list[dict[str, Any]]:
    """Cada tamanho de grupo contra as formações, com o veredito da régua."""
    medidas = []
    for tamanho in grupos:
        # Com dois tamanhos, o andamento diz em qual deles está.
        args.aviso = aviso.fase(f"{tamanho} jogadores") if aviso and len(grupos) > 1 else aviso
        # Um rng por tamanho, derivado da mesma semente: assim mudar a lista
        # de grupos nao muda o numero dos outros.
        bruto = sc.simular(monstros, tamanho, args, random.Random(f"{semente}:{tamanho}"))
        # Os extremos saem daqui prontos: a pior mesa é a resposta de "existe
        # grupo que esta sala mata?", e deixá-la para a página ordenar seria
        # pedir que ela soubesse o que a média esconde.
        mesas = sorted(bruto["composicoes"], key=lambda c: c["taxa"])
        # A pior formação nomeia quem sofreu E decide o veredito, e as duas
        # coisas são a mesma agora: com o catálogo fixo, a pior das que existem
        # é um número comparável entre medições. Era o décimo percentil, de
        # quando as mesas eram sorteadas. Ver `estatisticas.mesa_azarada`.
        azarada = mesa_azarada(bruto["composicoes"]) if len(mesas) > 1 else None
        medidas.append({
            "grupo": tamanho,
            "taxa": bruto["taxa"],
            "rodadas": None if bruto["rodadas"] != bruto["rodadas"] else bruto["rodadas"],
            "caidos": bruto["caidos"],
            "lutas": bruto["amostras"],
            "mesas": len(mesas),
            "composicoes": bruto["composicoes"],
            "pior": mesas[0] if len(mesas) > 1 else None,
            "melhor": mesas[-1] if len(mesas) > 1 else None,
            "azarada": azarada,
            **regua.veredito(bruto["taxa"], azarada),
        })
    return medidas


# ----------------------------------------------------- andamento e cancelar

class Cancelado(Exception):
    """O autor pediu para parar. Levantada pelo aviso, entre duas formações."""


# O que cada pedido em andamento já fez, e se pediram para parar. Em memória:
# só existe enquanto a medida roda, e o estúdio é de uma pessoa só.
_ANDAMENTO: dict[str, dict[str, Any]] = {}
_TRAVA_DO_ANDAMENTO = threading.Lock()


def _pedido(payload: dict[str, Any]) -> str:
    """O nome que a página deu à medida, para perguntar por ela depois."""
    pedido = payload.get("pedido")
    return pedido[:64] if isinstance(pedido, str) else ""


class _Aviso:
    """O que a simulação chama a cada formação: anota, e para se pediram.

    Um objeto, e não uma função solta, para o ajuste poder dizer em que fase
    está ("medição 2") sem mudar a assinatura de quem simula.
    """

    def __init__(self, pedido: str, rotulo: str = "") -> None:
        self.pedido, self.rotulo = pedido, rotulo

    def fase(self, rotulo: str) -> "_Aviso":
        return _Aviso(self.pedido, rotulo)

    def __call__(self, feitas: int, total: int) -> None:
        with _TRAVA_DO_ANDAMENTO:
            estado = _ANDAMENTO.get(self.pedido)
            if estado is None:
                return
            estado.update(feitas=feitas, total=total, fase=self.rotulo)
            parar = estado["cancelar"]
        if parar:
            raise Cancelado()


def _registrar(pedido: str) -> Optional[_Aviso]:
    if not pedido:
        return None
    with _TRAVA_DO_ANDAMENTO:
        _ANDAMENTO[pedido] = {"feitas": 0, "total": 0, "fase": "", "cancelar": False}
    return _Aviso(pedido)


def _encerrar(pedido: str) -> None:
    with _TRAVA_DO_ANDAMENTO:
        _ANDAMENTO.pop(pedido, None)


def andamento(payload: dict[str, Any]) -> dict[str, Any]:
    """Quantas formações a medida já fez. `fim` quando ela não roda mais."""
    with _TRAVA_DO_ANDAMENTO:
        estado = _ANDAMENTO.get(_pedido(payload))
        if estado is None:
            return {"fim": True}
        return {k: estado[k] for k in ("feitas", "total", "fase")}


def cancelar(payload: dict[str, Any]) -> dict[str, Any]:
    """Pede para a medida parar. Ela para na próxima formação, e não no meio
    de uma: a formação começada termina, e o que ela mediu é descartado."""
    with _TRAVA_DO_ANDAMENTO:
        estado = _ANDAMENTO.get(_pedido(payload))
        if estado is not None:
            estado["cancelar"] = True
    return {"ok": estado is not None}


# ------------------------------------------------------------------ ajustar


def ajustar(payload: dict[str, Any]) -> dict[str, Any]:
    """Procura quantas cópias põem a luta na faixa pedida, sem trocar criatura.

    O autor escolheu as criaturas pela ficção da sala; o que ele quer do
    Estúdio é o número. Varia a linha mais numerosa do bando — a dos lacaios,
    quase sempre —, com as outras fixas, pela mesma bisseção do sugeridor
    (`sugestor._melhor_na_escala`), e confirma a escolhida com a MESMA medida
    que o Estúdio mostra: o número que o autor lê no fim é comparável ao que
    ele leu antes de pedir.

    Quando nenhuma quantidade cai na faixa, diz por quê (`veredito`): "fraca"
    se nem o bando cheio chega, "forte" se até uma cópia passa, "pula" se a
    faixa fica entre duas quantidades vizinhas.
    """
    if falta := _falta_para_simular():
        return {"erro": falta}
    import simular_combate as sc
    import sugestor

    alvo = payload.get("alvo")
    if alvo not in regua.FAIXAS_DE_VITORIA:
        return {"erro": f"faixa '{alvo}' não existe. Use {', '.join(regua.FAIXAS_DE_VITORIA)}."}
    tier = _inteiro(payload.get("tier"), 2, 1, TIER_MAXIMO)
    linhas = [dict(m) for m in payload.get("bando") or []
              if isinstance(m, dict) and str(m.get("nome") or "").strip()]
    if not linhas:
        return {"erro": "o bando não tem criatura para ajustar."}

    def quantas(m: dict[str, Any]) -> int:
        return _inteiro(m.get("quantidade"), 1, 1, I.MAX_INIMIGOS)

    # A mais numerosa varia; no empate, a primeira escrita.
    escala = max(range(len(linhas)), key=lambda i: (quantas(linhas[i]), -i))
    fixas = sum(quantas(m) for i, m in enumerate(linhas) if i != escala)
    maximo = I.MAX_INIMIGOS - fixas
    if maximo < 1:
        return {"erro": "as outras criaturas já ocupam o bando inteiro."}

    def bando_com(n: int) -> list[dict[str, Any]]:
        novo = [dict(m) for m in linhas]
        novo[escala]["quantidade"] = n
        return novo

    def montar(n: int) -> list:
        monstros: list = []
        for m in bando_com(n):
            monstros.extend(I.monstros_de_criatura(m, "ajuste"))
        return monstros

    semente = payload.get("semente")
    if not isinstance(semente, int):
        semente = random.randrange(1, 10**8)
    nivel = min(10, tier * 2)
    pedido = _pedido(payload)
    aviso = _registrar(pedido)
    medicoes = [0]

    def montar_contando(n: int) -> list:
        # Cada chamada é uma medição nova da bisseção: é por aqui que o
        # andamento diz "medição 2", sem mexer no sugeridor.
        medicoes[0] += 1
        if aviso:
            ajuste.aviso = aviso.fase(f"medição {medicoes[0]}")
        return montar(n)

    ajuste = SimpleNamespace(aviso=aviso)

    def aviso_atual(feitas: int, total: int) -> None:
        if ajuste.aviso:
            ajuste.aviso(feitas, total)

    try:
        n, taxa_da_busca, veredito = sugestor._melhor_na_escala(
            montar_contando, regua.FAIXAS_DE_VITORIA[alvo], None, nivel, semente,
            1, maximo, aviso=aviso_atual,
        )
        if n is None:
            return {"veredito": "nao_monta",
                    "erro": "alguma criatura do bando não vira ficha. Confira os nomes."}
        proposta = bando_com(n)
        args = SimpleNamespace(classe=None, nivel=nivel, tier=tier, coletar_detalhes=False,
                               repeticoes=_inteiro(payload.get("repeticoes"), REPETICOES_PADRAO,
                                                   50, REPETICOES_MAXIMO))
        medidas = _medidas(sc, montar(n), [TAMANHO_MINIMO], args, semente,
                           aviso.fase("confirmando") if aviso else None)
    except Cancelado:
        return {"cancelado": True}
    finally:
        _encerrar(pedido)
    return {
        "alvo": alvo,
        "rotulo_do_alvo": regua.ROTULOS[alvo],
        "veredito": veredito,
        "criatura": str(linhas[escala]["nome"]).strip(),
        "antes": quantas(linhas[escala]),
        "quantidade": n,
        "bando": proposta,
        "taxa_da_busca": taxa_da_busca,
        "medida": {"tier": tier, "semente": semente, "repeticoes": args.repeticoes,
                   "medidas": medidas},
    }


def sugerir(payload: dict[str, Any]) -> dict[str, Any]:
    """Procura um bando que caia na faixa daquela dificuldade.

    A dificuldade aqui não é um rótulo que o estúdio escreve: é uma faixa de
    taxa de vitória que ele PROCURA, simulando. O número que volta é o que ele
    mediu, e `na_faixa` diz se caiu dentro — inclusive quando não caiu.
    """
    if falta := _falta_para_simular():
        return {"erro": falta}
    import sugestor

    return sugestor.sugerir(
        tier=_inteiro(payload.get("tier"), 2, 1, TIER_MAXIMO),
        ambiente=(payload.get("ambiente") or None),
        tipo=(payload.get("tipo") or None),
        dificuldade=str(payload.get("dificuldade") or "media"),
        classe=str(payload.get("classe") or "") or None,
        nivel=payload.get("nivel") if isinstance(payload.get("nivel"), int) else None,
        # Cada sugestão custa uma busca inteira, e a página espera por ela.
        quantas=_inteiro(payload.get("quantas"), 2, 1, 4),
        semente=payload.get("semente") if isinstance(payload.get("semente"), int) else None,
    )


ROTAS = {
    "/api/conteudo": lambda _: conteudo(),
    "/api/conferir": conferir,
    "/api/pool": pool,
    "/api/simular": simular,
    "/api/sugerir": sugerir,
    "/api/andamento": andamento,
    "/api/cancelar": cancelar,
    "/api/ajustar": ajustar,
}


# --------------------------------------------------------------- servidor


class Bancada(BaseHTTPRequestHandler):
    server_version = "EstudioDeIncursoes/1"

    def _responder(self, codigo: int, corpo: bytes, tipo: str) -> None:
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        # A pagina e servida pelo mesmo endereco, entao nao ha origem
        # cruzada para liberar — e liberar seria dar a qualquer aba aberta um
        # jeito de rodar simulacao nesta maquina.
        self.send_header("Cache-Control", "no-store")
        try:
            self.end_headers()
            self.wfile.write(corpo)
        except ConnectionError:
            # A aba fechou antes da resposta — o autor saiu no meio de uma
            # simulação. Não há a quem responder, e o traceback na janela do
            # estúdio só o faria achar que algo quebrou.
            self.close_connection = True

    def _json(self, codigo: int, dados: Any) -> None:
        self._responder(
            codigo, json.dumps(dados, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def do_GET(self) -> None:  # noqa: N802
        caminho = self.path.split("?")[0]
        estaticos = {
            "/": (PAGINA, "text/html; charset=utf-8"),
            "/index.html": (PAGINA, "text/html; charset=utf-8"),
            "/estudio.css": (PAGINA.with_name("estudio.css"), "text/css; charset=utf-8"),
            "/estudio.js": (PAGINA.with_name("estudio.js"), "text/javascript; charset=utf-8"),
        }
        if caminho in estaticos:
            arquivo, tipo = estaticos[caminho]
            try:
                self._responder(200, arquivo.read_bytes(), tipo)
            except OSError:
                self._json(500, {"erro": f"não achei o arquivo {arquivo.name}."})
            return
        if caminho == "/api/conteudo":
            self._json(200, conteudo())
            return
        self._json(404, {"erro": f"não há {caminho} aqui."})

    def do_POST(self) -> None:  # noqa: N802
        caminho = self.path.split("?")[0]
        rota = ROTAS.get(caminho)
        if rota is None or caminho == "/api/conteudo":
            self._json(404, {"erro": f"não há {caminho} aqui."})
            return
        tamanho = _inteiro(self.headers.get("Content-Length"), 0, 0, 20 * 1024 * 1024)
        try:
            payload = json.loads(self.rfile.read(tamanho) or b"{}")
        except json.JSONDecodeError as erro:
            self._json(400, {"erro": f"corpo não é JSON: {erro}"})
            return
        if not isinstance(payload, dict):
            self._json(400, {"erro": "o corpo precisa ser um objeto JSON."})
            return
        try:
            self._json(200, rota(payload))
        except Exception as erro:  # a bancada nao pode cair com o autor dentro
            self._json(500, {"erro": f"{type(erro).__name__}: {erro}"})

    def log_message(self, formato: str, *args: Any) -> None:
        # O log padrao escreve uma linha por requisicao, e a pagina conversa
        # muito: isso enterraria a linha que importa, que e o endereco.
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--porta", type=int, default=8765)
    parser.add_argument(
        "--sem-navegador", action="store_true",
        help="não abre o navegador sozinho",
    )
    args = parser.parse_args()

    if not PAGINA.exists():
        print(f"não achei a página em {PAGINA}.")
        return 1

    # 127.0.0.1 e nao 0.0.0.0, de proposito: ver o cabecalho do arquivo.
    servidor = ThreadingHTTPServer(("127.0.0.1", args.porta), Bancada)
    endereco = f"http://127.0.0.1:{servidor.server_port}/"
    print(f"Estúdio de Incursões em {endereco}")
    # O aviso sai ANTES do navegador abrir: quem roda fora do ambiente do bot
    # escreve a sala inteira e só descobre no clique de "Medir combate".
    if falta := _falta_para_simular():
        print(f"\nATENÇÃO: {falta}")
        print("O resto da bancada — escrever, conferir e exportar — funciona.\n")
    print("Ctrl+C para parar.")
    if not args.sem_navegador:
        threading.Timer(0.4, lambda: webbrowser.open(endereco)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nestúdio fechado.")
    finally:
        servidor.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
