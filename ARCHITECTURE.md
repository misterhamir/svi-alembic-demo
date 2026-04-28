# ARCHITECTURE — how the pieces fit

## The three running pieces

During a prospect demo, three processes run on the demo presenter's laptop:

```
┌─────────────────────────────────────────────────────────────────┐
│  Browser (the prospect sees this)                               │
│  http://localhost:8080                                          │
│  - operator-queue.html, case-detail.html (live-wired)           │
│  - canvas-editor.html, schema-library.html, etc. (static)       │
└──────────────────────────┬──────────────────────────────────────┘
                           │ fetch() calls to /api/*
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  svi-demo backend  (FastAPI, port 8080)                         │
│  ✦ this folder builds this ✦                                    │
│                                                                 │
│  Routes:                                                        │
│   POST /api/cases/upload         → store PDF, trigger extract   │
│   GET  /api/cases                → list (queue)                 │
│   GET  /api/cases/{id}           → case detail + fields         │
│   POST /api/cases/{id}/correct   → update a field               │
│   POST /api/cases/{id}/approve   → advance state, fire webhook  │
│   POST /api/cases/{id}/retry     → re-fire integration webhook  │
│   POST /api/mock-erp/invoices    → returns 201 (or 503 if toggled) │
│   POST /api/mock-erp/toggle      → flip 201/503 mode (demo only)│
│                                                                 │
│  Storage: SQLite or JSON file (see HANDOFF "Open questions")    │
│  Static files: serves /ui/* from the svi-demo/ui/ folder        │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP POST /api/v1/extract
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  pf-idp-processing  (FastAPI, port 8000)                        │
│  ✦ already exists, do not modify ✦                              │
│                                                                 │
│  Real Gemini multimodal extraction with confidence + bbox       │
└─────────────────────────────────────────────────────────────────┘
```

## Data flow — operator daily flow

### A — Pre-demo: seed cases

A seed script runs against svi-demo backend. For each sample PDF in `fixtures/`:

1. Read PDF bytes, base64-encode
2. POST to pf-idp-processing `/api/v1/extract` with the appropriate schema (Commercial Invoice or Faktur Pajak)
3. Receive structured fields with confidence + bbox
4. Insert a Case row into svi-demo storage with state=`pending_review`, fields stored as JSON

The queue is now populated.

### B — During the demo: operator reviews a case

1. Browser opens `operator-queue.html` → JS calls `GET /api/cases` → renders queue
2. Browser clicks a case → opens `case-detail.html?id=XYZ` → JS calls `GET /api/cases/XYZ`
3. Backend returns: case metadata + extracted fields with `{ name, value, confidence, bounding_box, provenance: 'ai' }` for each field
4. Browser renders fields in the Extracted Data tab, color-banded by confidence (green ≥0.85, amber 0.70–0.85, red <0.70)
5. Browser renders the source PDF in the Documents tab (PDF.js or page-image rendering)
6. Operator clicks an amber field → JS triggers Documents tab + draws bounding-box overlay using the field's `bounding_box` data
7. Operator types correction → JS calls `POST /api/cases/XYZ/correct` with `{ field_name, new_value }` → backend updates field, flips provenance to `human` → returns updated case
8. Operator clicks Approve → JS calls `POST /api/cases/XYZ/approve` → backend advances state machine

### C — State machine (segment 6 close)

A case has these states:
- `pending_review` — operator has not yet approved
- `pending_approval_L1` (optional, if workflow has approval levels) — manager review
- `posting_to_erp` — backend is firing the webhook now (transient)
- `complete` — ERP returned 201, case is done
- `integration_error` — ERP returned 5xx, case shows in queue with error panel

The approve action transitions `pending_review` → (`pending_approval_L1` or `posting_to_erp`). The state machine logic lives in the backend; the seed workflow has Review → Approval → Webhook → End Success.

When entering `posting_to_erp`, backend fires `POST http://localhost:8080/api/mock-erp/invoices` with the case's structured data. Result drives the next transition:
- 201 → `complete`
- 5xx → `integration_error` (with response captured in case record)

The mock ERP can be toggled via `POST /api/mock-erp/toggle` to switch between 201 and 503 mode. The demo presenter triggers this between Segment 5 and Segment 6 to set up the Retry Integration story.

### D — Retry Integration

From the case-detail integration-error panel, admin clicks Retry → `POST /api/cases/XYZ/retry` → backend re-fires the webhook. If mock ERP is back to 201 mode, case completes.

## Where state lives

```
svi-demo/backend/data/   ← created at runtime
  cases.db (or cases.json)   ← case state
  uploads/                   ← uploaded PDFs (also seeded)
  erp_log.jsonl              ← every ERP webhook attempt, append-only
  mock_erp_state.json        ← current 201/503 toggle
```

The reset script (`scripts/reset.py` or similar) deletes `data/` and re-runs the seed. Demo starts clean every time.

## Why FastAPI for the backend

- pf-idp-processing is already FastAPI, so the demo uses the same dependency tree (`pyproject.toml` can share much of it)
- Async HTTP client for calling the extraction service (`httpx`) is trivial
- Pydantic models give us request/response validation for free
- Static-file serving is one line for the UI

If you (the next agent) want to use Node/Express instead, that's fine — flag it to the user with a one-question recommendation. The downside: you'd need to call the Python extraction service over HTTP from Node, which works but adds a process boundary. Stick with FastAPI unless you have a reason.

## Static UI strategy

The svi-alembic-ui screens are static HTML with Tailwind. To make them live-wireable without rewriting them in a framework:

1. Copy each needed HTML file into `svi-demo/ui/`
2. For the live screens (`operator-queue.html`, `case-detail.html`), append a `<script>` block (or include an external JS file) that:
   - Fetches data from the backend on page load
   - Replaces the hardcoded mock data in the existing markup with real data
   - Wires button click handlers (Approve, Correct, Retry) to the backend
3. For the static screens, leave them untouched

This keeps the visual design intact without porting to React. If a screen turns out to need too much JS to wire, that's a signal to consider a framework — flag it to the user.

## What lives in `ui/` vs. `backend/static/`

The convention: `svi-demo/ui/` is the source of truth for static files; the FastAPI backend mounts that directory as `/ui/*`. There's no build step.

If you find yourself wanting a build step, stop and check with the user first. The point of using svi-alembic-ui's static HTML is to avoid build-toolchain overhead.

## Logging and observability

For demo robustness, log every backend call to stdout with timestamps. The demo presenter watches the terminal in case something hangs. Don't add OpenTelemetry, don't add structured logging libraries — `print(f"[{timestamp}] ...")` is fine.

## Configuration

Single `.env` file in `backend/` with:
- `EXTRACTION_SERVICE_URL` (default `http://localhost:8000`)
- `GEMINI_API_KEY` (passed through to pf-idp-processing if you start it from this folder; otherwise unused)
- `STORAGE_BACKEND` (`sqlite` or `json`)
- `LOG_LEVEL` (default `INFO`)

`.env.example` is checked in; `.env` is gitignored.
