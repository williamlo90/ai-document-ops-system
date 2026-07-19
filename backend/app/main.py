from __future__ import annotations

import atexit
from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.dependencies import build_container
from app.core.observability import (
    HttpMetrics,
    RequestObservabilityMiddleware,
    configure_structured_logging,
    readiness_payload,
)
from app.api.agent import router as agent_router
from app.api.agentops import router as agentops_router
from app.api.backoffice import router as backoffice_router
from app.api.documents import router as documents_router
from app.api.exports import router as exports_router
from app.api.integrations import router as integrations_router
from app.api.invoices import router as invoices_router
from app.api.metrics import router as metrics_router
from app.api.providers import router as providers_router
from app.api.operations import router as operations_router
from app.api.review import router as review_router
from app.api.auth import router as auth_router
from app.core.security import validate_access_token_policy, validate_public_demo_provider_policy
from app.core.security import SessionStore
from app.core.http_security import (
    CsrfOriginMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
)
from app.core.settings import Settings, is_hosted, load_settings
from app.api.legacy_redirects import router as legacy_redirect_router


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or load_settings()
    validate_access_token_policy(resolved_settings)
    validate_public_demo_provider_policy(resolved_settings)
    hosted = is_hosted(resolved_settings)
    configure_structured_logging()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.accepting_traffic = True
        logging.getLogger("docintel.lifecycle").info("application_started")
        try:
            yield
        finally:
            application.state.accepting_traffic = False
            application.state.container.close()
            logging.getLogger("docintel.lifecycle").info("application_stopping")

    app = FastAPI(
        title="AI Document Operations System",
        description=(
            "Local-first document intake, evidence validation, human review, "
            "controlled execution, and reliability evaluation. Invoice is the first "
            "fully supported document workflow."
        ),
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if hosted else "/docs",
        redoc_url=None if hosted else "/redoc",
        openapi_url=None if hosted else "/openapi.json",
    )
    app.state.accepting_traffic = True
    app.state.http_metrics = HttpMetrics()
    app.add_middleware(RequestObservabilityMiddleware, metrics=app.state.http_metrics)
    app.state.container = build_container(resolved_settings)
    app.state.sessions = SessionStore(resolved_settings.session_ttl_seconds)
    app.state.container._app_sessions = app.state.sessions
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CsrfOriginMiddleware,
        settings=resolved_settings,
        cookie_name="doc_intel_admin_token",
    )
    app.add_middleware(
        RateLimitMiddleware,
        requests=resolved_settings.rate_limit_requests,
        window_seconds=resolved_settings.rate_limit_window_seconds,
    )
    app.include_router(documents_router)
    app.include_router(auth_router)
    app.include_router(review_router)
    app.include_router(exports_router)
    app.include_router(integrations_router)
    app.include_router(metrics_router)
    app.include_router(providers_router)
    app.include_router(operations_router)
    app.include_router(agent_router)
    app.include_router(agentops_router)
    app.include_router(backoffice_router)
    app.include_router(invoices_router)
    app.include_router(legacy_redirect_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    def ready():
        if not app.state.accepting_traffic:
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "checks": {"lifecycle": "stopping"}},
            )
        checks = app.state.container.readiness()
        payload = readiness_payload(
            database_ready=checks["database"],
            storage_ready=checks["storage"],
        )
        return JSONResponse(
            status_code=200 if payload["status"] == "ready" else 503,
            content=payload,
        )

    @app.get("/internal/metrics", response_class=PlainTextResponse)
    def runtime_metrics() -> str:
        return app.state.http_metrics.prometheus()

    frontend_dist = _frontend_dist()
    if frontend_dist is not None:
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")

    return app


def _frontend_dist() -> Path | None:
    candidates = (
        Path("frontend/dist"),
        Path("../frontend/dist"),
        Path("/app/frontend/dist"),
    )
    return next((path.resolve() for path in candidates if path.is_dir()), None)


app = create_app()
atexit.register(app.state.container.close)
