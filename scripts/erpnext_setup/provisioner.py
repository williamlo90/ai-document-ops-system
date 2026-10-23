from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .api import ERPNextAPIError, ERPNextAdminClient
from .dataset import BenchmarkDataset


MANUAL_COMPANY = "Invoice Review Manual Benchmark"
ASSISTED_COMPANY = "Invoice Review Assisted Benchmark"
COMPANY_ABBREVIATIONS = {MANUAL_COMPANY: "IRM", ASSISTED_COMPANY: "IRA"}
METHOD_SUFFIXES = {MANUAL_COMPANY: "Manual", ASSISTED_COMPANY: "Assisted"}
INTEGRATION_ROLE = "Invoice Draft Integration"
PURCHASE_INVOICE_CUSTOM_FIELDS = (
    {
        "label": "Invoice Review Delivery Key",
        "fieldname": "custom_invoice_review_delivery_key",
        "insert_after": "bill_no",
        "unique": 1,
    },
    {
        "label": "Invoice Review Document ID",
        "fieldname": "custom_invoice_review_document_id",
        "insert_after": "custom_invoice_review_delivery_key",
        "unique": 0,
    },
    {
        "label": "Invoice Review Payload Hash",
        "fieldname": "custom_invoice_review_payload_hash",
        "insert_after": "custom_invoice_review_document_id",
        "unique": 0,
    },
)
READ_ONLY_DOCTYPES = (
    "Account",
    "Company",
    "Cost Center",
    "Currency",
    "Currency Exchange",
    "Fiscal Year",
    "Item",
    "Purchase Taxes and Charges Template",
    "Supplier",
    "Supplier Group",
    "UOM",
)


@dataclass(frozen=True)
class ProvisioningReport:
    dataset_id: str
    dataset_fingerprint_sha256: str
    companies: tuple[str, ...]
    supplier_mappings: dict[str, dict[str, str]]
    item_code: str
    expense_accounts: dict[str, str]
    payable_accounts: dict[str, dict[str, str]]
    tax_templates: dict[str, dict[str, str | None]]
    case_outcomes: dict[str, str]
    purchase_invoice_custom_fields: tuple[str, ...]

    def to_json(self) -> str:
        return json.dumps(
            {
                "dataset_id": self.dataset_id,
                "dataset_fingerprint_sha256": self.dataset_fingerprint_sha256,
                "companies": self.companies,
                "supplier_mappings": self.supplier_mappings,
                "item_code": self.item_code,
                "expense_accounts": self.expense_accounts,
                "payable_accounts": self.payable_accounts,
                "tax_templates": self.tax_templates,
                "case_outcomes": self.case_outcomes,
                "purchase_invoice_custom_fields": self.purchase_invoice_custom_fields,
            },
            indent=2,
            sort_keys=True,
        )


class MasterDataProvisioner:
    def __init__(self, client: ERPNextAdminClient, dataset: BenchmarkDataset) -> None:
        self.client = client
        self.dataset = dataset

    def provision(self) -> ProvisioningReport:
        self._ensure_initial_setup()
        self._ensure_company(ASSISTED_COMPANY)
        self._enable_currencies()
        self._ensure_exchange_rates()
        self._enable_supplier_invoice_uniqueness()
        self._ensure_item()
        self._ensure_integration_role()
        self._ensure_purchase_invoice_custom_fields()

        supplier_mappings = self._ensure_suppliers()
        expense_accounts: dict[str, str] = {}
        payable_accounts: dict[str, dict[str, str]] = {}
        tax_templates: dict[str, dict[str, str | None]] = {}
        for company in COMPANY_ABBREVIATIONS:
            expense_accounts[company] = self._ensure_expense_account(company)
            payable_accounts[company] = self._ensure_payable_accounts(company)
            tax_templates[company] = self._ensure_tax_templates(company)
        self._ensure_supplier_party_accounts(supplier_mappings, payable_accounts)

        return ProvisioningReport(
            dataset_id=self.dataset.dataset_id,
            dataset_fingerprint_sha256=self.dataset.fingerprint,
            companies=tuple(COMPANY_ABBREVIATIONS),
            supplier_mappings=supplier_mappings,
            item_code=self.dataset.default_item_code,
            expense_accounts=expense_accounts,
            payable_accounts=payable_accounts,
            tax_templates=tax_templates,
            case_outcomes={case.case_id: case.erp_outcome for case in self.dataset.cases},
            purchase_invoice_custom_fields=tuple(
                str(field["fieldname"]) for field in PURCHASE_INVOICE_CUSTOM_FIELDS
            ),
        )

    def verify(self) -> ProvisioningReport:
        report = self.provision()
        for company, abbreviation in COMPANY_ABBREVIATIONS.items():
            record = self.client.get_document("Company", company)
            _require_values(
                record,
                {
                    "abbr": abbreviation,
                    "country": "United States",
                    "default_currency": self.dataset.base_currency,
                },
                f"Company {company}",
            )

        for case in self.dataset.cases:
            if case.supplier_name is None and case.erp_outcome != "blocked_missing_supplier":
                raise ERPNextAPIError(
                    f"{case.case_id} has no supplier but is not explicitly blocked."
                )
            if case.erp_outcome == "draft_eligible" and case.supplier_name is None:
                raise ERPNextAPIError(f"{case.case_id} cannot map to an ERPNext Supplier.")

        integration_user = self.client.get_document("User", "invoice.integration@local.test")
        roles = {str(row.get("role")) for row in integration_user.get("roles", [])}
        if roles != {INTEGRATION_ROLE}:
            raise ERPNextAPIError(
                "ERPNext integration user roles do not match the locked boundary."
            )
        purchase_permission = self.client.find_one(
            "Custom DocPerm",
            {"parent": "Purchase Invoice", "role": INTEGRATION_ROLE, "permlevel": 0},
            fields=("name", "read", "write", "create", "submit", "cancel", "delete"),
        )
        if purchase_permission is None:
            raise ERPNextAPIError("Purchase Invoice integration permission is missing.")
        _require_values(
            purchase_permission,
            {"read": 1, "write": 1, "create": 1, "submit": 0, "cancel": 0, "delete": 0},
            "Purchase Invoice integration permission",
        )
        payment_permissions = self.client.list_documents(
            "Custom DocPerm",
            filters={"parent": "Payment Entry", "role": INTEGRATION_ROLE},
            fields=("name", "permlevel", "read", "write", "create", "submit", "cancel", "delete"),
        )
        if payment_permissions:
            raise ERPNextAPIError(
                "The ERPNext integration role must not have Payment Entry permissions."
            )
        missing_fields = {
            fieldname
            for fieldname in report.purchase_invoice_custom_fields
            if self.client.find_one(
                "Custom Field",
                {"dt": "Purchase Invoice", "fieldname": fieldname},
            )
            is None
        }
        if missing_fields:
            raise ERPNextAPIError(
                f"Purchase Invoice integration fields are missing: {sorted(missing_fields)}"
            )
        return report

    def _ensure_initial_setup(self) -> None:
        companies = self.client.list_documents("Company", fields=("name", "abbr"))
        if companies:
            names = {str(row["name"]) for row in companies}
            unexpected = names - set(COMPANY_ABBREVIATIONS)
            if unexpected:
                raise ERPNextAPIError(
                    f"ERPNext contains unexpected companies: {sorted(unexpected)}"
                )
            if MANUAL_COMPANY not in names:
                self._ensure_company(MANUAL_COMPANY)
            return

        setup_args = {
            "language": "English",
            "country": "United States",
            "timezone": "Asia/Jakarta",
            "currency": self.dataset.base_currency,
            "company_name": MANUAL_COMPANY,
            "company_abbr": COMPANY_ABBREVIATIONS[MANUAL_COMPANY],
            "chart_of_accounts": "Standard",
            "fy_start_date": "2026-01-01",
            "fy_end_date": "2026-12-31",
            "setup_demo": 0,
            "enable_telemetry": 0,
            "persona_implementing_for": "A client I'm consulting for",
            "persona_company_size": "1-10",
            "persona_industry": "Services / Consulting",
            "persona_current_system": "Nothing yet - starting fresh",
            "module_accounting": 1,
            "module_stock": 0,
            "module_manufacturing": 0,
            "module_projects": 0,
        }
        response = self.client.call_method(
            "frappe.desk.page.setup_wizard.setup_wizard.setup_complete",
            values={"args": json.dumps(setup_args, separators=(",", ":"))},
        )
        if not isinstance(response, dict) or response.get("status") != "ok":
            raise ERPNextAPIError("ERPNext setup wizard did not complete successfully.")
        if self.client.find_one("Company", {"name": MANUAL_COMPANY}) is None:
            raise ERPNextAPIError("ERPNext setup completed without creating the benchmark company.")

    def _ensure_company(self, company: str) -> None:
        abbreviation = COMPANY_ABBREVIATIONS[company]
        existing = self.client.find_one("Company", {"name": company})
        expected = {
            "abbr": abbreviation,
            "country": "United States",
            "default_currency": self.dataset.base_currency,
        }
        if existing:
            _require_values(
                self.client.get_document("Company", company), expected, f"Company {company}"
            )
            return
        created = self.client.create_document(
            "Company",
            {
                "company_name": company,
                "abbr": abbreviation,
                "country": "United States",
                "default_currency": self.dataset.base_currency,
                "create_chart_of_accounts_based_on": "Standard Template",
                "chart_of_accounts": "Standard",
                "valuation_method": "FIFO",
            },
        )
        _require_values(created, expected, f"Company {company}")

    def _enable_currencies(self) -> None:
        for currency in {case.currency for case in self.dataset.cases}:
            record = self.client.get_document("Currency", currency)
            if int(record.get("enabled") or 0) != 1:
                self.client.update_document("Currency", currency, {"enabled": 1})

    def _ensure_exchange_rates(self) -> None:
        for rate in self.dataset.exchange_rates:
            filters = {
                "date": rate["date"],
                "from_currency": rate["from_currency"],
                "to_currency": rate["to_currency"],
                "for_buying": 1,
            }
            existing = self.client.find_one(
                "Currency Exchange",
                filters,
                fields=("name", "exchange_rate"),
            )
            if existing:
                if str(existing.get("exchange_rate")) not in {
                    rate["exchange_rate"],
                    str(float(rate["exchange_rate"])),
                }:
                    raise ERPNextAPIError("Existing benchmark currency exchange rate conflicts.")
                continue
            self.client.create_document(
                "Currency Exchange",
                {
                    **filters,
                    "exchange_rate": float(rate["exchange_rate"]),
                    "for_selling": 0,
                },
            )

    def _enable_supplier_invoice_uniqueness(self) -> None:
        settings = self.client.get_document("Accounts Settings", "Accounts Settings")
        if int(settings.get("check_supplier_invoice_uniqueness") or 0) != 1:
            self.client.update_document(
                "Accounts Settings",
                "Accounts Settings",
                {"check_supplier_invoice_uniqueness": 1},
            )

    def _ensure_item(self) -> None:
        existing = self.client.find_one("Item", {"name": self.dataset.default_item_code})
        expected = {
            "item_name": self.dataset.default_item_name,
            "item_group": "Services",
            "stock_uom": "Nos",
            "is_stock_item": 0,
        }
        if existing:
            _require_values(
                self.client.get_document("Item", self.dataset.default_item_code),
                expected,
                "Benchmark item",
            )
            return
        created = self.client.create_document(
            "Item",
            {
                "item_code": self.dataset.default_item_code,
                **expected,
                "is_purchase_item": 1,
                "is_sales_item": 0,
                "include_item_in_manufacturing": 0,
                "description": "Non-stock service used by the controlled invoice benchmark.",
            },
        )
        _require_values(created, expected, "Benchmark item")

    def _ensure_integration_role(self) -> None:
        role = self.client.find_one("Role", {"name": INTEGRATION_ROLE})
        if role is None:
            self.client.create_document(
                "Role",
                {"role_name": INTEGRATION_ROLE, "desk_access": 0, "disabled": 0},
            )

        self._ensure_custom_permission(
            "Purchase Invoice",
            read=1,
            write=1,
            create=1,
        )
        for doctype in READ_ONLY_DOCTYPES:
            self._ensure_custom_permission(doctype, read=1, select=1)

        user = self.client.get_document("User", "invoice.integration@local.test")
        roles = {str(row.get("role")) for row in user.get("roles", [])}
        if roles != {INTEGRATION_ROLE}:
            self.client.update_document(
                "User",
                "invoice.integration@local.test",
                {"roles": [{"role": INTEGRATION_ROLE}]},
            )

    def _ensure_custom_permission(self, doctype: str, **grants: int) -> None:
        filters = {"parent": doctype, "role": INTEGRATION_ROLE, "permlevel": 0}
        expected = {
            "read": 0,
            "write": 0,
            "create": 0,
            "delete": 0,
            "submit": 0,
            "cancel": 0,
            "select": 0,
            **grants,
        }
        fields = ("name", *expected.keys())
        existing = self.client.find_one("Custom DocPerm", filters, fields=fields)
        if existing:
            _require_values(existing, expected, f"{doctype} integration permission")
            return
        self.client.create_document("Custom DocPerm", {**filters, **expected})

    def _ensure_purchase_invoice_custom_fields(self) -> None:
        for definition in PURCHASE_INVOICE_CUSTOM_FIELDS:
            fieldname = str(definition["fieldname"])
            expected = {
                "dt": "Purchase Invoice",
                "label": definition["label"],
                "fieldname": fieldname,
                "fieldtype": "Data",
                "insert_after": definition["insert_after"],
                "unique": definition["unique"],
                "no_copy": 1,
                "read_only": 1,
                "print_hide": 1,
                "allow_on_submit": 0,
            }
            existing = self.client.find_one(
                "Custom Field",
                {"dt": "Purchase Invoice", "fieldname": fieldname},
            )
            if existing:
                record = self.client.get_document("Custom Field", str(existing["name"]))
                _require_values(record, expected, f"Custom Field {fieldname}")
                continue
            self.client.create_document("Custom Field", expected)

    def _ensure_suppliers(self) -> dict[str, dict[str, str]]:
        mappings: dict[str, dict[str, str]] = {"manual": {}, "assisted": {}}
        for source_name, country, currency in self.dataset.suppliers:
            for company, suffix in METHOD_SUFFIXES.items():
                method = "manual" if company == MANUAL_COMPANY else "assisted"
                erp_name = f"{source_name} - {suffix} Benchmark"
                mappings[method][source_name] = erp_name
                expected = {
                    "supplier_name": erp_name,
                    "supplier_type": "Company",
                    "supplier_group": "Services",
                    "country": country,
                    "default_currency": currency,
                }
                existing = self.client.find_one("Supplier", {"name": erp_name})
                if existing:
                    _require_values(
                        self.client.get_document("Supplier", erp_name),
                        expected,
                        f"Supplier {erp_name}",
                    )
                    continue
                created = self.client.create_document("Supplier", expected)
                _require_values(created, expected, f"Supplier {erp_name}")
        return mappings

    def _ensure_expense_account(self, company: str) -> str:
        abbreviation = COMPANY_ABBREVIATIONS[company]
        account_name = f"Professional Services - {abbreviation}"
        existing = self.client.find_one("Account", {"name": account_name})
        if existing:
            return account_name
        parent = self._find_account_group(
            company,
            preferred_names=("Indirect Expenses", "Expenses"),
            root_type="Expense",
        )
        created = self.client.create_document(
            "Account",
            {
                "account_name": "Professional Services",
                "company": company,
                "parent_account": parent,
                "is_group": 0,
            },
        )
        return str(created["name"])

    def _require_company_payable_account(self, company: str) -> str:
        record = self.client.get_document("Company", company)
        account = record.get("default_payable_account")
        if not account:
            raise ERPNextAPIError(f"Company {company} has no default payable account.")
        return str(account)

    def _ensure_payable_accounts(self, company: str) -> dict[str, str]:
        abbreviation = COMPANY_ABBREVIATIONS[company]
        accounts = {self.dataset.base_currency: self._require_company_payable_account(company)}
        foreign_currencies = sorted(
            {currency for _, _, currency in self.dataset.suppliers} - {self.dataset.base_currency}
        )
        parent = self._find_account_group(
            company,
            preferred_names=("Accounts Payable", "Current Liabilities"),
            root_type="Liability",
        )
        for currency in foreign_currencies:
            account_name = f"Creditors {currency} - {abbreviation}"
            existing = self.client.find_one("Account", {"name": account_name})
            if existing is None:
                created = self.client.create_document(
                    "Account",
                    {
                        "account_name": f"Creditors {currency}",
                        "company": company,
                        "parent_account": parent,
                        "account_type": "Payable",
                        "account_currency": currency,
                        "is_group": 0,
                    },
                )
                account_name = str(created["name"])
            record = self.client.get_document("Account", account_name)
            _require_values(
                record,
                {
                    "company": company,
                    "account_type": "Payable",
                    "account_currency": currency,
                    "is_group": 0,
                },
                f"{currency} payable account for {company}",
            )
            accounts[currency] = account_name
        return accounts

    def _ensure_supplier_party_accounts(
        self,
        supplier_mappings: dict[str, dict[str, str]],
        payable_accounts: dict[str, dict[str, str]],
    ) -> None:
        for source_name, _, currency in self.dataset.suppliers:
            for company, suffix in METHOD_SUFFIXES.items():
                method = "manual" if suffix == "Manual" else "assisted"
                supplier_name = supplier_mappings[method][source_name]
                account = payable_accounts[company][currency]
                supplier = self.client.get_document("Supplier", supplier_name)
                current_accounts = [
                    row for row in supplier.get("accounts", []) if row.get("company") != company
                ]
                current_accounts.append({"company": company, "account": account})
                saved = self.client.update_document(
                    "Supplier",
                    supplier_name,
                    {"accounts": current_accounts},
                )
                matching = [
                    row
                    for row in saved.get("accounts", [])
                    if row.get("company") == company and row.get("account") == account
                ]
                if len(matching) != 1:
                    raise ERPNextAPIError(
                        f"Supplier {supplier_name} has no unique payable account mapping."
                    )

    def _ensure_tax_templates(self, company: str) -> dict[str, str | None]:
        abbreviation = COMPANY_ABBREVIATIONS[company]
        tax_account = f"Benchmark Input Tax - {abbreviation}"
        if self.client.find_one("Account", {"name": tax_account}) is None:
            parent = self._find_account_group(
                company,
                preferred_names=("Duties and Taxes", "Current Liabilities"),
                root_type="Liability",
            )
            created = self.client.create_document(
                "Account",
                {
                    "account_name": "Benchmark Input Tax",
                    "company": company,
                    "parent_account": parent,
                    "account_type": "Tax",
                    "is_group": 0,
                },
            )
            tax_account = str(created["name"])

        result: dict[str, str | None] = {"0": None}
        for rate in ("10", "20"):
            title = f"Benchmark Input Tax {rate}%"
            existing = self.client.find_one(
                "Purchase Taxes and Charges Template",
                {"title": title, "company": company},
            )
            if existing:
                result[rate] = str(existing["name"])
                continue
            created = self.client.create_document(
                "Purchase Taxes and Charges Template",
                {
                    "title": title,
                    "company": company,
                    "is_default": 0,
                    "disabled": 0,
                    "taxes": [
                        {
                            "category": "Total",
                            "add_deduct_tax": "Add",
                            "charge_type": "On Net Total",
                            "account_head": tax_account,
                            "description": f"Benchmark input tax {rate}%",
                            "rate": float(rate),
                        }
                    ],
                },
            )
            result[rate] = str(created["name"])
        return result

    def _find_account_group(
        self,
        company: str,
        *,
        preferred_names: tuple[str, ...],
        root_type: str,
    ) -> str:
        rows = self.client.list_documents(
            "Account",
            filters={"company": company, "is_group": 1, "root_type": root_type},
            fields=("name", "account_name", "parent_account"),
        )
        for preferred in preferred_names:
            match = next((row for row in rows if row.get("account_name") == preferred), None)
            if match:
                return str(match["name"])
        if not rows:
            raise ERPNextAPIError(f"No {root_type} account group exists for {company}.")
        return str(rows[0]["name"])


def write_private_report(report: ProvisioningReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.to_json() + "\n", encoding="utf-8")


def _require_values(
    record: dict[str, Any],
    expected: dict[str, Any],
    label: str,
) -> None:
    conflicts = {
        field: (record.get(field), expected_value)
        for field, expected_value in expected.items()
        if not _same_value(record.get(field), expected_value)
    }
    if conflicts:
        raise ERPNextAPIError(f"{label} conflicts with locked master data: {conflicts}")


def _same_value(actual: Any, expected: Any) -> bool:
    if isinstance(expected, int):
        try:
            return int(actual or 0) == expected
        except (TypeError, ValueError):
            return False
    return actual == expected
