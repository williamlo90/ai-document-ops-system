"""Offline evaluator baseline: controlled mutations, NOT a provider accuracy benchmark."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import re
from decimal import Decimal
import subprocess
from datetime import datetime, UTC
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.evaluation.invoice import evaluate_invoices, report_to_dict
from app.evaluation.external_holdout import build_external_evaluation_summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    path = ROOT / "examples/benchmark/datasets/invoice_quality_v2/expected.json"
    expected = json.loads(path.read_text(encoding="utf-8"))
    results = {}
    for name in (
        "reference_copy",
        "reordered",
        "wrong_quantity",
        "wrong_uom",
        "missing_provenance",
        "missing_line",
        "extra_line",
    ):
        predictions = deepcopy(expected)
        for record in predictions:
            if name == "reordered":
                record["line_items"].reverse()
            elif name == "wrong_quantity":
                record["line_items"][0]["quantity"] = "99999"
            elif name == "wrong_uom":
                record["line_items"][0]["uom"] = "BOX"
            elif name == "missing_provenance":
                record.pop("provenance")
            elif name == "missing_line":
                record["line_items"].pop()
            elif name == "extra_line":
                record["line_items"].append(deepcopy(record["line_items"][0]))
        report = report_to_dict(evaluate_invoices(expected, predictions))
        results[name] = {
            "header_field_accuracy": report["header_field_accuracy"],
            "full_invoice_exact_match_rate": report["full_invoice_exact_match_rate"],
            "line_field_accuracy": report["line_items"]["field_accuracy"],
            "missing_lines": report["line_items"]["missing_lines"],
            "extra_lines": report["line_items"]["extra_lines"],
        }
        assert report["header_field_accuracy"] == 1
        assert report["full_invoice_exact_match_rate"] == (
            1 if name in {"reference_copy", "reordered"} else 0
        )
    failed = build_external_evaluation_summary(
        expected,
        [
            {
                "document_id": item["document_id"],
                "error": "controlled_timeout",
                "predicted_fields": {},
                "predicted_validation_codes": [],
            }
            for item in expected
        ],
        split="development",
        provider="controlled_fixture",
        dataset_class="developer/AI-assisted synthetic development fixtures",
    )["metrics"]
    assert failed["validation_code_exact_match_rate"] == 0
    assert failed["approval_blocker_accuracy"] == 0
    assert failed["full_invoice_exact_match_rate"] == 0
    results["provider_failure"] = {
        key: failed[key]
        for key in (
            "provider_success_rate",
            "validation_code_exact_match_rate",
            "approval_blocker_accuracy",
            "full_invoice_exact_match_rate",
        )
    }
    replay = replay_corrections(expected, path.parent / "correction-timeline.json")
    result = {
        "report_version": "2.1",
        "contract_version": "2.0.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "worktree_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)),
        "evaluator_sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT / "backend/app/evaluation").glob("*.py")
        },
        "evaluation_input": "controlled_reference_mutations",
        "claim_boundary": "Evaluator regression evidence only; no OCR/AI provider was run.",
        "dataset_id": "invoice_quality_v2",
        "label_version": "2.0",
        "dataset_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "documents": len(expected),
        "lines": sum(len(r["line_items"]) for r in expected),
        "cases": results,
        "correction_replay": replay,
    }
    serialized = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized)


def apply_rule(record: dict, timeline: dict, rule: str) -> dict:
    prediction = deepcopy(record)
    if (
        rule == "decimal_comma_v1"
        and prediction["family_id"] == timeline["family_id"]
        and prediction["layout_family"] == "locale_id"
    ):
        evidence = prediction["line_items"][0]["provenance"]["quantity"]
        if evidence.get("transform") == "decimal_comma_v1" and re.fullmatch(
            r"[+-]?\d+,\d+", evidence["excerpt"]
        ):
            prediction["line_items"][0]["quantity"] = str(
                Decimal(evidence["excerpt"].replace(",", ".")).normalize()
            )
    return prediction


def replay_corrections(expected: list[dict], path: Path) -> dict:
    timeline = json.loads(path.read_text())
    proposal = timeline["original_proposal"]
    original_hash = hashlib.sha256(json.dumps(proposal, sort_keys=True).encode()).hexdigest()
    baseline = report_to_dict(evaluate_invoices(expected, expected))
    outcomes = []
    for revision in timeline["revisions"]:
        prediction = apply_rule(proposal, timeline, revision["rule"])
        oracle = next(r for r in expected if r["document_id"] == prediction["document_id"])
        score = report_to_dict(evaluate_invoices([oracle], [prediction]))
        regression = report_to_dict(
            evaluate_invoices(
                expected, [apply_rule(r, timeline, revision["rule"]) for r in expected]
            )
        )
        outcomes.append(
            {
                **revision,
                "proposal_exact": score["full_invoice_exact_match_rate"],
                "previously_correct_retained": regression["full_invoice_documents_matched"],
                "previously_correct_total": baseline["full_invoice_documents_matched"],
            }
        )
    corrected = deepcopy(proposal)
    corrected["line_items"][0]["quantity"] = timeline["corrected_value"]
    corrected["line_items"][0]["provenance"]["quantity"] = timeline["event"]
    final = report_to_dict(evaluate_invoices([timeline["corrected_oracle"]], [corrected]))
    assert [x["proposal_exact"] for x in outcomes] == [0, 1, 1]
    assert final["full_invoice_exact_match_rate"] == 1
    assert (
        original_hash == hashlib.sha256(json.dumps(proposal, sort_keys=True).encode()).hexdigest()
    )
    return {
        "kind": "controlled_simulation_not_operator_history",
        "timeline_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "original_preserved": True,
        "reviewed_exact": final["full_invoice_exact_match_rate"],
        "revisions": outcomes,
        "holdout_opened": False,
    }


if __name__ == "__main__":
    main()
