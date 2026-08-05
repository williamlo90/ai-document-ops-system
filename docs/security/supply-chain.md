# Supply-Chain Controls

The repository keeps direct Python dependencies in `requirements.in` and
`requirements-dev.in`. Linux and Windows each have complete Python 3.11 lockfiles with package
hashes because platform-specific dependencies differ. Frontend direct versions are exact and
`package-lock.json` supplies transitive versions and integrity hashes.

## Regenerate Python Locks

Regenerate on Python 3.11 from a fresh environment installed from the current hash-locked
development file. That file pins the compatible bootstrap tools (`pip==26.1.2`,
`setuptools==83.0.0`, and `pip-tools==7.6.0`):

```powershell
py -3.11 -m venv .venv-lock
.\.venv-lock\Scripts\python.exe -m pip install --require-hashes -r requirements-dev-windows.txt
.\.venv-lock\Scripts\python.exe -m piptools compile `
  --generate-hashes --resolver=backtracking --strip-extras --allow-unsafe --no-annotate `
  --no-emit-index-url --output-file=requirements-windows.txt requirements.in
.\.venv-lock\Scripts\python.exe -m piptools compile `
  --generate-hashes --resolver=backtracking --strip-extras --allow-unsafe --no-annotate `
  --no-emit-index-url --output-file=requirements-dev-windows.txt requirements-dev.in
git diff --exit-code -- requirements-windows.txt requirements-dev-windows.txt
```

The Windows lock files support local PowerShell setup. CI and the container use
`requirements.txt` and `requirements-dev.txt`, which are generated on Linux. The zero-diff command
is the reproducibility check when no direct dependency changed. Review both the direct input and
generated transitive diff when updating a dependency. Never hand-edit a generated lockfile. CI
also performs fresh Linux hash-locked installs on Python 3.11 and 3.12 before the Python quality
and smoke jobs run.

## Verification

CI and the documented local gate enforce:

- hash-verified Python installation;
- Python runtime advisory scanning with `pip-audit`;
- npm lockfile installation and high/critical advisory scanning;
- full Git-history secret scanning with only an exact documented placeholder allowlisted;
- immutable GitHub Action revisions;
- digest-pinned runtime, build, and local Postgres images;
- deployment of the exact scanned registry digest rather than a mutable image tag;
- a high/critical Trivy scan of the built application image; and
- weekly Dependabot checks for Python, npm, GitHub Actions, and Docker;
- grouped minor and patch version updates for each ecosystem; and
- manual review of major version updates instead of automatic major-version pull requests.

Dependency or action updates must pass the full backend, frontend, smoke, image-build, and image-scan
jobs before merge. A passing scan means no advisory matched the configured database and threshold at
scan time; it is not proof that the dependency graph is vulnerability-free.

## Frontend Advisory Closure

On 30 July 2026, the client moved from the `react-router-dom` compatibility package to
`react-router@8.3.0`, the patched release for `GHSA-qwww-vcr4-c8h2`. The package requires
Node.js 22.22 or newer, so the frontend engine and CI runtime enforce that minimum.

The dependency-audit allowlist is empty. `npm run audit` still evaluates the complete npm audit
report and fails on every high or critical finding unless a future, documented, time-limited
exception is reviewed and added explicitly.
