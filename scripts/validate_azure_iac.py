from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
AZURE_ROOT = REPOSITORY_ROOT / "infra" / "azure"
REQUIRED_MODULES = {
    "api.bicep",
    "container-apps-environment.bicep",
    "event-grid.bicep",
    "identities.bicep",
    "ingestion-function.bicep",
    "key-vault.bicep",
    "migration-job.bicep",
    "monitoring.bicep",
    "postgres.bicep",
    "registry.bicep",
    "role-assignments.bicep",
    "service-bus.bicep",
    "storage.bicep",
    "worker.bicep",
}
REQUIRED_SCRIPTS = {
    "collect-evidence.ps1",
    "deploy-runtime.ps1",
    "destroy.ps1",
    "inventory.ps1",
    "migrate.ps1",
    "preflight.ps1",
    "provision.ps1",
    "publish-image.ps1",
    "register-providers.ps1",
    "set-secrets.ps1",
    "validate-live.ps1",
}


def validate_sources(root: Path = AZURE_ROOT) -> list[str]:
    errors: list[str] = []
    modules = {path.name for path in (root / "modules").glob("*.bicep")}
    scripts = {path.name for path in (root / "scripts").glob("*.ps1")}
    errors.extend(_missing("module", REQUIRED_MODULES, modules))
    errors.extend(_missing("script", REQUIRED_SCRIPTS, scripts))

    main = (root / "main.bicep").read_text(encoding="utf-8")
    runtime = (root / "runtime.bicep").read_text(encoding="utf-8")
    api_module = (root / "modules" / "api.bicep").read_text(encoding="utf-8")
    worker_module = (root / "modules" / "worker.bicep").read_text(encoding="utf-8")
    role_module = (root / "modules" / "role-assignments.bicep").read_text(encoding="utf-8")
    destroy = (root / "scripts" / "destroy.ps1").read_text(encoding="utf-8")
    provision = (root / "scripts" / "provision.ps1").read_text(encoding="utf-8")
    deploy_runtime = (root / "scripts" / "deploy-runtime.ps1").read_text(encoding="utf-8")
    function_code = (root / "function-app" / "function_app.py").read_text(encoding="utf-8")

    for name in (
        "postgresAdministratorPassword",
        "adminToken",
        "uploaderToken",
        "reviewerToken",
        "metricsToken",
    ):
        pattern = rf"@secure\(\)\s+(?:@description\([^\n]+\)\s+)?param\s+{name}\s+string"
        if not re.search(pattern, main):
            errors.append(f"secure parameter decorator missing for {name}")

    if "expiresAt: expiresAt" not in main or "sourceRevision: sourceRevision" not in main:
        errors.append("resource tags must include expiration and source revision")
    if "@sha256:" not in (root / "runtime.parameters.example.json").read_text(encoding="utf-8"):
        errors.append("runtime example must demonstrate digest-only image references")
    if "Assert-ImmutableImageReference" not in deploy_runtime:
        errors.append("runtime deployment must reject mutable image references")
    if "ConfirmBillable" not in provision or "ConfirmBillable" not in deploy_runtime:
        errors.append("billable scripts require an explicit approval switch")
    if "ConfirmDestroy" not in destroy or "^rg-ai-document-" not in destroy:
        errors.append("destroy script must confirm and constrain its exact resource-group target")
    if re.search(r"(?:imageReference|clamavImageReference)\s*=.*:latest", runtime, re.IGNORECASE):
        errors.append("runtime template contains a mutable latest image")
    if "name: '${take(namePrefix, 25)}-worker'" not in runtime:
        errors.append("worker name must stay within the 32-character Container Apps limit")
    if "name: '${take(namePrefix, 24)}-migrate'" not in runtime:
        errors.append("migration job name must stay within the 32-character Container Apps limit")
    if "external: true" not in api_module or "allowInsecure: false" not in api_module:
        errors.append("API ingress must be explicit HTTPS-only external ingress")
    if "ingress:" in worker_module:
        errors.append("worker must not expose ingress")
    if "scope: resourceGroup()" in role_module:
        errors.append("data-plane roles must not be assigned at resource-group scope")
    for marker in ("acquire_lease", "docintel_ingested", "set_blob_metadata"):
        if marker not in function_code:
            errors.append(f"external-drop duplicate guard is missing: {marker}")

    parameter_text = "\n".join(
        path.read_text(encoding="utf-8") for path in root.glob("*.parameters.example.json")
    ).lower()
    for marker in ("password", "api-key", "secret-value", "connectionstring"):
        if marker in parameter_text:
            errors.append(
                f"committed parameter example appears to contain secret material: {marker}"
            )
    return errors


def validate_compiled(compiled_dir: Path) -> list[str]:
    errors: list[str] = []
    templates = [
        json.loads((compiled_dir / name).read_text(encoding="utf-8"))
        for name in ("main.json", "runtime.json", "event-grid.json")
    ]
    resources = [resource for template in templates for resource in _walk_resources(template)]

    errors.extend(
        _require_property(
            resources, "Microsoft.ContainerRegistry/registries", "adminUserEnabled", False
        )
    )
    errors.extend(
        _require_property(
            resources, "Microsoft.Storage/storageAccounts", "allowBlobPublicAccess", False
        )
    )
    errors.extend(
        _require_property(
            resources, "Microsoft.Storage/storageAccounts", "allowSharedKeyAccess", False
        )
    )
    errors.extend(
        _require_property(resources, "Microsoft.ServiceBus/namespaces", "disableLocalAuth", True)
    )
    errors.extend(
        _require_property(resources, "Microsoft.KeyVault/vaults", "enableRbacAuthorization", True)
    )
    errors.extend(
        _require_property(
            resources, "Microsoft.ServiceBus/namespaces/queues", "maxDeliveryCount", 5
        )
    )
    errors.extend(
        _require_property(
            resources, "Microsoft.ServiceBus/namespaces/queues", "requiresDuplicateDetection", True
        )
    )

    diagnostics = [
        resource
        for resource in resources
        if str(resource.get("type", "")).lower().endswith("/diagnosticsettings")
    ]
    if len(diagnostics) < 6:
        errors.append(f"expected diagnostics for managed services; found only {len(diagnostics)}")
    for diagnostic in diagnostics:
        if not diagnostic.get("properties", {}).get("workspaceId"):
            errors.append(
                f"diagnostic setting lacks a Log Analytics destination: {diagnostic.get('name')}"
            )

    role_assignments = [
        resource
        for resource in resources
        if str(resource.get("type", "")).lower().endswith("/roleassignments")
    ]
    if len(role_assignments) < 12:
        errors.append(
            f"expected scoped workload RBAC assignments; found only {len(role_assignments)}"
        )

    taggable = (
        "Microsoft.ManagedIdentity/userAssignedIdentities",
        "Microsoft.ContainerRegistry/registries",
        "Microsoft.Storage/storageAccounts",
        "Microsoft.ServiceBus/namespaces",
        "Microsoft.DBforPostgreSQL/flexibleServers",
        "Microsoft.KeyVault/vaults",
        "Microsoft.OperationalInsights/workspaces",
        "Microsoft.Insights/components",
        "Microsoft.App/managedEnvironments",
        "Microsoft.Web/serverfarms",
        "Microsoft.Web/sites",
        "Microsoft.App/containerApps",
        "Microsoft.App/jobs",
        "Microsoft.EventGrid/systemTopics",
    )
    for resource in resources:
        if str(resource.get("type", "")).lower() in {item.lower() for item in taggable}:
            if "tags" not in resource:
                errors.append(
                    f"taggable resource lacks tags: {resource.get('type')} {resource.get('name')}"
                )

    for template in templates:
        for output_name, output in _walk_outputs(template):
            if output.get("type", "").lower() in {"securestring", "secureobject"}:
                errors.append(f"template exposes a secure deployment output: {output_name}")

    serialized = json.dumps(templates).lower()
    if ":latest" in serialized:
        errors.append("compiled ARM contains a mutable latest image reference")
    return errors


def _missing(kind: str, required: set[str], actual: set[str]) -> list[str]:
    return [f"missing {kind}: {name}" for name in sorted(required - actual)]


def _walk_resources(template: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for resource in template.get("resources", []):
        yield resource
        nested_template = resource.get("properties", {}).get("template")
        if isinstance(nested_template, dict):
            yield from _walk_resources(nested_template)


def _walk_outputs(template: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    for name, output in template.get("outputs", {}).items():
        yield name, output
    for resource in template.get("resources", []):
        nested_template = resource.get("properties", {}).get("template")
        if isinstance(nested_template, dict):
            yield from _walk_outputs(nested_template)


def _require_property(
    resources: list[dict[str, Any]], resource_type: str, property_name: str, expected: object
) -> list[str]:
    matches = [
        resource
        for resource in resources
        if str(resource.get("type", "")).lower() == resource_type.lower()
    ]
    if not matches:
        return [f"compiled ARM lacks resource type {resource_type}"]
    errors = []
    for resource in matches:
        actual = resource.get("properties", {}).get(property_name)
        if actual != expected:
            errors.append(
                f"{resource_type} {resource.get('name')} has {property_name}={actual!r}, expected {expected!r}"
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Azure IaC safety contracts.")
    parser.add_argument("--compiled-dir", type=Path)
    args = parser.parse_args()
    errors = validate_sources()
    if args.compiled_dir:
        errors.extend(validate_compiled(args.compiled_dir))
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Azure IaC validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
