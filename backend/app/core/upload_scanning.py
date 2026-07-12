from __future__ import annotations

from typing import Iterable, Protocol

from app.providers.storage import StorageError


class UploadScanner(Protocol):
    def scan(self, chunks: Iterable[bytes]) -> Iterable[bytes]: ...


class SignatureUploadScanner:
    """Streaming scanner boundary, replaceable by ClamAV or a managed scanner."""

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
