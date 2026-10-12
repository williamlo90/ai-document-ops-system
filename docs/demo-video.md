# Demo Recording

**Artifact:** [AI-Powered Invoice Review & Approval System demo](assets/demo/invoice-review-demo.mp4)

The recording uses the real React routes and PDF viewer with deterministic, stateful API fixtures.
It demonstrates interface behavior and safety boundaries without provider credentials or latency.

Regenerate it with:

```powershell
.\scripts\build_demo_video.ps1
```

The script records the six active product routes, converts the Playwright WebM to an H.264
fast-start MP4, and writes both files under `docs/assets/demo`.

The video is not provider-benchmark evidence. Accuracy, latency, cost, failure iterations, and known
limits are documented under the [evidence index](INDEX.md).

## ERPNext Draft walkthrough

The recorded Exports screen uses fixtures and focuses on the CSV flow. To inspect the ERPNext
interaction in the live local sandbox, first complete the
[ERPNext environment prerequisites](erpnext-environment.md), including provisioned master data and
the integration user. Then:

1. Upload a synthetic invoice, review its extracted fields, and approve it.
2. Open **Exports** with `ACCOUNTING_PROVIDER=erpnext`. On the approved invoice row, select
   **Create ERP draft**.
3. Confirm the row status reads **ERP draft created** and use **Open in ERPNext** to inspect the
   resulting Purchase Invoice. In ERPNext, verify it remains **Draft** (`docstatus = 0`).

This path creates a draft only; it does not submit or pay the invoice. The technical verification is
recorded in [ERPNext Phase 7 verification](erpnext-phase7-verification.md).
