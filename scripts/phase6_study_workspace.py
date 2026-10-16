"""Prepare or serve the isolated human study; preparation never extracts a study invoice."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Thread

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]

from app.core.security import SecurityContext  # noqa: E402
from app.core.settings import load_settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.procurement.matching import MatchService  # noqa: E402
from app.procurement.models import ERPPostingProfile, Mapping, MatchPolicy, Policy  # noqa: E402
from app.api.procurement import posting_service  # noqa: E402
from phase6_provider_run import bounded_post, BoundedExtractor, RateAwareParser  # noqa: E402
from phase6_validate_pack import audit, file_digest, load_json  # noqa: E402


def study_settings(directory):
    return replace(load_settings(), app_env="local", workspace_id="phase6-human-study",
        storage_backend="sqlite", database_url=None, sqlite_path=directory / "study.db",
        upload_root=directory / "uploads", document_storage_backend="local",
        processing_queue_backend="memory", max_processing_attempts=1)


def build_study(pack: Path, directory: Path, *, initialize=False):
    pack, directory = pack.resolve(), directory.resolve()
    if ROOT not in directory.parents or "_local_docs" not in directory.parts:
        raise ValueError("Study workspace must remain in ignored local storage")
    audit(pack, require_sealed=True, inspect_pdf_text=False)
    binding = directory / "binding.json"
    expected = {"manifest_sha256": file_digest(pack / "manifest.json"), "pack": str(pack)}
    if initialize:
        directory.mkdir(parents=True, exist_ok=False)
        binding.write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
    elif load_json(binding) != expected or not (directory / "study.db").exists():
        raise ValueError("Study workspace is not bound to this sealed cohort")
    app = create_app(study_settings(directory))
    container = app.state.container
    # The same bounded extraction budget applies to human-assisted inputs.
    extractor = container.processing_service.extractor
    container.processing_service.extractor = BoundedExtractor(replace(extractor, post_json=bounded_post(extractor.post_json)))
    container.processing_service.parser = RateAwareParser(container.processing_service.parser)
    if initialize:
        try:
            profile = load_json(pack / "erp-profile.json")
            context = SecurityContext("Study setup", is_admin=True, workspace_id=container.settings.workspace_id)
            evidence = container.ap_service
            evidence.configure("mapping", Mapping(company=profile["company"],
                supplier_aliases=profile["supplier_ids"], item_mappings=profile["item_codes"],
                reason="Verified study sandbox master data"), context)
            evidence.configure("policy", Policy(company=profile["company"], currency="USD",
                reason="Frozen study same-currency evidence policy"), context)
            MatchService(evidence).configure_policy(MatchPolicy(company=profile["company"],
                effective_from=datetime(2026, 1, 1, tzinfo=UTC), mode="ordered",
                reason="Frozen exact quantity and price study rule"), context)
            posting_service(container).configure_profile(ERPPostingProfile.model_validate(profile), context)
            cohort = next(c for c in load_json(pack / "manifest.json")["cohorts"] if c["split"] == "time_study")
            for family in cohort["families"]:
                source = load_json(pack / "time_study" / family["family_id"] / "procurement.json")
                evidence.import_records([source["purchase_order"], source["purchase_receipt"]], context)
                inputs = directory / "inputs"
                inputs.mkdir(exist_ok=True)
                # Rename copies for upload identity without opening or extracting study PDFs.
                for label in load_json(pack / "time_study" / family["family_id"] / "invoice-labels.json"):
                    shutil.copyfile(pack / "time_study" / family["family_id"] / "invoice.pdf",
                                    inputs / (label["document_id"] + ".pdf"))
        finally:
            container.close()
    return app


def serve(app, port):
    import uvicorn
    original = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        stop = Event()
        def work():
            while not stop.is_set():
                application.state.container.document_module.queue_worker_service.run_once(max_wait_seconds=1)
        async with original(application):
            worker = Thread(target=work, name="human-study-worker", daemon=True)
            worker.start()
            try:
                yield
            finally:
                stop.set()
                worker.join(timeout=180)
    app.router.lifespan_context = lifespan
    uvicorn.run(app, host="127.0.0.1", port=port)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "serve", "check"))
    parser.add_argument("pack", type=Path)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    app = build_study(args.pack, args.workspace, initialize=args.action == "prepare")
    if args.action == "serve":
        serve(app, args.port)
    elif args.action == "check":
        from fastapi.testclient import TestClient
        with TestClient(app) as client:
            response = client.get("/ready")
            response.raise_for_status()
            print(json.dumps(response.json()))
    else:
        print("Study workspace prepared; no study PDFs processed and no timers started.")


if __name__ == "__main__":
    main()
