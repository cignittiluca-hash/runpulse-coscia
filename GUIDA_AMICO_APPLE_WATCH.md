# RunPulse (Apple Watch & Strava Edition) — Guida per l'Amico 🏃⌚

Benvenuto in **RunPulse**! Questa è la tua app personale di corsa su strada e recupero, con **Calippo AI** come tuo coach personale, progettata appositamente per chi corre con **Apple Watch** e sincronizza su **Strava**.

Tutti i tuoi dati restano **privati sul tuo server** (locale o cloud gratuito), senza costi di abbonamento (0€ per sempre).

---

## 🚀 1. Come avviare l'app

### Opzione A: Sul tuo computer (Mac, Windows con WSL, o Linux)
1. Apri il Terminale nella cartella di RunPulse:
   ```bash
   cd runpulse-applewatch
   ./start.sh
   ```
2. Apri nel browser: **`http://localhost:8000`**
3. Da iPhone collegato allo stesso Wi-Fi di casa, apri l'indirizzo mostrato nel terminale (es. `http://192.168.1.xxx:8000`).

---

### Opzione B: Online 24/7 Gratis (funziona anche a computer spento, 0€)
Se vuoi usarla ovunque dal tuo iPhone anche quando il computer è spento:
1. **Database gratuito**: Registrati gratis su **[neon.tech](https://neon.tech)** (nessuna carta di credito) e copia la tua `Connection string` (`postgresql://...`).
2. **Carica su GitHub**: Crea un repository **Privato** su GitHub con questa cartella.
3. **Deploy su Render**: Vai su **[render.com](https://render.com)** → New **Web Service** → collega il tuo repo privato (`Runtime: Docker`, piano **Free**).
   - Nelle Environment Variables imposta:
     - `DATABASE_URL` = stringa copiata da Neon
     - `RUNPULSE_ACCESS_PASSWORD` = un tuo PIN numerico (es. `4829`) per proteggere l'app online
     - `RUNPULSE_SECRET_SALT` = una frase segreta casuale
4. In 2 minuti la tua app sarà online con link HTTPS sicuro (es. `https://tua-app.onrender.com`).

---

## 🏃 2. Come sincronizzare le corse (Apple Watch → Strava)

> 💡 **SERVE STRAVA PRIME O UN ABBONAMENTO A PAGAMENTO?**
> **ASSOLUTAMENTE NO!** Non serve Strava Prime né alcun abbonamento a pagamento.
> L'account **gratuito al 100%** di Strava è tutto ciò che serve. L'accesso alle API per sincronizzare le tue attività personali e il collegamento tra l'app Allenamento dell'Apple Watch e l'app Strava su iPhone sono completamente gratuiti per sempre (0€).

1. Quando corri con l'**Apple Watch**, usa l'app che preferisci:
   - L'app nativa **Allenamento (Workout)** di Apple
   - L'app **Strava** su Apple Watch
   - **WorkOutDoors** o **Nike Run Club**
2. Se usi l'app Allenamento nativa di Apple, attiva la sincronizzazione automatica verso Strava (gratuita):
   - Apri l'app **Strava** sull'iPhone → **Profilo** → **Impostazioni (⚙️)** → **Applicazioni, servizi e dispositivi** → **Salute** → attiva l'invio automatico a Strava.
3. In **RunPulse**:
   - Vai nella scheda **Connessioni**.
   - Segui i passaggi per inserire Client ID e Client Secret di Strava (si creano gratis in 1 minuto su `strava.com/settings/api`).
   - Clicca **Salva e Connetti Strava**. Tutte le tue corse compariranno in RunPulse con i parziali al km, zone cardio, passo medio, TRIMP, cadenza ed efficienza.

---

## ⌚ 3. Come sincronizzare i dati di Salute & Sonno (Apple Watch → RunPulse)

Apple Watch raccoglie ogni notte e durante il giorno metriche fondamentali:
- **HRV (Variabilità Frequenza Cardiaca)** in millisecondi (SDNN)
- **Frequenza Cardiaca a Riposo** (RHR)
- **Sonno e Fasi** (Sonno Profondo, REM, Sonno Base/Core, Veglia)
- **Cardio Fitness** (stima del VO2 Max calcolata da Apple)
- **Anelli Attività** (Calorie Movimento, Minuti Esercizio, Ore in Piedi, Passi)

Hai **due metodi semplicissimi** a disposizione:

---

### METODO A: Comando Rapido su iPhone (Semplificato, 1 sola chiamata URL)
*(Non serve più creare complicati dizionari JSON! Ora basta una semplice chiamata URL GET)*

1. **Prendi i dati da RunPulse**:
   - Vai nella scheda **Apple Watch** o **Connessioni** in RunPulse.
   - Copia il tuo **Indirizzo Webhook** (es. `https://tuo-dominio.onrender.com/api/apple-health/sync` o `http://192.168.1.xxx:8000/api/apple-health/sync`) e il tuo **Token**.
   - ⚠️ *IMPORTANTE*: Se usi RunPulse sul computer di casa, non usare mai `localhost` sull'iPhone (l'iPhone cercherebbe se stesso!). Usa l'indirizzo IP locale mostrato nel terminale (es. `192.168.1.xxx`) o il link HTTPS di Render.

2. **Crea il comando rapido su iPhone**:
   - Apri l'app nativa **Comandi Rapidi (Shortcuts)** → tocca il **+** in alto a destra.
   - Assegna un nome, ad esempio: `Sincronizza RunPulse`.
   - Aggiungi queste azioni in ordine:
     1. **Cerca campioni di salute**:
        - Tipo di campione: *Frequenza cardiaca a riposo*
        - Ordina per: *Data di fine*
        - Ordine: *Dal più recente al meno recente*
        - Limite: *1 campione*
     2. **Cerca campioni di salute**:
        - Tipo di campione: *Variabilità della frequenza cardiaca*
        - Ordina per: *Data di fine*
        - Ordine: *Dal più recente al meno recente*
        - Limite: *1 campione*
     3. **Cerca campioni di salute**:
        - Tipo di campione: *Sonno*
        - Filtro: *Data di inizio nelle ultime 24 ore*
        - Valore: *Nella fase sonno* (oppure Somma durata)
     4. **Ottieni contenuti dall'URL**:
        - Incolla l'URL includendo i parametri direttamente:
          ```text
          https://tuo-link/api/apple-health/sync?hrv=[Variabilità]&rhr=[Frequenza]&sleep=[Sonno]&token=TUO_TOKEN
          ```
        - Metodo: **GET** (o POST)
   - Tocca **Esegui (▶️)** per provarlo: RunPulse gestisce automaticamente virgole, decimali italiani e unità di misura!

3. **Automazione mattutina (100% automatica)**:
   - Nell'app Comandi Rapidi, tocca la tab in basso **Automazione** → **Nuova automazione (+)**.
   - Scegli **Quando la sveglia viene interrotta** (o a un orario fisso come le 08:00).
   - Seleziona *Esegui immediatamente* (senza chiedere conferma).
   - Imposta l'azione: *Esegui comando rapido* → seleziona `Sincronizza RunPulse`.
   - Ogni mattina troverai il recupero pronto e Calippo saprà già consigliarti l'allenamento ideale!

---

### METODO B: App Gratuita "Health Auto Export" (Zero Comandi Rapidi, 100% Background)
Se non vuoi usare l'app Comandi Rapidi, puoi usare l'app ufficiale consigliata su App Store:

1. Scarica dall'App Store di iPhone l'app gratuita **[Health Auto Export](https://apps.apple.com/app/health-auto-export-csv-gpx/id1115569107)**.
2. Apri l'app e consenti l'accesso ai dati di Apple Salute.
3. Vai in **Automations** → **REST API / Webhook**:
   - **URL**: il tuo indirizzo webhook (es. `https://tuo-dominio.onrender.com/api/apple-health/sync`).
   - **Headers**: aggiungi `x-apple-health-token` con il tuo token.
   - **Metrics**: seleziona *Heart Rate Variability (SDNN)*, *Resting Heart Rate*, *Sleep Analysis*, *Step Count*.
   - **Export Frequency**: Background / Daily.
4. Fatto! L'app invierà i dati da sola in background ogni giorno senza che tu debba aprire nulla.

---

### METODO C: Check-in Manuale Rapido
Se vuoi registrare al volo sonno o battiti a mano:
- Nella scheda **Apple Watch**, tocca **✍️ Registra / Modifica Oggi**: compila in 5 secondi ed è fatto.

---

### ⚠️ Risoluzione problemi (Se il collegamento non risponde)
1. **Errore di connessione / Timeout**: Stai usando `localhost` dall'iPhone? Sostituiscilo con l'IP Wi-Fi del computer o con l'indirizzo Render online.
2. **Permessi Apple Salute negati**: Su iPhone vai in **Impostazioni** → **Salute** → **Accesso dati e dispositivi** → apri **Comandi Rapidi** (o *Health Auto Export*) e assicurati che tutte le levette siano verdi.
3. **Verifica rapida**: Apri Safari su iPhone e vai all'indirizzo `https://tuo-link/api/apple-health/sync`. Se vedi il messaggio `"Connessione Apple Health a RunPulse riuscita!"`, l'iPhone raggiunge correttamente il server!

---

## 🐱 4. Come attivare Calippo AI (Gratis)

**Calippo** è il tuo coach personale con intelligenza artificiale integrata, capace di analizzare le tue corse, il recupero e le proiezioni gara.

1. Vai su **[Google AI Studio](https://aistudio.google.com/apikey)** e accedi con il tuo account Google.
2. Clicca **Create API Key** (è **gratuita al 100% per sempre**, senza richiedere carta di credito).
3. Incolla la chiave in **Connessioni → Coach AI Google Gemini** e clicca **Salva**.
4. Ora puoi aprire la chat di **Calippo AI** e chiedergli qualsiasi cosa:
   - *"Cosa mi consigli di fare oggi in base al mio recupero?"*
   - *"Come è andata la mia ultima corsa?"*
   - *"Mi prepari una tabella per scendere sotto i 45 minuti nei 10 km?"*

---

## 📱 5. Come installare RunPulse su iPhone come un'App Vera (PWA)

1. Apri il link della tua app su **Safari dell'iPhone**.
2. Tocca l'icona **Condividi (`↑`)** in basso al centro su Safari.
3. Scorri verso il basso e tocca **Aggiungi alla schermata Home**.
4. Tocca **Aggiungi** in alto a destra.

Ora troverai l'icona di **RunPulse** sulla schermata Home del tuo iPhone: si apre a schermo intero senza barre del browser, fluida e reattiva come un'app nativa dell'App Store!

---

Buone corse! 🏃💨
