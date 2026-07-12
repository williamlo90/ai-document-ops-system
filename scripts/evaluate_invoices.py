from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.evaluation.invoice import evaluate_invoices, report_to_dict  # noqa: E402


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python scripts/evaluate_invoices.py expected.json predicted.json")
    expected = _load_records(Path(sys.argv[1]))
    predicted = _load_records(Path(sys.argv[2]))
    report = evaluate_invoices(expected, predicted)
    print(json.dumps(report_to_dict(report), indent=2))


def _load_records(path: Path) -> list[dict[str, object]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON list")
    return data


if __name__ == "__main__":
    main()
