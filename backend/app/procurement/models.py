from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def decimal_value(value):
    if isinstance(value, (float, bool)):
        raise ValueError("Use a decimal string, not a floating-point value")
    try:
        result = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Invalid decimal") from exc
    if not result.is_finite() or abs(result) > Decimal("1e15") or result.as_tuple().exponent < -8:
        raise ValueError("Decimal outside supported precision/range")
    return result


class SourceLine(StrictModel):
    source_line_id: str = Field(min_length=1, max_length=120)
    item_id: str = Field(min_length=1, max_length=120)
    uom: str = Field(min_length=1, max_length=40)
    quantity: Decimal = Field(ge=0)
    unit_price: Decimal = Field(ge=0)
    amount: Decimal = Field(ge=0)
    po_id: str | None = None
    po_line_id: str | None = None
    tax: Decimal | None = Field(default=None, ge=0)
    discount: Decimal | None = Field(default=None, ge=0)

    @field_validator("quantity", "unit_price", "amount", "tax", "discount", mode="before")
    @classmethod
    def decimals(cls, value):
        return None if value is None else decimal_value(value)


class ProcurementRecord(StrictModel):
    company: str = Field(min_length=1, max_length=120)
    kind: Literal["po", "receipt"]
    source_system: str = Field(min_length=1, max_length=80)
    source_id: str = Field(min_length=1, max_length=120)
    source_version: str = Field(min_length=1, max_length=120)
    supplier_id: str = Field(min_length=1, max_length=120)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    status: Literal["submitted", "cancelled", "draft"]
    source_updated_at: datetime
    lines: list[SourceLine] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_source(self):
        if self.source_updated_at.tzinfo is None:
            raise ValueError("Source timestamp requires timezone")
        ids = [line.source_line_id for line in self.lines]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate source line")
        if self.kind == "receipt" and any(
            not line.po_id or not line.po_line_id for line in self.lines
        ):
            raise ValueError("Receipt lines must reference PO and PO line")
        return self


class Mapping(StrictModel):
    company: str = Field(min_length=1, max_length=120)
    supplier_aliases: dict[str, str] = Field(default_factory=dict)
    item_mappings: dict[str, str] = Field(default_factory=dict)
    uom_mappings: dict[str, str] = Field(default_factory=dict)
    reason: str = Field(min_length=3, max_length=1000)

    @model_validator(mode="after")
    def unique_aliases(self):
        for mapping in (self.supplier_aliases, self.item_mappings, self.uom_mappings):
            keys = [" ".join(key.casefold().split()) for key in mapping]
            if (
                len(keys) != len(set(keys))
                or any(not key for key in keys)
                or any(not v.strip() for v in mapping.values())
            ):
                raise ValueError("Empty or colliding mapping")
        return self


class Policy(StrictModel):
    company: str = Field(min_length=1, max_length=120)
    max_age_hours: int = Field(default=24, ge=1, le=720)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    exchange_policy: Literal["same_currency_only"] = "same_currency_only"
    uom_policy: Literal["exact_or_verified_alias"] = "exact_or_verified_alias"
    rounding: Literal["ROUND_HALF_UP"] = "ROUND_HALF_UP"
    reason: str = Field(min_length=3, max_length=1000)


class FieldEvidence(StrictModel):
    kind: Literal["unknown", "observed", "normalized", "derived", "corrected"]
    raw: str | None = None
    normalized: str | None = None
    effective: str | None = None
    page: int | None = Field(default=None, ge=1)
    excerpt: str | None = None
    bbox: tuple[float, float, float, float] | None = None
    transform: str | None = None
    formula: str | None = None
    inputs: list[str] = Field(default_factory=list)
    reason: str | None = None

    @model_validator(mode="after")
    def evidence_requirements(self):
        if self.kind in {"observed", "normalized", "corrected"} and (
            not self.page or not self.excerpt or not self.excerpt.strip()
        ):
            raise ValueError("Page and excerpt required")
        if self.kind == "normalized" and not self.transform:
            raise ValueError("Normalization transform required")
        if self.kind == "derived" and (not self.formula or not self.inputs):
            raise ValueError("Formula and input paths required")
        if self.kind == "corrected" and (not self.reason or len(self.reason.strip()) < 3):
            raise ValueError("Correction reason required")
        if self.bbox is not None:
            x0, y0, x1, y1 = self.bbox
            if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
                raise ValueError("Bounding box must be normalized")
        return self


class EvidenceUpdate(StrictModel):
    expected_revision: int = Field(ge=0)
    fields: dict[str, FieldEvidence]
    reason: str = Field(min_length=3, max_length=1000)


class SnapshotInput(StrictModel):
    company: str = Field(min_length=1, max_length=120)
    expected_revision: int = Field(ge=1)
    po_ids: list[str] = Field(default_factory=list, max_length=30)
    receipt_ids: list[str] = Field(default_factory=list, max_length=30)
    source_system: str = Field(min_length=1, max_length=80)
    # Phase 3 will calculate allocations; these are explicit proposed references only.
    allocations: dict[str, str] = Field(default_factory=dict)


class MatchPolicy(StrictModel):
    company: str = Field(min_length=1, max_length=120)
    effective_from: datetime
    mode: Literal["received", "ordered"] = "received"
    price_tolerance_absolute: Decimal = Field(default=Decimal("0"), ge=0)
    price_tolerance_relative: Decimal = Field(default=Decimal("0"), ge=0, le=1)
    quantity_tolerance: Decimal = Field(default=Decimal("0"), ge=0)
    amount_tolerance: Decimal = Field(default=Decimal("0"), ge=0)
    rounding_places: int = Field(default=2, ge=0, le=4)
    approver_role: Literal["ap_approver", "admin"] = "ap_approver"
    reason: str = Field(min_length=3, max_length=1000)

    @field_validator("price_tolerance_absolute", "price_tolerance_relative", "quantity_tolerance", "amount_tolerance", mode="before")
    @classmethod
    def strict_decimal(cls, value):
        return decimal_value(value)

    @model_validator(mode="after")
    def timezone_required(self):
        if self.effective_from.tzinfo is None:
            raise ValueError("Policy effective date requires timezone")
        return self


class CommittedBilling(StrictModel):
    company: str = Field(min_length=1, max_length=120)
    source_system: str = Field(min_length=1, max_length=80)
    billing_id: str = Field(min_length=1, max_length=120)
    source_version: str = Field(min_length=1, max_length=120)
    source_updated_at: datetime
    po_id: str = Field(min_length=1, max_length=120)
    po_line_id: str = Field(min_length=1, max_length=120)
    uom: str = Field(min_length=1, max_length=40)
    quantity: Decimal = Field(ge=0)
    status: Literal["committed", "cancelled"]

    @field_validator("quantity", mode="before")
    @classmethod
    def strict_quantity(cls, value):
        return decimal_value(value)

    @model_validator(mode="after")
    def timestamp_required(self):
        if self.source_updated_at.tzinfo is None:
            raise ValueError("Billing timestamp requires timezone")
        return self
