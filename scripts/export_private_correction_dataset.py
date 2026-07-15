from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.api.dependencies import build_container
from app.core.settings import load_settings
from app.review.datasets import (
    assert_private_dataset_path,
    private_dataset_jsonl,
    sanitized_correction_summary,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export reviewer corrections to a Git-ignored private JSONL dataset."
    )
    parser.add_argument("--workspace", default="default")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "_private_data" / "reviewer-corrections.jsonl",
    )
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()

    try:
        output = assert_private_dataset_path(args.output, ROOT)
    except ValueError as exc:
        parser.error(str(exc))
    container = build_container(load_settings())
    try:
        events = container.correction_events.list_by_workspace(args.workspace)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(private_dataset_jsonl(events), encoding="utf-8")
        summary = sanitized_correction_summary(events)
        if args.summary:
            args.summary.parent.mkdir(parents=True, exist_ok=True)
            args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    finally:
        container.close()
    print(json.dumps({"output": str(output), **summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
