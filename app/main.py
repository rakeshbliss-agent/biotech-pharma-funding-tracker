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
    interpret_query,
    filter_rows_funding,
    filter_rows_deals,
    summarize_answer,
    merge_rows_for_chat,
)

APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parent

FUNDING_FILE = APP_DIR / "funding_data.json"
DEALS_FILE = APP_DIR / "deals_data.json"
WEB_DIR = REPO_ROOT / "web"

app = FastAPI(title="Biotech/Pharma Tracker", version="2.0.0")


def _clean_json(obj: Any) -> Any:
    """Convert NaN/Inf floats to None (JSON null) recursively."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _clean_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean_json(v) for v in obj]
    return obj


def _load_json_array(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Invalid JSON in {path.name} at line {e.lineno}, col {e.colno}: {e.msg}"
        ) from e

    data = _clean_json(data)
    return data if isinstance(data, list) else []


def load_funding() -> List[Dict[str, Any]]:
    return _load_json_array(FUNDING_FILE)


def load_deals() -> List[Dict[str, Any]]:
    return _load_json_array(DEALS_FILE)


def sort_by_date(rows: List[Dict[str, Any]], date_key: str) -> List[Dict[str, Any]]:
    return sorted(rows, key=lambda r: (r.get(date_key) or ""), reverse=True)


@app.get("/api/health")
def health():
    return {"ok": True, "funding_rows": len(load_funding()), "deals_rows": len(load_deals())}


@app.get("/api/funding")
def get_funding(
    # common filters
    date_preset: Optional[str] = None,  # this_week|last_7|last_30|ytd|all
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    keyword: Optional[str] = None,
    geo: Optional[str] = None,  # US|Europe|APAC|ROW
    modality: Optional[str] = None,
    therapeutic_area: Optional[str] = None,
    segment: Optional[str] = None,
    min_amount: Optional[float] = None,  # in USD
    max_amount: Optional[float] = None,  # in USD
    # funding-specific
    company: Optional[str] = None,
    round: Optional[str] = None,
    small_molecule: Optional[str] = None,  # yes|no
    limit: int = 50000,
):
    rows = sort_by_date(load_funding(), "Funding date")
    filters = {
        "date_preset": date_preset,
        "from_date": from_date,
        "to_date": to_date,
        "keyword": keyword,
        "geo": geo,
        "modality": modality,
        "therapeutic_area": therapeutic_area,
        "segment": segment,
        "min_amount": min_amount,
        "max_amount": max_amount,
        "company": company,
        "round": round,
        "small_molecule": small_molecule,
    }
    filtered = filter_rows_funding(rows, filters)
    result = {"count": len(filtered), "rows": filtered[: max(1, min(limit, 50000))]}
    return _clean_json(result)


@app.get("/api/deals")
def get_deals(
    # common filters
    date_preset: Optional[str] = None,  # this_week|last_7|last_30|ytd|all
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    keyword: Optional[str] = None,
    geo: Optional[str] = None,  # US|Europe|APAC|ROW (target geo)
    modality: Optional[str] = None,
    therapeutic_area: Optional[str] = None,
    segment: Optional[str] = None,
    min_amount: Optional[float] = None,  # in USD (upfront)
    max_amount: Optional[float] = None,  # in USD (upfront)
    # deals-specific
    acquirer: Optional[str] = None,
    target: Optional[str] = None,
    deal_type: Optional[str] = None,
    limit: int = 50000,
):
    rows = sort_by_date(load_deals(), "Deal date")
    filters = {
        "date_preset": date_preset,
        "from_date": from_date,
        "to_date": to_date,
        "keyword": keyword,
        "geo": geo,
        "modality": modality,
        "therapeutic_area": therapeutic_area,
        "segment": segment,
        "min_amount": min_amount,
        "max_amount": max_amount,
        "acquirer": acquirer,
        "target": target,
        "deal_type": deal_type,
    }
    filtered = filter_rows_deals(rows, filters)
    result = {"count": len(filtered), "rows": filtered[: max(1, min(limit, 50000))]}
    return _clean_json(result)


class ChatRequest(BaseModel):
    query: str
    mode: str = "funding"  # funding|deals|both


@app.post("/api/chat")
def chat(req: ChatRequest):
    mode = (req.mode or "funding").strip().lower()
    plan = interpret_query(req.query, mode=mode)

    funding_rows = sort_by_date(load_funding(), "Funding date")
    deals_rows = sort_by_date(load_deals(), "Deal date")

    out_rows: List[Dict[str, Any]] = []

    if mode in {"funding", "both"}:
        out_rows.extend(filter_rows_funding(funding_rows, plan.get("filters", {})))

    if mode in {"deals", "both"}:
        out_rows.extend(filter_rows_deals(deals_rows, plan.get("filters", {})))

    # For "both", normalize for display/summary
    merged = merge_rows_for_chat(out_rows, mode=mode)
    answer = summarize_answer(req.query, plan, merged)

    result = {
        "query": req.query,
        "mode": mode,
        "plan": plan,
        "answer": answer,
        "count": len(merged),
        "rows": merged[:500],
    }
    return _clean_json(result)


# Serve front-end
app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")


@app.get("/")
def root():
    index_file = WEB_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=500, detail="web/index.html not found")
    return FileResponse(str(index_file))
