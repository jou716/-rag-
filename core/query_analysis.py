from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from core.text_analysis import normalize_text

PRODUCT_RE = re.compile(r"(?<![a-z0-9])c(\d{3})(?!\d)", re.IGNORECASE)

CATEGORY_TERMS = {
    "upper_limb": ("上肢", "手臂", "肩部", "肩关节"),
    "waist_back": ("腰背", "腰部", "腰椎", "背部", "后背"),
    "lower_limb_load": ("负重下肢", "下肢", "腿部", "膝关节", "髋关节"),
}

TIER_TERMS = {
    "high": ("tier 3", "tier3", "高端", "先进智能"),
    "mid": ("tier 2", "tier2", "中端", "均衡性能"),
    "entry": ("tier 1", "tier1", "入门", "基础防护"),
}

POWER_TERMS = {
    "electric": ("电动", "动力驱动", "主动助力", "电驱"),
    "passive": ("被动", "机械助力", "纯机械"),
    "electric_cart": ("电动推车", "推车联动"),
}

METRIC_TERMS = (
    ("系统总重", "system_weight"),
    ("最大负载", "max_load"),
    ("助力扭矩", "assist_torque"),
    ("助力范围", "assist_range"),
    ("最大手臂助力", "max_assist"),
    ("最大助力", "max_assist"),
    ("易损件寿命", "service_life"),
    ("续航时间", "runtime"),
    ("续航", "runtime"),
    ("电池", "battery"),
    ("净重", "weight"),
    ("重量", "weight"),
    ("身高", "applicable_height"),
    ("减载效率", "relief_efficiency"),
    ("自由度", "dof"),
    ("工作温度", "operating_temperature"),
    ("材料", "materials"),
)

PROFILE_TERMS = (
    "什么类型",
    "是什么产品",
    "适合什么",
    "适合哪些",
    "面向哪些",
    "应用场景",
    "目标用户",
    "人群",
    "产品概览",
    "属于哪一类",
    "是否属于",
)

SECTION_TERMS = (
    "公司概况",
    "公司全称",
    "公司的全称",
    "售后",
    "服务内容",
    "响应",
    "地址",
    "电话",
    "邮箱",
    "怎么联系",
    "如何联系",
    "核心技术",
    "关键技术",
    "技术体系",
)

QUALITY_TERMS = (
    "规格不完整",
    "规格信息完整",
    "完整吗",
    "到底",
    "冲突",
    "复核",
    "需要确认",
)

COMPARISON_TERMS = ("区别", "对比", "比较", "分别", "差异")
FILTER_TERMS = ("有哪些", "哪些产品", "列出", "都有哪些", "tier")
SCENARIO_TERMS = (
    "场景",
    "推荐",
    "作业",
    "适合什么产品",
    "物流搬运",
    "装配场景",
    "矿业",
    "消防",
    "应急救援",
)


@dataclass(frozen=True)
class QueryAnalysis:
    query: str
    normalized: str
    intent: str
    product_ids: tuple[str, ...] = ()
    category_keys: tuple[str, ...] = ()
    tier_keys: tuple[str, ...] = ()
    power_types: tuple[str, ...] = ()
    metric_keys: tuple[str, ...] = ()
    chunk_types: tuple[str, ...] = ()
    signals: tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_structured_filters(self) -> bool:
        return bool(self.category_keys or self.tier_keys or self.power_types)

    def as_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "intent": self.intent,
            "product_ids": list(self.product_ids),
            "category_keys": list(self.category_keys),
            "tier_keys": list(self.tier_keys),
            "power_types": list(self.power_types),
            "metric_keys": list(self.metric_keys),
            "chunk_types": list(self.chunk_types),
            "signals": list(self.signals),
            "has_structured_filters": self.has_structured_filters,
        }


def _collect(text: str, mapping: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    values: list[str] = []
    for key, terms in mapping.items():
        if any(term in text for term in terms):
            values.append(key)
    return tuple(values)


def _collect_metrics(text: str) -> tuple[str, ...]:
    values: list[str] = []
    for term, metric_key in METRIC_TERMS:
        if term in text and metric_key not in values:
            values.append(metric_key)
    return tuple(values)


def _normalize_power_types(values: tuple[str, ...]) -> tuple[str, ...]:
    if "electric_cart" in values:
        return ("electric_cart",)
    if "electric" in values:
        return ("electric", "electric_cart")
    return values


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def analyze_query(query: str) -> QueryAnalysis:
    normalized = normalize_text(query)
    product_ids = tuple(dict.fromkeys(f"C{match}" for match in PRODUCT_RE.findall(query)))
    category_keys = _collect(normalized, CATEGORY_TERMS)
    tier_keys = _collect(normalized, TIER_TERMS)
    power_types = _normalize_power_types(_collect(normalized, POWER_TERMS))
    metric_keys = _collect_metrics(normalized)

    signals: list[str] = []
    if product_ids:
        signals.append("product_id")
    if category_keys:
        signals.append("category")
    if tier_keys:
        signals.append("tier")
    if power_types:
        signals.append("power")
    if metric_keys:
        signals.append("metric")

    profile_signal = _contains_any(normalized, PROFILE_TERMS)
    section_signal = _contains_any(normalized, SECTION_TERMS)
    quality_signal = _contains_any(normalized, QUALITY_TERMS)
    comparison_signal = len(product_ids) >= 2 and _contains_any(
        normalized, COMPARISON_TERMS
    )
    filter_signal = _contains_any(normalized, FILTER_TERMS) and bool(
        category_keys or tier_keys or power_types
    )
    scenario_signal = _contains_any(normalized, SCENARIO_TERMS)

    if section_signal and not product_ids:
        intent = "section"
    elif comparison_signal:
        intent = "comparison"
    elif quality_signal:
        intent = "quality"
    elif filter_signal:
        intent = "filter"
    elif product_ids and profile_signal:
        intent = "profile"
    elif scenario_signal and not metric_keys:
        intent = "scenario"
    elif product_ids and metric_keys:
        intent = "fact"
    elif product_ids:
        intent = "product"
    else:
        intent = "semantic"

    chunk_types: tuple[str, ...] = ()
    if intent in {"fact", "comparison"}:
        chunk_types = ("product_specs",)
    elif intent == "profile":
        chunk_types = ("product_profile",)
    elif intent == "quality":
        chunk_types = ("product_profile", "product_specs")
    elif intent == "section":
        chunk_types = ("section",)
    elif intent == "filter":
        chunk_types = ("product_profile", "matrix_tier", "matrix_category")
        if metric_keys:
            chunk_types = ("product_specs",) + chunk_types
    elif intent == "scenario":
        chunk_types = ("matrix_scenario",)

    for signal, enabled in (
        ("profile", profile_signal),
        ("quality", quality_signal),
        ("comparison", comparison_signal),
        ("filter", filter_signal),
        ("scenario", scenario_signal),
        ("section", section_signal),
    ):
        if enabled:
            signals.append(signal)

    return QueryAnalysis(
        query=query,
        normalized=normalized,
        intent=intent,
        product_ids=product_ids,
        category_keys=category_keys,
        tier_keys=tier_keys,
        power_types=power_types,
        metric_keys=metric_keys,
        chunk_types=chunk_types,
        signals=tuple(signals),
    )
