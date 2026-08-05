from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.benchmark.datasets import load_evaluation_dataset, records_from_dataset  # noqa: E402
from app.evaluation.external_holdout import build_external_evaluation_summary  # noqa: E402


def main() -> None:
    args = _arguments()
    pack_root = args.pack_root.resolve()
    private_result = args.private_result.resolve()
    if _is_relative_to(pack_root, ROOT) or _is_relative_to(private_result, ROOT):
        raise SystemExit("ERROR: pack and private result must remain outside the repository.")
    data = json.loads(private_result.read_text(encoding="utf-8"))
    observations = data.get("observations")
    if not isinstance(observations, list):
        raise SystemExit("ERROR: private result does not contain observations.")
    dataset = load_evaluation_dataset(pack_root / args.split)
    previous_summary = data.get("summary") or {}
    summary = build_external_evaluation_summary(
        records_from_dataset(dataset),
        observations,
        split=args.split,
        provider=str(previous_summary.get("provider") or "unknown"),
    )
    summary["generated_at"] = datetime.now(timezone.utc).isoformat()
    summary["holdout_seal_verified"] = previous_summary.get("holdout_seal_verified")
    summary["execution"] = previous_summary.get("execution") or {}
    _write_json(args.sanitized_output.resolve(), summary)
    print(f"Sanitized aggregate regenerated at {args.sanitized_output.resolve()}")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Regenerate sanitized metrics from a private external evaluation result."
    )
    parser.add_argument("pack_root", type=Path)
    parser.add_argument("private_result", type=Path)
    parser.add_argument("sanitized_output", type=Path)
    parser.add_argument("--split", choices=("diagnostic", "holdout"), required=True)
    return parser.parse_args()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


if __name__ == "__main__":
    main()
