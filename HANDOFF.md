# HANDOFF — for the next agent picking up svi-demo

You are picking up a partially-scaffolded sales demo. This document gives you everything you need to continue without asking the user to re-explain context.

## Confirm state first

Before doing anything material, confirm two things by inspecting files (not by asking the user):

1. The user's working folder still contains `svi-alembic-ui/`, `pf-idp/`, `docs/PRD-demo-scope-refined.docx`, and this `svi-demo/` folder. If anything is missing or renamed, surface that to the user before proceeding — paths in this doc may be stale.
2. The `pf-idp/pf-idp-processing/` FastAPI service still exposes `POST /api/v1/extract` with the request/response shape documented in `DATA-CONTRACTS.md`. If the API has changed, update DATA-CONTRACTS.md before writing client code against it.

## Who the user is

- **Name:** Hammam
- **Role:** Product at SVI Alembic
- **Background:** Non-infrastructure. He thinks in product and workflow terms, not in framework terms. Don't assume he knows the difference between FastAPI middleware vs. a route handler unless he asks.
- **Current project context:** SVI Alembic ADP — Indonesian mid-market AP MVP. The demo PRD and MVP PRD were finalized April 27, 2026 after a 16-session capability articulation pass.

## How he likes to work

These are not preferences — they're hard rules pulled from his memory file and recent conversations:

- **Plain English over jargon.** No `L30`, no `Q-OC-1`, no session numbers. He knows the system; he doesn't want to be reminded he's reading a spec. If you must reference a locked decision, paraphrase it.
- **Reference n8n / Make.com when explaining workflow concepts.** That's his mental model.
- **One question at a time.** When you need clarification, ask one question with a recommendation attached, not a wall of options. Use the AskUserQuestion tool, not inline prose questions.
- **Concrete worked examples beat abstract principles.** Show him "here's the JSON the operator queue will get" rather than "we'll define a Case domain model."
- **State-confirmation is load-bearing on cross-day handoffs.** His prompts can be stale across days because he's juggling multiple agent threads. If he says "continue with what we agreed yesterday," verify by reading the actual files before acting on assumptions.
- **Don't write extensive postambles after sharing files.** Give him the link, give him a 1–2 sentence summary, stop.

## What was decided in the initiating session

The user asked: "based on PRD-demo, reference also for ui under this /svi-alembic-ui folder and code from pf-idp folder, can we generate a working demo?"

The initiating agent surveyed both folders, confirmed feasibility, and asked one decision question. The user's answer:

**Demo fidelity = "Heart-of-pitch live, rest static."**

Specifically:
- **Live wired (real backend, real Gemini extraction, real state transitions):**
  - Demo segment 2 — operator daily flow (open queue → open case → see extracted fields → click amber field → see PDF highlight → correct field → approve)
  - Demo segment 6 — integration loop close (approve → mock ERP webhook fires → 201 Created → optional 503 simulation + Retry Integration)
- **Static walkthrough (existing svi-alembic-ui screens, no wiring needed):**
  - Demo segment 1 — opening pitch (no UI)
  - Demo segment 3 — workflow canvas walkthrough (use existing `canvas-editor.html`)
  - Demo segment 4 — schema library + extraction depth (use existing `schema-library.html`, `create-schema-step1.html` etc.)
  - Demo segment 5 — admin dashboards + Users & Roles (use existing `dashboard.html`, `users-roles.html`)
  - Demo segment 7 — SVI onboarding view (use existing `deployments.html` and tenant management screens)

Estimated build effort: 3–4 days for someone familiar with FastAPI + vanilla JS.

## Why this choice (not the user's job to remember)

The "everything live" path was 7–10 days and risks dragging the demo into bug territory during prospect calls. The "operator flow only" path skipped the ERP webhook close, which is the moment that lands the typing-elimination story. The chosen middle path makes the headline value prop (segments 2 + 6) visceral with real data while keeping segments 3, 4, 5, 7 as familiar UI walkthroughs that demo presenters can narrate over.

## What's NOT decided yet — open questions for you

These are things the initiating agent left for you to figure out. Don't pretend to know — ask the user when you hit them, with one question + a recommendation:

1. **Storage:** SQLite (survives restarts; nicer for repeated demos) vs. in-memory dict (simpler; resets on restart). Recommendation: SQLite, ~10 lines extra.
2. **PDF rendering for click-to-highlight:** PDF.js in the browser vs. server-rendered page images. Recommendation: PDF.js — it makes bbox overlay trivial and keeps the backend lighter.
3. **Sample documents:** real Indonesian Invoice + Faktur Pajak PDFs (must be sourced — see `fixtures/README.md`) vs. synthetic ones generated for demo. Recommendation: source real samples; fall back to synthetic if you can't get them within a day.
4. **Branding:** the existing svi-alembic-ui has a generic look. Does the user want logo / color tweaks before showing prospects? Recommendation: ship as-is for now; visual polish is a separate pass.
5. **Hosting for live demo:** localhost on the demo presenter's laptop vs. deploy to a staging URL. Recommendation: localhost first (simpler, works offline). Deployable later.

## What the user explicitly does not want

- **Don't merge the HonoX portal-app (`pf-idp/pf-idp-portal-app/`) into this demo.** It exists as a separate stack and is intentionally not the basis for svi-demo. The user pointed at svi-alembic-ui as the UI source.
- **Don't pretend the deferred features exist.** Auto-advance / STP, cross-tenant view, real ERP integration depth, in-app notifications — these are explicitly not in the demo. See `SCOPE.md` for the full not-shown list.
- **Don't claim "AI replaces your AP team."** The pitch is "copilot today, agentic when data earns it." Operator reviews every case at MVP — that's deliberate.

## Your starting point

After reading this doc and `SCOPE.md`, `ARCHITECTURE.md`, `DATA-CONTRACTS.md`: open `PLAN.md` and start at Phase 1. Each phase has explicit done-criteria. Don't skip phases — they have dependencies.

When you have something runnable end-to-end (Phase 3 done), run through `DEMO-RUNBOOK.md` yourself before telling the user it's ready. The user wants to be told "this works" only when it actually works on a fresh machine without you tweaking it live.
