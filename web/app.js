// web/app.js (matches your index.html IDs exactly)

function $(id) { return document.getElementById(id); }

function getMode() {
  const m = $("mode");
  return (m ? m.value : "funding").toLowerCase();
}

function endpointForMode(mode) {
  if (mode === "deals") return "/api/deals";
  if (mode === "both") return "/api/both";
  return "/api/funding";
}

function fmtUSD(n) {
  const x = Number(n);
  if (Number.isNaN(x)) return "";
  if (x >= 1e9) return `$${(x / 1e9).toFixed(1)}B`;
  if (x >= 1e6) return `$${(x / 1e6).toFixed(1)}M`;
  if (x >= 1e3) return `$${(x / 1e3).toFixed(0)}K`;
  return `$${x}`;
}

function syncAmountLabels() {
  const min = $("minAmount");
  const max = $("maxAmount");
  const minLabel = $("minAmountLabel");
  const maxLabel = $("maxAmountLabel");
  if (!min || !max || !minLabel || !maxLabel) return;

  // Ensure min <= max (optional UX safeguard)
  if (Number(min.value) > Number(max.value)) {
    // push max up to min
    max.value = min.value;
  }

  minLabel.textContent = fmtUSD(min.value);
  maxLabel.textContent = fmtUSD(max.value);
}

function openDrawer() {
  $("drawer")?.classList.remove("hidden");
  $("drawerBackdrop")?.classList.remove("hidden");
}
function closeDrawer() {
  $("drawer")?.classList.add("hidden");
  $("drawerBackdrop")?.classList.add("hidden");
}

function buildQueryParams() {
  const params = new URLSearchParams();
  params.set("limit", "50000");

  const datePreset = $("datePreset")?.value || "all";
  if (datePreset && datePreset !== "all") {
    params.set("date_preset", datePreset);
  }

  // Advanced filters
  const qDrawer = ($("qDrawer")?.value || "").trim();
  if (qDrawer) params.set("q", qDrawer);

  const geo = ($("geo")?.value || "").trim();
  if (geo) params.set("geo", geo);

  const modality = ($("modality")?.value || "").trim();
  if (modality) params.set("modality", modality);

  const segment = ($("segment")?.value || "").trim();
  if (segment) params.set("segment", segment);

  const ta = ($("therapeuticArea")?.value || "").trim();
  if (ta) params.set("therapeutic_area", ta);

  const minAmount = $("minAmount")?.value;
  const maxAmount = $("maxAmount")?.value;
  if (minAmount !== undefined && String(minAmount).trim() !== "") params.set("min_amount", String(minAmount));
  if (maxAmount !== undefined && String(maxAmount).trim() !== "") params.set("max_amount", String(maxAmount));

  return params;
}

function renderTable(rows) {
  const thead = $("thead");
  const tbody = $("resultsTableBody");
  const resultCount = $("resultCount");

  if (resultCount) resultCount.textContent = String(rows?.length || 0);

  if (!thead || !tbody) return;

  thead.innerHTML = "";
  tbody.innerHTML = "";

  if (!rows || rows.length === 0) {
    thead.innerHTML = "<tr><th>No results</th></tr>";
    return;
  }

  const keys = Object.keys(rows[0] || {});
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

async function fetchAndRender() {
  syncAmountLabels();

  const mode = getMode();
  const endpoint = endpointForMode(mode);
  const params = buildQueryParams();

  // Update title
  const title = $("tableTitle");
  if (title) title.textContent = (mode === "deals" ? "Deals (M&A)" : mode === "both" ? "Funding + Deals" : "Funding");

  const url = `${endpoint}?${params.toString()}`;

  try {
    const res = await fetch(url);
    if (!res.ok) {
      console.error("API error:", res.status, await res.text());
      renderTable([]);
      return;
    }
    const data = await res.json();
    renderTable(data.rows || []);

    const updatedLabel = $("updatedLabel");
    if (updatedLabel) {
      const now = new Date();
      updatedLabel.textContent = `Updated ${now.toLocaleString()}`;
    }
  } catch (e) {
    console.error("Fetch failed:", e);
    renderTable([]);
  }
}

async function sendChat() {
  const input = $("chatInput");
  const out = $("chatAnswer");

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
      body: JSON.stringify({ query: q, mode: getMode() })
    });

    if (!res.ok) {
      console.error("Chat API error:", res.status, await res.text());
      out.textContent = `Chat failed (${res.status}).`;
      return;
    }

    const data = await res.json();
    out.textContent = data.answer || "(No answer)";

    // Update table with chat rows
    if (Array.isArray(data.rows)) {
      renderTable(data.rows);
      if ($("resultCount") && typeof data.count === "number") {
        $("resultCount").textContent = String(data.count);
      }
      const title = $("tableTitle");
      if (title) title.textContent = (data.mode === "deals" ? "Deals (M&A)" : data.mode === "both" ? "Funding + Deals" : "Funding");
    }
  } catch (e) {
    console.error("Chat failed:", e);
    out.textContent = "Chat failed. Check console logs.";
  }
}

function clearFilters() {
  if ($("qDrawer")) $("qDrawer").value = "";
  if ($("geo")) $("geo").value = "";
  if ($("modality")) $("modality").value = "";
  if ($("segment")) $("segment").value = "";
  if ($("therapeuticArea")) $("therapeuticArea").value = "";

  if ($("minAmount")) $("minAmount").value = "0";
  if ($("maxAmount")) $("maxAmount").value = "2000000000";
  syncAmountLabels();

  fetchAndRender();
}

function wireEvents() {
  // Drawer
  $("openFilters")?.addEventListener("click", openDrawer);
  $("closeFilters")?.addEventListener("click", closeDrawer);
  $("drawerBackdrop")?.addEventListener("click", closeDrawer);

  // Apply/Clear
  $("applyBtn")?.addEventListener("click", (e) => {
    e.preventDefault();
    fetchAndRender();
    closeDrawer();
  });
  $("clearFilters")?.addEventListener("click", (e) => {
    e.preventDefault();
    clearFilters();
  });

  // Mode + date preset auto refresh
  $("mode")?.addEventListener("change", fetchAndRender);
  $("datePreset")?.addEventListener("change", fetchAndRender);

  // Refresh button
  $("refreshBtn")?.addEventListener("click", (e) => {
    e.preventDefault();
    if ($("chatInput")) $("chatInput").value = "";
  if ($("chatAnswer")) $("chatAnswer").textContent = "";
    // Reload home and refetch. (Reload is optional; refetch is enough.)
    fetchAndRender();
  });

  // Chat Ask button
  $("chatSend")?.addEventListener("click", (e) => {
    e.preventDefault();
    sendChat();
  });

  // Enter key behavior:
  // - Enter in chat input => chat
  // - Enter in any filter input => apply filters
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;

    const active = document.activeElement;
    if (!active) return;

    if (active.id === "chatInput") {
      e.preventDefault();
      sendChat();
      return;
    }

    // If cursor is in drawer inputs, apply filters
    if (["qDrawer", "modality", "segment", "therapeuticArea"].includes(active.id)) {
      e.preventDefault();
      fetchAndRender();
      return;
    }
  });

  // Slider label live update
  $("minAmount")?.addEventListener("input", syncAmountLabels);
  $("maxAmount")?.addEventListener("input", syncAmountLabels);

  syncAmountLabels();
}

document.addEventListener("DOMContentLoaded", () => {
  wireEvents();
  fetchAndRender();
});
