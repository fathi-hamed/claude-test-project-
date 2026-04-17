const tiles = document.getElementById("tiles");
const messagesEl = document.getElementById("messages");
const composer = document.getElementById("composer");
const input = document.getElementById("input");
const sendBtn = document.getElementById("send");
const toasts = document.getElementById("toasts");
const providerBadge = document.getElementById("provider-badge");

let currentProvider = "anthropic";
let history = [];

const PROVIDER_LABELS = {
  anthropic: { label: "claude-sonnet-4-6", cls: "anthropic" },
  gemini:    { label: "gemini-2.0-flash",  cls: "gemini" },
};

// ── Provider toggle ───────────────────────────────────────────────────────────

document.querySelectorAll(".provider-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    if (btn.dataset.provider === currentProvider) return;
    currentProvider = btn.dataset.provider;
    document.querySelectorAll(".provider-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    const meta = PROVIDER_LABELS[currentProvider];
    providerBadge.textContent = meta.label;
    providerBadge.className = `provider-badge ${meta.cls}`;
    // Reset conversation on provider switch
    history = [];
    messagesEl.innerHTML = "";
    const notice = document.createElement("div");
    notice.className = "msg assistant";
    notice.style.color = "var(--muted)";
    notice.style.fontSize = "12px";
    notice.textContent = `Switched to ${meta.label}. New conversation started.`;
    messagesEl.appendChild(notice);
  });
});

// ── Utilities ─────────────────────────────────────────────────────────────────

function toast(msg, kind = "ok") {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = msg;
  toasts.appendChild(el);
  setTimeout(() => el.remove(), 5000);
}

async function refreshCounts() {
  try {
    const r = await fetch("/tables");
    const data = await r.json();
    for (const row of data) {
      const tile = tiles.querySelector(`[data-table="${row.name}"] .count`);
      if (tile) tile.textContent = row.row_count.toLocaleString();
    }
  } catch (e) {
    console.error("count refresh failed", e);
  }
}

// ── File upload ───────────────────────────────────────────────────────────────

async function uploadFile(table, file) {
  const fd = new FormData();
  fd.append("file", file);
  toast(`Uploading ${file.name} → ${table}…`);
  try {
    const r = await fetch(`/ingest/${table}`, { method: "POST", body: fd });
    const body = await r.json();
    if (!r.ok) { toast(`Error: ${body.detail || r.statusText}`, "err"); return; }
    const { inserted, skipped_duplicates, rejected_rows } = body;
    toast(`${table}: +${inserted} inserted, ${skipped_duplicates} dup, ${rejected_rows} rejected`, "ok");
    refreshCounts();
  } catch (e) {
    toast(`Upload failed: ${e.message}`, "err");
  }
}

function wireDropzone(zone) {
  const table = zone.dataset.table;
  const fileInput = zone.querySelector("input[type=file]");
  fileInput.addEventListener("change", () => {
    if (fileInput.files[0]) uploadFile(table, fileInput.files[0]);
    fileInput.value = "";
  });
  zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("drag"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("drag"));
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("drag");
    if (e.dataTransfer.files[0]) uploadFile(table, e.dataTransfer.files[0]);
  });
}
document.querySelectorAll(".dropzone").forEach(wireDropzone);

// ── Chat ──────────────────────────────────────────────────────────────────────

function addMessage(role) {
  const el = document.createElement("div");
  el.className = `msg ${role}`;
  messagesEl.appendChild(el);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return el;
}

function renderToolPill(container, name, input) {
  const pill = document.createElement("span");
  pill.className = "tool-pill";
  const label = document.createElement("span");
  label.textContent = name;
  pill.appendChild(label);
  if (input && Object.keys(input).length) {
    const code = document.createElement("code");
    const preview = input.query
      ? (input.query.length > 80 ? input.query.slice(0, 77) + "…" : input.query)
      : JSON.stringify(input).slice(0, 80);
    code.textContent = preview;
    pill.appendChild(code);
  }
  container.appendChild(pill);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return pill;
}

async function sendMessage(text) {
  history.push({ role: "user", content: text });
  const userEl = addMessage("user");
  userEl.textContent = text;

  const assistantEl = addMessage("assistant");
  const toolPills = {};
  let currentText = "";
  let textNode = null;

  const appendText = (t) => {
    if (!textNode) { textNode = document.createElement("div"); assistantEl.appendChild(textNode); }
    currentText += t;
    textNode.textContent = currentText;
    messagesEl.scrollTop = messagesEl.scrollHeight;
  };

  // Provider badge inline label
  const badge = document.createElement("span");
  badge.className = `provider-badge ${PROVIDER_LABELS[currentProvider].cls}`;
  badge.style.cssText = "float:right;margin-left:8px;font-size:10px;";
  badge.textContent = PROVIDER_LABELS[currentProvider].label;
  assistantEl.appendChild(badge);

  sendBtn.disabled = true;
  try {
    const res = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: history, provider: currentProvider }),
    });
    if (!res.ok) { assistantEl.textContent = `Error: ${res.status} ${res.statusText}`; return; }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop() || "";
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        let event;
        try { event = JSON.parse(line.slice(6)); } catch { continue; }

        if (event.type === "text") {
          appendText(event.text);
        } else if (event.type === "tool") {
          textNode = null; currentText = "";
          toolPills[event.id] = renderToolPill(assistantEl, event.name, event.input);
        } else if (event.type === "tool_result") {
          const pill = toolPills[event.id];
          if (pill) pill.classList.add(event.ok ? "ok" : "err");
        } else if (event.type === "error") {
          const err = document.createElement("div");
          err.className = "tool-pill err";
          err.textContent = event.message;
          assistantEl.appendChild(err);
        } else if (event.type === "done") {
          if (currentText.trim()) history.push({ role: "assistant", content: currentText });
          refreshCounts();
        }
      }
    }
  } catch (e) {
    assistantEl.textContent = `Stream error: ${e.message}`;
  } finally {
    sendBtn.disabled = false;
  }
}

composer.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  sendMessage(text);
});

input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); composer.requestSubmit(); }
});

refreshCounts();
