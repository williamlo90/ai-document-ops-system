from __future__ import annotations

from datetime import date
from decimal import Decimal
import re

from app.procurement.service import digest


def normalize_supplier(value: str | None) -> str:
    return " ".join((value or "").casefold().split())


def normalize_number(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())[:120]


def ocr_skeleton(value: str) -> str:
    return value.translate(str.maketrans({"O": "0", "I": "1", "L": "1", "S": "5", "B": "8"}))


def canonical_supplier(value: str | None, aliases: dict[str, str]) -> str | None:
    normalized = normalize_supplier(value)
    indexed = {normalize_supplier(alias): supplier for alias, supplier in aliases.items()}
    return indexed.get(normalized)


def _value(fields, name):
    return fields.get(name, {}).get("effective")


def detect_duplicates(repo, workspace: str, snapshot: dict) -> dict:
    """Use only the product's current, reviewed evidence; candidates never approve themselves."""
    current = snapshot["inputs"]
    company = current["request"]["company"]
    fields = current["invoice"]["fields"]
    aliases = current["mapping"]["record"]["supplier_aliases"]
    supplier = canonical_supplier(_value(fields, "vendor_name"), aliases)
    number = normalize_number(_value(fields, "invoice_number"))
    amount = _value(fields, "total")
    invoice_date = _value(fields, "invoice_date")
    if not supplier or not number or amount is None or not invoice_date:
        return {"confirmed": [], "candidates": [], "corpus_hash": digest([])}
    reviewed = all(
        fields.get(path, {}).get("attestation") == "reviewer_verified"
        for path in ("vendor_name", "invoice_number", "invoice_date", "total")
    )
    if not reviewed:
        return {"confirmed": [], "candidates": [], "corpus_hash": digest([])}
    current_date = date.fromisoformat(invoice_date)
    current_amount = Decimal(str(amount))
    current_po = set(current["request"]["po_ids"])
    most_recent = {}
    for candidate in repo.all_latest(workspace, "snapshot"):
        if (
            candidate["inputs"]["request"]["company"] != company
            or candidate["document_id"] == snapshot["document_id"]
        ):
            continue
        prior = most_recent.get(candidate["document_id"])
        if prior is None or candidate["at"] > prior["at"]:
            most_recent[candidate["document_id"]] = candidate
    confirmed = []
    candidates = []
    considered = []
    for other in most_recent.values():
        other_inputs = other["inputs"]
        current_other = repo.latest(workspace, "invoice", other["document_id"])
        other_fields = (current_other or other_inputs["invoice"])["fields"]
        other_supplier = canonical_supplier(_value(other_fields, "vendor_name"), aliases)
        other_number = normalize_number(_value(other_fields, "invoice_number"))
        other_amount = _value(other_fields, "total")
        other_date = _value(other_fields, "invoice_date")
        if other_supplier != supplier or other_amount is None:
            continue
        if not all(
            other_fields.get(path, {}).get("attestation") == "reviewer_verified"
            for path in ("vendor_name", "total")
        ):
            continue
        days = abs((current_date - date.fromisoformat(other_date)).days) if other_date else None
        same_amount = Decimal(str(other_amount)) == current_amount
        po_overlap = bool(current_po.intersection(other_inputs["request"]["po_ids"]))
        identity_reviewed = all(
            other_fields.get(path, {}).get("attestation") == "reviewer_verified"
            for path in ("invoice_number", "invoice_date")
        )
        if not other_number or not other_date or not identity_reviewed:
            # An unresolved invoice on the same PO must not disappear from the
            # safety corpus merely because OCR omitted its identity. This is a
            # review candidate, never proof of a confirmed duplicate.
            if same_amount and po_overlap and (days is None or days <= 30):
                signal = {
                    "document_id": other["document_id"],
                    "snapshot_id": other["id"],
                    "invoice_number": other_number,
                    "days_apart": days,
                    "same_amount": True,
                    "po_overlap": True,
                    "number_relation": "incomplete_identity",
                    "invoice_revision": (current_other or other_inputs["invoice"])["version"],
                }
                candidates.append(signal)
                considered.append(signal)
            continue
        exact = number == other_number
        ocr_like = (
            not exact
            and len(number) == len(other_number)
            and ocr_skeleton(number) == ocr_skeleton(other_number)
        )
        if not exact and not ocr_like:
            continue
        signal = {
            "document_id": other["document_id"],
            "snapshot_id": other["id"],
            "invoice_number": other_number,
            "days_apart": days,
            "same_amount": same_amount,
            "po_overlap": po_overlap,
            "number_relation": "exact" if exact else "ocr_candidate",
            "invoice_revision": (current_other or other_inputs["invoice"])["version"],
        }
        if exact and same_amount and days <= 30 and (days <= 1 or po_overlap):
            confirmed.append(signal)
            considered.append(signal)
        elif exact and days <= 30 and ((same_amount and days <= 7) or po_overlap):
            candidates.append(signal)
            considered.append(signal)
        elif ocr_like and days <= 30 and same_amount and (days <= 1 or po_overlap):
            candidates.append(signal)
            considered.append(signal)
    return {
        "confirmed": sorted(confirmed, key=lambda r: r["document_id"]),
        "candidates": sorted(candidates, key=lambda r: r["document_id"]),
        "corpus_hash": digest(sorted(considered, key=lambda r: r["document_id"])),
    }
