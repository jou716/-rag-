import pytest

from core.query_analysis import analyze_query


def test_product_id_is_detected_next_to_chinese_text() -> None:
    analysis = analyze_query("C615的续航时间是多少")

    assert analysis.product_ids == ("C615",)
    assert analysis.intent == "fact"
    assert "runtime" in analysis.metric_keys
    assert analysis.chunk_types == ("product_specs",)


@pytest.mark.parametrize(
    ("query", "intent", "category", "tier", "power"),
    [
        ("高端电动上肢外骨骼有哪些？", "filter", "upper_limb", "high", "electric"),
        ("入门级腰背外骨骼有哪些？", "filter", "waist_back", "entry", None),
        ("负重下肢外骨骼有哪些产品？", "filter", "lower_limb_load", None, None),
        ("电动或动力驱动的腰背外骨骼有哪些？", "filter", "waist_back", None, "electric"),
        ("Tier 3 高端产品有哪些？", "filter", None, "high", None),
    ],
)
def test_filter_queries_extract_structured_filters(
    query: str,
    intent: str,
    category: str | None,
    tier: str | None,
    power: str | None,
) -> None:
    analysis = analyze_query(query)

    assert analysis.intent == intent
    assert (category in analysis.category_keys) if category else not analysis.category_keys
    assert (tier in analysis.tier_keys) if tier else not analysis.tier_keys
    assert (power in analysis.power_types) if power else not analysis.power_types


@pytest.mark.parametrize(
    ("query", "intent", "products", "chunk_types"),
    [
        ("C615 是什么类型的产品？", "profile", ("C615",), ("product_profile",)),
        ("C622 适合什么作业和人群？", "profile", ("C622",), ("product_profile",)),
        (
            "C615 和 C616 的电池与续航有什么区别？",
            "comparison",
            ("C615", "C616"),
            ("product_specs",),
        ),
        (
            "C655 的最大助力到底是多少？",
            "quality",
            ("C655",),
            ("product_profile", "product_specs"),
        ),
        ("C654 属于哪一类产品？", "profile", ("C654",), ("product_profile",)),
        ("公司的售后响应是什么？", "section", (), ("section",)),
        ("物流搬运与装卸场景推荐哪些产品？", "scenario", (), ("matrix_scenario",)),
    ],
)
def test_intent_routing(
    query: str,
    intent: str,
    products: tuple[str, ...],
    chunk_types: tuple[str, ...],
) -> None:
    analysis = analyze_query(query)

    assert analysis.intent == intent
    assert analysis.product_ids == products
    assert analysis.chunk_types == chunk_types


def test_unknown_product_id_is_preserved_for_refusal_routing() -> None:
    analysis = analyze_query("C999 的续航时间是多少？")

    assert analysis.product_ids == ("C999",)
    assert analysis.intent == "fact"


def test_back_alias_routes_enumeration_to_waist_filter() -> None:
    analysis = analyze_query("背部外骨骼有哪些，他们的重量是多少")

    assert analysis.intent == "filter"
    assert analysis.category_keys == ("waist_back",)
    assert "weight" in analysis.metric_keys
    assert analysis.chunk_types[0] == "product_specs"


def test_generic_electric_query_includes_cart_power_type() -> None:
    analysis = analyze_query("下肢外骨骼有哪些是电动的")

    assert analysis.power_types == ("electric", "electric_cart")


def test_explicit_cart_query_does_not_include_plain_electric() -> None:
    analysis = analyze_query("电动推车联动的下肢外骨骼有哪些")

    assert analysis.power_types == ("electric_cart",)
