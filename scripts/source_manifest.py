import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import BASE_DIR, settings


def build_manifest() -> dict[str, object]:
    source = settings.source_doc_path
    if not source.exists():
        raise FileNotFoundError(f"Source document not found: {source}")

    payload = source.read_bytes()
    stat = source.stat()
    return {
        "file_name": source.name,
        "absolute_path": str(source.resolve()),
        "size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "modified_at": datetime.fromtimestamp(
            stat.st_mtime, tz=timezone.utc
        ).isoformat(),
    }


def main() -> None:
    manifest = build_manifest()
    output = BASE_DIR / "data" / "source_manifest.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
