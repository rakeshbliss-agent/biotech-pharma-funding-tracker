from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from dateutil.relativedelta import relativedelta

MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12
}

def _today() -> date:
    return date.today()

def _parse_iso(d: Optional[str]) -> Optional[date]:
    if not d:
        return None
    try:
        return datetime.strptime(d, "%Y-%m-%d").date()
    except Exception:
        return None

def _amount_to_number(amount: str) -> Optional[float]:
    if not amount:
        return None
    s = str(amount).strip().replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*([MB])", s, re.I)
    if not m:
        return None
    val = float(m.group(1))
    unit = m.group(2).upper()
    return val * (1e9 if unit == "B" else 1e6)

def interpret_query(query: str) -> Dict[str, Any]:
    q = (query or "").strip().lower()
    filters: Dict[str, Any] = {}
    action: Dict[str, Any] = {"type": "filter"}

    if any(x in q for x in ["last week", "past week", "last 1 week", "past 7 days", "last 7 days"]):
        to_d = _today()
        from_d = to_d - timedelta(days=7)
        filters["from_date"] = from_d.isoformat()
        filters["to_date"] = to_d.isoformat()

    m = re.search(r"last\s+(\d+)\s+days", q)
    if m:
        n = int(m.group(1))
        to_d = _today()
        from_d = to_d - timedelta(days=n)
        filters["from_date"] = from_d.isoformat()
        filters["to_date"] = to_d.isoformat()

    m = re.search(r"last\s+(\d+)\s+weeks", q)
    if m:
        n = int(m.group(1))
        to_d = _today()
        from_d = to_d - timedelta(days=7 * n)
        filters["from_date"] = from_d.isoformat()
        filters["to_date"] = to_d.isoformat()

    if any(x in q for x in ["last month", "past month", "past 30 days"]):
        to_d = _today()
        from_d = to_d - timedelta(days=30)
        filters["from_date"] = from_d.isoformat()
        filters["to_date"] = to_d.isoformat()

    m = re.search(r"past\s+(\d+)\s+months", q)
    if m:
        n = int(m.group(1))
        to_d = _today()
        from_d = to_d - relativedelta(months=n)
        filters["from_date"] = from_d.isoformat()
        filters["to_date"] = to_d.isoformat()

    m = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\s+(20\d{2})\b", q, re.I)
    if m:
        mon = MONTH_MAP[m.group(1).lower()]
        yr = int(m.group(2))
        from_d = date(yr, mon, 1)
        to_d = from_d + relativedelta(months=1) - timedelta(days=1)
        filters["from_date"] = from_d.isoformat()
        filters["to_date"] = to_d.isoformat()

    m = re.search(r"\b(seed|pre-seed|series\s*[a-z]|series\s*\d)\b", q, re.I)
    if m:
        filters["round"] = m.group(0).strip()

    if "small molecule" in q:
        filters["small_molecule"] = "yes"
    if any(x in q for x in ["not small molecule", "non small molecule", "non-small molecule"]):
        filters["small_molecule"] = "no"

    m = re.search(r"hq\s+in\s+([a-z\s\.-]+)", q)
    if m:
        filters["hq_city"] = m.group(1).strip()

    m = re.search(r"\bin\s+([a-z]{2})\b", q)
    if m:
        st = m.group(1).upper()
        if st not in {"IN"}:
            filters["hq_state"] = st

    m = re.search(r"top\s+(\d+)", q)
    if m and any(x in q for x in ["largest", "biggest", "amount", "$"]):
        action = {"type": "top_by_amount", "n": int(m.group(1))}
    elif any(x in q for x in ["largest", "biggest"]):
        action = {"type": "top_by_amount", "n": 10}

    return {"query": query, "filters": filters, "action": action}

def _match_text(needle: str, hay: str) -> bool:
    return needle.lower() in (hay or "").lower()

def filter_rows(rows: List[Dict[str, Any]], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
    from_d = _parse_iso(filters.get("from_date"))
    to_d = _parse_iso(filters.get("to_date"))
    company = filters.get("company")
    round_q = filters.get("round")
    hq_state = filters.get("hq_state")
    hq_city = filters.get("hq_city")
    sm = filters.get("small_molecule")

    out: List[Dict[str, Any]] = []
    for r in rows:
        d = _parse_iso(r.get("Funding date"))
        if from_d and (not d or d < from_d):
            continue
        if to_d and (not d or d > to_d):
            continue
        if company and not _match_text(company, r.get("Company", "")):
            continue
        if round_q and not _match_text(round_q, r.get("Funding round", "")):
            continue
        if hq_state and not _match_text(hq_state, r.get("HQ State/Region", "")):
            continue
        if hq_city and not _match_text(hq_city, r.get("HQ City", "")):
            continue
        if sm:
            val = (r.get("Small molecule modality?") or "").strip().lower()
            if sm.lower().startswith("y") and val not in {"yes", "y", "true"}:
                continue
            if sm.lower().startswith("n") and val in {"yes", "y", "true"}:
                continue
        out.append(r)
    return out

def summarize_answer(user_query: str, plan: Dict[str, Any], rows: List[Dict[str, Any]]) -> str:
    action = (plan.get("action") or {}).get("type")
    if action == "top_by_amount":
        n = int((plan.get("action") or {}).get("n", 10))
        sorted_rows = sorted(rows, key=lambda r: _amount_to_number(r.get("Funding amount", "")) or 0, reverse=True)
        top = sorted_rows[:n]
        if not top:
            return "No matching funding rounds found."
        bullets = [f"- {r.get('Company','')} — {r.get('Funding amount','')} ({r.get('Funding round','')}, {r.get('Funding date','')})" for r in top]
        return "Here are the largest rounds in the selected set:\n" + "\n".join(bullets)

    if not rows:
        return "No matching funding rounds found."

    unique_companies = sorted({r.get("Company", "") for r in rows if r.get("Company")})
    show = rows[:10]
    bullets = [f"- {r.get('Company','')} — {r.get('Funding amount','')} ({r.get('Funding round','')}, {r.get('Funding date','')})" for r in show]
    more = "" if len(rows) <= 10 else f"\n… and {len(rows)-10} more."
    return f"Found {len(rows)} funding rounds across {len(unique_companies)} companies. Showing the latest {min(10,len(rows))}:\n" + "\n".join(bullets) + more
