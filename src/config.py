"""Configuracao lida do .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")

TOKEN = os.getenv("DISCORD_TOKEN", "")
GUILD_ID = int(os.getenv("GUILD_ID") or 0)
DB_PATH = RAIZ / os.getenv("DB_PATH", "data/incursoes.db")
INTERVALO_DIAS = int(os.getenv("INTERVALO_DIAS") or 7)

# Tamanho do grupo fixo de uma run e prazo maximo de cada votacao.
TAMANHO_GRUPO = int(os.getenv("TAMANHO_GRUPO") or 5)
MINUTOS_VOTACAO = int(os.getenv("MINUTOS_VOTACAO") or 30)

# Pontos que a Organizacao ganha so por o grupo ter levado a run ate o fim,
# vitoria ou derrota. Os bonus maiores vem das salas e da conclusao.
PONTOS_PARTICIPACAO = int(os.getenv("PONTOS_PARTICIPACAO") or 2)
