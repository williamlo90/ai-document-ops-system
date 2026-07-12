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

    def test_postgres_target_is_profiled_not_default_runtime_claim(self) -> None:
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

        self.assertIn("postgres-target:", compose)
        self.assertIn('profiles: ["postgres-target"]', compose)

    def test_dockerfile_sets_pythonpath_and_runs_api(self) -> None:
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn("PYTHONPATH=/app", dockerfile)
        self.assertIn("uvicorn", dockerfile)
        self.assertIn("app.main:app", dockerfile)

    def test_deployment_readiness_documents_honest_cloud_path(self) -> None:
        readiness = (ROOT / "DEPLOYMENT_READINESS.md").read_text(encoding="utf-8")

        self.assertIn("Local Deployment Path", readiness)
        self.assertIn("CI Quality Gates", readiness)
        self.assertIn("Production Readiness Gaps", readiness)
        self.assertIn("AWS Production-Shaped Split", readiness)
        self.assertIn("Kubernetes Path", readiness)
        self.assertIn("not yet a hosted production SaaS", readiness)


if __name__ == "__main__":
    unittest.main()
