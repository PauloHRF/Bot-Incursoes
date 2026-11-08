"""Configuracao lida do .env."""
import os
from datetime import timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")

TOKEN = os.getenv("DISCORD_TOKEN", "")


def guildas_de(cru: str) -> tuple[int, ...]:
    """Le uma lista de ids de guilda separados por virgula.

    Funcao pura, e separada da leitura do ambiente, porque e ela que tem
    regra: ignora espaco, vazio e lixo, e tira repetido mantendo a ordem —
    sincronizar duas vezes na mesma guilda e dois POST para o mesmo lugar.
    """
    vistos: dict[int, None] = {}
    for parte in cru.replace(";", ",").split(","):
        parte = parte.strip()
        if parte.isdigit() and int(parte) > 0:
            vistos[int(parte)] = None
    return tuple(vistos)


# Em que guildas os comandos de barra sao REGISTRADOS. Isto nao tem nada a ver
# com os dados: o banco separa por servidor pela coluna `guild_id` das tabelas,
# e um bot em tres servidores usa um banco so.
#
# Com guilda(s), os comandos aparecem NA HORA, em cada uma. Vazio, o registro e
# global: vale em todo servidor onde o bot esta, inclusive nos que entrarem
# depois, mas a primeira propagacao leva ate ~1h.
#
# GUILD_ID (singular) e o nome antigo e continua valendo, como INTERVALO_DIAS.
GUILD_IDS = guildas_de(os.getenv("GUILD_IDS") or os.getenv("GUILD_ID") or "")
DB_PATH = RAIZ / os.getenv("DB_PATH", "data/incursoes.db")
# A semana vira na segunda-feira 00:00 deste fuso (padrao: horario de Brasilia).
# Fuso fixo em vez de zoneinfo: o Brasil nao tem mais horario de verao, e assim o
# bot nao depende do pacote tzdata na maquina que hospeda.
FUSO = timezone(timedelta(hours=float(os.getenv("FUSO_UTC") or -3)))

# Quantas semanas cada jogador espera entre incursoes. 0 libera geral (playtest).
# INTERVALO_DIAS e o nome antigo: se ainda estiver no .env, vira semanas.
_semanas = os.getenv("INTERVALO_SEMANAS")
if _semanas is None and os.getenv("INTERVALO_DIAS"):
    _dias = int(os.getenv("INTERVALO_DIAS") or 7)
    _semanas = 0 if _dias <= 0 else -(-_dias // 7)
INTERVALO_SEMANAS = int(_semanas if _semanas is not None else 1)

# Tamanho do grupo fixo de uma run. A votacao nao tem prazo: fecha na maioria.
TAMANHO_GRUPO = int(os.getenv("TAMANHO_GRUPO") or 5)

# Pontos que a Organizacao ganha so por o grupo ter levado a run ate o fim,
# vitoria ou derrota. Os bonus maiores vem das salas e da conclusao.
PONTOS_PARTICIPACAO = int(os.getenv("PONTOS_PARTICIPACAO") or 2)
