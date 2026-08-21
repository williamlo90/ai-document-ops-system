from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.settings import load_settings  # noqa: E402
from erpnext_setup.api import ERPNextAdminClient  # noqa: E402
from erpnext_setup.dataset import load_benchmark_dataset  # noqa: E402
from erpnext_setup.provisioner import MasterDataProvisioner, write_private_report  # noqa: E402


MANIFEST = ROOT / "examples/erpnext/benchmark_cases.json"
REPORT = ROOT / "_private_data/erpnext-benchmark-phase4/master-data-report.json"


def main() -> None:
    settings = load_settings()
    _require_local_erpnext(settings.erpnext_base_url)
    admin_password = os.getenv("ERPNEXT_ADMIN_PASSWORD") or _read_env_value(
        ROOT / ".env", "ERPNEXT_ADMIN_PASSWORD"
    )
    if not admin_password:
        raise SystemExit("ERPNEXT_ADMIN_PASSWORD must be set in the ignored .env file.")

    dataset = load_benchmark_dataset(ROOT, MANIFEST)
    client = ERPNextAdminClient(
        settings.erpnext_base_url,
        timeout=max(settings.erpnext_timeout_seconds, 180),
    )
    client.login(admin_password)
    try:
        report = MasterDataProvisioner(client, dataset).verify()
        write_private_report(report, REPORT)
    finally:
        client.logout()

    eligible = sum(outcome == "draft_eligible" for outcome in report.case_outcomes.values())
    blocked = len(report.case_outcomes) - eligible
    print(f"ERPNext master data: verified ({len(report.companies)} companies)")
    print(f"Supplier mappings: verified ({sum(map(len, report.supplier_mappings.values()))})")
    print(
        f"Purchase Invoice identity fields: verified ({len(report.purchase_invoice_custom_fields)})"
    )
    print(f"Benchmark cases: {eligible} draft-eligible, {blocked} intentional blockers")
    print(f"Private report: {REPORT}")


def _require_local_erpnext(base_url: str) -> None:
    parsed = urlsplit(base_url)
    if parsed.scheme != "http" or (parsed.hostname or "").lower() not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        raise SystemExit(
            "Master-data provisioning is restricted to the local HTTP ERPNext sandbox."
        )
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SystemExit("ERPNEXT_BASE_URL must not contain credentials, query, or fragment.")


def _read_env_value(path: Path, key: str) -> str | None:
    if not path.is_file():
        return None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        candidate, value = line.split("=", 1)
        if candidate.strip() == key:
            return _unquote(value.strip())
    return None


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


if __name__ == "__main__":
    main()
