# Object Storage Boundary

Status: Step 5 foundation

Project 2 separates document object storage from metadata persistence.

## Current Adapter

The current implemented adapter is local private filesystem storage:

```text
DOCUMENT_STORAGE_BACKEND=local
UPLOAD_ROOT=/data/uploads
```

Uploaded documents stay behind storage keys and are not exposed as public/static files.

## Cloudflare R2 Target

The configuration shape is reserved now so the later adapter can be added without changing product architecture:

```text
DOCUMENT_STORAGE_BACKEND=s3
S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
S3_BUCKET=docintel-private
S3_REGION=auto
S3_ACCESS_KEY_ID=...
S3_SECRET_ACCESS_KEY=...
```

The S3-compatible adapter is implemented for Cloudflare R2 and MinIO. Objects
remain private and browser downloads use short-lived presigned URLs. `local`
remains the zero-credential default for development. Bucket encryption and
lifecycle/retention rules are configured in the R2 account and must be verified
as part of the deployment checklist.

## Rules

- Store private uploads outside public/static folders.
- Persist only storage keys in document records.
- Do not expose storage keys in public API/UI responses unless explicitly needed for internal debugging.
- Do not include private uploads in public artifacts.
- Do not log raw document contents.
- App and worker must read files through the `DocumentStorage` boundary.

## Current Interface

The storage boundary is represented by `DocumentStorage`:

```text
save_upload(...)
save_upload_stream(...)
open_for_parser(storage_key)
```

This is deliberately small. It supports the current app/worker parser flow while leaving room for the R2-compatible adapter later.
