"""Extractor facade — picks between real (Gemini direct) and stub (canned fields).

Updated 2026-04-27: real mode now calls Gemini directly from svi-demo (see
gemini_extractor.py). The pf-idp HTTP client is kept around as a legacy
fallback (EXTRACTION_BACKEND=pfidp) but is no longer the default real path.

How to switch backends:
- EXTRACTION_BACKEND=real   -> Gemini 2.5 Flash, direct from svi-demo (needs GEMINI_API_KEY)
- EXTRACTION_BACKEND=stub   -> canned fields, instant, no key needed
- EXTRACTION_BACKEND=auto   -> try Gemini, fall back to stub if it fails
                              (default — keeps the demo robust)
- EXTRACTION_BACKEND=pfidp  -> legacy: call pf-idp-processing on :8000

The stub returns fields with realistic Indonesian values, plausible bbox
coordinates (centered roughly where the field would sit on a typical page),
and a mix of confidence bands so the green/amber/red colour story still lands.
"""

from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import Any

import httpx

from .config import get_settings
from .extraction_client import ExtractionError, extract as extract_pfidp
from .gemini_extractor import GeminiExtractionError, extract_with_gemini
from .schemas import SCHEMAS

logger = logging.getLogger(__name__)


# A tiny "field bank" of realistic Indonesian values per schema field.
# Picked so each fixture run produces visibly different data, not 10 identical cases.
_INVOICE_VENDOR_POOL = [
    ("PT Alam Sutera Realty", "01.234.567.8-901.000"),
    ("PT Karyagraha Mandiri", "02.345.678.9-012.000"),
    ("PT Bhumyamca Sekawan", "03.456.789.0-123.000"),
    ("PT Grand Indonesia", "04.567.890.1-234.000"),
    ("PT Fairmont Indonesia", "05.678.901.2-345.000"),
    ("PT Tangerang City", "06.789.012.3-456.000"),
    ("PT Sentra Multi Karya", "07.890.123.4-567.000"),
]

_INVOICE_NUMBER_POOL = [
    "INV/2025/IX/00125", "INV/2025/IX/00214", "INV-2025-09-0033",
    "025.EC.IX.2025", "ELC.KN.2025.IX.057", "DN.1042602", "0388.GI.EL.M.09.25",
]

_AMOUNT_POOL_IDR = [
    8_750_000, 12_400_000, 15_250_000, 22_900_000, 35_600_000,
    47_300_000, 68_500_000, 92_100_000, 125_000_000, 187_500_000,
]


def _stub_invoice_fields(seed: str) -> list[dict[str, Any]]:
    """Build a plausible invoice extraction. seed makes runs deterministic per case."""
    rng = random.Random(seed)
    vendor_name, vendor_npwp = rng.choice(_INVOICE_VENDOR_POOL)
    invoice_number = rng.choice(_INVOICE_NUMBER_POOL)
    total = rng.choice(_AMOUNT_POOL_IDR)
    tax = round(total * 0.11)  # PPN 11%
    invoice_date = f"2025-{rng.randint(7, 9):02d}-{rng.randint(1, 28):02d}"
    due_date = f"2025-{rng.randint(10, 11):02d}-{rng.randint(1, 28):02d}"

    # Confidence is intentionally a mix: some green (>=0.85), some amber
    # (0.70-0.85), occasionally red (<0.70). This is what makes the click-the-
    # amber-field beat work in the demo.
    def conf(low: float, high: float) -> float:
        return round(rng.uniform(low, high), 2)

    # Bbox coordinates are in "PDF user space" (typical A4: 1240x1754 px when
    # rasterised at ~150 dpi). Roughly placed where these fields tend to
    # appear on real Indonesian invoices.
    return [
        {"name": "vendor_name", "value": vendor_name, "confidence": conf(0.88, 0.97),
         "bounding_box": {"x": 90, "y": 110, "width": 380, "height": 26, "page": 1},
         "field_type": "string", "description": "Vendor name as printed",
         "provenance": "ai", "history": []},
        {"name": "vendor_npwp", "value": vendor_npwp, "confidence": conf(0.78, 0.92),
         "bounding_box": {"x": 90, "y": 145, "width": 260, "height": 22, "page": 1},
         "field_type": "string", "description": "Vendor NPWP / tax ID",
         "provenance": "ai", "history": []},
        {"name": "invoice_number", "value": invoice_number, "confidence": conf(0.83, 0.95),
         "bounding_box": {"x": 880, "y": 145, "width": 230, "height": 22, "page": 1},
         "field_type": "string", "description": "Invoice number",
         "provenance": "ai", "history": []},
        {"name": "invoice_date", "value": invoice_date, "confidence": conf(0.86, 0.96),
         "bounding_box": {"x": 880, "y": 175, "width": 150, "height": 22, "page": 1},
         "field_type": "string", "description": "Invoice issue date",
         "provenance": "ai", "history": []},
        {"name": "due_date", "value": due_date, "confidence": conf(0.72, 0.84),
         "bounding_box": {"x": 880, "y": 205, "width": 150, "height": 22, "page": 1},
         "field_type": "string", "description": "Payment due date",
         "provenance": "ai", "history": []},
        {"name": "currency", "value": "IDR", "confidence": conf(0.93, 0.99),
         "bounding_box": {"x": 720, "y": 1100, "width": 50, "height": 22, "page": 1},
         "field_type": "string", "description": "Currency code",
         "provenance": "ai", "history": []},
        {"name": "invoice_total", "value": str(total), "confidence": conf(0.65, 0.82),
         "bounding_box": {"x": 800, "y": 1140, "width": 220, "height": 30, "page": 1},
         "field_type": "number", "description": "Total amount due",
         "provenance": "ai", "history": []},
        {"name": "tax_amount", "value": str(tax), "confidence": conf(0.74, 0.88),
         "bounding_box": {"x": 800, "y": 1090, "width": 220, "height": 26, "page": 1},
         "field_type": "number", "description": "Tax / VAT amount",
         "provenance": "ai", "history": []},
    ]


def _stub_faktur_pajak_fields(seed: str) -> list[dict[str, Any]]:
    rng = random.Random(seed + "_fp")
    pkp_name, pkp_npwp = rng.choice(_INVOICE_VENDOR_POOL)
    counterparty_npwp = "01.000.001.2-052.000"  # stand-in for Telkom
    fp_number = f"010.00{rng.randint(0, 9)}-{rng.randint(20, 25)}.{rng.randint(10000000, 99999999)}"
    dpp = rng.choice(_AMOUNT_POOL_IDR)
    ppn = round(dpp * 0.11)
    txn_date = f"2025-{rng.randint(7, 9):02d}-{rng.randint(1, 28):02d}"

    def conf(low: float, high: float) -> float:
        return round(rng.uniform(low, high), 2)

    return [
        {"name": "pkp_name", "value": pkp_name, "confidence": conf(0.86, 0.96),
         "bounding_box": {"x": 90, "y": 220, "width": 380, "height": 26, "page": 1},
         "field_type": "string", "description": "PKP (taxpayer) name",
         "provenance": "ai", "history": []},
        {"name": "pkp_npwp", "value": pkp_npwp, "confidence": conf(0.84, 0.94),
         "bounding_box": {"x": 90, "y": 255, "width": 260, "height": 22, "page": 1},
         "field_type": "string", "description": "PKP NPWP",
         "provenance": "ai", "history": []},
        {"name": "lawan_transaksi_npwp", "value": counterparty_npwp, "confidence": conf(0.76, 0.88),
         "bounding_box": {"x": 90, "y": 360, "width": 260, "height": 22, "page": 1},
         "field_type": "string", "description": "Counterparty NPWP",
         "provenance": "ai", "history": []},
        {"name": "faktur_pajak_number", "value": fp_number, "confidence": conf(0.88, 0.97),
         "bounding_box": {"x": 800, "y": 130, "width": 320, "height": 28, "page": 1},
         "field_type": "string", "description": "Faktur Pajak serial number",
         "provenance": "ai", "history": []},
        {"name": "transaction_date", "value": txn_date, "confidence": conf(0.80, 0.92),
         "bounding_box": {"x": 800, "y": 165, "width": 150, "height": 22, "page": 1},
         "field_type": "string", "description": "Transaction date",
         "provenance": "ai", "history": []},
        {"name": "dpp", "value": str(dpp), "confidence": conf(0.70, 0.83),
         "bounding_box": {"x": 800, "y": 950, "width": 220, "height": 26, "page": 1},
         "field_type": "number", "description": "DPP — taxable base",
         "provenance": "ai", "history": []},
        {"name": "ppn", "value": str(ppn), "confidence": conf(0.68, 0.80),
         "bounding_box": {"x": 800, "y": 985, "width": 220, "height": 26, "page": 1},
         "field_type": "number", "description": "PPN — VAT amount",
         "provenance": "ai", "history": []},
    ]


_STUB_BUILDERS = {
    "schema_invoice_v1": _stub_invoice_fields,
    "schema_faktur_pajak_v1": _stub_faktur_pajak_fields,
}


def _stub_extract(document_bytes: bytes, schema_id: str, *, seed: str) -> dict[str, Any]:
    builder = _STUB_BUILDERS.get(schema_id)
    if builder is None:
        raise ValueError(f"no stub builder for schema_id={schema_id}")
    fields = builder(seed)
    overall = round(sum(f["confidence"] for f in fields) / len(fields), 3)
    return {
        "fields": fields,
        "overall_confidence": overall,
        "page_count": 1,
        "pages_processed": 1,
        "page_dimensions": [{"page": 1, "width": 1240, "height": 1754}],
    }


async def extract_for_demo(
    document_bytes: bytes,
    schema_id: str,
    *,
    seed: str | None = None,
) -> tuple[dict[str, Any], str]:
    """Top-level extraction entry point used by the upload route.

    Returns (extraction_response, backend_used) where backend_used is one of
    "real", "stub", or "pfidp". The route hands `extraction_response` back
    through the same translation logic regardless of backend.
    """
    import os
    backend = os.getenv("EXTRACTION_BACKEND", "auto").lower()

    if schema_id not in SCHEMAS:
        raise ValueError(f"unknown schema_id: {schema_id}")
    schema = SCHEMAS[schema_id]
    seed_value = seed or schema_id

    if backend == "stub":
        logger.info("extractor: stub mode (forced)")
        return _stub_extract(document_bytes, schema_id, seed=seed_value), "stub"

    if backend == "pfidp":
        logger.info("extractor: pf-idp HTTP mode (forced)")
        result = await extract_pfidp(document_bytes, schema)
        return result, "pfidp"

    if backend == "real":
        logger.info("extractor: gemini-direct mode (forced)")
        result = await extract_with_gemini(document_bytes, schema)
        return result, "real"

    # auto: try gemini-direct, fall back to stub
    try:
        result = await extract_with_gemini(document_bytes, schema)
        return result, "real"
    except GeminiExtractionError as e:
        logger.warning(
            "extractor: gemini failed (%s) — falling back to stub", e,
        )
        return _stub_extract(document_bytes, schema_id, seed=seed_value), "stub"
