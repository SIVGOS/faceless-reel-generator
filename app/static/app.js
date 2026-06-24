"use strict";

// ---- tiny helpers ----
const $ = (sel) => document.querySelector(sel);
const show = (el) => el.classList.remove("hidden");
const hide = (el) => el.classList.add("hidden");

async function api(path, { method = "GET", body } = {}) {
  const opts = { method, headers: {}, credentials: "same-origin" };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  if (res.status === 204) return null;
  let data = null;
  try { data = await res.json(); } catch (_) { /* no body */ }
  if (!res.ok) {
    const detail = (data && data.detail) || res.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

// ---- state ----
let currentProjectId = null;

// ---- auth view ----
let authMode = "login";

function setAuthMode(mode) {
  authMode = mode;
  document.querySelectorAll(".tab").forEach((t) =>
    t.classList.toggle("active", t.dataset.mode === mode)
  );
  $("#auth-submit").textContent = mode === "login" ? "Log in" : "Create account";
  hide($("#auth-error"));
}

document.querySelectorAll(".tab").forEach((tab) =>
  tab.addEventListener("click", () => setAuthMode(tab.dataset.mode))
);

$("#auth-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const username = $("#auth-username").value.trim();
  const password = $("#auth-password").value;
  const path = authMode === "login" ? "/api/auth/login" : "/api/auth/register";
  try {
    const user = await api(path, { method: "POST", body: { username, password } });
    enterWorkspace(user);
  } catch (err) {
    const el = $("#auth-error");
    el.textContent = err.message;
    show(el);
  }
});

// ---- workspace ----
function enterWorkspace(user) {
  $("#user-name").textContent = user.username;
  show($("#user-chip"));
  hide($("#auth-view"));
  show($("#workspace-view"));
  loadProjects();
}

function leaveWorkspace() {
  hide($("#user-chip"));
  hide($("#workspace-view"));
  show($("#auth-view"));
  $("#auth-form").reset();
}

$("#logout-btn").addEventListener("click", async () => {
  await api("/api/auth/logout", { method: "POST" });
  leaveWorkspace();
});

function setStatus(text, kind) {
  const el = $("#status-line");
  el.className = "status " + (kind || "");
  el.textContent = text;
  show(el);
}

$("#generate-btn").addEventListener("click", async () => {
  const prompt = $("#prompt-input").value.trim();
  if (!prompt) { setStatus("Enter a prompt first.", "err"); return; }
  const btn = $("#generate-btn");
  btn.disabled = true;
  setStatus("Generating script with Gemini…", "busy");
  try {
    const data = await api("/api/projects/generate-script", {
      method: "POST", body: { prompt },
    });
    currentProjectId = data.project_id;
    $("#script-input").value = data.generated_script;
    $("#compile-btn").disabled = false;
    setStatus("Script ready. Edit it, then compile.", "ok");
    loadProjects();
  } catch (err) {
    setStatus(err.message, "err");
  } finally {
    btn.disabled = false;
  }
});

$("#compile-btn").addEventListener("click", async () => {
  if (!currentProjectId) return;
  const script = $("#script-input").value.trim();
  if (!script) { setStatus("Script is empty.", "err"); return; }
  const btn = $("#compile-btn");
  btn.disabled = true;
  setStatus("Rendering reel (voice → captions → FFmpeg)… this can take a minute.", "busy");
  try {
    // Persist any manual edits, then compile.
    await api(`/api/projects/${currentProjectId}/script`, {
      method: "PUT", body: { generated_script: script },
    });
    await api(`/api/projects/${currentProjectId}/compile`, { method: "POST" });
    setStatus("Reel compiled. See the gallery.", "ok");
    loadProjects();
  } catch (err) {
    setStatus(err.message, "err");
    loadProjects();
  } finally {
    btn.disabled = false;
  }
});

$("#refresh-btn").addEventListener("click", loadProjects);

// ---- gallery ----
function projectCard(p) {
  const card = document.createElement("div");
  card.className = "card";

  if (p.status === "done") {
    const v = document.createElement("video");
    v.controls = true;
    v.preload = "metadata";
    v.src = `/api/projects/${p.id}/video`;
    card.appendChild(v);
  }

  const prompt = document.createElement("div");
  prompt.className = "prompt";
  prompt.textContent = p.prompt;
  card.appendChild(prompt);

  const meta = document.createElement("div");
  meta.className = "meta";
  const badge = document.createElement("span");
  badge.className = "badge " + p.status;
  badge.textContent = p.status;
  const time = document.createElement("span");
  time.className = "muted";
  time.textContent = new Date(p.timestamp).toLocaleString();
  meta.append(badge, time);
  card.appendChild(meta);

  const actions = document.createElement("div");
  actions.className = "card-actions";
  if (p.status === "done") {
    const dl = document.createElement("a");
    dl.href = `/api/projects/${p.id}/video`;
    dl.setAttribute("download", `reel_${p.id}.mp4`);
    dl.textContent = "Download";
    actions.appendChild(dl);
  }
  const del = document.createElement("button");
  del.textContent = "Delete";
  del.addEventListener("click", async () => {
    await api(`/api/projects/${p.id}`, { method: "DELETE" });
    loadProjects();
  });
  actions.appendChild(del);
  card.appendChild(actions);

  return card;
}

async function loadProjects() {
  const list = $("#gallery-list");
  try {
    const projects = await api("/api/projects");
    list.innerHTML = "";
    if (!projects.length) {
      list.innerHTML = '<p class="muted empty">No projects yet. Generate a script to begin.</p>';
      return;
    }
    projects.forEach((p) => list.appendChild(projectCard(p)));
  } catch (err) {
    list.innerHTML = `<p class="error empty">${err.message}</p>`;
  }
}

// ---- boot: resume session if cookie is valid ----
(async function init() {
  setAuthMode("login");
  try {
    const user = await api("/api/auth/me");
    enterWorkspace(user);
  } catch (_) {
    leaveWorkspace();
  }
})();
