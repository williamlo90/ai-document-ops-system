from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from scripts import build_release_image, postgres_migrate


class ReleaseImageTests(unittest.TestCase):
    def test_release_build_refuses_a_dirty_worktree(self) -> None:
        with patch.object(build_release_image, "git_output", return_value=" M Dockerfile"):
            with self.assertRaisesRegex(RuntimeError, "clean container build inputs"):
                build_release_image.assert_clean_worktree()

    def test_release_build_accepts_a_clean_worktree(self) -> None:
        with patch.object(build_release_image, "git_output", return_value=""):
            build_release_image.assert_clean_worktree()


class MigrationEntrypointTests(unittest.TestCase):
    def test_migration_uses_database_url_from_environment(self) -> None:
        database_url = "postgresql://runtime:test@postgres/docintel"
        with (
            patch.dict(os.environ, {"DATABASE_URL": database_url}),
            patch.object(sys, "argv", ["postgres_migrate.py"]),
            patch.object(postgres_migrate, "apply_migrations", return_value=[]) as apply,
        ):
            self.assertEqual(postgres_migrate.main(), 0)

        apply.assert_called_once_with(database_url, postgres_migrate.default_migrations_dir())

    def test_runtime_contract_files_are_in_the_image_build_context(self) -> None:
        root = Path(__file__).resolve().parents[3]
        dockerignore = (root / ".dockerignore").read_text(encoding="utf-8")

        self.assertNotIn("scripts/", dockerignore)
        self.assertTrue((root / "scripts" / "container_runtime_smoke.py").is_file())


if __name__ == "__main__":
    unittest.main()
