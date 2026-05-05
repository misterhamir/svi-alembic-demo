"""svi-demo backend — FastAPI entry point.

Phase 1: minimal app with /api/health and /ui static mount. Subsequent phases
will register more routers (cases, mock_erp, config) — they live alongside this
file in app/ and get wired in here.

Run from the svi-demo/ directory:

    uvicorn backend.app.main:app --port 8080 --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import mock_erp, storage, workflows
from .config import get_settings
from .routes import cases as cases_routes
from .routes import metrics as metrics_routes
from .routes import flywheel as flywheel_routes

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown hooks. Phase 1 just configures logging."""
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
        force=True,
    )
    logger.info("=== svi-demo backend starting ===")
    logger.info("extraction_service_url: %s", settings.extraction_service_url)
    logger.info("storage_backend: %s", settings.storage_backend)
    logger.info("ui_dir: %s (exists=%s)", settings.ui_dir, settings.ui_dir.exists())

    # Make sure data/ + uploads/ exist so future phases can write into them
    # without a 'first write fails' surprise.
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)

    # Initialise the SQLite cases table on boot. Idempotent.
    await storage.init_storage()

    yield

    logger.info("=== svi-demo backend shutting down ===")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="svi-demo backend",
        description="Sales-demo orchestration layer for SVI Alembic ADP",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Permissive CORS — the demo runs entirely on localhost so this is fine.
    # Real product gets a stricter policy.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    # Wire case routes (Phase 2) and mock ERP (Phase 3).
    app.include_router(cases_routes.router)
    app.include_router(mock_erp.router)
    app.include_router(workflows.router)
    app.include_router(metrics_routes.router)
    app.include_router(flywheel_routes.router)

    # Static UI mount. The svi-alembic-ui screens live in ../ui/ relative
    # to backend/, copied in during Phase 4 / Phase 6. The mount is created
    # even if the dir is empty so the path exists from boot.
    if settings.ui_dir.exists():
        app.mount(
            "/ui",
            StaticFiles(directory=str(settings.ui_dir), html=True),
            name="ui",
        )
        logger.info("mounted /ui from %s", settings.ui_dir)
    else:
        logger.warning("ui dir not found: %s — /ui will 404 until Phase 4", settings.ui_dir)

    @app.get("/")
    def root() -> RedirectResponse:
        # Land users at /ui/ so they get the operator queue once it's wired.
        return RedirectResponse(url="/ui/")

    return app


app = create_app()
