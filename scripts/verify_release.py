from __future__ import annotations

import argparse
import json
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
DEFAULT_EVIDENCE = ROOT / "docs" / "evidence" / "release-verification.json"
RUNTIME_REQUIREMENTS = (
    ROOT / "requirements-windows.txt" if sys.platform == "win32" else ROOT / "requirements.txt"
)


def main() -> int:
    args = _arguments()
    if args.write_evidence and _git("status", "--porcelain"):
        print("ERROR: release evidence requires a clean worktree.", file=sys.stderr)
        return 2

    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if npm is None:
        print("ERROR: npm is not available.", file=sys.stderr)
        return 2
    node = shutil.which("node.exe") or shutil.which("node")
    if node is None:
        print("ERROR: node is not available.", file=sys.stderr)
        return 2

    checks = [
        Check(
            "python_dependency_audit",
            [
                sys.executable,
                "-m",
                "pip_audit",
                "--requirement",
                str(RUNTIME_REQUIREMENTS),
                "--disable-pip",
                "--strict",
            ],
        ),
        Check(
            "python_format",
            [
                sys.executable,
                "-m",
                "ruff",
                "format",
                "--check",
                "backend",
                "scripts",
                "run_tests.py",
            ],
        ),
        Check(
            "python_lint",
            [sys.executable, "-m", "ruff", "check", "backend", "scripts", "run_tests.py"],
        ),
        Check("backend_types", [sys.executable, "-m", "mypy"]),
        Check(
            "backend_tests",
            [
                sys.executable,
                "-m",
                "coverage",
                "run",
                "--branch",
                "--source=backend/app",
                "run_tests.py",
            ],
        ),
        Check("coverage_gate", [sys.executable, "scripts/coverage_gate.py"]),
        Check("complexity_gate", [sys.executable, "scripts/quality_report.py"]),
        Check("frontend_dependency_audit", [npm, "run", "audit"], cwd=FRONTEND),
        Check("frontend_format", [npm, "run", "format:check"], cwd=FRONTEND),
        Check("frontend_lint", [npm, "run", "lint"], cwd=FRONTEND),
        Check("frontend_tests", [npm, "run", "test"], cwd=FRONTEND),
        Check("frontend_build", [npm, "run", "build"], cwd=FRONTEND),
    ]
    if not args.skip_browser:
        checks.extend(
            [
                Check("browser_tests", [npm, "run", "test:e2e"], cwd=FRONTEND),
                Check(
                    "fullstack_browser_test",
                    [npm, "run", "test:e2e:fullstack"],
                    cwd=FRONTEND,
                ),
            ]
        )

    results = []
    failed = False
    for check in checks:
        result = _run(check)
        results.append(result)
        state = "PASS" if result["passed"] else "FAIL"
        print(f"[{state}] {check.name} ({result['duration_seconds']:.2f}s)")
        if not result["passed"]:
            failed = True
            print(result["output_tail"], file=sys.stderr)

    if failed:
        print("Release verification failed; no evidence file was written.", file=sys.stderr)
        return 1

    evidence = {
        "schema_version": "release_verification_v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "source": {
            "git_commit": _git("rev-parse", "HEAD"),
            "worktree_clean_at_start": True,
            "branch": _git("branch", "--show-current"),
        },
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "node": _version(node, "--version"),
            "npm": _version(npm, "--version"),
        },
        "counts": _counts(results),
        "dependency_exceptions": _dependency_exceptions(),
        "checks": [
            {
                "name": result["name"],
                "passed": result["passed"],
                "duration_seconds": result["duration_seconds"],
            }
            for result in results
        ],
        "claim_boundary": [
            "Local verification is not an independent security assessment.",
            "Browser fixture tests and one real local full-stack journey are both included.",
            "Real-provider evaluation is recorded separately and is not run by this gate.",
        ],
    }
    if args.write_evidence:
        args.write_evidence.parent.mkdir(parents=True, exist_ok=True)
        args.write_evidence.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        print(f"Evidence written to {args.write_evidence}")
    else:
        print(json.dumps(evidence["counts"], indent=2))
    return 0


class Check:
    def __init__(self, name: str, command: list[str], cwd: Path = ROOT) -> None:
        self.name = name
        self.command = command
        self.cwd = cwd


def _run(check: Check) -> dict[str, Any]:
    started = time.perf_counter()
    completed = subprocess.run(
        check.command,
        cwd=check.cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = f"{completed.stdout}\n{completed.stderr}".strip()
    return {
        "name": check.name,
        "passed": completed.returncode == 0,
        "duration_seconds": round(time.perf_counter() - started, 3),
        "output": output,
        "output_tail": "\n".join(output.splitlines()[-40:]),
    }


def _counts(results: list[dict[str, Any]]) -> dict[str, int]:
    by_name = {str(result["name"]): str(result["output"]) for result in results}
    counts: dict[str, int] = {}
    backend = re.search(r"Ran (\d+) tests?", by_name.get("backend_tests", ""))
    backend_skipped = re.search(r"skipped=(\d+)", by_name.get("backend_tests", ""))
    frontend = re.search(r"Tests\s+(\d+) passed", by_name.get("frontend_tests", ""))
    browser = re.search(r"(\d+) passed", by_name.get("browser_tests", ""))
    fullstack = re.search(r"(\d+) passed", by_name.get("fullstack_browser_test", ""))
    if backend:
        counts["backend_tests"] = int(backend.group(1))
    if backend_skipped:
        counts["backend_tests_skipped"] = int(backend_skipped.group(1))
    if frontend:
        counts["frontend_tests"] = int(frontend.group(1))
    if browser:
        counts["browser_tests"] = int(browser.group(1))
    if fullstack:
        counts["fullstack_browser_tests"] = int(fullstack.group(1))
    return counts


def _dependency_exceptions() -> list[dict[str, Any]]:
    path = FRONTEND / "audit-allowlist.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return list(payload.get("advisories") or [])


def _version(executable: str, argument: str) -> str:
    completed = subprocess.run(
        [executable, argument],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return completed.stdout.strip()


def _git(*arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return completed.stdout.strip()


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the local release gate and record its result."
    )
    parser.add_argument(
        "--write-evidence",
        nargs="?",
        type=Path,
        const=DEFAULT_EVIDENCE,
        help="Write machine-readable evidence after a clean, passing run.",
    )
    parser.add_argument(
        "--skip-browser",
        action="store_true",
        help="Skip Playwright suites for a faster non-release check.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
