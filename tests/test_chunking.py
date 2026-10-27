import pytest

from app.config import settings
from core.catalog import build_catalog
from core.chunking import build_chunk_report, build_chunks
from core.docx_parser import parse_docx

pytestmark = pytest.mark.skipif(
    not settings.source_doc_path.is_file(),
    reason="source DOCX is not included in the public repository",
)


def build_test_chunks() -> tuple[list[dict], dict]:
    parse_result = parse_docx(settings.source_doc_path)
    catalog = build_catalog(parse_result)
    chunks = build_chunks(parse_result, catalog)
    return chunks, build_chunk_report(chunks, parse_result)


def test_chunk_counts_and_types() -> None:
    chunks, report = build_test_chunks()

    assert len(chunks) == 48
    assert report["counts"]["by_type"] == {
        "product_profile": 16,
        "product_specs": 16,
        "section": 4,
        "matrix_scenario": 5,
        "matrix_tier": 3,
        "matrix_category": 3,
        "matrix_legend": 1,
    }


def test_every_block_is_covered() -> None:
    _, report = build_test_chunks()

    assert report["coverage"]["total_blocks"] == 271
    assert report["coverage"]["uncovered"] == []
    assert report["warnings"] == []


def test_chunk_ids_are_unique() -> None:
    chunks, report = build_test_chunks()

    assert report["counts"]["unique_chunk_ids"] == len(chunks)
    assert all(chunk["source_block_ids"] for chunk in chunks)


def test_c615_chunks_contain_key_specs() -> None:
    chunks, _ = build_test_chunks()
    by_id = {chunk["chunk_id"]: chunk for chunk in chunks}

    profile = by_id["chunk_product_C615_profile"]
    specs = by_id["chunk_product_C615_specs"]
    assert "AI 动力上肢外骨骼" in profile["text"]
    assert "3.9 kg" in specs["text"]
    assert "6–8 小时" in specs["text"]
    assert "blk_ac98d42e_p0089" in specs["source_block_ids"]


def test_matrix_chunk_preserves_raw_product_ids() -> None:
    chunks, _ = build_test_chunks()
    by_id = {chunk["chunk_id"]: chunk for chunk in chunks}

    chunk = by_id["chunk_matrix_tier_tbl_ac98d42e_t02_r04"]
    assert "上肢: C616(电)" in chunk["text"]
    assert "腰背: C615(电)" in chunk["text"]
    assert chunk["product_ids"] == ["C616", "C615", "C689"]
