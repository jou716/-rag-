from __future__ import annotations

import hashlib
import json
from pathlib import Path

from core.index_contract import (
    chunk_ids_digest,
    sha256_file,
    validate_index_contract,
)
from core.vector_store import build_vector_index


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _chunk(chunk_id: str) -> dict:
    return {
        "chunk_id": chunk_id,
        "chunk_type": "product_specs",
        "title": f"{chunk_id} 规格明细",
        "text": f"{chunk_id} 正文",
        "section_path": ["产品规格明细"],
        "product_ids": [],
        "category_keys": [],
        "tier_keys": [],
        "power_types": [],
        "quality_flags": [],
        "spec_ids": [],
        "metric_keys": [],
        "source_block_ids": [],
        "metadata": {},
    }


def build_fixture(
    base: Path,
    *,
    chunk_ids: tuple[str, ...] = ("chunk_a", "chunk_b"),
    source_bytes: bytes = b"doc-v1",
) -> tuple[Path, list[dict], str]:
    processed = base / "data" / "processed"
    indexes = base / "data" / "indexes"
    processed.mkdir(parents=True)
    indexes.mkdir(parents=True)

    source = base / "工业外骨骼产品目录.docx"
    source.write_bytes(source_bytes)
    source_sha = hashlib.sha256(source_bytes).hexdigest()
    chunks = [_chunk(chunk_id) for chunk_id in chunk_ids]

    (processed / "chunks.jsonl").write_text(
        "\n".join(json.dumps(chunk, ensure_ascii=False) for chunk in chunks) + "\n",
        encoding="utf-8",
    )
    (processed / "document_blocks.jsonl").write_text("{}\n", encoding="utf-8")
    _write_json(
        base / "data" / "source_manifest.json",
        {"file_name": source.name, "sha256": source_sha},
    )
    _write_json(
        processed / "chunk_report.json",
        {"source": {"sha256": source_sha}, "counts": {"chunks": len(chunks)}},
    )
    _write_json(
        indexes / "bm25_index.json",
        {"source_hash": source_sha, "chunk_count": len(chunks)},
    )
    _write_json(indexes / "bm25_report.json", {"source": {"sha256": source_sha}})

    model_manifest = base / "data" / "models" / "test-model" / "manifest.json"
    _write_json(model_manifest, {"model_name": "BAAI/test-model"})
    _write_json(
        indexes / "vector_manifest.json",
        {
            "source_sha256": source_sha,
            "chunk_ids_sha256": chunk_ids_digest(
                chunk["chunk_id"] for chunk in chunks
            ),
            "points_count": len(chunks),
            "collection_name": "exo_chunks",
            "embedding": {
                "model_name": "BAAI/test-model",
                "model_manifest": str(model_manifest),
                "model_manifest_sha256": sha256_file(model_manifest),
            },
        },
    )
    return source, chunks, source_sha


def test_consistent_indexes_pass(tmp_path) -> None:
    source, _, _ = build_fixture(tmp_path)

    report = validate_index_contract(
        tmp_path, source_doc=source, check_qdrant=False
    )

    assert report.ok, report.format_error()
    names = {check.name for check in report.checks}
    assert {"源文档 SHA256", "源文档版本链路", "chunk ID 指纹"} <= names


def test_changed_source_document_fails_fast(tmp_path) -> None:
    source, _, _ = build_fixture(tmp_path)
    source.write_bytes(b"doc-v2")

    report = validate_index_contract(
        tmp_path, source_doc=source, check_qdrant=False
    )

    assert not report.ok
    failed = {check.name: check for check in report.failed}
    assert "源文档 SHA256" in failed
    assert "源文档已变更" in failed["源文档 SHA256"].detail
    assert any("build_vectors.py" in step for step in report.next_steps)


def test_chunk_drift_points_to_vector_rebuild(tmp_path) -> None:
    source, _, _ = build_fixture(tmp_path)
    chunks_path = tmp_path / "data" / "processed" / "chunks.jsonl"
    with chunks_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_chunk("chunk_c"), ensure_ascii=False) + "\n")

    report = validate_index_contract(
        tmp_path, source_doc=source, check_qdrant=False
    )

    assert not report.ok
    failed = {check.name for check in report.failed}
    assert {"chunk 数量一致", "chunk ID 指纹"} <= failed
    assert any("build_vectors.py" in step for step in report.next_steps)


def test_missing_bm25_index_points_to_bm25_rebuild(tmp_path) -> None:
    source, _, _ = build_fixture(tmp_path)
    (tmp_path / "data" / "indexes" / "bm25_index.json").unlink()

    report = validate_index_contract(
        tmp_path, source_doc=source, check_qdrant=False
    )

    assert not report.ok
    assert any("build_bm25.py" in step for step in report.next_steps)


def test_changed_embedding_manifest_invalidates_vectors(tmp_path) -> None:
    source, _, _ = build_fixture(tmp_path)
    model_manifest = (
        tmp_path / "data" / "models" / "test-model" / "manifest.json"
    )
    _write_json(model_manifest, {"model_name": "BAAI/test-model", "revision": "new"})

    report = validate_index_contract(
        tmp_path, source_doc=source, check_qdrant=False
    )

    assert not report.ok
    failed = {check.name: check for check in report.failed}
    assert "向量模型清单" in failed
    assert any("build_vectors.py" in step for step in report.next_steps)


def test_duplicate_chunk_ids_are_rejected(tmp_path) -> None:
    source, chunks, _ = build_fixture(tmp_path)
    chunks_path = tmp_path / "data" / "processed" / "chunks.jsonl"
    chunks_path.write_text(
        "\n".join(
            json.dumps(chunk, ensure_ascii=False) for chunk in [chunks[0], chunks[0]]
        )
        + "\n",
        encoding="utf-8",
    )

    report = validate_index_contract(
        tmp_path, source_doc=source, check_qdrant=False
    )

    assert not report.ok
    assert "chunk 清单可读" in {check.name for check in report.failed}


def test_qdrant_collection_must_match_chunk_inventory(tmp_path) -> None:
    source, chunks, _ = build_fixture(tmp_path)
    index_path = tmp_path / "data" / "indexes" / "qdrant"
    build_vector_index(
        chunks,
        [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]],
        index_path=index_path,
    )

    passing = validate_index_contract(tmp_path, source_doc=source)
    assert passing.ok, passing.format_error()

    build_vector_index(
        [*chunks, _chunk("chunk_c")],
        [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0]],
        index_path=index_path,
    )

    failing = validate_index_contract(tmp_path, source_doc=source)
    assert not failing.ok
    failed = {check.name: check for check in failing.failed}
    assert "Qdrant 集合一致" in failed
    assert "不一致" in failed["Qdrant 集合一致"].detail
