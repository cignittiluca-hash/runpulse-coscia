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

1. Quando corri con l'**Apple Watch**, usa l'app che preferisci:
   - L'app nativa **Allenamento (Workout)** di Apple
   - L'app **Strava** su Apple Watch
   - **WorkOutDoors** o **Nike Run Club**
2. Se usi l'app Allenamento nativa di Apple, attiva la sincronizzazione automatica verso Strava:
   - Apri l'app **Strava** sull'iPhone → **Profilo** → **Impostazioni (⚙️)** → **Applicazioni, servizi e dispositivi** → **Salute** → attiva l'invio automatico a Strava.
3. In **RunPulse**:
   - Vai nella scheda **Connessioni**.
   - Segui i 3 passaggi per inserire Client ID e Client Secret di Strava (si creano in 1 minuto su `strava.com/settings/api`).
   - Clicca **Salva e Connetti Strava**. Tutte le tue corse compariranno in RunPulse con i parziali al km, zone cardio, passo medio, TRIMP, cadenza ed efficienza.

---

## ⌚ 3. Come sincronizzare i dati di Salute & Sonno (Apple Watch → RunPulse)

Apple Watch raccoglie ogni notte e durante il giorno metriche fondamentali:
- **HRV (Variabilità Frequenza Cardiaca)** in millisecondi (SDNN)
- **Frequenza Cardiaca a Riposo** (RHR)
- **Sonno e Fasi** (Sonno Profondo, REM, Sonno Base/Core, Veglia)
- **Cardio Fitness** (stima del VO2 Max calcolata da Apple)
- **Anelli Attività** (Calorie Movimento, Minuti Esercizio, Ore in Piedi, Passi)

### Metodo 1: Comando Rapido su iPhone (Automatico al 100%)
1. Nell'app RunPulse, vai su **Apple Watch** e clicca **📲 Sincronizza da iPhone**:
   - Copia il tuo **Indirizzo Webhook** e il tuo **Token di sicurezza**.
2. Sul tuo iPhone, apri l'app nativa **Comandi Rapidi (Shortcuts)**:
   - Crea un nuovo comando rapido che legge da Apple Salute: *Variabilità FC*, *FC a riposo*, *Sonno*.
   - Inserisci l'azione **Ottieni contenuti dall'URL** con metodo **POST**, inviando il JSON con il tuo token.
3. **Automazione mattutina**:
   - Nella scheda **Automazioni** di Comandi Rapidi, crea: *"Quando disattivo la sveglia al mattino"* → esegui il comando rapido.
   - Ogni mattina i dati del tuo sonno e del recupero saranno già sincronizzati e Calippo saprà già se consigliarti di spingere o riposare!

### Metodo 2: Inserimento / Check-in Rapido Manuale
Se non hai ancora creato il comando rapido o vuoi correggere al volo un dato:
- Nella scheda **Apple Watch**, clicca su **✍️ Registra / Modifica Oggi**: puoi inserire in 5 secondi sonno, HRV e battito a riposo.

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
