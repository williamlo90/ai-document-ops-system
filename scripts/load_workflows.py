"""Concurrent smoke/load coverage for the four critical workflow surfaces.

Runs against an isolated or local stack; it creates test records.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
from collections import Counter

import httpx


PDF = b"%PDF-1.4\nload-smoke\n%%EOF"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--token", default="123")
    parser.add_argument("--documents", type=int, default=8)
    parser.add_argument("--concurrency", type=int, default=4)
    args = parser.parse_args()
    headers = {"X-Admin-Token": args.token, "X-User-Id": "load-verifier"}

    def upload(index: int) -> tuple[int, str | None]:
        with httpx.Client(base_url=args.base_url, headers=headers, timeout=30) as client:
            response = client.post(
                "/documents/upload",
                files={"file": (f"load-{index}.pdf", PDF, "application/pdf")},
            )
            body = (
                response.json()
                if response.headers.get("content-type", "").startswith("application/json")
                else {}
            )
            return response.status_code, body.get("document", {}).get("id")

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        uploads = list(pool.map(upload, range(args.documents)))
    document_ids = [document_id for status, document_id in uploads if status == 200 and document_id]

    def process(document_id: str) -> int:
        with httpx.Client(base_url=args.base_url, headers=headers, timeout=30) as client:
            return client.post(f"/documents/{document_id}/process").status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        process_statuses = list(pool.map(process, document_ids))

    with httpx.Client(base_url=args.base_url, headers=headers, timeout=30) as client:
        first_page = client.get("/invoices", params={"page": 1, "page_size": 3})
        second_page = client.get("/invoices", params={"page": 2, "page_size": 3})
        pagination_ok = (
            first_page.status_code == 200
            and second_page.status_code == 200
            and not {item["id"] for item in first_page.json()["items"]}.intersection(
                item["id"] for item in second_page.json()["items"]
            )
        )

        approval_statuses: list[int] = []
        if document_ids:
            created = client.post(
                "/backoffice/work-items",
                json={
                    "title": "Load-test approval",
                    "work_type": "invoice_export",
                    "linked_document_ids": [document_ids[0]],
                    "requested_outcome": "export invoice",
                },
            ).json()["work_item"]
            planned = client.post(
                f"/backoffice/work-items/{created['id']}/plan",
                json={"requested_outcome": "export invoice"},
            ).json()["work_item"]
            if planned["approvals"]:
                approval_id = planned["approvals"][0]["id"]

                def approve(index: int) -> int:
                    with httpx.Client(
                        base_url=args.base_url, headers=headers, timeout=30
                    ) as concurrent_client:
                        return concurrent_client.post(
                            f"/backoffice/approvals/{approval_id}/approve",
                            json={"notes": f"Concurrent approval {index}"},
                        ).status_code

                with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
                    approval_statuses = list(pool.map(approve, range(args.concurrency)))

    passed = (
        len(document_ids) == args.documents
        and all(status == 200 for status in process_statuses)
        and pagination_ok
        and (
            not approval_statuses
            or (
                approval_statuses.count(200) >= 1
                and all(status in {200, 409} for status in approval_statuses)
            )
        )
    )
    print(
        json.dumps(
            {
                "passed": passed,
                "uploads": dict(Counter(status for status, _ in uploads)),
                "queue_processing": dict(Counter(process_statuses)),
                "pagination": pagination_ok,
                "concurrent_approvals": dict(Counter(approval_statuses)),
            },
            indent=2,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
