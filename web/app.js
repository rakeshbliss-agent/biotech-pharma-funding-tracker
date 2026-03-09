// web/app.js

function el(sel) { return document.querySelector(sel); }

function getMode() {
  return (el("#mode")?.value || "funding").toLowerCase();
}

function getEndpointForMode(mode) {
  if (mode === "deals") return "/api/deals";
  if (mode === "both") return "/api/both";
  return "/api/funding";
}

function fmtUSD(x) {
  const n = Number(x || 0);
  if (Number.isNaN(n)) return "";
  if (n >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `$${(n / 1e3).toFixed(0)}K`;
  return `$${n}`;
}

function syncAmountLabels() {
  const minSlider = el("#minAmount");
  const maxSlider = el("#maxAmount");
  const minLabel = el("#minAmountLabel");
  const maxLabel = el("#maxAmountLabel");
  if (!minSlider || !maxSlider || !minLabel || !maxLabel) return;
  minLabel.textContent = fmtUSD(minSlider.value);
  maxLabel.textContent = fmtUSD(maxSlider.value);
}

function openDrawer() {
  el("#drawer")?.classList.remove("hidden");
  el("#drawerBackdrop")?.classList.remove("hidden");
}
function closeDrawer() {
  el("#drawer")?.classList.add("hidden");
  el("#drawerBackdrop")?.classList.add("hidden");
}

function buildParams() {
  const params = new URLSearchParams();
  params.set("limit", "50000");

  // date preset
  const preset = el("#datePreset")?.value || "all";
  if (preset && preset !== "all") params.set("date_preset", preset);

  // keyword (table search)
  const q = (el("#q")?.value || "").trim();
  const qDrawer = (el("#qDrawer")?.value || "").trim();
  const combinedQ = [q, qDrawer].filter(Boolean).join(" + ");
  if (combinedQ) params.set("q", combinedQ);

  // drawer fields
  const geo = (el("#geo")?.value || "").trim();
  if (geo) params.set("geo", geo);

  const modality = (el("#modality")?.value || "").trim();
  if (modality) params.set("modality", modality);

  const segment = (el("#segment")?.value || "").trim();
  if (segment) params.set("segment", segment);

  const therapeuticArea = (el("#therapeuticArea")?.value || "").trim();
  if (therapeuticArea) params.set("therapeutic_area", therapeuticArea);

  const minAmount = el("#minAmount")?.value;
  const maxAmount = el("#maxAmount")?.value;
  if (minAmount !== undefined && String(minAmount).trim() !== "") params.set("min_amount", String(minAmount));
  if (maxAmount !== undefined && String(maxAmount).trim() !== "") params.set("max_amount", String(maxAmount));

  return params;
}

function renderTable(rows) {
  const thead = el("#thead");
  const tbody = el("#resultsTableBody");
  const countEl = el("#resultCount");

  if (countEl) countEl.textContent = String(rows?.length || 0);
  if (!thead || !tbody) return;

  tbody.innerHTML = "";
  thead.innerHTML = "";

  if (!rows || rows.length === 0) {
    thead.innerHTML = "<tr><th>No results</th></tr>";
    return;
  }

  const keys = Object.keys(rows[0]);

  const hr = document.createElement("tr");
  keys.forEach((k) => {
    const th = document.createElement("th");
    th.textContent = k;
    hr.appendChild(th);
  });
  thead.appendChild(hr);

  rows.forEach((r) => {
    const tr = document.createElement("tr");
    keys.forEach((k) => {
      const td = document.createElement("td");
      const v = r[k];
      td.textContent = (v === null || v === undefined) ? "" : String(v);
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
}

async function applyFilters() {
  syncAmountLabels();

  const mode = getMode();
  const endpoint = getEndpointForMode(mode);
  const params = buildParams();
  const url = `${endpoint}?${params.toString()}`;

  const res = await fetch(url);
  if (!res.ok) {
    console.error("API failed:", res.status, await res.text());
    renderTable([]);
    return;
  }
  const data = await res.json();
  renderTable(data.rows || []);
}

function clearFilters() {
  if (el("#q")) el("#q").value = "";
  if (el("#qDrawer")) el("#qDrawer").value = "";
  if (el("#geo")) el("#geo").value = "";
  if (el("#modality")) el("#modality").value = "";
  if (el("#segment")) el("#segment").value = "";
  if (el("#therapeuticArea")) el("#therapeuticArea").value = "";

  if (el("#minAmount")) el("#minAmount").value = "0";
  if (el("#maxAmount")) el("#maxAmount").value = "2000000000";
  syncAmountLabels();

  applyFilters();
}

async function sendChat() {
  const input = el("#chatInput");
  const out = el("#chatAnswer");
  const mode = getMode();

  if (!input || !out) return;

  const q = (input.value || "").trim();
  if (!q) {
    out.textContent = "Type a question first.";
    return;
  }

  out.textContent = "Thinking…";

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // backend expects: { "query": "..." }
      body: JSON.stringify({ query: q, mode })
    });

    if (!res.ok) {
      out.textContent = `Chat API failed (${res.status}).`;
      console.error(await res.text());
      return;
    }

    const data = await res.json();

    // show answer
    out.textContent = data.answer || "(No answer)";

    // also update table with returned rows if present
    if (Array.isArray(data.rows)) {
      renderTable(data.rows);
      const countEl = el("#resultCount");
      if (countEl && typeof data.count === "number") countEl.textContent = String(data.count);
    }
  } catch (e) {
    console.error(e);
    out.textContent = "Chat failed. Check console logs.";
  }
}

function wireEvents() {
  // Drawer open/close
  el("#openFilters")?.addEventListener("click", openDrawer);
  el("#closeFilters")?.addEventListener("click", closeDrawer);
  el("#drawerBackdrop")?.addEventListener("click", closeDrawer);

  // Apply/Clear
  el("#applyBtn")?.addEventListener("click", (e) => {
    e.preventDefault();
    applyFilters();
    closeDrawer();
  });
  el("#clearFilters")?.addEventListener("click", (e) => {
    e.preventDefault();
    clearFilters();
  });

  // Mode + datePreset refetch
  el("#mode")?.addEventListener("change", applyFilters);
  el("#datePreset")?.addEventListener("change", applyFilters);

  // Refresh button
  el("#refreshBtn")?.addEventListener("click", (e) => {
    e.preventDefault();
    applyFilters();
  });

  // Chat button
  el("#chatSend")?.addEventListener("click", (e) => {
    e.preventDefault();
    sendChat();
  });

  // Enter key: if focus is chat box -> chat; else -> apply filters
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;

    const active = document.activeElement;
    if (!active) return;

    // If user is typing in the chat input, Enter should send chat
    if (active.id === "chatInput") {
      e.preventDefault();
      sendChat();
      return;
    }

    // If user is typing anywhere else in filters/search, Enter applies filters
    if (["INPUT", "SELECT", "TEXTAREA"].includes(active.tagName)) {
      e.preventDefault();
      applyFilters();
    }
  });

  // Slider labels live
  el("#minAmount")?.addEventListener("input", syncAmountLabels);
  el("#maxAmount")?.addEventListener("input", syncAmountLabels);

  syncAmountLabels();
}

document.addEventListener("DOMContentLoaded", () => {
  wireEvents();
  applyFilters();
});
