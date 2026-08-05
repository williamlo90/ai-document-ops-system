from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from time import perf_counter
from typing import Any
from uuid import uuid4
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]


class VerificationError(RuntimeError):
    pass


def _run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=capture,
        check=False,
    )
    if result.returncode != 0:
        detail = ""
        if capture:
            detail = f"\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        raise VerificationError(
            f"Command failed ({result.returncode}): {' '.join(command)}{detail}"
        )
    return result


def _git(*args: str, capture: bool = True) -> str:
    result = _run(["git", *args], cwd=ROOT, capture=capture)
    return result.stdout.strip() if capture else ""


def _load_manifest() -> dict[str, Any]:
    return json.loads((ROOT / "milestones" / "manifest.json").read_text(encoding="utf-8"))


def _milestone(manifest: dict[str, Any], number: int) -> dict[str, Any]:
    milestone_id = f"M{number:02d}"
    for item in manifest["milestones"]:
        if item["id"] == milestone_id:
            return item
    raise VerificationError(f"Milestone is not declared: {milestone_id}")


def _assert_clean_tag(tag: str) -> str:
    commit = _git("rev-list", "-n", "1", tag)
    if not commit:
        raise VerificationError(f"Tag does not resolve: {tag}")
    head = _git("rev-parse", "HEAD")
    if commit != head:
        raise VerificationError(f"{tag} resolves to {commit}, but HEAD is {head}")
    if _git("status", "--porcelain"):
        raise VerificationError("Working tree must be clean before cumulative verification")
    return commit


def _assert_required_paths(item: dict[str, Any], root: Path) -> None:
    missing = [path for path in item["required_paths"] if not (root / path).is_file()]
    if missing:
        raise VerificationError(f"Required milestone files are missing: {', '.join(missing)}")


def _focused_command(item: dict[str, Any], root: Path) -> list[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "backend")
    env["ENV_FILE"] = r"C:\__codex_no_env__"
    command = [sys.executable, "-m", "unittest", *item["focused_modules"]]
    _run(command, cwd=root, env=env)
    return command


def _safe_replace_directory(path: Path, parent: Path) -> None:
    resolved_parent = parent.resolve()
    resolved_path = path.resolve()
    if resolved_path.parent != resolved_parent:
        raise VerificationError(f"Refusing to replace path outside snapshot root: {resolved_path}")
    if resolved_path.exists():
        shutil.rmtree(resolved_path)
    resolved_path.mkdir(parents=True)


def _write_snapshot(item: dict[str, Any], commit: str, snapshot_root: Path) -> tuple[Path, str]:
    destination = snapshot_root / f"{item['id']}-{item['slug']}"
    snapshot_root.mkdir(parents=True, exist_ok=True)
    _safe_replace_directory(destination, snapshot_root)

    archive = destination / "source.zip"
    _run(
        ["git", "archive", "--format=zip", f"--output={archive}", item["tag"]],
        cwd=ROOT,
    )
    archive_hash = sha256(archive.read_bytes()).hexdigest()
    (destination / "source.sha256").write_text(f"{archive_hash}\n", encoding="ascii")
    (destination / "commit.txt").write_text(f"{commit}\n", encoding="ascii")
    (destination / "changed-files.txt").write_text(
        _git("ls-tree", "-r", "--name-only", item["tag"]) + "\n",
        encoding="utf-8",
    )
    patch = _git("show", "--binary", "--format=", "--root", item["tag"])
    (destination / "milestone.patch").write_text(patch + "\n", encoding="utf-8")

    replay_root = snapshot_root / f".replay-{item['id'].lower()}-{uuid4().hex}"
    replay_root.mkdir()
    try:
        with ZipFile(archive) as bundle:
            bundle.extractall(replay_root)
        _assert_required_paths(item, replay_root)
        _focused_command(item, replay_root)
        shutil.copy2(
            replay_root / "reconstruction" / "provenance" / f"{item['id'].lower()}.csv",
            destination / "provenance.csv",
        )
    finally:
        if replay_root.parent.resolve() != snapshot_root.resolve():
            raise VerificationError("Replay root escaped the configured snapshot root")
        shutil.rmtree(replay_root, ignore_errors=True)

    checkout = (
        "param([Parameter(Mandatory=$true)][string]$Destination)\n"
        "$ErrorActionPreference = 'Stop'\n"
        f"Expand-Archive -LiteralPath '{archive}' -DestinationPath $Destination\n"
        f"Write-Host 'Extracted {item['tag']} ({commit})'\n"
    )
    (destination / "checkout.ps1").write_text(checkout, encoding="utf-8")
    return destination, archive_hash


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--through", type=int, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--snapshot-root", type=Path, required=True)
    args = parser.parse_args()

    if args.through != 1:
        raise VerificationError("This repository state can verify only M01")

    manifest = _load_manifest()
    item = _milestone(manifest, args.through)
    if args.tag != item["tag"]:
        raise VerificationError(f"Expected tag {item['tag']}; received {args.tag}")

    commit = _assert_clean_tag(args.tag)
    _assert_required_paths(item, ROOT)
    started = perf_counter()
    command = _focused_command(item, ROOT)
    snapshot, archive_hash = _write_snapshot(item, commit, args.snapshot_root.resolve())
    duration = perf_counter() - started

    evidence_dir = args.evidence_root.resolve() / item["id"]
    evidence_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "schema_version": 1,
        "milestone": item["id"],
        "tag": item["tag"],
        "commit": commit,
        "status": "passed",
        "command": command,
        "python": sys.version,
        "platform": sys.platform,
        "environment_file": r"C:\__codex_no_env__",
        "snapshot": str(snapshot),
        "snapshot_sha256": archive_hash,
        "duration_seconds": round(duration, 3),
        "recorded_at": datetime.now(UTC).isoformat(),
        "limitations": [
            "M01 proves only local walking-skeleton behavior.",
            "The archive replay reuses the already installed hash-locked environment.",
            "No invoice, persistence, AI, UI, production, or customer claim is evaluated.",
        ],
    }
    result_path = evidence_dir / "result.json"
    result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"M01 cumulative verification passed for {commit}")
    print(f"Evidence: {result_path}")
    print(f"Snapshot: {snapshot}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except VerificationError as exc:
        print(f"verification failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
