from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

from app.api.dependencies import build_container
from app.core.security import SecurityContext
from app.core.settings import Settings
from app.documents.jobs import ProcessingJob, ProcessingJobStatus
from app.documents.models import DocumentRecord
from app.documents.processing_queue import (
    InMemoryProcessingQueue,
    InvalidQueueMessage,
    ProcessingMessage,
)
from app.documents.repositories import InMemoryJobRepository
from app.documents.worker import DocumentProcessingWorker, QueueProcessingWorker
from app.providers.contracts import ProviderError


class ProcessingMessageTests(unittest.TestCase):
    def test_versioned_envelope_round_trips_without_invoice_content(self) -> None:
        message = ProcessingMessage(
            job_id=uuid4(),
            document_id=uuid4(),
            workspace_id="finance",
            trace_id="trace-123",
        )

        encoded = message.to_json()

        self.assertEqual(ProcessingMessage.from_json(encoded), message)
        self.assertNotIn("invoice", encoded.casefold())
        self.assertNotIn("filename", encoded.casefold())

    def test_unknown_or_extra_fields_are_rejected(self) -> None:
        with self.assertRaises(InvalidQueueMessage):
            ProcessingMessage.from_json('{"schema_version":2}')
        with self.assertRaises(InvalidQueueMessage):
            ProcessingMessage.from_json(
                '{"schema_version":1,"job_id":"00000000-0000-0000-0000-000000000000",'
                '"document_id":"00000000-0000-0000-0000-000000000000",'
                '"workspace_id":"default","trace_id":"trace","invoice_total":"100"}'
            )


class QueueProcessingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.container = build_container(
            Settings(
                app_env="test",
                admin_token="test-token",
                upload_root=Path(self.temp_dir.name) / "uploads",
                max_upload_bytes=10_000,
                processing_queue_backend="memory",
            )
        )
        self.context = SecurityContext(
            actor="Queue Tester",
            is_admin=True,
            workspace_id="finance",
            user_id="queue-tester",
            role="admin",
            trace_id="trace-queue-test",
        )
        queue = self.container.processing_queue
        self.assertIsInstance(queue, InMemoryProcessingQueue)
        self.queue = queue

    def tearDown(self) -> None:
        self.container.close()
        self.temp_dir.cleanup()

    def _upload(self):
        return self.container.upload_service.upload_pdf(
            "invoice.pdf",
            "application/pdf",
            [b"%PDF-1.4 queue test"],
            self.context,
        )

    def test_upload_message_processes_once_under_duplicate_delivery(self) -> None:
        upload = self._upload()
        body = self.queue.pending[0].body

        self.assertTrue(self.container.queue_worker_service.run_once(max_wait_seconds=0.1))
        self.assertEqual(
            self.container.jobs.get(upload.job.id).status,
            ProcessingJobStatus.SUCCEEDED,
        )

        self.queue.inject_raw(body)
        self.queue.inject_raw(body)
        self.container.queue_worker_service.run_once(max_wait_seconds=0.1)
        self.container.queue_worker_service.run_once(max_wait_seconds=0.1)

        persisted = self.container.jobs.get(upload.job.id)
        self.assertEqual(persisted.attempt_count, 1)
        self.assertEqual(self.queue.dead_letters, [])

    def test_poison_and_mismatched_messages_are_dead_lettered(self) -> None:
        upload = self._upload()
        self.queue.pending.clear()
        self.queue.inject_raw("not-json")
        self.queue.publish(
            ProcessingMessage(
                job_id=upload.job.id,
                document_id=uuid4(),
                workspace_id="finance",
                trace_id="trace-poison",
            )
        )

        self.container.queue_worker_service.run_once(max_wait_seconds=0.1)
        self.container.queue_worker_service.run_once(max_wait_seconds=0.1)

        self.assertEqual(len(self.queue.dead_letters), 2)
        self.assertEqual(
            self.container.jobs.get(upload.job.id).status,
            ProcessingJobStatus.QUEUED,
        )

    def test_transient_provider_failure_uses_database_retry_fallback(self) -> None:
        upload = self._upload()
        original_extractor = self.container.processing_service.extractor
        failing_extractor = Mock()
        failing_extractor.extract_invoice.side_effect = ProviderError(
            "temporary provider outage",
            "test-provider",
            retryable=True,
        )
        self.container.processing_service.extractor = failing_extractor

        self.container.queue_worker_service.run_once(max_wait_seconds=0.1)

        retrying = self.container.jobs.get(upload.job.id)
        self.assertEqual(retrying.status, ProcessingJobStatus.RETRYING)
        self.assertEqual(len(self.queue.pending), 0)
        retrying.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        self.container.jobs.save(retrying)
        self.container.processing_service.extractor = original_extractor

        result = self.container.worker_service.run_once(self.context)

        self.assertIsNotNone(result)
        self.assertEqual(
            self.container.jobs.get(upload.job.id).status,
            ProcessingJobStatus.SUCCEEDED,
        )

    def test_reprocess_records_actor_reason_and_publishes_new_job(self) -> None:
        upload = self._upload()
        self.container.queue_worker_service.run_once(max_wait_seconds=0.1)

        self.container.processing_service.reprocess_document(
            upload.document.id,
            self.context,
            reason="corrected vendor mapping",
        )

        events = self.container.audits.list_for_document(upload.document.id)
        self.assertEqual(events[-1].actor, "Queue Tester")
        self.assertEqual(events[-1].payload_summary, "corrected vendor mapping")
        self.assertEqual(len(self.queue.pending), 1)


class QueueRecoveryTests(unittest.TestCase):
    def test_interrupted_worker_recovers_expired_lease_without_duplicate_effect(self) -> None:
        jobs = InMemoryJobRepository()
        document_id = uuid4()
        job = jobs.add(ProcessingJob(document_id=document_id))
        processing = Mock()
        processing.process_job.side_effect = RuntimeError("worker interrupted")
        database_worker = DocumentProcessingWorker(jobs, processing, lease_seconds=1)
        queue = InMemoryProcessingQueue()
        queue_worker = QueueProcessingWorker(queue, jobs, database_worker)
        queue.publish(
            ProcessingMessage(
                job_id=job.id,
                document_id=document_id,
                workspace_id="default",
                trace_id="trace-recovery",
            )
        )

        queue_worker.run_once(max_wait_seconds=0.1)
        interrupted = jobs.get(job.id)
        token = interrupted.lease_token
        self.assertIsNotNone(token)
        interrupted.updated_at = datetime.now(UTC) - timedelta(seconds=2)
        jobs.save(interrupted, expected_lease_token=token)

        def succeed(job_id, *, context, lease_token):
            del context
            current = jobs.get(job_id)
            current.succeed()
            jobs.save(current, expected_lease_token=lease_token)
            return DocumentRecord(
                original_filename="invoice.pdf",
                storage_key="invoice.pdf",
                content_type="application/pdf",
                id=document_id,
            )

        processing.process_job.side_effect = succeed
        queue_worker.run_once(max_wait_seconds=0.1)

        recovered = jobs.get(job.id)
        self.assertEqual(recovered.status, ProcessingJobStatus.SUCCEEDED)
        self.assertEqual(recovered.attempt_count, 2)
        self.assertEqual(len(queue.pending), 0)


if __name__ == "__main__":
    unittest.main()
