import { api, escapeHtml, formatHoursMin, formatMinHM, formatPace, formatRaceTime, showToast } from "../api.js";
import { renderGarminStressChart, renderHrvSleepChart } from "../charts.js";

function formatPrValue(pr) {
  if (pr.value == null) return "--";
  if (pr.unit === "time" || [1, 2, 3, 4, 5, 6].includes(pr.type_id)) return formatRaceTime(pr.value);
  if (pr.unit === "steps" || [12, 13, 14].includes(pr.type_id)) return `${Math.round(pr.value).toLocaleString("it-IT")} passi`;
  if (pr.unit === "distance" || pr.type_id === 7) return `${(pr.value / 1000).toFixed(2)} km`;
  return String(Math.round(pr.value));
}

export async function renderWellness(container, navigate, isStale = () => false) {
  container.innerHTML = `<div class="loading-state">Caricamento dati completi Garmin Connect...</div>`;
  let data;
  try {
    data = await api.getWellness(30);
  } catch (err) {
    if (isStale()) return;
    container.innerHTML = `<div class="card empty-state">Errore: ${escapeHtml(err.message)}</div>`;
    return;
  }
  if (isStale()) return;

  const days = data.days || [];
  const latest = data.latest;
  const snaps = data.snapshots || {};

  if (!days.length) {
    container.innerHTML = `
      <div class="card empty-state">
        <h3>Nessun dato Garmin Connect ancora sincronizzato</h3>
        <p class="subtitle" style="margin:10px 0 18px;">
          Collega il tuo account Garmin Connect per importare Stress, Body Battery, HRV, Sonno, SpO2, Training Status, Running Dynamics, Scarpe e Record.
        </p>
        <div style="display:flex;gap:10px;justify-content:center;flex-wrap:wrap;">
          <button class="btn btn-garmin" id="w-go-settings">⌚ Collega Garmin Connect</button>
          <button class="btn btn-ghost" id="w-load-demo">✨ Carica Dati Demo</button>
        </div>
      </div>`;
    document.getElementById("w-go-settings")?.addEventListener("click", () => navigate("settings"));
    document.getElementById("w-load-demo")?.addEventListener("click", async (e) => {
      const btn = e.currentTarget;
      btn.disabled = true;
      try {
        await api.seedDemo();
        showToast("Dati demo caricati!", "success");
        renderWellness(container, navigate, isStale);
      } catch (err) {
        showToast(err.message, "error");
        btn.disabled = false;
      }
    });
    return;
  }

  const stressRest = latest.stress_rest_min || 0;
  const stressLow = latest.stress_low_min || 0;
  const stressMed = latest.stress_medium_min || 0;
  const stressHigh = latest.stress_high_min || 0;
  const stressTot = Math.max(1, stressRest + stressLow + stressMed + stressHigh);

  const sleepDeep = latest.sleep_deep_sec || 0;
  const sleepRem = latest.sleep_rem_sec || 0;
  const sleepLight = latest.sleep_light_sec || 0;
  const sleepTot = Math.max(1, sleepDeep + sleepRem + sleepLight);

  const avgStress7 = days.slice(-7).filter((d) => d.stress_avg != null);
  const stress7Val = avgStress7.length
    ? Math.round(avgStress7.reduce((s, d) => s + d.stress_avg, 0) / avgStress7.length)
    : "--";

  const avgHrv7 = days.slice(-7).filter((d) => d.hrv_avg != null);
  const hrv7Val = avgHrv7.length
    ? Math.round(avgHrv7.reduce((s, d) => s + d.hrv_avg, 0) / avgHrv7.length)
    : "--";

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

  const hasExtendedSnaps = Object.keys(snaps).length > 0;

  container.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;">
      <div class="subtitle">
        Giorno: <strong>${latest.date_key}</strong>
        ${latest.watch_sync_time ? ` · ⌚ Orologio → Cloud: <strong>${escapeHtml(latest.watch_sync_time.slice(11, 16))}</strong>` : ""}
        ${data.garmin_last_sync ? ` · App Sync: ${data.garmin_last_sync.slice(11, 16)}` : ""}
        ${devices.length ? ` · ${escapeHtml(devices[0].name)}` : ""}
      </div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;">
        ${
          data.garmin_connected
            ? `<button class="btn btn-garmin btn-sm" id="btn-sync-garmin-fast">⚡ Aggiorna Oggi (3s)</button>
               <button class="btn btn-ghost btn-sm" id="btn-sync-garmin-now">↻ Sync Completo 21g</button>`
            : `<button class="btn btn-garmin btn-sm" id="btn-connect-garmin">⌚ Collega Account Garmin Reale</button>`
        }
      </div>
    </div>

    ${
      !hasExtendedSnaps && data.garmin_connected
        ? `<div class="banner">
            <div>
              <strong>Nuovi dati Garmin sbloccati!</strong>
              <p class="subtitle" style="margin-top:4px;">
                Clicca <b>Sincronizza Tutto Garmin</b> qui sopra per scaricare subito Training Status, Endurance/Hill Score, Previsioni Gara Garmin, SpO2, Respirazione, Running Dynamics (Potenza/GCT/Falcata), Scarpe e Record Personali!
              </p>
            </div>
          </div>`
        : ""
    }

    <!-- Primary Biometrics -->
    <section class="grid-4">
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
        <div class="kpi-label">HRV Notturna</div>
        <div class="kpi-value" style="color:#10b981;">${latest.hrv_avg != null ? Math.round(latest.hrv_avg) + " ms" : "--"}</div>
        <div class="kpi-sub">Stato: <strong>${escapeHtml(latest.hrv_status || "N/D")}</strong> · Media 7g: ${hrv7Val} ms</div>
      </div>

      <div class="kpi-card">
        <div class="kpi-label">Sonno & FC Riposo</div>
        <div class="kpi-value" style="color:#a78bfa;">${latest.sleep_seconds ? formatHoursMin(latest.sleep_seconds) : "--"}</div>
        <div class="kpi-sub">Score ${latest.sleep_score ?? "--"}/100 · RHR ${latest.resting_hr ?? "--"} bpm · VO2 ${ts.vo2_max ?? latest.vo2_max ?? "--"}</div>
      </div>
    </section>

    <!-- Extended Biometrics (SpO2, Respiration, Calories, Intensity, Readiness) -->
    <section class="grid-4">
      <div class="kpi-card">
        <div class="kpi-label">Training Readiness & VO2</div>
        <div class="kpi-value" style="color:#38bdf8;">${latest.training_readiness ?? "--"}<span style="font-size:0.9rem;color:#93a1be">/100</span></div>
        <div class="kpi-sub">VO2 Max: <strong>${ts.vo2_max ?? latest.vo2_max ?? "--"}</strong>${ts.vo2_max_precise ? ` (${ts.vo2_max_precise})` : ""} · Recupero: ${latest.recovery_time_hours != null ? formatHoursMin(latest.recovery_time_hours * 3600) : "--"}</div>
      </div>

      <div class="kpi-card">
        <div class="kpi-label">SpO2 & Respirazione</div>
        <div class="kpi-value">${latest.spo2_avg != null ? latest.spo2_avg + "%" : "--"}</div>
        <div class="kpi-sub">Min SpO2: ${latest.spo2_min ?? "--"}% · Resp: ${latest.respiration_avg ?? "--"}/${latest.respiration_sleep ?? "--"} rpm</div>
      </div>

      <div class="kpi-card">
        <div class="kpi-label">Calorie & Intensità</div>
        <div class="kpi-value">${latest.active_calories ?? "--"} <span style="font-size:0.9rem;color:#93a1be;">kcal att.</span></div>
        <div class="kpi-sub">Mod: ${latest.intensity_moderate_min ?? 0}m · Vig: ${latest.intensity_vigorous_min ?? 0}m · Piani: ${latest.floors_ascended ?? "--"}</div>
      </div>

      <div class="kpi-card">
        <div class="kpi-label">Endurance / Hill / Peso</div>
        <div class="kpi-value" style="color:#fb923c;">${sc.endurance_score ?? "--"} <span style="font-size:0.9rem;color:#93a1be;">/ ${sc.hill_score ?? "--"}</span></div>
        <div class="kpi-sub">Peso: <strong>${bc.weight_kg ? bc.weight_kg + " kg" : "--"}</strong>${bc.body_fat_pct ? ` · Grasso ${bc.body_fat_pct}%` : ""}</div>
      </div>
    </section>

    <!-- Training Status, Load Focus & Garmin Race Predictor -->
    ${
      ts.status_phrase || gp.time_5k_sec
        ? `<section class="grid-2">
            <div class="card">
              <div class="card-header">
                <div class="card-title">📊 Garmin Training Status & Load Focus</div>
                <span class="pill pill-cyan">${escapeHtml(ts.status_phrase || "Sincronizzato")}</span>
              </div>
              <div class="grid-auto" style="margin-bottom:10px;">
                <div><div class="kpi-label">Carico Acuto / Cronico</div><div style="font-size:1.1rem;font-weight:700;">${ts.acute_load ?? "--"} / ${ts.chronic_load ?? "--"}</div></div>
                <div><div class="kpi-label">Rapporto ACWR</div><div style="font-size:1.1rem;font-weight:700;">${ts.acwr_ratio ?? "--"} (${escapeHtml(ts.acwr_status || "-")})</div></div>
                <div><div class="kpi-label">Focus Carico</div><div style="font-size:0.92rem;font-weight:700;color:#38bdf8;">${escapeHtml(ts.load_focus_phrase || "--")}</div></div>
              </div>
              <div style="display:flex;gap:14px;flex-wrap:wrap;font-size:0.83rem;color:#cbd5e1;">
                <span>🔵 Aerobico Basso: <strong>${ts.monthly_load_aerobic_low ?? "--"}</strong></span>
                <span>🟠 Aerobico Alto: <strong>${ts.monthly_load_aerobic_high ?? "--"}</strong></span>
                <span>🟣 Anaerobico: <strong>${ts.monthly_load_anaerobic ?? "--"}</strong></span>
              </div>
            </div>

            <div class="card">
              <div class="card-header">
                <div class="card-title">🏁 Previsioni Gara Ufficiali Garmin</div>
                <span class="pill pill-orange">Firstbeat Watch</span>
              </div>
              <div class="grid-4" style="gap:10px;">
                <div style="padding:10px;border-radius:10px;background:rgba(255,255,255,0.04);text-align:center;">
                  <div class="kpi-label">5 km</div>
                  <div style="font-size:1.15rem;font-weight:800;margin-top:4px;">${formatRaceTime(gp.time_5k_sec)}</div>
                </div>
                <div style="padding:10px;border-radius:10px;background:rgba(255,255,255,0.04);text-align:center;">
                  <div class="kpi-label">10 km</div>
                  <div style="font-size:1.15rem;font-weight:800;margin-top:4px;">${formatRaceTime(gp.time_10k_sec)}</div>
                </div>
                <div style="padding:10px;border-radius:10px;background:rgba(255,255,255,0.04);text-align:center;">
                  <div class="kpi-label">Mezza</div>
                  <div style="font-size:1.15rem;font-weight:800;margin-top:4px;">${formatRaceTime(gp.time_half_sec)}</div>
                </div>
                <div style="padding:10px;border-radius:10px;background:rgba(255,255,255,0.04);text-align:center;">
                  <div class="kpi-label">Maratona</div>
                  <div style="font-size:1.15rem;font-weight:800;margin-top:4px;">${formatRaceTime(gp.time_marathon_sec)}</div>
                </div>
              </div>
            </div>
          </section>`
        : ""
    }

    <!-- Stress Distribution & Sleep Stages -->
    <section class="grid-2">
      <div class="card">
        <div class="card-header">
          <div class="card-title">⚡ Distribuzione Stress Garmin (${latest.date_key})</div>
        </div>
        <div class="stacked-bar">
          <div style="width:${(stressRest / stressTot) * 100}%;background:#00b4d8" title="Riposo"></div>
          <div style="width:${(stressLow / stressTot) * 100}%;background:#10b981" title="Stress Basso"></div>
          <div style="width:${(stressMed / stressTot) * 100}%;background:#f59e0b" title="Stress Medio"></div>
          <div style="width:${(stressHigh / stressTot) * 100}%;background:#ef4444" title="Stress Alto"></div>
        </div>
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:10px;font-size:0.82rem;">
          <div><span style="color:#00b4d8">●</span> Riposo<br/><strong>${formatMinHM(stressRest)}</strong></div>
          <div><span style="color:#10b981">●</span> Basso<br/><strong>${formatMinHM(stressLow)}</strong></div>
          <div><span style="color:#f59e0b">●</span> Medio<br/><strong>${formatMinHM(stressMed)}</strong></div>
          <div><span style="color:#ef4444">●</span> Alto<br/><strong>${formatMinHM(stressHigh)}</strong></div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <div class="card-title">🌙 Fasi del Sonno (${latest.date_key})</div>
        </div>
        <div class="stacked-bar">
          <div style="width:${(sleepDeep / sleepTot) * 100}%;background:#6366f1" title="Profondo"></div>
          <div style="width:${(sleepRem / sleepTot) * 100}%;background:#a855f7" title="REM"></div>
          <div style="width:${(sleepLight / sleepTot) * 100}%;background:#38bdf8" title="Leggero"></div>
        </div>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:10px;font-size:0.82rem;">
          <div><span style="color:#6366f1">●</span> Profondo<br/><strong>${formatHoursMin(sleepDeep)}</strong></div>
          <div><span style="color:#a855f7">●</span> REM<br/><strong>${formatHoursMin(sleepRem)}</strong></div>
          <div><span style="color:#38bdf8">●</span> Leggero<br/><strong>${formatHoursMin(sleepLight)}</strong></div>
        </div>
      </div>
    </section>

    <!-- 30-day charts -->
    <section class="grid-2">
      <div class="card">
        <div class="card-header"><div class="card-title">Stress Medio vs Body Battery (30 giorni)</div></div>
        <div class="chart-box"><canvas id="chart-w-stress"></canvas></div>
      </div>
      <div class="card">
        <div class="card-header"><div class="card-title">HRV Notturna & Ore di Sonno (30 giorni)</div></div>
        <div class="chart-box"><canvas id="chart-w-hrv"></canvas></div>
      </div>
    </section>

    <!-- Garmin Running Dynamics & Training Effect -->
    ${
      gActs.length
        ? `<section class="card">
            <div class="card-header">
              <div class="card-title">⚙️ Running Dynamics & Training Effect (Ultime Corse Garmin)</div>
              <span class="pill pill-violet">Potenza · GCT · Falcata · TE</span>
            </div>
            <div style="overflow-x:auto;">
              <table class="data-table">
                <thead>
                  <tr><th>Data</th><th>Corsa</th><th>Km</th><th>Passo</th><th>Potenza</th><th>GCT</th><th>Osc. Vert.</th><th>Falcata</th><th>TE Aero / Anaero</th></tr>
                </thead>
                <tbody>
                  ${gActs
                    .slice(0, 12)
                    .map(
                      (a) => `<tr>
                        <td><strong>${a.date}</strong></td>
                        <td>${escapeHtml(a.name)}</td>
                        <td>${a.distance_km} km</td>
                        <td>${formatPace(a.pace_sec_km)}/km</td>
                        <td><strong>${a.avg_power_w ? a.avg_power_w + " W" : "--"}</strong></td>
                        <td>${a.gct_ms ? a.gct_ms + " ms" : "--"}</td>
                        <td>${a.vertical_osc_cm ? a.vertical_osc_cm + " cm" : "--"}</td>
                        <td>${a.stride_len_cm ? a.stride_len_cm + " cm" : "--"}</td>
                        <td>${a.aerobic_te ?? "--"} / ${a.anaerobic_te ?? "--"} <span class="subtitle">${escapeHtml(a.te_label || "")}</span></td>
                      </tr>`
                    )
                    .join("")}
                </tbody>
              </table>
            </div>
          </section>`
        : ""
    }

    <!-- Gear (Shoes) & Personal Records -->
    ${
      gear.length || prs.length
        ? `<section class="grid-2">
            <div class="card">
              <div class="card-header"><div class="card-title">👟 Scarpe & Equipaggiamento Garmin</div></div>
              ${
                gear.length
                  ? `<div style="display:flex;flex-direction:column;gap:12px;">
                      ${gear
                        .map((g) => {
                          const pct = g.max_km ? Math.min(100, Math.round((g.distance_km / g.max_km) * 100)) : 0;
                          return `<div>
                            <div style="display:flex;justify-content:space-between;font-size:0.86rem;margin-bottom:4px;">
                              <strong>${escapeHtml(g.name)}</strong>
                              <span><strong>${g.distance_km} km</strong>${g.max_km ? ` / ${g.max_km} km` : ""} (${g.activities_count} corse)</span>
                            </div>
                            ${g.max_km ? `<div class="progress-track"><div class="progress-fill" style="width:${pct}%;background:${pct > 85 ? "#ef4444" : "#00b4d8"}"></div></div>` : ""}
                          </div>`;
                        })
                        .join("")}
                    </div>`
                  : `<div class="subtitle">Nessuna scarpa registrata su Garmin Connect.</div>`
              }
            </div>

            <div class="card">
              <div class="card-header"><div class="card-title">🏆 Record Personali Garmin (PR)</div></div>
              ${
                prs.length
                  ? `<div style="display:grid;grid-template-columns:repeat(2,1fr);gap:10px;">
                      ${prs
                        .slice(0, 8)
                        .map(
                          (p) => `<div style="padding:10px 12px;border-radius:10px;background:rgba(255,255,255,0.04);border:1px solid var(--border);">
                            <div class="kpi-label">${escapeHtml(p.label)}</div>
                            <div style="font-size:1.08rem;font-weight:800;margin-top:2px;">${formatPrValue(p)}</div>
                            <div class="subtitle" style="font-size:0.74rem;">${escapeHtml(p.date || "")}</div>
                          </div>`
                        )
                        .join("")}
                    </div>`
                  : `<div class="subtitle">Nessun record personale trovato.</div>`
              }
            </div>
          </section>`
        : ""
    }

    <!-- Daily Table -->
    <section class="card">
      <div class="card-header"><div class="card-title">Storico Giornaliero Garmin (ultimi 14 giorni)</div></div>
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
  `;

  renderGarminStressChart("chart-w-stress", days);
  renderHrvSleepChart("chart-w-hrv", days);

  document.getElementById("btn-connect-garmin")?.addEventListener("click", () => navigate("settings"));
  document.getElementById("btn-sync-garmin-fast")?.addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    btn.textContent = "Aggiornamento rapido...";
    try {
      const res = await api.syncGarmin(3, false);
      showToast(`Garmin aggiornato in ${res.duration_s ?? "?"}s (${res.days_synced} giorni)!`, "success");
      renderWellness(container, navigate);
    } catch (err) {
      showToast(err.message, "error");
      btn.disabled = false;
      btn.textContent = "⚡ Aggiorna Oggi (3s)";
    }
  });
  document.getElementById("btn-sync-garmin-now")?.addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    btn.textContent = "Sincronizzazione 21g...";
    try {
      const res = await api.syncGarmin(21, true);
      const extCount = Object.keys(res.extended || {}).length;
      showToast(`Garmin sincronizzato in ${res.duration_s ?? "?"}s: ${res.days_synced}g + ${extCount} moduli!`, "success");
      renderWellness(container, navigate);
    } catch (err) {
      showToast(err.message, "error");
      btn.disabled = false;
      btn.textContent = "↻ Sync Completo 21g";
    }
  });
}
