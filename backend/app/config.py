"""Centralised settings — read once from env, cached for the rest of the process.

Think of this like the credentials/connection panel at the top of an n8n workflow:
one place that defines where external services live and how loud the logs are.
"""

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# Look for a .env file next to backend/, then in svi-demo/, in that order.
# The svi-demo backend folder is parent-of-this-file's-parent.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_DEMO_ROOT = _BACKEND_DIR.parent
load_dotenv(_BACKEND_DIR / ".env")
load_dotenv(_DEMO_ROOT / ".env")


class Settings:
    """Lightweight settings object — no pydantic-settings ceremony needed yet."""

    def __init__(self) -> None:
        self.extraction_service_url: str = os.getenv(
            "EXTRACTION_SERVICE_URL", "http://localhost:8000"
        ).rstrip("/")
        self.gemini_api_key: str | None = os.getenv("GEMINI_API_KEY") or None
        # Default to flash-lite — same model pf-idp uses, less prone to 503
        # rate-limiting than gemini-2.5-flash. Override via env if needed.
        self.gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
        self.storage_backend: str = os.getenv("STORAGE_BACKEND", "sqlite")
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()

        # Path layout. data/ is created lazily by storage; uploads/ inside it
        # holds the original PDFs the operator uploaded (or were seeded).
        self.backend_dir: Path = _BACKEND_DIR
        self.demo_root: Path = _DEMO_ROOT
        self.ui_dir: Path = _DEMO_ROOT / "ui"
        self.data_dir: Path = _BACKEND_DIR / "data"
        self.uploads_dir: Path = self.data_dir / "uploads"
        self.fixtures_dir: Path = _DEMO_ROOT / "fixtures"

        # Optional override for the SQLite file path. Useful in sandboxes
        # whose mount doesn't support SQLite locking; on a real laptop this
        # is unset and the DB lives at data_dir/cases.db.
        _db_override = os.getenv("SQLITE_DB_PATH")
        self.sqlite_db_path: Path = Path(_db_override) if _db_override else self.data_dir / "cases.db"

        # HTTP timeout when calling pf-idp-processing. Gemini extraction can
        # take 10-30s on a multi-page PDF; we give it room.
        self.extraction_timeout_seconds: float = float(
            os.getenv("EXTRACTION_TIMEOUT_SECONDS", "120")
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
