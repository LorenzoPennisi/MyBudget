# 💰 MyBudget (Contabile)

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![UI Framework](https://img.shields.io/badge/GUI-CustomTkinter-blueviolet.svg)](https://github.com/TomSchimansky/CustomTkinter)
[![Database](https://img.shields.io/badge/Database-SQLite%20(WAL)-003B57.svg)](https://sqlite.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**MyBudget** is a lightweight, offline-first personal finance application designed to streamline expense tracking and budget management.

Its standout feature is direct integration with a **Telegram Bot** and **Google Sheets**, enabling instant, 24/7 expense logging on the go. For the fastest experience, pair it with an **iOS Shortcut** to record expenses in seconds with a single tap, a home screen widget, or via Siri.

---

## ✨ Key Features

- 🖥️ **Modern Desktop Dashboard:**
  - Built with **CustomTkinter** in Dark Mode with responsive and resizable layouts.
  - Interactive **Matplotlib** visualizations: category breakdown pie charts, monthly burn rates, and daily trend analyses.
  - Full CRUD transaction table with search, category filtering, and in-place editing.
- 📱 **Effortless Mobile Tracking (Telegram Bot):**
  - Log expenses anytime, anywhere by simply texting your private bot: `15.50, Alimentari, Spesa al supermercato`.
  - Works **24/7 without needing your PC to stay on** thanks to a serverless Google Apps Script webhook.
- 📲 **iOS Shortcut Integration:**
  - Fast logging via Siri or an iOS Action Button/Home Widget that formats and forwards input directly to the bot.
- 🔄 **True Two-Way Google Sheets Sync:**
  - Seamless bidirectional synchronization with strict **1:1 ID parity** between Google Sheets rows and the local SQLite database.
  - Edits or deletions made on the desktop app immediately reflect in the cloud, and vice versa.
- ⏳ **Installment Plans & Subscriptions:**
  - Differentiates between open-ended subscriptions (e.g., Netflix, Gym) and fixed-term installment plans (e.g., 10 of 24 installments paid).
  - Automated due-date processing with payment tracking and Telegram notification alerts.
- 📦 **100% Portable:**
  - Can be bundled into a standalone Windows `.exe` requiring zero external dependencies, runtimes, or Python installation.

---

## 🏗️ Project Architecture

```text
contabile/
├── desktop_app.py        # Native Desktop Application (CustomTkinter + Matplotlib)
├── database.py           # SQLite manager with WAL mode, transactions, plans & rate tracking
├── google_sheets_sync.py # Bidirectional Google Sheets & Apps Script cloud synchronizer
├── google_apps_script.js # Serverless Google Apps Script handler (Cloud webhook 24/7)
├── bot.py                # Optional local asynchronous Telegram Bot (polling mode)
├── notifier.py           # Decoupled Telegram notification dispatcher
├── config.py             # Centralized configuration, categories, and environment loader
├── test_core.py          # Unit and integration test suite
├── app_icon.ico          # Application desktop icon
├── requirements.txt      # Python dependencies
├── .env.example          # Template for environment configuration
├── start.bat             # One-click Windows startup script
└── README.md             # Project documentation
```

---

## 🚀 Getting Started

### 1. Prerequisites
- **Python 3.10+** installed on your system.
- Git (optional, for cloning).

### 2. Installation
Clone the repository and install the dependencies in a virtual environment:

```bash
# Clone the repository
git clone https://github.com/your-username/mybudget.git
cd mybudget

# Create and activate virtual environment
python -m venv venv

# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# Windows (cmd):
venv\Scripts\activate.bat
# macOS / Linux:
source venv/bin/activate

# Install required packages
pip install -r requirements.txt
```

### 3. Configuration (`.env`)
Create your `.env` configuration file from the template:

```bash
cp .env.example .env
```

Open `.env` and fill in your values:

```env
# Telegram Bot Token from @BotFather
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRstUVwxyZ

# Your personal numeric Telegram User ID (get it from @userinfobot)
TELEGRAM_USER_ID=123456789

# Default monthly budget limit in EUR
MONTHLY_BUDGET=1000.0

# SQLite database file name
DB_NAME=spese.db

# Google Apps Script WebApp URL (see instructions below)
GOOGLE_SHEETS_URL=https://script.google.com/macros/s/AKfycb.../exec
```

---

## ☁️ Google Sheets & Cloud Sync Setup (2 Minutes)

To enable 24/7 cloud sync and mobile Telegram tracking when your PC is turned off:

1. Go to [Google Drive](https://drive.google.com) and create a new **Google Sheet**.
2. In the top menu, open **Extensions** ➔ **Apps Script**.
3. Replace any code in the editor with the complete contents of [`google_apps_script.js`](google_apps_script.js).
4. Update `BOT_TOKEN` at line 31 with your Telegram Bot Token.
5. In the top right corner, click **Deploy** ➔ **New deployment**:
   - **Type:** Web app
   - **Execute as:** *Me (your Google account)*
   - **Who has access:** *Anyone*
6. Copy the resulting Web app URL (ending in `/exec`).
7. In the Apps Script toolbar, run the `setupWebhook` function once to connect Telegram.
8. Open the Desktop App, click **"⚙️ Imposta URL Foglio"** in the sidebar, paste your URL, and click Save.

---

## 📲 Recommended Workflow: iOS Shortcut

For the fastest expense logging experience on iPhone:
1. Open the **Shortcuts** app on iOS and tap **+** to create a new shortcut named *"Add Expense"*.
2. Add the action **"Ask for Input"** (Prompt: *"Amount?"*, Type: *Number*).
3. Add another **"Choose from List"** or **"Ask for Input"** for the Category (e.g., `Alimentari`, `Trasporti`, `Svago`, `Casa`, `Salute`, `Altro`).
4. Add an action to ask for an optional description (Prompt: *"Description?"*).
5. Add a **"Send Message via Telegram"** action (or an HTTP POST to Telegram API / Webhook) to send the formatted text:
   ```text
   [Amount], [Category], [Description]
   ```
6. Assign the shortcut to your **Action Button**, a **Home Screen Widget**, or invoke it via **Siri** (*"Hey Siri, Add Expense"*).

---

## 🖥️ Running the Application

### Method 1: Start Script (Windows)
Double-click [`start.bat`](start.bat) to automatically activate the virtual environment and start the desktop app.

### Method 2: Command Line
```powershell
python desktop_app.py
```

### Method 3: Run Unit Tests
To verify database integrity, recurring expense automation, and sync logic:
```powershell
python test_core.py
```

---

## 📦 Building a Standalone Executable (Windows)

If you wish to create a self-contained `.exe` that runs without requiring Python:

```powershell
pip install pyinstaller
pyinstaller --noconsole --onefile --name "Contabile" --collect-all customtkinter desktop_app.py
```

The compiled standalone executable will be located in the `dist/` directory.

---

## 📄 License
This project is open-source and available under the [MIT License](LICENSE).
