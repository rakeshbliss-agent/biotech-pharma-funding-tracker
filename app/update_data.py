from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import feedparser
import requests
import yaml
from bs4 import BeautifulSoup

USE_OPENAI = bool(os.getenv("OPENAI_API_KEY"))
try:
    from openai import OpenAI
except Exception:
    OpenAI = None  # type: ignore

APP_DIR = Path(__file__).resolve().parent
DATA_FILE = APP_DIR / "funding_data.json"
SOURCES_FILE = APP_DIR / "sources.yaml"

EXTRACTION_PROMPT = """Extract biotech/pharma funding round information from the provided article text.
Return STRICT JSON with this schema:
{
  "items": [
    {
      "Company": "",
      "Funding date": "YYYY-MM-DD" or "",
      "Funding round": "",
      "Funding amount": "",
      "Investors": "",
      "Description": "",
      "Therapeutic Area": "",
      "Therapeutic Modality": "",
      "Lead Clinical Stage": "",
      "Small molecule modality?": "Yes"|"No"|"",
      "HQ City": "",
      "HQ State/Region": ""
    }
  ]
}
Rules:
- If the article is not about a funding round, return {"items": []}
- If a field is missing, use "".
""".strip()

def load_json() -> List[Dict[str, Any]]:
    if not DATA_FILE.exists():
        return []
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))

def save_json(rows: List[Dict[str, Any]]) -> None:
    rows_sorted = sorted(rows, key=lambda r: (r.get("Funding date") or ""), reverse=True)
    DATA_FILE.write_text(json.dumps(rows_sorted, indent=2, ensure_ascii=False), encoding="utf-8")

def norm_date(dt: str) -> Optional[str]:
    if not dt:
        return None
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(dt.strip(), fmt).date().isoformat()
        except Exception:
            pass
    try:
        parsed = feedparser._parse_date(dt)  # type: ignore
        if parsed:
            return datetime(*parsed[:6]).date().isoformat()
    except Exception:
        pass
    return None

def fingerprint(company: str, funding_date: str, amount: str, round_: str) -> str:
    raw = f"{company}|{funding_date}|{amount}|{round_}".lower()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

def load_sources() -> List[str]:
    if not SOURCES_FILE.exists():
        return []
    data = yaml.safe_load(SOURCES_FILE.read_text(encoding="utf-8")) or {}
    return list(data.get("sources") or [])

def article_text(url: str) -> str:
    r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text

def extract_with_openai(text: str) -> List[Dict[str, Any]]:
    if not USE_OPENAI or OpenAI is None:
        return []
    client = OpenAI()
    text = text[:12000]
    resp = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": EXTRACTION_PROMPT},
            {"role": "user", "content": text},
        ],
        temperature=0.0,
    )
    content = resp.choices[0].message.content or "{}"
    try:
        data = json.loads(content)
        items = data.get("items") or []
        return [i for i in items if isinstance(i, dict)]
    except Exception:
        return []

def update(lookback_days: int = 8) -> Tuple[int, int]:
    existing = load_json()
    existing_keys = set(
        fingerprint(
            r.get("Company",""),
            r.get("Funding date",""),
            r.get("Funding amount",""),
            r.get("Funding round",""),
        )
        for r in existing
    )

    sources = load_sources()
    if not sources:
        save_json(existing)
        return (0, len(existing))

    cutoff = datetime.utcnow().date() - timedelta(days=lookback_days)
    new_items: List[Dict[str, Any]] = []

    for feed_url in sources:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries[:60]:
            link = getattr(entry, "link", None)
            if not link:
                continue

            published = None
            if getattr(entry, "published", None):
                published = norm_date(entry.published)
            elif getattr(entry, "updated", None):
                published = norm_date(entry.updated)

            if published:
                try:
                    if datetime.strptime(published, "%Y-%m-%d").date() < cutoff:
                        continue
                except Exception:
                    pass

            try:
                txt = article_text(link)
            except Exception:
                continue

            extracted = extract_with_openai(txt)
            for it in extracted:
                it["Funding date"] = norm_date(it.get("Funding date","")) or it.get("Funding date","")
                k = fingerprint(it.get("Company",""), it.get("Funding date",""), it.get("Funding amount",""), it.get("Funding round",""))
                if k in existing_keys:
                    continue
                existing_keys.add(k)
                new_items.append(it)

    if new_items:
        existing.extend(new_items)
        save_json(existing)

    return (len(new_items), len(existing))

if __name__ == "__main__":
    added, total = update()
    print(f"Added {added} new funding rounds. Total rows: {total}.")
