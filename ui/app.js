const $ = (sel) => document.querySelector(sel);
const state = {
  session: { workspace: "", tier: "code", last_model: "qwen3-coder:30b", projects: [] },
  files: [],
  selectedFile: "",
  lastDiff: "",
  tab: "session",
  editor: null,
  compareModels: [],
  busy: false,
  logPath: "",
};

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  const data = await res.json().catch(() => ({ ok: false, error: res.statusText }));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

function toast(text) {
  $("#statusLine").textContent = text;
}

function renderChips(status, mesh) {
  const box = $("#chips");
  box.innerHTML = "";
  const farm = status.farm?.ok;
  addChip(box, farm ? "Farm Brain up" : "Farm Brain down", farm ? "ok" : "down");
  addChip(box, status.vast_active ? "Vast active — no 5090" : "5090 free", status.vast_active ? "warn" : "ok");
  const bc = (mesh && mesh.farm_hosts) || [];
  if (bc.length) {
    const live = bc.filter((n) => n.ok).length;
    addChip(box, `BC-250 ${live}/${bc.length}`, live ? "ok" : "down");
  }
  const ray = mesh && mesh.ray;
  if (ray) {
    addChip(box, ray.head_ok ? "Ray head up" : "Ray head down", ray.head_ok ? "ok" : "down");
  }
  for (const be of Object.values(status.backends || {})) {
    const loaded = (be.running || []).map((r) => r.name).join(", ") || "idle";
    addChip(box, `${be.label}: ${be.ok ? loaded : "down"}`, be.ok ? "ok" : "down");
  }
}

function addChip(box, text, cls) {
  const el = document.createElement("span");
  el.className = `chip ${cls || ""}`;
  el.textContent = text;
  box.appendChild(el);
}

function renderTiers() {
  const burst = $("#burstBtn");
  if (burst) {
    burst.classList.toggle("active", state.session.tier === "burst" && !burst.disabled);
  }
}

function pickerFromStatus(status) {
  const groups = { code: [], chat: [], burst: [] };
  const skip = /embed|nomic|rerank|whisper|tts|clip|moondream/i;
  for (const be of Object.values((status && status.backends) || {})) {
    const role = be.role;
    if (!groups[role]) continue;
    const running = be.running || [];
    for (const m of be.models || []) {
      if (!m.name || skip.test(m.name)) continue;
      const loaded = running.some((r) => (r.name || "").startsWith((m.name || "").split(":")[0]));
      groups[role].push({
        name: m.name,
        loaded,
        gpu: be.gpu,
        ok: be.ok,
        blocked: role === "burst" && !!status.vast_active,
        tier: role,
      });
    }
  }
  return {
    vast_active: !!(status && status.vast_active),
    groups,
    defaults: { code: "qwen3-coder:30b", chat: "qwen3.8:27b" },
  };
}

function renderPicker(picker) {
  const groups = (picker && picker.groups) || {};
  const defaults = (picker && picker.defaults) || {};
  fillSelect(
    $("#codeModel"),
    groups.code || [],
    state.session.code_model || defaults.code || "qwen3-coder:30b",
    "No AMD code models"
  );
  fillSelect(
    $("#chatModel"),
    groups.chat || [],
    state.session.chat_model || defaults.chat || "qwen3.8:27b",
    "No CUDA chat models"
  );
  const burst = $("#burstBtn");
  if (burst) {
    const blocked = !!(picker && picker.vast_active);
    burst.disabled = blocked;
    burst.title = blocked ? "Blocked while Vast is live" : "Use the tower 5090 (burst only)";
    burst.classList.toggle("active", state.session.tier === "burst" && !blocked);
  }
  renderComparePicks(picker);
}

function renderComparePicks(picker) {
  const box = $("#comparePicks");
  if (!box) return;
  const groups = (picker && picker.groups) || {};
  const rows = []
    .concat(groups.code || [], groups.chat || [], (picker && picker.vast_active ? [] : groups.burst || []))
    .filter((r) => r && r.name);
  const seen = new Set();
  const unique = [];
  for (const row of rows) {
    const key = `${row.tier}:${row.name}`;
    if (seen.has(key)) continue;
    seen.add(key);
    unique.push(row);
  }
  if (!state.compareModels.length) {
    const seed = [state.session.chat_model, state.session.code_model].filter(Boolean);
    for (const name of seed) {
      const hit = unique.find((r) => r.name === name);
      if (hit && !state.compareModels.includes(`${hit.tier}:${hit.name}`)) {
        state.compareModels.push(`${hit.tier}:${hit.name}`);
      }
    }
    if (state.compareModels.length < 2) {
      for (const row of unique) {
        const key = `${row.tier}:${row.name}`;
        if (!state.compareModels.includes(key)) state.compareModels.push(key);
        if (state.compareModels.length >= 2) break;
      }
    }
    state.compareModels = state.compareModels.slice(0, 3);
  }
  box.innerHTML = "";
  const note = document.createElement("span");
  note.className = "status-line";
  note.textContent = "Compare (max 3):";
  box.appendChild(note);
  for (const row of unique) {
    const key = `${row.tier}:${row.name}`;
    const label = document.createElement("label");
    label.className = "compare-pick";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.value = key;
    cb.checked = state.compareModels.includes(key);
    cb.addEventListener("change", () => {
      if (cb.checked) {
        if (state.compareModels.length >= 3) {
          cb.checked = false;
          toast("Compare allows at most 3 models.");
          return;
        }
        state.compareModels.push(key);
      } else {
        state.compareModels = state.compareModels.filter((k) => k !== key);
      }
    });
    label.appendChild(cb);
    label.appendChild(document.createTextNode(` ${row.name}`));
    box.appendChild(label);
  }
}

function fillSelect(sel, rows, current, emptyText) {
  if (!sel) return;
  if (document.activeElement === sel) return;
  const names = rows.map((r) => r.name);
  const chosen = names.includes(current) ? current : (rows[0] && rows[0].name) || "";
  sel.innerHTML = "";
  if (!rows.length) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = emptyText;
    sel.appendChild(opt);
    sel.disabled = true;
    return;
  }
  sel.disabled = false;
  for (const row of rows) {
    const opt = document.createElement("option");
    opt.value = row.name;
    const pulse = row.loaded ? "● " : "";
    opt.textContent = `${pulse}${row.name}`;
    if (row.name === chosen) opt.selected = true;
    sel.appendChild(opt);
  }
}

function renderProjects() {
  const box = $("#projects");
  box.innerHTML = "";
  const rows = state.session.projects || [];
  if (!rows.length) {
    box.innerHTML = "<p class='status-line'>Open a folder to start a project.</p>";
    return;
  }
  for (const row of rows) {
    const el = document.createElement("div");
    el.className = "project" + (row.path === state.session.workspace ? " active" : "");
    el.dataset.path = row.path;
    el.innerHTML = `<strong>${row.name || row.path.split(/\\|\//).pop()}</strong><small>${row.tier} · ${row.model}</small><small>${row.path}</small>`;
    el.addEventListener("click", async () => {
      await api("/api/open", { method: "POST", body: JSON.stringify({ path: row.path }) });
      await refreshAll();
    });
    el.addEventListener("dragover", (e) => {
      e.preventDefault();
      el.classList.add("drop-over");
    });
    el.addEventListener("dragleave", () => el.classList.remove("drop-over"));
    el.addEventListener("drop", async (e) => {
      e.preventDefault();
      el.classList.remove("drop-over");
      const raw = e.dataTransfer.getData("application/json");
      if (!raw) return;
      const payload = JSON.parse(raw);
      await api("/api/projects", {
        method: "POST",
        body: JSON.stringify({ path: row.path, tier: payload.tier, model: payload.model }),
      });
      toast(`Assigned ${payload.model} → ${row.name || row.path}`);
      await refreshAll();
    });
    box.appendChild(el);
  }
}

function renderFiles(entries) {
  const box = $("#files");
  box.innerHTML = "";
  for (const entry of entries || []) {
    const btn = document.createElement("button");
    btn.className = "file" + (entry.path === state.selectedFile ? " active" : "");
    btn.textContent = (entry.kind === "dir" ? "▸ " : "") + entry.name;
    btn.addEventListener("click", async () => {
      if (entry.kind === "dir") {
        const data = await api(`/api/files?path=${encodeURIComponent(entry.path)}`);
        renderFiles(data.entries);
        return;
      }
      state.selectedFile = entry.path;
      await openFile(entry.path);
    });
    box.appendChild(btn);
  }
}

async function openFile(rel) {
  const data = await api(`/api/file?path=${encodeURIComponent(rel)}`);
  setTab("file");
  ensureEditor();
  if (state.editor) {
    const model = monaco.editor.createModel(data.text, languageFor(rel), monaco.Uri.parse("file:///" + rel));
    state.editor.setModel(model);
  } else {
    const area = $("#plainEditor");
    if (area) area.value = data.text;
  }
  renderFiles(state.files);
}

function languageFor(path) {
  const ext = (path.split(".").pop() || "").toLowerCase();
  return {
    py: "python",
    js: "javascript",
    ts: "typescript",
    json: "json",
    md: "markdown",
    css: "css",
    html: "html",
    toml: "ini",
    yml: "yaml",
    yaml: "yaml",
    ps1: "powershell",
    cjs: "javascript",
  }[ext] || "plaintext";
}

function ensureEditor() {
  const host = $("#editor");
  if (window.monaco && !state.editor) {
    state.editor = monaco.editor.create(host, {
      theme: "vs-dark",
      automaticLayout: true,
      fontSize: 13,
      minimap: { enabled: false },
      wordWrap: "on",
    });
    return;
  }
  if (!window.monaco && !host.querySelector("textarea")) {
    const area = document.createElement("textarea");
    area.id = "plainEditor";
    area.style.cssText = "width:100%;height:100%;background:#140f0c;color:#f4e6d4;border:0;padding:12px;font-family:var(--mono);font-size:13px;";
    host.appendChild(area);
  }
}

function setTab(name) {
  state.tab = name;
  $("#session").style.display = name === "session" ? "block" : "none";
  $("#log").style.display = name === "log" ? "block" : "none";
  $("#diff").style.display = name === "diff" ? "block" : "none";
  $("#editor").style.display = name === "file" ? "block" : "none";
  document.querySelectorAll(".center-tabs .btn").forEach((b) => {
    b.classList.toggle("primary", b.dataset.tab === name);
  });
  if (name === "log") refreshLog().catch((err) => toast(String(err.message || err)));
}

function addMessage(role, text, meta = "") {
  const el = document.createElement("div");
  el.className = `msg ${role}`;
  el.innerHTML = `${meta ? `<div class="meta">${escapeHtml(meta)}</div>` : ""}<div class="body">${escapeHtml(text)}</div>`;
  $("#session").appendChild(el);
  $("#session").scrollTop = $("#session").scrollHeight;
  return el;
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function renderDiff(text) {
  state.lastDiff = text;
  const pre = document.createElement("pre");
  pre.className = "diff";
  pre.innerHTML = text
    .split("\n")
    .map((line) => {
      const cls = line.startsWith("+") && !line.startsWith("+++") ? "add" : line.startsWith("-") && !line.startsWith("---") ? "del" : "";
      return `<span class="${cls}">${escapeHtml(line)}</span>`;
    })
    .join("\n");
  $("#diff").innerHTML = "";
  $("#diff").appendChild(pre);
  setTab("diff");
}

function renderMesh(mesh) {
  const box = $("#mesh");
  box.innerHTML = "";
  if (!mesh || mesh.error) {
    box.innerHTML = `<p class="status-line">${escapeHtml((mesh && mesh.error) || "Mesh unavailable.")}</p>`;
    return;
  }
  box.appendChild(renderRayCard(mesh.ray || {}));
  box.appendChild(renderOntologyCard(mesh.ontology || {}));
  const nodes = mesh.nodes || [];
  if (!nodes.length) {
    const empty = document.createElement("p");
    empty.className = "status-line";
    empty.textContent = "No hosts in live inventory yet.";
    box.appendChild(empty);
  }
  for (const node of nodes) {
    const farm = node.kind === "bc250" || node.role === "farm";
    const assignable = !farm && (node.role === "code" || node.role === "chat" || node.role === "burst");
    const el = document.createElement("div");
    el.className = "node" + (node.ok ? "" : " down") + (farm ? " farm" : "");
    const pills = (node.models || [])
      .map((m) => {
        const loaded = (node.running || []).some((r) => (r.name || "").startsWith((m.name || "").split(":")[0]));
        const tier = node.role === "code" ? "code" : node.role === "burst" ? "burst" : "chat";
        const drag = assignable ? ` draggable="true" data-model="${escapeHtml(m.name)}" data-tier="${tier}"` : "";
        return `<span class="model-pill ${loaded ? "loaded" : ""} ${assignable ? "" : "locked"}"${drag}>${escapeHtml(m.name)}</span>`;
      })
      .join("");
    const badges = farm
      ? `<div class="badges">
          <span class="badge ${node.ray ? "on" : ""}">${node.ray ? "Ray" : "Ray off"}</span>
          <span class="badge ${node.ollama ? "on" : ""}">${node.ollama ? "Ollama" : "Ollama off"}</span>
          ${node.posture ? `<span class="badge">${escapeHtml(node.posture)}</span>` : ""}
        </div>`
      : "";
    const sub = farm
      ? `${escapeHtml(node.detail || node.id)} · ${escapeHtml(node.base || node.lan_ip || "")}`
      : `${escapeHtml(node.base)}${node.blocked ? " · blocked (Vast)" : ""}`;
    el.innerHTML = `<h3>${escapeHtml(node.label)} · ${escapeHtml(node.gpu)}</h3>
      <small>${sub}</small>
      ${badges}
      <div>${pills || "<small>no tags</small>"}</div>`;
    box.appendChild(el);
  }
  box.querySelectorAll(".model-pill[draggable='true']").forEach((pill) => {
    pill.addEventListener("dragstart", (e) => {
      e.dataTransfer.setData(
        "application/json",
        JSON.stringify({ model: pill.dataset.model, tier: pill.dataset.tier })
      );
    });
    pill.addEventListener("click", async () => {
      await api("/api/use", {
        method: "POST",
        body: JSON.stringify({ tier: pill.dataset.tier, model: pill.dataset.model }),
      });
      await refreshAll();
    });
  });
  box.querySelectorAll("[data-launch]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const out = await api("/api/launch", { method: "POST", body: JSON.stringify({ target: btn.dataset.launch }) });
      toast(out.url || out.path || btn.dataset.launch);
    });
  });
}

function renderRayCard(ray) {
  const el = document.createElement("div");
  el.className = "node mesh-card" + (ray.ok || ray.head_ok ? "" : " down");
  const jobs = (ray.jobs || []).slice(0, 3);
  const extra = Math.max(0, (ray.job_count || 0) - jobs.length);
  const jobLines = jobs.length
    ? jobs
        .map((j) => `<li><span class="badge ${String(j.status).toUpperCase() === "RUNNING" ? "on" : ""}">${escapeHtml(j.status)}</span> ${escapeHtml(j.name || j.id)}</li>`)
        .join("") + (extra ? `<li>+${extra} more on the Ray Dashboard</li>` : "")
    : "<li>No recent jobs in the live Ray API.</li>";
  const running = ray.running ? `${ray.running} running` : "idle";
  el.innerHTML = `<h3>Ray · Farm-Ontology head</h3>
    <small>${ray.head_ok ? "head up" : "head down"} · ${escapeHtml(running)}${ray.bc250_present ? " · BC-250 in cluster" : ""}</small>
    <ul class="job-list">${jobLines}</ul>
    <div class="mesh-actions">
      <button type="button" class="btn" data-launch="ray">Ray Dashboard</button>
      <button type="button" class="btn" data-launch="compute">Farm Compute</button>
    </div>`;
  return el;
}

function renderOntologyCard(ont) {
  const el = document.createElement("div");
  el.className = "node mesh-card" + (ont.ok ? "" : " down");
  const entities = ont.entities != null ? `${ont.entities} entities` : "no snapshot";
  const actors = ont.ray_actors != null ? `${ont.ray_actors} Ray actor handle${ont.ray_actors === 1 ? "" : "s"}` : "actors unknown";
  el.innerHTML = `<h3>Ontology · SQLite SSOT</h3>
    <small>${ont.ok ? "API up" : "API down"} · ${escapeHtml(entities)} · ${escapeHtml(actors)}</small>
    <div class="mesh-actions">
      <button type="button" class="btn" data-launch="ontology">Ontology docs</button>
      <button type="button" class="btn" data-launch="ray">Ray jobs</button>
    </div>`;
  return el;
}

function renderRecipes(recipes) {
  const box = $("#recipes");
  box.innerHTML = "";
  for (const row of recipes || []) {
    const btn = document.createElement("button");
    btn.className = "recipe";
    btn.textContent = row.label;
    btn.addEventListener("click", () => runRecipe(row.id));
    box.appendChild(btn);
  }
}

function renderLinks(links) {
  const box = $("#links");
  box.innerHTML = "";
  for (const row of links || []) {
    const btn = document.createElement("button");
    btn.className = "link";
    btn.textContent = row.label;
    btn.addEventListener("click", async () => {
      const out = await api("/api/launch", { method: "POST", body: JSON.stringify({ target: row.id }) });
      toast(out.url || out.path || row.label);
    });
    box.appendChild(btn);
  }
}

async function refreshAll() {
  const desk = await api("/api/desk");
  state.session = desk.state;
  state.files = desk.files || [];
  if (desk.log_path) state.logPath = desk.log_path;
  renderTiers();
  renderProjects();
  renderFiles(state.files);
  renderRecipes(desk.recipes);
  renderLinks(desk.links);
  toast(`edit ${desk.state.code_model || ""} · ask ${desk.state.chat_model || ""} · ${desk.state.workspace || "no workspace"}`);
  const [status, mesh] = await Promise.all([api("/api/status"), api("/api/mesh")]);
  renderChips(status, mesh);
  renderPicker(pickerFromStatus(status));
  renderMesh(mesh);
  await refreshLog();
}

function renderLog(data) {
  const box = $("#log");
  if (!box) return;
  const path = (data && data.path) || state.logPath || "%LOCALAPPDATA%\\Forge\\sessions.jsonl";
  const turns = (data && data.turns) || [];
  box.innerHTML = "";
  const cap = document.createElement("p");
  cap.className = "log-path";
  cap.textContent = path;
  box.appendChild(cap);
  if (!turns.length) {
    const empty = document.createElement("p");
    empty.className = "status-line";
    empty.textContent = "No turns yet. Ask or Edit from the desk or CLI — both append to this file.";
    box.appendChild(empty);
    return;
  }
  for (const row of turns) {
    const el = document.createElement("div");
    el.className = "log-row";
    const bits = [row.at, row.kind, row.model, row.backend, row.gpu].filter(Boolean);
    if (row.files && row.files.length) bits.push(row.files.join(", "));
    if (row.applied) bits.push("applied");
    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent = bits.join(" · ");
    const prompt = document.createElement("div");
    prompt.className = "prompt";
    prompt.textContent = row.prompt || "(no prompt stored)";
    el.appendChild(meta);
    el.appendChild(prompt);
    box.appendChild(el);
  }
}

async function refreshLog() {
  try {
    const data = await api("/api/log?limit=80");
    if (data.path) state.logPath = data.path;
    renderLog(data);
  } catch (err) {
    const box = $("#log");
    if (!box) return;
    box.innerHTML = `<p class="status-line">${escapeHtml(String(err.message || err))}</p>`;
  }
}

function selectedFiles() {
  return state.selectedFile ? [state.selectedFile] : [];
}

function parseSseBuffer(buf) {
  const frames = buf.split("\n\n");
  const rest = frames.pop() || "";
  const events = [];
  for (const frame of frames) {
    const line = frame.split("\n").find((l) => l.startsWith("data:"));
    if (!line) continue;
    const raw = line.replace(/^data:\s?/, "");
    try {
      events.push(JSON.parse(raw));
    } catch {
      events.push({ error: raw });
    }
  }
  return { events, rest };
}

async function readSse(res, onEvent) {
  if (!res.body || !res.body.getReader) {
    const text = await res.text();
    const parsed = parseSseBuffer(text.endsWith("\n\n") ? text : text + "\n\n");
    for (const ev of parsed.events) onEvent(ev);
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const parsed = parseSseBuffer(buf);
    buf = parsed.rest;
    for (const ev of parsed.events) onEvent(ev);
  }
  if (buf.trim()) {
    const parsed = parseSseBuffer(buf + "\n\n");
    for (const ev of parsed.events) onEvent(ev);
  }
}

async function send(kind) {
  const prompt = $("#prompt").value.trim();
  if (!prompt) return;
  const files = selectedFiles();
  addMessage("user", prompt, files.length ? files.join(", ") : "no file context");
  const bubble = addMessage("assistant", "", "streaming…");
  bubble.classList.add("streaming");
  const bodyEl = bubble.querySelector(".body");
  const metaEl = bubble.querySelector(".meta");
  setBusy(true);
  toast(kind === "edit" ? "Streaming coder diff…" : "Streaming local Qwen…");
  let text = "";
  try {
    const res = await fetch(kind === "edit" ? "/api/edit/stream" : "/api/ask/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt,
        files,
        tier: kind === "edit" ? "code" : "chat",
        model: kind === "edit" ? $("#codeModel").value || undefined : $("#chatModel").value || undefined,
      }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({ error: res.statusText }));
      throw new Error(data.error || res.statusText);
    }
    await readSse(res, (ev) => {
      if (ev.meta) {
        const meta = `${ev.meta.model || ""} · ${ev.meta.backend || ""} · ${ev.meta.gpu || ""}`.trim();
        if (metaEl && meta) metaEl.textContent = meta;
        toast(meta || "streaming…");
      }
      if (ev.delta) {
        text += ev.delta;
        if (bodyEl) bodyEl.textContent = text;
        $("#session").scrollTop = $("#session").scrollHeight;
      }
      if (ev.error) throw new Error(ev.error);
      if (ev.done && ev.text && !text) text = ev.text;
      if (ev.done && ev.model && metaEl) {
        metaEl.textContent = `${ev.model} · ${ev.backend || ""} · ${ev.gpu || ""}`;
      }
    });
    if (bodyEl) bodyEl.textContent = text;
    if (kind === "edit") renderDiff(text);
    toast(metaEl ? metaEl.textContent : "done");
    await refreshLog();
  } catch (err) {
    if (bodyEl && !bodyEl.textContent) bodyEl.textContent = String(err.message || err);
    else addMessage("assistant", String(err.message || err), "error");
    if (metaEl) metaEl.textContent = "error";
    toast(String(err.message || err));
  } finally {
    bubble.classList.remove("streaming");
    setBusy(false);
  }
}

function setBusy(busy) {
  state.busy = !!busy;
  ["askBtn", "editBtn", "compareAskBtn", "compareEditBtn"].forEach((id) => {
    const el = $("#" + id);
    if (el) el.disabled = busy;
  });
}

function selectedCompareModels() {
  return (state.compareModels || []).slice(0, 3).map((key) => {
    const [tier, ...rest] = key.split(":");
    return { tier, model: rest.join(":") };
  });
}

async function sendCompare(kind) {
  const prompt = $("#prompt").value.trim();
  if (!prompt) return;
  const files = selectedFiles();
  const models = selectedCompareModels();
  if (models.length < 2) return toast("Pick at least two live models to compare.");
  addMessage("user", prompt, `compare ${kind} · ${models.map((m) => m.model).join(", ")}`);
  setBusy(true);
  toast(`Comparing ${models.length} models; AMD 30B will judge…`);
  try {
    const data = await api("/api/compare", {
      method: "POST",
      body: JSON.stringify({ kind, prompt, files, models }),
    });
    const judge = data.judge || {};
    addMessage(
      "assistant",
      `${judge.reason || ""}\n\n${data.text || ""}`,
      `WINNER ${judge.winner} · ${judge.pick_model || data.model} · judged by ${judge.model || "qwen3-coder:30b"}`
    );
    for (const row of data.candidates || []) {
      addMessage(
        "assistant",
        row.ok ? row.text || "" : row.error || "failed",
        `${row.index}) ${row.ok ? "ok" : "fail"} · ${row.model} · ${row.backend || ""}`
      );
    }
    if (kind === "edit" && data.text) renderDiff(data.text);
    toast(`Winner: ${judge.pick_model || ""} — not applied`);
    await refreshLog();
  } catch (err) {
    addMessage("assistant", String(err.message || err), "error");
    toast(String(err.message || err));
  } finally {
    setBusy(false);
  }
}

async function applyDiff() {
  if (!state.lastDiff) return toast("No diff to apply");
  const confirmProtected = /farm-brain/i.test(state.session.workspace || "")
    ? window.confirm("This workspace is farm-brain. Apply anyway? QC gate still applies.")
    : false;
  try {
    const out = await api("/api/apply", {
      method: "POST",
      body: JSON.stringify({ diff: state.lastDiff, confirm_protected: confirmProtected }),
    });
    toast("Applied " + (out.changed || []).join(", "));
    await refreshAll();
    await refreshLog();
  } catch (err) {
    toast(String(err.message || err));
  }
}

async function runRecipe(id) {
  const extra = $("#prompt").value.trim();
  $("#askBtn").disabled = true;
  try {
    const data = await api(`/api/recipes/${id}/run`, {
      method: "POST",
      body: JSON.stringify({ prompt: extra, files: selectedFiles() }),
    });
    if (data.text) {
      addMessage("assistant", data.text, `${data.model || id} · recipe`);
      if (data.kind === "edit") renderDiff(data.text);
      await refreshLog();
    } else {
      toast(data.url || data.path || id);
    }
  } catch (err) {
    toast(String(err.message || err));
  } finally {
    $("#askBtn").disabled = false;
  }
}

function bind() {
  $("#codeModel").addEventListener("change", async () => {
    const model = $("#codeModel").value;
    if (!model) return;
    await api("/api/use", { method: "POST", body: JSON.stringify({ tier: "code", model }) });
    await refreshAll();
  });
  $("#chatModel").addEventListener("change", async () => {
    const model = $("#chatModel").value;
    if (!model) return;
    await api("/api/use", { method: "POST", body: JSON.stringify({ tier: "chat", model }) });
    await refreshAll();
  });
  $("#burstBtn").addEventListener("click", async () => {
    try {
      await api("/api/use", { method: "POST", body: JSON.stringify({ tier: "burst" }) });
    } catch (err) {
      toast(String(err.message || err));
    }
    await refreshAll();
  });
  $("#askBtn").addEventListener("click", () => send("ask"));
  $("#editBtn").addEventListener("click", () => send("edit"));
  $("#compareAskBtn").addEventListener("click", () => sendCompare("ask"));
  $("#compareEditBtn").addEventListener("click", () => sendCompare("edit"));
  $("#applyBtn").addEventListener("click", applyDiff);
  $("#rejectBtn").addEventListener("click", () => {
    state.lastDiff = "";
    $("#diff").innerHTML = "";
    setTab("session");
  });
  $("#openBtn").addEventListener("click", async () => {
    const path = window.prompt("Workspace path", state.session.workspace || "C:\\Users\\jlay\\Grok\\forge");
    if (!path) return;
    await api("/api/open", { method: "POST", body: JSON.stringify({ path }) });
    await refreshAll();
  });
  document.querySelectorAll(".center-tabs .btn").forEach((btn) => {
    btn.addEventListener("click", () => setTab(btn.dataset.tab));
  });
  $("#prompt").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) send("ask");
  });
}

window.addEventListener("load", async () => {
  bind();
  try {
    await refreshAll();
  } catch (err) {
    toast(String(err.message || err));
  }
  setInterval(() => {
    if (state.busy) return;
    refreshAll().catch((err) => toast(String(err.message || err)));
  }, 20000);
});
