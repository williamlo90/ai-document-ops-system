from __future__ import annotations

from dataclasses import dataclass

from app.core.settings import Settings


@dataclass(frozen=True, slots=True)
class AppContainer:
    settings: Settings

    def readiness(self) -> dict[str, bool]:
        return {
            "database": self.settings.database_ready,
            "storage": self.settings.storage_ready,
        }


def build_container(settings: Settings) -> AppContainer:
    return AppContainer(settings=settings)
