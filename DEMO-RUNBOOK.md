# DEMO-RUNBOOK — how to actually run a prospect demo

This is the script for the demo presenter on the day of a prospect call. It assumes everything in `PLAN.md` is built.

## Pre-call setup (15 minutes before the call)

### 1. Start the extraction backend (port 8000)

```bash
cd ../pf-idp/pf-idp-processing
# follow that folder's README to start its service. Typical:
uv run uvicorn processing_engine.main:app --port 8000
```

Wait for it to log "ready" — Gemini API setup takes a few seconds, OCR warmup takes longer.

### 2. Reset the svi-demo state

```bash
cd svi-demo
python scripts/reset.py
```

This wipes any prior demo state and re-seeds with the canonical mock cases. Should take <30 seconds.

### 3. Start the svi-demo backend (port 8080)

```bash
uvicorn backend.app.main:app --port 8080
```

### 4. Sanity check

Open `http://localhost:8080/ui/operator-queue.html` in a browser. You should see ~10–15 mock cases with realistic timestamps and a mix of states.

If you don't, check:
- Is the extraction service responding? `curl http://localhost:8000/api/v1/health`
- Is the svi-demo backend responding? `curl http://localhost:8080/api/health`
- Did the seed script complete? Check `data/cases.db` exists and has rows.

### 5. Set the mock ERP to default mode

```bash
curl -X POST http://localhost:8080/api/mock-erp/toggle -d '{"mode":"201"}' -H 'Content-Type: application/json'
```

(Should already be in 201 mode after a reset, but verify.)

### 6. Open the browser windows in this order

In sequence (one tab each — switching between them is part of the flow):

1. `http://localhost:8080/ui/operator-queue.html` — the heart-of-pitch starting point
2. `http://localhost:8080/ui/case-detail.html?id=<a-pending-review-case-id>` — pre-loaded so the click is instant
3. `http://localhost:8080/ui/canvas-editor.html` — for segment 3 (static walkthrough)
4. `http://localhost:8080/ui/schema-library.html` — for segment 4
5. `http://localhost:8080/ui/dashboard.html` — for segment 5
6. `http://localhost:8080/ui/deployments.html` — for segment 7

Tip: name each tab via DevTools or use a tab-grouping extension.

## During the call — segment by segment

Reference: `../docs/PRD-demo-scope-refined.docx` has the full beat sequence per segment with talk-tracks. This runbook only adds the "how to drive the demo software" notes.

### Segment 1 — Opening pitch (2–3 min, no UI)

Just talk. Use the n8n / Make.com analogy. Land "copilot today, agentic when data earns it." Then say "let me show you the operator's day first" and switch to tab 1.

### Segment 2 — Operator daily flow (5–7 min) — LIVE

You are now driving real software. The data the prospect sees is from a real Gemini extraction.

1. Show the queue. Read 2–3 case rows aloud, mention the bundle counts and ages.
2. Click into a `pending_review` case (tab 2 has one pre-loaded — switch tabs).
3. **Documents tab** — show the multi-doc tab strip. Click between Invoice and Faktur Pajak to demonstrate the bundle.
4. **Extracted Data tab** — point out green/amber/red color bands. Find an amber field and pause on it.
5. **Click the amber field** — the source PDF region highlights. *"Operator verifies by looking, not by retyping."*
6. **Correct one field inline** — click a value, type a correction, press Enter. The provenance icon flips from AI-extracted to human-corrected. *"One keystroke if the system got it wrong."*
7. **Approve** — the case advances. Show the toast / state change. *"Case moves to manager approval."*
8. (Optional) Open a stuck case from the queue, click Reassign, show the unblock.

### Segment 3 — Workflow canvas walkthrough (5–7 min) — STATIC

Switch to tab 3 (canvas-editor.html). The data here is hardcoded mock — the prospect doesn't know that. You're narrating over a screen.

1. Show the seeded AP workflow on canvas. Walk through: Intake → Classify → Extract → Validate → Switch → Review → Approval → Webhook.
2. Click into Switch's config drawer. Walk through the chip-drag form. (No actual drag-drop happens — the screen is a screenshot-equivalent.)
3. Pretend to publish; show the version history.

If a prospect tries to click something and it doesn't respond, smoothly say: *"This is the canvas authoring experience — we're showing the visual configuration model. Configuration changes are managed by SVI during pilot phase."*

### Segment 4 — Schema Library (3–4 min) — STATIC

Switch to tab 4 (schema-library.html). Show the seeded Commercial Invoice + Faktur Pajak schemas. Walk through versioning. If you have time, click into create-schema-step1 → step2 etc. to show the multi-step Run Discovery flow.

### Segment 5 — Admin dashboards (3–4 min) — STATIC

Switch to tab 5 (dashboard.html). Walk through cycle-time tile, correction-rate tile, cases-closed tile. Click stuck-cases tile (it'll just navigate or do nothing — narrate what *would* happen: "drills into a filtered queue").

Switch to users-roles.html. Show groups, users, role assignments.

### Segment 6 — Integration loop close (2–3 min) — LIVE

This is the second live segment. The setup matters.

**Before this segment, in a side terminal:**

```bash
# Toggle mock ERP to 503 so we can show the failure flow
curl -X POST http://localhost:8080/api/mock-erp/toggle -d '{"mode":"503"}' -H 'Content-Type: application/json'
```

Now switch back to tab 1 (queue). Open a fresh `pending_review` case, walk through approve. The case will land in `integration_error` state — show the integration error panel.

**Then in the side terminal:**

```bash
curl -X POST http://localhost:8080/api/mock-erp/toggle -d '{"mode":"201"}' -H 'Content-Type: application/json'
```

Click Retry Integration on the errored case. It succeeds. Case completes.

(Alternative — if you don't want to use a side terminal during the demo, build a tiny "Demo Controls" floating panel that's only visible when a `?demo=true` query param is set. Phase 6 task to add later.)

### Segment 7 — Onboarding (2–3 min) — STATIC

Switch to tab 6 (deployments.html). Walk through tenant list, click Add Tenant (just opens the form — no real submission), walk through the form fields, mention magic-link welcome email.

### Segment 8 — Q&A + close (5+ min)

Common questions and answers are in `../docs/PRD-demo-scope-refined.docx` — sections 11 and 13 are the prep notes for this segment.

## Reset between calls

If you have back-to-back calls:

```bash
# In the svi-demo directory
python scripts/reset.py
# Set mock ERP back to 201 mode (reset script should do this, but verify)
curl -X POST http://localhost:8080/api/mock-erp/toggle -d '{"mode":"201"}' -H 'Content-Type: application/json'
```

The backend keeps running; only the data resets.

## Common failure modes during a call

### The operator queue is empty after a reset

Causes:
- Seed script failed silently — check the terminal where you ran it
- Extraction service (port 8000) wasn't running when seed ran — restart and re-seed
- `GEMINI_API_KEY` is missing or invalid — check `pf-idp/pf-idp-processing/.env`

Recovery: restart both services, re-run reset, refresh the queue page.

### Click-to-highlight draws the box in the wrong place

Cause: the bbox coordinate system is mismatched between extraction (uses native PDF page dimensions) and rendering (canvas scale).

Recovery: keep going — narrate around it ("the highlight here is approximate; in production the alignment is pixel-perfect"). File a bug.

### Approve hangs

Cause: the webhook to mock ERP is timing out, or the state machine has a bug.

Recovery: refresh the case page (the state may have advanced). If still stuck, check backend logs in the terminal. If you can't recover live, smoothly transition to a static walkthrough segment and skip ahead.

### The whole thing crashes mid-call

Recovery: have a screen recording of a clean run-through ready as a backup. If everything fails, *"Let me show you a recording of the same flow"* is much better than fumbling. Build the recording during a successful internal dry-run.

## Things to never do during a live demo

- Don't click "Edit" on the canvas-editor — it'll do nothing and the prospect will notice
- Don't toggle mock ERP modes from the browser DevTools — use the side terminal so you don't accidentally show URL paths
- Don't open the backend's /docs (FastAPI auto-docs) — it gives away the demo's lightweight nature
- Don't show the file system or terminal unless you control what's visible
