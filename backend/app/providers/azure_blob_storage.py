from __future__ import annotations

import base64
import hashlib
import logging
from datetime import datetime
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile
from typing import Iterable
from uuid import uuid4

from azure.core.exceptions import (
    HttpResponseError,
    ResourceExistsError,
    ResourceNotFoundError,
    ServiceRequestError,
    ServiceResponseError,
)
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings

from app.providers.storage import (
    PDF_SIGNATURE,
    StorageError,
    StorageNotFoundError,
    StorageTransientError,
    StoredFile,
)


_AZURITE_CONNECTION_STRING = (
    "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/"
    "K1SZFPTOtr/KBHBeksoGMGw==;"
    "BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
)
_RETRY_OPTIONS = {
    "retry_total": 3,
    "retry_connect": 3,
    "retry_read": 3,
    "retry_status": 3,
    "retry_backoff_max": 4,
}

# Azure's INFO-level HTTP policy includes object paths and is too verbose for
# application logs. Operational failures are surfaced through typed errors.
logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)


class AzureBlobStorageService:
    def __init__(
        self,
        *,
        container: str,
        cache_root: Path,
        max_upload_bytes: int,
        account_url: str = "",
        connection_string: str = "",
        managed_identity_client_id: str = "",
        operation_timeout_seconds: int = 30,
        create_container: bool = False,
    ) -> None:
        if not container:
            raise StorageError("AZURE_STORAGE_CONTAINER is required")
        if operation_timeout_seconds < 1:
            raise StorageError("AZURE_STORAGE_TIMEOUT_SECONDS must be positive")
        if connection_string:
            service = BlobServiceClient.from_connection_string(
                (
                    _AZURITE_CONNECTION_STRING
                    if connection_string == "UseDevelopmentStorage=true"
                    else connection_string
                ),
                connection_timeout=operation_timeout_seconds,
                read_timeout=operation_timeout_seconds,
                **_RETRY_OPTIONS,
            )
        elif account_url:
            credential = DefaultAzureCredential(
                managed_identity_client_id=managed_identity_client_id or None
            )
            service = BlobServiceClient(
                account_url=account_url,
                credential=credential,
                connection_timeout=operation_timeout_seconds,
                read_timeout=operation_timeout_seconds,
                **_RETRY_OPTIONS,
            )
        else:
            raise StorageError(
                "Set AZURE_STORAGE_ACCOUNT_URL for Managed Identity or "
                "AZURE_STORAGE_CONNECTION_STRING for local development"
            )
        self.container = service.get_container_client(container)
        self.cache_root = cache_root.resolve()
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self.max_upload_bytes = max_upload_bytes
        self.operation_timeout_seconds = operation_timeout_seconds
        if create_container:
            try:
                self.container.create_container(
                    public_access=None,
                    timeout=self.operation_timeout_seconds,
                )
            except ResourceExistsError:
                pass
            except Exception as exc:
                raise _storage_error(exc, "Azure Blob container creation failed") from exc

    def save_upload(
        self,
        original_filename: str,
        content_type: str,
        content: bytes,
        *,
        workspace_id: str = "default",
    ) -> StoredFile:
        return self.save_upload_stream(
            original_filename,
            content_type,
            (content,),
            workspace_id=workspace_id,
        )

    def save_upload_stream(
        self,
        original_filename: str,
        content_type: str,
        chunks: Iterable[bytes],
        *,
        workspace_id: str = "default",
    ) -> StoredFile:
        _validate_pdf_name_and_type(original_filename, content_type)
        content = _bounded_content(chunks, self.max_upload_bytes)
        object_id = uuid4().hex
        workspace_hash = _workspace_hash(workspace_id)
        storage_key = f"workspaces/{workspace_hash}/{object_id}.pdf"
        filename = _display_filename(original_filename)
        metadata = {
            "workspace_hash": workspace_hash,
            "object_id": object_id,
            "sha256": hashlib.sha256(content).hexdigest(),
            "size_bytes": str(len(content)),
            "original_filename_b64": base64.urlsafe_b64encode(filename.encode("utf-8")).decode(
                "ascii"
            ),
        }
        try:
            self.container.upload_blob(
                name=storage_key,
                data=content,
                overwrite=False,
                metadata=metadata,
                content_settings=ContentSettings(content_type="application/pdf"),
                timeout=self.operation_timeout_seconds,
            )
        except Exception as exc:
            raise _storage_error(exc, "Azure Blob upload failed") from exc
        return StoredFile(
            storage_key=storage_key,
            original_filename=filename,
            content_type=content_type,
            size_bytes=len(content),
        )

    def open_for_parser(self, storage_key: str) -> Path:
        _validate_storage_key(storage_key)
        target = self._cache_path(storage_key)
        temp_path: Path | None = None
        try:
            with NamedTemporaryFile(delete=False, dir=self.cache_root, suffix=".tmp") as temp:
                temp_path = Path(temp.name)
                stream = self.container.download_blob(
                    storage_key,
                    timeout=self.operation_timeout_seconds,
                )
                stream.readinto(temp)
            temp_path.replace(target)
            return target
        except Exception as exc:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            raise _storage_error(exc, "Azure Blob download failed") from exc

    def create_download_url(self, storage_key: str, expires_seconds: int = 300) -> None:
        _validate_storage_key(storage_key)
        # Downloads stay behind the authenticated application content route.
        # This avoids account-key SAS generation when production uses Managed Identity.
        return None

    def delete(self, storage_key: str) -> None:
        _validate_storage_key(storage_key)
        try:
            self.container.delete_blob(
                storage_key,
                delete_snapshots="include",
                timeout=self.operation_timeout_seconds,
            )
        except ResourceNotFoundError:
            pass
        except Exception as exc:
            raise _storage_error(exc, "Azure Blob delete failed") from exc
        self._cache_path(storage_key).unlink(missing_ok=True)

    def purge_parser_cache(self, older_than: datetime) -> int:
        removed = 0
        cutoff = older_than.timestamp()
        for path in self.cache_root.glob("*.pdf"):
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
                removed += 1
        return removed

    def is_ready(self) -> bool:
        try:
            properties = self.container.get_container_properties(
                timeout=self.operation_timeout_seconds
            )
            return properties.public_access is None
        except Exception:
            return False

    def _cache_path(self, storage_key: str) -> Path:
        filename = f"{hashlib.sha256(storage_key.encode('utf-8')).hexdigest()}.pdf"
        return self.cache_root / filename


def _validate_pdf_name_and_type(original_filename: str, content_type: str) -> None:
    if Path(original_filename).suffix.lower() != ".pdf" or content_type != "application/pdf":
        raise StorageError("Only PDF files are accepted")


def _bounded_content(chunks: Iterable[bytes], max_upload_bytes: int) -> bytes:
    content = bytearray()
    for chunk in chunks:
        if chunk:
            content.extend(chunk)
        if len(content) > max_upload_bytes:
            raise StorageError("Upload exceeds max file size")
    if not content:
        raise StorageError("Upload is empty")
    if not content.startswith(PDF_SIGNATURE):
        raise StorageError("File signature is not a PDF")
    return bytes(content)


def _validate_storage_key(storage_key: str) -> None:
    path = PurePosixPath(storage_key)
    workspace_part = path.parts[1] if len(path.parts) == 3 else ""
    filename = path.parts[2] if len(path.parts) == 3 else ""
    object_part = filename.removesuffix(".pdf")
    if (
        path.is_absolute()
        or len(path.parts) != 3
        or path.parts[0] != "workspaces"
        or len(workspace_part) != 24
        or any(character not in "0123456789abcdef" for character in workspace_part)
        or len(filename) != 36
        or not filename.endswith(".pdf")
        or any(character not in "0123456789abcdef" for character in object_part)
        or any(part in {".", ".."} for part in path.parts)
    ):
        raise StorageError("Invalid Azure Blob storage key")


def _workspace_hash(workspace_id: str) -> str:
    if not workspace_id.strip():
        raise StorageError("Workspace ID is required for Azure Blob storage")
    return hashlib.sha256(workspace_id.encode("utf-8")).hexdigest()[:24]


def _display_filename(original_filename: str) -> str:
    cleaned = "".join(char for char in Path(original_filename).name if char.isprintable())
    return cleaned[:255] or "upload.pdf"


def _storage_error(exc: Exception, message: str) -> StorageError:
    if isinstance(exc, ResourceNotFoundError):
        return StorageNotFoundError("Stored file does not exist")
    if isinstance(exc, (ServiceRequestError, ServiceResponseError)):
        return StorageTransientError(message)
    if isinstance(exc, HttpResponseError) and exc.status_code in {408, 429, 500, 502, 503, 504}:
        return StorageTransientError(message)
    return StorageError(message)
