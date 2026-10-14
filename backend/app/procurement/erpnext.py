from __future__ import annotations

from urllib.parse import quote
from app.procurement.models import ProcurementRecord


def read_procurement(client, kind, source_id, site_timezone=None):
    """Bounded GET-only ERP adapter. Import validation remains the same as JSON/CSV."""
    doctype = {"po": "Purchase Order", "receipt": "Purchase Receipt"}[kind]
    response = client._request(
        "GET",
        f"/api/resource/{quote(doctype, safe='')}/{quote(source_id, safe='')}",
        write_request=False,
    )
    data = response.get("data")
    if not isinstance(data, dict) or data.get("name") != source_id:
        raise ValueError("ERP returned the wrong source document")
    if not data.get("modified"):
        raise ValueError("ERP source lacks version timestamp")
    # ERP timestamps are site-local and cannot be assigned a timezone by guessing.
    modified = str(data["modified"])
    from datetime import datetime

    if datetime.fromisoformat(modified).tzinfo is None:
        if not site_timezone:
            raise ValueError(
                "ERP source timestamp requires an explicit site timezone before import"
            )
        from zoneinfo import ZoneInfo

        modified = (
            datetime.fromisoformat(modified).replace(tzinfo=ZoneInfo(site_timezone)).isoformat()
        )
    return ProcurementRecord.model_validate(
        {
            "company": data["company"],
            "kind": kind,
            "source_system": "erpnext",
            "source_id": source_id,
            "source_version": modified,
            "source_updated_at": modified,
            "supplier_id": data["supplier"],
            "currency": data["currency"],
            "status": {0: "draft", 1: "submitted", 2: "cancelled"}[data["docstatus"]],
            "lines": [
                {
                    "source_line_id": r["name"],
                    "item_id": r["item_code"],
                    "uom": r["uom"],
                    "quantity": str(r["qty"]),
                    "unit_price": str(r["rate"]),
                    "amount": str(r["amount"]),
                    "po_id": r.get("purchase_order"),
                    "po_line_id": r.get("purchase_order_item"),
                }
                for r in data["items"]
            ],
        }
    )
