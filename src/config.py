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
