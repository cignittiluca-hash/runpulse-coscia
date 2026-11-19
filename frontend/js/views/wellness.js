import { api, escapeHtml, formatHoursMin, formatMinHM, formatPace, formatRaceTime, showToast } from "../api.js";
import { renderGarminStressChart, renderHrvSleepChart, renderWhoopTrendsChart } from "../charts.js";

function formatPrValue(pr) {
  if (pr.value == null) return "--";
  if (pr.unit === "time" || [1, 2, 3, 4, 5, 6].includes(pr.type_id)) return formatRaceTime(pr.value);
  if (pr.unit === "steps" || [12, 13, 14].includes(pr.type_id)) return `${Math.round(pr.value).toLocaleString("it-IT")} passi`;
  if (pr.unit === "distance" || pr.type_id === 7) return `${(pr.value / 1000).toFixed(2)} km`;
  return String(Math.round(pr.value));
}

let activeTab = "whoop"; // 'whoop' | 'garmin' | 'compare'

export async function renderWellness(container, navigate, isStale = () => false) {
  container.innerHTML = `<div class="loading-state">Caricamento biometrie Garmin & Whoop 4.0...</div>`;
  let data;
  try {
    data = await api.getWellness(30);
  } catch (err) {
    if (isStale()) return;
    container.innerHTML = `<div class="card empty-state">Errore caricamento dati: ${escapeHtml(err.message)}</div>`;
    return;
  }
  if (isStale()) return;

  const days = data.days || [];
  const latest = data.latest || {};
  const whoopDays = data.whoop_days || [];
  const latestWhoop = data.latest_whoop || (whoopDays.length ? whoopDays[0] : null);
  const snaps = data.snapshots || {};

  const hasGarmin = Boolean(days.length);
  const hasWhoop = Boolean(latestWhoop && (latestWhoop.recovery_score != null || latestWhoop.day_strain != null));

  if (!hasGarmin && !hasWhoop) {
    container.innerHTML = `
      <div class="card empty-state">
        <div style="font-size:3rem;margin-bottom:12px;">⌚ × 🟡</div>
        <h3>Nessun dato biometrico ancora registrato</h3>
        <p class="subtitle" style="margin:10px 0 20px;max-width:540px;margin-left:auto;margin-right:auto;">
          RunPulse supporta l'ecosistema completo di <strong>Garmin Connect</strong> e <strong>Whoop 4.0</strong>. Collega i tuoi dispositivi o carica una simulazione demo realistica di 60 giorni per esplorare tutti i parametri!
        </p>
        <div style="display:flex;gap:12px;justify-content:center;flex-wrap:wrap;">
          <button class="btn btn-primary" id="w-go-settings" style="background:#f59e0b;color:#090c14;border:none;">⚙️ Apri Connessioni Dispositivi</button>
          <button class="btn btn-ghost" id="w-load-demo">✨ Carica Dati Demo Completi</button>
        </div>
      </div>`;
    document.getElementById("w-go-settings")?.addEventListener("click", () => navigate("settings"));
    document.getElementById("w-load-demo")?.addEventListener("click", async (e) => {
      const btn = e.currentTarget;
      btn.disabled = true;
      try {
        await api.seedDemo();
        showToast("Dati demo Garmin e Whoop caricati!", "success");
        renderWellness(container, navigate, isStale);
      } catch (err) {
        showToast(err.message, "error");
        btn.disabled = false;
      }
    });
    return;
  }

  // If no Whoop but has Garmin, default tab to Garmin
  if (!hasWhoop && hasGarmin && activeTab === "whoop") {
    activeTab = "garmin";
  }

  // Whoop calculations
  const wRec = latestWhoop ? latestWhoop.recovery_score : null;
  const wState = latestWhoop ? (latestWhoop.recovery_state || "GREEN").toUpperCase() : "GREEN";
  const wColor = wState === "GREEN" ? "#10b981" : (wState === "YELLOW" ? "#f59e0b" : "#ef4444");
  const wStateLabel = wState === "GREEN" ? "Ottimo Recupero (Verde)" : (wState === "YELLOW" ? "Recupero Adeguato (Giallo)" : "Affaticamento Elevato (Rosso)");
  const wStrain = latestWhoop && latestWhoop.day_strain != null ? latestWhoop.day_strain : "--";
  const wHrv = latestWhoop && latestWhoop.hrv_rmssd != null ? Math.round(latestWhoop.hrv_rmssd) : "--";
  const wRhr = latestWhoop && latestWhoop.resting_hr != null ? latestWhoop.resting_hr : "--";
  const wSpo2 = latestWhoop && latestWhoop.spo2_pct != null ? latestWhoop.spo2_pct + "%" : "--";
  const wSkin = latestWhoop && latestWhoop.skin_temp_celsius != null ? (latestWhoop.skin_temp_celsius > 0 ? `+${latestWhoop.skin_temp_celsius}` : `${latestWhoop.skin_temp_celsius}`) + "°C" : "--";
  const wResp = latestWhoop && latestWhoop.respiratory_rate != null ? latestWhoop.respiratory_rate + " rpm" : "--";
  const wCal = latestWhoop && latestWhoop.calories != null ? Math.round(latestWhoop.calories) : "--";
  const wKj = latestWhoop && latestWhoop.kilojoules != null ? Math.round(latestWhoop.kilojoules) : "--";

  const wSleepActual = latestWhoop && latestWhoop.sleep_hours != null ? latestWhoop.sleep_hours : null;
  const wSleepNeeded = latestWhoop && latestWhoop.sleep_needed_hours != null ? latestWhoop.sleep_needed_hours : 8.0;
  const wSleepPerf = latestWhoop && latestWhoop.sleep_performance_pct != null ? latestWhoop.sleep_performance_pct : (wSleepActual ? Math.min(100, Math.round((wSleepActual / wSleepNeeded) * 100)) : "--");
  const wSleepDebt = latestWhoop && latestWhoop.sleep_debt_minutes != null ? latestWhoop.sleep_debt_minutes : 0;
  const wSleepEff = latestWhoop && latestWhoop.sleep_efficiency_pct != null ? latestWhoop.sleep_efficiency_pct : "--";
  const wSleepCons = latestWhoop && latestWhoop.sleep_consistency_pct != null ? latestWhoop.sleep_consistency_pct : "--";
  const wDisturb = latestWhoop && latestWhoop.disturbances_count != null ? latestWhoop.disturbances_count : "--";
  const wCycles = latestWhoop && latestWhoop.sleep_cycles_count != null ? latestWhoop.sleep_cycles_count : "--";

  // Whoop sleep stage percentages
  const deepH = latestWhoop && latestWhoop.sleep_deep_hours != null ? latestWhoop.sleep_deep_hours : 0;
  const remH = latestWhoop && latestWhoop.sleep_rem_hours != null ? latestWhoop.sleep_rem_hours : 0;
  const lightH = latestWhoop && latestWhoop.sleep_light_hours != null ? latestWhoop.sleep_light_hours : 0;
  const awakeH = latestWhoop && latestWhoop.sleep_awake_hours != null ? latestWhoop.sleep_awake_hours : 0;
  const totalBedH = Math.max(0.1, (deepH + remH + lightH + awakeH) || (wSleepActual || 7.5));
  const deepPct = Math.round((deepH / totalBedH) * 100);
  const remPct = Math.round((remH / totalBedH) * 100);
  const lightPct = Math.round((lightH / totalBedH) * 100);
  const awakePct = Math.max(0, 100 - deepPct - remPct - lightPct);

  // Parse workouts
  let whoopWorkouts = [];
  if (latestWhoop && latestWhoop.workouts) {
    whoopWorkouts = Array.isArray(latestWhoop.workouts) ? latestWhoop.workouts : [];
  } else if (latestWhoop && latestWhoop.workouts_json) {
    try {
      whoopWorkouts = typeof latestWhoop.workouts_json === "string" ? JSON.parse(latestWhoop.workouts_json) : latestWhoop.workouts_json;
    } catch (_) {
      whoopWorkouts = [];
    }
  }

  // Garmin calculations
  const avgStress7 = days.slice(-7).filter((d) => d.stress_avg != null);
  const stress7Val = avgStress7.length ? Math.round(avgStress7.reduce((s, d) => s + d.stress_avg, 0) / avgStress7.length) : "--";
  const avgHrv7 = days.slice(-7).filter((d) => d.hrv_avg != null);
  const hrv7Val = avgHrv7.length ? Math.round(avgHrv7.reduce((s, d) => s + d.hrv_avg, 0) / avgHrv7.length) : "--";

  const ts = snaps.training_status || {};
  const sc = snaps.scores || {};
  const gp = snaps.race_predictions || {};
  const bc = snaps.body_composition || {};
  const gear = snaps.gear || [];
  const prs = snaps.personal_records || [];
  const devices = snaps.devices || [];
  const gActs = (snaps.garmin_activities || []).filter(
    (a) => a.avg_power_w || a.gct_ms || a.aerobic_te != null || a.stride_len_cm
  );

  container.innerHTML = `
    <!-- Header with Device Status & Tab Switcher -->
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;margin-bottom:18px;">
      <div>
        <h2 style="margin:0 0 4px;font-size:1.4rem;display:flex;align-items:center;gap:10px;">
          <span>🔋</span> Recupero & Dispositivi
        </h2>
        <div class="subtitle">
          ${latestWhoop ? `🟡 Whoop: <strong>${latestWhoop.date_key}</strong>` : ""}
          ${latest.date_key ? ` · ⌚ Garmin: <strong>${latest.date_key}</strong>` : ""}
        </div>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        ${
          data.whoop_connected
            ? `<button class="btn btn-ghost btn-sm" id="btn-sync-whoop-now">↻ Sync Whoop</button>`
            : ""
        }
        ${
          data.garmin_connected
            ? `<button class="btn btn-garmin btn-sm" id="btn-sync-garmin-fast">⚡ Sync Garmin (3s)</button>`
            : ""
        }
        <button class="btn btn-ghost btn-sm" id="btn-whoop-quick-checkin">✍️ Check-in Whoop</button>
      </div>
    </div>

    <!-- Segmented Tab Navigation -->
    <div style="display:flex;gap:6px;background:rgba(255,255,255,0.04);padding:4px;border-radius:12px;margin-bottom:20px;border:1px solid rgba(255,255,255,0.08);overflow-x:auto;">
      <button class="btn ${activeTab === "whoop" ? "btn-primary" : "btn-ghost"}" id="tab-whoop" style="${activeTab === "whoop" ? "background:#f59e0b;color:#090c14;border:none;font-weight:700;" : ""}">
        🟡 Whoop 4.0 (Tutti i Dati)
      </button>
      <button class="btn ${activeTab === "garmin" ? "btn-primary" : "btn-ghost"}" id="tab-garmin" style="${activeTab === "garmin" ? "background:#00b4d8;color:#090c14;border:none;font-weight:700;" : ""}">
        ⌚ Garmin Connect
      </button>
      <button class="btn ${activeTab === "compare" ? "btn-primary" : "btn-ghost"}" id="tab-compare" style="${activeTab === "compare" ? "background:#10b981;color:#090c14;border:none;font-weight:700;" : ""}">
        ⚖️ Matrice Doppia (Whoop vs Garmin)
      </button>
    </div>

    <!-- TAB 1: WHOOP 4.0 COMPLETE METRICS -->
    <div id="section-whoop" style="display:${activeTab === "whoop" ? "block" : "none"};">
      ${
        !latestWhoop
          ? `<div class="card empty-state">
              <h3>Nessun dato Whoop 4.0 registrato</h3>
              <p class="subtitle" style="margin:10px 0 16px;">Collega il tuo account Whoop in Connessioni oppure inserisci un check-in rapido per visualizzare Recovery, Day Strain e Sleep Coach.</p>
              <button class="btn btn-primary" id="w-connect-whoop-btn" style="background:#f59e0b;color:#090c14;border:none;">Connetti Whoop</button>
            </div>`
          : `
            <!-- Top Hero Grid: Recovery Gauge & Day Strain -->
            <section class="grid-2" style="margin-bottom:16px;">
              <!-- Whoop Recovery Card -->
              <div class="card" style="border-left:5px solid ${wColor};position:relative;overflow:hidden;">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                  <div>
                    <div class="card-title" style="color:#f3f6fc;display:flex;align-items:center;gap:8px;">
                      <span>⭕</span> WHOOP RECOVERY
                    </div>
                    <div style="margin-top:4px;">
                      <span class="pill" style="background:${wColor}22;color:${wColor};font-weight:700;border:1px solid ${wColor}55;">
                        ${wStateLabel}
                      </span>
                    </div>
                  </div>
                  <div style="text-align:right;">
                    <div style="font-size:3.2rem;font-weight:900;line-height:1;color:${wColor};">
                      ${wRec != null ? wRec : "--"}<span style="font-size:1.4rem;font-weight:500;">%</span>
                    </div>
                  </div>
                </div>

                <p class="subtitle" style="margin:14px 0 16px;line-height:1.45;">
                  ${
                    wRec >= 67
                      ? "Sistema nervoso autonomo bilanciato con tono parasimpatico dominante. Il corpo è pronto ad assorbire allenamenti intensi (ripetute, lunghi o gare)."
                      : (wRec >= 34
                        ? "Recupero fisiologico adeguato. Puoi mantenere il volume di allenamento programmato prestando attenzione all'idratazione e al riscaldamento."
                        : "Forte affaticamento sistemico o debito di sonno accumulato. Consigliata una corsa rigenerante Z2 molto facile o una giornata di scarico attivo.")
                  }
                </p>

                <div class="grid-4" style="margin-top:10px;">
                  <div style="background:rgba(255,255,255,0.03);padding:10px;border-radius:8px;border:1px solid rgba(255,255,255,0.05);">
                    <div style="font-size:0.75rem;color:#94a3b8;text-transform:uppercase;">HRV RMSSD</div>
                    <div style="font-size:1.3rem;font-weight:700;color:#10b981;margin-top:2px;">${wHrv} <small style="font-size:0.75rem;font-weight:400;color:#94a3b8;">ms</small></div>
                  </div>
                  <div style="background:rgba(255,255,255,0.03);padding:10px;border-radius:8px;border:1px solid rgba(255,255,255,0.05);">
                    <div style="font-size:0.75rem;color:#94a3b8;text-transform:uppercase;">FC Riposo</div>
                    <div style="font-size:1.3rem;font-weight:700;color:#38bdf8;margin-top:2px;">${wRhr} <small style="font-size:0.75rem;font-weight:400;color:#94a3b8;">bpm</small></div>
                  </div>
                  <div style="background:rgba(255,255,255,0.03);padding:10px;border-radius:8px;border:1px solid rgba(255,255,255,0.05);">
                    <div style="font-size:0.75rem;color:#94a3b8;text-transform:uppercase;">Ossigeno SpO2</div>
                    <div style="font-size:1.3rem;font-weight:700;color:#a78bfa;margin-top:2px;">${wSpo2}</div>
                  </div>
                  <div style="background:rgba(255,255,255,0.03);padding:10px;border-radius:8px;border:1px solid rgba(255,255,255,0.05);">
                    <div style="font-size:0.75rem;color:#94a3b8;text-transform:uppercase;">Temp. Cutanea</div>
                    <div style="font-size:1.3rem;font-weight:700;color:#f59e0b;margin-top:2px;">${wSkin}</div>
                  </div>
                </div>
              </div>

              <!-- Whoop Strain Card -->
              <div class="card" style="border-left:5px solid #3b82f6;">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                  <div>
                    <div class="card-title" style="color:#f3f6fc;display:flex;align-items:center;gap:8px;">
                      <span>⚡</span> WHOOP DAY STRAIN (0.0 - 21.0)
                    </div>
                    <div style="margin-top:4px;">
                      <span class="pill pill-blue">Scala Logaritmica Borg</span>
                    </div>
                  </div>
                  <div style="text-align:right;">
                    <div style="font-size:3.2rem;font-weight:900;line-height:1;color:#3b82f6;">
                      ${wStrain}
                    </div>
                  </div>
                </div>

                <div style="margin:16px 0 8px;">
                  <div style="display:flex;justify-content:space-between;font-size:0.8rem;color:#94a3b8;margin-bottom:6px;">
                    <span>Leggero (0-9)</span>
                    <span>Moderato (10-13)</span>
                    <span>Allenante (14-17)</span>
                    <span>All-Out (18-21)</span>
                  </div>
                  <div style="height:10px;background:rgba(255,255,255,0.08);border-radius:5px;overflow:hidden;position:relative;">
                    <div style="width:${Math.min(100, Math.round(((parseFloat(wStrain) || 0) / 21.0) * 100))}%;height:100%;background:linear-gradient(90deg, #10b981 0%, #f59e0b 55%, #ef4444 100%);border-radius:5px;"></div>
                  </div>
                </div>

                <div class="grid-4" style="margin-top:14px;">
                  <div style="background:rgba(255,255,255,0.03);padding:10px;border-radius:8px;border:1px solid rgba(255,255,255,0.05);">
                    <div style="font-size:0.75rem;color:#94a3b8;text-transform:uppercase;">Calorie Totali</div>
                    <div style="font-size:1.3rem;font-weight:700;color:#fb923c;margin-top:2px;">${wCal} <small style="font-size:0.75rem;font-weight:400;color:#94a3b8;">kcal</small></div>
                  </div>
                  <div style="background:rgba(255,255,255,0.03);padding:10px;border-radius:8px;border:1px solid rgba(255,255,255,0.05);">
                    <div style="font-size:0.75rem;color:#94a3b8;text-transform:uppercase;">Energia Spesa</div>
                    <div style="font-size:1.3rem;font-weight:700;color:#fbbf24;margin-top:2px;">${wKj} <small style="font-size:0.75rem;font-weight:400;color:#94a3b8;">kJ</small></div>
                  </div>
                  <div style="background:rgba(255,255,255,0.03);padding:10px;border-radius:8px;border:1px solid rgba(255,255,255,0.05);">
                    <div style="font-size:0.75rem;color:#94a3b8;text-transform:uppercase;">FC Media 24h</div>
                    <div style="font-size:1.3rem;font-weight:700;color:#38bdf8;margin-top:2px;">${latestWhoop.avg_hr != null ? latestWhoop.avg_hr + " bpm" : "--"}</div>
                  </div>
                  <div style="background:rgba(255,255,255,0.03);padding:10px;border-radius:8px;border:1px solid rgba(255,255,255,0.05);">
                    <div style="font-size:0.75rem;color:#94a3b8;text-transform:uppercase;">FC Massima 24h</div>
                    <div style="font-size:1.3rem;font-weight:700;color:#ef4444;margin-top:2px;">${latestWhoop.max_hr != null ? latestWhoop.max_hr + " bpm" : "--"}</div>
                  </div>
                </div>
              </div>
            </section>

            <!-- Sleep Coach & Architecture Card -->
            <section class="card" style="margin-bottom:16px;">
              <div class="card-header">
                <div>
                  <div class="card-title" style="display:flex;align-items:center;gap:8px;">
                    <span>🌙</span> WHOOP SLEEP COACH & ARCHITETTURA DEL SONNO
                  </div>
                  <div class="subtitle" style="margin-top:2px;">
                    Sonno effettivo, debito accumulato, stadi REM/Profondo e frequenza respiratoria
                  </div>
                </div>
                <div>
                  <span class="pill pill-purple" style="font-size:0.9rem;padding:6px 12px;">
                    Performance: <strong>${wSleepPerf}%</strong>
                  </span>
                </div>
              </div>

              <!-- Sleep Stages Bar -->
              <div style="margin:16px 0 20px;">
                <div style="display:flex;justify-content:space-between;font-size:0.85rem;margin-bottom:8px;">
                  <span>Tempo a letto: <strong>${(latestWhoop.time_in_bed_hours || wSleepActual || 0).toFixed(1)} ore</strong></span>
                  <span>Sonno reale dormito: <strong style="color:#a78bfa;">${(wSleepActual || 0).toFixed(1)} ore</strong></span>
                  <span>Necessità calcolata: <strong style="color:#38bdf8;">${wSleepNeeded.toFixed(1)} ore</strong></span>
                </div>

                <div style="height:22px;background:rgba(255,255,255,0.06);border-radius:8px;overflow:hidden;display:flex;">
                  <div style="width:${deepPct}%;background:#3b82f6;height:100%;" title="Profondo / SWS: ${deepH}h (${deepPct}%)"></div>
                  <div style="width:${remPct}%;background:#8b5cf6;height:100%;" title="REM: ${remH}h (${remPct}%)"></div>
                  <div style="width:${lightPct}%;background:#06b6d4;height:100%;" title="Leggero: ${lightH}h (${lightPct}%)"></div>
                  <div style="width:${awakePct}%;background:#ef4444;height:100%;" title="Sveglio nel letto: ${awakeH}h (${awakePct}%)"></div>
                </div>

                <div style="display:flex;gap:16px;flex-wrap:wrap;font-size:0.8rem;margin-top:8px;color:#94a3b8;">
                  <span style="display:flex;align-items:center;gap:6px;"><span style="width:10px;height:10px;border-radius:2px;background:#3b82f6;display:inline-block;"></span> Profondo (SWS): <strong>${deepH}h (${deepPct}%)</strong></span>
                  <span style="display:flex;align-items:center;gap:6px;"><span style="width:10px;height:10px;border-radius:2px;background:#8b5cf6;display:inline-block;"></span> REM: <strong>${remH}h (${remPct}%)</strong></span>
                  <span style="display:flex;align-items:center;gap:6px;"><span style="width:10px;height:10px;border-radius:2px;background:#06b6d4;display:inline-block;"></span> Leggero: <strong>${lightH}h (${lightPct}%)</strong></span>
                  <span style="display:flex;align-items:center;gap:6px;"><span style="width:10px;height:10px;border-radius:2px;background:#ef4444;display:inline-block;"></span> Sveglio: <strong>${awakeH}h (${awakePct}%)</strong></span>
                </div>
              </div>

              <!-- Sleep Metrics Grid -->
              <div class="grid-4">
                <div class="kpi-card">
                  <div class="kpi-label">Debito di Sonno</div>
                  <div class="kpi-value" style="color:${wSleepDebt > 45 ? "#ef4444" : (wSleepDebt > 20 ? "#f59e0b" : "#10b981")};">
                    ${wSleepDebt} <small style="font-size:0.85rem;color:#94a3b8;">min</small>
                  </div>
                  <div class="kpi-sub">${wSleepDebt === 0 ? "Nessun debito" : "Da recuperare stanotte"}</div>
                </div>

                <div class="kpi-card">
                  <div class="kpi-label">Efficienza Sonno</div>
                  <div class="kpi-value" style="color:#10b981;">
                    ${wSleepEff != null ? wSleepEff + "%" : "--"}
                  </div>
                  <div class="kpi-sub">Tempo dormito su tempo a letto</div>
                </div>

                <div class="kpi-card">
                  <div class="kpi-label">Frequenza Respiratoria</div>
                  <div class="kpi-value" style="color:#06b6d4;">
                    ${wResp}
                  </div>
                  <div class="kpi-sub">Valore notturno di riferimento</div>
                </div>

                <div class="kpi-card">
                  <div class="kpi-label">Disturbi & Cicli</div>
                  <div class="kpi-value" style="color:#e2e8f0;">
                    ${wDisturb} <small style="font-size:0.85rem;color:#94a3b8;">risvegli</small>
                  </div>
                  <div class="kpi-sub">${wCycles} cicli completi di 90 min</div>
                </div>
              </div>
            </section>

            <!-- Recorded Whoop Workouts (if any) -->
            ${
              whoopWorkouts.length
                ? `<section class="card" style="margin-bottom:16px;">
                    <div class="card-header">
                      <div class="card-title">🏃 Allenamenti & Attività Registrate da Whoop</div>
                      <span class="pill pill-blue">${whoopWorkouts.length} sessioni</span>
                    </div>
                    <div class="grid-3">
                      ${whoopWorkouts
                        .map(
                          (w) => `
                        <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);padding:14px;border-radius:10px;">
                          <div style="display:flex;justify-content:space-between;align-items:center;">
                            <strong style="color:#f3f6fc;font-size:1.05rem;">${escapeHtml(w.sport_name || "Attività")}</strong>
                            <span class="pill pill-yellow" style="font-weight:700;">Strain ${w.strain ?? "--"}</span>
                          </div>
                          <div style="margin-top:10px;font-size:0.88rem;color:#94a3b8;display:grid;grid-template-columns:1fr 1fr;gap:6px;">
                            <div>FC Media: <strong style="color:#cbd5e1;">${w.avg_hr ?? "--"} bpm</strong></div>
                            <div>FC Max: <strong style="color:#cbd5e1;">${w.max_hr ?? "--"} bpm</strong></div>
                            <div>Calorie: <strong style="color:#fb923c;">${w.calories ?? "--"} kcal</strong></div>
                            <div>Distanza: <strong style="color:#38bdf8;">${w.distance_km ? w.distance_km + " km" : "--"}</strong></div>
                          </div>
                        </div>`
                        )
                        .join("")}
                    </div>
                  </section>`
                : ""
            }

            <!-- Whoop 30-Day Interactive Chart -->
            <section class="card" style="margin-bottom:16px;">
              <div class="card-header">
                <div>
                  <div class="card-title">📈 Trend Whoop 30 Giorni (Recovery % vs Day Strain vs HRV)</div>
                  <div class="subtitle">Evoluzione del recupero autonomico correlato al carico di lavoro</div>
                </div>
              </div>
              <div style="height:280px;position:relative;">
                <canvas id="chart-w-whoop-trends"></canvas>
              </div>
            </section>

            <!-- Whoop 14-Day Table -->
            <section class="card">
              <div class="card-header">
                <div class="card-title">Storico Dettagliato Whoop (ultimi 14 giorni)</div>
              </div>
              <div style="overflow-x:auto;">
                <table class="data-table">
                  <thead>
                    <tr>
                      <th>Data</th>
                      <th>Recovery</th>
                      <th>Stato</th>
                      <th>Strain</th>
                      <th>HRV</th>
                      <th>FC Riposo</th>
                      <th>Sonno</th>
                      <th>Debito</th>
                      <th>SpO2</th>
                      <th>Respirazione</th>
                      <th>Calorie</th>
                    </tr>
                  </thead>
                  <tbody>
                    ${whoopDays
                      .slice(0, 14)
                      .map((w) => {
                        const st = (w.recovery_state || "GREEN").toUpperCase();
                        const col = st === "GREEN" ? "#10b981" : (st === "YELLOW" ? "#f59e0b" : "#ef4444");
                        return `<tr>
                          <td><strong>${w.date_key}</strong></td>
                          <td style="color:${col};font-weight:700;">${w.recovery_score != null ? w.recovery_score + "%" : "--"}</td>
                          <td><span class="pill" style="background:${col}22;color:${col};font-size:0.75rem;">${st}</span></td>
                          <td style="color:#3b82f6;font-weight:700;">${w.day_strain != null ? w.day_strain : "--"}</td>
                          <td>${w.hrv_rmssd != null ? Math.round(w.hrv_rmssd) + " ms" : "--"}</td>
                          <td>${w.resting_hr ?? "--"} bpm</td>
                          <td>${w.sleep_hours != null ? w.sleep_hours + "h" : "--"}</td>
                          <td style="color:${(w.sleep_debt_minutes || 0) > 30 ? "#ef4444" : "#94a3b8"};">${w.sleep_debt_minutes != null ? w.sleep_debt_minutes + "m" : "--"}</td>
                          <td>${w.spo2_pct != null ? w.spo2_pct + "%" : "--"}</td>
                          <td>${w.respiratory_rate != null ? w.respiratory_rate + " rpm" : "--"}</td>
                          <td>${w.calories != null ? Math.round(w.calories) : "--"}</td>
                        </tr>`;
                      })
                      .join("")}
                  </tbody>
                </table>
              </div>
            </section>
          `
      }
    </div>

    <!-- TAB 2: GARMIN CONNECT METRICS -->
    <div id="section-garmin" style="display:${activeTab === "garmin" ? "block" : "none"};">
      ${
        !days.length
          ? `<div class="card empty-state">
              <h3>Nessun dato Garmin Connect ancora sincronizzato</h3>
              <p class="subtitle" style="margin:10px 0 16px;">Collega il tuo account Garmin Connect per importare Body Battery, Stress, Dinamiche di corsa e Record.</p>
              <button class="btn btn-garmin" id="btn-go-settings-garmin">⌚ Connetti Garmin</button>
            </div>`
          : `
            <!-- Primary Garmin Biometrics -->
            <section class="grid-4" style="margin-bottom:16px;">
              <div class="kpi-card">
                <div class="kpi-label">Stress Medio Oggi</div>
                <div class="kpi-value" style="color:${(latest.stress_avg || 0) > 45 ? "#ef4444" : (latest.stress_avg || 0) > 32 ? "#f59e0b" : "#10b981"}">
                  ${latest.stress_avg != null ? latest.stress_avg : "--"}<span style="font-size:0.95rem;color:#93a1be">/100</span>
                </div>
                <div class="kpi-sub">Picco: ${latest.stress_max ?? "--"} · Media 7g: ${stress7Val}</div>
              </div>

              <div class="kpi-card">
                <div class="kpi-label">Body Battery (Attuale)</div>
                <div class="kpi-value" style="color:#00b4d8;">${latest.body_battery_current ?? latest.body_battery_max ?? "--"}<span style="font-size:0.95rem;color:#93a1be">/100</span></div>
                <div class="kpi-sub">Max: ${latest.body_battery_max ?? "--"} · +${latest.body_battery_charged ?? "--"} / -${latest.body_battery_drained ?? "--"}</div>
              </div>

              <div class="kpi-card">
                <div class="kpi-label">HRV Notturna Garmin</div>
                <div class="kpi-value" style="color:#10b981;">${latest.hrv_avg != null ? Math.round(latest.hrv_avg) + " ms" : "--"}</div>
                <div class="kpi-sub">Stato: <strong>${escapeHtml(latest.hrv_status || "N/D")}</strong> · Media 7g: ${hrv7Val} ms</div>
              </div>

              <div class="kpi-card">
                <div class="kpi-label">Sonno Garmin & VO2</div>
                <div class="kpi-value" style="color:#a78bfa;">${latest.sleep_seconds ? formatHoursMin(latest.sleep_seconds) : "--"}</div>
                <div class="kpi-sub">Score ${latest.sleep_score ?? "--"}/100 · VO2 ${ts.vo2_max ?? latest.vo2_max ?? "--"}</div>
              </div>
            </section>

            <!-- Extended Garmin Metrics -->
            <section class="grid-4" style="margin-bottom:16px;">
              <div class="kpi-card">
                <div class="kpi-label">Training Readiness</div>
                <div class="kpi-value" style="color:#38bdf8;">${latest.training_readiness ?? "--"}<span style="font-size:0.9rem;color:#93a1be">/100</span></div>
                <div class="kpi-sub">Tempo Recupero: ${latest.recovery_time_hours != null ? formatHoursMin(latest.recovery_time_hours * 3600) : "--"}</div>
              </div>

              <div class="kpi-card">
                <div class="kpi-label">SpO2 Garmin</div>
                <div class="kpi-value">${latest.spo2_avg != null ? latest.spo2_avg + "%" : "--"}</div>
                <div class="kpi-sub">Minimo notturno: ${latest.spo2_min != null ? latest.spo2_min + "%" : "--"}</div>
              </div>

              <div class="kpi-card">
                <div class="kpi-label">Calorie Attive & Passi</div>
                <div class="kpi-value" style="color:#fb923c;">${latest.active_calories != null ? latest.active_calories.toLocaleString("it-IT") : "--"} <small style="font-size:0.85rem;color:#94a3b8;">kcal</small></div>
                <div class="kpi-sub">Passi: ${latest.steps != null ? latest.steps.toLocaleString("it-IT") : "--"}</div>
              </div>

              <div class="kpi-card">
                <div class="kpi-label">Minuti di Intensità</div>
                <div class="kpi-value" style="color:#facc15;">
                  ${((latest.intensity_moderate_min || 0) + (latest.intensity_vigorous_min || 0) * 2)} <small style="font-size:0.85rem;color:#94a3b8;">min</small>
                </div>
                <div class="kpi-sub">Mod: ${latest.intensity_moderate_min ?? 0}m · Vig: ${latest.intensity_vigorous_min ?? 0}m</div>
              </div>
            </section>

            <!-- Garmin Charts -->
            <section class="grid-2" style="margin-bottom:16px;">
              <div class="card">
                <div class="card-header"><div class="card-title">Stress Giornaliero & Body Battery Max (30g)</div></div>
                <div style="height:240px;position:relative;"><canvas id="chart-w-stress"></canvas></div>
              </div>
              <div class="card">
                <div class="card-header"><div class="card-title">HRV Notturna & Ore di Sonno Garmin (30g)</div></div>
                <div style="height:240px;position:relative;"><canvas id="chart-w-hrv"></canvas></div>
              </div>
            </section>

            <!-- Garmin Daily Table -->
            <section class="card">
              <div class="card-header"><div class="card-title">Storico Giornaliero Garmin Connect (ultimi 14 giorni)</div></div>
              <div style="overflow-x:auto;">
                <table class="data-table">
                  <thead>
                    <tr>
                      <th>Data</th><th>Stress</th><th>Body Battery</th><th>HRV</th><th>Sonno</th><th>FC Riposo</th><th>SpO2</th><th>Readiness</th><th>Kcal Att.</th><th>Passi</th>
                    </tr>
                  </thead>
                  <tbody>
                    ${days
                      .slice(-14)
                      .reverse()
                      .map(
                        (d) => `<tr>
                          <td><strong>${d.date_key}</strong></td>
                          <td style="color:${d.stress_avg == null ? "#93a1be" : d.stress_avg > 45 ? "#ef4444" : d.stress_avg > 32 ? "#f59e0b" : "#10b981"}"><strong>${d.stress_avg ?? "--"}</strong></td>
                          <td>${d.body_battery_max ?? "--"} / ${d.body_battery_min ?? "--"}</td>
                          <td>${d.hrv_avg != null ? Math.round(d.hrv_avg) + " ms" : "--"}</td>
                          <td>${d.sleep_seconds ? formatHoursMin(d.sleep_seconds) : "--"} (${d.sleep_score ?? "--"})</td>
                          <td>${d.resting_hr ?? "--"} bpm</td>
                          <td>${d.spo2_avg != null ? d.spo2_avg + "%" : "--"}</td>
                          <td>${d.training_readiness ?? "--"}</td>
                          <td>${d.active_calories ?? "--"}</td>
                          <td>${d.steps ? d.steps.toLocaleString("it-IT") : "--"}</td>
                        </tr>`
                      )
                      .join("")}
                  </tbody>
                </table>
              </div>
            </section>
          `
      }
    </div>

    <!-- TAB 3: DUAL-DEVICE MATRIX (WHOOP × GARMIN) -->
    <div id="section-compare" style="display:${activeTab === "compare" ? "block" : "none"};">
      <section class="card" style="margin-bottom:16px;">
        <div class="card-header">
          <div>
            <div class="card-title" style="display:flex;align-items:center;gap:8px;">
              <span>⚖️</span> CONFRONTO DIRETTO: WHOOP 4.0 vs GARMIN CONNECT
            </div>
            <div class="subtitle" style="margin-top:2px;">
              Due sensori di livello mondiale per convalidare il tuo recupero parasimpatico e il carico cardiaco
            </div>
          </div>
        </div>

        <div style="overflow-x:auto;">
          <table class="data-table" style="font-size:0.95rem;">
            <thead>
              <tr style="background:rgba(255,255,255,0.04);">
                <th style="width:25%;">Parametro Biometrico</th>
                <th style="width:35%;color:#f59e0b;">🟡 Whoop 4.0</th>
                <th style="width:35%;color:#00b4d8;">⌚ Garmin Connect</th>
                <th style="width:5%;">Sintonia</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td><strong>Punteggio Recupero</strong></td>
                <td><strong style="color:${wColor};font-size:1.1rem;">${wRec != null ? wRec + "% (" + wState + ")" : "--"}</strong></td>
                <td><strong style="color:#00b4d8;font-size:1.1rem;">${latest.training_readiness != null ? latest.training_readiness + "/100" : (latest.body_battery_max != null ? latest.body_battery_max + "% BB" : "--")}</strong></td>
                <td>${wRec != null && latest.body_battery_max != null && Math.abs(wRec - latest.body_battery_max) < 15 ? "🟢 Alta" : "🟡 Media"}</td>
              </tr>
              <tr>
                <td><strong>HRV Notturna</strong></td>
                <td><strong style="color:#10b981;">${wHrv} ms</strong> (RMSSD)</td>
                <td><strong style="color:#10b981;">${latest.hrv_avg != null ? Math.round(latest.hrv_avg) + " ms" : "--"}</strong> (${latest.hrv_status || "-"})</td>
                <td>🟢 Conforme</td>
              </tr>
              <tr>
                <td><strong>Carico / Sforzo</strong></td>
                <td><strong style="color:#3b82f6;">Strain ${wStrain} / 21.0</strong> (${wCal} kcal)</td>
                <td><strong style="color:#f59e0b;">Stress ${latest.stress_avg ?? "--"}/100</strong> (${latest.active_calories ?? "--"} kcal)</td>
                <td>🟢 Bilanciato</td>
              </tr>
              <tr>
                <td><strong>Sonno Dormito</strong></td>
                <td><strong>${wSleepActual ? wSleepActual + " ore" : "--"}</strong> (Eff. ${wSleepEff}%)</td>
                <td><strong>${latest.sleep_seconds ? formatHoursMin(latest.sleep_seconds) : "--"}</strong> (Score ${latest.sleep_score ?? "--"})</td>
                <td>🟢 Allineato</td>
              </tr>
              <tr>
                <td><strong>Debito / Recupero</strong></td>
                <td>Debito: <strong style="color:${wSleepDebt > 30 ? "#ef4444" : "#10b981"};">${wSleepDebt} min</strong></td>
                <td>Tempo recupero: <strong>${latest.recovery_time_hours != null ? formatHoursMin(latest.recovery_time_hours * 3600) : "--"}</strong></td>
                <td>🟢 Sincrono</td>
              </tr>
              <tr>
                <td><strong>Frequenza Respiratoria</strong></td>
                <td><strong>${wResp}</strong></td>
                <td><strong>${latest.respiration_sleep != null ? latest.respiration_sleep + " rpm" : (latest.respiration_avg != null ? latest.respiration_avg + " rpm" : "--")}</strong></td>
                <td>🟢 Ottimo</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- Coach Insight Dual-Device -->
      <section class="card" style="border-left:5px solid #10b981;">
        <div class="card-header">
          <div class="card-title" style="display:flex;align-items:center;gap:8px;">
            <img src="/static/icons/calippo.jpg" alt="Calippo" style="width:26px;height:26px;border-radius:50%;" />
            <span>Verdetto Calippo AI sulla Doppia Istanza</span>
          </div>
        </div>
        <p style="margin:0;line-height:1.55;color:#cbd5e1;">
          ${
            wRec != null && latest.body_battery_max != null
              ? `I tuoi due dispositivi concordano: con un Recovery Whoop del <strong>${wRec}%</strong> e un Body Battery Garmin di picco a <strong>${latest.body_battery_max}/100</strong>, hai un quadro parasimpatico chiaro. ` +
                (wRec >= 67 && (latest.stress_avg || 0) < 35
                  ? "Sia Garmin che Whoop danno via libera al carico! Puoi spingere su ritmi target e volume."
                  : "Uno o entrambi i dispositivi segnalano affaticamento o debito di sonno. Non forzare allenamenti lattacidi.")
              : "Collega o aggiorna regolarmente sia Garmin che Whoop per ottenere l'analisi comparata incrociata da parte di Calippo AI."
          }
        </p>
      </section>
    </div>
  `;

  // Render Charts
  if (hasWhoop && activeTab === "whoop") {
    renderWhoopTrendsChart("chart-w-whoop-trends", whoopDays.slice(-30).reverse());
  }
  if (hasGarmin && activeTab === "garmin") {
    renderGarminStressChart("chart-w-stress", days);
    renderHrvSleepChart("chart-w-hrv", days);
  }

  // Tab switching events
  document.getElementById("tab-whoop")?.addEventListener("click", () => {
    activeTab = "whoop";
    renderWellness(container, navigate, isStale);
  });
  document.getElementById("tab-garmin")?.addEventListener("click", () => {
    activeTab = "garmin";
    renderWellness(container, navigate, isStale);
  });
  document.getElementById("tab-compare")?.addEventListener("click", () => {
    activeTab = "compare";
    renderWellness(container, navigate, isStale);
  });

  // Action button events
  document.getElementById("w-connect-whoop-btn")?.addEventListener("click", () => navigate("settings"));
  document.getElementById("btn-go-settings-garmin")?.addEventListener("click", () => navigate("settings"));

  document.getElementById("btn-sync-whoop-now")?.addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    btn.textContent = "Sincronizzazione Whoop...";
    try {
      const res = await api.syncWhoop();
      showToast(`Whoop sincronizzato (${res.synced_days || 0} giorni)!`, "success");
      renderWellness(container, navigate, isStale);
    } catch (err) {
      showToast(err.message, "error");
      btn.disabled = false;
      btn.textContent = "↻ Sync Whoop";
    }
  });

  document.getElementById("btn-sync-garmin-fast")?.addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    btn.textContent = "Aggiornamento...";
    try {
      const res = await api.syncGarmin(3, false);
      showToast(`Garmin aggiornato in ${res.duration_s ?? "?"}s!`, "success");
      renderWellness(container, navigate, isStale);
    } catch (err) {
      showToast(err.message, "error");
      btn.disabled = false;
      btn.textContent = "⚡ Sync Garmin (3s)";
    }
  });

  // Whoop Quick Checkin Modal
  document.getElementById("btn-whoop-quick-checkin")?.addEventListener("click", () => {
    openWhoopCheckinModal(latestWhoop, () => {
      renderWellness(container, navigate, isStale);
    });
  });
}

export function openWhoopCheckinModal(latestWhoop, onSuccess) {
  const todayStr = new Date().toISOString().slice(0, 10);
  const existingRec = latestWhoop ? latestWhoop.recovery_score || "" : "";
  const existingStrain = latestWhoop ? latestWhoop.day_strain || "" : "";
  const existingHrv = latestWhoop ? latestWhoop.hrv_rmssd || "" : "";
  const existingRhr = latestWhoop ? latestWhoop.resting_hr || "" : "";
  const existingSleep = latestWhoop ? latestWhoop.sleep_hours || "" : "";

  const modal = document.createElement("div");
  modal.style.cssText = "position:fixed;inset:0;background:rgba(0,0,0,0.75);display:flex;align-items:center;justify-content:center;z-index:9999;padding:16px;";
  modal.innerHTML = `
    <div class="card" style="max-width:440px;width:100%;max-height:90vh;overflow-y:auto;border:1px solid rgba(245,158,11,0.5);">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
        <h3 style="margin:0;font-size:1.15rem;display:flex;align-items:center;gap:8px;">
          <span>🟡</span> Check-in Rapido Whoop 4.0
        </h3>
        <button class="btn btn-ghost btn-sm" id="modal-close" style="padding:4px 8px;">✕</button>
      </div>
      <p class="subtitle" style="margin-bottom:14px;font-size:0.85rem;">
        Inserisci o aggiorna i valori Whoop di oggi in 5 secondi:
      </p>

      <form id="whoop-checkin-form">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">
          <div>
            <label style="font-size:0.75rem;color:#94a3b8;display:block;margin-bottom:4px;">Data</label>
            <input type="date" id="chk-date" class="input" value="${todayStr}" required style="padding:8px 10px;font-size:0.9rem;" />
          </div>
          <div>
            <label style="font-size:0.75rem;color:#94a3b8;display:block;margin-bottom:4px;">Recovery Score %</label>
            <input type="number" id="chk-rec" class="input" min="0" max="100" placeholder="es. 84" value="${existingRec}" required style="padding:8px 10px;font-size:0.9rem;" />
          </div>
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">
          <div>
            <label style="font-size:0.75rem;color:#94a3b8;display:block;margin-bottom:4px;">Day Strain (0-21)</label>
            <input type="number" step="0.1" id="chk-strain" class="input" min="0" max="21" placeholder="es. 14.8" value="${existingStrain}" style="padding:8px 10px;font-size:0.9rem;" />
          </div>
          <div>
            <label style="font-size:0.75rem;color:#94a3b8;display:block;margin-bottom:4px;">HRV RMSSD (ms)</label>
            <input type="number" step="0.1" id="chk-hrv" class="input" placeholder="es. 74" value="${existingHrv}" style="padding:8px 10px;font-size:0.9rem;" />
          </div>
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">
          <div>
            <label style="font-size:0.75rem;color:#94a3b8;display:block;margin-bottom:4px;">FC a Riposo (bpm)</label>
            <input type="number" id="chk-rhr" class="input" placeholder="es. 50" value="${existingRhr}" style="padding:8px 10px;font-size:0.9rem;" />
          </div>
          <div>
            <label style="font-size:0.75rem;color:#94a3b8;display:block;margin-bottom:4px;">Ore di Sonno (h)</label>
            <input type="number" step="0.1" id="chk-sleep" class="input" placeholder="es. 7.5" value="${existingSleep}" style="padding:8px 10px;font-size:0.9rem;" />
          </div>
        </div>

        <div style="display:flex;gap:10px;margin-top:16px;">
          <button type="submit" class="btn btn-primary" style="flex:1;background:#f59e0b;color:#090c14;border:none;font-weight:700;">
            💾 Salva Dati Whoop
          </button>
          <button type="button" class="btn btn-ghost" id="modal-cancel">Annulla</button>
        </div>
      </form>
    </div>
  `;

  document.body.appendChild(modal);

  const closeModal = () => modal.remove();
  modal.querySelector("#modal-close")?.addEventListener("click", closeModal);
  modal.querySelector("#modal-cancel")?.addEventListener("click", closeModal);

  modal.querySelector("#whoop-checkin-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = {
      date: document.getElementById("chk-date").value,
      recovery_score: parseInt(document.getElementById("chk-rec").value, 10),
      day_strain: parseFloat(document.getElementById("chk-strain").value) || null,
      hrv_rmssd: parseFloat(document.getElementById("chk-hrv").value) || null,
      resting_hr: parseInt(document.getElementById("chk-rhr").value, 10) || null,
      sleep_hours: parseFloat(document.getElementById("chk-sleep").value) || null,
    };

    try {
      await api.manualWhoopEntry(payload);
      showToast("Dati Whoop salvati con successo!", "success");
      closeModal();
      if (typeof onSuccess === "function") onSuccess();
    } catch (err) {
      showToast(err.message, "error");
    }
  });
}
