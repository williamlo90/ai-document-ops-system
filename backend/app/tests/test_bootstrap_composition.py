from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.dependencies import AppContainer, build_container
from app.core.settings import Settings
from app.documents.jobs import ProcessingJob
from app.documents.processing_policy import ProcessingRetryPolicy
from app.main import create_app
from app.providers.contracts import ProviderError


class BootstrapCompositionTests(unittest.TestCase):
    def test_container_keeps_flat_api_with_explicit_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = _memory_settings(Path(temp_dir))
            container = build_container(settings)

            self.assertIsInstance(container, AppContainer)
            self.assertIs(container.processing_service.documents, container.documents)
            self.assertIs(container.processing_service.result_recorder.jobs, container.jobs)
            self.assertIs(
                container.processing_service.result_recorder.retry_policy,
                container.processing_service.retry_policy,
            )
            self.assertFalse(hasattr(container, "_app_sessions"))

    def test_fastapi_uses_the_container_session_store(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = create_app(_memory_settings(Path(temp_dir)))

            self.assertIs(app.state.sessions, app.state.container.sessions)

    def test_lifespan_is_the_single_container_close_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = create_app(_memory_settings(Path(temp_dir)))
            with patch.object(
                app.state.container,
                "close",
                wraps=app.state.container.close,
            ) as close:
                with TestClient(app):
                    pass

            close.assert_called_once_with()


class ProcessingRetryPolicyTests(unittest.TestCase):
    def test_retryable_provider_errors_respect_attempt_limit(self) -> None:
        policy = ProcessingRetryPolicy(max_attempts=2)
        error = ProviderError("temporary outage", "ocr", retryable=True)
        job = ProcessingJob(document_id=uuid4())
        job.start()

        self.assertTrue(policy.should_retry(error, job))
        self.assertEqual(policy.error_code(error), "provider_error:ocr")

        job.retry("provider_error:ocr", next_attempt_at=policy.next_attempt_at(job))
        job.start()

        self.assertFalse(policy.should_retry(error, job))

    def test_non_provider_errors_are_terminal_and_sanitized(self) -> None:
        policy = ProcessingRetryPolicy()
        error = RuntimeError("sensitive internal detail")

        self.assertFalse(policy.should_retry(error, ProcessingJob(document_id=uuid4())))
        self.assertEqual(policy.error_code(error), "RuntimeError")


def _memory_settings(root: Path) -> Settings:
    return Settings(
        app_env="local",
        admin_token="test-token",
        upload_root=root / "uploads",
        max_upload_bytes=1_000_000,
        sqlite_path=root / "app.db",
        storage_backend="memory",
        parser_provider="mock",
        extractor_provider="mock",
    )
