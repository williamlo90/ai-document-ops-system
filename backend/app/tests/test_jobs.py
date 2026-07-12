from __future__ import annotations

import unittest
from uuid import uuid4

from app.documents.jobs import ProcessingJob, ProcessingJobStatus


class ProcessingJobTests(unittest.TestCase):
    def test_jobs_get_unique_ids_and_timestamps(self) -> None:
        first = ProcessingJob(document_id=uuid4())
        second = ProcessingJob(document_id=uuid4())

        self.assertNotEqual(first.id, second.id)
        self.assertNotEqual(first.created_at, second.created_at)

    def test_start_increments_attempt_and_sets_started_at(self) -> None:
        job = ProcessingJob(document_id=uuid4())

        job.start()

        self.assertEqual(job.status, ProcessingJobStatus.RUNNING)
        self.assertEqual(job.attempt_count, 1)
        self.assertIsNotNone(job.started_at)

    def test_succeed_sets_finished_at(self) -> None:
        job = ProcessingJob(document_id=uuid4())
        job.start()

        job.succeed()

        self.assertEqual(job.status, ProcessingJobStatus.SUCCEEDED)
        self.assertIsNotNone(job.finished_at)

    def test_fail_persists_safe_error_message(self) -> None:
        job = ProcessingJob(document_id=uuid4())

        job.fail("parser_error")

        self.assertEqual(job.status, ProcessingJobStatus.FAILED)
        self.assertEqual(job.error_message, "parser_error")

    def test_retry_keeps_job_processable(self) -> None:
        job = ProcessingJob(document_id=uuid4())

        job.retry("provider_timeout")

        self.assertEqual(job.status, ProcessingJobStatus.RETRYING)
        self.assertEqual(job.error_message, "provider_timeout")
        self.assertIsNone(job.finished_at)

    def test_dead_letter_finishes_job(self) -> None:
        job = ProcessingJob(document_id=uuid4())

        job.dead_letter("max_attempts_exceeded")

        self.assertEqual(job.status, ProcessingJobStatus.DEAD_LETTER)
        self.assertEqual(job.error_message, "max_attempts_exceeded")
        self.assertIsNotNone(job.finished_at)


if __name__ == "__main__":
    unittest.main()
