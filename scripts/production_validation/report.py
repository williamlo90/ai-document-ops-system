from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from scripts.production_validation.models import CheckResult, RequestSample


def build_report(
    *,
    manifest: dict[str, object],
    summary: dict[str, object],
    checks: list[CheckResult],
    samples: list[RequestSample],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "passed" if checks and all(check.passed for check in checks) else "failed",
        "manifest": manifest,
        "summary": summary,
        "checks": [asdict(check) for check in checks],
        "samples": [asdict(sample) for sample in samples],
    }


def write_report(report: dict[str, object], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=False)
    json_path = output_dir / "production-validation-report.json"
    markdown_path = output_dir / "production-validation-report.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def render_markdown(report: dict[str, object]) -> str:
    manifest = _dict(report["manifest"])
    summary = _dict(report["summary"])
    checks = report["checks"]
    operations = _dict(summary["operations"])
    lines = [
        "# Production Validation Report",
        "",
        f"- Status: **{str(report['status']).upper()}**",
        f"- Run ID: `{manifest['run_id']}`",
        f"- Scope: `{manifest['scope']}`",
        f"- Target label: `{manifest['target_label']}`",
        f"- Source revision: `{manifest['source_revision']}`",
        f"- Source worktree dirty: `{str(manifest.get('source_dirty', 'unknown')).lower()}`",
        f"- Started: `{manifest['started_at']}`",
        f"- Completed: `{manifest['completed_at']}`",
        "",
        "## Request Summary",
        "",
        "| Operation | Count | Expected | Failures | p50 ms | p90 ms | p95 ms | p99 ms |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for operation, raw_value in operations.items():
        value = _dict(raw_value)
        lines.append(
            f"| {operation} | {value['count']} | {value['expected_responses']} | "
            f"{value['unexpected_failures']} | {_display(value['p50_ms'])} | "
            f"{_display(value['p90_ms'])} | {_display(value['p95_ms'])} | "
            f"{_display(value['p99_ms'])} |"
        )
    lines.extend(
        [
            "",
            f"Overall availability: **{summary['availability_percent']}%**  ",
            f"Unexpected 5xx rate: **{summary['unexpected_5xx_percent']}%**  ",
            f"Aggregate throughput: **{summary['throughput_rps']} requests/second**",
            "",
            "## Acceptance Checks",
            "",
            "| Result | Check | Expected | Observed |",
            "| --- | --- | --- | --- |",
        ]
    )
    if not isinstance(checks, list):
        raise TypeError("report checks must be a list")
    for raw_check in checks:
        check = _dict(raw_check)
        result = "PASS" if check["passed"] else "FAIL"
        lines.append(
            f"| {result} | `{check['code']}` | {check['expected']} | {check['observed']} |"
        )
    lines.extend(
        [
            "",
            "This report contains synthetic identifiers and measurements only. Authentication "
            "tokens and the target URL are intentionally excluded.",
            "",
        ]
    )
    return "\n".join(lines)


def _dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError("expected a dictionary")
    return value


def _display(value: object) -> str:
    return "-" if value is None else str(value)

