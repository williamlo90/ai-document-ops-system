"""Durable, sandbox-scoped AP posting with separate draft and submit decisions."""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from app.core.security import require_any_role
from app.documents.repositories import NotFoundError
from app.integrations.models import IntegrationDeliveryError
from app.procurement.matching import MatchService
from app.procurement.models import ERPPostingProfile
from app.procurement.posting_contract import draft_request, expected_invoice, money, verify_document, verify_ledger
from app.procurement.service import EvidenceConflict, digest, now


class PostingService:
    def __init__(self, evidence, client, *, sandbox_enabled: bool):
        self.evidence = evidence
        self.repo = evidence.repo
        self.client = client
        self.sandbox_enabled = sandbox_enabled
        self.matching = MatchService(evidence)

    def _enabled(self):
        if not self.sandbox_enabled:
            raise EvidenceConflict("ERP posting requires the explicitly enabled sandbox")

    def configure_profile(self, profile: ERPPostingProfile, context):
        require_any_role(context, {"admin"})
        self._enabled()
        with self.repo.transaction(context.workspace_id):
            return self.repo.append(context.workspace_id, "posting_profile", profile.company, {
                "record": profile.model_dump(mode="json"), "actor": context.actor, "at": now().isoformat()})

    def _fresh(self, match_id, context):
        status = self.matching.status(match_id, context)
        match = status["match"]
        if status["status"] != "approved":
            raise EvidenceConflict("A current approved AP match and active reservation are required")
        latest = self.repo.latest_for_document(context.workspace_id, "match", match["document_id"])
        if not latest or latest["id"] != match_id:
            raise EvidenceConflict("A newer match supersedes this approval")
        snapshot = self.repo.latest(context.workspace_id, "snapshot", match["snapshot_id"])
        profile = self.repo.latest(context.workspace_id, "posting_profile", match["company"])
        if not profile:
            raise EvidenceConflict("A verified ERP posting profile is required")
        return match, snapshot, profile, status["approval"]

    def _operation(self, workspace, kind, match_id):
        return self.repo.latest(workspace, "posting_operation", f"{kind}:{match_id}")

    def _source_fresh(self, snapshot, match, context):
        """The live ERP source must equal the approved snapshot and local billed baseline."""
        inputs = snapshot["inputs"]
        if inputs["request"]["source_system"] != "erpnext":
            raise EvidenceConflict("Only ERPNext-sourced purchasing evidence may be posted")
        billings = [row["record"] for row in self.repo.all_latest(context.workspace_id, "billing")
                    if row["record"]["company"] == match["company"] and row["record"]["status"] == "committed"]
        for kind in ("po", "receipt"):
            for source in inputs["sources"][kind]:
                expected = source["record"]
                actual = self.client.get_procurement_document(kind, expected["source_id"])
                try:
                    recorded_time = datetime.fromisoformat(expected["source_version"]).replace(tzinfo=None)
                    live_time = datetime.fromisoformat(str(actual.get("modified"))).replace(tzinfo=None)
                except ValueError as exc:
                    raise EvidenceConflict("ERP source timestamp is invalid; sync before posting") from exc
                if (actual.get("docstatus") != 1 or actual.get("company") != expected["company"]
                        or actual.get("supplier") != expected["supplier_id"]
                        or actual.get("currency") != expected["currency"] or live_time != recorded_time):
                    raise EvidenceConflict("ERP purchasing source changed; sync and reassess before posting")
                indexed = {row.get("name"): row for row in actual.get("items", [])}
                for line in expected["lines"]:
                    live = indexed.get(line["source_line_id"])
                    if (not live or live.get("item_code") != line["item_id"]
                            or Decimal(str(live.get("qty"))) != Decimal(str(line["quantity"]))
                            or live.get("uom") != line["uom"]):
                        raise EvidenceConflict("ERP purchasing line changed; sync and reassess")
                    if kind == "po":
                        local_billed = sum((Decimal(str(row["quantity"])) * Decimal(str(line["unit_price"]))
                                            for row in billings if row["po_id"] == expected["source_id"]
                                            and row["po_line_id"] == line["source_line_id"]), Decimal(0))
                        if money(live.get("billed_amt") or 0) > money(local_billed):
                            raise EvidenceConflict("ERP PO billing exceeds imported committed billings; sync billing before posting")

    def _save(self, op, context, **changes):
        with self.repo.transaction(context.workspace_id):
            current = self.repo.latest(context.workspace_id, "posting_operation", op["id"])
            if not current or current["version"] != op["version"]:
                raise EvidenceConflict("Posting operation changed; reconcile before retrying")
            return self.repo.append(context.workspace_id, "posting_operation", op["id"], {
                **current, **changes, "at": now().isoformat(), "actor": context.actor})

    def _verify_draft(self, op, actual):
        return verify_document(actual, op["expected"], docstatus=0,
                               operation_key=op["idempotency_key"], document_id=op["document_id"],
                               payload_hash=op["payload_hash"])

    def create_draft(self, match_id, expected_basis_hash, receipt_allocations, context):
        require_any_role(context, {"admin", "ap_approver"})
        self._enabled()
        previous = self._operation(context.workspace_id, "create", match_id)
        if previous:
            self.evidence.document(previous["document_id"], context)
            if (previous["basis_hash"] != expected_basis_hash
                    or previous["receipt_allocations"] != receipt_allocations):
                raise EvidenceConflict("Draft replay differs from its reserved inputs")
            if previous["state"] in {"confirmed", "pending", "unknown", "reconciliation_required"}:
                return previous
        match, snapshot, profile, approval = self._fresh(match_id, context)
        if match["basis_hash"] != expected_basis_hash:
            raise EvidenceConflict("AP match basis differs")
        if not self.client.has_permission("Purchase Invoice", "create"):
            raise EvidenceConflict("Integration identity lacks Purchase Invoice create permission")
        self._source_fresh(snapshot, match, context)
        expected = expected_invoice(snapshot, match, profile, receipt_allocations)
        payload_hash = digest({"expected": expected, "match_basis": match["basis_hash"],
                               "match_approval": approval, "profile": profile})
        identifier = f"create:{match_id}"
        key = f"ap5:{match_id}"
        with self.repo.transaction(context.workspace_id):
            _, _, current_profile, _ = self._fresh(match_id, context)
            if current_profile["version"] != profile["version"]:
                raise EvidenceConflict("ERP profile changed before draft reservation")
            existing = self._operation(context.workspace_id, "create", match_id)
            if existing:
                if existing["payload_hash"] != payload_hash:
                    raise EvidenceConflict("Draft already reserved with different inputs")
                if existing["state"] == "confirmed":
                    return existing
                if existing["state"] in {"pending", "unknown", "reconciliation_required"}:
                    return existing
                if existing["state"] != "failed" or not existing.get("retryable"):
                    raise EvidenceConflict("Draft requires reconciliation before another create attempt")
                op = self.repo.append(context.workspace_id, "posting_operation", identifier, {
                    **existing, "state": "pending", "attempt_count": existing["attempt_count"] + 1,
                    "at": now().isoformat(), "actor": context.actor})
            else:
                other = [item for item in self.repo.all_latest(context.workspace_id, "posting_operation")
                         if item["kind"] == "create" and item["document_id"] == match["document_id"]]
                if other:
                    raise EvidenceConflict("This invoice already has a reserved ERP target")
                op = self.repo.append(context.workspace_id, "posting_operation", identifier, {
                    "id": identifier, "kind": "create", "state": "pending", "document_id": match["document_id"],
                    "match_id": match_id, "basis_hash": match["basis_hash"], "profile_version": profile["version"],
                    "payload_hash": payload_hash, "idempotency_key": key, "expected": expected,
                    "receipt_allocations": receipt_allocations, "target": None, "attempt_count": 1,
                    "retryable": False, "created_at": now().isoformat(), "at": now().isoformat(), "actor": context.actor})
        # A retryable failure is checked against ERP first, even if an HTTP error claimed no write.
        if op["attempt_count"] > 1:
            recovered = self.reconcile(match_id, "create", context)
            if recovered["state"] in {"confirmed", "reconciliation_required"}:
                return recovered
        target = ""
        try:
            response = self.client.create_purchase_invoice(draft_request(expected, operation_key=key,
                                                                          document_id=match["document_id"], payload_hash=payload_hash))
            target = str(response.get("name") or "")
            if not target:
                raise IntegrationDeliveryError("Draft create receipt lacks target", code="erpnext_invalid_receipt",
                                               retryable=False, outcome_unknown=True)
            actual = self.client.get_purchase_invoice(target)
            verification_hash = self._verify_draft(op, actual)
        except IntegrationDeliveryError as exc:
            uncertain = exc.outcome_unknown or bool(target)
            return self._save(op, context, state="unknown" if uncertain else "failed", target=target or None,
                              retryable=exc.retryable and not uncertain, error_code=exc.code)
        except EvidenceConflict as exc:
            return self._save(op, context, state="reconciliation_required", target=target,
                              error_code="draft_readback_mismatch", error_detail=str(exc))
        return self._save(op, context, state="confirmed", target=target, verification_hash=verification_hash,
                          verified_modified=str(actual["modified"]), receipt={"docstatus": 0, "name": target})

    def approve_submit(self, match_id, operation_id, draft_verification_hash, reason, context):
        require_any_role(context, {"admin", "ap_approver"})
        self._enabled()
        match, _, profile, _ = self._fresh(match_id, context)
        op = self._operation(context.workspace_id, "create", match_id)
        if not op or op["id"] != operation_id or op["state"] != "confirmed" or op.get("verification_hash") != draft_verification_hash or op["profile_version"] != profile["version"]:
            raise EvidenceConflict("A verified draft is required for submit approval")
        actual = self.client.get_purchase_invoice(op["target"])
        if self._verify_draft(op, actual) != draft_verification_hash:
            raise EvidenceConflict("ERP draft changed after verification")
        approval_hash = digest({"match_basis": match["basis_hash"], "profile": profile,
                                "draft_verification": draft_verification_hash, "target": op["target"]})
        with self.repo.transaction(context.workspace_id):
            _, _, current_profile, _ = self._fresh(match_id, context)
            if current_profile["version"] != profile["version"]:
                raise EvidenceConflict("ERP profile changed during submit approval")
            if self.repo.latest(context.workspace_id, "posting_submit_approval", match_id):
                raise EvidenceConflict("Submit approval already recorded")
            return self.repo.append(context.workspace_id, "posting_submit_approval", match_id, {
                "document_id": match["document_id"], "match_id": match_id, "operation_id": operation_id,
                "target": op["target"], "draft_verification_hash": draft_verification_hash,
                "profile_version": profile["version"], "approval_hash": approval_hash,
                "reason": reason, "actor": context.actor, "at": now().isoformat()})

    def _verify_posted(self, op, actual):
        document_hash = verify_document(actual, op["expected"], docstatus=1,
                                        operation_key=op["idempotency_key"], document_id=op["document_id"],
                                        payload_hash=op["payload_hash"])
        ledger_hash = verify_ledger(self.client.get_gl_entries(op["target"]), op["expected"], target=op["target"])
        return document_hash, ledger_hash

    def submit_draft(self, match_id, approval_hash, context):
        require_any_role(context, {"admin", "ap_approver"})
        self._enabled()
        previous = self._operation(context.workspace_id, "submit", match_id)
        if previous:
            self.evidence.document(previous["document_id"], context)
            if previous["approval_hash"] != approval_hash:
                raise EvidenceConflict("Submit replay differs from the approved request")
            return previous
        match, snapshot, profile, _ = self._fresh(match_id, context)
        draft = self._operation(context.workspace_id, "create", match_id)
        approved = self.repo.latest(context.workspace_id, "posting_submit_approval", match_id)
        if not draft or draft["state"] != "confirmed" or not approved or approved["approval_hash"] != approval_hash:
            raise EvidenceConflict("Separate submit approval is required")
        if approved["target"] != draft["target"] or approved["profile_version"] != profile["version"]:
            raise EvidenceConflict("Draft or ERP profile changed after submit approval")
        if not self.client.has_permission("Purchase Invoice", "submit", name=draft["target"]):
            raise EvidenceConflict("Integration identity lacks Purchase Invoice submit permission")
        self._source_fresh(snapshot, match, context)
        with self.repo.transaction(context.workspace_id):
            _, _, current_profile, _ = self._fresh(match_id, context)
            if current_profile["version"] != profile["version"]:
                raise EvidenceConflict("ERP profile changed before submit reservation")
            existing = self._operation(context.workspace_id, "submit", match_id)
            if existing:
                return existing
            op = self.repo.append(context.workspace_id, "posting_operation", f"submit:{match_id}", {
                "id": f"submit:{match_id}", "kind": "submit", "state": "pending",
                "document_id": match["document_id"], "match_id": match_id, "basis_hash": match["basis_hash"],
                "profile_version": profile["version"], "payload_hash": draft["payload_hash"],
                "idempotency_key": draft["idempotency_key"], "expected": draft["expected"],
                "target": draft["target"], "draft_verification_hash": approved["draft_verification_hash"],
                "approval_hash": approval_hash, "attempt_count": 1,
                "created_at": now().isoformat(), "at": now().isoformat(), "actor": context.actor})
        try:
            self._source_fresh(snapshot, match, context)
            actual = self.client.get_purchase_invoice(draft["target"])
            if self._verify_draft(draft, actual) != approved["draft_verification_hash"]:
                raise EvidenceConflict("ERP draft changed after submit approval")
            self.client.submit_purchase_invoice(actual)
            posted = self.client.get_purchase_invoice(draft["target"])
            document_hash, ledger_hash = self._verify_posted(op, posted)
        except EvidenceConflict as exc:
            return self._save(op, context, state="reconciliation_required", error_code="submit_verification_mismatch",
                              error_detail=str(exc))
        except IntegrationDeliveryError as exc:
            return self._save(op, context, state="unknown" if exc.outcome_unknown else "reconciliation_required",
                              error_code=exc.code)
        return self._save(op, context, state="confirmed", receipt={"docstatus": 1, "name": draft["target"]},
                          document_hash=document_hash, ledger_hash=ledger_hash, posted_verified=True)

    def reconcile(self, match_id, kind, context):
        require_any_role(context, {"admin", "ap_approver"})
        self._enabled()
        op = self._operation(context.workspace_id, kind, match_id)
        if not op:
            raise NotFoundError("Posting operation not found")
        self.evidence.document(op["document_id"], context)
        if op["state"] == "confirmed":
            return op
        if kind == "create":
            matches = self.client.find_purchase_invoices_by_delivery_key(op["idempotency_key"])
            if len(matches) > 1:
                return self._save(op, context, state="reconciliation_required", error_code="duplicate_erp_target")
            if not matches:
                return op
            target = str(matches[0].get("name") or "")
            if op.get("target") and target != op["target"]:
                return self._save(op, context, state="reconciliation_required", error_code="erp_target_changed")
            actual = self.client.get_purchase_invoice(target)
            try:
                verification_hash = self._verify_draft(op, actual)
            except EvidenceConflict as exc:
                return self._save(op, context, state="reconciliation_required", target=target,
                                  error_code="draft_readback_mismatch", error_detail=str(exc))
            return self._save(op, context, state="confirmed", target=target, verification_hash=verification_hash,
                              verified_modified=str(actual["modified"]), receipt={"docstatus": 0, "name": target})
        if kind != "submit" or not op.get("target"):
            raise EvidenceConflict("Unknown posting operation kind or target")
        actual = self.client.get_purchase_invoice(op["target"])
        if actual.get("docstatus") == 0:
            return op
        if actual.get("docstatus") != 1:
            return self._save(op, context, state="reconciliation_required", error_code="erp_target_not_submitted")
        try:
            document_hash, ledger_hash = self._verify_posted(op, actual)
        except (EvidenceConflict, IntegrationDeliveryError) as exc:
            return self._save(op, context, state="reconciliation_required", error_code="posted_verification_mismatch",
                              error_detail=str(exc))
        return self._save(op, context, state="confirmed", receipt={"docstatus": 1, "name": op["target"]},
                          document_hash=document_hash, ledger_hash=ledger_hash, posted_verified=True)

    def confirm_create_absent_for_retry(self, match_id, context):
        """An admin may retry a stranded create only after two negative ERP lookups."""
        require_any_role(context, {"admin"})
        self._enabled()
        op = self._operation(context.workspace_id, "create", match_id)
        if not op:
            raise NotFoundError("Draft operation not found")
        self.evidence.document(op["document_id"], context)
        if op["state"] not in {"pending", "unknown"} or op.get("target"):
            raise EvidenceConflict("Only a targetless pending or unknown draft can be retried")
        if now() - datetime.fromisoformat(op["at"]) < timedelta(seconds=30):
            raise EvidenceConflict("Wait for ERP visibility before declaring a draft absent")
        for _ in range(2):
            if self.client.find_purchase_invoices_by_delivery_key(op["idempotency_key"]):
                raise EvidenceConflict("ERP draft exists; reconcile it instead of retrying")
        return self._save(op, context, state="failed", retryable=True,
                          error_code="confirmed_absent_for_retry",
                          error_detail="Two ERP lookups found no target; retry uses the same unique delivery key")

    def status(self, match_id, context):
        require_any_role(context, {"admin", "reviewer", "ap_approver"})
        match = self.matching.status(match_id, context)
        profile = self.repo.latest(context.workspace_id, "posting_profile", match["match"]["company"])
        return {"match_status": match["status"], "sandbox_enabled": self.sandbox_enabled,
                "profile_version": profile["version"] if profile else None,
                "draft": self._operation(context.workspace_id, "create", match_id),
                "submit_approval": self.repo.latest(context.workspace_id, "posting_submit_approval", match_id),
                "submit": self._operation(context.workspace_id, "submit", match_id),
                "posted_verified": bool((self._operation(context.workspace_id, "submit", match_id) or {}).get("posted_verified"))}
