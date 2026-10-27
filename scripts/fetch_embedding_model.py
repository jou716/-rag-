from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import BASE_DIR

MODEL_NAME = "BAAI/bge-small-zh-v1.5"
MODEL_REPO = "Qdrant/bge-small-zh-v1.5"
MODEL_REVISION = "677b527935023b31f309ecb027745526aa5f680f"
MODEL_ROOT = BASE_DIR / "data" / "models" / "bge-small-zh-v1.5"
BASE_URL = "https://www.modelscope.cn/models/{repo}/resolve/{revision}/{path}"

FILES = {
    "config.json": {
        "size": 739,
        "sha256": "9088751d39abbf86ec3d19ffca92ad62ad19075f7e59712e6c71217fa125d1d3",
    },
    "model_optimized.onnx": {
        "size": 94781076,
        "sha256": "1294ea4b6331115a353d81f96b85e8c8d7fdcc284453d5b2fab5b016230aad38",
    },
    "special_tokens_map.json": {
        "size": 125,
        "sha256": "b6d346be366a7d1d48332dbc9fdf3bf8960b5d879522b7799ddba59e76237ee3",
    },
    "tokenizer.json": {
        "size": 439125,
        "sha256": "48cea5d44424912a6fd1ea647bf4fe50b55ab8b1e5879c3275f80e339e8fae26",
    },
    "tokenizer_config.json": {
        "size": 367,
        "sha256": "e6f3b96db926a37d4039995fbf5ad17de158dfb8f6343d607e4dbaad18d75f5a",
    },
    "vocab.txt": {
        "size": 109540,
        "sha256": "45bbac6b341c319adc98a532532882e91a9cefc0329aa57bac9ae761c27b291c",
    },
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_is_valid(path: Path, expected: dict[str, object]) -> bool:
    return (
        path.is_file()
        and path.stat().st_size == expected["size"]
        and sha256_file(path) == expected["sha256"]
    )


def download_file(name: str, expected: dict[str, object], force: bool) -> str:
    target = MODEL_ROOT / name
    if not force and file_is_valid(target, expected):
        print(f"cached  {name} ({expected['size']} bytes)")
        return "cached"

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".part")
    temporary.unlink(missing_ok=True)
    url = BASE_URL.format(repo=MODEL_REPO, revision=MODEL_REVISION, path=name)
    request = urllib.request.Request(url, headers={"User-Agent": "ExoRAG/1.0"})
    digest = hashlib.sha256()
    downloaded = 0
    last_bucket = -1
    started = time.monotonic()

    print(f"fetch   {name} ({expected['size']} bytes)")
    try:
        with urllib.request.urlopen(request, timeout=120) as response, temporary.open(
            "wb"
        ) as output:
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                output.write(block)
                digest.update(block)
                downloaded += len(block)
                bucket = int(downloaded * 10 / int(expected["size"]))
                if bucket != last_bucket:
                    last_bucket = bucket
                    print(f"        {min(bucket * 10, 100):3d}%  {downloaded} bytes")

        actual_sha = digest.hexdigest()
        if downloaded != expected["size"]:
            raise ValueError(
                f"size mismatch for {name}: {downloaded} != {expected['size']}"
            )
        if actual_sha != expected["sha256"]:
            raise ValueError(
                f"sha256 mismatch for {name}: {actual_sha} != {expected['sha256']}"
            )
        temporary.replace(target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    elapsed = time.monotonic() - started
    print(f"saved   {name} in {elapsed:.1f}s")
    return "downloaded"


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch pinned BGE embedding model")
    parser.add_argument("--force", action="store_true", help="redownload every file")
    args = parser.parse_args()

    actions: dict[str, str] = {}
    for name, expected in FILES.items():
        actions[name] = download_file(name, expected, force=args.force)

    manifest = {
        "model_name": MODEL_NAME,
        "provider": "fastembed-onnx",
        "repo": MODEL_REPO,
        "source": "modelscope",
        "revision": MODEL_REVISION,
        "dimension": 512,
        "files": FILES,
        "total_size_bytes": sum(int(item["size"]) for item in FILES.values()),
    }
    manifest_path = MODEL_ROOT / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(
        json.dumps(
            {
                "model_dir": str(MODEL_ROOT),
                "manifest": str(manifest_path),
                "files": len(FILES),
                "total_size_bytes": manifest["total_size_bytes"],
                "actions": actions,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
