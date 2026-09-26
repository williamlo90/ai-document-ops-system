from __future__ import annotations

import logging

from azure.identity import DefaultAzureCredential
from azure.servicebus import AutoLockRenewer, ServiceBusClient, ServiceBusMessage
from azure.servicebus.exceptions import ServiceBusError

from app.documents.processing_queue import (
    InvalidQueueMessage,
    MessageHandler,
    ProcessingMessage,
    QueueDisposition,
    QueueError,
    QueueTransientError,
)


logging.getLogger("azure.servicebus").setLevel(logging.WARNING)


class AzureServiceBusProcessingQueue:
    enabled = True

    def __init__(
        self,
        *,
        queue_name: str,
        fully_qualified_namespace: str = "",
        connection_string: str = "",
        managed_identity_client_id: str = "",
        operation_timeout_seconds: int = 30,
        max_lock_renewal_seconds: int = 300,
    ) -> None:
        if not queue_name.strip():
            raise QueueError("AZURE_SERVICE_BUS_QUEUE_NAME is required")
        if operation_timeout_seconds < 1 or max_lock_renewal_seconds < 1:
            raise QueueError("Service Bus timeout settings must be positive")
        self._credential: DefaultAzureCredential | None = None
        if connection_string:
            self._client = ServiceBusClient.from_connection_string(
                connection_string,
                retry_total=3,
                retry_backoff_max=4,
            )
        elif fully_qualified_namespace:
            self._credential = DefaultAzureCredential(
                managed_identity_client_id=managed_identity_client_id or None
            )
            self._client = ServiceBusClient(
                fully_qualified_namespace,
                self._credential,
                retry_total=3,
                retry_backoff_max=4,
            )
        else:
            raise QueueError(
                "Set AZURE_SERVICE_BUS_NAMESPACE for Managed Identity or "
                "AZURE_SERVICE_BUS_CONNECTION_STRING for local development"
            )
        self.queue_name = queue_name
        self.operation_timeout_seconds = operation_timeout_seconds
        self.max_lock_renewal_seconds = max_lock_renewal_seconds

    def publish(self, message: ProcessingMessage) -> None:
        outbound = ServiceBusMessage(
            message.to_json(),
            content_type="application/json",
            message_id=str(message.job_id),
            correlation_id=message.trace_id,
            subject="document.processing.requested.v1",
        )
        try:
            with self._client.get_queue_sender(self.queue_name) as sender:
                sender.send_messages(outbound, timeout=self.operation_timeout_seconds)
        except ServiceBusError as exc:
            raise QueueTransientError("Azure Service Bus publish failed") from exc
        except Exception as exc:
            raise QueueError("Azure Service Bus publish failed") from exc

    def receive_one(self, handler: MessageHandler, *, max_wait_seconds: float) -> bool:
        wait_seconds = max(0.1, min(max_wait_seconds, self.operation_timeout_seconds))
        renewer = AutoLockRenewer()
        try:
            with self._client.get_queue_receiver(
                self.queue_name,
                max_wait_time=wait_seconds,
            ) as receiver:
                messages = receiver.receive_messages(
                    max_message_count=1,
                    max_wait_time=wait_seconds,
                )
                if not messages:
                    return False
                received = messages[0]
                try:
                    message = ProcessingMessage.from_json(str(received))
                except InvalidQueueMessage:
                    receiver.dead_letter_message(
                        received,
                        reason="invalid_envelope",
                        error_description="Message does not match processing schema version 1",
                    )
                    return True
                renewer.register(
                    receiver,
                    received,
                    max_lock_renewal_duration=self.max_lock_renewal_seconds,
                )
                disposition = handler(message, int(received.delivery_count or 1))
                if disposition == QueueDisposition.COMPLETE:
                    receiver.complete_message(received)
                elif disposition == QueueDisposition.ABANDON:
                    receiver.abandon_message(received)
                else:
                    receiver.dead_letter_message(
                        received,
                        reason="processing_rejected",
                        error_description="Message could not be matched to a processable job",
                    )
                return True
        except ServiceBusError as exc:
            raise QueueTransientError("Azure Service Bus receive failed") from exc
        except QueueError:
            raise
        except Exception as exc:
            raise QueueError("Azure Service Bus receive failed") from exc
        finally:
            renewer.close()

    def is_ready(self) -> bool:
        try:
            with self._client.get_queue_receiver(self.queue_name, max_wait_time=0.1) as receiver:
                receiver.peek_messages(max_message_count=1, timeout=self.operation_timeout_seconds)
            return True
        except Exception:
            return False

    def close(self) -> None:
        self._client.close()
        if self._credential is not None:
            self._credential.close()
