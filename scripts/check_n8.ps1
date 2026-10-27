$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:PYTHONUTF8 = "1"

& "$root\.venv\Scripts\python.exe" -m pytest -q
& "$root\.venv\Scripts\python.exe" scripts\check_llm.py
& "$root\.venv\Scripts\python.exe" scripts\check_ask_api.py "C615 和 C616 的电池与续航有什么区别？"
& "$root\.venv\Scripts\python.exe" scripts\check_ask_api.py "C615 的价格是多少？"
& "$root\.venv\Scripts\python.exe" scripts\evaluate_answers.py
