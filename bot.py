"""
Bot Telegram per la registrazione rapida delle spese personali.
Usa python-telegram-bot in modalità long-polling asincrona.
"""
import logging
from datetime import datetime
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import (
    TELEGRAM_BOT_TOKEN,
    AUTHORIZED_USER_ID,
    CATEGORIES,
    CATEGORIES_LOOKUP,
    CATEGORY_ICONS,
    MONTHLY_BUDGET,
)
from database import (
    init_db,
    add_transaction,
    delete_transaction,
    get_monthly_summary,
    get_recent_transactions,
    get_recurring_expenses_list,
    get_recurring_breakdown_totals,
    process_due_recurring_expenses,
    add_recurring_expense,
)

# Configurazione logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def is_authorized(user_id: int) -> bool:
    """Verifica se l'utente che invia il messaggio è autorizzato."""
    if AUTHORIZED_USER_ID is None:
        return False
    return user_id == AUTHORIZED_USER_ID


def format_categories_help() -> str:
    """Genera la lista formattata delle categorie con relative emoji."""
    return "\n".join([f"• {CATEGORY_ICONS.get(cat, '🏷️')} *{cat}*" for cat in CATEGORIES])


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce il comando /start."""
    user = update.effective_user
    if not is_authorized(user.id):
        await update.message.reply_text(
            f"⛔ *Accesso non autorizzato!*\n\n"
            f"Il tuo Telegram User ID è: `{user.id}`\n\n"
            f"Inserisci questo valore in `TELEGRAM_USER_ID` nel tuo file `.env` per abilitare l'accesso.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    msg = (
        f"👋 Ciao *{user.first_name}*!\n\n"
        f"Benvenuto nel tuo assistente per il tracciamento delle spese personali.\n\n"
        f"📝 *Come registrare una spesa:*\n"
        f"Invia un messaggio nel formato:\n"
        f"`importo, categoria, descrizione`\n\n"
        f"*Esempio:*\n"
        f"`15.50, Alimentari, Spesa supermercato`\n"
        f"`8, Trasporti, Biglietto treno`\n\n"
        f"💡 *Digita /comandi per vedere l'elenco completo delle funzionalità!*"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def comandi_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra l'elenco completo dei comandi disponibili (/comandi o /commands)."""
    user = update.effective_user
    if not is_authorized(user.id):
        return

    msg = (
        "🤖 *ELENCO COMPLETO DEI COMANDI DISPONIBILI*\n\n"
        "📝 *REGISTRAZIONE SPESE VELOCI*\n"
        "• Invia: `<importo>, <categoria>, <descrizione>`\n"
        "  _Es: 15.50, Alimentari, Spesa Coop_\n"
        "• Oppure con testo descrittivo libero\n\n"
        "📊 *DATI AGGREGATI & STATISTICHE GLOBALI*\n"
        "• `/budget` o `/stats`: Totale speso nel mese, budget residuo e progress bar\n"
        "• `/ultime` o `/last`: Mostra le ultime 5 spese salvate con ID\n\n"
        "🔁 *GESTIONE GUIDATA RATE & ABBONAMENTI*\n"
        "• `/nuovoabbonamento`: Procedura a step per aggiungere un abbonamento continuo (Netflix, Palestra, ecc.)\n"
        "• `/nuovarata`: Procedura a step per aggiungere un finanziamento (con rate totali e pagate)\n"
        "• `/piani` o `/abbonamenti`: Elenco di tutti gli abbonamenti e le rate attive\n"
        "• `/annulla`: Interrompe la procedura guidata in qualsiasi momento\n\n"
        "🗑️ *CANCELLAZIONE & CORREZIONE*\n"
        "• `/elimina` o `/delete`: Cancella l'ultima spesa inserita\n"
        "• `/elimina <ID>`: Cancella una spesa specifica per ID (es. `/elimina 42`)\n\n"
        "💡 _Tutti i dati sono sempre salvati e sincronizzati anche col Foglio Google!_"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce il comando /help delegando a /comandi."""
    await comandi_command(update, context)


async def budget_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce il comando /budget e /stats."""
    user = update.effective_user
    if not is_authorized(user.id):
        return

    now = datetime.now()
    summary = get_monthly_summary(now.year, now.month)
    total = summary["total"]
    remaining = MONTHLY_BUDGET - total
    percent = (total / MONTHLY_BUDGET * 100) if MONTHLY_BUDGET > 0 else 0

    status_icon = "🟢" if total <= MONTHLY_BUDGET else "🔴"
    progress_bar = "▓" * min(int(percent / 10), 10) + "░" * max(0, 10 - int(percent / 10))

    breakdown = get_recurring_breakdown_totals()

    msg = (
        f"📊 *Riepilogo Spese - {now.strftime('%B %Y')}*\n\n"
        f"💰 *Speso:* `{total:.2f} €`\n"
        f"🎯 *Budget:* `{MONTHLY_BUDGET:.2f} €`\n"
        f"{status_icon} *Residuo:* `{remaining:.2f} €` ({percent:.1f}%)\n"
        f"Progresso: `[{progress_bar}]`\n\n"
        f"💼 *Impegni Fissi Mensili (Piani):*\n"
        f"• 🔁 Abbonamenti: `{breakdown['abbonamenti_totale']:.2f} €/mese`\n"
        f"• ⏳ Rate in corso: `{breakdown['rate_totale']:.2f} €/mese`\n"
        f"• *Totale Fisse:* `{breakdown['totale_fisse']:.2f} €/mese`\n\n"
        f"🔢 *Transazioni totali:* {summary['count']}\n"
        f"📈 *Spesa media:* `{summary['average']:.2f} €`\n"
        f"🔝 *Spesa massima:* `{summary['max_expense']:.2f} €`"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def last_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce il comando /last e /ultime per mostrare le ultime spese."""
    user = update.effective_user
    if not is_authorized(user.id):
        return

    recent = get_recent_transactions(limit=5)
    if not recent:
        await update.message.reply_text("Nessuna spesa registrata finora.")
        return

    lines = ["🕒 *Ultime 5 spese registrate:*\n"]
    for item in recent:
        icon = CATEGORY_ICONS.get(item["category"], "🏷️")
        desc = f" - _{item['description']}_" if item["description"] else ""
        lines.append(
            f"• `[ID {item['id']}]` {icon} *{item['amount']:.2f} €* ({item['category']}){desc} | 📅 {item['date']}"
        )

    lines.append("\nPer cancellare una voce usa `/elimina <ID>` oppure `/elimina`")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestisce il comando /delete ed /elimina (<ID> opzionale)."""
    user = update.effective_user
    if not is_authorized(user.id):
        return

    args = context.args
    target_id = None
    if args and args[0].isdigit():
        target_id = int(args[0])
    else:
        recent = get_recent_transactions(limit=1)
        if not recent:
            await update.message.reply_text("ℹ️ Nessuna spesa registrata da eliminare.")
            return
        target_id = recent[0]["id"]

    success = delete_transaction(target_id)
    if success:
        await update.message.reply_text(
            f"🗑️ Transazione `#{target_id}` eliminata con successo.",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(
            f"❌ Nessuna transazione trovata con ID `#{target_id}`.",
            parse_mode=ParseMode.MARKDOWN
        )


async def nuovoabbonamento_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Avvia la procedura guidata per registrare un nuovo abbonamento."""
    user = update.effective_user
    if not is_authorized(user.id):
        return

    context.user_data.clear()
    context.user_data["wizard"] = "abbonamento"
    context.user_data["step"] = 1

    msg = (
        "🔁 *CONFIGURAZIONE NUOVO ABBONAMENTO (Passo 1 di 4)*\n\n"
        "Qual è il *nome del servizio* o abbonamento?\n"
        "_(es. Netflix, Spotify, Palestra, Fibra Casa...)_\n\n"
        "👉 _Scrivi /annulla per interrompere in qualsiasi momento._"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def nuovarata_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Avvia la procedura guidata per registrare un nuovo piano rateale."""
    user = update.effective_user
    if not is_authorized(user.id):
        return

    context.user_data.clear()
    context.user_data["wizard"] = "rata"
    context.user_data["step"] = 1

    msg = (
        "⏳ *CONFIGURAZIONE NUOVO PIANO RATEALE (Passo 1 di 6)*\n\n"
        "Qual è il *titolo o descrizione* del finanziamento/acquisto a rate?\n"
        "_(es. Finanziamento Auto, Smartphone a rate, Elettrodomestico...)_\n\n"
        "👉 _Scrivi /annulla per interrompere in qualsiasi momento._"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def annulla_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Interrompe qualsiasi procedura guidata in corso."""
    user = update.effective_user
    if not is_authorized(user.id):
        return

    if context.user_data.get("wizard"):
        context.user_data.clear()
        await update.message.reply_text(
            "🛑 *Procedura guidata annullata.* Nessun piano è stato registrato.",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(
            "ℹ️ Nessuna procedura guidata in corso.",
            parse_mode=ParseMode.MARKDOWN
        )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Riceve i messaggi di testo e gestisce:
    1. I passi sequenziali delle procedure guidate (/nuovoabbonamento, /nuovarata).
    2. La registrazione classica di una spesa (importo, categoria, descrizione).
    """
    user = update.effective_user
    if not is_authorized(user.id):
        await update.message.reply_text(
            f"⛔ *Accesso non autorizzato!*\n"
            f"ID Telegram: `{user.id}`\n"
            f"Inseriscilo in `.env` come `TELEGRAM_USER_ID`.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    text = update.message.text.strip()

    # =========================================================================
    # GESTIONE WIZARD ABBONAMENTO
    # =========================================================================
    if context.user_data.get("wizard") == "abbonamento":
        step = context.user_data.get("step", 1)
        if step == 1:
            context.user_data["name"] = text
            context.user_data["step"] = 2
            await update.message.reply_text(
                f"💰 *(Passo 2 di 4)*\n\nInserisci l'importo mensile in Euro per *{text}*:\n_(es. 12.99 oppure 15)_",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        if step == 2:
            raw_amt = text.replace("€", "").replace(",", ".").strip()
            try:
                amt = float(raw_amt)
                if amt <= 0:
                    raise ValueError()
            except ValueError:
                await update.message.reply_text("⚠️ _Inserisci un importo valido maggiore di zero (es. 12.99):_", parse_mode=ParseMode.MARKDOWN)
                return
            context.user_data["amount"] = amt
            context.user_data["step"] = 3
            await update.message.reply_text(
                "📅 *(Passo 3 di 4)*\n\nIn quale *giorno del mese* viene effettuato l'addebito?\n_(inserisci un numero da 1 a 31)_",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        if step == 3:
            try:
                day = int(text.strip())
                if not (1 <= day <= 31):
                    raise ValueError()
            except ValueError:
                await update.message.reply_text("⚠️ _Inserisci un giorno valido tra 1 e 31:_", parse_mode=ParseMode.MARKDOWN)
                return
            context.user_data["day"] = day
            context.user_data["step"] = 4
            await update.message.reply_text(
                f"🏷️ *(Passo 4 di 4)*\n\nScegli la *categoria* dell'abbonamento tra quelle disponibili:\n\n{format_categories_help()}",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        if step == 4:
            cat_raw = text.strip().lower()
            cat = CATEGORIES_LOOKUP.get(cat_raw, "Altro")
            name = context.user_data["name"]
            amt = context.user_data["amount"]
            day = context.user_data["day"]
            now_iso = datetime.now().strftime("%Y-%m-%d")

            plan_id = add_recurring_expense(
                tipo="abbonamento",
                nome_descrizione=name,
                importo=amt,
                categoria=cat,
                giorno_addebito=day,
                data_inizio=now_iso,
                stato="attivo"
            )
            context.user_data.clear()

            icon = CATEGORY_ICONS.get(cat, "🏷️")
            ok_msg = (
                f"✅ *ABBONAMENTO CREATO CON SUCCESSO!*\n\n"
                f"🔢 *ID:* `#{plan_id}`\n"
                f"🔁 *Nome:* *{name}*\n"
                f"💶 *Importo:* `{amt:.2f} € / mese`\n"
                f"📅 *Giorno Addebito:* ogni {day} del mese\n"
                f"{icon} *Categoria:* {cat}\n\n"
                f"_Memorizzato e attivo nel sistema!_"
            )
            await update.message.reply_text(ok_msg, parse_mode=ParseMode.MARKDOWN)
            return

    # =========================================================================
    # GESTIONE WIZARD RATA
    # =========================================================================
    if context.user_data.get("wizard") == "rata":
        step = context.user_data.get("step", 1)
        if step == 1:
            context.user_data["name"] = text
            context.user_data["step"] = 2
            await update.message.reply_text(
                f"💰 *(Passo 2 di 6)*\n\nInserisci l'importo della *singola rata mensile* in Euro:\n_(es. 150 oppure 49.90)_",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        if step == 2:
            raw_amt = text.replace("€", "").replace(",", ".").strip()
            try:
                amt = float(raw_amt)
                if amt <= 0:
                    raise ValueError()
            except ValueError:
                await update.message.reply_text("⚠️ _Inserisci un importo valido maggiore di zero (es. 150):_", parse_mode=ParseMode.MARKDOWN)
                return
            context.user_data["amount"] = amt
            context.user_data["step"] = 3
            await update.message.reply_text(
                f"🏷️ *(Passo 3 di 6)*\n\nScegli la *categoria* per questa spesa rateale:\n\n{format_categories_help()}",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        if step == 3:
            cat_raw = text.strip().lower()
            cat = CATEGORIES_LOOKUP.get(cat_raw, "Altro")
            context.user_data["category"] = cat
            context.user_data["step"] = 4
            await update.message.reply_text(
                "📅 *(Passo 4 di 6)*\n\nIn quale *giorno del mese* scade la rata?\n_(inserisci un numero da 1 a 31)_",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        if step == 4:
            try:
                day = int(text.strip())
                if not (1 <= day <= 31):
                    raise ValueError()
            except ValueError:
                await update.message.reply_text("⚠️ _Inserisci un giorno valido tra 1 e 31:_", parse_mode=ParseMode.MARKDOWN)
                return
            context.user_data["day"] = day
            context.user_data["step"] = 5
            await update.message.reply_text(
                "🔢 *(Passo 5 di 6)*\n\nQuante sono le *rate totali* previste dal finanziamento?\n_(es. 12, 24, 36, 48)_",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        if step == 5:
            try:
                tot_rate = int(text.strip())
                if tot_rate <= 0:
                    raise ValueError()
            except ValueError:
                await update.message.reply_text("⚠️ _Inserisci un numero di rate intero positivo (es. 12):_", parse_mode=ParseMode.MARKDOWN)
                return
            context.user_data["totRate"] = tot_rate
            context.user_data["step"] = 6
            await update.message.reply_text(
                "⏳ *(Passo 6 di 6)*\n\nQuante rate hai *già pagato* finora?\n_(scrivi 0 se inizi a pagare adesso, oppure es. 4 se ne hai già pagate 4)_",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        if step == 6:
            try:
                pagate = int(text.strip())
                if pagate < 0:
                    raise ValueError()
            except ValueError:
                await update.message.reply_text("⚠️ _Inserisci un numero intero maggiore o uguale a 0:_", parse_mode=ParseMode.MARKDOWN)
                return

            name = context.user_data["name"]
            amt = context.user_data["amount"]
            cat = context.user_data["category"]
            day = context.user_data["day"]
            tot_rate = context.user_data["totRate"]
            now_iso = datetime.now().strftime("%Y-%m-%d")
            stato = "completato" if pagate >= tot_rate else "attivo"

            plan_id = add_recurring_expense(
                tipo="rata",
                nome_descrizione=name,
                importo=amt,
                categoria=cat,
                giorno_addebito=day,
                numero_rate_totali=tot_rate,
                rate_pagate=pagate,
                data_inizio=now_iso,
                stato=stato
            )
            context.user_data.clear()

            pct = round((pagate / tot_rate) * 100) if tot_rate > 0 else 0
            ok_msg = (
                f"✅ *PIANO RATEALE CREATO CON SUCCESSO!*\n\n"
                f"🔢 *ID:* `#{plan_id}`\n"
                f"⏳ *Finanziamento:* *{name}*\n"
                f"💶 *Importo Rata:* `{amt:.2f} € / mese`\n"
                f"📅 *Giorno Addebito:* ogni {day} del mese\n"
                f"📊 *Avanzamento:* {pagate}/{tot_rate} rate pagate ({pct}%)\n"
                f"🏷️ *Categoria:* {cat}\n\n"
                f"_Memorizzato e attivo nel sistema!_"
            )
            await update.message.reply_text(ok_msg, parse_mode=ParseMode.MARKDOWN)
            return

    # =========================================================================
    # INSERIMENTO SPESA STANDARD (importo, categoria, descrizione)
    # =========================================================================
    parts = [p.strip() for p in text.split(",")]

    if len(parts) < 2:
        await update.message.reply_text(
            "⚠️ *Formato non valido!*\n\n"
            "Il messaggio deve contenere almeno *importo* e *categoria*, separati da virgola:\n"
            "`importo, categoria, descrizione opzionale`\n\n"
            "*Esempio:*\n"
            "`15.50, Alimentari, Spesa al supermercato`\n\n"
            "Oppure usa i comandi guidati come `/nuovoabbonamento` o `/nuovarata`.\n"
            "Digita `/comandi` per la lista completa.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # 1. Validazione Importo
    raw_amount = parts[0].replace("€", "").replace(",", ".").strip()
    try:
        amount = float(raw_amount)
        if amount <= 0:
            raise ValueError("L'importo deve essere positivo")
    except ValueError:
        await update.message.reply_text(
            f"⚠️ *Importo non valido:* `{parts[0]}`\n"
            "L'importo deve essere un numero positivo (es. `15.50` o `15,50`).",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # 2. Validazione Categoria
    raw_category = parts[1].strip().lower()
    if raw_category not in CATEGORIES_LOOKUP:
        await update.message.reply_text(
            f"⚠️ *Categoria non riconosciuta:* `{parts[1]}`\n\n"
            f"📂 *Le categorie ammesse sono esclusivamente:*\n"
            f"{format_categories_help()}\n\n"
            "Riprova ad inviare la spesa con una di queste categorie.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    category = CATEGORIES_LOOKUP[raw_category]

    # 3. Descrizione (opzionale)
    description = ", ".join(parts[2:]).strip() if len(parts) > 2 else ""

    # 4. Salvataggio su Database
    try:
        tx_id = add_transaction(
            amount=amount,
            category=category,
            description=description,
            source="bot"
        )
    except Exception as e:
        logger.error(f"Errore salvataggio database: {e}")
        await update.message.reply_text(
            "❌ Errore durante il salvataggio nel database locale. Controlla i log."
        )
        return

    # 5. Calcolo metriche aggiornate per feedback istantaneo
    now = datetime.now()
    summary = get_monthly_summary(now.year, now.month)
    icon = CATEGORY_ICONS.get(category, "🏷️")
    desc_str = f" - _{description}_" if description else ""

    total = summary["total"]
    remaining = MONTHLY_BUDGET - total
    status_icon = "🟢" if total <= MONTHLY_BUDGET else "🔴"

    reply = (
        f"✅ *Spesa registrata con successo!*\n\n"
        f"🔖 `ID #{tx_id}` | {icon} *{category}*\n"
        f"💶 *Importo:* `{amount:.2f} €`{desc_str}\n"
        f"📅 *Data:* `{now.strftime('%d/%m/%Y %H:%M')}`\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📊 *Situazione Mese:* `{total:.2f} €` spesi su `{MONTHLY_BUDGET:.2f} €`\n"
        f"{status_icon} *Budget residuo:* `{remaining:.2f} €`"
    )
    await update.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN)


async def recurring_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra l'elenco delle uscite periodiche differenziando tra Abbonamenti e Rate (/piani)."""
    user = update.effective_user
    if not is_authorized(user.id):
        return

    items = get_recurring_expenses_list()
    if not items:
        await update.message.reply_text(
            "ℹ️ Nessuna spesa periodica (abbonamento o rata) registrata.\n"
            "Usa `/nuovoabbonamento` o `/nuovarata` per crearne una!",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    breakdown = get_recurring_breakdown_totals()
    lines = ["📊 *Uscite Periodiche Programmate (Piani):*\n"]

    # 1. Sezione Abbonamenti a durata indeterminata
    abbonamenti = [i for i in items if i["tipo"] == "abbonamento"]
    if abbonamenti:
        lines.append("🔁 *Abbonamenti (Durata Indeterminata):*")
        for item in abbonamenti:
            status = "🟢" if item["stato"] == "attivo" else "⏸️"
            icon = CATEGORY_ICONS.get(item["categoria"], "🏷️")
            billed = f" | Addebitato: {item['ultimo_mese_addebitato']}" if item.get("ultimo_mese_addebitato") else ""
            lines.append(
                f"{status} `[#{item['id']}]` *{item['nome_descrizione']}*\n"
                f"   {icon} {item['categoria']} • `{item['importo']:.2f} €/mese` (Giorno {item['giorno_addebito']}){billed}"
            )
        lines.append("")

    # 2. Sezione Rate a durata determinata
    rate = [i for i in items if i["tipo"] == "rata"]
    if rate:
        lines.append("⏳ *Piani di Rateizzazione (Durata Determinata):*")
        for item in rate:
            if item["stato"] == "completato":
                status = "✅ (Completata)"
            elif item["stato"] == "attivo":
                status = "🟢"
            else:
                status = "⏸️"
            icon = CATEGORY_ICONS.get(item["categoria"], "🏷️")
            tot_r = item["numero_rate_totali"] or "?"
            pag = item["rate_pagate"]
            lines.append(
                f"{status} `[#{item['id']}]` *{item['nome_descrizione']}*\n"
                f"   {icon} {item['categoria']} • `{item['importo']:.2f} €` (Rata *{pag}/{tot_r}*, Giorno {item['giorno_addebito']})"
            )
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━")
    lines.append(f"📱 Quota Abbonamenti: `{breakdown['abbonamenti_totale']:.2f} €`")
    lines.append(f"⏳ Quota Rate: `{breakdown['rate_totale']:.2f} €`")
    lines.append(f"💰 *Totale Uscite Fisse Mese:* `{breakdown['totale_fisse']:.2f} €`")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


def start_recurring_checker():
    """Avvia un worker in background che controlla le spese ricorrenti ogni ora."""
    import threading
    import time

    def worker():
        time.sleep(5)
        while True:
            try:
                processed = process_due_recurring_expenses(send_notification=True)
                if processed:
                    logger.info(f"Processate {len(processed)} spese ricorrenti automatiche.")
            except Exception as e:
                logger.error(f"Errore controllo spese ricorrenti: {e}")
            time.sleep(3600)

    t = threading.Thread(target=worker, daemon=True, name="RecurringExpensesWorker")
    t.start()


def build_bot_app():
    """Costruisce e configura l'applicazione Telegram Bot con tutti i comandi."""
    if not TELEGRAM_BOT_TOKEN:
        return None

    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler(["start"], start_command))
    application.add_handler(CommandHandler(["comandi", "command", "commands"], comandi_command))
    application.add_handler(CommandHandler(["help"], help_command))
    application.add_handler(CommandHandler(["budget", "stats", "totale", "mese"], budget_command))
    application.add_handler(CommandHandler(["last", "ultime"], last_command))
    application.add_handler(CommandHandler(["delete", "elimina", "cancella"], delete_command))
    application.add_handler(CommandHandler(["piani", "recurring", "abbonamenti", "rate"], recurring_command))
    application.add_handler(CommandHandler(["nuovoabbonamento", "abbonamento"], nuovoabbonamento_command))
    application.add_handler(CommandHandler(["nuovarata", "rata"], nuovarata_command))
    application.add_handler(CommandHandler(["annulla", "stop"], annulla_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return application


def main():
    """Punto di ingresso principale per l'esecuzione del Bot Telegram."""
    if not TELEGRAM_BOT_TOKEN:
        print("\n❌ ERRORE CRITICO: Variabile TELEGRAM_BOT_TOKEN non configurata.")
        print("Configura il file .env con il token fornito da @BotFather.\n")
        return

    init_db()
    print("==================================================")
    print("🤖 Avvio del Bot Telegram Gestione Spese...")
    if AUTHORIZED_USER_ID:
        print(f"🔒 Filtro sicurezza attivo per User ID: {AUTHORIZED_USER_ID}")
    else:
        print("⚠️ Nessun TELEGRAM_USER_ID impostato: scrivi /start al bot per ottenere il tuo ID!")
    print("📡 In ascolto in modalità Long-Polling...")
    print("==================================================")

    # Avvio worker per gli addebiti ricorrenti
    start_recurring_checker()

    application = build_bot_app()
    application.run_polling()


if __name__ == "__main__":
    main()
