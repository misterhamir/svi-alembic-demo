"""Seeded JSON schemas the demo passes to pf-idp-processing during extraction.

These are a 1:1 copy of the schemas spelled out in DATA-CONTRACTS.md. Keeping them
in code (not JSON files) so a misedit shows up in IDE/linters rather than at runtime.

If you change a schema here, update DATA-CONTRACTS.md to match — the doc is the
contract, this file is the implementation.
"""

from typing import Any

# ---------------------------------------------------------------------------
# schema_invoice_v1 — Indonesian Commercial Invoice (Tagihan / Invoice komersial)
# ---------------------------------------------------------------------------
INVOICE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "vendor_name": {
            "type": "string",
            "description": "Vendor name as printed on the invoice",
        },
        "vendor_npwp": {
            "type": "string",
            "description": "Vendor NPWP / tax ID",
        },
        "invoice_number": {
            "type": "string",
            "description": "Invoice number",
        },
        "invoice_date": {
            "type": "string",
            "description": "Invoice issue date (YYYY-MM-DD)",
        },
        "due_date": {
            "type": "string",
            "description": "Payment due date (YYYY-MM-DD)",
        },
        "currency": {
            "type": "string",
            "description": "Currency code, e.g. IDR",
        },
        "invoice_total": {
            "type": "number",
            "description": "Total amount due",
        },
        "tax_amount": {
            "type": "number",
            "description": "Tax / VAT amount",
        },
        "line_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "quantity": {"type": "number"},
                    "unit_price": {"type": "number"},
                    "amount": {"type": "number"},
                },
            },
        },
        "terms": {
            "type": "string",
            "description": "Payment terms",
        },
    },
    "required": ["vendor_name", "invoice_number", "invoice_total"],
}


# ---------------------------------------------------------------------------
# schema_faktur_pajak_v1 — Indonesian VAT invoice (DJP-issued)
# ---------------------------------------------------------------------------
FAKTUR_PAJAK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "pkp_name": {
            "type": "string",
            "description": "PKP (taxpayer) name",
        },
        "pkp_npwp": {
            "type": "string",
            "description": "PKP NPWP",
        },
        "lawan_transaksi_npwp": {
            "type": "string",
            "description": "Counterparty NPWP",
        },
        "faktur_pajak_number": {
            "type": "string",
            "description": "Faktur Pajak serial number",
        },
        "transaction_date": {
            "type": "string",
            "description": "Transaction date",
        },
        "dpp": {
            "type": "number",
            "description": "DPP — taxable base",
        },
        "ppn": {
            "type": "number",
            "description": "PPN — VAT amount",
        },
        "ppnbm": {
            "type": "number",
            "description": "PPnBM — luxury tax (if applicable)",
        },
    },
    "required": [
        "pkp_npwp",
        "lawan_transaksi_npwp",
        "faktur_pajak_number",
        "dpp",
        "ppn",
    ],
}


# Lookup table keyed by schema_id (used by the extractor + UI)
SCHEMAS: dict[str, dict[str, Any]] = {
    "schema_invoice_v1": INVOICE_SCHEMA,
    "schema_faktur_pajak_v1": FAKTUR_PAJAK_SCHEMA,
}


# Confidence bands for color rendering (mirrors DATA-CONTRACTS.md)
# Exposed via GET /api/config/thresholds in Phase 2.
CONFIDENCE_BANDS: dict[str, dict[str, Any]] = {
    "green": {"min": 0.85, "max": 1.01, "fg": "#385723", "bg": "#E2EFDA"},
    "amber": {"min": 0.70, "max": 0.85, "fg": "#806000", "bg": "#FFF2CC"},
    "red": {"min": 0.0, "max": 0.70, "fg": "#823535", "bg": "#FBE4E4"},
}
