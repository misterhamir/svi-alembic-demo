"""Case routes — upload, list, get, document stream, plus stubs for the
correct/approve/reject/retry endpoints that get filled in Phase 3.

DATA-CONTRACTS.md is the source of truth for request/response shapes.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import ulid  # ulid-py 1.x

from .. import state_machine, storage
from ..case_builder import build_case, build_document
from ..config import get_settings
from ..extractor import extract_for_demo
from ..schemas import CONFIDENCE_BANDS, SCHEMAS
from ..state_machine import TransitionError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["cases"])


# Default workflow + which schemas to apply. Mirrors the seeded workflow
# from DATA-CONTRACTS.md (ap_invoice_faktur_pajak_v1).
_DEFAULT_WORKFLOW = "ap_invoice_faktur_pajak_v1"
_DEFAULT_SCHEMAS = ["schema_invoice_v1", "schema_faktur_pajak_v1"]


def _new_case_id() -> str:
    return f"case_{ulid.new()}"


def _document_pdf_url(case_id: str, doc_id: str) -> str:
    return f"/api/cases/{case_id}/document/{doc_id}.pdf"


# ---------------------------------------------------------------------------
# POST /api/cases/upload
# ---------------------------------------------------------------------------

@router.post("/cases/upload", status_code=201)
async def upload_case(
    file: UploadFile = File(...),
    workflow_id: str = Form(_DEFAULT_WORKFLOW),
    subject: str | None = Form(None),
):
    """Accept a PDF, run extraction (one call per schema), persist the case."""
    settings = get_settings()
    case_id = _new_case_id()

    # 1) Save the original PDF to disk first so streaming endpoints work.
    pdf_bytes = await file.read()
    pdf_path = settings.uploads_dir / f"{case_id}.pdf"
    pdf_path.write_bytes(pdf_bytes)
    logger.info("upload: case_id=%s file=%s bytes=%d", case_id, file.filename, len(pdf_bytes))

    # 2) Run extraction per schema in parallel. Each becomes one "document"
    #    in the resulting case. In stub mode this is instant; in real mode
    #    it's two Gemini calls running concurrently.
    extractions = await asyncio.gather(
        *(extract_for_demo(pdf_bytes, sid, seed=case_id) for sid in _DEFAULT_SCHEMAS),
        return_exceptions=True,
    )

    documents: list[dict[str, Any]] = []
    backends_used: list[str] = []
    for schema_id, outcome in zip(_DEFAULT_SCHEMAS, extractions):
        if isinstance(outcome, BaseException):
            logger.error("extraction failed for %s: %s", schema_id, outcome)
            continue
        extraction, backend_used = outcome
        backends_used.append(backend_used)
        doc = build_document(extraction, schema_id=schema_id)
        doc["pdf_url"] = _document_pdf_url(case_id, doc["doc_id"])
        documents.append(doc)

    if not documents:
        # Both extractions failed — surface a 500 rather than silently store
        # an empty case. The error response shape matches DATA-CONTRACTS.md.
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "EXTRACTION_FAILED",
                               "message": "all schema extractions failed"}},
        )

    # 3) Use a fallback subject if none provided. Fall back to the filename
    #    minus extension, which is what AP teams typically recognize.
    if not subject:
        subject = Path(file.filename or "uploaded").stem

    case = build_case(
        case_id=case_id,
        subject=subject,
        workflow_id=workflow_id,
        documents=documents,
    )
    await storage.create_case(case)

    logger.info(
        "case stored: %s docs=%d backends=%s state=%s",
        case_id, len(documents), backends_used, case["state"],
    )
    return JSONResponse(
        status_code=201,
        content={
            "case_id": case_id,
            "state": case["state"],
            "created_at": case["created_at"],
            "subject": subject,
            "extraction_backends": backends_used,
        },
    )


# ---------------------------------------------------------------------------
# GET /api/cases  (queue listing)
# ---------------------------------------------------------------------------

@router.get("/cases")
async def list_cases(
    state: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    rows, total = await storage.list_cases(state=state, limit=limit)
    return {"cases": rows, "total": total}


# ---------------------------------------------------------------------------
# GET /api/cases/{case_id}
# ---------------------------------------------------------------------------

@router.get("/cases/{case_id}")
async def get_case(case_id: str):
    case = await storage.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="case not found")
    return case


# ---------------------------------------------------------------------------
# GET /api/cases/{case_id}/document/{doc_id}.pdf
# ---------------------------------------------------------------------------

@router.get("/cases/{case_id}/document/{doc_id}.pdf")
async def get_document_pdf(case_id: str, doc_id: str):
    """Stream the original uploaded PDF.

    Phase 2 simplification: every document in a case shares the same source PDF,
    so we ignore doc_id and just stream `{uploads_dir}/{case_id}.pdf`. When/if
    we ever split a multi-page bundle into per-document PDFs, this is where we
    select which one to serve.
    """
    settings = get_settings()
    pdf_path = settings.uploads_dir / f"{case_id}.pdf"
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="document pdf not found")
    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"{case_id}.pdf",
    )


# ---------------------------------------------------------------------------
# GET /api/config/thresholds
# ---------------------------------------------------------------------------

@router.get("/config/thresholds")
def thresholds():
    return {"bands": CONFIDENCE_BANDS}


# ---------------------------------------------------------------------------
# Phase 3 stubs — these return 501 so the UI can detect they're not wired yet.
# ---------------------------------------------------------------------------

class CorrectRequest(BaseModel):
    doc_id: str
    field_name: str
    new_value: str
    actor: str = "user_demo"


class ApproveRequest(BaseModel):
    actor: str = "user_demo"


class RejectRequest(BaseModel):
    actor: str = "user_demo"
    reason: str | None = None


@router.post("/cases/{case_id}/correct")
async def correct_field(case_id: str, body: CorrectRequest):
    """Phase 2: persist the correction (storage layer already supports it).
    Phase 3 will refine the response shape if needed."""
    field = await storage.update_field(
        case_id=case_id,
        doc_id=body.doc_id,
        field_name=body.field_name,
        new_value=body.new_value,
        actor=body.actor,
    )
    if field is None:
        raise HTTPException(status_code=404, detail="case/doc/field not found")
    return field


@router.post("/cases/{case_id}/approve")
async def approve(case_id: str, body: ApproveRequest):
    try:
        return await state_machine.approve(case_id, actor=body.actor)
    except TransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/cases/{case_id}/reject")
async def reject(case_id: str, body: RejectRequest):
    try:
        return await state_machine.reject(case_id, actor=body.actor, reason=body.reason)
    except TransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/cases/{case_id}/retry")
async def retry(case_id: str):
    try:
        return await state_machine.retry(case_id)
    except TransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))
