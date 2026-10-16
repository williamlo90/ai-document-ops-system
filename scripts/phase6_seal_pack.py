"""Seal a complete local Phase 6 pack with reproducible source and oracle hashes.

This is a one-way operation: a sealed pack is never modified or resealed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.settings import load_settings  # noqa: E402
from app.providers.llm_json import extraction_prompt_sha256  # noqa: E402
from phase6_provider_run import SOURCE_FILES, config_fingerprint  # noqa: E402
from phase6_validate_pack import audit, file_digest, load_json  # noqa: E402

FROZEN_FILES = sorted(
    set(
        SOURCE_FILES
        + [
            "scripts/phase6_generate_synthetic_pack.py",
            "scripts/phase6_seal_pack.py",
            "scripts/phase6_reference_match.py",
            "scripts/phase6_replay_revisions.py",
            "scripts/phase6_time_study.py",
            "backend/app/procurement/matching.py",
            "backend/app/procurement/service.py",
            "backend/app/procurement/posting.py",
            "backend/app/procurement/erpnext.py",
            "docs/evidence/invoice-review-v2/manifest.schema.json",
        ]
        + [
            str(path.relative_to(ROOT)).replace("\\", "/")
            for path in (ROOT / "backend/app").rglob("*.py")
        ]
        + [
            str(path.relative_to(ROOT)).replace("\\", "/")
            for path in (ROOT / "scripts").glob("phase6_*.py")
        ]
        + [
            str(path.relative_to(ROOT)).replace("\\", "/")
            for path in (ROOT / "frontend/src").rglob("*")
            if path.suffix in {".tsx", ".ts", ".css"}
        ]
    )
)


def oracle_hash(pack: Path) -> str:
    digest = hashlib.sha256()
    for relative in (
        "erp-profile.json",
        "erp-provision-journal.json",
        "erp-environment.json",
        "lineage.json",
    ):
        if (pack / relative).exists():
            digest.update(f"{relative}\0{file_digest(pack / relative)}\n".encode())
    manifest = load_json(pack / "manifest.json")
    for cohort in sorted(manifest["cohorts"], key=lambda item: item["split"]):
        split = cohort["split"]
        path = pack / split / "expected.json"
        digest.update(f"{split}/expected.json\0{file_digest(path)}\n".encode())
        for family in sorted(cohort["families"], key=lambda item: item["family_id"]):
            for artifact in sorted(family["artifacts"], key=lambda item: item["path"]):
                digest.update(f"{artifact['path']}\0{artifact['sha256']}\n".encode())
    return digest.hexdigest()


def seal(pack: Path) -> dict:
    pack = pack.resolve()
    if ROOT not in pack.parents or "_local_docs" not in pack.parts:
        raise ValueError("Only an ignored local Phase 6 pack may be sealed")
    if (pack / "freeze-details.json").exists():
        raise ValueError("Pack already has freeze details")
    report = audit(pack, inspect_pdf_text=True)
    if report["status"] != "planned":
        raise ValueError("Only a planned pack may be sealed once")
    for split, expected in (("development", 60), ("quality_holdout", 40), ("time_study", 20)):
        if report["cohorts"][split]["families"] != expected:
            raise ValueError(f"Incomplete {split} cohort")
    quality = report["cohorts"]["quality_holdout"]
    if (
        any(
            quality["category_positives"].get(key, 0) < 10
            for key in ("quantity", "price", "duplicate", "receipt")
        )
        or quality["clean_ready"] < 10
        or quality["eligible"] < 10
    ):
        raise ValueError("Quality holdout coverage is below the frozen contract")
    time_study = report["cohorts"]["time_study"]
    if time_study["eligible"] < 10 or time_study["invoices"] - time_study["eligible"] < 10:
        raise ValueError("Time-study terminal outcome coverage is incomplete")
    if report["cohorts"]["development"]["rule_revisions"] < 3:
        raise ValueError("Three dated development revisions are required")
    profile = load_json(pack / "erp-profile.json")
    journal = load_json(pack / "erp-provision-journal.json")["families"]
    for cohort in load_json(pack / "manifest.json")["cohorts"]:
        if cohort["split"] == "development":
            continue
        for family in cohort["families"]:
            family_id = family["family_id"]
            sources = load_json(pack / cohort["split"] / family_id / "procurement.json")
            for condition in (
                ("quality",) if cohort["split"] == "quality_holdout" else ("assisted", "manual")
            ):
                prefix = "manual_" if condition == "manual" else ""
                for key, kind in (("po", "purchase_order"), ("receipt", "purchase_receipt")):
                    if (
                        journal.get(family_id, {}).get(condition, {}).get(key)
                        != sources[prefix + kind]["source_id"]
                    ):
                        raise ValueError("Complete ERP source bindings are required before seal")
            if sources["purchase_order"]["supplier_id"] not in profile["supplier_ids"]:
                raise ValueError("ERP supplier profile is incomplete")
    settings = load_settings()
    if settings.parser_provider != "ocr_space" or settings.extractor_provider != "llm_json":
        raise ValueError("Unexpected model providers")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()
    if len(head) != 40:
        raise ValueError("No valid base commit")
    source_hashes = {path: file_digest(ROOT / path) for path in FROZEN_FILES}
    frozen_at = datetime.now(UTC).isoformat()
    freeze = {
        "commit": head,
        "sealed_at": frozen_at,
        "model_version": f"ocr_space:engine{settings.ocr_space_engine};llm_json:{settings.extractor_model}",
        "prompt_sha256": extraction_prompt_sha256(),
        "config_sha256": config_fingerprint(settings),
        "evaluator_version": "2.1",
        "oracle_sha256": oracle_hash(pack),
    }
    manifest = load_json(pack / "manifest.json")
    manifest["status"] = "sealed"
    manifest["freeze"] = freeze
    manifest_bytes = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
    details = {
        "freeze": freeze,
        "source_hashes": source_hashes,
        "code_snapshot_sha256": hashlib.sha256(
            json.dumps(source_hashes, sort_keys=True).encode()
        ).hexdigest(),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "note": "Frozen source hashes include uncommitted Phase 6 files; commit refers to Phase 5 base.",
    }
    # Write details first; the manifest is the final state transition. Any write failure
    # leaves a planned manifest that the audit refuses to treat as sealed.
    (pack / "freeze-details.json").write_bytes(
        (json.dumps(details, indent=2) + "\n").encode("utf-8")
    )
    (pack / "manifest.json").write_bytes(manifest_bytes)
    audit(pack, require_sealed=True, inspect_pdf_text=False)
    return {
        "status": "sealed",
        "cohorts": report["cohorts"],
        "oracle_sha256": freeze["oracle_sha256"],
        "prompt_sha256": freeze["prompt_sha256"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack", type=Path)
    args = parser.parse_args()
    print(json.dumps(seal(args.pack), indent=2))


if __name__ == "__main__":
    main()
