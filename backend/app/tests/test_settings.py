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
                "APP_METRICS_TOKEN",
                "APP_UPLOADER_TOKEN",
                "APP_REVIEWER_TOKEN",
                "APP_WORKSPACE_ID",
                "PARSER_PROVIDER",
                "EXTRACTOR_PROVIDER",
                "EXTRACTOR_ENDPOINT",
                "EXTRACTOR_MODEL",
                "MISTRAL_API_KEY",
                "DATABASE_URL",
                "DOCUMENT_STORAGE_BACKEND",
                "S3_ENDPOINT_URL",
                "S3_BUCKET",
                "S3_REGION",
                "S3_ACCESS_KEY_ID",
                "S3_SECRET_ACCESS_KEY",
                "AZURE_STORAGE_ACCOUNT_URL",
                "AZURE_STORAGE_CONNECTION_STRING",
                "AZURE_STORAGE_CONTAINER",
                "AZURE_MANAGED_IDENTITY_CLIENT_ID",
                "AZURE_STORAGE_TIMEOUT_SECONDS",
                "AZURE_STORAGE_CREATE_CONTAINER",
                "PROCESSING_QUEUE_BACKEND",
                "AZURE_SERVICE_BUS_NAMESPACE",
                "AZURE_SERVICE_BUS_CONNECTION_STRING",
                "AZURE_SERVICE_BUS_QUEUE_NAME",
                "AZURE_SERVICE_BUS_TIMEOUT_SECONDS",
                "AZURE_SERVICE_BUS_MAX_LOCK_RENEWAL_SECONDS",
                "AZURE_SERVICE_BUS_MAX_DELIVERY_COUNT",
                "MALWARE_SCANNER_BACKEND",
                "CLAMAV_HOST",
                "DOCUMENT_RETENTION_DAYS",
                "PARSER_CACHE_RETENTION_HOURS",
                "MISTRAL_ALLOWED_HOSTS",
                "EXTRACTOR_ALLOWED_HOSTS",
                "ERPNEXT_BASE_URL",
                "ERPNEXT_SITE",
                "ERPNEXT_API_USER",
                "ERPNEXT_API_KEY",
                "ERPNEXT_API_SECRET",
                "ERPNEXT_TIMEOUT_SECONDS",
                "ERPNEXT_ALLOWED_HOSTS",
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
                        "APP_METRICS_TOKEN=metrics-file-token",
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
                        "AZURE_STORAGE_ACCOUNT_URL=https://docs.blob.core.windows.net",
                        "AZURE_STORAGE_CONTAINER=private-documents",
                        "AZURE_MANAGED_IDENTITY_CLIENT_ID=managed-client-id",
                        "AZURE_STORAGE_TIMEOUT_SECONDS=20",
                        "AZURE_STORAGE_CREATE_CONTAINER=true",
                        "PROCESSING_QUEUE_BACKEND=azure-service-bus",
                        "AZURE_SERVICE_BUS_NAMESPACE=docs.servicebus.windows.net",
                        "AZURE_SERVICE_BUS_QUEUE_NAME=invoice-jobs",
                        "AZURE_SERVICE_BUS_TIMEOUT_SECONDS=15",
                        "AZURE_SERVICE_BUS_MAX_LOCK_RENEWAL_SECONDS=240",
                        "AZURE_SERVICE_BUS_MAX_DELIVERY_COUNT=7",
                        "MALWARE_SCANNER_BACKEND=clamav",
                        "CLAMAV_HOST=clamav.internal",
                        "DOCUMENT_RETENTION_DAYS=45",
                        "PARSER_CACHE_RETENTION_HOURS=12",
                        "MISTRAL_ALLOWED_HOSTS=api.mistral.ai,ocr.example.test",
                        "EXTRACTOR_ENDPOINT=https://api.openai.com/v1/chat/completions",
                        "EXTRACTOR_MODEL=gpt-5.4-mini-2026-03-17",
                        "EXTRACTOR_ALLOWED_HOSTS=api.openai.com",
                        "ERPNEXT_BASE_URL=http://127.0.0.1:8080",
                        "ERPNEXT_SITE=frontend",
                        "ERPNEXT_API_USER=invoice.integration@local.test",
                        "ERPNEXT_API_KEY=erp-key",
                        "ERPNEXT_API_SECRET=erp-secret",
                        "ERPNEXT_TIMEOUT_SECONDS=45",
                        "ERPNEXT_ALLOWED_HOSTS=127.0.0.1,localhost",
                    ]
                ),
                encoding="utf-8",
            )
            os.environ["ENV_FILE"] = str(env_file)

            settings = load_settings()

        self.assertEqual(settings.admin_token, "file-token")
        self.assertEqual(settings.metrics_token, "metrics-file-token")
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
        self.assertEqual(
            settings.azure_storage_account_url,
            "https://docs.blob.core.windows.net",
        )
        self.assertEqual(settings.azure_storage_container, "private-documents")
        self.assertEqual(settings.azure_managed_identity_client_id, "managed-client-id")
        self.assertEqual(settings.azure_storage_timeout_seconds, 20)
        self.assertTrue(settings.azure_storage_create_container)
        self.assertEqual(settings.processing_queue_backend, "azure-service-bus")
        self.assertEqual(
            settings.azure_service_bus_namespace,
            "docs.servicebus.windows.net",
        )
        self.assertEqual(settings.azure_service_bus_queue_name, "invoice-jobs")
        self.assertEqual(settings.azure_service_bus_timeout_seconds, 15)
        self.assertEqual(settings.azure_service_bus_max_lock_renewal_seconds, 240)
        self.assertEqual(settings.azure_service_bus_max_delivery_count, 7)
        self.assertEqual(settings.malware_scanner_backend, "clamav")
        self.assertEqual(settings.clamav_host, "clamav.internal")
        self.assertEqual(settings.document_retention_days, 45)
        self.assertEqual(settings.parser_cache_retention_hours, 12)
        self.assertEqual(
            settings.mistral_allowed_hosts,
            ("api.mistral.ai", "ocr.example.test"),
        )
        self.assertEqual(
            settings.extractor_endpoint,
            "https://api.openai.com/v1/chat/completions",
        )
        self.assertEqual(settings.extractor_model, "gpt-5.4-mini-2026-03-17")
        self.assertEqual(settings.extractor_allowed_hosts, ("api.openai.com",))
        self.assertEqual(settings.erpnext_base_url, "http://127.0.0.1:8080")
        self.assertEqual(settings.erpnext_site, "frontend")
        self.assertEqual(settings.erpnext_api_user, "invoice.integration@local.test")
        self.assertEqual(settings.erpnext_api_key, "erp-key")
        self.assertEqual(settings.erpnext_api_secret, "erp-secret")
        self.assertEqual(settings.erpnext_timeout_seconds, 45)
        self.assertEqual(settings.erpnext_allowed_hosts, ("127.0.0.1", "localhost"))

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
