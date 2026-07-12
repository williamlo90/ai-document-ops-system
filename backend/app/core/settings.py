from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    app_env: str
    admin_token: str | None
    upload_root: Path
    max_upload_bytes: int
    document_storage_backend: str = "local"
    storage_backend: str = "memory"
    sqlite_path: Path = Path("backend/data/doc_intel.sqlite3")
    database_url: str | None = None
    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None
    s3_region: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    parser_provider: str = "mock"
    extractor_provider: str = "mock"
    mistral_api_key: str | None = None
    mistral_ocr_endpoint: str = "https://api.mistral.ai/v1/ocr"
    mistral_ocr_model: str = "mistral-ocr-latest"
    extractor_api_key: str | None = None
    extractor_endpoint: str = ""
    extractor_model: str = ""
    benchmark_real_provider_max_documents: int = 3
    max_processing_attempts: int = 3
    provider_timeout_seconds: int = 60
    email_provider: str = "mock"
    email_sandbox_mode: bool = True
    resend_api_key: str | None = None
    email_from: str = "onboarding@resend.dev"
    email_test_recipient: str | None = None
    accounting_provider: str = "csv_download"
    accounting_sandbox_mode: bool = True
    session_ttl_seconds: int = 28_800
    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60
    malware_scanning_enabled: bool = True


def is_production_like(settings: Settings) -> bool:
    return settings.app_env.strip().lower() in {"prod", "production"}


def is_public_demo(settings: Settings) -> bool:
    return settings.app_env.strip().lower() in {"public", "public-demo", "public_demo", "portfolio"}


def load_settings() -> Settings:
    config = _load_env_file()
    return Settings(
        app_env=_setting(config, "APP_ENV", "local"),
        admin_token=_setting(config, "APP_ADMIN_TOKEN"),
        upload_root=Path(_setting(config, "UPLOAD_ROOT", "backend/data/uploads")),
        max_upload_bytes=int(_setting(config, "MAX_UPLOAD_BYTES", "15728640")),
        document_storage_backend=_setting(config, "DOCUMENT_STORAGE_BACKEND", "local"),
        storage_backend=_setting(config, "STORAGE_BACKEND", "memory"),
        sqlite_path=Path(_setting(config, "SQLITE_PATH", "backend/data/doc_intel.sqlite3")),
        database_url=_setting(config, "DATABASE_URL"),
        s3_endpoint_url=_setting(config, "S3_ENDPOINT_URL"),
        s3_bucket=_setting(config, "S3_BUCKET"),
        s3_region=_setting(config, "S3_REGION"),
        s3_access_key_id=_setting(config, "S3_ACCESS_KEY_ID"),
        s3_secret_access_key=_setting(config, "S3_SECRET_ACCESS_KEY"),
        parser_provider=_setting(config, "PARSER_PROVIDER", "mock"),
        extractor_provider=_setting(config, "EXTRACTOR_PROVIDER", "mock"),
        mistral_api_key=_setting(config, "MISTRAL_API_KEY"),
        mistral_ocr_endpoint=_setting(
            config,
            "MISTRAL_OCR_ENDPOINT",
            "https://api.mistral.ai/v1/ocr",
        ),
        mistral_ocr_model=_setting(config, "MISTRAL_OCR_MODEL", "mistral-ocr-latest"),
        extractor_api_key=_setting(config, "EXTRACTOR_API_KEY"),
        extractor_endpoint=_setting(config, "EXTRACTOR_ENDPOINT", ""),
        extractor_model=_setting(config, "EXTRACTOR_MODEL", ""),
        benchmark_real_provider_max_documents=int(
            _setting(config, "BENCHMARK_REAL_PROVIDER_MAX_DOCUMENTS", "3")
        ),
        max_processing_attempts=int(_setting(config, "MAX_PROCESSING_ATTEMPTS", "3")),
        provider_timeout_seconds=int(_setting(config, "PROVIDER_TIMEOUT_SECONDS", "60")),
        email_provider=_setting(config, "EMAIL_PROVIDER", "mock"),
        email_sandbox_mode=_boolean(_setting(config, "EMAIL_SANDBOX_MODE", "true")),
        resend_api_key=_setting(config, "RESEND_API_KEY"),
        email_from=_setting(config, "EMAIL_FROM", "onboarding@resend.dev"),
        email_test_recipient=_setting(config, "EMAIL_TEST_RECIPIENT"),
        accounting_provider=_setting(config, "ACCOUNTING_PROVIDER", "csv_download"),
        accounting_sandbox_mode=_boolean(_setting(config, "ACCOUNTING_SANDBOX_MODE", "true")),
        session_ttl_seconds=int(_setting(config, "SESSION_TTL_SECONDS", "28800")),
        rate_limit_requests=int(_setting(config, "RATE_LIMIT_REQUESTS", "120")),
        rate_limit_window_seconds=int(_setting(config, "RATE_LIMIT_WINDOW_SECONDS", "60")),
        malware_scanning_enabled=_boolean(_setting(config, "MALWARE_SCANNING_ENABLED", "true")),
    )


def _setting(config: dict[str, str], key: str, default: str | None = None) -> str | None:
    return os.getenv(key) or config.get(key) or default


def _load_env_file() -> dict[str, str]:
    path = _env_file_path()
    if path is None or not path.exists():
        return {}
    config: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        config[key.strip()] = _unquote(value.strip())
    return config


def _env_file_path() -> Path | None:
    explicit = os.getenv("ENV_FILE")
    if explicit:
        return Path(explicit)
    candidates = (Path.cwd() / ".env", Path.cwd().parent / ".env")
    return next((path for path in candidates if path.exists()), None)


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _boolean(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}
