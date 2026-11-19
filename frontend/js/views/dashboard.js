import {
  api,
  categoryBadge,
  escapeHtml,
  formatDuration,
  formatHoursMin,
  formatPace,
  formatRaceTime,
  showToast,
  simpleMarkdown,
} from "../api.js";
import {
  renderGarminStressChart,
  renderLoadChart,
  renderWeeklyVolumeChart,
} from "../charts.js";
import { openActivityModal } from "./activities.js";

export async function renderDashboard(container, navigate, isStale = () => false) {
  container.innerHTML = `<div class="loading-state">Analisi dati Strava e Garmin in corso...</div>`;
  let data;
  try {
    data = await api.getDashboard(false);
  } catch (err) {
    if (isStale()) return;
    container.innerHTML = `<div class="card empty-state">Errore caricamento dashboard: ${escapeHtml(err.message)}</div>`;
    return;
  }
  if (isStale()) return;

  const { summary, daily_advice, recent_activities, active_goal, connections } = data;
  const r = summary.readiness;
  const load = summary.load.current;
  const lg = summary.latest_garmin;
  const weeklyGoal = summary.weekly_goal_km || 40;
  const weeklyPct = Math.min(100, Math.round((summary.load.this_week_km / weeklyGoal) * 100));

  const badgeClass = {
    prime: "pill-green",
    moderate: "pill-amber",
    recovery: "pill-orange",
    rest: "pill-red",
  }[r.zone] || "pill-cyan";

  const showOnboarding = !connections.strava_connected && !connections.garmin_connected;
  const hasRuns = recent_activities && recent_activities.length > 0;

  container.innerHTML = `
    ${
      showOnboarding
        ? `<div class="banner">
            <div>
              <strong>Collega Strava e Garmin per iniziare con i tuoi dati reali</strong>
              <p class="subtitle" style="margin-top:4px;">
                Vai in <b>Connessioni</b> per associare subito il tuo account Strava (OAuth2) e Garmin Connect.
                ${!hasRuns ? "Oppure carica un set di 60 giorni demo per esplorare subito tutti i grafici." : ""}
              </p>
            </div>
            <div style="display:flex;gap:10px;flex-wrap:wrap;">
              <button class="btn btn-primary btn-sm" id="dash-go-settings">🔗 Connetti Strava & Garmin</button>
              ${
                !hasRuns
                  ? `<button class="btn btn-ghost btn-sm" id="dash-load-demo">✨ Prova con Dati Demo</button>`
                  : ""
              }
            </div>
          </div>`
        : ""
    }

    <!-- Daily Coach Hero -->
    <section class="coach-hero">
      <div class="readiness-ring-wrap">
        <div class="readiness-ring" style="background: conic-gradient(${r.color} ${r.score * 3.6}deg, rgba(255,255,255,0.08) 0deg);">
          <div class="readiness-ring-inner">
            <div class="readiness-score" style="color:${r.color}">${r.score}</div>
            <div class="readiness-tag">Readiness</div>
          </div>
        </div>
        <span class="pill ${badgeClass}">${escapeHtml(r.zone_label)}</span>
      </div>

      <div class="coach-content">
        <div class="coach-headline-row">
          <span class="pill ${badgeClass}">${escapeHtml(daily_advice.badge)}</span>
          <h2 class="coach-headline">${escapeHtml(daily_advice.headline)}</h2>
          <button class="btn btn-ai btn-sm" id="btn-refresh-ai" style="margin-left:auto;">
            ✨ Consiglio AI Gemini
          </button>
        </div>

        <p class="coach-text">${escapeHtml(daily_advice.workout_suggestion)}</p>

        ${
          daily_advice.plan_note
            ? `<div style="font-size:0.86rem;color:#38bdf8;">🎯 ${escapeHtml(daily_advice.plan_note)}</div>`
            : ""
        }

        <div class="coach-meta-chips">
          <span class="chip">⏱️ Passo: ${escapeHtml(daily_advice.target_pace)}</span>
          <span class="chip">💓 Zona: ${escapeHtml(daily_advice.target_zone)}</span>
          <span class="chip">⚡ Stress Garmin: ${lg && lg.stress_avg != null ? lg.stress_avg + "/100" : "N/D"}</span>
          <span class="chip">🔋 Body Battery: ${lg && (lg.body_battery_current ?? lg.body_battery_max) != null ? `${lg.body_battery_current ?? lg.body_battery_max}${lg.body_battery_max != null && lg.body_battery_current != null && lg.body_battery_current !== lg.body_battery_max ? ` (max ${lg.body_battery_max})` : ""}` : "N/D"}</span>
          <span class="chip">📈 HRV: ${lg && lg.hrv_avg != null ? Math.round(lg.hrv_avg) + " ms" : "N/D"}</span>
          <span class="chip">🌙 Sonno: ${lg && lg.sleep_seconds ? formatHoursMin(lg.sleep_seconds) : "N/D"}</span>
        </div>

        ${
          daily_advice.warnings && daily_advice.warnings.length
            ? `<div style="display:flex;flex-direction:column;gap:4px;font-size:0.83rem;color:#fbbf24;">
                ${daily_advice.warnings.map((w) => `<div>⚠️ ${escapeHtml(w)}</div>`).join("")}
               </div>`
            : ""
        }

        <div id="ai-narrative-slot"></div>

        <form class="ask-coach-bar" id="ask-coach-form">
          <img src="/static/icons/calippo.jpg" alt="Calippo" class="calippo-avatar-sm" style="flex-shrink:0;" />
          <input class="input" id="ask-coach-input" placeholder="Chiedi a Calippo (es. 'Ho le gambe pesanti, faccio lo stesso le ripetute?')" />
          <button class="btn btn-ghost" type="submit" id="ask-coach-btn">Chiedi</button>
        </form>
        <div id="ask-coach-reply"></div>
      </div>
    </section>

    <!-- Primary KPIs -->
    <section class="grid-4">
      <div class="kpi-card">
        <div class="kpi-label">Fitness (CTL) / Fatica (ATL)</div>
        <div class="kpi-value">${load.ctl} <span style="font-size:1rem;color:#93a1be;font-weight:600">/ ${load.atl}</span></div>
        <div class="kpi-sub">Forma (TSB): <strong style="color:${load.tsb >= -10 ? "#10b981" : "#f59e0b"}">${load.tsb >= 0 ? "+" : ""}${load.tsb}</strong> · ACWR <strong>${load.acwr}</strong></div>
      </div>

      <div class="kpi-card">
        <div class="kpi-label">Volume Settimana Corrente</div>
        <div class="kpi-value">${summary.load.this_week_km} <span style="font-size:0.95rem;color:#93a1be;">/ ${weeklyGoal} km</span></div>
        <div class="progress-track" style="margin-top:4px;"><div class="progress-fill" style="width:${weeklyPct}%"></div></div>
        <div class="kpi-sub">${summary.load.this_week_runs} corse · 30g: ${summary.stats_30d.km} km (${summary.stats_30d.avg_pace}/km)</div>
      </div>

      <div class="kpi-card">
        <div class="kpi-label">VDOT Stimato & Passo Soglia</div>
        <div class="kpi-value" style="color:#38bdf8;">${summary.vdot}</div>
        <div class="kpi-sub">Soglia: <strong>${summary.paces.threshold.range}</strong> · Facile: ${summary.paces.easy.range}</div>
      </div>

      <div class="kpi-card">
        <div class="kpi-label">Proiezioni Tempi Gara</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px 10px;font-size:0.86rem;margin-top:2px;">
          <div>5K: <strong>${summary.race_predictions["5k"]}</strong></div>
          <div>10K: <strong>${summary.race_predictions["10k"]}</strong></div>
          <div>21K: <strong>${summary.race_predictions["half_marathon"]}</strong></div>
          <div>42K: <strong>${summary.race_predictions["marathon"]}</strong></div>
        </div>
        <div class="kpi-sub">Da ${escapeHtml(summary.vdot_source)}</div>
      </div>
    </section>

    <!-- Active Race Goal strip (if present) -->
    ${
      active_goal
        ? (() => {
            const daysLeft = Math.max(0, Math.ceil((new Date(active_goal.race_date) - new Date()) / 86400000));
            const totalW = active_goal.workouts.filter((w) => w.workout_type !== "rest").length;
            const doneW = active_goal.workouts.filter((w) => w.workout_type !== "rest" && w.completed).length;
            return `<section class="card" style="display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap;border-color:rgba(252,76,2,0.3);">
              <div>
                <div class="pill pill-orange" style="margin-bottom:6px;">🎯 OBIETTIVO GARA ATTIVO · -${daysLeft} GIORNI</div>
                <div style="font-size:1.1rem;font-weight:700;">${escapeHtml(active_goal.name)} — Target ${formatRaceTime(active_goal.target_time_sec)} (${escapeHtml(active_goal.paces?.race_pace || "")})</div>
                <div class="subtitle">Completati ${doneW}/${totalW} allenamenti del piano · Data gara: ${active_goal.race_date}</div>
              </div>
              <button class="btn btn-ghost btn-sm" id="dash-go-plans">Apri Piano Gara →</button>
            </section>`;
          })()
        : ""
    }

    <!-- Charts Row -->
    <section class="grid-2">
      <div class="card">
        <div class="card-header">
          <div class="card-title">📈 Carico Allenamento (CTL / ATL / TSB — 60 giorni)</div>
          <span class="pill pill-muted">Strava TRIMP</span>
        </div>
        <div class="chart-box"><canvas id="chart-load"></canvas></div>
      </div>

      <div class="card">
        <div class="card-header">
          <div class="card-title">🫀 Stress Garmin vs Body Battery (30 giorni)</div>
          <span class="pill pill-cyan">Garmin Wellness</span>
        </div>
        <div class="chart-box"><canvas id="chart-garmin"></canvas></div>
      </div>
    </section>

    <!-- Weekly Volume + Readiness Breakdown -->
    <section class="grid-2">
      <div class="card">
        <div class="card-header">
          <div class="card-title">📊 Chilometri Settimanali (ultime 8 settimane)</div>
        </div>
        <div class="chart-box-sm"><canvas id="chart-weekly"></canvas></div>
      </div>

      <div class="card">
        <div class="card-header">
          <div class="card-title">🧬 Scomposizione Readiness Oggi</div>
        </div>
        <div style="display:flex;flex-direction:column;gap:10px;">
          ${r.components
            .map(
              (c) => `
              <div>
                <div style="display:flex;justify-content:space-between;font-size:0.84rem;margin-bottom:4px;">
                  <span><strong>${escapeHtml(c.label)}</strong> · <span style="color:#93a1be">${escapeHtml(c.value)}</span></span>
                  <span style="font-weight:700;color:${c.score >= 75 ? "#10b981" : c.score >= 55 ? "#f59e0b" : "#ef4444"}">${c.score}/100</span>
                </div>
                <div class="progress-track">
                  <div class="progress-fill" style="width:${c.score}%;background:${c.score >= 75 ? "#10b981" : c.score >= 55 ? "#f59e0b" : "#ef4444"}"></div>
                </div>
              </div>`
            )
            .join("")}
        </div>
      </div>
    </section>

    <!-- Recent Runs -->
    <section class="card">
      <div class="card-header">
        <div class="card-title">🏃 Ultime Corse & Allenamenti</div>
        <button class="btn btn-ghost btn-sm" id="dash-go-activities">Vedi tutte →</button>
      </div>
      ${
        hasRuns
          ? `<div class="activity-list">
              ${recent_activities
                .map(
                  (a) => `
                  <div class="activity-row" data-act-id="${escapeHtml(a.id)}">
                    <div>
                      <div class="activity-name">${escapeHtml(a.name)}</div>
                      <div class="activity-date">${a.date_key} · ${escapeHtml(a.sport_type)}</div>
                    </div>
                    <div><strong>${(a.distance_m / 1000).toFixed(2)} km</strong></div>
                    <div><strong>${formatPace(a.avg_pace_sec_km)}</strong> <span class="activity-date">/km</span></div>
                    <div class="hide-sm">${formatDuration(a.moving_time_s)}</div>
                    <div class="hide-sm">${a.avg_hr ? Math.round(a.avg_hr) + " bpm" : "--"}</div>
                    <div class="hide-sm">${categoryBadge(a.workout_category)}</div>
                  </div>`
                )
                .join("")}
            </div>`
          : `<div class="empty-state">Nessun allenamento ancora presente. Collega Strava nelle Impostazioni oppure carica i dati demo!</div>`
      }
    </section>
  `;

  // Mount charts
  renderLoadChart("chart-load", summary.load.series);
  renderWeeklyVolumeChart("chart-weekly", summary.load.weekly_volumes);
  if (summary.garmin_series && summary.garmin_series.length) {
    renderGarminStressChart("chart-garmin", summary.garmin_series);
  } else {
    const gEl = document.getElementById("chart-garmin")?.parentElement;
    if (gEl) gEl.innerHTML = `<div class="empty-state">Collega Garmin Connect in Connessioni per visualizzare Stress e Body Battery.</div>`;
  }

  // Event listeners
  document.getElementById("dash-go-settings")?.addEventListener("click", () => navigate("settings"));
  document.getElementById("dash-go-activities")?.addEventListener("click", () => navigate("activities"));
  document.getElementById("dash-go-plans")?.addEventListener("click", () => navigate("plans"));

  document.getElementById("dash-load-demo")?.addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    btn.textContent = "Generazione dati...";
    try {
      await api.seedDemo();
      showToast("Caricati 60 giorni di dati demo Strava + Garmin!", "success");
      renderDashboard(container, navigate, isStale);
    } catch (err) {
      showToast(err.message, "error");
      btn.disabled = false;
      btn.textContent = "✨ Prova con Dati Demo";
    }
  });

  document.getElementById("btn-refresh-ai")?.addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    btn.textContent = "Analisi Gemini...";
    try {
      const res = await api.getDailyCoach(true);
      const slot = document.getElementById("ai-narrative-slot");
      if (res.ai_narrative) {
        slot.innerHTML = `<div class="ai-box"><strong>✨ RunPulse AI Coach:</strong><br/>${simpleMarkdown(res.ai_narrative)}</div>`;
      } else {
        slot.innerHTML = `<div class="ai-box">Configura una chiave gratuita <strong>Google Gemini API</strong> nella scheda <em>Connessioni</em> per attivare la narrazione AI personalizzata!</div>`;
      }
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "✨ Consiglio AI Gemini";
    }
  });

  document.getElementById("ask-coach-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = document.getElementById("ask-coach-input");
    const replyEl = document.getElementById("ask-coach-reply");
    const btn = document.getElementById("ask-coach-btn");
    const q = input.value.trim();
    if (!q) return;
    btn.disabled = true;
    btn.textContent = "...";
    try {
      const res = await api.sendCalippoMessage(q);
      replyEl.innerHTML = `<div class="ai-box" style="margin-top:8px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;gap:8px;flex-wrap:wrap;">
          <strong>${res.ai_powered ? "✨ Calippo AI" : "📊 Calippo"}</strong>
          <button type="button" class="btn btn-ghost btn-sm" id="dash-open-calippo" style="min-height:28px;padding:3px 9px;font-size:0.75rem;">Apri chat completa →</button>
        </div>
        ${simpleMarkdown(res.reply.content)}
      </div>`;
      document.getElementById("dash-open-calippo")?.addEventListener("click", () => navigate("calippo"));
      input.value = "";
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "Chiedi";
    }
  });

  container.querySelectorAll(".activity-row[data-act-id]").forEach((row) => {
    row.addEventListener("click", () => openActivityModal(row.dataset.actId));
  });
}
