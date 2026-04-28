# fixtures/

Sample data for the demo. The seed script reads from here.

## Layout

```
fixtures/
  README.md             ← you are here
  seed-cases/           ← PDFs to upload during seed (each becomes a case)
    01-acme-invoice.pdf
    02-bumi-faktur-pajak.pdf
    03-multi-doc-bundle.pdf       ← Invoice + Faktur Pajak in one PDF
    ...
  vendor-master.json    ← mock vendor data for the Lookup demo (segment 6)
  case-templates.json   ← optional: hand-crafted case templates if you skip live extraction during seed
```

## Sourcing real Indonesian sample documents

The demo lands harder with real Indonesian Commercial Invoice + Faktur Pajak documents. Options:

1. **Best:** ask the user (Hammam) for sample documents from prior pilot conversations or the SVI team's reference set. He has connections to mid-market AP teams.
2. **Acceptable:** use synthetic but realistic-looking documents generated from a template — search "Faktur Pajak template Indonesia" and adapt one for `Acme Indonesia → Bumi Sejahtera` style fictional vendors. Use realistic amounts (Rp 5,000,000 – Rp 250,000,000 ranges; that's the AP sweet spot).
3. **Last resort:** use synthetic documents in English. Loses the "tuned for Indonesian market" credibility but gets the demo running.

What you need at minimum for Phase 6 (seed):
- 5–10 single-document PDFs (some Invoice, some Faktur Pajak)
- 2–3 multi-doc bundle PDFs (Invoice + Faktur Pajak in one file)
- A mix of confidence levels — some clearly extractable (clean print), some borderline (faxed-quality scan, partial occlusion)

## What the seed script does

For each PDF in `seed-cases/`:
1. Reads the file
2. POSTs to svi-demo backend `/api/cases/upload` (or directly inserts via storage layer)
3. Awaits the extraction round-trip
4. The case lands in storage with state `pending_review`

Filename convention drives metadata:
- `XX-vendor-name-doc-type.pdf` — XX is sort order, vendor-name appears in the case subject, doc-type is hint for classifier
- Files starting with `error-` get their cases pre-set to `integration_error` state for the Retry Integration demo

## vendor-master.json

For segment 6's optional Lookup demo:
```json
{
  "vendors": [
    {
      "npwp": "01.234.567.8-901.000",
      "name": "Acme Indonesia",
      "approved": true,
      "credit_limit": 500000000
    }
  ]
}
```

The svi-demo backend can expose this as a fake "vendor master Lookup endpoint" at `/api/mock-vendor-master/lookup?npwp=...` for the demo presenter to point at during the canvas walkthrough.

## What's NOT in this folder

- Real prospect data — never. Sanitize before adding any real-world doc.
- The actual ERP system — that's the mock, lives in the backend code, not here.
- Test fixtures for unit testing — those go in `backend/tests/fixtures/` if you write tests.
