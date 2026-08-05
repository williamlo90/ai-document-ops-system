from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from app.api.exceptions import http_problem_handler
from app.api.serializers import (
    HealthResponse,
    ProblemResponse,
    ReadinessResponse,
    RuntimeSummaryResponse,
    ServiceMetadataResponse,
)
from app.bootstrap.container import build_container
from app.core.observability import (
    RequestMetrics,
    RequestObservabilityMiddleware,
    readiness_payload,
    request_metrics_payload,
)
from app.core.settings import Settings, load_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or load_settings()
    container = build_container(resolved)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.accepting_traffic = True
        try:
            yield
        finally:
            application.state.accepting_traffic = False

    app = FastAPI(
        title="Invoice Review API",
        description="Stable read-only contracts for the invoice review service.",
        version="0.2.0-m03",
        lifespan=lifespan,
    )
    app.add_exception_handler(HTTPException, http_problem_handler)
    app.state.settings = resolved
    app.state.container = container
    app.state.accepting_traffic = True
    app.state.request_metrics = RequestMetrics()
    app.add_middleware(RequestObservabilityMiddleware, metrics=app.state.request_metrics)

    problem_responses: dict[int | str, dict[str, Any]] = {404: {"model": ProblemResponse}}

    @app.get(
        "/health",
        operation_id="getHealth",
        response_model=HealthResponse,
        responses=problem_responses,
    )
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.get(
        "/ready",
        operation_id="getReadiness",
        response_model=ReadinessResponse,
        responses={503: {"model": ReadinessResponse}},
    )
    def ready() -> JSONResponse:
        dependencies = container.readiness()
        payload = readiness_payload(
            lifecycle_ready=bool(app.state.accepting_traffic),
            database_ready=dependencies["database"],
            storage_ready=dependencies["storage"],
        )
        return JSONResponse(
            status_code=200 if payload["status"] == "ready" else 503,
            content=payload,
        )

    @app.get(
        "/internal/runtime-summary",
        operation_id="getRuntimeSummary",
        response_model=RuntimeSummaryResponse,
    )
    def runtime_summary() -> RuntimeSummaryResponse:
        return RuntimeSummaryResponse(
            environment=resolved.environment,
            metrics=request_metrics_payload(app.state.request_metrics),
        )

    @app.get(
        "/meta",
        operation_id="getServiceMetadata",
        response_model=ServiceMetadataResponse,
        responses=problem_responses,
    )
    def metadata() -> ServiceMetadataResponse:
        return ServiceMetadataResponse()

    @app.get("/meta/{key}", operation_id="getMetadataValue", responses=problem_responses)
    def metadata_value(key: str) -> dict[str, str]:
        if key != "document-type":
            raise HTTPException(status_code=404, detail="Metadata key not found")
        return {"key": key, "value": "invoice"}

    return app


app = create_app()
