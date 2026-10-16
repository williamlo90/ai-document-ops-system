"""Run the same AP posting/recovery contract against PostgreSQL version storage."""

from __future__ import annotations

import os
import unittest
from datetime import UTC, datetime

from app.postgres.store import PostgresStore
from app.procurement.matching import MatchService
from app.procurement.models import Mapping, MatchPolicy, Policy
from app.procurement.repository import VersionRepository
from app.procurement.service import EvidenceService
from app.tests import test_ap_posting as fixtures


@unittest.skipUnless(
    os.getenv("POSTGRES_TEST_DATABASE_URL"), "POSTGRES_TEST_DATABASE_URL is required"
)
class PostgresPostingTests(fixtures.PostingTests):
    def setUp(self):
        super().setUp()
        connection = PostgresStore(os.environ["POSTGRES_TEST_DATABASE_URL"], pool_size=2)
        self.addCleanup(connection.close)
        workspace = self.admin.workspace_id
        self.addCleanup(
            connection.execute, "DELETE FROM ap_versions WHERE workspace_id = ?", (workspace,)
        )
        self.addCleanup(
            connection.execute, "DELETE FROM ap_scope_locks WHERE workspace_id = ?", (workspace,)
        )
        self.repo = VersionRepository(connection)
        self.evidence = EvidenceService(self.repo, self.docs, self.extractions)
        self.match = MatchService(self.evidence)
        self.evidence.configure(
            "mapping",
            Mapping(
                company="AC",
                supplier_aliases={"Vendor": "SUP"},
                item_mappings={"Widget": "W"},
                reason="Verified PostgreSQL test master",
            ),
            self.admin,
        )
        self.evidence.configure(
            "policy",
            Policy(company="AC", currency="USD", reason="Verified source policy"),
            self.admin,
        )
        self.match.configure_policy(
            MatchPolicy(
                company="AC",
                effective_from=datetime(2026, 1, 1, tzinfo=UTC),
                reason="Exact PostgreSQL posting policy",
            ),
            self.admin,
        )
        self.source("po", "PO1", "p1", "100", "5000")
        self.source("receipt", "R1", "r1", "70", "3500")
