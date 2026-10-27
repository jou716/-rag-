import numpy as np
import pytest

from core.embeddings import (
    MODEL_DIR,
    MODEL_DIMENSION,
    build_embedding_text,
    embed_query,
    embed_texts,
    get_embedding_info,
)

pytestmark = pytest.mark.skipif(
    not (MODEL_DIR / "model_optimized.onnx").is_file(),
    reason="BGE model not downloaded",
)


def test_embedding_provider_metadata() -> None:
    info = get_embedding_info()

    assert info.model_name == "BAAI/bge-small-zh-v1.5"
    assert info.provider == "fastembed-onnx"
    assert info.dimension == MODEL_DIMENSION == 512
    assert len(info.revision) == 40


def test_embedding_is_normalized_and_deterministic() -> None:
    first = embed_texts(["C615 续航时间 6–8 小时"])[0]
    second = embed_texts(["C615 续航时间 6–8 小时"])[0]

    assert len(first) == MODEL_DIMENSION
    assert np.allclose(first, second)
    assert round(float(np.linalg.norm(first)), 6) == 1.0


def test_embedding_text_keeps_structured_context() -> None:
    text = build_embedding_text(
        {
            "chunk_id": "chunk_product_C615_specs",
            "chunk_type": "product_specs",
            "title": "C615 规格明细",
            "text": "续航 6–8 小时",
            "product_ids": ["C615"],
            "category_keys": ["upper_limb"],
            "tier_keys": ["high"],
            "power_types": ["electric"],
            "section_path": ["产品规格明细", "上肢外骨骼", "C615"],
        }
    )

    assert "标题：C615 规格明细" in text
    assert "产品编号：C615" in text
    assert "章节：产品规格明细 > 上肢外骨骼 > C615" in text
    assert text.endswith("续航 6–8 小时")


def test_bge_ranks_relevant_product_text_above_unrelated_section() -> None:
    chunks = [
        {
            "chunk_type": "product_specs",
            "title": "C615 规格明细",
            "text": "产品编号：C615 电池 92Wh 续航 6–8 小时 净重 3.9 kg",
            "product_ids": ["C615"],
            "category_keys": ["upper_limb"],
            "tier_keys": ["high"],
            "power_types": ["electric"],
            "section_path": ["产品规格明细", "上肢外骨骼", "C615"],
        },
        {
            "chunk_type": "section",
            "title": "7. 服务与支持",
            "text": "公司提供售后服务、备件供应和客户支持。",
            "product_ids": [],
            "category_keys": [],
            "tier_keys": [],
            "power_types": [],
            "section_path": ["7. 服务与支持"],
        },
    ]
    vectors = embed_texts([build_embedding_text(chunk) for chunk in chunks])
    query = np.asarray(embed_query("C615 电池续航时间多久"))

    similarities = [float(query @ np.asarray(vector)) for vector in vectors]
    assert similarities[0] > similarities[1]
