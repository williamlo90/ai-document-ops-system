# Recruiter Demo Video

**Artifact:** [AI Document Operations System - 4:01 MP4](assets/demo/ai-document-ops-demo.mp4)

The captioned recording is designed for a recruiter or hiring manager who will not clone the
repository before deciding whether to inspect it further.

## What It Shows

1. An uploader selects a synthetic invoice PDF and sees the source document.
2. Extracted fields, source evidence, and deterministic arithmetic checks appear beside the PDF.
3. The invoice is sent to a separate reviewer instead of being auto-approved.
4. The reviewer compares the PDF and fields, records a note, and explicitly approves the invoice.
5. A second PDF with the same vendor and invoice number is detected as a duplicate.
6. The duplicate enters the correction queue and its Approve button remains disabled.
7. The closing card states the measured synthetic evidence and its limitations.

## Evidence Boundary

The video renders the committed synthetic PDFs through the real React PDF viewer. Route-level API
responses are deterministic and stateful so the four-minute product walkthrough is reproducible and
does not depend on hosted-provider latency or credentials.

The recording is therefore evidence of the UI workflow and decision boundaries, not an independent
provider benchmark. Real Mistral OCR and Groq extraction results, the 20-PDF scenario evaluation,
backend enforcement, and audit behavior are documented in the reliability report and case study.

## Regenerate

Prerequisites: the normal frontend dependencies plus internet access the first time the temporary
FFmpeg binary is downloaded.

```powershell
.\scripts\build_demo_video.ps1
```

The script:

- starts the normal Playwright-managed Vite server;
- records the stateful demo at 1280 x 720;
- downloads pinned `ffmpeg-static@5.2.0` into the system temp directory when needed;
- converts the ignored WebM capture to H.264 MP4 with fast-start metadata; and
- writes `docs/assets/demo/ai-document-ops-demo.mp4`.

No API key, private invoice, uploaded runtime file, or customer data is included.

## Presentation Note

The committed version intentionally uses readable captions without synthetic narration. A human
voice-over can follow `docs/demo-script.md` when a spoken version is needed.
