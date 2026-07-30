from __future__ import annotations

from app.api.dependencies import AppContainer, build_container
from app.core.security import SecurityContext
from app.core.settings import Settings, load_settings


def run_once(container: AppContainer, settings: Settings | None = None) -> bool:
    resolved_settings = settings or container.settings
    result = container.worker_service.run_once(
        context=SecurityContext(
            actor="worker",
            is_admin=True,
            workspace_id=resolved_settings.workspace_id.strip() or "default",
            user_id="worker",
            role="admin",
        )
    )
    return result is not None


def run_single() -> bool:
    settings = load_settings()
    container = build_container(settings)
    try:
        return run_once(container, settings)
    finally:
        container.close()


if __name__ == "__main__":
    raise SystemExit(0 if run_single() else 1)
