from __future__ import annotations

import socket
import struct
from typing import Iterable, Protocol

from app.core.settings import Settings
from app.providers.storage import StorageError


class UploadScanner(Protocol):
    def scan(self, chunks: Iterable[bytes]) -> Iterable[bytes]: ...


class UploadScannerUnavailable(StorageError):
    pass


class SignatureUploadScanner:
    """Local development guard; this is not a production antivirus engine."""

    _blocked = (b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE",)

    def scan(self, chunks: Iterable[bytes]) -> Iterable[bytes]:
        overlap = b""
        for chunk in chunks:
            sample = overlap + chunk
            if any(signature in sample for signature in self._blocked):
                raise StorageError("Upload rejected by malware scanner")
            overlap = sample[-64:]
            yield chunk


class PassthroughUploadScanner:
    def scan(self, chunks: Iterable[bytes]) -> Iterable[bytes]:
        yield from chunks


class ClamAvUploadScanner:
    """Fail-closed ClamAV INSTREAM adapter for untrusted production uploads."""

    _chunk_size = 64 * 1024

    def __init__(
        self,
        *,
        host: str,
        port: int,
        timeout_seconds: float,
        max_upload_bytes: int,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout_seconds = timeout_seconds
        self.max_upload_bytes = max_upload_bytes

    def scan(self, chunks: Iterable[bytes]) -> Iterable[bytes]:
        content = bytearray()
        for chunk in chunks:
            if not chunk:
                continue
            content.extend(chunk)
            if len(content) > self.max_upload_bytes:
                raise StorageError("Upload exceeds max file size")
        if not content:
            raise StorageError("Upload is empty")
        payload = bytes(content)
        self._scan_payload(payload)
        yield payload

    def _scan_payload(self, payload: bytes) -> None:
        try:
            with socket.create_connection(
                (self.host, self.port), timeout=self.timeout_seconds
            ) as connection:
                connection.settimeout(self.timeout_seconds)
                connection.sendall(b"zINSTREAM\0")
                for offset in range(0, len(payload), self._chunk_size):
                    chunk = payload[offset : offset + self._chunk_size]
                    connection.sendall(struct.pack("!I", len(chunk)))
                    connection.sendall(chunk)
                connection.sendall(struct.pack("!I", 0))
                response = _receive_clamav_response(connection)
        except (OSError, TimeoutError) as exc:
            raise UploadScannerUnavailable("Upload scanner is unavailable") from exc
        _require_clean_clamav_response(response)


def build_upload_scanner(settings: Settings) -> UploadScanner:
    if not settings.malware_scanning_enabled:
        return PassthroughUploadScanner()
    backend = settings.malware_scanner_backend.strip().lower()
    if backend == "signature":
        return SignatureUploadScanner()
    if backend == "clamav":
        return ClamAvUploadScanner(
            host=settings.clamav_host,
            port=settings.clamav_port,
            timeout_seconds=settings.clamav_timeout_seconds,
            max_upload_bytes=settings.max_upload_bytes,
        )
    raise ValueError(f"Unsupported malware scanner backend: {settings.malware_scanner_backend}")


def validate_upload_scanning_policy(settings: Settings) -> None:
    backend = settings.malware_scanner_backend.strip().lower()
    if backend not in {"signature", "clamav"}:
        raise ValueError(f"Unsupported malware scanner backend: {settings.malware_scanner_backend}")
    if backend == "clamav" and settings.malware_scanning_enabled:
        if not settings.clamav_host.strip():
            raise ValueError("CLAMAV_HOST is required for ClamAV upload scanning")
        if not 1 <= settings.clamav_port <= 65_535:
            raise ValueError("CLAMAV_PORT must be between 1 and 65535")
        if settings.clamav_timeout_seconds <= 0:
            raise ValueError("CLAMAV_TIMEOUT_SECONDS must be greater than zero")
    if settings.app_env.strip().lower() in {"prod", "production"}:
        if not settings.malware_scanning_enabled or backend != "clamav":
            raise ValueError("Production requires fail-closed ClamAV upload scanning")


def _receive_clamav_response(connection: socket.socket) -> bytes:
    response = bytearray()
    while len(response) < 4096:
        chunk = connection.recv(1024)
        if not chunk:
            break
        response.extend(chunk)
        if b"\0" in chunk or b"\n" in chunk:
            break
    if not response:
        raise UploadScannerUnavailable("Upload scanner returned no result")
    return bytes(response).split(b"\0", 1)[0].strip()


def _require_clean_clamav_response(response: bytes) -> None:
    if response.endswith(b" OK"):
        return
    if response.endswith(b" FOUND"):
        raise StorageError("Upload rejected by malware scanner")
    raise UploadScannerUnavailable("Upload scanner could not verify the file")
