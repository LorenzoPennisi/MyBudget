/**
 * ==============================================================================
 * CONTABILE SPESE - GOOGLE APPS SCRIPT (TELEGRAM BOT WEBHOOK & CLOUD DATABASE)
 * ==============================================================================
 * 
 * Questo script gratuito gira 24 ore su 24 sui server di Google a costo zero.
 * 
 * FUNZIONALITÀ COMPLETE:
 * 1. Fogli Gestiti nel Spreadsheet:
 *    - "Spese": Registro dettagliato di tutte le spese singole.
 *    - "Piani": Registro di Rate determinate e Abbonamenti indeterminati.
 *    - "Riepilogo": Valori aggregati globali (Totale Mese, Budget, Residuo, Categorie, Fisse).
 * 2. Comandi Bot Telegram:
 *    - /comandi o /help: Elenco completo di tutti i comandi disponibili.
 *    - /budget o /stats: Riepilogo dettagliato con valori aggregati e progress bar.
 *    - /nuovoabbonamento: Procedura guidata passo-passo per aggiungere un abbonamento.
 *    - /nuovarata: Procedura guidata passo-passo per aggiungere un piano rateale.
 *    - /piani o /abbonamenti: Visualizza tutti gli impegni fissi attivi.
 *    - /ultime: Ultime 5 spese inserite.
 *    - /elimina: Cancella l'ultima spesa o una spesa specifica per ID.
 *    - /annulla: Annulla la procedura guidata in corso.
 * 3. Protezione anti-loop di Telegram con CacheService e verifica ultima riga.
 * 4. API di Sincronizzazione bidirezionale con l'applicazione desktop Windows.
 * ==============================================================================
 */

// ==============================================================================
// CONFIGURAZIONE PRINCIPALE (Sostituisci con i tuoi dati)
// ==============================================================================
var BOT_TOKEN = "INSERISCI_QUI_IL_TUO_BOT_TOKEN"; // Token fornito da @BotFather (es. 123456789:ABCdefGh...)
var ALLOWED_USER_ID = 0; // Il tuo Telegram User ID univoco numerico (es. 123456789)
var SHEET_SPESE = "Spese";
var SHEET_PIANI = "Piani";
var SHEET_RIEPILOGO = "Riepilogo";
var MONTHLY_BUDGET = 1000.0;

// Categorie predefinite ed emoji
var CATEGORIES = {
  "alimentari": { name: "Alimentari", icon: "🛒" },
  "trasporti": { name: "Trasporti", icon: "🚗" },
  "casa": { name: "Casa", icon: "🏠" },
  "svago": { name: "Svago", icon: "🎉" },
  "salute": { name: "Salute", icon: "💊" },
  "altro": { name: "Altro", icon: "📦" }
};

// Dizionario parole chiave per auto-categorizzazione rapida
var KEYWORDS_MAP = {
  "spesa": "Alimentari", "supermercato": "Alimentari", "pane": "Alimentari", "pasta": "Alimentari",
  "pranzo": "Alimentari", "cena": "Alimentari", "pizza": "Alimentari", "ristorante": "Alimentari",
  "bar": "Alimentari", "caffè": "Alimentari", "colazione": "Alimentari", "kebab": "Svago",
  "benzina": "Trasporti", "gasolio": "Trasporti", "diesel": "Trasporti", "treno": "Trasporti",
  "metro": "Trasporti", "bus": "Trasporti", "autostrada": "Trasporti", "parcheggio": "Trasporti",
  "affitto": "Casa", "bolletta": "Casa", "luce": "Casa", "gas": "Casa", "wifi": "Casa",
  "cinema": "Svago", "concerto": "Svago", "aperitivo": "Svago", "cuffie": "Svago", "palestra": "Svago",
  "farmacia": "Salute", "medico": "Salute", "visita": "Salute", "medicine": "Salute"
};

// ==============================================================================
// GESTIONE E INIZIALIZZAZIONE FOGLI
// ==============================================================================
function getOrCreateSheet(sheetName) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(sheetName);
  if (!sheet) {
    sheet = ss.insertSheet(sheetName);
  }
  
  if (sheetName === SHEET_SPESE && sheet.getLastRow() === 0) {
    var headers = ["ID", "Data", "Importo", "Categoria", "Descrizione", "Origine", "Timestamp"];
    sheet.appendRow(headers);
    formatHeaderRow(sheet, headers.length);
    sheet.setColumnWidth(1, 60);  // ID
    sheet.setColumnWidth(2, 110); // Data
    sheet.setColumnWidth(3, 90);  // Importo
    sheet.setColumnWidth(4, 120); // Categoria
    sheet.setColumnWidth(5, 250); // Descrizione
    sheet.setColumnWidth(6, 90);  // Origine
    sheet.setColumnWidth(7, 160); // Timestamp
  }
  
  if (sheetName === SHEET_PIANI && sheet.getLastRow() === 0) {
    var pHeaders = ["ID", "Tipo", "Nome / Descrizione", "Importo", "Categoria", "Giorno Addebito", "Rate Totali", "Rate Pagate", "Stato", "Ultimo Mese", "Data Inizio"];
    sheet.appendRow(pHeaders);
    formatHeaderRow(sheet, pHeaders.length);
    sheet.setColumnWidth(1, 50);  // ID
    sheet.setColumnWidth(2, 90);  // Tipo
    sheet.setColumnWidth(3, 180); // Nome
    sheet.setColumnWidth(4, 90);  // Importo
    sheet.setColumnWidth(5, 120); // Categoria
    sheet.setColumnWidth(6, 110); // Giorno
    sheet.setColumnWidth(7, 90);  // Rate Totali
    sheet.setColumnWidth(8, 90);  // Rate Pagate
    sheet.setColumnWidth(9, 90);  // Stato
    sheet.setColumnWidth(10, 100);// Ultimo Mese
    sheet.setColumnWidth(11, 110);// Data Inizio
  }
  
  return sheet;
}

function formatHeaderRow(sheet, cols) {
  var range = sheet.getRange(1, 1, 1, cols);
  range.setBackground("#0F172A");
  range.setFontColor("#F8FAFC");
  range.setFontWeight("bold");
  range.setHorizontalAlignment("center");
  sheet.setFrozenRows(1);
}

// Aggiorna il foglio "Riepilogo" con i valori aggregati in tempo reale
function updateSummarySheet() {
  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var sSheet = ss.getSheetByName(SHEET_RIEPILOGO) || ss.insertSheet(SHEET_RIEPILOGO);
    sSheet.clear();
    
    var now = new Date();
    var curMonthStr = Utilities.formatDate(now, Session.getScriptTimeZone(), "yyyy-MM");
    var agg = calculateAggregates(curMonthStr);
    
    sSheet.appendRow(["📊 DASHBOARD VALORI AGGREGATI", "MESE: " + curMonthStr]);
    sSheet.getRange(1, 1, 1, 2).setBackground("#1E293B").setFontColor("#38BDF8").setFontWeight("bold");
    
    sSheet.appendRow(["Metrica", "Valore (€)"]);
    formatHeaderRow(sSheet, 2);
    
    sSheet.appendRow(["🎯 Budget Mensile Target", agg.budget.toFixed(2) + " €"]);
    sSheet.appendRow(["💰 Totale Speso nel Mese", agg.totalSpent.toFixed(2) + " €"]);
    sSheet.appendRow(["🟢 Budget Residuo", agg.remaining.toFixed(2) + " €"]);
    sSheet.appendRow(["📈 Percentuale Utilizzo", agg.pct.toFixed(1) + "%"]);
    sSheet.appendRow(["🔁 Totale Abbonamenti Attivi", agg.totalAbbonamenti.toFixed(2) + " €/mese"]);
    sSheet.appendRow(["⏳ Totale Rate Attive", agg.totalRate.toFixed(2) + " €/mese"]);
    sSheet.appendRow(["💼 Totale Impegni Fissi Mensili", agg.totalFixed.toFixed(2) + " €/mese"]);
    sSheet.appendRow(["🔢 Numero Spese Registrate", agg.txCount]);
    
    sSheet.appendRow(["", ""]);
    sSheet.appendRow(["📂 RIPARTIZIONE PER CATEGORIA", "TOTALE SPESO"]);
    sSheet.getRange(12, 1, 1, 2).setBackground("#1E293B").setFontColor("#38BDF8").setFontWeight("bold");
    
    for (var cat in agg.categories) {
      var icon = CATEGORIES[cat.toLowerCase()] ? CATEGORIES[cat.toLowerCase()].icon : "🏷️";
      sSheet.appendRow([icon + " " + cat, agg.categories[cat].toFixed(2) + " €"]);
    }
    
    sSheet.setColumnWidth(1, 260);
    sSheet.setColumnWidth(2, 150);
  } catch (err) {
    Logger.log("Errore updateSummarySheet: " + err);
  }
}

// Calcola i valori aggregati direttamente dai dati presenti nel foglio
function calculateAggregates(targetMonthStr) {
  var speseSheet = getOrCreateSheet(SHEET_SPESE);
  var pianiSheet = getOrCreateSheet(SHEET_PIANI);
  
  var totalSpent = 0.0;
  var txCount = 0;
  var catTotals = {
    "Alimentari": 0.0,
    "Trasporti": 0.0,
    "Casa": 0.0,
    "Svago": 0.0,
    "Salute": 0.0,
    "Altro": 0.0
  };
  
  // 1. Calcolo spese mese
  var lastSpese = speseSheet.getLastRow();
  if (lastSpese > 1) {
    var sData = speseSheet.getRange(2, 2, lastSpese - 1, 3).getValues(); // Data, Importo, Categoria
    for (var i = 0; i < sData.length; i++) {
      var dVal = sData[i][0];
      var dStr = (dVal instanceof Date) ? Utilities.formatDate(dVal, Session.getScriptTimeZone(), "yyyy-MM-dd") : String(dVal).trim();
      if (dStr.indexOf(targetMonthStr) === 0) {
        var amt = parseFloat(sData[i][1]) || 0.0;
        var cat = String(sData[i][2] || "Altro").trim();
        totalSpent += amt;
        txCount++;
        if (catTotals[cat] !== undefined) {
          catTotals[cat] += amt;
        } else {
          catTotals["Altro"] += amt;
        }
      }
    }
  }
  
  // 2. Calcolo impegni fissi (Abbonamenti e Rate)
  var totalAbb = 0.0;
  var totalRate = 0.0;
  var lastPiani = pianiSheet.getLastRow();
  if (lastPiani > 1) {
    var pData = pianiSheet.getRange(2, 2, lastPiani - 1, 8).getValues(); // Tipo(col B), ..., Importo(col D), ..., Stato(col I)
    for (var j = 0; j < pData.length; j++) {
      var tipo = String(pData[j][0] || "").trim().toLowerCase();
      var pAmt = parseFloat(pData[j][2]) || 0.0;
      var stato = String(pData[j][7] || "attivo").trim().toLowerCase();
      if (stato === "attivo") {
        if (tipo === "abbonamento") {
          totalAbb += pAmt;
        } else if (tipo === "rata") {
          totalRate += pAmt;
        }
      }
    }
  }
  
  var remaining = MONTHLY_BUDGET - totalSpent;
  var pct = (MONTHLY_BUDGET > 0) ? (totalSpent / MONTHLY_BUDGET * 100) : 0;
  
  return {
    month: targetMonthStr,
    budget: MONTHLY_BUDGET,
    totalSpent: totalSpent,
    remaining: remaining,
    pct: pct,
    txCount: txCount,
    totalAbbonamenti: totalAbb,
    totalRate: totalRate,
    totalFixed: totalAbb + totalRate,
    categories: catTotals
  };
}

// ==============================================================================
// GESTIONE TELEGRAM WEBHOOK (doPost)
// ==============================================================================
function doPost(e) {
  try {
    var data = null;
    if (e && e.postData && e.postData.contents) {
      try {
        data = JSON.parse(e.postData.contents);
      } catch (jsonErr) {
        // Contenuto non JSON (es. form urlencoded)
      }
    }
    
    // Fallback: se non è JSON, usa i parametri di richiesta
    if (!data || typeof data !== "object") {
      data = (e && e.parameter) ? e.parameter : {};
    } else if (e && e.parameter) {
      for (var k in e.parameter) {
        if (data[k] === undefined) data[k] = e.parameter[k];
      }
    }
    
    // 1. Chiamata API desktop o Comando Rapido (JSON o Form)
    if (data.action || data.amount !== undefined || data.importo !== undefined) {
      if (!data.action && (data.amount !== undefined || data.importo !== undefined)) {
        data.action = "add";
      }
      return handleApiPost(data);
    }
    
    // 2. Se inviata una stringa di testo diretta (es. {"text": "15, spesa, cena"})
    if (data.text && !data.message) {
      var fakeMsg = { chat: { id: ALLOWED_USER_ID || 0 }, text: data.text };
      handleTelegramMessage(fakeMsg);
      return HtmlService.createHtmlOutput("OK");
    }
    
    // 3. Cache anti-loop retry
    var updateId = data.update_id ? String(data.update_id) : null;
    if (updateId) {
      var cache = CacheService.getScriptCache();
      if (cache.get("up_" + updateId)) {
        return HtmlService.createHtmlOutput("OK");
      }
      cache.put("up_" + updateId, "1", 300);
    }
    
    // 4. Elaborazione messaggio Telegram standard (Webhook)
    if (data.message && data.message.text) {
      handleTelegramMessage(data.message);
    }
    
    return HtmlService.createHtmlOutput("OK");
  } catch (err) {
    Logger.log("Errore doPost: " + err);
    return HtmlService.createHtmlOutput("OK");
  }
}

// Smista i messaggi Telegram e gestisce la macchina a stati per i wizard guidati
function handleTelegramMessage(msg) {
  var chatId = msg.chat.id;
  var fromId = msg.from ? msg.from.id : 0;
  var text = (msg.text || "").trim();
  
  if (ALLOWED_USER_ID && ALLOWED_USER_ID !== 0 && fromId !== ALLOWED_USER_ID) {
    sendTelegramMessage(chatId, "⛔ <b>Accesso non autorizzato!</b>\nIl tuo Telegram ID è: <code>" + fromId + "</code>.");
    return;
  }
  
  if (!text) return;
  
  var cache = CacheService.getScriptCache();
  var stateKey = "state_" + chatId;
  var userStateRaw = cache.get(stateKey);
  
  // Comando di annullamento wizard in qualsiasi momento
  if (text === "/annulla" || text === "/stop") {
    if (userStateRaw) {
      cache.remove(stateKey);
      sendTelegramMessage(chatId, "🛑 <b>Procedura guidata annullata.</b> Nessun piano è stato registrato.");
    } else {
      sendTelegramMessage(chatId, "ℹ️ Nessuna procedura guidata in corso.");
    }
    return;
  }
  
  // Se l'utente si trova all'interno di una procedura guidata, gestisci lo step corrente
  if (userStateRaw && !text.startsWith("/")) {
    try {
      var userState = JSON.parse(userStateRaw);
      if (userState.wizard === "abbonamento") {
        handleAbbonamentoWizardStep(chatId, text, userState, stateKey, cache);
        return;
      } else if (userState.wizard === "rata") {
        handleRataWizardStep(chatId, text, userState, stateKey, cache);
        return;
      }
    } catch (e) {
      cache.remove(stateKey);
    }
  }
  
  // 1. Comando /comandi o /commands o /help o /start
  if (text.startsWith("/comandi") || text.startsWith("/commands") || text.startsWith("/help") || text.startsWith("/start")) {
    handleCommandsList(chatId);
    return;
  }
  
  // 2. Comando /budget o /stats o /totale
  if (text.startsWith("/budget") || text.startsWith("/stats") || text.startsWith("/totale") || text.startsWith("/mese")) {
    handleBudgetCommand(chatId);
    return;
  }
  
  // 3. Procedura guidata: /nuovoabbonamento
  if (text.startsWith("/nuovoabbonamento") || text.startsWith("/abbonamento")) {
    startAbbonamentoWizard(chatId, stateKey, cache);
    return;
  }
  
  // 4. Procedura guidata: /nuovarata
  if (text.startsWith("/nuovarata") || text.startsWith("/rata")) {
    startRataWizard(chatId, stateKey, cache);
    return;
  }
  
  // 5. Elenco piani: /piani
  if (text.startsWith("/piani") || text.startsWith("/rate") || text.startsWith("/abbonamenti")) {
    handleListPlansCommand(chatId);
    return;
  }
  
  // 6. Ultime spese: /ultime
  if (text.startsWith("/ultime") || text.startsWith("/last")) {
    handleLastCommand(chatId);
    return;
  }
  
  // 7. Eliminazione spesa: /elimina
  if (text.startsWith("/elimina") || text.startsWith("/cancella") || text.startsWith("/delete")) {
    handleDeleteCommand(chatId, text);
    return;
  }
  
  // 8. Inserimento spesa standard (es. "15.50 spesa coop" o "12, alimentari, cena")
  handleExpenseInsert(chatId, text);
}

// ==============================================================================
// COMANDI PRINCIPALI TELEGRAM
// ==============================================================================

// Mostra l'elenco completo di tutti i comandi disponibili (/comandi)
function handleCommandsList(chatId) {
  var msg = "🤖 <b>ELENCO COMPLETO DEI COMANDI DISPONIBILI</b>\n\n" +
    "📝 <b>REGISTRAZIONE SPESE VELOCI</b>\n" +
    "• Scrivi semplicemente: <code>&lt;importo&gt;, &lt;categoria&gt;, &lt;descrizione&gt;</code>\n" +
    "  <i>Es: 15.50, Alimentari, Spesa Coop</i>\n" +
    "• Oppure testo libero: <code>12 pizza margherita</code>\n\n" +
    "📊 <b>DATI AGGREGATI & STATISTICHE GLOBALI</b>\n" +
    "• <b>/budget</b> o <b>/stats</b> ➔ Riepilogo completo: budget residuo, speso, suddivisione per categoria e impegni fissi calcolati in tempo reale dal tuo Foglio Google h24!\n" +
    "• <b>/ultime</b> ➔ Visualizza le ultime 5 spese salvate con relativi ID\n\n" +
    "🔁 <b>GESTIONE GUIDATA RATE & ABBONAMENTI</b>\n" +
    "• <b>/nuovoabbonamento</b> ➔ Procedura a step per aggiungere un abbonamento continuo (es. Netflix, Palestra)\n" +
    "• <b>/nuovarata</b> ➔ Procedura a step per aggiungere un finanziamento (con totale rate e rate già pagate)\n" +
    "• <b>/piani</b> ➔ Elenco di tutti gli abbonamenti e le rate attive con date e scadenze\n" +
    "• <b>/annulla</b> ➔ Interrompe la procedura guidata in qualsiasi momento\n\n" +
    "🗑️ <b>CANCELLAZIONE & CORREZIONE</b>\n" +
    "• <b>/elimina</b> ➔ Cancella l'ultima spesa inserita dal Foglio\n" +
    "• <b>/elimina &lt;ID&gt;</b> ➔ Cancella una spesa specifica (es. <code>/elimina 42</code>)\n\n" +
    "💡 <i>Tutti i dati sono sempre salvati e accessibili anche a PC spento!</i>";
  sendTelegramMessage(chatId, msg);
}

// Mostra il report aggregato completo (/budget)
function handleBudgetCommand(chatId) {
  var now = new Date();
  var curMonthStr = Utilities.formatDate(now, Session.getScriptTimeZone(), "yyyy-MM");
  var agg = calculateAggregates(curMonthStr);
  
  var statusBadge = agg.remaining >= 0 ? "🟢 In Budget" : "🔴 Sforato";
  var pctNorm = Math.min(Math.max(agg.pct, 0), 100);
  var filledBlocks = Math.round(pctNorm / 10);
  var emptyBlocks = 10 - filledBlocks;
  var progressBar = "";
  for (var k = 0; k < filledBlocks; k++) progressBar += "█";
  for (var m = 0; m < emptyBlocks; m++) progressBar += "░";
  
  var msg = "📊 <b>RIEPILOGO FINANZIARIO GLOBALE • " + Utilities.formatDate(now, Session.getScriptTimeZone(), "MMMM yyyy").toUpperCase() + "</b>\n\n" +
    "💰 <b>Totale Speso Mese:</b> <code>" + agg.totalSpent.toFixed(2) + " €</code>\n" +
    "🎯 <b>Budget Target:</b> <code>" + agg.budget.toFixed(2) + " €</code>\n" +
    statusBadge + " <b>Residuo:</b> <code>" + agg.remaining.toFixed(2) + " €</code> (" + agg.pct.toFixed(1) + "%)\n" +
    "Progresso: <code>[" + progressBar + "]</code>\n\n" +
    "📂 <b>Ripartizione per Categoria:</b>\n";
    
  for (var c in agg.categories) {
    if (agg.categories[c] > 0) {
      var icon = CATEGORIES[c.toLowerCase()] ? CATEGORIES[c.toLowerCase()].icon : "🏷️";
      msg += "• " + icon + " " + c + ": <code>" + agg.categories[c].toFixed(2) + " €</code>\n";
    }
  }
  
  msg += "\n💼 <b>Impegni Fissi Mensili (Piani):</b>\n" +
    "• 🔁 Abbonamenti: <code>" + agg.totalAbbonamenti.toFixed(2) + " €/mese</code>\n" +
    "• ⏳ Rate in corso: <code>" + agg.totalRate.toFixed(2) + " €/mese</code>\n" +
    "• <b>Totale Uscite Fisse:</b> <code>" + agg.totalFixed.toFixed(2) + " €/mese</code>\n\n" +
    "🔢 <i>Transazioni registrate nel mese: " + agg.txCount + "</i>\n" +
    "☁️ <i>Valori aggregati calcolati dal Foglio Google.</i>";
    
  sendTelegramMessage(chatId, msg);
}

// ==============================================================================
// PROCEDURA GUIDATA NUOVO ABBONAMENTO (/nuovoabbonamento)
// ==============================================================================
function startAbbonamentoWizard(chatId, stateKey, cache) {
  var state = { wizard: "abbonamento", step: 1, data: {} };
  cache.put(stateKey, JSON.stringify(state), 900); // Scade dopo 15 minuti
  
  var msg = "🔁 <b>CONFIGURAZIONE NUOVO ABBONAMENTO (Passo 1 di 4)</b>\n\n" +
    "Qual è il <b>nome del servizio</b> o abbonamento?\n" +
    "<i>(es. Netflix, Spotify, Palestra, Fibra Casa...)</i>\n\n" +
    "👉 <i>Scrivi /annulla per interrompere in qualsiasi momento.</i>";
  sendTelegramMessage(chatId, msg);
}

function handleAbbonamentoWizardStep(chatId, text, state, stateKey, cache) {
  if (state.step === 1) {
    state.data.name = text;
    state.step = 2;
    cache.put(stateKey, JSON.stringify(state), 900);
    sendTelegramMessage(chatId, "💰 <b>(Passo 2 di 4)</b>\n\nInserisci l'<b>importo mensile</b> in Euro per <b>" + escapeHtml(state.data.name) + "</b>:\n<i>(es. 12.99 oppure 15)</i>");
    return;
  }
  
  if (state.step === 2) {
    var amt = parseFloat(text.replace("€", "").replace(",", "."));
    if (isNaN(amt) || amt <= 0) {
      sendTelegramMessage(chatId, "⚠️ <i>Inserisci un importo valido maggiore di zero (es. 12.99):</i>");
      return;
    }
    state.data.amount = amt;
    state.step = 3;
    cache.put(stateKey, JSON.stringify(state), 900);
    sendTelegramMessage(chatId, "📅 <b>(Passo 3 di 4)</b>\n\nIn quale <b>giorno del mese</b> scatta l'addebito?\n<i>(Inserisci un numero da 1 a 31, es. 15)</i>");
    return;
  }
  
  if (state.step === 3) {
    var day = parseInt(text);
    if (isNaN(day) || day < 1 || day > 31) {
      sendTelegramMessage(chatId, "⚠️ <i>Inserisci un giorno compreso tra 1 e 31:</i>");
      return;
    }
    state.data.day = day;
    state.step = 4;
    cache.put(stateKey, JSON.stringify(state), 900);
    sendTelegramMessage(chatId, "🏷️ <b>(Passo 4 di 4)</b>\n\nScegli la <b>categoria</b> scrivendola qui sotto:\n• 🛒 Alimentari\n• 🚗 Trasporti\n• 🏠 Casa\n• 🎉 Svago\n• 💊 Salute\n• 📦 Altro");
    return;
  }
  
  if (state.step === 4) {
    var cat = normalizeCategory(text);
    var pSheet = getOrCreateSheet(SHEET_PIANI);
    var nextId = getNextTransactionId(pSheet);
    var todayStr = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "yyyy-MM-dd");
    
    // [ID, Tipo, Nome, Importo, Categoria, Giorno, Rate Totali, Rate Pagate, Stato, Ultimo Mese, Data Inizio]
    pSheet.appendRow([
      nextId,
      "abbonamento",
      state.data.name,
      state.data.amount,
      cat,
      state.data.day,
      "", // Nessuna rata totale
      "", // Nessuna rata pagata
      "attivo",
      "",
      todayStr
    ]);
    
    cache.remove(stateKey);
    updateSummarySheet();
    
    var okMsg = "✅ <b>ABBONAMENTO CONFIGURATO CON SUCCESSO!</b>\n\n" +
      "🔢 <b>ID Piano:</b> <code>#" + nextId + "</code>\n" +
      "🔁 <b>Servizio:</b> <b>" + escapeHtml(state.data.name) + "</b>\n" +
      "💶 <b>Importo:</b> <code>" + state.data.amount.toFixed(2) + " € / mese</code>\n" +
      "📅 <b>Giorno Addebito:</b> ogni " + state.data.day + " del mese\n" +
      "🏷️ <b>Categoria:</b> " + cat + "\n\n" +
      "<i>Memorizzato nel tuo Foglio Google e pronto per la sincronizzazione con il PC!</i>";
    sendTelegramMessage(chatId, okMsg);
  }
}

// ==============================================================================
// PROCEDURA GUIDATA NUOVA RATA (/nuovarata)
// ==============================================================================
function startRataWizard(chatId, stateKey, cache) {
  var state = { wizard: "rata", step: 1, data: {} };
  cache.put(stateKey, JSON.stringify(state), 900);
  
  var msg = "⏳ <b>CONFIGURAZIONE NUOVA RATA (Passo 1 di 6)</b>\n\n" +
    "Qual è il <b>nome del finanziamento o acquisto a rate</b>?\n" +
    "<i>(es. Rata Smartphone, Finanziamento Auto, Polizza Semestrale...)</i>\n\n" +
    "👉 <i>Scrivi /annulla per interrompere in qualsiasi momento.</i>";
  sendTelegramMessage(chatId, msg);
}

function handleRataWizardStep(chatId, text, state, stateKey, cache) {
  if (state.step === 1) {
    state.data.name = text;
    state.step = 2;
    cache.put(stateKey, JSON.stringify(state), 900);
    sendTelegramMessage(chatId, "💶 <b>(Passo 2 di 6)</b>\n\nInserisci l'<b>importo di ciascuna rata mensile</b> in Euro per <b>" + escapeHtml(state.data.name) + "</b>:\n<i>(es. 49.90)</i>");
    return;
  }
  
  if (state.step === 2) {
    var amt = parseFloat(text.replace("€", "").replace(",", "."));
    if (isNaN(amt) || amt <= 0) {
      sendTelegramMessage(chatId, "⚠️ <i>Inserisci un importo valido (es. 49.90):</i>");
      return;
    }
    state.data.amount = amt;
    state.step = 3;
    cache.put(stateKey, JSON.stringify(state), 900);
    sendTelegramMessage(chatId, "🏷️ <b>(Passo 3 di 6)</b>\n\nScegli la <b>categoria</b> della spesa:\n• 🛒 Alimentari\n• 🚗 Trasporti\n• 🏠 Casa\n• 🎉 Svago\n• 💊 Salute\n• 📦 Altro");
    return;
  }
  
  if (state.step === 3) {
    state.data.category = normalizeCategory(text);
    state.step = 4;
    cache.put(stateKey, JSON.stringify(state), 900);
    sendTelegramMessage(chatId, "📅 <b>(Passo 4 di 6)</b>\n\nIn quale <b>giorno del mese</b> scatta l'addebito della rata?\n<i>(Numero da 1 a 31, es. 5)</i>");
    return;
  }
  
  if (state.step === 4) {
    var day = parseInt(text);
    if (isNaN(day) || day < 1 || day > 31) {
      sendTelegramMessage(chatId, "⚠️ <i>Inserisci un giorno compreso tra 1 e 31:</i>");
      return;
    }
    state.data.day = day;
    state.step = 5;
    cache.put(stateKey, JSON.stringify(state), 900);
    sendTelegramMessage(chatId, "🔢 <b>(Passo 5 di 6)</b>\n\nQuante sono le <b>rate totali previste</b> dal piano?\n<i>(es. 12, 24, 36...)</i>");
    return;
  }
  
  if (state.step === 5) {
    var tot = parseInt(text);
    if (isNaN(tot) || tot <= 0) {
      sendTelegramMessage(chatId, "⚠️ <i>Inserisci un numero intero valido maggiore di zero (es. 12):</i>");
      return;
    }
    state.data.totRate = tot;
    state.step = 6;
    cache.put(stateKey, JSON.stringify(state), 900);
    sendTelegramMessage(chatId, "✅ <b>(Passo 6 di 6)</b>\n\nQuante rate hai <b>già pagato finora</b>?\n<i>(Scrivi 0 se inizi adesso, oppure il numero di rate già saldate es. 3)</i>");
    return;
  }
  
  if (state.step === 6) {
    var pag = parseInt(text);
    if (isNaN(pag) || pag < 0) {
      sendTelegramMessage(chatId, "⚠️ <i>Inserisci 0 o il numero di rate già pagate:</i>");
      return;
    }
    state.data.pagRate = pag;
    
    var pSheet = getOrCreateSheet(SHEET_PIANI);
    var nextId = getNextTransactionId(pSheet);
    var todayStr = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "yyyy-MM-dd");
    var stato = (pag >= state.data.totRate) ? "completato" : "attivo";
    
    pSheet.appendRow([
      nextId,
      "rata",
      state.data.name,
      state.data.amount,
      state.data.category,
      state.data.day,
      state.data.totRate,
      pag,
      stato,
      "",
      todayStr
    ]);
    
    cache.remove(stateKey);
    updateSummarySheet();
    
    var pct = Math.round((pag / state.data.totRate) * 100);
    var okMsg = "✅ <b>PIANO RATEALE CREATO CON SUCCESSO!</b>\n\n" +
      "🔢 <b>ID Piano:</b> <code>#" + nextId + "</code>\n" +
      "⏳ <b>Finanziamento:</b> <b>" + escapeHtml(state.data.name) + "</b>\n" +
      "💶 <b>Importo Rata:</b> <code>" + state.data.amount.toFixed(2) + " € / mese</code>\n" +
      "📅 <b>Giorno Addebito:</b> ogni " + state.data.day + " del mese\n" +
      "📊 <b>Avanzamento:</b> " + pag + "/" + state.data.totRate + " rate pagate (" + pct + "%)\n" +
      "🏷️ <b>Categoria:</b> " + state.data.category + "\n\n" +
      "<i>Memorizzato nel Foglio Google e pronto per la sincronizzazione con il PC!</i>";
    sendTelegramMessage(chatId, okMsg);
  }
}

// Mostra l'elenco dei piani attivi (/piani)
function handleListPlansCommand(chatId) {
  var pSheet = getOrCreateSheet(SHEET_PIANI);
  var lastRow = pSheet.getLastRow();
  if (lastRow <= 1) {
    sendTelegramMessage(chatId, "ℹ️ Nessun abbonamento o rata configurata finora.\nUsa <b>/nuovoabbonamento</b> o <b>/nuovarata</b> per aggiungerne uno!");
    return;
  }
  
  var data = pSheet.getRange(2, 1, lastRow - 1, 9).getValues();
  var msg = "📋 <b>ELENCO IMPEGNI FISSI & RATE ATTIVE</b>\n\n";
  var count = 0;
  
  for (var i = 0; i < data.length; i++) {
    var r = data[i];
    var id = r[0];
    var tipo = String(r[1] || "").trim().toLowerCase();
    var nome = escapeHtml(String(r[2] || ""));
    var amt = parseFloat(r[3]) || 0;
    var day = r[5];
    var stato = String(r[8] || "attivo").trim().toLowerCase();
    
    if (stato === "attivo") {
      count++;
      if (tipo === "rata") {
        var tot = r[6] || 0;
        var pag = r[7] || 0;
        msg += "• ⏳ <b>#" + id + " " + nome + "</b>: <code>" + amt.toFixed(2) + " €</code> (giorno " + day + " • " + pag + "/" + tot + " rate)\n";
      } else {
        msg += "• 🔁 <b>#" + id + " " + nome + "</b>: <code>" + amt.toFixed(2) + " €</code> (giorno " + day + " di ogni mese)\n";
      }
    }
  }
  
  if (count === 0) {
    msg += "<i>Tutti i piani risultano completati o in pausa.</i>";
  }
  
  sendTelegramMessage(chatId, msg);
}

// ==============================================================================
// GESTIONE INSERIMENTO SPESA STANDARD & ELIMINAZIONE
// ==============================================================================
function handleExpenseInsert(chatId, text) {
  var sheet = getOrCreateSheet(SHEET_SPESE);
  var parsed = parseExpenseInput(text);
  
  if (!parsed) {
    sendTelegramMessage(chatId, "⚠️ <b>Formato non riconosciuto!</b>\n\nScrivi ad esempio:\n<code>15.50, alimentari, spesa coop</code>\noppure\n<code>12 pizza</code>\n\nScrivi <b>/comandi</b> per la guida completa.");
    return;
  }
  
  var now = new Date();
  var dateStr = Utilities.formatDate(now, Session.getScriptTimeZone(), "yyyy-MM-dd");
  var timeStr = Utilities.formatDate(now, Session.getScriptTimeZone(), "yyyy-MM-dd HH:mm:ss");
  
  // Anti-duplicato: se l'ultima riga ha lo stesso importo e descrizione, ignora
  var lastRow = sheet.getLastRow();
  if (lastRow > 1) {
    var lastValues = sheet.getRange(lastRow, 2, 1, 4).getValues()[0];
    var lAmt = parseFloat(lastValues[1]) || 0;
    var lDesc = String(lastValues[3] || "").trim().toLowerCase();
    if (Math.abs(lAmt - parsed.amount) < 0.001 && lDesc === parsed.description.toLowerCase()) {
      sendTelegramMessage(chatId, "ℹ️ Spesa già registrata nel Foglio.");
      return;
    }
  }
  
  var nextId = getNextTransactionId(sheet);
  sheet.appendRow([
    nextId,
    dateStr,
    parsed.amount,
    parsed.category,
    parsed.description,
    "bot",
    timeStr
  ]);
  
  updateSummarySheet();
  
  var icon = CATEGORIES[parsed.category.toLowerCase()] ? CATEGORIES[parsed.category.toLowerCase()].icon : "🏷️";
  var safeDesc = escapeHtml(parsed.description);
  var curMonthStr = Utilities.formatDate(now, Session.getScriptTimeZone(), "yyyy-MM");
  var agg = calculateAggregates(curMonthStr);
  
  var confirmMsg = "✅ <b>Spesa salvata nel Foglio!</b>\n\n" +
    "🔢 <b>ID:</b> <code>#" + nextId + "</code>\n" +
    "💰 <b>Importo:</b> <code>" + parsed.amount.toFixed(2) + " €</code>\n" +
    icon + " <b>Categoria:</b> <code>" + parsed.category + "</code>\n" +
    (safeDesc ? ("📝 <b>Descrizione:</b> " + safeDesc + "\n") : "") +
    "📅 <b>Data:</b> <code>" + Utilities.formatDate(now, Session.getScriptTimeZone(), "dd/MM/yyyy") + "</code>\n\n" +
    "📊 <b>Totale Mese:</b> <code>" + agg.totalSpent.toFixed(2) + " €</code> (Residuo: <code>" + agg.remaining.toFixed(2) + " €</code>)";
    
  sendTelegramMessage(chatId, confirmMsg);
}

function handleDeleteCommand(chatId, text) {
  var sheet = getOrCreateSheet(SHEET_SPESE);
  var lastRow = sheet.getLastRow();
  if (lastRow <= 1) {
    sendTelegramMessage(chatId, "ℹ️ Nessuna spesa presente nel foglio da eliminare.");
    return;
  }
  
  var parts = text.split(/\s+/);
  var targetId = (parts.length > 1 && !isNaN(parseInt(parts[1]))) ? parseInt(parts[1]) : null;
  var rowToDelete = -1;
  
  if (targetId !== null) {
    var ids = sheet.getRange(2, 1, lastRow - 1, 1).getValues();
    for (var i = 0; i < ids.length; i++) {
      if (parseInt(ids[i][0]) === targetId) {
        rowToDelete = i + 2;
        break;
      }
    }
    if (rowToDelete === -1) {
      sendTelegramMessage(chatId, "⚠️ Nessuna spesa trovata con ID <code>#" + targetId + "</code>.");
      return;
    }
  } else {
    rowToDelete = lastRow;
  }
  
  var rowValues = sheet.getRange(rowToDelete, 1, 1, 6).getValues()[0];
  var deletedId = rowValues[0];
  var deletedAmt = parseFloat(rowValues[2]) || 0;
  var deletedCat = rowValues[3];
  var deletedDesc = escapeHtml(String(rowValues[4] || ""));
  
  sheet.deleteRow(rowToDelete);
  updateSummarySheet();
  
  var delMsg = "🗑️ <b>Spesa eliminata dal Foglio Google!</b>\n\n" +
    "🔢 <b>ID:</b> <code>#" + deletedId + "</code>\n" +
    "💰 <b>Importo:</b> <code>" + deletedAmt.toFixed(2) + " €</code>\n" +
    "🏷️ <b>Categoria:</b> " + deletedCat + "\n" +
    (deletedDesc ? ("📝 <b>Descrizione:</b> " + deletedDesc + "\n") : "") +
    "\nIl foglio e i dati aggregati sono stati aggiornati.";
  sendTelegramMessage(chatId, delMsg);
}

function handleLastCommand(chatId) {
  var sheet = getOrCreateSheet(SHEET_SPESE);
  var lastRow = sheet.getLastRow();
  if (lastRow <= 1) {
    sendTelegramMessage(chatId, "ℹ️ Nessuna spesa registrata finora.");
    return;
  }
  
  var startRow = Math.max(2, lastRow - 4);
  var numRows = lastRow - startRow + 1;
  var rows = sheet.getRange(startRow, 1, numRows, 5).getValues();
  
  var msg = "📋 <b>Ultime " + numRows + " spese registrate:</b>\n\n";
  for (var i = rows.length - 1; i >= 0; i--) {
    var r = rows[i];
    var id = r[0];
    var amt = parseFloat(r[2]) || 0;
    var cat = r[3];
    var desc = r[4] ? (" - " + escapeHtml(String(r[4]))) : "";
    msg += "• <code>#" + id + "</code> <code>" + amt.toFixed(2) + " €</code> (" + cat + ")" + desc + "\n";
  }
  sendTelegramMessage(chatId, msg);
}

// ==============================================================================
// UTILITY PARSER & HELPERS
// ==============================================================================
function normalizeCategory(text) {
  var t = (text || "").toLowerCase().trim();
  for (var k in CATEGORIES) {
    if (t.indexOf(k) !== -1) return CATEGORIES[k].name;
  }
  return "Altro";
}

function formatDateInputToIso(val) {
  if (!val) return Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "yyyy-MM-dd");
  var s = String(val).trim();
  if (s.indexOf("/") !== -1) {
    var parts = s.split("/");
    if (parts.length === 3) {
      var d = parts[0].length === 1 ? ("0" + parts[0]) : parts[0];
      var m = parts[1].length === 1 ? ("0" + parts[1]) : parts[1];
      var y = parts[2];
      return y + "-" + m + "-" + d;
    }
  }
  return s;
}

function parseExpenseInput(text) {
  text = text.trim();
  if (text.startsWith("/spesa")) {
    text = text.substring(6).trim();
  }
  
  if (text.indexOf(",") !== -1) {
    var parts = text.split(",").map(function(s) { return s.trim(); });
    var amtStr = parts[0].replace("€", "").replace(",", ".").trim();
    var amt = parseFloat(amtStr);
    if (!isNaN(amt) && amt > 0) {
      var cat = "Altro";
      var desc = "";
      if (parts.length >= 2) {
        cat = normalizeCategory(parts[1]);
      }
      if (parts.length >= 3) {
        desc = parts.slice(2).join(", ");
      }
      return { amount: amt, category: cat, description: desc };
    }
  }
  
  var tokens = text.split(/\s+/);
  if (tokens.length >= 1) {
    var firstAmtStr = tokens[0].replace("€", "").replace(",", ".").trim();
    var firstAmt = parseFloat(firstAmtStr);
    if (!isNaN(firstAmt) && firstAmt > 0) {
      var restWords = tokens.slice(1).join(" ").trim();
      var detectedCat = "Altro";
      var lowerRest = restWords.toLowerCase();
      
      for (var kw in KEYWORDS_MAP) {
        if (lowerRest.indexOf(kw) !== -1) {
          detectedCat = KEYWORDS_MAP[kw];
          break;
        }
      }
      return { amount: firstAmt, category: detectedCat, description: restWords };
    }
  }
  return null;
}

function getNextTransactionId(sheet) {
  var lastRow = sheet.getLastRow();
  if (lastRow <= 1) return 1;
  var ids = sheet.getRange(2, 1, lastRow - 1, 1).getValues();
  var maxId = 0;
  for (var i = 0; i < ids.length; i++) {
    var val = parseInt(ids[i][0]);
    if (!isNaN(val) && val > maxId) {
      maxId = val;
    }
  }
  return maxId + 1;
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function sendTelegramMessage(chatId, htmlText) {
  if (!BOT_TOKEN || BOT_TOKEN === "INSERISCI_QUI_IL_TUO_BOT_TOKEN") return;
  var url = "https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage";
  var payload = { chat_id: chatId, text: htmlText, parse_mode: "HTML" };
  try {
    UrlFetchApp.fetch(url, {
      method: "post",
      contentType: "application/json",
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    });
  } catch (err) {
    Logger.log("Errore invio telegram: " + err);
  }
}

// ==============================================================================
// ENDPOINT API DESKTOP WINDOWS (doGet & doPost)
// ==============================================================================
function doGet(e) {
  var action = (e && e.parameter && e.parameter.action) ? e.parameter.action : "get_all";
  
  if (action === "get_all" || action === "sync") {
    var sSheet = getOrCreateSheet(SHEET_SPESE);
    var pSheet = getOrCreateSheet(SHEET_PIANI);
    
    var transactions = [];
    var lastS = sSheet.getLastRow();
    if (lastS > 1) {
      var sData = sSheet.getRange(2, 1, lastS - 1, 7).getValues();
      for (var i = 0; i < sData.length; i++) {
        var row = sData[i];
        var dVal = row[1];
        var dStr = (dVal instanceof Date) ? Utilities.formatDate(dVal, Session.getScriptTimeZone(), "yyyy-MM-dd") : String(dVal).trim();
        var tsVal = row[6];
        var tsStr = (tsVal instanceof Date) ? Utilities.formatDate(tsVal, Session.getScriptTimeZone(), "yyyy-MM-dd HH:mm:ss") : String(tsVal).trim();
        transactions.push({
          id: parseInt(row[0]) || 0,
          date: dStr,
          amount: parseFloat(row[2]) || 0.0,
          category: String(row[3]).trim(),
          description: String(row[4] || "").trim(),
          source: String(row[5] || "bot").trim(),
          timestamp: tsStr
        });
      }
    }
    
    var plans = [];
    var lastP = pSheet.getLastRow();
    if (lastP > 1) {
      var pData = pSheet.getRange(2, 1, lastP - 1, 11).getValues();
      for (var j = 0; j < pData.length; j++) {
        var pr = pData[j];
        plans.push({
          id: parseInt(pr[0]) || 0,
          tipo: String(pr[1] || "abbonamento").trim(),
          nome_descrizione: String(pr[2] || "").trim(),
          importo: parseFloat(pr[3]) || 0.0,
          categoria: String(pr[4] || "Altro").trim(),
          giorno_addebito: parseInt(pr[5]) || 1,
          numero_rate_totali: pr[6] ? parseInt(pr[6]) : null,
          rate_pagate: parseInt(pr[7]) || 0,
          stato: String(pr[8] || "attivo").trim(),
          ultimo_mese_addebitato: String(pr[9] || "").trim(),
          data_inizio: String(pr[10] || "").trim()
        });
      }
    }
    
    var now = new Date();
    var curMonthStr = Utilities.formatDate(now, Session.getScriptTimeZone(), "yyyy-MM");
    var summary = calculateAggregates(curMonthStr);
    
    return ContentService.createTextOutput(JSON.stringify({
      status: "success",
      count: transactions.length,
      transactions: transactions,
      plans: plans,
      summary: summary
    })).setMimeType(ContentService.MimeType.JSON);
  }
  
  if (action === "delete") {
    var delId = parseInt(e.parameter.id);
    var sheet = getOrCreateSheet(SHEET_SPESE);
    var lastRow = sheet.getLastRow();
    var found = false;
    if (lastRow > 1) {
      var ids = sheet.getRange(2, 1, lastRow - 1, 1).getValues();
      for (var k = 0; k < ids.length; k++) {
        if (parseInt(ids[k][0]) === delId) {
          sheet.deleteRow(k + 2);
          found = true;
          break;
        }
      }
    }
    updateSummarySheet();
    return ContentService.createTextOutput(JSON.stringify({ status: found ? "success" : "not_found" }))
      .setMimeType(ContentService.MimeType.JSON);
  }
  
  if (action === "add") {
    var amt = parseFloat(e.parameter.amount || e.parameter.importo);
    if (!isNaN(amt) && amt > 0) {
      var cat = normalizeCategory(e.parameter.category || e.parameter.categoria || "Altro");
      var desc = String(e.parameter.description || e.parameter.descrizione || "").trim();
      var now = new Date();
      var dateStr = e.parameter.date ? String(e.parameter.date).trim() : Utilities.formatDate(now, Session.getScriptTimeZone(), "yyyy-MM-dd");
      var timeStr = Utilities.formatDate(now, Session.getScriptTimeZone(), "yyyy-MM-dd HH:mm:ss");
      var src = e.parameter.source || "shortcut";
      
      var sSheet = getOrCreateSheet(SHEET_SPESE);
      var nextId = getNextTransactionId(sSheet);
      sSheet.appendRow([
        nextId,
        dateStr,
        amt,
        cat,
        desc,
        src,
        timeStr
      ]);
      updateSummarySheet();
      
      if (ALLOWED_USER_ID && ALLOWED_USER_ID !== 0 && src !== "desktop") {
        var curMonthStr = Utilities.formatDate(now, Session.getScriptTimeZone(), "yyyy-MM");
        var agg = calculateAggregates(curMonthStr);
        var icon = CATEGORIES[cat.toLowerCase()] ? CATEGORIES[cat.toLowerCase()].icon : "🏷️";
        var confirmMsg = "✅ <b>SPESA REGISTRATA CON SUCCESSO!</b>\n" +
          "📊 <i>Il Foglio Google è stato aggiornato correttamente.</i>\n\n" +
          "🔢 <b>ID:</b> <code>#" + nextId + "</code>\n" +
          "💰 <b>Importo:</b> <code>" + amt.toFixed(2) + " €</code>\n" +
          icon + " <b>Categoria:</b> <code>" + cat + "</code>\n" +
          (desc ? ("📝 <b>Descrizione:</b> " + escapeHtml(desc) + "\n") : "") +
          "📅 <b>Data:</b> <code>" + Utilities.formatDate(now, Session.getScriptTimeZone(), "dd/MM/yyyy") + "</code>\n\n" +
          "━━━━━━━━━━━━━━━━━━━\n" +
          "📈 <b>Totale Speso Mese:</b> <code>" + agg.totalSpent.toFixed(2) + " €</code>\n" +
          "🎯 <b>Budget Residuo:</b> <code>" + agg.remaining.toFixed(2) + " €</code>";
        sendTelegramMessage(ALLOWED_USER_ID, confirmMsg);
      }
      
      return ContentService.createTextOutput(JSON.stringify({
        status: "success",
        id: nextId,
        amount: amt,
        category: cat,
        description: desc
      })).setMimeType(ContentService.MimeType.JSON);
    }
    return ContentService.createTextOutput(JSON.stringify({ status: "error", message: "Importo non valido" }))
      .setMimeType(ContentService.MimeType.JSON);
  }
  
  if (action === "edit" || action === "update") {
    var editId = parseInt(e.parameter.id);
    var sSheet = getOrCreateSheet(SHEET_SPESE);
    var lastRow = sSheet.getLastRow();
    var found = false;
    if (lastRow > 1 && !isNaN(editId)) {
      var ids = sSheet.getRange(2, 1, lastRow - 1, 1).getValues();
      for (var e_i = 0; e_i < ids.length; e_i++) {
        if (parseInt(ids[e_i][0]) === editId) {
          var rowIdx = e_i + 2;
          if (e.parameter.date || e.parameter.data) {
            sSheet.getRange(rowIdx, 2).setValue(formatDateInputToIso(e.parameter.date || e.parameter.data));
          }
          if (e.parameter.amount !== undefined || e.parameter.importo !== undefined) {
            var nAmt = parseFloat(e.parameter.amount || e.parameter.importo);
            if (!isNaN(nAmt) && nAmt > 0) sSheet.getRange(rowIdx, 3).setValue(nAmt);
          }
          if (e.parameter.category || e.parameter.categoria) {
            sSheet.getRange(rowIdx, 4).setValue(normalizeCategory(e.parameter.category || e.parameter.categoria));
          }
          if (e.parameter.description !== undefined || e.parameter.descrizione !== undefined) {
            sSheet.getRange(rowIdx, 5).setValue(String(e.parameter.description || e.parameter.descrizione).trim());
          }
          found = true;
          break;
        }
      }
    }
    if (found) {
      updateSummarySheet();
      return ContentService.createTextOutput(JSON.stringify({ status: "success", id: editId }))
        .setMimeType(ContentService.MimeType.JSON);
    } else {
      return ContentService.createTextOutput(JSON.stringify({ status: "not_found", message: "ID spesa non trovato" }))
        .setMimeType(ContentService.MimeType.JSON);
    }
  }
  
  return ContentService.createTextOutput(JSON.stringify({ status: "unknown_action" }))
    .setMimeType(ContentService.MimeType.JSON);
}

function handleApiPost(data) {
  if (data.action === "edit" || data.action === "update") {
    var editId = parseInt(data.id);
    var sSheet = getOrCreateSheet(SHEET_SPESE);
    var lastRow = sSheet.getLastRow();
    var found = false;
    if (lastRow > 1 && !isNaN(editId)) {
      var ids = sSheet.getRange(2, 1, lastRow - 1, 1).getValues();
      for (var ep_i = 0; ep_i < ids.length; ep_i++) {
        if (parseInt(ids[ep_i][0]) === editId) {
          var rowIdx = ep_i + 2;
          if (data.date || data.data) {
            sSheet.getRange(rowIdx, 2).setValue(formatDateInputToIso(data.date || data.data));
          }
          if (data.amount !== undefined || data.importo !== undefined) {
            var nAmt = parseFloat(data.amount || data.importo);
            if (!isNaN(nAmt) && nAmt > 0) sSheet.getRange(rowIdx, 3).setValue(nAmt);
          }
          if (data.category || data.categoria) {
            sSheet.getRange(rowIdx, 4).setValue(normalizeCategory(data.category || data.categoria));
          }
          if (data.description !== undefined || data.descrizione !== undefined) {
            sSheet.getRange(rowIdx, 5).setValue(String(data.description || data.descrizione).trim());
          }
          found = true;
          break;
        }
      }
    }
    if (found) {
      updateSummarySheet();
      return ContentService.createTextOutput(JSON.stringify({ status: "success", id: editId }))
        .setMimeType(ContentService.MimeType.JSON);
    } else {
      return ContentService.createTextOutput(JSON.stringify({ status: "not_found", message: "ID spesa non trovato" }))
        .setMimeType(ContentService.MimeType.JSON);
    }
  }

  if (data.action === "add") {
    var amt = parseFloat(data.amount || data.importo);
    if (!isNaN(amt) && amt > 0) {
      var cat = normalizeCategory(data.category || data.categoria || "Altro");
      var desc = String(data.description || data.descrizione || "").trim();
      var now = new Date();
      var dateStr = data.date ? String(data.date).trim() : Utilities.formatDate(now, Session.getScriptTimeZone(), "yyyy-MM-dd");
      var timeStr = Utilities.formatDate(now, Session.getScriptTimeZone(), "yyyy-MM-dd HH:mm:ss");
      var src = data.source || "shortcut";
      
      var sSheet = getOrCreateSheet(SHEET_SPESE);
      var nextId = getNextTransactionId(sSheet);
      sSheet.appendRow([
        nextId,
        dateStr,
        amt,
        cat,
        desc,
        src,
        timeStr
      ]);
      updateSummarySheet();
      
      if (ALLOWED_USER_ID && ALLOWED_USER_ID !== 0 && src !== "desktop") {
        var curMonthStr = Utilities.formatDate(now, Session.getScriptTimeZone(), "yyyy-MM");
        var agg = calculateAggregates(curMonthStr);
        var icon = CATEGORIES[cat.toLowerCase()] ? CATEGORIES[cat.toLowerCase()].icon : "🏷️";
        var confirmMsg = "✅ <b>SPESA REGISTRATA CON SUCCESSO!</b>\n" +
          "📊 <i>Il Foglio Google è stato aggiornato correttamente.</i>\n\n" +
          "🔢 <b>ID:</b> <code>#" + nextId + "</code>\n" +
          "💰 <b>Importo:</b> <code>" + amt.toFixed(2) + " €</code>\n" +
          icon + " <b>Categoria:</b> <code>" + cat + "</code>\n" +
          (desc ? ("📝 <b>Descrizione:</b> " + escapeHtml(desc) + "\n") : "") +
          "📅 <b>Data:</b> <code>" + Utilities.formatDate(now, Session.getScriptTimeZone(), "dd/MM/yyyy") + "</code>\n\n" +
          "━━━━━━━━━━━━━━━━━━━\n" +
          "📈 <b>Totale Speso Mese:</b> <code>" + agg.totalSpent.toFixed(2) + " €</code>\n" +
          "🎯 <b>Budget Residuo:</b> <code>" + agg.remaining.toFixed(2) + " €</code>";
        sendTelegramMessage(ALLOWED_USER_ID, confirmMsg);
      }
      
      return ContentService.createTextOutput(JSON.stringify({
        status: "success",
        id: nextId,
        amount: amt,
        category: cat,
        description: desc
      })).setMimeType(ContentService.MimeType.JSON);
    }
    return ContentService.createTextOutput(JSON.stringify({ status: "error", message: "Importo non valido" }))
      .setMimeType(ContentService.MimeType.JSON);
  }

  if (data.action === "bulk_push") {
    var sSheet = getOrCreateSheet(SHEET_SPESE);
    var pSheet = getOrCreateSheet(SHEET_PIANI);
    
    // 1. Inserimento spese singole
    var addedTxs = 0;
    if (Array.isArray(data.transactions) && data.transactions.length > 0) {
      var existingSigs = {};
      var lastS = sSheet.getLastRow();
      if (lastS > 1) {
        var sData = sSheet.getRange(2, 1, lastS - 1, 7).getValues();
        for (var i = 0; i < sData.length; i++) {
          var r = sData[i];
          var dStr = (r[1] instanceof Date) ? Utilities.formatDate(r[1], Session.getScriptTimeZone(), "yyyy-MM-dd") : String(r[1]).trim();
          var amt = parseFloat(r[2]) || 0;
          var desc = String(r[4] || "").trim().toLowerCase();
          existingSigs[dStr + "_" + amt.toFixed(2) + "_" + desc] = true;
        }
      }
      
      var nextId = getNextTransactionId(sSheet);
      var toAppend = [];
      for (var j = 0; j < data.transactions.length; j++) {
        var t = data.transactions[j];
        var amtVal = parseFloat(t.amount) || 0;
        var tDate = String(t.date || "").trim();
        var tDesc = String(t.description || "").trim();
        var sigKey = tDate + "_" + amtVal.toFixed(2) + "_" + tDesc.toLowerCase();
        if (!existingSigs[sigKey]) {
          toAppend.push([
            nextId++,
            tDate,
            amtVal,
            t.category || "Altro",
            tDesc,
            t.source || "desktop",
            t.timestamp || (tDate + " 12:00:00")
          ]);
          existingSigs[sigKey] = true;
          addedTxs++;
        }
      }
      if (toAppend.length > 0) {
        sSheet.getRange(sSheet.getLastRow() + 1, 1, toAppend.length, 7).setValues(toAppend);
      }
    }
    
    // 2. Inserimento piani (Rate & Abbonamenti)
    var addedPlans = 0;
    if (Array.isArray(data.plans) && data.plans.length > 0) {
      var existingPNames = {};
      var lastP = pSheet.getLastRow();
      if (lastP > 1) {
        var pNames = pSheet.getRange(2, 3, lastP - 1, 1).getValues();
        for (var m = 0; m < pNames.length; m++) {
          existingPNames[String(pNames[m][0] || "").trim().toLowerCase()] = true;
        }
      }
      
      var nextPId = getNextTransactionId(pSheet);
      var plansToAppend = [];
      for (var n = 0; n < data.plans.length; n++) {
        var pl = data.plans[n];
        var pName = String(pl.nome_descrizione || "").trim();
        if (!existingPNames[pName.toLowerCase()]) {
          plansToAppend.push([
            nextPId++,
            pl.tipo || "abbonamento",
            pName,
            parseFloat(pl.importo) || 0,
            pl.categoria || "Altro",
            parseInt(pl.giorno_addebito) || 1,
            pl.numero_rate_totali || "",
            pl.rate_pagate || 0,
            pl.stato || "attivo",
            pl.ultimo_mese_addebitato || "",
            pl.data_inizio || Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "yyyy-MM-dd")
          ]);
          existingPNames[pName.toLowerCase()] = true;
          addedPlans++;
        }
      }
      if (plansToAppend.length > 0) {
        pSheet.getRange(pSheet.getLastRow() + 1, 1, plansToAppend.length, 11).setValues(plansToAppend);
      }
    }
    
    updateSummarySheet();
    return ContentService.createTextOutput(JSON.stringify({
      status: "success",
      added_transactions: addedTxs,
      added_plans: addedPlans
    })).setMimeType(ContentService.MimeType.JSON);
  }
  
  return ContentService.createTextOutput(JSON.stringify({ status: "unknown" }))
    .setMimeType(ContentService.MimeType.JSON);
}

// ==============================================================================
// FUNZIONI DI CONFIGURAZIONE TELEGRAM & UTILITY
// ==============================================================================
function setupWebhook() {
  if (!BOT_TOKEN || BOT_TOKEN === "INSERISCI_QUI_IL_TUO_BOT_TOKEN") {
    throw new Error("Devi prima inserire il tuo BOT_TOKEN in cima al file!");
  }
  var webAppUrl = ScriptApp.getService().getUrl();
  if (!webAppUrl || webAppUrl === "") {
    throw new Error("Devi prima fare 'Distribuisci' -> 'Nuova Distribuzione' come Applicazione Web!");
  }
  if (webAppUrl.indexOf("/dev") !== -1) {
    webAppUrl = webAppUrl.replace("/dev", "/exec");
  }
  
  // 1. Registra i comandi nel menu nativo di Telegram
  var cmdUrl = "https://api.telegram.org/bot" + BOT_TOKEN + "/setMyCommands";
  var commandsList = [
    { command: "comandi", description: "Elenco completo di tutti i comandi" },
    { command: "budget", description: "Riepilogo budget, categorie e totali" },
    { command: "nuovoabbonamento", description: "Aggiungi un abbonamento guidato" },
    { command: "nuovarata", description: "Aggiungi un finanziamento a rate a step" },
    { command: "piani", description: "Mostra rate e abbonamenti attivi" },
    { command: "ultime", description: "Mostra le ultime 5 spese registrate" },
    { command: "elimina", description: "Cancella ultima spesa o per ID" },
    { command: "annulla", description: "Annulla procedura in corso" }
  ];
  UrlFetchApp.fetch(cmdUrl, {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify({ commands: commandsList }),
    muteHttpExceptions: true
  });
  
  // 2. Imposta il Webhook con drop_pending_updates per ripulire la coda
  var whUrl = "https://api.telegram.org/bot" + BOT_TOKEN + "/setWebhook?url=" + encodeURIComponent(webAppUrl) + "&drop_pending_updates=true";
  var response = UrlFetchApp.fetch(whUrl);
  Logger.log("Risposta setWebhook: " + response.getContentText());
  
  // 3. Inizializza i 3 fogli
  getOrCreateSheet(SHEET_SPESE);
  getOrCreateSheet(SHEET_PIANI);
  updateSummarySheet();
}

function cleanupDuplicateRows() {
  var sheet = getOrCreateSheet(SHEET_SPESE);
  var lastRow = sheet.getLastRow();
  if (lastRow <= 2) return;
  
  var data = sheet.getRange(2, 1, lastRow - 1, 7).getValues();
  var rowsToDelete = [];
  var seen = {};
  
  for (var i = 0; i < data.length; i++) {
    var r = data[i];
    var dStr = (r[1] instanceof Date) ? Utilities.formatDate(r[1], Session.getScriptTimeZone(), "yyyy-MM-dd") : String(r[1]).trim();
    var amt = parseFloat(r[2]) || 0;
    var desc = String(r[4] || "").trim().toLowerCase();
    var key = dStr + "_" + amt.toFixed(2) + "_" + desc;
    if (seen[key]) {
      rowsToDelete.push(i + 2);
    } else {
      seen[key] = true;
    }
  }
  
  for (var k = rowsToDelete.length - 1; k >= 0; k--) {
    sheet.deleteRow(rowsToDelete[k]);
  }
  updateSummarySheet();
  Logger.log("Rimosse " + rowsToDelete.length + " righe duplicate!");
}
