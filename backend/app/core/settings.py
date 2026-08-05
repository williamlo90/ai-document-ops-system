from __future__ import annotations

from dataclasses import dataclass
from os import environ
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

    @classmethod
    def from_environment(cls, values: Mapping[str, str] | None = None) -> Settings:
        source = environ if values is None else values
        environment = source.get("APP_ENV", "local").strip() or "local"
        return cls(
            environment=environment,
            database_ready=_read_bool(source, "DATABASE_READY", True),
            storage_ready=_read_bool(source, "STORAGE_READY", True),
        )


def load_settings() -> Settings:
    return Settings.from_environment()
