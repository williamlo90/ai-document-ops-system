from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass
from enum import StrEnum
from typing import Callable, Protocol
from uuid import UUID
from uuid import uuid4

from app.core.observability import OperationEvent, log_operation
from app.core.security import SecurityContext
from app.documents.jobs import ProcessingJob
from app.documents.models import DocumentRecord


MESSAGE_SCHEMA_VERSION = 1
_MESSAGE_FIELDS = {
    "schema_version",
    "job_id",
    "document_id",
    "workspace_id",
    "trace_id",
}


class QueueError(RuntimeError):
    pass


class QueueTransientError(QueueError):
    pass


class InvalidQueueMessage(QueueError):
    pass


class QueueDisposition(StrEnum):
    COMPLETE = "complete"
    ABANDON = "abandon"
    DEAD_LETTER = "dead_letter"


@dataclass(frozen=True)
class ProcessingMessage:
    job_id: UUID
    document_id: UUID
    workspace_id: str
    trace_id: str
    schema_version: int = MESSAGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != MESSAGE_SCHEMA_VERSION:
            raise InvalidQueueMessage(
                f"Unsupported processing message schema: {self.schema_version}"
            )
        if not self.workspace_id.strip() or len(self.workspace_id) > 128:
            raise InvalidQueueMessage("workspace_id is required and must be at most 128 characters")
        if not self.trace_id.strip() or len(self.trace_id) > 128:
            raise InvalidQueueMessage("trace_id is required and must be at most 128 characters")

    def to_json(self) -> str:
        return json.dumps(
            {
                "schema_version": self.schema_version,
                "job_id": str(self.job_id),
                "document_id": str(self.document_id),
                "workspace_id": self.workspace_id,
                "trace_id": self.trace_id,
            },
            separators=(",", ":"),
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, value: str) -> ProcessingMessage:
        try:
            payload = json.loads(value)
            if not isinstance(payload, dict) or set(payload) != _MESSAGE_FIELDS:
                raise InvalidQueueMessage("Processing message has an invalid envelope")
            return cls(
                schema_version=int(payload["schema_version"]),
                job_id=UUID(str(payload["job_id"])),
                document_id=UUID(str(payload["document_id"])),
                workspace_id=str(payload["workspace_id"]),
                trace_id=str(payload["trace_id"]),
            )
        except InvalidQueueMessage:
            raise
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise InvalidQueueMessage("Processing message has an invalid envelope") from exc


MessageHandler = Callable[[ProcessingMessage, int], QueueDisposition]


class ProcessingQueue(Protocol):
    enabled: bool

    def publish(self, message: ProcessingMessage) -> None: ...

    def receive_one(self, handler: MessageHandler, *, max_wait_seconds: float) -> bool: ...

    def is_ready(self) -> bool: ...

    def close(self) -> None: ...


class NullProcessingQueue:
    """No-op wake-up transport; the database polling worker remains authoritative."""

    enabled = False

    def publish(self, message: ProcessingMessage) -> None:
        del message

    def receive_one(self, handler: MessageHandler, *, max_wait_seconds: float) -> bool:
        del handler, max_wait_seconds
        return False

    def is_ready(self) -> bool:
        return True

    def close(self) -> None:
        return None


@dataclass
class _MemoryDelivery:
    body: str
    delivery_count: int = 1


class InMemoryProcessingQueue:
    """Deterministic queue used by contract tests and local composition tests."""

    def __init__(self) -> None:
        self.enabled = True
        self.pending: deque[_MemoryDelivery] = deque()
        self.dead_letters: list[_MemoryDelivery] = []

    def publish(self, message: ProcessingMessage) -> None:
        self.pending.append(_MemoryDelivery(message.to_json()))

    def inject_raw(self, body: str, *, delivery_count: int = 1) -> None:
        self.pending.append(_MemoryDelivery(body, delivery_count))

    def receive_one(self, handler: MessageHandler, *, max_wait_seconds: float) -> bool:
        del max_wait_seconds
        if not self.pending:
            return False
        delivery = self.pending.popleft()
        try:
            message = ProcessingMessage.from_json(delivery.body)
            disposition = handler(message, delivery.delivery_count)
        except InvalidQueueMessage:
            disposition = QueueDisposition.DEAD_LETTER
        if disposition == QueueDisposition.ABANDON:
            delivery.delivery_count += 1
            self.pending.append(delivery)
        elif disposition == QueueDisposition.DEAD_LETTER:
            self.dead_letters.append(delivery)
        return True

    def is_ready(self) -> bool:
        return True

    def close(self) -> None:
        return None


def publish_wakeup(
    queue: ProcessingQueue,
    job: ProcessingJob,
    document: DocumentRecord,
    context: SecurityContext,
) -> None:
    if not queue.enabled:
        return
    trace_id = context.trace_id or uuid4().hex
    try:
        queue.publish(
            ProcessingMessage(
                job_id=job.id,
                document_id=document.id,
                workspace_id=document.workspace_id,
                trace_id=trace_id,
            )
        )
        log_operation(
            OperationEvent(
                event_type="queue_wakeup_published",
                workspace_id=document.workspace_id,
                actor=context.actor,
                document_id=str(document.id),
                job_id=str(job.id),
                status=job.status.value,
                trace_id=trace_id,
            )
        )
    except QueueError:
        # The committed database job remains processable by the polling fallback.
        log_operation(
            OperationEvent(
                event_type="queue_publish_failed",
                workspace_id=document.workspace_id,
                actor=context.actor,
                document_id=str(document.id),
                job_id=str(job.id),
                status=job.status.value,
                error_code="queue_unavailable",
                retryable=True,
                trace_id=trace_id,
            )
        )
