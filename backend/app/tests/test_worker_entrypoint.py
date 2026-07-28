from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.core.settings import Settings
from app.worker import run_once


class WorkerEntrypointTests(unittest.TestCase):
    def test_worker_uses_the_configured_workspace(self) -> None:
        settings = Settings(
            app_env="test",
            admin_token="test-token",
            upload_root=Path("uploads"),
            max_upload_bytes=1_000,
            workspace_id="finance-ops",
        )
        worker_service = Mock()
        worker_service.run_once.return_value = object()
        container = SimpleNamespace(worker_service=worker_service)

        with (
            patch("app.worker.load_settings", return_value=settings),
            patch("app.worker.build_container", return_value=container),
        ):
            processed = run_once()

        self.assertTrue(processed)
        context = worker_service.run_once.call_args.kwargs["context"]
        self.assertEqual(context.workspace_id, "finance-ops")
        self.assertEqual(context.role, "admin")
        self.assertTrue(context.is_admin)


if __name__ == "__main__":
    unittest.main()
