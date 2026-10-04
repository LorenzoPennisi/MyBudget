"""
Test unitari e di integrazione per verificare il core dell'applicazione (DB, configurazione e logiche).
"""
import os
import unittest
from datetime import datetime
from pathlib import Path

# Assicuriamo un database temporaneo per i test
os.environ["DB_NAME"] = "test_spese.db"

import database
from config import CATEGORIES_LOOKUP, CATEGORIES

class TestExpenseTracker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database.init_db()

    @classmethod
    def tearDownClass(cls):
        test_db = Path("test_spese.db")
        if test_db.exists():
            test_db.unlink(missing_ok=True)
        wal_file = Path("test_spese.db-wal")
        if wal_file.exists():
            wal_file.unlink(missing_ok=True)
        shm_file = Path("test_spese.db-shm")
        if shm_file.exists():
            shm_file.unlink(missing_ok=True)

    def test_categories_lookup(self):
        for cat in CATEGORIES:
            self.assertEqual(CATEGORIES_LOOKUP[cat.lower()], cat)
        self.assertEqual(CATEGORIES_LOOKUP["alimentari"], "Alimentari")
        self.assertEqual(CATEGORIES_LOOKUP["svago"], "Svago")

    def test_add_and_get_transaction(self):
        tx_id = database.add_transaction(
            amount=42.50,
            category="alimentari",
            description="Spesa test",
            date_str="2026-10-04",
            source="test"
        )
        self.assertIsInstance(tx_id, int)

        df = database.get_transactions_df(start_date="2026-10-04", end_date="2026-10-04")
        self.assertFalse(df.empty)
        row = df[df["id"] == tx_id].iloc[0]
        self.assertEqual(row["amount"], 42.50)
        self.assertEqual(row["category"], "Alimentari")
        self.assertEqual(row["description"], "Spesa test")
        self.assertEqual(row["source"], "test")

    def test_monthly_summary(self):
        now = datetime.now()
        year = now.year
        month = now.month
        today_str = now.strftime("%Y-%m-%d")

        tx1 = database.add_transaction(10.0, "Trasporti", "Metro", date_str=today_str)
        tx2 = database.add_transaction(20.0, "Svago", "Cinema", date_str=today_str)

        summary = database.get_monthly_summary(year, month)
        self.assertGreaterEqual(summary["count"], 2)
        self.assertGreaterEqual(summary["total"], 30.0)

        # Cleanup
        database.delete_transaction(tx1)
        database.delete_transaction(tx2)

    def test_delete_transaction(self):
        tx_id = database.add_transaction(99.0, "Casa", "Lampadina")
        deleted = database.delete_transaction(tx_id)
        self.assertTrue(deleted)

        df = database.get_transactions_df()
        self.assertTrue(df[df["id"] == tx_id].empty)

    def test_recurring_expenses_crud_and_automation(self):
        from datetime import date
        test_ref_date = date(2026, 10, 4)

        # 1. Creazione Abbonamento a tempo indeterminato
        abb_id = database.add_recurring_expense(
            tipo="abbonamento",
            nome_descrizione="Spotify Test",
            importo=9.99,
            categoria="Svago",
            giorno_addebito=4,
            data_inizio="2026-10-01"
        )
        self.assertIsInstance(abb_id, int)

        # 2. Creazione Rata a tempo determinato (finanziamento 2 rate, 1 già pagata)
        rata_id = database.add_recurring_expense(
            tipo="rata",
            nome_descrizione="Smartphone Test",
            importo=50.00,
            categoria="Altro",
            giorno_addebito=4,
            numero_rate_totali=2,
            rate_pagate=1,
            data_inizio="2026-10-01"
        )
        self.assertIsInstance(rata_id, int)

        # 3. Test riepilogo suddivisione quote
        breakdown = database.get_recurring_breakdown_totals()
        self.assertGreaterEqual(breakdown["abbonamenti_totale"], 9.99)
        self.assertGreaterEqual(breakdown["rate_totale"], 50.00)
        self.assertGreaterEqual(breakdown["totale_fisse"], 59.99)

        # 4. Test automazione addebiti
        processed = database.process_due_recurring_expenses(ref_date=test_ref_date, send_notification=False)
        self.assertTrue(any(p["id"] == abb_id for p in processed))
        self.assertTrue(any(p["id"] == rata_id for p in processed))

        # Verifica avanzamento rata e completamento
        rate_item = [p for p in processed if p["id"] == rata_id][0]
        self.assertEqual(rate_item["rata_corrente"], 2)
        self.assertEqual(rate_item["rate_totali"], 2)
        self.assertTrue(rate_item["completata"])

        # Verifica stato nel DB dopo l'addebito
        recs = database.get_recurring_expenses_list()
        updated_rata = [r for r in recs if r["id"] == rata_id][0]
        self.assertEqual(updated_rata["stato"], "completato")
        self.assertEqual(updated_rata["rate_pagate"], 2)

        # 5. Verifica anti-duplicazione
        processed_again = database.process_due_recurring_expenses(ref_date=test_ref_date, send_notification=False)
        self.assertFalse(any(p["id"] == abb_id for p in processed_again))
        self.assertFalse(any(p["id"] == rata_id for p in processed_again))

        # Cleanup
        database.delete_recurring_expense(abb_id)
        database.delete_recurring_expense(rata_id)

    def test_date_normalization_and_european_format(self):
        # Test formati GG/MM/AAAA
        iso1 = database.normalize_date_to_iso("15/10/2026")
        self.assertEqual(iso1, "2026-10-15")

        iso2 = database.normalize_date_to_iso("04-05-2026")
        self.assertEqual(iso2, "2026-05-04")

        iso3 = database.normalize_date_to_iso("2026-12-25")
        self.assertEqual(iso3, "2026-12-25")

        # Test inserimento spesa usando formato europeo GG/MM/AAAA
        tx_id = database.add_transaction(
            amount=18.50,
            category="Alimentari",
            description="Pizza con amici",
            date_str="25/12/2026",
            source="manuale"
        )
        self.assertIsInstance(tx_id, int)

        df = database.get_transactions_df(start_date="2026-12-25", end_date="2026-12-25")
        self.assertFalse(df.empty)
        row = df[df["id"] == tx_id].iloc[0]
        self.assertEqual(row["date"], "2026-12-25")
        self.assertEqual(row["amount"], 18.50)

        # Cleanup
        database.delete_transaction(tx_id)

    def test_sync_plans_and_transactions_integration(self):
        from unittest.mock import patch
        import google_sheets_sync

        fake_cloud_data = {
            "transactions": [
                {
                    "id": 999,
                    "date": "2026-10-04",
                    "amount": 25.0,
                    "category": "Alimentari",
                    "description": "Spesa Cloud Sync",
                    "source": "bot",
                    "timestamp": "2026-10-04 15:00:00"
                }
            ],
            "plans": [
                {
                    "id": 888,
                    "tipo": "abbonamento",
                    "nome_descrizione": "Gym Cloud",
                    "importo": 39.90,
                    "categoria": "Svago",
                    "giorno_addebito": 10,
                    "numero_rate_totali": None,
                    "rate_pagate": 0,
                    "stato": "attivo",
                    "data_inizio": "2026-10-01"
                },
                {
                    "id": 889,
                    "tipo": "rata",
                    "nome_descrizione": "TV Cloud",
                    "importo": 50.00,
                    "categoria": "Casa",
                    "giorno_addebito": 15,
                    "numero_rate_totali": 10,
                    "rate_pagate": 3,
                    "stato": "attivo",
                    "data_inizio": "2026-10-01"
                }
            ],
            "summary": {}
        }

        with patch("google_sheets_sync.get_google_sync_url", return_value="https://script.google.com/macros/s/test/exec"):
            with patch("google_sheets_sync.fetch_from_cloud", return_value=fake_cloud_data):
                res = google_sheets_sync.sync_with_google_sheets()
                self.assertTrue(res["success"])
                self.assertGreaterEqual(res["imported"], 1)
                self.assertGreaterEqual(res["imported_plans"], 2)

                # Verifica presenza in database
                plans = database.get_recurring_expenses_list()
                tv_plan = [p for p in plans if p["nome_descrizione"] == "TV Cloud"]
                self.assertTrue(len(tv_plan) > 0)
                self.assertEqual(tv_plan[0]["rate_pagate"], 3)
                self.assertEqual(tv_plan[0]["numero_rate_totali"], 10)

                gym_plan = [p for p in plans if p["nome_descrizione"] == "Gym Cloud"]
                self.assertTrue(len(gym_plan) > 0)

                # Cleanup
                if tv_plan:
                    database.delete_recurring_expense(tv_plan[0]["id"])
                if gym_plan:
                    database.delete_recurring_expense(gym_plan[0]["id"])

    def test_update_transaction_and_get_by_id(self):
        tx_id = database.add_transaction(
            amount=15.00,
            category="Svago",
            description="Prima del cambio",
            date_str="2026-10-04",
            source="manuale"
        )
        self.assertIsInstance(tx_id, int)

        # Verifica lettura iniziale
        tx_orig = database.get_transaction_by_id(tx_id)
        self.assertIsNotNone(tx_orig)
        self.assertEqual(tx_orig["amount"], 15.00)
        self.assertEqual(tx_orig["description"], "Prima del cambio")

        # Modifica campi
        updated = database.update_transaction(
            transaction_id=tx_id,
            amount=22.50,
            category="Alimentari",
            description="Dopo il cambio",
            date_str="2026-10-05"
        )
        self.assertTrue(updated)

        # Verifica lettura dopo aggiornamento
        tx_mod = database.get_transaction_by_id(tx_id)
        self.assertIsNotNone(tx_mod)
        self.assertEqual(tx_mod["amount"], 22.50)
        self.assertEqual(tx_mod["category"], "Alimentari")
        self.assertEqual(tx_mod["description"], "Dopo il cambio")
        self.assertEqual(tx_mod["date"], "2026-10-05")

        # Cleanup
        database.delete_transaction(tx_id)

    def test_sync_cloud_edits_updates_local_database(self):
        from unittest.mock import patch
        import google_sheets_sync

        # Inserisci una transazione locale con ID 777 (identico al cloud)
        local_id = database.add_transaction(
            amount=30.00,
            category="Svago",
            description="Cinema",
            date_str="2026-10-04",
            source="desktop",
            tx_id=777
        )

        # Simula modifica su Google Sheets (stesso ID 777, ma importo 35.00 e descrizione "Cinema IMAX")
        cloud_mock_data = {
            "transactions": [
                {
                    "id": 777,
                    "date": "2026-10-04",
                    "amount": 35.00,
                    "category": "Svago",
                    "description": "Cinema IMAX",
                    "source": "sheet",
                    "timestamp": "2026-10-04 12:00:00"
                }
            ],
            "plans": [],
            "summary": {}
        }

        with patch("google_sheets_sync.get_google_sync_url", return_value="https://script.google.com/macros/s/test/exec"):
            with patch("google_sheets_sync.fetch_from_cloud", return_value=cloud_mock_data):
                res = google_sheets_sync.sync_with_google_sheets()
                self.assertTrue(res["success"])
                self.assertEqual(res["updated"], 1)

        # Verifica che il DB locale sia stato aggiornato in tempo reale
        updated_tx = database.get_transaction_by_id(local_id)
        self.assertEqual(updated_tx["amount"], 35.00)
        self.assertEqual(updated_tx["description"], "Cinema IMAX")

        # Cleanup
        database.delete_transaction(local_id)


if __name__ == "__main__":
    unittest.main()
