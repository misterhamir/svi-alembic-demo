# ui/

Static HTML files served by the svi-demo backend at `http://localhost:8080/ui/*`.

## What goes here

Two categories of files:

### Live-wired (Phases 4 + 5)

These are copied from `../../svi-alembic-ui/operator/` and have JavaScript appended to call the svi-demo backend:

- `operator-queue.html` — fetches `/api/cases`, renders queue, navigates to detail
- `case-detail.html` — fetches `/api/cases/{id}`, renders fields with PDF + bbox overlay, wires correction + approve + retry buttons

### Static walkthrough (Phase 6)

These are copied from `../../svi-alembic-ui/admin/` unchanged. The hardcoded mock data inside them is fine — the demo presenter narrates over it.

- `dashboard.html`
- `canvas-editor.html`, `workflows.html`, `node-configuration.html`, `configuration-sidebar.html`
- `schema-library.html`, `create-schema-step1.html` through `step4.html`
- `users-roles.html`, `instance-monitor.html`, `deployments.html`
- (anything else from `svi-alembic-ui/admin/` that the demo needs)

### Top-level

- `index.html` — landing page with two prominent links: "Operator Queue" (heart-of-pitch entry) and "Admin Dashboard" (static walkthrough entry). Useful for the demo presenter.
- `js/` — folder for shared JavaScript if you choose to extract it (otherwise inline in each HTML file is fine for a demo)
- `assets/` — any images or shared CSS overrides (logo, favicon — copy from `../../svi-alembic-ui/SVI_logo/`)

## Conventions for the wiring JS

When you add JS to a copied HTML file:

1. Keep all wiring at the bottom of the file in a single `<script>` block, or in a separate file referenced as `<script src="js/operator-queue.js"></script>`. Don't scatter logic.
2. The existing markup has hardcoded mock data — your job is to replace specific elements (table rows, field values, PDF viewer) with rendered content from the API. Don't rebuild the layout — find the elements by ID or class and swap their contents.
3. If the existing markup doesn't have stable IDs/classes, add them. Document any added IDs at the top of your JS as a comment.
4. No frameworks. Plain `fetch()`, plain DOM manipulation. If you reach for React, stop and check with the user first — that's a meaningful escalation.

## What NOT to do

- Don't rewrite the HTML in JSX or Vue templates — defeats the point of using svi-alembic-ui as the visual base.
- Don't add a build step (Webpack, Vite, esbuild). The whole point is no build toolchain.
- Don't pull in dependencies via npm — load anything you need (PDF.js) from a CDN.
- Don't change visual styling unless the user asks. The svi-alembic-ui designs are the agreed-upon look.
