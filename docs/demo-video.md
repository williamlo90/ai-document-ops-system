# Recruiter Demo Video

**Artifact:** [AI Document Operations System - captioned MP4](assets/demo/ai-document-ops-demo.mp4)

**Runtime:** 3 minutes 53 seconds at 1280 x 720, H.264.

The recording is designed for a recruiter or hiring manager who will not clone the repository
before deciding whether to inspect it further.

## What It Shows

1. Overview turns invoice activity into a clear decision queue.
2. Invoices and Review Queue expose the source PDF, ownership, confidence, risk, and validation
   finding without granting approval authority to the model.
3. Invoice Review places source evidence, extracted data, line items, and reviewer actions together.
4. A deterministic blocker prevents approval and routes the invoice through Exceptions and the
   uploader correction loop.
5. A completed approval exposes actor, timestamp, audit consequence, and export eligibility.
6. Exports demonstrates approved-only batches, eligibility checks, idempotent execution, and
   failure-aware retry evidence.
7. Evaluation and System expose bounded model-quality, cost, and operational evidence outside the
   daily review workflow.

## Evidence Boundary

The video renders a committed synthetic PDF through the real React PDF viewer. Route-level API
responses are deterministic and stateful so the product walkthrough remains reproducible without
provider credentials or latency.

The recording is evidence of UI behavior and decision boundaries, not an independent provider
benchmark. Provider runs, evaluation history, costs, failure iterations, and known limitations are
documented separately in the reliability and evaluation evidence.

## Regenerate

```powershell
.\scripts\build_demo_video.ps1
```

The script records the current route tree at 1600 x 900, scales the video to 1280 x 720, downloads
the pinned `ffmpeg-static@5.2.0` binary into the system temp directory when needed, and writes an
H.264 fast-start MP4 under `docs/assets/demo`.

No API key, private invoice, uploaded runtime file, or customer data is included.
