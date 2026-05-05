"""SQLite-backed case storage.

Mental model: one big spreadsheet of cases. Each row holds the entire case JSON
in a `payload` column. We pull a few fields (state, created_at, subject) into
their own indexed columns so the queue page can filter/sort cheaply, but the
source of truth is the JSON blob — that's what gets returned by /api/cases/{id}.

Why JSON-in-a-column instead of a relational schema with a documents table and
a fields table:
- The case shape is documented once, in DATA-CONTRACTS.md, and matches what the
  browser receives. Splitting it across 3-4 normalized tables would mean joining
  + reassembling on every read. That's overhead the demo doesn't need.
- All updates are at the case level (correct one field, advance state). We never
  query "find all fields with confidence < 0.7 across all cases" — that's a
  product feature we're explicitly NOT building.
- SQLite handles JSON gracefully via the json1 extension (sqlite3 standard).
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

import aiosqlite

from .config import get_settings

logger = logging.getLogger(__name__)


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS cases (
    case_id     TEXT PRIMARY KEY,
    state       TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    subject     TEXT,
    payload     TEXT NOT NULL  -- full case JSON (DATA-CONTRACTS.md shape)
);

CREATE INDEX IF NOT EXISTS idx_cases_state ON cases(state);
CREATE INDEX IF NOT EXISTS idx_cases_created_at ON cases(created_at);
"""


def _db_path() -> Path:
    return get_settings().sqlite_db_path


async def _apply_pragmas(db: aiosqlite.Connection) -> None:
    """Pragmas that make SQLite portable across local disks and sandbox mounts.

    journal_mode=MEMORY skips creating the on-disk .db-journal file, which
    some FUSE-style mounts don't support. The trade-off is that an OS crash
    mid-write could corrupt the DB — fine for a demo, not fine for prod.
    synchronous=NORMAL relaxes fsyncs for the same reason.
    """
    await db.execute("PRAGMA journal_mode=MEMORY")
    await db.execute("PRAGMA synchronous=NORMAL")


async def init_storage() -> None:
    """Create the SQLite file + schema if missing. Idempotent."""
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(_db_path()) as db:
        await _apply_pragmas(db)
        await db.executescript(_SCHEMA_SQL)
        await db.commit()
    logger.info("storage initialised at %s", _db_path())


@asynccontextmanager
async def _connect() -> AsyncIterator[aiosqlite.Connection]:
    """Yield a connection with row_factory set to return dicts."""
    db = await aiosqlite.connect(_db_path())
    try:
        await _apply_pragmas(db)
        db.row_factory = aiosqlite.Row
        yield db
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# Case CRUD
# ---------------------------------------------------------------------------

async def create_case(case: dict[str, Any]) -> None:
    """Insert a new case. Payload is the full case dict per DATA-CONTRACTS.md."""
    async with _connect() as db:
        await db.execute(
            "INSERT INTO cases (case_id, state, created_at, subject, payload) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                case["case_id"],
                case["state"],
                case["created_at"],
                case.get("subject"),
                json.dumps(case),
            ),
        )
        await db.commit()
    logger.info("case created: %s state=%s", case["case_id"], case["state"])


async def get_case(case_id: str) -> dict[str, Any] | None:
    async with _connect() as db:
        async with db.execute(
            "SELECT payload FROM cases WHERE case_id = ?", (case_id,)
        ) as cur:
            row = await cur.fetchone()
    if row is None:
        return None
    return json.loads(row["payload"])


async def list_cases(
    state: str | None = None,
    limit: int = 50,
) -> tuple[list[dict[str, Any]], int]:
    """Return (rows, total). Rows are queue-shaped summaries, not full payloads.

    The queue endpoint per DATA-CONTRACTS.md returns a small subset per case:
    case_id, subject, state, created_at, doc_count, overall_confidence,
    responsible. We compute these by reading the payload JSON. For ~10-50 cases
    in a demo this is fine; if it ever became 10k cases we'd promote those
    fields to columns.
    """
    sql = "SELECT case_id, payload FROM cases"
    params: list[Any] = []
    if state:
        sql += " WHERE state = ?"
        params.append(state)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    async with _connect() as db:
        async with db.execute(sql, params) as cur:
            rows_raw = await cur.fetchall()
        async with db.execute(
            "SELECT COUNT(*) AS n FROM cases" + (" WHERE state = ?" if state else ""),
            ([state] if state else []),
        ) as cur:
            total_row = await cur.fetchone()
            total = int(total_row["n"]) if total_row else 0

    rows: list[dict[str, Any]] = []
    for r in rows_raw:
        full = json.loads(r["payload"])
        rows.append(_to_queue_summary(full))
    return rows, total


def _to_queue_summary(case: dict[str, Any]) -> dict[str, Any]:
    """Project a full case payload down to the queue-row shape."""
    docs = case.get("documents", [])
    # overall_confidence is per-document in pf-idp's response; for the queue
    # we surface the lowest of any doc — that's the one most likely to need
    # human attention, which is the spirit of the column.
    confidences = [d.get("overall_confidence") for d in docs if d.get("overall_confidence") is not None]
    overall = min(confidences) if confidences else None
    return {
        "case_id": case["case_id"],
        "subject": case.get("subject"),
        "state": case["state"],
        "created_at": case["created_at"],
        "doc_count": len(docs),
        "overall_confidence": overall,
        "responsible": case.get("responsible"),
    }


_UNSET: Any = object()


async def update_state(
    case_id: str,
    new_state: str,
    *,
    history_event: dict[str, Any] | None = None,
    integration_error: Any = _UNSET,
    integration_result: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Advance a case's state and append an optional history entry.

    Phase 3's state machine drives this. Pass `integration_error` to set or
    clear the integration_error block (None clears, a dict sets, omit to leave
    it as-is). `integration_result` is logged into history so the presenter
    can show the 201 path.
    """
    case = await get_case(case_id)
    if case is None:
        return None
    case["state"] = new_state
    if history_event:
        case.setdefault("history", []).append(history_event)
    if integration_error is not _UNSET:
        case["integration_error"] = integration_error
    if integration_result is not None:
        # Don't store on the case body — keep history as the audit trail.
        case.setdefault("history", []).append({
            "at": _now_iso(),
            "actor": "system",
            "event": "integration_success",
            "detail": integration_result,
        })

    async with _connect() as db:
        await db.execute(
            "UPDATE cases SET state = ?, payload = ? WHERE case_id = ?",
            (new_state, json.dumps(case), case_id),
        )
        await db.commit()
    logger.info("case %s -> state=%s", case_id, new_state)
    return case


async def update_field(
    case_id: str,
    doc_id: str,
    field_name: str,
    new_value: Any,
    actor: str,
) -> dict[str, Any] | None:
    """Patch a single field inside a doc; flip provenance to 'human'.

    Returns the updated field dict, or None if the case/doc/field wasn't found.
    """
    case = await get_case(case_id)
    if case is None:
        return None

    target_field: dict[str, Any] | None = None
    for doc in case.get("documents", []):
        if doc.get("doc_id") != doc_id:
            continue
        for f in doc.get("fields", []):
            if f.get("name") == field_name:
                old_value = f.get("value")
                f["value"] = new_value
                f["provenance"] = "human"
                f.setdefault("history", []).append({
                    "at": _now_iso(),
                    "actor": actor,
                    "from": old_value,
                    "to": new_value,
                })
                target_field = f
                break
        if target_field is not None:
            break

    if target_field is None:
        return None

    case.setdefault("history", []).append({
        "at": _now_iso(),
        "actor": actor,
        "event": "field_corrected",
        "detail": {"doc_id": doc_id, "field": field_name},
    })

    async with _connect() as db:
        await db.execute(
            "UPDATE cases SET payload = ? WHERE case_id = ?",
            (json.dumps(case), case_id),
        )
        await db.commit()
    logger.info("case %s field corrected: %s.%s by %s", case_id, doc_id, field_name, actor)
    return target_field


async def get_case_stats() -> dict[str, Any]:
    """Aggregate field and correction stats across all cases for metrics/flywheel."""
    async with _connect() as db:
        async with db.execute("SELECT payload FROM cases") as cur:
            rows = await cur.fetchall()

    total_fields = 0
    total_corrections = 0
    confidence_values: list[float] = []
    field_stats: dict[str, dict[str, int]] = {}  # name -> {total, corrections}
    case_dates: list[str] = []                    # YYYY-MM-DD
    correction_dates: list[str] = []              # YYYY-MM-DD of each correction

    for row in rows:
        case = json.loads(row["payload"])
        created_at = case.get("created_at", "")
        if created_at:
            case_dates.append(created_at[:10])

        for doc in case.get("documents", []):
            for field in doc.get("fields", []):
                total_fields += 1
                fname = field.get("name", "unknown")
                conf = field.get("confidence")
                if conf is not None:
                    try:
                        confidence_values.append(float(conf))
                    except (TypeError, ValueError):
                        pass

                fs = field_stats.setdefault(fname, {"total": 0, "corrections": 0})
                fs["total"] += 1

                if field.get("provenance") == "human":
                    total_corrections += 1
                    fs["corrections"] += 1
                    for h in field.get("history", []):
                        if "from" in h and h.get("at"):
                            correction_dates.append(h["at"][:10])
                            break

    return {
        "case_count": len(rows),
        "total_fields": total_fields,
        "total_corrections": total_corrections,
        "confidence_values": confidence_values,
        "field_stats": field_stats,
        "case_dates": case_dates,
        "correction_dates": correction_dates,
    }


async def force_save(case: dict[str, Any]) -> None:
    """Overwrite the stored payload and state for a case. Used by demo reset."""
    case_id = case["case_id"]
    async with _connect() as db:
        await db.execute(
            "UPDATE cases SET state = ?, payload = ? WHERE case_id = ?",
            (case["state"], json.dumps(case), case_id),
        )
        await db.commit()
    logger.info("case %s force-saved (state=%s)", case_id, case["state"])


async def wipe_all() -> None:
    """Hard reset: delete every case. Used by scripts/reset.py."""
    async with _connect() as db:
        await db.execute("DELETE FROM cases")
        await db.commit()
    logger.info("storage wiped")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
