"""
Modulo di configurazione centralizzata per l'applicazione di Gestione Spese.
Carica le variabili d'ambiente da .env e definisce costanti globali.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

import sys

# Percorso base del progetto (supporta sia script Python che eseguibile portatile compilato)
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

# Carica le variabili dal file .env se presente
load_dotenv(BASE_DIR / ".env")

# Configurazione Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_USER_ID = os.getenv("TELEGRAM_USER_ID", "").strip()

# Se impostato, converti TELEGRAM_USER_ID in intero per confronti rapidi
AUTHORIZED_USER_ID = int(TELEGRAM_USER_ID) if TELEGRAM_USER_ID.isdigit() else None

# Configurazione Budget Mensile di default (€)
try:
    MONTHLY_BUDGET = float(os.getenv("MONTHLY_BUDGET", "1000.0"))
except ValueError:
    MONTHLY_BUDGET = 1000.0

# Percorso Database SQLite
DB_NAME = os.getenv("DB_NAME", "spese.db").strip()
DB_PATH = BASE_DIR / DB_NAME

# Configurazione Google Sheets & Cloud Sync
GOOGLE_SHEETS_URL = os.getenv("GOOGLE_SHEETS_URL", os.getenv("GOOGLE_SCRIPT_URL", "")).strip()

# Categorie prestabilite e standardizzate
CATEGORIES = [
    "Alimentari",
    "Trasporti",
    "Casa",
    "Svago",
    "Salute",
    "Altro"
]

# Mappatura case-insensitive per normalizzare gli input utente
CATEGORIES_LOOKUP = {c.strip().lower(): c for c in CATEGORIES}

# Emoji associate a ciascuna categoria per una UI gradevole
CATEGORY_ICONS = {
    "Alimentari": "🛒",
    "Trasporti": "🚗",
    "Casa": "🏠",
    "Svago": "🎉",
    "Salute": "💊",
    "Altro": "📦"
}
