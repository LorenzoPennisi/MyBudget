"""
Modulo di sincronizzazione tra il database locale SQLite e Google Fogli / Google Drive.
Permette all'app desktop di:
1. Leggere le spese registrate dal telefono tramite il Bot Telegram mentre il PC era spento (24/7).
2. Caricare tutte le spese storiche/passate memorizzate in SQLite sul Foglio Google.
3. Configurare e diagnosticare automaticamente il Webhook di Telegram su Google Cloud a costo zero.
"""
import csv
import io
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import requests

from config import BASE_DIR, CATEGORIES_LOOKUP, TELEGRAM_BOT_TOKEN
import database

logger = logging.getLogger(__name__)

ENV_FILE = BASE_DIR / ".env"


def get_google_sync_url() -> str:
    """Restituisce l'URL configurato per Google Sheets o Google Apps Script."""
    return os.getenv("GOOGLE_SHEETS_URL", os.getenv("GOOGLE_SCRIPT_URL", "")).strip()


def save_google_sync_url(url: str) -> bool:
    """Salva o aggiorna l'URL di Google Sheets / Apps Script nel file .env."""
    url = url.strip()
    os.environ["GOOGLE_SHEETS_URL"] = url
    try:
        lines = []
        found = False
        if ENV_FILE.exists():
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("GOOGLE_SHEETS_URL=") or line.startswith("GOOGLE_SCRIPT_URL="):
                        lines.append(f"GOOGLE_SHEETS_URL={url}\n")
                        found = True
                    else:
                        lines.append(line)
        if not found:
            lines.append(f"\nGOOGLE_SHEETS_URL={url}\n")

        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.writelines(lines)
        return True
    except Exception as e:
        logger.error(f"Errore durante il salvataggio di GOOGLE_SHEETS_URL in .env: {e}")
        return False


def set_telegram_webhook(url: Optional[str] = None) -> Dict[str, Any]:
    """
    Collega automaticamente il Webhook di Telegram all'URL di Google Apps Script.
    In questo modo Telegram inoltra tutte le spese direttamente a Google anche a PC spento.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN).strip()
    if not token or token in ("tuo_token_qui", "INCOLLA_QUI_IL_TUO_TOKEN"):
        return {"success": False, "error": "Token Telegram mancante in .env"}

    target_url = (url or get_google_sync_url()).strip()
    if not target_url:
        return {"success": False, "error": "URL Google Apps Script mancante"}

    # Assicurati che non sia l'URL /dev
    if target_url.endswith("/dev"):
        target_url = target_url[:-4] + "/exec"

    api_url = f"https://api.telegram.org/bot{token}/setWebhook"
    try:
        resp = requests.get(api_url, params={"url": target_url, "drop_pending_updates": "true"}, timeout=10.0)
        data = resp.json()
        if data.get("ok"):
            return {"success": True, "description": data.get("description", "Webhook impostato con successo")}
        else:
            return {"success": False, "error": data.get("description", "Errore impostazione webhook")}
    except Exception as e:
        return {"success": False, "error": str(e)}


def check_cloud_diagnostics() -> Dict[str, Any]:
    """
    Esegue una diagnosi completa del collegamento tra Telegram, Google Apps Script e Google Sheets:
    - Verifica se Telegram riceve risposte corrette o errori 401.
    - Verifica se Google Apps Script è distribuito con permessi pubblici ('Chiunque').
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN).strip()
    url = get_google_sync_url()
    
    result = {
        "webhook_url": "",
        "webhook_ok": False,
        "webhook_pending": 0,
        "webhook_last_error": "",
        "script_accessible": False,
        "script_auth_error": False,
        "message": ""
    }

    if not url:
        result["message"] = "URL di Google Apps Script non configurato."
        return result

    # 1. Test accesso a Google Apps Script
    try:
        resp = requests.get(url, headers={"User-Agent": "ContabileApp/2.0"}, timeout=10.0)
        if resp.status_code == 401 or "accounts.google.com" in resp.text or "Sign in" in resp.text:
            result["script_auth_error"] = True
            result["message"] = (
                "⚠️ ATTENZIONE: Google ha bloccato la richiesta con errore 401 (Richiede Login)!\n"
                "Nella schermata di distribuzione di Apps Script devi modificare:\n"
                "'Chi può accedere' da 'Solo io' a 'Chiunque' (Anyone)."
            )
            return result
        elif resp.status_code == 200:
            result["script_accessible"] = True
    except Exception as e:
        result["message"] = f"Errore di rete verso Google: {e}"
        return result

    # 2. Test stato Webhook Telegram
    if token:
        try:
            wh_resp = requests.get(f"https://api.telegram.org/bot{token}/getWebhookInfo", timeout=10.0)
            wh_data = wh_resp.json()
            if wh_data.get("ok"):
                r = wh_data.get("result", {})
                result["webhook_url"] = r.get("url", "")
                result["webhook_pending"] = r.get("pending_update_count", 0)
                result["webhook_last_error"] = r.get("last_error_message", "")
                result["webhook_ok"] = bool(result["webhook_url"] and not result["webhook_last_error"])
                
                if "401" in result["webhook_last_error"]:
                    result["script_auth_error"] = True
                    result["message"] = (
                        "⚠️ Telegram ha ricevuto errore 401 Unauthorized da Google!\n"
                        "Significa che in Apps Script hai lasciato 'Chi può accedere: Solo io'.\n"
                        "Imposta 'Chi può accedere: Chiunque' per permettere a Telegram di scrivere."
                    )
                    return result
        except Exception:
            pass

    if result["script_accessible"] and result["webhook_ok"]:
        result["message"] = "✅ Collegamento perfetto! Il bot Telegram e Google Fogli funzionano h24."
    else:
        result["message"] = "Stato verificato."
        
    return result


def fetch_from_cloud() -> Dict[str, Any]:
    """
    Scarica le transazioni e i piani (rate/abbonamenti) da Google Sheets o dall'endpoint Google Apps Script.
    Supporta sia l'URL WebApp (Apps Script JSON) che l'URL diretto di esportazione CSV di Google Sheets.
    Restituisce un dizionario con 'transactions', 'plans' e 'summary'.
    """
    url = get_google_sync_url()
    if not url:
        raise ValueError("Nessun URL Google Sheets / Apps Script configurato.")

    if "docs.google.com/spreadsheets" in url and "/export" not in url and "/exec" not in url:
        parts = url.split("/d/")
        if len(parts) > 1:
            sheet_id = parts[1].split("/")[0]
            url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid=0"

    headers = {"User-Agent": "ContabileApp/2.0"}
    resp = requests.get(url, headers=headers, timeout=12.0)

    if resp.status_code == 401 or "accounts.google.com" in resp.text:
        raise PermissionError(
            "Accesso negato da Google (401). Verifica in Apps Script di aver impostato 'Chi può accedere: Chiunque'."
        )

    resp.raise_for_status()
    content_type = resp.headers.get("Content-Type", "")
    
    # Caso 1: Risposta JSON (da Google Apps Script WebApp)
    if "json" in content_type or resp.text.strip().startswith("{"):
        try:
            data = resp.json()
            if isinstance(data, dict):
                return {
                    "transactions": data.get("transactions", []),
                    "plans": data.get("plans", []),
                    "summary": data.get("summary", {})
                }
            elif isinstance(data, list):
                return {"transactions": data, "plans": [], "summary": {}}
        except Exception:
            pass

    # Caso 2: Risposta CSV
    csv_file = io.StringIO(resp.text)
    reader = csv.reader(csv_file)
    rows = list(reader)
    if not rows or len(rows) < 2:
        return {"transactions": [], "plans": [], "summary": {}}

    header = [h.strip().lower() for h in rows[0]]
    id_idx = header.index("id") if "id" in header else 0
    date_idx = header.index("data") if "data" in header else 1
    amt_idx = header.index("importo") if "importo" in header else 2
    cat_idx = header.index("categoria") if "categoria" in header else 3
    desc_idx = header.index("descrizione") if "descrizione" in header else 4
    src_idx = header.index("origine") if "origine" in header else -1
    ts_idx = header.index("timestamp") if "timestamp" in header else -1

    transactions = []
    for r in rows[1:]:
        if not r or len(r) <= max(date_idx, amt_idx):
            continue
        try:
            raw_amt = r[amt_idx].replace("€", "").replace(",", ".").strip()
            amount = float(raw_amt)
            d_val = r[date_idx].strip()
            iso_date = database.normalize_date_to_iso(d_val)
            cat = r[cat_idx].strip() if len(r) > cat_idx else "Altro"
            desc = r[desc_idx].strip() if len(r) > desc_idx else ""
            src = r[src_idx].strip() if src_idx != -1 and len(r) > src_idx else "bot"
            ts = r[ts_idx].strip() if ts_idx != -1 and len(r) > ts_idx else f"{iso_date} 12:00:00"
            raw_id = int(r[id_idx].replace("#", "")) if len(r) > id_idx and r[id_idx].replace("#", "").isdigit() else 0

            transactions.append({
                "id": raw_id,
                "date": iso_date,
                "amount": amount,
                "category": cat,
                "description": desc,
                "source": src,
                "timestamp": ts
            })
        except Exception as err:
            logger.warning(f"Salto riga malformata da Google Sheets: {r} -> {err}")
            continue

    return {"transactions": transactions, "plans": [], "summary": {}}


def sync_with_google_sheets() -> Dict[str, Any]:
    """
    Scarica le nuove transazioni e i piani registrati su Google Sheets mentre l'app era chiusa
    e li inserisce nel DB SQLite locale senza generare duplicati.
    """
    url = get_google_sync_url()
    if not url:
        return {
            "success": False,
            "error": "URL non configurato",
            "message": "Nessun URL di Google Sheets o Apps Script impostato nelle impostazioni."
        }

    try:
        cloud_data = fetch_from_cloud()
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"Errore di connessione a Google Sheets: {e}"
        }

    cloud_txs = cloud_data.get("transactions", []) if isinstance(cloud_data, dict) else (cloud_data or [])
    cloud_plans = cloud_data.get("plans", []) if isinstance(cloud_data, dict) else []

    # 1. Sincronizzazione Transazioni: IDs 100% IDENTICI tra Google Sheets e SQLite
    imported_count = 0
    updated_count = 0
    deleted_count = 0

    with database.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, date, amount, category, description, source, timestamp FROM transactions;")
        local_rows = {int(r["id"]): dict(r) for r in cursor.fetchall()}

        cloud_ids_in_sheet = set()
        for ctx in cloud_txs:
            c_id = int(ctx.get("id") or 0)
            if not c_id:
                continue
            cloud_ids_in_sheet.add(c_id)

            norm_cat = CATEGORIES_LOOKUP.get(ctx["category"].strip().lower(), ctx["category"].strip())
            iso_date = database.normalize_date_to_iso(ctx["date"])
            amt = round(float(ctx["amount"]), 2)
            desc = ctx.get("description", "").strip()
            ts = ctx.get("timestamp") or f"{iso_date} 12:00:00"
            src = ctx.get("source") or "bot"

            if c_id in local_rows:
                # Transazione già presente con lo STESSO IDENTICO ID
                loc = local_rows[c_id]
                loc_amt = round(float(loc["amount"]), 2)
                loc_cat = loc["category"].strip()
                loc_desc = (loc["description"] or "").strip()
                loc_date = database.normalize_date_to_iso(loc["date"])

                if (amt != loc_amt) or (norm_cat != loc_cat) or (desc != loc_desc) or (iso_date != loc_date):
                    cursor.execute(
                        """
                        UPDATE transactions
                        SET amount = ?, category = ?, description = ?, date = ?, cloud_id = ?
                        WHERE id = ?;
                        """,
                        (amt, norm_cat, desc, iso_date, c_id, c_id)
                    )
                    updated_count += 1
            else:
                # Nuova transazione: memorizza con lo STESSO IDENTICO ID DEL FOGLIO!
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO transactions (id, timestamp, date, amount, category, description, source, cloud_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (c_id, ts, iso_date, amt, norm_cat, desc, src, c_id)
                )
                imported_count += 1

        # Riconciliazione eliminazioni: se una spesa è stata rimossa dal foglio Google, eliminala anche da SQLite
        if cloud_ids_in_sheet:
            for loc_id in list(local_rows.keys()):
                if loc_id not in cloud_ids_in_sheet:
                    cursor.execute("DELETE FROM transactions WHERE id = ?;", (loc_id,))
                    deleted_count += 1

    # 2. Sincronizzazione Piani (Rate & Abbonamenti)
    local_plans = database.get_recurring_expenses_list()
    existing_plans = {p["nome_descrizione"].strip().lower(): p for p in local_plans}
    imported_plans_count = 0

    for cp in cloud_plans:
        p_name = str(cp.get("nome_descrizione", "")).strip()
        if not p_name:
            continue
        p_key = p_name.lower()
        if p_key not in existing_plans:
            try:
                database.add_recurring_expense(
                    tipo=str(cp.get("tipo", "abbonamento")),
                    nome_descrizione=p_name,
                    importo=float(cp.get("importo", 0.0)),
                    categoria=str(cp.get("categoria", "Altro")),
                    giorno_addebito=int(cp.get("giorno_addebito", 1)),
                    numero_rate_totali=int(cp["numero_rate_totali"]) if cp.get("numero_rate_totali") else None,
                    rate_pagate=int(cp.get("rate_pagate", 0)),
                    data_inizio=cp.get("data_inizio"),
                    stato=str(cp.get("stato", "attivo"))
                )
                imported_plans_count += 1
            except Exception as e_plan:
                logger.warning(f"Errore import piano {p_name} da cloud: {e_plan}")
        else:
            loc_p = existing_plans[p_key]
            cp_pagate = int(cp.get("rate_pagate", 0))
            cp_stato = str(cp.get("stato", loc_p["stato"]))
            if cp_pagate > loc_p["rate_pagate"] or cp_stato != loc_p["stato"]:
                with database.get_connection() as conn:
                    conn.cursor().execute(
                        "UPDATE recurring_expenses SET rate_pagate = ?, stato = ? WHERE id = ?;",
                        (max(cp_pagate, loc_p["rate_pagate"]), cp_stato, loc_p["id"])
                    )

    msg_items = []
    if imported_count > 0:
        msg_items.append(f"{imported_count} nuove spese")
    if updated_count > 0:
        msg_items.append(f"{updated_count} spese modificate")
    if deleted_count > 0:
        msg_items.append(f"{deleted_count} spese eliminate")
    if imported_plans_count > 0:
        msg_items.append(f"{imported_plans_count} nuovi piani")

    if not msg_items:
        final_msg = "Sincronizzazione completata: dati già aggiornati col cloud."
    else:
        final_msg = f"Sincronizzazione completata! ({', '.join(msg_items)})"

    return {
        "success": True,
        "imported": imported_count,
        "updated": updated_count,
        "deleted": deleted_count,
        "imported_plans": imported_plans_count,
        "total_cloud": len(cloud_txs),
        "message": final_msg
    }


def push_all_local_to_cloud() -> Dict[str, Any]:
    """
    Carica tutte le spese e i piani memorizzati nel database locale SQLite verso il Foglio Google.
    Permette di popolare il foglio Google con tutte le spese e rate inserite in precedenza.
    """
    url = get_google_sync_url()
    if not url:
        return {"success": False, "error": "URL Google non configurato"}

    local_df = database.get_transactions_df()
    local_plans = database.get_recurring_expenses_list()
    if local_df.empty and not local_plans:
        return {"success": True, "pushed": 0, "message": "Nessuna spesa o piano locale da sincronizzare."}

    records = []
    if not local_df.empty:
        for _, row in local_df.iterrows():
            records.append({
                "id": int(row["id"]),
                "date": str(row["date"]),
                "amount": float(row["amount"]),
                "category": str(row["category"]),
                "description": str(row["description"] or ""),
                "source": str(row["source"] or "desktop"),
                "timestamp": str(row.get("timestamp", f"{row['date']} 12:00:00"))
            })

    plans_payload = []
    for p in local_plans:
        plans_payload.append({
            "id": int(p["id"]),
            "tipo": str(p["tipo"]),
            "nome_descrizione": str(p["nome_descrizione"]),
            "importo": float(p["importo"]),
            "categoria": str(p["categoria"]),
            "giorno_addebito": int(p["giorno_addebito"]),
            "numero_rate_totali": p["numero_rate_totali"],
            "rate_pagate": int(p["rate_pagate"]),
            "stato": str(p["stato"]),
            "ultimo_mese_addebitato": str(p.get("ultimo_mese_addebitato") or ""),
            "data_inizio": str(p["data_inizio"])
        })

    payload = {
        "action": "bulk_push",
        "transactions": records,
        "plans": plans_payload
    }

    try:
        resp = requests.post(url, json=payload, timeout=25.0)
        if resp.status_code == 401 or "accounts.google.com" in resp.text:
            return {
                "success": False,
                "error": "Accesso negato da Google (401). Verifica 'Chi può accedere: Chiunque' in Apps Script."
            }
        
        data = resp.json()
        if data.get("status") == "success":
            pushed_tx = data.get("added_transactions", data.get("added", len(records)))
            pushed_plans = data.get("added_plans", len(plans_payload))
            return {
                "success": True,
                "pushed": pushed_tx,
                "pushed_plans": pushed_plans,
                "total": len(records),
                "message": f"Sincronizzazione riuscita! Caricate {pushed_tx} spese e {pushed_plans} piani sul foglio Google."
            }
        else:
            return {"success": False, "error": f"Risposta inattesa da Google: {resp.text[:100]}"}
    except Exception as e:
        return {"success": False, "error": f"Errore durante l'invio a Google: {e}"}


def send_delete_to_cloud(tx_id: int, cloud_id: Optional[int] = None) -> bool:
    """Se configurato un WebApp URL di Apps Script, inoltra la richiesta di eliminazione al foglio Google."""
    url = get_google_sync_url()
    if not url or "script.google.com" not in url:
        return False
    try:
        if cloud_id is not None:
            target_id = cloud_id
        else:
            target_id = tx_id
            tx = database.get_transaction_by_id(tx_id)
            if tx and tx.get("cloud_id"):
                target_id = int(tx["cloud_id"])

        delete_url = f"{url}?action=delete&id={target_id}"
        resp = requests.get(delete_url, timeout=8.0)
        return resp.status_code == 200
    except Exception as e:
        logger.warning(f"Impossibile sincronizzare eliminazione su cloud: {e}")
        return False


def send_edit_to_cloud(tx_id: int, amount: float, category: str, description: str, date_iso: str) -> Dict[str, Any]:
    """Se configurato un WebApp URL di Apps Script, inoltra la modifica della spesa al foglio Google."""
    url = get_google_sync_url()
    if not url or "script.google.com" not in url:
        return {"success": False, "error": "URL Google non configurato"}
    try:
        target_id = tx_id
        tx = database.get_transaction_by_id(tx_id)
        if tx and tx.get("cloud_id"):
            target_id = int(tx["cloud_id"])

        payload = {
            "action": "edit",
            "id": target_id,
            "amount": float(amount),
            "category": category,
            "description": description,
            "date": date_iso
        }
        resp = requests.post(url, json=payload, timeout=20.0)
        if resp.status_code == 200:
            try:
                res_json = resp.json()
                if res_json.get("status") == "success":
                    return {"success": True, "id": target_id}
                else:
                    return {"success": False, "error": res_json.get("message") or res_json.get("status", "unknown")}
            except Exception:
                pass

        # Fallback via GET query params
        resp_get = requests.get(url, params=payload, timeout=20.0)
        if resp_get.status_code == 200:
            try:
                res_json = resp_get.json()
                if res_json.get("status") == "success":
                    return {"success": True, "id": target_id}
                else:
                    return {"success": False, "error": res_json.get("message") or res_json.get("status", "unknown")}
            except Exception:
                pass

        return {"success": False, "error": f"HTTP {resp.status_code}"}
    except Exception as e:
        logger.warning(f"Impossibile sincronizzare modifica spesa a Google Sheets: {e}")
        return {"success": False, "error": str(e)}


def send_add_to_cloud(amount: float, category: str, description: str, date_iso: str, source: str = "desktop") -> Optional[int]:
    """Invia la nuova spesa a Google Sheets e restituisce l'ID assegnato da Google (colonna A), oppure None se offline."""
    url = get_google_sync_url()
    if not url or "script.google.com" not in url:
        return None
    try:
        params = {
            "action": "add",
            "amount": amount,
            "category": category,
            "description": description,
            "date": date_iso,
            "source": source
        }
        resp = requests.get(url, params=params, timeout=20.0)
        if resp.status_code == 200:
            try:
                data = resp.json()
                if data.get("status") == "success" and data.get("id"):
                    return int(data["id"])
            except Exception:
                pass
        return None
    except Exception as e:
        logger.warning(f"Impossibile inviare spesa a Google Sheets: {e}")
        return None
