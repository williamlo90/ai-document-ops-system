from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.backoffice.models import WorkType
from app.backoffice.planner import PlanningInput
from app.core.security import SecurityContext
from app.core.settings import Settings
from app.main import create_app
from app.tests.auth_helpers import session_headers


TOKEN = "test-token"
HEADERS = {"X-Admin-Token": TOKEN}


class AgentOpsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        settings = Settings(
            app_env="test",
            admin_token=TOKEN,
            upload_root=Path(self.temp_dir.name),
            max_upload_bytes=1000,
        )
        self.client = TestClient(create_app(settings))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_agentops_requires_admin_token(self) -> None:
        response = self.client.get("/agentops/summary")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Unauthorized")

    def test_summary_empty_state_is_honest(self) -> None:
        response = self.client.get("/agentops/summary", headers=HEADERS)

        self.assertEqual(response.status_code, 200)
        summary = response.json()["summary"]
        self.assertEqual(summary["total_runs"], 0)
        self.assertIsNone(summary["tool_selection_accuracy"])
        self.assertEqual(summary["confidence_distribution"], {})

    def test_agentops_lists_runs_and_summary_from_copilot_traces(self) -> None:
        self.client.post(
            "/agent/copilot",
            headers=HEADERS,
            json={
                "message": "Summarize workflow metrics and cost",
                "expected_tool": "get_metrics_summary",
            },
        )
        self.client.post(
            "/agent/copilot",
            headers=HEADERS,
            json={
                "message": "What needs review today?",
                "expected_tool": "list_review_queue",
            },
        )

        list_response = self.client.get("/agentops/runs", headers=HEADERS)
        summary_response = self.client.get("/agentops/summary", headers=HEADERS)

        self.assertEqual(list_response.status_code, 200)
        runs = list_response.json()["runs"]
        self.assertEqual(len(runs), 2)
        self.assertEqual(runs[0]["workspace_id"], "default")
        self.assertIn("evaluation", runs[0])
        self.assertIn("decision_reason", runs[0]["evaluation"])

        summary = summary_response.json()["summary"]
        self.assertEqual(summary["total_runs"], 2)
        self.assertEqual(summary["evaluated_runs"], 2)
        self.assertEqual(summary["tool_selection_accuracy"], 1.0)
        self.assertEqual(summary["prompt_versions"][0]["prompt_version"], "deterministic-v1")

    def test_run_detail_is_workspace_scoped_and_includes_trace_without_payload_leakage(
        self,
    ) -> None:
        created = self.client.post(
            "/agent/copilot",
            headers=HEADERS,
            json={
                "message": "Summarize workflow metrics and cost",
                "expected_tool": "get_metrics_summary",
            },
        )
        run_id = created.json()["run"]["id"]

        detail_response = self.client.get(f"/agentops/runs/{run_id}", headers=HEADERS)
        other_workspace_response = self.client.get(
            f"/agentops/runs/{run_id}",
            headers=session_headers(
                self.client,
                actor="other-admin",
                workspace_id="other",
            ),
        )

        self.assertEqual(detail_response.status_code, 200)
        detail = detail_response.json()
        self.assertEqual(detail["id"], run_id)
        self.assertEqual(detail["tool_calls"][0]["tool_name"], "get_metrics_summary")
        self.assertNotIn("data", detail["tool_calls"][0])
        self.assertNotIn("evidence", detail["tool_calls"][0])
        self.assertEqual(other_workspace_response.status_code, 404)

    def test_prompt_versions_and_regression_endpoints_return_comparison_shapes(self) -> None:
        for _ in range(2):
            self.client.post(
                "/agent/copilot",
                headers=HEADERS,
                json={
                    "message": "Summarize workflow metrics",
                    "expected_tool": "get_metrics_summary",
                },
            )

        prompt_response = self.client.get("/agentops/prompt-versions", headers=HEADERS)
        regression_response = self.client.post(
            "/agentops/regression",
            headers=HEADERS,
            json={"previous_limit": 1, "current_limit": 1},
        )

        self.assertEqual(prompt_response.status_code, 200)
        self.assertEqual(
            prompt_response.json()["prompt_versions"][0]["prompt_version"],
            "deterministic-v1",
        )
        self.assertEqual(regression_response.status_code, 200)
        regression = regression_response.json()["regression"]
        self.assertIn("deltas", regression)
        self.assertIn("regressed_metrics", regression)
        self.assertEqual(regression["current"]["total_runs"], 1)
        self.assertEqual(regression["previous"]["total_runs"], 1)

    def test_scenario_contract_prepares_step4_without_running_replay(self) -> None:
        response = self.client.get("/agentops/scenarios", headers=HEADERS)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["dataset_id"], "agentops_core")
        self.assertEqual(payload["dataset_version"], "v1")
        self.assertEqual(payload["scenario_count"], 9)
        self.assertEqual(payload["scenarios"][0]["id"], "workflow_summary")
        self.assertIn("expected_tool", payload["required_fields"])

    def test_scenario_evaluation_compares_run_with_fixture(self) -> None:
        created = self.client.post(
            "/agent/copilot",
            headers=HEADERS,
            json={
                "message": "Summarize workflow metrics and cost",
                "expected_tool": "get_metrics_summary",
            },
        )
        run_id = created.json()["run"]["id"]

        response = self.client.post(
            "/agentops/scenarios/evaluate",
            headers=HEADERS,
            json={"scenario_id": "workflow_summary", "run_id": run_id},
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()["result"]
        self.assertTrue(result["passed"])
        self.assertEqual(result["dataset_version"], "v1")
        self.assertEqual(result["expected_tool"], "get_metrics_summary")
        self.assertEqual(result["selected_tool"], "get_metrics_summary")

    def test_scenario_evaluation_is_workspace_scoped(self) -> None:
        created = self.client.post(
            "/agent/copilot",
            headers=HEADERS,
            json={
                "message": "Summarize workflow metrics and cost",
                "expected_tool": "get_metrics_summary",
            },
        )
        run_id = created.json()["run"]["id"]

        response = self.client.post(
            "/agentops/scenarios/evaluate",
            headers=session_headers(
                self.client,
                actor="other-admin",
                workspace_id="other",
            ),
            json={"scenario_id": "workflow_summary", "run_id": run_id},
        )

        self.assertEqual(response.status_code, 404)

    def test_backoffice_scenario_contract_lists_document_operations_dataset(self) -> None:
        response = self.client.get("/agentops/backoffice/scenarios", headers=HEADERS)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["dataset_id"], "document_operations")
        self.assertEqual(payload["dataset_version"], "v1")
        self.assertEqual(payload["scenario_count"], 5)
        self.assertEqual(payload["scenarios"][0]["id"], "invoice_review_read_only")
        self.assertEqual(payload["scenarios"][0]["document_type"], "invoice")
        self.assertEqual(payload["scenarios"][0]["operation_type"], "document_review")
        self.assertIn("document_type", payload["required_fields"])
        self.assertIn("operation_type", payload["required_fields"])
        self.assertIn("expected_plan_steps", payload["required_fields"])

    def test_backoffice_scenario_evaluation_compares_plan_with_fixture(self) -> None:
        container = self.client.app.state.container
        security_context = _security_context()
        work_item = container.backoffice_service.create_work_item(
            title="Prepare approved invoice export",
            context=security_context,
            work_type=WorkType.INVOICE_EXPORT,
            linked_document_ids=(uuid4(),),
        )
        container.backoffice_service.plan_work_item(
            work_item_id=work_item.id,
            context=security_context,
            planning_input=PlanningInput(
                requested_outcome="export invoice",
                approved_for_export=True,
            ),
        )

        response = self.client.post(
            "/agentops/backoffice/scenarios/evaluate",
            headers=HEADERS,
            json={
                "scenario_id": "approved_invoice_export_confirmation",
                "work_item_id": str(work_item.id),
            },
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()["result"]
        self.assertTrue(result["passed"])
        self.assertEqual(result["dataset_version"], "v1")
        self.assertTrue(result["checks"]["document_type"])
        self.assertTrue(result["checks"]["operation_type"])
        self.assertEqual(result["actual_document_type"], "invoice")
        self.assertEqual(result["actual_operation_type"], "document_export")
        self.assertEqual(
            result["actual_plan_steps"],
            ["inspect_queue", "export_approved_invoice"],
        )
        evaluations_response = self.client.get("/agentops/evaluations", headers=HEADERS)
        evaluation = evaluations_response.json()["evaluations"][0]
        evidence = evaluation["evidence"]

        self.assertEqual(evaluations_response.status_code, 200)
        self.assertEqual(evaluation["evaluation_type"], "backoffice")
        self.assertEqual(evaluation["scenario_id"], "approved_invoice_export_confirmation")
        self.assertEqual(evidence["expected_document_type"], "invoice")
        self.assertEqual(evidence["actual_document_type"], "invoice")
        self.assertEqual(evidence["expected_operation_type"], "document_export")
        self.assertEqual(evidence["actual_operation_type"], "document_export")
        self.assertTrue(evidence["checks"]["document_type"])
        self.assertTrue(evidence["checks"]["operation_type"])

    def test_backoffice_plan_creates_resolvable_agentops_trace(self) -> None:
        container = self.client.app.state.container
        work_item = container.backoffice_service.create_work_item(
            title="Review linked invoice",
            context=_security_context(),
            work_type=WorkType.INVOICE_REVIEW,
            linked_document_ids=(uuid4(),),
        )
        container.backoffice_service.plan_work_item(
            work_item_id=work_item.id,
            context=_security_context(),
        )

        detail = self.client.get(f"/backoffice/work-items/{work_item.id}", headers=HEADERS).json()[
            "work_item"
        ]
        run_id = detail["current_plan"]["agent_run_id"]
        trace = self.client.get(f"/agentops/runs/{run_id}", headers=HEADERS)

        self.assertIsNotNone(run_id)
        self.assertEqual(trace.status_code, 200)
        self.assertEqual(trace.json()["work_item_id"], str(work_item.id))
        self.assertEqual(trace.json()["plan_id"], detail["current_plan"]["id"])
        self.assertEqual(trace.json()["prompt_version"], detail["current_plan"]["planner_version"])
        self.assertIsNotNone(trace.json()["latency_ms"])
        self.assertEqual(detail["activity"][-1]["agent_run_id"], run_id)

    def test_backoffice_scenario_evaluation_is_workspace_scoped(self) -> None:
        container = self.client.app.state.container
        security_context = _security_context()
        work_item = container.backoffice_service.create_work_item(
            title="Review invoice",
            context=security_context,
            work_type=WorkType.INVOICE_REVIEW,
            linked_document_ids=(uuid4(),),
        )
        container.backoffice_service.plan_work_item(
            work_item_id=work_item.id,
            context=security_context,
        )

        response = self.client.post(
            "/agentops/backoffice/scenarios/evaluate",
            headers=session_headers(
                self.client,
                actor="other-admin",
                workspace_id="other",
            ),
            json={
                "scenario_id": "invoice_review_read_only",
                "work_item_id": str(work_item.id),
            },
        )

        self.assertEqual(response.status_code, 404)


def _security_context():
    return SecurityContext(
        actor="admin",
        workspace_id="default",
        role="admin",
        is_admin=True,
    )


if __name__ == "__main__":
    unittest.main()
