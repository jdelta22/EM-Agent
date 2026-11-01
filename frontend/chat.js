const STORAGE_KEY = "em_conversation_id";
const POLL_MS = 3000;
const WELCOME = "Oi! Eu sou o assistente virtual da Empório da Música. Posso ajudar com instrumentos, preços, " +
  "promoções, pedidos e políticas da loja. Como posso ajudar?";
const SUGGESTIONS = [
  "Quais promoções estão ativas?",
  "Quero um violão para iniciante",
  "Qual o prazo para devolução?",
  "Quero saber do meu pedido",
];
const WHO = { customer: null, agent: null, attendant: "Atendente da loja" };

const $ = (id) => document.getElementById(id);
const thread = $("thread"), scroller = $("scroller"), input = $("input"), form = $("form"), sendBtn = $("send");
const composer = setupComposer(input, form);

let conversationId = localStorage.getItem(STORAGE_KEY);
let total = 0;            // messages already shown, used as the `after` cursor
let handledBy = "agent";
let pollTimer = null;
let busy = false;

async function api(path, options) {
  const res = await fetch(path, options);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Algo deu errado. Tente novamente.");
  return body;
}

function add(role, text) {
  const el = messageEl(role, text, WHO[role]);
  thread.appendChild(el);
  scrollToEnd(scroller);
  return el;
}

function setHandler(next) {
  const changed = next !== handledBy;
  handledBy = next;
  const pill = $("status");
  pill.textContent = next === "human" ? "Atendente da loja" : "Assistente virtual";
  pill.classList.toggle("human", next === "human");
  if (next === "human") startPolling(); else stopPolling();
  return changed;
}

function startPolling() {
  if (!pollTimer && conversationId) pollTimer = setInterval(sync, POLL_MS);
}
function stopPolling() {
  clearInterval(pollTimer);
  pollTimer = null;
}

// Fetches what the server has after `total` and shows it. The server is the source of truth.
async function sync() {
  if (busy || !conversationId) return;
  try {
    const data = await api(`/api/chat/${conversationId}?after=${total}`);
    data.messages.forEach((m) => add(m.role, m.text));
    total = data.total;
    const previous = handledBy;
    setHandler(data.handled_by);
    if (previous === "human" && data.handled_by === "agent") {
      add("system", "O atendimento voltou para o assistente virtual.");
    }
  } catch {
    /* transient failure while polling: try again on the next tick */
  }
}

function showWelcome() {
  add("agent", WELCOME);
  const chips = document.createElement("div");
  chips.className = "chips";
  chips.id = "chips";
  SUGGESTIONS.forEach((text) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip";
    chip.textContent = text;
    chip.addEventListener("click", () => send(text));
    chips.appendChild(chip);
  });
  thread.appendChild(chips);
}

async function restore() {
  if (conversationId) {
    try {
      const data = await api(`/api/chat/${conversationId}`);
      if (data.messages.length) {
        data.messages.forEach((m) => add(m.role, m.text));
        total = data.total;
        setHandler(data.handled_by);
        return;
      }
    } catch {
      /* fall through to a fresh welcome */
    }
  }
  showWelcome();
}

async function send(text) {
  text = text.trim();
  if (!text || busy) return;
  busy = true;
  sendBtn.disabled = true;
  $("chips")?.remove();
  composer.reset();

  const pending = add("customer", text);
  pending.classList.add("pending");
  const typing = typingEl();
  if (handledBy === "agent") { thread.appendChild(typing); scrollToEnd(scroller); }

  try {
    const res = await api("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, ...(conversationId && { conversation_id: conversationId }) }),
    });
    conversationId = res.conversation_id;
    localStorage.setItem(STORAGE_KEY, conversationId);
    pending.remove();
    typing.remove();
    busy = false;
    await sync();            // shows the customer message and the answer, as stored
    setHandler(res.handled_by);
    if (res.handled_by === "human" && !pollTimer) startPolling();
  } catch (err) {
    pending.remove();
    typing.remove();
    add("error", err.message);
    input.value = text;      // let the customer retry without retyping
  } finally {
    busy = false;
    sendBtn.disabled = false;
    input.focus();
  }
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  send(input.value);
});

$("new-chat").addEventListener("click", () => {
  if (total > 0 && !confirm("Começar uma nova conversa? A atual deixará de aparecer aqui.")) return;
  stopPolling();
  localStorage.removeItem(STORAGE_KEY);
  conversationId = null;
  total = 0;
  handledBy = "agent";
  setHandler("agent");
  thread.replaceChildren();
  showWelcome();
  input.focus();
});

restore();
