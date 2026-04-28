"""Mock ERP — the receiving side of the integration webhook.

Mental model: this is what we'd hit in a real prospect's environment, but for
the demo it lives inside the same FastAPI app. Default mode returns 201 like a
healthy ERP. Toggle it to 503 to demonstrate the integration-error -> Retry
flow (segment 6 of the demo).

State is persisted to disk (data/mock_erp_state.json) so toggling sticks across
restarts. Every request gets appended to data/erp_log.jsonl as an audit trail.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/mock-erp", tags=["mock_erp"])


def _state_file() -> Path:
    return get_settings().data_dir / "mock_erp_state.json"


def _log_file() -> Path:
    return get_settings().data_dir / "erp_log.jsonl"


def get_mode() -> str:
    """Read current mode from disk. Defaults to '201' on first run."""
    p = _state_file()
    if not p.exists():
        return "201"
    try:
        return json.loads(p.read_text()).get("mode", "201")
    except Exception:
        return "201"


def set_mode(mode: str) -> str:
    """Persist a new mode. Caller validates the value first."""
    p = _state_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"mode": mode}))
    logger.info("mock-erp mode set to %s", mode)
    return mode


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _append_log(entry: dict[str, Any]) -> None:
    p = _log_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as fh:
        fh.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------------------
# POST /api/mock-erp/invoices
# ---------------------------------------------------------------------------

@router.post("/invoices")
async def receive_invoice(request: Request):
    """The endpoint the demo backend posts to when a case advances past the
    webhook node. Returns 201 normally, 503 when toggled."""
    mode = get_mode()
    body_bytes = await request.body()
    try:
        body_json = json.loads(body_bytes) if body_bytes else None
    except Exception:
        body_json = None

    log_entry = {
        "at": _now_iso(),
        "mode": mode,
        "headers": {k: v for k, v in request.headers.items()
                    if k.lower() in {"idempotency-key", "x-api-key", "content-type"}},
        "body": body_json,
    }

    if mode == "503":
        log_entry["response"] = {"status": 503, "body": {"error": "erp_unavailable"}}
        _append_log(log_entry)
        return JSONResponse(
            status_code=503,
            content={"error": "erp_unavailable", "retry_after_seconds": 30},
        )

    # 201 path — synthesise an erp_record_id deterministically per
    # idempotency key so retries return the same id (real ERP behaviour).
    idem = request.headers.get("idempotency-key")
    erp_record_id = f"INV-EXT-{(hash(idem) & 0xFFFF):04d}" if idem else f"INV-EXT-{uuid4().hex[:6].upper()}"
    body_resp = {"erp_record_id": erp_record_id, "received_at": _now_iso()}
    log_entry["response"] = {"status": 201, "body": body_resp}
    _append_log(log_entry)
    return JSONResponse(status_code=201, content=body_resp)


# ---------------------------------------------------------------------------
# POST /api/mock-erp/toggle
# ---------------------------------------------------------------------------

class ToggleRequest(BaseModel):
    mode: str  # "201" or "503"


@router.post("/toggle")
def toggle(body: ToggleRequest):
    if body.mode not in {"201", "503"}:
        raise HTTPException(
            status_code=400,
            detail="mode must be '201' or '503'",
        )
    set_mode(body.mode)
    return {"mode": body.mode}


# ---------------------------------------------------------------------------
# GET /api/mock-erp/status — convenience for the demo presenter / runbook
# ---------------------------------------------------------------------------

@router.get("/status")
def status():
    return {"mode": get_mode()}
