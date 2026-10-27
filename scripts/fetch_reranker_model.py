from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.request
from urllib.parse import urlencode
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import BASE_DIR

MODEL_NAME = "BAAI/bge-reranker-v2-m3-int8"
MODEL_REPO = "onnx-community/bge-reranker-v2-m3-ONNX"
MODEL_REVISION = "cb859a7bfce86974a7e15899e2f993b4c9aa108c"
MODEL_ROOT = BASE_DIR / "data" / "models" / "bge-reranker-v2-m3-int8"
BASE_URL = "https://www.modelscope.cn/api/v1/models/{repo}/repo"

FILES = {
    "config.json": {
        "size": 848,
        "sha256": "122e922dcfed6503c8721e6fe1daf090340c3d95ca7f3aa3a72730b321a51cfd",
    },
    "onnx/model_int8.onnx": {
        "size": 570727094,
        "sha256": "912fc1215c2dbff6499700534bd8d31253af01573861abbfc43afd1fab6cce5d",
    },
    "special_tokens_map.json": {
        "size": 964,
        "sha256": "8c785abebea9ae3257b61681b4e6fd8365ceafde980c21970d001e834cf10835",
    },
    "tokenizer.json": {
        "size": 17082900,
        "sha256": "8bf8afbfd11306bd872018c53bfdf2e160a56f8edbcf49933324404791c148d3",
    },
    "tokenizer_config.json": {
        "size": 1203,
        "sha256": "b87c8703482b0300d3da30e201519aa641f6a450f5eb5bf1e624afbf70c74d80",
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
    url = BASE_URL.format(repo=MODEL_REPO) + "?" + urlencode(
        {"Revision": MODEL_REVISION, "FilePath": name}
    )
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
    parser = argparse.ArgumentParser(description="Fetch pinned BGE reranker model")
    parser.add_argument("--force", action="store_true", help="redownload every file")
    args = parser.parse_args()

    actions: dict[str, str] = {}
    for name, expected in FILES.items():
        actions[name] = download_file(name, expected, force=args.force)

    manifest = {
        "model_name": MODEL_NAME,
        "provider": "fastembed-onnx-cross-encoder",
        "repo": MODEL_REPO,
        "source": "modelscope",
        "revision": MODEL_REVISION,
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
