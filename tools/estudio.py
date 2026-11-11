"""A bancada de quem escreve dungeon. Roda na máquina do autor.

    python tools/estudio.py
    python tools/estudio.py --porta 8765 --sem-navegador

Sobe um servidor em 127.0.0.1 e abre a página. Ali dá para escrever sala,
montar o filtro da dungeon vendo o pool que ele deixa, medir a sala contra o
grupo e exportar o JSON pronto para mandar.

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
import json
import random
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import bestiario, incursoes as I  # noqa: E402
from src.rules import ATRIBUTOS, PERICIAS, TIER_MAXIMO  # noqa: E402
from src import classes  # noqa: E402

PAGINA = Path(__file__).resolve().parent / "estudio" / "index.html"
PASTA_BANCOS = RAIZ / "data" / "bancos"
PASTA_INCURSOES = RAIZ / "data" / "incursoes"

# Quantos confrontos por tamanho de grupo. 2000 leva ~1,8s por tamanho nesta
# maquina; o padrao e menor para o botao responder rapido, e a pagina pede
# mais quando o autor quer confirmar um numero.
REPETICOES_PADRAO = 800
REPETICOES_MAXIMO = 20000
GRUPOS_PADRAO = (5, 4, 3, 2)


# --------------------------------------------------------------- leitura


def _bancos() -> dict[str, Any]:
    """Os bancos do disco, tolerando o arquivo quebrado como o bot faz."""
    bancos, problemas = I.carregar_bancos_tolerante(PASTA_BANCOS)
    return {
        "bancos": {
            nome: {
                "organizacao": nome,
                "arquivo": f"{I.arquivo_da_organizacao(nome)}.json",
                "salas": [s.para_dict() for s in banco.salas],
            }
            for nome, banco in sorted(bancos.items())
        },
        "problemas": problemas,
    }


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


def _faixas_de_combate() -> dict[str, list[float]]:
    """As faixas de taxa de vitória que o sugeridor procura."""
    import sugestor

    return {nome: list(faixa) for nome, faixa in sugestor.FAIXAS_DE_VITORIA.items()}


def conteudo() -> dict[str, Any]:
    """Tudo que a página precisa saber para desenhar os campos.

    Vem do código, e não repetido no JavaScript: tema, tipo de sala e limite
    mudam aqui dentro, e uma lista copiada na página envelheceria calada.
    """
    incursoes, ruins = I.carregar_todas_tolerante(PASTA_INCURSOES)
    do_disco = _bancos()
    return {
        "temas": list(I.TEMAS),
        "tipos": list(I.TIPOS_SALA),
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
        },
        "ambientes": list(bestiario.AMBIENTES),
        # Os tipos de bicho com quantas criaturas cada um tem: sem o número, o
        # autor não sabe que 'ooze' corta o bestiário para quatro.
        "tipos_de_bicho": _tipos_de_bicho(),
        "dificuldades_de_combate": _faixas_de_combate(),
        "bancos": do_disco["bancos"],
        "incursoes": {i.id: i.para_dict() for i in sorted(
            incursoes.values(), key=lambda x: x.id
        )},
        "problemas": do_disco["problemas"] + ruins,
    }


# ------------------------------------------------------------ conferir


def _tipo_do_payload(dados: dict[str, Any]) -> str:
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


def _avisos(tipo: str, dados: dict[str, Any]) -> list[str]:
    """O que passa no bot e ainda assim não faz o que o autor espera."""
    import validar_conteudo as V

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

    incursao = SimpleNamespace(filtro=filtro, tamanho=tamanho,
                               passos=I.TAMANHOS[tamanho])
    cruzados, avisos = I.conferir_filtro(incursao, banco)
    sorteaveis = I.salas_sorteaveis(banco)
    deixadas = filtro.aplicar(sorteaveis)
    passos = I.TAMANHOS[tamanho]
    return {
        "pool": [{"id": s.id, "nome": s.nome, "tipo": s.tipo, "temas": s.temas}
                 for s in deixadas],
        "sorteaveis": len(sorteaveis),
        "no_banco": len(banco.salas),
        "terminar": passos,
        "folga": passos + I.OPCOES_POR_PASSO - 1,
        "problemas": cruzados,
        "avisos": avisos,
    }


# -------------------------------------------------------------- simular


def _inteiro(valor: Any, padrao: int, menor: int, maior: int) -> int:
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return padrao
    return max(menor, min(maior, numero))


def simular(payload: dict[str, Any]) -> dict[str, Any]:
    """Mede a sala de combate com o motor do bot.

    O grupo simulado é de uma classe só, de propósito: o que se quer medir é a
    SALA, e misturar classes trocaria a variação da sala pela variação do
    grupo. A semente vai na resposta para dois autores comparando números
    verem o mesmo número.
    """
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

    classe = str(payload.get("classe") or "guerreiro")
    if classes.classe(classe) is None:
        return {"erro": f"classe desconhecida: {classe}."}
    nivel = _inteiro(payload.get("nivel"), min(10, tier * 2), 1, 10)
    repeticoes = _inteiro(payload.get("repeticoes"), REPETICOES_PADRAO, 50,
                          REPETICOES_MAXIMO)
    semente = payload.get("semente")
    if not isinstance(semente, int):
        semente = random.randrange(1, 10**8)

    grupos = payload.get("grupos") or list(GRUPOS_PADRAO)
    grupos = [g for g in grupos if isinstance(g, int) and 1 <= g <= 6]
    if not grupos:
        grupos = list(GRUPOS_PADRAO)

    args = SimpleNamespace(classe=classe, nivel=nivel, repeticoes=repeticoes)
    medidas = []
    for tamanho in grupos:
        # Um rng por tamanho, derivado da mesma semente: assim mudar a lista
        # de grupos nao muda o numero dos outros.
        bruto = sc.simular(monstros, tamanho, args, random.Random(f"{semente}:{tamanho}"))
        medidas.append({
            "grupo": tamanho,
            "taxa": bruto["taxa"],
            "rodadas": None if bruto["rodadas"] != bruto["rodadas"] else bruto["rodadas"],
            "caidos": bruto["caidos"],
        })
    return {
        "sala": sala.id,
        "tema": tema,
        "tier": tier,
        "classe": classe,
        "nivel": nivel,
        "repeticoes": repeticoes,
        "semente": semente,
        "criaturas": [{"nome": m.nome, "ca": m.ca, "hp": m.hp} for m in monstros],
        "medidas": medidas,
    }


def sugerir(payload: dict[str, Any]) -> dict[str, Any]:
    """Procura um bando que caia na faixa daquela dificuldade.

    A dificuldade aqui não é um rótulo que o estúdio escreve: é uma faixa de
    taxa de vitória que ele PROCURA, simulando. O número que volta é o que ele
    mediu, e `na_faixa` diz se caiu dentro — inclusive quando não caiu.
    """
    import sugestor

    return sugestor.sugerir(
        tier=_inteiro(payload.get("tier"), 2, 1, TIER_MAXIMO),
        ambiente=(payload.get("ambiente") or None),
        tipo=(payload.get("tipo") or None),
        dificuldade=str(payload.get("dificuldade") or "media"),
        classe=str(payload.get("classe") or "guerreiro"),
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
        self.end_headers()
        self.wfile.write(corpo)

    def _json(self, codigo: int, dados: Any) -> None:
        self._responder(
            codigo, json.dumps(dados, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def do_GET(self) -> None:  # noqa: N802
        caminho = self.path.split("?")[0]
        if caminho in ("/", "/index.html"):
            try:
                self._responder(
                    200, PAGINA.read_bytes(), "text/html; charset=utf-8"
                )
            except OSError:
                self._json(500, {"erro": f"não achei a página em {PAGINA}."})
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
