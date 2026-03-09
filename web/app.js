// web/app.js
(() => {
  // ---- helpers ----
  const $ = (id) => document.getElementById(id);

  const state = {
    mode: "funding",          // funding | deals | both
    date_preset: "all",       // all | today | last_7 | last_30 | ytd | mtd
    filters: {
      q: "",
      geo: "",
      modality: "",
      segment: "",
      therapeutic_area: "",
      min_amount: null,
      max_amount: null,
    }
  };

  function formatUSD(n) {
    if (n === null || n === undefined || Number.isNaN(n)) return "";
    const num = Number(n);
    if (num >= 1e9) return (num / 1e9).toFixed(2).replace(/\.00$/, "") + "B";
    if (num >= 1e6) return (num / 1e6).toFixed(2).replace(/\.00$/, "") + "M";
    if (num >= 1e3) return (num / 1e3).toFixed(0) + "K";
    return String(num);
  }

  function buildApiUrl() {
    let base = "/api/funding";
    if (state.mode === "deals") base = "/api/deals";
    if (state.mode === "both") base = "/api/both";

    const params = new URLSearchParams();

    // IMPORTANT: snake_case keys expected by FastAPI
    if (state.date_preset && state.date_preset !== "all") {
      params.set("date_preset", state.date_preset);
    }

    const f = state.filters;

    if (f.q) params.set("q", f.q);
    if (f.geo) params.set("geo", f.geo);
    if (f.modality) params.set("modality", f.modality);
    if (f.segment) params.set("segment", f.segment);
    if (f.therapeutic_area) params.set("therapeutic_area", f.therapeutic_area);

    if (f.min_amount !== null && f.min_amount !== undefined) params.set("min_amount", String(f.min_amount));
    if (f.max_amount !== null && f.max_amount !== undefined) params.set("max_amount", String(f.max_amount));

    params.set("limit", "50000");
    return `${base}?${params.toString()}`;
  }

  async function fetchJson(url, opts) {
    const res = await fetch(url, opts);
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`HTTP ${res.status}: ${text}`);
    }
    return res.json();
  }

  // ---- table rendering ----
  function setTitle() {
    const title = state.mode === "funding" ? "Funding"
      : state.mode === "deals" ? "Deals (M&A)"
      : "Funding + Deals";
    $("tableTitle").textContent = title;
  }

  function renderTable(rows) {
    const thead = $("thead");
    const tbody = $("resultsTableBody");

    thead.innerHTML = "";
    tbody.innerHTML = "";

    if (!rows || rows.length === 0) return;

    // columns vary by mode
    const cols = Object.keys(rows[0]);

    const trh = document.createElement("tr");
    cols.forEach((c) => {
      const th = document.createElement("th");
      th.textContent = c;
      trh.appendChild(th);
    });
    thead.appendChild(trh);

    rows.slice(0, 500).forEach((r) => {
      const tr = document.createElement("tr");
      cols.forEach((c) => {
        const td = document.createElement("td");
        const v = r[c];
        td.textContent = (v === null || v === undefined) ? "" : String(v);
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
  }

  async function loadTable() {
    setTitle();
    const url = buildApiUrl();
    const data = await fetchJson(url);
    $("resultCount").textContent = String(data.count ?? 0);
    $("updatedLabel").textContent = `Loaded ${new Date().toLocaleString()}`;
    renderTable(data.rows || []);
  }

  // ---- drawer (advanced filters) ----
  function openDrawer() {
    $("drawer").classList.remove("hidden");
    $("drawerBackdrop").classList.remove("hidden");
    $("qDrawer").focus();
  }

  function closeDrawer() {
    $("drawer").classList.add("hidden");
    $("drawerBackdrop").classList.add("hidden");
  }

  function readDrawerIntoState() {
    state.filters.q = $("qDrawer").value.trim();
    state.filters.geo = $("geo").value.trim();
    state.filters.modality = $("modality").value.trim();
    state.filters.segment = $("segment").value.trim();
    state.filters.therapeutic_area = $("therapeuticArea").value.trim();

    // sliders are numeric
    const minA = Number($("minAmount").value);
    const maxA = Number($("maxAmount").value);

    // ensure min <= max
    const minVal = Math.min(minA, maxA);
    const maxVal = Math.max(minA, maxA);

    state.filters.min_amount = minVal > 0 ? minVal : null;
    state.filters.max_amount = maxVal < 2000000000 ? maxVal : null;
  }

  function clearDrawer() {
    $("qDrawer").value = "";
    $("geo").value = "";
    $("modality").value = "";
    $("segment").value = "";
    $("therapeuticArea").value = "";

    $("minAmount").value = "0";
    $("maxAmount").value = "2000000000";
    updateSliderLabels();

    state.filters = {
      q: "",
      geo: "",
      modality: "",
      segment: "",
      therapeutic_area: "",
      min_amount: null,
      max_amount: null
    };
  }

  function updateSliderLabels() {
    const minA = Number($("minAmount").value);
    const maxA = Number($("maxAmount").value);
    $("minAmountLabel").textContent = formatUSD(minA);
    $("maxAmountLabel").textContent = formatUSD(maxA);
  }

  // ---- chat ----
  async function runChat() {
    const text = $("chatInput").value.trim();
    if (!text) return;

    $("chatAnswer").textContent = "Thinking…";

    const payload = {
      query: text,
      mode: state.mode
    };

    try {
      const data = await fetchJson("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      $("chatAnswer").textContent = data.answer || "(no answer)";
      $("resultCount").textContent = String(data.count ?? 0);
      $("updatedLabel").textContent = `Chat results ${new Date().toLocaleString()}`;

      // Render rows returned by chat in the table (best UX)
      renderTable(data.rows || []);
    } catch (e) {
      $("chatAnswer").textContent = `Error: ${e.message}`;
    }
  }

  // ---- refresh ----
  async function doRefresh() {
    // reset state + UI
    state.mode = "funding";
    state.date_preset = "all";
    $("mode").value = "funding";
    $("datePreset").value = "all";

    // clear chat UI
    $("chatInput").value = "";
    $("chatAnswer").textContent = "";

    // clear drawer UI + state
    clearDrawer();
    closeDrawer();

    await loadTable();
  }

  // ---- wire events (IMPORTANT: only once) ----
  function wireEvents() {
    // Mode selector
    $("mode").addEventListener("change", async (e) => {
      state.mode = e.target.value;
      // keep current filters, reload
      await loadTable();
    });

    // Date preset selector
    $("datePreset").addEventListener("change", async (e) => {
      state.date_preset = e.target.value; // today | last_7 | last_30 | ytd | all
      await loadTable();
    });

    // Drawer open/close
    $("openFilters").addEventListener("click", openDrawer);
    $("closeFilters").addEventListener("click", closeDrawer);
    $("drawerBackdrop").addEventListener("click", closeDrawer);

    // Apply / Clear
    $("applyBtn").addEventListener("click", async () => {
      readDrawerIntoState();
      closeDrawer();
      await loadTable();
    });

    $("clearFilters").addEventListener("click", async () => {
      clearDrawer();
      await loadTable();
    });

    // Enter in drawer should apply
    $("drawer").addEventListener("keydown", async (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        readDrawerIntoState();
        closeDrawer();
        await loadTable();
      }
      if (e.key === "Escape") {
        e.preventDefault();
        closeDrawer();
      }
    });

    // Sliders update label live
    $("minAmount").addEventListener("input", updateSliderLabels);
    $("maxAmount").addEventListener("input", updateSliderLabels);

    // Chat ask button
    $("chatSend").addEventListener("click", async () => {
      await runChat();
    });

    // Chat enter key always works
    $("chatInput").addEventListener("keydown", async (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        await runChat();
      }
    });

    // Refresh
    $("refreshBtn").addEventListener("click", async () => {
      await doRefresh();
    });
  }

  // ---- init ----
  async function init() {
    updateSliderLabels();
    wireEvents();
    await loadTable();
  }

  window.addEventListener("DOMContentLoaded", init);
})();
