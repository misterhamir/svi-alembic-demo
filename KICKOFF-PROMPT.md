# Kickoff prompt for the next agent

Paste the block below into a fresh agent session. The agent will read it and pick up the work.

The prompt is intentionally short — the deep context lives in the docs the agent will read on its first turn. Don't try to inline the full brief here; that's what `HANDOFF.md` is for.

---

```
You're picking up a partially-scaffolded sales demo at /Users/user/Documents/PROJECT/pf_with_files/svi-demo. The previous agent (in a separate session, on April 27, 2026) scaffolded the folder and wrote 7 hand-off docs. No code has been written yet.

Your starting moves, in order:

1. Read svi-demo/README.md and svi-demo/HANDOFF.md. HANDOFF tells you who I am, how I like to work, and what's already been decided. Don't skip this — the working-style rules in there are not preferences, they're hard rules.

2. Confirm state before assuming. Verify three things by reading files (not by asking me):
   - svi-demo/ contains the 7 .md docs and the ui/, backend/, fixtures/, scripts/ subfolders with their READMEs
   - ../svi-alembic-ui/ still exists with admin/ and operator/ subfolders of static HTML
   - ../pf-idp/pf-idp-processing/ still exists and its FastAPI extract route still matches what's documented in svi-demo/DATA-CONTRACTS.md
   If anything is missing, renamed, or has changed since April 27, 2026, surface that to me before proceeding.

3. Read svi-demo/SCOPE.md, ARCHITECTURE.md, DATA-CONTRACTS.md, PLAN.md, and DEMO-RUNBOOK.md. By the end of this you should be able to explain the three-process architecture (extraction service on 8000, demo backend on 8080, browser at /ui/) and the heart-of-pitch demo flow without re-reading.

4. Tell me you've read everything and what you understood. One short paragraph, plain English. No bullet-point summary of the docs — I wrote them, I don't need them recited. I want to know if your mental model matches what's in the docs.

5. After I confirm, start Phase 1 in PLAN.md. Each phase has explicit done-criteria — don't move forward until they're met.

Open questions you'll hit are listed in HANDOFF.md. When you hit one, ask me with the AskUserQuestion tool — one question, one recommendation attached, two or three options. Don't ask all the open questions at once.

Things you'll be tempted to do that I don't want:
- Don't merge the HonoX portal-app from pf-idp/pf-idp-portal-app/. It's a separate stack, intentionally not the basis for this demo.
- Don't add a JS build step (Webpack, Vite, esbuild). The point of using svi-alembic-ui's static HTML is to avoid build-toolchain overhead.
- Don't rewrite the UI in React/Vue. Wire JS into the existing static HTML.
- Don't write extensive postambles after sharing files. Link, one-sentence summary, stop.

I'm Hammam — Product at SVI Alembic, non-infrastructure background. I think in product and workflow terms. When you explain technical choices, ground them in n8n / Make.com analogies if relevant. Use plain English over framework jargon.
```

---

## Why this prompt is short

The deep brief is in `HANDOFF.md` (75 lines), `SCOPE.md` (90), `ARCHITECTURE.md` (140), `DATA-CONTRACTS.md` (397), `PLAN.md` (200), and `DEMO-RUNBOOK.md` (179). Inlining all of that into the kickoff prompt would bloat it past the point of usefulness and risk drift if the docs get updated.

The kickoff prompt's job is to (1) point the agent at the right entry doors, (2) make state-confirmation the first action so stale assumptions get caught early, and (3) seed the working-style rules early enough that the agent doesn't make a wrong move on turn 1.

## When to update this prompt

- If you change the working-folder layout
- If you make a major scope decision that contradicts something in `HANDOFF.md` (update both)
- If you abandon FastAPI for a different backend stack
- If you decide a different UI source (e.g. switching from svi-alembic-ui to the HonoX portal-app)

Otherwise leave it alone. The prompt is a stable entry point; the docs underneath it are where the live state lives.
