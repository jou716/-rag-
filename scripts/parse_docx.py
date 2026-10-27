import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import BASE_DIR, settings
from core.docx_parser import parse_docx, write_parse_artifacts


def main() -> None:
    result = parse_docx(settings.source_doc_path)
    output_dir = BASE_DIR / "data" / "processed"
    write_parse_artifacts(result, output_dir)
    print(json.dumps(result["report"]["counts"], ensure_ascii=False, indent=2))
    print(f"artifacts={output_dir}")
    if result["report"]["warnings"]:
        print("warnings=")
        for warning in result["report"]["warnings"]:
            print(f"- {warning}")


if __name__ == "__main__":
    main()
