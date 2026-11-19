import {
  api,
  categoryBadge,
  escapeHtml,
  formatDuration,
  formatPace,
  showToast,
  simpleMarkdown,
} from "../api.js";
import { renderAthleteProgressionChart, renderRunSplitsChart } from "../charts.js";

const MONTH_SHORT = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"];

const CATEGORIES = [
  { id: "all", label: "Tutte" },
  { id: "easy", label: "Facili Z2" },
  { id: "recovery", label: "Rigeneranti" },
  { id: "tempo", label: "Tempo / Soglia" },
  { id: "intervals", label: "Ripetute VO2" },
  { id: "long", label: "Lunghi" },
  { id: "race", label: "Gare" },
  { id: "strength", label: "Forza / Pesi" },
  { id: "cross_training", label: "Cross-Training" },
];

function buildAthleteProgression(allActivities, rangeKey) {
  const runs = allActivities
    .filter((a) => String(a.sport_type || "").toLowerCase().includes("run") && (a.distance_m || 0) > 200)
    .sort((a, b) => String(a.date_key).localeCompare(String(b.date_key)));

  const now = new Date();
  let cutoffIso = null;
  let granularity = "month";
  if (rangeKey === "90d") {
    cutoffIso = new Date(now.getTime() - 90 * 86400000).toISOString().slice(0, 10);
    granularity = "week";
  } else if (rangeKey === "6m") {
    cutoffIso = new Date(now.getTime() - 183 * 86400000).toISOString().slice(0, 10);
    granularity = "month";
  } else if (rangeKey === "1y") {
    cutoffIso = new Date(now.getTime() - 365 * 86400000).toISOString().slice(0, 10);
    granularity = "month";
  }

  const scoped = cutoffIso ? runs.filter((r) => r.date_key >= cutoffIso) : runs;
  const map = new Map();

  for (const r of scoped) {
    let key;
    let label;
    if (granularity === "week") {
      const [y, m, d] = r.date_key.split("-").map(Number);
      const dt = new Date(y, m - 1, d);
      const dayShift = (dt.getDay() + 6) % 7;
      dt.setDate(dt.getDate() - dayShift);
      key = `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}-${String(dt.getDate()).padStart(2, "0")}`;
      label = `${String(dt.getDate()).padStart(2, "0")}/${String(dt.getMonth() + 1).padStart(2, "0")}`;
    } else {
      key = r.date_key.slice(0, 7);
      const [yy, mm] = key.split("-").map(Number);
      label = `${MONTH_SHORT[(mm || 1) - 1]} ${String(yy).slice(2)}`;
    }

    if (!map.has(key)) {
      map.set(key, {
        key,
        label,
        km: 0,
        sec: 0,
        trimp: 0,
        runs: 0,
        efWeightedSum: 0,
        efWeight: 0,
        easyKm: 0,
        longKm: 0,
        tempoKm: 0,
        hardKm: 0,
      });
    }
    const b = map.get(key);
    const km = (r.distance_m || 0) / 1000;
    const sec = r.moving_time_s || 0;
    b.km += km;
    b.sec += sec;
    b.trimp += Number(r.trimp || 0);
    b.runs += 1;
    if (r.efficiency_factor && sec > 0) {
      b.efWeightedSum += Number(r.efficiency_factor) * sec;
      b.efWeight += sec;
    }
    const cat = r.workout_category || "easy";
    if (cat === "recovery" || cat === "easy") b.easyKm += km;
    else if (cat === "long") b.longKm += km;
    else if (cat === "tempo") b.tempoKm += km;
    else b.hardKm += km;
  }

  const buckets = Array.from(map.values())
    .sort((a, b) => a.key.localeCompare(b.key))
    .map((b) => ({
      label: b.label,
      km: +b.km.toFixed(1),
      trimp: Math.round(b.trimp),
      runs: b.runs,
      avgPaceSec: b.km > 0.2 ? Math.round(b.sec / b.km) : null,
      ef: b.efWeight > 0 ? +(b.efWeightedSum / b.efWeight).toFixed(2) : null,
      easyKm: +b.easyKm.toFixed(1),
      longKm: +b.longKm.toFixed(1),
      tempoKm: +b.tempoKm.toFixed(1),
      hardKm: +b.hardKm.toFixed(1),
    }));

  const mid = Math.max(1, Math.floor(scoped.length / 2));
  const firstRuns = scoped.slice(0, mid);
  const secondRuns = scoped.slice(mid);

  const avgEfOf = (arr) => {
    let s = 0;
    let w = 0;
    for (const r of arr) {
      if (r.efficiency_factor && r.moving_time_s > 0) {
        s += r.efficiency_factor * r.moving_time_s;
        w += r.moving_time_s;
      }
    }
    return w > 0 ? s / w : null;
  };
  const avgPaceOf = (arr) => {
    const km = arr.reduce((a, r) => a + (r.distance_m || 0) / 1000, 0);
    const sec = arr.reduce((a, r) => a + (r.moving_time_s || 0), 0);
    return km > 0.5 ? sec / km : null;
  };

  const ef1 = avgEfOf(firstRuns);
  const ef2 = avgEfOf(secondRuns);
  const efDeltaPct = ef1 && ef2 ? +(((ef2 - ef1) / ef1) * 100).toFixed(1) : null;

  const p1 = avgPaceOf(firstRuns);
  const p2 = avgPaceOf(secondRuns);
  const paceDeltaSec = p1 && p2 ? Math.round(p2 - p1) : null;

  const totalKm = scoped.reduce((a, r) => a + (r.distance_m || 0) / 1000, 0);
  const easyTotalKm = scoped
    .filter((r) => ["recovery", "easy", "long"].includes(r.workout_category || "easy"))
    .reduce((a, r) => a + (r.distance_m || 0) / 1000, 0);
  const aerobicPct = totalKm > 0 ? Math.round((easyTotalKm / totalKm) * 100) : null;

  let weeksSpan = 1;
  if (scoped.length >= 2) {
    const d1 = new Date(scoped[0].date_key);
    const d2 = new Date(scoped[scoped.length - 1].date_key);
    weeksSpan = Math.max(1, (d2 - d1) / (7 * 86400000));
  }

  return {
    buckets,
    runCount: scoped.length,
    totalKm: +totalKm.toFixed(1),
    kmPerWeek: +(totalKm / weeksSpan).toFixed(1),
    runsPerWeek: +(scoped.length / weeksSpan).toFixed(1),
    efCurrent: ef2 ? +ef2.toFixed(2) : (ef1 ? +ef1.toFixed(2) : null),
    efDeltaPct,
    paceCurrent: p2 || p1,
    paceDeltaSec,
    aerobicPct,
  };
}

export async function renderActivities(container, isStale = () => false) {
  container.innerHTML = `<div class="loading-state">Caricamento archivio completo allenamenti...</div>`;
  let allActivities = [];
  try {
    const res = await api.getActivities({ limit: 5000 });
    allActivities = res.activities || [];
  } catch (err) {
    if (isStale()) return;
    container.innerHTML = `<div class="card empty-state">Errore: ${escapeHtml(err.message)}</div>`;
    return;
  }
  if (isStale()) return;

  let activeCat = "all";
  let activeYear = "all";
  let searchQuery = "";
  let pageSize = 60;
  let progRange = "90d";
  let progMode = "efficiency";

  const years = Array.from(
    new Set(allActivities.map((a) => String(a.date_key || "").slice(0, 4)).filter((y) => y.length === 4))
  ).sort((a, b) => b.localeCompare(a));

  const runActs = allActivities.filter((a) => String(a.sport_type || "").toLowerCase().includes("run"));
  const totalRunKm = runActs.reduce((s, a) => s + (a.distance_m || 0) / 1000, 0);
  const totalCount = allActivities.length;
  const firstRunDate = allActivities.length ? allActivities[allActivities.length - 1].date_key : "--";
  const avgTrimp = totalCount ? allActivities.reduce((s, a) => s + (a.trimp || 0), 0) / totalCount : 0;
  const runsWithEf = runActs.filter((a) => a.efficiency_factor);
  const avgEf = runsWithEf.length
    ? runsWithEf.reduce((s, a) => s + a.efficiency_factor, 0) / runsWithEf.length
    : null;

  container.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;">
      <div class="subtitle">
        Archivio caricato dal <strong>${firstRunDate}</strong> · <strong>${totalCount}</strong> attività totali (<strong>${runActs.length}</strong> corse)
      </div>
      <button class="btn btn-primary btn-sm" id="btn-import-all-strava">
        📥 Importa Storico Completo Strava (dalla 1ª corsa)
      </button>
    </div>

    <section class="grid-4">
      <div class="kpi-card">
        <div class="kpi-label">Allenamenti Tracciati</div>
        <div class="kpi-value">${totalCount}</div>
        <div class="kpi-sub">${runActs.length} corse · ${totalCount - runActs.length} altri sport</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Km di Corsa Totali</div>
        <div class="kpi-value">${totalRunKm.toFixed(1)} km</div>
        <div class="kpi-sub">Dal ${firstRunDate} ad oggi</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Carico Medio (TRIMP)</div>
        <div class="kpi-value">${avgTrimp.toFixed(0)}</div>
        <div class="kpi-sub">Per singolo allenamento</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Efficiency Factor Corsa</div>
        <div class="kpi-value" style="color:#10b981;">${avgEf ? avgEf.toFixed(2) : "--"}</div>
        <div class="kpi-sub">Velocità (m/min) ÷ FC media</div>
      </div>
    </section>

    <!-- Athlete Progression Dashboard -->
    <section class="card" style="border-color:rgba(16,185,129,0.3);">
      <div class="card-header">
        <div>
          <div class="card-title">📈 Dashboard Andamento Atleta</div>
          <p class="subtitle">Come stai evolvendo nel tempo tra efficienza aerobica, passo medio, volumi e polarizzazione</p>
        </div>
        <div class="filter-bar" id="prog-range-bar">
          <button class="filter-pill active" data-range="90d">3 Mesi</button>
          <button class="filter-pill" data-range="6m">6 Mesi</button>
          <button class="filter-pill" data-range="1y">1 Anno</button>
          <button class="filter-pill" data-range="all">Carriera</button>
        </div>
      </div>

      <div id="prog-kpi-strip" class="grid-4" style="margin-bottom:16px;"></div>

      <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:10px;">
        <div class="filter-bar" id="prog-mode-bar">
          <button class="filter-pill active" data-mode="efficiency">⚡ Efficienza & Passo</button>
          <button class="filter-pill" data-mode="volume">📊 Volume & TRIMP</button>
          <button class="filter-pill" data-mode="intensity">🎯 Mix Intensità</button>
        </div>
        <span class="subtitle" id="prog-chart-caption"></span>
      </div>

      <div class="chart-box" style="height:290px;"><canvas id="chart-athlete-progression"></canvas></div>
    </section>

    <section class="card">
      <div class="card-header">
        <div class="filter-bar" id="cat-filters">
          ${CATEGORIES.map(
            (c) => `<button class="filter-pill ${c.id === activeCat ? "active" : ""}" data-cat="${c.id}">${c.label}</button>`
          ).join("")}
        </div>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
          <select class="select" id="act-year-filter" style="width:auto;min-width:130px;">
            <option value="all">Tutti gli anni (${totalCount})</option>
            ${years.map((y) => `<option value="${y}">${y}</option>`).join("")}
          </select>
          <input class="input" id="act-search" placeholder="Cerca corsa..." style="max-width:210px;" />
        </div>
      </div>

      <div id="activities-count-note" class="subtitle" style="margin-bottom:10px;"></div>
      <div id="activities-list-slot" class="activity-list"></div>
      <div id="activities-more-slot" style="margin-top:14px;text-align:center;"></div>
    </section>
  `;

  function drawProgression() {
    const prog = buildAthleteProgression(allActivities, progRange);
    const kpiSlot = document.getElementById("prog-kpi-strip");
    const caption = document.getElementById("prog-chart-caption");

    if (!prog.buckets.length) {
      if (kpiSlot) kpiSlot.innerHTML = "";
      if (caption) caption.textContent = "Nessuna corsa nel periodo selezionato.";
      return;
    }

    const efBadge =
      prog.efDeltaPct != null
        ? `<span style="color:${prog.efDeltaPct >= 0 ? "#10b981" : "#f59e0b"};font-weight:700;">${prog.efDeltaPct >= 0 ? "▲ +" : "▼ "}${prog.efDeltaPct}%</span> vs inizio periodo`
        : "Serve FC su più corse";

    const paceBadge =
      prog.paceDeltaSec != null
        ? `<span style="color:${prog.paceDeltaSec <= 0 ? "#10b981" : "#f59e0b"};font-weight:700;">${prog.paceDeltaSec <= 0 ? "▲ " : "▼ +"}${prog.paceDeltaSec}s/km</span> vs inizio periodo`
        : "Media periodo";

    const aeroLabel =
      prog.aerobicPct == null
        ? "N/D"
        : prog.aerobicPct >= 75
          ? "Ottima base aerobica (80/20)"
          : prog.aerobicPct >= 60
            ? "Equilibrio moderato"
            : "Molta intensità: cura i lenti Z2";

    if (kpiSlot) {
      kpiSlot.innerHTML = `
        <div class="kpi-card" style="background:rgba(255,255,255,0.03);">
          <div class="kpi-label">Trend Efficienza (EF)</div>
          <div class="kpi-value" style="color:#10b981;">${prog.efCurrent ?? "--"}</div>
          <div class="kpi-sub">${efBadge}</div>
        </div>
        <div class="kpi-card" style="background:rgba(255,255,255,0.03);">
          <div class="kpi-label">Passo Medio Periodo</div>
          <div class="kpi-value" style="color:#38bdf8;">${formatPace(prog.paceCurrent)}</div>
          <div class="kpi-sub">${paceBadge}</div>
        </div>
        <div class="kpi-card" style="background:rgba(255,255,255,0.03);">
          <div class="kpi-label">Consistenza Settimanale</div>
          <div class="kpi-value">${prog.kmPerWeek} <span style="font-size:0.85rem;color:#93a1be;">km/sett</span></div>
          <div class="kpi-sub">${prog.runsPerWeek} corse/sett · ${prog.totalKm} km (${prog.runCount} corse)</div>
        </div>
        <div class="kpi-card" style="background:rgba(255,255,255,0.03);">
          <div class="kpi-label">Polarizzazione Aerobica</div>
          <div class="kpi-value" style="color:#a78bfa;">${prog.aerobicPct != null ? prog.aerobicPct + "%" : "--"}</div>
          <div class="kpi-sub">${aeroLabel}</div>
        </div>
      `;
    }

    if (caption) {
      caption.textContent =
        progMode === "efficiency"
          ? "EF più alto = corri più veloce a parità di battiti"
          : progMode === "volume"
            ? "Confronto tra km corsi e carico interno TRIMP"
            : "Distribuzione km tra base aerobica, lunghi, soglia e lavori veloci";
    }

    renderAthleteProgressionChart("chart-athlete-progression", prog.buckets, progMode);
  }

  function drawList() {
    const slot = document.getElementById("activities-list-slot");
    const moreSlot = document.getElementById("activities-more-slot");
    const countNote = document.getElementById("activities-count-note");
    const filtered = allActivities.filter((a) => {
      if (activeCat !== "all" && a.workout_category !== activeCat) return false;
      if (activeYear !== "all" && !String(a.date_key || "").startsWith(activeYear)) return false;
      if (searchQuery && !`${a.name} ${a.date_key} ${a.sport_type}`.toLowerCase().includes(searchQuery)) return false;
      return true;
    });

    if (!filtered.length) {
      if (countNote) countNote.textContent = "";
      if (moreSlot) moreSlot.innerHTML = "";
      slot.innerHTML = `<div class="empty-state">Nessuna corsa trovata con questi filtri. Clicca "Importa Storico Completo Strava" in alto per scaricare tutte le tue attività!</div>`;
      return;
    }

    const visible = filtered.slice(0, pageSize);
    if (countNote) {
      const fKm = filtered
        .filter((a) => String(a.sport_type || "").toLowerCase().includes("run"))
        .reduce((s, a) => s + (a.distance_m || 0) / 1000, 0);
      countNote.textContent = `Visualizzate ${visible.length} di ${filtered.length} attività (${fKm.toFixed(1)} km di corsa nel filtro)`;
    }

    slot.innerHTML = visible
      .map(
        (a) => `
        <div class="activity-row" data-act-id="${escapeHtml(a.id)}">
          <div>
            <div class="activity-name">${escapeHtml(a.name)}</div>
            <div class="activity-date">
              ${a.date_key} · ${escapeHtml(a.sport_type)} · D+ ${Math.round(a.elevation_gain_m || 0)}m
              ${a.cardiac_drift_pct != null ? `· Deriva ${a.cardiac_drift_pct > 0 ? "+" : ""}${a.cardiac_drift_pct}%` : ""}
            </div>
          </div>
          <div><strong>${(a.distance_m / 1000).toFixed(2)} km</strong></div>
          <div><strong>${formatPace(a.avg_pace_sec_km)}</strong> <span class="activity-date">/km</span></div>
          <div class="hide-sm">${formatDuration(a.moving_time_s)}</div>
          <div class="hide-sm">
            <div>${a.avg_hr ? Math.round(a.avg_hr) + " bpm" : "--"}</div>
            <div class="activity-date">TRIMP ${Math.round(a.trimp || 0)}</div>
          </div>
          <div class="hide-sm">${categoryBadge(a.workout_category)}</div>
        </div>`
      )
      .join("");

    slot.querySelectorAll(".activity-row[data-act-id]").forEach((row) => {
      row.addEventListener("click", () => openActivityModal(row.dataset.actId));
    });

    if (moreSlot) {
      if (visible.length < filtered.length) {
        const rem = filtered.length - visible.length;
        moreSlot.innerHTML = `
          <div style="display:flex;gap:10px;justify-content:center;flex-wrap:wrap;">
            <button class="btn btn-ghost btn-sm" id="btn-load-more-acts">Mostra altre 60 (${rem} rimanenti)</button>
            <button class="btn btn-ghost btn-sm" id="btn-load-all-acts">Mostra tutte (${filtered.length})</button>
          </div>`;
        document.getElementById("btn-load-more-acts")?.addEventListener("click", () => {
          pageSize += 60;
          drawList();
        });
        document.getElementById("btn-load-all-acts")?.addEventListener("click", () => {
          pageSize = filtered.length;
          drawList();
        });
      } else {
        moreSlot.innerHTML = "";
      }
    }
  }

  drawProgression();
  drawList();

  container.querySelectorAll("#prog-range-bar .filter-pill").forEach((btn) => {
    btn.addEventListener("click", () => {
      container.querySelectorAll("#prog-range-bar .filter-pill").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      progRange = btn.dataset.range;
      drawProgression();
    });
  });

  container.querySelectorAll("#prog-mode-bar .filter-pill").forEach((btn) => {
    btn.addEventListener("click", () => {
      container.querySelectorAll("#prog-mode-bar .filter-pill").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      progMode = btn.dataset.mode;
      drawProgression();
    });
  });

  container.querySelectorAll("#cat-filters .filter-pill").forEach((btn) => {
    btn.addEventListener("click", () => {
      container.querySelectorAll("#cat-filters .filter-pill").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      activeCat = btn.dataset.cat;
      pageSize = 60;
      drawList();
    });
  });

  document.getElementById("act-year-filter")?.addEventListener("change", (e) => {
    activeYear = e.target.value;
    pageSize = 60;
    drawList();
  });

  document.getElementById("act-search")?.addEventListener("input", (e) => {
    searchQuery = e.target.value.trim().toLowerCase();
    pageSize = 60;
    drawList();
  });

  document.getElementById("btn-import-all-strava")?.addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    btn.textContent = "Importazione storico completo Strava...";
    try {
      const res = await api.syncStrava(0, true);
      showToast(`Storico completo Strava importato: ${res.synced_activities} attività totali!`, "success");
      renderActivities(container, isStale);
    } catch (err) {
      showToast(err.message, "error");
      btn.disabled = false;
      btn.textContent = "📥 Importa Storico Completo Strava (dalla 1ª corsa)";
    }
  });
}

let modalSeq = 0;

export async function openActivityModal(activityId) {
  const myModalSeq = ++modalSeq;
  const backdrop = document.getElementById("modal-backdrop");
  const titleEl = document.getElementById("modal-title");
  const subEl = document.getElementById("modal-subtitle");
  const bodyEl = document.getElementById("modal-body");

  backdrop.classList.remove("hidden");
  document.body.classList.add("modal-open");
  titleEl.textContent = "Caricamento analisi corsa...";
  subEl.textContent = "";
  bodyEl.innerHTML = `<div class="loading-state">Recupero parziali km e metriche avanzate...</div>`;

  let act;
  try {
    const res = await api.getActivity(activityId);
    act = res.activity;
  } catch (err) {
    if (myModalSeq !== modalSeq || backdrop.classList.contains("hidden")) return;
    bodyEl.innerHTML = `<div class="empty-state">Errore: ${escapeHtml(err.message)}</div>`;
    return;
  }
  if (myModalSeq !== modalSeq || backdrop.classList.contains("hidden")) return;

  const isRun = String(act.sport_type || "").toLowerCase().includes("run");
  const isRide = String(act.sport_type || "").toLowerCase().includes("ride");
  const cadUnit = isRide ? "rpm" : "spm";
  const speedKmh = act.avg_speed_ms ? (act.avg_speed_ms * 3.6).toFixed(1) : "--";

  titleEl.textContent = act.name;
  subEl.textContent = `${act.date_key} · ${act.sport_type} · ${categoryBadge(act.workout_category).replace(/<[^>]+>/g, "")}`;

  const zones = act.hr_zones || {};
  const hasZones = Object.keys(zones).length > 0;
  const zoneColors = { Z1: "#64748b", Z2: "#10b981", Z3: "#f59e0b", Z4: "#f97316", Z5: "#ef4444" };
  const splits = act.splits || [];

  bodyEl.innerHTML = `
    <div class="grid-auto">
      <div class="kpi-card">
        <div class="kpi-label">Distanza</div>
        <div class="kpi-value">${(act.distance_m / 1000).toFixed(2)} km</div>
        <div class="kpi-sub">Durata ${formatDuration(act.moving_time_s)}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">${isRide ? "Velocità Media" : "Passo Medio"}</div>
        <div class="kpi-value" style="color:#00b4d8;">${isRide ? speedKmh + " km/h" : formatPace(act.avg_pace_sec_km)}</div>
        <div class="kpi-sub">D+ ${Math.round(act.elevation_gain_m || 0)} m</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Frequenza Cardiaca</div>
        <div class="kpi-value" style="color:#f87171;">${act.avg_hr ? Math.round(act.avg_hr) : "--"} <span style="font-size:0.9rem;">bpm</span></div>
        <div class="kpi-sub">Max ${act.max_hr ? Math.round(act.max_hr) + " bpm" : "--"} · Cadenza ${act.avg_cadence ? Math.round(act.avg_cadence) + " " + cadUnit : "--"}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">${isRun ? "Efficienza & Deriva" : "Carico (TRIMP)"}</div>
        <div class="kpi-value">${isRun ? (act.efficiency_factor || "--") + ' <span style="font-size:0.85rem;color:#93a1be;">EF</span>' : Math.round(act.trimp || 0)}</div>
        <div class="kpi-sub">${isRun ? `Deriva: <strong>${act.cardiac_drift_pct != null ? (act.cardiac_drift_pct > 0 ? "+" : "") + act.cardiac_drift_pct + "%" : "N/D"}</strong> · TRIMP ${Math.round(act.trimp || 0)}` : `Calorie: ${act.calories ? Math.round(act.calories) + " kcal" : "--"}`}</div>
      </div>
    </div>

    <!-- AI Analysis Box -->
    <div style="display:flex;flex-direction:column;gap:10px;">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;">
        <strong>🧠 Analisi Tecnica & Coach AI</strong>
        <button class="btn btn-ai btn-sm" id="btn-analyze-run">✨ Genera / Aggiorna Analisi Corsa</button>
      </div>
      <div id="run-ai-box" class="ai-box" style="${act.ai_analysis ? "" : "display:none;"}">
        ${simpleMarkdown(act.ai_analysis)}
      </div>
    </div>

    ${
      hasZones
        ? `<div>
            <strong style="font-size:0.9rem;">Distribuzione Zone Cardio (stimate dai parziali)</strong>
            <div class="stacked-bar">
              ${Object.entries(zones)
                .map(([z, pct]) => (pct > 0 ? `<div style="width:${pct}%;background:${zoneColors[z] || "#64748b"}" title="${z}: ${pct}%"></div>` : ""))
                .join("")}
            </div>
            <div style="display:flex;gap:12px;flex-wrap:wrap;font-size:0.78rem;color:#93a1be;">
              ${Object.entries(zones)
                .map(([z, pct]) => `<span><span style="color:${zoneColors[z]}">●</span> ${z}: <strong>${pct}%</strong></span>`)
                .join("")}
            </div>
          </div>`
        : ""
    }

    ${
      splits.length
        ? `<div>
            <strong style="font-size:0.9rem;">📊 Passo vs Frequenza Cardiaca per Km</strong>
            <div class="chart-box-sm" style="margin-top:10px;"><canvas id="chart-run-splits"></canvas></div>
          </div>
          <div>
            <strong style="font-size:0.9rem;">Tabella Parziali Km</strong>
            <div style="overflow-x:auto;margin-top:8px;">
              <table class="data-table">
                <thead>
                  <tr><th>Km</th><th>Distanza</th><th>Passo</th><th>FC Media</th><th>Dislivello</th></tr>
                </thead>
                <tbody>
                  ${splits
                    .map((s, idx) => {
                      const dKm = (s.distance || 0) / 1000;
                      const pSec = dKm > 0 ? s.moving_time / dKm : 0;
                      return `<tr>
                        <td><strong>${idx + 1}</strong></td>
                        <td>${dKm.toFixed(2)} km</td>
                        <td><strong>${formatPace(pSec)} /km</strong></td>
                        <td>${s.average_heartrate ? Math.round(s.average_heartrate) + " bpm" : "--"}</td>
                        <td>${s.elevation_difference != null ? (s.elevation_difference >= 0 ? "+" : "") + s.elevation_difference + " m" : "--"}</td>
                      </tr>`;
                    })
                    .join("")}
                </tbody>
              </table>
            </div>
          </div>`
        : `<div class="empty-state" style="padding:18px;">Nessun parziale km disponibile per questa attività.</div>`
    }
  `;

  if (splits.length) {
    renderRunSplitsChart("chart-run-splits", splits);
  }

  document.getElementById("btn-analyze-run")?.addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    btn.textContent = "Analisi in corso...";
    try {
      const res = await api.analyzeActivity(act.id);
      const box = document.getElementById("run-ai-box");
      box.style.display = "block";
      box.innerHTML = simpleMarkdown(res.analysis);
      showToast(res.ai_powered ? "Analisi Gemini AI completata!" : "Analisi fisiologica completata!", "success");
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "✨ Genera / Aggiorna Analisi Corsa";
    }
  });
}
