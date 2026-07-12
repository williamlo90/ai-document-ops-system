from __future__ import annotations

import http.cookiejar
import os
import urllib.parse
import urllib.request


BASE_URL = os.getenv("DOC_INTEL_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def main() -> None:
    admin_token = _admin_token()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )
    _get(opener, "/ui")
    _post(opener, "/ui/login", {"admin_token": admin_token})
    page = _get(opener, "/ui/benchmarks?run=true")

    required = (
        "Document AI evaluation lab",
        "Provider ranking",
        "Recent runs",
        "Decision",
        "Decision score",
        "Mock mode does not call paid provider APIs",
        "<dt>Mode</dt><dd>mock</dd>",
        "Known limitations",
        "mock_parser + mock_extractor",
    )
    missing = [text for text in required if text not in page]
    if "Failure details" not in page and "No field mismatches in this run." not in page:
        missing.append("Failure details or no-mismatch state")
    if missing:
        raise SystemExit(f"Benchmark UI smoke test failed. Missing: {', '.join(missing)}")
    print("Benchmark UI smoke test passed.")


def _get(opener: urllib.request.OpenerDirector, path: str) -> str:
    with opener.open(f"{BASE_URL}{path}", timeout=10) as response:
        return response.read().decode("utf-8", errors="replace")


def _post(opener: urllib.request.OpenerDirector, path: str, form: dict[str, str]) -> str:
    data = urllib.parse.urlencode(form).encode("utf-8")
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with opener.open(request, timeout=10) as response:
        return response.read().decode("utf-8", errors="replace")


def _admin_token() -> str:
    return (
        os.getenv("DOC_INTEL_ADMIN_TOKEN")
        or os.getenv("APP_ADMIN_TOKEN")
        or _env_file_value("APP_ADMIN_TOKEN")
        or "change-me-for-local-demo"
    )


def _env_file_value(key: str) -> str | None:
    for filename in (".env", ".env.example"):
        if not os.path.exists(filename):
            continue
        with open(filename, "r", encoding="utf-8") as file:
            for raw_line in file:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, value = line.split("=", 1)
                if name.strip() == key:
                    return value.strip().strip("'\"")
    return None


if __name__ == "__main__":
    main()
