$ErrorActionPreference = 'Stop'
if (-not (Test-Path '.venv')) { py -m venv .venv }
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
uvicorn backend.app.main:app --reload --port 8000
