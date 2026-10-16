"""Create or score a paired, single-operator Phase 6 time-study worksheet.

The worksheet contains no answers. The operator supplies timings, terminal
read-back evidence, and final invoice fields for both conditions.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.benchmark.datasets import load_evaluation_dataset, records_from_dataset  # noqa: E402
from app.evaluation.invoice import evaluate_invoices  # noqa: E402
from phase6_validate_pack import audit, file_digest, load_json  # noqa: E402
from phase6_end_to_end import independent_readback  # noqa: E402


def verify_terminal(pack, document, condition, outcome, reference):
    """A string reference alone cannot establish a completed accounting outcome."""
    if not isinstance(reference, str):
        return False
    path = Path(reference).resolve()
    if ROOT not in path.parents or "_local_docs" not in path.parts or not path.is_file():
        return False
    proof = load_json(path)
    if (proof.get("document_id") != document.document_id or proof.get("condition") != condition
            or proof.get("manifest_sha256") != file_digest(pack / "manifest.json")):
        return False
    directory = document.source_path.parent
    sources = load_json(directory / "procurement.json")
    if condition == "manual":
        sources = {key: sources["manual_" + key] for key in ("purchase_order", "purchase_receipt")}
    if outcome == "posted_verified":
        return not independent_readback(document.expected_fields, sources, load_json(pack / "erp-profile.json"),
            proof.get("erp_readback", {}), proof.get("ledger_readback", []))
    if outcome != "exception_resolved" or proof.get("erp_readback", {}).get("docstatus") == 1:
        return False
    wanted = next(row for row in load_json(directory / "expected-match.json")
                  if row["document_id"] == document.document_id)["issue_codes"]
    decisions = proof.get("dispositions", [])
    refs = {sources["purchase_order"]["source_id"], sources["purchase_receipt"]["source_id"]}
    return bool(wanted and decisions and refs.issubset(set(proof.get("source_refs", [])))
        and {row.get("code") for row in decisions} == set(wanted)
        and all(row.get("state") == "rejected" and row.get("authorizer") and row.get("reason")
                and row.get("evidence_refs") for row in decisions))


def prepare(pack: Path) -> dict:
    pack = pack.resolve()
    audit(pack, require_sealed=True, inspect_pdf_text=False)
    dataset = load_evaluation_dataset(pack / "time_study")
    if len(dataset.documents) != 20:
        raise ValueError("The paired study requires exactly 20 families")
    pairs = []
    for index, document in enumerate(dataset.documents):
        order = ["manual", "assisted"] if index % 2 == 0 else ["assisted", "manual"]
        procurement = load_json(document.source_path.parent / "procurement.json")
        sources = {condition: {"purchase_order": procurement[("manual_" if condition == "manual" else "") + "purchase_order"]["source_id"],
                              "purchase_receipt": procurement[("manual_" if condition == "manual" else "") + "purchase_receipt"]["source_id"]}
                   for condition in order}
        pairs.append({"document_id": document.document_id,
                      "source_pdf": str(document.source_path.relative_to(pack)).replace("\\", "/"),
                      "condition_order": order,
                      "procurement_sources": sources,
                      "runs": [{"condition": condition, "active_seconds": None,
                                "elapsed_seconds": None, "terminal_outcome": None,
                                "erp_readback_reference": None, "predicted_fields": None,
                                "original_predicted_fields": None,
                                "original_capture_reference": None,
                                "operator_notes": None} for condition in order]})
    return {"protocol_version": "phase6-paired-v1", "created_at": datetime.now(UTC).isoformat(),
            "manifest_sha256": file_digest(pack / "manifest.json"), "operator_id": None,
            "operator_familiarity": None, "pairs": pairs}


def score(pack: Path, worksheet: dict) -> dict:
    pack = pack.resolve()
    audit(pack, require_sealed=True, inspect_pdf_text=False)
    if worksheet.get("protocol_version") != "phase6-paired-v1" or \
            worksheet.get("manifest_sha256") != file_digest(pack / "manifest.json"):
        raise ValueError("Worksheet protocol or frozen manifest differs")
    if not worksheet.get("operator_id") or not worksheet.get("operator_familiarity"):
        raise ValueError("Operator identity and familiarity must be recorded")
    dataset = load_evaluation_dataset(pack / "time_study")
    expected = records_from_dataset(dataset)
    documents_by_id = {document.document_id: document for document in dataset.documents}
    outcomes = {}
    for cohort in load_json(pack / "manifest.json")["cohorts"]:
        if cohort["split"] == "time_study":
            for family in cohort["families"]:
                for posting in load_json(pack / "time_study" / family["family_id"] / "expected-posting.json"):
                    outcomes[posting["document_id"]] = posting["terminal_outcome"]
    pairs = worksheet.get("pairs")
    if not isinstance(pairs, list) or len(pairs) != 20 or \
            [pair.get("document_id") for pair in pairs] != [d.document_id for d in dataset.documents]:
        raise ValueError("All 20 sealed pairs must remain in the denominator")
    predictions = {"manual": [], "assisted": []}
    values = {"manual": [], "assisted": []}
    terminal_correct = {"manual": 0, "assisted": 0}
    original_assisted = []
    invalid = []
    for index, pair in enumerate(pairs):
        document_id = pair["document_id"]
        expected_order = ["manual", "assisted"] if index % 2 == 0 else ["assisted", "manual"]
        if pair.get("condition_order") != expected_order or \
                [run.get("condition") for run in pair.get("runs", [])] != expected_order:
            raise ValueError(f"Counterbalanced order changed for pair {index + 1}")
        for run in pair["runs"]:
            condition = run["condition"]
            active, elapsed = run.get("active_seconds"), run.get("elapsed_seconds")
            if not isinstance(active, (int, float)) or not isinstance(elapsed, (int, float)) \
                    or not math.isfinite(active) or not math.isfinite(elapsed) or active < 0 or elapsed < active:
                invalid.append(f"{document_id}:{condition}:timing")
                continue
            values[condition].append((float(active), float(elapsed)))
            if (run.get("terminal_outcome") == outcomes[document_id]
                    and verify_terminal(pack, documents_by_id[document_id], condition,
                                        run["terminal_outcome"], run.get("erp_readback_reference"))):
                terminal_correct[condition] += 1
            else:
                invalid.append(f"{document_id}:{condition}:terminal_evidence")
            if condition == "assisted":
                if isinstance(run.get("original_predicted_fields"), dict):
                    original_assisted.append({"document_id": document_id, **run["original_predicted_fields"]})
                    reference = run.get("original_capture_reference")
                    if not reference or not Path(reference).is_file():
                        invalid.append(f"{document_id}:assisted:original_capture")
                    else:
                        original = load_json(Path(reference))
                        if (original.get("document_id") != document_id or original.get("condition") != "assisted"
                                or original.get("manifest_sha256") != worksheet["manifest_sha256"]
                                or original.get("original_predicted_fields") != run["original_predicted_fields"]):
                            invalid.append(f"{document_id}:assisted:original_capture_mismatch")
                else:
                    invalid.append(f"{document_id}:assisted:original_extraction")
            if isinstance(run.get("predicted_fields"), dict):
                predictions[condition].append({"document_id": document_id, **run["predicted_fields"]})
                reference = run.get("erp_readback_reference")
                if (not reference or not Path(reference).is_file()
                        or load_json(Path(reference)).get("predicted_fields") != run["predicted_fields"]):
                    invalid.append(f"{document_id}:{condition}:fields_differ_from_capture")
            else:
                invalid.append(f"{document_id}:{condition}:invoice_fields")
    result = {"scope": "single-operator, synthetic/sandbox, paired 20-family study",
              "manifest_sha256": worksheet["manifest_sha256"], "operator_id": worksheet["operator_id"],
              "scheduled_pairs": 20, "invalid_or_incomplete": invalid,
              "conditions": {}}
    for condition in ("manual", "assisted"):
        quality = evaluate_invoices(expected, predictions[condition]).quality
        timings = values[condition]
        result["conditions"][condition] = {
            "timed_runs": len(timings), "terminal_correct": terminal_correct[condition],
            "terminal_denominator": 20, "full_invoice_exact": quality["full_invoice_documents_matched"],
            "full_invoice_denominator": quality["full_invoice_documents_total"],
            "median_active_seconds": statistics.median(row[0] for row in timings) if timings else None,
            "median_elapsed_seconds": statistics.median(row[1] for row in timings) if timings else None}
    result["original_assisted_quality"] = evaluate_invoices(expected, original_assisted).quality
    if (len(values["manual"]) == len(values["assisted"]) == 20 and not invalid
            and all(result["conditions"][c]["full_invoice_exact"] == 20 for c in ("manual", "assisted"))
            and terminal_correct["manual"] == terminal_correct["assisted"] == 20):
        manual = result["conditions"]["manual"]["median_active_seconds"]
        assisted = result["conditions"]["assisted"]["median_active_seconds"]
        result["median_active_reduction"] = (manual - assisted) / manual if manual else None
    else:
        result["median_active_reduction"] = None
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    make = sub.add_parser("prepare")
    make.add_argument("pack", type=Path)
    make.add_argument("--output", type=Path, required=True)
    analyze = sub.add_parser("score")
    analyze.add_argument("pack", type=Path)
    analyze.add_argument("worksheet", type=Path)
    analyze.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to overwrite a study worksheet or report")
    result = prepare(args.pack) if args.action == "prepare" else score(args.pack, load_json(args.worksheet))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"action": args.action, "output": str(args.output),
                      "pairs": len(result.get("pairs", [])),
                      "incomplete": len(result.get("invalid_or_incomplete", []))}, indent=2))


if __name__ == "__main__":
    main()
