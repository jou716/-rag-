from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import BASE_DIR
from core.embeddings import (
    MODEL_MANIFEST_PATH,
    embed_chunks,
    embed_query,
    get_embedding_info,
)
from core.vector_store import (
    COLLECTION_NAME,
    DEFAULT_QDRANT_PATH,
    VectorFilters,
    build_vector_index,
    collection_manifest,
    search_vectors,
    write_json,
)

SMOKE_CASES = (
    {
        "name": "matrix_scenario",
        "query": "物流搬运与装卸推荐哪些产品",
        "filters": VectorFilters(),
    },
    {
        "name": "company_service",
        "query": "公司售后怎么联系",
        "filters": VectorFilters(),
    },
    {
        "name": "overhead_work",
        "query": "过顶举臂装配作业适合什么产品",
        "filters": VectorFilters(),
    },
    {
        "name": "product_filter",
        "query": "电池续航时间多久",
        "filters": VectorFilters(product_ids=("C615",), chunk_types=("product_specs",)),
    },
    {
        "name": "category_filter",
        "query": "最大助力是多少",
        "filters": VectorFilters(category_keys=("waist_back",)),
    },
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_chunks() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    processed = BASE_DIR / "data" / "processed"
    chunks = [
        json.loads(line)
        for line in (processed / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    report = json.loads((processed / "chunk_report.json").read_text(encoding="utf-8"))
    return chunks, report


def directory_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Qdrant vector index")
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()

    chunks, chunk_report = load_chunks()
    if len(chunks) != 48:
        raise RuntimeError(f"Expected 48 chunks, got {len(chunks)}")
    unique_ids = {chunk["chunk_id"] for chunk in chunks}
    if len(unique_ids) != len(chunks):
        raise RuntimeError("chunk_id must be unique before vector indexing")

    embedding_info = get_embedding_info()
    started = time.monotonic()
    vectors = embed_chunks(chunks, batch_size=args.batch_size)
    embedding_seconds = time.monotonic() - started
    if len(vectors) != len(chunks):
        raise RuntimeError("Embedding count does not match chunk count")
    if any(len(vector) != embedding_info.dimension for vector in vectors):
        raise RuntimeError("Embedding dimension does not match provider metadata")

    started = time.monotonic()
    index_summary = build_vector_index(chunks, vectors, index_path=DEFAULT_QDRANT_PATH)
    index_seconds = time.monotonic() - started
    manifest = collection_manifest(DEFAULT_QDRANT_PATH)
    if manifest["points_count"] != len(chunks):
        raise RuntimeError(
            f"Qdrant point count mismatch: {manifest['points_count']} != {len(chunks)}"
        )
    if manifest["chunk_ids"] != sorted(unique_ids):
        raise RuntimeError("Qdrant payload chunk_ids do not match source chunks")

    smoke_results = {}
    for case in SMOKE_CASES:
        results = search_vectors(
            embed_query(case["query"]),
            top_k=3,
            filters=case["filters"],
            index_path=DEFAULT_QDRANT_PATH,
        )
        smoke_results[case["name"]] = {
            "query": case["query"],
            "filters": {
                "product_ids": case["filters"].product_ids,
                "category_keys": case["filters"].category_keys,
                "tier_keys": case["filters"].tier_keys,
                "power_types": case["filters"].power_types,
                "chunk_types": case["filters"].chunk_types,
                "quality_status": case["filters"].quality_status,
            },
            "results": [result.as_dict() for result in results],
        }

    source_hash = chunk_report["source"]["sha256"]
    chunk_ids_digest = hashlib.sha256(
        "\n".join(sorted(unique_ids)).encode("utf-8")
    ).hexdigest()
    model_manifest_sha = sha256_file(MODEL_MANIFEST_PATH)
    common_manifest = {
        "version": 1,
        "schema": "exorag-qdrant-v1",
        "source_sha256": source_hash,
        "collection_name": COLLECTION_NAME,
        "index_path": str(DEFAULT_QDRANT_PATH),
        "points_count": manifest["points_count"],
        "chunk_ids_sha256": chunk_ids_digest,
        "vector_size": manifest["vector_size"],
        "distance": manifest["distance"],
        "embedding": {
            **embedding_info.as_dict(),
            "model_manifest": str(MODEL_MANIFEST_PATH),
            "model_manifest_sha256": model_manifest_sha,
        },
    }
    write_json(BASE_DIR / "data" / "indexes" / "vector_manifest.json", common_manifest)

    report = {
        **common_manifest,
        "counts": {
            "chunks": len(chunks),
            "by_type": dict(Counter(chunk["chunk_type"] for chunk in chunks).most_common()),
            "unique_chunk_ids": len(unique_ids),
        },
        "embedding_text": {
            "template": embedding_info.document_template,
            "avg_chars": round(
                sum(len(chunk["text"]) for chunk in chunks) / len(chunks), 2
            ),
        },
        "timing_seconds": {
            "embedding": round(embedding_seconds, 3),
            "indexing": round(index_seconds, 3),
        },
        "index_size_bytes": directory_size(DEFAULT_QDRANT_PATH),
        "collection_stats": index_summary | {"payload_indexes_local_mode": "no effect"},
        "smoke_queries": smoke_results,
    }
    report_path = BASE_DIR / "data" / "indexes" / "qdrant_report.json"
    write_json(report_path, report)

    print(
        json.dumps(
            {
                "points_count": manifest["points_count"],
                "vector_size": manifest["vector_size"],
                "distance": manifest["distance"],
                "embedding_model": embedding_info.model_name,
                "embedding_seconds": report["timing_seconds"]["embedding"],
                "index_size_bytes": report["index_size_bytes"],
                "report": str(report_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
