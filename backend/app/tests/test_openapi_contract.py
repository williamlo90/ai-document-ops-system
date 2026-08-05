from __future__ import annotations

import unittest

from app.api.serializers import API_VERSION
from app.main import create_app


class OpenApiContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = create_app().openapi()

    def test_operations_have_unique_explicit_ids_and_responses(self) -> None:
        operation_ids: list[str] = []
        for path, path_item in self.schema["paths"].items():
            for method, operation in path_item.items():
                if method not in {"get", "post", "put", "patch", "delete"}:
                    continue
                self.assertIn("operationId", operation, f"{method.upper()} {path}")
                self.assertTrue(operation.get("responses"), f"{method.upper()} {path}")
                operation_ids.append(operation["operationId"])
        self.assertEqual(len(operation_ids), len(set(operation_ids)))

    def test_metadata_publishes_versioned_read_only_contract(self) -> None:
        metadata = self.schema["paths"]["/meta"]["get"]
        self.assertEqual(metadata["operationId"], "getServiceMetadata")
        self.assertIn("200", metadata["responses"])
        self.assertEqual(API_VERSION, "2026-08-05")
        self.assertFalse(any(method in {"post", "put", "patch", "delete"} for item in self.schema["paths"].values() for method in item))

    def test_problem_response_is_declared(self) -> None:
        response = self.schema["paths"]["/meta/{key}"]["get"]["responses"]["404"]
        schema = response["content"]["application/json"]["schema"]
        self.assertEqual(schema["$ref"], "#/components/schemas/ProblemResponse")


if __name__ == "__main__":
    unittest.main()
