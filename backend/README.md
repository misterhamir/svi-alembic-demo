# backend/

The orchestration layer. FastAPI app on port 8080. Talks to the existing pf-idp-processing extraction service on port 8000.

## What this service does

- Manages case state (storage, queue, detail, transitions)
- Wraps Gemini extraction calls (delegates to pf-idp-processing)
- Hosts the mock ERP endpoint (the Webhook target)
- Serves static UI files from `../ui/`

## What this service does NOT do

- Real authentication (uses hardcoded user identities for demo)
- Real multi-tenancy (single-tenant)
- Real workflow editing (the seeded workflow is hardcoded)
- Real schema editing (seeded schemas are hardcoded)
- Real OCR / extraction (delegates to pf-idp-processing)

## Suggested layout

```
backend/
  README.md               ← you are here
  pyproject.toml          ← dependencies (or requirements.txt if simpler)
  .env.example            ← config template
  app/
    __init__.py
    main.py               ← FastAPI app, mounts routes + static files
    config.py             ← env var loading
    storage.py            ← SQLite (or JSON) abstraction
    extraction_client.py  ← async client for pf-idp-processing
    state_machine.py      ← workflow state transitions
    cases.py              ← /api/cases/* route handlers
    mock_erp.py           ← /api/mock-erp/* route handlers
    schemas.py            ← seeded JSON schemas (Invoice, Faktur Pajak)
    workflows.py          ← seeded workflow definition
    seed.py               ← seed function (callable from scripts/seed.py)
  data/                   ← runtime state (gitignored)
    cases.db
    uploads/
    erp_log.jsonl
    mock_erp_state.json
```

This layout is a suggestion, not a requirement. If you prefer a different structure (e.g. routes as separate files), that's fine.

## Running locally

```bash
# from svi-demo/
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt   # or: pip install -e .
cp .env.example .env
# edit .env with EXTRACTION_SERVICE_URL etc.

uvicorn app.main:app --port 8080 --reload
```

Then visit http://localhost:8080/ui/operator-queue.html.

## Dependencies on the extraction service

Before this backend can do anything useful, pf-idp-processing must be running on its own port (default 8000). See its README in `../../pf-idp/pf-idp-processing/`.

If you want a single command to start both, build a `scripts/start-all.sh` in Phase 1. Don't put orchestration logic inside the FastAPI app — the user shouldn't need a process supervisor for a demo.

## Storage choice

The user's open question (see `../HANDOFF.md`): SQLite vs. JSON file vs. in-memory dict.

Recommendation: SQLite. Reasons:
- Survives restarts (matters when iterating on UI changes — don't want to re-extract every time)
- SQL's `WHERE state = ?` filtering is trivial; JSON requires writing your own filter
- aiosqlite + FastAPI is well-trodden ground; ~30 lines of code total

If you go JSON instead, that's fine — keep it under one file and write a transactional save (write to temp file, rename) so it survives interrupts.

If you go in-memory, document it loudly because every backend restart wipes the demo state.

## State that's intentionally process-local

These don't need to persist:
- The mock ERP toggle mode — but persisting it makes the demo more robust against accidental backend restart mid-call. Recommend persisting.

## Logging

Print to stdout. Format:
```
[09:15:08.123] [INFO]  case_create  case_id=case_01HZK... duration_ms=1240
[09:15:08.456] [INFO]  extract_call  doc_size_kb=890 fields=12 confidence=0.87
[09:17:00.012] [INFO]  webhook_fire  url=...mock-erp/invoices status=201 duration_ms=15
```

The demo presenter watches the terminal during the call. Don't add structured logging libraries.

## Testing

A handful of smoke tests in `backend/tests/`:
- Test that upload + retrieve round-trips
- Test that approve transitions state correctly
- Test that mock ERP toggle works
- Test that retry re-fires the webhook

Don't aim for high coverage — the demo's correctness is verified by running through DEMO-RUNBOOK.md, not by unit tests.
