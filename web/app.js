let MODE = "funding"; // funding|deals|both

let FILTERS = {
  keyword: "",
  geo: "",
  modality: "",
  therapeutic_area: "",
  segment: "",
  min_amount: "",
  max_amount: "",
  date_preset: "this_week",
};

function escapeHtml(s) {
  if (s === null || s === undefined) return "";
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function setMeta(count) {
  document.getElementById("countLabel").textContent = `${count} rows`;
  document.getElementById("updatedLabel").textContent = `Updated: ${new Date().toLocaleString()}`;
}

function setTitle() {
  const title = MODE === "funding" ? "Funding"
              : MODE === "deals" ? "Deals (M&A)"
              : "Funding + Deals";
  document.getElementById("tableTitle").textContent = title;
}

function getColumnsForMode(mode, rows) {
  if (mode === "funding") {
    return ["Company","Funding date","Funding round","Funding amount","Investors","Description","Therapeutic Area","Therapeutic Modality","Lead Clinical Stage","Small molecule modality?","HQ City","HQ State/Region","HQ Country"];
  }
  if (mode === "deals") {
    return ["Deal date","Acquirer","Target","Deal type","Upfront","Total value","Therapeutic Area","Modality","Target HQ Country","Source","Description"];
  }
  // both: use normalized schema from backend merge_rows_for_chat()
  return ["Type","Date","Company/Target","Counterparty","Amount","Round/Deal","Therapeutic Area","Modality","Geo","Description"];
}

function renderTable(mode, rows) {
  const thead = document.getElementById("thead");
  const tbody = document.getElementById("tbody");

  const cols = getColumnsForMode(mode, rows);
  thead.innerHTML = `<tr>${cols.map(c => `<th>${escapeHtml(c)}</th>`).join("")}</tr>`;

  tbody.innerHTML = "";
  for (const r of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = cols.map(c => `<td>${escapeHtml(r[c])}</td>`).join("");
    tbody.appendChild(tr);
  }
}

function buildQueryParams(extra = {}) {
  const params = new URLSearchParams();

  // date preset always sent
  params.set("date_preset", FILTERS.date_preset || "all");

  if (FILTERS.keyword) params.set("keyword", FILTERS.keyword);
  if (FILTERS.geo) params.set("geo", FILTERS.geo);
  if (FILTERS.modality) params.set("modality", FILTERS.modality);
  if (FILTERS.therapeutic_area) params.set("therapeutic_area", FILTERS.therapeutic_area);
  if (FILTERS.segment) params.set("segment", FILTERS.segment);
  if (FILTERS.min_amount) params.set("min_amount", FILTERS.min_amount);
  if (FILTERS.max_amount) params.set("max_amount", FILTERS.max_amount);

  // extra overrides
  for (const [k, v] of Object.entries(extra)) {
    if (v !== null && v !== undefined && String(v).length > 0) params.set(k, v);
  }

  params.set("limit", "50000");
  return params.toString();
}

async function fetchRows() {
  setTitle();

  if (MODE === "funding") {
    const res = await fetch(`/api/funding?${buildQueryParams()}`);
    if (!res.ok) throw new Error("Failed to load funding");
    return await res.json();
  }

  if (MODE === "deals") {
    const res = await fetch(`/api/deals?${buildQueryParams()}`);
    if (!res.ok) throw new Error("Failed to load deals");
    return await res.json();
  }

  // both mode uses chat endpoint for merged results so it has a unified schema
  const query = FILTERS.keyword ? `keyword: ${FILTERS.keyword}` : "show latest";
  const res = await fetch(`/api/chat`, {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({query, mode: "both"})
  });
  if (!res.ok) throw new Error("Failed to load both");
  const data = await res.json();
  return {count: data.count, rows: data.rows};
}

async function refresh() {
  document.getElementById("chatAnswer").textContent = "";
  const data = await fetchRows();
  renderTable(MODE, data.rows || []);
  setMeta(data.count || 0);
}

async function runChat() {
  const input = document.getElementById("chatInput");
  const answerEl = document.getElementById("chatAnswer");
  const q = input.value.trim();
  if (!q) return;

  answerEl.textContent = "Thinking…";
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({query: q, mode: MODE})
  });
  if (!res.ok) {
    answerEl.textContent = "Error running query.";
    return;
  }
  const data = await res.json();
  answerEl.textContent = data.answer || "";
  renderTable(MODE === "both" ? "both" : MODE, data.rows || []);
  setMeta(data.count || 0);
}

/* Drawer */
function openDrawer() {
  document.getElementById("drawerBackdrop").classList.remove("hidden");
  document.getElementById("drawer").classList.remove("hidden");
}
function closeDrawer() {
  document.getElementById("drawerBackdrop").classList.add("hidden");
  document.getElementById("drawer").classList.add("hidden");
}
function applyDrawerToFilters() {
 const taSelect = document.getElementById("fTA");
const selected = [...taSelect.selectedOptions].map(o => o.value);
FILTERS.therapeutic_area = selected.join(",");
  FILTERS.keyword = document.getElementById("fKeyword").value.trim();
  FILTERS.geo = document.getElementById("fGeo").value.trim();
  FILTERS.modality = document.getElementById("fModality").value.trim();
  FILTERS.therapeutic_area = document.getElementById("fTA").value.trim();
  FILTERS.segment = document.getElementById("fSegment").value.trim();
  FILTERS.min_amount = document.getElementById("fMinAmt").value.trim();
  FILTERS.max_amount = document.getElementById("fMaxAmt").value.trim();
  const minM = parseInt(document.getElementById("minAmt").value, 10);
const maxM = parseInt(document.getElementById("maxAmt").value, 10);

// store as USD
FILTERS.min_amount = String(minM * 1_000_000);
FILTERS.max_amount = String(maxM * 1_000_000);
}
function wireEnterToApply() {
  const ids = ["fKeyword","fModality","fTA","fSegment","fMinAmt","fMaxAmt"];
  ids.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener("keydown", async (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        applyDrawerToFilters();
        closeDrawer();
        await refresh();
      }
    });
  });
}

function wireAmountSliders() {
  const minEl = document.getElementById("minAmt");
  const maxEl = document.getElementById("maxAmt");
  const minLab = document.getElementById("minAmtLabel");
  const maxLab = document.getElementById("maxAmtLabel");

  function sync() {
    let minV = parseInt(minEl.value, 10);
    let maxV = parseInt(maxEl.value, 10);
    if (minV > maxV) {
      // keep them consistent
      maxV = minV;
      maxEl.value = String(maxV);
    }
    minLab.textContent = String(minV);
    maxLab.textContent = String(maxV);
  }

  minEl.addEventListener("input", sync);
  maxEl.addEventListener("input", sync);
  sync();
}
function clearDrawer() {
  ["fKeyword","fGeo","fModality","fTA","fSegment","fMinAmt","fMaxAmt"].forEach(id=>{
    const el = document.getElementById(id);
    if (!el) return;
    el.value = "";
  });
  FILTERS.keyword = "";
  FILTERS.geo = "";
  FILTERS.modality = "";
  FILTERS.therapeutic_area = "";
  FILTERS.segment = "";
  FILTERS.min_amount = "";
  FILTERS.max_amount = "";
  document.getElementById("minAmt").value = "0";
document.getElementById("maxAmt").value = "1000";
document.getElementById("minAmtLabel").textContent = "0";
document.getElementById("maxAmtLabel").textContent = "1000";
FILTERS.min_amount = "";
FILTERS.max_amount = "";
}

function setActiveTab(mode) {
  MODE = mode;
  document.querySelectorAll(".tab").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.mode === mode);
  });
  setTitle();
}

window.addEventListener("DOMContentLoaded", async () => {
  // tabs
  document.querySelectorAll(".tab").forEach(btn => {
    btn.addEventListener("click", async () => {
      setActiveTab(btn.dataset.mode);
      wireEnterToApply();
      wireAmountSliders();
      await refresh();
    });
  });

  // date preset
  document.getElementById("datePreset").addEventListener("change", async (e) => {
    FILTERS.date_preset = e.target.value;
    await refresh();
  });

  // refresh
  document.getElementById("refreshBtn").addEventListener("click", refresh);

  // chat
  document.getElementById("chatSend").addEventListener("click", runChat);
  document.getElementById("chatInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter") runChat();
  });

  // drawer
  document.getElementById("openFilters").addEventListener("click", openDrawer);
  document.getElementById("closeFilters").addEventListener("click", closeDrawer);
  document.getElementById("drawerBackdrop").addEventListener("click", closeDrawer);

  document.getElementById("applyFilters").addEventListener("click", async () => {
    applyDrawerToFilters();
    closeDrawer();
    await refresh();
  });

  document.getElementById("clearFilters").addEventListener("click", async () => {
    clearDrawer();
    await refresh();
  });

  // init preset
  document.getElementById("datePreset").value = FILTERS.date_preset;
  await refresh();
});
