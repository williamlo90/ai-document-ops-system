from __future__ import annotations

from typing import Protocol


class UploadRejected(ValueError):
    pass


class ScannerUnavailable(RuntimeError):
    pass


class UploadScanner(Protocol):
    def scan(self, content: bytes) -> None: ...


class SignaturePdfScanner:
    def scan(self, content: bytes) -> None:
        if not content.startswith(b"%PDF-"):
            raise UploadRejected("File is not a PDF")
        if b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE" in content:
            raise UploadRejected("File failed malware scan")


class UnavailableClamAvScanner:
    def scan(self, content: bytes) -> None:
        raise ScannerUnavailable("ClamAV scanner is unavailable")


def build_scanner(profile: str) -> UploadScanner:
    if profile == "signature":
        return SignaturePdfScanner()
    if profile == "clamav":
        return UnavailableClamAvScanner()
    raise ScannerUnavailable(f"Unsupported scanner profile: {profile}")
