"""Independent ERP expectation and strict read-back checks for AP-reviewed invoices."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from app.procurement.service import EvidenceConflict, digest


def money(value):
    try:
        result = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError) as exc:
        raise EvidenceConflict("ERP amount is missing or invalid") from exc
    if not result.is_finite():
        raise EvidenceConflict("ERP amount is not finite")
    return result


def number(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise EvidenceConflict("ERP numeric value is missing or invalid") from exc
    if not result.is_finite():
        raise EvidenceConflict("ERP numeric value is not finite")
    return result


def value(fields, path):
    result = fields.get(path, {}).get("effective")
    if result is None:
        raise EvidenceConflict(f"Missing reviewed invoice value: {path}")
    return str(result)


def expected_invoice(snapshot, match, profile, receipt_allocations):
    """Derive the independent oracle from reviewed evidence and verified master data."""
    inputs = snapshot["inputs"]
    if inputs["request"]["source_system"] != "erpnext":
        raise EvidenceConflict("Only ERPNext-sourced purchasing evidence may be posted")
    fields = inputs["invoice"]["fields"]
    mapping = inputs["mapping"]["record"]
    rules = profile["record"]
    if any(
        source["record"]["company"] != rules["erp_company"]
        for kind in ("po", "receipt")
        for source in inputs["sources"][kind]
    ):
        raise EvidenceConflict("ERP company must match every linked purchase order and receipt")
    canonical = {k.casefold(): v for k, v in mapping["supplier_aliases"].items()}
    supplier_id = canonical.get(value(fields, "vendor_name").casefold())
    supplier = rules["supplier_ids"].get(supplier_id or "")
    currency = value(fields, "currency")
    payable = rules["payable_accounts"].get(currency)
    rate = rules["exchange_rates"].get(currency)
    if not supplier or not payable or not rate:
        raise EvidenceConflict("Verified supplier, payable account and exchange rate are required")
    po_lines = {
        (r["record"]["source_id"], line["source_line_id"]): line
        for r in inputs["sources"]["po"]
        for line in r["record"]["lines"]
    }
    receipts = {}
    for source in inputs["sources"]["receipt"]:
        if source["record"]["status"] != "submitted":
            continue
        for line in source["record"]["lines"]:
            receipts.setdefault((line["po_id"], line["po_line_id"]), []).append(
                (source["record"]["source_id"], line)
            )
    rows = []
    matched = {row["line_id"]: row for row in match["lines"]}
    for line_id in inputs["invoice"]["line_ids"]:
        line_match = matched.get(line_id)
        if not line_match:
            raise EvidenceConflict("Every invoice line requires an approved PO allocation")
        po_id, po_line_id = line_match["source_ref"].split(":", 1)
        po_line = po_lines[(po_id, po_line_id)]
        item_id = po_line["item_id"]
        item_code = rules["item_codes"].get(item_id)
        expense = rules["expense_accounts"].get(item_id)
        if not item_code or not expense:
            raise EvidenceConflict("Verified item and expense account mappings are required")
        possible = receipts.get((po_id, po_line_id), [])
        chosen = receipt_allocations.get(line_id)
        if chosen:
            selected = [
                (receipt_id, line)
                for receipt_id, line in possible
                if f"{receipt_id}:{line['source_line_id']}" == chosen
            ]
        else:
            selected = possible if len(possible) == 1 else []
        if len(selected) != 1:
            raise EvidenceConflict("Choose one accepted receipt line for each invoice line")
        receipt_id, receipt_line = selected[0]
        qty = Decimal(value(fields, f"lines.{line_id}.quantity"))
        if qty > Decimal(str(receipt_line["quantity"])):
            raise EvidenceConflict("Invoice line exceeds its selected receipt line")
        rows.append(
            {
                "item_code": item_code,
                "description": value(fields, f"lines.{line_id}.description"),
                "qty": str(qty),
                "uom": po_line["uom"],
                "rate": str(money(value(fields, f"lines.{line_id}.unit_price"))),
                "amount": str(money(value(fields, f"lines.{line_id}.amount"))),
                "expense_account": expense,
                "purchase_order": po_id,
                "po_detail": po_line_id,
                "purchase_receipt": receipt_id,
                "pr_detail": receipt_line["source_line_id"],
            }
        )
    subtotal = money(value(fields, "subtotal"))
    tax = money(value(fields, "tax"))
    discount = money(fields.get("discount", {}).get("effective") or "0")
    total = money(value(fields, "total"))
    if (
        sum((money(row["amount"]) for row in rows), Decimal(0)) != subtotal
        or subtotal + tax - discount != total
    ):
        raise EvidenceConflict("Reviewed invoice totals do not reconcile for ERP posting")
    if tax and not rules["tax_accounts"].get(currency):
        raise EvidenceConflict("Tax account mapping is required for taxed invoices")
    expected = {
        "doctype": "Purchase Invoice",
        "company": rules["erp_company"],
        "supplier": supplier,
        "posting_date": value(fields, "invoice_date"),
        "bill_date": value(fields, "invoice_date"),
        "bill_no": value(fields, "invoice_number"),
        "currency": currency,
        "conversion_rate": str(rate),
        "credit_to": payable,
        "items": rows,
        "subtotal": str(subtotal),
        "tax": str(tax),
        "discount": str(discount),
        "grand_total": str(total),
        "tax_account": rules["tax_accounts"].get(currency),
    }
    if fields.get("due_date", {}).get("effective"):
        expected["due_date"] = value(fields, "due_date")
    return expected


def draft_request(expected, *, operation_key, document_id, payload_hash):
    request = {
        key: expected[key]
        for key in (
            "doctype",
            "company",
            "supplier",
            "posting_date",
            "bill_date",
            "bill_no",
            "currency",
            "credit_to",
        )
    }
    request.update(
        {
            "conversion_rate": expected["conversion_rate"],
            "set_posting_time": 1,
            "docstatus": 0,
            "items": [
                {
                    k: row[k]
                    for k in (
                        "item_code",
                        "description",
                        "qty",
                        "uom",
                        "rate",
                        "expense_account",
                        "purchase_order",
                        "po_detail",
                        "purchase_receipt",
                        "pr_detail",
                    )
                }
                for row in expected["items"]
            ],
            "custom_invoice_review_delivery_key": operation_key,
            "custom_invoice_review_document_id": document_id,
            "custom_invoice_review_payload_hash": payload_hash,
        }
    )
    if expected.get("due_date"):
        request["due_date"] = expected["due_date"]
    if money(expected["tax"]):
        request["taxes"] = [
            {
                "charge_type": "Actual",
                "account_head": expected["tax_account"],
                "tax_amount": expected["tax"],
                "description": "Reviewed invoice tax",
            }
        ]
    if money(expected["discount"]):
        request.update(
            {"apply_discount_on": "Grand Total", "discount_amount": expected["discount"]}
        )
    return request


def verify_document(actual, expected, *, docstatus, operation_key, document_id, payload_hash):
    if not isinstance(actual, dict) or str(actual.get("name") or "") == "":
        raise EvidenceConflict("ERP returned an incomplete Purchase Invoice")
    if actual.get("docstatus") != docstatus:
        raise EvidenceConflict("ERP Purchase Invoice has the wrong docstatus")
    required = {
        key: expected[key]
        for key in (
            "doctype",
            "company",
            "supplier",
            "posting_date",
            "bill_date",
            "bill_no",
            "currency",
            "credit_to",
        )
    }
    if expected.get("due_date"):
        required["due_date"] = expected["due_date"]
    required.update(
        {
            "custom_invoice_review_delivery_key": operation_key,
            "custom_invoice_review_document_id": document_id,
            "custom_invoice_review_payload_hash": payload_hash,
        }
    )
    for key, value in required.items():
        if str(actual.get(key) or "") != str(value):
            raise EvidenceConflict(f"ERP Purchase Invoice field differs: {key}")
    if number(actual.get("conversion_rate")) != number(expected["conversion_rate"]):
        raise EvidenceConflict("ERP exchange rate differs")
    if money(actual.get("grand_total")) != money(expected["grand_total"]):
        raise EvidenceConflict("ERP grand total differs")
    if money(actual.get("net_total")) != money(expected["subtotal"]):
        raise EvidenceConflict("ERP subtotal differs")
    if money(actual.get("discount_amount") or 0) != money(expected["discount"]):
        raise EvidenceConflict("ERP discount differs")
    rows = actual.get("items")
    if not isinstance(rows, list) or len(rows) != len(expected["items"]):
        raise EvidenceConflict("ERP invoice line count differs")
    text_fields = (
        "item_code",
        "description",
        "uom",
        "expense_account",
        "purchase_order",
        "po_detail",
        "purchase_receipt",
        "pr_detail",
    )
    numeric_fields = ("qty", "rate", "amount")
    for actual_row, wanted in zip(rows, expected["items"], strict=True):
        if not isinstance(actual_row, dict):
            raise EvidenceConflict("ERP invoice line is invalid")
        for key in text_fields:
            if str(actual_row.get(key) or "") != str(wanted[key]):
                raise EvidenceConflict(f"ERP invoice line differs: {key}")
        for key in numeric_fields:
            actual_number = (
                number(actual_row.get(key)) if key == "qty" else money(actual_row.get(key))
            )
            wanted_number = number(wanted[key]) if key == "qty" else money(wanted[key])
            if actual_number != wanted_number:
                raise EvidenceConflict(f"ERP invoice line differs: {key}")
    taxes = actual.get("taxes") or []
    if money(expected["tax"]):
        if (
            len(taxes) != 1
            or taxes[0].get("account_head") != expected["tax_account"]
            or money(taxes[0].get("tax_amount")) != money(expected["tax"])
        ):
            raise EvidenceConflict("ERP tax row differs")
    elif taxes:
        raise EvidenceConflict("ERP has unexpected tax rows")
    if not actual.get("modified"):
        raise EvidenceConflict("ERP document has no version timestamp")
    return digest(
        {
            "name": actual["name"],
            "modified": actual["modified"],
            "expected": expected,
            "docstatus": docstatus,
        }
    )


def verify_ledger(rows, expected, *, target):
    if not rows:
        raise EvidenceConflict("Submitted invoice has no readable GL entries")
    for row in rows:
        if (
            row.get("voucher_type") != "Purchase Invoice"
            or row.get("voucher_no") != target
            or row.get("company") != expected["company"]
            or row.get("is_cancelled") not in (0, False)
        ):
            raise EvidenceConflict("GL entry identity differs from the invoice")
    debit = sum((money(row.get("debit")) for row in rows), Decimal(0))
    credit = sum((money(row.get("credit")) for row in rows), Decimal(0))
    total_base = money(Decimal(expected["grand_total"]) * Decimal(expected["conversion_rate"]))
    payable = sum(
        (
            money(row.get("credit")) - money(row.get("debit"))
            for row in rows
            if row.get("account") == expected["credit_to"]
        ),
        Decimal(0),
    )
    if debit != credit or payable != total_base or debit < total_base:
        raise EvidenceConflict("GL balance or payable does not match the submitted invoice")
    expected_debits = {}
    for item in expected["items"]:
        account = item["expense_account"]
        expected_debits[account] = expected_debits.get(account, Decimal(0)) + money(item["amount"])
    discount = money(expected["discount"])
    if discount:
        subtotal = money(expected["subtotal"])
        accounts = sorted(expected_debits)
        allocated = Decimal(0)
        for account in accounts[:-1]:
            share = money(discount * expected_debits[account] / subtotal)
            expected_debits[account] -= share
            allocated += share
        expected_debits[accounts[-1]] -= discount - allocated
    if money(expected["tax"]):
        tax_account = expected["tax_account"]
        expected_debits[tax_account] = expected_debits.get(tax_account, Decimal(0)) + money(
            expected["tax"]
        )
    rate = number(expected["conversion_rate"])
    for account, amount in expected_debits.items():
        actual = sum(
            (
                money(row.get("debit")) - money(row.get("credit"))
                for row in rows
                if row.get("account") == account
            ),
            Decimal(0),
        )
        if actual != money(amount * rate):
            raise EvidenceConflict(f"GL amount differs for configured account: {account}")
    allowed = set(expected_debits) | {expected["credit_to"]}
    if any(
        row.get("account") not in allowed and (money(row.get("debit")) or money(row.get("credit")))
        for row in rows
    ):
        raise EvidenceConflict("GL contains an unexpected nonzero account")
    return digest(sorted(rows, key=lambda row: str(row.get("name"))))
