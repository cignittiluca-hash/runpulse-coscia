import { api, escapeHtml, showToast, simpleMarkdown } from "../api.js";

const AVATAR_URL = "/static/icons/calippo.jpg";

function renderMessageHtml(msg) {
  const isUser = msg.role === "user";
  const timeStr = msg.created_at ? msg.created_at.slice(11, 16) : "";
  if (isUser) {
    return `
      <div class="chat-row chat-row-user">
        <div class="chat-bubble chat-bubble-user">
          <div class="chat-text">${escapeHtml(msg.content).replace(/\n/g, "<br/>")}</div>
          ${timeStr ? `<div class="chat-time">${timeStr}</div>` : ""}
        </div>
      </div>`;
  }
  return `
    <div class="chat-row chat-row-bot">
      <img src="${AVATAR_URL}" alt="Calippo" class="calippo-msg-avatar" />
      <div class="chat-bubble chat-bubble-bot">
        <div class="chat-sender">
          Calippo
          ${msg.ai_powered ? `<span class="chat-ai-tag">Gemini AI</span>` : `<span class="chat-local-tag">Dati Live</span>`}
        </div>
        <div class="chat-text">${simpleMarkdown(msg.content)}</div>
        ${timeStr ? `<div class="chat-time">${timeStr}</div>` : ""}
      </div>
    </div>`;
}

function welcomeMessageHtml() {
  return `
    <div class="chat-row chat-row-bot">
      <img src="${AVATAR_URL}" alt="Calippo" class="calippo-msg-avatar" />
      <div class="chat-bubble chat-bubble-bot">
        <div class="chat-sender">Calippo <span class="chat-ai-tag">Personal Coach</span></div>
        <div class="chat-text">
          Ehi! Sono <strong>Calippo</strong>, il tuo coach personale di corsa.<br/>
          Ho accesso in tempo reale alle tue corse <strong>Strava</strong>, ai dati di salute/HRV/sonno <strong>Apple Watch</strong> e al tuo <strong>piano gara</strong>.<br/>
          Chiedimi pure qualsiasi cosa sui tuoi dati o su cosa fare oggi!
        </div>
      </div>
    </div>`;
}

function createTypingNode(isGemini = false) {
  const wrap = document.createElement("div");
  wrap.className = "chat-row chat-row-bot";
  wrap.innerHTML = `
    <img src="${AVATAR_URL}" alt="Calippo" class="calippo-msg-avatar" />
    <div class="chat-bubble chat-bubble-bot">
      <div style="display:flex;align-items:center;gap:10px;">
        <div class="typing-dots"><span></span><span></span><span></span></div>
        <span style="font-size:0.8rem;color:#93a1be;">${isGemini ? "Calippo (Gemini 3.8) sta riflettendo sui tuoi dati..." : "Analisi dati..."}</span>
      </div>
    </div>`;
  return wrap;
}

const isTouchDevice = () => window.matchMedia && window.matchMedia("(pointer: coarse)").matches;

export async function renderCalippo(container, navigate, isStale = () => false) {
  container.innerHTML = `<div class="loading-state">Sto svegliando Calippo...</div>`;
  let data;
  try {
    data = await api.getCalippoMessages();
  } catch (err) {
    if (isStale()) return;
    const hint = err.message.includes("Not Found")
      ? "<br/><br/>Il server locale va riavviato una volta per attivare Calippo: premi <code>Ctrl+C</code> nel terminale e rilancia <code>./start.sh</code>, poi ricarica la pagina."
      : "";
    container.innerHTML = `<div class="card empty-state">Errore caricamento Calippo: ${escapeHtml(err.message)}${hint}</div>`;
    return;
  }
  if (isStale()) return;

  const messages = data.messages || [];
  const suggestions = data.suggestions || [];

  container.innerHTML = `
    <section class="calippo-shell card">
      <div class="calippo-header">
        <div class="calippo-id">
          <div class="calippo-avatar-wrap">
            <img src="${AVATAR_URL}" alt="Calippo" class="calippo-avatar-lg" />
            <span class="online-dot"></span>
          </div>
          <div>
            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
              <h2 style="font-size:1.2rem;font-weight:800;">Calippo</h2>
              <span class="pill ${data.gemini_configured ? "pill-violet" : "pill-amber"}">
                ${data.gemini_configured ? "✨ Gemini 3.8 Thinking Attivo" : "⚠️ Solo Risposte Locali (Gemini non collegato)"}
              </span>
            </div>
            <p class="subtitle">Chatbot AI connesso ai tuoi dati Strava, Garmin Stress/HRV e Piano Gara</p>
          </div>
        </div>

        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          <button class="btn btn-ghost btn-sm" id="calippo-clear-btn">🗑️ Nuova Chat</button>
        </div>
      </div>

      ${
        !data.gemini_configured
          ? `<form id="calippo-inline-gemini" style="display:flex;flex-wrap:wrap;align-items:center;gap:10px;padding:12px 18px;background:rgba(139,92,246,0.12);border-bottom:1px solid rgba(139,92,246,0.3);">
              <div style="flex:1;min-width:240px;font-size:0.83rem;color:#ede9fe;">
                <strong>Per far ragionare Calippo come il vero Gemini 3.8:</strong>
                crea una chiave gratuita su <a href="https://aistudio.google.com/apikey" target="_blank" style="color:#c4b5fd;text-decoration:underline;">aistudio.google.com/apikey</a> e incollala qui:
              </div>
              <input class="input" id="calippo-inline-key" type="password" placeholder="Incolla Gemini API Key (AIza...)" style="max-width:260px;" required />
              <button class="btn btn-ai btn-sm" type="submit" id="calippo-inline-save">✨ Attiva Gemini 3.8</button>
            </form>`
          : ""
      }

      <div class="calippo-messages" id="calippo-messages">
        ${messages.length ? messages.map(renderMessageHtml).join("") : welcomeMessageHtml()}
      </div>

      <div class="calippo-suggestions" id="calippo-suggestions">
        ${suggestions
          .map((s) => `<button type="button" class="suggestion-chip" data-q="${escapeHtml(s)}">${escapeHtml(s)}</button>`)
          .join("")}
      </div>

      <form class="calippo-input-bar" id="calippo-form">
        <input
          class="input"
          id="calippo-input"
          placeholder="Scrivi a Calippo (es. 'Com'è andato il mio stress Garmin questa settimana?')"
          autocomplete="off"
        />
        <button class="btn btn-primary" type="submit" id="calippo-send-btn">Invia</button>
      </form>
    </section>
  `;

  const msgBox = document.getElementById("calippo-messages");
  const input = document.getElementById("calippo-input");
  const sendBtn = document.getElementById("calippo-send-btn");
  const chips = Array.from(container.querySelectorAll(".suggestion-chip"));
  msgBox.scrollTop = msgBox.scrollHeight;
  let isSending = false;

  async function sendQuestion(text) {
    const q = text.trim();
    if (!q || isSending) return;
    isSending = true;
    input.value = "";
    sendBtn.disabled = true;
    chips.forEach((c) => { c.disabled = true; });

    const nowTime = new Date().toTimeString().slice(0, 5);
    msgBox.insertAdjacentHTML(
      "beforeend",
      renderMessageHtml({ role: "user", content: q, created_at: `0000-00-00 ${nowTime}` })
    );
    const typingEl = createTypingNode(data.gemini_configured);
    msgBox.appendChild(typingEl);
    msgBox.scrollTop = msgBox.scrollHeight;

    try {
      const res = await api.sendCalippoMessage(q);
      typingEl.remove();
      msgBox.insertAdjacentHTML("beforeend", renderMessageHtml(res.reply));
      msgBox.scrollTop = msgBox.scrollHeight;
    } catch (err) {
      typingEl.remove();
      showToast(err.message, "error");
    } finally {
      isSending = false;
      sendBtn.disabled = false;
      chips.forEach((c) => { c.disabled = false; });
      if (!isTouchDevice()) input.focus();
    }
  }

  document.getElementById("calippo-form")?.addEventListener("submit", (e) => {
    e.preventDefault();
    sendQuestion(input.value);
  });

  chips.forEach((chip) => {
    chip.addEventListener("click", () => sendQuestion(chip.dataset.q));
  });

  document.getElementById("calippo-clear-btn")?.addEventListener("click", async () => {
    if (!confirm("Vuoi azzerare l'intera conversazione con Calippo?")) return;
    try {
      await api.clearCalippoMessages();
      msgBox.innerHTML = welcomeMessageHtml();
      showToast("Chat con Calippo azzerata!", "info");
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  document.getElementById("calippo-inline-gemini")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const keyInput = document.getElementById("calippo-inline-key");
    const btn = document.getElementById("calippo-inline-save");
    const key = keyInput.value.trim();
    if (!key) return;
    btn.disabled = true;
    btn.textContent = "Verifica Gemini...";
    try {
      await api.updateSettings({ gemini_api_key: key, gemini_model: "gemini-3.8-flash" });
      const test = await api.testGemini();
      if (!test.ok) {
        showToast(test.error || "Chiave Gemini non valida.", "error");
        btn.disabled = false;
        btn.textContent = "✨ Attiva Gemini 3.8";
        return;
      }
      showToast("Gemini 3.8 Thinking attivato! Ora Calippo ragiona sui tuoi dati reali!", "success");
      renderCalippo(container, navigate);
    } catch (err) {
      showToast(err.message, "error");
      btn.disabled = false;
      btn.textContent = "✨ Attiva Gemini 3.8";
    }
  });
}

// Floating Calippo Chat Drawer accessible from every other tab
export function initCalippoWidget(navigate) {
  const fab = document.getElementById("calippo-fab");
  const drawer = document.getElementById("calippo-drawer");
  const closeBtn = document.getElementById("calippo-drawer-close");
  const expandBtn = document.getElementById("calippo-drawer-expand");
  const body = document.getElementById("calippo-drawer-messages");
  const form = document.getElementById("calippo-drawer-form");
  const input = document.getElementById("calippo-drawer-input");
  const sendBtn = document.getElementById("calippo-drawer-send");

  if (!fab || !drawer) return;

  let drawerGemini = false;
  let drawerSending = false;

  async function loadDrawerMessages() {
    try {
      const data = await api.getCalippoMessages();
      drawerGemini = Boolean(data.gemini_configured);
      const msgs = data.messages || [];
      body.innerHTML = msgs.length ? msgs.slice(-20).map(renderMessageHtml).join("") : welcomeMessageHtml();
      body.scrollTop = body.scrollHeight;
    } catch {
      body.innerHTML = welcomeMessageHtml();
    }
  }

  fab.addEventListener("click", async () => {
    const isOpen = !drawer.classList.contains("hidden");
    if (isOpen) {
      drawer.classList.add("hidden");
    } else {
      drawer.classList.remove("hidden");
      await loadDrawerMessages();
      if (!isTouchDevice()) input?.focus();
    }
  });

  closeBtn?.addEventListener("click", () => drawer.classList.add("hidden"));
  expandBtn?.addEventListener("click", () => {
    drawer.classList.add("hidden");
    navigate("calippo");
  });

  form?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const q = input.value.trim();
    if (!q || drawerSending) return;
    drawerSending = true;
    input.value = "";
    sendBtn.disabled = true;

    const nowTime = new Date().toTimeString().slice(0, 5);
    body.insertAdjacentHTML(
      "beforeend",
      renderMessageHtml({ role: "user", content: q, created_at: `0000-00-00 ${nowTime}` })
    );
    const typingEl = createTypingNode(drawerGemini);
    body.appendChild(typingEl);
    body.scrollTop = body.scrollHeight;

    try {
      const res = await api.sendCalippoMessage(q);
      typingEl.remove();
      body.insertAdjacentHTML("beforeend", renderMessageHtml(res.reply));
      body.scrollTop = body.scrollHeight;
    } catch (err) {
      typingEl.remove();
      showToast(err.message, "error");
    } finally {
      drawerSending = false;
      sendBtn.disabled = false;
      if (!isTouchDevice()) input.focus();
    }
  });
}
