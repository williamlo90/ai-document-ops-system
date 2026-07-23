# Backend

Backend for Invoice Review, an approval-gated invoice intake, validation, correction, and export
workflow.

The API supports local-first document intake, deterministic invoice validation, reviewer
decisions, audit evidence, controlled exports, and bounded reliability evaluation. Some internal
`backoffice` and `agentops` namespaces are compatibility boundaries inherited from the workflow
engine; they are not public product vocabulary.

Run tests from this directory:

```powershell
$env:PYTHONPATH = "."
python -m unittest discover -s app/tests
```

Run the API from this directory:

```powershell
$env:PYTHONPATH = "."
$env:APP_ADMIN_TOKEN = "123"
$env:APP_UPLOADER_TOKEN = "uploader-123"
$env:APP_REVIEWER_TOKEN = "reviewer-123"
uvicorn app.main:app --reload
```

Browser login exchanges one of those credentials for an opaque session. The backend assigns the
principal and workspace; browser-supplied identity headers are ignored. For direct local admin API
calls, use:

```text
X-Admin-Token: 123
```

Role-specific direct API calls use `X-Access-Token` with the uploader or reviewer credential.
Hosted modes require unique credentials of at least 24 non-default characters.
