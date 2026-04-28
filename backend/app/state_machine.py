"""State machine — drives a case through the seeded workflow on approve/retry.

The seeded workflow is `ap_invoice_faktur_pajak_v1` from DATA-CONTRACTS.md:
    intake -> classify -> extract -> validate -> review -> approval -> webhook -> end

For Phase 3 we only need to model the part the operator sees:
    review (pending_review)
       └─ approve ──> approval (pending_approval_L1)
                          └─ approve ──> webhook
                                            ├─ 2xx ──> complete
                                            └─ non-2xx ─> integration_error
                                                            └─ retry ─> webhook (re-fire)

Mental model: think of this like an n8n workflow's "Wait for Approval" node
followed by an "HTTP Request" node. We're hand-rolling the runner because the
demo only has one workflow and three transitions; a generic runner is overkill.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from . import storage
from .config import get_settings
from .mock_erp import get_mode  # not strictly needed but useful for debug

logger = logging.getLogger(__name__)


# Webhook URL — points at our own mock_erp router. In a real deployment this
# would be the prospect's ERP endpoint; for the demo it's localhost.
def _webhook_url() -> str:
    return f"http://localhost:8080/api/mock-erp/invoices"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _idempotency_key(case_id: str) -> str:
    """Deterministic key per case-and-node so retries hit the same id at the
    receiving end. The seeded workflow has the webhook at node n7."""
    return f"{case_id}:n7-webhook"


def _build_webhook_payload(case: dict[str, Any]) -> dict[str, Any]:
    """Pull invoice fields from the case and shape them per the workflow's
    payload_mapping. Mirrors DATA-CONTRACTS.md `n7.config.payload_mapping`."""
    invoice_doc: dict[str, Any] | None = None
    for d in case.get("documents", []):
        if d.get("document_type") == "commercial_invoice":
            invoice_doc = d
            break

    field_value: dict[str, Any] = {}
    if invoice_doc:
        for f in invoice_doc.get("fields", []):
            field_value[f["name"]] = f.get("value")

    return {
        "vendor_id": field_value.get("vendor_npwp"),
        "vendor_name": field_value.get("vendor_name"),
        "amount": field_value.get("invoice_total"),
        "currency": field_value.get("currency", "IDR"),
        "invoice_number": field_value.get("invoice_number"),
        "case_id": case["case_id"],
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class TransitionError(Exception):
    """Raised when the requested action is illegal in the current state."""


async def approve(case_id: str, actor: str) -> dict[str, Any]:
    """Advance a case one step. Returns the response shape from
    DATA-CONTRACTS.md POST /api/cases/{id}/approve."""
    case = await storage.get_case(case_id)
    if case is None:
        raise TransitionError(f"case not found: {case_id}")

    state = case["state"]

    if state == "pending_review":
        # Move into manager-approval queue.
        history_event = {
            "at": _now_iso(), "actor": actor, "event": "approved_by_clerk",
            "detail": {"from": "pending_review", "to": "pending_approval_L1"},
        }
        await storage.update_state(
            case_id, "pending_approval_L1",
            history_event=history_event,
        )
        return {
            "case_id": case_id,
            "state": "pending_approval_L1",
            "transitioned_at": _now_iso(),
            "next_action": "awaiting_manager_approval",
            "integration_result": None,
        }

    if state == "pending_approval_L1":
        # Manager approved. Fire the webhook.
        return await _fire_webhook(case, actor=actor, action="approved_by_manager")

    if state == "integration_error":
        raise TransitionError(
            "case is in integration_error — call /retry instead of /approve",
        )

    raise TransitionError(f"cannot approve from state '{state}'")


async def retry(case_id: str, actor: str = "system") -> dict[str, Any]:
    case = await storage.get_case(case_id)
    if case is None:
        raise TransitionError(f"case not found: {case_id}")

    if case["state"] != "integration_error":
        raise TransitionError(
            f"retry only valid from state 'integration_error', not '{case['state']}'",
        )

    # Bump retry_count on the existing integration_error block before re-firing.
    err = case.get("integration_error") or {}
    case["integration_error"] = {**err, "retry_count": int(err.get("retry_count", 0)) + 1}
    return await _fire_webhook(case, actor=actor, action="retry_integration")


async def reject(case_id: str, actor: str, reason: str | None) -> dict[str, Any]:
    case = await storage.get_case(case_id)
    if case is None:
        raise TransitionError(f"case not found: {case_id}")
    if case["state"] in {"complete", "rejected"}:
        raise TransitionError(f"case already terminal: state='{case['state']}'")

    history_event = {
        "at": _now_iso(), "actor": actor, "event": "rejected",
        "detail": {"reason": reason, "from": case["state"]},
    }
    await storage.update_state(case_id, "rejected", history_event=history_event)
    return {"case_id": case_id, "state": "rejected"}


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

async def _fire_webhook(case: dict[str, Any], *, actor: str, action: str) -> dict[str, Any]:
    """POST to the configured webhook URL with the mapped payload. Drive the
    state machine into either 'complete' or 'integration_error' based on the
    response status."""
    url = _webhook_url()
    payload = _build_webhook_payload(case)
    headers = {
        "Idempotency-Key": _idempotency_key(case["case_id"]),
        "X-API-Key": "demo-key",
        "Content-Type": "application/json",
    }

    logger.info("firing webhook for %s -> %s (mode=%s)", case["case_id"], url, get_mode())

    try:
        # trust_env=False skips picking up HTTP_PROXY / SOCKS_PROXY from the
        # environment. The webhook always targets localhost in the demo, so
        # going through any proxy is wrong.
        async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
            resp = await client.post(url, json=payload, headers=headers)
        status_code = resp.status_code
        body_text = resp.text
        try:
            body_json: Any = resp.json()
        except Exception:
            body_json = None
    except Exception as e:
        logger.error("webhook request errored: %s", e)
        # Treat any transport error as an integration_error. retry_count is
        # already bumped by the caller for retry; for first-time approvals it
        # starts at 0 and we increment to 1 on this entry.
        existing = case.get("integration_error") or {}
        retry_count = int(existing.get("retry_count", 0))
        await storage.update_state(
            case["case_id"], "integration_error",
            history_event={
                "at": _now_iso(), "actor": actor, "event": f"{action}_then_webhook_failed",
                "detail": {"error": str(e)},
            },
            integration_error={
                "at": _now_iso(),
                "endpoint": url,
                "status_code": 0,
                "response_body": str(e),
                "retry_count": retry_count,
            },
        )
        return {
            "case_id": case["case_id"],
            "state": "integration_error",
            "transitioned_at": _now_iso(),
            "next_action": "review_integration_error",
            "integration_result": None,
        }

    if 200 <= status_code < 300:
        erp_record_id = (body_json or {}).get("erp_record_id") if isinstance(body_json, dict) else None
        integration_result = {
            "endpoint": url,
            "status_code": status_code,
            "erp_record_id": erp_record_id,
        }
        # Clear any prior integration_error and mark complete.
        await storage.update_state(
            case["case_id"], "complete",
            history_event={
                "at": _now_iso(), "actor": actor, "event": f"{action}_webhook_success",
                "detail": integration_result,
            },
            integration_result=integration_result,
            integration_error=None,
        )
        return {
            "case_id": case["case_id"],
            "state": "complete",
            "transitioned_at": _now_iso(),
            "next_action": None,
            "integration_result": integration_result,
        }

    # Non-2xx — integration_error.
    existing = case.get("integration_error") or {}
    retry_count = int(existing.get("retry_count", 0))
    error_block = {
        "at": _now_iso(),
        "endpoint": url,
        "status_code": status_code,
        "response_body": body_text,
        "retry_count": retry_count,
    }
    await storage.update_state(
        case["case_id"], "integration_error",
        history_event={
            "at": _now_iso(), "actor": actor, "event": f"{action}_webhook_failed",
            "detail": {"status_code": status_code, "response_body_preview": body_text[:200]},
        },
        integration_error=error_block,
    )
    return {
        "case_id": case["case_id"],
        "state": "integration_error",
        "transitioned_at": _now_iso(),
        "next_action": "review_integration_error",
        "integration_result": None,
    }
