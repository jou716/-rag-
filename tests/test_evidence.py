import pytest

from core.evidence import build_evidence_bundle, describe_block_locator


def _result(chunk_id: str, block_id: str) -> dict:
    return {
        "chunk_id": chunk_id,
        "chunk_type": "product_specs",
        "title": "C615 规格明细",
        "text": "产品编号：C615\n续航：6–8 小时",
        "section_path": ["产品目录", "6. 产品规格明细", "C615"],
        "product_ids": ["C615"],
        "quality_status": "needs_review",
        "source_block_ids": [block_id],
        "channel_ranks": {"exact": 1, "bm25": 2, "vector": 1},
        "channel_scores": {"exact": 1.0, "bm25": 8.2, "vector": 0.91},
        "rrf_score": 0.061,
        "reranker_probability": 0.98,
        "final_score": 0.95,
    }


def test_evidence_item_is_citable_and_traceable_to_word_paragraph() -> None:
    blocks = {
        "blk_p0077": {
            "block_id": "blk_p0077",
            "block_type": "body",
            "text": "产品编号：C615",
            "source": {"paragraph_index": 77, "word_style": "Normal"},
        }
    }
    manifest = {
        "file_name": "工业外骨骼产品目录.docx",
        "absolute_path": "D:/RAG知识库问答系统/工业外骨骼产品目录.docx",
        "sha256": "abc123",
    }

    evidence = build_evidence_bundle(
        [_result("chunk_product_C615_specs", "blk_p0077")],
        limit=8,
        blocks_by_id=blocks,
        source_manifest=manifest,
    )

    assert len(evidence) == 1
    assert evidence[0]["evidence_id"] == "E1"
    assert evidence[0]["citation"] == "[E1]"
    assert evidence[0]["source"]["document"]["file_name"] == (
        "工业外骨骼产品目录.docx"
    )
    assert evidence[0]["source"]["blocks"][0]["locator"] == {
        "kind": "paragraph",
        "paragraph_index": 77,
        "label": "Word 段落 77",
    }
    assert evidence[0]["retrieval"]["channels"] == ["bm25", "exact", "vector"]


def test_table_row_locator_exposes_table_and_row() -> None:
    locator = describe_block_locator(
        {
            "block_id": "tbl_t01_r02",
            "block_type": "table_row",
            "source": {"table_index": 1, "row_index": 2},
        }
    )

    assert locator == {
        "kind": "table_row",
        "table_index": 1,
        "row_index": 2,
        "label": "表格 1 第 2 行",
    }


def test_evidence_bundle_limits_to_top_eight_and_assigns_sequential_ids() -> None:
    blocks = {
        f"blk_{index}": {
            "block_id": f"blk_{index}",
            "block_type": "body",
            "text": f"证据 {index}",
            "source": {"paragraph_index": index},
        }
        for index in range(1, 11)
    }
    results = [
        _result(f"chunk_{index}", f"blk_{index}") for index in range(1, 11)
    ]

    evidence = build_evidence_bundle(
        results,
        limit=8,
        blocks_by_id=blocks,
        source_manifest={"file_name": "source.docx"},
    )

    assert [item["evidence_id"] for item in evidence] == [
        "E1",
        "E2",
        "E3",
        "E4",
        "E5",
        "E6",
        "E7",
        "E8",
    ]
    assert evidence[-1]["chunk_id"] == "chunk_8"


def test_missing_source_block_is_reported_not_silently_dropped() -> None:
    evidence = build_evidence_bundle(
        [_result("chunk_missing", "blk_missing")],
        blocks_by_id={},
        source_manifest={"file_name": "source.docx"},
    )

    assert evidence[0]["source"]["blocks"] == [
        {"block_id": "blk_missing", "missing": True}
    ]
    assert evidence[0]["source"]["missing_block_ids"] == ["blk_missing"]


def test_evidence_limit_must_be_positive() -> None:
    with pytest.raises(ValueError):
        build_evidence_bundle([], limit=0, blocks_by_id={}, source_manifest={})
