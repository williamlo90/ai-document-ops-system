# Security Remediation V6

- Remediation date: 19 July 2026
- Mode: `SELF_VERIFICATION`
- Scope: SEC-009 from the 15 July 2026 security baseline
- Independent review: Not yet performed

## Verdict

| Finding | Result | Current boundary |
| --- | --- | --- |
| SEC-009: dependency and CI supply chain was not reproducible or continuously scanned | `CLOSED_WITH_TIME_BOUND_SCAN_LIMITATION` | Python and npm graphs are locked, CI actions and images are immutable, advisory and image scans fail the build at the documented threshold, and update automation is enabled. A clean scan reflects the advisory databases available at scan time, not the absence of unknown vulnerabilities. |

## Implemented Controls

- Direct Python dependencies live in `.in` files; Python 3.11 lockfiles include every transitive
  version and artifact hash. Installation uses `--require-hashes` locally, in CI, and in Docker.
- The development-only vulnerable Black version was removed. Ruff 0.15.22 now provides both format
  and lint gates, avoiding a known-vulnerable formatter dependency.
- Frontend direct dependencies are exact, the npm lockfile records transitive versions and integrity
  hashes, and supported Node/npm versions are explicit.
- GitHub Actions use commit SHAs, receive read-only repository contents permission, and use exact
  Python and Node versions.
- `pip-audit`, `npm audit`, immutable image build, and Trivy HIGH/CRITICAL scans are CI gates.
- Node, Python, and Postgres images use registry digests. The final application image removes pip,
  setuptools, and wheel after installation because they are not runtime requirements.
- Dependabot checks Python, npm, GitHub Actions, and Docker weekly. Updates still require the full CI
  gate before merge.

## Executed Evidence

| Check | Result |
| --- | --- |
| Fresh Python 3.11.14 hash-verified development install | Passed, 63 locked packages installed in an empty environment |
| Python runtime `pip-audit --strict` | No known vulnerabilities found |
| npm audit at HIGH threshold | 0 vulnerabilities |
| Ruff format and lint | 180 files formatted; all lint checks passed |
| Full backend regression | 422 passed, 2 skipped |
| Frontend unit, lint, and production build | 13 passed; lint and build passed |
| Digest-pinned Docker build | Passed |
| Built-container health and readiness smoke | Passed as non-root runtime user |
| Trivy 0.72.0 image scan, fixed HIGH/CRITICAL threshold | 0 findings after runtime build-tool removal |

The first image scan found two fixed HIGH advisories in `setuptools`-vendored build metadata. The
final image does not need package installation, so pip, setuptools, and wheel were removed. The
rebuilt image remained operational and the repeated scan returned zero findings at the configured
threshold.

## Residual Limitations

- Advisory databases can lag disclosure and cannot detect unknown vulnerabilities.
- Dependabot proposals and scanner updates require ongoing repository maintenance.
- The local scan covers the built Linux image; an independently built release image must be scanned
  again by CI and bound to its immutable digest.
- Signed provenance, an organizational action allowlist, and registry admission policy are not
  claimed by this portfolio repository.

## Release Decision

- Local synthetic and controlled provider evaluation: `PASS_WITH_LIMITATIONS`.
- Dependency and candidate-image supply-chain gate: `PASS` for the inspected candidate.
- Hosted real-data release: still `BLOCKED` by external scanner deployment, provider governance,
  protected metrics access, hosted infrastructure verification, and independent review.
