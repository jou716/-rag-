$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
& "$root\.venv\Scripts\python.exe" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
