from __future__ import annotations

from dataclasses import dataclass

from app.core.settings import Settings
from app.core.security import SessionStore
from app.bootstrap.persistence import PersistenceModule, build_persistence_module
from app.bootstrap.documents import DocumentModule, build_document_module


@dataclass(frozen=True, slots=True)
class AppContainer:
    settings: Settings
    sessions: SessionStore
    persistence: PersistenceModule
    document_module: DocumentModule

    def readiness(self) -> dict[str, bool]:
        return {
            "database": self.settings.database_ready,
            "storage": self.settings.storage_ready,
        }

    def close(self) -> None:
        self.persistence.close()


def build_container(settings: Settings) -> AppContainer:
    persistence = build_persistence_module(settings)
    return AppContainer(
        settings=settings,
        sessions=SessionStore(settings.session_ttl_seconds),
        persistence=persistence,
        document_module=build_document_module(settings, persistence),
    )
