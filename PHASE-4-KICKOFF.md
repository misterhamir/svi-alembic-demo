# PHASE-4-KICKOFF — picking up svi-demo in Claude Code

This is the hand-off prompt for the agent picking up at Phase 4 (UI wiring) in
your IDE. It's the Phase 4 sibling of `KICKOFF-PROMPT.md`. Paste the body of
the **Kickoff prompt for Claude Code** section below into a fresh Claude Code
session and it has everything it needs.

The previous session (Cowork, on 2026-04-27) completed Phases 1–3. Backend is
end-to-end runnable; UI is empty. Done-criteria from `PLAN.md` were met for
each phase and verified via curl.

## What's in place

### Code

```
svi-demo/backend/app/
  __init__.py
  main.py                  ← FastAPI app, lifespan, /api/health, /ui mount
  config.py                ← env-driven settings, includes SQLITE_DB_PATH override
  schemas.py               ← schema_invoice_v1, schema_faktur_pajak_v1, CONFIDENCE_BANDS
  storage.py               ← aiosqlite-backed CRUD, journal_mode=MEMORY
  case_builder.py          ← translates extractor output -> case shape
  extraction_client.py     ← async POST to pf-idp /api/v1/extract
  extractor.py             ← facade with real | stub | auto modes
  state_machine.py         ← linear walk: review -> approval -> webhook -> complete/error
  mock_erp.py              ← /api/mock-erp/{invoices,toggle,status} + JSONL log
  routes/
    __init__.py
    cases.py               ← upload, list, get, document, correct, approve, reject, retry
                             + /api/config/thresholds

svi-demo/scripts/
  smoke_test_extraction.py ← Phase 1 smoke test (needs pf-idp running)

svi-demo/fixtures/seed-cases/
  10 real Indonesian PDFs from training/source_docs (curated 2026-04-27)
  Mix of single-doc invoices, 1 standalone Faktur Pajak, 2 multi-doc bundles
```

### Endpoints — all wired, all tested

```
GET  /api/health                                      -> {"status":"ok"}
GET  /api/config/thresholds                           -> green/amber/red bands
POST /api/cases/upload    (multipart: file, workflow_id?, subject?)
GET  /api/cases?state=&limit=
GET  /api/cases/{case_id}
GET  /api/cases/{case_id}/document/{doc_id}.pdf       -> streams the original PDF
POST /api/cases/{case_id}/correct                     -> patches one field
POST /api/cases/{case_id}/approve                     -> advances state machine
POST /api/cases/{case_id}/reject
POST /api/cases/{case_id}/retry                       -> from integration_error
POST /api/mock-erp/invoices                           -> 201 default, 503 toggleable
POST /api/mock-erp/toggle                             -> {"mode": "201"|"503"}
GET  /api/mock-erp/status
```

Response shapes match `DATA-CONTRACTS.md` exactly. The mock ERP audit trail
lands in `backend/data/erp_log.jsonl` (JSONL, append-only).

## Decisions made in the previous session (not in HANDOFF.md)

These are real product/technical calls that locked in during Phases 1–3.
Future agents should treat them as decided.

1. **Two extraction backends, switchable via env.**
   `EXTRACTION_BACKEND=real|stub|auto` (default: `auto`). Stub returns plausible
   Indonesian field values + ballpark bboxes per fixture so Phase 4-5 can be
   built/demoed without an API key. Real mode calls pf-idp-processing.
   Reason: Hammam's call on 2026-04-27 — "we can put the SLM and OCR later,
   just so the demo shows end-to-end flow."
2. **One case = two documents (Invoice + Faktur Pajak).** Every upload runs both
   schemas in parallel. In real mode that's two Gemini calls per upload.
   Sidesteps classification logic for the demo and gives every case a multi-tab
   "documents" strip — which the heart-of-pitch flow needs.
3. **Fixtures as-is.** The 10 PDFs in `fixtures/seed-cases/` are real Telkom AP
   docs from `training/source_docs/`. Hammam confirmed OK to show prospects
   unredacted (utility/landlord billings, not commercially sensitive).
4. **Storage = SQLite, not JSON.** With `journal_mode=MEMORY` + `synchronous=
   NORMAL` so it works on FUSE mounts and exotic disks. On a real laptop the
   defaults are fine; the demo is durable enough.
5. **`SQLITE_DB_PATH` env var override.** Existed only because the prior
   session's sandbox couldn't write SQLite journals to its FUSE mount. **Drop
   it on a real machine** — the DB lands at `backend/data/cases.db` next to
   `uploads/`.
6. **Webhook httpx client uses `trust_env=False`.** Localhost webhooks must
   not get routed through HTTP_PROXY / SOCKS_PROXY env vars. Don't change this.

## Still-open questions (from HANDOFF.md)

These haven't been answered yet. Hit them in Phase 4–5 when relevant.

- **PDF.js vs server-rendered images** for click-to-highlight. Recommendation in
  HANDOFF.md is PDF.js (CDN, no build step). Confirm with Hammam before Phase 5.
- **Branding** (svi-alembic-ui has a generic look). Recommendation: ship as-is.
- **Hosting** (localhost vs staging URL). Recommendation: localhost first.

Already-answered: storage (SQLite), sample documents (real Telkom docs).

## What runs locally

```bash
cd svi-demo
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt

# .env should already exist (copied from .env.example by the previous session).
# If not: cp backend/.env.example backend/.env

# Start the demo backend
EXTRACTION_BACKEND=stub uvicorn backend.app.main:app --port 8080 --reload
```

Then in another terminal, walk through the heart-of-pitch flow with curl —
upload a fixture, approve twice, watch it complete. The same flow Phase 4–5
needs to wire into the browser:

```bash
# Upload
CASE=$(curl -s -X POST -F "file=@fixtures/seed-cases/01-alam-sutera-invoice.pdf" \
  http://localhost:8080/api/cases/upload | jq -r .case_id)
echo "case=$CASE"

# Inspect
curl -s "http://localhost:8080/api/cases/$CASE" | jq

# Approve x2 -> webhook -> complete
curl -s -X POST -H "Content-Type: application/json" -d '{"actor":"clerk"}' \
  "http://localhost:8080/api/cases/$CASE/approve"
curl -s -X POST -H "Content-Type: application/json" -d '{"actor":"manager"}' \
  "http://localhost:8080/api/cases/$CASE/approve"

# Toggle 503 to demo the integration-error flow
curl -s -X POST -H "Content-Type: application/json" -d '{"mode":"503"}' \
  http://localhost:8080/api/mock-erp/toggle
```

To use real Gemini extraction instead of the stub, start `pf-idp-processing`
on `:8000` per its README, then run the demo backend with
`EXTRACTION_BACKEND=real` (or `auto` to fall back to stub if pf-idp is down).

## Phase 4 starting point

`PLAN.md` Phase 4 is the source of truth — done-criteria are explicit. In short:

1. Copy `../svi-alembic-ui/operator/operator-queue.html` to `svi-demo/ui/operator-queue.html`.
2. Inspect existing markup — find the table/list element where mock cases are
   rendered, and the column structure.
3. Append a `<script>` block (or extract to `ui/js/operator-queue.js`) that:
   - On page load, calls `GET /api/cases`
   - Replaces hardcoded mock rows with rendered rows from real data
   - Wires each row's click handler to navigate to `case-detail.html?id=<case_id>`
   - Filter dropdowns/buttons for state call `GET /api/cases?state=<x>` and re-render
4. Test: refresh page, see real cases. Click one, lands on case-detail.html
   (which is still static — Phase 5 wires it).

Done-criteria (from `PLAN.md`):

- Open `http://localhost:8080/ui/operator-queue.html` → see real cases from the backend
- Filter dropdown changes the queue
- Clicking a case navigates to `case-detail.html?id=<case_id>`

---

## Kickoff prompt for Claude Code

Copy the block below into a fresh Claude Code session at the repo root.

> You're picking up at Phase 4 of svi-demo, a sales demo for SVI Alembic ADP.
> Phases 1–3 (backend, storage, state machine, mock ERP) are complete and
> verified. Working folder is the repo containing `svi-demo/`,
> `svi-alembic-ui/`, `pf-idp/`, and `docs/`.
>
> **First moves, in order:**
>
> 1. Read `svi-demo/README.md`, `svi-demo/HANDOFF.md`, and
>    `svi-demo/PHASE-4-KICKOFF.md`. The phase-4 kickoff has everything that
>    happened in the prior session and is the most recent source of truth.
> 2. Confirm state by inspecting files: backend code in
>    `svi-demo/backend/app/`, fixtures in `svi-demo/fixtures/seed-cases/`. If
>    something looks renamed or missing, surface it before proceeding.
> 3. Read `svi-demo/PLAN.md` Phase 4 + `svi-demo/DATA-CONTRACTS.md` (queue
>    response shape).
> 4. Boot the backend locally and walk the curl heart-of-pitch flow at the
>    bottom of `PHASE-4-KICKOFF.md` to make sure your machine is set up
>    before writing UI code.
> 5. Tell me you've read everything and what you understood — one short
>    paragraph, plain English. Then start Phase 4.
>
> **Working-style rules (hard, from prior memory):**
> - Plain English over jargon. No L-codes, no session numbers, no Q-codes. If
>   you reference a locked decision, paraphrase it.
> - Reference n8n / Make.com when explaining workflow concepts.
> - **One question at a time.** Use the AskUserQuestion-equivalent (or
>   inline-but-marked-as-question prose) with a recommendation attached, not
>   a wall of options.
> - Concrete worked examples beat abstract principles.
> - State-confirmation is load-bearing on cross-day handoffs.
> - **No extensive postambles after sharing files.** Link, one-sentence
>   summary, stop.
>
> **What I do not want you to do:**
> - Don't add a build step (Webpack/Vite/esbuild). Static HTML + vanilla JS,
>   loaded from CDN if needed.
> - Don't rewrite the UI in React/Vue. Wire JS into the existing static HTML
>   from `svi-alembic-ui/operator/`.
> - Don't merge the HonoX portal-app from `pf-idp/pf-idp-portal-app/`. It's a
>   separate stack, intentionally not the basis for this demo.
>
> I'm Hammam — Product at SVI Alembic, non-infrastructure background. I think
> in product and workflow terms.
