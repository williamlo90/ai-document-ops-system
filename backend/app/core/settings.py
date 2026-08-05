from __future__ import annotations

from dataclasses import dataclass
from os import environ
from pathlib import Path
from typing import Mapping


_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


def _read_bool(values: Mapping[str, str], name: str, default: bool) -> bool:
    raw = values.get(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise ValueError(f"{name} must be a boolean value")


@dataclass(frozen=True, slots=True)
class Settings:
    """Settings needed by the walking skeleton.

    Configuration is read from the process environment only. M01 intentionally does not load a
    repository `.env` file or require a personal credential.
    """

    environment: str = "local"
    database_ready: bool = True
    storage_ready: bool = True
    admin_token: str = "local-admin"
    uploader_token: str = "local-uploader"
    reviewer_token: str = "local-reviewer"
    workspace_id: str = "default"
    session_ttl_seconds: int = 28_800
    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60
    persistence_backend: str = "memory"
    sqlite_path: Path = Path("runtime/invoice-review.sqlite3")
    upload_root: Path = Path("runtime/private-uploads")
    max_upload_bytes: int = 10_000_000
    scanner_profile: str = "signature"

    @classmethod
    def from_environment(cls, values: Mapping[str, str] | None = None) -> Settings:
        source = environ if values is None else values
        environment = source.get("APP_ENV", "local").strip() or "local"
        return cls(
            environment=environment,
            database_ready=_read_bool(source, "DATABASE_READY", True),
            storage_ready=_read_bool(source, "STORAGE_READY", True),
            admin_token=source.get("APP_ADMIN_TOKEN", "local-admin"),
            uploader_token=source.get("APP_UPLOADER_TOKEN", "local-uploader"),
            reviewer_token=source.get("APP_REVIEWER_TOKEN", "local-reviewer"),
            workspace_id=source.get("APP_WORKSPACE_ID", "default").strip() or "default",
            session_ttl_seconds=int(source.get("SESSION_TTL_SECONDS", "28800")),
            rate_limit_requests=int(source.get("RATE_LIMIT_REQUESTS", "120")),
            rate_limit_window_seconds=int(source.get("RATE_LIMIT_WINDOW_SECONDS", "60")),
            persistence_backend=source.get("PERSISTENCE_BACKEND", "memory").strip().lower(),
            sqlite_path=Path(source.get("SQLITE_PATH", "runtime/invoice-review.sqlite3")),
            upload_root=Path(source.get("UPLOAD_ROOT", "runtime/private-uploads")),
            max_upload_bytes=int(source.get("MAX_UPLOAD_BYTES", "10000000")),
            scanner_profile=source.get("SCANNER_PROFILE", "signature").strip().lower(),
        )


def load_settings() -> Settings:
    return Settings.from_environment()


def is_hosted(settings: Settings) -> bool:
    return settings.environment.strip().lower() in {"prod", "production", "public-demo"}
