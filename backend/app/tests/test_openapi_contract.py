from __future__ import annotations

import unittest
from pathlib import Path

from app.core.settings import Settings
from app.main import create_app


class OpenApiContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = create_app(
            Settings(
                app_env="test",
                admin_token="test-token",
                upload_root=Path("uploads"),
                max_upload_bytes=1_000,
            )
        ).openapi()

    def test_every_api_operation_has_a_unique_operation_id_and_response_contract(self) -> None:
        operation_ids: list[str] = []
        for path, path_item in self.schema["paths"].items():
            if path.startswith("/ui"):
                continue
            for method, operation in path_item.items():
                if method not in {"get", "post", "put", "patch", "delete"}:
                    continue
                self.assertIn("operationId", operation, f"{method.upper()} {path}")
                self.assertTrue(operation.get("responses"), f"{method.upper()} {path}")
                operation_ids.append(operation["operationId"])
        self.assertEqual(len(operation_ids), len(set(operation_ids)))

    def test_product_metadata_describes_the_supported_document_operations_scope(self) -> None:
        info = self.schema["info"]
        self.assertEqual(info["title"], "AI Document Operations System")
        self.assertEqual(info["version"], "0.1.0")
        self.assertIn("Invoice is the first fully supported document workflow", info["description"])

    def test_critical_aggregate_and_mutation_contracts_are_published(self) -> None:
        expected = {
            ("/backoffice/workspace", "get"),
            ("/backoffice/work-items", "post"),
            ("/backoffice/work-items/{work_item_id}", "get"),
            ("/backoffice/work-items/{work_item_id}", "patch"),
            ("/backoffice/work-items/{work_item_id}/plan", "post"),
            ("/backoffice/approvals/{approval_id}/approve", "post"),
            ("/backoffice/approvals/{approval_id}/reject", "post"),
            ("/backoffice/work-items/{work_item_id}/steps/{action_step_id}/execute", "post"),
            ("/documents/{document_id}/workflow", "get"),
            ("/documents/{document_id}/retry", "post"),
            ("/documents/{document_id}/reprocess", "post"),
            ("/documents/{document_id}/cancel", "post"),
            ("/documents/{document_id}/request-correction", "post"),
            ("/documents/{document_id}/escalate", "post"),
            ("/invoices/{document_id}/workflow", "get"),
            ("/invoices/{document_id}/retry", "post"),
            ("/invoices/{document_id}/request-correction", "post"),
            ("/invoices/{document_id}/escalate", "post"),
            ("/operations/jobs/{job_id}/retry", "post"),
        }
        published = {
            (path, method)
            for path, item in self.schema["paths"].items()
            for method in item
            if method in {"get", "post", "put", "patch", "delete"}
        }
        self.assertTrue(expected.issubset(published), expected - published)

    def test_mutations_declare_json_or_validation_responses(self) -> None:
        for path, item in self.schema["paths"].items():
            for method in {"post", "put", "patch", "delete"}.intersection(item):
                operation = item[method]
                responses = operation["responses"]
                self.assertTrue(
                    any(code.startswith("2") for code in responses),
                    f"{method.upper()} {path} has no success response",
                )
                if operation.get("requestBody"):
                    self.assertIn("422", responses, f"{method.upper()} {path}")


if __name__ == "__main__":
    unittest.main()
