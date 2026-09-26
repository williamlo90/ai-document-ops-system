from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class DockerProfileTests(unittest.TestCase):
    def test_compose_defines_api_worker_and_shared_data_volume(self) -> None:
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

        self.assertIn("api:", compose)
        self.assertIn("worker:", compose)
        self.assertIn("docintel-data:/data", compose)
        self.assertIn('python", "-m", "app.worker_loop', compose)
        self.assertIn("healthcheck:", compose)
        self.assertIn("migrate:", compose)
        self.assertIn('profiles: ["migrate"]', compose)
        self.assertGreaterEqual(compose.count("read_only: true"), 3)
        self.assertGreaterEqual(compose.count('cap_drop: ["ALL"]'), 3)
        self.assertGreaterEqual(compose.count("no-new-privileges:true"), 3)

    def test_postgres_target_is_profiled_not_default_runtime_claim(self) -> None:
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

        self.assertIn("postgres-target:", compose)
        self.assertIn('profiles: ["postgres-target"]', compose)

    def test_dockerfile_sets_pythonpath_and_runs_api(self) -> None:
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn("PYTHONPATH=/app", dockerfile)
        self.assertIn("uvicorn", dockerfile)
        self.assertIn("app.main:app", dockerfile)
        self.assertIn("org.opencontainers.image.revision", dockerfile)
        self.assertIn("org.opencontainers.image.created", dockerfile)
        self.assertIn("chmod -R a-w /app", dockerfile)

    def test_container_apps_contract_uses_digest_identity_probes_and_scaling(self) -> None:
        contracts = ROOT / "infra" / "azure" / "container-apps"
        api = (contracts / "api.yaml").read_text(encoding="utf-8")
        worker = (contracts / "worker.yaml").read_text(encoding="utf-8")
        migration = (contracts / "migration-job.yaml").read_text(encoding="utf-8")

        for contract in (api, worker, migration):
            self.assertIn("@sha256:<IMAGE_DIGEST>", contract)
            self.assertIn("UserAssigned", contract)
            self.assertIn("identity:", contract)
            self.assertNotIn(":latest", contract)
        self.assertIn("activeRevisionsMode: Single", api)
        self.assertIn("type: Liveness", api)
        self.assertIn("type: Readiness", api)
        self.assertIn("type: azure-servicebus", worker)
        self.assertIn("minReplicas: 0", worker)
        self.assertIn("type: Microsoft.App/jobs", migration)
        self.assertIn("triggerType: Manual", migration)
        self.assertIn("replicaCompletionCount: 1", migration)

    def test_published_deployment_docs_describe_honest_cloud_path(self) -> None:
        docker_profile = (ROOT / "docs" / "docker_profile.md").read_text(encoding="utf-8")
        aws_deployment = (ROOT / "docs" / "aws_deployment.md").read_text(encoding="utf-8")
        runbook = (ROOT / "RUNBOOK.md").read_text(encoding="utf-8")

        self.assertIn("self-contained local Docker topology", docker_profile)
        self.assertIn("does not make the system production-ready", docker_profile)
        self.assertIn("hosted or production certified", aws_deployment)
        self.assertIn("ECS", aws_deployment)
        self.assertIn("RDS", aws_deployment)
        self.assertIn("docs/docker_profile.md", runbook)
        self.assertIn("docs/aws_deployment.md", runbook)
        self.assertNotIn("DEPLOYMENT_READINESS.md", runbook)


if __name__ == "__main__":
    unittest.main()
