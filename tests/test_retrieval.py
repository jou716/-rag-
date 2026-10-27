from core.bm25 import build_bm25_index, search_bm25
from core.exact_search import comparable_range
from core.text_analysis import tokenize


def sample_chunks() -> list[dict]:
    return [
        {
            "chunk_id": "chunk_product_C615_specs",
            "chunk_type": "product_specs",
            "title": "C615 规格明细",
            "text": "产品编号：C615 净重 3.9 kg 电池 92Wh 续航 6–8 小时 最大手臂助力 20 kg",
            "section_path": ["产品规格明细", "上肢外骨骼", "C615"],
            "source_block_ids": ["b1"],
            "heading_block_ids": [],
            "product_ids": ["C615"],
            "category_keys": ["upper_limb"],
            "tier_keys": ["high"],
            "power_types": ["electric"],
            "quality_flags": [],
            "metadata": {"quality_status": "needs_review"},
        },
        {
            "chunk_id": "chunk_product_C685_specs",
            "chunk_type": "product_specs",
            "title": "C685 规格明细",
            "text": "产品编号：C685 净重 ≤2.3 kg 最大助力 60 kg 续航 30–45%",
            "section_path": ["产品规格明细", "腰背外骨骼", "C685"],
            "source_block_ids": ["b2"],
            "heading_block_ids": [],
            "product_ids": ["C685"],
            "category_keys": ["waist_back"],
            "tier_keys": ["mid"],
            "power_types": ["passive"],
            "quality_flags": [],
            "metadata": {"quality_status": "ok"},
        },
    ]


def test_tokenizer_keeps_domain_terms_and_units() -> None:
    tokens = tokenize("C615 的续航时间是多少？最大助力 60 kg")

    assert "c615" in tokens
    assert "续航" in tokens
    assert "助力" in tokens
    assert "60kg" in tokens
    assert "多少" not in tokens


def test_comparable_force_and_mass_units() -> None:
    force = comparable_range(
        {
            "metric_key": "max_assist",
            "value_num": 300,
            "value_min": None,
            "value_max": None,
            "unit_normalized": "N",
        }
    )
    assert round(force["high"], 4) == round(300 / 9.80665, 4)
    assert force["unit"] == "kgf"

    mass = comparable_range(
        {
            "metric_key": "weight",
            "value_num": 850,
            "value_min": None,
            "value_max": None,
            "unit_normalized": "g",
        }
    )
    assert mass["high"] == 0.85
    assert mass["unit"] == "kg"


def test_bm25_ranks_matching_chunk_first() -> None:
    index = build_bm25_index(sample_chunks())
    results = search_bm25(index, "C615 续航时间", top_k=2)

    assert results[0]["chunk_id"] == "chunk_product_C615_specs"
    assert results[0]["score"] > results[1]["score"]


def test_bm25_filters_by_product() -> None:
    index = build_bm25_index(sample_chunks())
    results = search_bm25(
        index,
        "最大助力 60 kg",
        top_k=5,
        filters={"product_ids": ["C685"]},
    )

    assert len(results) == 1
    assert results[0]["chunk_id"] == "chunk_product_C685_specs"
