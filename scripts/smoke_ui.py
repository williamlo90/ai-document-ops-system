from __future__ import annotations

import http.cookiejar
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path


BASE_URL = "http://127.0.0.1:8000"
ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    admin_token = _admin_token()
    cookies = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
    opener.open(
        urllib.request.Request(
            f"{BASE_URL}/ui/login",
            data=urllib.parse.urlencode({"admin_token": admin_token}).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    )
    upload = opener.open(
        urllib.request.Request(
            f"{BASE_URL}/ui/documents/upload",
            data=_multipart_pdf(),
            headers={"Content-Type": "multipart/form-data; boundary=----codexboundary"},
        )
    )
    upload.read()
    match = re.search(r"document_id=([0-9a-f-]+)", upload.url)
    if match is None:
        raise RuntimeError(f"Upload redirect did not include document_id: {upload.url}")
    document_id = match.group(1)
    opener.open(urllib.request.Request(f"{BASE_URL}/ui/documents/{document_id}/process", data=b""))
    page = opener.open(f"{BASE_URL}/ui?document_id={document_id}").read().decode()
    csv_text = opener.open(f"{BASE_URL}/ui/export").read().decode()
    result = {
        "document_id": document_id,
        "approved_visible": "approved" in page,
        "vendor_visible": "Acme Logistics" in page,
        "csv_contains_document": document_id in csv_text,
    }
    print(result)
    if not all(result[key] for key in result if key != "document_id"):
        raise SystemExit(1)


def _admin_token() -> str:
    token = os.environ.get("APP_ADMIN_TOKEN")
    if token:
        return token
    env_file = Path(os.environ.get("ENV_FILE") or ROOT / ".env")
    if not env_file.is_absolute():
        env_file = ROOT / env_file
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == "APP_ADMIN_TOKEN":
                value = value.strip().strip('"').strip("'")
                if value:
                    return value
    return "test-token"


def _multipart_pdf() -> bytes:
    boundary = "----codexboundary"
    prefix = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="invoice.pdf"\r\n'
        "Content-Type: application/pdf\r\n"
        "\r\n"
    ).encode()
    suffix = f"\r\n--{boundary}--\r\n".encode()
    return prefix + b"%PDF- invoice" + suffix


if __name__ == "__main__":
    main()
