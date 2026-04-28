# svi-demo

A working sales demo for **SVI Alembic ADP** — Indonesian mid-market accounts payable. Operators drop a PDF, an LLM extracts fields with confidence + bounding boxes, the operator reviews/corrects, then approves through a manager → mock ERP webhook closes the loop.

**Self-contained.** One Python service, one folder, no external dependencies beyond a Gemini API key.

---

## Quick start

### 1. Set your Gemini API key

The only credential you need. Get a free key at [aistudio.google.com](https://aistudio.google.com).

Open `backend/.env` and paste it in:

```bash
GEMINI_API_KEY=YOUR_KEY_HERE
```

That's it. (Optional override: `GEMINI_MODEL=gemini-2.5-flash` if you want the larger model. Default is `gemini-2.5-flash-lite` — cheap, fast, returns bounding boxes.)

### 2. Install + run

```bash
cd svi-demo
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt

# Real Gemini extraction (recommended once your key is set):
EXTRACTION_BACKEND=real uvicorn backend.app.main:app --port 8080 --reload

# Or stub mode — instant, no API calls, plausible synthetic data:
EXTRACTION_BACKEND=stub uvicorn backend.app.main:app --port 8080 --reload
```

### 3. Open the demo

[http://localhost:8080/ui/operator-queue.html](http://localhost:8080/ui/operator-queue.html)

Sample PDFs are at `test-pdfs/` (or `fixtures/seed-cases/`). Click **+ NEW CASE** in the top right and drop one in.

---

## What you can do

| Page | URL | What it does |
|---|---|---|
| Operator queue | `/ui/operator-queue.html` | All cases, status filter, click into any case |
| Case detail | `/ui/case-detail.html?id=<id>` | Real PDF + extracted fields side-by-side. Click any field → bbox highlight. Pencil icon → inline correction. Approve / reject / retry. |
| Approvals (manager) | `/ui/approvals-queue.html` | Cases awaiting L1 approval |
| Dashboard | `/ui/dashboard.html` | Live KPIs by state, mock ERP toggle |
| Workflow canvas | `/ui/canvas-editor.html` | View-only render of the seeded `ap_invoice_faktur_pajak_v1` workflow |

**Heart-of-pitch flow:** queue → click pending case → click an amber-confidence field (PDF highlights it) → correct it → approve → approve again as manager → mock ERP returns 201 → case complete.

**Demo the failure path:** dashboard → "Toggle 201 ⇄ 503" → upload a fresh case → approve → ERP returns 503 → integration error banner → click RETRY (after toggling back to 201) → completes.

---

## Architecture

```
┌──────────────────┐     ┌────────────────────┐     ┌──────────────┐
│  Static UI       │────▶│  svi-demo backend  │────▶│   Gemini     │
│  (HTML + JS,     │     │  (FastAPI, SQLite) │     │   2.5 Flash  │
│  PDF.js, Drawflow│     │  state machine,    │     │   (cloud)    │
│  via CDN)        │     │  mock ERP, queue   │     └──────────────┘
└──────────────────┘     └────────────────────┘
```

Think of it like an n8n workflow runner with a custom UI on top. Backend persists cases in SQLite, walks them through a linear state machine (`pending_review → pending_approval_L1 → webhook → complete`), and calls Gemini directly for extraction. Mock ERP lives in the same process (`/api/mock-erp/invoices`) so you can demo the integration loop without leaving localhost.

**No build step.** All UI assets are static HTML loaded from CDN at runtime. Edit any file under `ui/` and refresh.

---

## Folder layout

```
svi-demo/
├── backend/
│   ├── .env                  ← your Gemini key goes here
│   ├── .env.example          ← template
│   ├── requirements.txt
│   └── app/
│       ├── main.py           ← FastAPI entry
│       ├── config.py         ← env loader
│       ├── extractor.py      ← stub | real | auto facade
│       ├── gemini_extractor.py  ← Gemini 2.5 direct client
│       ├── extraction_client.py ← legacy pf-idp HTTP client (unused by default)
│       ├── case_builder.py   ← extraction result → case shape
│       ├── state_machine.py  ← linear walk through workflow
│       ├── storage.py        ← SQLite + uploads
│       ├── schemas.py        ← seeded Invoice + Faktur Pajak schemas
│       ├── workflows.py      ← seeded workflow definition
│       ├── mock_erp.py       ← /api/mock-erp/* (toggle 201/503)
│       └── routes/cases.py   ← upload/list/get/correct/approve/reject/retry
├── ui/
│   ├── operator-queue.html
│   ├── case-detail.html      ← PDF.js viewer + click-to-highlight
│   ├── approvals-queue.html
│   ├── dashboard.html
│   ├── canvas-editor.html    ← Drawflow view-only canvas
│   └── SVI_logo/
├── fixtures/seed-cases/      ← 10 real Indonesian AP PDFs
├── test-pdfs/                ← shortcut copies for the file picker (gitignored)
├── scripts/                  ← Playwright smoke tests, seed/reset
└── docs/                     ← PLAN.md, HANDOFF.md, ARCHITECTURE.md, etc.
```

---

## Extraction modes

Set with the `EXTRACTION_BACKEND` env var:

- **`real`** — Gemini 2.5 Flash-Lite, direct from this backend. Needs `GEMINI_API_KEY`. Takes 7–15s per case.
- **`stub`** — instant fake fields with plausible Indonesian values. No API key needed. Best for UI development or when offline.
- **`auto`** *(default)* — try Gemini, fall back to stub if it fails (rate limit, no key, etc.). Robust default.
- **`pfidp`** — legacy: HTTP-call out to `pf-idp-processing` on `:8000` (the original pf-idp monorepo's extraction service). Only used if you want to demo the OCR-first pipeline.

---

## More docs

- `PLAN.md` — phase-by-phase build plan
- `HANDOFF.md` — context for any agent picking up this folder
- `SCOPE.md` — what's in / out
- `ARCHITECTURE.md` — deeper technical notes
- `DATA-CONTRACTS.md` — JSON shapes for every endpoint
- `DEMO-RUNBOOK.md` — script for running a live prospect demo

---

## License & attribution

Internal sales demo for SVI Alembic. Not for redistribution.
