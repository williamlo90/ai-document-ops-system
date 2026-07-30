from __future__ import annotations

import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from app.core.security import SecurityContext
from app.core.settings import Settings
from app.documents.jobs import ProcessingJob
from app.documents.models import DocumentRecord
from app.documents.repositories import InMemoryJobRepository
from app.documents.worker import DocumentProcessingWorker
from app.worker import run_once, run_single
from app.worker_loop import run_forever


class WorkerEntrypointTests(unittest.TestCase):
    def test_worker_renews_lease_during_long_processing(self) -> None:
        jobs = InMemoryJobRepository()
        job = jobs.add(ProcessingJob(document_id=uuid4()))
        processing_service = Mock()
        claimed_at = []

        def process(*_args, **_kwargs) -> DocumentRecord:
            claimed_at.append(jobs.get(job.id).updated_at)
            time.sleep(1.15)
            return DocumentRecord(
                original_filename="invoice.pdf",
                storage_key="invoice.pdf",
                content_type="application/pdf",
                id=job.document_id,
            )

        processing_service.process_job.side_effect = process
        worker = DocumentProcessingWorker(
            jobs,
            processing_service,
            lease_seconds=1,
        )

        worker.run_once(SecurityContext(actor="worker", is_admin=True))

        self.assertGreater(jobs.get(job.id).updated_at, claimed_at[0])

    def test_terminal_job_does_not_turn_a_successful_run_into_a_lease_failure(self) -> None:
        jobs = InMemoryJobRepository()
        job = jobs.add(ProcessingJob(document_id=uuid4()))
        processing_service = Mock()

        def process(*_args, **_kwargs) -> DocumentRecord:
            running = jobs.get(job.id)
            lease_token = running.lease_token
            self.assertIsNotNone(lease_token)
            running.succeed()
            jobs.save(running, expected_lease_token=lease_token)
            time.sleep(1.15)
            return DocumentRecord(
                original_filename="invoice.pdf",
                storage_key="invoice.pdf",
                content_type="application/pdf",
                id=job.document_id,
            )

        processing_service.process_job.side_effect = process
        worker = DocumentProcessingWorker(jobs, processing_service, lease_seconds=1)

        result = worker.run_once(SecurityContext(actor="worker", is_admin=True))

        self.assertEqual(result.id, job.document_id)

    def test_worker_uses_the_configured_workspace(self) -> None:
        settings = Settings(
            app_env="test",
            admin_token="test-token",
            upload_root=Path("uploads"),
            max_upload_bytes=1_000,
            workspace_id="finance-ops",
        )
        worker_service = Mock()
        worker_service.run_once.return_value = object()
        container = SimpleNamespace(worker_service=worker_service, settings=settings)

        processed = run_once(container)

        self.assertTrue(processed)
        context = worker_service.run_once.call_args.kwargs["context"]
        self.assertEqual(context.workspace_id, "finance-ops")
        self.assertEqual(context.role, "admin")
        self.assertTrue(context.is_admin)

    def test_single_run_closes_its_container(self) -> None:
        settings = Settings(
            app_env="test",
            admin_token="test-token",
            upload_root=Path("uploads"),
            max_upload_bytes=1_000,
        )
        worker_service = Mock()
        worker_service.run_once.return_value = object()
        container = SimpleNamespace(worker_service=worker_service, close=Mock())

        with (
            patch("app.worker.load_settings", return_value=settings),
            patch("app.worker.build_container", return_value=container),
        ):
            processed = run_single()

        self.assertTrue(processed)
        container.close.assert_called_once_with()

    def test_worker_loop_builds_one_container_and_closes_it(self) -> None:
        settings = Settings(
            app_env="test",
            admin_token="test-token",
            upload_root=Path("uploads"),
            max_upload_bytes=1_000,
        )
        container = SimpleNamespace(close=Mock())

        class OneIterationEvent:
            def __init__(self) -> None:
                self.check_count = 0

            def is_set(self) -> bool:
                self.check_count += 1
                return self.check_count > 1

            def set(self) -> None:
                self.check_count = 2

            def wait(self, _timeout: float) -> bool:
                return False

        with (
            patch("app.worker_loop.threading.Event", return_value=OneIterationEvent()),
            patch("app.worker_loop.signal.signal"),
            patch("app.worker_loop.load_settings", return_value=settings),
            patch("app.worker_loop.build_container", return_value=container) as build,
            patch("app.worker_loop.run_once", return_value=False) as process,
        ):
            run_forever(poll_seconds=0.1)

        build.assert_called_once_with(settings)
        process.assert_called_once_with(container, settings)
        container.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
