from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from dateutil.relativedelta import relativedelta

MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12
}

REGION_US = {"USA", "US", "UNITED STATES", "UNITED STATES OF AMERICA"}
REGION_EUROPE_HINTS = {
    "UK", "UNITED KINGDOM", "ENGLAND", "SCOTLAND", "WALES",
    "IRELAND", "FRANCE", "GERMANY", "SPAIN", "ITALY", "NETHERLANDS",
    "SWITZERLAND", "DENMARK", "SWEDEN", "NORWAY", "FINLAND", "BELGIUM",
    "AUSTRIA", "PORTUGAL", "ICELAND", "LUXEMBOURG", "CZECH", "POLAND"
}
REGION_APAC_HINTS = {
    "CHINA", "JAPAN", "SOUTH KOREA", "KOREA", "INDIA", "SINGAPORE",
    "HONG KONG", "TAIWAN", "AUSTRALIA", "NEW ZEALAND"
}

DEFAULT_SEGMENTS = [
    "ADMET/PK", "SBDD", "Drug Repurposing", "GenChem",
    "Knowledge Graph", "Lab Informatics", "Automation"
]

DEAL_HINT_RE = re.compile(
    r"\b(acquisition|acquisitions|acquire|acquired|buyout|merger|takeover|m\s*&\s*a|m&a)\b",
    re.I
)

AMOUNT_TOKEN_RE = re.compile(r"^\d+(?:\.\d+)?[kmb]$", re.I)


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
    """
    Parses strings like "$60M", "€46.6 million", "305M", "$2.5B", "about $52 million", "500k"
    Returns approx number (no FX conversion; just numeric scaling).
    """
    if not amount:
        return None
    s = str(amount).replace(",", "").strip()

    # 60M / 2.5B / 500K
    m = re.search(r"(\d+(?:\.\d+)?)\s*([KMB])\b", s, re.I)
    if m:
        val = float(m.group(1))
        unit = m.group(2).upper()
        if unit == "K":
            return val * 1e3
        return val * (1e9 if unit == "B" else 1e6)

    # "million" / "billion"
    m2 = re.search(r"(\d+(?:\.\d+)?)\s*(million|billion)\b", s, re.I)
    if m2:
        val = float(m2.group(1))
        unit = m2.group(2).lower()
        return val * (1e9 if unit == "billion" else 1e6)

    return None


def _text_in(needle: Optional[str], hay: str) -> bool:
    if not needle:
        return True
    return needle.lower() in (hay or "").lower()


def _normalize_country(country: Optional[str]) -> str:
    return (country or "").strip().upper()


def _geo_bucket(country: Optional[str]) -> Optional[str]:
    c = _normalize_country(country)
    if not c:
        return None
    if c in REGION_US:
        return "US"
    if c in REGION_EUROPE_HINTS or "EUROPE" in c:
        return "Europe"
    if c in REGION_APAC_HINTS or "ASIA" in c:
        return "APAC"
    return "ROW"


def apply_date_preset(filters: Dict[str, Any]) -> None:
    """
    Public helper (used by main.py) to translate date_preset into from_date/to_date.
    Supported: today, this_week, last_7, last_30, mtd, ytd, all/none
    """
    preset = (filters.get("date_preset") or "").strip().lower()
    if preset in {"", "all", "none"}:
        return

    to_d = _today()

    if preset == "today":
        filters["from_date"] = to_d.isoformat()
        filters["to_date"] = to_d.isoformat()
        return

    if preset == "this_week":
        from_d = to_d - timedelta(days=to_d.weekday())
        filters["from_date"] = from_d.isoformat()
        filters["to_date"] = to_d.isoformat()
        return

    if preset == "last_7":
        filters["from_date"] = (to_d - timedelta(days=7)).isoformat()
        filters["to_date"] = to_d.isoformat()
        return

    if preset == "last_30":
        filters["from_date"] = (to_d - timedelta(days=30)).isoformat()
        filters["to_date"] = to_d.isoformat()
        return

    if preset == "mtd":
        from_d = date(to_d.year, to_d.month, 1)
        filters["from_date"] = from_d.isoformat()
        filters["to_date"] = to_d.isoformat()
        return

    if preset == "ytd":
        from_d = date(to_d.year, 1, 1)
        filters["from_date"] = from_d.isoformat()
        filters["to_date"] = to_d.isoformat()
        return


def _date_in_range(d_str: Optional[str], from_d: Optional[date], to_d: Optional[date]) -> bool:
    if not (from_d or to_d):
        return True
    d = _parse_iso(d_str)
    if not d:
        return False
    if from_d and d < from_d:
        return False
    if to_d and d > to_d:
        return False
    return True


def _parse_amount_filter(x: Any) -> Optional[float]:
    if x is None:
        return None
    s = str(x).strip()
    if s == "" or s.lower() in {"null", "none"}:
        return None
    try:
        return float(s)
    except Exception:
        return None


def _extract_amount_from_query_text(q: str) -> Optional[float]:
    """
    Extracts a number like 500k / 2m / 1.2b from a free-text query and returns numeric value.
    """
    if not q:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*(k|m|b)\b", q, re.I)
    if not m:
        return None
    val = float(m.group(1))
    unit = m.group(2).lower()
    mult = 1e3 if unit == "k" else (1e6 if unit == "m" else 1e9)
    return val * mult


def _split_terms(keyword: str) -> List[str]:
    """
    AND terms only when user uses '+' or ' and ' explicitly.
    Otherwise treat it as a phrase (single term).
    """
    if not keyword:
        return []
    if "+" in keyword or re.search(r"\s+and\s+", keyword, flags=re.I):
        parts = re.split(r"\+|(?:\s+and\s+)", keyword, flags=re.I)
        return [p.strip().lower() for p in parts if p.strip()]
    return [keyword.strip().lower()]


def infer_mode_from_query(query: str) -> Optional[str]:
    if not query:
        return None
    return "deals" if DEAL_HINT_RE.search(query) else None


def interpret_query(query: str, mode: str = "funding") -> Dict[str, Any]:
    """
    Rules-based interpretation for /api/chat.
    Key: do NOT treat full questions as keyword. Extract only meaningful terms.
    """
    q_raw = (query or "").strip()
    q = q_raw.lower()

    filters: Dict[str, Any] = {}
    action: Dict[str, Any] = {"type": "filter"}
    mode = (mode or "funding").strip().lower()

    # ---- date phrases ----
    if any(x in q for x in ["today", "since yesterday"]):
        filters["date_preset"] = "today"
    elif any(x in q for x in ["current week", "this week"]):
        filters["date_preset"] = "this_week"
    elif any(x in q for x in ["last week", "past week", "past 7 days", "last 7 days", "since last week"]):
        filters["date_preset"] = "last_7"
    elif any(x in q for x in ["this month", "current month", "month to date", "mtd"]):
        filters["date_preset"] = "mtd"
    elif any(x in q for x in ["last month", "past month", "past 30 days", "since last month"]):
        filters["date_preset"] = "last_30"
    elif "ytd" in q or "year to date" in q:
        filters["date_preset"] = "ytd"

    # explicit last N days
    m = re.search(r"last\s+(\d+)\s+days", q)
    if m:
        n = int(m.group(1))
        to_d = _today()
        from_d = to_d - timedelta(days=n)
        filters["from_date"] = from_d.isoformat()
        filters["to_date"] = to_d.isoformat()

    # past N months
    m = re.search(r"past\s+(\d+)\s+months", q)
    if m:
        n = int(m.group(1))
        to_d = _today()
        from_d = to_d - relativedelta(months=n)
        filters["from_date"] = from_d.isoformat()
        filters["to_date"] = to_d.isoformat()

    # Month + year
    m = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\s+(20\d{2})\b", q, re.I)
    if m:
        mon = MONTH_MAP[m.group(1).lower()]
        yr = int(m.group(2))
        from_d = date(yr, mon, 1)
        to_d = from_d + relativedelta(months=1) - timedelta(days=1)
        filters["from_date"] = from_d.isoformat()
        filters["to_date"] = to_d.isoformat()

    # modality hints
    if "small molecule" in q:
        filters["modality"] = "small molecule"
    elif any(x in q for x in ["biologic", "antibody", "mab"]):
        filters["modality"] = "biologic"
    elif any(x in q for x in ["gene therapy", "cell therapy", "car-t", "crispr"]):
        filters["modality"] = "cell/gene"
    elif any(x in q for x in ["rna", "sirna", "mrna"]):
        filters["modality"] = "rna"
    elif "adc" in q:
        filters["modality"] = "adc"

    # geo hints
    if any(x in q for x in ["us", "usa", "united states"]):
        filters["geo"] = "US"
    elif "europe" in q or "uk" in q:
        filters["geo"] = "Europe"
    elif any(x in q for x in ["apac", "asia", "china", "japan", "korea", "australia"]):
        filters["geo"] = "APAC"

    # segment hints
    if "admet" in q:
        filters["segment"] = "ADMET/PK"
    else:
        for seg in DEFAULT_SEGMENTS:
            if seg.lower() in q:
                filters["segment"] = seg
                break

    # funding round hints
    m = re.search(r"\b(seed|pre-seed|series\s*[a-z]|series\s*\d)\b", q, re.I)
    if m:
        filters["round"] = m.group(0).strip()

    # deal type hints
    if DEAL_HINT_RE.search(q_raw):
        filters["deal_type"] = "Acquisition/Merger"

    # top/large
    m = re.search(r"top\s+(\d+)", q)
    if m and any(x in q for x in ["largest", "biggest", "amount", "$"]):
        action = {"type": "top_by_amount", "n": int(m.group(1))}
    elif any(x in q for x in ["largest", "biggest"]):
        action = {"type": "top_by_amount", "n": 10}

    # amount hint from query (also remove it from keyword later)
    amt = _extract_amount_from_query_text(q)
    if amt is not None:
        filters["min_amount"] = str(amt)

    # ---- keyword extraction (safe token-based; no substring replace of "in"/"on") ----
    # Remove common question phrases (multi-word) first.
    phrase_markers = [
        "which companies", "which company", "received funding", "receive funding",
        "funding", "funded", "deals", "deal", "acquisitions", "acquisition", "acquired",
        "this week", "current week", "last week",
        "this month", "current month", "month to date",
        "last month", "past month", "past 7 days", "past 30 days",
        "since last week", "since last month",
        "year to date",
    ]
    cleaned = q
    for ph in phrase_markers:
        cleaned = cleaned.replace(ph, " ")

    # Keep '+' for AND queries; normalize punctuation to spaces.
    cleaned = re.sub(r"[^a-z0-9\s\+]+", " ", cleaned)
    cleaned = cleaned.replace("+", " + ")

    stopwords = {
        "who", "which", "companies", "company", "show", "list", "find",
        "since", "past", "last", "today", "ytd",
        "in", "on", "of", "the", "to", "for",
        "week", "month", "days",
    }

    tokens = []
    for t in cleaned.split():
        if not t:
            continue
        if t in stopwords:
            continue
        # drop amount tokens like 500k / 2m / 1.2b (we already extracted)
        if AMOUNT_TOKEN_RE.match(t):
            continue
        tokens.append(t)

    cleaned = " ".join(tokens).replace(" + ", "+").strip()
    if cleaned:
        filters["keyword"] = cleaned

    apply_date_preset(filters)
    return {"query": query, "mode": mode, "filters": filters, "action": action}


def filter_rows_funding(rows: List[Dict[str, Any]], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
    from_d = _parse_iso(filters.get("from_date"))
    to_d = _parse_iso(filters.get("to_date"))

    keyword = filters.get("keyword")
    geo = filters.get("geo")
    modality = filters.get("modality")
    therapeutic_area = filters.get("therapeutic_area")
    segment = filters.get("segment")
    min_amount_f = _parse_amount_filter(filters.get("min_amount"))
    max_amount_f = _parse_amount_filter(filters.get("max_amount"))

    company = filters.get("company")
    round_q = filters.get("round")
    small_molecule = filters.get("small_molecule")

    # If user typed "500k" inside keyword, treat it as min_amount if not already set
    if keyword and min_amount_f is None:
        implied = _extract_amount_from_query_text(str(keyword))
        if implied is not None:
            min_amount_f = implied

    terms = _split_terms(str(keyword)) if keyword else []

    out: List[Dict[str, Any]] = []
    for r in rows:
        if not _date_in_range(r.get("Funding date"), from_d, to_d):
            continue

        if terms:
            blob = " | ".join([
                str(r.get("Company", "")),
                str(r.get("Investors", "")),
                str(r.get("Description", "")),
                str(r.get("Therapeutic Area", "")),
                str(r.get("Therapeutic Modality", "")),
                str(r.get("Funding round", "")),
                str(r.get("HQ City", "")),
                str(r.get("HQ State/Region", "")),
                str(r.get("HQ Country", "")),
            ]).lower()
            if any(t not in blob for t in terms):
                continue

        if company and not _text_in(company, str(r.get("Company", ""))):
            continue
        if round_q and not _text_in(round_q, str(r.get("Funding round", ""))):
            continue

        if modality:
            if not _text_in(modality, str(r.get("Therapeutic Modality", ""))):
                sm_flag = str(r.get("Small molecule modality?", "")).lower()
                if modality.lower().startswith("small") and sm_flag in {"yes", "y", "true"}:
                    pass
                else:
                    continue

        if therapeutic_area:
            ta_field = str(r.get("Therapeutic Area", ""))
            tas = [x.strip() for x in str(therapeutic_area).split(",") if x.strip()]
            if tas and not any(_text_in(t, ta_field) for t in tas):
                continue

        if segment:
            segq = str(segment).strip().lower()
            if segq == "admet":
                segq = "admet/pk"
            blob = " | ".join([
                str(r.get("Segment", "")),
                str(r.get("Description", "")),
                str(r.get("Therapeutic Modality", "")),
                str(r.get("Therapeutic Area", "")),
                str(r.get("Investors", "")),
                str(r.get("Company", "")),
            ]).lower()
            if segq not in blob:
                continue

        if geo:
            bucket = _geo_bucket(r.get("HQ Country"))
            if not bucket or bucket.lower() != str(geo).strip().lower():
                continue

        if small_molecule:
            sm = str(r.get("Small molecule modality?", "")).strip().lower()
            if str(small_molecule).lower().startswith("y") and sm not in {"yes", "y", "true"}:
                continue
            if str(small_molecule).lower().startswith("n") and sm in {"yes", "y", "true"}:
                continue

        amt = _amount_to_number(str(r.get("Funding amount", "")))
        if min_amount_f is not None and (amt is None or amt < min_amount_f):
            continue
        if max_amount_f is not None and (amt is None or amt > max_amount_f):
            continue

        out.append(r)

    return out


def filter_rows_deals(rows: List[Dict[str, Any]], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
    from_d = _parse_iso(filters.get("from_date"))
    to_d = _parse_iso(filters.get("to_date"))

    keyword = filters.get("keyword")
    geo = filters.get("geo")
    modality = filters.get("modality")
    therapeutic_area = filters.get("therapeutic_area")
    segment = filters.get("segment")
    min_amount_f = _parse_amount_filter(filters.get("min_amount"))
    max_amount_f = _parse_amount_filter(filters.get("max_amount"))

    acquirer = filters.get("acquirer")
    target = filters.get("target")
    deal_type = filters.get("deal_type")

    if keyword and min_amount_f is None:
        implied = _extract_amount_from_query_text(str(keyword))
        if implied is not None:
            min_amount_f = implied

    terms = _split_terms(str(keyword)) if keyword else []

    out: List[Dict[str, Any]] = []
    for r in rows:
        if not _date_in_range(r.get("Deal date"), from_d, to_d):
            continue

        if terms:
            blob = " | ".join([
                str(r.get("Acquirer", "")),
                str(r.get("Target", "")),
                str(r.get("Description", "")),
                str(r.get("Therapeutic Area", "")),
                str(r.get("Modality", "")),
                str(r.get("Deal type", "")),
                str(r.get("Source", "")),
                str(r.get("Target HQ Country", "")),
            ]).lower()
            if any(t not in blob for t in terms):
                continue

        if acquirer and not _text_in(acquirer, str(r.get("Acquirer", ""))):
            continue
        if target and not _text_in(target, str(r.get("Target", ""))):
            continue
        if deal_type and not _text_in(deal_type, str(r.get("Deal type", ""))):
            continue

        if modality and not _text_in(modality, str(r.get("Modality", ""))):
            continue

        if therapeutic_area:
            ta_field = str(r.get("Therapeutic Area", ""))
            tas = [x.strip() for x in str(therapeutic_area).split(",") if x.strip()]
            if tas and not any(_text_in(t, ta_field) for t in tas):
                continue

        if segment:
            segq = str(segment).strip().lower()
            if segq == "admet":
                segq = "admet/pk"
            blob = " | ".join([
                str(r.get("Segment", "")),
                str(r.get("Description", "")),
                str(r.get("Modality", "")),
                str(r.get("Therapeutic Area", "")),
                str(r.get("Acquirer", "")),
                str(r.get("Target", "")),
            ]).lower()
            if segq not in blob:
                continue

        if geo:
            bucket = _geo_bucket(r.get("Target HQ Country"))
            if not bucket or bucket.lower() != str(geo).strip().lower():
                continue

        upfront = _amount_to_number(str(r.get("Upfront", "")))
        if min_amount_f is not None and (upfront is None or upfront < min_amount_f):
            continue
        if max_amount_f is not None and (upfront is None or upfront > max_amount_f):
            continue

        out.append(r)

    return out


def merge_rows_for_chat(rows: List[Dict[str, Any]], mode: str) -> List[Dict[str, Any]]:
    mode = (mode or "funding").lower()
    if mode != "both":
        return rows

    out: List[Dict[str, Any]] = []
    for r in rows:
        if "Funding date" in r:
            out.append({
                "Type": "Funding",
                "Date": r.get("Funding date"),
                "Company/Target": r.get("Company"),
                "Counterparty": r.get("Investors"),
                "Amount": r.get("Funding amount"),
                "Round/Deal": r.get("Funding round"),
                "Therapeutic Area": r.get("Therapeutic Area"),
                "Modality": r.get("Therapeutic Modality"),
                "Geo": _geo_bucket(r.get("HQ Country")) or "",
                "Description": r.get("Description"),
            })
        else:
            out.append({
                "Type": "Deal",
                "Date": r.get("Deal date"),
                "Company/Target": r.get("Target"),
                "Counterparty": r.get("Acquirer"),
                "Amount": r.get("Upfront"),
                "Round/Deal": r.get("Deal type"),
                "Therapeutic Area": r.get("Therapeutic Area"),
                "Modality": r.get("Modality"),
                "Geo": _geo_bucket(r.get("Target HQ Country")) or "",
                "Description": r.get("Description"),
            })

    out.sort(key=lambda x: (x.get("Date") or ""), reverse=True)
    return out


def summarize_answer(user_query: str, plan: Dict[str, Any], rows: List[Dict[str, Any]]) -> str:
    action = (plan.get("action") or {}).get("type")

    if action == "top_by_amount":
        n = int((plan.get("action") or {}).get("n", 10))

        def amt_of(r: Dict[str, Any]) -> float:
            a = r.get("Funding amount") or r.get("Upfront") or r.get("Amount") or ""
            return _amount_to_number(str(a)) or 0.0

        top = sorted(rows, key=amt_of, reverse=True)[:n]
        if not top:
            return "No matching results found."

        bullets: List[str] = []
        for r in top:
            if "Funding date" in r:
                bullets.append(
                    f"- {r.get('Company','')} — {r.get('Funding amount','')} "
                    f"({r.get('Funding round','')}, {r.get('Funding date','')})"
                )
            elif "Deal date" in r:
                bullets.append(
                    f"- {r.get('Target','')} — {r.get('Upfront','')} "
                    f"({r.get('Acquirer','')}, {r.get('Deal date','')})"
                )
            else:
                bullets.append(
                    f"- {r.get('Company/Target','')} — {r.get('Amount','')} "
                    f"({r.get('Round/Deal','')}, {r.get('Date','')})"
                )

        return "Here are the largest items in the selected set:\n" + "\n".join(bullets)

    if not rows:
        return "No matching results found."

    show = rows[:10]
    bullets: List[str] = []
    for r in show:
        if "Funding date" in r:
            bullets.append(
                f"- {r.get('Company','')} — {r.get('Funding amount','')} "
                f"({r.get('Funding round','')}, {r.get('Funding date','')})"
            )
        elif "Deal date" in r:
            bullets.append(
                f"- {r.get('Target','')} — {r.get('Upfront','')} "
                f"({r.get('Acquirer','')}, {r.get('Deal date','')})"
            )
        else:
            bullets.append(
                f"- {r.get('Company/Target','')} — {r.get('Amount','')} "
                f"({r.get('Round/Deal','')}, {r.get('Date','')})"
            )

    more = "" if len(rows) <= 10 else f"\n… and {len(rows) - 10} more."
    return f"Found {len(rows)} results. Showing the latest {min(10, len(rows))}:\n" + "\n".join(bullets) + more
