"""
Modulo per la gestione del database SQLite locale.
Garantisce accessi concorrenti sicuri abilitando WAL (Write-Ahead Logging).
Gestisce transazioni e uscite periodiche (differenziando tra Abbonamenti e Rate determinate).
"""
import calendar
import sqlite3
from contextlib import contextmanager
from datetime import datetime, date
from typing import List, Dict, Any, Optional
import pandas as pd

from config import DB_PATH, CATEGORIES_LOOKUP
from notifier import notify_recurring_charge


@contextmanager
def get_connection():
    """
    Context manager per connessione a SQLite.
    Abilita WAL mode e timeout di attesa per prevenire lock concorrenti.
    """
    conn = sqlite3.connect(str(DB_PATH), timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """
    Inizializza le tabelle del database ed esegue la migrazione automatica
    se la tabella recurring_expenses esiste con il vecchio schema.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Tabella Transazioni Principali
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                date TEXT NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                description TEXT,
                source TEXT NOT NULL DEFAULT 'bot',
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            );
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions(category);")

        cursor.execute("PRAGMA table_info(transactions);")
        tx_cols = {row["name"] for row in cursor.fetchall()}
        if "cloud_id" not in tx_cols:
            cursor.execute("ALTER TABLE transactions ADD COLUMN cloud_id INTEGER;")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_cloud_id ON transactions(cloud_id);")

        # 2. Verifica / Creazione Tabella Spese Ricorrenti (Rate vs Abbonamenti)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='recurring_expenses';")
        table_exists = cursor.fetchone() is not None

        if table_exists:
            cursor.execute("PRAGMA table_info(recurring_expenses);")
            cols = {row["name"] for row in cursor.fetchall()}
            
            # Se la tabella usa il vecchio schema (con 'name' al posto di 'nome_descrizione'), migra i dati
            if "nome_descrizione" not in cols:
                cursor.execute(
                    """
                    CREATE TABLE recurring_expenses_v2 (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        tipo TEXT NOT NULL DEFAULT 'abbonamento',
                        nome_descrizione TEXT NOT NULL,
                        importo REAL NOT NULL,
                        categoria TEXT NOT NULL,
                        giorno_addebito INTEGER NOT NULL,
                        numero_rate_totali INTEGER,
                        rate_pagate INTEGER NOT NULL DEFAULT 0,
                        stato TEXT NOT NULL DEFAULT 'attivo',
                        ultimo_mese_addebitato TEXT,
                        data_inizio TEXT NOT NULL,
                        created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
                    );
                    """
                )
                
                # Migra i dati esistenti mappandoli su abbonamenti
                cursor.execute(
                    """
                    INSERT INTO recurring_expenses_v2 (
                        id, tipo, nome_descrizione, importo, categoria, giorno_addebito,
                        numero_rate_totali, rate_pagate, stato, ultimo_mese_addebitato,
                        data_inizio, created_at
                    )
                    SELECT 
                        id, 'abbonamento', name, amount, category, day_of_month,
                        NULL, 0, CASE WHEN is_active=1 THEN 'attivo' ELSE 'in pausa' END,
                        last_billed_month, start_date, created_at
                    FROM recurring_expenses;
                    """
                )
                cursor.execute("DROP TABLE recurring_expenses;")
                cursor.execute("ALTER TABLE recurring_expenses_v2 RENAME TO recurring_expenses;")
        else:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS recurring_expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tipo TEXT NOT NULL DEFAULT 'abbonamento', -- 'abbonamento' oppure 'rata'
                    nome_descrizione TEXT NOT NULL,
                    importo REAL NOT NULL,
                    categoria TEXT NOT NULL,
                    giorno_addebito INTEGER NOT NULL,
                    numero_rate_totali INTEGER,             -- Valido per le rate, nullo per gli abbonamenti
                    rate_pagate INTEGER NOT NULL DEFAULT 0, -- Contatore incrementale rate saldate
                    stato TEXT NOT NULL DEFAULT 'attivo',   -- 'attivo', 'in pausa', 'completato'
                    ultimo_mese_addebitato TEXT,            -- 'YYYY-MM' per prevenire duplicati
                    data_inizio TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
                );
                """
            )

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_recurring_stato ON recurring_expenses(stato);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_recurring_tipo ON recurring_expenses(tipo);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_recurring_giorno ON recurring_expenses(giorno_addebito);")


# =============================================================================
# OPERAZIONI TRANSAZIONI SINGOLE
# =============================================================================

def normalize_date_to_iso(date_str: Optional[str]) -> str:
    """
    Normalizza qualsiasi formato di data (es. '04/10/2026', '04-10-2026', '04.10.2026', '2026-10-04')
    nel formato standard ISO 'YYYY-MM-DD'. Se vuota o non valida, restituisce la data odierna.
    """
    if not date_str or not str(date_str).strip():
        return datetime.now().strftime("%Y-%m-%d")
    s = str(date_str).strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s


def add_transaction(
    amount: float,
    category: str,
    description: str = "",
    date_str: Optional[str] = None,
    source: str = "bot",
    tx_id: Optional[int] = None
) -> int:
    """Inserisce una nuova spesa nel database con ID identico a Google Sheets o autoincrementale."""
    norm_category = CATEGORIES_LOOKUP.get(category.strip().lower(), category.strip())
    now = datetime.now()
    
    if not date_str:
        tx_date = now.strftime("%Y-%m-%d")
        timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S")
    else:
        tx_date = normalize_date_to_iso(date_str)
        timestamp_str = f"{tx_date} {now.strftime('%H:%M:%S')}"

    with get_connection() as conn:
        cursor = conn.cursor()
        if tx_id is not None:
            cursor.execute(
                """
                INSERT OR REPLACE INTO transactions (id, timestamp, date, amount, category, description, source, cloud_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (tx_id, timestamp_str, tx_date, round(float(amount), 2), norm_category, description.strip(), source, tx_id)
            )
            return tx_id
        else:
            cursor.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM transactions;")
            next_id = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO transactions (id, timestamp, date, amount, category, description, source, cloud_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (next_id, timestamp_str, tx_date, round(float(amount), 2), norm_category, description.strip(), source, next_id)
            )
            return next_id


def delete_transaction(transaction_id: int) -> bool:
    """Elimina una transazione tramite ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM transactions WHERE id = ?;", (transaction_id,))
        return cursor.rowcount > 0


def update_transaction(
    transaction_id: int,
    amount: float,
    category: str,
    description: str = "",
    date_str: Optional[str] = None
) -> bool:
    """Aggiorna i campi di una transazione esistente tramite ID."""
    norm_category = CATEGORIES_LOOKUP.get(category.strip().lower(), category.strip())
    iso_date = normalize_date_to_iso(date_str)
    amt = round(float(amount), 2)
    desc = description.strip()

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE transactions
            SET amount = ?, category = ?, description = ?, date = ?
            WHERE id = ?;
            """,
            (amt, norm_category, desc, iso_date, transaction_id)
        )
        return cursor.rowcount > 0


def get_transaction_by_id(transaction_id: int) -> Optional[Dict[str, Any]]:
    """Restituisce i dati completi di una transazione dato il suo ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM transactions WHERE id = ?;", (transaction_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_transactions_df(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    category: Optional[str] = None
) -> pd.DataFrame:
    """Restituisce un DataFrame pandas delle transazioni con eventuali filtri."""
    query = "SELECT id, date, timestamp, amount, category, description, source, cloud_id FROM transactions WHERE 1=1"
    params = []

    if start_date:
        query += " AND date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date <= ?"
        params.append(end_date)
    if category and category != "Tutte":
        query += " AND category = ?"
        params.append(category)

    query += " ORDER BY date DESC, id DESC"

    with get_connection() as conn:
        return pd.read_sql_query(query, conn, params=params)


def get_monthly_summary(year: int, month: int) -> Dict[str, Any]:
    """Restituisce statistiche aggregate per un mese specifico."""
    month_prefix = f"{year:04d}-{month:02d}%"
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 
                COUNT(*) as count,
                COALESCE(SUM(amount), 0.0) as total,
                COALESCE(AVG(amount), 0.0) as average,
                COALESCE(MAX(amount), 0.0) as max_expense
            FROM transactions
            WHERE date LIKE ?;
            """,
            (month_prefix,)
        )
        row = cursor.fetchone()
        return {
            "count": row["count"],
            "total": round(row["total"], 2),
            "average": round(row["average"], 2),
            "max_expense": round(row["max_expense"], 2),
        }


def get_recent_transactions(limit: int = 5) -> List[Dict[str, Any]]:
    """Restituisce le ultime N transazioni inserite."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, date, amount, category, description, source
            FROM transactions
            ORDER BY id DESC
            LIMIT ?;
            """,
            (limit,)
        )
        return [dict(row) for row in cursor.fetchall()]


# =============================================================================
# OPERAZIONI SPESE PERIODICHE: RATE VS ABBONAMENTI
# =============================================================================

def add_recurring_expense(
    tipo: str,
    nome_descrizione: str,
    importo: float,
    categoria: str,
    giorno_addebito: int,
    numero_rate_totali: Optional[int] = None,
    rate_pagate: int = 0,
    data_inizio: Optional[str] = None,
    stato: str = "attivo"
) -> int:
    """
    Crea una nuova spesa periodica distinguendo tra 'abbonamento' e 'rata'.
    """
    norm_tipo = "rata" if tipo.strip().lower() in ("rata", "rate", "finanziamento") else "abbonamento"
    norm_categoria = CATEGORIES_LOOKUP.get(categoria.strip().lower(), categoria.strip())
    
    data_inizio = normalize_date_to_iso(data_inizio)
        
    giorno = max(1, min(31, int(giorno_addebito)))
    rate_tot = int(numero_rate_totali) if (norm_tipo == "rata" and numero_rate_totali is not None) else None
    pagate = int(rate_pagate) if norm_tipo == "rata" else 0
    
    # Se le rate pagate raggiungono già il totale, imposta a completato
    init_stato = stato.strip().lower()
    if norm_tipo == "rata" and rate_tot and pagate >= rate_tot:
        init_stato = "completato"

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO recurring_expenses (
                tipo, nome_descrizione, importo, categoria, giorno_addebito,
                numero_rate_totali, rate_pagate, stato, ultimo_mese_addebitato, data_inizio
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?);
            """,
            (
                norm_tipo,
                nome_descrizione.strip(),
                round(float(importo), 2),
                norm_categoria,
                giorno,
                rate_tot,
                pagate,
                init_stato,
                data_inizio
            )
        )
        return cursor.lastrowid


def get_recurring_expenses_df(tipo: Optional[str] = None, stato: Optional[str] = None) -> pd.DataFrame:
    """Restituisce un DataFrame con le spese periodiche filtrate."""
    query = "SELECT * FROM recurring_expenses WHERE 1=1"
    params = []
    if tipo:
        query += " AND tipo = ?"
        params.append(tipo)
    if stato:
        query += " AND stato = ?"
        params.append(stato)
    query += " ORDER BY giorno_addebito ASC, id ASC"

    with get_connection() as conn:
        return pd.read_sql_query(query, conn, params=params)


def get_recurring_expenses_list(tipo: Optional[str] = None, stato: Optional[str] = None) -> List[Dict[str, Any]]:
    """Restituisce la lista di dizionari delle spese periodiche."""
    query = "SELECT * FROM recurring_expenses WHERE 1=1"
    params = []
    if tipo:
        query += " AND tipo = ?"
        params.append(tipo)
    if stato:
        query += " AND stato = ?"
        params.append(stato)
    query += " ORDER BY giorno_addebito ASC, id ASC"

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def update_recurring_expense_status(expense_id: int, new_status: str) -> bool:
    """Aggiorna lo stato di una spesa periodica ('attivo', 'in pausa', 'completato')."""
    valid_states = ("attivo", "in pausa", "completato")
    st_val = new_status.strip().lower()
    if st_val not in valid_states:
        return False
        
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE recurring_expenses SET stato = ? WHERE id = ?;", (st_val, expense_id))
        return cursor.rowcount > 0


def delete_recurring_expense(expense_id: int) -> bool:
    """Elimina definitivamente una spesa periodica."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM recurring_expenses WHERE id = ?;", (expense_id,))
        return cursor.rowcount > 0


def get_recurring_breakdown_totals() -> Dict[str, float]:
    """
    Calcola il totale mensile previsto delle uscite fisse attive,
    separando chiaramente la quota degli abbonamenti dal totale delle rate attive.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        # Abbonamenti attivi
        cursor.execute(
            "SELECT COALESCE(SUM(importo), 0.0) as tot, COUNT(*) as cnt FROM recurring_expenses WHERE tipo = 'abbonamento' AND stato = 'attivo';"
        )
        row_abb = cursor.fetchone()
        tot_abbonamenti = round(float(row_abb["tot"]), 2)
        cnt_abbonamenti = row_abb["cnt"]

        # Rate attive (non completate né in pausa)
        cursor.execute(
            "SELECT COALESCE(SUM(importo), 0.0) as tot, COUNT(*) as cnt FROM recurring_expenses WHERE tipo = 'rata' AND stato = 'attivo';"
        )
        row_rate = cursor.fetchone()
        tot_rate = round(float(row_rate["tot"]), 2)
        cnt_rate = row_rate["cnt"]

        return {
            "abbonamenti_totale": tot_abbonamenti,
            "abbonamenti_count": cnt_abbonamenti,
            "rate_totale": tot_rate,
            "rate_count": cnt_rate,
            "totale_fisse": round(tot_abbonamenti + tot_rate, 2)
        }


def get_upcoming_charges_this_month(ref_date: Optional[date] = None) -> List[Dict[str, Any]]:
    """
    Restituisce le spese periodiche attive che devono ancora essere addebitate nel mese corrente,
    con il calcolo dei giorni mancanti.
    """
    if ref_date is None:
        ref_date = date.today()

    current_month_str = ref_date.strftime("%Y-%m")
    current_day = ref_date.day
    days_in_month = calendar.monthrange(ref_date.year, ref_date.month)[1]

    items = get_recurring_expenses_list(stato="attivo")
    upcoming = []

    for item in items:
        # Se già addebitato questo mese, salta
        if item.get("ultimo_mese_addebitato") == current_month_str:
            continue

        target_day = min(item["giorno_addebito"], days_in_month)
        
        # Considera le spese con giorno addebito futuro nel mese
        days_left = target_day - current_day
        item_copy = dict(item)
        item_copy["target_day"] = target_day
        item_copy["days_left"] = days_left
        item_copy["is_overdue"] = days_left <= 0
        upcoming.append(item_copy)

    # Ordina per giorno di scadenza
    upcoming.sort(key=lambda x: x["target_day"])
    return upcoming


def process_due_recurring_expenses(
    ref_date: Optional[date] = None,
    send_notification: bool = True
) -> List[Dict[str, Any]]:
    """
    Routine di controllo ed esecuzione automatica delle scadenze periodiche:
    - Se oggi >= giorno_addebito e spesa non ancora registrata nel mese:
      - Crea la transazione nella tabella principale transactions (source='abbonamento' o 'rata').
      - Per le rate: incrementa rate_pagate. Se rate_pagate >= numero_rate_totali, imposta stato = 'completato'.
      - Aggiorna ultimo_mese_addebitato = current_month_str.
      - Invia notifica Telegram personalizzata (specificando il tipo o il progresso X/Y).
    """
    if ref_date is None:
        ref_date = date.today()

    current_month_str = ref_date.strftime("%Y-%m")
    current_day = ref_date.day
    days_in_month = calendar.monthrange(ref_date.year, ref_date.month)[1]

    processed = []
    items = get_recurring_expenses_list(stato="attivo")

    for item in items:
        # Verifica data inizio
        start_d = datetime.strptime(item["data_inizio"], "%Y-%m-%d").date()
        if ref_date < start_d:
            continue

        # Evita duplicati nello stesso mese
        if item.get("ultimo_mese_addebitato") == current_month_str:
            continue

        target_day = min(item["giorno_addebito"], days_in_month)

        if current_day >= target_day:
            billing_date_str = f"{current_month_str}-{target_day:02d}"
            item_id = item["id"]
            tipo = item["tipo"]
            nome = item["nome_descrizione"]
            importo = item["importo"]
            cat = item["categoria"]

            if tipo == "rata":
                new_rate_pagate = item["rate_pagate"] + 1
                rate_totali = item["numero_rate_totali"] or new_rate_pagate
                is_completed = new_rate_pagate >= rate_totali
                new_stato = "completato" if is_completed else "attivo"
                desc = f"[Rata {new_rate_pagate}/{rate_totali}] {nome}"

                tx_id = add_transaction(
                    amount=importo,
                    category=cat,
                    description=desc,
                    date_str=billing_date_str,
                    source="rata"
                )

                with get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        UPDATE recurring_expenses
                        SET rate_pagate = ?, stato = ?, ultimo_mese_addebitato = ?
                        WHERE id = ?;
                        """,
                        (new_rate_pagate, new_stato, current_month_str, item_id)
                    )

                p_info = {
                    "id": item_id,
                    "tipo": "rata",
                    "nome": nome,
                    "importo": importo,
                    "categoria": cat,
                    "giorno": item["giorno_addebito"],
                    "rata_corrente": new_rate_pagate,
                    "rate_totali": rate_totali,
                    "completata": is_completed,
                    "billed_date": billing_date_str,
                    "tx_id": tx_id
                }
                processed.append(p_info)

                if send_notification:
                    try:
                        notify_recurring_charge(
                            tipo="rata",
                            nome=nome,
                            importo=importo,
                            categoria=cat,
                            giorno=item["giorno_addebito"],
                            rata_corrente=new_rate_pagate,
                            rate_totali=rate_totali,
                            completata=is_completed,
                            tx_id=tx_id
                        )
                    except Exception as e:
                        print(f"Errore notifica Telegram: {e}")

            else:
                # Abbonamento a durata indeterminata
                desc = f"[Abbonamento] {nome}"
                tx_id = add_transaction(
                    amount=importo,
                    category=cat,
                    description=desc,
                    date_str=billing_date_str,
                    source="abbonamento"
                )

                with get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "UPDATE recurring_expenses SET ultimo_mese_addebitato = ? WHERE id = ?;",
                        (current_month_str, item_id)
                    )

                p_info = {
                    "id": item_id,
                    "tipo": "abbonamento",
                    "nome": nome,
                    "importo": importo,
                    "categoria": cat,
                    "giorno": item["giorno_addebito"],
                    "billed_date": billing_date_str,
                    "tx_id": tx_id
                }
                processed.append(p_info)

                if send_notification:
                    try:
                        notify_recurring_charge(
                            tipo="abbonamento",
                            nome=nome,
                            importo=importo,
                            categoria=cat,
                            giorno=item["giorno_addebito"],
                            tx_id=tx_id
                        )
                    except Exception as e:
                        print(f"Errore notifica Telegram: {e}")

    return processed
