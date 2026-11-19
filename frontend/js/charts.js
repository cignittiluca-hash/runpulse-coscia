// Chart.js wrapper helpers with consistent dark athletic styling
import { formatHoursMin, formatPace } from "./api.js";

const chartInstances = new Map();

const baseGrid = { color: "rgba(255,255,255,0.06)" };
const baseTicks = { color: "#93a1be", font: { size: 11 } };

function mountChart(canvasId, config) {
  const el = document.getElementById(canvasId);
  if (!el || typeof Chart === "undefined") return null;
  destroyChart(canvasId);
  const inst = new Chart(el, config);
  chartInstances.set(canvasId, inst);
  return inst;
}

export function destroyChart(canvasId) {
  if (chartInstances.has(canvasId)) {
    try { chartInstances.get(canvasId).destroy(); } catch {}
    chartInstances.delete(canvasId);
  }
}

export function destroyAllCharts() {
  for (const inst of chartInstances.values()) {
    try { inst.destroy(); } catch {}
  }
  chartInstances.clear();
}

export function renderLoadChart(canvasId, series) {
  const labels = series.map((d) => d.date.slice(5));
  return mountChart(canvasId, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Fitness (CTL)",
          data: series.map((d) => d.ctl),
          borderColor: "#00b4d8",
          backgroundColor: "rgba(0,180,216,0.12)",
          fill: true,
          tension: 0.35,
          pointRadius: 0,
          borderWidth: 2.2,
        },
        {
          label: "Fatica (ATL)",
          data: series.map((d) => d.atl),
          borderColor: "#fc4c02",
          tension: 0.35,
          pointRadius: 0,
          borderWidth: 2,
        },
        {
          label: "Forma (TSB)",
          data: series.map((d) => d.tsb),
          borderColor: "#10b981",
          borderDash: [4, 4],
          tension: 0.35,
          pointRadius: 0,
          borderWidth: 1.8,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { labels: { color: "#cbd5e1", boxWidth: 12 } } },
      scales: {
        x: { grid: { display: false }, ticks: { ...baseTicks, maxTicksLimit: 10 } },
        y: { grid: baseGrid, ticks: baseTicks },
      },
    },
  });
}

export function renderWeeklyVolumeChart(canvasId, weeklyVolumes) {
  return mountChart(canvasId, {
    type: "bar",
    data: {
      labels: weeklyVolumes.map((w) => w.week_label),
      datasets: [
        {
          label: "Km settimanali",
          data: weeklyVolumes.map((w) => w.km),
          backgroundColor: "rgba(252, 76, 2, 0.72)",
          borderColor: "#fc4c02",
          borderWidth: 1,
          borderRadius: 7,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: baseTicks },
        y: { grid: baseGrid, ticks: baseTicks, beginAtZero: true },
      },
    },
  });
}

export function renderGarminStressChart(canvasId, garminDays) {
  const labels = garminDays.map((d) => d.date_key.slice(5));
  return mountChart(canvasId, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Stress Medio",
          data: garminDays.map((d) => d.stress_avg),
          borderColor: "#f59e0b",
          backgroundColor: "rgba(245,158,11,0.12)",
          fill: true,
          spanGaps: true,
          tension: 0.3,
          pointRadius: 2,
          borderWidth: 2,
        },
        {
          label: "Body Battery Max",
          data: garminDays.map((d) => d.body_battery_max),
          borderColor: "#00b4d8",
          spanGaps: true,
          tension: 0.3,
          pointRadius: 2,
          borderWidth: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { labels: { color: "#cbd5e1", boxWidth: 12 } } },
      scales: {
        x: { grid: { display: false }, ticks: { ...baseTicks, maxTicksLimit: 10 } },
        y: { grid: baseGrid, ticks: baseTicks, min: 0, max: 100 },
      },
    },
  });
}

export function renderHrvSleepChart(canvasId, garminDays) {
  const labels = garminDays.map((d) => d.date_key.slice(5));
  return mountChart(canvasId, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "HRV (ms)",
          data: garminDays.map((d) => d.hrv_avg),
          borderColor: "#10b981",
          backgroundColor: "rgba(16,185,129,0.12)",
          fill: true,
          spanGaps: true,
          tension: 0.35,
          yAxisID: "y",
          borderWidth: 2.2,
        },
        {
          label: "Sonno",
          data: garminDays.map((d) => (d.sleep_seconds ? +(d.sleep_seconds / 3600).toFixed(2) : null)),
          borderColor: "#8b5cf6",
          spanGaps: true,
          tension: 0.35,
          yAxisID: "y1",
          borderWidth: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { labels: { color: "#cbd5e1", boxWidth: 12 } },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              if (ctx.dataset.label === "Sonno" && ctx.parsed.y != null) {
                return `Sonno: ${formatHoursMin(ctx.parsed.y * 3600)}`;
              }
              return `${ctx.dataset.label}: ${ctx.parsed.y ?? "--"}`;
            },
          },
        },
      },
      scales: {
        x: { grid: { display: false }, ticks: { ...baseTicks, maxTicksLimit: 10 } },
        y: { position: "left", grid: baseGrid, ticks: baseTicks },
        y1: { position: "right", grid: { display: false }, ticks: baseTicks, min: 3, max: 11 },
      },
    },
  });
}

export function renderRunSplitsChart(canvasId, splits) {
  const valid = splits.filter((s) => s.distance >= 300 && s.moving_time > 0);
  const labels = valid.map((_, i) => `Km ${i + 1}`);
  const pacesMin = valid.map((s) => +(s.moving_time / (s.distance / 1000) / 60).toFixed(2));
  const hrs = valid.map((s) => s.average_heartrate || null);

  return mountChart(canvasId, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          type: "bar",
          label: "Passo (min/km)",
          data: pacesMin,
          backgroundColor: "rgba(0, 180, 216, 0.55)",
          borderColor: "#00b4d8",
          borderRadius: 5,
          yAxisID: "y",
        },
        {
          type: "line",
          label: "FC Media (bpm)",
          data: hrs,
          borderColor: "#ef4444",
          backgroundColor: "#ef4444",
          tension: 0.3,
          borderWidth: 2.2,
          pointRadius: 3,
          yAxisID: "y1",
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { labels: { color: "#cbd5e1", boxWidth: 12 } },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              if (ctx.dataset.yAxisID === "y" && ctx.parsed.y != null) {
                return `Passo: ${formatPace(ctx.parsed.y * 60)} /km`;
              }
              if (ctx.dataset.yAxisID === "y1" && ctx.parsed.y != null) {
                return `FC Media: ${Math.round(ctx.parsed.y)} bpm`;
              }
              return `${ctx.dataset.label}: ${ctx.parsed.y ?? "--"}`;
            },
          },
        },
      },
      scales: {
        x: { grid: { display: false }, ticks: baseTicks },
        y: {
          position: "left",
          reverse: true,
          grid: baseGrid,
          ticks: { ...baseTicks, callback: (v) => formatPace(v * 60) },
        },
        y1: { position: "right", grid: { display: false }, ticks: baseTicks },
      },
    },
  });
}

export function renderPlanVolumeChart(canvasId, workouts) {
  const byWeek = new Map();
  for (const w of workouts) {
    const cur = byWeek.get(w.week_number) || { km: 0, phase: w.phase };
    cur.km += Number(w.target_distance_km || 0);
    byWeek.set(w.week_number, cur);
  }
  const weeks = Array.from(byWeek.entries()).sort((a, b) => a[0] - b[0]);
  const phaseColors = {
    "Costruzione Base": "rgba(0, 180, 216, 0.72)",
    "Sviluppo Specifico": "rgba(245, 158, 11, 0.78)",
    "Picco Gara": "rgba(252, 76, 2, 0.85)",
    "Scarico / Taper": "rgba(16, 185, 129, 0.78)",
    "Settimana Gara": "rgba(139, 92, 246, 0.85)",
  };

  return mountChart(canvasId, {
    type: "bar",
    data: {
      labels: weeks.map(([num]) => `Sett ${num}`),
      datasets: [
        {
          label: "Km Previsti",
          data: weeks.map(([, v]) => +v.km.toFixed(1)),
          backgroundColor: weeks.map(([, v]) => phaseColors[v.phase] || "rgba(252,76,2,0.7)"),
          borderRadius: 6,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: baseTicks },
        y: { grid: baseGrid, ticks: baseTicks, beginAtZero: true },
      },
    },
  });
}

export function renderAthleteProgressionChart(canvasId, buckets, mode = "efficiency") {
  const labels = buckets.map((b) => b.label);

  if (mode === "volume") {
    return mountChart(canvasId, {
      type: "bar",
      data: {
        labels,
        datasets: [
          {
            type: "bar",
            label: "Km Corsa",
            data: buckets.map((b) => b.km),
            backgroundColor: "rgba(252, 76, 2, 0.72)",
            borderColor: "#fc4c02",
            borderRadius: 6,
            yAxisID: "y",
          },
          {
            type: "line",
            label: "Carico (TRIMP)",
            data: buckets.map((b) => b.trimp),
            borderColor: "#00b4d8",
            backgroundColor: "rgba(0, 180, 216, 0.12)",
            fill: true,
            spanGaps: true,
            tension: 0.32,
            borderWidth: 2.3,
            pointRadius: 3,
            yAxisID: "y1",
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { labels: { color: "#cbd5e1", boxWidth: 12 } },
          tooltip: {
            callbacks: {
              afterBody: (items) => {
                const idx = items[0]?.dataIndex;
                const b = buckets[idx];
                return b ? `Corse nel periodo: ${b.runs}` : "";
              },
            },
          },
        },
        scales: {
          x: { grid: { display: false }, ticks: { ...baseTicks, maxTicksLimit: 12 } },
          y: { position: "left", grid: baseGrid, ticks: baseTicks, beginAtZero: true },
          y1: { position: "right", grid: { display: false }, ticks: baseTicks, beginAtZero: true },
        },
      },
    });
  }

  if (mode === "intensity") {
    return mountChart(canvasId, {
      type: "bar",
      data: {
        labels,
        datasets: [
          {
            label: "Facili / Rigeneranti (km)",
            data: buckets.map((b) => b.easyKm),
            backgroundColor: "rgba(16, 185, 129, 0.78)",
            borderRadius: 4,
          },
          {
            label: "Lunghi (km)",
            data: buckets.map((b) => b.longKm),
            backgroundColor: "rgba(139, 92, 246, 0.78)",
            borderRadius: 4,
          },
          {
            label: "Tempo / Soglia (km)",
            data: buckets.map((b) => b.tempoKm),
            backgroundColor: "rgba(245, 158, 11, 0.85)",
            borderRadius: 4,
          },
          {
            label: "Ripetute / Gara (km)",
            data: buckets.map((b) => b.hardKm),
            backgroundColor: "rgba(252, 76, 2, 0.88)",
            borderRadius: 4,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: { legend: { labels: { color: "#cbd5e1", boxWidth: 12 } } },
        scales: {
          x: { stacked: true, grid: { display: false }, ticks: { ...baseTicks, maxTicksLimit: 12 } },
          y: { stacked: true, grid: baseGrid, ticks: baseTicks, beginAtZero: true },
        },
      },
    });
  }

  // Default mode: "efficiency" — Efficiency Factor (EF) + Avg Pace (inverted) + subtle Km bars
  return mountChart(canvasId, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          type: "bar",
          label: "Km Corsa",
          data: buckets.map((b) => b.km),
          backgroundColor: "rgba(252, 76, 2, 0.22)",
          borderColor: "rgba(252, 76, 2, 0.45)",
          borderWidth: 1,
          borderRadius: 5,
          yAxisID: "y2",
        },
        {
          type: "line",
          label: "Efficienza Aerobica (EF)",
          data: buckets.map((b) => b.ef),
          borderColor: "#10b981",
          backgroundColor: "rgba(16, 185, 129, 0.14)",
          fill: false,
          spanGaps: true,
          tension: 0.32,
          borderWidth: 2.6,
          pointRadius: 3.5,
          yAxisID: "y",
        },
        {
          type: "line",
          label: "Passo Medio",
          data: buckets.map((b) => (b.avgPaceSec ? +(b.avgPaceSec / 60).toFixed(2) : null)),
          borderColor: "#00b4d8",
          borderDash: [4, 3],
          spanGaps: true,
          tension: 0.32,
          borderWidth: 2.2,
          pointRadius: 3,
          yAxisID: "y1",
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { labels: { color: "#cbd5e1", boxWidth: 12 } },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              if (ctx.dataset.yAxisID === "y1" && ctx.parsed.y != null) {
                return `Passo Medio: ${formatPace(ctx.parsed.y * 60)} /km`;
              }
              if (ctx.dataset.yAxisID === "y" && ctx.parsed.y != null) {
                return `Efficienza (EF): ${ctx.parsed.y.toFixed(2)}`;
              }
              if (ctx.dataset.yAxisID === "y2" && ctx.parsed.y != null) {
                return `Volume: ${ctx.parsed.y} km`;
              }
              return `${ctx.dataset.label}: ${ctx.parsed.y ?? "--"}`;
            },
          },
        },
      },
      scales: {
        x: { grid: { display: false }, ticks: { ...baseTicks, maxTicksLimit: 12 } },
        y: {
          position: "left",
          grid: baseGrid,
          ticks: { ...baseTicks, color: "#34d399" },
          title: { display: true, text: "EF ↑ meglio", color: "#34d399", font: { size: 10 } },
        },
        y1: {
          position: "right",
          reverse: true,
          grid: { display: false },
          ticks: { ...baseTicks, color: "#38bdf8", callback: (v) => formatPace(v * 60) },
          title: { display: true, text: "Passo ↑ più veloce", color: "#38bdf8", font: { size: 10 } },
        },
        y2: {
          display: false,
          beginAtZero: true,
        },
      },
    },
  });
}
