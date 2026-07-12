"""Dependency-free concurrent read smoke test for a running DocOps API.

Usage:
    python scripts/load_smoke.py --base-url http://127.0.0.1:8000 --requests 100 --concurrency 10
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import statistics
import time
import urllib.error
import urllib.request


def request_once(url: str, token: str) -> tuple[int, float]:
    started = time.perf_counter()
    request = urllib.request.Request(
        url,
        headers={"X-Admin-Token": token, "X-User-Id": "load-smoke"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, time.perf_counter() - started
    except urllib.error.HTTPError as error:
        return error.code, time.perf_counter() - started


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--path", default="/backoffice/workspace")
    parser.add_argument("--token", default="123")
    parser.add_argument("--requests", type=int, default=50)
    parser.add_argument("--concurrency", type=int, default=8)
    args = parser.parse_args()

    url = f"{args.base_url.rstrip('/')}{args.path}"
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        results = list(
            executor.map(
                lambda _: request_once(url, args.token),
                range(args.requests),
            )
        )

    statuses = [status for status, _ in results]
    latencies = sorted(elapsed * 1000 for _, elapsed in results)
    failures = sum(status >= 400 for status in statuses)
    report = {
        "requests": len(results),
        "concurrency": args.concurrency,
        "failures": failures,
        "status_counts": {str(status): statuses.count(status) for status in sorted(set(statuses))},
        "latency_ms": {
            "median": round(statistics.median(latencies), 2),
            "p95": round(latencies[max(0, int(len(latencies) * 0.95) - 1)], 2),
            "max": round(max(latencies), 2),
        },
    }
    print(json.dumps(report, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
