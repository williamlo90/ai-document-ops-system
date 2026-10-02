from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence


REQUIRED_STAGES = {
    "api": ("request_completed",),
    "publish": ("queue_wakeup_published",),
    "worker": ("queue_message_completed", "queue_message_dead_lettered"),
    "terminal": ("processing_succeeded", "processing_failed", "processing_dead_lettered"),
}


def build_trace_query(trace_id: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{32}", trace_id):
        raise ValueError("trace ID must contain exactly 32 lowercase hexadecimal characters")
    return "\n".join(
        [
            "ContainerAppConsoleLogs_CL",
            f'| where Log_s has "{trace_id}"',
            "| project TimeGenerated, ContainerAppName_s, RevisionName_s, Log_s",
            "| order by TimeGenerated asc",
        ]
    )


def evaluate_trace_rows(rows: list[dict[str, object]]) -> dict[str, object]:
    serialized_rows = [json.dumps(row, sort_keys=True) for row in rows]
    stages: dict[str, dict[str, object]] = {}
    for stage, accepted_events in REQUIRED_STAGES.items():
        matched = [
            event
            for event in accepted_events
            if any(event in serialized for serialized in serialized_rows)
        ]
        stages[stage] = {"passed": bool(matched), "matched_events": matched}
    return {
        "passed": all(bool(value["passed"]) for value in stages.values()),
        "row_count": len(rows),
        "stages": stages,
    }


def query_trace(*, workspace_id: str, trace_id: str, timespan: str) -> list[dict[str, object]]:
    result = subprocess.run(
        [
            "az",
            "monitor",
            "log-analytics",
            "query",
            "--workspace",
            workspace_id,
            "--analytics-query",
            build_trace_query(trace_id),
            "--timespan",
            timespan,
            "--output",
            "json",
            "--only-show-errors",
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("Azure Log Analytics trace query failed")
    payload = json.loads(result.stdout)
    if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
        raise RuntimeError("Azure Log Analytics returned an unexpected response")
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify API-to-worker trace correlation.")
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--trace-id", required=True)
    parser.add_argument("--timespan", default="PT1H")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    rows = query_trace(
        workspace_id=args.workspace_id,
        trace_id=args.trace_id,
        timespan=args.timespan,
    )
    evaluation = evaluate_trace_rows(rows)
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "trace_id": args.trace_id,
        "evaluation": evaluation,
        "events": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Trace correlation: {'PASSED' if evaluation['passed'] else 'FAILED'}")
    print(f"Report: {args.output}")
    return 0 if evaluation["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
