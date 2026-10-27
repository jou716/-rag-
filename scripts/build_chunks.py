import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import BASE_DIR
from core.chunking import build_chunk_report, build_chunks, write_chunk_artifacts


def main() -> None:
    processed = BASE_DIR / "data" / "processed"
    blocks = [
        json.loads(line)
        for line in (processed / "document_blocks.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    tables = json.loads((processed / "tables.json").read_text(encoding="utf-8"))
    report = json.loads((processed / "parse_report.json").read_text(encoding="utf-8"))
    catalog = json.loads((processed / "catalog.json").read_text(encoding="utf-8"))
    parse_result = {"blocks": blocks, "tables": tables, "report": report}

    chunks = build_chunks(parse_result, catalog)
    chunk_report = build_chunk_report(chunks, parse_result)
    write_chunk_artifacts(chunks, chunk_report, processed)
    print(json.dumps(chunk_report, ensure_ascii=False, indent=2))
    print(f"artifacts={processed}")


if __name__ == "__main__":
    main()
