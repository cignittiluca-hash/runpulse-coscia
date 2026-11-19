// API client & formatting utilities for RunPulse

export async function apiRequest(path, options = {}) {
  const opts = {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  };
  if (opts.body && typeof opts.body !== "string") {
    opts.body = JSON.stringify(opts.body);
  }
  const resp = await fetch(path, opts);
  let data = null;
  try {
    data = await resp.json();
  } catch {
    data = null;
  }
  if (!resp.ok) {
    if (resp.status === 401 && !path.startsWith("/api/auth/")) {
      window.dispatchEvent(new CustomEvent("runpulse:unauthorized"));
    }
    const msg = (data && (data.detail || data.message)) || `Errore HTTP ${resp.status}`;
    throw new Error(msg);
  }
  return data;
}

export const api = {
  getDashboard: (useAi = false) => apiRequest(`/api/dashboard?use_ai=${useAi}`),
  getActivities: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return apiRequest(`/api/activities${q ? "?" + q : ""}`);
  },
  getActivity: (id) => apiRequest(`/api/activities/${encodeURIComponent(id)}`),
  analyzeActivity: (id) => apiRequest(`/api/activities/${encodeURIComponent(id)}/analyze`, { method: "POST" }),
  getWellness: (days = 30) => apiRequest(`/api/wellness?days=${days}`),
  getDailyCoach: (useAi = true) => apiRequest(`/api/coach/daily?use_ai=${useAi}`),
  askCoach: (question) => apiRequest("/api/coach/ask", { method: "POST", body: { question } }),
  getCalippoMessages: () => apiRequest("/api/calippo/messages"),
  sendCalippoMessage: (question) => apiRequest("/api/calippo/chat", { method: "POST", body: { question } }),
  clearCalippoMessages: () => apiRequest("/api/calippo/messages", { method: "DELETE" }),
  testGemini: () => apiRequest("/api/gemini/test", { method: "POST" }),
  getAuthStatus: () => apiRequest("/api/auth/status"),
  loginApp: (password) => apiRequest("/api/auth/login", { method: "POST", body: { password } }),
  logoutApp: () => apiRequest("/api/auth/logout", { method: "POST" }),
  getMobileInfo: () => apiRequest("/api/mobile-info"),
  getPlans: () => apiRequest("/api/plans"),
  createPlan: (payload) => apiRequest("/api/plans", { method: "POST", body: payload }),
  activatePlan: (id) => apiRequest(`/api/plans/${id}/activate`, { method: "POST" }),
  adaptPlan: (id) => apiRequest(`/api/plans/${id}/adapt`, { method: "POST" }),
  deletePlan: (id) => apiRequest(`/api/plans/${id}`, { method: "DELETE" }),
  toggleWorkout: (id, completed) =>
    apiRequest(`/api/workouts/${id}`, { method: "PATCH", body: { completed } }),
  getSettings: () => apiRequest("/api/settings"),
  updateSettings: (payload) => apiRequest("/api/settings", { method: "PUT", body: payload }),
  getStravaAuthUrl: () => apiRequest("/api/strava/auth-url"),
  syncStrava: (days = 60, all_history = false) =>
    apiRequest("/api/strava/sync", { method: "POST", body: { days, all_history } }),
  disconnectStrava: () => apiRequest("/api/strava/disconnect", { method: "POST" }),
  loginGarmin: (email, password, mfa_code = null) =>
    apiRequest("/api/garmin/login", { method: "POST", body: { email, password, mfa_code } }),
  submitGarminMfa: (mfa_code) =>
    apiRequest("/api/garmin/mfa", { method: "POST", body: { mfa_code } }),
  syncGarmin: (days = 14, force_full = false) =>
    apiRequest("/api/garmin/sync", { method: "POST", body: { days, force_full } }),
  disconnectGarmin: () => apiRequest("/api/garmin/disconnect", { method: "POST" }),
  getWhoopConfig: () => apiRequest("/api/whoop/config"),
  getWhoopAuthUrl: () => apiRequest("/api/whoop/auth-url"),
  syncWhoop: () => apiRequest("/api/whoop/sync", { method: "POST" }),
  getWhoopDaily: (days = 30) => apiRequest(`/api/whoop/daily?days=${days}`),
  manualWhoopEntry: (payload) => apiRequest("/api/whoop/manual", { method: "POST", body: payload }),
  syncAll: (days = 30) => apiRequest("/api/sync-all", { method: "POST", body: { days } }),
  seedDemo: () => apiRequest("/api/demo/seed", { method: "POST" }),
  clearDemo: () => apiRequest("/api/demo/clear", { method: "DELETE" }),
  importBackup: (payload) => apiRequest("/api/backup/import", { method: "POST", body: payload }),
};

export function formatPace(secPerKm) {
  if (!secPerKm || secPerKm <= 0 || !isFinite(secPerKm)) return "--:--";
  const tot = Math.round(secPerKm);
  const m = Math.floor(tot / 60);
  const s = tot % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function formatHoursMin(sec) {
  if (sec == null || sec <= 0 || !isFinite(sec)) return "0m";
  const totMin = Math.round(sec / 60);
  const h = Math.floor(totMin / 60);
  const m = totMin % 60;
  if (h > 0) return `${h}h ${String(m).padStart(2, "0")}m`;
  return `${m}m`;
}

export function formatMinHM(minutes) {
  if (minutes == null || minutes <= 0 || !isFinite(minutes)) return "0m";
  return formatHoursMin(minutes * 60);
}

export function localDateIso(d = new Date()) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function formatDuration(sec) {
  if (!sec || sec <= 0) return "0m";
  const t = Math.round(sec);
  const h = Math.floor(t / 3600);
  const m = Math.floor((t % 3600) / 60);
  const s = t % 60;
  if (h > 0) return `${h}h ${String(m).padStart(2, "0")}m`;
  return `${m}m ${String(s).padStart(2, "0")}s`;
}

export function formatRaceTime(sec) {
  if (!sec || sec <= 0) return "--:--";
  const t = Math.round(sec);
  const h = Math.floor(t / 3600);
  const m = Math.floor((t % 3600) / 60);
  const s = t % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function categoryBadge(cat) {
  const map = {
    recovery: ["Rigenerante", "pill-cyan"],
    easy: ["Facile Z2", "pill-green"],
    tempo: ["Tempo / Soglia", "pill-amber"],
    intervals: ["Ripetute VO2", "pill-orange"],
    long: ["Lungo", "pill-violet"],
    race: ["Gara", "pill-red"],
    strength: ["Forza / Pesi", "pill-violet"],
    cross_training: ["Cross-Training", "pill-cyan"],
    rest: ["Riposo", "pill-muted"],
  };
  const [label, cls] = map[cat] || [cat || "Corsa", "pill-muted"];
  return `<span class="pill ${cls}">${label}</span>`;
}

export function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function simpleMarkdown(text) {
  if (!text) return "";
  return escapeHtml(text)
    .replace(/^### (.+)$/gm, "<h4 style='margin:10px 0 4px;color:#fb923c;'>$1</h4>")
    .replace(/^## (.+)$/gm, "<h3 style='margin:12px 0 5px;color:#f3f6fc;font-size:1rem;'>$1</h3>")
    .replace(/^[-*•]\s+(.+)$/gm, "• $1")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[\s(])\*([^*\n]+?)\*([\s).,!?:;]|$)/g, "$1<em>$2</em>$3")
    .replace(/`([^`]+)`/g, "<code style='background:rgba(255,255,255,0.09);padding:1px 5px;border-radius:5px;font-size:0.84em;'>$1</code>")
    .replace(/\n{2,}/g, "<br/><br/>")
    .replace(/\n/g, "<br/>");
}

export function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  if (!container) return;
  const el = document.createElement("div");
  el.className = `toast toast-${type}`;
  el.textContent = message;
  container.appendChild(el);
  setTimeout(() => {
    el.style.opacity = "0";
    setTimeout(() => el.remove(), 220);
  }, 4200);
}
