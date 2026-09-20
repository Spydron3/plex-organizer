const $ = (sel) => document.querySelector(sel);

async function api(path, options = {}) {
  const resp = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${resp.status}`);
  }
  return resp.status === 204 ? null : resp.json();
}

let currentPlanId = null;

// ---------- Settings ----------

async function loadTvdbStatus() {
  const data = await api("/api/settings/tvdb-key");
  const el = $("#tvdb-status");
  el.textContent = data.configured ? "Key configured" : "No key set — matches will be filename-only";
  el.className = "status " + (data.configured ? "ok" : "warn");
}

$("#save-key-btn").addEventListener("click", async () => {
  const value = $("#tvdb-key").value.trim();
  await api("/api/settings/tvdb-key", { method: "POST", body: JSON.stringify({ value }) });
  $("#tvdb-key").value = "";
  await loadTvdbStatus();
});

$("#save-pin-btn").addEventListener("click", async () => {
  const value = $("#tvdb-pin").value.trim();
  await api("/api/settings/tvdb-pin", { method: "POST", body: JSON.stringify({ value }) });
  $("#tvdb-pin").value = "";
});

// ---------- Libraries ----------

async function loadLibraries() {
  const libraries = await api("/api/libraries");
  const tbody = $("#libraries-table tbody");
  tbody.innerHTML = "";
  for (const lib of libraries) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="mono">${escapeHtml(lib.path)}</td>
      <td>${lib.type}</td>
      <td>
        <button data-scan="${lib.id}">Scan</button>
        <button data-remove="${lib.id}" class="danger">Remove</button>
      </td>`;
    tbody.appendChild(tr);
  }
}

$("#add-library-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const path = $("#new-path").value.trim();
  const type = $("#new-type").value;
  try {
    await api("/api/libraries", { method: "POST", body: JSON.stringify({ path, type }) });
    $("#new-path").value = "";
    await loadLibraries();
  } catch (err) {
    alert(err.message);
  }
});

$("#libraries-table").addEventListener("click", async (e) => {
  const scanId = e.target.getAttribute("data-scan");
  const removeId = e.target.getAttribute("data-remove");
  if (scanId) {
    e.target.disabled = true;
    e.target.textContent = "Scanning…";
    try {
      const plan = await api(`/api/libraries/${scanId}/scan`, { method: "POST" });
      await openPlan(plan.id);
    } catch (err) {
      alert(err.message);
    } finally {
      e.target.disabled = false;
      e.target.textContent = "Scan";
    }
  } else if (removeId) {
    if (!confirm("Remove this library from the app? Files on disk are not touched.")) return;
    await api(`/api/libraries/${removeId}`, { method: "DELETE" });
    await loadLibraries();
  }
});

// ---------- Folder browser ----------

let browsePath = null;

async function openBrowser() {
  const seed = $("#new-path").value.trim();
  browsePath = seed || null;
  $("#browse-modal").hidden = false;
  await renderBrowser();
}

function closeBrowser() {
  $("#browse-modal").hidden = true;
}

async function renderBrowser() {
  const list = $("#browse-list");
  list.innerHTML = `<div class="browse-entry empty">Loading…</div>`;
  let data;
  try {
    const qs = browsePath ? `?path=${encodeURIComponent(browsePath)}` : "";
    data = await api(`/api/browse${qs}`);
  } catch (err) {
    list.innerHTML = `<div class="browse-entry empty">${escapeHtml(err.message)}</div>`;
    return;
  }
  browsePath = data.path;
  $("#browse-current").textContent = data.path;

  list.innerHTML = "";
  if (data.parent) {
    const up = document.createElement("div");
    up.className = "browse-entry up";
    up.textContent = ".. (up)";
    up.addEventListener("click", () => {
      browsePath = data.parent;
      renderBrowser();
    });
    list.appendChild(up);
  }
  if (data.dirs.length === 0) {
    const empty = document.createElement("div");
    empty.className = "browse-entry empty";
    empty.textContent = "(no subfolders)";
    list.appendChild(empty);
  }
  for (const name of data.dirs) {
    const row = document.createElement("div");
    row.className = "browse-entry";
    row.textContent = name;
    row.addEventListener("click", () => {
      browsePath = data.path.endsWith("/") ? data.path + name : `${data.path}/${name}`;
      renderBrowser();
    });
    list.appendChild(row);
  }
}

$("#browse-btn").addEventListener("click", openBrowser);
$("#browse-cancel").addEventListener("click", closeBrowser);
$("#browse-modal").addEventListener("click", (e) => {
  if (e.target.id === "browse-modal") closeBrowser();
});
$("#browse-select").addEventListener("click", () => {
  $("#new-path").value = browsePath;
  closeBrowser();
});

// ---------- Plan ----------

function badge(text, cls) {
  return `<span class="badge ${cls}">${escapeHtml(text)}</span>`;
}

async function openPlan(planId) {
  currentPlanId = planId;
  const data = await api(`/api/plans/${planId}`);
  renderPlan(data);
  $("#plan-section").hidden = false;
  $("#plan-section").scrollIntoView({ behavior: "smooth" });
  await loadHistory();
}

function renderPlan(data) {
  const { plan, library, items } = data;
  const statusLabel = { executed: "(executed)", cancelled: "(declined)" }[plan.status] || "(dry run)";
  $("#plan-status").textContent = statusLabel;
  $("#plan-summary").textContent =
    `${library.path} — ${items.length} change(s) proposed, ${plan.skipped_up_to_date} already correctly named.`;

  const tbody = $("#plan-table tbody");
  tbody.innerHTML = "";
  for (const item of items) {
    const tr = document.createElement("tr");
    const disabled = plan.status !== "pending" ? "disabled" : "";
    const checked = item.status !== "skip" ? "checked" : "";
    tr.innerHTML = `
      <td><input type="checkbox" data-item="${item.id}" ${checked} ${disabled} /></td>
      <td class="mono">${escapeHtml(item.source_path)}</td>
      <td class="mono">${escapeHtml(item.target_path || "(unresolved)")}</td>
      <td>${item.matched ? badge("matched", "matched") : badge("unmatched", "unmatched")}</td>
      <td>${badge(item.status, item.status)}</td>`;
    tbody.appendChild(tr);
  }

  const locked = plan.status !== "pending";
  $("#execute-plan-btn").disabled = locked;
  $("#decline-plan-btn").disabled = locked;
  $("#execute-result").textContent = "";
}

$("#plan-table").addEventListener("change", async (e) => {
  const itemId = e.target.getAttribute("data-item");
  if (!itemId) return;
  const status = e.target.checked ? "pending" : "skip";
  await api(`/api/plans/${currentPlanId}/items/${itemId}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
});

$("#execute-plan-btn").addEventListener("click", async () => {
  if (!confirm("This will move and rename files on disk according to the plan above. Continue?")) return;
  const btn = $("#execute-plan-btn");
  btn.disabled = true;
  btn.textContent = "Executing…";
  try {
    const result = await api(`/api/plans/${currentPlanId}/execute`, { method: "POST" });
    $("#execute-result").textContent =
      `Done: ${result.done}, skipped: ${result.skipped}, failed: ${result.failed}`;
    $("#execute-result").className = "status " + (result.failed ? "warn" : "ok");
    const data = await api(`/api/plans/${currentPlanId}`);
    renderPlan(data);
  } catch (err) {
    alert(err.message);
  } finally {
    btn.textContent = "Accept & Execute";
  }
  await loadHistory();
});

$("#decline-plan-btn").addEventListener("click", async () => {
  if (!confirm("Decline this plan? No files will be changed and this plan will be closed.")) return;
  try {
    await api(`/api/plans/${currentPlanId}/cancel`, { method: "POST" });
    const data = await api(`/api/plans/${currentPlanId}`);
    renderPlan(data);
  } catch (err) {
    alert(err.message);
  }
  await loadHistory();
});

// ---------- History ----------

async function loadHistory() {
  const plans = await api("/api/plans");
  const libraries = await api("/api/libraries");
  const libById = Object.fromEntries(libraries.map((l) => [l.id, l]));
  const tbody = $("#history-table tbody");
  tbody.innerHTML = "";
  const badgeClass = { executed: "done", cancelled: "skip", pending: "pending" };
  for (const plan of plans) {
    const lib = libById[plan.library_id];
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${plan.id}</td>
      <td class="mono">${lib ? escapeHtml(lib.path) : plan.library_id}</td>
      <td>${new Date(plan.created_at + "Z").toLocaleString()}</td>
      <td>${badge(plan.status, badgeClass[plan.status] || "pending")}</td>
      <td><button data-open="${plan.id}">Open</button></td>`;
    tbody.appendChild(tr);
  }
}

$("#history-table").addEventListener("click", async (e) => {
  const id = e.target.getAttribute("data-open");
  if (id) await openPlan(id);
});

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// ---------- Init ----------

loadTvdbStatus();
loadLibraries();
loadHistory();
