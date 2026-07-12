# Backend

Initial backend foundation for Doc Intel MVP.

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
