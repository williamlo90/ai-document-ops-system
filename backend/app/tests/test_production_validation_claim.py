from __future__ import annotations

import unittest
from pathlib import Path

from app.core.settings import Settings
from app.main import create_app
from app.production_validation_claim import ValidationGuardError, validate_claim_guards


class ProductionValidationClaimGuardTests(unittest.TestCase):
    def test_accepts_only_explicit_isolated_mock_production_profile(self) -> None:
        settings = self._settings()

        validate_claim_guards(
            settings,
            requested_run_id="pg01-20261002t120000z-abcd1234",
            configured_run_id="pg01-20261002t120000z-abcd1234",
            confirmed=True,
        )

    def test_rejects_normal_runtime_and_mismatched_run_id(self) -> None:
        settings = self._settings(
            app_env="local",
            workspace_id="default",
            parser_provider="mistral_ocr",
            extractor_provider="llm_json",
        )

        with self.assertRaises(ValidationGuardError) as raised:
            validate_claim_guards(
                settings,
                requested_run_id="pg01-20261002t120000z-abcd1234",
                configured_run_id="pg01-different-run",
                confirmed=False,
            )

        message = str(raised.exception)
        self.assertIn("APP_ENV must equal production", message)
        self.assertIn("APP_WORKSPACE_ID must equal azure-validation", message)
        self.assertIn("PARSER_PROVIDER must equal mock", message)
        self.assertIn("EXTRACTOR_PROVIDER must equal mock", message)
        self.assertIn("run ID must exactly match", message)
        self.assertIn("explicit lease-abandonment confirmation", message)

    def test_fault_command_is_not_exposed_as_an_http_route(self) -> None:
        app = create_app(
            self._settings(
                app_env="local",
                workspace_id="default",
                storage_backend="memory",
                database_url=None,
                malware_scanner_backend="signature",
            )
        )
        try:
            paths = {getattr(route, "path", "") for route in app.routes}
        finally:
            app.state.container.close()

        self.assertFalse(any("claim-and-exit" in path for path in paths))
        self.assertFalse(any("production-validation" in path for path in paths))

    @staticmethod
    def _settings(**overrides: object) -> Settings:
        values: dict[str, object] = {
            "app_env": "production",
            "admin_token": "a" * 24,
            "upload_root": Path("/tmp/uploads"),
            "max_upload_bytes": 1_000,
            "metrics_token": "m" * 24,
            "workspace_id": "azure-validation",
            "storage_backend": "postgres",
            "database_url": "postgresql://validation.invalid/db",
            "parser_provider": "mock",
            "extractor_provider": "mock",
        }
        values.update(overrides)
        return Settings(**values)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
