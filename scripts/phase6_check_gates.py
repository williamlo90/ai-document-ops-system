"""Check frozen Phase 6 technical gates; human timing remains a separate pending gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def check(summary, revisions):
    metrics, pipeline = summary["metrics"], summary["pipeline"]
    gates = {}

    def minimum(name, value, target):
        gates[name] = {
            "value": value,
            "target_min": target,
            "passed": value is not None and value >= target,
        }

    def maximum(name, value, target):
        gates[name] = {
            "value": value,
            "target_max": target,
            "passed": value is not None and value <= target,
        }

    def ratio(pair):
        return pair["numerator"] / pair["denominator"] if pair["denominator"] else None

    minimum("whole_invoice_exact", metrics["full_invoice_exact_match_rate"], 0.90)
    minimum("processing_completion", metrics["provider_success_rate"], 0.95)
    minimum("validation_completion", metrics["validation_completion_rate"], 0.95)
    minimum("validation_exact", metrics["validation_code_exact_match_rate"], 0.95)
    for category, matrix in pipeline["category_matrices"].items():
        n = matrix["TP"] + matrix["FN"]
        minimum(category + "_recall", matrix["TP"] / n if n else None, 0.95)
    minimum("duplicate_pair_precision", metrics["duplicate_detection"]["precision"], 0.95)
    maximum("false_holds", ratio(pipeline["false_holds"]), 0.05)
    maximum("unsafe_ready", ratio(pipeline["unsafe_ready"]), 0)
    maximum("unsafe_submit", pipeline["unsafe_submit"], 0)
    minimum("posting_correctness", pipeline["posting_correctness"], 1)
    minimum("eligible_posting_completion", ratio(pipeline["eligible_posting_completion"]), 0.95)
    maximum("duplicate_erp_effects", pipeline["duplicate_erp_effects"], 0)
    n = pipeline["scheduled"]
    minimum(
        "resolved_end_to_end_completion",
        pipeline["strict_correct_terminal"] / n if n else None,
        0.95,
    )
    gates["revision_recovery"] = {
        "passed": revisions["scheduled"] >= 3
        and revisions["correct"] == revisions["scheduled"]
        and all(
            row["posting_verification"].get("independently_verified")
            and row["posting_verification"].get("erp_target_count") == 1
            for row in revisions["revisions"]
        )
    }
    gates["regression_retention"] = {
        "passed": bool(revisions["cumulative_regression"])
        and all(
            row["unaffected_retained"] == row["unaffected_scheduled"]
            for row in revisions["cumulative_regression"]
        )
    }
    gates["restart_idempotency"] = {
        "passed": pipeline["submitted_readbacks"] > 0
        and pipeline["restart_replay_same_target"] == pipeline["submitted_readbacks"]
    }
    return {
        "contract_version": "2.0.0",
        "evaluator_version": summary["report_version"],
        "manifest_sha256": summary["manifest_sha256"],
        "completed_at": summary["completed_at"],
        "technical_gates_passed": summary["run_status"] == "completed"
        and all(row["passed"] for row in gates.values()),
        "gates": gates,
        "human_study": "pending_operator",
        "phase_complete": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary", type=Path)
    parser.add_argument("revisions", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to overwrite gate evidence")
    result = check(json.loads(args.summary.read_text()), json.loads(args.revisions.read_text()))
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
