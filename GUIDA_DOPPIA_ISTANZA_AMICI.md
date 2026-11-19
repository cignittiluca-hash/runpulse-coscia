# RunPulse (Garmin + Whoop Edition) — Guida Completa per i Tuoi Due Amici 🏃⚡

Benvenuto nella versione **RunPulse Garmin & Whoop**!  
Questa edizione unisce il meglio dei due mondi:
* **Garmin Connect**: tracciamento corse GPS, passo, cadenza, **Body Battery** (0–100), stress e sonno;
* **Whoop 4.0**: **Recovery Score** (0–100% Verde/Giallo/Rosso), **Day Strain** (0–21), **HRV RMSSD** notturno e **Debito di Sonno**;
* **Strava**: sincronizzazione completa di tutte le attività storiche con parziali km e carico TRIMP;
* **Coach Calippo AI**: intelligenza artificiale con Gemini 3.8 Flash che analizza insieme Garmin, Whoop e Strava.

---

## 🚀 Come Pubblicare 2 App Indipendenti (Una per ciascun amico, 0€ per sempre)

Poiché i dati di salute (credenziali Garmin, account Whoop e corse Strava) sono personali e privati, la soluzione migliore e sicura al 100% è creare **due servizi gratuiti su Render** (uno per amico):
* Amico 1: `https://runpulse-nome1.onrender.com` (con suo PIN personale)
* Amico 2: `https://runpulse-nome2.onrender.com` (con suo PIN personale)

### Passo 1: Carica questa cartella su un repo GitHub privato
1. Crea un repository privato su GitHub (es. `runpulse-pro`).
2. Dal terminale del Mac:
   ```bash
   cd /Users/lucacignitti/.gemini/antigravity/scratch/runpulse-garmin-whoop
   git remote add origin https://github.com/cignittiluca-hash/runpulse-pro.git
   git branch -M main
   git push -u origin main
   ```

### Passo 2: Database Neon (0€, 30 secondi)
1. Vai su [neon.tech](https://neon.tech) e crea due database (o due branch):
   * `db_amico1` → copia la connection string
   * `db_amico2` → copia la connection string

### Passo 3: Due Web Service su Render (1 minuto ciascuno)
1. Su Render clicca **New +** → **Web Service** → collega `runpulse-pro`.
   * Nome: `runpulse-amico1`
   * Environment Variables:
     * `DATABASE_URL`: stringa di `db_amico1`
     * `RUNPULSE_ACCESS_PASSWORD`: PIN per amico 1 (es. `1111`)
     * `STRAVA_CLIENT_ID`: `298398`
     * `STRAVA_CLIENT_SECRET`: `fad5d4cc0dfb53e143f7ae1c2df1d0df854d0677`
     * `GEMINI_API_KEY`: tua chiave Gemini gratuita
2. Ripeti per il secondo amico (`runpulse-amico2`, PIN `2222`, stringa di `db_amico2`).

---

## 📱 Messaggio WhatsApp pronto per ciascun amico

> Ciao! 🏃🔋  
> Ti ho configurato la tua app personale **RunPulse** per la corsa e il recupero, con integrazione per **Garmin Connect** e **Whoop 4.0**, e il coach **Calippo AI** integrato!
> 
> Gira sul cloud ed è attiva 24/7, quindi la usi direttamente da iPhone anche a computer spento.
> 
> 🔗 **Il tuo link:** `https://runpulse-tuonome.onrender.com`  
> 🔑 **PIN:** `xxxx`
> 
> **Come iniziare in 30 secondi:**
> 1. **Metti l'icona su iPhone**: apri il link con **Safari**, tocca **Condividi** (`↑`) e scegli **"Aggiungi a schermata Home"**.
> 2. **Collega Strava**: entra nell'app con il PIN, vai su **Connessioni** e tocca **"Connetti Strava"** (1 tap).
> 3. **Collega Garmin**: inserisci email e password di Garmin Connect per sincronizzare Body Battery, Stress e Sonno.
> 4. **Whoop 4.0**: nella scheda **Recupero** puoi registrare in 5 secondi il tuo Recovery Score e Day Strain con il pulsante **"✍️ Registra Whoop Oggi"** (o autorizzare le API ufficiali).
> 5. **Coach Calippo**: chiedi a Calippo se oggi è il giorno per spingere o riposare in base al tuo Recovery Whoop e alla Body Battery Garmin!
