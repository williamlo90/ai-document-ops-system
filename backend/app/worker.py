from __future__ import annotations

from app.api.dependencies import build_container
from app.core.security import SecurityContext
from app.core.settings import load_settings


def run_once() -> bool:
    settings = load_settings()
    container = build_container(settings)
    result = container.worker_service.run_once(
        context=SecurityContext(
            actor="worker",
            is_admin=True,
            workspace_id=settings.workspace_id.strip() or "default",
            user_id="worker",
            role="admin",
        )
    )
    return result is not None


if __name__ == "__main__":
    raise SystemExit(0 if run_once() else 1)
