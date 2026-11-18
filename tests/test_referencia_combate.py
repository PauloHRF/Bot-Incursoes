"""Combates gravados: o que o cog faz hoje, com o sorteio preso.

Este arquivo existe para a extração do `src/cogs/incursao.py`. O cog tem mais
de sete mil linhas, e tirar dele as regras é mudar MUITO código sem mudar
comportamento nenhum. Os testes de cada classe provam o que alguém pensou em
provar; uma referência prova o resto — o que ninguém pensou, mas acontece.

Cada cenário é um combate de verdade, pelas mesmas portas dos botões
(`atacar`, `usar_habilidade`, `usar_pocao`), com os dublês do Discord e o
sorteio preso numa semente (`aleatorio.usar`). Tudo o que sai é gravado, ação
por ação:

- o que o jogador que clicou leu, na resposta privada;
- o que mudou no canal: mensagem nova, editada (o painel) ou apagada;
- o que mudou no banco, linha por linha, em todas as tabelas.

Depois o arquivo gravado é a resposta esperada. Qualquer desvio — um dano a
mais, uma linha a menos no log, uma condição que dura uma rodada a mais, um
botão que sumiu — fica vermelho, e a falha diz em qual ação e em qual campo.

**Gravar de novo é decisão, não conserto.** Quando o comportamento muda DE
PROPÓSITO (uma regra nova, um texto novo), o arquivo é regravado com
`--regravar`, e o diff dele mostra o que a mudança fez. Durante a extração,
regravar é admitir que ela mudou o jogo.

    .venv/Scripts/python.exe tests/test_referencia_combate.py
    .venv/Scripts/python.exe tests/test_referencia_combate.py --regravar
    .venv/Scripts/python.exe tests/test_referencia_combate.py --so t5_linha_de_frente

O QUE O DRIVER USA DO COG que não é botão está todo em `_Cog`, abaixo: ler o
estado, saber de quem é a vez, listar as habilidades e os alvos. Se a
extração mudar esses nomes, muda-se ali, e só ali — a referência não muda.

POR QUE A POLÍTICA É BURRA. Quem joga aqui não tenta vencer: gira pelas
habilidades ativas em ordem de id, intercaladas com o ataque, e bebe as
poções que recebeu em momentos fixos. O objetivo é passar pelo maior número
de caminhos do cog, e não jogar bem. E ela mora aqui, e não em
`tools/simulacao`, porque a simulação também vai mudar na extração.
"""
from __future__ import annotations

import asyncio
import json
import random
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import discord  # noqa: E402

from src import aleatorio, classes, config, database as db, rules  # noqa: E402
from src.cogs.incursao import Incursoes  # noqa: E402
from src.incursoes import banco_de_dict, de_dict  # noqa: E402
import fakes  # noqa: E402
from fakes import (  # noqa: E402
    CANAL,
    GUILD,
    LORE_TESTE,
    ORG_PADRAO,
    FakeBot,
    FakeCanal,
    FakeInteraction,
    sala,
    salas_sem_combate,
)

AQUI = Path(__file__).resolve().parent
PASTA = AQUI / "referencia"
# O que esta rodada produziu, quando diverge: para abrir lado a lado com o
# gravado. Fica fora do repositorio (ver .gitignore).
OBTIDO = PASTA / "obtido"
BANCO = AQUI / "teste_referencia.db"

# Ninguem joga um combate de vinte rodadas: chegar aqui quer dizer que o
# cenario empacou, e o que ele fez ate ali ja esta gravado.
LIMITE_DE_RODADAS = 20

# Quantas vezes o mesmo jogador pode agir na mesma rodada antes de o driver
# desistir. A Pocao da Aceleracao nao gasta a acao, e uma habilidade recusada
# tambem nao: duas ou tres sao normais. Mais que isto e a fila parada.
TENTATIVAS_POR_VEZ = 5

# As pocoes de cada um, pela posicao no grupo, e quando ele bebe.
# `None` = quando o HP cair abaixo de 40%; um numero = naquela rodada.
POCOES = {
    0: [("pocao_vida_menor", None)],
    1: [("pocao_vida_menor", None), ("pocao_aceleracao_1", 1)],
    2: [("pocao_vida_menor", None), ("pocao_dano_1", 2)],
    3: [("pocao_vida_menor", None), ("pocao_bencao_1", 1)],
    4: [("pocao_vida_menor", None)],
}

# `variante` escolhe, em cada escolha de classe, a opcao de indice
# `variante % len(opcoes)`: cenarios diferentes passam por opcoes diferentes.
#
# `modo`: "na_vez" age so quando a fila chega no jogador; "adiantado" faz o
# grupo inteiro escolher no comeco da rodada, que e o outro jeito de jogar —
# a acao fica guardada e sai quando a iniciativa chegar nele.
CENARIOS = [
    dict(
        nome="t5_linha_de_frente", semente=5101, modo="na_vez", variante=0,
        grupo=[("barbaro", 10), ("guerreiro", 10), ("paladino", 10),
               ("clerigo", 10), ("bardo", 10)],
        # Regeneracao (Troll) e Taticas de Matilha (Cao Infernal), com recarga.
        monstros=[("Troll", 3), ("Cão Infernal", 3)],
    ),
    dict(
        nome="t5_conjuradores", semente=5202, modo="adiantado", variante=1,
        grupo=[("mago", 10), ("feiticeiro", 10), ("bruxo", 10),
               ("druida", 10), ("xama", 10)],
        monstros=[("Observador", 2), ("Nothic", 2)],
    ),
    dict(
        nome="t5_mistos", semente=5303, modo="na_vez", variante=2,
        grupo=[("ladino", 9), ("monge", 9), ("patrulheiro", 9),
               ("artifice", 9), ("mago", 9)],
        # O Revenante regenera; a Mumia tem habilidade com save.
        monstros=[("Revenante", 2), ("Múmia", 3)],
    ),
    dict(
        nome="t3_meio", semente=3404, modo="adiantado", variante=3,
        grupo=[("guerreiro", 5), ("clerigo", 5), ("ladino", 5),
               ("feiticeiro", 5), ("druida", 5)],
        monstros=[("Gárgula", 3), ("Aranha de Fase", 2)],
    ),
    dict(
        nome="t1_comeco", semente=1505, modo="na_vez", variante=1,
        grupo=[("barbaro", 1), ("bardo", 1), ("bruxo", 1),
               ("paladino", 1), ("patrulheiro", 1)],
        monstros=[("Carniçal", 3), ("Espectro", 2)],
    ),
    dict(
        # Tres de tier 2 contra o Observador: e o caminho da DERROTA, que o
        # resto dos cenarios quase nao pisa.
        nome="t2_derrota", semente=2606, modo="na_vez", variante=0,
        grupo=[("monge", 3), ("xama", 3), ("artifice", 3)],
        monstros=[("Observador", 1)],
    ),
]


# --------------------------------------------------- o que o driver usa do cog


class _Cog:
    """Os nomes internos do cog que o driver precisa, num lugar só.

    Os botões são públicos e ficam onde estão. Estes não: são leitura que o
    jogador faz OLHANDO a tela (de quem é a vez, que habilidades aparecem no
    menu, que alvos o seletor oferece). Se a extração os mover, o conserto é
    aqui.
    """

    def __init__(self, cog: Incursoes):
        self.cog = cog

    def passo(self, run):
        return self.cog._passo(run)

    async def estado(self, run, sala_):
        return await self.cog._estado_combate(run, sala_)

    async def abrir(self, run, sala_):
        await self.cog._abrir_combate(run, sala_)

    async def de_quem_e_a_vez(self, run, estado):
        return await self.cog._de_quem_e_a_vez(run, estado)

    async def ativas(self, run, user_id):
        """As habilidades que o menu mostraria, só as que se clicam."""
        personagem = await self.cog._personagem_na_run(run, user_id)
        if personagem is None:
            return []
        disponiveis = await self.cog._habilidades_disponiveis(
            run, personagem, self.passo(run)
        )
        return sorted(
            (h for h, _ in disponiveis
             if h.acao and (h.acao or {}).get("tipo") != "reacao"),
            key=lambda h: h.id,
        )

    async def alvos(self, run, habilidade, estado):
        return await self.cog._alvos_possiveis(run, habilidade, estado)


# ------------------------------------------------------------------ gravacao

_RELOGIO = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}")


def _limpo(valor):
    """Tira o relógio: a hora em que o teste rodou não é comportamento."""
    if isinstance(valor, str) and _RELOGIO.match(valor):
        return "<relogio>"
    return valor


def _embed(embed: discord.Embed) -> dict:
    d = embed.to_dict()
    d.pop("timestamp", None)
    return d


def _componente(item) -> dict:
    if isinstance(item, discord.ui.Button):
        d = {"botao": item.label, "id": item.custom_id, "estilo": str(item.style),
             "emoji": str(item.emoji) if item.emoji else None}
    elif isinstance(item, discord.ui.Select):
        d = {"menu": item.placeholder, "id": item.custom_id,
             "valores": [item.min_values, item.max_values],
             "opcoes": [[o.label, o.value, o.description, o.default]
                        for o in item.options]}
    else:
        d = {"componente": type(item).__name__}
    d["desligado"] = bool(getattr(item, "disabled", False))
    d["linha"] = getattr(item, "row", None)
    return d


def _view(view):
    if view is None:
        return None
    return [_componente(i) for i in view.children]


def _mensagem(msg) -> dict:
    arquivo = getattr(msg, "arquivo", None)
    return {
        "conteudo": msg.content,
        "embeds": [_embed(e) for e in msg.embeds],
        "view": _view(msg.view),
        "arquivo": getattr(arquivo, "filename", None) if arquivo else None,
        "apagada": msg.apagada,
    }


class _Canal:
    """O que mudou no canal desde a última olhada."""

    def __init__(self, canal: FakeCanal):
        self.canal = canal
        self.vistas: dict[int, str] = {}

    def mudancas(self) -> list[dict]:
        saida = []
        for msg in self.canal.enviadas:
            agora = _mensagem(msg)
            texto = json.dumps(agora, ensure_ascii=False, sort_keys=True)
            antes = self.vistas.get(msg.id)
            if antes == texto:
                continue
            self.vistas[msg.id] = texto
            saida.append({"mensagem": msg.id, "como": "nova" if antes is None else "editada",
                          **agora})
        return saida


async def _banco(conn) -> dict[str, list[str]]:
    """Todas as tabelas, cada linha como JSON ordenado — para comparar."""
    async with conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
        " AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ) as cur:
        tabelas = [r[0] for r in await cur.fetchall()]
    foto = {}
    for tabela in tabelas:
        async with conn.execute(f"SELECT * FROM {tabela}") as cur:
            nomes = [c[0] for c in cur.description]
            linhas = await cur.fetchall()
        foto[tabela] = sorted(
            json.dumps({n: _limpo(v) for n, v in zip(nomes, linha)},
                       ensure_ascii=False, sort_keys=True)
            for linha in linhas
        )
    return foto


def _diferenca(antes: dict, depois: dict) -> dict:
    """Por tabela, as linhas que entraram (+) e as que saíram (-)."""
    saida = {}
    for tabela in sorted(set(antes) | set(depois)):
        a, d = set(antes.get(tabela, [])), set(depois.get(tabela, []))
        mais, menos = sorted(d - a), sorted(a - d)
        if mais or menos:
            saida[tabela] = {"+": [json.loads(x) for x in mais],
                             "-": [json.loads(x) for x in menos]}
    return saida


def _leu(inter: FakeInteraction) -> dict:
    """O que o jogador que clicou viu em privado."""
    d = {}
    if inter.resposta is not None:
        d["resposta"] = inter.resposta
    if inter.resposta_atual not in (None, inter.resposta):
        d["depois"] = inter.resposta_atual
    if inter.seguimento is not None:
        d["seguimento"] = inter.seguimento
    view = inter.view_do_seguimento or inter.view_editada or inter.view_enviada
    if view is not None:
        d["view"] = _view(view)
    if inter.efemera_apagada:
        d["apagada"] = True
    return d


# ------------------------------------------------------------------- montagem


def _escolhas(classe_id: str, nivel: int, variante: int) -> dict:
    """Uma opção de cada escolha que a ficha tem, girando pela variante."""
    ficha = classes.CLASSES[classe_id]
    teto = rules.tier(nivel)
    escolhas = {}
    for t in sorted(ficha.habilidades):
        if t > teto:
            continue
        for h in ficha.habilidades[t]:
            forma = h.escolha or {}
            opcoes = forma.get("opcoes") or []
            if forma.get("tipo") == "opcao" and opcoes:
                escolhas[h.id] = opcoes[variante % len(opcoes)]["id"]
    return escolhas


def _definicao(cenario: dict) -> dict:
    """O cenário como fica gravado: com as escolhas já resolvidas."""
    return {
        "nome": cenario["nome"],
        "semente": cenario["semente"],
        "modo": cenario["modo"],
        "grupo": [
            {"classe": c, "nivel": n,
             "escolhas": _escolhas(c, n, cenario["variante"]),
             "pocoes": [list(p) for p in POCOES.get(i, [])]}
            for i, (c, n) in enumerate(cenario["grupo"])
        ],
        "monstros": [list(m) for m in cenario["monstros"]],
    }


async def _montar(definicao: dict):
    BANCO.unlink(missing_ok=True)
    config.DB_PATH = BANCO
    config.TAMANHO_GRUPO = 6
    conn = await db.conectar()
    await db.criar_schema(conn)
    canal = FakeCanal(CANAL)
    cog = Incursoes(FakeBot(conn, canal))

    objetivo = sala(
        "OBJ", "Combate",
        monstros=[{"nome": nome, "quantidade": q} for nome, q in definicao["monstros"]],
    )
    incursao = de_dict({
        "id": "ref", "nome": "Incursão de referência", "organizacao": ORG_PADRAO,
        "tamanho": "Curta", "tier": None, "lore_inicial": LORE_TESTE,
        "lore_final": "Epílogo da referência.", "imagem_capa": None,
        "recompensa_mes": 10, "pontos_conclusao": 10, "objetivo": objetivo,
    })
    banco = banco_de_dict({
        "organizacao": ORG_PADRAO,
        "salas": [*salas_sem_combate(), sala("DESC", "Descanso")],
    })
    cog.incursoes[incursao.id] = incursao
    cog.bancos[banco.organizacao] = banco

    jogadores = []
    run_id = await db.criar_run(conn, GUILD, CANAL, incursao.id, fakes.JOGADORES[0])
    for i, ficha in enumerate(definicao["grupo"]):
        user_id = 101 + i
        pid = await db.criar_personagem(
            conn, GUILD, user_id, f"{ficha['classe'].capitalize()}{user_id}",
            ficha["classe"], list(fakes.TREINADAS), nivel=ficha["nivel"],
        )
        for chave, opcao in ficha["escolhas"].items():
            await db.definir_escolha(conn, pid, chave, opcao)
        for pocao_id, _quando in ficha["pocoes"]:
            await db.dar_item(conn, pid, pocao_id)
        entrou = await db.adicionar_participante(
            conn, run_id, user_id, pid, tier=rules.tier(ficha["nivel"]),
        )
        assert entrou, ficha
        jogadores.append(user_id)
    await db.inicializar_hp(conn, run_id)
    await db.atualizar_run(
        conn, run_id, status="objetivo", sala_atual="OBJ",
        linha_atual=incursao.passos + 1,
    )
    return conn, canal, cog, incursao, run_id, jogadores


# ------------------------------------------------------------------ a partida


class _Jogo:
    def __init__(self, definicao, conn, canal, cog, incursao, run_id, jogadores):
        self.definicao = definicao
        self.conn, self.canal, self.cog = conn, canal, cog
        self.le = _Cog(cog)
        self.sala = incursao.objetivo
        self.run_id = run_id
        self.jogadores = jogadores
        self.vezes = {uid: 0 for uid in jogadores}
        # As pocoes que cada um ainda vai tentar beber: (id, quando).
        self.pocoes = {uid: [tuple(p) for p in ficha["pocoes"]]
                       for uid, ficha in zip(jogadores, definicao["grupo"])}
        self.olho = _Canal(canal)
        self.foto = None
        self.acoes = []

    async def run(self):
        return await db.buscar_run(self.conn, self.run_id)

    async def em_combate(self, run) -> bool:
        return bool(run) and run["status"] in ("em_sala", "objetivo") and run["sala_atual"] == "OBJ"

    async def painel(self, run):
        try:
            return await self.canal.fetch_message(run["mensagem_id"])
        except (discord.NotFound, TypeError):
            return None

    async def abrir(self) -> dict:
        await self.le.abrir(await self.run(), self.sala)
        self.foto = await _banco(self.conn)
        return {"canal": self.olho.mudancas(), "banco": self.foto}

    async def quem_age(self, run, estado):
        """Quem clica agora: o da vez, ou — adiantado — o primeiro que não escolheu."""
        if self.definicao["modo"] == "adiantado":
            passo = self.le.passo(run)
            for uid in self.jogadores:
                c = estado.combatente(uid)
                if c is None or c.caido or c.atordoado or c.e_invocacao:
                    continue
                if not await db.acao_do_turno(self.conn, run["id"], passo, estado.rodada, uid):
                    return uid
        return await self.le.de_quem_e_a_vez(run, estado)

    async def decidir(self, run, estado, uid):
        """(o que faz, id, alvos). Gira pelas ativas e pelo ataque."""
        rodada = estado.rodada
        participantes = await db.personagens_da_run(self.conn, run["id"])
        eu = next(p for p in participantes if p["user_id"] == uid)
        for i, (pocao_id, quando) in enumerate(self.pocoes[uid]):
            baixo = eu["hp_max"] and eu["hp_atual"] < 0.4 * eu["hp_max"]
            if (quando is None and baixo) or (quando is not None and rodada >= quando):
                del self.pocoes[uid][i]
                return "pocao", pocao_id, []

        ativas = await self.le.ativas(run, uid)
        roda = [*ativas, None]
        escolhida = roda[self.vezes[uid] % len(roda)]
        self.vezes[uid] += 1
        if escolhida is None:
            return "ataque", None, []

        opcoes = await self.le.alvos(run, escolhida, estado)
        if opcoes is None:
            return "habilidade", escolhida.id, []
        if not opcoes:
            return "ataque", None, []
        acao = escolhida.acao or {}
        quantos = acao.get("alvos", 1)
        quantos = quantos if isinstance(quantos, int) else len(opcoes)
        validos = [int(v) for v, _, _ in opcoes]
        if acao.get("tipo") == "cura" or acao.get("alvo") in ("aliado", "aliados"):
            por_hp = sorted(
                (p for p in participantes if p["user_id"] in validos),
                key=lambda p: (p["hp_atual"] / max(1, p["hp_max"]), p["user_id"]),
            )
            return "habilidade", escolhida.id, [p["user_id"] for p in por_hp[:quantos]]
        return "habilidade", escolhida.id, validos[:quantos]

    async def agir(self, run, estado, uid) -> None:
        faz, qual, alvos = await self.decidir(run, estado, uid)
        inter = FakeInteraction(self.canal, uid, await self.painel(run))
        if faz == "pocao":
            await self.cog.usar_pocao(inter, self.run_id, "OBJ", qual)
        elif faz == "habilidade":
            await self.cog.usar_habilidade(inter, self.run_id, "OBJ", qual, alvos)
        else:
            await self.cog.atacar(inter, self.run_id, "OBJ")
        depois = await _banco(self.conn)
        self.acoes.append({
            "rodada": estado.rodada,
            "quem": uid,
            "faz": faz if qual is None else f"{faz}:{qual}",
            "alvos": alvos,
            "leu": _leu(inter),
            "canal": self.olho.mudancas(),
            "banco": _diferenca(self.foto, depois),
        })
        self.foto = depois

    async def jogar(self) -> dict:
        abertura = await self.abrir()
        tentativas: dict[tuple, int] = {}
        motivo = None
        while motivo is None:
            run = await self.run()
            if not await self.em_combate(run):
                motivo = f"a run saiu do combate: {run['status'] if run else 'sumiu'}"
                break
            estado = await self.le.estado(run, self.sala)
            if estado is None:
                motivo = "o combate sumiu"
                break
            if estado.rodada > LIMITE_DE_RODADAS:
                motivo = "limite de rodadas"
                break
            uid = await self.quem_age(run, estado)
            if uid is None:
                raise RuntimeError(
                    f"{self.definicao['nome']}: ninguem esta sendo esperado na "
                    f"rodada {estado.rodada}, e o combate nao acabou"
                )
            chave = (estado.rodada, uid)
            tentativas[chave] = tentativas.get(chave, 0) + 1
            if tentativas[chave] > TENTATIVAS_POR_VEZ:
                raise RuntimeError(
                    f"{self.definicao['nome']}: {uid} clicou {TENTATIVAS_POR_VEZ} vezes"
                    f" na rodada {estado.rodada} e a vez nao andou"
                )
            await self.agir(run, estado, uid)
        return {
            "cenario": self.definicao,
            "abertura": abertura,
            "acoes": self.acoes,
            "fim": {"motivo": motivo},
        }


async def jogar(definicao: dict) -> dict:
    conn = None
    try:
        with aleatorio.usar(random.Random(definicao["semente"])):
            conn, canal, cog, incursao, run_id, jogadores = await _montar(definicao)
            jogo = _Jogo(definicao, conn, canal, cog, incursao, run_id, jogadores)
            gravado = await jogo.jogar()
        # Ida e volta pelo JSON: tupla vira lista e chave vira texto, como
        # no arquivo, para a comparacao ser de igual para igual.
        return json.loads(json.dumps(gravado, ensure_ascii=False))
    finally:
        if conn is not None:
            await conn.close()
        for sufixo in ("", "-wal", "-shm"):
            Path(f"{BANCO}{sufixo}").unlink(missing_ok=True)


# ----------------------------------------------------------------- comparacao


def _arquivo(nome: str, pasta: Path = PASTA) -> Path:
    return pasta / f"{nome}.json"


def _escrever(caminho: Path, gravado: dict) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    # `newline="\n"`: o arquivo e o mesmo no Windows e no CI.
    with open(caminho, "w", encoding="utf-8", newline="\n") as f:
        json.dump(gravado, f, ensure_ascii=False, indent=1)
        f.write("\n")


def _primeira_diferenca(esperado, obtido, caminho="") -> str | None:
    """O primeiro lugar onde os dois divergem, como caminho legível."""
    if type(esperado) is not type(obtido):
        return f"{caminho}: era {esperado!r:.300}, veio {obtido!r:.300}"
    if isinstance(esperado, dict):
        for chave in list(esperado) + [k for k in obtido if k not in esperado]:
            if chave not in obtido:
                return f"{caminho}.{chave}: sumiu (era {esperado[chave]!r:.300})"
            if chave not in esperado:
                return f"{caminho}.{chave}: apareceu ({obtido[chave]!r:.300})"
            achou = _primeira_diferenca(esperado[chave], obtido[chave], f"{caminho}.{chave}")
            if achou:
                return achou
        return None
    if isinstance(esperado, list):
        for i, (a, b) in enumerate(zip(esperado, obtido)):
            achou = _primeira_diferenca(a, b, f"{caminho}[{i}]")
            if achou:
                return achou
        if len(esperado) != len(obtido):
            return f"{caminho}: eram {len(esperado)} itens, vieram {len(obtido)}"
        return None
    if isinstance(esperado, str) and esperado != obtido:
        return f"{caminho}: {_trecho(esperado, obtido)}"
    if esperado != obtido:
        return f"{caminho}: era {esperado!r:.300}, veio {obtido!r:.300}"
    return None


def _trecho(esperado: str, obtido: str, antes: int = 60, depois: int = 120) -> str:
    """Os dois textos em volta do primeiro caractere que difere.

    O painel tem milhares de caracteres e a diferença costuma estar no fim;
    cortar pelo começo mostrava duas metades iguais e escondia o que mudou.
    """
    i = next((k for k, (a, b) in enumerate(zip(esperado, obtido)) if a != b),
             min(len(esperado), len(obtido)))
    inicio = max(0, i - antes)
    reticencias = "…" if inicio else ""
    return (f"difere no caractere {i}\n"
            f"      era:  {reticencias}{esperado[inicio:i + depois]!r}\n"
            f"      veio: {reticencias}{obtido[inicio:i + depois]!r}")


def _onde(gravado: dict, caminho: str) -> str:
    """Contexto da ação em que a diferença caiu: rodada, quem, o que fazia."""
    achou = re.match(r"\.acoes\[(\d+)\]", caminho)
    if not achou:
        return ""
    i = int(achou.group(1))
    acoes = gravado.get("acoes", [])
    if i >= len(acoes):
        return ""
    a = acoes[i]
    return f"  (acao {i}: rodada {a['rodada']}, jogador {a['quem']}, {a['faz']})"


def _resumo(gravado: dict) -> str:
    acoes = gravado["acoes"]
    rodadas = acoes[-1]["rodada"] if acoes else 0
    tamanho = len(json.dumps(gravado, ensure_ascii=False)) // 1024
    return (f"{len(acoes)} acoes, {rodadas} rodadas, {gravado['fim']['motivo']}"
            f" ({tamanho} KB)")


async def regravar(cenarios) -> None:
    for cenario in cenarios:
        gravado = await jogar(_definicao(cenario))
        _escrever(_arquivo(cenario["nome"]), gravado)
        print(f"  {cenario['nome']}: gravado — {_resumo(gravado)}")


async def comparar(cenarios) -> list[str]:
    falhas = []
    for cenario in cenarios:
        caminho = _arquivo(cenario["nome"])
        if not caminho.exists():
            falhas.append(f"{cenario['nome']}: sem referencia gravada ({caminho.name});"
                          " rode com --regravar")
            continue
        esperado = json.loads(caminho.read_text(encoding="utf-8"))
        # O cenario do codigo tem de ser o gravado. Mexer em CENARIOS sem
        # regravar faria o teste comparar o combate novo com o antigo, e a
        # falha pareceria do cog.
        definicao = json.loads(json.dumps(_definicao(cenario), ensure_ascii=False))
        mudou = _primeira_diferenca(esperado["cenario"], definicao, ".cenario")
        if mudou:
            falhas.append(f"{cenario['nome']}: o cenario mudou desde a gravacao"
                          f" ({mudou}); rode com --regravar se foi de proposito")
            continue
        obtido = await jogar(esperado["cenario"])
        diferenca = _primeira_diferenca(esperado, obtido)
        if diferenca:
            _escrever(_arquivo(cenario["nome"], OBTIDO), obtido)
            falhas.append(
                f"{cenario['nome']}: o combate mudou\n    {diferenca}"
                f"{_onde(esperado, diferenca)}\n"
                f"    o que veio agora: {_arquivo(cenario['nome'], OBTIDO).relative_to(RAIZ)}"
            )
            continue
        # O que sobrou de uma falha anterior ja nao diz nada, e confundiria.
        _arquivo(cenario["nome"], OBTIDO).unlink(missing_ok=True)
        print(f"  {cenario['nome']}: igual ao gravado — {_resumo(obtido)}")
    if OBTIDO.is_dir() and not any(OBTIDO.iterdir()):
        OBTIDO.rmdir()
    return falhas


def main(argv: list[str]) -> int:
    fakes.iniciativa_de_verdade(True)
    cenarios = CENARIOS
    if "--so" in argv:
        nome = argv[argv.index("--so") + 1]
        cenarios = [c for c in CENARIOS if c["nome"] == nome]
        if not cenarios:
            print(f"cenario desconhecido: {nome}")
            return 2
    if "--regravar" in argv:
        asyncio.run(regravar(cenarios))
        print("REFERENCIA REGRAVADA")
        return 0
    falhas = asyncio.run(comparar(cenarios))
    if falhas:
        print("\n".join(falhas))
        return 1
    print("TESTES DA REFERENCIA DE COMBATE PASSARAM")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
