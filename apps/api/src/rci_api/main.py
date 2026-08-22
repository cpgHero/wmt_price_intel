"""FastAPI application factory and service endpoints."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Protocol

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from rci_api.analyses import router as analysis_router
from rci_api.automation import router as automation_router
from rci_api.collections import router as collection_router
from rci_api.competitive_leadership import router as competitive_leadership_router
from rci_api.locations import router as location_router
from rci_api.matching_v2 import router as matching_v2_router
from rci_api.matching_v2_review import router as matching_v2_review_router
from rci_api.price_monitoring import router as price_monitoring_router
from rci_api.product_packs import (
    router as product_pack_router,
)
from rci_api.product_packs import (
    synchronize_product_pack_catalog,
)
from rci_api.report_publication import router as report_publication_router
from rci_api.studies import router as study_router
from rci_core import APP_VERSION, AppSettings
from rci_db import DatabaseProbe


class ReadinessProbe(Protocol):
    async def is_ready(self) -> bool: ...

    async def dispose(self) -> None: ...


def create_app(settings: AppSettings | None = None) -> FastAPI:
    resolved_settings = settings or AppSettings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.database_probe = DatabaseProbe(resolved_settings.database_url)
        try:
            if resolved_settings.is_production:
                repository_root = Path(os.getenv("RCI_REPOSITORY_ROOT", Path.cwd())).resolve()
                await synchronize_product_pack_catalog(
                    app.state.database_probe.engine,
                    repository_root,
                )
            yield
        finally:
            await app.state.database_probe.dispose()

    app = FastAPI(
        title="Retail Competitive Intelligence API",
        version=resolved_settings.app_version,
        docs_url="/api/docs" if not resolved_settings.is_production else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if not resolved_settings.is_production else None,
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.include_router(analysis_router)
    app.include_router(automation_router)
    app.include_router(collection_router)
    app.include_router(competitive_leadership_router)
    app.include_router(location_router)
    app.include_router(matching_v2_router)
    app.include_router(matching_v2_review_router)
    app.include_router(price_monitoring_router)
    app.include_router(product_pack_router)
    app.include_router(report_publication_router)
    app.include_router(study_router)

    @app.get("/health/live", tags=["health"])
    async def liveness() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "api",
            "version": resolved_settings.app_version,
        }

    @app.get("/health/ready", tags=["health"])
    async def readiness(request: Request) -> JSONResponse:
        probe: ReadinessProbe = request.app.state.database_probe
        ready = await probe.is_ready()
        return JSONResponse(
            status_code=status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "ready" if ready else "not_ready",
                "service": "api",
                "dependencies": {"postgres": "ok" if ready else "unavailable"},
            },
        )

    @app.get("/api/v1/version", tags=["system"])
    async def version() -> dict[str, str]:
        return {"version": resolved_settings.app_version or APP_VERSION}

    return app


app = create_app()
