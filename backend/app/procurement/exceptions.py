from __future__ import annotations

from decimal import Decimal

from app.core.security import require_any_role
from app.documents.repositories import NotFoundError
from app.procurement.models import ExceptionPolicy, ExceptionUpdate
from app.procurement.service import EvidenceConflict, digest, now


NON_WAIVABLE = {"duplicate_confirmed", "evidence_approval_required", "evidence_blocker",
               "unallocated_line", "unknown_po_line", "ambiguous_po_line", "missing_invoice_value",
               "quantity_exceeds_available", "receipt_shortfall", "unknown_erp_outcome"}


def case_id(document_id, issue):
    facts = issue.get("facts", {})
    identity = {"document_id": document_id, "code": issue["code"], "line_id": issue.get("line_id"),
                "source": facts.get("other_document_id") or facts.get("po_id") or facts.get("detail")}
    return digest(identity)[:32]


class ExceptionService:
    def __init__(self, evidence):
        self.evidence = evidence
        self.repo = evidence.repo

    def configure_policy(self, policy: ExceptionPolicy, context):
        require_any_role(context, {"admin"})
        with self.repo.transaction(context.workspace_id):
            return self.repo.append(context.workspace_id, "exception_policy", policy.company,
                                    {"record": policy.model_dump(mode="json"), "actor": context.actor, "at": now().isoformat()})

    def sync_for_match(self, match, context):
        """Called under the match transaction. A changed basis reopens recurring issues."""
        workspace = context.workspace_id
        existing = {r["id"]: r for r in self.repo.all_latest(workspace, "ap_exception")
                    if r["document_id"] == match["document_id"]}
        current = {}
        for issue in match["issues"]:
            identifier = case_id(match["document_id"], issue)
            current[identifier] = issue
            prior = existing.get(identifier)
            retain = prior and prior["basis_hash"] == match["basis_hash"] and prior["state"] in {"needs_info", "waived"}
            self.repo.append(workspace, "ap_exception", identifier, {
                "id": identifier, "document_id": match["document_id"], "company": match["company"],
                "code": issue["code"], "line_id": issue.get("line_id"), "issue": issue,
                "state": prior["state"] if retain else "open", "owner": prior["owner"] if prior else None,
                "reason": prior.get("reason") if retain else "Detected by current match",
                "evidence_refs": prior.get("evidence_refs", []) if retain else [],
                "authorizer": prior.get("authorizer") if retain else None,
                "waiver_policy_version": prior.get("waiver_policy_version") if retain else None,
                "match_id": match["id"], "basis_hash": match["basis_hash"],
                "created_at": prior["created_at"] if prior else now().isoformat(),
                "at": now().isoformat(), "actor": context.actor,
            })
        for identifier, prior in existing.items():
            if identifier not in current and prior["state"] != "superseded":
                self.repo.append(workspace, "ap_exception", identifier, {
                    **prior, "state": "superseded", "reason": "Issue absent in current reassessment",
                    "match_id": match["id"], "basis_hash": match["basis_hash"],
                    "at": now().isoformat(), "actor": context.actor,
                })

    def list_cases(self, context, *, document_id=None):
        require_any_role(context, {"admin", "reviewer", "ap_approver"})
        rows = [r for r in self.repo.all_latest(context.workspace_id, "ap_exception")
                if document_id is None or r["document_id"] == str(document_id)]
        if document_id is not None:
            self.evidence.document(document_id, context)
        priority = {"duplicate_confirmed": 0, "evidence_blocker": 1, "quantity_exceeds_available": 2,
                    "price_variance": 3, "duplicate_candidate": 4}
        return sorted(rows, key=lambda r: (r["state"] in {"resolved", "superseded", "waived"},
                                           priority.get(r["code"], 5), r["created_at"], r["id"]))

    def _waiver_allowed(self, case, policy):
        if case["code"] in NON_WAIVABLE or not policy:
            return False
        rules = policy["record"]
        if case["code"] not in rules["allowed_waivers"]:
            return False
        if case["code"] == "price_variance":
            return abs(Decimal(str(case["issue"]["facts"]["delta"]))) <= Decimal(str(rules["max_price_delta"]))
        return case["code"] == "duplicate_candidate"

    def update(self, identifier, update: ExceptionUpdate, context, matching):
        require_any_role(context, {"admin", "reviewer", "ap_approver"})
        with self.repo.transaction(context.workspace_id):
            case = self.repo.latest(context.workspace_id, "ap_exception", identifier)
            if not case:
                raise NotFoundError("AP exception not found")
            self.evidence.document(case["document_id"], context)
            if case["version"] != update.expected_version or case["match_id"] != update.expected_match_id:
                raise EvidenceConflict("Exception changed; reload before decision")
            if case["state"] == "superseded" and update.state != "resolved":
                raise EvidenceConflict("Superseded issue cannot be reopened without a new match")
            match = self.repo.latest_for_document(context.workspace_id, "match", case["document_id"])
            if not match or matching.status(match["id"], context)["status"] == "stale":
                raise EvidenceConflict("Match is stale; reassess before exception action")
            current = matching._evaluate(match["snapshot_id"], context)
            present = any(case_id(match["document_id"], issue) == identifier for issue in current["issues"])
            if update.state == "resolved":
                if present:
                    raise EvidenceConflict("Issue remains; correct the source and reassess")
            elif match["id"] != case["match_id"]:
                raise EvidenceConflict("Exception belongs to an older match")
            policy = self.repo.latest(context.workspace_id, "exception_policy", case["company"])
            if update.state == "waived":
                require_any_role(context, {"admin"})
                if not present or not self._waiver_allowed(case, policy):
                    raise EvidenceConflict("This issue cannot be waived by current policy")
            elif update.state in {"open", "needs_info", "resolved"}:
                require_any_role(context, {"admin", "reviewer"})
            return self.repo.append(context.workspace_id, "ap_exception", identifier, {
                **case, "state": update.state, "owner": update.owner, "reason": update.reason,
                "evidence_refs": update.evidence_refs, "authorizer": context.actor if update.state == "waived" else None,
                "waiver_policy_version": policy["version"] if update.state == "waived" and policy else None,
                "match_id": match["id"], "basis_hash": match["basis_hash"],
                "at": now().isoformat(), "actor": context.actor,
            })

    def all_issues_cleared(self, match, context):
        if not match["issues"]:
            return True
        policy = self.repo.latest(context.workspace_id, "exception_policy", match["company"])
        for issue in match["issues"]:
            case = self.repo.latest(context.workspace_id, "ap_exception", case_id(match["document_id"], issue))
            if not case or case["state"] != "waived" or case["basis_hash"] != match["basis_hash"]:
                return False
            if not self._waiver_allowed(case, policy) or case["waiver_policy_version"] != policy["version"]:
                return False
        return True
