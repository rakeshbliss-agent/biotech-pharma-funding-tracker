from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .nlp import interpret_query, filter_rows, summarize_answer

APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parent
DATA_FILE = APP_DIR / "funding_data.json"
WEB_DIR = REPO_ROOT / "web"

app = FastAPI(title="Biotech/Pharma Funding Tracker", version="1.0.0")


def load_data() -> List[Dict[str, Any]]:
    if not DATA_FILE.exists():
        return []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def sort_data(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(rows, key=lambda r: (r.get("Funding date") or ""), reverse=True)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/funding")
def get_funding(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    company: Optional[str] = None,
    round: Optional[str] = None,
    hq_state: Optional[str] = None,
    hq_city: Optional[str] = None,
    small_molecule: Optional[str] = None,
    limit: int = 50000,
):
    rows = sort_data(load_data())
    filters = {
        "from_date": from_date,
        "to_date": to_date,
        "company": company,
        "round": round,
        "hq_state": hq_state,
        "hq_city": hq_city,
        "small_molecule": small_molecule,
    }
    filtered = filter_rows(rows, filters)
    return {"count": len(filtered), "rows": filtered[: max(1, min(limit, 50000))]}


class ChatRequest(BaseModel):
    query: str


@app.post("/api/chat")
def chat(req: ChatRequest):
    rows = sort_data(load_data())
    plan = interpret_query(req.query)
    filtered = filter_rows(rows, plan.get("filters", {}))
    answer = summarize_answer(req.query, plan, filtered)
    return {"query": req.query, "plan": plan, "answer": answer, "count": len(filtered), "rows": filtered[:500]}


# Serve front-end
app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")


@app.get("/")
def root():
    index_file = WEB_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=500, detail="web/index.html not found")
    return FileResponse(str(index_file))
