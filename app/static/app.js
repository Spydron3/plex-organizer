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
let LANGUAGES = [];
let PREFERRED_LANGUAGES = [];

async function loadLanguages() {
  try {
    LANGUAGES = await api("/api/settings/languages");
  } catch {
    LANGUAGES = [];
  }
  renderLanguageMultiSelect();
}

async function loadPreferredLanguages() {
  try {
    const data = await api("/api/settings/preferred-languages");
    PREFERRED_LANGUAGES = data.languages || [];
  } catch {
    PREFERRED_LANGUAGES = [];
  }
  renderLanguageMultiSelect();
}

// PREFERRED_LANGUAGES is the source of truth; the <select> only ever shows a
// filtered subset, so selections on hidden options must not be lost when the
// filter changes — the select's `change` handler keeps PREFERRED_LANGUAGES in
// sync with whatever's currently visible, leaving hidden entries untouched.
function renderLanguageMultiSelect() {
  const select = $("#preferred-languages");
  const filter = $("#language-filter").value.trim().toLowerCase();
  const list = filter ? LANGUAGES.filter((l) => l.name.toLowerCase().includes(filter)) : LANGUAGES;
  select.innerHTML = list
    .map(
      (l) =>
        `<option value="${l.id}" ${PREFERRED_LANGUAGES.includes(l.id) ? "selected" : ""}>${escapeHtml(l.name)}</option>`
    )
    .join("");
}

$("#language-filter").addEventListener("input", renderLanguageMultiSelect);

$("#preferred-languages").addEventListener("change", () => {
  const select = $("#preferred-languages");
  const renderedIds = Array.from(select.options).map((o) => o.value);
  const selectedNow = new Set(Array.from(select.selectedOptions).map((o) => o.value));
  PREFERRED_LANGUAGES = PREFERRED_LANGUAGES.filter((id) => !renderedIds.includes(id) || selectedNow.has(id));
  for (const id of selectedNow) {
    if (!PREFERRED_LANGUAGES.includes(id)) PREFERRED_LANGUAGES.push(id);
  }
});

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
  await loadLanguages();
});

$("#save-pin-btn").addEventListener("click", async () => {
  const value = $("#tvdb-pin").value.trim();
  await api("/api/settings/tvdb-pin", { method: "POST", body: JSON.stringify({ value }) });
  $("#tvdb-pin").value = "";
});

$("#save-languages-btn").addEventListener("click", async () => {
  const data = await api("/api/settings/preferred-languages", {
    method: "POST",
    body: JSON.stringify({ languages: PREFERRED_LANGUAGES }),
  });
  PREFERRED_LANGUAGES = data.languages || [];
  const status = $("#languages-status");
  status.textContent = PREFERRED_LANGUAGES.length ? `Saved (${PREFERRED_LANGUAGES.length})` : "Saved (none)";
  status.className = "status ok";
});

$("#settings-btn").addEventListener("click", () => {
  $("#settings-modal").hidden = false;
  $("#language-filter").value = "";
  renderLanguageMultiSelect();
});
$("#settings-close").addEventListener("click", () => {
  $("#settings-modal").hidden = true;
});
$("#settings-modal").addEventListener("click", (e) => {
  if (e.target.id === "settings-modal") $("#settings-modal").hidden = true;
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
      <td id="lib-actions-${lib.id}">
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
    await startScan(scanId);
  } else if (removeId) {
    if (!confirm("Remove this library from the app? Files on disk are not touched.")) return;
    await api(`/api/libraries/${removeId}`, { method: "DELETE" });
    await loadLibraries();
  }
});

async function startScan(libraryId) {
  const cell = document.getElementById(`lib-actions-${libraryId}`);
  cell.innerHTML = `
    <progress id="scan-bar-${libraryId}" value="0" max="1"></progress>
    <span id="scan-label-${libraryId}" class="hint">Starting…</span>`;

  try {
    await api(`/api/libraries/${libraryId}/scan`, { method: "POST" });
  } catch (err) {
    alert(err.message);
    await loadLibraries();
    return;
  }

  pollScan(libraryId);
}

async function pollScan(libraryId) {
  let state;
  try {
    state = await api(`/api/libraries/${libraryId}/scan-progress`);
  } catch (err) {
    alert(err.message);
    await loadLibraries();
    return;
  }

  const bar = document.getElementById(`scan-bar-${libraryId}`);
  const label = document.getElementById(`scan-label-${libraryId}`);
  if (bar && label) {
    const total = Math.max(state.total, 1);
    bar.max = total;
    bar.value = state.processed;
    label.textContent = state.total
      ? `${state.processed} / ${state.total} files`
      : "Scanning…";
  }

  if (state.status === "done") {
    await openPlan(state.plan_id);
    await loadLibraries();
  } else if (state.status === "error") {
    alert(`Scan failed: ${state.error}`);
    await loadLibraries();
  } else {
    setTimeout(() => pollScan(libraryId), 400);
  }
}

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

function candidatePicker(item, disabledAttr) {
  if (!item.candidates) return "";
  let candidates;
  try {
    candidates = JSON.parse(item.candidates);
  } catch {
    return "";
  }
  if (!candidates.length) return "";

  const matchLabel = (c) => {
    const name = c.title || c.name;
    return c.year ? `${name} (${c.year})` : name;
  };
  const displayLabel = (c) => matchLabel(c) + (c.language ? ` [${c.language}]` : "");
  const selectedIndex = candidates.findIndex(
    (c) => matchLabel(c) === (item.year ? `${item.title} (${item.year})` : item.title)
  );
  const options = candidates
    .map((c, i) => `<option value="${i}" ${i === selectedIndex ? "selected" : ""}>${escapeHtml(displayLabel(c))}</option>`)
    .join("");
  return `<select data-select-item="${item.id}" ${disabledAttr}>${options}</select>`;
}

function searchTitleEditor(item, disabledAttr) {
  if (item.media_type !== "movie" && item.media_type !== "tv") return "";
  const value = escapeHtml(item.search_query || "");
  const preselected = item.language || PREFERRED_LANGUAGES[0] || "";
  // Only offer the languages chosen in Settings; fall back to the full list
  // when none are configured yet, so the dropdown is never a dead end.
  const choices = PREFERRED_LANGUAGES.length
    ? LANGUAGES.filter((l) => PREFERRED_LANGUAGES.includes(l.id))
    : LANGUAGES;
  const langOptions = choices
    .map((l) => `<option value="${l.id}" ${l.id === preselected ? "selected" : ""}>${escapeHtml(l.name)}</option>`)
    .join("");
  return `
    <span class="search-editor">
      <input type="text" class="mono" data-research-input="${item.id}" value="${value}" ${disabledAttr} />
      <select data-research-lang="${item.id}" ${disabledAttr}>
        <option value="">Any language</option>
        ${langOptions}
      </select>
      <button type="button" data-research-btn="${item.id}" ${disabledAttr}>Search</button>
    </span>`;
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
      <td>${searchTitleEditor(item, disabled)}</td>
      <td class="mono">${escapeHtml(item.target_path || "(unresolved)")}</td>
      <td>${item.matched ? badge("matched", "matched") : badge("unmatched", "unmatched")}</td>
      <td class="mono">${item.language ? escapeHtml(item.language) : "—"}</td>
      <td>${badge(item.status, item.status)}</td>
      <td>${candidatePicker(item, disabled)}</td>`;
    tbody.appendChild(tr);
  }

  const locked = plan.status !== "pending";
  $("#execute-plan-btn").disabled = locked;
  $("#decline-plan-btn").disabled = locked;
  $("#execute-result").textContent = "";
}

$("#plan-table").addEventListener("change", async (e) => {
  const itemId = e.target.getAttribute("data-item");
  const selectItemId = e.target.getAttribute("data-select-item");
  if (itemId) {
    const status = e.target.checked ? "pending" : "skip";
    await api(`/api/plans/${currentPlanId}/items/${itemId}`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    });
  } else if (selectItemId) {
    try {
      await api(`/api/plans/${currentPlanId}/items/${selectItemId}/select`, {
        method: "POST",
        body: JSON.stringify({ candidate_index: Number(e.target.value) }),
      });
      const data = await api(`/api/plans/${currentPlanId}`);
      renderPlan(data);
    } catch (err) {
      alert(err.message);
    }
  }
});

async function runResearch(itemId) {
  const input = document.querySelector(`[data-research-input="${itemId}"]`);
  const langSelect = document.querySelector(`[data-research-lang="${itemId}"]`);
  const query = input.value.trim();
  if (!query) return;
  const language = langSelect ? langSelect.value : "";
  try {
    await api(`/api/plans/${currentPlanId}/items/${itemId}/research`, {
      method: "POST",
      body: JSON.stringify({ query, language }),
    });
    const data = await api(`/api/plans/${currentPlanId}`);
    renderPlan(data);
  } catch (err) {
    alert(err.message);
  }
}

$("#plan-table").addEventListener("click", (e) => {
  const itemId = e.target.getAttribute("data-research-btn");
  if (itemId) runResearch(itemId);
});

$("#plan-table").addEventListener("keydown", (e) => {
  const itemId = e.target.getAttribute("data-research-input");
  if (itemId && e.key === "Enter") {
    e.preventDefault();
    runResearch(itemId);
  }
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

$("#save-plan-btn").addEventListener("click", () => {
  $("#plan-section").hidden = true;
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
      <td>
        <button data-open="${plan.id}">Open</button>
        <button data-delete-plan="${plan.id}" class="danger">Delete</button>
      </td>`;
    tbody.appendChild(tr);
  }
}

$("#history-table").addEventListener("click", async (e) => {
  const openId = e.target.getAttribute("data-open");
  const deleteId = e.target.getAttribute("data-delete-plan");
  if (openId) {
    await openPlan(openId);
  } else if (deleteId) {
    if (!confirm("Delete this plan from history? Files on disk are not touched.")) return;
    await api(`/api/plans/${deleteId}`, { method: "DELETE" });
    if (String(currentPlanId) === deleteId) {
      $("#plan-section").hidden = true;
      currentPlanId = null;
    }
    await loadHistory();
  }
});

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// ---------- Init ----------

loadTvdbStatus();
loadLanguages();
loadPreferredLanguages();
loadLibraries();
loadHistory();
