from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import feedparser
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"

FUNDING_JSON = APP_DIR / "funding_data.json"
DEALS_JSON = APP_DIR / "deals_data.json"

USER_AGENT = os.getenv(
    "SCRAPER_UA",
    "Mozilla/5.0 (compatible; BiotechPharmaTracker/1.0; +https://example.com)",
)
TIMEOUT = 30
SLEEP_BETWEEN_REQ_SEC = 1.0

AMOUNT_HINT = re.compile(
    r"(\$|€|£)\s?\d+(?:\.\d+)?\s*(k|m|b|thousand|million|billion)?\b|\b\d+(?:\.\d+)?\s*(k|m|b)\b",
    re.I,
)
FUNDING_HINTS = re.compile(r"\b(raised|secures|secured|financing|series|seed|funding|round)\b", re.I)
DEAL_HINTS = re.compile(r"\b(acquire|acquired|acquisition|merger|buyout|takeover|deal)\b", re.I)

# --- sources you listed ---
@dataclass
class Source:
    name: str
    kind: str  # html | rss
    url: str
    topic: str  # funding | deals | both
    tag: str = "trusted"


SOURCES: List[Source] = [
    # HTML trackers
    Source(
        name="FierceBiotech - Fundraising Tracker",
        kind="html",
        url="https://www.fiercebiotech.com/biotech/fierce-biotech-fundraising-tracker-26",
        topic="funding",
        tag="reputable_news",
    ),
    Source(
        name="Labiotech - Funding Tracker 2026",
        kind="html",
        url="https://www.labiotech.eu/biotech-funding-2026-tracker/",
        topic="funding",
        tag="reputable_news",
    ),
    Source(
        name="Labiotech - Deals 2026",
        kind="html",
        url="https://www.labiotech.eu/biotech-deals-2026/",
        topic="deals",
        tag="reputable_news",
    ),
    Source(
        name="BioPharmaDive - VC Funding Tracker",
        kind="html",
        url="https://www.biopharmadive.com/news/biotech-venture-capital-funding-startup-tracker/726829/",
        topic="funding",
        tag="reputable_news",
    ),
    Source(
        name="BioPharmaDive - M&A Tracker",
        kind="html",
        url="https://www.biopharmadive.com/news/biotech-pharma-deals-merger-acquisitions-tracker/604262/",
        topic="deals",
        tag="reputable_news",
    ),
    # RSS backups
    Source(
        name="FierceBiotech - RSS",
        kind="rss",
        url="https://www.fiercebiotech.com/rss/xml",
        topic="both",
        tag="reputable_news",
    ),
    Source(
        name="Business Wire - Pharma RSS",
        kind="rss",
        url="https://feed.businesswire.com/rss/home/?rss=G1QFDERJXkJeEFpQWQ==",
        topic="both",
        tag="reputable_news",
    ),
    Source(
        name="GlobeNewswire - Pharma RSS",
        kind="rss",
        url="https://www.globenewswire.com/RssFeed/industry/Pharmaceuticals",
        topic="both",
        tag="reputable_news",
    ),
]


def fetch(url: str) -> str:
    time.sleep(SLEEP_BETWEEN_REQ_SEC)
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text


def load_json_list(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_json_list(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")


def normalize_whitespace(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def guess_company_pair(text: str) -> Tuple[str, str]:
    """
    Very heuristic: "X acquires Y" / "X to acquire Y" / "X buys Y"
    """
    t = normalize_whitespace(text)
    m = re.search(r"^(.*?)\s+(to\s+acquire|acquires|acquired|buys|buying|purchase|purchases)\s+(.*?)(?:\s+for\s+|$)", t, re.I)
    if m:
        return m.group(1).strip(), m.group(3).strip()
    m = re.search(r"^(.*?)\s+(merges\s+with)\s+(.*)$", t, re.I)
    if m:
        return m.group(1).strip(), m.group(3).strip()
    return "", ""


def first_amount(text: str) -> str:
    m = AMOUNT_HINT.search(text or "")
    return m.group(0).strip() if m else ""


def normalize_funding(row: Dict[str, Any]) -> Dict[str, Any]:
    # Keep canonical keys
    out = {
        "Company": row.get("Company", "") or "",
        "Funding date": row.get("Funding date", "") or "",
        "Funding round": row.get("Funding round", "") or "",
        "Funding amount": row.get("Funding amount", "") or "",
        "Investors": row.get("Investors", "") or "",
        "Description": row.get("Description", "") or "",
        "Therapeutic Area": row.get("Therapeutic Area", "") or "",
        "Therapeutic Modality": row.get("Therapeutic Modality", "") or "",
        "Lead Clinical Stage": row.get("Lead Clinical Stage", "") or "",
        "Small molecule modality?": row.get("Small molecule modality?", "") or "",
        "HQ City": row.get("HQ City", "") or "",
        "HQ State/Region": row.get("HQ State/Region", "") or "",
        "HQ Country": row.get("HQ Country", "") or "",
        "Source": row.get("Source", "") or "",
    }
    # pass-through metadata if present
    if "__source_url" in row:
        out["__source_url"] = row["__source_url"]
    if "__source_tag" in row:
        out["__source_tag"] = row["__source_tag"]
    return out


def normalize_deal(row: Dict[str, Any]) -> Dict[str, Any]:
    out = {
        "Deal date": row.get("Deal date", "") or "",
        "Acquirer": row.get("Acquirer", "") or "",
        "Target": row.get("Target", "") or "",
        "Deal type": row.get("Deal type", "") or "",
        "Upfront": row.get("Upfront", "") or "",
        "Total value": row.get("Total value", "") or "",
        "Therapeutic Area": row.get("Therapeutic Area", "") or "",
        "Modality": row.get("Modality", "") or "",
        "Segment": row.get("Segment", "") or "",
        "Target HQ Country": row.get("Target HQ Country", "") or "",
        "Description": row.get("Description", "") or "",
        "Source": row.get("Source", "") or "",
    }
    if "__source_url" in row:
        out["__source_url"] = row["__source_url"]
    if "__source_tag" in row:
        out["__source_tag"] = row["__source_tag"]
    return out


def nonempty_merge(old: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge where non-empty new values overwrite old; otherwise keep old.
    """
    merged = dict(old)
    for k, v in new.items():
        if v is None:
            continue
        if isinstance(v, str):
            if v.strip():
                merged[k] = v
        else:
            merged[k] = v
    return merged


def funding_key(r: Dict[str, Any]) -> str:
    return "|".join(
        [
            (r.get("Company") or "").strip().lower(),
            (r.get("Funding date") or "").strip(),
            (r.get("Funding amount") or "").strip().lower(),
            (r.get("Funding round") or "").strip().lower(),
        ]
    )


def deals_key(r: Dict[str, Any]) -> str:
    return "|".join(
        [
            (r.get("Acquirer") or "").strip().lower(),
            (r.get("Target") or "").strip().lower(),
            (r.get("Deal date") or "").strip(),
            (r.get("Upfront") or "").strip().lower(),
        ]
    )


def upsert_rows(existing: List[Dict[str, Any]], incoming: List[Dict[str, Any]], key_fn) -> List[Dict[str, Any]]:
    idx: Dict[str, Dict[str, Any]] = {}
    for r in existing:
        idx[key_fn(r)] = r

    for r in incoming:
        k = key_fn(r)
        if k in idx:
            idx[k] = nonempty_merge(idx[k], r)
        else:
            idx[k] = r

    return list(idx.values())


def curated_patches() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Guaranteed rows you specifically asked for (so they are always present).
    Dates are set based on your prompt; edit if needed.
    """
    funding: List[Dict[str, Any]] = []

    deals: List[Dict[str, Any]] = [
        normalize_deal(
            {
                "Deal date": "2026-03-04",
                "Acquirer": "Eli Lilly",
                "Target": "Ventyx Biosciences",
                "Deal type": "Acquisition/Merger",
                "Upfront": "$1.2B",
                "Total value": "$1.2B",
                "Therapeutic Area": "",
                "Modality": "",
                "Segment": "",
                "Target HQ Country": "USA",
                "Description": "Ventyx Biosciences completes $1.2B acquisition by Eli Lilly; company delists from Nasdaq.",
                "Source": "Curated patch",
                "__source_tag": "curated",
                "__source_url": "",
            }
        ),
        normalize_deal(
            {
                "Deal date": "2026-03-05",
                "Acquirer": "Asahi Kasei",
                "Target": "AiCuris",
                "Deal type": "Acquisition/Merger",
                "Upfront": "€780M",
                "Total value": "€780M",
                "Therapeutic Area": "",
                "Modality": "",
                "Segment": "",
                "Target HQ Country": "Germany",
                "Description": "Japan's Asahi Kasei acquires Germany's AiCuris for €780M.",
                "Source": "Curated patch",
                "__source_tag": "curated",
                "__source_url": "",
            }
        ),
    ]
    return funding, deals


def soup(url: str) -> BeautifulSoup:
    return BeautifulSoup(fetch(url), "lxml")


def scrape_tracker_like_funding(url: str, source: Source) -> List[Dict[str, Any]]:
    """
    Generic funding extraction from tracker page: find blocks with funding hints + amount.
    """
    out: List[Dict[str, Any]] = []
    s = soup(url)
    blocks = s.find_all(["h2", "h3", "p", "li"])
    window: List[str] = []

    for el in blocks:
        txt = normalize_whitespace(el.get_text(" "))
        if not txt:
            continue
        window.append(txt)
        if len(window) > 3:
            window.pop(0)
        blob = " ".join(window)

        if not FUNDING_HINTS.search(blob):
            continue
        amt = first_amount(blob)
        if not amt:
            continue

        company = ""
        m = re.search(r"^(.*?)\s+(raised|secures|secured|closes|closed)\b", txt, re.I)
        if m:
            company = m.group(1).strip()
        else:
            company = " ".join(txt.split()[:5]).strip()

        out.append(
            normalize_funding(
                {
                    "Company": company,
                    "Funding date": "",
                    "Funding round": "",
                    "Funding amount": amt,
                    "Investors": "",
                    "Description": blob[:5000],
                    "Therapeutic Area": "",
                    "Therapeutic Modality": "",
                    "Lead Clinical Stage": "",
                    "Small molecule modality?": "",
                    "HQ City": "",
                    "HQ State/Region": "",
                    "HQ Country": "",
                    "Source": source.name,
                    "__source_tag": source.tag,
                    "__source_url": source.url,
                }
            )
        )

    return out


def scrape_tracker_like_deals(url: str, source: Source) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    s = soup(url)
    blocks = s.find_all(["h2", "h3", "p", "li"])
    window: List[str] = []

    for el in blocks:
        txt = normalize_whitespace(el.get_text(" "))
        if not txt:
            continue
        window.append(txt)
        if len(window) > 3:
            window.pop(0)
        blob = " ".join(window)

        if not DEAL_HINTS.search(blob):
            continue

        amt = first_amount(blob)
        acq, tgt = guess_company_pair(txt)
        if not acq or not tgt:
            acq, tgt = guess_company_pair(blob)
        if not acq or not tgt:
            continue

        out.append(
            normalize_deal(
                {
                    "Deal date": "",
                    "Acquirer": acq,
                    "Target": tgt,
                    "Deal type": "Acquisition/Merger" if "acqui" in blob.lower() or "merger" in blob.lower() else "Deal",
                    "Upfront": amt,
                    "Total value": amt,
                    "Therapeutic Area": "",
                    "Modality": "",
                    "Segment": "",
                    "Target HQ Country": "",
                    "Description": blob[:5000],
                    "Source": source.name,
                    "__source_tag": source.tag,
                    "__source_url": source.url,
                }
            )
        )

    return out


def build_funding_from_rss(entry: Any, source_name: str, source_url: str, tag: str) -> Optional[Dict[str, Any]]:
    title = normalize_whitespace(getattr(entry, "title", "") or "")
    summary = normalize_whitespace(getattr(entry, "summary", "") or "")
    text = f"{title} {summary}"

    if not FUNDING_HINTS.search(text):
        return None
    amt = first_amount(text)
    if not amt:
        return None

    company = " ".join(title.split()[:5]).strip()
    return normalize_funding(
        {
            "Company": company,
            "Funding date": "",
            "Funding round": "",
            "Funding amount": amt,
            "Investors": "",
            "Description": text[:5000],
            "Therapeutic Area": "",
            "Therapeutic Modality": "",
            "Lead Clinical Stage": "",
            "Small molecule modality?": "",
            "HQ City": "",
            "HQ State/Region": "",
            "HQ Country": "",
            "Source": source_name,
            "__source_tag": tag,
            "__source_url": source_url,
        }
    )


def build_deal_from_rss(entry: Any, source_name: str, source_url: str, tag: str) -> Optional[Dict[str, Any]]:
    title = normalize_whitespace(getattr(entry, "title", "") or "")
    summary = normalize_whitespace(getattr(entry, "summary", "") or "")
    text = f"{title} {summary}"

    if not DEAL_HINTS.search(text):
        return None

    acq, tgt = guess_company_pair(title)
    if not acq or not tgt:
        acq, tgt = guess_company_pair(text)
    if not acq or not tgt:
        return None

    amt = first_amount(text)
    return normalize_deal(
        {
            "Deal date": "",
            "Acquirer": acq,
            "Target": tgt,
            "Deal type": "Acquisition/Merger",
            "Upfront": amt,
            "Total value": amt,
            "Therapeutic Area": "",
            "Modality": "",
            "Segment": "",
            "Target HQ Country": "",
            "Description": text[:5000],
            "Source": source_name,
            "__source_tag": tag,
            "__source_url": source_url,
        }
    )


def collect_from_sources() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    funding_rows: List[Dict[str, Any]] = []
    deal_rows: List[Dict[str, Any]] = []

    f0, d0 = curated_patches()
    funding_rows.extend(f0)
    deal_rows.extend(d0)

    for src in SOURCES:
        try:
            if src.kind == "rss":
                feed = feedparser.parse(src.url)
                for entry in feed.entries[:250]:
                    if src.topic in {"funding", "both"}:
                        fr = build_funding_from_rss(entry, src.name, src.url, src.tag)
                        if fr:
                            funding_rows.append(fr)
                    if src.topic in {"deals", "both"}:
                        dr = build_deal_from_rss(entry, src.name, src.url, src.tag)
                        if dr:
                            deal_rows.append(dr)

            elif src.kind == "html":
                if src.topic == "funding":
                    funding_rows.extend(scrape_tracker_like_funding(src.url, src))
                elif src.topic == "deals":
                    deal_rows.extend(scrape_tracker_like_deals(src.url, src))
                else:
                    funding_rows.extend(scrape_tracker_like_funding(src.url, src))
                    deal_rows.extend(scrape_tracker_like_deals(src.url, src))

        except Exception:
            # keep going if a site blocks or changes structure
            continue

    return funding_rows, deal_rows


def main() -> None:
    existing_funding = [normalize_funding(r) for r in load_json_list(FUNDING_JSON)]
    existing_deals = [normalize_deal(r) for r in load_json_list(DEALS_JSON)]

    incoming_funding, incoming_deals = collect_from_sources()

    merged_funding = upsert_rows(existing_funding, incoming_funding, funding_key)
    merged_deals = upsert_rows(existing_deals, incoming_deals, deals_key)

    # sort (ISO dates sort naturally; blanks go last)
    merged_funding.sort(key=lambda r: (r.get("Funding date") or ""), reverse=True)
    merged_deals.sort(key=lambda r: (r.get("Deal date") or ""), reverse=True)

    save_json_list(FUNDING_JSON, merged_funding)
    save_json_list(DEALS_JSON, merged_deals)

    print(f"[OK] funding rows: {len(merged_funding)}")
    print(f"[OK] deals rows:   {len(merged_deals)}")
    print(f"[OK] updated at:   {datetime.utcnow().isoformat()}Z")


if __name__ == "__main__":
    main()
