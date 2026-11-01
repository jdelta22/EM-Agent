const TOKEN_KEY = "em_attendant_token";
const WHO = { customer: "Cliente", agent: "Assistente (IA)", attendant: "Você" };
const QUEUE_REFRESH_MS = 15000;

const $ = (id) => document.getElementById(id);
const thread = $("thread"), scroller = $("scroller"), input = $("input"), form = $("form");
const composer = setupComposer(input, form);

let token = sessionStorage.getItem(TOKEN_KEY);
let queue = [];
let selected = null;            // conversation id open on the right
let handledBy = "human";        // of the open conversation
const unread = new Map();       // conversation id -> new customer messages
let streamAbort = null;

async function api(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", "X-Attendant-Token": token, ...options.headers },
  });
  if (res.status === 401) { logout("Token inválido."); throw new Error("unauthorized"); }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Erro inesperado.");
  return body;
}

// ---------- login ----------
function showPanel(on) {
  $("login").hidden = on;
  $("panel").hidden = !on;
}

function logout(message = "") {
  streamAbort?.abort();
  sessionStorage.removeItem(TOKEN_KEY);
  token = null;
  showPanel(false);
  $("login-error").textContent = message;
}

$("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  token = $("token").value.trim();
  $("login-error").textContent = "";
  try {
    await api("/api/attendant/conversations");
  } catch (err) {
    if (err.message !== "unauthorized") $("login-error").textContent = err.message;
    return;
  }
  sessionStorage.setItem(TOKEN_KEY, token);
  $("token").value = "";
  start();
});

$("logout").addEventListener("click", () => logout());

// ---------- queue ----------
function minutes(seconds) {
  return Math.max(1, Math.round(seconds / 60));
}

function renderQueue() {
  const box = $("queue");
  box.replaceChildren();
  if (!queue.length) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "Nenhuma conversa em atendimento humano.";
    box.appendChild(empty);
    return;
  }
  for (const item of queue) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "q-item" + (item.conversation_id === selected ? " active" : "");

    const row = document.createElement("div");
    row.className = "row";
    const id = document.createElement("span");
    id.textContent = `#${item.conversation_id.slice(0, 6)} · expira em ${minutes(item.expires_in)} min`;
    row.appendChild(id);
    const count = unread.get(item.conversation_id);
    if (count) {
      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = count;
      row.appendChild(badge);
    }

    const reason = document.createElement("div");
    reason.className = "reason";
    reason.textContent = item.reason || "Sem resumo do assistente.";

    btn.append(row, reason);
    btn.addEventListener("click", () => openConversation(item.conversation_id));
    box.appendChild(btn);
  }
}

async function refreshQueue() {
  queue = await api("/api/attendant/conversations");
  renderQueue();
  updateTitle();
}

function updateTitle() {
  const n = [...unread.values()].reduce((a, b) => a + b, 0);
  document.title = (n ? `(${n}) ` : "") + "Atendimento — Empório da Música";
}

// ---------- open conversation ----------
async function openConversation(id) {
  selected = id;
  unread.delete(id);
  renderQueue();
  updateTitle();
  await loadConversation();
  input.focus();
}

async function loadConversation() {
  if (!selected) return;
  const data = await api(`/api/attendant/conversations/${selected}`);
  handledBy = data.handled_by;
  thread.replaceChildren();
  data.messages.forEach((m) => thread.appendChild(messageEl(m.role, m.text, WHO[m.role])));
  if (handledBy !== "human") {
    thread.appendChild(messageEl("system", "Esta conversa está com o assistente virtual. Se você responder, assume o atendimento."));
  }
  $("placeholder").hidden = true;
  $("convo-head").hidden = false;
  $("composer").hidden = false;
  $("release").disabled = handledBy !== "human";
  const item = queue.find((q) => q.conversation_id === selected);
  $("convo-title").textContent = `Conversa #${selected.slice(0, 6)}`;
  $("convo-reason").textContent = item?.reason || "";
  $("convo-reason").title = item?.reason || "";
  scrollToEnd(scroller);
}

function closeConversation() {
  selected = null;
  thread.replaceChildren();
  $("placeholder").hidden = false;
  $("convo-head").hidden = true;
  $("composer").hidden = true;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text || !selected) return;
  $("send").disabled = true;
  try {
    await api(`/api/attendant/conversations/${selected}/message`, { method: "POST", body: JSON.stringify({ text }) });
    composer.reset();
    await refreshQueue();
    await loadConversation();
  } catch (err) {
    if (err.message !== "unauthorized") thread.appendChild(messageEl("error", `Não enviou: ${err.message}`));
  } finally {
    $("send").disabled = false;
    input.focus();
  }
});

$("release").addEventListener("click", async () => {
  if (!selected || !confirm("Devolver esta conversa ao assistente virtual?")) return;
  try {
    await api(`/api/attendant/conversations/${selected}/release`, { method: "POST" });
    closeConversation();
    await refreshQueue();
  } catch (err) {
    if (err.message !== "unauthorized") alert(err.message);
  }
});

// ---------- live events (server-sent events over fetch, so the token goes in a header) ----------
function setLive(on) {
  $("dot").classList.toggle("on", on);
  $("live-text").textContent = on ? "Ao vivo" : "Reconectando…";
}

function handleEvent(event) {
  const id = event.conversation_id;
  if (event.type === "customer_message" && id !== selected) {
    unread.set(id, (unread.get(id) || 0) + 1);
  }
  if (event.type === "transfer") {
    unread.set(id, unread.get(id) || 1);
    if (document.hidden && "Notification" in window && Notification.permission === "granted") {
      new Notification("Nova conversa para atender", { body: event.reason || "" });
    }
  }
  if (event.type === "released" && id === selected) closeConversation();
  refreshQueue()
    .then(() => {
      if (selected && id === selected && event.type === "customer_message") return loadConversation();
    })
    .catch(() => {});
}

async function listen() {
  streamAbort = new AbortController();
  const { signal } = streamAbort;
  let delay = 1000;
  while (!signal.aborted) {
    try {
      const res = await fetch("/api/attendant/events", { headers: { "X-Attendant-Token": token }, signal });
      if (res.status === 401) return logout("Token inválido.");
      if (!res.ok) throw new Error(`status ${res.status}`);
      setLive(true);
      delay = 1000;
      refreshQueue().catch(() => {});   // catch up on anything missed while disconnected
      const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
      let buffer = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += value;
        let end;
        while ((end = buffer.indexOf("\n\n")) >= 0) {
          const chunk = buffer.slice(0, end);
          buffer = buffer.slice(end + 2);
          const line = chunk.split("\n").find((l) => l.startsWith("data: "));
          if (line) {
            try { handleEvent(JSON.parse(line.slice(6))); } catch { /* ignore a malformed event */ }
          }
        }
      }
    } catch {
      if (signal.aborted) return;
    }
    setLive(false);
    await new Promise((r) => setTimeout(r, delay));
    delay = Math.min(delay * 2, 15000);
  }
}

function start() {
  showPanel(true);
  closeConversation();
  refreshQueue().catch(() => {});
  listen();
  if ("Notification" in window && Notification.permission === "default") Notification.requestPermission();
}

setInterval(() => { if (token && !$("panel").hidden) refreshQueue().catch(() => {}); }, QUEUE_REFRESH_MS);

if (token) {
  api("/api/attendant/conversations").then(start).catch(() => {});
}
