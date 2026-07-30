# Supply-Chain Controls

The repository keeps direct Python dependencies in `requirements.in` and
`requirements-dev.in`. The corresponding `.txt` files are complete Python 3.11 lockfiles with
package hashes. Frontend direct versions are exact and `package-lock.json` supplies transitive
versions and integrity hashes.

## Regenerate Python Locks

Regenerate on Python 3.11 from a fresh environment installed from the current hash-locked
development file. That file pins the compatible bootstrap tools (`pip==26.1.2`,
`setuptools==83.0.0`, and `pip-tools==7.6.0`):

```powershell
py -3.11 -m venv .venv-lock
.\.venv-lock\Scripts\python.exe -m pip install --require-hashes -r requirements-dev.txt
.\.venv-lock\Scripts\python.exe -m piptools compile `
  --generate-hashes --resolver=backtracking --strip-extras --allow-unsafe `
  --no-emit-index-url --output-file=requirements.txt requirements.in
.\.venv-lock\Scripts\python.exe -m piptools compile `
  --generate-hashes --resolver=backtracking --strip-extras --allow-unsafe `
  --no-emit-index-url --output-file=requirements-dev.txt requirements-dev.in
git diff --exit-code -- requirements.txt requirements-dev.txt
```

The zero-diff command is the reproducibility check when no direct dependency changed. Review both
the direct input and generated transitive diff when updating a dependency. Never hand-edit a
generated lockfile. CI also performs fresh hash-locked installs on Python 3.11 and 3.12 before the
Python quality and smoke jobs run.

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

## Temporary Frontend Advisory Exception

As of 28 July 2026, the npm registry reports `GHSA-qwww-vcr4-c8h2` against React Router
`7.12.0` through `8.2.0`. The registry's suggested downgrade to `7.11.0` reintroduces several older
high-severity React Router advisories, while `7.18.1` is the latest available release.

The application remains on `7.18.1`. The affected React Server Components and framework-mode
server-action path is not used: this repository builds a client-only Vite SPA with no React Router
SSR, RSC, server actions, or server-side route execution. This is a bounded risk acceptance, not a
claim that the dependency graph is advisory-free.

`npm run audit` still runs the complete npm audit and fails on every unreviewed high or critical
finding. Its allowlist accepts only this advisory for `react-router` and `react-router-dom` and
expires on 15 August 2026, forcing a review or upgrade when a patched release becomes available.
