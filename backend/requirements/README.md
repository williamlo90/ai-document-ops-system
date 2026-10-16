# Python dependencies

Run install/compile commands from the repository root. Runtime and development inputs are
`requirements.in` and `requirements-dev.in`; the development input includes the runtime input.
Hash-locked `.txt` files are separate for Linux containers/CI and Windows development.

```powershell
.\.venv\Scripts\python.exe -m pip install --require-hashes -r backend/requirements/requirements-dev-windows.txt
```

Linux CI uses `backend/requirements/requirements-dev.txt`; Docker installs
`backend/requirements/requirements.txt`. Keep both platform locks synchronized when intentionally
updating inputs. CI checks regeneration using the pinned pip-tools version.
