from __future__ import annotations

import csv
from typing import Any
import hashlib
import io
import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL

from app.core.security import require_any_role
from app.documents.repositories import NotFoundError
from app.procurement.models import ProcurementRecord


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def key(*values):
    return canonical(values)


def now() -> datetime:
    return datetime.now(UTC)


class EvidenceConflict(ValueError):
    pass


class EvidenceService:
    def __init__(self, repository: Any, documents: Any, extractions: Any) -> None:
        self.repo = repository
        self.documents = documents
        self.extractions = extractions

    def document(self, document_id, context) -> Any:
        require_any_role(context, {"admin", "reviewer", "ap_approver"})
        document = self.documents.get(UUID(str(document_id)))
        if document.workspace_id != context.workspace_id:
            raise NotFoundError("Document not found")
        return document

    def invoice_values(self, document_id, context) -> Any:
        self.document(document_id, context)
        stored = self.extractions.get_for_document(UUID(str(document_id)))
        data = json.loads(canonical(asdict(stored.extraction_result.extraction.data)))
        fields = {k: v for k, v in data.items() if k != "line_items"}
        lines = []
        for index, row in enumerate(data["line_items"]):
            line_id = row.get("line_id") or str(uuid5(NAMESPACE_URL, f"{document_id}:line:{index}"))
            if line_id in lines:
                raise EvidenceConflict("Duplicate invoice line ID")
            lines.append(line_id)
            for name, value in row.items():
                if name != "line_id":
                    fields[f"lines.{line_id}.{name}"] = value
        return fields, lines, stored.validation_report.has_errors

    def capture(
        self, document_id, context, reason="Capture current extraction; provenance requires review"
    ) -> dict[str, Any]:
        with self.repo.transaction(context.workspace_id):
            values, lines, _ = self.invoice_values(document_id, context)
            stored = self.extractions.get_for_document(UUID(str(document_id)))
            anchors = {c.field_name: c for c in stored.extraction_result.extraction.confidence}
            previous = self.repo.latest(context.workspace_id, "invoice", str(document_id))
            fingerprint = digest(values)
            if previous and previous["extraction_hash"] == fingerprint:
                return previous
            evidence = {}
            for path, value in values.items():
                old = previous["fields"].get(path) if previous else None
                if old and old["effective"] == value:
                    evidence[path] = old
                else:
                    evidence[path] = {
                        "kind": "unknown",
                        "raw": anchors[path].source_text if path in anchors else None,
                        "normalized": value,
                        "effective": value,
                        "page": anchors[path].source_page if path in anchors else None,
                        "excerpt": anchors[path].source_text if path in anchors else None,
                        "bbox": None,
                        "transform": None,
                        "formula": None,
                        "inputs": [],
                        "reason": reason,
                    }
            return self.repo.append(
                context.workspace_id,
                "invoice",
                str(document_id),
                {
                    "schema_version": "invoice_evidence_v2",
                    "document_id": str(document_id),
                    "extraction_hash": fingerprint,
                    "line_ids": lines,
                    "fields": evidence,
                    "actor": context.actor,
                    "at": now().isoformat(),
                    "reason": reason,
                    "changes": {
                        p: {"before": previous["fields"].get(p) if previous else None, "after": v}
                        for p, v in evidence.items()
                        if not previous or previous["fields"].get(p) != v
                    }
                    | {
                        p: {"before": v, "after": {"kind": "removed", "effective": None}}
                        for p, v in (previous["fields"].items() if previous else [])
                        if p not in evidence
                    },
                },
            )

    def attest(self, document_id, update, context):
        require_any_role(context, {"admin", "reviewer"})
        with self.repo.transaction(context.workspace_id):
            revision = self.capture(document_id, context)
            if revision["version"] != update.expected_revision:
                raise EvidenceConflict("Invoice revision changed; reload before review")
            if not update.fields:
                raise EvidenceConflict("No evidence supplied")
            fields = dict(revision["fields"])
            for path, evidence in update.fields.items():
                if path not in fields or evidence.effective != fields[path]["effective"]:
                    raise EvidenceConflict("Evidence must refer to the current invoice value")
                if evidence.kind == "derived" and any(
                    p not in fields or p == path for p in evidence.inputs
                ):
                    raise EvidenceConflict("Unknown formula input")
                item = evidence.model_dump(mode="json")
                item.update(
                    actor=context.actor, at=now().isoformat(), attestation="reviewer_verified"
                )
                fields[path] = item
            updated = dict(
                revision,
                fields=fields,
                actor=context.actor,
                at=now().isoformat(),
                reason=update.reason,
                changes={
                    p: {"before": revision["fields"][p], "after": fields[p]} for p in update.fields
                },
            )
            return self.repo.append(context.workspace_id, "invoice", str(document_id), updated)

    def import_records(self, records, context, refresh_unchanged=False):
        require_any_role(context, {"admin"})
        if not 1 <= len(records) <= 100:
            raise EvidenceConflict("Import must contain 1 to 100 records")
        records = [ProcurementRecord.model_validate(r) for r in records]
        identifiers = [key(r.company, r.source_system, r.source_id) for r in records]
        if len(set(zip([r.kind for r in records], identifiers, strict=True))) != len(records):
            raise EvidenceConflict("Duplicate source in import")
        result = []
        with self.repo.transaction(context.workspace_id):
            for record, entity in zip(records, identifiers, strict=True):
                data = record.model_dump(mode="json")
                if record.source_updated_at > now() + timedelta(minutes=5):
                    raise EvidenceConflict("Source timestamp is in the future")
                previous = self.repo.latest(context.workspace_id, record.kind, entity)
                if previous:
                    if previous["record"]["source_version"] == record.source_version:
                        if not refresh_unchanged or previous["record"] != data:
                            raise EvidenceConflict("Duplicate or conflicting source version")
                    if record.source_updated_at < datetime.fromisoformat(
                        previous["record"]["source_updated_at"]
                    ):
                        raise EvidenceConflict("Source update is older than current version")
                result.append(
                    self.repo.append(
                        context.workspace_id,
                        record.kind,
                        entity,
                        {
                            "record": data,
                            "actor": context.actor,
                            "synced_at": now().isoformat(),
                            "source_hash": digest(data),
                        },
                    )
                )
        return result

    def import_csv(self, content, context):
        if len(content.encode()) > 1_000_000:
            raise EvidenceConflict("CSV too large")
        reader = csv.DictReader(io.StringIO(content))
        required = {
            "company",
            "kind",
            "source_system",
            "source_id",
            "source_version",
            "supplier_id",
            "currency",
            "status",
            "source_updated_at",
            "source_line_id",
            "item_id",
            "uom",
            "quantity",
            "unit_price",
            "amount",
        }
        allowed = required | {"po_id", "po_line_id", "tax", "discount"}
        if (
            not reader.fieldnames
            or len(set(reader.fieldnames)) != len(reader.fieldnames)
            or not required <= set(reader.fieldnames)
            or set(reader.fieldnames) - allowed
        ):
            raise EvidenceConflict("Invalid CSV columns")
        grouped = {}
        line_fields = {
            "source_line_id",
            "item_id",
            "uom",
            "quantity",
            "unit_price",
            "amount",
            "po_id",
            "po_line_id",
            "tax",
            "discount",
        }
        for index, row in enumerate(reader):
            if index >= 1000 or None in row or any(value is None for value in row.values()):
                raise EvidenceConflict("Malformed or oversized CSV")
            header = {k: v for k, v in row.items() if k not in line_fields}
            entity = key(row["company"], row["kind"], row["source_system"], row["source_id"])
            group = grouped.setdefault(entity, dict(header, lines=[]))
            if {k: v for k, v in group.items() if k != "lines"} != header:
                raise EvidenceConflict("Conflicting source header")
            group["lines"].append({k: v for k, v in row.items() if k in line_fields and v != ""})
        return self.import_records(list(grouped.values()), context)

    def configure(self, kind, payload, context):
        require_any_role(context, {"admin"})
        with self.repo.transaction(context.workspace_id):
            return self.repo.append(
                context.workspace_id,
                kind,
                payload.company,
                {
                    "record": payload.model_dump(mode="json"),
                    "actor": context.actor,
                    "at": now().isoformat(),
                },
            )

    def _source(self, workspace, kind, company, system, source_id):
        result = self.repo.latest(workspace, kind, key(company, system, source_id))
        if result is None:
            raise EvidenceConflict(f"Missing {kind} source: {source_id}")
        return result

    def inputs(self, document_id, request, context):
        revision = self.capture(document_id, context)
        if revision["version"] != request.expected_revision:
            raise EvidenceConflict("Invoice revision changed")
        mapping = self.repo.latest(context.workspace_id, "mapping", request.company)
        policy = self.repo.latest(context.workspace_id, "policy", request.company)
        if not mapping or not policy:
            raise EvidenceConflict("Verified mapping and policy are required")
        sources = {}
        for kind, ids in [("po", request.po_ids), ("receipt", request.receipt_ids)]:
            if len(ids) != len(set(ids)):
                raise EvidenceConflict("Duplicate source reference")
            sources[kind] = [
                self._source(context.workspace_id, kind, request.company, request.source_system, i)
                for i in ids
            ]
        return {
            "invoice": revision,
            "mapping": mapping,
            "policy": policy,
            "sources": sources,
            "allocations": request.allocations,
            "request": request.model_dump(mode="json"),
        }

    def blockers(self, inputs):
        reasons = []
        invoice = inputs["invoice"]
        fields = invoice["fields"]
        policy = inputs["policy"]["record"]
        required = [
            "vendor_name",
            "invoice_number",
            "invoice_date",
            "subtotal",
            "tax",
            "total",
            "currency",
        ]
        for line in invoice["line_ids"]:
            required += [
                f"lines.{line}.{name}"
                for name in ("description", "uom", "quantity", "unit_price", "amount")
            ]
        if not invoice["line_ids"]:
            reasons.append("missing_invoice_lines")
        for path in required:
            item = fields.get(path, {})
            if item.get("effective") is None or item.get("kind", "unknown") == "unknown":
                reasons.append("missing_evidence:" + path)
        for path, item in fields.items():
            if item.get("effective") is not None and item.get("kind") == "unknown":
                reasons.append("unknown_evidence:" + path)
        currency = fields.get("currency", {}).get("effective")
        alias = " ".join((fields.get("vendor_name", {}).get("effective") or "").casefold().split())
        aliases = {
            " ".join(k.casefold().split()): v
            for k, v in inputs["mapping"]["record"]["supplier_aliases"].items()
        }
        supplier = aliases.get(alias)
        if not supplier:
            reasons.append("unverified_supplier_alias")
        if currency != policy["currency"]:
            reasons.append("currency_policy_mismatch")
        cutoff = now() - timedelta(hours=policy["max_age_hours"])
        po_lines = {
            (r["record"]["source_id"], line["source_line_id"])
            for r in inputs["sources"]["po"]
            for line in r["record"]["lines"]
        }
        for records in inputs["sources"].values():
            for source in records:
                r = source["record"]
                if r["status"] != "submitted":
                    reasons.append("source_not_submitted:" + r["source_id"])
                if datetime.fromisoformat(source["synced_at"]) < cutoff:
                    reasons.append("stale_source:" + r["source_id"])
                if r["currency"] != currency:
                    reasons.append("source_currency_mismatch:" + r["source_id"])
                if r["supplier_id"] != supplier:
                    reasons.append("supplier_mismatch:" + r["source_id"])
                if r["kind"] == "receipt" and any(
                    (line["po_id"], line["po_line_id"]) not in po_lines for line in r["lines"]
                ):
                    reasons.append("receipt_po_reference_mismatch")
        if set(inputs["allocations"]) != set(invoice["line_ids"]):
            reasons.append("missing_line_allocations")
        targets = {f"{po}:{line}" for po, line in po_lines}
        if any(target not in targets for target in inputs["allocations"].values()):
            reasons.append("unknown_allocation_target")
        mapping = inputs["mapping"]["record"]
        targets_by_id = {
            f"{r['record']['source_id']}:{line['source_line_id']}": line
            for r in inputs["sources"]["po"]
            for line in r["record"]["lines"]
        }
        for line_id, target in inputs["allocations"].items():
            row = targets_by_id.get(target)
            if row is None:
                continue
            description = fields.get(f"lines.{line_id}.description", {}).get("effective")
            uom = fields.get(f"lines.{line_id}.uom", {}).get("effective")
            if mapping["item_mappings"].get(description) != row["item_id"]:
                reasons.append("unverified_item_mapping:" + line_id)
            if mapping["uom_mappings"].get(uom, uom) != row["uom"]:
                reasons.append("uom_policy_mismatch:" + line_id)
        return sorted(set(reasons))

    def snapshot(self, document_id, request, context):
        require_any_role(context, {"admin", "reviewer"})
        with self.repo.transaction(context.workspace_id):
            inputs = self.inputs(document_id, request, context)
            blockers = self.blockers(inputs)
            if self.invoice_values(document_id, context)[2]:
                blockers.append("invoice_validation_errors")
            snapshot_id = str(uuid4())
            return self.repo.append(
                context.workspace_id,
                "snapshot",
                snapshot_id,
                {
                    "id": snapshot_id,
                    "document_id": str(document_id),
                    "inputs": inputs,
                    "payload_hash": digest(inputs),
                    "blockers": blockers,
                    "actor": context.actor,
                    "at": now().isoformat(),
                    "scope": "evidence_review_only; matching and posting not yet implemented",
                },
            )

    def approve(self, snapshot_id, expected_hash, context):
        require_any_role(context, {"admin", "ap_approver"})
        with self.repo.transaction(context.workspace_id):
            snapshot = self.repo.latest(context.workspace_id, "snapshot", snapshot_id)
            if not snapshot:
                raise NotFoundError("Snapshot not found")
            if snapshot["payload_hash"] != expected_hash:
                raise EvidenceConflict("Snapshot hash mismatch")
            from app.procurement.models import SnapshotInput

            current = self.inputs(
                snapshot["document_id"],
                SnapshotInput.model_validate(snapshot["inputs"]["request"]),
                context,
            )
            if digest(current) != expected_hash or self.blockers(current):
                raise EvidenceConflict("Snapshot is stale or has missing evidence")
            if self.invoice_values(snapshot["document_id"], context)[2]:
                raise EvidenceConflict("Invoice validation failed")
            if self.repo.latest(context.workspace_id, "approval", snapshot_id):
                raise EvidenceConflict("Snapshot already approved")
            return self.repo.append(
                context.workspace_id,
                "approval",
                snapshot_id,
                {
                    "snapshot_id": snapshot_id,
                    "document_id": snapshot["document_id"],
                    "payload_hash": expected_hash,
                    "actor": context.actor,
                    "at": now().isoformat(),
                    "scope": "evidence_review_only",
                },
            )

    def approval_status(self, snapshot_id, context):
        from app.procurement.models import SnapshotInput

        snapshot = self.repo.latest(context.workspace_id, "snapshot", snapshot_id)
        if not snapshot:
            raise NotFoundError("Snapshot not found")
        self.document(snapshot["document_id"], context)
        approval = self.repo.latest(context.workspace_id, "approval", snapshot_id)
        try:
            current = self.inputs(
                snapshot["document_id"],
                SnapshotInput.model_validate(snapshot["inputs"]["request"]),
                context,
            )
            stale = (
                digest(current) != snapshot["payload_hash"]
                or bool(self.blockers(current))
                or self.invoice_values(snapshot["document_id"], context)[2]
            )
        except EvidenceConflict:
            stale = True
        return {
            "snapshot": snapshot,
            "approval": approval,
            "status": "stale" if stale else ("approved" if approval else "awaiting_approval"),
            "posting_ready": False,
        }
