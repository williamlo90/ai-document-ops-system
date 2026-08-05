from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.extraction.schemas import InvoiceData
from app.review.corrections import CorrectionFeedbackService
from app.review.datasets import sanitized_correction_summary
from app.review.models import CorrectionSource
from app.review.repositories import InMemoryCorrectionEventRepository


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate the reviewer-correction feedback contract with synthetic data."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "docs" / "evidence" / "reviewer-correction-feedback-v1.json",
    )
    args = parser.parse_args()

    repository = InMemoryCorrectionEventRepository()
    service = CorrectionFeedbackService(repository)
    document_id = UUID("00000000-0000-0000-0000-000000000201")
    ai_output = InvoiceData(
        vendor_name="Synthetic Vendor",
        invoice_number="SYN-001",
        invoice_date=date(2026, 7, 15),
        subtotal=Decimal("100.00"),
        tax=Decimal("10.00"),
        total=Decimal("100.00"),
        currency="USD",
    )
    no_op = service.capture(
        workspace_id="evaluation",
        document_id=document_id,
        before=ai_output,
        after=ai_output,
        actor="synthetic-uploader",
        reason="No change",
        source=CorrectionSource.INTAKE_CHECK,
    )
    first_output = replace(ai_output, vendor_name="Synthetic Vendor Ltd", total=Decimal("110.00"))
    first = service.capture(
        workspace_id="evaluation",
        document_id=document_id,
        before=ai_output,
        after=first_output,
        actor="synthetic-uploader",
        reason="Matched the PDF.",
        source=CorrectionSource.INTAKE_CHECK,
    )
    second_output = replace(first_output, currency="IDR")
    second = service.capture(
        workspace_id="evaluation",
        document_id=document_id,
        before=first_output,
        after=second_output,
        actor="synthetic-uploader",
        reason=None,
        requested_reason="Use the printed currency.",
        source=CorrectionSource.INTAKE_CHECK,
    )
    summary = sanitized_correction_summary(repository.records)
    summary_text = json.dumps(summary, sort_keys=True)
    checks = {
        "no_op_save_ignored": no_op is None,
        "first_diff_captured": bool(first and len(first.changes) == 2),
        "sequential_diff_captured": bool(second and len(second.changes) == 1),
        "original_ai_snapshot_preserved": bool(
            first and second and first.original_ai_data == second.original_ai_data == ai_output
        ),
        "reviewer_reason_carried_forward": bool(
            second and second.reason == "Use the printed currency."
        ),
        "public_summary_excludes_sensitive_values": all(
            value not in summary_text
            for value in (
                "Synthetic Vendor",
                "SYN-001",
                "synthetic-uploader",
                str(document_id),
            )
        ),
    }
    report = {
        "evaluation_id": "reviewer_correction_feedback_v1",
        "evidence_type": "deterministic_synthetic_contract",
        "scenario_count": len(checks),
        "passed_count": sum(checks.values()),
        "failed_count": len(checks) - sum(checks.values()),
        "passed": all(checks.values()),
        "checks": checks,
        "aggregate_example": summary,
        "claim_boundary": (
            "This proves deterministic correction lineage and privacy filtering, not user adoption "
            "or model improvement on real invoices."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
