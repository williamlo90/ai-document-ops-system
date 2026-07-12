from __future__ import annotations

from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterable, Protocol
from uuid import uuid4


PDF_SIGNATURE = b"%PDF-"


class StorageError(ValueError):
    pass


@dataclass(frozen=True)
class StoredFile:
    storage_key: str
    original_filename: str
    content_type: str
    size_bytes: int


class DocumentStorage(Protocol):
    def save_upload(
        self,
        original_filename: str,
        content_type: str,
        content: bytes,
    ) -> StoredFile: ...

    def save_upload_stream(
        self,
        original_filename: str,
        content_type: str,
        chunks: Iterable[bytes],
    ) -> StoredFile: ...

    def open_for_parser(self, storage_key: str) -> Path: ...

    def create_download_url(self, storage_key: str, expires_seconds: int = 300) -> str | None: ...


class LocalStorageService:
    def __init__(self, upload_root: Path, max_upload_bytes: int = 15 * 1024 * 1024) -> None:
        self.upload_root = upload_root.resolve()
        self.max_upload_bytes = max_upload_bytes
        self.upload_root.mkdir(parents=True, exist_ok=True)

    def save_upload(self, original_filename: str, content_type: str, content: bytes) -> StoredFile:
        self._validate_upload(original_filename, content_type, content)
        storage_key = f"{uuid4()}.pdf"
        target_path = self._resolve_storage_key(storage_key)
        target_path.write_bytes(content)
        return StoredFile(
            storage_key=storage_key,
            original_filename=Path(original_filename).name,
            content_type=content_type,
            size_bytes=len(content),
        )

    def save_upload_stream(
        self,
        original_filename: str,
        content_type: str,
        chunks: Iterable[bytes],
    ) -> StoredFile:
        if Path(original_filename).suffix.lower() != ".pdf":
            raise StorageError("Only PDF files are accepted")
        if content_type != "application/pdf":
            raise StorageError("Invalid content type for PDF upload")

        storage_key = f"{uuid4()}.pdf"
        target_path = self._resolve_storage_key(storage_key)
        size_bytes = 0
        first_bytes = b""
        temp_path: Path | None = None
        try:
            with NamedTemporaryFile(delete=False, dir=self.upload_root, suffix=".tmp") as temp_file:
                temp_path = Path(temp_file.name)
                for chunk in chunks:
                    if not chunk:
                        continue
                    if not first_bytes:
                        first_bytes = chunk[: len(PDF_SIGNATURE)]
                    size_bytes += len(chunk)
                    if size_bytes > self.max_upload_bytes:
                        raise StorageError("Upload exceeds max file size")
                    temp_file.write(chunk)
            if size_bytes == 0:
                raise StorageError("Upload is empty")
            if not first_bytes.startswith(PDF_SIGNATURE):
                raise StorageError("File signature is not a PDF")
        except Exception:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            raise
        temp_path.replace(target_path)
        return StoredFile(
            storage_key=storage_key,
            original_filename=self._display_filename(original_filename),
            content_type=content_type,
            size_bytes=size_bytes,
        )

    def open_for_parser(self, storage_key: str) -> Path:
        path = self._resolve_storage_key(storage_key)
        if not path.exists():
            raise StorageError("Stored file does not exist")
        return path

    def create_download_url(self, storage_key: str, expires_seconds: int = 300) -> str | None:
        self._resolve_storage_key(storage_key)
        return None

    def _validate_upload(self, original_filename: str, content_type: str, content: bytes) -> None:
        if not content:
            raise StorageError("Upload is empty")
        if len(content) > self.max_upload_bytes:
            raise StorageError("Upload exceeds max file size")
        if Path(original_filename).suffix.lower() != ".pdf":
            raise StorageError("Only PDF files are accepted")
        if content_type != "application/pdf":
            raise StorageError("Invalid content type for PDF upload")
        if not content.startswith(PDF_SIGNATURE):
            raise StorageError("File signature is not a PDF")

    def _resolve_storage_key(self, storage_key: str) -> Path:
        if Path(storage_key).name != storage_key:
            raise StorageError("Invalid storage key")
        resolved = (self.upload_root / storage_key).resolve()
        if not resolved.is_relative_to(self.upload_root):
            raise StorageError("Storage path escapes upload root")
        return resolved

    def _display_filename(self, original_filename: str | PathLike[str]) -> str:
        filename = Path(original_filename).name
        cleaned = "".join(char for char in filename if char.isprintable())
        return cleaned[:255] or "upload.pdf"


class S3CompatibleStorageService:
    def __init__(
        self,
        *,
        endpoint_url: str,
        bucket: str,
        region: str,
        access_key_id: str,
        secret_access_key: str,
        cache_root: Path,
        max_upload_bytes: int,
    ) -> None:
        try:
            import boto3
        except ImportError as exc:
            raise StorageError("boto3 is required for S3-compatible storage") from exc
        if not all((endpoint_url, bucket, access_key_id, secret_access_key)):
            raise StorageError("S3-compatible storage credentials are incomplete")
        self.bucket = bucket
        self.max_upload_bytes = max_upload_bytes
        self.cache_root = cache_root.resolve()
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region or "auto",
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
        )

    def save_upload(self, original_filename: str, content_type: str, content: bytes) -> StoredFile:
        return self.save_upload_stream(original_filename, content_type, (content,))

    def save_upload_stream(
        self, original_filename: str, content_type: str, chunks: Iterable[bytes]
    ) -> StoredFile:
        if Path(original_filename).suffix.lower() != ".pdf" or content_type != "application/pdf":
            raise StorageError("Only PDF files are accepted")
        content = b"".join(chunks)
        if not content or not content.startswith(PDF_SIGNATURE):
            raise StorageError("File signature is not a PDF")
        if len(content) > self.max_upload_bytes:
            raise StorageError("Upload exceeds max file size")
        storage_key = f"{uuid4()}.pdf"
        self.client.put_object(
            Bucket=self.bucket,
            Key=storage_key,
            Body=content,
            ContentType="application/pdf",
            ServerSideEncryption="AES256",
        )
        return StoredFile(
            storage_key=storage_key,
            original_filename=Path(original_filename).name,
            content_type=content_type,
            size_bytes=len(content),
        )

    def open_for_parser(self, storage_key: str) -> Path:
        if Path(storage_key).name != storage_key:
            raise StorageError("Invalid storage key")
        target = (self.cache_root / storage_key).resolve()
        if not target.is_relative_to(self.cache_root):
            raise StorageError("Storage path escapes cache root")
        self.client.download_file(self.bucket, storage_key, str(target))
        return target

    def create_download_url(self, storage_key: str, expires_seconds: int = 300) -> str:
        if Path(storage_key).name != storage_key:
            raise StorageError("Invalid storage key")
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": storage_key},
            ExpiresIn=min(max(expires_seconds, 60), 900),
        )


def build_document_storage(
    backend: str,
    upload_root: Path,
    max_upload_bytes: int,
    *,
    s3_endpoint_url: str = "",
    s3_bucket: str = "",
    s3_region: str = "auto",
    s3_access_key_id: str = "",
    s3_secret_access_key: str = "",
) -> DocumentStorage:
    normalized = backend.strip().lower()
    if normalized == "local":
        return LocalStorageService(upload_root, max_upload_bytes=max_upload_bytes)
    if normalized in {"s3", "s3-compatible", "s3_compatible", "minio"}:
        return S3CompatibleStorageService(
            endpoint_url=s3_endpoint_url,
            bucket=s3_bucket,
            region=s3_region,
            access_key_id=s3_access_key_id,
            secret_access_key=s3_secret_access_key,
            cache_root=upload_root,
            max_upload_bytes=max_upload_bytes,
        )
    raise StorageError(f"Unsupported document storage backend: {backend}")
