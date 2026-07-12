from __future__ import annotations

import asyncio
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCREENSHOTS = ROOT / "docs" / "assets" / "screenshots"
BASE_URL = os.environ.get("DOC_INTEL_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


async def main() -> None:
    from playwright.async_api import async_playwright

    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    admin_token = _admin_token()

    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="msedge", headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        await page.goto(f"{BASE_URL}/ui", wait_until="networkidle")
        await page.fill('input[name="admin_token"]', admin_token)
        await page.click('button[type="submit"]')
        await page.wait_for_load_state("networkidle")

        await page.goto(
            f"{BASE_URL}/ui/benchmarks?dataset=pdf_sample&provider=mock&run=true",
            wait_until="networkidle",
        )
        await page.screenshot(
            path=str(SCREENSHOTS / "benchmark-decision-view.png"),
            full_page=True,
        )
        await browser.close()

    print(f"Saved {SCREENSHOTS / 'benchmark-decision-view.png'}")


def _admin_token() -> str:
    return (
        os.environ.get("DOC_INTEL_ADMIN_TOKEN")
        or os.environ.get("APP_ADMIN_TOKEN")
        or _env_file_value("APP_ADMIN_TOKEN")
        or "change-me-for-local-demo"
    )


def _env_file_value(key: str) -> str | None:
    for filename in (".env", ".env.example"):
        path = ROOT / filename
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            if name.strip() == key:
                return value.strip().strip("'\"")
    return None


if __name__ == "__main__":
    asyncio.run(main())
