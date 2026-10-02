from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from typing import Sequence
from uuid import UUID, uuid4

from azure.identity import DefaultAzureCredential
from azure.servicebus import ServiceBusClient, ServiceBusMessage, ServiceBusSubQueue

RUN_ID_ENV = "PRODUCTION_VALIDATION_RUN_ID"
RUN_ID_PROPERTY = "production_validation_run_id"


@dataclass(frozen=True)
class ProbeEnvelope:
    body: str
    message_id: str
    correlation_id: str
    subject: str
    run_id: str

    def service_bus_message(self) -> ServiceBusMessage:
        return ServiceBusMessage(
            self.body,
            content_type="application/json",
            message_id=self.message_id,
            correlation_id=self.correlation_id,
            subject=self.subject,
            application_properties={RUN_ID_PROPERTY: self.run_id},
        )


def processing_envelope(
    *,
    run_id: str,
    job_id: UUID,
    document_id: UUID,
    workspace_id: str,
    trace_id: str,
) -> ProbeEnvelope:
    body = json.dumps(
        {
            "document_id": str(document_id),
            "job_id": str(job_id),
            "schema_version": 1,
            "trace_id": trace_id,
            "workspace_id": workspace_id,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    return ProbeEnvelope(
        body=body,
        message_id=f"validation-{job_id}-{uuid4().hex[:12]}",
        correlation_id=trace_id,
        subject="production.validation.processing.v1",
        run_id=run_id,
    )


def poison_envelope(*, run_id: str) -> ProbeEnvelope:
    return ProbeEnvelope(
        body='{"schema_version":999,"production_validation":true}',
        message_id=f"validation-poison-{uuid4().hex}",
        correlation_id=run_id,
        subject="production.validation.poison.v1",
        run_id=run_id,
    )


def message_belongs_to_run(message: object, run_id: str) -> bool:
    properties = getattr(message, "application_properties", None) or {}
    for key, value in properties.items():
        normalized_key = key.decode() if isinstance(key, bytes) else str(key)
        normalized_value = value.decode() if isinstance(value, bytes) else str(value)
        if normalized_key == RUN_ID_PROPERTY and normalized_value == run_id:
            return True
    return False


def require_owned_inventory(messages: list[object], run_id: str) -> None:
    foreign = [message for message in messages if not message_belongs_to_run(message, run_id)]
    if foreign:
        raise RuntimeError(
            "DLQ contains messages not owned by this validation run; refusing replay"
        )


class QueueProbe:
    def __init__(self, *, namespace: str, queue_name: str, client_id: str = "") -> None:
        if not namespace or not queue_name:
            raise ValueError("namespace and queue name are required")
        self.credential = DefaultAzureCredential(managed_identity_client_id=client_id or None)
        self.client = ServiceBusClient(namespace, self.credential)
        self.queue_name = queue_name

    def publish(self, envelope: ProbeEnvelope) -> None:
        with self.client.get_queue_sender(self.queue_name) as sender:
            sender.send_messages(envelope.service_bus_message())

    def inspect_dead_letters(self, *, run_id: str, maximum: int = 20) -> list[dict[str, object]]:
        with self.client.get_queue_receiver(
            self.queue_name,
            sub_queue=ServiceBusSubQueue.DEAD_LETTER,
            max_wait_time=5,
        ) as receiver:
            messages = receiver.peek_messages(max_message_count=maximum)
        return [
            {
                "owned_by_run": message_belongs_to_run(message, run_id),
                "message_id": str(message.message_id or ""),
                "correlation_id": str(message.correlation_id or ""),
                "dead_letter_reason": str(getattr(message, "dead_letter_reason", "") or ""),
            }
            for message in messages
        ]

    def replay_owned(
        self,
        *,
        run_id: str,
        replacement: ProbeEnvelope,
        confirmed: bool,
    ) -> dict[str, object]:
        if not confirmed:
            raise ValueError("--confirm-owned-replay is required")
        if replacement.run_id != run_id:
            raise ValueError("replacement run ID does not match the requested run")
        with self.client.get_queue_receiver(
            self.queue_name,
            sub_queue=ServiceBusSubQueue.DEAD_LETTER,
            max_wait_time=5,
        ) as receiver:
            inventory = receiver.peek_messages(max_message_count=20)
            require_owned_inventory(inventory, run_id)
            messages = receiver.receive_messages(max_message_count=1, max_wait_time=5)
            if not messages:
                raise RuntimeError("no dead-letter message owned by this validation run was found")
            selected = messages[0]
            if not message_belongs_to_run(selected, run_id):
                receiver.abandon_message(selected)
                raise RuntimeError(
                    "received dead-letter message is not owned by this validation run"
                )
            with self.client.get_queue_sender(self.queue_name) as sender:
                sender.send_messages(replacement.service_bus_message())
            receiver.complete_message(selected)
        return {
            "completed_dead_letter_message_id": str(selected.message_id or ""),
            "replacement_message_id": replacement.message_id,
            "run_id": run_id,
        }

    def close(self) -> None:
        self.client.close()
        self.credential.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    configured_run_id = os.environ.get(RUN_ID_ENV, "")
    if not configured_run_id or args.run_id != configured_run_id:
        raise SystemExit(f"--run-id must exactly match {RUN_ID_ENV}")
    probe = QueueProbe(
        namespace=args.namespace,
        queue_name=args.queue_name,
        client_id=args.managed_identity_client_id,
    )
    try:
        if args.command == "publish-poison":
            envelope = poison_envelope(run_id=args.run_id)
            probe.publish(envelope)
            result: object = {"message_id": envelope.message_id, "run_id": args.run_id}
        elif args.command == "publish-processing":
            envelope = _processing_from_args(args)
            probe.publish(envelope)
            result = {"message_id": envelope.message_id, "run_id": args.run_id}
        elif args.command == "inspect-dlq":
            result = probe.inspect_dead_letters(run_id=args.run_id, maximum=args.maximum)
        else:
            replacement = _processing_from_args(args)
            result = probe.replay_owned(
                run_id=args.run_id,
                replacement=replacement,
                confirmed=args.confirm_owned_replay,
            )
    finally:
        probe.close()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Guarded Azure Service Bus validation probe.")
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--queue-name", required=True)
    parser.add_argument("--managed-identity-client-id", default="")
    parser.add_argument("--run-id", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("publish-poison")
    inspect = commands.add_parser("inspect-dlq")
    inspect.add_argument("--maximum", type=int, default=20)
    for name in ("publish-processing", "replay-owned"):
        command = commands.add_parser(name)
        command.add_argument("--job-id", type=UUID, required=True)
        command.add_argument("--document-id", type=UUID, required=True)
        command.add_argument("--workspace-id", default="azure-validation")
        command.add_argument("--trace-id", default="")
        if name == "replay-owned":
            command.add_argument("--confirm-owned-replay", action="store_true")
    return parser


def _processing_from_args(args: argparse.Namespace) -> ProbeEnvelope:
    if args.workspace_id != "azure-validation":
        raise SystemExit("queue probes are restricted to the azure-validation workspace")
    trace_id = args.trace_id.strip() or uuid4().hex
    return processing_envelope(
        run_id=args.run_id,
        job_id=args.job_id,
        document_id=args.document_id,
        workspace_id=args.workspace_id,
        trace_id=trace_id,
    )


if __name__ == "__main__":
    raise SystemExit(main())
