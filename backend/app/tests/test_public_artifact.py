from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "prepare_public_artifact.py"


class PublicArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.output = tempfile.mkdtemp()

    def tearDown(self) -> None:
        for root, dirs, files in os.walk(self.output, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(self.output)

    def _run_script(self, *args: str) -> subprocess.CompletedProcess:
        cmd = [sys.executable, str(SCRIPT), *args]
        return subprocess.run(cmd, capture_output=True, text=True, cwd=SCRIPT.parents[1])

    def test_source_parent_named_dist_does_not_exclude_repository_files(self) -> None:
        spec = importlib.util.spec_from_file_location("prepare_public_artifact", SCRIPT)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader if spec else None)
        module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(module)  # type: ignore[union-attr]

        simulated_root = Path(self.output) / "dist" / "clean-clone"
        with patch.object(module, "ROOT", simulated_root):
            self.assertFalse(
                module._has_private_parent(simulated_root / "backend" / "app" / "main.py")
            )
            self.assertTrue(
                module._has_private_parent(simulated_root / "frontend" / "dist" / "index.html")
            )

    def test_excludes_dot_env(self) -> None:
        result = self._run_script(self.output)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        output_path = Path(self.output)
        env_files = list(output_path.rglob(".env"))
        self.assertEqual(env_files, [])

    def test_excludes_sqlite_files(self) -> None:
        result = self._run_script(self.output)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        output_path = Path(self.output)
        sqlite_files = [
            p for p in output_path.rglob("*") if "sqlite" in p.suffix or "sqlite3" in p.name
        ]
        self.assertEqual(sqlite_files, [])

    def test_excludes_upload_folders(self) -> None:
        result = self._run_script(self.output)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        output_path = Path(self.output)
        upload_paths = [
            p for p in output_path.rglob("*") if "data" in p.parts and "uploads" in p.parts
        ]
        self.assertEqual(upload_paths, [])

    def test_includes_env_example(self) -> None:
        result = self._run_script(self.output)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertTrue((Path(self.output) / ".env.example").exists())

    def test_includes_readme(self) -> None:
        result = self._run_script(self.output)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertTrue((Path(self.output) / "README.md").exists())

    def test_includes_roadmap(self) -> None:
        result = self._run_script(self.output)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertTrue((Path(self.output) / "ROADMAP.md").exists())

    def test_includes_portfolio_case_study(self) -> None:
        result = self._run_script(self.output)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        output = Path(self.output)
        self.assertTrue((output / "PORTFOLIO_CASE_STUDY.md").exists())
        self.assertTrue((output / "SCENARIO_COVERAGE_MATRIX.md").exists())

    def test_excludes_local_only_planning_documents(self) -> None:
        result = self._run_script(self.output)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        script_source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('"_private_data"', script_source)
        self.assertIn("Private evaluation data found in output", script_source)
        output = Path(self.output)
        self.assertFalse((output / "_local_docs").exists())
        self.assertFalse((output / "_private_data").exists())
        self.assertFalse((output / "AGENTS.md").exists())
        self.assertFalse((output / "PORTFOLIO_STORY.md").exists())
        self.assertFalse((output / "AGENT_TOOL_CONTRACTS.md").exists())
        self.assertFalse((output / "AGENT_GUARDRAILS.md").exists())
        self.assertFalse((output / "AGENTOPS_EVALUATION_PLAN.md").exists())
        self.assertFalse((output / "EVALUATION_DATASET.md").exists())
        self.assertFalse((output / "AUTONOMY_POLICY.md").exists())
        self.assertFalse((output / "BACKOFFICE_WORKFLOW.md").exists())
        self.assertFalse((output / "PROJECT_4_READINESS.md").exists())
        self.assertFalse((output / "DEPLOYMENT_READINESS.md").exists())
        self.assertFalse((output / "FUNCTIONAL_COMPLETION_TODO.md").exists())
        self.assertFalse((output / "SPRINT_PLAN.md").exists())
        self.assertFalse((output / "BACKEND_SPRINT_PLAN.md").exists())
        self.assertFalse((output / "FRONTEND_SPRINT_PLAN.md").exists())

    def test_includes_quality_gate_files(self) -> None:
        result = self._run_script(self.output)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        output = Path(self.output)
        self.assertTrue((output / "pyproject.toml").exists())
        self.assertTrue((output / "requirements-dev.txt").exists())
        self.assertTrue((output / ".github" / "workflows" / "ci.yml").exists())
        self.assertTrue((output / "scripts" / "quality_report.py").exists())

    def test_includes_docker_profile_files(self) -> None:
        result = self._run_script(self.output)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        output = Path(self.output)
        self.assertTrue((output / "Dockerfile").exists())
        self.assertTrue((output / "docker-compose.yml").exists())
        self.assertTrue((output / "scripts" / "start_docker.ps1").exists())

    def test_includes_benchmark_fixture(self) -> None:
        result = self._run_script(self.output)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        benchmark_fixture = (
            Path(self.output)
            / "examples"
            / "benchmark"
            / "datasets"
            / "simple_two"
            / "expected.json"
        )
        self.assertTrue(benchmark_fixture.exists())

    def test_includes_portfolio_demo_package(self) -> None:
        result = self._run_script(self.output)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        output = Path(self.output)
        self.assertTrue((output / "docs" / "demo-script.md").exists())
        self.assertTrue((output / "docs" / "demo-video.md").exists())
        self.assertTrue((output / "docs" / "INDEX.md").exists())
        self.assertTrue((output / "docs" / "security" / "SECURITY_POSTURE.md").exists())
        self.assertTrue((output / "docs" / "invoice-scenarios-v1-evidence.md").exists())
        self.assertTrue((output / "docs" / "reliability-report.md").exists())
        screenshot_root = output / "docs" / "assets" / "screenshots"
        for screenshot in (
            "inbox.png",
            "invoices.png",
            "review.png",
            "exports.png",
            "quality.png",
            "operations.png",
            "reviewer-decision.png",
            "approved-decision.png",
            "uploader-correction.png",
        ):
            self.assertTrue((screenshot_root / screenshot).exists(), msg=screenshot)
        for viewport in ("compact", "tablet", "mobile"):
            for screenshot in (
                "inbox.png",
                "invoices.png",
                "review.png",
                "exports.png",
                "quality.png",
                "operations.png",
            ):
                self.assertTrue(
                    (screenshot_root / viewport / screenshot).exists(),
                    msg=f"{viewport}/{screenshot}",
                )
        self.assertTrue((output / "docs" / "assets" / "demo" / "invoice-review-demo.mp4").exists())

    def test_excludes_obsolete_public_plans(self) -> None:
        result = self._run_script(self.output)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        output = Path(self.output)
        self.assertFalse((output / "UI_PLAN.md").exists())
        self.assertFalse((output / "docs" / "portfolio-demo.md").exists())
        self.assertFalse((output / "docs" / "final-release-notes.md").exists())
        self.assertFalse((output / "docs" / "project-4-handoff.md").exists())
        self.assertFalse((output / "docs" / "pivot").exists())

    def test_includes_agentops_scenario_dataset(self) -> None:
        result = self._run_script(self.output)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        scenario_dataset = Path(self.output) / "examples" / "agentops" / "scenarios_v1.json"
        document_operations_dataset = (
            Path(self.output) / "examples" / "agentops" / "document_operations_scenarios_v1.json"
        )
        self.assertTrue(scenario_dataset.exists())
        self.assertTrue(document_operations_dataset.exists())

    def test_includes_pdf_backed_benchmark_dataset(self) -> None:
        result = self._run_script(self.output)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        pdf_fixture = (
            Path(self.output)
            / "examples"
            / "benchmark"
            / "datasets"
            / "pdf_sample"
            / "documents"
            / "sample_invoice.pdf"
        )
        expected = (
            Path(self.output)
            / "examples"
            / "benchmark"
            / "datasets"
            / "pdf_sample"
            / "expected.json"
        )
        self.assertTrue(pdf_fixture.exists())
        self.assertTrue(expected.exists())

    def test_excludes_delegation_working_files(self) -> None:
        result = self._run_script(self.output)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertFalse((Path(self.output) / "delegation").exists())

    def test_includes_backend_app(self) -> None:
        result = self._run_script(self.output)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        backend_app = Path(self.output) / "backend" / "app"
        self.assertTrue(backend_app.is_dir())
        main_py = backend_app / "main.py"
        self.assertTrue(main_py.exists())

    def test_excludes_pycache(self) -> None:
        result = self._run_script(self.output)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        output_path = Path(self.output)
        pycache_dirs = list(output_path.rglob("__pycache__"))
        self.assertEqual(pycache_dirs, [])


if __name__ == "__main__":
    unittest.main()
