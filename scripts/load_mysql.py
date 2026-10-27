import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import BASE_DIR
from app.db import get_engine
from core.db_ingest import create_schema, load_catalog


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

    engine = get_engine()
    create_schema(engine)
    counts = load_catalog(engine, parse_result, catalog)
    print(json.dumps(counts, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
