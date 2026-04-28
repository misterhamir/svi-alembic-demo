"""Direct Gemini extraction — bypasses pf-idp-processing.

Self-contained alternative to extraction_client.py. Calls Gemini 2.5 Flash
with the PDF bytes and a schema-shaped prompt, gets back fields with
bounding boxes already grounded by Gemini's spatial reasoning.

Why this exists: Hammam wanted the demo backend self-contained — no
separate pf-idp service to start, key in svi-demo/.env. This module is the
"real" extraction path when EXTRACTION_BACKEND=real.

Coordinate convention:
- Gemini returns bboxes normalised to a 0-1000 box per page.
- We surface page_dimensions={1000, 1000} so the UI's existing scaling
  math (sx = renderedCanvasWidth / page_dimensions.width) lands the
  highlight overlay in the right region without any UI changes.

Trade-offs vs pf-idp:
- Gemini-only — no OCR pre-processing layer (Gemini handles vision natively)
- bboxes are AI-estimated, not pixel-perfect from OCR. Close enough for
  click-to-highlight; not surveyor-grade.
- Single Gemini call per document instead of OCR + SLM hop.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Any

from google import genai
from google.genai import types

from .config import get_settings

logger = logging.getLogger(__name__)


# Gemini Flash-Lite occasionally returns 503/429 under load. Retry a few
# times with backoff before giving up — these are almost always transient.
_RETRYABLE_STATUSES = (429, 503)
_MAX_RETRIES = 4


class GeminiExtractionError(Exception):
    """Raised when Gemini returns nothing usable."""


# Map JSON-schema types to a friendly hint we put in the prompt
_TYPE_HINT = {
    "string": "string (verbatim text from the document)",
    "number": "number (numeric value, no formatting)",
    "integer": "integer",
    "boolean": "boolean (true/false)",
    "array": "array",
    "object": "object",
}


def _build_prompt(schema: dict[str, Any]) -> str:
    properties: dict[str, Any] = schema.get("properties", {})
    required: list[str] = list(schema.get("required", []))

    field_lines: list[str] = []
    for name, props in properties.items():
        if not isinstance(props, dict):
            continue
        # Skip nested arrays/objects in the prompt body — too noisy for the
        # demo's seeded schemas which only use them for line_items.
        ftype = props.get("type", "string")
        desc = props.get("description", "")
        hint = _TYPE_HINT.get(ftype, ftype)
        marker = " [REQUIRED]" if name in required else ""
        field_lines.append(f"  - {name}: {desc} ({hint}){marker}")

    fields_block = "\n".join(field_lines)

    return f"""You are an Indonesian accounts-payable document extraction specialist.
Extract the following fields from the attached PDF.

Fields to extract:
{fields_block}

Rules:
1. Use values exactly as they appear in the document (verbatim text). Do not
   reformat numbers — return the raw digits the document shows.
2. If a field is genuinely absent, return value=null and confidence=0.
3. For each field, give a tight bounding box (just around the printed value,
   not the whole row).
4. Coordinates are normalised: 0..1000 across page width, 0..1000 down page
   height. Origin is top-left.
5. Confidence is your belief that the extracted value is correct (0..1).
6. Pages are 1-indexed.

Return ONLY a JSON object — no prose, no markdown fences."""


# Pydantic-style response schema (passed via google-genai's response_schema)
# is friendlier than asking the model to free-form JSON.
_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "fields": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "value": {"type": "string", "nullable": True},
                    "confidence": {"type": "number"},
                    "field_type": {"type": "string"},
                    "bounding_box": {
                        "type": "object",
                        "properties": {
                            "x": {"type": "number"},
                            "y": {"type": "number"},
                            "width": {"type": "number"},
                            "height": {"type": "number"},
                            "page": {"type": "integer"},
                        },
                        "required": ["x", "y", "width", "height", "page"],
                    },
                },
                "required": ["name", "confidence", "field_type", "bounding_box"],
            },
        },
        "page_count": {"type": "integer"},
    },
    "required": ["fields", "page_count"],
}


# Coordinate space we tell Gemini to use, and that we hand to the UI as
# page_dimensions. The UI scales overlays as (rendered_canvas / dim).
_NORMALISED_DIM = 1000


async def extract_with_gemini(
    document_bytes: bytes,
    schema: dict[str, Any],
) -> dict[str, Any]:
    """Run Gemini extraction. Returns the same shape as extraction_client.extract().

    Raises GeminiExtractionError on any failure — the extractor facade
    falls back to the stub if EXTRACTION_BACKEND=auto.
    """
    settings = get_settings()
    if not settings.gemini_api_key:
        raise GeminiExtractionError(
            "GEMINI_API_KEY is not set in svi-demo/backend/.env"
        )

    client = genai.Client(api_key=settings.gemini_api_key)
    prompt = _build_prompt(schema)

    response = None
    last_error: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=settings.gemini_model,
                contents=[
                    prompt,
                    types.Part.from_bytes(data=document_bytes, mime_type="application/pdf"),
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=_RESPONSE_SCHEMA,
                    temperature=0.1,
                ),
            )
            break
        except Exception as e:
            last_error = e
            status = getattr(e, "code", None) or getattr(e, "status_code", None)
            msg = str(e)
            is_retryable = (
                status in _RETRYABLE_STATUSES
                or "503" in msg or "429" in msg
                or "UNAVAILABLE" in msg or "RESOURCE_EXHAUSTED" in msg
            )
            if not is_retryable or attempt == _MAX_RETRIES - 1:
                raise GeminiExtractionError(
                    f"Gemini API call failed after {attempt + 1} attempts: {type(e).__name__}: {e}"
                ) from e
            # Exponential backoff with jitter: 1s, 2s, 4s, 8s base + 0-500ms jitter
            delay = (2 ** attempt) + random.uniform(0, 0.5)
            logger.warning(
                "gemini retry %d/%d after %.1fs (status=%s): %s",
                attempt + 1, _MAX_RETRIES, delay, status, msg[:120],
            )
            await asyncio.sleep(delay)

    if response is None:
        raise GeminiExtractionError(f"Gemini API call failed: {last_error}")

    text = (response.text or "").strip()
    if not text:
        raise GeminiExtractionError("Gemini returned empty response")

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise GeminiExtractionError(f"Gemini returned invalid JSON: {e}") from e

    raw_fields = parsed.get("fields", [])
    if not isinstance(raw_fields, list):
        raise GeminiExtractionError("Gemini response missing fields array")

    # Normalise into the shape pf-idp/extraction_client returns. Add the bits
    # the rest of the demo code expects (description, provenance, history).
    schema_props: dict[str, Any] = schema.get("properties", {})
    fields: list[dict[str, Any]] = []
    for raw in raw_fields:
        if not isinstance(raw, dict):
            continue
        name = raw.get("name")
        if not name or name not in schema_props:
            # Skip anything Gemini hallucinated that isn't in the schema
            continue
        bbox = raw.get("bounding_box") or {}
        # Clamp into the 0..1000 box in case Gemini went slightly over
        bbox_clamped = {
            "x": max(0, min(_NORMALISED_DIM, float(bbox.get("x", 0)))),
            "y": max(0, min(_NORMALISED_DIM, float(bbox.get("y", 0)))),
            "width": max(0, min(_NORMALISED_DIM, float(bbox.get("width", 0)))),
            "height": max(0, min(_NORMALISED_DIM, float(bbox.get("height", 0)))),
            "page": int(bbox.get("page", 1)),
        }
        prop = schema_props.get(name, {})
        fields.append({
            "name": name,
            "value": raw.get("value"),
            "confidence": float(raw.get("confidence", 0)),
            "bounding_box": bbox_clamped,
            "field_type": raw.get("field_type") or prop.get("type", "string"),
            "description": prop.get("description", ""),
            "provenance": "ai",
            "history": [],
            "children": None,
        })

    if not fields:
        raise GeminiExtractionError("Gemini returned no recognisable fields for this schema")

    page_count = max(1, int(parsed.get("page_count") or 1))
    overall = round(sum(f["confidence"] for f in fields) / len(fields), 3) if fields else 0.0

    return {
        "fields": fields,
        "overall_confidence": overall,
        "page_count": page_count,
        "pages_processed": page_count,
        "page_dimensions": [
            {"page": p, "width": _NORMALISED_DIM, "height": _NORMALISED_DIM}
            for p in range(1, page_count + 1)
        ],
    }
