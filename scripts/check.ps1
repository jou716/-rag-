$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

& "$root\.venv\Scripts\python.exe" scripts\fetch_embedding_model.py
& "$root\.venv\Scripts\python.exe" scripts\fetch_reranker_model.py
& "$root\.venv\Scripts\python.exe" -m pytest
& "$root\.venv\Scripts\python.exe" scripts\source_manifest.py
& "$root\.venv\Scripts\python.exe" scripts\parse_docx.py
& "$root\.venv\Scripts\python.exe" scripts\build_catalog.py
& "$root\.venv\Scripts\python.exe" scripts\load_mysql.py
& "$root\.venv\Scripts\python.exe" scripts\check_mysql.py
& "$root\.venv\Scripts\python.exe" scripts\build_chunks.py
& "$root\.venv\Scripts\python.exe" scripts\validate_eval.py
& "$root\.venv\Scripts\python.exe" scripts\build_bm25.py
& "$root\.venv\Scripts\python.exe" scripts\build_vectors.py
& "$root\.venv\Scripts\python.exe" scripts\evaluate_retrieval.py
& "$root\.venv\Scripts\python.exe" scripts\verify_evidence.py

if ($env:RUN_LLM_CHECKS -eq "1") {
    & "$root\.venv\Scripts\python.exe" scripts\check_llm.py
    & "$root\.venv\Scripts\python.exe" scripts\check_ask_api.py "C615 和 C616 的电池与续航有什么区别？"
    & "$root\.venv\Scripts\python.exe" scripts\evaluate_answers.py
}
