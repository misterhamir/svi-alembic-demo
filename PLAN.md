# PLAN — phased build for svi-demo

Six phases, each with explicit done-criteria. Don't move to the next phase until the current one's criteria are met.

Estimated total: 3–4 days for someone fluent in FastAPI + vanilla JS.

## Phase 0 — Scaffold (DONE by initiating agent)

✓ Folder structure (`ui/`, `backend/`, `fixtures/`, `scripts/`)
✓ Hand-off docs (`README.md`, `HANDOFF.md`, `SCOPE.md`, `ARCHITECTURE.md`, `DATA-CONTRACTS.md`, this file, `DEMO-RUNBOOK.md`)
✓ `.gitignore`
✓ Stub README in each subfolder

## Phase 1 — Backend skeleton + extraction round-trip (~half a day)

Goal: prove svi-demo backend can take a PDF and get back structured fields from the existing pf-idp-processing service.

### Tasks

1. Create `backend/pyproject.toml` (or `requirements.txt` if simpler) with: `fastapi`, `uvicorn[standard]`, `httpx`, `pydantic`, `python-dotenv`, `python-multipart`, `aiosqlite` (or skip if going JSON).
2. Create `backend/app/main.py` with a minimal FastAPI app that:
   - Mounts `/ui/` static files from `../ui/`
   - Has a `/api/health` endpoint returning `{"status": "ok"}`
3. Create `backend/app/extraction_client.py` with an async function `extract(document_bytes, schema_dict) -> dict` that:
   - Base64-encodes the bytes
   - POSTs to `${EXTRACTION_SERVICE_URL}/api/v1/extract`
   - Returns the parsed JSON response
4. Create `backend/app/schemas.py` with the two seeded schemas (Invoice, Faktur Pajak) — copy from `DATA-CONTRACTS.md`.
5. Write a test `scripts/smoke_test_extraction.py` that:
   - Reads a sample PDF from `fixtures/`
   - Calls the extraction client directly (no FastAPI involved)
   - Prints the extracted fields

### Done-criteria
- `uvicorn backend.app.main:app --port 8080` starts without error
- `curl http://localhost:8080/api/health` returns `{"status":"ok"}`
- `python scripts/smoke_test_extraction.py fixtures/sample-invoice.pdf` prints fields with non-null confidences
- The pf-idp-processing service is running on port 8000 (you may need to start it manually first — see its own README)

### Dependencies on user
- A `GEMINI_API_KEY` to start pf-idp-processing — ask if not in `.env`
- Sample PDFs in `fixtures/` — see `fixtures/README.md`. If empty, ask the user where to source them or fall back to synthetic PDFs (segment 4 of demo PRD references a sample multi-doc PDF for live extraction).

## Phase 2 — Case storage + queue + detail endpoints (~half a day)

Goal: backend has cases in storage and exposes the queue + detail endpoints.

### Tasks

1. Pick storage backend (SQLite recommended). Create `backend/app/storage.py` with:
   - `init_storage()` creating tables/files
   - `create_case(case_dict)`, `get_case(case_id)`, `list_cases(filters)`, `update_field(case_id, doc_id, field_name, new_value, actor)`, `update_state(case_id, new_state, ...)`
2. Create `backend/app/cases.py` with the route handlers for `/api/cases/*` (upload, list, get, correct, approve, reject, retry) per `DATA-CONTRACTS.md`.
3. The upload handler:
   - Saves the PDF bytes to `data/uploads/{case_id}.pdf`
   - Calls extraction (initial naive: extract once with a combined schema, or extract twice if you can detect doc boundaries cheaply — okay to start simple and split into two extractions per doc later)
   - Translates the extraction response into the case shape from DATA-CONTRACTS.md
   - Inserts the case with state `pending_review`
   - Returns `{ case_id, state, ... }`
4. Add a `/api/cases/{case_id}/document/{doc_id}.pdf` endpoint that streams the original PDF bytes — used by the browser for PDF.js rendering.
5. Add `/api/config/thresholds` returning the confidence band thresholds (see DATA-CONTRACTS.md).

### Done-criteria
- `curl -F file=@fixtures/sample-invoice.pdf -F workflow_id=ap_invoice_faktur_pajak_v1 http://localhost:8080/api/cases/upload` creates a case and returns its ID
- `curl http://localhost:8080/api/cases` lists the case
- `curl http://localhost:8080/api/cases/{id}` returns the full case detail with extracted fields
- Storage survives backend restart (if SQLite)

## Phase 3 — Mock ERP + state machine + approve/reject/retry (~half a day)

Goal: approve action transitions the case end-to-end, including the webhook fire.

### Tasks

1. Create `backend/app/mock_erp.py` with:
   - `POST /api/mock-erp/invoices` returning 201 (or 503 when toggled)
   - `POST /api/mock-erp/toggle` flipping the in-memory mode
   - State persisted to `data/mock_erp_state.json` so it survives restarts
   - Append-only log to `data/erp_log.jsonl` of every request received
2. Create `backend/app/state_machine.py` implementing the linear workflow walk:
   - `pending_review` + approve → next node from the workflow definition
   - If next node is `approval`, → `pending_approval_L1`; another approve from a manager-group user → next
   - If next node is `webhook`, fire it; on 201 → `complete`; on non-2xx → `integration_error`
   - `integration_error` + retry → re-fire the webhook (same node)
3. Wire the approve/reject/retry route handlers to call the state machine.
4. Add the `Idempotency-Key` header to webhook requests (UUID per case-node combo, deterministic so retries hit the same key).

### Done-criteria
- Approve a case → see the webhook hit `mock-erp/invoices` → case goes to `complete`
- Toggle mock ERP to 503 → approve another case → case goes to `integration_error` with response captured
- Retry on the errored case (after toggling back to 201) → case goes to `complete`
- The erp_log.jsonl file shows every attempt with timestamp + headers + body

## Phase 4 — Wire operator-queue.html (~half a day)

Goal: the operator queue page shows real cases and is clickable.

### Tasks

1. Copy `svi-alembic-ui/operator/operator-queue.html` to `svi-demo/ui/operator-queue.html`
2. Inspect the existing markup — find the table/list element where mock cases are rendered, and the column structure (case ID, age, doc count, status, etc.)
3. Append a `<script>` block at the bottom of the file (or extract to `ui/js/operator-queue.js`) that:
   - On page load, calls `GET /api/cases`
   - Replaces the hardcoded mock rows with rendered rows from real data
   - Wires each row's click handler to navigate to `case-detail.html?id=<case_id>`
   - Filter dropdowns/buttons for state should call `GET /api/cases?state=<x>` and re-render
4. Test: refresh page, see real cases. Click one, lands on case-detail page (which still shows static mock data — that's fine for now).
5. Visual: confidence color bands render based on the case's `overall_confidence` (in the table, if there's a confidence column; otherwise skip)

### Done-criteria
- Open `http://localhost:8080/ui/operator-queue.html` → see real cases from the backend
- Filter dropdown changes the queue
- Clicking a case navigates to `case-detail.html?id=<case_id>` (where Phase 5 picks up)

## Phase 5 — Wire case-detail.html (~1 full day)

Goal: case detail loads real data, click-to-highlight works, inline correction works, approve/reject/retry buttons work.

This is the most complex phase. Budget time accordingly.

### Tasks

1. Copy `svi-alembic-ui/operator/case-detail.html` to `svi-demo/ui/case-detail.html`
2. Identify the existing markup for: document tabs, extracted-data tab, action bar, history panel
3. Append JS that, on page load:
   - Reads `id` from URL query string
   - Calls `GET /api/cases/{id}`
   - Renders the documents tabs from `case.documents[]`
   - Renders the extracted-data fields from each doc's `fields[]`, color-banded by confidence
   - Renders the history panel from `case.history[]`
   - If `case.integration_error` is non-null, renders the integration-error panel
4. Add PDF.js for document rendering:
   - Load `pdfjs-dist` from CDN (no build step)
   - Render each document's PDF in its tab
5. Implement click-to-highlight:
   - When operator clicks a field in the Extracted Data tab → switch to the corresponding document tab → draw an absolutely-positioned overlay div on the PDF canvas using the field's `bounding_box` coordinates (remember to scale by the canvas's render scale vs. the PDF's native resolution stored in `page_dimensions`)
6. Implement inline correction:
   - Make field values clickable → replace with `<input>` → on Enter or blur, call `POST /api/cases/{id}/correct`
   - On success, update the field in place; provenance icon flips from AI to human
7. Wire action bar:
   - Approve button → `POST /api/cases/{id}/approve` → on success, redirect back to queue or show a toast and reload the case
   - Reject → similar, with a reason prompt
   - Retry Integration → `POST /api/cases/{id}/retry` (only visible if state is `integration_error`)

### Done-criteria
- Open a case from the queue → see real fields, real PDF, real confidence colors
- Click an amber-banded field → PDF tab activates with a highlight overlay on the right region
- Click an extracted value → type a correction → press Enter → field updates with `human-corrected` provenance indicator
- Click Approve → case advances per the workflow → ends in `complete` (in default mock-ERP mode) or `integration_error` (if toggled to 503)
- On `integration_error`, the error panel shows; Retry button works

## Phase 6 — Static walkthrough screens + reset script + runbook test (~half a day)

Goal: copy in the rest of the demo screens, write the reset script, run through DEMO-RUNBOOK end-to-end.

### Tasks

1. Copy these screens from `svi-alembic-ui/admin/` to `svi-demo/ui/`:
   - `dashboard.html`, `canvas-editor.html`, `workflows.html`, `node-configuration.html`, `configuration-sidebar.html`
   - `schema-library.html`, `create-schema-step1.html` through `step4.html`
   - `users-roles.html`, `instance-monitor.html`, `deployments.html`
2. Update each screen's nav links so they point to the right paths (relative to `/ui/`).
3. Create a top-level `index.html` in `ui/` that links to the demo's natural entry points (operator queue, admin dashboard) — useful as a demo-presenter starting page.
4. Create `scripts/seed.py`:
   - Reset all storage (delete `data/`, recreate)
   - Read each PDF in `fixtures/seed-cases/`
   - Upload each to the backend (or directly insert via storage layer)
   - Print a summary: "Seeded N cases"
5. Create `scripts/reset.py`:
   - Wipe `data/`, re-run seed
6. Walk through `DEMO-RUNBOOK.md` from a clean state. Note any gaps. Fix.

### Done-criteria
- Reset script gets the demo to a known seed state in <30 seconds
- Static walkthrough screens are reachable from the operator/admin landing pages
- DEMO-RUNBOOK can be followed by someone else (not the agent who built this) without questions

## What you (the next agent) should NOT build

Per `SCOPE.md`. If you find yourself building these, stop:

- Any kind of build step (webpack, vite, esbuild) for the UI — keep it static HTML
- A real database with migrations
- Multi-tenancy / real auth
- The HonoX portal-app — explicitly out of scope
- Real ERP integration depth — mock is fine
- Auto-advance / Gate node logic — palette-only at MVP, not in the demo

## When to stop and ask

Use the AskUserQuestion tool with one question + recommendation when:
- You hit one of the open questions in `HANDOFF.md`
- You discover the source folders have changed since this plan was written
- A phase's done-criteria can't be met for a reason that needs a product decision (not a technical workaround)
- You're about to spend more than half a day on something not listed in this plan

Don't ask when:
- A library choice is purely technical (pick the simplest thing that works)
- A naming or formatting choice has no product impact
- You can verify by reading the source folders
