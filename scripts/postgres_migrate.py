from __future__ import annotations

import argparse
import os
from pathlib import Path


def default_migrations_dir() -> Path:
    repository_path = Path("backend/migrations/postgres")
    return repository_path if repository_path.exists() else Path("migrations/postgres")


def apply_migrations(database_url: str, migrations_dir: Path) -> list[int]:
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("Install psycopg with: pip install 'psycopg[binary]'") from exc

    files = sorted(migrations_dir.glob("*.sql"))
    applied: list[int] = []
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            # Serialize deploy-time migration runners for the lifetime of this
            # transaction. A failed migration rolls the whole batch back.
            cursor.execute("SELECT pg_advisory_xact_lock(786234901)")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cursor.execute("SELECT version FROM schema_migrations")
            existing = {row[0] for row in cursor.fetchall()}
            for path in files:
                version_text = path.stem.split("_", 1)[0]
                version = int(version_text)
                if version in existing:
                    continue
                cursor.execute(path.read_text(encoding="utf-8"))
                cursor.execute(
                    "INSERT INTO schema_migrations (version, name) VALUES (%s, %s)",
                    (version, path.name),
                )
                applied.append(version)
        connection.commit()
    return applied


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply ordered PostgreSQL migrations.")
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        help="PostgreSQL URL. Defaults to DATABASE_URL so credentials do not appear in argv.",
    )
    parser.add_argument(
        "--migrations-dir",
        type=Path,
        default=default_migrations_dir(),
    )
    args = parser.parse_args()
    if not args.database_url:
        parser.error("DATABASE_URL or --database-url is required")
    versions = apply_migrations(args.database_url, args.migrations_dir)
    print("Applied:", ", ".join(map(str, versions)) if versions else "none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
