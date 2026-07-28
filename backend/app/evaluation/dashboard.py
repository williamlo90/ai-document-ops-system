from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path
from threading import Lock
from typing import Any

from app.benchmark.datasets import load_evaluation_dataset, records_from_dataset
from app.benchmark.history import BenchmarkHistoryRepository
from app.benchmark.models import EvaluationDataset
from app.benchmark.service import invoice_data_to_fields
from app.core.security import SecurityContext, require_admin
from app.core.settings import Settings
from app.evaluation.external_holdout import build_external_evaluation_summary
from app.evaluation.history import (
    EvaluationAttemptRecord,
    EvaluationAttemptRepository,
)
from app.evaluation.provider_costs import build_provider_economics
from app.providers.contracts import DocumentSource, ExtractorProvider, ParserProvider, ProviderError
from app.validation.invoice import validate_invoice


REPO_ROOT = Path(__file__).resolve().parents[3]
PUBLIC_EVIDENCE_ROOT = REPO_ROOT / "docs" / "evidence"
SCENARIO_DATASET_ROOT = REPO_ROOT / "examples" / "benchmark" / "datasets" / "invoice_scenarios_v1"
FIELD_GATE = 0.95
VALIDATION_GATE = 0.95
REGRESSION_TOLERANCE = 0.005
FIELD_LABELS = {
    "vendor_name": "Vendor",
    "invoice_number": "Invoice number",
    "invoice_date": "Invoice date",
    "due_date": "Due date",
    "subtotal": "Subtotal",
    "tax": "Tax",
    "total": "Total",
    "currency": "Currency",
}


class EvaluationRunIncomplete(RuntimeError):
    def __init__(
        self,
        attempt: EvaluationAttemptRecord,
        failures: tuple[dict[str, Any], ...] = (),
        economics: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(attempt.error_message or "Evaluation did not complete.")
        self.attempt = attempt
        self.failures = failures
        self.economics = economics


class EvaluationDashboardService:
    def __init__(
        self,
        *,
        settings: Settings,
        history: BenchmarkHistoryRepository,
        attempts: EvaluationAttemptRepository,
        parser: ParserProvider,
        extractor: ExtractorProvider,
    ) -> None:
        self.settings = settings
        self.history = history
        self.attempts = attempts
        self.parser = parser
        self.extractor = extractor
        self._run_lock = Lock()

    def dashboard(
        self,
        *,
        context: SecurityContext,
        run_id: str | None,
        range_limit: int,
    ) -> dict[str, object]:
        require_admin(context)
        runs = self._all_runs(context.workspace_id)
        selected = self._select_run(runs, run_id)
        if selected is None:
            return {
                "gates": self._gates(),
                "preflight": self.preflight(context),
                "runs": [],
                "selected_run": None,
                "trend": [],
                "regression": None,
                "fields": [],
                "scenario_coverage": self._scenario_coverage(None),
                "attempts": self._attempt_responses(context.workspace_id),
            }
        series = [run for run in runs if run["series_key"] == selected["series_key"]]
        series.sort(key=lambda run: str(run["observed_at"]))
        bounded = series[-max(1, min(range_limit, 20)) :]
        previous = self._previous_comparable(runs, selected)
        field_rows, regression = self._field_comparison(selected, previous)
        return {
            "gates": self._gates(),
            "preflight": self.preflight(context),
            "runs": [self._selector_response(run, selected["id"]) for run in runs[:20]],
            "selected_run": selected,
            "trend": [self._trend_response(run, selected["id"]) for run in bounded],
            "regression": regression,
            "fields": field_rows,
            "scenario_coverage": self._scenario_coverage(selected),
            "attempts": self._attempt_responses(context.workspace_id),
        }

    def preflight(self, context: SecurityContext) -> dict[str, object]:
        require_admin(context)
        dataset = load_evaluation_dataset(SCENARIO_DATASET_ROOT)
        requested = min(
            len(dataset.documents),
            max(1, self.settings.benchmark_real_provider_max_documents),
        )
        return {
            "dataset_id": "invoice_scenarios_v1",
            "dataset_version": "1.0",
            "dataset_label": "Synthetic invoice scenarios v1",
            "available_documents": len(dataset.documents),
            "documents": requested,
            "limited": requested < len(dataset.documents),
            "provider_calls_estimate": requested * 2,
            "estimated_cost_usd": None,
            "cost_note": "Cost is calculated from provider-reported usage after completion.",
            "runnable": True,
            "provider": f"{self.parser.provider_name}+{self.extractor.provider_name}",
        }

    def run(self, *, context: SecurityContext) -> dict[str, object]:
        require_admin(context)
        if not self._run_lock.acquire(blocking=False):
            raise RuntimeError("An evaluation is already running in this process.")
        dataset = self._limited_dataset(load_evaluation_dataset(SCENARIO_DATASET_ROOT))
        attempt = self.attempts.save(
            EvaluationAttemptRecord(
                workspace_id=context.workspace_id,
                requested_by=context.actor,
                dataset_id="invoice_scenarios_v1",
                dataset_version="1.0",
                documents_requested=len(dataset.documents),
            )
        )
        observations: list[dict[str, Any]] = []
        try:
            for index, document in enumerate(dataset.documents):
                if index > 0:
                    time.sleep(0.2)
                observations.append(self._run_document(document.document_id, document.source_path))
            economics = build_provider_economics(
                observations,
                parser_model=self.settings.mistral_ocr_model,
                extractor_model=self.settings.extractor_model,
            )
            processed = sum(1 for item in observations if not item.get("error"))
            provider_calls = int(economics["attempts"]["total"])
            if processed != len(dataset.documents):
                failed = self.attempts.save(
                    attempt.failed(
                        documents_processed=processed,
                        provider_calls=provider_calls,
                    )
                )
                raise EvaluationRunIncomplete(
                    failed,
                    failures=_failure_details(observations),
                    economics=economics,
                )
            report = build_external_evaluation_summary(
                records_from_dataset(dataset),
                observations,
                split="diagnostic",
                provider=f"{self.parser.provider_name}+{self.extractor.provider_name}",
            )
            now = datetime.now(UTC)
            report.update(
                {
                    "dataset_id": "invoice_scenarios_v1",
                    "dataset_version": "1.0",
                    "dataset_class": "deterministic synthetic invoice scenarios",
                    "workspace_id": context.workspace_id,
                    "generated_at": now.isoformat(),
                    "provider_economics": economics,
                    "experiment": {
                        "experiment_id": str(attempt.id),
                        "started_at": attempt.started_at.isoformat(),
                        "dataset_fingerprint_sha256": None,
                    },
                    "limitations": [
                        "Results use a small deterministic synthetic invoice set, not customer traffic.",
                        "The configured safety cap may evaluate only part of the 20-document suite.",
                        "Cost is a list-price estimate from provider-reported usage, not a billing record.",
                        "Latency depends on the local network and hosted provider conditions.",
                    ],
                }
            )
            saved = self.history.save(
                "invoice_scenarios_v1",
                str(report["provider"]),
                report,
            )
            completed = self.attempts.save(
                attempt.succeeded(
                    run_id=saved.id,
                    documents_processed=processed,
                    provider_calls=provider_calls,
                )
            )
            return {
                "attempt": self._attempt_response(completed),
                "run_id": str(saved.id),
            }
        except EvaluationRunIncomplete:
            raise
        except Exception as exc:
            economics = build_provider_economics(
                observations,
                parser_model=self.settings.mistral_ocr_model,
                extractor_model=self.settings.extractor_model,
            )
            failed = self.attempts.save(
                attempt.failed(
                    documents_processed=sum(1 for item in observations if not item.get("error")),
                    provider_calls=int(economics["attempts"]["total"]),
                )
            )
            failures = _failure_details(observations)
            if not failures:
                failures = (
                    {
                        "document_id": None,
                        "stage": "evaluation",
                        "provider": "application",
                        "error_code": "unexpected_evaluation_error",
                        "retryable": False,
                    },
                )
            raise EvaluationRunIncomplete(
                failed,
                failures=failures,
                economics=economics,
            ) from exc
        finally:
            self._run_lock.release()

    def _all_runs(self, workspace_id: str) -> list[dict[str, Any]]:
        runs = self._public_runs()
        for record in self.history.list_recent(limit=100):
            report_workspace = record.report.get("workspace_id")
            if report_workspace not in {None, workspace_id}:
                continue
            runs.append(
                self._normalize_report(
                    record.report,
                    fallback_id=str(record.id),
                    dataset_name=record.dataset_name,
                    provider_name=record.provider_name,
                    created_at=record.created_at,
                    source="workspace_history",
                )
            )
        unique = {str(run["id"]): run for run in runs}
        return sorted(unique.values(), key=lambda run: str(run["observed_at"]), reverse=True)

    def _public_runs(self) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = []
        aggregate_path = PUBLIC_EVIDENCE_ROOT / "invoice-scenarios-v1-runs.json"
        if aggregate_path.is_file():
            aggregate = _read_json(aggregate_path)
            for raw in aggregate.get("runs", []):
                report = {
                    **raw,
                    "dataset_id": aggregate.get("dataset_id"),
                    "dataset_version": aggregate.get("dataset_version"),
                    "dataset_class": aggregate.get("dataset_class"),
                    "source_document": aggregate.get("source"),
                }
                runs.append(
                    self._normalize_report(
                        report,
                        fallback_id=str(raw.get("id")),
                        dataset_name=str(aggregate.get("dataset_id")),
                        provider_name=str(raw.get("provider")),
                        created_at=_observed_datetime(raw),
                        source="public_evidence",
                    )
                )
        for path in sorted(PUBLIC_EVIDENCE_ROOT.glob("external-invoice*.json")):
            report = _read_json(path)
            runs.append(
                self._normalize_report(
                    report,
                    fallback_id=path.stem,
                    dataset_name=str(report.get("dataset_class") or path.stem),
                    provider_name=str(report.get("provider") or "unknown"),
                    created_at=_observed_datetime(report),
                    source="public_evidence",
                )
            )
        return runs

    def _normalize_report(
        self,
        report: dict[str, Any],
        *,
        fallback_id: str,
        dataset_name: str,
        provider_name: str,
        created_at: datetime,
        source: str,
    ) -> dict[str, Any]:
        metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else report
        experiment = report.get("experiment") if isinstance(report.get("experiment"), dict) else {}
        economics = (
            report.get("provider_economics")
            if isinstance(report.get("provider_economics"), dict)
            else {}
        )
        cost = (
            economics.get("cost")
            if isinstance(economics.get("cost"), dict)
            else report.get("cost_estimate", {})
        )
        cost = cost if isinstance(cost, dict) else {}
        attempts = economics.get("attempts") if isinstance(economics.get("attempts"), dict) else {}
        dataset_id = str(report.get("dataset_id") or _slug(dataset_name))
        dataset_version = str(report.get("dataset_version") or "unversioned")
        split = str(report.get("split") or "diagnostic")
        fingerprint = experiment.get("dataset_fingerprint_sha256")
        observed_at = _observed_datetime(report)
        field_match = _number(metrics.get("field_accuracy"))
        validation_match = _number(metrics.get("validation_code_exact_match_rate"))
        passed = (
            field_match is not None
            and validation_match is not None
            and field_match >= FIELD_GATE
            and validation_match >= VALIDATION_GATE
        )
        duration_seconds, duration_kind = _duration(report, metrics)
        by_field = metrics.get("by_field") if isinstance(metrics.get("by_field"), dict) else {}
        run_id = str(
            fallback_id
            if source == "workspace_history"
            else experiment.get("experiment_id") or report.get("id") or fallback_id
        )
        limitations = [str(item) for item in report.get("limitations", [])]
        return {
            "id": run_id,
            "label": str(report.get("label") or f"{dataset_id} / {split}"),
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "dataset_class": str(report.get("dataset_class") or dataset_name),
            "split": split,
            "provider": str(report.get("provider") or provider_name),
            "source": source,
            "source_document": report.get("source_document"),
            "observed_at": observed_at.isoformat(),
            "documents": int(report.get("documents_count") or metrics.get("documents_total") or 0),
            "fields_matched": _integer(metrics.get("fields_matched")),
            "fields_total": _integer(metrics.get("fields_total")),
            "field_match": field_match,
            "validation_match": validation_match,
            "document_exact_match": _number(metrics.get("document_exact_match_rate")),
            "approval_blocker_accuracy": _number(metrics.get("approval_blocker_accuracy")),
            "provider_errors": int(
                report.get("provider_errors") or metrics.get("documents_failed") or 0
            ),
            "duration_seconds": duration_seconds,
            "duration_kind": duration_kind,
            "provider_calls": _optional_integer(attempts.get("total")),
            "estimated_cost_usd": _number(cost.get("estimated_total_usd")),
            "cost_status": cost.get("status"),
            "cost_claim": cost.get("claim_boundary"),
            "passed": passed,
            "verdict_available": validation_match is not None and field_match is not None,
            "by_field": {str(key): float(value) for key, value in by_field.items()},
            "failure_taxonomy": {
                str(key): int(value)
                for key, value in (report.get("failure_taxonomy") or {}).items()
            },
            "limitations": limitations,
            "series_key": f"{dataset_id}:{split}",
            "comparison_key": str(fingerprint or f"{dataset_id}:{dataset_version}:{split}"),
            "is_current": False,
        }

    @staticmethod
    def _select_run(runs: list[dict[str, Any]], run_id: str | None) -> dict[str, Any] | None:
        selected = next((run for run in runs if run["id"] == run_id), None) if run_id else None
        if selected is None:
            selected = next(
                (run for run in runs if run["verdict_available"]), runs[0] if runs else None
            )
        if selected is not None:
            selected = {**selected, "is_current": True}
        return selected

    @staticmethod
    def _previous_comparable(
        runs: list[dict[str, Any]], selected: dict[str, Any]
    ) -> dict[str, Any] | None:
        candidates = [
            run
            for run in runs
            if run["comparison_key"] == selected["comparison_key"]
            and run["observed_at"] < selected["observed_at"]
        ]
        return max(candidates, key=lambda run: str(run["observed_at"]), default=None)

    def _field_comparison(
        self,
        current: dict[str, Any],
        previous: dict[str, Any] | None,
    ) -> tuple[list[dict[str, object]], dict[str, object]]:
        current_fields = current["by_field"]
        previous_fields = previous["by_field"] if previous else {}
        rows: list[dict[str, object]] = []
        counts = Counter()
        for field_name, label in FIELD_LABELS.items():
            current_value = current_fields.get(field_name)
            previous_value = previous_fields.get(field_name)
            status = "excluded"
            delta_pp = None
            if current_value is not None and previous_value is not None:
                delta_pp = round((current_value - previous_value) * 100, 2)
                if current_value - previous_value > REGRESSION_TOLERANCE:
                    status = "improved"
                elif current_value - previous_value < -REGRESSION_TOLERANCE:
                    status = "regressed"
                else:
                    status = "stable"
            elif current_value is not None:
                status = "new"
            counts[status] += 1
            rows.append(
                {
                    "field": field_name,
                    "label": label,
                    "current": current_value,
                    "previous": previous_value,
                    "delta_pp": delta_pp,
                    "status": status,
                    "current_matches": (
                        round(current_value * int(current["documents"]))
                        if current_value is not None
                        else None
                    ),
                    "current_denominator": int(current["documents"]),
                    "previous_matches": (
                        round(previous_value * int(previous["documents"]))
                        if previous_value is not None and previous
                        else None
                    ),
                    "previous_denominator": int(previous["documents"]) if previous else None,
                }
            )
        comparable = counts["improved"] + counts["stable"] + counts["regressed"]
        return rows, {
            "comparison_run_id": previous["id"] if previous else None,
            "comparison_observed_at": previous["observed_at"] if previous else None,
            "tolerance_pp": REGRESSION_TOLERANCE * 100,
            "comparable_fields": comparable,
            "improved": counts["improved"],
            "stable": counts["stable"],
            "regressed": counts["regressed"],
            "new_fields": counts["new"],
            "excluded_fields": counts["excluded"],
            "new_failures": (
                sum(current["failure_taxonomy"].values())
                - sum(previous["failure_taxonomy"].values())
                if previous
                else None
            ),
        }

    def _scenario_coverage(self, selected: dict[str, Any] | None) -> dict[str, object]:
        expected = _read_json(SCENARIO_DATASET_ROOT / "expected.json")
        contract = _read_json(SCENARIO_DATASET_ROOT / "coverage.json")
        counts = Counter(str(item.get("scenario_category")) for item in expected)
        groups = []
        for group in contract["groups"]:
            current = sum(counts[str(category)] for category in group["categories"])
            target = int(group["target"])
            groups.append(
                {
                    "id": group["id"],
                    "label": group["label"],
                    "current": current,
                    "target": target,
                    "coverage": round(min(current / target, 1.0), 4) if target else None,
                    "remaining": max(target - current, 0),
                    "case_ids": [
                        str(item["document_id"])
                        for item in expected
                        if item.get("scenario_category") in group["categories"]
                    ],
                }
            )
        return {
            "dataset_id": contract["dataset_id"],
            "dataset_version": contract["dataset_version"],
            "claim_boundary": contract["claim_boundary"],
            "included_in_selected_run": bool(
                selected and selected["dataset_id"] == contract["dataset_id"]
            ),
            "groups": groups,
        }

    def _attempt_responses(self, workspace_id: str) -> list[dict[str, object]]:
        return [self._attempt_response(item) for item in self.attempts.list_recent(workspace_id)]

    def attempt_response(self, attempt: EvaluationAttemptRecord) -> dict[str, object]:
        return self._attempt_response(attempt)

    @staticmethod
    def _attempt_response(attempt: EvaluationAttemptRecord) -> dict[str, object]:
        return {
            "id": str(attempt.id),
            "status": attempt.status.value,
            "dataset_id": attempt.dataset_id,
            "dataset_version": attempt.dataset_version,
            "documents_requested": attempt.documents_requested,
            "documents_processed": attempt.documents_processed,
            "provider_calls": attempt.provider_calls,
            "run_id": str(attempt.run_id) if attempt.run_id else None,
            "error_code": attempt.error_code,
            "error_message": attempt.error_message,
            "requested_by": attempt.requested_by,
            "started_at": attempt.started_at.isoformat(),
            "completed_at": attempt.completed_at.isoformat() if attempt.completed_at else None,
        }

    @staticmethod
    def _selector_response(run: dict[str, Any], selected_id: str) -> dict[str, object]:
        return {
            "id": run["id"],
            "label": run["label"],
            "dataset_id": run["dataset_id"],
            "split": run["split"],
            "observed_at": run["observed_at"],
            "passed": run["passed"],
            "verdict_available": run["verdict_available"],
            "current": run["id"] == selected_id,
        }

    @staticmethod
    def _trend_response(run: dict[str, Any], selected_id: str) -> dict[str, object]:
        return {
            "id": run["id"],
            "observed_at": run["observed_at"],
            "field_match": run["field_match"],
            "validation_match": run["validation_match"],
            "documents": run["documents"],
            "provider_errors": run["provider_errors"],
            "estimated_cost_usd": run["estimated_cost_usd"],
            "selected": run["id"] == selected_id,
        }

    @staticmethod
    def _gates() -> dict[str, object]:
        return {
            "field_match": FIELD_GATE,
            "validation_match": VALIDATION_GATE,
            "regression_tolerance_pp": REGRESSION_TOLERANCE * 100,
        }

    def _limited_dataset(self, dataset: EvaluationDataset) -> EvaluationDataset:
        limit = max(1, self.settings.benchmark_real_provider_max_documents)
        return EvaluationDataset(
            name=dataset.name,
            documents=dataset.documents[:limit],
            root_path=dataset.root_path,
        )

    def _run_document(self, document_id: str, source_path: Path | None) -> dict[str, Any]:
        if source_path is None:
            raise ValueError(f"Evaluation source is missing for {document_id}.")
        source = DocumentSource(
            storage_key=document_id,
            path=source_path,
            original_filename=source_path.name,
            content_type="application/pdf",
        )
        started = time.perf_counter()
        attempts: list[dict[str, Any]] = []
        stage = "parser"
        try:
            parsed = self.parser.parse(source)
            attempts.append(
                _provider_attempt(
                    "parser", parsed.provider_name, parsed.provider_model, parsed.usage
                )
            )
            if not parsed.text:
                raise ProviderError("empty_parsed_text", self.parser.provider_name)
            stage = "extractor"
            result = self.extractor.extract_invoice(parsed)
            attempts.append(
                _provider_attempt(
                    "extractor", result.provider_name, result.provider_model, result.usage
                )
            )
            invoice = result.extraction.data
            confidence_fields = sorted({item.field_name for item in result.extraction.confidence})
            evidence_fields = sorted(
                {
                    item.field_name
                    for item in result.extraction.confidence
                    if item.source_page is not None
                    and item.source_text
                    and _evidence_exists(parsed, item.source_page, item.source_text)
                }
            )
            return {
                "document_id": document_id,
                "predicted_fields": invoice_data_to_fields(invoice),
                "predicted_validation_codes": sorted(
                    {issue.code for issue in validate_invoice(invoice).issues}
                ),
                "confidence_fields": confidence_fields,
                "evidence_fields": evidence_fields,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "provider_attempts": attempts,
                "error": None,
            }
        except ProviderError as exc:
            error_code = _safe_provider_error_code(exc)
            error = {
                "category": "provider_error",
                "stage": stage,
                "provider": exc.provider_name,
                "error_code": error_code,
                "retryable": exc.retryable,
            }
            attempts.append(
                {
                    "attempt": 1,
                    "stage": stage,
                    "status": "failed",
                    "provider": exc.provider_name,
                    "error": "provider_error",
                    "error_code": error_code,
                    "retryable": exc.retryable,
                }
            )
            return {
                "document_id": document_id,
                "predicted_fields": {},
                "predicted_validation_codes": [],
                "confidence_fields": [],
                "evidence_fields": [],
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "provider_attempts": attempts,
                "error": error,
            }


def _provider_attempt(stage: str, provider: str, model: str | None, usage: Any) -> dict[str, Any]:
    return {
        "attempt": 1,
        "stage": stage,
        "status": "succeeded",
        "provider": provider,
        "model": model,
        "usage": asdict(usage),
    }


def _safe_provider_error_code(exc: ProviderError) -> str:
    value = str(exc)
    if len(value) <= 80 and value.replace("_", "").isalnum():
        return value
    return "provider_request_failed"


def _failure_details(observations: list[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    failures: list[dict[str, Any]] = []
    for observation in observations:
        error = observation.get("error")
        if not error:
            continue
        if isinstance(error, dict):
            failures.append(
                {
                    "document_id": observation.get("document_id"),
                    "stage": error.get("stage") or "provider",
                    "provider": error.get("provider") or "unknown",
                    "error_code": error.get("error_code") or "provider_request_failed",
                    "retryable": bool(error.get("retryable")),
                }
            )
            continue
        failures.append(
            {
                "document_id": observation.get("document_id"),
                "stage": "provider",
                "provider": "unknown",
                "error_code": "provider_request_failed",
                "retryable": False,
            }
        )
    return tuple(failures)


def _evidence_exists(parsed: Any, page_number: int, source_text: str) -> bool:
    if parsed.pages:
        page = next((item for item in parsed.pages if item.page_number == page_number), None)
        return bool(page and source_text in page.text)
    return page_number == 1 and source_text in parsed.text


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _observed_datetime(report: dict[str, Any]) -> datetime:
    experiment = report.get("experiment") if isinstance(report.get("experiment"), dict) else {}
    value = (
        experiment.get("started_at")
        or report.get("started_at")
        or report.get("generated_at")
        or report.get("observed_on")
    )
    if not value:
        return datetime.now(UTC)
    text = str(value)
    if len(text) == 10:
        return datetime.combine(date.fromisoformat(text), datetime.min.time(), tzinfo=UTC)
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _duration(report: dict[str, Any], metrics: dict[str, Any]) -> tuple[float | None, str]:
    experiment = report.get("experiment") if isinstance(report.get("experiment"), dict) else {}
    started = experiment.get("started_at") or report.get("started_at")
    finished = report.get("finished_at") or report.get("generated_at")
    if started and finished:
        delta = _observed_datetime({"started_at": finished}) - _observed_datetime(
            {"started_at": started}
        )
        return round(max(delta.total_seconds(), 0.0), 2), "wall_clock"
    latency = (
        metrics.get("latency_ms")
        if isinstance(metrics.get("latency_ms"), dict)
        else metrics.get("latency", {})
    )
    average = _number(latency.get("average") if isinstance(latency, dict) else None)
    documents = int(report.get("documents_count") or metrics.get("documents_total") or 0)
    if average is not None and documents:
        return round(average * documents / 1000, 2), "summed_provider_latency"
    return None, "unavailable"


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int:
    return int(value) if value is not None else 0


def _optional_integer(value: Any) -> int | None:
    return int(value) if value is not None else None


def _slug(value: str) -> str:
    return "_".join(
        part for part in "".join(ch if ch.isalnum() else " " for ch in value.casefold()).split()
    )
