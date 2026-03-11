from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .nlp import (
    apply_date_preset,
    filter_rows_deals,
    filter_rows_funding,
    infer_mode_from_query,
    interpret_query,
    merge_rows_for_chat,
    summarize_answer,
)

APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parent

FUNDING_FILE = APP_DIR / "funding_data.json"
DEALS_FILE = APP_DIR / "deals_data.json"
WEB_DIR = REPO_ROOT / "web"

app = FastAPI(title="Biotech/Pharma Funding + Deals Tracker", version="1.2.1")


def _clean_json(obj: Any) -> Any:
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _clean_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean_json(v) for v in obj]
    return obj


def _load_list(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data = _clean_json(data)
    return data if isinstance(data, list) else []


def _sort_by_date(rows: List[Dict[str, Any]], date_key: str) -> List[Dict[str, Any]]:
    # Works only if date is ISO "YYYY-MM-DD". Missing -> "" pushes to bottom.
    return sorted(rows, key=lambda r: (r.get(date_key) or ""), reverse=True)


@app.get("/api/health")
def health():
    return {"ok": True}


def _build_filters(
    date_preset: Optional[str] = None,
    q: Optional[str] = None,
    geo: Optional[str] = None,
    modality: Optional[str] = None,
    segment: Optional[str] = None,
    therapeutic_area: Optional[str] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
) -> Dict[str, Any]:
    filters: Dict[str, Any] = {}
    if date_preset:
        filters["date_preset"] = date_preset
    if q:
        filters["keyword"] = q
    if geo:
        filters["geo"] = geo
    if modality:
        filters["modality"] = modality
    if segment:
        filters["segment"] = segment
    if therapeutic_area:
        filters["therapeutic_area"] = therapeutic_area
    if min_amount is not None:
        filters["min_amount"] = min_amount
    if max_amount is not None:
        filters["max_amount"] = max_amount

    apply_date_preset(filters)
    return filters


@app.get("/api/funding")
def api_funding(
    date_preset: Optional[str] = None,
    q: Optional[str] = None,
    geo: Optional[str] = None,
    modality: Optional[str] = None,
    segment: Optional[str] = None,
    therapeutic_area: Optional[str] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    limit: int = 50000,
):
    rows = _sort_by_date(_load_list(FUNDING_FILE), "Funding date")
    filters = _build_filters(date_preset, q, geo, modality, segment, therapeutic_area, min_amount, max_amount)
    filtered = filter_rows_funding(rows, filters)
    lim = max(1, min(int(limit), 50000))
    return {"count": len(filtered), "rows": filtered[:lim]}


@app.get("/api/deals")
def api_deals(
    date_preset: Optional[str] = None,
    q: Optional[str] = None,
    geo: Optional[str] = None,
    modality: Optional[str] = None,
    segment: Optional[str] = None,
    therapeutic_area: Optional[str] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    limit: int = 50000,
):
    rows = _sort_by_date(_load_list(DEALS_FILE), "Deal date")
    filters = _build_filters(date_preset, q, geo, modality, segment, therapeutic_area, min_amount, max_amount)
    filtered = filter_rows_deals(rows, filters)
    lim = max(1, min(int(limit), 50000))
    return {"count": len(filtered), "rows": filtered[:lim]}


@app.get("/api/both")
def api_both(
    date_preset: Optional[str] = None,
    q: Optional[str] = None,
    geo: Optional[str] = None,
    modality: Optional[str] = None,
    segment: Optional[str] = None,
    therapeutic_area: Optional[str] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    limit: int = 50000,
):
    funding = _sort_by_date(_load_list(FUNDING_FILE), "Funding date")
    deals = _sort_by_date(_load_list(DEALS_FILE), "Deal date")

    filters = _build_filters(date_preset, q, geo, modality, segment, therapeutic_area, min_amount, max_amount)

    f_rows = filter_rows_funding(funding, filters)
    d_rows = filter_rows_deals(deals, filters)

    merged = merge_rows_for_chat(f_rows + d_rows, "both")
    lim = max(1, min(int(limit), 50000))
    return {"count": len(merged), "rows": merged[:lim]}


class ChatRequest(BaseModel):
    query: str
    mode: str = "funding"  # funding | deals | both


@app.post("/api/chat")
def chat(req: ChatRequest):
    # UI-selected mode
    mode = (req.mode or "funding").lower().strip()

    # auto-switch for acquisition queries if user is on Funding tab
    inferred = infer_mode_from_query(req.query)
    if inferred == "deals" and mode == "funding":
        mode = "deals"

    plan = interpret_query(req.query, mode=mode)

    funding_rows = _sort_by_date(_load_list(FUNDING_FILE), "Funding date")
    deals_rows = _sort_by_date(_load_list(DEALS_FILE), "Deal date")

    filters = (plan.get("filters") or {}).copy()
    apply_date_preset(filters)

    if mode == "deals":
        filtered = filter_rows_deals(deals_rows, filters)
    elif mode == "both":
        f = filter_rows_funding(funding_rows, filters)
        d = filter_rows_deals(deals_rows, filters)
        filtered = merge_rows_for_chat(f + d, "both")
    else:
        filtered = filter_rows_funding(funding_rows, filters)

    answer = summarize_answer(req.query, plan, filtered)

    return {
        "query": req.query,
        "mode": mode,
        "plan": plan,
        "answer": answer,
        "count": len(filtered),
        "rows": filtered[:500],
    }


# Serve the front-end
app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")


@app.get("/")
def root():
    index_file = WEB_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=500, detail="web/index.html not found")
    return FileResponse(str(index_file))
