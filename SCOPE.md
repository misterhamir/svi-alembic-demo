# SCOPE — what's in, what's out

The user picked "heart-of-pitch live, rest static." This document is the precise breakdown of what that means.

## Live-wired segments (real backend, real extraction, real state)

### Segment 2 — Operator daily flow

**Screens involved:** `operator-queue.html`, `case-detail.html` (both copied from `svi-alembic-ui/operator/`)

The full beat sequence from the demo PRD must work end-to-end with real data:

1. Operator opens the queue → sees real cases pulled from the backend (each one was uploaded earlier or exists from a seed script)
2. Operator clicks a case → case-detail loads with real extracted fields (from a real Gemini extraction call that happened at upload time) and color bands driven by the real confidence scores
3. Operator clicks an amber-banded field → the PDF page renders with the bounding box highlighted in the right place
4. Operator types a correction in the field → backend persists the correction, the field's provenance flips from "AI-extracted" to "human-corrected"
5. Operator clicks Approve → case state advances; if there's a next workflow node (e.g. Approval), it advances to that; if the workflow ends with a Webhook, the webhook fires (segment 6)

### Segment 6 — Integration loop close

**Screens involved:** `case-detail.html` (showing the integration error panel after a simulated failure), and a tiny mock ERP endpoint inside the svi-demo backend.

1. After the operator approves, the backend POSTs to the mock ERP endpoint
2. By default the mock ERP returns 201 Created → case marks as successfully integrated
3. The demo presenter can toggle the mock ERP to return 503 → next approval routes the case to Review state with an integration error panel showing the response body, status code, retry history
4. Admin clicks "Retry Integration" on the case → request fires again; if mock ERP is back to 201, case completes

## Static-walkthrough segments (existing svi-alembic-ui screens, no wiring)

These segments are demo'd by the presenter clicking through the existing static HTML. The data shown is the hardcoded mock data already in the files — that's fine; the presenter narrates what the buyer is looking at.

| Demo segment | Screens to use (from svi-alembic-ui) |
|---|---|
| Segment 3 — Workflow canvas walkthrough | `admin/canvas-editor.html`, `admin/workflows.html`, `admin/node-configuration.html`, `admin/configuration-sidebar.html` |
| Segment 4 — Schema Library + extraction depth | `admin/schema-library.html`, `admin/create-schema-step1.html` through `step4.html` |
| Segment 5 — Admin dashboards + Users & Roles | `admin/dashboard.html`, `admin/users-roles.html`, `admin/instance-monitor.html` |
| Segment 7 — SVI onboarding view | `admin/deployments.html`, `admin/training-files.html`, `admin/start-new-case.html` |

These screens get copied into `ui/` alongside the live ones, and a top-nav link structure ties them together so the demo presenter can flow between live and static segments naturally.

## Explicitly not in the demo

These come from the demo PRD's "don't show" list. If you find yourself building any of these, stop and check with the user first.

### Out — these are real future capabilities, just not in the demo

- Auto-advance / straight-through processing
- Cross-tenant SVI fleet view
- Operator personal performance view
- Auto-processing dashboard UI
- In-app notification bell + external notification delivery
- Document viewer annotation / markup
- Tenant admin canvas editing (read-only at MVP)
- Tenant self-serve add-tenant
- Hard delete platform UI
- MFA enforcement on first login
- PDF export from dashboards
- Reverse-direction click-to-highlight (forward direction only)
- Saved quick views in queue
- Per-node retry override
- Schema-drift detection alerts

### Out — the rule grammar's intentional bounds

The demo only needs to show that workflows have rules, not to demo the full rule editor. If asked, the rule grammar bounds are:

- Comparators: `=`, `!=`, `<`, `≤`, `>`, `≥`, `in`, `not_in`, `contains`, `is_null`, `is_not_null` — and that's it
- Bounded aggregates: `sum` and `count` over current-bundle arrays only
- Match modes: `ALL` (implicit AND) or `ANY` (OR)
- No filters in aggregates, no nested aggregates, no arithmetic in operands, no free-text expressions, no parens

### Don't claim during the demo

- "AI replaces your AP team" — false; operator reviews every case at MVP
- "Real-time everything" — dashboards refresh every 5–15 minutes
- "Auto-advance / STP at pilot" — that's a future capability, earned per tenant
- "Any document type, any language" — Bahasa Indonesia + English optimized; other scripts soft-degrade
- "Plug into any ERP" — REST + 4 auth methods at MVP; SOAP/GraphQL/mTLS/OAuth refresh are future releases

## Demo-vs-product distinction

The svi-demo backend is a demo orchestration layer, not a real product implementation. It can take shortcuts the real product can't:

- In-memory or SQLite storage is fine — no need for proper database with migrations
- Hardcoded tenant ID is fine — multi-tenancy is not demonstrated
- Mocked ERP is fine — real ERP integration happens during pilot onboarding
- Hardcoded user identities are fine — no real auth flow
- Reset script wipes everything — that's expected; demo starts from a known seed each time

If you find yourself building something that would survive into production, stop. That's outside this folder's scope. Real product implementation lives in `pf-idp/` (and a future svi-alembic-* repo for the platform layer).
