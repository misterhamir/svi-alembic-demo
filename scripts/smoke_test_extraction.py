#!/usr/bin/env python3
"""Phase 1 smoke test — prove the extraction round-trip works end-to-end.

What this does:
1. Reads a sample PDF from svi-demo/fixtures/seed-cases/ (or a path you pass on CLI)
2. POSTs it to pf-idp-processing /api/v1/extract using the seeded Invoice schema
3. Prints each extracted field with confidence + bbox + page

Pre-requisites:
- pf-idp-processing must be running on EXTRACTION_SERVICE_URL (default :8000)
- Its .env must have a working GEMINI_API_KEY

Usage:
    # From the svi-demo/ folder:
    python scripts/smoke_test_extraction.py
    python scripts/smoke_test_extraction.py fixtures/seed-cases/01-alam-sutera-invoice.pdf
    python scripts/smoke_test_extraction.py --schema faktur_pajak fixtures/seed-cases/08-tangcity-faktur-pajak.pdf

Phase 1 done-criterion: this script prints fields with non-null confidences.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make `from app.* import ...` work regardless of where the script is invoked.
_DEMO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_DEMO_ROOT / "backend"))

from app.extraction_client import ExtractionError, extract_sync  # noqa: E402
from app.schemas import SCHEMAS  # noqa: E402

DEFAULT_PDF = (
    _DEMO_ROOT
    / "fixtures"
    / "seed-cases"
    / "01-alam-sutera-invoice.pdf"
)

SCHEMA_ALIASES = {
    "invoice": "schema_invoice_v1",
    "faktur_pajak": "schema_faktur_pajak_v1",
    "fp": "schema_faktur_pajak_v1",
}


def _format_bbox(bbox: dict | None) -> str:
    if not bbox:
        return "(no bbox)"
    return (
        f"page {bbox.get('page', '?')} "
        f"x={bbox.get('x', '?'):.0f} y={bbox.get('y', '?'):.0f} "
        f"w={bbox.get('width', '?'):.0f} h={bbox.get('height', '?'):.0f}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="svi-demo extraction smoke test")
    parser.add_argument(
        "pdf",
        nargs="?",
        default=str(DEFAULT_PDF),
        help=f"path to PDF (default: {DEFAULT_PDF.relative_to(_DEMO_ROOT)})",
    )
    parser.add_argument(
        "--schema",
        choices=list(SCHEMA_ALIASES.keys()) + list(SCHEMAS.keys()) + ["discovery"],
        default="invoice",
        help="schema id to use, or 'discovery' for auto-detect",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="dump the full JSON response instead of a pretty summary",
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.is_absolute():
        pdf_path = (_DEMO_ROOT / pdf_path).resolve()
    if not pdf_path.exists():
        print(f"ERROR: PDF not found: {pdf_path}", file=sys.stderr)
        return 2

    schema_id = SCHEMA_ALIASES.get(args.schema, args.schema)
    if schema_id == "discovery":
        schema = None
        schema_label = "(discovery mode)"
    else:
        if schema_id not in SCHEMAS:
            print(f"ERROR: unknown schema id: {schema_id}", file=sys.stderr)
            return 2
        schema = SCHEMAS[schema_id]
        schema_label = schema_id

    print(f"-> reading PDF:  {pdf_path}")
    print(f"-> schema:       {schema_label}")
    document_bytes = pdf_path.read_bytes()
    print(f"-> bytes:        {len(document_bytes):,}")

    try:
        result = extract_sync(document_bytes, schema)
    except ExtractionError as e:
        print(f"\nFAILED with HTTP {e.status_code}:\n{e.body[:1000]}", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001 — we want anything that goes wrong here
        print(f"\nFAILED: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    if args.raw:
        print(json.dumps(result, indent=2))
        return 0

    fields = result.get("fields", [])
    print(
        f"\n-> overall_confidence: {result.get('overall_confidence', 0):.3f}  "
        f"page_count: {result.get('page_count')}  "
        f"pages_processed: {result.get('pages_processed')}\n"
    )
    if not fields:
        print("(no fields returned)")
        return 1

    name_w = max((len(f.get("name", "")) for f in fields), default=12)
    print(f"  {'field'.ljust(name_w)}  conf   value")
    print(f"  {'-' * name_w}  -----  -----")
    for f in fields:
        conf = f.get("confidence", 0.0)
        value = f.get("value", "")
        if isinstance(value, str) and len(value) > 80:
            value = value[:77] + "..."
        print(f"  {f.get('name', '').ljust(name_w)}  {conf:.2f}   {value}")
        bbox = f.get("bounding_box")
        if bbox:
            print(f"  {' ' * name_w}         {_format_bbox(bbox)}")

    # Phase 1 done-criterion: at least one field with non-null confidence.
    if not any(f.get("confidence") is not None for f in fields):
        print("\nWARNING: no field returned a confidence score.", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
