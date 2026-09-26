from __future__ import annotations

import logging
import os
from pathlib import PurePosixPath
from urllib.parse import unquote, urlparse

import azure.functions as func
import httpx
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from azure.storage.blob import BlobClient


app = func.FunctionApp()
_MAX_UPLOAD_BYTES = 15 * 1024 * 1024


def _required_setting(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _blob_location(event_data: dict[str, object]) -> tuple[str, str]:
    raw_url = str(event_data.get("url", ""))
    parsed = urlparse(raw_url)
    expected_account = urlparse(_required_setting("STORAGE_ACCOUNT_URL"))
    if parsed.scheme != "https" or parsed.hostname != expected_account.hostname:
        raise ValueError("Blob event URL is outside the configured storage account")
    parts = PurePosixPath(unquote(parsed.path)).parts
    expected_container = _required_setting("EXTERNAL_DROP_CONTAINER")
    if len(parts) < 3 or parts[1] != expected_container:
        raise ValueError("Blob event is outside the external-drop container")
    return raw_url, parts[-1]


def _credential() -> DefaultAzureCredential:
    return DefaultAzureCredential(
        managed_identity_client_id=os.environ.get("AZURE_CLIENT_ID") or None
    )


def _forward_blob(blob_url: str, filename: str, event_id: str) -> None:
    credential = _credential()
    blob = BlobClient.from_blob_url(blob_url, credential=credential)
    lease = blob.acquire_lease(lease_duration=60)
    try:
        properties = blob.get_blob_properties(lease=lease)
        metadata = dict(properties.metadata or {})
        if metadata.get("docintel_ingested") == "true":
            logging.info("external_blob_already_ingested event_id=%s", event_id)
            return
        if properties.size <= 0 or properties.size > _MAX_UPLOAD_BYTES:
            raise ValueError("Blob size is outside the accepted PDF upload range")
        if not filename.lower().endswith(".pdf"):
            raise ValueError("Only PDF blobs are accepted")
        payload = blob.download_blob(lease=lease, max_concurrency=1).readall()
        if len(payload) != properties.size:
            raise RuntimeError("Blob download size mismatch")

        vault = SecretClient(vault_url=_required_setting("KEY_VAULT_URI"), credential=credential)
        uploader_token = vault.get_secret("uploader-token").value
        if not uploader_token:
            raise RuntimeError("Uploader token is empty")

        endpoint = f"{_required_setting('API_BASE_URL').rstrip('/')}/documents/upload"
        with httpx.Client(timeout=45.0) as client:
            response = client.post(
                endpoint,
                headers={"X-Access-Token": uploader_token},
                files={"file": (filename, payload, "application/pdf")},
            )
        response.raise_for_status()
        metadata["docintel_ingested"] = "true"
        metadata["docintel_event_id"] = event_id
        blob.set_blob_metadata(metadata=metadata, lease=lease)
    finally:
        lease.release()


@app.event_grid_trigger(arg_name="event")
def BlobCreatedIngestion(event: func.EventGridEvent) -> None:
    data = event.get_json()
    if not isinstance(data, dict):
        raise ValueError("Event Grid payload must be an object")
    blob_url, filename = _blob_location(data)
    logging.info(
        "external_blob_received event_id=%s subject=%s",
        event.id,
        event.subject,
    )
    _forward_blob(blob_url, filename, event.id)
    logging.info("external_blob_forwarded event_id=%s", event.id)
