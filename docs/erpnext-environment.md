# ERPNext Local Environment

Status: operational; provider, ERPNext auth, and Draft integration smoke tests passed
Last verified: 2026-08-14

This environment supports the draft Purchase Invoice integration and controlled workflow benchmark.
It is an isolated local sandbox, not a production ERP deployment.

## Installed Environment

- Source: official `frappe/frappe_docker` repository at commit
  `e33f185a0cb14980f1fb8a24989df18f0a41d86b`.
- ERP image: `frappe/erpnext:v16.32.0`.
- Installed apps: Frappe `16.31.0` and ERPNext `16.32.0`.
- Local URL: `http://127.0.0.1:8080`.
- Site name: `frontend`.
- Compose project: `invoice-erpnext`.
- Local source and runtime data: `_private_data/erpnext-sandbox/frappe_docker`.

The runtime directory is ignored by Git. Do not move its volumes, database, backups, or credentials
into a tracked directory.

## Access Controls

- The default ERPNext Administrator password was replaced with a random local password.
- The application integration uses `invoice.integration@local.test`, not Administrator.
- The integration user has the custom `Invoice Draft Integration` role. It can read ERP mappings
  and create or update a draft Purchase Invoice, but it cannot submit, cancel, or delete one.
- API key, API secret, and the local Administrator password are stored only in the ignored `.env`.
- Application code does not load or use the Administrator password.
- The broad ERPNext `Accounts User` role was removed after Phase 4 showed that it also grants submit
  and cancel permissions.

## Start and Verify

Start Docker Desktop, then run from the ignored Frappe Docker checkout:

```powershell
docker compose -p invoice-erpnext -f pwd.yml up -d
docker compose -p invoice-erpnext -f pwd.yml ps
```

Run the project smoke test from the project root:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_erpnext.py
```

The smoke test checks the unauthenticated health endpoint and an authenticated identity endpoint.
It never prints an API key or secret.

Stop the sandbox without deleting its database:

```powershell
docker compose -p invoice-erpnext -f pwd.yml down
```

Do not add `-v` unless the sandbox database is intentionally being destroyed and rebuilt.

## Provider Status

- Existing Mistral OCR token: retained and verified against the real OCR endpoint on 2026-08-13.
- Existing OpenAI extraction token: retained after its account credit was replenished and verified
  against `gpt-5.4-mini-2026-03-17` on 2026-08-14.
- Full OCR-to-extraction smoke test: passed with one PDF page, 1,193 extraction tokens, and no
  invoice validation errors.

The ERPNext Draft adapter is implemented. The ignored local `.env` uses
`ACCOUNTING_PROVIDER=erpnext`; `.env.example` remains on `csv_download` so a fresh clone does not
claim an external provider without credentials and provisioned master data.

## Next Boundary

Re-run the idempotent setup and Draft integration smoke with:

```powershell
.\.venv\Scripts\python.exe scripts\provision_erpnext_master_data.py
.\.venv\Scripts\python.exe scripts\smoke_erpnext_draft.py
```

Both commands are restricted to the loopback HTTP sandbox. Provisioning writes only an ignored
verification report. The Draft smoke creates one `PHASE6-SMOKE-` Purchase Invoice, verifies it
through the runtime token, and removes only that matching Draft with Administrator cleanup
credentials. It refuses to delete benchmark or submitted records.
