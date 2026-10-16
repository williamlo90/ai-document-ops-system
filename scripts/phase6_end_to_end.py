"""One-pass PDF/provider/AP approval/ERP sandbox evaluation with independent scoring.

Synthetic test identities attest only provider anchors present in the OCR source;
they do not correct values or inspect oracle answers before an action. This is a
local service harness, distinct from the later human operator study.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]

from app.benchmark.datasets import load_evaluation_dataset, records_from_dataset  # noqa: E402
from app.core.security import SecurityContext  # noqa: E402
from app.core.settings import load_settings  # noqa: E402
from app.documents.models import DocumentRecord  # noqa: E402
from app.documents.sqlite_repositories import SqliteDocumentRepository, SqliteExtractionRepository  # noqa: E402
from app.documents.sqlite_store import SqliteStore  # noqa: E402
from app.evaluation.external_holdout import build_external_evaluation_summary  # noqa: E402
from app.evaluation.invoice import evaluate_invoices  # noqa: E402
from app.extraction.schemas import InvoiceExtraction  # noqa: E402
from app.integrations.erpnext_client import ERPNextClient  # noqa: E402
from app.procurement.matching import MatchService  # noqa: E402
from app.procurement.exceptions import ExceptionService  # noqa: E402
from app.procurement.models import ExceptionUpdate  # noqa: E402
from app.procurement.models import (
    EvidenceUpdate,
    FieldEvidence,
    Mapping,
    MatchPolicy,
    Policy,
    SnapshotInput,
    ERPPostingProfile,
)  # noqa: E402
from app.procurement.posting import PostingService  # noqa: E402
from app.procurement.repository import VersionRepository  # noqa: E402
from app.procurement.service import EvidenceService  # noqa: E402
from app.providers.contracts import ExtractionResult  # noqa: E402
from app.providers.factory import build_parser_provider, build_extractor_provider  # noqa: E402
from app.providers.llm_json import _invoice_data  # noqa: E402
from app.validation.invoice import validate_invoice  # noqa: E402
from phase6_provider_run import (
    run_document,
    bounded_post,
    write_json,
    _percentile,
    latency_summary,
    RateAwareParser,
)  # noqa: E402
from phase6_provider_run import BoundedExtractor  # noqa: E402
from phase6_provider_run import physical_ocr_attempts  # noqa: E402
from phase6_reference_match import CATEGORY_CODES  # noqa: E402
from phase6_validate_pack import audit, file_digest, load_json  # noqa: E402


def independent_readback(label, source, profile, actual, ledger) -> list[str]:
    """Compare ERP output directly with authored invoice/source labels, not app payloads."""
    errors = []
    supplier = source["purchase_order"].get("supplier_id", label["vendor_name"])
    text = {
        "company": profile["erp_company"],
        "supplier": profile.get("supplier_ids", {}).get(supplier, supplier),
        "bill_no": label["invoice_number"],
        "bill_date": label["invoice_date"],
        "posting_date": label["invoice_date"],
        "due_date": label["due_date"],
        "currency": label["currency"],
        "credit_to": profile["payable_accounts"][label["currency"]],
    }
    for field, value in text.items():
        if str(actual.get(field)) != str(value):
            errors.append(field)
    if actual.get("docstatus") != 1:
        errors.append("docstatus")
    for field, value in (
        ("net_total", label["subtotal"]),
        ("grand_total", label["total"]),
        ("conversion_rate", "1"),
        ("total_taxes_and_charges", label["tax"]),
    ):
        if Decimal(str(actual.get(field, "NaN"))) != Decimal(value):
            errors.append(field)
    lines = actual.get("items", [])
    if len(lines) != len(label["line_items"]):
        errors.append("line_count")
    else:
        for line, wanted in zip(lines, label["line_items"], strict=True):
            po, pr = source["purchase_order"], source["purchase_receipt"]
            for field, value in {
                "item_code": wanted["description"],
                "description": wanted["description"],
                "uom": wanted["uom"],
                "purchase_order": po["source_id"],
                "po_detail": po["lines"][0]["source_line_id"],
                "purchase_receipt": pr["source_id"],
                "pr_detail": pr["lines"][0]["source_line_id"],
                "expense_account": profile["expense_accounts"][wanted["description"]],
            }.items():
                if line.get(field) != value:
                    errors.append("line." + field)
            for field, name in (("qty", "quantity"), ("rate", "unit_price"), ("amount", "amount")):
                if Decimal(str(line.get(field, "NaN"))) != Decimal(wanted[name]):
                    errors.append("line." + field)
    expected_accounts = {profile["payable_accounts"]["USD"]: (Decimal(0), Decimal(label["total"]))}
    expense = profile["expense_accounts"][label["line_items"][0]["description"]]
    expected_accounts[expense] = (Decimal(label["subtotal"]), Decimal(0))
    accounts = {}
    for row in ledger:
        if (
            row.get("company") != profile["erp_company"]
            or row.get("voucher_no") != actual.get("name")
            or row.get("voucher_type") != "Purchase Invoice"
            or row.get("is_cancelled") not in (0, False)
        ):
            errors.append("ledger_identity")
        debit, credit = accounts.get(row.get("account"), (Decimal(0), Decimal(0)))
        accounts[row.get("account")] = (
            debit + Decimal(str(row.get("debit", 0))),
            credit + Decimal(str(row.get("credit", 0))),
        )
    if accounts != expected_accounts:
        errors.append("ledger_accounts_or_amounts")
    return sorted(set(errors))


def _grounded_fields(revision, predicted, pages):
    fields = {}
    for path, value in revision["fields"].items():
        if value["effective"] is None:
            continue
        if path.startswith("lines."):
            _, line_id, field = path.split(".", 2)
            index = int(line_id[1:]) - 1
            anchor = predicted["line_items"][index].get("provenance", {}).get(field)
        else:
            anchor = predicted.get("provenance", {}).get(path)
        if not anchor or anchor.get("excerpt") not in pages.get(anchor.get("page"), ""):
            continue
        # No oracle lookup and no substitution of a missing/incorrect provider value.
        if str(value["effective"]) not in anchor["excerpt"]:
            continue
        fields[path] = FieldEvidence(
            kind="observed",
            raw=str(value["effective"]),
            effective=value["effective"],
            page=anchor["page"],
            excerpt=anchor["excerpt"],
        )
    return fields


def workflow(observation, source, evidence, matcher, posting, erp, contexts):
    admin, reviewer, approver = contexts
    observation["workflow"] = result = {
        "action": "hold",
        "issue_codes": [],
        "state": "provider_failed",
    }
    if observation["error"]:
        return
    tick = time.perf_counter()
    predicted = observation["predicted_fields"]
    data = _invoice_data(predicted)
    data = replace(
        data,
        line_items=tuple(
            replace(row, line_id=f"L{i + 1}") for i, row in enumerate(data.line_items)
        ),
    )
    document = DocumentRecord(
        original_filename="synthetic.pdf",
        storage_key=observation["document_id"],
        content_type="application/pdf",
    )
    evidence.documents.save(document)
    evidence.extractions.save(
        document.id,
        ExtractionResult(InvoiceExtraction(data), "phase6_original_provider"),
        validate_invoice(data),
    )
    result["document_id"] = str(document.id)
    revision = evidence.capture(document.id, reviewer)
    fields = _grounded_fields(
        revision, predicted, {p["page"]: p["text"] for p in observation["source_pages"]}
    )
    if fields:
        revision = evidence.attest(
            document.id,
            EvidenceUpdate(
                expected_revision=revision["version"],
                fields=fields,
                reason="Synthetic harness checked source anchors; original values unchanged",
            ),
            reviewer,
        )
    evidence.import_records(
        [source["purchase_order"], source["purchase_receipt"]], admin, refresh_unchanged=True
    )
    po = source["purchase_order"]
    snapshot = evidence.snapshot(
        document.id,
        SnapshotInput(
            company=po["company"],
            expected_revision=revision["version"],
            source_system="erpnext",
            po_ids=[po["source_id"]],
            receipt_ids=[source["purchase_receipt"]["source_id"]],
            allocations={
                row.line_id: f"{po['source_id']}:{po['lines'][0]['source_line_id']}"
                for row in data.line_items
            },
        ),
        reviewer,
    )
    result["blockers"] = snapshot["blockers"]
    if snapshot["blockers"]:
        result["state"] = "evidence_hold"
        result["match_latency_ms"] = round((time.perf_counter() - tick) * 1000, 2)
        return
    evidence.approve(snapshot["id"], snapshot["payload_hash"], approver)
    match = matcher.assess(snapshot["id"], reviewer)
    result.update(
        issue_codes=sorted({i["code"] for i in match["issues"]}),
        match_id=match["id"],
        state="match_hold",
        match_latency_ms=round((time.perf_counter() - tick) * 1000, 2),
    )
    result["detected_duplicate_document_ids"] = sorted(
        {
            i["facts"]["other_document_id"]
            for i in match["issues"]
            if i["code"] in {"duplicate_confirmed", "duplicate_candidate"}
        }
    )
    if match["recommendation"] != "ready_for_approval":
        exceptions = ExceptionService(evidence)
        decisions = []
        for case in exceptions.list_cases(approver, document_id=document.id):
            if case["match_id"] != match["id"] or case["state"] == "superseded":
                continue
            decision = exceptions.update(
                case["id"],
                ExceptionUpdate(
                    expected_version=case["version"],
                    expected_match_id=match["id"],
                    state="rejected",
                    owner=approver.actor,
                    reason="Synthetic approver rejects this non-payable revision due to the current procurement discrepancy",
                    evidence_refs=[
                        snapshot["id"],
                        match["id"],
                        po["source_id"],
                        source["purchase_receipt"]["source_id"],
                    ],
                ),
                approver,
                matcher,
            )
            decisions.append(
                {
                    key: decision[key]
                    for key in (
                        "id",
                        "state",
                        "basis_hash",
                        "authorizer",
                        "evidence_refs",
                        "reason",
                    )
                }
            )
        result["dispositions"] = decisions
        result["disposition_status"] = matcher.status(match["id"], approver)["status"]
        if decisions and result["disposition_status"] == "rejected":
            result["state"] = "exception_resolved"
        return
    result["action"] = "submit"
    matcher.approve(match["id"], match["basis_hash"], approver)
    tick = time.perf_counter()
    draft = posting.create_draft(match["id"], match["basis_hash"], {}, approver)
    result.update(state="draft_" + draft["state"], target=draft.get("target"))
    if draft["state"] == "confirmed":
        approval = posting.approve_submit(
            match["id"],
            draft["id"],
            draft["verification_hash"],
            "Synthetic sandbox separate submit approval after verified draft",
            approver,
        )
        posted = posting.submit_draft(match["id"], approval["approval_hash"], approver)
        result.update(
            state="submit_" + posted["state"],
            approval_hash=approval["approval_hash"],
            posted_verified=posted.get("posted_verified", False),
            error_code=posted.get("error_code"),
        )
        if posted.get("target"):
            actual = erp.get_purchase_invoice(posted["target"])
            result["erp_readback"] = actual
            if actual.get("docstatus") == 1:
                result["ledger_readback"] = erp.get_gl_entries(posted["target"])
    result["erp_latency_ms"] = round((time.perf_counter() - tick) * 1000, 2)


def summarize(pack, split, dataset, observations, profile):
    expected = records_from_dataset(dataset)
    summary = build_external_evaluation_summary(
        expected,
        observations,
        split=split,
        provider="ocr_space+llm_json",
        dataset_class="Phase 6 recovery AI-assisted synthetic invoices",
    )
    labels = {row["document_id"]: row for row in expected}
    expectations = {}
    for document in dataset.documents:
        directory = document.source_path.parent
        for row in load_json(directory / "expected-match.json"):
            expectations[row["document_id"]] = row
    eligible = unsafe_ready = unsafe_submit = false_holds = verified = submitted = completion = (
        correct_terminal
    ) = 0
    correct_holds = resolved_exceptions = 0
    matrices = {
        category: {key: 0 for key in ("TP", "FN", "FP", "TN")} for category in CATEGORY_CODES
    }
    observed_by_id = {row["document_id"]: row for row in observations}
    for document in dataset.documents:
        row = observed_by_id.get(
            document.document_id, {"document_id": document.document_id, "predicted_fields": {}}
        )
        wanted = expectations[row["document_id"]]
        result = row.get("workflow", {})
        scheduled_eligible = wanted["expected_action"] == "submit"
        eligible += scheduled_eligible
        ready = result.get("action") == "submit"
        actual = result.get("erp_readback", {})
        is_submitted = actual.get("docstatus") == 1
        false_holds += scheduled_eligible and not ready
        unsafe_ready += not scheduled_eligible and ready
        unsafe_submit += not scheduled_eligible and is_submitted
        actual_codes = set(result.get("issue_codes", []))
        wanted_codes = set(wanted.get("pipeline_issue_codes", wanted["issue_codes"]))
        for category, codes in CATEGORY_CODES.items():
            positive, detected = bool(wanted_codes & codes), bool(actual_codes & codes)
            matrices[category][
                "TP" if positive and detected else "FN" if positive else "FP" if detected else "TN"
            ] += 1
        invoice_correct = bool(
            evaluate_invoices(
                [labels[row["document_id"]]],
                [{"document_id": row["document_id"], **row["predicted_fields"]}],
            ).quality["full_invoice_documents_matched"]
        )
        if is_submitted:
            submitted += 1
            directory = next(
                d.source_path.parent
                for d in dataset.documents
                if d.document_id == row["document_id"]
            )
            mismatches = independent_readback(
                labels[row["document_id"]],
                load_json(directory / "procurement.json"),
                profile,
                actual,
                result.get("ledger_readback", []),
            )
            result["independent_oracle_mismatches"] = mismatches
            verified += not mismatches
            completion += (
                scheduled_eligible and not mismatches and bool(result.get("posted_verified"))
            )
            terminal = scheduled_eligible and not mismatches and result.get("posted_verified")
        else:
            correct_hold = not scheduled_eligible and wanted_codes == actual_codes and not ready
            correct_holds += correct_hold
            decisions = result.get("dispositions", [])
            resolved = (
                correct_hold
                and result.get("state") == "exception_resolved"
                and result.get("disposition_status") == "rejected"
                and bool(decisions)
                and all(
                    d.get("state") == "rejected" and d.get("authorizer") and d.get("evidence_refs")
                    for d in decisions
                )
            )
            resolved_exceptions += bool(resolved)
            terminal = resolved
        correct_terminal += bool(terminal and invoice_correct)
    summary["pipeline"] = {
        "scheduled": len(dataset.documents),
        "observed": len(observations),
        "strict_correct_terminal": correct_terminal,
        "eligible_scheduled": eligible,
        "correct_hold_decisions": correct_holds,
        "completed_exception_dispositions": resolved_exceptions,
        "false_holds": {"numerator": false_holds, "denominator": eligible},
        "unsafe_ready": {
            "numerator": unsafe_ready,
            "denominator": len(dataset.documents) - eligible,
        },
        "unsafe_submit": unsafe_submit,
        "category_matrices": matrices,
        "submitted_readbacks": submitted,
        "independently_correct_postings": verified,
        "posting_correctness": verified / submitted if submitted else None,
        "eligible_posting_completion": {"numerator": completion, "denominator": eligible},
        "restart_replay_same_target": sum(
            bool(row.get("workflow", {}).get("restart_replay_same_target")) for row in observations
        ),
        "duplicate_erp_effects": sum(
            row.get("workflow", {}).get("erp_target_count", 1) > 1 for row in observations
        ),
    }
    groups = {}
    for label in expected:
        if label.get("duplicate_group"):
            groups.setdefault(label["duplicate_group"], []).append(label["document_id"])
    from itertools import combinations

    expected_pairs = {
        frozenset(pair) for group in groups.values() for pair in combinations(group, 2)
    }
    local_ids = {
        row.get("workflow", {}).get("document_id"): row["document_id"] for row in observations
    }
    detected_pairs = {
        frozenset((row["document_id"], local_ids.get(other, "unknown:" + other)))
        for row in observations
        for other in row.get("workflow", {}).get("detected_duplicate_document_ids", [])
    }
    tp, fp, fn = (
        len(expected_pairs & detected_pairs),
        len(detected_pairs - expected_pairs),
        len(expected_pairs - detected_pairs),
    )
    summary["metrics"]["identity_pair_diagnostic"] = summary["metrics"].pop("duplicate_detection")
    summary["metrics"]["duplicate_detection"] = {
        "input": "actual_match_detector_issue_pairs",
        "positive_pairs_expected": len(expected_pairs),
        "true_positive_pairs": tp,
        "false_positive_pairs": fp,
        "false_negative_pairs": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
    }
    latency = {}
    for stage in ("match", "erp", "pipeline_total"):
        values = [row.get("workflow", {}).get(stage + "_latency_ms") for row in observations]
        values = [value for value in values if value is not None]
        latency[stage] = {
            "N": len(values),
            **{f"p{p}_ms": _percentile(values, p) for p in (50, 90, 95)},
        }
    summary["pipeline_latency_ms"] = latency
    summary["stage_latency_ms"] = latency_summary(observations)
    summary["provider_usage"] = {
        "ocr_attempts": sum(
            len(physical_ocr_attempts(stage))
            for row in observations
            for stage in row["stages"]
            if stage["stage"] == "ocr"
        ),
        "ocr_rate_limit_responses": sum(
            attempt.get("http_status") == 429
            for row in observations
            for stage in row["stages"]
            if stage["stage"] == "ocr"
            for attempt in physical_ocr_attempts(stage)
        ),
        "ocr_retry_wait_seconds": sum(
            attempt.get("wait_before_retry_seconds", 0)
            for row in observations
            for stage in row["stages"]
            if stage["stage"] == "ocr"
            for attempt in stage.get("attempts", [])
        ),
        "extractor_attempts": sum(
            len(stage.get("attempts", [])) or 1
            for row in observations
            for stage in row["stages"]
            if stage["stage"] == "extraction"
        ),
        "ocr_pages": sum(
            stage.get("usage", {}).get("pages_processed") or 0
            for row in observations
            for stage in row["stages"]
            if stage["stage"] == "ocr"
        ),
        "extractor_input_tokens": sum(
            stage.get("usage", {}).get("input_tokens") or 0
            for row in observations
            for stage in row["stages"]
            if stage["stage"] == "extraction"
        ),
        "extractor_output_tokens": sum(
            stage.get("usage", {}).get("output_tokens") or 0
            for row in observations
            for stage in row["stages"]
            if stage["stage"] == "extraction"
        ),
        "billed_cost_usd": None,
    }
    summary["manifest_sha256"] = file_digest(pack / "manifest.json")
    summary["limitations"].extend(
        [
            "Local synchronous service harness with synthetic approval identities; no human correction.",
            "API, worker queue and queue-wait latency are not measured by this synchronous harness.",
            "Billed dollar cost is unverified; provider tokens/pages are retained in the private stage records.",
        ]
    )
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack", type=Path)
    parser.add_argument("--split", choices=("development", "quality_holdout"), required=True)
    parser.add_argument("--output-prefix", type=Path, required=True)
    parser.add_argument("--max-documents", type=int)
    parser.add_argument("--development-probes", action="store_true")
    parser.add_argument("--rate-limit-seconds", type=float, default=5)
    args = parser.parse_args()
    pack = args.pack.resolve()
    prefix = args.output_prefix.resolve()
    if (
        ROOT not in prefix.parents
        or "_local_docs" not in prefix.parts
        or args.rate_limit_seconds < 0
    ):
        raise SystemExit("Private evidence must remain local; delay cannot be negative")
    if args.max_documents is not None and (args.split != "development" or args.max_documents < 1):
        raise SystemExit("Only development diagnostics may select a subset")
    if args.development_probes and args.split != "development":
        raise SystemExit("Scenario probes are development only")
    audit(pack, require_sealed=args.split != "development", inspect_pdf_text=False)
    settings = load_settings()
    if not settings.accounting_sandbox_mode or not settings.erpnext_sandbox_posting_enabled:
        raise SystemExit("Explicit ERP sandbox flags required")
    from urllib.parse import urlparse

    if urlparse(settings.erpnext_base_url).hostname not in {"localhost", "127.0.0.1"}:
        raise SystemExit("Only a local ERP sandbox is allowed")
    private, aggregate, db = (
        Path(str(prefix) + suffix) for suffix in ("-private.json", "-summary.json", ".db")
    )
    if any(path.exists() for path in (private, aggregate, db)):
        raise SystemExit("Refusing to overwrite a run")
    prefix.parent.mkdir(parents=True, exist_ok=True)
    if args.split == "quality_holdout":
        from phase6_provider_run import config_fingerprint
        from app.providers.llm_json import extraction_prompt_sha256

        freeze = load_json(pack / "manifest.json")["freeze"]
        if (
            freeze["config_sha256"] != config_fingerprint(settings)
            or freeze["prompt_sha256"] != extraction_prompt_sha256()
        ):
            raise SystemExit("Frozen provider configuration changed")
        with (pack / "quality-run-claim.json").open("x", encoding="utf-8") as claim:
            json.dump(
                {"started_at": datetime.now(UTC).isoformat(), "output_prefix": str(prefix)}, claim
            )
    dataset = load_evaluation_dataset(pack / args.split)
    if args.development_probes:
        families = next(
            c["families"]
            for c in load_json(pack / "manifest.json")["cohorts"]
            if c["split"] == "development"
        )
        selected = {f["family_id"] for i, f in enumerate(families) if i % 10 == 1}
        dataset = replace(
            dataset,
            documents=tuple(d for d in dataset.documents if d.source_path.parent.name in selected),
        )
    if args.max_documents:
        dataset = replace(dataset, documents=dataset.documents[: args.max_documents])
    profile = load_json(pack / "erp-profile.json")
    admin = SecurityContext("Phase 6 sandbox admin", role="admin", is_admin=True)
    reviewer = SecurityContext("Phase 6 synthetic anchor reviewer", role="reviewer")
    approver = SecurityContext("Phase 6 synthetic AP approver", role="ap_approver")
    erp = ERPNextClient(
        settings.erpnext_base_url,
        api_key=settings.erpnext_api_key,
        api_secret=settings.erpnext_api_secret,
        allowed_hosts=settings.erpnext_allowed_hosts,
        timeout_seconds=60,
    )
    store = SqliteStore(db)
    observations = []
    started_at = datetime.now(UTC).isoformat()

    def services(connection):
        evidence = EvidenceService(
            VersionRepository(connection),
            SqliteDocumentRepository(connection),
            SqliteExtractionRepository(connection),
        )
        return evidence, MatchService(evidence), PostingService(evidence, erp, sandbox_enabled=True)

    evidence, matcher, posting = services(store)
    evidence.configure(
        "mapping",
        Mapping(
            company=profile["company"],
            supplier_aliases=profile["supplier_ids"],
            item_mappings=profile["item_codes"],
            reason="Verified Phase 6 sandbox master",
        ),
        admin,
    )
    evidence.configure(
        "policy",
        Policy(company=profile["company"], currency="USD", reason="Frozen same-currency policy"),
        admin,
    )
    matcher.configure_policy(
        MatchPolicy(
            company=profile["company"],
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
            mode="ordered",
            reason="Frozen exact quantity and price purchasing rule",
        ),
        admin,
    )
    posting.configure_profile(ERPPostingProfile.model_validate(profile), admin)
    ocr = RateAwareParser(build_parser_provider(settings))
    extractor = build_extractor_provider(settings)
    extractor = replace(extractor, post_json=bounded_post(extractor.post_json))
    extractor = BoundedExtractor(extractor)
    write_json(
        private, {"status": "started", "scheduled": len(dataset.documents), "observations": []}
    )
    try:
        for index, document in enumerate(dataset.documents):
            if index and args.rate_limit_seconds:
                time.sleep(args.rate_limit_seconds)
            started = time.perf_counter()
            observation = run_document(document, ocr, extractor)
            try:
                workflow(
                    observation,
                    load_json(document.source_path.parent / "procurement.json"),
                    evidence,
                    matcher,
                    posting,
                    erp,
                    (admin, reviewer, approver),
                )
            except Exception as exc:
                observation.setdefault("workflow", {}).update(
                    state="workflow_error",
                    error_type=type(exc).__name__,
                    error_detail=str(exc)[:500],
                )
            observation.setdefault("workflow", {})["pipeline_total_latency_ms"] = round(
                (time.perf_counter() - started) * 1000, 2
            )
            observations.append(observation)
            write_json(
                private,
                {
                    "status": "running",
                    "scheduled": len(dataset.documents),
                    "observations": observations,
                },
            )
            print(
                f"{index + 1}/{len(dataset.documents)}: {observation['workflow']['state']}",
                flush=True,
            )
    except KeyboardInterrupt:
        print(
            "Run interrupted; unobserved scheduled invoices remain in the denominator", flush=True
        )
    finally:
        store.close()
        write_json(
            private,
            {
                "status": "completed" if len(observations) == len(dataset.documents) else "partial",
                "scheduled": len(dataset.documents),
                "observations": observations,
            },
        )
    # Fresh repositories emulate an application restart; saved operations must
    # replay to the same remote target without another create or submit effect.
    store = SqliteStore(db)
    try:
        _, _, restarted = services(store)
        for row in observations:
            result = row.get("workflow", {})
            if result.get("posted_verified"):
                try:
                    replay = restarted.submit_draft(
                        result["match_id"], result["approval_hash"], approver
                    )
                    result["restart_replay_same_target"] = replay["target"] == result["target"]
                    create = restarted._operation(
                        approver.workspace_id, "create", result["match_id"]
                    )
                    result["erp_target_count"] = len(
                        erp.find_purchase_invoices_by_delivery_key(create["idempotency_key"])
                    )
                except Exception as exc:
                    result["restart_verification_error"] = type(exc).__name__
    finally:
        store.close()
    summary = summarize(pack, args.split, dataset, observations, profile)
    summary["run_status"] = (
        "completed" if len(observations) == len(dataset.documents) else "partial"
    )
    summary["started_at"] = started_at
    summary["completed_at"] = datetime.now(UTC).isoformat()
    write_json(
        private,
        {
            "status": summary["run_status"],
            "scheduled": len(dataset.documents),
            "observations": observations,
        },
    )
    write_json(aggregate, summary)
    print(json.dumps(summary["pipeline"], indent=2))


if __name__ == "__main__":
    main()
