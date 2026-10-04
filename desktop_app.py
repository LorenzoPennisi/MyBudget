"""
Applicazione Desktop Nativa per la Gestione Finanziaria Personale - Contabile.
Interfaccia moderna Dark Mode realizzata con CustomTkinter, Matplotlib e SQLite.
Include: gestione avanzata Rate (con ammortamento) vs Abbonamenti, automazione scadenze,
grafici interattivi, controllo Bot Telegram e notifiche in tempo reale.
"""
import calendar
from datetime import datetime, date, timedelta
import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
import pandas as pd
import customtkinter as ctk
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from config import (
    CATEGORIES,
    CATEGORIES_LOOKUP,
    CATEGORY_ICONS,
    MONTHLY_BUDGET,
    TELEGRAM_BOT_TOKEN,
    BASE_DIR,
)
from database import (
    init_db,
    add_transaction,
    delete_transaction,
    update_transaction,
    get_transaction_by_id,
    get_transactions_df,
    get_monthly_summary,
    add_recurring_expense,
    get_recurring_expenses_list,
    update_recurring_expense_status,
    delete_recurring_expense,
    get_recurring_breakdown_totals,
    get_upcoming_charges_this_month,
    process_due_recurring_expenses,
    normalize_date_to_iso,
)
from google_sheets_sync import (
    get_google_sync_url,
    save_google_sync_url,
    sync_with_google_sheets,
    push_all_local_to_cloud,
    set_telegram_webhook,
    check_cloud_diagnostics,
    send_add_to_cloud,
    send_delete_to_cloud,
    send_edit_to_cloud,
)

# Configurazione Aspetto CustomTkinter
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")
matplotlib.use("TkAgg")

# Palette Colori Obsidian Dark / Modern Fintech
PALETTE = {
    "bg_root": "#090D16",        # Sfondo profondo Midnight Obsidian
    "bg_sidebar": "#0F172A",     # Sidebar scura
    "bg_card": "#131D31",        # Card elevata
    "bg_card_inner": "#0A101D",  # Sfondo input / sub-card
    "border": "#22314E",         # Bordo sottile ed elegante
    "border_glow": "#38BDF8",    # Bagliore celeste al focus
    "accent": "#38BDF8",         # Electric Sky Blue
    "accent_hover": "#0EA5E9",   # Sky Blue hover
    "emerald": "#10B981",        # Verde successo
    "rose": "#F43F5E",           # Rosso allerta
    "amber": "#F59E0B",          # Arancione avviso
    "violet": "#818CF8",         # Viola per rate e ammortamenti
    "text_primary": "#F8FAFC",   # Bianco primario
    "text_muted": "#94A3B8",     # Testo secondario
    "text_dim": "#64748B",       # Testo discreto
}

CATEGORY_COLORS = {
    "Alimentari": "#10B981",
    "Trasporti": "#38BDF8",
    "Casa": "#F59E0B",
    "Svago": "#818CF8",
    "Salute": "#EC4899",
    "Altro": "#94A3B8"
}


class ContabileApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Configurazione Finestra Principale
        self.title("Contabile • Gestione Finanziaria, Rate & Abbonamenti")
        self.geometry("1260x820")
        self.minsize(1080, 700)
        self.configure(fg_color=PALETTE["bg_root"])

        # Icona Finestra e Taskbar
        icon_file = BASE_DIR / "app_icon.ico"
        if icon_file.exists():
            try:
                self.iconbitmap(str(icon_file))
            except Exception:
                pass

        # Inizializza Database SQLite
        init_db()

        # Variabili di stato
        now = datetime.now()
        self.current_year = now.year
        self.current_month = now.month
        self.current_budget = float(MONTHLY_BUDGET)
        self.bot_process = None
        self.last_tx_count = -1
        self.quick_filter = "Questo Mese"

        # Esegui primo controllo scadenze periodiche
        try:
            process_due_recurring_expenses(send_notification=True)
        except Exception:
            pass

        # Layout Principale a Griglia: Sidebar (colonna 0) + Area Contenuto (colonna 1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self.setup_sidebar()
        self.setup_content_area()

        # Mostra la vista iniziale
        self.show_view("dashboard")

        # Avvio automatico del Bot se il token è impostato
        self.auto_start_bot()

        # Avvio sincronizzazione automatica iniziale con Google Fogli
        self.cloud_syncing = False
        self.after(1200, self.trigger_background_cloud_sync)

        # Controllo periodico ogni 3 secondi per sincronizzare scadenze e messaggi bot
        self.after(3000, self.periodic_check)

        # Chiusura pulita dei processi in background
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    # =========================================================================
    # SIDEBAR MODERNA
    # =========================================================================
    def setup_sidebar(self):
        self.sidebar_frame = ctk.CTkScrollableFrame(
            self,
            width=280,
            corner_radius=0,
            fg_color=PALETTE["bg_sidebar"],
            border_width=1,
            border_color=PALETTE["border"],
            scrollbar_button_color=PALETTE["border"],
            scrollbar_button_hover_color=PALETTE["accent"]
        )
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        self.sidebar_frame.grid_columnconfigure(0, weight=1)

        # Logo & Titolo
        header_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, padx=22, pady=(24, 18), sticky="ew")

        logo_title = ctk.CTkLabel(
            header_frame,
            text="💎 CONTABILE",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color=PALETTE["text_primary"]
        )
        logo_title.pack(anchor="w")

        logo_sub = ctk.CTkLabel(
            header_frame,
            text="Finanze Personali & Rate",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=PALETTE["text_muted"]
        )
        logo_sub.pack(anchor="w", pady=(2, 0))

        # Menu di Navigazione
        self.nav_buttons = {}
        nav_items = [
            ("dashboard", "📊  Panoramica"),
            ("movements", "📝  Movimenti"),
            ("plans", "🔁  Rate & Abbonamenti"),
            ("new_expense", "➕  Nuova Spesa")
        ]

        for idx, (view_id, label) in enumerate(nav_items, start=2):
            btn = ctk.CTkButton(
                self.sidebar_frame,
                text=label,
                anchor="w",
                font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
                height=42,
                corner_radius=10,
                fg_color="transparent",
                text_color=PALETTE["text_muted"],
                hover_color=PALETTE["bg_card"],
                command=lambda v=view_id: self.show_view(v)
            )
            btn.grid(row=idx, column=0, padx=16, pady=4, sticky="ew")
            self.nav_buttons[view_id] = btn

        # Selettore Periodo
        sep1 = ctk.CTkFrame(self.sidebar_frame, height=1, fg_color=PALETTE["border"])
        sep1.grid(row=6, column=0, padx=20, pady=(18, 12), sticky="ew")

        ctk.CTkLabel(
            self.sidebar_frame,
            text="PERIODO DI RIFERIMENTO",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=PALETTE["text_dim"]
        ).grid(row=7, column=0, padx=20, pady=(0, 6), sticky="w")

        months = [f"{m:02d} - {calendar.month_name[m]}" for m in range(1, 13)]
        self.month_combo = ctk.CTkComboBox(
            self.sidebar_frame,
            values=months,
            height=34,
            corner_radius=8,
            fg_color=PALETTE["bg_card"],
            border_color=PALETTE["border"],
            text_color=PALETTE["text_primary"],
            dropdown_fg_color=PALETTE["bg_card"],
            command=self.on_period_change
        )
        self.month_combo.set(months[self.current_month - 1])
        self.month_combo.grid(row=8, column=0, padx=16, pady=3, sticky="ew")

        years = [str(y) for y in range(self.current_year - 2, self.current_year + 3)]
        self.year_combo = ctk.CTkComboBox(
            self.sidebar_frame,
            values=years,
            height=34,
            corner_radius=8,
            fg_color=PALETTE["bg_card"],
            border_color=PALETTE["border"],
            text_color=PALETTE["text_primary"],
            dropdown_fg_color=PALETTE["bg_card"],
            command=self.on_period_change
        )
        self.year_combo.set(str(self.current_year))
        self.year_combo.grid(row=9, column=0, padx=16, pady=3, sticky="ew")

        # Box Budget Mensile
        self.budget_box = ctk.CTkFrame(
            self.sidebar_frame,
            corner_radius=12,
            fg_color=PALETTE["bg_card"],
            border_width=1,
            border_color=PALETTE["border"]
        )
        self.budget_box.grid(row=10, column=0, padx=16, pady=14, sticky="ew")

        ctk.CTkLabel(
            self.budget_box,
            text="🎯 Budget Mensile Target",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=PALETTE["text_primary"]
        ).pack(anchor="w", padx=12, pady=(10, 4))

        b_row = ctk.CTkFrame(self.budget_box, fg_color="transparent")
        b_row.pack(fill="x", padx=12, pady=(0, 10))

        self.budget_entry = ctk.CTkEntry(
            b_row,
            height=32,
            corner_radius=8,
            fg_color=PALETTE["bg_card_inner"],
            border_color=PALETTE["border"],
            text_color=PALETTE["text_primary"]
        )
        self.budget_entry.insert(0, f"{self.current_budget:.2f}")
        self.budget_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        ctk.CTkButton(
            b_row,
            text="Salva",
            width=50,
            height=32,
            corner_radius=8,
            fg_color=PALETTE["accent"],
            hover_color=PALETTE["accent_hover"],
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.update_budget
        ).pack(side="right")

        # Bot Telegram Card
        self.bot_card = ctk.CTkFrame(
            self.sidebar_frame,
            corner_radius=12,
            fg_color=PALETTE["bg_card"],
            border_width=1,
            border_color=PALETTE["border"]
        )
        self.bot_card.grid(row=11, column=0, padx=16, pady=4, sticky="ew")

        bot_header = ctk.CTkFrame(self.bot_card, fg_color="transparent")
        bot_header.pack(fill="x", padx=12, pady=(10, 4))

        self.bot_status_indicator = ctk.CTkLabel(
            bot_header,
            text="●",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=PALETTE["rose"]
        )
        self.bot_status_indicator.pack(side="left", padx=(0, 6))

        ctk.CTkLabel(
            bot_header,
            text="Bot Telegram",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=PALETTE["text_primary"]
        ).pack(side="left")

        self.bot_status_sub = ctk.CTkLabel(
            self.bot_card,
            text="In attesa di avvio",
            font=ctk.CTkFont(size=11),
            text_color=PALETTE["text_muted"]
        )
        self.bot_status_sub.pack(anchor="w", padx=12, pady=(0, 8))

        self.bot_toggle_btn = ctk.CTkButton(
            self.bot_card,
            text="Avvia Bot",
            height=32,
            corner_radius=8,
            fg_color=PALETTE["accent"],
            hover_color=PALETTE["accent_hover"],
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.toggle_bot
        )
        self.bot_toggle_btn.pack(fill="x", padx=12, pady=(0, 6))

        ctk.CTkButton(
            self.bot_card,
            text="⚙️ Imposta Token",
            height=26,
            corner_radius=6,
            fg_color="transparent",
            hover_color=PALETTE["bg_card_inner"],
            text_color=PALETTE["text_muted"],
            font=ctk.CTkFont(size=11),
            command=self.open_token_dialog
        ).pack(fill="x", padx=12, pady=(0, 8))

        # Google Fogli / Cloud Sync Card
        self.cloud_card = ctk.CTkFrame(
            self.sidebar_frame,
            corner_radius=12,
            fg_color=PALETTE["bg_card"],
            border_width=1,
            border_color=PALETTE["border"]
        )
        self.cloud_card.grid(row=12, column=0, padx=16, pady=4, sticky="ew")

        cloud_header = ctk.CTkFrame(self.cloud_card, fg_color="transparent")
        cloud_header.pack(fill="x", padx=12, pady=(10, 4))

        has_cloud = bool(get_google_sync_url())
        self.cloud_status_indicator = ctk.CTkLabel(
            cloud_header,
            text="●",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=PALETTE["emerald"] if has_cloud else PALETTE["amber"]
        )
        self.cloud_status_indicator.pack(side="left", padx=(0, 6))

        ctk.CTkLabel(
            cloud_header,
            text="Google Fogli Sync",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=PALETTE["text_primary"]
        ).pack(side="left")

        self.cloud_status_sub = ctk.CTkLabel(
            self.cloud_card,
            text="Pronto alla sincro" if has_cloud else "URL non impostato",
            font=ctk.CTkFont(size=11),
            text_color=PALETTE["emerald"] if has_cloud else PALETTE["text_muted"]
        )
        self.cloud_status_sub.pack(anchor="w", padx=12, pady=(0, 8))

        self.cloud_sync_btn = ctk.CTkButton(
            self.cloud_card,
            text="☁️  Sincronizza Ora",
            height=32,
            corner_radius=8,
            fg_color=PALETTE["violet"],
            hover_color="#7C3AED",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.trigger_background_cloud_sync
        )
        self.cloud_sync_btn.pack(fill="x", padx=12, pady=(0, 6))

        ctk.CTkButton(
            self.cloud_card,
            text="⬆️  Carica Passate sul Foglio",
            height=26,
            corner_radius=6,
            fg_color=PALETTE["bg_sidebar"],
            hover_color=PALETTE["border"],
            border_width=1,
            border_color=PALETTE["border"],
            text_color=PALETTE["text_primary"],
            font=ctk.CTkFont(size=11),
            command=self.push_past_expenses_to_cloud
        ).pack(fill="x", padx=12, pady=(0, 6))

        ctk.CTkButton(
            self.cloud_card,
            text="⚙️ Imposta URL Foglio",
            height=26,
            corner_radius=6,
            fg_color="transparent",
            hover_color=PALETTE["bg_card_inner"],
            text_color=PALETTE["text_muted"],
            font=ctk.CTkFont(size=11),
            command=self.open_cloud_sync_dialog
        ).pack(fill="x", padx=12, pady=(0, 8))

        # Bottom Refresh Action
        bottom_bar = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        bottom_bar.grid(row=13, column=0, padx=16, pady=16, sticky="ew")

        ctk.CTkButton(
            bottom_bar,
            text="🔄  Aggiorna Tutto",
            height=36,
            corner_radius=8,
            fg_color=PALETTE["bg_card"],
            hover_color=PALETTE["border"],
            border_width=1,
            border_color=PALETTE["border"],
            text_color=PALETTE["text_primary"],
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.refresh_all
        ).pack(fill="x")

    # =========================================================================
    # AREA CONTENUTO
    # =========================================================================
    def setup_content_area(self):
        self.content_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.content_frame.grid(row=0, column=1, sticky="nsew", padx=24, pady=24)
        self.content_frame.grid_rowconfigure(0, weight=1)
        self.content_frame.grid_columnconfigure(0, weight=1)

        self.views = {
            "dashboard": ctk.CTkFrame(self.content_frame, fg_color="transparent"),
            "movements": ctk.CTkFrame(self.content_frame, fg_color="transparent"),
            "plans": ctk.CTkFrame(self.content_frame, fg_color="transparent"),
            "new_expense": ctk.CTkFrame(self.content_frame, fg_color="transparent")
        }

        for view in self.views.values():
            view.grid(row=0, column=0, sticky="nsew")

        self.build_dashboard_view()
        self.build_movements_view()
        self.build_plans_view()
        self.build_new_expense_view()

    def show_view(self, view_name: str):
        """Passa a una vista con evidenziazione fluida del pulsante attivo."""
        for name, view in self.views.items():
            if name == view_name:
                view.tkraise()
                self.nav_buttons[name].configure(
                    fg_color=PALETTE["bg_card"],
                    text_color=PALETTE["accent"]
                )
            else:
                self.nav_buttons[name].configure(
                    fg_color="transparent",
                    text_color=PALETTE["text_muted"]
                )

        if view_name == "dashboard":
            self.update_dashboard_data()
        elif view_name == "movements":
            self.load_movements_data()
        elif view_name == "plans":
            self.load_plans_data()

    # =========================================================================
    # VISTA 1: PANORAMICA (DASHBOARD)
    # =========================================================================
    def build_dashboard_view(self):
        dash = self.views["dashboard"]
        dash.grid_rowconfigure(4, weight=1)
        dash.grid_columnconfigure(0, weight=1)

        # Header Dashboard
        top_bar = ctk.CTkFrame(dash, fg_color="transparent")
        top_bar.grid(row=0, column=0, sticky="ew", pady=(0, 14))

        self.dash_title = ctk.CTkLabel(
            top_bar,
            text="",
            font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"),
            text_color=PALETTE["text_primary"]
        )
        self.dash_title.pack(side="left")

        self.status_badge = ctk.CTkLabel(
            top_bar,
            text="🟢 In Budget",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=PALETTE["emerald"],
            fg_color=PALETTE["bg_card"],
            corner_radius=12,
            padx=14,
            pady=5
        )
        self.status_badge.pack(side="right")

        # 4 KPI Cards
        self.kpi_container = ctk.CTkFrame(dash, fg_color="transparent")
        self.kpi_container.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        for col in range(4):
            self.kpi_container.grid_columnconfigure(col, weight=1)

        self.kpi_labels = {}
        cards_info = [
            ("remaining", "🎯 BUDGET RESIDUO", "0.00 €", PALETTE["emerald"]),
            ("total", "💰 TOTALE USCITE MESE", "0.00 €", PALETTE["accent"]),
            ("recurring", "🔁 USCITE FISSE MESE", "0.00 €", PALETTE["violet"]),
            ("average", "📈 MEDIA GIORNALIERA", "0.00 €", PALETTE["amber"]),
        ]

        for col, (kpi_id, title, def_val, accent_col) in enumerate(cards_info):
            card = ctk.CTkFrame(
                self.kpi_container,
                corner_radius=14,
                fg_color=PALETTE["bg_card"],
                border_width=1,
                border_color=PALETTE["border"]
            )
            card.grid(row=0, column=col, padx=6, sticky="ew")

            top_row = ctk.CTkFrame(card, fg_color="transparent")
            top_row.pack(fill="x", padx=16, pady=(14, 2))

            ctk.CTkLabel(
                top_row,
                text=title,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color=PALETTE["text_muted"]
            ).pack(side="left")

            val_lbl = ctk.CTkLabel(
                card,
                text=def_val,
                font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
                text_color=PALETTE["text_primary"]
            )
            val_lbl.pack(anchor="w", padx=16, pady=(0, 2))

            sub_lbl = ctk.CTkLabel(
                card,
                text="In aggiornamento...",
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=PALETTE["text_dim"]
            )
            sub_lbl.pack(anchor="w", padx=16, pady=(0, 12))

            self.kpi_labels[kpi_id] = (val_lbl, sub_lbl)

        # Budget Progress Bar Moderna
        self.progress_card = ctk.CTkFrame(
            dash,
            corner_radius=14,
            fg_color=PALETTE["bg_card"],
            border_width=1,
            border_color=PALETTE["border"]
        )
        self.progress_card.grid(row=2, column=0, sticky="ew", pady=(0, 12))

        p_top = ctk.CTkFrame(self.progress_card, fg_color="transparent")
        p_top.pack(fill="x", padx=18, pady=(10, 4))

        ctk.CTkLabel(
            p_top,
            text="Avanzamento del Budget Mensile",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=PALETTE["text_primary"]
        ).pack(side="left")

        self.lbl_progress_pct = ctk.CTkLabel(
            p_top,
            text="0%",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=PALETTE["accent"]
        )
        self.lbl_progress_pct.pack(side="right")

        self.progress_bar = ctk.CTkProgressBar(
            self.progress_card,
            height=10,
            corner_radius=5,
            fg_color=PALETTE["bg_card_inner"],
            progress_color=PALETTE["accent"]
        )
        self.progress_bar.pack(fill="x", padx=18, pady=(0, 12))
        self.progress_bar.set(0)

        # Widget Avviso Prossime Scadenze nel Mese
        self.upcoming_frame = ctk.CTkFrame(dash, fg_color="transparent")
        self.upcoming_frame.grid(row=3, column=0, sticky="ew", pady=(0, 10))

        # Contenitore Grafici con Bordo Divisorio Ridimensionabile (PanedWindow)
        self.charts_paned = tk.PanedWindow(
            dash,
            orient=tk.HORIZONTAL,
            sashwidth=8,
            sashpad=2,
            sashrelief=tk.FLAT,
            bg=PALETTE["bg_root"],
            bd=0,
            cursor="sb_h_double_arrow",
            showhandle=True,
            handlepad=6,
            handlesize=10
        )
        self.charts_paned.grid(row=4, column=0, sticky="nsew", pady=(2, 0))

        # 1. Contenitore Grafico a Torta / Categorie
        self.pie_card = ctk.CTkFrame(
            self.charts_paned,
            corner_radius=14,
            fg_color=PALETTE["bg_card"],
            border_width=1,
            border_color=PALETTE["border"]
        )
        self.charts_paned.add(self.pie_card, minsize=260)

        pie_head = ctk.CTkFrame(self.pie_card, fg_color="transparent")
        pie_head.pack(fill="x", padx=14, pady=(10, 2))
        ctk.CTkLabel(
            pie_head,
            text="🍩 Ripartizione Categorie",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=PALETTE["text_primary"]
        ).pack(side="left")
        ctk.CTkLabel(
            pie_head,
            text="↔ Bordo regolabile",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=PALETTE["text_dim"]
        ).pack(side="right")

        plt.style.use("dark_background")
        self.fig_pie, self.ax_pie = plt.subplots(figsize=(4.6, 3.8), facecolor=PALETTE["bg_card"])
        self.canvas_pie = FigureCanvasTkAgg(self.fig_pie, master=self.pie_card)
        self.canvas_pie_widget = self.canvas_pie.get_tk_widget()
        self.canvas_pie_widget.configure(bg=PALETTE["bg_card"], bd=0, highlightthickness=0)
        self.canvas_pie_widget.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # 2. Contenitore Grafico Trend Cumulativo
        self.line_card = ctk.CTkFrame(
            self.charts_paned,
            corner_radius=14,
            fg_color=PALETTE["bg_card"],
            border_width=1,
            border_color=PALETTE["border"]
        )
        self.charts_paned.add(self.line_card, minsize=260)

        line_head = ctk.CTkFrame(self.line_card, fg_color="transparent")
        line_head.pack(fill="x", padx=14, pady=(10, 2))
        ctk.CTkLabel(
            line_head,
            text="📈 Trend Giornaliero vs Budget",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=PALETTE["text_primary"]
        ).pack(side="left")
        ctk.CTkLabel(
            line_head,
            text="↔ Trascina per regolare",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=PALETTE["text_dim"]
        ).pack(side="right")

        self.fig_line, self.ax_line = plt.subplots(figsize=(4.6, 3.8), facecolor=PALETTE["bg_card"])
        self.canvas_line = FigureCanvasTkAgg(self.fig_line, master=self.line_card)
        self.canvas_line_widget = self.canvas_line.get_tk_widget()
        self.canvas_line_widget.configure(bg=PALETTE["bg_card"], bd=0, highlightthickness=0)
        self.canvas_line_widget.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def update_dashboard_data(self):
        """Aggiorna le schede KPI, i grafici e il widget delle scadenze."""
        self.dash_title.configure(
            text=f"{calendar.month_name[self.current_month]} {self.current_year}"
        )

        summary = get_monthly_summary(self.current_year, self.current_month)
        tot = summary["total"]
        rem = self.current_budget - tot
        count = summary["count"]

        days_in_m = calendar.monthrange(self.current_year, self.current_month)[1]
        now = datetime.now()
        days_passed = now.day if (self.current_year == now.year and self.current_month == now.month) else days_in_m
        avg = tot / max(1, days_passed)

        breakdown = get_recurring_breakdown_totals()

        # Aggiorna KPI
        self.kpi_labels["remaining"][0].configure(
            text=f"{rem:,.2f} €",
            text_color=PALETTE["emerald"] if rem >= 0 else PALETTE["rose"]
        )
        self.kpi_labels["remaining"][1].configure(
            text=f"Target: {self.current_budget:,.2f} €"
        )

        self.kpi_labels["total"][0].configure(text=f"{tot:,.2f} €")
        self.kpi_labels["total"][1].configure(text=f"{count} movimenti registrati")

        self.kpi_labels["recurring"][0].configure(text=f"{breakdown['totale_fisse']:,.2f} €")
        self.kpi_labels["recurring"][1].configure(
            text=f"Abb: {breakdown['abbonamenti_totale']:.2f} € • Rate: {breakdown['rate_totale']:.2f} €"
        )

        self.kpi_labels["average"][0].configure(text=f"{avg:,.2f} €")
        self.kpi_labels["average"][1].configure(
            text=f"Proiezione fine mese: {(avg * days_in_m):,.2f} €"
        )

        # Progress bar
        pct = (tot / self.current_budget * 100) if self.current_budget > 0 else 0
        norm_pct = min(max(tot / self.current_budget, 0.0), 1.0) if self.current_budget > 0 else 0
        self.progress_bar.set(norm_pct)

        if rem >= 0:
            self.progress_bar.configure(progress_color=PALETTE["accent"])
            self.status_badge.configure(text=f"🟢 In Budget ({rem:,.2f} € rimasti)", text_color=PALETTE["emerald"])
        else:
            self.progress_bar.configure(progress_color=PALETTE["rose"])
            self.status_badge.configure(text=f"🔴 Sforato di {abs(rem):,.2f} €", text_color=PALETTE["rose"])

        self.lbl_progress_pct.configure(text=f"{tot:,.2f} € su {self.current_budget:,.2f} € ({pct:.1f}%)")

        # Aggiorna Widget Scadenze Imminenti
        for widget in self.upcoming_frame.winfo_children():
            widget.destroy()

        upcoming = get_upcoming_charges_this_month()
        if upcoming:
            card_up = ctk.CTkFrame(
                self.upcoming_frame,
                corner_radius=12,
                fg_color=PALETTE["bg_card"],
                border_width=1,
                border_color=PALETTE["border"]
            )
            card_up.pack(fill="x", pady=(0, 4))

            title_row = ctk.CTkFrame(card_up, fg_color="transparent")
            title_row.pack(fill="x", padx=16, pady=(10, 6))

            ctk.CTkLabel(
                title_row,
                text="🔔 Prossime Scadenze in Arrivo nel Mese",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=PALETTE["accent"]
            ).pack(side="left")

            items_row = ctk.CTkFrame(card_up, fg_color="transparent")
            items_row.pack(fill="x", padx=16, pady=(0, 10))

            for up in upcoming[:4]:
                due_lbl = "Oggi!" if up["days_left"] == 0 else f"Tra {up['days_left']}gg"
                tipo_lbl = "⏳ Rata" if up["tipo"] == "rata" else "🔁 Abb."
                tag_col = PALETTE["violet"] if up["tipo"] == "rata" else PALETTE["accent"]

                box = ctk.CTkFrame(items_row, corner_radius=8, fg_color=PALETTE["bg_card_inner"], border_width=1, border_color=PALETTE["border"])
                box.pack(side="left", padx=4, fill="x", expand=True)

                ctk.CTkLabel(
                    box,
                    text=f"{tipo_lbl} • {due_lbl}",
                    font=ctk.CTkFont(size=10, weight="bold"),
                    text_color=tag_col
                ).pack(anchor="w", padx=10, pady=(6, 2))

                ctk.CTkLabel(
                    box,
                    text=f"{up['nome_descrizione']} ({up['importo']:.2f} €)",
                    font=ctk.CTkFont(size=11, weight="bold"),
                    text_color=PALETTE["text_primary"]
                ).pack(anchor="w", padx=10, pady=(0, 6))

        # Recupera dati transazioni del mese per grafici
        df = get_transactions_df()
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
            df_m = df[
                (df["date"].dt.year == self.current_year) &
                (df["date"].dt.month == self.current_month)
            ]
        else:
            df_m = pd.DataFrame()

        # Ridisegna Grafici
        self.ax_pie.clear()
        self.ax_line.clear()

        self.fig_pie.patch.set_facecolor(PALETTE["bg_card"])
        self.fig_line.patch.set_facecolor(PALETTE["bg_card"])
        self.ax_pie.set_facecolor(PALETTE["bg_card"])
        self.ax_line.set_facecolor(PALETTE["bg_card"])

        if not df_m.empty:
            # 1. Donut Chart
            cat_sum = df_m.groupby("category")["amount"].sum()
            colors = [CATEGORY_COLORS.get(c, "#64748B") for c in cat_sum.index]
            wedges, texts, autotexts = self.ax_pie.pie(
                cat_sum,
                labels=[f"{CATEGORY_ICONS.get(c, '')} {c}" for c in cat_sum.index],
                autopct="%1.1f%%",
                pctdistance=0.75,
                startangle=140,
                colors=colors,
                wedgeprops=dict(width=0.45, edgecolor=PALETTE["bg_card"], linewidth=2),
                textprops=dict(color=PALETTE["text_primary"], fontsize=9)
            )
            for at in autotexts:
                at.set_color("white")
                at.set_fontsize(8)
                at.set_weight("bold")

            self.ax_pie.set_title("Ripartizione Categorie", color=PALETTE["text_primary"], fontsize=11, pad=10, weight="bold")

            # 2. Area Chart Cumulativa
            all_days = pd.date_range(
                f"{self.current_year}-{self.current_month:02d}-01",
                f"{self.current_year}-{self.current_month:02d}-{days_in_m:02d}",
                freq="D"
            )
            daily = df_m.groupby(df_m["date"].dt.normalize())["amount"].sum().reindex(all_days, fill_value=0)
            cum = daily.cumsum()

            self.ax_line.fill_between(all_days.day, cum.values, color=PALETTE["accent"], alpha=0.15)
            self.ax_line.plot(all_days.day, cum.values, marker="o", markersize=4, color=PALETTE["accent"], linewidth=2.2, label="Cumulato")
            self.ax_line.axhline(self.current_budget, color=PALETTE["rose"], linestyle="--", linewidth=1.4, label="Budget")

            self.ax_line.set_title("Trend Giornaliero (€)", color=PALETTE["text_primary"], fontsize=11, pad=10, weight="bold")
            self.ax_line.set_xlabel("Giorno", color=PALETTE["text_muted"], fontsize=8)
            self.ax_line.set_ylabel("Totale (€)", color=PALETTE["text_muted"], fontsize=8)
            self.ax_line.tick_params(colors=PALETTE["text_muted"], labelsize=8)
            self.ax_line.grid(True, linestyle=":", alpha=0.25, color=PALETTE["border"])

            for spine in self.ax_line.spines.values():
                spine.set_color(PALETTE["border"])

            leg = self.ax_line.legend(loc="upper left", facecolor=PALETTE["bg_card_inner"], edgecolor=PALETTE["border"], fontsize=8)
            for t in leg.get_texts():
                t.set_color(PALETTE["text_primary"])
        else:
            self.ax_pie.text(0.5, 0.5, "Nessuna spesa\nnel mese", color=PALETTE["text_muted"], ha="center", va="center", fontsize=11)
            self.ax_line.text(0.5, 0.5, "Nessun dato cumulativo", color=PALETTE["text_muted"], ha="center", va="center", fontsize=11)

        try:
            self.fig_pie.tight_layout()
            self.canvas_pie.draw()
        except Exception:
            pass

        try:
            self.fig_line.tight_layout()
            self.canvas_line.draw()
        except Exception:
            pass

    # =========================================================================
    # VISTA 2: MOVIMENTI
    # =========================================================================
    def build_movements_view(self):
        mov = self.views["movements"]
        mov.grid_rowconfigure(2, weight=1)
        mov.grid_columnconfigure(0, weight=1)

        # Quick Filter Chips
        chips_frame = ctk.CTkFrame(mov, corner_radius=12, fg_color=PALETTE["bg_card"], border_width=1, border_color=PALETTE["border"])
        chips_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        ctk.CTkLabel(chips_frame, text="⚡ Filtro Periodo:", font=ctk.CTkFont(size=11, weight="bold"), text_color=PALETTE["text_muted"]).pack(side="left", padx=(14, 8), pady=10)
        
        self.chip_buttons = {}
        chip_opts = ["Questo Mese", "Oggi", "Ultimi 7 Giorni", "Mese Scorso", "Tutte"]
        for opt in chip_opts:
            btn = ctk.CTkButton(
                chips_frame,
                text=opt,
                height=30,
                corner_radius=8,
                fg_color=PALETTE["accent"] if opt == self.quick_filter else "transparent",
                hover_color=PALETTE["accent_hover"],
                text_color=PALETTE["bg_root"] if opt == self.quick_filter else PALETTE["text_muted"],
                font=ctk.CTkFont(size=11, weight="bold"),
                command=lambda o=opt: self.set_quick_filter(o)
            )
            btn.pack(side="left", padx=4, pady=10)
            self.chip_buttons[opt] = btn

        # Barra Filtri Categoria e Testo
        filter_card = ctk.CTkFrame(mov, corner_radius=12, fg_color=PALETTE["bg_card"], border_width=1, border_color=PALETTE["border"])
        filter_card.grid(row=1, column=0, sticky="ew", pady=(0, 12))

        ctk.CTkLabel(filter_card, text="Categoria:", font=ctk.CTkFont(size=12, weight="bold"), text_color=PALETTE["text_muted"]).pack(side="left", padx=(16, 6), pady=10)
        self.filter_cat = ctk.CTkComboBox(
            filter_card,
            values=["Tutte"] + CATEGORIES,
            width=140,
            height=34,
            corner_radius=8,
            fg_color=PALETTE["bg_card_inner"],
            border_color=PALETTE["border"],
            text_color=PALETTE["text_primary"],
            command=lambda _: self.load_movements_data()
        )
        self.filter_cat.set("Tutte")
        self.filter_cat.pack(side="left", padx=4, pady=10)

        ctk.CTkLabel(filter_card, text="Cerca:", font=ctk.CTkFont(size=12, weight="bold"), text_color=PALETTE["text_muted"]).pack(side="left", padx=(16, 6), pady=10)
        self.search_entry = ctk.CTkEntry(
            filter_card,
            placeholder_text="Descrizione o note...",
            width=220,
            height=34,
            corner_radius=8,
            fg_color=PALETTE["bg_card_inner"],
            border_color=PALETTE["border"],
            text_color=PALETTE["text_primary"]
        )
        self.search_entry.pack(side="left", padx=4, pady=10)
        self.search_entry.bind("<Return>", lambda _: self.load_movements_data())

        ctk.CTkButton(
            filter_card,
            text="Filtra",
            width=70,
            height=34,
            corner_radius=8,
            fg_color=PALETTE["accent"],
            hover_color=PALETTE["accent_hover"],
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.load_movements_data
        ).pack(side="left", padx=8, pady=10)

        ctk.CTkButton(
            filter_card,
            text="Reset",
            width=70,
            height=34,
            corner_radius=8,
            fg_color="transparent",
            hover_color=PALETTE["bg_card_inner"],
            text_color=PALETTE["text_muted"],
            border_width=1,
            border_color=PALETTE["border"],
            font=ctk.CTkFont(size=12),
            command=self.reset_filters
        ).pack(side="left", padx=4, pady=10)

        # Tabella Treeview
        table_card = ctk.CTkFrame(mov, corner_radius=12, fg_color=PALETTE["bg_card"], border_width=1, border_color=PALETTE["border"])
        table_card.grid(row=2, column=0, sticky="nsew")
        table_card.grid_rowconfigure(0, weight=1)
        table_card.grid_columnconfigure(0, weight=1)

        cols = ("id", "date", "amount", "category", "description", "source")
        self.tree = ttk.Treeview(table_card, columns=cols, show="headings", selectmode="browse")

        self.tree.heading("id", text="# ID")
        self.tree.heading("date", text="📅 Data")
        self.tree.heading("amount", text="💶 Importo")
        self.tree.heading("category", text="🏷️ Categoria")
        self.tree.heading("description", text="📝 Descrizione")
        self.tree.heading("source", text="Canale")

        self.tree.column("id", width=65, anchor="center")
        self.tree.column("date", width=110, anchor="center")
        self.tree.column("amount", width=120, anchor="e")
        self.tree.column("category", width=140, anchor="w")
        self.tree.column("description", width=420, anchor="w")
        self.tree.column("source", width=110, anchor="center")

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Treeview",
            background=PALETTE["bg_card"],
            foreground=PALETTE["text_primary"],
            rowheight=34,
            fieldbackground=PALETTE["bg_card"],
            bordercolor=PALETTE["border"],
            font=("Segoe UI", 10)
        )
        style.configure(
            "Treeview.Heading",
            background=PALETTE["bg_sidebar"],
            foreground=PALETTE["text_muted"],
            relief="flat",
            font=("Segoe UI", 10, "bold")
        )
        style.map("Treeview", background=[("selected", "#0284C7")], foreground=[("selected", "white")])

        sb = ttk.Scrollbar(table_card, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)

        self.tree.grid(row=0, column=0, sticky="nsew", padx=(12, 0), pady=12)
        sb.grid(row=0, column=1, sticky="ns", padx=(0, 12), pady=12)
        self.tree.bind("<Double-1>", lambda e: self.edit_selected_transaction())

        # Azioni in basso
        action_bar = ctk.CTkFrame(mov, fg_color="transparent")
        action_bar.grid(row=3, column=0, sticky="ew", pady=(12, 0))

        self.lbl_table_count = ctk.CTkLabel(
            action_bar,
            text="",
            font=ctk.CTkFont(size=12),
            text_color=PALETTE["text_muted"]
        )
        self.lbl_table_count.pack(side="left")

        ctk.CTkButton(
            action_bar,
            text="📥  Esporta CSV",
            height=36,
            corner_radius=8,
            fg_color=PALETTE["bg_card"],
            hover_color=PALETTE["border"],
            border_width=1,
            border_color=PALETTE["border"],
            text_color=PALETTE["text_primary"],
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.export_csv
        ).pack(side="right", padx=6)

        ctk.CTkButton(
            action_bar,
            text="🗑️  Elimina Spesa",
            height=36,
            corner_radius=8,
            fg_color=PALETTE["rose"],
            hover_color="#DC2626",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.delete_selected_transaction
        ).pack(side="right", padx=6)

        ctk.CTkButton(
            action_bar,
            text="✏️  Modifica Spesa",
            height=36,
            corner_radius=8,
            fg_color=PALETTE["accent"],
            hover_color=PALETTE["accent_hover"],
            text_color=PALETTE["bg_root"],
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.edit_selected_transaction
        ).pack(side="right", padx=6)

    def set_quick_filter(self, opt: str):
        self.quick_filter = opt
        for k, btn in self.chip_buttons.items():
            if k == opt:
                btn.configure(fg_color=PALETTE["accent"], text_color=PALETTE["bg_root"])
            else:
                btn.configure(fg_color="transparent", text_color=PALETTE["text_muted"])
        self.load_movements_data()

    def load_movements_data(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        df = get_transactions_df()
        if df.empty:
            self.lbl_table_count.configure(text="Nessuna transazione registrata nel database.")
            return

        df["date_dt"] = pd.to_datetime(df["date"])
        today_d = date.today()

        if self.quick_filter == "Oggi":
            filtered = df[df["date_dt"].dt.date == today_d].copy()
        elif self.quick_filter == "Ultimi 7 Giorni":
            filtered = df[df["date_dt"].dt.date >= (today_d - timedelta(days=7))].copy()
        elif self.quick_filter == "Questo Mese":
            filtered = df[
                (df["date_dt"].dt.year == self.current_year) &
                (df["date_dt"].dt.month == self.current_month)
            ].copy()
        elif self.quick_filter == "Mese Scorso":
            first_curr = date(self.current_year, self.current_month, 1)
            prev_d = first_curr - timedelta(days=1)
            filtered = df[
                (df["date_dt"].dt.year == prev_d.year) &
                (df["date_dt"].dt.month == prev_d.month)
            ].copy()
        else:
            filtered = df.copy()

        cat = self.filter_cat.get()
        if cat != "Tutte":
            filtered = filtered[filtered["category"] == cat]

        query = self.search_entry.get().strip()
        if query:
            filtered = filtered[filtered["description"].str.contains(query, case=False, na=False)]

        tot = filtered["amount"].sum()
        self.lbl_table_count.configure(
            text=f"Visualizzate {len(filtered)} transazioni • Totale: {tot:,.2f} € (Filtro: {self.quick_filter})"
        )

        for _, row in filtered.iterrows():
            icon = CATEGORY_ICONS.get(row["category"], "🏷️")
            src = row["source"]
            if src == "rata":
                src_txt = "⏳ Rata"
            elif src == "abbonamento":
                src_txt = "🔁 Abb."
            elif src == "bot":
                src_txt = "📱 Telegram"
            else:
                src_txt = "💻 Manuale"

            self.tree.insert(
                "",
                "end",
                values=(
                    f"#{row['id']}",
                    row["date_dt"].strftime("%d/%m/%Y"),
                    f"{row['amount']:.2f} €",
                    f"{icon} {row['category']}",
                    row["description"] or "-",
                    src_txt
                )
            )

    def reset_filters(self):
        self.filter_cat.set("Tutte")
        self.search_entry.delete(0, "end")
        self.set_quick_filter("Questo Mese")

    def delete_selected_transaction(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Attenzione", "Seleziona prima una transazione da eliminare.")
            return

        item = self.tree.item(selected[0])
        tx_id_str = item["values"][0].replace("#", "").strip()
        try:
            tx_id = int(tx_id_str)
        except ValueError:
            messagebox.showerror("Errore", "ID transazione non valido.")
            return

        amount = item["values"][2]
        desc = item["values"][4]

        # Recupera i dati e il cloud_id PRIMA di eliminare dal DB locale
        tx = get_transaction_by_id(tx_id)
        cloud_id = tx.get("cloud_id") if tx else None

        if messagebox.askyesno("Conferma Eliminazione", f"Vuoi eliminare la spesa #{tx_id} di {amount} ({desc})?"):
            # 1. Se configurato il cloud, elimina prima su Google Sheets in background
            threading.Thread(
                target=lambda: send_delete_to_cloud(tx_id, cloud_id=cloud_id),
                daemon=True
            ).start()

            # 2. Elimina dal DB locale SQLite
            if delete_transaction(tx_id):
                messagebox.showinfo("Successo", f"Transazione #{tx_id} eliminata con successo sia in locale che su Google Fogli.")
                self.load_movements_data()
                self.update_dashboard_data()
            else:
                messagebox.showerror("Errore", "Impossibile eliminare la transazione dal database locale.")

    def edit_selected_transaction(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Attenzione", "Seleziona prima una transazione da modificare.")
            return

        item = self.tree.item(selected[0])
        tx_id_str = str(item["values"][0]).replace("#", "").strip()
        try:
            tx_id = int(tx_id_str)
        except ValueError:
            messagebox.showerror("Errore", "ID transazione non valido.")
            return

        self.open_edit_transaction_dialog(tx_id)

    def open_edit_transaction_dialog(self, tx_id: int):
        """Apre un dialogo modale moderno per modificare una spesa (con sincronizzazione bidirezionale)."""
        tx = get_transaction_by_id(tx_id)
        if not tx:
            messagebox.showerror("Errore", f"Transazione #{tx_id} non trovata.")
            return

        dlg = ctk.CTkToplevel(self)
        dlg.title(f"Modifica Spesa #{tx_id}")
        dlg.geometry("520x560")
        dlg.resizable(False, False)
        dlg.grab_set()

        dlg.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 520) // 2
        y = self.winfo_y() + (self.winfo_height() - 560) // 2
        dlg.geometry(f"+{x}+{y}")
        dlg.configure(fg_color=PALETTE["bg_root"])

        ctk.CTkLabel(
            dlg,
            text=f"✏️  Modifica Spesa #{tx_id}",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color=PALETTE["text_primary"]
        ).pack(padx=24, pady=(20, 2), anchor="w")

        cloud_info = f" (Collegata al Foglio Google riga #{tx['cloud_id']})" if tx.get("cloud_id") else " (Spesa locale)"
        ctk.CTkLabel(
            dlg,
            text=f"Aggiorna i dettagli della transazione.{cloud_info}\nLe modifiche verranno sincronizzate in tempo reale sul Foglio Google.",
            font=ctk.CTkFont(size=12),
            text_color=PALETTE["text_muted"],
            justify="left"
        ).pack(padx=24, pady=(0, 14), anchor="w")

        card = ctk.CTkFrame(dlg, corner_radius=14, fg_color=PALETTE["bg_card"], border_width=1, border_color=PALETTE["border"])
        card.pack(fill="both", expand=True, padx=24, pady=(0, 16))

        # Importo
        ctk.CTkLabel(card, text="Importo (€):", font=ctk.CTkFont(size=12, weight="bold"), text_color=PALETTE["text_muted"]).pack(anchor="w", padx=24, pady=(16, 2))
        ed_amount = ctk.CTkEntry(
            card,
            height=38,
            corner_radius=8,
            fg_color=PALETTE["bg_card_inner"],
            border_color=PALETTE["border"],
            text_color=PALETTE["text_primary"]
        )
        ed_amount.insert(0, f"{float(tx['amount']):.2f}")
        ed_amount.pack(fill="x", padx=24, pady=(0, 10))

        # Categoria
        ctk.CTkLabel(card, text="Categoria:", font=ctk.CTkFont(size=12, weight="bold"), text_color=PALETTE["text_muted"]).pack(anchor="w", padx=24, pady=(4, 2))
        cat_labels = [f"{CATEGORY_ICONS.get(c, '🏷️')}  {c}" for c in CATEGORIES]
        ed_cat = ctk.CTkComboBox(
            card,
            values=cat_labels,
            height=38,
            corner_radius=8,
            fg_color=PALETTE["bg_card_inner"],
            border_color=PALETTE["border"],
            text_color=PALETTE["text_primary"]
        )
        current_cat = tx.get("category", "Altro")
        matching = [cl for cl in cat_labels if current_cat.lower() in cl.lower()]
        ed_cat.set(matching[0] if matching else cat_labels[0])
        ed_cat.pack(fill="x", padx=24, pady=(0, 10))

        # Data
        d_row = ctk.CTkFrame(card, fg_color="transparent")
        d_row.pack(fill="x", padx=24, pady=(4, 2))
        ctk.CTkLabel(d_row, text="Data (Giorno / Mese / Anno):", font=ctk.CTkFont(size=12, weight="bold"), text_color=PALETTE["text_muted"]).pack(side="left")
        ctk.CTkLabel(d_row, text="Formato GG/MM/AAAA", font=ctk.CTkFont(size=11), text_color=PALETTE["accent"]).pack(side="right")

        ed_date = ctk.CTkEntry(
            card,
            height=38,
            corner_radius=8,
            fg_color=PALETTE["bg_card_inner"],
            border_color=PALETTE["border"],
            text_color=PALETTE["text_primary"]
        )
        raw_db_date = str(tx.get("date", ""))
        try:
            disp_date_init = datetime.strptime(raw_db_date, "%Y-%m-%d").strftime("%d/%m/%Y")
        except Exception:
            disp_date_init = raw_db_date
        ed_date.insert(0, disp_date_init)
        ed_date.pack(fill="x", padx=24, pady=(0, 10))

        # Descrizione
        ctk.CTkLabel(card, text="Descrizione:", font=ctk.CTkFont(size=12, weight="bold"), text_color=PALETTE["text_muted"]).pack(anchor="w", padx=24, pady=(4, 2))
        ed_desc = ctk.CTkEntry(
            card,
            height=38,
            corner_radius=8,
            fg_color=PALETTE["bg_card_inner"],
            border_color=PALETTE["border"],
            text_color=PALETTE["text_primary"]
        )
        ed_desc.insert(0, str(tx.get("description") or ""))
        ed_desc.pack(fill="x", padx=24, pady=(0, 10))

        status_lbl = ctk.CTkLabel(card, text="", font=ctk.CTkFont(size=12, weight="bold"))
        status_lbl.pack(pady=(2, 6))

        # Pulsanti Azione
        btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_row.pack(fill="x", padx=24, pady=(0, 20))

        def _save_changes():
            raw_amt = ed_amount.get().replace("€", "").replace(",", ".").strip()
            try:
                amount_val = float(raw_amt)
                if amount_val <= 0:
                    raise ValueError()
            except ValueError:
                status_lbl.configure(text="⚠️ Inserisci un importo valido maggiore di zero.", text_color=PALETTE["rose"])
                return

            cat_sel = ed_cat.get().split()[-1]
            raw_d = ed_date.get().strip().lower()

            if raw_d in ("oggi", ""):
                iso_d = date.today().strftime("%Y-%m-%d")
            elif raw_d in ("ieri",):
                iso_d = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
            else:
                iso_d = None
                for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d"):
                    try:
                        iso_d = datetime.strptime(raw_d, fmt).strftime("%Y-%m-%d")
                        break
                    except ValueError:
                        continue
                if not iso_d:
                    status_lbl.configure(text="⚠️ Data non valida! Usa formato GG/MM/AAAA (es. 15/10/2026).", text_color=PALETTE["rose"])
                    return

            desc_val = ed_desc.get().strip()

            btn_save.configure(state="disabled", text="⏳ Salvataggio...")
            btn_cancel.configure(state="disabled")
            status_lbl.configure(text="Sincronizzazione con il Foglio Google in corso...", text_color=PALETTE["accent"])
            dlg.update()

            def _worker():
                res = send_edit_to_cloud(tx_id, amount_val, cat_sel, desc_val, iso_d)

                def _on_finish():
                    if res.get("success"):
                        update_transaction(
                            transaction_id=tx_id,
                            amount=amount_val,
                            category=cat_sel,
                            description=desc_val,
                            date_str=iso_d
                        )
                        dlg.destroy()
                        self.load_movements_data()
                        self.update_dashboard_data()
                        messagebox.showinfo(
                            "Modifica Spesa",
                            f"✅ Spesa #{tx_id} aggiornata con successo sia nel Foglio Google che nell'app!"
                        )
                    else:
                        err = str(res.get("error", "Errore"))
                        btn_save.configure(state="normal", text="💾  Salva Modifiche")
                        btn_cancel.configure(state="normal")
                        if "unknown" in err.lower():
                            status_lbl.configure(
                                text="⚠️ Google Apps Script non aggiornato alla nuova versione!",
                                text_color=PALETTE["rose"]
                            )
                            messagebox.showwarning(
                                "Distribuzione Apps Script Richiesta",
                                "⚠️ Il server Google Apps Script non ha ancora la funzione di modifica attiva!\n\n"
                                "Per risolvere definitivamente:\n"
                                "1. Apri il tuo progetto su script.google.com\n"
                                "2. Copia e incolla il codice aggiornato da 'google_apps_script.js'\n"
                                "3. Clicca su 'Distribuisci' ➔ 'Gestisci distribuzioni' ➔ ✏️ (Modifica)\n"
                                "4. In 'Versione' seleziona 'Nuova versione' e clicca 'Distribuisci'."
                            )
                        else:
                            status_lbl.configure(text=f"❌ Errore Google: {err}", text_color=PALETTE["rose"])

                self.after(0, _on_finish)

            threading.Thread(target=_worker, daemon=True).start()

        btn_cancel = ctk.CTkButton(
            btn_row,
            text="Annulla",
            height=38,
            corner_radius=8,
            fg_color="transparent",
            hover_color=PALETTE["bg_card"],
            border_width=1,
            border_color=PALETTE["border"],
            text_color=PALETTE["text_muted"],
            font=ctk.CTkFont(size=12),
            command=dlg.destroy
        )
        btn_cancel.pack(side="left", padx=(0, 8), fill="x", expand=True)

        btn_save = ctk.CTkButton(
            btn_row,
            text="💾  Salva Modifiche",
            height=38,
            corner_radius=8,
            fg_color=PALETTE["accent"],
            hover_color=PALETTE["accent_hover"],
            text_color=PALETTE["bg_root"],
            font=ctk.CTkFont(size=12, weight="bold"),
            command=_save_changes
        )
        btn_save.pack(side="right", padx=(8, 0), fill="x", expand=True)

    def export_csv(self):
        df = get_transactions_df()
        if df.empty:
            messagebox.showinfo("Esporta CSV", "Nessun dato da esportare.")
            return

        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("File CSV", "*.csv")],
            initialfile=f"movimenti_{self.current_year}_{self.current_month:02d}.csv"
        )
        if filename:
            df.to_csv(filename, index=False)
            messagebox.showinfo("Esportazione", f"File salvato con successo:\n{filename}")

    # =========================================================================
    # VISTA 3: PIANIFICAZIONE & RATE / ABBONAMENTI
    # =========================================================================
    def build_plans_view(self):
        plan_view = self.views["plans"]
        plan_view.grid_rowconfigure(1, weight=1)
        plan_view.grid_columnconfigure(0, weight=1)

        # Header con statistiche quote e pulsante verifica scadenze
        header_card = ctk.CTkFrame(plan_view, corner_radius=12, fg_color=PALETTE["bg_card"], border_width=1, border_color=PALETTE["border"])
        header_card.grid(row=0, column=0, sticky="ew", pady=(0, 12))

        h_left = ctk.CTkFrame(header_card, fg_color="transparent")
        h_left.pack(side="left", padx=16, pady=12)

        ctk.CTkLabel(
            h_left,
            text="🔁 Pianificazione: Rate vs Abbonamenti",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=PALETTE["text_primary"]
        ).pack(anchor="w")

        self.lbl_plan_summary = ctk.CTkLabel(
            h_left,
            text="Caricamento impegni...",
            font=ctk.CTkFont(size=12),
            text_color=PALETTE["text_muted"]
        )
        self.lbl_plan_summary.pack(anchor="w")

        h_right = ctk.CTkFrame(header_card, fg_color="transparent")
        h_right.pack(side="right", padx=16, pady=12)

        ctk.CTkButton(
            h_right,
            text="⚡ Verifica Scadenze Ora",
            height=34,
            corner_radius=8,
            fg_color=PALETTE["accent"],
            hover_color=PALETTE["accent_hover"],
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.check_recurring_now
        ).pack(side="right")

        # Split Layout con Bordo Ridimensionabile (PanedWindow)
        main_split = tk.PanedWindow(
            plan_view,
            orient=tk.HORIZONTAL,
            sashwidth=8,
            sashpad=2,
            sashrelief=tk.FLAT,
            bg=PALETTE["bg_root"],
            bd=0,
            cursor="sb_h_double_arrow",
            showhandle=True,
            handlepad=6,
            handlesize=10
        )
        main_split.grid(row=1, column=0, sticky="nsew")

        # Tabella Piani & Abbonamenti (Sinistra)
        t_card = ctk.CTkFrame(main_split, corner_radius=12, fg_color=PALETTE["bg_card"], border_width=1, border_color=PALETTE["border"])
        main_split.add(t_card, minsize=380)
        t_card.grid_rowconfigure(0, weight=1)
        t_card.grid_columnconfigure(0, weight=1)

        p_cols = ("id", "type", "name", "amount", "day", "progress", "status")
        self.plan_tree = ttk.Treeview(t_card, columns=p_cols, show="headings", selectmode="browse")

        self.plan_tree.heading("id", text="# ID")
        self.plan_tree.heading("type", text="Tipo")
        self.plan_tree.heading("name", text="Nome / Servizio")
        self.plan_tree.heading("amount", text="Importo")
        self.plan_tree.heading("day", text="Giorno")
        self.plan_tree.heading("progress", text="Progresso Rate")
        self.plan_tree.heading("status", text="Stato")

        self.plan_tree.column("id", width=45, anchor="center")
        self.plan_tree.column("type", width=70, anchor="center")
        self.plan_tree.column("name", width=160, anchor="w")
        self.plan_tree.column("amount", width=85, anchor="e")
        self.plan_tree.column("day", width=65, anchor="center")
        self.plan_tree.column("progress", width=120, anchor="center")
        self.plan_tree.column("status", width=95, anchor="center")

        p_sb = ttk.Scrollbar(t_card, orient="vertical", command=self.plan_tree.yview)
        self.plan_tree.configure(yscrollcommand=p_sb.set)

        self.plan_tree.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=10)
        p_sb.grid(row=0, column=1, sticky="ns", padx=(0, 10), pady=10)

        # Azioni Sotto Tabella
        p_act = ctk.CTkFrame(t_card, fg_color="transparent")
        p_act.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))

        ctk.CTkButton(
            p_act,
            text="⏸️/▶️ Attiva o Pausa",
            height=32,
            corner_radius=8,
            fg_color=PALETTE["bg_sidebar"],
            hover_color=PALETTE["border"],
            border_width=1,
            border_color=PALETTE["border"],
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.toggle_selected_plan
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            p_act,
            text="🗑️ Elimina",
            height=32,
            corner_radius=8,
            fg_color=PALETTE["rose"],
            hover_color="#DC2626",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.delete_selected_plan
        ).pack(side="left")

        # Modulo Inserimento Piano (Destra)
        form_card = ctk.CTkFrame(main_split, corner_radius=12, fg_color=PALETTE["bg_card"], border_width=1, border_color=PALETTE["border"])
        main_split.add(form_card, minsize=300)

        ctk.CTkLabel(
            form_card,
            text="➕ Configura Nuova Uscita Periodica",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color=PALETTE["text_primary"]
        ).pack(anchor="w", padx=18, pady=(16, 2))

        ctk.CTkLabel(
            form_card,
            text="Distingui tra abbonamento continuo o piano a rate",
            font=ctk.CTkFont(size=11),
            text_color=PALETTE["text_muted"]
        ).pack(anchor="w", padx=18, pady=(0, 12))

        # Scelta Tipo
        self.tipo_var = ctk.StringVar(value="abbonamento")
        r_box = ctk.CTkFrame(form_card, fg_color="transparent")
        r_box.pack(fill="x", padx=18, pady=(0, 8))

        ctk.CTkRadioButton(
            r_box,
            text="🔁 Abbonamento",
            variable=self.tipo_var,
            value="abbonamento",
            command=self.on_tipo_change,
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(side="left", padx=(0, 14))

        ctk.CTkRadioButton(
            r_box,
            text="⏳ Rata (Finanziamento)",
            variable=self.tipo_var,
            value="rata",
            command=self.on_tipo_change,
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(side="left")

        # Campi Comuni
        ctk.CTkLabel(form_card, text="Nome / Servizio:", font=ctk.CTkFont(size=11, weight="bold"), text_color=PALETTE["text_muted"]).pack(anchor="w", padx=18, pady=(4, 2))
        self.in_p_name = ctk.CTkEntry(form_card, placeholder_text="es. Netflix, Rata Auto, Palestra...", height=34, corner_radius=8, fg_color=PALETTE["bg_card_inner"], border_color=PALETTE["border"])
        self.in_p_name.pack(fill="x", padx=18, pady=(0, 6))

        ctk.CTkLabel(form_card, text="Importo Rata/Quota Mensile (€):", font=ctk.CTkFont(size=11, weight="bold"), text_color=PALETTE["text_muted"]).pack(anchor="w", padx=18, pady=(2, 2))
        self.in_p_amount = ctk.CTkEntry(form_card, placeholder_text="es. 49.90", height=34, corner_radius=8, fg_color=PALETTE["bg_card_inner"], border_color=PALETTE["border"])
        self.in_p_amount.pack(fill="x", padx=18, pady=(0, 6))

        ctk.CTkLabel(form_card, text="Categoria:", font=ctk.CTkFont(size=11, weight="bold"), text_color=PALETTE["text_muted"]).pack(anchor="w", padx=18, pady=(2, 2))
        cat_labels = [f"{CATEGORY_ICONS.get(c, '🏷️')}  {c}" for c in CATEGORIES]
        self.in_p_cat = ctk.CTkComboBox(form_card, values=cat_labels, height=34, corner_radius=8, fg_color=PALETTE["bg_card_inner"], border_color=PALETTE["border"], text_color=PALETTE["text_primary"])
        self.in_p_cat.set(cat_labels[0])
        self.in_p_cat.pack(fill="x", padx=18, pady=(0, 6))

        ctk.CTkLabel(form_card, text="Giorno del Mese (1 - 31):", font=ctk.CTkFont(size=11, weight="bold"), text_color=PALETTE["text_muted"]).pack(anchor="w", padx=18, pady=(2, 2))
        self.in_p_day = ctk.CTkEntry(form_card, placeholder_text="es. 15", height=34, corner_radius=8, fg_color=PALETTE["bg_card_inner"], border_color=PALETTE["border"])
        self.in_p_day.insert(0, "1")
        self.in_p_day.pack(fill="x", padx=18, pady=(0, 6))

        # Campi specifici per Rate
        self.rate_fields_frame = ctk.CTkFrame(form_card, fg_color="transparent")
        
        ctk.CTkLabel(self.rate_fields_frame, text="Numero Rate Totali:", font=ctk.CTkFont(size=11, weight="bold"), text_color=PALETTE["text_muted"]).pack(anchor="w", pady=(2, 2))
        self.in_p_tot_rate = ctk.CTkEntry(self.rate_fields_frame, placeholder_text="es. 12 o 24", height=34, corner_radius=8, fg_color=PALETTE["bg_card_inner"], border_color=PALETTE["border"])
        self.in_p_tot_rate.insert(0, "12")
        self.in_p_tot_rate.pack(fill="x", pady=(0, 6))

        ctk.CTkLabel(self.rate_fields_frame, text="Rate Già Saldate (se in corso):", font=ctk.CTkFont(size=11, weight="bold"), text_color=PALETTE["text_muted"]).pack(anchor="w", pady=(2, 2))
        self.in_p_pag_rate = ctk.CTkEntry(self.rate_fields_frame, placeholder_text="es. 0", height=34, corner_radius=8, fg_color=PALETTE["bg_card_inner"], border_color=PALETTE["border"])
        self.in_p_pag_rate.insert(0, "0")
        self.in_p_pag_rate.pack(fill="x", pady=(0, 6))

        self.lbl_p_status = ctk.CTkLabel(form_card, text="", font=ctk.CTkFont(size=11, weight="bold"))
        self.lbl_p_status.pack(pady=(2, 4))

        ctk.CTkButton(
            form_card,
            text="💾 Salva Spesa Periodica",
            height=38,
            corner_radius=8,
            fg_color=PALETTE["accent"],
            hover_color=PALETTE["accent_hover"],
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.submit_plan
        ).pack(fill="x", padx=18, pady=(0, 14))

    def on_tipo_change(self):
        if self.tipo_var.get() == "rata":
            self.rate_fields_frame.pack(fill="x", padx=18, pady=(0, 4))
        else:
            self.rate_fields_frame.pack_forget()

    def load_plans_data(self):
        for item in self.plan_tree.get_children():
            self.plan_tree.delete(item)

        items = get_recurring_expenses_list()
        breakdown = get_recurring_breakdown_totals()
        self.lbl_plan_summary.configure(
            text=f"Totale Fisse: {breakdown['totale_fisse']:,.2f} €/mese (Abbonamenti: {breakdown['abbonamenti_totale']:,.2f} € • Rate: {breakdown['rate_totale']:,.2f} €)"
        )

        for r in items:
            is_rata = r["tipo"] == "rata"
            tipo_txt = "⏳ Rata" if is_rata else "🔁 Abb."
            
            if r["stato"] == "completato":
                st_txt = "✅ Concluso"
            elif r["stato"] == "attivo":
                st_txt = "🟢 Attivo"
            else:
                st_txt = "⏸️ In Pausa"

            if is_rata and r.get("numero_rate_totali"):
                pct = int((r["rate_pagate"] / r["numero_rate_totali"]) * 100)
                prog_txt = f"{r['rate_pagate']}/{r['numero_rate_totali']} ({pct}%)"
            else:
                prog_txt = "Continuo"

            self.plan_tree.insert(
                "",
                "end",
                values=(
                    f"#{r['id']}",
                    tipo_txt,
                    r["nome_descrizione"],
                    f"{r['importo']:.2f} €",
                    f"Giorno {r['giorno_addebito']}",
                    prog_txt,
                    st_txt
                )
            )

    def submit_plan(self):
        nome = self.in_p_name.get().strip()
        if not nome:
            self.lbl_p_status.configure(text="⚠️ Inserisci un nome per la spesa.", text_color=PALETTE["rose"])
            return

        try:
            importo = float(self.in_p_amount.get().replace(",", "."))
            if importo <= 0:
                raise ValueError()
        except ValueError:
            self.lbl_p_status.configure(text="⚠️ Importo non valido.", text_color=PALETTE["rose"])
            return

        try:
            giorno = int(self.in_p_day.get().strip())
            if not (1 <= giorno <= 31):
                raise ValueError()
        except ValueError:
            self.lbl_p_status.configure(text="⚠️ Giorno del mese tra 1 e 31.", text_color=PALETTE["rose"])
            return

        cat = self.in_p_cat.get().split()[-1]
        tipo = self.tipo_var.get()

        tot_rate = None
        pag_rate = 0
        if tipo == "rata":
            try:
                tot_rate = int(self.in_p_tot_rate.get().strip())
                pag_rate = int(self.in_p_pag_rate.get().strip())
                if tot_rate <= 1:
                    raise ValueError()
            except ValueError:
                self.lbl_p_status.configure(text="⚠️ Specifica il numero di rate valido (>= 2).", text_color=PALETTE["rose"])
                return

        new_id = add_recurring_expense(
            tipo=tipo,
            nome_descrizione=nome,
            importo=importo,
            categoria=cat,
            giorno_addebito=giorno,
            numero_rate_totali=tot_rate,
            rate_pagate=pag_rate
        )

        self.lbl_p_status.configure(text=f"✅ Spesa #{new_id} registrata!", text_color=PALETTE["emerald"])
        self.in_p_name.delete(0, "end")
        self.in_p_amount.delete(0, "end")
        self.load_plans_data()
        self.update_dashboard_data()

    def toggle_selected_plan(self):
        selected = self.plan_tree.selection()
        if not selected:
            messagebox.showwarning("Attenzione", "Seleziona prima una voce dall'elenco.")
            return

        item = self.plan_tree.item(selected[0])
        plan_id = int(item["values"][0].replace("#", ""))
        st_curr = item["values"][6]

        new_st = "in pausa" if "Attivo" in st_curr else "attivo"
        update_recurring_expense_status(plan_id, new_st)
        self.load_plans_data()
        self.update_dashboard_data()

    def delete_selected_plan(self):
        selected = self.plan_tree.selection()
        if not selected:
            messagebox.showwarning("Attenzione", "Seleziona prima una voce dall'elenco.")
            return

        item = self.plan_tree.item(selected[0])
        plan_id = int(item["values"][0].replace("#", ""))
        nome = item["values"][2]

        if messagebox.askyesno("Conferma", f"Eliminare definitivamente '{nome}'?"):
            delete_recurring_expense(plan_id)
            self.load_plans_data()
            self.update_dashboard_data()

    def check_recurring_now(self):
        processed = process_due_recurring_expenses(send_notification=True)
        if processed:
            messagebox.showinfo("Addebiti Registrati", f"Elaborati {len(processed)} addebiti maturati!")
        else:
            messagebox.showinfo("Controllo Scadenze", "Nessuna spesa periodica in scadenza per oggi.")
        self.refresh_all()
        self.load_plans_data()

    # =========================================================================
    # VISTA 4: NUOVA SPESA MANUALE
    # =========================================================================
    def build_new_expense_view(self):
        form_view = self.views["new_expense"]
        form_view.grid_rowconfigure(0, weight=1)
        form_view.grid_columnconfigure(0, weight=1)

        card = ctk.CTkFrame(
            form_view,
            corner_radius=18,
            fg_color=PALETTE["bg_card"],
            border_width=1,
            border_color=PALETTE["border"],
            width=500
        )
        card.grid(row=0, column=0, padx=40, pady=30)
        card.grid_propagate(False)

        ctk.CTkLabel(
            card,
            text="➕ Registra Nuova Spesa",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=PALETTE["text_primary"]
        ).pack(pady=(28, 4))

        ctk.CTkLabel(
            card,
            text="Inserisci i dettagli dell'uscita estemporanea",
            font=ctk.CTkFont(size=12),
            text_color=PALETTE["text_muted"]
        ).pack(pady=(0, 22))

        ctk.CTkLabel(card, text="Importo (€):", font=ctk.CTkFont(size=12, weight="bold"), text_color=PALETTE["text_muted"]).pack(anchor="w", padx=40, pady=(4, 2))
        self.in_amount = ctk.CTkEntry(
            card,
            placeholder_text="es. 15.50 o 15,50",
            height=38,
            corner_radius=8,
            fg_color=PALETTE["bg_card_inner"],
            border_color=PALETTE["border"],
            text_color=PALETTE["text_primary"]
        )
        self.in_amount.pack(fill="x", padx=40, pady=(0, 10))

        ctk.CTkLabel(card, text="Categoria:", font=ctk.CTkFont(size=12, weight="bold"), text_color=PALETTE["text_muted"]).pack(anchor="w", padx=40, pady=(4, 2))
        cat_labels = [f"{CATEGORY_ICONS.get(c, '🏷️')}  {c}" for c in CATEGORIES]
        self.in_category = ctk.CTkComboBox(
            card,
            values=cat_labels,
            height=38,
            corner_radius=8,
            fg_color=PALETTE["bg_card_inner"],
            border_color=PALETTE["border"],
            text_color=PALETTE["text_primary"]
        )
        self.in_category.set(cat_labels[0])
        self.in_category.pack(fill="x", padx=40, pady=(0, 10))

        date_lbl_row = ctk.CTkFrame(card, fg_color="transparent")
        date_lbl_row.pack(fill="x", padx=40, pady=(4, 2))
        ctk.CTkLabel(date_lbl_row, text="Data (Giorno / Mese / Anno):", font=ctk.CTkFont(size=12, weight="bold"), text_color=PALETTE["text_muted"]).pack(side="left")
        ctk.CTkLabel(date_lbl_row, text="Formato GG/MM/AAAA", font=ctk.CTkFont(size=11), text_color=PALETTE["accent"]).pack(side="right")

        self.in_date = ctk.CTkEntry(
            card,
            placeholder_text="es. 15/10/2026 (oppure 'oggi')",
            height=38,
            corner_radius=8,
            fg_color=PALETTE["bg_card_inner"],
            border_color=PALETTE["border"],
            text_color=PALETTE["text_primary"]
        )
        self.in_date.insert(0, date.today().strftime("%d/%m/%Y"))
        self.in_date.pack(fill="x", padx=40, pady=(0, 10))

        ctk.CTkLabel(card, text="Descrizione (opzionale):", font=ctk.CTkFont(size=12, weight="bold"), text_color=PALETTE["text_muted"]).pack(anchor="w", padx=40, pady=(4, 2))
        self.in_desc = ctk.CTkEntry(
            card,
            placeholder_text="es. Spesa supermercato, benzina, cena...",
            height=38,
            corner_radius=8,
            fg_color=PALETTE["bg_card_inner"],
            border_color=PALETTE["border"],
            text_color=PALETTE["text_primary"]
        )
        self.in_desc.pack(fill="x", padx=40, pady=(0, 16))

        self.in_status_lbl = ctk.CTkLabel(card, text="", font=ctk.CTkFont(size=12, weight="bold"))
        self.in_status_lbl.pack(pady=(0, 6))

        ctk.CTkButton(
            card,
            text="💾  Salva Spesa",
            height=44,
            corner_radius=10,
            fg_color=PALETTE["accent"],
            hover_color=PALETTE["accent_hover"],
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.submit_manual_expense
        ).pack(fill="x", padx=40, pady=(0, 24))

    def submit_manual_expense(self):
        raw_amt = self.in_amount.get().replace("€", "").replace(",", ".").strip()
        try:
            amount = float(raw_amt)
            if amount <= 0:
                raise ValueError()
        except ValueError:
            self.in_status_lbl.configure(text="⚠️ Inserisci un importo valido maggiore di zero.", text_color=PALETTE["rose"])
            return

        cat_str = self.in_category.get().split()[-1]
        raw_date = self.in_date.get().strip().lower()

        # Riconoscimento intelligente della data (Giorno/Mese/Anno)
        if raw_date in ("oggi", ""):
            iso_date = date.today().strftime("%Y-%m-%d")
        elif raw_date in ("ieri",):
            iso_date = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            iso_date = None
            for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d"):
                try:
                    iso_date = datetime.strptime(raw_date, fmt).strftime("%Y-%m-%d")
                    break
                except ValueError:
                    continue

            if not iso_date:
                self.in_status_lbl.configure(
                    text="⚠️ Data non valida! Usa il formato GG/MM/AAAA (es. 15/10/2026).",
                    text_color=PALETTE["rose"]
                )
                return

        desc = self.in_desc.get().strip()

        self.in_status_lbl.configure(text="⏳ Registrazione su Google Fogli in corso...", text_color=PALETTE["accent"])
        self.update()

        def _worker():
            assigned_id = None
            if get_google_sync_url():
                assigned_id = send_add_to_cloud(amount, cat_str, desc, iso_date)

            tx_id = add_transaction(
                amount=amount,
                category=cat_str,
                description=desc,
                date_str=iso_date,
                source="manuale",
                tx_id=assigned_id
            )

            def _on_done():
                disp_date = datetime.strptime(iso_date, "%Y-%m-%d").strftime("%d/%m/%Y")
                self.in_status_lbl.configure(
                    text=f"✅ Spesa #{tx_id} di {amount:.2f} € salvata con successo ({disp_date})!",
                    text_color=PALETTE["emerald"]
                )
                self.in_amount.delete(0, "end")
                self.in_desc.delete(0, "end")
                self.load_movements_data()
                self.update_dashboard_data()

            self.after(0, _on_done)

        threading.Thread(target=_worker, daemon=True).start()

    # =========================================================================
    # LOGICHE DI AGGIORNAMENTO, PERIODIC CHECK & CONTROLLER TELEGRAM
    # =========================================================================
    def on_period_change(self, _=None):
        self.current_month = int(self.month_combo.get().split("-")[0].strip())
        self.current_year = int(self.year_combo.get())
        self.refresh_all()

    def update_budget(self):
        try:
            val = float(self.budget_entry.get().replace(",", "."))
            if val <= 0:
                raise ValueError()
            self.current_budget = val
            messagebox.showinfo("Budget", f"Budget mensile aggiornato a {val:.2f} €")
            self.update_dashboard_data()
        except ValueError:
            messagebox.showerror("Errore", "Inserisci un importo valido per il budget.")

    def refresh_all(self):
        self.update_dashboard_data()
        self.load_movements_data()
        self.load_plans_data()

    def periodic_check(self):
        """Controlla se dal bot Telegram sono arrivate nuove transazioni e aggiorna la schermata live."""
        try:
            # Controllo automatico spese ricorrenti in scadenza oggi
            process_due_recurring_expenses(send_notification=True)

            summary = get_monthly_summary(self.current_year, self.current_month)
            curr = summary["count"]
            if self.last_tx_count != -1 and curr != self.last_tx_count:
                self.refresh_all()
            self.last_tx_count = curr

            # Auto-sincronizzazione periodica leggera col Cloud ogni 30 secondi se configurato
            self.cloud_sync_tick = getattr(self, "cloud_sync_tick", 0) + 1
            if self.cloud_sync_tick >= 10:
                self.cloud_sync_tick = 0
                if get_google_sync_url():
                    self.trigger_background_cloud_sync()
        except Exception:
            pass
        finally:
            self.after(3000, self.periodic_check)

    def auto_start_bot(self):
        """Avvia il monitoraggio del Bot: se è configurato Google Sheets usa il Webhook 24/7, altrimenti il polling locale."""
        cloud_url = get_google_sync_url()
        cur_token = os.getenv("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN).strip()

        if cloud_url and cur_token and cur_token not in ("tuo_token_qui", "INCOLLA_QUI_IL_TUO_TOKEN", ""):
            # Modalità Cloud 24/7: Telegram comunica direttamente con Google Fogli a PC spento
            self.bot_status_indicator.configure(text="●", text_color=PALETTE["emerald"])
            self.bot_status_sub.configure(text="Attivo Cloud 24/7", text_color=PALETTE["emerald"])
            self.bot_toggle_btn.configure(
                text="☁️ Gestito da Google Fogli",
                fg_color=PALETTE["border"],
                state="disabled"
            )
            # Verifica e ripristina il Webhook in background per garantire funzionamento h24
            threading.Thread(target=set_telegram_webhook, daemon=True).start()
            return

        if cur_token and cur_token not in ("tuo_token_qui", "INCOLLA_QUI_IL_TUO_TOKEN", ""):
            self.start_bot_process()
        else:
            self.bot_status_indicator.configure(text="●", text_color=PALETTE["amber"])
            self.bot_status_sub.configure(text="Token mancante", text_color=PALETTE["amber"])
            self.bot_toggle_btn.configure(
                text="⚙️ Imposta Token",
                fg_color=PALETTE["amber"],
                hover_color="#D97706",
                command=self.open_token_dialog
            )

    def open_token_dialog(self):
        dialog = ctk.CTkInputDialog(
            text="Incolla il Token HTTP ricevuto da @BotFather:\n(es. 7123456789:AAHjKlmNo...)",
            title="Configurazione Token Telegram"
        )
        token = dialog.get_input()
        if token and token.strip():
            self.save_token_to_env(token.strip())

    def save_token_to_env(self, new_token: str):
        env_path = BASE_DIR / ".env"
        lines = []
        if env_path.exists():
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

        token_found = False
        new_lines = []
        for line in lines:
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                new_lines.append(f"TELEGRAM_BOT_TOKEN={new_token}\n")
                token_found = True
            else:
                new_lines.append(line)

        if not token_found:
            new_lines.append(f"TELEGRAM_BOT_TOKEN={new_token}\n")

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        os.environ["TELEGRAM_BOT_TOKEN"] = new_token
        messagebox.showinfo("Configurazione Salvata", "Token salvato con successo in .env!\nAvvio del Bot in corso...")
        self.bot_toggle_btn.configure(
            fg_color=PALETTE["accent"],
            hover_color=PALETTE["accent_hover"],
            command=self.toggle_bot
        )
        self.start_bot_process()

    def toggle_bot(self):
        if self.bot_process and self.bot_process.poll() is None:
            self.stop_bot_process()
        else:
            cur_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
            if not cur_token or cur_token in ("tuo_token_qui", "INCOLLA_QUI_IL_TUO_TOKEN"):
                self.open_token_dialog()
            else:
                self.start_bot_process()

    def start_bot_process(self):
        if self.bot_process and self.bot_process.poll() is None:
            return

        bot_script = BASE_DIR / "bot.py"
        try:
            self.bot_process = subprocess.Popen([sys.executable, str(bot_script)], cwd=str(BASE_DIR))
            self.bot_status_indicator.configure(text="●", text_color=PALETTE["emerald"])
            self.bot_status_sub.configure(text="In ascolto (Polling)", text_color=PALETTE["emerald"])
            self.bot_toggle_btn.configure(
                text="Arresta Bot",
                fg_color=PALETTE["rose"],
                hover_color="#DC2626",
                command=self.toggle_bot
            )
        except Exception as e:
            messagebox.showerror("Errore Avvio Bot", f"Impossibile avviare il bot:\n{e}")

    def stop_bot_process(self):
        if self.bot_process and self.bot_process.poll() is None:
            self.bot_process.terminate()
            try:
                self.bot_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.bot_process.kill()
        self.bot_process = None
        self.bot_status_indicator.configure(text="●", text_color=PALETTE["rose"])
        self.bot_status_sub.configure(text="Bot arrestato", text_color=PALETTE["text_muted"])
        self.bot_toggle_btn.configure(
            text="Avvia Bot",
            fg_color=PALETTE["accent"],
            hover_color=PALETTE["accent_hover"],
            command=self.toggle_bot
        )

    # =========================================================================
    # SINCRONIZZAZIONE GOOGLE FOGLI & CLOUD
    # =========================================================================
    def trigger_background_cloud_sync(self):
        """Avvia la sincronizzazione con Google Fogli in un thread separato non bloccante."""
        if getattr(self, "cloud_syncing", False):
            return

        url = get_google_sync_url()
        if not url:
            self.cloud_status_indicator.configure(text="●", text_color=PALETTE["amber"])
            self.cloud_status_sub.configure(text="URL non configurato", text_color=PALETTE["text_muted"])
            return

        self.cloud_syncing = True
        self.cloud_status_indicator.configure(text="●", text_color=PALETTE["accent"])
        self.cloud_status_sub.configure(text="Sincronizzazione...", text_color=PALETTE["accent"])
        self.cloud_sync_btn.configure(state="disabled", text="⏳ In corso...")

        def _worker():
            res = sync_with_google_sheets()
            self.after(0, lambda: self._on_cloud_sync_done(res))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_cloud_sync_done(self, res: dict):
        self.cloud_syncing = False
        self.cloud_sync_btn.configure(state="normal", text="☁️  Sincronizza Ora")

        if res.get("success"):
            self.cloud_status_indicator.configure(text="●", text_color=PALETTE["emerald"])
            imported = res.get("imported", 0)
            updated = res.get("updated", 0)
            if imported > 0 or updated > 0:
                parts = []
                if imported > 0:
                    parts.append(f"+{imported} nuove")
                if updated > 0:
                    parts.append(f"{updated} modificate")
                self.cloud_status_sub.configure(
                    text=f"Sync: {', '.join(parts)}",
                    text_color=PALETTE["emerald"]
                )
                self.refresh_all()
            else:
                self.cloud_status_sub.configure(
                    text="Dati allineati al 100%",
                    text_color=PALETTE["emerald"]
                )
        else:
            self.cloud_status_indicator.configure(text="●", text_color=PALETTE["rose"])
            err_msg = res.get("error", "Errore")
            self.cloud_status_sub.configure(
                text="Errore connessione",
                text_color=PALETTE["rose"]
            )

    def push_past_expenses_to_cloud(self):
        """Invia tutte le spese registrate nel database locale verso il Foglio Google."""
        url = get_google_sync_url()
        if not url:
            messagebox.showwarning("Attenzione", "Devi prima impostare l'URL di Google Apps Script!")
            return

        def _worker():
            res = push_all_local_to_cloud()
            if res.get("success"):
                self.after(0, lambda: messagebox.showinfo(
                    "Sincronizzazione Riuscita",
                    f"✅ {res.get('message', 'Tutte le spese passate sono state caricate sul Foglio Google!')}"
                ))
            else:
                self.after(0, lambda: messagebox.showerror(
                    "Errore Sincronizzazione",
                    f"❌ {res.get('error', 'Impossibile inviare le spese al foglio Google.')}"
                ))

        threading.Thread(target=_worker, daemon=True).start()

    def open_cloud_sync_dialog(self):
        """Finestra modale moderna per configurare il Google Foglio, Webhook e invio spese passate."""
        dlg = ctk.CTkToplevel(self)
        dlg.title("Configurazione Google Fogli & Cloud (0 € h24)")
        dlg.geometry("620x560")
        dlg.resizable(False, False)
        dlg.grab_set()

        # Posiziona al centro
        dlg.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 620) // 2
        y = self.winfo_y() + (self.winfo_height() - 560) // 2
        dlg.geometry(f"+{x}+{y}")
        dlg.configure(fg_color=PALETTE["bg_root"])

        ctk.CTkLabel(
            dlg,
            text="☁️  Sincronizzazione Google Fogli / Drive",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=PALETTE["text_primary"]
        ).pack(padx=24, pady=(16, 4), anchor="w")

        info_txt = (
            "Permette al tuo bot Telegram di funzionare 24/7 dal telefono a PC spento.\n"
            "Tutte le spese inviate da smartphone vengono scritte nel tuo Google Foglio,\n"
            "e l'app le sincronizza automaticamente sul tuo computer a costo zero."
        )
        ctk.CTkLabel(
            dlg,
            text=info_txt,
            font=ctk.CTkFont(size=12),
            text_color=PALETTE["text_muted"],
            justify="left"
        ).pack(padx=24, pady=(0, 12), anchor="w")

        card = ctk.CTkFrame(dlg, corner_radius=12, fg_color=PALETTE["bg_card"], border_width=1, border_color=PALETTE["border"])
        card.pack(fill="both", expand=True, padx=24, pady=(0, 14))

        ctk.CTkLabel(
            card,
            text="URL Applicazione Web Apps Script (che finisce per /exec):",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=PALETTE["text_primary"]
        ).pack(padx=16, pady=(14, 4), anchor="w")

        current_url = get_google_sync_url()
        url_entry = ctk.CTkEntry(
            card,
            placeholder_text="https://script.google.com/macros/s/.../exec",
            height=36,
            corner_radius=8,
            fg_color=PALETTE["bg_card_inner"],
            border_color=PALETTE["border"],
            text_color=PALETTE["text_primary"]
        )
        url_entry.insert(0, current_url)
        url_entry.pack(fill="x", padx=16, pady=(0, 8))

        status_lbl = ctk.CTkLabel(card, text="", font=ctk.CTkFont(size=11, weight="bold"), wraplength=550, justify="left")
        status_lbl.pack(padx=16, pady=(0, 8), anchor="w")

        def _save_url():
            u = url_entry.get().strip()
            if save_google_sync_url(u):
                status_lbl.configure(text="✅ URL salvato correttamente in .env!", text_color=PALETTE["emerald"])
                has_cloud = bool(u)
                self.cloud_status_indicator.configure(text="●", text_color=PALETTE["emerald"] if has_cloud else PALETTE["amber"])
                self.cloud_status_sub.configure(text="Pronto alla sincro" if has_cloud else "URL non impostato", text_color=PALETTE["emerald"] if has_cloud else PALETTE["text_muted"])
            else:
                status_lbl.configure(text="❌ Impossibile salvare il file .env.", text_color=PALETTE["rose"])

        def _test_sync():
            _save_url()
            status_lbl.configure(text="⏳ Connessione a Google in corso...", text_color=PALETTE["accent"])
            dlg.update()
            res = sync_with_google_sheets()
            if res.get("success"):
                status_lbl.configure(
                    text=f"✅ Connessione riuscita! Scaricate {res.get('imported', 0)} spese da Google.",
                    text_color=PALETTE["emerald"]
                )
                self.refresh_all()
            else:
                status_lbl.configure(
                    text=f"❌ Errore: {res.get('error', 'Verifica URL e permessi')}",
                    text_color=PALETTE["rose"]
                )

        def _push_past():
            _save_url()
            status_lbl.configure(text="⏳ Invio di tutte le spese passate al Foglio Google...", text_color=PALETTE["accent"])
            dlg.update()
            res = push_all_local_to_cloud()
            if res.get("success"):
                status_lbl.configure(
                    text=f"✅ {res.get('message', 'Spese passate caricate sul Foglio!')}",
                    text_color=PALETTE["emerald"]
                )
            else:
                status_lbl.configure(
                    text=f"❌ Errore invio spese: {res.get('error', 'Verifica permessi Google')}",
                    text_color=PALETTE["rose"]
                )

        def _activate_webhook():
            _save_url()
            status_lbl.configure(text="⏳ Configurazione Webhook Telegram...", text_color=PALETTE["accent"])
            dlg.update()
            wh_res = set_telegram_webhook()
            if wh_res.get("success"):
                status_lbl.configure(
                    text="✅ Webhook collegato con successo! Telegram invierà i messaggi a Google Fogli h24.",
                    text_color=PALETTE["emerald"]
                )
            else:
                status_lbl.configure(
                    text=f"❌ Errore Webhook: {wh_res.get('error', 'Token o URL errato')}",
                    text_color=PALETTE["rose"]
                )

        def _diagnose():
            _save_url()
            status_lbl.configure(text="⏳ Diagnosi in corso...", text_color=PALETTE["accent"])
            dlg.update()
            diag = check_cloud_diagnostics()
            msg = diag.get("message", "")
            if diag.get("script_auth_error"):
                status_lbl.configure(text=msg, text_color=PALETTE["rose"])
            elif diag.get("script_accessible"):
                status_lbl.configure(text=msg, text_color=PALETTE["emerald"])
            else:
                status_lbl.configure(text=msg, text_color=PALETTE["amber"])

        # Riga 1 Pulsanti: Salva e Testa
        r1 = ctk.CTkFrame(card, fg_color="transparent")
        r1.pack(fill="x", padx=16, pady=(0, 6))

        ctk.CTkButton(
            r1,
            text="💾 Salva URL",
            height=32,
            corner_radius=8,
            fg_color=PALETTE["accent"],
            hover_color=PALETTE["accent_hover"],
            font=ctk.CTkFont(size=12, weight="bold"),
            command=_save_url
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            r1,
            text="⚡ Scarica Spese dal Foglio",
            height=32,
            corner_radius=8,
            fg_color=PALETTE["violet"],
            hover_color="#7C3AED",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=_test_sync
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            r1,
            text="🔍 Diagnosi Collegamento",
            height=32,
            corner_radius=8,
            fg_color=PALETTE["bg_card_inner"],
            hover_color=PALETTE["border"],
            border_width=1,
            border_color=PALETTE["border"],
            font=ctk.CTkFont(size=11),
            command=_diagnose
        ).pack(side="left")

        # Riga 2 Pulsanti: Invia passate e Attiva Webhook
        r2 = ctk.CTkFrame(card, fg_color="transparent")
        r2.pack(fill="x", padx=16, pady=(6, 12))

        ctk.CTkButton(
            r2,
            text="⬆️  Carica Tutte le Spese Passate sul Foglio Google",
            height=34,
            corner_radius=8,
            fg_color=PALETTE["emerald"],
            hover_color="#059669",
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=_push_past
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            r2,
            text="🔗 Collega Telegram a Google (1 Clic)",
            height=34,
            corner_radius=8,
            fg_color=PALETTE["accent"],
            hover_color=PALETTE["accent_hover"],
            text_color="#0F172A",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=_activate_webhook
        ).pack(side="left")

        def _open_script_file():
            script_path = BASE_DIR / "google_apps_script.js"
            if script_path.exists():
                try:
                    os.startfile(str(script_path))
                except Exception:
                    messagebox.showinfo("Script Google", f"Il codice da incollare si trova in:\n{script_path}")

        ctk.CTkButton(
            dlg,
            text="📄 Apri File con il Codice di Google Apps Script (google_apps_script.js)",
            height=30,
            corner_radius=8,
            fg_color="transparent",
            hover_color=PALETTE["bg_card"],
            text_color=PALETTE["accent"],
            font=ctk.CTkFont(size=11),
            command=_open_script_file
        ).pack(pady=(0, 12))

    def on_closing(self):
        self.stop_bot_process()
        cloud_url = get_google_sync_url()
        if cloud_url:
            try:
                set_telegram_webhook(cloud_url)
            except Exception:
                pass
        self.destroy()


def main():
    app = ContabileApp()
    app.mainloop()


if __name__ == "__main__":
    main()
