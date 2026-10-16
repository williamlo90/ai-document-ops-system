"""Bounded development-only API/queue/worker profiling with real configured providers."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]

from fastapi.testclient import TestClient  # noqa: E402
from app.benchmark.datasets import load_evaluation_dataset  # noqa: E402
from app.core.settings import load_settings  # noqa: E402
from app.main import create_app  # noqa: E402
from phase6_provider_run import _percentile, bounded_post, BoundedExtractor, RateAwareParser  # noqa: E402
from phase6_validate_pack import audit, file_digest, load_json  # noqa: E402
from phase6_provider_run import config_fingerprint  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-documents", type=int, default=3)
    args = parser.parse_args()
    if args.output.exists() or not 1 <= args.max_documents <= 10:
        raise SystemExit("Refusing to overwrite or exceed the bounded diagnostic")
    audit(args.pack, inspect_pdf_text=False)
    dataset = load_evaluation_dataset(args.pack / "development")
    observations = []
    started_at = datetime.now(UTC).isoformat()
    with tempfile.TemporaryDirectory() as temporary:
        token = uuid4().hex
        settings = replace(
            load_settings(),
            app_env="test",
            admin_token=token,
            upload_root=Path(temporary) / "uploads",
            sqlite_path=Path(temporary) / "profile.db",
            storage_backend="sqlite",
            document_storage_backend="local",
            processing_queue_backend="memory",
            max_processing_attempts=1,
            accounting_provider="mock",
            accounting_sandbox_mode=True,
        )
        app = create_app(settings)
        service = app.state.container.processing_service
        service.parser = RateAwareParser(service.parser)
        service.extractor = BoundedExtractor(
            replace(service.extractor, post_json=bounded_post(service.extractor.post_json))
        )
        try:
            client = TestClient(app)
            container = app.state.container
            headers = {"X-Access-Token": token}
            for document in dataset.documents[: args.max_documents]:
                row = {}
                tick = time.perf_counter()
                response = client.post(
                    "/documents/upload",
                    headers=headers,
                    files={
                        "file": (
                            document.source_path.name,
                            document.source_path.read_bytes(),
                            "application/pdf",
                        )
                    },
                )
                row["api_upload_ms"] = round((time.perf_counter() - tick) * 1000, 2)
                row["api_upload_status"] = response.status_code
                if response.status_code == 200:
                    payload = response.json()
                    job_id = UUID(payload["job"]["id"])
                    tick = time.perf_counter()
                    container.document_module.queue_worker_service.run_once(max_wait_seconds=0)
                    row["worker_ms"] = round((time.perf_counter() - tick) * 1000, 2)
                    job = container.jobs.get(job_id)
                    row.update(
                        job_status=str(job.status),
                        attempt_count=job.attempt_count,
                        queue_wait_ms=round(
                            (job.started_at - job.created_at).total_seconds() * 1000, 2
                        )
                        if job.started_at
                        else None,
                    )
                    tick = time.perf_counter()
                    detail = client.get(f"/documents/{payload['document']['id']}", headers=headers)
                    row["api_detail_ms"] = round((time.perf_counter() - tick) * 1000, 2)
                    row["api_detail_status"] = detail.status_code
                observations.append(row)
        finally:
            app.state.container.close()
    report = {
        "scope": "development PDFs; in-process FastAPI TestClient + SQLite + memory queue + real OCR/extractor; no ERP writes",
        "manifest_sha256": file_digest(args.pack / "manifest.json"),
        "freeze": load_json(args.pack / "manifest.json").get("freeze"),
        "config_sha256": config_fingerprint(load_settings()),
        "started_at": started_at,
        "completed_at": datetime.now(UTC).isoformat(),
        "scheduled": args.max_documents,
        "observations": observations,
        "limitations": [
            "Small bounded local sample; API times exclude socket/network overhead.",
            "Queue wait reflects immediate local consumption and is not a production SLO.",
        ],
    }
    report["latency_ms"] = {}
    for stage in ("api_upload", "api_detail", "worker", "queue_wait"):
        values = [row[stage + "_ms"] for row in observations if row.get(stage + "_ms") is not None]
        report["latency_ms"][stage] = {
            "N": len(values),
            **{f"p{p}_ms": _percentile(values, p) for p in (50, 90, 95)},
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["latency_ms"], indent=2))


if __name__ == "__main__":
    main()
