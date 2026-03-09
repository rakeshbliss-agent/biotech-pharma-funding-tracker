// web/app.js

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

function el(sel) {
  return document.querySelector(sel);
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

function renderTable(rows) {
  const body = el("#resultsTableBody");
  const countEl = el("#resultCount");
  if (countEl) countEl.textContent = `${rows.length}`;

  if (!body) return;
  body.innerHTML = "";

  const keys = rows.length ? Object.keys(rows[0]) : [];
  rows.forEach((r) => {
    const tr = document.createElement("tr");
    keys.forEach((k) => {
      const td = document.createElement("td");
      td.textContent = (r[k] === null || r[k] === undefined) ? "" : String(r[k]);
      tr.appendChild(td);
    });
    body.appendChild(tr);
  });
}

async function applyFilters() {
  const mode = (el("#mode")?.value || "funding").toLowerCase();
  const endpoint = getEndpointForMode(mode);

  const params = new URLSearchParams();
  params.set("limit", "50000");

  const preset = el("#datePreset")?.value || "all";
  if (preset && preset !== "all") params.set("date_preset", preset);

  const q = (el("#q")?.value || "").trim();
  if (q) params.set("q", q);

  const geo = el("#geo")?.value || "all";
  if (geo && geo !== "all") params.set("geo", geo);

  const modality = el("#modality")?.value || "all";
  if (modality && modality !== "all") params.set("modality", modality);

  const segment = el("#segment")?.value || "all";
  if (segment && segment !== "all") params.set("segment", segment);

  const therapeuticArea = el("#therapeuticArea")?.value || "";
  if (therapeuticArea.trim()) params.set("therapeutic_area", therapeuticArea.trim());

  const minAmount = el("#minAmount")?.value;
  const maxAmount = el("#maxAmount")?.value;
  if (minAmount !== undefined && minAmount !== null && String(minAmount).trim() !== "") {
    params.set("min_amount", String(minAmount));
  }
  if (maxAmount !== undefined && maxAmount !== null && String(maxAmount).trim() !== "") {
    params.set("max_amount", String(maxAmount));
  }

  // Fetch and render
  const url = `${endpoint}?${params.toString()}`;
  const res = await fetch(url);
  if (!res.ok) {
    console.error("Fetch failed:", res.status, await res.text());
    renderTable([]);
    return;
  }
  const data = await res.json();
  renderTable(data.rows || []);
}

function wireEvents() {
  // Apply button
  el("#applyBtn")?.addEventListener("click", (e) => {
    e.preventDefault();
    applyFilters();
  });

  // Enter key triggers apply (for inputs/selects)
  document.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      const active = document.activeElement;
      if (active && ["INPUT", "SELECT", "TEXTAREA"].includes(active.tagName)) {
        e.preventDefault();
        applyFilters();
      }
    }
  });

  // Mode/preset/filters change triggers apply
  ["#mode", "#datePreset", "#geo", "#modality", "#segment"].forEach((sel) => {
    el(sel)?.addEventListener("change", applyFilters);
  });

  // Query typing: optional "live" behavior (comment out if you want manual only)
  // el("#q")?.addEventListener("input", debounce(applyFilters, 400));

  // Sliders update labels live + reapply on change
  el("#minAmount")?.addEventListener("input", () => {
    syncAmountLabels();
  });
  el("#maxAmount")?.addEventListener("input", () => {
    syncAmountLabels();
  });

  // If you want changing slider to automatically apply:
  el("#minAmount")?.addEventListener("change", applyFilters);
  el("#maxAmount")?.addEventListener("change", applyFilters);

  syncAmountLabels();
}

document.addEventListener("DOMContentLoaded", () => {
  wireEvents();
  applyFilters(); // initial load
});
