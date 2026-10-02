from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from hmac import compare_digest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Protocol
from urllib.parse import parse_qs, unquote, urlparse

from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient


DELIVERY_KEY_FIELD = "custom_invoice_review_delivery_key"


class DraftStore(Protocol):
    def create_or_get(self, delivery_key: str, draft: dict[str, object]) -> dict[str, object]: ...

    def get_by_key(self, delivery_key: str) -> dict[str, object] | None: ...

    def get_by_name(self, name: str) -> dict[str, object] | None: ...


class InMemoryDraftStore:
    def __init__(self) -> None:
        self.by_key: dict[str, dict[str, object]] = {}

    def create_or_get(self, delivery_key: str, draft: dict[str, object]) -> dict[str, object]:
        return self.by_key.setdefault(delivery_key, draft)

    def get_by_key(self, delivery_key: str) -> dict[str, object] | None:
        return self.by_key.get(delivery_key)

    def get_by_name(self, name: str) -> dict[str, object] | None:
        return next((draft for draft in self.by_key.values() if draft.get("name") == name), None)


class AzureBlobDraftStore:
    def __init__(self, account_url: str, container_name: str, client_id: str = "") -> None:
        self.credential = DefaultAzureCredential(managed_identity_client_id=client_id or None)
        self.service = BlobServiceClient(account_url=account_url, credential=self.credential)
        self.container = self.service.get_container_client(container_name)

    def create_or_get(self, delivery_key: str, draft: dict[str, object]) -> dict[str, object]:
        blob = self.container.get_blob_client(_blob_name(delivery_key))
        body = json.dumps(draft, separators=(",", ":"), sort_keys=True)
        try:
            blob.upload_blob(body, overwrite=False)
            return draft
        except ResourceExistsError:
            return _decode_draft(blob.download_blob().readall())

    def get_by_key(self, delivery_key: str) -> dict[str, object] | None:
        blob = self.container.get_blob_client(_blob_name(delivery_key))
        try:
            return _decode_draft(blob.download_blob().readall())
        except ResourceNotFoundError:
            return None

    def get_by_name(self, name: str) -> dict[str, object] | None:
        if not name.startswith("PV-"):
            return None
        for item in self.container.list_blobs(name_starts_with="drafts/"):
            draft = _decode_draft(self.container.download_blob(item.name).readall())
            if draft.get("name") == name:
                return draft
        return None


@dataclass(frozen=True)
class SinkConfig:
    run_id: str
    authorization: str
    response_delay_seconds: float


def validate_sink_environment(environment: dict[str, str]) -> SinkConfig:
    failures: list[str] = []
    if environment.get("APP_ENV", "").strip().lower() != "production":
        failures.append("APP_ENV must equal production")
    if environment.get("VALIDATION_SINK_ENABLED", "").strip().lower() != "true":
        failures.append("VALIDATION_SINK_ENABLED must equal true")
    run_id = environment.get("PRODUCTION_VALIDATION_RUN_ID", "").strip()
    if len(run_id) < 12:
        failures.append("PRODUCTION_VALIDATION_RUN_ID is required")
    secret = environment.get("VALIDATION_SINK_SECRET", "").strip()
    if len(secret) < 24:
        failures.append("VALIDATION_SINK_SECRET must contain at least 24 characters")
    try:
        delay = float(environment.get("VALIDATION_SINK_RESPONSE_DELAY_SECONDS", "5"))
        if delay <= 0:
            raise ValueError
    except ValueError:
        failures.append("VALIDATION_SINK_RESPONSE_DELAY_SECONDS must be positive")
        delay = 0
    if failures:
        raise RuntimeError("; ".join(failures))
    return SinkConfig(
        run_id=run_id,
        authorization=f"token validation:{secret}",
        response_delay_seconds=delay,
    )


def build_draft(payload: dict[str, object]) -> tuple[str, dict[str, object]]:
    delivery_key = str(payload.get(DELIVERY_KEY_FIELD) or "").strip()
    if not delivery_key:
        raise ValueError("delivery key is required")
    items = payload.get("items")
    taxes = payload.get("taxes", [])
    if (
        not isinstance(items, list)
        or not items
        or not all(isinstance(item, dict) for item in items)
    ):
        raise ValueError("items must be a non-empty array of objects")
    if not isinstance(taxes, list) or not all(isinstance(item, dict) for item in taxes):
        raise ValueError("taxes must be an array of objects")
    try:
        net_total = sum(
            Decimal(str(item.get("qty", 0))) * Decimal(str(item.get("rate", 0))) for item in items
        )
        tax_total = sum(
            net_total * Decimal(str(item.get("rate", 0))) / Decimal("100") for item in taxes
        )
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("item and tax values must be numeric") from exc
    draft = {
        **payload,
        "name": f"PV-{sha256(delivery_key.encode()).hexdigest()[:12].upper()}",
        "docstatus": 0,
        "grand_total": str((net_total + tax_total).quantize(Decimal("0.01"))),
        "modified": datetime.now(UTC).isoformat(),
    }
    return delivery_key, draft


def handler_factory(store: DraftStore, config: SinkConfig) -> type[BaseHTTPRequestHandler]:
    class ValidationSinkHandler(BaseHTTPRequestHandler):
        server_version = "ProductionValidationSink/1"

        def do_POST(self) -> None:  # noqa: N802
            if not self._authorized():
                return
            if self.path != "/api/resource/Purchase%20Invoice":
                self._json(404, {"message": "Not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("payload must be an object")
                delivery_key, draft = build_draft(payload)
                persisted = store.create_or_get(delivery_key, draft)
            except (ValueError, json.JSONDecodeError):
                self._json(400, {"message": "Invalid validation payload"})
                return
            time.sleep(config.response_delay_seconds)
            self._json(200, {"data": persisted})

        def do_GET(self) -> None:  # noqa: N802
            if not self._authorized():
                return
            parsed = urlparse(self.path)
            collection = "/api/resource/Purchase%20Invoice"
            if parsed.path == collection:
                try:
                    filters = json.loads(parse_qs(parsed.query).get("filters", ["{}"])[0])
                    delivery_key = str(filters.get(DELIVERY_KEY_FIELD) or "")
                except (AttributeError, json.JSONDecodeError):
                    self._json(400, {"message": "Invalid filters"})
                    return
                draft = store.get_by_key(delivery_key)
                data = [] if draft is None else [_lookup_projection(draft)]
                self._json(200, {"data": data})
                return
            prefix = collection + "/"
            if parsed.path.startswith(prefix):
                draft = store.get_by_name(unquote(parsed.path[len(prefix) :]))
                self._json(
                    200 if draft else 404, {"data": draft} if draft else {"message": "Not found"}
                )
                return
            self._json(404, {"message": "Not found"})

        def log_message(self, format: str, *args: object) -> None:
            return None

        def _authorized(self) -> bool:
            if compare_digest(self.headers.get("Authorization", ""), config.authorization):
                return True
            self._json(403, {"message": "Forbidden"})
            return False

        def _json(self, status: int, payload: dict[str, object]) -> None:
            body = json.dumps(payload, separators=(",", ":")).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    return ValidationSinkHandler


def main() -> None:
    config = validate_sink_environment(dict(os.environ))
    store = AzureBlobDraftStore(
        _required("VALIDATION_SINK_STORAGE_URL"),
        _required("VALIDATION_SINK_CONTAINER"),
        os.environ.get("AZURE_MANAGED_IDENTITY_CLIENT_ID", ""),
    )
    port = int(os.environ.get("PORT", "8080"))
    ThreadingHTTPServer(("0.0.0.0", port), handler_factory(store, config)).serve_forever()


def _lookup_projection(draft: dict[str, object]) -> dict[str, object]:
    return {
        "name": draft.get("name"),
        "docstatus": draft.get("docstatus"),
        "custom_invoice_review_payload_hash": draft.get("custom_invoice_review_payload_hash"),
    }


def _blob_name(delivery_key: str) -> str:
    return f"drafts/{sha256(delivery_key.encode()).hexdigest()}.json"


def _decode_draft(value: bytes) -> dict[str, object]:
    payload = json.loads(value.decode())
    if not isinstance(payload, dict):
        raise RuntimeError("validation sink state is invalid")
    return payload


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


if __name__ == "__main__":
    main()
