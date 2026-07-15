from __future__ import annotations

import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "dist" / "public-ai-document-ops-system"

ALLOWLIST_TOP_LEVEL = {
    "README.md",
    "ROADMAP.md",
    "PRD.md",
    "ARCHITECTURE.md",
    "PORTFOLIO_CASE_STUDY.md",
    "RECRUITER_EVIDENCE_PACK.md",
    "SCENARIO_COVERAGE_MATRIX.md",
    "RUNBOOK.md",
    ".env.example",
    ".gitignore",
    ".dockerignore",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.production.yml",
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "run_tests.py",
    "sample_invoice.pdf",
}

ALLOWLIST_DIRECTORIES = {
    ".github",
    "backend",
    "docs",
    "examples",
    "frontend",
    "scripts",
}

ALLOWLIST_BACKEND = {
    "app",
    "migrations",
    "README.md",
}

EXCLUDE_ANYWHERE = {
    ".env",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "pembelajaran",
    "Implementation_plan",
    "delegation",
    "dist",
    "_local_docs",
    "_private_data",
    "node_modules",
    "playwright-report",
    "pivot",
    "test-results",
}

EXCLUDE_GLOB = {
    "*.pyc",
    "*.sqlite3",
    "*.sqlite",
    "*.db",
}


def _should_exclude(name: str) -> bool:
    if name in EXCLUDE_ANYWHERE:
        return True
    for pattern in EXCLUDE_GLOB:
        if name.endswith(pattern.replace("*", "")):
            return True
    return False


def _has_private_parent(path: Path) -> bool:
    for part in path.parts:
        if part in EXCLUDE_ANYWHERE:
            return True
    return False


def _copy_allowed(src: Path, dst: Path, allowed_items: set[str]) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for item in sorted(src.iterdir()):
        if _should_exclude(item.name):
            continue
        if item.name not in allowed_items:
            continue
        dest_path = dst / item.name
        if item.is_dir():
            _copy_tree(item, dest_path)
        else:
            shutil.copy2(item, dest_path)


def _copy_tree(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for item in sorted(src.iterdir()):
        if _should_exclude(item.name):
            continue
        if _has_private_parent(item):
            continue
        dest_path = dst / item.name
        if item.is_dir():
            _copy_tree(item, dest_path)
        else:
            shutil.copy2(item, dest_path)


def _fail_if_leaked(output: Path) -> None:
    leaked_dotenv = list(output.rglob(".env"))
    if leaked_dotenv:
        print("FAIL: .env found in output:", leaked_dotenv)
        sys.exit(1)

    leaked_sqlite = [p for p in output.rglob("*") if p.suffix in {".sqlite3", ".sqlite", ".db"}]
    if leaked_sqlite:
        print("FAIL: SQLite files found in output:", leaked_sqlite)
        sys.exit(1)

    leaked_uploads = [p for p in output.rglob("*") if "data" in p.parts and "uploads" in p.parts]
    if leaked_uploads:
        print("FAIL: Upload data found in output:", leaked_uploads)
        sys.exit(1)

    leaked_private_data = [p for p in output.rglob("*") if "_private_data" in p.parts]
    if leaked_private_data:
        print("FAIL: Private evaluation data found in output:", leaked_private_data)
        sys.exit(1)


def _summary(output: Path) -> None:
    print(f"Output: {output}")
    top = sorted(
        p
        for p in output.iterdir()
        if p.is_dir() or (p.is_file() and p.name not in {".gitignore", ".dockerignore"})
    )
    for entry in top:
        if entry.is_dir():
            count = sum(1 for _ in entry.rglob("*"))
            print(f"  [DIR] {entry.name}/  ({count} items)")
        else:
            size = entry.stat().st_size
            print(f"  [FILE] {entry.name}  ({size} bytes)")


def main() -> None:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT

    if output == ROOT:
        raise SystemExit("Refusing to copy into the project root itself.")

    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    for filename in ALLOWLIST_TOP_LEVEL:
        src = ROOT / filename
        if src.exists():
            if src.is_file():
                shutil.copy2(src, output / filename)

    for dirname in ALLOWLIST_DIRECTORIES:
        src = ROOT / dirname
        if src.is_dir():
            if dirname == "backend":
                _copy_allowed(src, output / dirname, ALLOWLIST_BACKEND)
            else:
                _copy_tree(src, output / dirname)

    _fail_if_leaked(output)
    _summary(output)
    print("\nPublic artifact ready. Review the output before sharing.")


if __name__ == "__main__":
    main()
