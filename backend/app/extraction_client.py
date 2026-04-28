"""Thin async wrapper around pf-idp-processing's POST /api/v1/extract.

This is the only place in the demo backend that talks to the extraction service.
Phase 2 routes (upload) call into here; the smoke-test script calls into here too.

Mental model: think of pf-idp-processing as an "HTTP node" in n8n — we pass it a
PDF and a schema, it returns structured fields with confidence + bounding boxes.
The shape it returns is documented in DATA-CONTRACTS.md under "pf-idp-processing
API". We keep its shape unchanged inside this module and translate it into the
case shape one layer up (in the upload route).
"""

from __future__ import annotations

import base64
import logging
from typing import Any

import httpx

from .config import get_settings

logger = logging.getLogger(__name__)


class ExtractionError(Exception):
    """Raised when pf-idp-processing returns a non-2xx response."""

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"extraction service returned {status_code}: {body[:300]}")


async def extract(
    document_bytes: bytes,
    schema: dict[str, Any] | None = None,
    *,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Send a PDF/image to pf-idp-processing and return the parsed extraction.

    Args:
        document_bytes: raw PDF or image bytes. The service auto-detects PDF vs image.
        schema: a JSON-Schema-like dict describing the fields to extract.
            Pass None for discovery mode (auto-detect fields). For the heart-of-pitch
            demo flow we always pass a schema.
        timeout: request timeout in seconds. Defaults to settings.extraction_timeout_seconds.

    Returns:
        The full JSON body returned by pf-idp-processing — see DATA-CONTRACTS.md
        section "pf-idp-processing API". Notable keys: "fields", "overall_confidence",
        "page_count", "pages_processed", "page_dimensions".

    Raises:
        ExtractionError: if the service returns non-2xx.
        httpx.TimeoutException: if the request times out (cold-start can be slow).
    """
    settings = get_settings()
    url = f"{settings.extraction_service_url}/api/v1/extract"

    payload: dict[str, Any] = {
        "document": base64.b64encode(document_bytes).decode("ascii"),
    }
    if schema is not None:
        # The service exposes the field as "schema" externally (alias) even
        # though internally it's bound to extraction_schema. We send "schema".
        payload["schema"] = schema

    effective_timeout = timeout if timeout is not None else settings.extraction_timeout_seconds

    logger.info(
        "calling extraction service: url=%s schema_keys=%s bytes=%d timeout=%.0fs",
        url,
        list((schema or {}).get("properties", {}).keys()) or None,
        len(document_bytes),
        effective_timeout,
    )

    async with httpx.AsyncClient(timeout=effective_timeout) as client:
        response = await client.post(url, json=payload)

    if response.status_code >= 300:
        raise ExtractionError(response.status_code, response.text)

    body = response.json()
    logger.info(
        "extraction ok: overall_confidence=%.3f field_count=%d pages=%s",
        body.get("overall_confidence", 0.0),
        len(body.get("fields", [])),
        body.get("pages_processed"),
    )
    return body


def extract_sync(
    document_bytes: bytes,
    schema: dict[str, Any] | None = None,
    *,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Synchronous convenience wrapper for scripts that don't run an event loop.

    Used by scripts/smoke_test_extraction.py. Application code (FastAPI routes)
    should use the async `extract` directly.
    """
    settings = get_settings()
    url = f"{settings.extraction_service_url}/api/v1/extract"

    payload: dict[str, Any] = {
        "document": base64.b64encode(document_bytes).decode("ascii"),
    }
    if schema is not None:
        payload["schema"] = schema

    effective_timeout = timeout if timeout is not None else settings.extraction_timeout_seconds

    with httpx.Client(timeout=effective_timeout) as client:
        response = client.post(url, json=payload)

    if response.status_code >= 300:
        raise ExtractionError(response.status_code, response.text)

    return response.json()
