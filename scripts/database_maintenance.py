from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from pathlib import Path
import shutil
import sqlite3
import subprocess


def backup_sqlite(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as source_db, sqlite3.connect(destination) as backup_db:
        source_db.backup(backup_db)
    return destination


def restore_sqlite(source: Path, destination: Path) -> Path:
    if not source.exists():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    with sqlite3.connect(destination) as database:
        result = database.execute("PRAGMA integrity_check").fetchone()
    if result is None or result[0] != "ok":
        raise RuntimeError("Restored SQLite database failed integrity_check")
    return destination


def backup_postgres(database_url: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["pg_dump", "--format=custom", "--file", str(destination), database_url],
        check=True,
    )
    return destination


def restore_postgres(database_url: str, source: Path) -> None:
    subprocess.run(
        [
            "pg_restore",
            "--clean",
            "--if-exists",
            "--no-owner",
            "--dbname",
            database_url,
            str(source),
        ],
        check=True,
    )


def prune(directory: Path, retention_days: int) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=max(retention_days, 1))
    removed = 0
    for path in directory.glob("docintel-*"):
        modified = datetime.fromtimestamp(path.stat().st_mtime, UTC)
        if path.is_file() and modified < cutoff:
            path.unlink()
            removed += 1
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description="Backup, restore, verify, and prune databases.")
    parser.add_argument(
        "action",
        choices=("backup-sqlite", "restore-sqlite", "backup-postgres", "restore-postgres", "prune"),
    )
    parser.add_argument("--source", type=Path)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--database-url")
    parser.add_argument("--directory", type=Path, default=Path("backups"))
    parser.add_argument("--retention-days", type=int, default=14)
    args = parser.parse_args()

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    if args.action == "backup-sqlite":
        source = args.source or Path("backend/data/doc_intel.sqlite3")
        destination = args.destination or args.directory / f"docintel-{timestamp}.sqlite3"
        print(backup_sqlite(source, destination))
    elif args.action == "restore-sqlite":
        if args.source is None:
            parser.error("--source is required")
        print(
            restore_sqlite(
                args.source, args.destination or Path("backend/data/restore-drill.sqlite3")
            )
        )
    elif args.action == "backup-postgres":
        if not args.database_url:
            parser.error("--database-url is required")
        destination = args.destination or args.directory / f"docintel-{timestamp}.dump"
        print(backup_postgres(args.database_url, destination))
    elif args.action == "restore-postgres":
        if not args.database_url or args.source is None:
            parser.error("--database-url and --source are required")
        restore_postgres(args.database_url, args.source)
    else:
        print(prune(args.directory, args.retention_days))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
