import { api, escapeHtml, formatHoursMin, formatMinHM, formatPace, formatRaceTime, showToast } from "../api.js";
import { renderAppleActivityChart, renderHrvSleepChart } from "../charts.js";

export async function renderWellness(container, navigate, isStale = () => false) {
  container.innerHTML = `<div class="loading-state">Caricamento dati Apple Watch & Apple Health...</div>`;
  let data;
  try {
    data = await api.getWellness(30);
  } catch (err) {
    if (isStale()) return;
    container.innerHTML = `<div class="card empty-state">Errore caricamento: ${escapeHtml(err.message)}</div>`;
    return;
  }
  if (isStale()) return;

  const days = data.days || [];
  const latest = data.latest;
  const readiness = data.readiness || {};
  const snaps = data.snapshots || {};

  if (!days.length) {
    container.innerHTML = `
      <div class="card empty-state">
        <div style="font-size:2.8rem;margin-bottom:10px;">⌚</div>
        <h3>Nessun dato Apple Watch o Apple Health ancora sincronizzato</h3>
        <p class="subtitle" style="margin:10px 0 20px;max-width:540px;margin-left:auto;margin-right:auto;">
          Sincronizza automaticamente le metriche del tuo Apple Watch (Sonno con fasi, HRV SDNN, Battito a riposo, Cardio Fitness VO2 max e Anelli Attività) oppure prova subito i dati demo.
        </p>
        <div style="display:flex;gap:12px;justify-content:center;flex-wrap:wrap;">
          <button class="btn btn-primary" id="w-btn-setup-shortcut">📲 Sincronizza da iPhone (Comando Rapido)</button>
          <button class="btn btn-ghost" id="w-btn-manual-entry">✍️ Inserimento Manuale</button>
          <button class="btn btn-ghost" id="w-load-demo">✨ Carica Dati Demo Apple Watch</button>
        </div>
      </div>
      <div id="w-modal-host"></div>`;

    _attachEmptyHandlers(container, navigate, isStale);
    return;
  }

  // Sleep breakdown calculations
  const sleepDeep = latest.sleep_deep_sec || 0;
  const sleepRem = latest.sleep_rem_sec || 0;
  const sleepLight = latest.sleep_light_sec || 0;
  const sleepAwake = latest.sleep_awake_sec || 0;
  const sleepTot = Math.max(1, sleepDeep + sleepRem + sleepLight + sleepAwake);

  const pctDeep = Math.round((sleepDeep / sleepTot) * 100);
  const pctRem = Math.round((sleepRem / sleepTot) * 100);
  const pctLight = Math.round((sleepLight / sleepTot) * 100);
  const pctAwake = Math.round((sleepAwake / sleepTot) * 100);

  // 7-day rolling averages
  const recent7 = days.slice(-7);
  const avgHrv7 = recent7.filter((d) => d.hrv_avg != null);
  const hrv7Val = avgHrv7.length
    ? Math.round(avgHrv7.reduce((s, d) => s + d.hrv_avg, 0) / avgHrv7.length)
    : "--";

  const avgRhr7 = recent7.filter((d) => d.resting_hr != null);
  const rhr7Val = avgRhr7.length
    ? Math.round(avgRhr7.reduce((s, d) => s + d.resting_hr, 0) / avgRhr7.length)
    : "--";

  const deviceInfo = snaps.device_info || {};

  container.innerHTML = `
    <!-- Top Action Bar -->
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;margin-bottom:18px;">
      <div class="subtitle" style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
        <span class="pill pill-success" style="font-weight:700;">⌚ Apple HealthKit</span>
        <span>Giorno: <strong>${latest.date_key}</strong></span>
        ${data.apple_health_last_sync ? ` · Ultimo Sync: <strong>${data.apple_health_last_sync.slice(11, 16)}</strong>` : ""}
        ${deviceInfo.model ? ` · <span style="color:#93a1be;">${escapeHtml(deviceInfo.model)}</span>` : ""}
      </div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;">
        <button class="btn btn-ghost btn-sm" id="w-btn-manual-entry">✍️ Registra / Modifica Oggi</button>
        <button class="btn btn-primary btn-sm" id="w-btn-setup-shortcut">📲 Sincronizza da iPhone</button>
      </div>
    </div>

    <!-- Hero Readiness & Recovery Card -->
    <div class="card" style="margin-bottom:20px;background:linear-gradient(135deg, rgba(16,185,129,0.08) 0%, rgba(9,12,20,0.95) 100%);border-color:rgba(16,185,129,0.25);">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:16px;">
        <div>
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;">
            <span style="font-size:1.6rem;">💖</span>
            <h2 style="font-size:1.35rem;font-weight:800;margin:0;">Prontezza Atletica</h2>
            <span class="pill" style="background:${readiness.color || '#10b981'}25;color:${readiness.color || '#10b981'};font-weight:700;border:1px solid ${readiness.color || '#10b981'}50;">
              ${readiness.zone_label || 'Pronto'}
            </span>
          </div>
          <p class="subtitle" style="margin:0;max-width:580px;">
            Calcolata combinando la variabilità cardiaca notturna (HRV SDNN), il sonno Apple Health, la frequenza cardiaca a riposo e il carico di allenamento Strava.
          </p>
        </div>
        <div style="text-align:right;">
          <div style="font-size:3rem;font-weight:900;line-height:1;color:${readiness.color || '#10b981'};font-feature-settings:'tnum';">
            ${readiness.score || 75}<span style="font-size:1.2rem;color:#64748b;font-weight:600;">/100</span>
          </div>
          <div style="font-size:0.75rem;color:#93a1be;margin-top:4px;">Punteggio di Recupero</div>
        </div>
      </div>

      <!-- Readiness Components Grid -->
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin-top:18px;">
        ${(readiness.components || [])
          .map(
            (c) => `
          <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);border-radius:10px;padding:10px 12px;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
              <span style="font-size:0.75rem;color:#93a1be;">${escapeHtml(c.label)}</span>
              <span class="pill pill-${c.status === 'ottimo' ? 'success' : c.status === 'moderato' ? 'warning' : 'danger'}" style="font-size:0.65rem;padding:2px 6px;">
                ${escapeHtml(c.status)}
              </span>
            </div>
            <div style="font-size:1.05rem;font-weight:700;color:#f8fafc;">${escapeHtml(c.value)}</div>
            <div style="font-size:0.7rem;color:#64748b;margin-top:2px;">${escapeHtml(c.detail || '')}</div>
          </div>`
          )
          .join("")}
      </div>
    </div>

    <!-- Apple Watch Biometrics Grid -->
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;margin-bottom:20px;">
      
      <!-- Card 1: HRV SDNN -->
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
          <div style="display:flex;align-items:center;gap:8px;">
            <span style="font-size:1.3rem;">📈</span>
            <h3 style="font-size:1rem;margin:0;">HRV Notturna (SDNN)</h3>
          </div>
          <span class="pill ${latest.hrv_status === 'Ottimale' ? 'pill-success' : latest.hrv_status === 'Basso / Affaticato' ? 'pill-danger' : 'pill-warning'}">
            ${latest.hrv_status || 'Normale'}
          </span>
        </div>
        <div style="display:flex;align-items:baseline;gap:8px;">
          <span style="font-size:2.2rem;font-weight:800;color:#10b981;">
            ${latest.hrv_avg != null ? Math.round(latest.hrv_avg) : '--'}
          </span>
          <span style="font-size:0.95rem;color:#93a1be;">ms</span>
        </div>
        <div style="margin-top:10px;font-size:0.8rem;color:#cbd5e1;line-height:1.4;">
          Baseline ottimale: <strong>${latest.hrv_baseline_low ? Math.round(latest.hrv_baseline_low) : 50} – ${latest.hrv_baseline_high ? Math.round(latest.hrv_baseline_high) : 75} ms</strong><br/>
          Media 7 giorni: <strong>${hrv7Val} ms</strong>
        </div>
      </div>

      <!-- Card 2: FC a Riposo -->
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
          <div style="display:flex;align-items:center;gap:8px;">
            <span style="font-size:1.3rem;">🫀</span>
            <h3 style="font-size:1rem;margin:0;">FC a Riposo (RHR)</h3>
          </div>
          <span class="pill pill-success">Apple Health</span>
        </div>
        <div style="display:flex;align-items:baseline;gap:8px;">
          <span style="font-size:2.2rem;font-weight:800;color:#f87171;">
            ${latest.resting_hr || '--'}
          </span>
          <span style="font-size:0.95rem;color:#93a1be;">bpm</span>
        </div>
        <div style="margin-top:10px;font-size:0.8rem;color:#cbd5e1;line-height:1.4;">
          Media ultimi 7 giorni: <strong>${rhr7Val} bpm</strong><br/>
          ${latest.walking_hr_avg ? `Media camminata Apple Watch: <strong>${Math.round(latest.walking_hr_avg)} bpm</strong>` : "Misurato costantemente al risveglio dall'Apple Watch."}
        </div>
      </div>

      <!-- Card 3: Sonno con Fasi -->
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
          <div style="display:flex;align-items:center;gap:8px;">
            <span style="font-size:1.3rem;">🌙</span>
            <h3 style="font-size:1rem;margin:0;">Sonno Apple Watch</h3>
          </div>
          ${latest.sleep_score ? `<span class="pill pill-success">Qualità ${latest.sleep_score}/100</span>` : ""}
        </div>
        <div style="display:flex;align-items:baseline;gap:8px;">
          <span style="font-size:2.2rem;font-weight:800;color:#a78bfa;">
            ${formatHoursMin(latest.sleep_seconds)}
          </span>
        </div>

        <!-- Sleep Stages Bar -->
        ${
          sleepDeep || sleepRem
            ? `
          <div style="margin-top:12px;">
            <div style="height:10px;border-radius:5px;overflow:hidden;display:flex;background:#1e293b;margin-bottom:8px;">
              <div style="width:${pctDeep}%;background:#8b5cf6;" title="Profondo: ${formatHoursMin(sleepDeep)} (${pctDeep}%)"></div>
              <div style="width:${pctRem}%;background:#38bdf8;" title="REM: ${formatHoursMin(sleepRem)} (${pctRem}%)"></div>
              <div style="width:${pctLight}%;background:#0ea5e9;" title="Base/Core: ${formatHoursMin(sleepLight)} (${pctLight}%)"></div>
              ${pctAwake ? `<div style="width:${pctAwake}%;background:#64748b;" title="Veglia: ${formatHoursMin(sleepAwake)} (${pctAwake}%)"></div>` : ""}
            </div>
            <div style="display:flex;justify-content:space-between;font-size:0.72rem;color:#93a1be;flex-wrap:wrap;gap:4px;">
              <span><strong style="color:#8b5cf6;">■</strong> Profondo: ${formatHoursMin(sleepDeep)}</span>
              <span><strong style="color:#38bdf8;">■</strong> REM: ${formatHoursMin(sleepRem)}</span>
              <span><strong style="color:#0ea5e9;">■</strong> Core: ${formatHoursMin(sleepLight)}</span>
            </div>
          </div>`
            : `<div style="font-size:0.8rem;color:#93a1be;margin-top:10px;">Monitorato tramite modalità Sonno su watchOS.</div>`
        }
      </div>

      <!-- Card 4: Anelli Attività Apple Watch -->
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
          <div style="display:flex;align-items:center;gap:8px;">
            <span style="font-size:1.3rem;">⭕</span>
            <h3 style="font-size:1rem;margin:0;">Anelli Attività</h3>
          </div>
          <span class="pill pill-warning">Apple Activity</span>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;text-align:center;">
          <div style="background:rgba(250,45,72,0.1);border:1px solid rgba(250,45,72,0.25);border-radius:10px;padding:8px 4px;">
            <div style="color:#fa2d48;font-size:0.75rem;font-weight:700;">MOVIMENTO</div>
            <div style="font-size:1.25rem;font-weight:800;color:#f8fafc;margin:2px 0;">${latest.active_calories || 0}</div>
            <div style="font-size:0.65rem;color:#93a1be;">kcal</div>
          </div>
          <div style="background:rgba(164,255,0,0.1);border:1px solid rgba(164,255,0,0.25);border-radius:10px;padding:8px 4px;">
            <div style="color:#a4ff00;font-size:0.75rem;font-weight:700;">ESERCIZIO</div>
            <div style="font-size:1.25rem;font-weight:800;color:#f8fafc;margin:2px 0;">${latest.exercise_min || 0}</div>
            <div style="font-size:0.65rem;color:#93a1be;">min</div>
          </div>
          <div style="background:rgba(0,240,255,0.1);border:1px solid rgba(0,240,255,0.25);border-radius:10px;padding:8px 4px;">
            <div style="color:#00f0ff;font-size:0.75rem;font-weight:700;">IN PIEDI</div>
            <div style="font-size:1.25rem;font-weight:800;color:#f8fafc;margin:2px 0;">${latest.stand_hours || 0}</div>
            <div style="font-size:0.65rem;color:#93a1be;">ore</div>
          </div>
        </div>
        <div style="margin-top:10px;font-size:0.8rem;color:#cbd5e1;text-align:center;">
          👟 Passi totali: <strong>${(latest.steps || 0).toLocaleString("it-IT")}</strong>
        </div>
      </div>

      <!-- Card 5: Cardio Fitness (VO2 Max) -->
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
          <div style="display:flex;align-items:center;gap:8px;">
            <span style="font-size:1.3rem;">🫁</span>
            <h3 style="font-size:1rem;margin:0;">Cardio Fitness (VO2 Max)</h3>
          </div>
          <span class="pill pill-success">Stima Watch</span>
        </div>
        <div style="display:flex;align-items:baseline;gap:8px;">
          <span style="font-size:2.2rem;font-weight:800;color:#00b4d8;">
            ${latest.vo2_max || '--'}
          </span>
          <span style="font-size:0.95rem;color:#93a1be;">ml/kg/min</span>
        </div>
        <div style="margin-top:10px;font-size:0.8rem;color:#cbd5e1;line-height:1.4;">
          Calcolato da Apple Watch durante le corse e camminate all'aperto con GPS e cardiofrequenzimetro.
        </div>
      </div>

      <!-- Card 6: Metriche Polso & SpO2 -->
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
          <div style="display:flex;align-items:center;gap:8px;">
            <span style="font-size:1.3rem;">🌡️</span>
            <h3 style="font-size:1rem;margin:0;">Biometria Polso</h3>
          </div>
          <span class="pill pill-muted">Sensori Notturni</span>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
          <div>
            <div style="font-size:0.75rem;color:#93a1be;">Ossigeno (SpO2)</div>
            <div style="font-size:1.35rem;font-weight:800;color:#f8fafc;">
              ${latest.spo2_avg ? `${latest.spo2_avg}%` : '--'}
            </div>
          </div>
          <div>
            <div style="font-size:0.75rem;color:#93a1be;">Respirazione</div>
            <div style="font-size:1.35rem;font-weight:800;color:#f8fafc;">
              ${latest.respiration_avg ? `${latest.respiration_avg} /m` : '--'}
            </div>
          </div>
        </div>
        <div style="margin-top:10px;font-size:0.8rem;color:#cbd5e1;">
          ${latest.wrist_temperature_c != null ? `Temp. polso basale: <strong>${latest.wrist_temperature_c >= 0 ? '+' : ''}${latest.wrist_temperature_c}°C</strong>` : "Include livelli SpO2 e frequenza respiratoria notturna."}
        </div>
      </div>

    </div>

    <!-- Charts Section -->
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px;margin-bottom:24px;">
      <div class="card">
        <h3 style="font-size:1rem;margin:0 0 12px;">Trend HRV & Sonno (Ultimi 30 Giorni)</h3>
        <div style="height:230px;">
          <canvas id="chart-apple-hrv-sleep"></canvas>
        </div>
      </div>
      <div class="card">
        <h3 style="font-size:1rem;margin:0 0 12px;">Attività & Esercizio Apple Watch</h3>
        <div style="height:230px;">
          <canvas id="chart-apple-activity"></canvas>
        </div>
      </div>
    </div>

    <div id="w-modal-host"></div>
  `;

  // Mount Charts
  setTimeout(() => {
    if (isStale()) return;
    renderHrvSleepChart("chart-apple-hrv-sleep", days);
    renderAppleActivityChart("chart-apple-activity", days);
  }, 30);

  _attachEvents(container, latest, isStale, navigate);
}

function _attachEmptyHandlers(container, navigate, isStale) {
  document.getElementById("w-btn-setup-shortcut")?.addEventListener("click", () => _openShortcutModal());
  document.getElementById("w-btn-manual-entry")?.addEventListener("click", () => _openManualEntryModal(null, () => renderWellness(container, navigate, isStale)));
  document.getElementById("w-load-demo")?.addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    try {
      await api.seedDemo();
      showToast("Dati demo Apple Watch caricati con successo!", "success");
      renderWellness(container, navigate, isStale);
    } catch (err) {
      showToast(err.message, "error");
      btn.disabled = false;
    }
  });
}

function _attachEvents(container, latest, isStale, navigate) {
  document.getElementById("w-btn-setup-shortcut")?.addEventListener("click", () => _openShortcutModal());
  document.getElementById("w-btn-manual-entry")?.addEventListener("click", () => _openManualEntryModal(latest, () => renderWellness(container, navigate, isStale)));
}

async function _openShortcutModal() {
  const host = document.getElementById("w-modal-host");
  if (!host) return;

  let cfg = { webhook_url: `${window.location.origin}/api/apple-health/sync`, auth_token: "token_qui" };
  try {
    cfg = await api.getAppleHealthConfig();
  } catch {}

  const sampleJsonStr = JSON.stringify(cfg.sample_payload || {}, null, 2);

  host.innerHTML = `
    <div class="modal-backdrop" id="shortcut-modal">
      <div class="modal-card" style="max-width:620px;">
        <div class="modal-header">
          <div>
            <h2 style="font-size:1.25rem;margin:0;">📲 Sincronizzazione Apple Health da iPhone</h2>
            <p class="subtitle" style="margin:2px 0 0;">Configura un Comando Rapido su iOS in 2 minuti (gratis per sempre)</p>
          </div>
          <button class="btn-icon" id="shortcut-modal-close">✕</button>
        </div>
        <div class="modal-body" style="font-size:0.88rem;line-height:1.5;">
          <p style="color:#cbd5e1;margin-top:0;">
            Grazie all'app nativa <strong>Comandi Rapidi (Shortcuts)</strong> di iOS, il tuo iPhone può inviare automaticamente a RunPulse le tue metriche ogni mattina (ad esempio quando suona la sveglia o con un tap dal widget!).
          </p>

          <div style="background:#131826;border:1px solid rgba(255,255,255,0.08);border-radius:10px;padding:12px;margin:12px 0;">
            <div style="font-size:0.75rem;color:#93a1be;margin-bottom:4px;">1. IL TUO INDIRIZZO WEBHOOK PERSONALE:</div>
            <div style="display:flex;gap:8px;align-items:center;">
              <input class="input" readonly value="${escapeHtml(cfg.webhook_url)}" id="sc-input-url" style="font-family:monospace;font-size:0.8rem;" />
              <button class="btn btn-ghost btn-sm" id="sc-btn-copy-url">Copia</button>
            </div>
            
            <div style="font-size:0.75rem;color:#93a1be;margin:10px 0 4px;">2. CHIAVE DI AUTORIZZAZIONE (TOKEN):</div>
            <div style="display:flex;gap:8px;align-items:center;">
              <input class="input" readonly value="${escapeHtml(cfg.auth_token)}" id="sc-input-token" style="font-family:monospace;font-size:0.8rem;" />
              <button class="btn btn-ghost btn-sm" id="sc-btn-copy-token">Copia</button>
            </div>
          </div>

          <h4 style="margin:16px 0 8px;color:#f8fafc;">Come creare il Comando Rapido su iPhone:</h4>
          <ol style="color:#cbd5e1;padding-left:20px;margin:0 0 16px;">
            <li>Apri l'app <strong>Comandi Rapidi</strong> su iPhone → tocca <strong>+</strong> in alto a destra.</li>
            <li>Aggiungi le azioni:
              <br/>• <em>"Trova campioni di salute"</em> per <strong>Variabilità FC</strong> (tipo SDNN)
              <br/>• <em>"Trova campioni di salute"</em> per <strong>Frequenza cardiaca a riposo</strong>
              <br/>• <em>"Trova campioni di salute"</em> per <strong>Sonno</strong>
            </li>
            <li>Aggiungi l'azione <strong>"Dizionario"</strong> con le chiavi <code>hrv_sdnn_ms</code>, <code>resting_hr</code>, <code>sleep_hours</code> e <code>auth_token</code>.</li>
            <li>Aggiungi l'azione <strong>"Ottieni contenuti dall'URL"</strong>:
              <br/>• Metodo: <strong>POST</strong>
              <br/>• Corpo della richiesta: <strong>JSON</strong> (il dizionario appena creato)
              <br/>• Intestazione facoltativa: <code>x-apple-health-token: ${escapeHtml(cfg.auth_token)}</code>
            </li>
            <li><em>(Consigliato)</em>: Vai nella tab <strong>Automazione</strong> di Comandi Rapidi → crea una nuova automazione <em>"Quando la sveglia viene interrotta"</em> → esegui subito questo comando rapido!</li>
          </ol>

          <details style="background:#090c14;border:1px solid rgba(255,255,255,0.06);border-radius:8px;padding:10px;">
            <summary style="cursor:pointer;font-weight:600;color:#00b4d8;">Visualizza Payload JSON di Esempio</summary>
            <pre style="margin:10px 0 0;font-size:0.75rem;color:#cbd5e1;overflow-x:auto;">${escapeHtml(sampleJsonStr)}</pre>
          </details>

          <div style="margin-top:16px;text-align:right;">
            <button class="btn btn-primary" id="sc-btn-done">Ho Capito, Chiudi</button>
          </div>
        </div>
      </div>
    </div>
  `;

  document.getElementById("shortcut-modal-close")?.addEventListener("click", () => { host.innerHTML = ""; });
  document.getElementById("sc-btn-done")?.addEventListener("click", () => { host.innerHTML = ""; });
  document.getElementById("sc-btn-copy-url")?.addEventListener("click", () => {
    navigator.clipboard.writeText(cfg.webhook_url);
    showToast("URL Webhook copiato negli appunti!", "success");
  });
  document.getElementById("sc-btn-copy-token")?.addEventListener("click", () => {
    navigator.clipboard.writeText(cfg.auth_token);
    showToast("Token copiato negli appunti!", "success");
  });
}

function _openManualEntryModal(latest, onSaved) {
  const host = document.getElementById("w-modal-host");
  if (!host) return;

  const todayStr = new Date().toISOString().slice(0, 10);
  const curDate = latest?.date_key || todayStr;

  host.innerHTML = `
    <div class="modal-backdrop" id="manual-modal">
      <div class="modal-card" style="max-width:500px;">
        <div class="modal-header">
          <div>
            <h2 style="font-size:1.25rem;margin:0;">✍️ Registra Metriche Giornaliere</h2>
            <p class="subtitle" style="margin:2px 0 0;">Inserisci o correggi i valori del tuo Apple Watch per oggi</p>
          </div>
          <button class="btn-icon" id="manual-modal-close">✕</button>
        </div>
        <form id="manual-entry-form" style="display:flex;flex-direction:column;gap:12px;padding-top:10px;">
          <div>
            <label class="label">Data (YYYY-MM-DD)</label>
            <input class="input" type="date" id="me-date" value="${curDate}" required />
          </div>

          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
            <div>
              <label class="label">HRV Notturna (ms)</label>
              <input class="input" type="number" step="0.1" id="me-hrv" placeholder="es. 68" value="${latest?.hrv_avg ?? ''}" />
            </div>
            <div>
              <label class="label">FC a Riposo (bpm)</label>
              <input class="input" type="number" id="me-rhr" placeholder="es. 50" value="${latest?.resting_hr ?? ''}" />
            </div>
          </div>

          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
            <div>
              <label class="label">Ore Sonno Totali</label>
              <input class="input" type="number" step="0.1" id="me-sleep-h" placeholder="es. 7.5" value="${latest?.sleep_seconds ? (latest.sleep_seconds / 3600).toFixed(1) : ''}" />
            </div>
            <div>
              <label class="label">Cardio Fitness (VO2 Max)</label>
              <input class="input" type="number" step="0.1" id="me-vo2" placeholder="es. 52.4" value="${latest?.vo2_max ?? ''}" />
            </div>
          </div>

          <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;">
            <div>
              <label class="label">Calorie Attive</label>
              <input class="input" type="number" id="me-cals" placeholder="kcal" value="${latest?.active_calories ?? ''}" />
            </div>
            <div>
              <label class="label">Esercizio (min)</label>
              <input class="input" type="number" id="me-exercise" placeholder="min" value="${latest?.exercise_min ?? ''}" />
            </div>
            <div>
              <label class="label">Passi</label>
              <input class="input" type="number" id="me-steps" placeholder="passi" value="${latest?.steps ?? ''}" />
            </div>
          </div>

          <div style="margin-top:10px;display:flex;justify-content:flex-end;gap:10px;">
            <button class="btn btn-ghost" type="button" id="me-btn-cancel">Annulla</button>
            <button class="btn btn-primary" type="submit" id="me-btn-submit">Salva Metriche</button>
          </div>
        </form>
      </div>
    </div>
  `;

  document.getElementById("manual-modal-close")?.addEventListener("click", () => { host.innerHTML = ""; });
  document.getElementById("me-btn-cancel")?.addEventListener("click", () => { host.innerHTML = ""; });

  document.getElementById("manual-entry-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = document.getElementById("me-btn-submit");
    btn.disabled = true;

    const payload = {
      date_key: document.getElementById("me-date").value,
      hrv_avg: document.getElementById("me-hrv").value ? parseFloat(document.getElementById("me-hrv").value) : null,
      resting_hr: document.getElementById("me-rhr").value ? parseInt(document.getElementById("me-rhr").value) : null,
      sleep_hours: document.getElementById("me-sleep-h").value ? parseFloat(document.getElementById("me-sleep-h").value) : null,
      vo2_max: document.getElementById("me-vo2").value ? parseFloat(document.getElementById("me-vo2").value) : null,
      active_calories: document.getElementById("me-cals").value ? parseInt(document.getElementById("me-cals").value) : null,
      exercise_min: document.getElementById("me-exercise").value ? parseInt(document.getElementById("me-exercise").value) : null,
      steps: document.getElementById("me-steps").value ? parseInt(document.getElementById("me-steps").value) : null,
    };

    try {
      await api.manualAppleHealthEntry(payload);
      showToast("Metriche Apple Watch registrate con successo!", "success");
      host.innerHTML = "";
      if (onSaved) onSaved();
    } catch (err) {
      showToast(err.message, "error");
      btn.disabled = false;
    }
  });
}
