
from core.exact_candidates import build_exact_candidates
from core.hybrid_search import (
    HybridRetriever,
    blend_rerank_scores,
    build_product_card,
    normalize_scores,
    reciprocal_rank_fusion,
)
from core.query_analysis import analyze_query


def test_rrf_uses_weighted_reciprocal_ranks() -> None:
    fused = reciprocal_rank_fusion(
        {
            "exact": [{"chunk_id": "a", "score": 1.0}],
            "bm25": [{"chunk_id": "b", "score": 10.0}, {"chunk_id": "a", "score": 8.0}],
        },
        weights={"exact": 2.0, "bm25": 1.0},
        rrf_k=60,
    )

    assert fused["a"].rrf_score > fused["b"].rrf_score
    assert fused["a"].channel_ranks == {"exact": 1, "bm25": 2}
    assert fused["b"].channel_ranks == {"bm25": 1}


def test_normalize_scores_handles_constant_values() -> None:
    assert normalize_scores([3.0, 3.0]) == [0.0, 0.0]
    assert normalize_scores([1.0, 3.0]) == [0.0, 1.0]


def test_blend_rerank_scores_keeps_both_signals() -> None:
    final, normalized_rrf = blend_rerank_scores(
        [0.06, 0.02],
        [0.4, 0.9],
        rerank_weight=0.75,
    )

    assert normalized_rrf == [1.0, 0.0]
    assert final[1] > final[0]


def test_filter_evidence_spreads_one_chunk_per_product(monkeypatch) -> None:
    retriever = HybridRetriever(engine=object(), chunks=[], bm25_index={"dummy": 1})
    monkeypatch.setattr(
        HybridRetriever,
        "_matched_products",
        lambda self, analysis: [{"product_id": "C616"}, {"product_id": "C686"}],
    )
    results = [
        {
            "chunk_id": "matrix",
            "chunk_type": "matrix_category",
            "product_ids": [],
            "final_score": 0.5,
        },
        {
            "chunk_id": "C616_profile",
            "chunk_type": "product_profile",
            "product_ids": ["C616"],
            "final_score": 0.9,
        },
        {
            "chunk_id": "C616_specs",
            "chunk_type": "product_specs",
            "product_ids": ["C616"],
            "final_score": 0.7,
        },
        {
            "chunk_id": "C686_profile",
            "chunk_type": "product_profile",
            "product_ids": ["C686"],
            "final_score": 0.8,
        },
    ]
    analysis = analyze_query("背部外骨骼有哪些，他们的重量是多少")

    ordered = retriever._spread_by_product(results, analysis)

    assert [result["chunk_id"] for result in ordered[:3]] == [
        "matrix",
        "card_product_C616",
        "card_product_C686",
    ]
    assert "净重：5.6 kg" in ordered[1]["text"]
    assert ordered[1]["card_chunk_ids"] == [
        "chunk_product_C616_profile",
        "chunk_product_C616_specs",
    ]


def test_product_card_combines_profile_and_specs() -> None:
    parts = {
        "product_profile": {
            "chunk_id": "profile",
            "chunk_type": "product_profile",
            "text": "产品编号：C615\n产品类别：上肢外骨骼\n类型：AI 动力上肢外骨骼",
            "section_path": ["6. 产品规格明细", "6.1 上肢外骨骼", "C615"],
            "product_ids": ["C615"],
            "source_block_ids": ["p1", "p2"],
            "quality_flags": [],
            "metadata": {"quality_status": "normal"},
        },
        "product_specs": {
            "chunk_id": "specs",
            "chunk_type": "product_specs",
            "text": "产品编号：C615\n产品类别：上肢外骨骼\n规格明细：\n- 净重：3.9 kg\n- 电池：92Wh",
            "section_path": ["6. 产品规格明细", "6.1 上肢外骨骼", "C615"],
            "product_ids": ["C615"],
            "source_block_ids": ["p2", "p3"],
            "quality_flags": ["tier_matrix_category_conflict"],
            "metadata": {"quality_status": "needs_review"},
        },
    }

    card = build_product_card("C615", parts)

    assert card is not None
    assert card["text"].count("产品编号：C615") == 1
    assert "净重：3.9 kg" in card["text"]
    assert "电池：92Wh" in card["text"]
    assert card["card_chunk_ids"] == ["profile", "specs"]
    assert card["source_block_ids"] == ["p1", "p2", "p3"]
    assert card["quality_status"] == "needs_review"
    assert card["quality_flags"] == ["tier_matrix_category_conflict"]


def test_fact_evidence_expands_to_full_product_card() -> None:
    chunks = [
        {
            "chunk_id": "chunk_product_C615_profile",
            "chunk_type": "product_profile",
            "title": "C615 产品概览",
            "text": "产品编号：C615\n产品类别：上肢外骨骼\n类型：AI 动力上肢外骨骼",
            "section_path": ["6. 产品规格明细", "6.1 上肢外骨骼", "C615"],
            "product_ids": ["C615"],
            "source_block_ids": ["p1"],
            "metadata": {"quality_status": "normal"},
        },
        {
            "chunk_id": "chunk_product_C615_specs",
            "chunk_type": "product_specs",
            "title": "C615 规格明细",
            "text": "产品编号：C615\n产品类别：上肢外骨骼\n规格明细：\n- 净重：3.9 kg",
            "section_path": ["6. 产品规格明细", "6.1 上肢外骨骼", "C615"],
            "product_ids": ["C615"],
            "source_block_ids": ["p2"],
            "metadata": {"quality_status": "normal"},
        },
    ]
    retriever = HybridRetriever(
        engine=object(), chunks=chunks, bm25_index={"dummy": 1}
    )
    analysis = analyze_query("C615 的重量是多少？")
    results = [
        {
            "chunk_id": "chunk_product_C615_specs",
            "chunk_type": "product_specs",
            "product_ids": ["C615"],
            "final_score": 0.9,
        }
    ]

    expanded = retriever._expand_product_cards(results, analysis)

    assert len(expanded) == 1
    assert expanded[0]["chunk_id"] == "card_product_C615"
    assert expanded[0]["chunk_type"] == "product_specs"
    assert "3.9 kg" in expanded[0]["text"]
    assert expanded[0]["final_score"] == 0.9


def test_scenario_exact_candidate_matches_matrix_row() -> None:
    chunks = [
        {
            "chunk_id": "chunk_matrix_scenario_logistics",
            "chunk_type": "matrix_scenario",
            "title": "场景矩阵｜物流搬运与装卸",
            "text": "物流搬运与装卸",
        },
        {
            "chunk_id": "chunk_matrix_scenario_fire",
            "chunk_type": "matrix_scenario",
            "title": "场景矩阵｜消防与应急救援",
            "text": "消防与应急救援",
        },
    ]
    analysis = analyze_query("物流搬运与装卸场景推荐哪些产品？")

    candidates = build_exact_candidates(analysis, chunks)

    assert candidates[0].chunk_id == "chunk_matrix_scenario_logistics"
    assert candidates[0].reason == "scenario_matrix"


def test_filter_candidates_put_matrix_and_mysql_products_first() -> None:
    chunks = [
        {
            "chunk_id": "chunk_matrix_tier_entry",
            "chunk_type": "matrix_tier",
            "title": "层级矩阵｜Tier 1",
            "text": "入门级",
            "tier_keys": ["entry"],
            "category_keys": [],
        },
        {
            "chunk_id": "chunk_product_C621_profile",
            "chunk_type": "product_profile",
            "title": "C621 产品概览",
            "text": "C621",
            "product_ids": ["C621"],
        },
        {
            "chunk_id": "chunk_product_C621_specs",
            "chunk_type": "product_specs",
            "title": "C621 规格明细",
            "text": "C621",
            "product_ids": ["C621"],
        },
    ]
    analysis = analyze_query("入门级腰背外骨骼有哪些？")
    products = [{"product_id": "C621"}]

    candidates = build_exact_candidates(analysis, chunks, products)

    assert [candidate.chunk_id for candidate in candidates] == [
        "chunk_matrix_tier_entry",
        "chunk_product_C621_profile",
    ]


def test_quality_query_requests_profile_and_specs() -> None:
    analysis = analyze_query("C655 的最大助力到底是多少？")

    assert analysis.intent == "quality"
    assert set(analysis.chunk_types) == {"product_profile", "product_specs"}
