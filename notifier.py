"""
Modulo per l'invio di notifiche Telegram disaccoppiate via API HTTP.
Supporta notifiche differenziate per Abbonamenti e Rate a tempo determinato.
"""
import logging
import requests
from config import TELEGRAM_BOT_TOKEN, AUTHORIZED_USER_ID, CATEGORY_ICONS

logger = logging.getLogger(__name__)


def send_telegram_notification(message: str) -> bool:
    """
    Invia un messaggio di notifica all'utente autorizzato tramite l'API HTTP di Telegram.
    """
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN in ("tuo_token_qui", "INCOLLA_QUI_IL_TUO_TOKEN", ""):
        logger.warning("Impossibile inviare notifica: TELEGRAM_BOT_TOKEN non configurato.")
        return False

    if not AUTHORIZED_USER_ID:
        logger.warning("Impossibile inviare notifica: TELEGRAM_USER_ID non configurato.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": AUTHORIZED_USER_ID,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:
        resp = requests.post(url, json=payload, timeout=6.0)
        return resp.status_code == 200
    except Exception as e:
        logger.error(f"Errore invio notifica Telegram: {e}")
        return False


def notify_recurring_charge(
    tipo: str,
    nome: str,
    importo: float,
    categoria: str,
    giorno: int,
    rata_corrente: int = None,
    rate_totali: int = None,
    completata: bool = False,
    tx_id: int = None
) -> bool:
    """
    Invia una notifica formattata e differenziata per Abbonamenti o Rate.
    """
    icon = CATEGORY_ICONS.get(categoria, "🏷️")
    id_str = f" `[ID #{tx_id}]`" if tx_id else ""

    if tipo == "rata":
        tot_str = f" di {rate_totali}" if rate_totali else ""
        pct_str = f" ({int((rata_corrente / rate_totali) * 100)}%)" if rate_totali else ""
        
        lines = [
            f"🔔 *ADDEBITO RATA REGISTRATO*{id_str}\n",
            f"📌 Finanziamento: *{nome}*",
            f"⏳ Progresso Piano: *Rata {rata_corrente}{tot_str}*{pct_str}",
            f"{icon} Categoria: *{categoria}*",
            f"💶 Importo addebitato: `{importo:.2f} €`",
            f"📅 Giorno addebito: *{giorno}* del mese"
        ]

        if completata:
            lines.append("\n🎉 *PIANO DI AMMORTAMENTO COMPLETATO!*")
            lines.append(f"Tutte le {rate_totali} rate sono state saldate con successo. La spesa è stata archiviata automaticamente.")
        else:
            residue = rate_totali - rata_corrente if rate_totali else 0
            lines.append(f"\n_Restano {residue} rate prima dell'estinzione del piano._")

        msg = "\n".join(lines)
    else:
        # Abbonamento a tempo indeterminato
        msg = (
            f"🔔 *ADDEBITO ABBONAMENTO REGISTRATO*{id_str}\n\n"
            f"🔁 Servizio: *{nome}*\n"
            f"{icon} Categoria: *{categoria}*\n"
            f"💶 Quota mensile: `{importo:.2f} €`\n"
            f"📅 Giorno addebito: *{giorno}* di ogni mese\n\n"
            f"_Spesa fissa a durata indeterminata registrata nel bilancio mensile._"
        )

    return send_telegram_notification(msg)
