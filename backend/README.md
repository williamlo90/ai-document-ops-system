# Backend

Backend service for the AI Document Operations System.

The API supports local-first document intake, invoice evidence validation, review queues,
approval-gated document operations, AgentOps evaluation, and bounded back-office workflows.
Invoice is the first complete document workflow; generic document contracts are additive and
must preserve compatibility aliases.

Run tests from this directory:

```powershell
$env:PYTHONPATH = "."
python -m unittest discover -s app/tests
```

Run the API from this directory:

```powershell
$env:PYTHONPATH = "."
$env:APP_ADMIN_TOKEN = "dev-token"
uvicorn app.main:app --reload
```

Then call protected endpoints with:

```text
X-Admin-Token: dev-token
```
