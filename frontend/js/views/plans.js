import {
  api,
  categoryBadge,
  escapeHtml,
  formatRaceTime,
  localDateIso,
  showToast,
  simpleMarkdown,
} from "../api.js";
import { renderPlanVolumeChart } from "../charts.js";

const DAY_NAMES = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"];
const DIST_LABELS = {
  "5k": "5 km",
  "10k": "10 km",
  half_marathon: "Mezza Maratona (21.1 km)",
  marathon: "Maratona (42.2 km)",
};

function daysUntilLocal(isoDateStr) {
  const [y, m, d] = isoDateStr.split("-").map(Number);
  const target = new Date(y, m - 1, d);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.max(0, Math.round((target - today) / 86400000));
}

function parseTimeToSeconds(str) {
  if (!str || !str.trim()) return null;
  const parts = str.trim().split(":").map((x) => Number(x));
  if (parts.some((n) => Number.isNaN(n) || n < 0)) return null;
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
  if (parts.length === 2) return parts[0] * 60 + parts[1];
  return null;
}

export async function renderPlans(container, isStale = () => false) {
  container.innerHTML = `<div class="loading-state">Caricamento obiettivi gara e piani...</div>`;
  let data;
  try {
    data = await api.getPlans();
  } catch (err) {
    if (isStale()) return;
    container.innerHTML = `<div class="card empty-state">Errore: ${escapeHtml(err.message)}</div>`;
    return;
  }
  if (isStale()) return;

  const goals = data.goals || [];
  const active = data.active_goal;
  const defaultDate = localDateIso(new Date(Date.now() + 84 * 86400000));

  let activePlanHtml = "";
  if (active) {
    const todayIso = localDateIso();
    const daysLeft = daysUntilLocal(active.race_date);
    const workouts = active.workouts || [];
    const runWorkouts = workouts.filter((w) => w.workout_type !== "rest");
    const doneCount = runWorkouts.filter((w) => w.completed).length;
    const pctDone = runWorkouts.length ? Math.round((doneCount / runWorkouts.length) * 100) : 0;

    // Group workouts by week
    const weeksMap = new Map();
    for (const w of workouts) {
      if (!weeksMap.has(w.week_number)) weeksMap.set(w.week_number, []);
      weeksMap.get(w.week_number).push(w);
    }
    const weeks = Array.from(weeksMap.entries()).sort((a, b) => a[0] - b[0]);

    // Find current week to auto-expand
    const currentWeekEntry = weeks.find(([, ws]) => ws.some((w) => w.scheduled_date >= todayIso)) || weeks[0];
    const currentWeekNum = currentWeekEntry ? currentWeekEntry[0] : 1;

    const paces = active.paces || {};

    activePlanHtml = `
      <section class="card" style="border-color:rgba(252,76,2,0.35);">
        <div class="card-header">
          <div>
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:6px;">
              <span class="pill pill-orange">🎯 PIANO ATTIVO</span>
              <span class="pill pill-cyan">${DIST_LABELS[active.distance_type] || active.distance_type}</span>
              <span class="pill pill-muted">-${daysLeft} giorni alla gara</span>
            </div>
            <h2 style="font-size:1.35rem;font-weight:800;">${escapeHtml(active.name)}</h2>
            <p class="subtitle">
              Data: <strong>${active.race_date}</strong> · Obiettivo: <strong>${formatRaceTime(active.target_time_sec)}</strong>
              (${escapeHtml(paces.race_pace || "--")}) · VDOT ${active.current_vdot ?? "--"} → ${active.target_vdot ?? "--"}
            </p>
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;">
            <button class="btn btn-garmin btn-sm" id="btn-adapt-plan" data-goal-id="${active.id}">
              🫀 Adatta allo Stress Garmin
            </button>
            <button class="btn btn-danger btn-sm" id="btn-delete-plan" data-goal-id="${active.id}">
              Elimina
            </button>
          </div>
        </div>

        <div style="margin-bottom:14px;">
          <div style="display:flex;justify-content:space-between;font-size:0.83rem;margin-bottom:5px;">
            <span id="plan-progress-label">Avanzamento piano (${doneCount}/${runWorkouts.length} allenamenti)</span>
            <strong id="plan-progress-pct">${pctDone}%</strong>
          </div>
          <div class="progress-track"><div class="progress-fill" id="plan-progress-fill" style="width:${pctDone}%"></div></div>
        </div>

        ${
          active.ai_summary
            ? `<div class="ai-box" style="margin-bottom:16px;">${simpleMarkdown(active.ai_summary)}</div>`
            : ""
        }

        <!-- Training Pace Zones -->
        <div style="margin-bottom:18px;">
          <div style="font-size:0.82rem;font-weight:700;color:#93a1be;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:8px;">
            Ritmi di Allenamento Personalizzati (VDOT)
          </div>
          <div class="grid-auto">
            ${["recovery", "easy", "marathon", "threshold", "interval"]
              .filter((k) => paces[k])
              .map(
                (k) => `<div style="padding:10px 12px;border-radius:10px;background:rgba(255,255,255,0.035);border:1px solid rgba(255,255,255,0.07);">
                  <div style="font-size:0.74rem;color:#93a1be;">${escapeHtml(paces[k].label)}</div>
                  <div style="font-weight:700;font-size:0.95rem;margin-top:2px;">${escapeHtml(paces[k].range)}</div>
                </div>`
              )
              .join("")}
          </div>
        </div>

        <!-- Weekly Volume Progression Chart -->
        <div style="margin-bottom:20px;">
          <div style="font-size:0.85rem;font-weight:700;margin-bottom:8px;">📈 Progressione Chilometri Settimanali & Fasi</div>
          <div class="chart-box-sm"><canvas id="chart-plan-volume"></canvas></div>
        </div>

        <!-- Week-by-Week Calendar -->
        <div style="display:flex;flex-direction:column;gap:12px;" id="plan-weeks-list">
          ${weeks
            .map(([wNum, ws]) => {
              const phase = ws[0]?.phase || "";
              const wKm = ws.reduce((s, x) => s + Number(x.target_distance_km || 0), 0);
              const wDone = ws.filter((x) => x.workout_type !== "rest" && x.completed).length;
              const wTot = ws.filter((x) => x.workout_type !== "rest").length;
              const isOpen = wNum === currentWeekNum || wNum === currentWeekNum + 1;
              return `
                <div class="week-block">
                  <div class="week-header" data-toggle-week="${wNum}">
                    <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
                      <strong>Settimana ${wNum}</strong>
                      <span class="pill pill-cyan">${escapeHtml(phase)}</span>
                      <span class="subtitle">${ws[0]?.scheduled_date} → ${ws[ws.length - 1]?.scheduled_date}</span>
                    </div>
                    <div style="display:flex;align-items:center;gap:12px;font-size:0.84rem;">
                      <span><strong>${wKm.toFixed(1)} km</strong></span>
                      <span class="pill ${wDone === wTot && wTot > 0 ? "pill-green" : "pill-muted"}" id="week-badge-${wNum}">${wDone}/${wTot} fatti</span>
                    </div>
                  </div>
                  <div class="week-workouts" id="week-body-${wNum}" style="${isOpen ? "" : "display:none;"}">
                    ${ws
                      .map((w) => {
                        const isToday = w.scheduled_date === todayIso;
                        const isRest = w.workout_type === "rest";
                        return `
                          <div class="workout-tile ${w.completed ? "completed" : ""} ${isToday ? "is-today" : ""} ${isRest ? "is-rest" : ""}">
                            <div class="workout-day">
                              <span>${DAY_NAMES[w.day_of_week] || ""} · ${w.scheduled_date.slice(5)} ${isToday ? "· OGGI" : ""}</span>
                              ${categoryBadge(w.workout_type)}
                            </div>
                            <div style="font-weight:700;font-size:0.9rem;">${escapeHtml(w.title)}</div>
                            <div style="font-size:0.8rem;color:#cbd5e1;flex:1;">${escapeHtml(w.description)}</div>
                            ${
                              !isRest
                                ? `<div style="font-size:0.77rem;color:#93a1be;">
                                    ${w.target_distance_km} km · Passo: <strong>${escapeHtml(w.target_pace_range)}</strong> · ${escapeHtml(w.target_hr_zone)}
                                   </div>`
                                : ""
                            }
                            ${
                              w.adapted_reason
                                ? `<div style="font-size:0.74rem;color:#38bdf8;background:rgba(0,180,216,0.12);padding:4px 8px;border-radius:7px;">
                                    🫀 ${escapeHtml(w.adapted_reason)}
                                   </div>`
                                : ""
                            }
                            ${
                              !isRest
                                ? `<label style="display:flex;align-items:center;gap:7px;font-size:0.8rem;margin-top:4px;cursor:pointer;">
                                    <input type="checkbox" class="chk-workout" data-workout-id="${w.id}" ${w.completed ? "checked" : ""} />
                                    <span>${w.completed ? "Completato" + (w.linked_activity_id ? " (Strava)" : "") : "Segna completato"}</span>
                                   </label>`
                                : ""
                            }
                          </div>`;
                      })
                      .join("")}
                  </div>
                </div>`;
            })
            .join("")}
        </div>
      </section>
    `;
  }

  container.innerHTML = `
    <!-- Create New Race Goal Form -->
    <section class="card">
      <div class="card-header">
        <div>
          <div class="card-title">🏁 Crea Nuovo Obiettivo Gara & Piano di Allenamento</div>
          <p class="subtitle">Genera un piano periodizzato su misura dai tuoi dati Strava/VDOT, pronto per adattarsi allo stress Garmin.</p>
        </div>
      </div>

      <form id="create-plan-form" class="form-grid">
        <div class="form-field">
          <label for="goal-name">Nome della gara</label>
          <input class="input" id="goal-name" placeholder="es. Mezza Maratona di Milano" required />
        </div>

        <div class="form-field">
          <label for="goal-distance">Distanza</label>
          <select class="select" id="goal-distance">
            <option value="5k">5 km</option>
            <option value="10k">10 km</option>
            <option value="half_marathon" selected>Mezza Maratona (21.1 km)</option>
            <option value="marathon">Maratona (42.2 km)</option>
          </select>
        </div>

        <div class="form-field">
          <label for="goal-date">Data della gara</label>
          <input class="input" id="goal-date" type="date" value="${defaultDate}" required />
        </div>

        <div class="form-field">
          <label for="goal-target">Tempo obiettivo (opzionale, es. 1:40:00 o 45:00)</label>
          <input class="input" id="goal-target" placeholder="Lascia vuoto per calcolo automatico dal VDOT" />
        </div>

        <div class="form-field">
          <label for="goal-days">Giorni di allenamento a settimana</label>
          <select class="select" id="goal-days">
            <option value="3">3 giorni / settimana</option>
            <option value="4" selected>4 giorni / settimana (Consigliato)</option>
            <option value="5">5 giorni / settimana</option>
            <option value="6">6 giorni / settimana</option>
          </select>
        </div>

        <div class="form-field">
          <label for="goal-longday">Giorno del Lungo</label>
          <select class="select" id="goal-longday">
            <option value="5">Sabato</option>
            <option value="6" selected>Domenica</option>
            <option value="2">Mercoledì</option>
          </select>
        </div>

        <div class="form-field">
          <label for="goal-weekly-km">Km settimanali attuali (opzionale)</label>
          <input class="input" id="goal-weekly-km" type="number" min="10" max="150" placeholder="Auto-rilevato da Strava" />
        </div>

        <div class="form-field">
          <label for="goal-notes">Note personali (infortuni, preferenze)</label>
          <input class="input" id="goal-notes" placeholder="es. Preferisco ripetute il martedì" />
        </div>

        <div class="form-field full" style="flex-direction:row;justify-content:flex-end;">
          <button class="btn btn-primary" type="submit" id="btn-create-plan">🚀 Genera Piano Gara Personalizzato</button>
        </div>
      </form>
    </section>

    ${
      goals.length > 1
        ? `<section class="card">
            <div class="card-header"><div class="card-title">I Tuoi Obiettivi Salvati</div></div>
            <div style="display:flex;gap:10px;flex-wrap:wrap;">
              ${goals
                .map(
                  (g) => `<button class="btn btn-sm ${active && g.id === active.id ? "btn-primary" : "btn-ghost"}" data-activate-goal="${g.id}">
                    ${escapeHtml(g.name)} (${g.race_date})
                  </button>`
                )
                .join("")}
            </div>
          </section>`
        : ""
    }

    ${activePlanHtml}
  `;

  if (active && active.workouts?.length) {
    renderPlanVolumeChart("chart-plan-volume", active.workouts);
  }

  // Toggle week accordion
  container.querySelectorAll("[data-toggle-week]").forEach((hdr) => {
    hdr.addEventListener("click", () => {
      const body = document.getElementById(`week-body-${hdr.dataset.toggleWeek}`);
      if (body) body.style.display = body.style.display === "none" ? "grid" : "none";
    });
  });

  // Create plan submit
  document.getElementById("create-plan-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = document.getElementById("btn-create-plan");
    const targetRaw = document.getElementById("goal-target").value.trim();
    const targetSec = parseTimeToSeconds(targetRaw);
    if (targetRaw && !targetSec) {
      showToast("Formato tempo non valido. Usa MM:SS (es. 45:00) oppure HH:MM:SS (es. 1:42:00).", "error");
      return;
    }
    const weeklyKmRaw = document.getElementById("goal-weekly-km").value.trim();

    btn.disabled = true;
    btn.textContent = "Generazione piano in corso...";
    try {
      await api.createPlan({
        name: document.getElementById("goal-name").value.trim(),
        distance_type: document.getElementById("goal-distance").value,
        race_date: document.getElementById("goal-date").value,
        target_time_sec: targetSec,
        days_per_week: Number(document.getElementById("goal-days").value),
        long_run_day: Number(document.getElementById("goal-longday").value),
        current_weekly_km: weeklyKmRaw ? Number(weeklyKmRaw) : null,
        notes: document.getElementById("goal-notes").value.trim(),
        use_ai: true,
      });
      showToast("Piano gara generato e attivato!", "success");
      renderPlans(container);
    } catch (err) {
      showToast(err.message, "error");
      btn.disabled = false;
      btn.textContent = "🚀 Genera Piano Gara Personalizzato";
    }
  });

  // Adapt plan for Garmin stress
  document.getElementById("btn-adapt-plan")?.addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    const goalId = Number(btn.dataset.goalId);
    btn.disabled = true;
    btn.textContent = "Analisi stress Garmin...";
    try {
      const res = await api.adaptPlan(goalId);
      showToast(res.message, res.adapted_count > 0 ? "success" : "info");
      renderPlans(container);
    } catch (err) {
      showToast(err.message, "error");
      btn.disabled = false;
      btn.textContent = "🫀 Adatta allo Stress Garmin";
    }
  });

  // Delete plan
  document.getElementById("btn-delete-plan")?.addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    const goalId = Number(btn.dataset.goalId);
    if (!confirm("Vuoi eliminare questo piano gara?")) return;
    btn.disabled = true;
    try {
      await api.deletePlan(goalId);
      showToast("Piano gara eliminato.", "info");
      renderPlans(container, isStale);
    } catch (err) {
      showToast(err.message, "error");
      btn.disabled = false;
    }
  });

  // Switch active plan
  container.querySelectorAll("[data-activate-goal]").forEach((b) => {
    b.addEventListener("click", async () => {
      b.disabled = true;
      try {
        await api.activatePlan(Number(b.dataset.activateGoal));
        renderPlans(container, isStale);
      } catch (err) {
        showToast(err.message, "error");
        b.disabled = false;
      }
    });
  });

  // Checkboxes — live-update tile, label, week badge, and global progress bar
  container.querySelectorAll(".chk-workout").forEach((chk) => {
    chk.addEventListener("change", async () => {
      const id = Number(chk.dataset.workoutId);
      try {
        await api.toggleWorkout(id, chk.checked);
        const tile = chk.closest(".workout-tile");
        if (tile) tile.classList.toggle("completed", chk.checked);
        const lblSpan = chk.parentElement?.querySelector("span");
        if (lblSpan) lblSpan.textContent = chk.checked ? "Completato" : "Segna completato";

        // Recalculate week badge & global progress bar
        const weekBody = chk.closest(".week-workouts");
        if (weekBody) {
          const wNum = weekBody.id.replace("week-body-", "");
          const wChks = Array.from(weekBody.querySelectorAll(".chk-workout"));
          const wDoneNow = wChks.filter((c) => c.checked).length;
          const badge = document.getElementById(`week-badge-${wNum}`);
          if (badge) {
            badge.textContent = `${wDoneNow}/${wChks.length} fatti`;
            badge.className = `pill ${wDoneNow === wChks.length && wChks.length > 0 ? "pill-green" : "pill-muted"}`;
          }
        }
        const allChks = Array.from(container.querySelectorAll(".chk-workout"));
        const totDone = allChks.filter((c) => c.checked).length;
        const pct = allChks.length ? Math.round((totDone / allChks.length) * 100) : 0;
        const pLbl = document.getElementById("plan-progress-label");
        const pPct = document.getElementById("plan-progress-pct");
        const pFill = document.getElementById("plan-progress-fill");
        if (pLbl) pLbl.textContent = `Avanzamento piano (${totDone}/${allChks.length} allenamenti)`;
        if (pPct) pPct.textContent = `${pct}%`;
        if (pFill) pFill.style.width = `${pct}%`;
      } catch (err) {
        chk.checked = !chk.checked;
        showToast(err.message, "error");
      }
    });
  });
}
