from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.core.observability import (
    RequestMetrics,
    RequestObservabilityMiddleware,
    readiness_payload,
    request_metrics_payload,
)
from app.core.settings import Settings, load_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or load_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.accepting_traffic = True
        try:
            yield
        finally:
            application.state.accepting_traffic = False

    app = FastAPI(
        title="Invoice Review API",
        description="Runnable foundation for the invoice review reconstruction.",
        version="0.1.0-m01",
        lifespan=lifespan,
    )
    app.state.settings = resolved
    app.state.accepting_traffic = True
    app.state.request_metrics = RequestMetrics()
    app.add_middleware(RequestObservabilityMiddleware, metrics=app.state.request_metrics)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    def ready() -> JSONResponse:
        payload = readiness_payload(
            lifecycle_ready=bool(app.state.accepting_traffic),
            database_ready=resolved.database_ready,
            storage_ready=resolved.storage_ready,
        )
        return JSONResponse(
            status_code=200 if payload["status"] == "ready" else 503,
            content=payload,
        )

    @app.get("/internal/runtime-summary")
    def runtime_summary() -> dict[str, object]:
        return {
            "environment": resolved.environment,
            "metrics": request_metrics_payload(app.state.request_metrics),
        }

    return app


app = create_app()
