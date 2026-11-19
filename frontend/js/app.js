import { api, showToast } from "./api.js";
import { destroyAllCharts, destroyChart } from "./charts.js";
import { renderDashboard } from "./views/dashboard.js";
import { renderActivities } from "./views/activities.js";
import { renderWellness } from "./views/wellness.js";
import { renderPlans } from "./views/plans.js";
import { renderSettings } from "./views/settings.js";
import { initCalippoWidget, renderCalippo } from "./views/calippo.js";

const VIEW_META = {
  dashboard: {
    title: "Dashboard",
    subtitle: "Analisi giornaliera del recupero Garmin, carico Strava e consiglio del Coach",
  },
  activities: {
    title: "Corse & Analisi",
    subtitle: "Studia ogni allenamento: parziali, zone cardio, deriva cardiaca ed efficienza",
  },
  wellness: {
    title: "Stress & Benessere Garmin",
    subtitle: "Monitoraggio Stress giornaliero, Body Battery, HRV notturna, Sonno e FC a riposo",
  },
  plans: {
    title: "Obiettivo Gara & Piano",
    subtitle: "Crea tabelle periodizzate (5K, 10K, Mezza, Maratona) adattabili allo stress Garmin",
  },
  calippo: {
    title: "Calippo AI",
    subtitle: "Parla liberamente con Calippo di tutte le tue corse, stress Garmin e obiettivi",
  },
  settings: {
    title: "Connessioni & Profilo",
    subtitle: "Collega Strava, Garmin Connect, Google Gemini AI e configura l'auto-sync",
  },
};

let currentView = "dashboard";
let navSeq = 0;

async function refreshSidebarStatus() {
  try {
    const s = await api.getSettings();
    const badge = document.getElementById("athlete-badge");
    if (badge) badge.textContent = `🏃 ${s.athlete_name || "Runner"}`;
    const pills = document.getElementById("sidebar-conn-pills");
    if (pills) {
      pills.innerHTML = `
        <span class="pill ${s.strava_connected ? "pill-green" : "pill-muted"}">
          Strava: ${s.strava_connected ? "Connesso" : "Off"}
        </span>
        <span class="pill ${s.garmin_connected ? "pill-cyan" : "pill-muted"}">
          Garmin: ${s.garmin_connected ? "Connesso" : "Off"}
        </span>
      `;
    }
  } catch {
    // Ignore transient status fetch failure
  }
}

export async function navigate(view) {
  if (!VIEW_META[view]) view = "dashboard";
  const mySeq = ++navSeq;
  currentView = view;
  if (window.location.hash.replace("#", "") !== view) {
    window.location.hash = view;
  }
  destroyAllCharts();

  document.querySelectorAll("[data-view]").forEach((el) => {
    el.classList.toggle("active", el.dataset.view === view);
  });

  document.getElementById("page-title").textContent = VIEW_META[view].title;
  document.getElementById("page-subtitle").textContent = VIEW_META[view].subtitle;

  const container = document.getElementById("view-container");
  const fab = document.getElementById("calippo-fab");
  const drawer = document.getElementById("calippo-drawer");
  if (fab) fab.style.display = view === "calippo" ? "none" : "flex";
  if (view === "calippo" && drawer) drawer.classList.add("hidden");

  // Render into detached proxy check: views check navSeq via isCurrentNav
  const isStale = () => mySeq !== navSeq;
  if (view === "dashboard") await renderDashboard(container, navigate, isStale);
  else if (view === "activities") await renderActivities(container, isStale);
  else if (view === "wellness") await renderWellness(container, navigate, isStale);
  else if (view === "plans") await renderPlans(container, isStale);
  else if (view === "calippo") await renderCalippo(container, navigate, isStale);
  else if (view === "settings") await renderSettings(container, refreshSidebarStatus, isStale);
}

async function triggerGlobalSync(btn) {
  const prev = btn.innerHTML;
  btn.disabled = true;
  btn.textContent = "Sincronizzazione...";
  try {
    const res = await api.syncAll(30);
    const parts = [];
    if (res.strava) parts.push(`Strava: ${res.strava.synced_activities} attività`);
    if (res.garmin) parts.push(`Garmin: ${res.garmin.days_synced} giorni`);
    if (res.errors?.length) showToast(res.errors.join(" | "), "error");
    else showToast(`Sync completato! ${parts.join(" · ")}`, "success");
    await refreshSidebarStatus();
    await navigate(currentView);
  } catch (err) {
    showToast(err.message, "error");
  } finally {
    btn.disabled = false;
    btn.innerHTML = prev;
  }
}

function initModal() {
  const backdrop = document.getElementById("modal-backdrop");
  const closeBtn = document.getElementById("modal-close");
  const bodyEl = document.getElementById("modal-body");
  const close = () => {
    destroyChart("chart-run-splits");
    backdrop?.classList.add("hidden");
    document.body.classList.remove("modal-open");
    if (bodyEl) bodyEl.innerHTML = "";
  };
  closeBtn?.addEventListener("click", close);
  backdrop?.addEventListener("click", (e) => {
    if (e.target === backdrop) close();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && backdrop && !backdrop.classList.contains("hidden")) close();
  });
}

function setupIosInstallBanner() {
  const banner = document.getElementById("ios-install-banner");
  const closeBtn = document.getElementById("ios-banner-close");
  if (!banner) return;
  const isIos = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
  const isStandalone = window.navigator.standalone === true || window.matchMedia("(display-mode: standalone)").matches;
  const dismissed = localStorage.getItem("runpulse_ios_banner_dismissed") === "1";
  if (isIos && !isStandalone && !dismissed) {
    banner.classList.remove("hidden");
  }
  closeBtn?.addEventListener("click", () => {
    banner.classList.add("hidden");
    localStorage.setItem("runpulse_ios_banner_dismissed", "1");
  });
}

let _lockListenerBound = false;
let _unlockResolve = null;

function showLockOverlay() {
  const screen = document.getElementById("lock-screen");
  const form = document.getElementById("lock-form");
  const input = document.getElementById("lock-password");
  const errEl = document.getElementById("lock-error");
  const btn = document.getElementById("lock-submit");
  if (!screen) return Promise.resolve(true);
  screen.classList.remove("hidden");
  if (!window.matchMedia("(pointer: coarse)").matches) input?.focus();

  if (!_lockListenerBound && form) {
    _lockListenerBound = true;
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      errEl.textContent = "";
      btn.disabled = true;
      btn.textContent = "Verifica...";
      try {
        await api.loginApp(input.value);
        screen.classList.add("hidden");
        input.value = "";
        btn.disabled = false;
        btn.textContent = "🔓 Sblocca RunPulse";
        if (_unlockResolve) {
          const r = _unlockResolve;
          _unlockResolve = null;
          r(true);
        }
      } catch (err) {
        errEl.textContent = err.message;
        btn.disabled = false;
        btn.textContent = "🔓 Sblocca RunPulse";
      }
    });
  }
  return new Promise((resolve) => {
    _unlockResolve = resolve;
  });
}

async function ensureUnlocked() {
  try {
    const auth = await api.getAuthStatus();
    if (!auth.password_enabled || auth.authenticated) return true;
  } catch {
    return true;
  }
  return showLockOverlay();
}

async function boot() {
  initModal();
  setupIosInstallBanner();
  window.addEventListener("runpulse:unauthorized", () => {
    showLockOverlay().then(() => navigate(currentView));
  });
  window.addEventListener("hashchange", () => {
    const target = window.location.hash.replace("#", "") || "dashboard";
    if (target !== currentView && VIEW_META[target]) {
      navigate(target);
    }
  });
  await ensureUnlocked();
  initCalippoWidget(navigate);

  // Register Service Worker for PWA installability
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }

  // Nav bindings
  document.querySelectorAll("[data-view]").forEach((btn) => {
    btn.addEventListener("click", () => navigate(btn.dataset.view));
  });

  document.getElementById("btn-global-sync")?.addEventListener("click", (e) => triggerGlobalSync(e.currentTarget));
  document.getElementById("btn-mobile-sync")?.addEventListener("click", (e) => triggerGlobalSync(e.currentTarget));

  // Handle Strava OAuth callback query parameter
  const params = new URLSearchParams(window.location.search);
  if (params.get("strava") === "connected") {
    showToast("Account Strava collegato e allenamenti sincronizzati!", "success");
    window.history.replaceState({}, "", "/#settings");
  } else if (params.get("strava") === "error") {
    showToast("Autorizzazione Strava annullata o non riuscita.", "error");
    window.history.replaceState({}, "", "/#settings");
  }

  const initialHash = window.location.hash.replace("#", "") || "dashboard";
  await Promise.all([refreshSidebarStatus(), navigate(initialHash)]);
}

boot();
