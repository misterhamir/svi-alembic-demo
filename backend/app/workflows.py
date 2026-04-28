"""Seeded workflow definitions + read-only routes.

Mirrors the workflow JSON in DATA-CONTRACTS.md. The state machine in
state_machine.py walks this in code; the canvas page (`/ui/canvas-editor.html`)
fetches it via these routes to render a view-only diagram. Editing is out of
scope for the demo — workflows are configured by SVI deployment per tenant.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


AP_INVOICE_FAKTUR_PAJAK_V1 = {
    "id": "ap_invoice_faktur_pajak_v1",
    "name": "AP Invoice + Faktur Pajak",
    "version": 1,
    "status": "active",
    "description": "Standard Indonesian AP intake — Commercial Invoice + Faktur Pajak with manager approval and ERP webhook close.",
    "nodes": [
        {"id": "n1", "type": "intake", "label": "Intake",
         "config": {"sources": ["Email", "Manual Upload"]}},
        {"id": "n2", "type": "classify", "label": "Classify",
         "config": {"expected_schemas": ["schema_invoice_v1", "schema_faktur_pajak_v1"]}},
        {"id": "n3", "type": "extract", "label": "Extract",
         "config": {"schema_pinning": {"commercial_invoice": "schema_invoice_v1",
                                       "faktur_pajak": "schema_faktur_pajak_v1"}}},
        {"id": "n4", "type": "validate", "label": "Validate",
         "config": {"rules": [
             {"operand_a": "invoice.invoice_total",
              "comparator": "=",
              "operand_b": "sum(invoice.line_items.amount)",
              "fail_action": "warn"}
         ], "match_mode": "ALL"}},
        {"id": "n5", "type": "review", "label": "Review",
         "config": {"responsible": {"type": "group", "value": "AP_clerk"}}},
        {"id": "n6", "type": "approval", "label": "Approval",
         "config": {"levels": [
             {"label": "Verify", "responsible": {"type": "group", "value": "AP_manager"}}
         ]}},
        {"id": "n7", "type": "webhook", "label": "Webhook → ERP",
         "config": {
             "url": {"production": "http://localhost:8080/api/mock-erp/invoices",
                     "sandbox": "http://localhost:8080/api/mock-erp/invoices"},
             "auth": {"method": "api_key", "header": "X-API-Key", "value": "demo-key"},
             "payload_mapping": {
                 "vendor_id": "{{invoice.vendor_npwp}}",
                 "vendor_name": "{{invoice.vendor_name}}",
                 "amount": "{{invoice.invoice_total}}",
                 "currency": "{{invoice.currency}}",
                 "invoice_number": "{{invoice.invoice_number}}",
             },
             "idempotency_key_header": "Idempotency-Key",
         }},
        {"id": "n8", "type": "end_success", "label": "Complete", "config": {}},
    ],
    "edges": [
        {"from": "n1", "to": "n2"},
        {"from": "n2", "to": "n3"},
        {"from": "n3", "to": "n4"},
        {"from": "n4", "to": "n5"},
        {"from": "n5", "to": "n6"},
        {"from": "n6", "to": "n7"},
        {"from": "n7", "to": "n8"},
    ],
}

WORKFLOWS = {
    AP_INVOICE_FAKTUR_PAJAK_V1["id"]: AP_INVOICE_FAKTUR_PAJAK_V1,
}


@router.get("")
def list_workflows() -> dict:
    summaries = [
        {"id": w["id"], "name": w["name"], "version": w["version"],
         "status": w["status"], "node_count": len(w["nodes"])}
        for w in WORKFLOWS.values()
    ]
    return {"workflows": summaries, "total": len(summaries)}


@router.get("/{workflow_id}")
def get_workflow(workflow_id: str) -> dict:
    wf = WORKFLOWS.get(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")
    return wf
