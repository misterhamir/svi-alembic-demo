# scripts/

Dev and demo-driving scripts.

## Files to create (per PLAN.md phases)

### `smoke_test_extraction.py` (Phase 1)

Reads a PDF from `fixtures/`, calls pf-idp-processing directly, prints fields. Used to verify the extraction pipeline works before wiring the rest.

```python
# rough shape
import sys, base64, httpx
pdf = open(sys.argv[1], "rb").read()
r = httpx.post("http://localhost:8000/api/v1/extract", json={
  "document": base64.b64encode(pdf).decode(),
  "schema": {...}  # the Invoice or Faktur Pajak schema from DATA-CONTRACTS.md
})
print(r.json())
```

### `seed.py` (Phase 6)

Reads PDFs from `../fixtures/seed-cases/`, uploads each to the running svi-demo backend, prints summary. Idempotent — running it twice doesn't double-create cases.

### `reset.py` (Phase 6)

Wipes `../backend/data/`, recreates empty structure, calls `seed.py`. Single command for the demo presenter to reset between calls.

```bash
python scripts/reset.py
```

Should complete in <30 seconds. Print progress so the presenter sees something is happening.

### `start-all.sh` (optional, Phase 1)

Convenience script to start both the extraction service and the svi-demo backend in two separate terminals (or as background processes with logs to files). Saves the demo presenter from running two `uvicorn` commands manually.

## Conventions

- Scripts are run from the `svi-demo/` directory (one level up). Use relative paths from there: `fixtures/...` not `../fixtures/...`.
- Print human-readable output. Don't make the demo presenter parse JSON to know what happened.
- Exit codes matter: 0 on success, non-zero on failure. The reset script's failure should be loud.
- No dependencies beyond what's in `backend/requirements.txt`. If you reach for click or rich, that's overkill — `argparse` and `print` are fine.
