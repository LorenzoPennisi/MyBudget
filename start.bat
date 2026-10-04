@echo off
chcp 65001 >nul
echo ======================================================
echo   Avvio Gestione Spese Personali (Applicazione Desktop)
echo ======================================================

IF NOT EXIST venv (
    echo [INFO] Creazione ambiente virtuale venv in corso...
    python -m venv venv
    call venv\Scripts\activate.bat
    echo [INFO] Installazione dipendenze in corso...
    pip install -r requirements.txt
) ELSE (
    call venv\Scripts\activate.bat
)

IF NOT EXIST .env (
    echo [AVVISO] File .env non trovato! Creazione da .env.example...
    copy .env.example .env
    echo [!] Ricordati di configurare TELEGRAM_BOT_TOKEN nel file .env!
)

python desktop_app.py
