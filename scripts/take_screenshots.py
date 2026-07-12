from __future__ import annotations

import asyncio
import csv
import os
from pathlib import Path
from io import StringIO
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
SCREENSHOTS = ROOT / "docs" / "assets" / "screenshots"
BASE_URL = os.environ.get("DOC_INTEL_BASE_URL", "http://127.0.0.1:8000")
SAMPLE_PDF = ROOT / "sample_invoice.pdf"


async def main() -> None:
    from playwright.async_api import async_playwright

    admin_token = _admin_token()
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        await page.goto(f"{BASE_URL}/ui", wait_until="networkidle")
        await page.screenshot(path=str(SCREENSHOTS / "01-login.png"), full_page=True)
        print("01-login.png captured")

        await page.fill('input[name="admin_token"]', admin_token)
        await page.click('button[type="submit"]')
        await page.wait_for_load_state("networkidle")
        await page.screenshot(path=str(SCREENSHOTS / "02-dashboard.png"), full_page=True)
        print("02-dashboard.png captured")

        await page.set_input_files('input[name="file"]', str(SAMPLE_PDF))
        await page.click('form[action="/ui/documents/upload"] button[type="submit"]')
        await page.wait_for_url("**/ui?document_id=**")
        document_id = _document_id_from_url(page.url)

        await page.click(
            f'form[action="/ui/documents/{document_id}/process"] button[type="submit"]'
        )
        await page.wait_for_url("**message=Processed")
        await page.screenshot(path=str(SCREENSHOTS / "03-processed-detail.png"), full_page=True)
        print("03-processed-detail.png captured")

        preview_check = await page.evaluate(
            """
            async (documentId) => {
              const response = await fetch(`/ui/documents/${documentId}/preview`);
              const bytes = new Uint8Array(await response.arrayBuffer()).slice(0, 5);
              return {
                ok: response.ok,
                contentType: response.headers.get("content-type") || "",
                signature: String.fromCharCode(...bytes),
              };
            }
            """,
            document_id,
        )
        if (
            not preview_check["ok"]
            or "application/pdf" not in preview_check["contentType"]
            or not preview_check["signature"].startswith("%PDF-")
        ):
            raise RuntimeError(f"PDF preview check failed: {preview_check}")
        await page.locator(".preview-pane").screenshot(path=str(SCREENSHOTS / "04-pdf-preview.png"))
        print("04-pdf-preview.png captured")

        await page.goto(f"{BASE_URL}/ui?document_id={document_id}", wait_until="networkidle")
        csv_result = await page.evaluate(
            """
            async () => {
              const response = await fetch('/ui/export');
              return {
                ok: response.ok,
                contentType: response.headers.get("content-type") || "",
                text: await response.text(),
              };
            }
            """
        )
        if not csv_result["ok"] or "text/csv" not in csv_result["contentType"]:
            raise RuntimeError(f"CSV export check failed: {csv_result['contentType']}")
        csv_path = SCREENSHOTS / "05-export.csv"
        csv_path.write_text(
            _current_document_csv(csv_result["text"], document_id), encoding="utf-8"
        )
        print(f"05-export.csv downloaded ({csv_path.stat().st_size} bytes)")

        await page.goto(f"{BASE_URL}/ui?document_id={document_id}", wait_until="networkidle")
        await page.screenshot(path=str(SCREENSHOTS / "05-dashboard-export.png"), full_page=True)
        print("05-dashboard-export.png captured")

        await browser.close()

    print("All screenshots captured")


def _document_id_from_url(url: str) -> str:
    parsed = urlparse(url)
    values = parse_qs(parsed.query).get("document_id")
    if not values:
        raise RuntimeError(f"Upload redirect did not include document_id: {url}")
    return values[0]


def _current_document_csv(csv_text: str, document_id: str) -> str:
    reader = csv.DictReader(StringIO(csv_text))
    rows = [row for row in reader if row.get("document_id") == document_id]
    if not rows:
        raise RuntimeError(f"CSV export did not include current document: {document_id}")
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=reader.fieldnames or [])
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _admin_token() -> str:
    token = os.environ.get("APP_ADMIN_TOKEN")
    if token:
        return token
    env_file = Path(os.environ.get("ENV_FILE") or ROOT / ".env.example")
    if not env_file.is_absolute():
        env_file = ROOT / env_file
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == "APP_ADMIN_TOKEN":
                value = value.strip().strip('"').strip("'")
                if value:
                    return value
    return "123"


if __name__ == "__main__":
    asyncio.run(main())
