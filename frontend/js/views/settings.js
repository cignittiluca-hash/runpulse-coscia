import { api, escapeHtml, formatPace, showToast } from "../api.js";

export async function renderSettings(container, refreshSidebarStatus, isStale = () => false) {
  container.innerHTML = `<div class="loading-state">Caricamento impostazioni...</div>`;
  let s;
  let mobile = { wifi_url: null, tailscale_url: null, local_url: "http://localhost:8000" };
  try {
    [s, mobile] = await Promise.all([api.getSettings(), api.getMobileInfo().catch(() => mobile)]);
  } catch (err) {
    if (isStale()) return;
    container.innerHTML = `<div class="card empty-state">Errore: ${escapeHtml(err.message)}</div>`;
    return;
  }
  if (isStale()) return;

  const threshPaceStr = formatPace(s.threshold_pace_sec);
  const preferredMobileUrl = mobile.tailscale_url || mobile.wifi_url || mobile.local_url;

  container.innerHTML = `
    <!-- IPHONE MOBILE APP & 4G/5G ACCESS -->
    <section class="card" style="border-color:rgba(0,180,216,0.4);">
      <div class="card-header">
        <div>
          <div class="card-title">📱 App iPhone (Schermata Home + 4G/5G Ovunque — Gratis)</div>
          <div class="subtitle">Installa RunPulse + Calippo sulla Home del tuo iPhone e accedi anche fuori casa in 4G/5G</div>
        </div>
        <span class="pill ${mobile.tailscale_url ? "pill-green" : "pill-cyan"}">
          ${mobile.tailscale_url ? "4G/5G TAILSCALE ATTIVO" : "PRONTA PER IPHONE"}
        </span>
      </div>

      <div class="grid-2" style="align-items:start;">
        <div style="display:flex;flex-direction:column;gap:12px;">
          ${
            mobile.tailscale_url
              ? `<div>
                  <div style="font-size:0.78rem;color:#34d399;font-weight:700;margin-bottom:4px;">🌐 LINK 4G/5G OVUNQUE (Tailscale rilevato ✓)</div>
                  <div class="url-copy-box">
                    <span>${escapeHtml(mobile.tailscale_url)}</span>
                    <button class="btn btn-ghost btn-sm" data-copy-url="${escapeHtml(mobile.tailscale_url)}">Copia</button>
                  </div>
                </div>`
              : ""
          }
          ${
            mobile.wifi_url
              ? `<div>
                  <div style="font-size:0.78rem;color:#38bdf8;font-weight:700;margin-bottom:4px;">📶 LINK WI-FI DI CASA (apri da Safari su iPhone)</div>
                  <div class="url-copy-box">
                    <span>${escapeHtml(mobile.wifi_url)}</span>
                    <button class="btn btn-ghost btn-sm" data-copy-url="${escapeHtml(mobile.wifi_url)}">Copia</button>
                  </div>
                </div>`
              : ""
          }

          <div class="guide-steps" style="margin-bottom:0;">
            <strong>Come usarla su iPhone anche in 4G/5G (100% gratis, zero costi):</strong>
            <ol>
              <li>Installa l'app gratuita <strong>Tailscale</strong> sul Mac (<a href="https://tailscale.com/download/mac" target="_blank" style="color:#38bdf8;">tailscale.com</a>) e sull'<strong>iPhone</strong> (App Store), accedendo con lo stesso account Apple/Google.</li>
              <li>Apri l'indirizzo Tailscale (<code>http://100.x.y.z:8000</code>) su <strong>Safari su iPhone</strong> (funziona ovunque in 4G/5G in modo criptato!).</li>
              <li>Su Safari tocca <strong>Condividi (↑)</strong> → <strong>Aggiungi alla schermata Home</strong>: avrai l'icona RunPulse a schermo intero come un'app nativa!</li>
            </ol>
          </div>
        </div>

        <div style="display:flex;flex-direction:column;gap:14px;">
          <div style="display:flex;gap:16px;align-items:center;flex-wrap:wrap;background:rgba(0,0,0,0.22);padding:14px;border-radius:14px;border:1px solid var(--border);">
            <img
              src="/api/qr.svg?data=${encodeURIComponent(preferredMobileUrl)}"
              alt="QR Code iPhone"
              style="width:140px;height:140px;border-radius:12px;border:4px solid #ffffff;background:#ffffff;display:block;"
            />
            <div style="flex:1;min-width:170px;">
              <div style="font-weight:700;font-size:0.92rem;margin-bottom:4px;">📸 Scansiona con la fotocamera iPhone</div>
              <p class="subtitle" style="font-size:0.8rem;">
                Inquadra il QR code per aprire subito <code>${escapeHtml(preferredMobileUrl)}</code> su Safari del tuo iPhone.
              </p>
            </div>
          </div>

          <form id="pin-form" style="padding:14px;border-radius:14px;background:rgba(255,255,255,0.03);border:1px solid var(--border);">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
              <strong style="font-size:0.88rem;">🔒 Protezione PIN / Password Remota</strong>
              <span class="pill ${s.app_password_enabled ? "pill-green" : "pill-muted"}">
                ${s.app_password_enabled ? "ATTIVA" : "DISATTIVA"}
              </span>
            </div>
            <div style="display:flex;gap:8px;flex-wrap:wrap;">
              <input class="input" id="app-pin-input" type="password" placeholder="${s.app_password_enabled ? "Nuovo PIN/Password" : "Imposta PIN (es. 4829)"}" style="flex:1;min-width:160px;" />
              <button class="btn btn-garmin btn-sm" type="submit">Salva PIN</button>
              ${s.app_password_enabled ? `<button class="btn btn-danger btn-sm" type="button" id="btn-clear-pin">Rimuovi</button>` : ""}
            </div>
          </form>
        </div>
      </div>
    </section>

    <div class="grid-2">
      <!-- STRAVA CONNECTION -->
      <section class="card" style="border-color:${s.strava_connected ? "rgba(16,185,129,0.4)" : "rgba(252,76,2,0.35)"};">
        <div class="card-header">
          <div>
            <div class="card-title">🟠 Strava (Sync Automatico Allenamenti)</div>
            <div class="subtitle">API ufficiale OAuth2 — carica automaticamente corse, parziali e FC</div>
          </div>
          <span class="pill ${s.strava_connected ? "pill-green" : "pill-orange"}">
            ${s.strava_connected ? "CONNESSO" : "DA COLLEGARE"}
          </span>
        </div>

        <div class="guide-steps">
          <strong>Come collegare Strava in 60 secondi:</strong>
          <ol>
            <li>Apri <a href="https://www.strava.com/settings/api" target="_blank" style="color:#fc4c02;">strava.com/settings/api</a> ed entra col tuo account.</li>
            <li>Crea la tua app personale (Nome: <code>RunPulse</code>, Sito: <code>http://localhost:8000</code>, <strong>Authorization Callback Domain</strong>: <code>localhost</code>).</li>
            <li>Copia qui sotto <strong>Client ID</strong> e <strong>Client Secret</strong> e clicca <em>Salva e Connetti Strava</em>.</li>
          </ol>
        </div>

        <form id="strava-form" class="form-grid">
          <div class="form-field">
            <label for="strava-client-id">Strava Client ID</label>
            <input class="input" id="strava-client-id" value="${escapeHtml(s.strava_client_id)}" placeholder="es. 123456" />
          </div>
          <div class="form-field">
            <label for="strava-client-secret">Strava Client Secret ${s.strava_has_secret ? "(salvato ✓)" : ""}</label>
            <input class="input" id="strava-client-secret" type="password" placeholder="${s.strava_has_secret ? "•••••••• (lascia vuoto per mantenere)" : "Incolla Client Secret"}" />
          </div>
          <div class="form-field full" style="flex-direction:row;gap:10px;flex-wrap:wrap;">
            <button class="btn btn-primary" type="submit" id="btn-strava-connect">
              ${s.strava_connected ? "🔄 Ricollega Strava" : "🔗 Salva e Connetti Strava"}
            </button>
            ${
              s.strava_connected
                ? `<button class="btn btn-ghost" type="button" id="btn-strava-sync">↻ Sincronizza 60 giorni</button>
                   <button class="btn btn-ghost" type="button" id="btn-strava-sync-all">📥 Importa Tutto Storico</button>
                   <button class="btn btn-danger" type="button" id="btn-strava-disconnect">Disconnetti</button>`
                : ""
            }
          </div>
        </form>
        ${
          s.strava_connected
            ? `<div class="subtitle" style="margin-top:12px;">Atleta: <strong>${escapeHtml(s.strava_athlete_name)}</strong> · Ultimo sync: ${escapeHtml(s.strava_last_sync || "mai")}</div>`
            : ""
        }
      </section>

      <!-- GARMIN CONNECTION -->
      <section class="card" style="border-color:${s.garmin_connected ? "rgba(16,185,129,0.4)" : "rgba(0,180,216,0.35)"};">
        <div class="card-header">
          <div>
            <div class="card-title">🔵 Garmin Connect (Stress, HRV, Body Battery, Sonno)</div>
            <div class="subtitle">Accesso sicuro locale con token OAuth salvati solo sul tuo Mac</div>
          </div>
          <span class="pill ${s.garmin_connected ? "pill-green" : "pill-cyan"}">
            ${s.garmin_connected ? "CONNESSO" : "DA COLLEGARE"}
          </span>
        </div>

        <div class="guide-steps">
          <strong>Sicurezza & Privacy:</strong>
          <p style="margin-top:4px;">
            La password viene usata una sola volta per ottenere i token di sessione Garmin in <code>data/garmin_tokens/</code> e <strong>non viene mai salvata</strong> nel database. Supporta anche verifica a 2 fattori (MFA/OTP).
          </p>
        </div>

        <form id="garmin-form" class="form-grid">
          <div class="form-field">
            <label for="garmin-email">Email Garmin Connect</label>
            <input class="input" id="garmin-email" type="email" value="${escapeHtml(s.garmin_email)}" placeholder="tua@email.com" required />
          </div>
          <div class="form-field">
            <label for="garmin-password">Password Garmin</label>
            <input class="input" id="garmin-password" type="password" placeholder="Password Garmin Connect" required />
          </div>
          <div class="form-field full" style="flex-direction:row;gap:10px;flex-wrap:wrap;">
            <button class="btn btn-garmin" type="submit" id="btn-garmin-login">
              ${s.garmin_connected ? "🔄 Aggiorna Sessione Garmin" : "⌚ Connetti Garmin Connect"}
            </button>
            ${
              s.garmin_connected
                ? `<button class="btn btn-ghost" type="button" id="btn-garmin-sync">↻ Sincronizza 14 giorni</button>
                   <button class="btn btn-danger" type="button" id="btn-garmin-disconnect">Disconnetti</button>`
                : ""
            }
          </div>
        </form>

        <!-- MFA Box (shown dynamically if Garmin requests OTP) -->
        <form id="garmin-mfa-form" style="display:none;margin-top:14px;padding:14px;border-radius:12px;background:rgba(0,180,216,0.12);border:1px solid rgba(0,180,216,0.35);">
          <div style="font-weight:700;margin-bottom:6px;">🔐 Codice Verifica Garmin (MFA/OTP)</div>
          <p class="subtitle" style="margin-bottom:10px;">Inserisci il codice a 6 cifre ricevuto via email o SMS da Garmin.</p>
          <div style="display:flex;gap:10px;">
            <input class="input" id="garmin-mfa-code" placeholder="es. 123456" />
            <button class="btn btn-garmin" type="submit" id="btn-garmin-mfa-submit">Verifica</button>
          </div>
        </form>

        ${
          s.garmin_connected
            ? `<div class="subtitle" style="margin-top:12px;">Profilo: <strong>${escapeHtml(s.garmin_display_name)}</strong> · Ultimo sync: ${escapeHtml(s.garmin_last_sync || "mai")}</div>`
            : ""
        }
      </section>

      <!-- WHOOP 4.0 REAL-TIME CONNECTION -->
      <section class="card" style="border-color:${s.whoop_connected ? "rgba(16,185,129,0.4)" : "rgba(245,158,11,0.4)"};">
        <div class="card-header">
          <div>
            <div class="card-title">🟡 Whoop 4.0 (Recupero & Strain in Tempo Reale)</div>
            <div class="subtitle">Sincronizzazione automatica continua di Recovery Score (%), Day Strain e Sonno</div>
          </div>
          <span class="pill ${s.whoop_connected ? "pill-green" : "pill-muted"}">
            ${s.whoop_connected ? "COLLEGATO IN TEMPO REALE" : "DA COLLEGARE"}
          </span>
        </div>

        <div style="margin-top:14px;">
          ${
            s.whoop_connected
              ? `<div style="background:rgba(16,185,129,0.1);border:1px solid rgba(16,185,129,0.3);border-radius:10px;padding:12px;margin-bottom:12px;">
                   <div style="color:#10b981;font-weight:700;display:flex;align-items:center;gap:8px;">
                     <span>✓</span> Whoop è connesso! I dati di recupero e sforzo arrivano in automatico in tempo reale.
                   </div>
                   <div style="font-size:0.8rem;color:#93a1be;margin-top:4px;">
                     Ultimo aggiornamento: <strong>${escapeHtml(s.whoop_last_sync || "in attesa del primo dato")}</strong>
                   </div>
                 </div>
                 <div style="display:flex;gap:10px;flex-wrap:wrap;">
                   <button class="btn btn-ghost btn-sm" id="btn-whoop-sync-now" type="button">↻ Sincronizza Adesso</button>
                 </div>`
              : `<p style="color:#cbd5e1;font-size:0.9rem;margin-bottom:14px;line-height:1.5;">
                   Tocca il pulsante qui sotto per collegare il tuo account Whoop in 1 solo tap: i tuoi dati si aggiorneranno da soli ogni giorno in tempo reale!
                 </p>
                 <button class="btn btn-primary" id="btn-whoop-oauth-1tap" style="background:#f59e0b;color:#090c14;font-size:1rem;font-weight:700;padding:12px 22px;display:flex;align-items:center;gap:10px;border:none;">
                   <span style="font-size:1.25rem;">⚡</span> Connetti Whoop
                 </button>`
          }
        </div>
      </section>
    </div>

    <div class="grid-2">
      <!-- GEMINI AI -->
      <section class="card">
        <div class="card-header">
          <div>
            <div class="card-title">✨ Coach AI Google Gemini (Ibrido)</div>
            <div class="subtitle">Potenzia i consigli giornalieri, l'analisi delle corse e la chat coach</div>
          </div>
          <span class="pill ${s.gemini_configured ? "pill-violet" : "pill-muted"}">
            ${s.gemini_configured ? "ATTIVO" : "OPZIONALE"}
          </span>
        </div>

        <div class="guide-steps">
          Puoi ottenere una chiave API gratuita su <a href="https://aistudio.google.com/apikey" target="_blank" style="color:#c4b5fd;">Google AI Studio</a>.
          Anche senza chiave, RunPulse calcola comunque tutte le metriche scientifiche, readiness e piani gara in locale!
        </div>

        <form id="gemini-form" class="form-grid">
          <div class="form-field">
            <label for="gemini-key">Gemini API Key ${s.gemini_configured ? "(configurata ✓)" : ""}</label>
            <input class="input" id="gemini-key" type="password" placeholder="${s.gemini_configured ? "•••••••• (inserisci nuova per sostituire)" : "AIza..."}" />
          </div>
          <div class="form-field">
            <label for="gemini-model">Modello Gemini</label>
            <select class="select" id="gemini-model">
              <option value="gemini-3.8-flash" ${s.gemini_model === "gemini-3.8-flash" || s.gemini_model === "gemini-2.5-flash" ? "selected" : ""}>gemini-3.8-flash (Consigliato — Thinking + Free Tier)</option>
              <option value="gemini-3.5-flash-lite" ${s.gemini_model === "gemini-3.5-flash-lite" ? "selected" : ""}>gemini-3.5-flash-lite (Ultra-veloce — Free Tier)</option>
              <option value="gemini-3.8-pro" ${s.gemini_model === "gemini-3.8-pro" ? "selected" : ""}>gemini-3.8-pro (Ragionamento avanzato)</option>
            </select>
          </div>
          <div class="form-field full" style="flex-direction:row;justify-content:flex-end;gap:10px;">
            ${s.gemini_configured ? `<button class="btn btn-ghost" type="button" id="btn-test-gemini">🧪 Testa Gemini</button>` : ""}
            <button class="btn btn-ai" type="submit">Salva Impostazioni AI</button>
          </div>
        </form>
      </section>

      <!-- ATHLETE PROFILE & AUTO SYNC -->
      <section class="card">
        <div class="card-header">
          <div>
            <div class="card-title">🏃 Profilo Runner & Auto-Sync</div>
            <div class="subtitle">Parametri fisiologici usati per zone cardio, TRIMP e ritmi gara</div>
          </div>
        </div>

        <form id="profile-form" class="form-grid">
          <div class="form-field">
            <label for="prof-name">Nome</label>
            <input class="input" id="prof-name" value="${escapeHtml(s.athlete_name)}" />
          </div>
          <div class="form-field">
            <label for="prof-weekly">Obiettivo Km Settimanali</label>
            <input class="input" id="prof-weekly" type="number" step="1" value="${s.weekly_goal_km}" />
          </div>
          <div class="form-field">
            <label for="prof-maxhr">FC Massima (bpm)</label>
            <input class="input" id="prof-maxhr" type="number" value="${s.max_hr}" />
          </div>
          <div class="form-field">
            <label for="prof-rhr">FC a Riposo (bpm)</label>
            <input class="input" id="prof-rhr" type="number" value="${s.resting_hr}" />
          </div>
          <div class="form-field">
            <label for="prof-thresh">Passo Soglia (es. 4:35)</label>
            <input class="input" id="prof-thresh" value="${threshPaceStr}" placeholder="4:35" />
          </div>
          <div class="form-field">
            <label for="prof-sync-int">Intervallo Auto-Sync (minuti)</label>
            <input class="input" id="prof-sync-int" type="number" min="5" max="1440" value="${s.auto_sync_interval_min}" />
          </div>
          <div class="form-field full" style="flex-direction:row;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;">
            <label style="display:flex;align-items:center;gap:8px;cursor:pointer;color:#f3f6fc;">
              <input type="checkbox" id="prof-autosync" ${s.auto_sync_enabled ? "checked" : ""} />
              Sincronizza Strava & Garmin automaticamente in background
            </label>
            <button class="btn btn-primary" type="submit">Salva Profilo</button>
          </div>
        </form>
      </section>
    </div>

    <!-- CLOUD 24/7 MIGRATION & BACKUP -->
    <section class="card" style="border-color:rgba(16,185,129,0.35);">
      <div class="card-header">
        <div>
          <div class="card-title">☁️ Backup & Migrazione Cloud 24/7 (Mac Spento)</div>
          <div class="subtitle">
            Database attivo: <strong>${s.storage_backend === "postgresql" ? "PostgreSQL Cloud (Persistente ✓)" : "SQLite Locale (Mac)"}</strong> ·
            Esporta tutto dal Mac (corse Strava, Garmin, token OAuth, Calippo) e importalo sul tuo link Cloud in 1 click!
          </div>
        </div>
        <span class="pill ${s.storage_backend === "postgresql" ? "pill-green" : "pill-cyan"}">
          ${s.storage_backend === "postgresql" ? "CLOUD 24/7" : "LOCALE"}
        </span>
      </div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;">
        <a class="btn btn-garmin btn-sm" href="/api/backup/export" download="runpulse-backup.json">
          ⬇️ Esporta Backup Completo (.json)
        </a>
        <label class="btn btn-ghost btn-sm" style="cursor:pointer;">
          ⬆️ Importa Backup (.json)
          <input type="file" id="input-import-backup" accept="application/json,.json" style="display:none;" />
        </label>
      </div>
    </section>

    <!-- DEMO DATA UTILITIES -->
    <section class="card">
      <div class="card-header">
        <div>
          <div class="card-title">🧪 Modalità Anteprima & Dati Demo</div>
          <div class="subtitle">
            Database attuale: <strong>${s.data_counts.activities}</strong> allenamenti · <strong>${s.data_counts.garmin_days}</strong> giorni Garmin · <strong>${s.data_counts.race_goals}</strong> piani gara.
          </div>
        </div>
        <div style="display:flex;gap:10px;flex-wrap:wrap;">
          <button class="btn btn-ghost btn-sm" id="btn-seed-demo">✨ Carica 60g Dati Demo</button>
          <button class="btn btn-danger btn-sm" id="btn-clear-demo">🗑️ Rimuovi Solo Dati Demo</button>
        </div>
      </div>
    </section>
  `;

  // Copy mobile URL buttons
  container.querySelectorAll("[data-copy-url]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const url = btn.dataset.copyUrl;
      try {
        await navigator.clipboard.writeText(url);
        showToast("Link copiato negli appunti!", "success");
      } catch {
        showToast(url, "info");
      }
    });
  });

  // App PIN / Password protection
  document.getElementById("pin-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const val = document.getElementById("app-pin-input").value.trim();
    if (!val) {
      showToast("Inserisci un PIN o una password.", "error");
      return;
    }
    try {
      await api.updateSettings({ app_password: val });
      showToast("Protezione PIN attivata! Questo dispositivo resta sbloccato per 90 giorni.", "success");
      renderSettings(container, refreshSidebarStatus);
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  document.getElementById("btn-clear-pin")?.addEventListener("click", async () => {
    try {
      await api.updateSettings({ app_password: "__CLEAR__" });
      showToast("Protezione PIN rimossa.", "info");
      renderSettings(container, refreshSidebarStatus);
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  // Strava submit -> save credentials & redirect to Strava OAuth
  document.getElementById("strava-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const clientId = document.getElementById("strava-client-id").value.trim();
    const clientSecret = document.getElementById("strava-client-secret").value.trim();
    if (!clientId) {
      showToast("Inserisci lo Strava Client ID.", "error");
      return;
    }
    try {
      const payload = { strava_client_id: clientId };
      if (clientSecret) payload.strava_client_secret = clientSecret;
      await api.updateSettings(payload);
      const { auth_url } = await api.getStravaAuthUrl();
      window.location.href = auth_url;
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  document.getElementById("btn-strava-sync")?.addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    btn.textContent = "Sincronizzazione...";
    try {
      const res = await api.syncStrava(60);
      showToast(`Strava sincronizzato! ${res.synced_activities} attività caricate (${res.detailed_runs_fetched} dettagliate).`, "success");
      await refreshSidebarStatus();
      renderSettings(container, refreshSidebarStatus);
    } catch (err) {
      showToast(err.message, "error");
      btn.disabled = false;
      btn.textContent = "↻ Sincronizza 60 giorni";
    }
  });

  document.getElementById("btn-strava-sync-all")?.addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    btn.textContent = "Importazione storico...";
    try {
      const res = await api.syncStrava(0, true);
      showToast(`Storico completo Strava importato! ${res.synced_activities} attività caricate.`, "success");
      await refreshSidebarStatus();
      renderSettings(container, refreshSidebarStatus, isStale);
    } catch (err) {
      showToast(err.message, "error");
      btn.disabled = false;
      btn.textContent = "📥 Importa Tutto Storico";
    }
  });

  document.getElementById("btn-strava-disconnect")?.addEventListener("click", async () => {
    if (!confirm("Vuoi scollegare il tuo account Strava?")) return;
    try {
      await api.disconnectStrava();
      showToast("Strava disconnesso.", "info");
      await refreshSidebarStatus();
      renderSettings(container, refreshSidebarStatus, isStale);
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  // Garmin login + MFA handling
  document.getElementById("garmin-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = document.getElementById("btn-garmin-login");
    const email = document.getElementById("garmin-email").value.trim();
    const password = document.getElementById("garmin-password").value;
    btn.disabled = true;
    btn.textContent = "Accesso a Garmin...";
    try {
      const res = await api.loginGarmin(email, password);
      if (res.status === "mfa_required") {
        showToast(res.message, "info");
        document.getElementById("garmin-mfa-form").style.display = "block";
        document.getElementById("garmin-mfa-code").focus();
        btn.disabled = false;
        btn.textContent = "⌚ Connetti Garmin Connect";
        return;
      }
      showToast("Garmin Connect collegato! Avvio sincronizzazione 14 giorni...", "success");
      try {
        const sRes = await api.syncGarmin(14);
        showToast(`Sincronizzati ${sRes.days_synced} giorni Garmin (Stress, HRV, Sonno, Body Battery)!`, "success");
      } catch (syncErr) {
        showToast("Connesso, ma sync iniziale: " + syncErr.message, "info");
      }
      await refreshSidebarStatus();
      renderSettings(container, refreshSidebarStatus);
    } catch (err) {
      showToast(err.message, "error");
      btn.disabled = false;
      btn.textContent = "⌚ Connetti Garmin Connect";
    }
  });

  document.getElementById("garmin-mfa-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = document.getElementById("btn-garmin-mfa-submit");
    const code = document.getElementById("garmin-mfa-code").value.trim();
    if (!code) return;
    btn.disabled = true;
    btn.textContent = "Verifica...";
    try {
      await api.submitGarminMfa(code);
      showToast("MFA confermato! Sincronizzazione Garmin in corso...", "success");
      await api.syncGarmin(14);
      showToast("Dati Garmin importati con successo!", "success");
      await refreshSidebarStatus();
      renderSettings(container, refreshSidebarStatus);
    } catch (err) {
      showToast(err.message, "error");
      btn.disabled = false;
      btn.textContent = "Verifica";
    }
  });

  document.getElementById("btn-garmin-sync")?.addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    btn.textContent = "Sincronizzazione...";
    try {
      const res = await api.syncGarmin(14);
      showToast(`Garmin sincronizzato (${res.days_synced} giorni)!`, "success");
      await refreshSidebarStatus();
      renderSettings(container, refreshSidebarStatus);
    } catch (err) {
      showToast(err.message, "error");
      btn.disabled = false;
      btn.textContent = "↻ Sincronizza 14 giorni";
    }
  });

  document.getElementById("btn-garmin-disconnect")?.addEventListener("click", async () => {
    if (!confirm("Vuoi scollegare il tuo account Garmin Connect?")) return;
    try {
      await api.disconnectGarmin();
      showToast("Garmin Connect disconnesso.", "info");
      await refreshSidebarStatus();
      renderSettings(container, refreshSidebarStatus, isStale);
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  
  // Whoop 1-Tap OAuth & Sync
  document.getElementById("btn-whoop-oauth-1tap")?.addEventListener("click", async () => {
    try {
      const res = await api.getWhoopAuthUrl();
      if (res && res.url) {
        window.location.href = res.url;
      }
    } catch (err) {
      showToast(err.message || "Errore avvio connessione Whoop", "error");
    }
  });

  document.getElementById("btn-whoop-sync-now")?.addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    btn.textContent = "Sincronizzazione...";
    try {
      const res = await api.syncWhoop();
      showToast(`Whoop sincronizzato con successo (${res.synced_days || 0} giorni)!`, "success");
      await refreshSidebarStatus();
      renderSettings(container, refreshSidebarStatus);
    } catch (err) {
      showToast(err.message, "error");
      btn.disabled = false;
      btn.textContent = "↻ Sincronizza Adesso";
    }
  });

  // Gemini save & test
  document.getElementById("gemini-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const key = document.getElementById("gemini-key").value.trim();
    const model = document.getElementById("gemini-model").value;
    const payload = { gemini_model: model };
    if (key) payload.gemini_api_key = key;
    try {
      await api.updateSettings(payload);
      const test = await api.testGemini();
      if (test.ok) {
        showToast(`Gemini (${test.model}) collegato e verificato!`, "success");
      } else {
        showToast("Salvato, ma test Gemini fallito: " + test.error, "error");
      }
      renderSettings(container, refreshSidebarStatus);
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  document.getElementById("btn-test-gemini")?.addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    btn.textContent = "Test in corso...";
    try {
      const test = await api.testGemini();
      if (test.ok) showToast(`OK! Connesso a ${test.model}`, "success");
      else showToast(test.error || "Errore test Gemini", "error");
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "🧪 Testa Gemini";
    }
  });

  // Profile save
  document.getElementById("profile-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const pRaw = document.getElementById("prof-thresh").value.trim();
    let threshSec = s.threshold_pace_sec;
    if (pRaw.includes(":")) {
      const [m, sec] = pRaw.split(":").map(Number);
      if (!Number.isNaN(m) && !Number.isNaN(sec)) threshSec = m * 60 + sec;
    }
    try {
      await api.updateSettings({
        athlete_name: document.getElementById("prof-name").value.trim() || "Runner",
        weekly_goal_km: Number(document.getElementById("prof-weekly").value),
        max_hr: Number(document.getElementById("prof-maxhr").value),
        resting_hr: Number(document.getElementById("prof-rhr").value),
        threshold_pace_sec: threshSec,
        auto_sync_interval_min: Number(document.getElementById("prof-sync-int").value),
        auto_sync_enabled: document.getElementById("prof-autosync").checked,
      });
      showToast("Profilo atleta aggiornato!", "success");
      await refreshSidebarStatus();
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  // Backup import
  document.getElementById("input-import-backup")?.addEventListener("change", async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      const parsed = JSON.parse(text);
      const res = await api.importBackup(parsed);
      const imp = res.imported || {};
      showToast(
        `Backup importato! ${imp.activities || 0} attività, ${imp.garmin_days || 0}g Garmin, ${imp.messages || 0} msg Calippo.`,
        "success"
      );
      await refreshSidebarStatus();
      renderSettings(container, refreshSidebarStatus, isStale);
    } catch (err) {
      showToast("Errore importazione backup: " + err.message, "error");
    } finally {
      e.target.value = "";
    }
  });

  // Demo controls
  document.getElementById("btn-seed-demo")?.addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    try {
      await api.seedDemo();
      showToast("Caricati 60 giorni di dati demo Strava + Garmin!", "success");
      renderSettings(container, refreshSidebarStatus, isStale);
    } catch (err) {
      showToast(err.message, "error");
      btn.disabled = false;
    }
  });

  document.getElementById("btn-clear-demo")?.addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    try {
      const res = await api.clearDemo();
      showToast(`Rimossi ${res.activities_deleted} allenamenti e ${res.garmin_days_deleted} giorni demo.`, "info");
      renderSettings(container, refreshSidebarStatus, isStale);
    } catch (err) {
      showToast(err.message, "error");
      btn.disabled = false;
    }
  });
}
