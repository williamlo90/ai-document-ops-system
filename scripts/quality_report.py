from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAX_NEW_COMPLEXITY = 15
MAX_NEW_FUNCTION_LINES = 80
COMPLEXITY_EXCEPTIONS = {
    "backend/app/evaluation/dashboard.py::EvaluationDashboardService._normalize_report": 30,
    "backend/app/exports/batch_service.py::ExportBatchService.workspace": 28,
    "backend/app/api/review.py::review_worklist_row": 27,
    "backend/app/providers/llm_json.py::_ground_extraction": 22,
    "backend/app/exports/batch_service.py::ExportBatchService._invoice_row": 22,
    "backend/app/system/dashboard.py::SystemDashboardService._provider_service": 21,
    "backend/app/overview/dashboard.py::OverviewDashboardService.dashboard": 21,
    "backend/app/exports/batch_service.py::ExportBatchService.eligibility": 19,
    "backend/app/api/review.py::review_worklist": 19,
    "backend/app/agentops/service.py::AgentOpsEvaluationService.summarize": 19,
    "backend/app/agent/repositories.py::_run_from_dict": 18,
    "backend/app/evaluation/external_holdout.py::_failure_taxonomy": 17,
    "backend/app/backoffice/services.py::BackofficeWorkflowService.plan_work_item": 17,
    "backend/app/api/exceptions.py::_filter_rows": 17,
    "backend/app/system/dashboard.py::SystemDashboardService._flow": 16,
}
FUNCTION_LENGTH_EXCEPTIONS = {
    "backend/app/documents/sqlite_repositories.py::SqliteStore._init_schema_locked": 232,
    "backend/app/api/dependencies.py::build_container": 231,
    "backend/app/exports/batch_service.py::ExportBatchService.execute": 127,
    "backend/app/integrations/services.py::InvoiceIntegrationService._deliver": 118,
    "backend/app/backoffice/services.py::BackofficeWorkflowService.plan_work_item": 118,
    "backend/app/evaluation/dashboard.py::EvaluationDashboardService.run": 115,
    "backend/app/documents/services.py::DocumentProcessingService._process_job": 105,
    "backend/app/api/invoices.py::save_intake_draft": 102,
    "backend/app/main.py::create_app": 99,
    "backend/app/documents/retention.py::SqliteRetentionRepository.purge": 95,
    "backend/app/documents/retention.py::InMemoryRetentionRepository.purge": 94,
    "backend/app/overview/dashboard.py::OverviewDashboardService.dashboard": 91,
    "backend/app/backoffice/services.py::BackofficeWorkflowService.execute_approved_step": 84,
    "backend/app/exports/batch_service.py::ExportBatchService.workspace": 83,
    "backend/app/evaluation/dashboard.py::EvaluationDashboardService._normalize_report": 83,
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
        f"and <= {MAX_NEW_FUNCTION_LINES} lines."
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


def _is_test_path(path: str) -> bool:
    return "/tests/" in path.replace("\\", "/")


if __name__ == "__main__":
    raise SystemExit(main())
