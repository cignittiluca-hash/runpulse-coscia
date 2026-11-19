# RunPulse — Apple Watch & Strava Personal Running Coach 🏃⌚

RunPulse è un'applicazione web progressiva (PWA per iPhone e desktop) open-source e gratuita, pensata per chi corre con **Apple Watch** e sincronizza i propri allenamenti su **Strava**.

Dispone di un motore scientifico di recupero e carico (CTL/ATL/TSB, VDOT Jack Daniels, Prontezza Atletica basata su HRV SDNN e sonno), generatore di piani gara periodizzati e un coach conversazionale personalizzato (**Calippo AI**, alimentato da Google Gemini 3.8 Flash con Thinking).

---

## ⚡ Caratteristiche principali

1. **Sincronizzazione Corse Strava (Apple Watch)**:
   - OAuth2 nativo con importazione automatica e manuale di tutto lo storico delle corse.
   - Scomposizione chilometrica con passo, FC, dislivello, stima deriva cardiaca (cardiac drift) ed Efficiency Factor (EF).
   - Calcolo del carico Banister TRIMP e distribuzione zone cardio Z1–Z5.
2. **Ecosistema Apple Watch & Apple Health**:
   - Ingestione webhook sicura tramite **Comandi Rapidi (iOS Shortcuts)** o app come Health Auto Export.
   - Monitoraggio Sonno con stadi nativi watchOS: Sonno Profondo, Fase REM, Sonno Base (Core) e Veglia.
   - Tracciamento della variabilità della frequenza cardiaca (**HRV SDNN notturna**) con baseline dinamica a 14 giorni.
   - Monitoraggio Frequenza Cardiaca a Riposo (RHR), Cardio Fitness (VO2 Max stimato da Apple Watch), Anelli Movimento/Esercizio/In Piedi e Passi.
3. **Prontezza Atletica Scientifica (Readiness 0–100)**:
   - Punteggio trasparente ponderato che combina HRV, RHR, qualità del sonno e bilanciamento del carico di allenamento (TSB / ACWR).
4. **Calippo AI Coach**:
   - Assistente virtuale multi-turno con memoria persistente nel database.
   - Analizza la condizione atletica complessiva in tempo reale e risponde in italiano naturale, fornendo consigli tattici su allenamento e recupero.
5. **Piani Gara Periodizzati Dinamici**:
   - Generazione tabelle per 5K, 10K, Mezza Maratona e Maratona con ritmi calcolati su VDOT.
   - Adattamento dinamico degli allenamenti in base al punteggio di recupero calcolato dall'Apple Watch.
6. **Architettura Cloud & Locale 100% Gratuita**:
   - Database dual-engine: SQLite in locale, PostgreSQL persistente su cloud (es. Neon.tech gratuito).
   - Pronto per il deploy 24/7 su Render.com Free.
   - Backup & Migrazione in 1 click (JSON).

---

## 🚀 Avvio Rapido

```bash
# Avvio in locale (richiede Python 3.9+)
./start.sh
```

Apri `http://localhost:8000` nel tuo browser.

Per tutte le istruzioni dettagliate (incluso il deploy su cloud gratuito e la configurazione del comando rapido su iPhone), consulta la guida dedicata:
👉 **[GUIDA_AMICO_APPLE_WATCH.md](GUIDA_AMICO_APPLE_WATCH.md)**
