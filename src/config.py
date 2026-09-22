"""Configuracao lida do .env."""
import os
from datetime import timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")

TOKEN = os.getenv("DISCORD_TOKEN", "")
GUILD_ID = int(os.getenv("GUILD_ID") or 0)
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
