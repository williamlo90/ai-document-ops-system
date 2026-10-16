from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAX_NEW_COMPLEXITY = 15
MAX_NEW_FUNCTION_LINES = 80
MAX_NEW_CLASS_LINES = 300
# Existing Phase 6 code (0695599), retained without increased complexity.
# These budgets are ceilings, not exemptions from future growth checks.
COMPLEXITY_EXCEPTIONS = {
    "backend/app/agent/repositories.py::_run_from_dict": 18,
    "backend/app/agentops/service.py::AgentOpsEvaluationService.summarize": 19,
    "backend/app/api/exceptions.py::_filter_rows": 17,
    "backend/app/api/integrations.py::integration_status": 23,
    "backend/app/api/review.py::review_worklist": 19,
    "backend/app/api/review.py::review_worklist_row": 27,
    "backend/app/backoffice/services.py::BackofficeWorkflowService.plan_work_item": 17,
    "backend/app/evaluation/dashboard.py::EvaluationDashboardService._normalize_report": 30,
    "backend/app/evaluation/dashboard.py::EvaluationDashboardService.run": 16,
    "backend/app/evaluation/external_holdout.py::_failure_taxonomy": 17,
    "backend/app/evaluation/invoice.py::evaluate_invoices": 23,
    "backend/app/evaluation/line_items.py::evaluate_line_items": 23,
    "backend/app/evaluation/provenance.py::evidence_valid": 17,
    "backend/app/exports/batch_service.py::ExportBatchService._invoice_row": 22,
    "backend/app/exports/batch_service.py::ExportBatchService.eligibility": 19,
    "backend/app/exports/batch_service.py::ExportBatchService.workspace": 28,
    "backend/app/overview/dashboard.py::OverviewDashboardService.dashboard": 21,
    "backend/app/procurement/duplicates.py::detect_duplicates": 49,
    "backend/app/procurement/exceptions.py::ExceptionService.sync_for_match": 16,
    "backend/app/procurement/exceptions.py::ExceptionService.update": 27,
    "backend/app/procurement/matching.py::MatchService._evaluate": 90,
    "backend/app/procurement/models.py::FieldEvidence.evidence_requirements": 16,
    "backend/app/procurement/posting.py::PostingService._source_fresh": 25,
    "backend/app/procurement/posting.py::PostingService.create_draft": 28,
    "backend/app/procurement/posting.py::PostingService.submit_draft": 16,
    "backend/app/procurement/posting_contract.py::expected_invoice": 33,
    "backend/app/procurement/posting_contract.py::verify_document": 33,
    "backend/app/procurement/posting_contract.py::verify_ledger": 26,
    "backend/app/procurement/service.py::EvidenceService.blockers": 40,
    "backend/app/procurement/service.py::EvidenceService.capture": 18,
    "backend/app/procurement/service.py::EvidenceService.import_csv": 19,
    "backend/app/providers/gemini.py::GeminiOcrParserProvider.parse": 22,
    "backend/app/providers/llm_json.py::_columnar_facts": 20,
    "backend/app/providers/llm_json.py::_columnar_money": 20,
    "backend/app/providers/llm_json.py::_columnar_supplier_names": 16,
    "backend/app/providers/llm_json.py::_find_labeled_currency": 23,
    "backend/app/providers/llm_json.py::_find_labeled_money": 16,
    "backend/app/providers/llm_json.py::_ground_extraction": 50,
    "backend/app/providers/llm_json.py::_ground_line_confidence": 36,
    "backend/app/providers/llm_json.py::_header_anchor": 24,
    "backend/app/providers/ocr_space.py::OcrSpaceParserProvider.parse": 31,
    "backend/app/providers/ocr_space.py::_positional_table_text": 50,
    "backend/app/system/dashboard.py::SystemDashboardService._flow": 16,
    "backend/app/system/dashboard.py::SystemDashboardService._provider_service": 21,
}
FUNCTION_LENGTH_EXCEPTIONS = {
    "backend/app/api/integrations.py::integration_status": 98,
    "backend/app/api/invoices.py::save_intake_draft": 102,
    "backend/app/backoffice/services.py::BackofficeWorkflowService.execute_approved_step": 84,
    "backend/app/backoffice/services.py::BackofficeWorkflowService.plan_work_item": 118,
    "backend/app/core/settings.py::load_settings": 111,
    "backend/app/documents/retention.py::InMemoryRetentionRepository.purge": 94,
    "backend/app/documents/retention.py::SqliteRetentionRepository.purge": 95,
    "backend/app/documents/sqlite_repositories.py::SqliteStore._init_schema_locked": 232,
    "backend/app/evaluation/dashboard.py::EvaluationDashboardService._normalize_report": 83,
    "backend/app/evaluation/dashboard.py::EvaluationDashboardService.run": 131,
    "backend/app/evaluation/line_items.py::evaluate_line_items": 84,
    "backend/app/exports/batch_service.py::ExportBatchService.execute": 127,
    "backend/app/exports/batch_service.py::ExportBatchService.workspace": 83,
    "backend/app/integrations/services.py::InvoiceIntegrationService._deliver": 118,
    "backend/app/main.py::create_app": 102,
    "backend/app/overview/dashboard.py::OverviewDashboardService.dashboard": 91,
    "backend/app/postgres/repositories.py::PostgresRetentionRepository.purge": 94,
    "backend/app/procurement/duplicates.py::detect_duplicates": 105,
    "backend/app/procurement/matching.py::MatchService._evaluate": 328,
    "backend/app/procurement/posting.py::PostingService.create_draft": 142,
    "backend/app/procurement/posting.py::PostingService.submit_draft": 89,
    "backend/app/procurement/posting_contract.py::expected_invoice": 110,
    "backend/app/procurement/posting_contract.py::verify_document": 83,
    "backend/app/procurement/service.py::EvidenceService.blockers": 92,
    "backend/app/providers/gemini.py::GeminiOcrParserProvider.parse": 96,
    "backend/app/providers/llm_json.py::_ground_extraction": 107,
    "backend/app/providers/llm_json.py::_ground_line_confidence": 93,
    "backend/app/providers/ocr_space.py::OcrSpaceParserProvider.parse": 90,
    "backend/app/providers/ocr_space.py::_positional_table_text": 109,
    "backend/app/review/services.py::ReviewService.save_review": 82,
}
CLASS_LENGTH_EXCEPTIONS = {
    "backend/app/backoffice/execution.py::BackofficeExecutionCoordinator": 414,
    "backend/app/backoffice/planning_service.py::BackofficePlanningService": 469,
    "backend/app/backoffice/services.py::BackofficeWorkflowService": 467,
    "backend/app/evaluation/dashboard.py::EvaluationDashboardService": 613,
    "backend/app/exports/execution.py::ExportExecutionLifecycle": 301,
    "backend/app/exports/workspace.py::ExportWorkspaceQuery": 409,
    "backend/app/integrations/services.py::InvoiceIntegrationService": 334,
    "backend/app/overview/dashboard.py::OverviewDashboardService": 535,
    "backend/app/procurement/matching.py::MatchService": 558,
    "backend/app/procurement/posting.py::PostingService": 543,
    "backend/app/procurement/service.py::EvidenceService": 439,
    "backend/app/system/dashboard.py::SystemDashboardService": 472,
}


def main() -> int:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "radon",
            "cc",
            "backend/app",
            "-j",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        return result.returncode
    report = json.loads(result.stdout)
    violations = [
        *complexity_violations(report),
        *function_length_violations(report),
        *class_length_violations(),
    ]
    scored = [
        item["complexity"]
        for path, entries in report.items()
        if not _is_test_path(path)
        for item in entries
        if item["type"] in {"function", "method"}
    ]
    print(
        f"Complexity policy: {len(scored)} functions checked; "
        f"new functions must be <= {MAX_NEW_COMPLEXITY} complexity "
        f"and <= {MAX_NEW_FUNCTION_LINES} lines; "
        f"new classes must be <= {MAX_NEW_CLASS_LINES} lines."
    )
    if violations:
        print("Complexity budget exceeded:", file=sys.stderr)
        for violation in violations:
            print(f"- {violation}", file=sys.stderr)
        return 1
    print("Complexity budget passed.")
    return 0


def complexity_violations(report: dict[str, list[dict[str, object]]]) -> list[str]:
    violations = []
    for raw_path, entries in report.items():
        path = raw_path.replace("\\", "/")
        if _is_test_path(path):
            continue
        for item in entries:
            if item["type"] not in {"function", "method"}:
                continue
            complexity = int(item["complexity"])
            if complexity <= MAX_NEW_COMPLEXITY:
                continue
            class_name = str(item.get("classname") or "")
            name = str(item["name"])
            qualified_name = f"{class_name}.{name}" if class_name else name
            key = f"{path}::{qualified_name}"
            allowed = COMPLEXITY_EXCEPTIONS.get(key)
            if allowed is None:
                violations.append(f"{key} has complexity {complexity}; no exception is recorded")
            elif complexity > allowed:
                violations.append(f"{key} increased from allowed {allowed} to {complexity}")
    return violations


def function_length_violations(report: dict[str, list[dict[str, object]]]) -> list[str]:
    violations = []
    for raw_path, entries in report.items():
        path = raw_path.replace("\\", "/")
        if _is_test_path(path):
            continue
        for item in entries:
            if item["type"] not in {"function", "method"}:
                continue
            length = int(item["endline"]) - int(item["lineno"]) + 1
            if length <= MAX_NEW_FUNCTION_LINES:
                continue
            class_name = str(item.get("classname") or "")
            name = str(item["name"])
            qualified_name = f"{class_name}.{name}" if class_name else name
            key = f"{path}::{qualified_name}"
            allowed = FUNCTION_LENGTH_EXCEPTIONS.get(key)
            if allowed is None:
                violations.append(f"{key} has {length} lines; no exception is recorded")
            elif length > allowed:
                violations.append(f"{key} increased from allowed {allowed} to {length} lines")
    return violations


def class_length_violations() -> list[str]:
    violations = []
    for source_path in (ROOT / "backend" / "app").rglob("*.py"):
        path = source_path.relative_to(ROOT).as_posix()
        if _is_test_path(path):
            continue
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or node.end_lineno is None:
                continue
            length = node.end_lineno - node.lineno + 1
            if length <= MAX_NEW_CLASS_LINES:
                continue
            key = f"{path}::{node.name}"
            allowed = CLASS_LENGTH_EXCEPTIONS.get(key)
            if allowed is None:
                violations.append(f"{key} has {length} lines; no exception is recorded")
            elif length > allowed:
                violations.append(f"{key} increased from allowed {allowed} to {length} lines")
    return violations


def _is_test_path(path: str) -> bool:
    return "/tests/" in path.replace("\\", "/")


if __name__ == "__main__":
    raise SystemExit(main())
