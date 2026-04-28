"""Translate raw extractor output into the case shape from DATA-CONTRACTS.md.

This is the bridge between two contracts:
- Input:  what extractor.extract_for_demo returns (matches pf-idp-processing's
          response shape)
- Output: a case dict with documents[] / fields[] as the browser expects

Mental model: this is the "Edit Fields" node in n8n right after the HTTP
extraction call — it reshapes one envelope into another and adds metadata
(provenance=ai, history=[], document_type, schema_id) that the source response
doesn't carry.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


# Maps schema_id to the human-facing document_type label used in tabs/UI.
# Mirrors the workflow's `classify` node config (DATA-CONTRACTS.md).
_SCHEMA_TO_DOC_TYPE: dict[str, str] = {
    "schema_invoice_v1": "commercial_invoice",
    "schema_faktur_pajak_v1": "faktur_pajak",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_document(
    extraction: dict[str, Any],
    *,
    schema_id: str,
    page_offset: int = 0,
) -> dict[str, Any]:
    """Build one document entry from one extractor response."""
    doc_id = f"doc_{uuid4().hex[:12]}"
    document_type = _SCHEMA_TO_DOC_TYPE.get(schema_id, "unknown")

    # Translate fields: the wire shape is already very close, we just need
    # to add provenance and history (DATA-CONTRACTS.md case fields).
    fields: list[dict[str, Any]] = []
    for f in extraction.get("fields", []):
        fields.append({
            "name": f.get("name"),
            "value": f.get("value"),
            "confidence": f.get("confidence"),
            "bounding_box": f.get("bounding_box"),
            "field_type": f.get("field_type", "string"),
            "description": f.get("description"),
            "provenance": "ai",
            "history": [],
        })

    page_count = extraction.get("page_count") or 1
    page_dimensions = extraction.get("page_dimensions") or [
        {"page": 1, "width": 1240, "height": 1754}
    ]

    return {
        "doc_id": doc_id,
        "document_type": document_type,
        "schema_id": schema_id,
        "page_range": [1 + page_offset, page_count + page_offset],
        "page_count": page_count,
        "page_dimensions": page_dimensions,
        "pdf_url": None,  # filled in by the route — needs the case_id
        "overall_confidence": extraction.get("overall_confidence"),
        "fields": fields,
    }


def build_case(
    *,
    case_id: str,
    subject: str | None,
    workflow_id: str,
    documents: list[dict[str, Any]],
) -> dict[str, Any]:
    created = now_iso()
    history = [
        {"at": created, "actor": "system", "event": "case_created"},
        {"at": now_iso(), "actor": "system", "event": "extraction_complete",
         "detail": {
             "doc_count": len(documents),
             "overall_confidences": [d.get("overall_confidence") for d in documents],
         }},
    ]
    return {
        "case_id": case_id,
        "subject": subject,
        "state": "pending_review",
        "created_at": created,
        "workflow_id": workflow_id,
        "current_node": "review",
        "responsible": {"type": "group", "value": "AP_clerk"},
        "documents": documents,
        "history": history,
        "integration_error": None,
    }
