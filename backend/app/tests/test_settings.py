from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.core.settings import load_settings


class SettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_env = {
            key: os.environ.get(key)
            for key in (
                "ENV_FILE",
                "APP_ADMIN_TOKEN",
                "APP_UPLOADER_TOKEN",
                "APP_REVIEWER_TOKEN",
                "APP_WORKSPACE_ID",
                "PARSER_PROVIDER",
                "EXTRACTOR_PROVIDER",
                "MISTRAL_API_KEY",
                "DATABASE_URL",
                "DOCUMENT_STORAGE_BACKEND",
                "S3_ENDPOINT_URL",
                "S3_BUCKET",
                "S3_REGION",
                "S3_ACCESS_KEY_ID",
                "S3_SECRET_ACCESS_KEY",
                "MALWARE_SCANNER_BACKEND",
                "CLAMAV_HOST",
                "DOCUMENT_RETENTION_DAYS",
                "PARSER_CACHE_RETENTION_HOURS",
                "MISTRAL_ALLOWED_HOSTS",
                "EXTRACTOR_ALLOWED_HOSTS",
            )
        }
        for key in self.original_env:
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_load_settings_reads_env_file_without_printing_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env_file = Path(temp_dir) / ".env"
            env_file.write_text(
                "\n".join(
                    [
                        "APP_ADMIN_TOKEN=file-token",
                        "APP_UPLOADER_TOKEN=uploader-token",
                        "APP_REVIEWER_TOKEN=reviewer-token",
                        "APP_WORKSPACE_ID=finance-ops",
                        "PARSER_PROVIDER=mistral_ocr",
                        "EXTRACTOR_PROVIDER=llm_json",
                        "MISTRAL_API_KEY='mistral-secret'",
                        "DATABASE_URL=postgresql://docintel:docintel@db:5432/docintel",
                        "MAX_PROCESSING_ATTEMPTS=5",
                        "DOCUMENT_STORAGE_BACKEND=local",
                        "S3_ENDPOINT_URL=http://minio:9000",
                        "S3_BUCKET=docintel-private",
                        "S3_REGION=us-east-1",
                        "S3_ACCESS_KEY_ID=minio",
                        "S3_SECRET_ACCESS_KEY=minio-secret",
                        "MALWARE_SCANNER_BACKEND=clamav",
                        "CLAMAV_HOST=clamav.internal",
                        "DOCUMENT_RETENTION_DAYS=45",
                        "PARSER_CACHE_RETENTION_HOURS=12",
                        "MISTRAL_ALLOWED_HOSTS=api.mistral.ai,ocr.example.test",
                        "EXTRACTOR_ALLOWED_HOSTS=api.groq.com",
                    ]
                ),
                encoding="utf-8",
            )
            os.environ["ENV_FILE"] = str(env_file)

            settings = load_settings()

        self.assertEqual(settings.admin_token, "file-token")
        self.assertEqual(settings.uploader_token, "uploader-token")
        self.assertEqual(settings.reviewer_token, "reviewer-token")
        self.assertEqual(settings.workspace_id, "finance-ops")
        self.assertEqual(settings.parser_provider, "mistral_ocr")
        self.assertEqual(settings.extractor_provider, "llm_json")
        self.assertEqual(settings.mistral_api_key, "mistral-secret")
        self.assertEqual(
            settings.database_url,
            "postgresql://docintel:docintel@db:5432/docintel",
        )
        self.assertEqual(settings.max_processing_attempts, 5)
        self.assertEqual(settings.document_storage_backend, "local")
        self.assertEqual(settings.s3_endpoint_url, "http://minio:9000")
        self.assertEqual(settings.s3_bucket, "docintel-private")
        self.assertEqual(settings.s3_region, "us-east-1")
        self.assertEqual(settings.s3_access_key_id, "minio")
        self.assertEqual(settings.s3_secret_access_key, "minio-secret")
        self.assertEqual(settings.malware_scanner_backend, "clamav")
        self.assertEqual(settings.clamav_host, "clamav.internal")
        self.assertEqual(settings.document_retention_days, 45)
        self.assertEqual(settings.parser_cache_retention_hours, 12)
        self.assertEqual(
            settings.mistral_allowed_hosts,
            ("api.mistral.ai", "ocr.example.test"),
        )
        self.assertEqual(settings.extractor_allowed_hosts, ("api.groq.com",))

    def test_environment_variable_overrides_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env_file = Path(temp_dir) / ".env"
            env_file.write_text("APP_ADMIN_TOKEN=file-token", encoding="utf-8")
            os.environ["ENV_FILE"] = str(env_file)
            os.environ["APP_ADMIN_TOKEN"] = "shell-token"

            settings = load_settings()

        self.assertEqual(settings.admin_token, "shell-token")


if __name__ == "__main__":
    unittest.main()
