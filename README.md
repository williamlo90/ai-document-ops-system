# AI-Powered Invoice Review And Approval System

This repository is rebuilt as a sequence of runnable engineering milestones. The current state is
**M01: Walking Skeleton And Evidence Harness**.

M01 proves only that a clean Python environment can start the API, report liveness and readiness as
different runtime concepts, and replay its tests from a tagged source archive. It does not yet
claim invoice processing, persistence, AI extraction, review, export, or a browser interface.

## Run M01

```powershell
.\scripts\setup_local_venv.ps1
.\scripts\start_dev.ps1
```

Then open `http://127.0.0.1:8000/health` and `http://127.0.0.1:8000/ready`.

## Verify M01

```powershell
$env:PYTHONPATH = "backend"
$py = ".\.venv\Scripts\python.exe"
& $py -m unittest app.tests.test_api app.tests.test_settings app.tests.test_runtime_observability
```

The cumulative verifier is run after the local `reconstruction-m01` tag exists. It stores raw
results outside the repository and replays the tagged archive rather than trusting the working
tree.

## Current Boundary

- Local single-node development only.
- No personal credential or `.env` file is required.
- `/health` means the process is alive.
- `/ready` means the process is accepting traffic and its introduced dependencies are ready.
- No production readiness, customer outcome, compliance, or invoice accuracy claim is made.
