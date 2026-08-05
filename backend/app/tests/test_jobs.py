from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.documents.jobs import JobStatus, ProcessingJob, StaleLeaseError


class JobTests(unittest.TestCase):
    def test_claim_heartbeat_complete_and_stale_fence(self) -> None:
        job = ProcessingJob(uuid4())
        token = job.claim(60)
        job.heartbeat(token, 60)
        with self.assertRaises(StaleLeaseError):
            job.complete("stale")
        job.complete(token)
        self.assertEqual(job.status, JobStatus.COMPLETED)

    def test_expired_lease_is_reclaimed(self) -> None:
        now = datetime.now(UTC)
        job = ProcessingJob(uuid4())
        job.next_attempt_at = now
        job.claim(1, now)
        self.assertTrue(job.reclaim_if_expired(now + timedelta(seconds=2)))
        self.assertEqual(job.status, JobStatus.RETRY)


if __name__ == "__main__":
    unittest.main()
