# Supply-Chain Controls

The repository keeps direct Python dependencies in `requirements.in` and
`requirements-dev.in`. The corresponding `.txt` files are complete Python 3.11 lockfiles with
package hashes. Frontend direct versions are exact and `package-lock.json` supplies transitive
versions and integrity hashes.

## Regenerate Python Locks

Use Python 3.11 and the pinned pip-tools version:

```powershell
python -m pip install pip-tools==7.6.0
pip-compile --generate-hashes --resolver=backtracking --strip-extras --allow-unsafe `
  --no-emit-index-url --output-file=requirements.txt requirements.in
pip-compile --generate-hashes --resolver=backtracking --strip-extras --allow-unsafe `
  --no-emit-index-url --output-file=requirements-dev.txt requirements-dev.in
```

Review both the direct input and generated transitive diff. Never hand-edit a generated lockfile.

## Verification

CI and the documented local gate enforce:

- hash-verified Python installation;
- Python runtime advisory scanning with `pip-audit`;
- npm lockfile installation and high/critical advisory scanning;
- immutable GitHub Action revisions;
- digest-pinned runtime, build, and local Postgres images;
- a high/critical Trivy scan of the built application image; and
- weekly Dependabot checks for Python, npm, GitHub Actions, and Docker.

Dependency or action updates must pass the full backend, frontend, smoke, image-build, and image-scan
jobs before merge. A passing scan means no advisory matched the configured database and threshold at
scan time; it is not proof that the dependency graph is vulnerability-free.
