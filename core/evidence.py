from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from functools import lru_cache
from typing import Any

from app.config import BASE_DIR

DEFAULT_EVIDENCE_LIMIT = 15


@lru_cache(maxsize=1)
def load_source_manifest() -> dict[str, Any]:
    path = BASE_DIR / "data" / "source_manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_blocks_by_id() -> dict[str, dict[str, Any]]:
    path = BASE_DIR / "data" / "processed" / "document_blocks.jsonl"
    blocks = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return {block["block_id"]: block for block in blocks}


def describe_block_locator(block: Mapping[str, Any]) -> dict[str, Any]:
    source = block.get("source") or {}
    if "table_index" in source and "row_index" in source:
        table_index = source["table_index"]
        row_index = source["row_index"]
        return {
            "kind": "table_row",
            "table_index": table_index,
            "row_index": row_index,
            "label": f"表格 {table_index} 第 {row_index} 行",
        }
    if "paragraph_index" in source:
        paragraph_index = source["paragraph_index"]
        return {
            "kind": "paragraph",
            "paragraph_index": paragraph_index,
            "label": f"Word 段落 {paragraph_index}",
        }
    return {"kind": "document", "label": "Word 文档正文"}


def _source_document(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "file_name": manifest.get("file_name"),
        "source_path": manifest.get("absolute_path"),
        "sha256": manifest.get("sha256"),
    }


def _source_block(
    block_id: str, blocks_by_id: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    block = blocks_by_id.get(block_id)
    if block is None:
        return {"block_id": block_id, "missing": True}
    return {
        "block_id": block_id,
        "block_type": block.get("block_type"),
        "locator": describe_block_locator(block),
        "text": block.get("text", ""),
    }


def build_evidence_item(
    result: Mapping[str, Any],
    rank: int,
    *,
    blocks_by_id: Mapping[str, Mapping[str, Any]] | None = None,
    source_manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    blocks_by_id = blocks_by_id or load_blocks_by_id()
    source_manifest = source_manifest or load_source_manifest()
    block_ids = list(result.get("source_block_ids") or [])
    source_blocks = [_source_block(block_id, blocks_by_id) for block_id in block_ids]
    return {
        "evidence_id": f"E{rank}",
        "citation": f"[E{rank}]",
        "rank": rank,
        "chunk_id": result["chunk_id"],
        "chunk_type": result.get("chunk_type"),
        "title": result.get("title"),
        "card_chunk_ids": result.get("card_chunk_ids", []),
        "text": result.get("text", ""),
        "section_path": result.get("section_path", []),
        "product_ids": result.get("product_ids", []),
        "quality_status": result.get("quality_status"),
        "quality_flags": result.get("quality_flags", []),
        "source": {
            "document": _source_document(source_manifest),
            "block_ids": block_ids,
            "blocks": source_blocks,
            "missing_block_ids": [
                block["block_id"] for block in source_blocks if block.get("missing")
            ],
        },
        "retrieval": {
            "channels": sorted((result.get("channel_ranks") or {}).keys()),
            "channel_ranks": result.get("channel_ranks", {}),
            "channel_scores": result.get("channel_scores", {}),
            "rrf_score": result.get("rrf_score"),
            "reranker_probability": result.get("reranker_probability"),
            "final_score": result.get("final_score"),
        },
    }


def build_evidence_bundle(
    results: Sequence[Mapping[str, Any]],
    *,
    limit: int = DEFAULT_EVIDENCE_LIMIT,
    blocks_by_id: Mapping[str, Mapping[str, Any]] | None = None,
    source_manifest: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if limit < 1:
        raise ValueError("Evidence limit must be at least 1")
    blocks_by_id = blocks_by_id or load_blocks_by_id()
    source_manifest = source_manifest or load_source_manifest()
    return [
        build_evidence_item(
            result,
            rank,
            blocks_by_id=blocks_by_id,
            source_manifest=source_manifest,
        )
        for rank, result in enumerate(results[:limit], start=1)
    ]
