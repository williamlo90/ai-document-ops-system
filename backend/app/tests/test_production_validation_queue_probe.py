from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from scripts.production_validation.queue_probe import (
    RUN_ID_PROPERTY,
    message_belongs_to_run,
    poison_envelope,
    processing_envelope,
    require_owned_inventory,
)


class ProductionValidationQueueProbeTests(unittest.TestCase):
    def test_processing_envelope_is_schema_valid_and_run_scoped(self) -> None:
        job_id = uuid4()
        document_id = uuid4()
        envelope = processing_envelope(
            run_id="pg01-20261002t120000z-abcd1234",
            job_id=job_id,
            document_id=document_id,
            workspace_id="azure-validation",
            trace_id="a" * 32,
        )

        self.assertIn(str(job_id), envelope.body)
        self.assertIn(str(document_id), envelope.body)
        self.assertEqual(envelope.correlation_id, "a" * 32)
        self.assertNotEqual(envelope.message_id, str(job_id))

    def test_poison_envelope_is_intentionally_invalid_and_run_scoped(self) -> None:
        envelope = poison_envelope(run_id="pg01-20261002t120000z-abcd1234")

        self.assertIn('"schema_version":999', envelope.body)
        self.assertEqual(envelope.run_id, "pg01-20261002t120000z-abcd1234")

    def test_dlq_ownership_requires_exact_application_property(self) -> None:
        owned = SimpleNamespace(
            application_properties={RUN_ID_PROPERTY.encode(): b"pg01-20261002t120000z-abcd1234"}
        )
        foreign = SimpleNamespace(
            application_properties={RUN_ID_PROPERTY: "pg01-another-validation-run"}
        )

        self.assertTrue(message_belongs_to_run(owned, "pg01-20261002t120000z-abcd1234"))
        self.assertFalse(message_belongs_to_run(foreign, "pg01-20261002t120000z-abcd1234"))
        with self.assertRaisesRegex(RuntimeError, "refusing replay"):
            require_owned_inventory([owned, foreign], "pg01-20261002t120000z-abcd1234")

    @patch("scripts.production_validation.queue_probe.ServiceBusClient.from_connection_string")
    def test_local_emulator_connection_does_not_create_azure_credential(
        self, from_connection_string: MagicMock
    ) -> None:
        from scripts.production_validation.queue_probe import QueueProbe

        probe = QueueProbe(
            namespace="",
            queue_name="document-processing",
            connection_string="Endpoint=sb://localhost;UseDevelopmentEmulator=true;",
        )
        probe.close()

        from_connection_string.assert_called_once()
        self.assertIsNone(probe.credential)


if __name__ == "__main__":
    unittest.main()
