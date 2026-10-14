"""Grant only sandbox Purchase Invoice submit and GL Entry read to the integration role."""
from pathlib import Path
import os
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]

from app.core.settings import load_settings  # noqa: E402
from erpnext_setup.api import ERPNextAdminClient  # noqa: E402
from erpnext_setup.provisioner import MasterDataProvisioner  # noqa: E402
from provision_erpnext_master_data import _read_env_value  # noqa: E402


def main():
    settings = load_settings()
    parsed = urlsplit(settings.erpnext_base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("Phase 5 permission change is restricted to the local sandbox")
    password = os.getenv("ERPNEXT_ADMIN_PASSWORD") or _read_env_value(ROOT / ".env", "ERPNEXT_ADMIN_PASSWORD")
    if not password:
        raise SystemExit("Sandbox Administrator credential is not configured")
    client = ERPNextAdminClient(settings.erpnext_base_url, timeout=30)
    client.login(password)
    try:
        provisioner = MasterDataProvisioner(client, dataset=None)
        provisioner._ensure_custom_permission("Purchase Invoice", read=1, write=1, create=1, submit=1)
        provisioner._ensure_custom_permission("GL Entry", read=1, select=1)
        for doctype, expected in (("Purchase Invoice", {"read": 1, "write": 1, "create": 1, "submit": 1,
                                                         "cancel": 0, "delete": 0}),
                                  ("GL Entry", {"read": 1, "write": 0, "create": 0, "submit": 0,
                                                "cancel": 0, "delete": 0})):
            row = client.find_one("Custom DocPerm", {"parent": doctype, "role": "Invoice Draft Integration", "permlevel": 0},
                                  fields=("name", *expected))
            if row is None or any(row[key] != value for key, value in expected.items()):
                raise RuntimeError(f"Sandbox permission verification failed: {doctype}")
        payment = client.list_documents("Custom DocPerm", filters={"parent": "Payment Entry", "role": "Invoice Draft Integration"})
        if payment:
            raise RuntimeError("Integration role unexpectedly has payment permission")
    finally:
        client.logout()
    print("Sandbox permissions verified: Purchase Invoice submit and GL Entry read; no payment/cancel/delete grant")


if __name__ == "__main__":
    main()
