from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINIMUM_LINE_COVERAGE = 85.0
MINIMUM_BRANCH_COVERAGE = 75.0


def main() -> int:
    with tempfile.TemporaryDirectory() as temp_dir:
        report_path = Path(temp_dir) / "coverage.json"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "coverage",
                "json",
                "--omit=*/tests/*",
                "-o",
                str(report_path),
            ],
            cwd=ROOT,
            check=False,
        )
        if result.returncode != 0:
            return result.returncode
        totals = json.loads(report_path.read_text(encoding="utf-8"))["totals"]

    line_coverage = _percentage(totals["covered_lines"], totals["num_statements"])
    branch_coverage = _percentage(totals["covered_branches"], totals["num_branches"])
    print(
        "Backend coverage: "
        f"lines {line_coverage:.2f}% (minimum {MINIMUM_LINE_COVERAGE:.0f}%), "
        f"branches {branch_coverage:.2f}% (minimum {MINIMUM_BRANCH_COVERAGE:.0f}%)"
    )
    if line_coverage < MINIMUM_LINE_COVERAGE:
        print("Line coverage is below the enforced baseline.", file=sys.stderr)
        return 1
    if branch_coverage < MINIMUM_BRANCH_COVERAGE:
        print("Branch coverage is below the enforced baseline.", file=sys.stderr)
        return 1
    return 0


def _percentage(covered: int, total: int) -> float:
    return 100.0 if total == 0 else covered * 100.0 / total


if __name__ == "__main__":
    raise SystemExit(main())
