#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"

FUNDING_PATH = APP_DIR / "funding_data.json"
DEALS_PATH = APP_DIR / "deals_data.json"

# -----------------------------
# Utilities
# -----------------------------

def load_json_list(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []

def save_json_list(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

def iso_date(s: str) -> Optional[str]:
    """Try to coerce date strings into YYYY-MM-DD."""
    if not s:
        return None
    s = s.strip()
    # Already ISO
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s
    # Common formats like "March 6, 2026"
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except Exception:
            pass
    return None

def norm(s: Any) -> str:
    return str(s or "").strip()

def stable_hash(parts: List[str]) -> str:
    raw = "||".join([p.strip().lower() for p in parts if p is not None])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

def dedupe(existing: List[Dict[str, Any]], incoming: List[Dict[str, Any]], key_fn) -> Tuple[List[Dict[str, Any]], int]:
    seen = set()
    out = []
    for r in existing:
        k = key_fn(r)
        if k:
            seen.add(k)
        out.append(r)

    added = 0
    for r in incoming:
        k = key_fn(r)
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(r)
        added += 1

    return out, added

# -----------------------------
# Your schema key functions
# -----------------------------

def funding_key(r: Dict[str, Any]) -> str:
    # Company + date + round + amount is usually unique enough
    return stable_hash([
        norm(r.get("Company")),
        norm(r.get("Funding date")),
        norm(r.get("Funding round")),
        norm(r.get("Funding amount")),
    ])

def deal_key(r: Dict[str, Any]) -> str:
    # Acquirer + Target + date + value
    return stable_hash([
        norm(r.get("Acquirer")),
        norm(r.get("Target")),
        norm(r.get("Deal date")),
        norm(r.get("Total value")) or norm(r.get("Upfront")),
    ])

# -----------------------------
# Fetch + parse sources (starter set)
# -----------------------------
# NOTE: Start simple; you can add sources gradually.
# The key is: each source function returns a list of records in YOUR schema.
# -----------------------------

UA = {"User-Agent": "Mozilla/5.0 (compatible; tracker-bot/1.0; +https://github.com/)"}

def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=UA, timeout=30)
    resp.raise_for_status()
    return resp.text

def parse_biopharmadive_tracker_deals(url: str) -> List[Dict[str, Any]]:
    """
    Starter parser for BioPharma Dive tracker-type pages.
    This WILL NOT catch everything. It’s just a template you can iterate on.
    """
    try:
        html = fetch_html(url)
    except Exception:
        return []

    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text("\n")

    # This page format can change; we keep this simple and conservative.
    # If you want higher fidelity, we can later parse the structured blocks.

    deals: List[Dict[str, Any]] = []

    # Very rough heuristic: look for lines with "$" and "acquire" etc.
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    for ln in lines:
        if "acquir" in ln.lower() and "$" in ln:
            # We do not auto-infer full structured record here to avoid garbage.
            # Instead, skip; rely on explicit sources (press releases) or better parsers.
            pass

    return deals

def parse_press_release_deal(acquirer: str, target: str, deal_date: str, value: str, source: str, desc: str,
                             ta: str = "", modality: str = "", segment: str = "", country: str = "USA") -> Dict[str, Any]:
    return {
        "Deal date": deal_date,
        "Acquirer": acquirer,
        "Target": target,
        "Deal type": "Acquisition/Merger",
        "Upfront": value,
        "Total value": value,
        "Therapeutic Area": ta,
        "Modality": modality,
        "Segment": segment,
        "Target HQ Country": country,
        "Description": desc,
        "Source": source,
    }

def parse_press_release_funding(company: str, funding_date: str, round_: str, amount: str, investors: str, desc: str,
                                ta: str = "", modality: str = "", stage: str = "", sm: str = "", city: str = "", state: str = "", country: str = "") -> Dict[str, Any]:
    return {
        "Company": company,
        "Funding date": funding_date,
        "Funding round": round_,
        "Funding amount": amount,
        "Investors": investors,
        "Description": desc,
        "Therapeutic Area": ta,
        "Therapeutic Modality": modality,
        "Lead Clinical Stage": stage,
        "Small molecule modality?": sm,
        "HQ City": city,
        "HQ State/Region": state,
        "HQ Country": country,
    }

def curated_latest_additions() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    This is where you can "seed" specific known missing items quickly,
    while you expand automated parsers over time.
    """
    deals: List[Dict[str, Any]] = []
    funding: List[Dict[str, Any]] = []

    # Example: add the 2 deals you mentioned (fill date/desc precisely once you confirm)
    # NOTE: Put real ISO date here (YYYY-MM-DD). If unknown, leave it out and don't add.
    deals.append(parse_press_release_deal(
        acquirer="Eli Lilly",
        target="Ventyx Biosciences",
        deal_date="2026-03-??",  # <-- replace with actual ISO date
        value="$1.2B",
        source="Company announcement / reliable news source",
        desc="Ventyx Biosciences completes ~$1.2B acquisition by Eli Lilly; Ventyx delists from Nasdaq.",
        ta="",
        modality="",
        segment="",
        country="USA",
    ))

    deals.append(parse_press_release_deal(
        acquirer="Asahi Kasei",
        target="Aicuris",
        deal_date="2026-03-??",  # <-- replace with actual ISO date
        value="€780M",
        source="Company announcement / reliable news source",
        desc="Asahi Kasei acquires Germany's Aicuris for €780M.",
        ta="",
        modality="",
        segment="",
        country="Germany",
    ))

    return funding, deals

# -----------------------------
# Main update routine
# -----------------------------

def main() -> None:
    existing_funding = load_json_list(FUNDING_PATH)
    existing_deals = load_json_list(DEALS_PATH)

    new_funding: List[Dict[str, Any]] = []
    new_deals: List[Dict[str, Any]] = []

    # 1) curated patch list (fast way to fix known gaps)
    f_cur, d_cur = curated_latest_additions()
    new_funding.extend(f_cur)
    new_deals.extend(d_cur)

    # 2) add automated sources incrementally (start small)
    # Example placeholder:
    # tracker_url = "https://www.biopharmadive.com/news/biotech-pharma-deals-merger-acquisitions-tracker/604262/"
    # new_deals.extend(parse_biopharmadive_tracker_deals(tracker_url))

    # Normalize dates (optional but recommended)
    for r in new_funding:
        r["Funding date"] = iso_date(norm(r.get("Funding date"))) or norm(r.get("Funding date"))
    for r in new_deals:
        r["Deal date"] = iso_date(norm(r.get("Deal date"))) or norm(r.get("Deal date"))

    # De-dupe merge
    merged_funding, added_funding = dedupe(existing_funding, new_funding, funding_key)
    merged_deals, added_deals = dedupe(existing_deals, new_deals, deal_key)

    # Sort newest first
    merged_funding.sort(key=lambda r: norm(r.get("Funding date")), reverse=True)
    merged_deals.sort(key=lambda r: norm(r.get("Deal date")), reverse=True)

    save_json_list(FUNDING_PATH, merged_funding)
    save_json_list(DEALS_PATH, merged_deals)

    print(f"[OK] Funding: {len(existing_funding)} -> {len(merged_funding)} (added {added_funding})")
    print(f"[OK] Deals:   {len(existing_deals)} -> {len(merged_deals)} (added {added_deals})")

if __name__ == "__main__":
    main()
