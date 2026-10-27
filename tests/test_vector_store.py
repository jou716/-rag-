import pytest

from core.vector_store import (
    VectorFilters,
    build_payload,
    build_vector_index,
    collection_manifest,
    point_id_for_chunk,
    search_vectors,
)


def sample_chunks() -> list[dict]:
    return [
        {
            "chunk_id": "chunk_product_C615_specs",
            "chunk_type": "product_specs",
            "title": "C615 规格明细",
            "text": "C615 净重 3.9 kg 续航 6–8 小时",
            "section_path": ["产品规格明细", "上肢外骨骼", "C615"],
            "source_block_ids": ["b1"],
            "heading_block_ids": [],
            "product_ids": ["C615"],
            "category_keys": ["upper_limb"],
            "tier_keys": ["high"],
            "power_types": ["electric"],
            "quality_flags": ["tier_matrix_category_conflict"],
            "spec_ids": ["spec_C615_02"],
            "metric_keys": ["runtime"],
            "metadata": {"quality_status": "needs_review"},
        },
        {
            "chunk_id": "chunk_product_C685_specs",
            "chunk_type": "product_specs",
            "title": "C685 规格明细",
            "text": "C685 最大助力 60 kg",
            "section_path": ["产品规格明细", "腰背外骨骼", "C685"],
            "source_block_ids": ["b2"],
            "heading_block_ids": [],
            "product_ids": ["C685"],
            "category_keys": ["waist_back"],
            "tier_keys": ["mid"],
            "power_types": ["passive"],
            "quality_flags": [],
            "spec_ids": ["spec_C685_03"],
            "metric_keys": ["max_assist"],
            "metadata": {"quality_status": "ok"},
        },
        {
            "chunk_id": "chunk_section_service",
            "chunk_type": "section",
            "title": "7. 服务与支持",
            "text": "公司提供售后服务和备件供应",
            "section_path": ["7. 服务与支持"],
            "source_block_ids": ["b3"],
            "heading_block_ids": ["h3"],
            "product_ids": [],
            "category_keys": [],
            "tier_keys": [],
            "power_types": [],
            "quality_flags": [],
            "spec_ids": [],
            "metric_keys": [],
            "metadata": {},
        },
    ]


def sample_vectors() -> list[list[float]]:
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.8, 0.2, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
    ]


def test_point_id_is_stable_and_chunk_specific() -> None:
    first = point_id_for_chunk("chunk_product_C615_specs")
    second = point_id_for_chunk("chunk_product_C615_specs")
    other = point_id_for_chunk("chunk_product_C685_specs")

    assert first == second
    assert first != other
    assert len(first) == 36


def test_payload_preserves_traceability_fields() -> None:
    payload = build_payload(sample_chunks()[0])

    assert payload["chunk_id"] == "chunk_product_C615_specs"
    assert payload["product_ids"] == ["C615"]
    assert payload["quality_status"] == "needs_review"
    assert payload["source_block_ids"] == ["b1"]
    assert payload["spec_ids"] == ["spec_C615_02"]


def test_vector_index_rebuild_is_idempotent(tmp_path) -> None:
    index_path = tmp_path / "qdrant"
    chunks = sample_chunks()
    vectors = sample_vectors()

    first = build_vector_index(chunks, vectors, index_path=index_path)
    second = build_vector_index(chunks, vectors, index_path=index_path)

    assert first["points_count"] == 3
    assert second["points_count"] == 3
    manifest = collection_manifest(index_path)
    assert manifest["points_count"] == 3
    assert manifest["vector_size"] == 4
    assert manifest["distance"] == "Cosine"
    assert manifest["chunk_ids"] == sorted(chunk["chunk_id"] for chunk in chunks)


def test_vector_search_is_sorted_and_filterable(tmp_path) -> None:
    index_path = tmp_path / "qdrant"
    build_vector_index(sample_chunks(), sample_vectors(), index_path=index_path)

    unfiltered = search_vectors([1.0, 0.0, 0.0, 0.0], top_k=3, index_path=index_path)
    assert [result.score for result in unfiltered] == sorted(
        [result.score for result in unfiltered], reverse=True
    )
    assert unfiltered[0].chunk_id == "chunk_product_C615_specs"

    filtered = search_vectors(
        [1.0, 0.0, 0.0, 0.0],
        top_k=3,
        filters=VectorFilters(
            product_ids=("C685",),
            category_keys=("waist_back",),
            tier_keys=("mid",),
            power_types=("passive",),
            chunk_types=("product_specs",),
            quality_status=("ok",),
        ),
        index_path=index_path,
    )
    assert len(filtered) == 1
    assert filtered[0].chunk_id == "chunk_product_C685_specs"


def test_search_missing_collection_has_actionable_error(tmp_path) -> None:
    with pytest.raises(RuntimeError, match="build_vectors.py"):
        search_vectors([1.0, 0.0], index_path=tmp_path / "empty-qdrant")
