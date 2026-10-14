from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP, localcontext
import json
from uuid import uuid4

from app.core.security import require_any_role
from app.documents.repositories import NotFoundError
from app.procurement.models import CommittedBilling, MatchPolicy
from app.procurement.service import EvidenceConflict, digest, key, now


def d(value):
    return Decimal(str(value))


def number(value):
    return format(value, "f")


class MatchService:
    """Immutable assessments and conservative, workspace-locked quantity reservations."""

    def __init__(self, evidence):
        self.evidence = evidence
        self.repo = evidence.repo

    def configure_policy(self, payload: MatchPolicy, context):
        require_any_role(context, {"admin"})
        with self.repo.transaction(context.workspace_id):
            history = self.repo.history(context.workspace_id, "match_policy", payload.company)
            if history and payload.effective_from < datetime.fromisoformat(history[-1]["record"]["effective_from"]):
                raise EvidenceConflict("Policy effective date cannot move backwards")
            return self.repo.append(context.workspace_id, "match_policy", payload.company, {
                "record": payload.model_dump(mode="json"), "actor": context.actor, "at": now().isoformat()
            })

    def import_billings(self, records, context):
        require_any_role(context, {"admin"})
        if not 1 <= len(records) <= 100:
            raise EvidenceConflict("Import must contain 1 to 100 billings")
        parsed = [CommittedBilling.model_validate(r) for r in records]
        ids = [key(r.company, r.source_system, r.billing_id) for r in parsed]
        if len(ids) != len(set(ids)):
            raise EvidenceConflict("Duplicate billing in batch")
        output = []
        with self.repo.transaction(context.workspace_id):
            for record, entity in zip(parsed, ids, strict=True):
                if record.source_updated_at > now():
                    raise EvidenceConflict("Billing timestamp is in the future")
                old = self.repo.latest(context.workspace_id, "billing", entity)
                if old and (old["record"]["source_version"] == record.source_version or record.source_updated_at <= datetime.fromisoformat(old["record"]["source_updated_at"])):
                    raise EvidenceConflict("Billing version must advance")
                output.append(self.repo.append(context.workspace_id, "billing", entity, {
                    "record": record.model_dump(mode="json"), "actor": context.actor, "at": now().isoformat()
                }))
        return output

    def _policy(self, company, invoice_date, workspace):
        policy_date = date.fromisoformat(str(invoice_date))
        eligible = [row for row in self.repo.history(workspace, "match_policy", company)
                    if datetime.fromisoformat(row["record"]["effective_from"]).date() <= policy_date]
        if not eligible:
            raise EvidenceConflict("No matching policy effective for invoice date")
        return eligible[-1]

    def _ledger(self, workspace, company):
        billings = [r for r in self.repo.all_latest(workspace, "billing") if r["record"]["company"] == company]
        reservations = [r for r in self.repo.all_latest(workspace, "reservation") if r["company"] == company]
        return billings, reservations

    def _evaluate(self, snapshot_id, context, *, exclude_match=None):
        snapshot = self.repo.latest(context.workspace_id, "snapshot", snapshot_id)
        if not snapshot:
            raise NotFoundError("Snapshot not found")
        self.evidence.document(snapshot["document_id"], context)
        inputs = snapshot["inputs"]
        company = inputs["request"]["company"]
        fields = inputs["invoice"]["fields"]
        invoice_date = fields.get("invoice_date", {}).get("effective")
        if not invoice_date:
            raise EvidenceConflict("Invoice date is required for policy selection")
        policy = self._policy(company, invoice_date, context.workspace_id)
        rule = policy["record"]
        billings, reservations = self._ledger(context.workspace_id, company)
        issues = []

        def issue(code, line=None, **facts):
            issues.append({"code": code, "line_id": line, "facts": facts})

        evidence_status = self.evidence.approval_status(snapshot_id, context)
        if evidence_status["status"] != "approved":
            issue("evidence_approval_required", status=evidence_status["status"])
        if snapshot["blockers"]:
            for blocker in snapshot["blockers"]:
                issue("evidence_blocker", detail=blocker)
        po_lines = {(r["record"]["source_id"], line["source_line_id"]): line
                    for r in inputs["sources"]["po"] for line in r["record"]["lines"]}
        receipt_lines = {}
        for receipt in inputs["sources"]["receipt"]:
            if receipt["record"]["status"] != "submitted":
                continue
            for line in receipt["record"]["lines"]:
                pair = (line["po_id"], line["po_line_id"])
                po_line = po_lines.get(pair)
                if po_line and line["uom"] != po_line["uom"]:
                    issue("receipt_uom_mismatch", receipt_id=receipt["record"]["source_id"], po_id=pair[0], po_line_id=pair[1], receipt_uom=line["uom"], po_uom=po_line["uom"])
                    continue
                if po_line and line["item_id"] != po_line["item_id"]:
                    issue("receipt_item_mismatch", receipt_id=receipt["record"]["source_id"], po_id=pair[0], po_line_id=pair[1], receipt_item=line["item_id"], po_item=po_line["item_id"])
                    continue
                receipt_lines[pair] = receipt_lines.get(pair, Decimal(0)) + d(line["quantity"])
        quantities = {}
        results = []
        allocated = set()
        quantum = Decimal(1).scaleb(-rule["rounding_places"])
        for line_id in inputs["invoice"]["line_ids"]:
            target = inputs["allocations"].get(line_id)
            if not target or ":" not in target:
                description = fields.get(f"lines.{line_id}.description", {}).get("effective")
                invoice_uom = fields.get(f"lines.{line_id}.uom", {}).get("effective")
                mapping = inputs["mapping"]["record"]
                item_id = mapping["item_mappings"].get(description)
                po_uom = mapping["uom_mappings"].get(invoice_uom, invoice_uom)
                candidates = [f"{po_id}:{po_line_id}" for (po_id, po_line_id), row in po_lines.items()
                              if row["item_id"] == item_id and row["uom"] == po_uom]
                issue("unallocated_line", line_id, candidate_po_lines=sorted(candidates))
                continue
            pairs = [pair for pair in po_lines if f"{pair[0]}:{pair[1]}" == target]
            if len(pairs) != 1:
                issue("ambiguous_po_line" if pairs else "unknown_po_line", line_id, target=target)
                continue
            po_id, po_line_id = pair = pairs[0]
            po_line = po_lines[pair]
            required = [f"lines.{line_id}.{name}" for name in ("quantity", "unit_price", "amount")]
            if any(fields.get(path, {}).get("effective") is None for path in required):
                issue("missing_invoice_value", line_id, fields=required)
                continue
            qty = d(fields[f"lines.{line_id}.quantity"]["effective"])
            price = d(fields[f"lines.{line_id}.unit_price"]["effective"])
            amount = d(fields[f"lines.{line_id}.amount"]["effective"])
            ordered = d(po_line["quantity"])
            received = receipt_lines.get(pair, Decimal(0))
            accepted = min(ordered, received)
            for billing in billings:
                b = billing["record"]
                if b["status"] == "committed" and (b["po_id"], b["po_line_id"]) == pair and b["uom"] != po_line["uom"]:
                    issue("billing_uom_mismatch", line_id, billing_id=b["billing_id"], billing_uom=b["uom"], po_uom=po_line["uom"])
            if received > ordered:
                issue("over_receipt", line_id, ordered=number(ordered), received=number(received))
            billed = sum((d(row["record"]["quantity"]) for row in billings
                          if row["record"]["status"] == "committed" and row["record"]["po_id"] == po_id
                          and row["record"]["po_line_id"] == po_line_id), Decimal(0))
            reserved = sum((d(row["quantity"]) for row in reservations if row["po_id"] == po_id
                            and row["po_line_id"] == po_line_id and row["status"] == "active"
                            and row["match_id"] != exclude_match), Decimal(0))
            capacity = accepted
            available = max(Decimal(0), capacity - billed - reserved)
            expected_price = d(po_line["unit_price"])
            delta = price - expected_price
            threshold = max(d(rule["price_tolerance_absolute"]), abs(expected_price) * d(rule["price_tolerance_relative"]))
            if abs(delta) > threshold:
                issue("price_variance", line_id, expected=number(expected_price), actual=number(price), delta=number(delta), threshold=number(threshold))
            with localcontext() as arithmetic:
                arithmetic.prec = 64
                line_total = (qty * price).quantize(quantum, rounding=ROUND_HALF_UP)
            if abs(line_total - amount) > d(rule["amount_tolerance"]):
                issue("line_amount_mismatch", line_id, expected=number(line_total), actual=number(amount), threshold=rule["amount_tolerance"])
            for component in ("tax", "discount"):
                actual = fields.get(f"lines.{line_id}.{component}", {}).get("effective")
                if actual is not None:
                    expected = po_line.get(component)
                    if expected is None:
                        issue("unverified_line_" + component, line_id, actual=str(actual))
                    elif abs(d(actual) - d(expected)) > d(rule["amount_tolerance"]):
                        issue("line_" + component + "_variance", line_id, expected=str(expected), actual=str(actual), threshold=rule["amount_tolerance"])
            if qty <= 0:
                issue("invalid_quantity", line_id, actual=number(qty))
            if rule["mode"] == "ordered" and received < qty:
                issue("receipt_shortfall", line_id, expected=number(qty), received=number(received))
            quantities[pair] = quantities.get(pair, Decimal(0)) + qty
            allocated.add(pair)
            results.append({"line_id": line_id, "po_id": po_id, "po_line_id": po_line_id,
                            "source_ref": target, "expected_price": number(expected_price), "actual_price": number(price),
                            "price_delta": number(delta), "price_threshold": number(threshold),
                            "ordered": number(ordered), "received": number(received), "billed": number(billed),
                            "reserved": number(reserved), "available": number(available), "invoice_quantity": number(qty),
                            "amount_expected": number(line_total), "amount_actual": number(amount)})
        for pair in sorted(allocated):
            po_line = po_lines[pair]
            ordered = d(po_line["quantity"])
            received = min(ordered, receipt_lines.get(pair, Decimal(0)))
            billed = sum((d(row["record"]["quantity"]) for row in billings if row["record"]["status"] == "committed"
                          and (row["record"]["po_id"], row["record"]["po_line_id"]) == pair), Decimal(0))
            reserved = sum((d(row["quantity"]) for row in reservations if row["status"] == "active"
                            and (row["po_id"], row["po_line_id"]) == pair and row["match_id"] != exclude_match), Decimal(0))
            capacity = received
            available = max(Decimal(0), capacity - billed - reserved)
            if quantities[pair] > available:
                issue("quantity_exceeds_available", None, po_id=pair[0], po_line_id=pair[1],
                      requested=number(quantities[pair]), available=number(available), billed=number(billed), reserved=number(reserved),
                      threshold=rule["quantity_tolerance"], within_tolerance=quantities[pair] <= available + d(rule["quantity_tolerance"]))
        line_amount_sum = sum((d(row["amount_actual"]) for row in results), Decimal(0))
        subtotal = fields.get("subtotal", {}).get("effective")
        if subtotal is not None and len(results) == len(inputs["invoice"]["line_ids"]) and abs(line_amount_sum - d(subtotal)) > d(rule["amount_tolerance"]):
            issue("subtotal_mismatch", expected=number(line_amount_sum), actual=str(subtotal))
        total = fields.get("total", {}).get("effective")
        tax = fields.get("tax", {}).get("effective")
        discount = fields.get("discount", {}).get("effective")
        for component, header in (("tax", tax), ("discount", discount)):
            supplied = [fields.get(f"lines.{line}.{component}", {}).get("effective") for line in inputs["invoice"]["line_ids"]]
            if any(value is not None for value in supplied) and header is not None:
                line_sum = sum((d(value or 0) for value in supplied), Decimal(0))
                if abs(line_sum - d(header)) > d(rule["amount_tolerance"]):
                    issue("line_" + component + "_sum_mismatch", expected=number(line_sum), actual=str(header))
        if total is not None and subtotal is not None:
            expected_total = d(subtotal) + d(tax or 0) - d(discount or 0)
            if abs(expected_total - d(total)) > d(rule["amount_tolerance"]):
                issue("invoice_total_mismatch", expected=number(expected_total), actual=str(total))
        basis = {"snapshot_hash": snapshot["payload_hash"], "evidence_approval": evidence_status["approval"],
                 "policy": policy, "billings": billings, "reservations": [r for r in reservations if r["match_id"] != exclude_match],
                 "sources": inputs["sources"], "invoice_revision": inputs["invoice"]["version"]}
        incomplete = {"evidence_approval_required", "evidence_blocker", "unallocated_line", "unknown_po_line", "ambiguous_po_line", "missing_invoice_value"}
        reviewable = {"unverified_line_tax", "unverified_line_discount"}
        recommendation = ("assessment_incomplete" if any(i["code"] in incomplete for i in issues)
                          else "needs_review" if issues and all(i["code"] in reviewable or
                              (i["code"] == "quantity_exceeds_available" and i["facts"]["within_tolerance"]) for i in issues)
                          else "hold" if issues else "ready_for_approval")
        return {"snapshot_id": snapshot_id, "document_id": snapshot["document_id"], "company": company,
                "policy": policy, "basis_hash": digest(basis), "lines": results, "issues": issues,
                "recommendation": recommendation, "quantities": {key(*pair): number(qty) for pair, qty in quantities.items()}}

    def assess(self, snapshot_id, context):
        require_any_role(context, {"admin", "reviewer", "ap_approver"})
        with self.repo.transaction(context.workspace_id):
            evaluation = self._evaluate(snapshot_id, context)
            match_id = str(uuid4())
            return self.repo.append(context.workspace_id, "match", match_id, {
                **evaluation, "id": match_id, "actor": context.actor, "at": now().isoformat()
            })

    def status(self, match_id, context):
        require_any_role(context, {"admin", "reviewer", "ap_approver"})
        record = self.repo.latest(context.workspace_id, "match", match_id)
        if not record:
            raise NotFoundError("Match not found")
        self.evidence.document(record["document_id"], context)
        approval = self.repo.latest(context.workspace_id, "match_approval", match_id)
        active_own = any(r["match_id"] == match_id and r["status"] == "active"
                         for r in self.repo.all_latest(context.workspace_id, "reservation"))
        try:
            current = self._evaluate(record["snapshot_id"], context, exclude_match=match_id if approval else None)
            stale = current["basis_hash"] != record["basis_hash"] or current["recommendation"] != record["recommendation"]
        except (EvidenceConflict, NotFoundError):
            stale = True
        return {"match": record, "approval": approval,
                "status": "released" if approval and not active_own else ("stale" if stale else ("approved" if approval else record["recommendation"])),
                "posting_ready": False}

    def approve(self, match_id, expected_hash, context):
        require_any_role(context, {"admin", "ap_approver"})
        with self.repo.transaction(context.workspace_id):
            record = self.repo.latest(context.workspace_id, "match", match_id)
            if not record:
                raise NotFoundError("Match not found")
            self.evidence.document(record["document_id"], context)
            if record["policy"]["record"]["approver_role"] == "admin":
                require_any_role(context, {"admin"})
            if record["basis_hash"] != expected_hash or record["recommendation"] != "ready_for_approval":
                raise EvidenceConflict("Match is not ready or hash differs")
            if self.repo.latest(context.workspace_id, "match_approval", match_id):
                raise EvidenceConflict("Match already approved")
            if any(r["status"] == "active" and r["document_id"] == record["document_id"] for r in self.repo.all_latest(context.workspace_id, "reservation")):
                raise EvidenceConflict("Invoice already has an active reservation")
            current = self._evaluate(record["snapshot_id"], context)
            if current["basis_hash"] != expected_hash or current["recommendation"] != "ready_for_approval":
                raise EvidenceConflict("Match changed; reassess")
            approval = self.repo.append(context.workspace_id, "match_approval", match_id, {
                "match_id": match_id, "document_id": record["document_id"], "basis_hash": expected_hash,
                "actor": context.actor, "at": now().isoformat()
            })
            for encoded, qty in record["quantities"].items():
                po_id, po_line_id = json.loads(encoded)
                reservation_id = str(uuid4())
                self.repo.append(context.workspace_id, "reservation", reservation_id, {
                    "id": reservation_id, "match_id": match_id, "document_id": record["document_id"],
                    "company": record["company"], "po_id": po_id, "po_line_id": po_line_id,
                    "quantity": qty, "status": "active", "actor": context.actor, "at": now().isoformat()
                })
            return approval

    def release(self, match_id, reason, reconciliation_ref, context):
        require_any_role(context, {"admin"})
        if len(reason.strip()) < 10 or len(reconciliation_ref.strip()) < 3:
            raise EvidenceConflict("Reconciliation reference and reason required")
        with self.repo.transaction(context.workspace_id):
            record = self.repo.latest(context.workspace_id, "match", match_id)
            if not record:
                raise NotFoundError("Match not found")
            self.evidence.document(record["document_id"], context)
            active = [r for r in self.repo.all_latest(context.workspace_id, "reservation")
                      if r["match_id"] == match_id and r["status"] == "active"]
            if not active:
                raise EvidenceConflict("No active reservation")
            return [self.repo.append(context.workspace_id, "reservation", r["id"], {
                **r, "status": "released", "release_reason": reason,
                "reconciliation_ref": reconciliation_ref, "released_by": context.actor, "released_at": now().isoformat()
            }) for r in active]
