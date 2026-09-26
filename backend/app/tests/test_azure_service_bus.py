from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

from azure.servicebus import ServiceBusClient, ServiceBusMessage, ServiceBusSubQueue

from app.api.dependencies import build_container
from app.core.security import SecurityContext
from app.core.settings import Settings
from app.documents.jobs import ProcessingJobStatus
from app.documents.processing_queue import ProcessingMessage, QueueDisposition
from app.providers.azure_service_bus import AzureServiceBusProcessingQueue


class AzureServiceBusAdapterTests(unittest.TestCase):
    @patch("app.providers.azure_service_bus.ServiceBusClient.from_connection_string")
    def test_publish_uses_identifier_only_envelope(self, build_client) -> None:
        client = MagicMock()
        sender = MagicMock()
        client.get_queue_sender.return_value.__enter__.return_value = sender
        build_client.return_value = client
        queue = AzureServiceBusProcessingQueue(
            queue_name="document-processing",
            connection_string="Endpoint=sb://local;SharedAccessKeyName=test;SharedAccessKey=test",
        )
        message = ProcessingMessage(
            job_id=uuid4(),
            document_id=uuid4(),
            workspace_id="finance",
            trace_id="trace-adapter",
        )

        queue.publish(message)

        outbound = sender.send_messages.call_args.args[0]
        self.assertEqual(str(outbound), message.to_json())
        self.assertEqual(outbound.message_id, str(message.job_id))
        self.assertEqual(outbound.correlation_id, "trace-adapter")

    @patch("app.providers.azure_service_bus.AutoLockRenewer")
    @patch("app.providers.azure_service_bus.ServiceBusClient.from_connection_string")
    def test_receive_settles_complete_before_receiver_closes(self, build_client, renewer) -> None:
        client = MagicMock()
        receiver = MagicMock()
        build_client.return_value = client
        client.get_queue_receiver.return_value.__enter__.return_value = receiver
        message = ProcessingMessage(
            job_id=uuid4(),
            document_id=uuid4(),
            workspace_id="finance",
            trace_id="trace-receive",
        )
        received = MagicMock()
        received.__str__.return_value = message.to_json()
        received.delivery_count = 1
        receiver.receive_messages.return_value = [received]
        handler = MagicMock(return_value=QueueDisposition.COMPLETE)

        queue = AzureServiceBusProcessingQueue(
            queue_name="document-processing",
            connection_string="Endpoint=sb://local;SharedAccessKeyName=test;SharedAccessKey=test",
        )
        handled = queue.receive_one(handler, max_wait_seconds=1)

        self.assertTrue(handled)
        handler.assert_called_once_with(message, 1)
        receiver.complete_message.assert_called_once_with(received)
        renewer.return_value.close.assert_called_once_with()

    @patch("app.providers.azure_service_bus.AutoLockRenewer")
    @patch("app.providers.azure_service_bus.ServiceBusClient.from_connection_string")
    def test_invalid_envelope_is_dead_lettered(self, build_client, renewer) -> None:
        client = MagicMock()
        receiver = MagicMock()
        build_client.return_value = client
        client.get_queue_receiver.return_value.__enter__.return_value = receiver
        received = MagicMock()
        received.__str__.return_value = "not-json"
        receiver.receive_messages.return_value = [received]
        queue = AzureServiceBusProcessingQueue(
            queue_name="document-processing",
            connection_string="Endpoint=sb://local;SharedAccessKeyName=test;SharedAccessKey=test",
        )

        handled = queue.receive_one(MagicMock(), max_wait_seconds=1)

        self.assertTrue(handled)
        receiver.dead_letter_message.assert_called_once()
        renewer.return_value.close.assert_called_once_with()


@unittest.skipUnless(
    os.getenv("SERVICE_BUS_TEST_CONNECTION_STRING"),
    "SERVICE_BUS_TEST_CONNECTION_STRING is required for Service Bus integration tests",
)
class AzureServiceBusIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection_string = os.environ["SERVICE_BUS_TEST_CONNECTION_STRING"]
        self.queue_name = os.getenv("SERVICE_BUS_TEST_QUEUE", "document-processing")
        self.queue = AzureServiceBusProcessingQueue(
            queue_name=self.queue_name,
            connection_string=self.connection_string,
            operation_timeout_seconds=10,
            max_lock_renewal_seconds=30,
        )

    def tearDown(self) -> None:
        self.queue.close()

    def test_application_upload_is_delivered_to_queue_worker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            container = build_container(
                Settings(
                    app_env="test",
                    admin_token="test-token",
                    upload_root=Path(temp_dir) / "uploads",
                    max_upload_bytes=10_000,
                    processing_queue_backend="azure-service-bus",
                    azure_service_bus_connection_string=self.connection_string,
                    azure_service_bus_queue_name=self.queue_name,
                    azure_service_bus_timeout_seconds=10,
                    azure_service_bus_max_lock_renewal_seconds=30,
                )
            )
            context = SecurityContext(
                actor="Service Bus Integration Tester",
                is_admin=True,
                workspace_id="integration",
                user_id="service-bus-integration",
                role="admin",
                trace_id=uuid4().hex,
            )
            try:
                upload = container.upload_service.upload_pdf(
                    "invoice.pdf",
                    "application/pdf",
                    [b"%PDF-1.4 service bus integration"],
                    context,
                )

                self.assertTrue(container.queue_worker_service.run_once(max_wait_seconds=5))
                persisted = container.jobs.get(upload.job.id)
                self.assertEqual(persisted.status, ProcessingJobStatus.SUCCEEDED)
                self.assertEqual(persisted.attempt_count, 1)
            finally:
                container.close()

    def test_publish_receive_duplicate_and_poison_dead_letter(self) -> None:
        message = ProcessingMessage(
            job_id=uuid4(),
            document_id=uuid4(),
            workspace_id="integration",
            trace_id=uuid4().hex,
        )
        received: list[ProcessingMessage] = []
        self.queue.publish(message)
        self.queue.publish(message)

        for _ in range(2):
            handled = self.queue.receive_one(
                lambda item, _count: received.append(item) or QueueDisposition.COMPLETE,
                max_wait_seconds=5,
            )
            self.assertTrue(handled)
        self.assertEqual(received, [message, message])

        with ServiceBusClient.from_connection_string(self.connection_string) as client:
            with client.get_queue_sender(self.queue_name) as sender:
                sender.send_messages(ServiceBusMessage("not-json"))
            self.assertTrue(
                self.queue.receive_one(
                    lambda _message, _count: QueueDisposition.COMPLETE,
                    max_wait_seconds=5,
                )
            )
            with client.get_queue_receiver(
                self.queue_name,
                sub_queue=ServiceBusSubQueue.DEAD_LETTER,
                max_wait_time=5,
            ) as receiver:
                dead_letters = receiver.receive_messages(max_message_count=1, max_wait_time=5)
                self.assertEqual(len(dead_letters), 1)
                receiver.complete_message(dead_letters[0])


if __name__ == "__main__":
    unittest.main()
