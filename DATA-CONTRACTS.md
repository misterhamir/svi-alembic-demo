# DATA-CONTRACTS — JSON shapes and API endpoints

This is the wire format between browser, svi-demo backend, and pf-idp-processing. Stick to these shapes; the next agent shouldn't have to guess.

## svi-demo backend API

Base URL: `http://localhost:8080/api`

### POST `/api/cases/upload`

Upload a multi-doc PDF, trigger extraction, return the created case.

**Request:** `multipart/form-data` with:
- `file` — the PDF file
- `workflow_id` — string, e.g. `"ap_invoice_faktur_pajak_v1"` (defaults to the seeded workflow)
- `subject` — optional string, free-text label like `"Acme Vendor — INV-2026-001"`

**Response 201:**
```json
{
  "case_id": "case_01HZK...",
  "state": "pending_review",
  "created_at": "2026-04-27T09:15:00Z",
  "subject": "Acme Vendor — INV-2026-001"
}
```

**Response 500:** `{ "error": { "code": "...", "message": "..." } }`

The backend's responsibility on this call: store the PDF, call the extraction service per document type detected (initially: classify all pages as Invoice or Faktur Pajak via simple heuristic or single-call extraction with a combined schema), persist the result, return immediately. Extraction is synchronous in the demo for simplicity — the client waits.

### GET `/api/cases`

Returns the queue.

**Query params (all optional):**
- `state` — filter to one of `pending_review | pending_approval_L1 | integration_error | complete | rejected`
- `limit` — default 50

**Response 200:**
```json
{
  "cases": [
    {
      "case_id": "case_01HZK...",
      "subject": "Acme Vendor — INV-2026-001",
      "state": "pending_review",
      "created_at": "2026-04-27T09:15:00Z",
      "doc_count": 2,
      "overall_confidence": 0.87,
      "responsible": { "type": "group", "value": "AP_clerk" }
    }
  ],
  "total": 12
}
```

### GET `/api/cases/{case_id}`

Full case detail for the case-detail page.

**Response 200:**
```json
{
  "case_id": "case_01HZK...",
  "subject": "Acme Vendor — INV-2026-001",
  "state": "pending_review",
  "created_at": "2026-04-27T09:15:00Z",
  "workflow_id": "ap_invoice_faktur_pajak_v1",
  "current_node": "review",
  "responsible": { "type": "group", "value": "AP_clerk" },
  "documents": [
    {
      "doc_id": "doc_01...",
      "document_type": "commercial_invoice",
      "schema_id": "schema_invoice_v1",
      "page_range": [1, 1],
      "page_count": 1,
      "page_dimensions": [{ "page": 1, "width": 1240, "height": 1754 }],
      "pdf_url": "/api/cases/case_01HZK.../document/doc_01...pdf",
      "fields": [
        {
          "name": "vendor_name",
          "value": "Acme Indonesia",
          "confidence": 0.94,
          "bounding_box": { "x": 120, "y": 80, "width": 240, "height": 28, "page": 1 },
          "field_type": "string",
          "description": "Vendor name as printed on the invoice",
          "provenance": "ai",
          "history": []
        },
        {
          "name": "invoice_total",
          "value": "12500000",
          "confidence": 0.78,
          "bounding_box": { "x": 800, "y": 950, "width": 160, "height": 28, "page": 1 },
          "field_type": "number",
          "provenance": "ai",
          "history": []
        }
      ]
    },
    {
      "doc_id": "doc_02...",
      "document_type": "faktur_pajak",
      "schema_id": "schema_faktur_pajak_v1",
      "page_range": [2, 2],
      "page_count": 1,
      "fields": [/* ... DPP, PPN, etc. ... */]
    }
  ],
  "history": [
    { "at": "2026-04-27T09:15:00Z", "actor": "system", "event": "case_created" },
    { "at": "2026-04-27T09:15:08Z", "actor": "system", "event": "extraction_complete", "detail": { "overall_confidence": 0.87 } }
  ],
  "integration_error": null
}
```

If `state == "integration_error"`, populate `integration_error`:
```json
"integration_error": {
  "at": "2026-04-27T09:18:00Z",
  "endpoint": "http://localhost:8080/api/mock-erp/invoices",
  "status_code": 503,
  "response_body": "{ \"error\": \"erp_unavailable\" }",
  "retry_count": 0
}
```

### POST `/api/cases/{case_id}/correct`

Operator corrects a field inline.

**Request:**
```json
{
  "doc_id": "doc_01...",
  "field_name": "invoice_total",
  "new_value": "12500000",
  "actor": "user_jane_doe"
}
```

**Response 200:** the updated field object (same shape as inside `documents[].fields[]`), with `provenance: "human"` and a new entry in `history`:
```json
{
  "name": "invoice_total",
  "value": "12500000",
  "confidence": 0.78,
  "bounding_box": { /* unchanged */ },
  "field_type": "number",
  "provenance": "human",
  "history": [
    { "at": "2026-04-27T09:16:30Z", "actor": "user_jane_doe", "from": "12,500,00", "to": "12500000" }
  ]
}
```

### POST `/api/cases/{case_id}/approve`

Operator approves the case. State machine advances per the seeded workflow.

**Request:**
```json
{ "actor": "user_jane_doe" }
```

**Response 200:**
```json
{
  "case_id": "case_01HZK...",
  "state": "complete",            // or "pending_approval_L1", or "integration_error"
  "transitioned_at": "2026-04-27T09:17:00Z",
  "next_action": null,            // or "awaiting_manager_approval", "review_integration_error"
  "integration_result": {         // present iff webhook fired during this transition
    "endpoint": "http://localhost:8080/api/mock-erp/invoices",
    "status_code": 201,
    "erp_record_id": "INV-EXT-9921"
  }
}
```

### POST `/api/cases/{case_id}/reject`

Operator rejects the case. Sets state to `rejected`, terminal.

**Request:** `{ "actor": "user_...", "reason": "Duplicate of INV-2025-998" }`
**Response 200:** `{ "case_id": "...", "state": "rejected" }`

### POST `/api/cases/{case_id}/retry`

Admin clicks Retry Integration on an integration_error case. Re-fires the webhook.

**Response 200:** same shape as the approve response (since the same state machine step runs).

### Mock ERP

#### POST `/api/mock-erp/invoices`

The mock ERP endpoint. Returns 201 by default. Toggleable to 503.

**Request:** any JSON body — backend just logs it.

**Response 201:**
```json
{ "erp_record_id": "INV-EXT-9921", "received_at": "2026-04-27T09:17:00Z" }
```

**Response 503 (when toggled):**
```json
{ "error": "erp_unavailable", "retry_after_seconds": 30 }
```

#### POST `/api/mock-erp/toggle`

Demo control: flip the mock ERP between 201 and 503 modes.

**Request:** `{ "mode": "201" }` or `{ "mode": "503" }`
**Response 200:** `{ "mode": "201" }`

This endpoint is for the demo presenter; in a real product it would not exist.

## pf-idp-processing API (existing — do not modify)

Base URL: `http://localhost:8000/api/v1`

### POST `/api/v1/extract`

Already documented in the existing service. The svi-demo backend calls this; do not call from the browser.

**Request:**
```json
{
  "document": "<base64-encoded PDF or image bytes>",
  "schema": {
    "type": "object",
    "properties": {
      "vendor_name": { "type": "string", "description": "Vendor name as printed" },
      "invoice_total": { "type": "number", "description": "Total amount due" }
    },
    "required": ["vendor_name", "invoice_total"]
  }
}
```

If `schema` is omitted, the service runs in discovery mode (auto-detect fields) — useful for the Run Discovery flow if you choose to demo it; not required for the heart-of-pitch path.

**Response 200:**
```json
{
  "fields": [
    {
      "name": "vendor_name",
      "value": "Acme Indonesia",
      "confidence": 0.94,
      "bounding_box": { "x": 120, "y": 80, "width": 240, "height": 28, "page": 1 },
      "field_type": "string",
      "description": "Vendor name as printed",
      "children": null
    }
  ],
  "overall_confidence": 0.87,
  "page_count": 1,
  "pages_processed": 1,
  "page_dimensions": [{ "page": 1, "width": 1240, "height": 1754 }]
}
```

The svi-demo backend translates this into its own case representation — it does not pass the response through to the browser unchanged. Translation rules:
- Each `field` from extraction → a field in the case's `documents[<i>].fields[]`
- `field.confidence` → keep as-is
- `field.bounding_box` → keep as-is (browser uses it for highlight overlay)
- Provenance starts as `"ai"`; flips to `"human"` only when the operator corrects
- `history` starts as `[]`

## Schema definitions for the seeded document types

These are the JSON schemas the svi-demo backend passes to pf-idp-processing during extraction. Keep them in `backend/seed/schemas.py` or similar.

### `schema_invoice_v1` (Commercial Invoice)

```python
{
  "type": "object",
  "properties": {
    "vendor_name": {"type": "string", "description": "Vendor name as printed"},
    "vendor_npwp": {"type": "string", "description": "Vendor NPWP / tax ID"},
    "invoice_number": {"type": "string", "description": "Invoice number"},
    "invoice_date": {"type": "string", "description": "Invoice issue date (YYYY-MM-DD)"},
    "due_date": {"type": "string", "description": "Payment due date (YYYY-MM-DD)"},
    "currency": {"type": "string", "description": "Currency code, e.g. IDR"},
    "invoice_total": {"type": "number", "description": "Total amount due"},
    "tax_amount": {"type": "number", "description": "Tax / VAT amount"},
    "line_items": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "description": {"type": "string"},
          "quantity": {"type": "number"},
          "unit_price": {"type": "number"},
          "amount": {"type": "number"}
        }
      }
    },
    "terms": {"type": "string", "description": "Payment terms"}
  },
  "required": ["vendor_name", "invoice_number", "invoice_total"]
}
```

### `schema_faktur_pajak_v1`

```python
{
  "type": "object",
  "properties": {
    "pkp_name": {"type": "string", "description": "PKP (taxpayer) name"},
    "pkp_npwp": {"type": "string", "description": "PKP NPWP"},
    "lawan_transaksi_npwp": {"type": "string", "description": "Counterparty NPWP"},
    "faktur_pajak_number": {"type": "string", "description": "Faktur Pajak serial number"},
    "transaction_date": {"type": "string", "description": "Transaction date"},
    "dpp": {"type": "number", "description": "DPP — taxable base"},
    "ppn": {"type": "number", "description": "PPN — VAT amount"},
    "ppnbm": {"type": "number", "description": "PPnBM — luxury tax (if applicable)"}
  },
  "required": ["pkp_npwp", "lawan_transaksi_npwp", "faktur_pajak_number", "dpp", "ppn"]
}
```

## Confidence thresholds (for color bands)

These belong in a shared constant in the backend, exposed via an endpoint like `GET /api/config/thresholds` so the browser can fetch them rather than hardcode them.

| Band | Range | Color (hex) | Meaning |
|---|---|---|---|
| Green | confidence ≥ 0.85 | `#385723` / bg `#E2EFDA` | High confidence — safe to skim |
| Amber | 0.70 ≤ confidence < 0.85 | `#806000` / bg `#FFF2CC` | Worth a second look |
| Red | confidence < 0.70 | `#823535` / bg `#FBE4E4` | Verify against source |

The "highlight threshold" per schema (default 0.75) is an additional knob for which fields draw attention; for the demo, just use the bands above.

## Workflow definition (seeded)

The seed script registers a single workflow: `ap_invoice_faktur_pajak_v1`. Stored as JSON in `backend/seed/workflows.py`:

```python
{
  "id": "ap_invoice_faktur_pajak_v1",
  "name": "AP Invoice + Faktur Pajak",
  "version": 1,
  "status": "active",
  "nodes": [
    {"id": "n1", "type": "intake"},
    {"id": "n2", "type": "classify",
     "config": {"expected_schemas": ["schema_invoice_v1", "schema_faktur_pajak_v1"]}},
    {"id": "n3", "type": "extract",
     "config": {"schema_pinning": {"commercial_invoice": "schema_invoice_v1",
                                   "faktur_pajak": "schema_faktur_pajak_v1"}}},
    {"id": "n4", "type": "validate",
     "config": {"rules": [
       {"operand_a": "invoice.invoice_total", "comparator": "=", "operand_b": "sum(invoice.line_items.amount)",
        "fail_action": "warn"}
     ], "match_mode": "ALL"}},
    {"id": "n5", "type": "review",
     "config": {"responsible": {"type": "group", "value": "AP_clerk"}}},
    {"id": "n6", "type": "approval",
     "config": {"levels": [
       {"label": "Verify", "responsible": {"type": "group", "value": "AP_manager"}}
     ]}},
    {"id": "n7", "type": "webhook",
     "config": {
       "url": {"production": "http://localhost:8080/api/mock-erp/invoices",
               "sandbox": "http://localhost:8080/api/mock-erp/invoices"},
       "auth": {"method": "api_key", "header": "X-API-Key", "value": "demo-key"},
       "payload_mapping": {
         "vendor_id": "{{invoice.vendor_npwp}}",
         "vendor_name": "{{invoice.vendor_name}}",
         "amount": "{{invoice.invoice_total}}",
         "currency": "{{invoice.currency}}",
         "invoice_number": "{{invoice.invoice_number}}"
       },
       "idempotency_key_header": "Idempotency-Key"
     }},
    {"id": "n8", "type": "end_success"}
  ],
  "edges": [
    {"from": "n1", "to": "n2"}, {"from": "n2", "to": "n3"},
    {"from": "n3", "to": "n4"}, {"from": "n4", "to": "n5"},
    {"from": "n5", "to": "n6"}, {"from": "n6", "to": "n7"},
    {"from": "n7", "to": "n8"}
  ]
}
```

The state machine in the backend can be a simple linear walk — the demo workflow has no Switch or Gate, so no branching logic needed at runtime.
