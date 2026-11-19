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
              <button class="btn btn-primary btn-sm" type="submit">Salva PIN</button>
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
            <div class="card-title">🟠 Strava (Sync Automatico Corse Apple Watch)</div>
            <div class="subtitle">Tutte le corse registrate con Apple Watch sincronizzate automaticamente</div>
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

      <!-- APPLE WATCH & APPLE HEALTH -->
      <section class="card" style="border-color:${s.apple_health_connected ? "rgba(16,185,129,0.4)" : "rgba(0,180,216,0.35)"};">
        <div class="card-header">
          <div>
            <div class="card-title">⌚ Apple Watch & Apple Health</div>
            <div class="subtitle">HRV SDNN notturna, Sonno con fasi, FC riposo e Anelli Attività</div>
          </div>
          <span class="pill ${s.apple_health_connected ? "pill-green" : "pill-cyan"}">
            ${s.apple_health_connected ? "CONNESSO" : "PRONTO"}
          </span>
        </div>

        <div class="guide-steps">
          <strong>Sincronizzazione da iPhone (100% gratuita):</strong>
          <p style="margin-top:4px;">
            I dati di salute del tuo Apple Watch vengono inviati dall'app nativa <strong>Comandi Rapidi (Shortcuts)</strong> del tuo iPhone via webhook REST sicuro.
          </p>
        </div>

        <div style="background:rgba(0,0,0,0.22);padding:14px;border-radius:12px;border:1px solid var(--border);margin-bottom:14px;">
          <div style="font-size:0.75rem;color:#93a1be;margin-bottom:4px;">INDIRIZZO WEBHOOK PERSONALE:</div>
          <div class="url-copy-box" style="margin-bottom:10px;">
            <span>${escapeHtml(preferredMobileUrl)}/api/apple-health/sync</span>
            <button class="btn btn-ghost btn-sm" data-copy-url="${escapeHtml(preferredMobileUrl)}/api/apple-health/sync">Copia</button>
          </div>
          <div style="font-size:0.75rem;color:#93a1be;margin-bottom:4px;">CHIAVE DI ACCESSO (TOKEN):</div>
          <div class="url-copy-box">
            <span>${escapeHtml(s.apple_health_api_key)}</span>
            <button class="btn btn-ghost btn-sm" data-copy-url="${escapeHtml(s.apple_health_api_key)}">Copia</button>
          </div>
        </div>

        <form id="apple-health-token-form" class="form-grid">
          <div class="form-field full">
            <label for="apple-health-token-input">Token Personale Sincronizzazione</label>
            <div style="display:flex;gap:8px;">
              <input class="input" id="apple-health-token-input" value="${escapeHtml(s.apple_health_api_key)}" placeholder="Token segreto" style="flex:1;" />
              <button class="btn btn-primary btn-sm" type="submit">Salva Token</button>
            </div>
          </div>
        </form>

        <div style="display:flex;justify-content:space-between;align-items:center;margin-top:12px;flex-wrap:wrap;gap:8px;">
          <div class="subtitle">
            Stato: <strong>${s.apple_health_connected ? "Dati ricevuti ✓" : "In attesa di sincronizzazione"}</strong> · Ultimo sync: ${escapeHtml(s.apple_health_last_sync || "mai")}
          </div>
        </div>
      </section>
    </div>

    <div class="grid-2">
      <!-- GEMINI AI -->
      <section class="card">
        <div class="card-header">
          <div>
            <div class="card-title">✨ Coach AI Google Gemini (Ibrido)</div>
            <div class="subtitle">Potenzia i consigli giornalieri, l'analisi delle corse e la chat coach Calippo</div>
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
              Sincronizza Strava automaticamente in background
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
            Database attivo: <strong>${s.storage_backend === "postgresql" ? "PostgreSQL Cloud (Persistente ✓)" : "SQLite Locale"}</strong> ·
            Esporta tutto (corse Strava, salute Apple Watch, Calippo) e importalo sul tuo link Cloud in 1 click!
          </div>
        </div>
        <span class="pill ${s.storage_backend === "postgresql" ? "pill-green" : "pill-cyan"}">
          ${s.storage_backend === "postgresql" ? "CLOUD 24/7" : "LOCALE"}
        </span>
      </div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;">
        <a class="btn btn-primary btn-sm" href="/api/backup/export" download="runpulse-applewatch-backup.json">
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
            Database attuale: <strong>${s.data_counts.activities}</strong> corse · <strong>${s.data_counts.wellness_days ?? s.data_counts.garmin_days ?? 0}</strong> giorni Apple Watch · <strong>${s.data_counts.race_goals}</strong> piani gara.
          </div>
        </div>
        <div style="display:flex;gap:10px;flex-wrap:wrap;">
          <button class="btn btn-ghost btn-sm" id="btn-seed-demo">✨ Carica Dati Demo Apple Watch</button>
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
        showToast("Copiato negli appunti!", "success");
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
      showToast(`Strava sincronizzato! ${res.synced_activities} attività caricate.`, "success");
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

  // Apple Health token save
  document.getElementById("apple-health-token-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const token = document.getElementById("apple-health-token-input").value.trim();
    if (!token) {
      showToast("Inserisci un token.", "error");
      return;
    }
    try {
      await api.updateSettings({ apple_health_api_key: token });
      showToast("Token Apple Health salvato!", "success");
      renderSettings(container, refreshSidebarStatus);
    } catch (err) {
      showToast(err.message, "error");
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
        `Backup importato! ${imp.activities || 0} corse, ${imp.wellness_days || 0}g Apple Watch.`,
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
      showToast("Caricati dati demo Apple Watch & Strava!", "success");
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
      showToast(`Rimossi ${res.activities_deleted} allenamenti e ${res.wellness_days_deleted} giorni demo.`, "info");
      renderSettings(container, refreshSidebarStatus, isStale);
    } catch (err) {
      showToast(err.message, "error");
      btn.disabled = false;
    }
  });
}
