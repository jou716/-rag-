import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import check_database


def main() -> int:
    result = check_database()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
