from __future__ import annotations

import re
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Iterable, Mapping, Sequence

from app.config import settings
from app.db import get_engine
from core.hybrid_search import HybridRetriever
from core.llm import LLMConfig, LLMError, OpenAICompatibleClient
from core.prompting import build_llm_messages
from core.query_analysis import QueryAnalysis, analyze_query
from core.text_analysis import normalize_text

MAX_EVIDENCE = 15
CITATION_RE = re.compile(r"\[\s*E(\d+)\s*\]")
CITATION_RANGE_RE = re.compile(
    r"\[\s*E(\d+)\s*\]?\s*[–—\-~]\s*\[?\s*E(\d+)\s*\]"
)
GROUNDING_TOKEN_RE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:kgf|kg|g|wh|mah|cm|mm|n·m|n|v|h|s|%|小时|分钟|秒|次|档|°c)",
    re.IGNORECASE,
)

MISSING_MARKERS = (
    "未提供",
    "未提及",
    "未说明",
    "未列出",
    "未包含",
    "无法确认",
    "无法回答",
    "未找到",
    "均缺失",
    "缺失",
)

METRIC_LABELS = {
    "system_weight": ("系统总重",),
    "max_load": ("最大负载", "推荐负载"),
    "assist_torque": ("助力扭矩",),
    "assist_range": ("助力范围", "推荐负载"),
    "max_assist": (
        "最大手臂助力",
        "最大肩部助力",
        "每侧髋最大",
        "每膝最大",
        "最大助力",
        "助力",
    ),
    "service_life": ("易损件寿命",),
    "runtime": ("续航", "电池续航"),
    "battery": ("电池", "电池规格"),
    "weight": ("净重", "单体重量", "重量"),
    "applicable_height": (
        "适用身高范围",
        "尺寸/适用身高",
        "推荐用户身高",
        "推荐身高",
        "身高",
    ),
    "relief_efficiency": ("减载效率", "行走助力效率", "站立助力效率"),
    "dof": ("自由度",),
    "operating_temperature": ("工作温度",),
    "materials": ("材料",),
    "product_type": ("类型",),
    "target_users": ("目标用户",),
    "applications": ("应用场景",),
    "power_source": ("动力源", "动力类型"),
}

METRIC_NAMES = {
    "system_weight": "系统总重",
    "max_load": "最大负载",
    "assist_torque": "助力扭矩",
    "assist_range": "助力范围",
    "max_assist": "最大助力",
    "service_life": "易损件寿命",
    "runtime": "续航",
    "battery": "电池",
    "weight": "重量",
    "applicable_height": "适用身高",
    "relief_efficiency": "减载效率",
    "dof": "自由度",
    "operating_temperature": "工作温度",
    "materials": "材料",
    "product_type": "产品类型",
    "target_users": "目标用户",
    "applications": "应用场景",
    "power_source": "动力源",
}

QUALITY_FLAG_LABELS = {
    "height_field_conflict": "身高字段冲突",
    "assist_payload_inconsistency": "最大助力与助力负载冲突",
    "assist_load_semantics_mismatch": "最大助力与最大负载语义不一致",
    "missing_tier": "缺少产品层级",
    "category_boundary": "产品类别边界冲突",
    "incomplete_specs": "规格信息不完整",
    "missing_usage_fields": "缺少目标用户或应用场景",
    "tier_matrix_category_conflict": "层级矩阵与产品类别冲突",
    "matrix_product_separator_missing": "矩阵产品分隔缺失",
    "assist_unit_inconsistency": "助力单位不一致",
}

UNSUPPORTED_FIELD_TERMS = (
    {
        "key": "price",
        "query_terms": ("价格", "售价", "报价", "多少钱", "费用"),
        "evidence_terms": ("价格", "售价", "报价", "费用"),
        "message": "产品目录未提供价格信息",
    },
    {
        "key": "warranty",
        "query_terms": ("保修", "质保", "保修期"),
        "evidence_terms": ("保修", "质保"),
        "message": "产品目录未提供保修期信息",
    },
    {
        "key": "certification",
        "query_terms": ("认证", "证书", "ce认证"),
        "evidence_terms": ("认证", "证书", "ce认证"),
        "message": "产品目录未提及 CE 或其他认证信息，不能推断已通过",
    },
    {
        "key": "bluetooth",
        "query_terms": ("蓝牙", "bluetooth"),
        "evidence_terms": ("蓝牙", "bluetooth"),
        "message": "产品目录未提及蓝牙功能，无法确认",
    },
)


@dataclass(frozen=True)
class EvidenceLine:
    label: str
    value: str
    raw: str


@dataclass
class AnswerDraft:
    status: str
    answer: str
    missing_parts: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    refusal_reason: str | None = None


def _clean_markdown(text: str) -> str:
    return text.replace("**", "").replace("__", "").strip()


def parse_evidence_lines(text: str) -> list[EvidenceLine]:
    lines: list[EvidenceLine] = []
    for raw_line in text.splitlines():
        line = _clean_markdown(raw_line.strip())
        if not line:
            continue
        if line.startswith("- "):
            line = line[2:].strip()
        match = re.match(r"^([^：:]{1,40})[：:](.*)$", line)
        if match and match.group(2).strip():
            lines.append(
                EvidenceLine(
                    label=match.group(1).strip(),
                    value=match.group(2).strip(),
                    raw=line,
                )
            )
        else:
            lines.append(EvidenceLine(label="", value=line, raw=line))
    return lines


def _citation(evidence: Mapping[str, Any]) -> str:
    return evidence.get("citation") or f"[{evidence['evidence_id']}]"


def _evidence_text(evidence: Mapping[str, Any]) -> str:
    return str(evidence.get("text", ""))


def _find_exact_lines(
    evidence: Mapping[str, Any], labels: Sequence[str]
) -> list[EvidenceLine]:
    wanted = set(labels)
    return [
        line
        for line in parse_evidence_lines(_evidence_text(evidence))
        if line.label in wanted
    ]


def _find_contains_lines(
    evidence: Mapping[str, Any], labels: Sequence[str]
) -> list[EvidenceLine]:
    return [
        line
        for line in parse_evidence_lines(_evidence_text(evidence))
        if any(label in line.label for label in labels)
    ]


def _find_label_lines(
    evidence: Mapping[str, Any], labels: Sequence[str]
) -> list[EvidenceLine]:
    return _find_exact_lines(evidence, labels) or _find_contains_lines(evidence, labels)


def _metric_matches(
    evidence_items: Sequence[Mapping[str, Any]], metric_key: str
) -> list[tuple[Mapping[str, Any], EvidenceLine]]:
    labels = METRIC_LABELS.get(metric_key)
    if not labels:
        return []
    matches: list[tuple[Mapping[str, Any], EvidenceLine]] = []
    for evidence in evidence_items:
        for line in _find_label_lines(evidence, labels):
            matches.append((evidence, line))
    return matches


def _product_evidence(
    evidence_items: Sequence[Mapping[str, Any]],
    product_id: str,
    *,
    preferred_chunk_types: Sequence[str] = (),
) -> list[Mapping[str, Any]]:
    candidates = [
        evidence
        for evidence in evidence_items
        if product_id in (evidence.get("product_ids") or [])
    ]
    preferences = {
        chunk_type: index for index, chunk_type in enumerate(preferred_chunk_types)
    }
    return sorted(
        candidates,
        key=lambda evidence: (
            preferences.get(evidence.get("chunk_type"), len(preferences)),
            int(evidence.get("rank") or 999),
        ),
    )


def _dedupe_values(
    matches: Sequence[tuple[Mapping[str, Any], EvidenceLine]]
) -> list[tuple[Mapping[str, Any], EvidenceLine]]:
    seen: set[tuple[str, str, str]] = set()
    result: list[tuple[Mapping[str, Any], EvidenceLine]] = []
    for evidence, line in matches:
        key = (str(evidence.get("evidence_id")), line.label, line.value)
        if key in seen:
            continue
        seen.add(key)
        result.append((evidence, line))
    return result


def _quality_flags(evidence_items: Iterable[Mapping[str, Any]]) -> set[str]:
    flags: set[str] = set()
    for evidence in evidence_items:
        flags.update(evidence.get("quality_flags") or [])
    return flags


def _quality_notes(
    product_id: str,
    evidence_items: Sequence[Mapping[str, Any]],
    *,
    relevant_only: bool = False,
) -> list[str]:
    flags = _quality_flags(evidence_items)
    if not flags:
        return []
    if relevant_only and not flags & {
        "assist_payload_inconsistency",
        "category_boundary",
        "incomplete_specs",
    }:
        return []

    notes: list[str] = []
    primary = evidence_items[0]
    citation = _citation(primary)

    if "assist_payload_inconsistency" in flags:
        conflict_matches = [
            (evidence, line)
            for evidence in evidence_items
            for line in parse_evidence_lines(_evidence_text(evidence))
            if "最大助力" in line.label and "助力负载" in line.value
        ]
        if conflict_matches:
            conflict_evidence, line = conflict_matches[0]
            notes.append(
                f"{product_id} 的原文同一行写“{line.label}：{line.value}”，"
                f"最大助力与助力负载上限不一致，存在参数冲突，需要人工复核 "
                f"{_citation(conflict_evidence)}。"
            )

    if "category_boundary" in flags:
        category_lines = _find_label_lines(primary, ("产品类别",))
        type_lines = _find_label_lines(primary, ("类型",))
        section_path = primary.get("section_path") or []
        section = section_path[-2] if len(section_path) >= 2 else "原文对应章节"
        category = category_lines[0].value if category_lines else "未识别"
        product_type = type_lines[0].value if type_lines else "未识别"
        notes.append(
            f"{product_id} 在目录中位于“{section}”章节，类别字段为“{category}”，"
            f"但类型描述为“{product_type}”，存在类别边界冲突，建议人工复核 {citation}。"
        )

    if "incomplete_specs" in flags:
        spec_labels: list[str] = []
        for evidence in evidence_items:
            for line in parse_evidence_lines(_evidence_text(evidence)):
                if line.label in {
                    "产品编号",
                    "产品类别",
                    "产品层级",
                    "规格明细",
                }:
                    continue
                if line.label and line.label not in spec_labels:
                    spec_labels.append(line.label)
        details = "、".join(spec_labels[:4]) if spec_labels else "少量字段"
        missing_usage = (
            "，且目标用户和应用场景字段缺失"
            if "missing_usage_fields" in flags
            else ""
        )
        notes.append(
            f"{product_id} 的规格信息不完整：现有证据只提供 {details}{missing_usage}，"
            f"建议人工复核 {citation}。"
        )

    if not notes:
        labels = "、".join(
            QUALITY_FLAG_LABELS.get(flag, flag) for flag in sorted(flags)
        )
        notes.append(f"{product_id} 存在质量标记：{labels}，建议人工复核 {citation}。")
    return notes


def _detect_unsupported_fields(
    query: str, evidence_items: Sequence[Mapping[str, Any]]
) -> list[dict[str, str]]:
    normalized_query = normalize_text(query)
    normalized_evidence = normalize_text(
        "\n".join(_evidence_text(evidence) for evidence in evidence_items)
    )
    unsupported: list[dict[str, str]] = []
    for definition in UNSUPPORTED_FIELD_TERMS:
        query_hit = any(term in normalized_query for term in definition["query_terms"])
        if definition["key"] == "certification":
            query_hit = query_hit or bool(
                re.search(r"(?<![a-z])ce(?![a-z])", normalized_query)
            )
        if not query_hit:
            continue
        evidence_hit = any(
            term in normalized_evidence for term in definition["evidence_terms"]
        )
        if not evidence_hit:
            unsupported.append(
                {"key": definition["key"], "message": definition["message"]}
            )
    return unsupported


def _answer_fact(
    analysis: QueryAnalysis, evidence_items: Sequence[Mapping[str, Any]]
) -> AnswerDraft:
    parts: list[str] = []
    missing: list[str] = []
    for product_id in analysis.product_ids:
        product_items = _product_evidence(
            evidence_items,
            product_id,
            preferred_chunk_types=("product_specs", "product_profile"),
        )
        if not product_items:
            missing.append(f"{product_id} 的证据")
            continue
        for metric_key in analysis.metric_keys:
            matches = _dedupe_values(_metric_matches(product_items, metric_key))
            if not matches:
                missing.append(
                    f"{product_id} 的{METRIC_NAMES.get(metric_key, metric_key)}"
                )
                continue
            for evidence, line in matches:
                parts.append(
                    f"{product_id} 的{METRIC_NAMES.get(metric_key, line.label)}为 "
                    f"{line.value} {_citation(evidence)}。"
                )
    if not parts:
        return AnswerDraft(
            status="refused",
            answer="",
            refusal_reason="现有证据没有覆盖问题中的关键字段",
            missing_parts=missing,
        )
    return AnswerDraft(
        status="partial" if missing else "answered",
        answer="\n".join(parts),
        missing_parts=missing,
    )


def _comparison_all_values(
    product_items: Sequence[Mapping[str, Any]],
) -> dict[str, list[tuple[str, Mapping[str, Any]]]]:
    label_values: dict[str, list[tuple[str, Mapping[str, Any]]]] = {}
    for evidence in product_items:
        for line in parse_evidence_lines(_evidence_text(evidence)):
            if line.label in {
                "产品编号",
                "产品类别",
                "产品层级",
                "规格明细",
            }:
                continue
            if line.label:
                label_values.setdefault(line.label, []).append((line.value, evidence))
    return label_values


def _answer_comparison(
    analysis: QueryAnalysis, evidence_items: Sequence[Mapping[str, Any]]
) -> AnswerDraft:
    products = list(analysis.product_ids)
    metrics = list(analysis.metric_keys)
    parts: list[str] = []
    missing: list[str] = []

    for product_id in products:
        product_items = _product_evidence(
            evidence_items,
            product_id,
            preferred_chunk_types=("product_specs", "product_profile"),
        )
        if not product_items:
            missing.append(f"{product_id} 的证据")
            continue
        if metrics:
            values: list[str] = []
            for metric_key in metrics:
                matches = _dedupe_values(_metric_matches(product_items, metric_key))
                if not matches:
                    missing.append(
                        f"{product_id} 的{METRIC_NAMES.get(metric_key, metric_key)}"
                    )
                    continue
                rendered = "；".join(
                    f"{line.label} {line.value} {_citation(evidence)}"
                    for evidence, line in matches
                )
                values.append(rendered)
            if values:
                parts.append(f"{product_id}：" + "；".join(values) + "。")
        else:
            label_values = _comparison_all_values(product_items)
            if label_values:
                rendered = "；".join(
                    f"{label} {values[0][0]} {_citation(values[0][1])}"
                    for label, values in list(label_values.items())[:8]
                )
                parts.append(f"{product_id}：" + rendered + "。")
        parts.extend(_quality_notes(product_id, product_items, relevant_only=True))

    if not parts:
        return AnswerDraft(
            status="refused",
            answer="",
            refusal_reason="现有证据不足以完成对比",
            missing_parts=missing,
        )
    return AnswerDraft(
        status="partial" if missing else "answered",
        answer="\n".join(parts),
        missing_parts=missing,
    )


def _answer_profile(
    analysis: QueryAnalysis, evidence_items: Sequence[Mapping[str, Any]]
) -> AnswerDraft:
    query = normalize_text(analysis.query)
    parts: list[str] = []
    missing: list[str] = []
    for product_id in analysis.product_ids:
        product_items = _product_evidence(
            evidence_items,
            product_id,
            preferred_chunk_types=("product_profile", "product_specs"),
        )
        if not product_items:
            missing.append(f"{product_id} 的证据")
            continue
        primary = product_items[0]
        selected_labels: list[str] = []
        if "类型" in query or "是什么产品" in query:
            selected_labels.append("类型")
        if "人群" in query or "用户" in query:
            selected_labels.append("目标用户")
        if "场景" in query or "应用" in query:
            selected_labels.append("应用场景")
        if "作业" in query or "适合" in query:
            selected_labels.extend(["类型", "目标用户", "应用场景"])
        if "哪一类" in query or "属于" in query:
            selected_labels.extend(["产品类别", "产品层级", "类型", "动力类型"])
        if not selected_labels:
            selected_labels.extend(
                [
                    "产品类别",
                    "产品层级",
                    "动力类型",
                    "类型",
                    "目标用户",
                    "应用场景",
                    "动力源",
                ]
            )

        seen_labels: set[str] = set()
        for label in selected_labels:
            if label in seen_labels:
                continue
            seen_labels.add(label)
            matches = _find_label_lines(primary, (label,))
            if not matches:
                continue
            parts.append(f"{product_id} 的{label}：{matches[0].value} {_citation(primary)}。")
        parts.extend(
            _quality_notes(
                product_id,
                product_items,
                relevant_only=not any(
                    term in query for term in ("冲突", "复核", "完整", "属于", "哪一类")
                ),
            )
        )
    if not parts:
        return AnswerDraft(
            status="refused",
            answer="",
            refusal_reason="现有证据不足以描述该产品",
            missing_parts=missing,
        )
    return AnswerDraft(
        status="partial" if missing else "answered",
        answer="\n".join(parts),
        missing_parts=missing,
    )


def _answer_filter(
    analysis: QueryAnalysis, evidence_items: Sequence[Mapping[str, Any]]
) -> AnswerDraft:
    parts: list[str] = []
    seen_products: set[str] = set()
    for evidence in evidence_items:
        if evidence.get("chunk_type") != "product_profile":
            continue
        for product_id in evidence.get("product_ids") or []:
            if product_id in seen_products:
                continue
            seen_products.add(product_id)
            category = _find_label_lines(evidence, ("产品类别",))
            tier = _find_label_lines(evidence, ("产品层级",))
            power = _find_label_lines(evidence, ("动力类型",))
            labels = [value[0].value for value in (category, tier, power) if value]
            suffix = f"（{'，'.join(labels)}）" if labels else ""
            parts.append(f"- {product_id}{suffix} {_citation(evidence)}")

    if not parts:
        for evidence in evidence_items:
            recommended = _find_label_lines(evidence, ("推荐产品（原文）",))
            if recommended:
                parts.append(
                    f"原文推荐产品：{recommended[0].value} {_citation(evidence)}。"
                )
                break
    if parts:
        for evidence in evidence_items:
            if evidence.get("chunk_type") == "matrix_tier":
                basis = _find_label_lines(evidence, ("产品层级",))
            elif evidence.get("chunk_type") == "matrix_category":
                basis = _find_label_lines(evidence, ("类别",))
            else:
                continue
            if basis:
                parts.append(
                    f"筛选依据：{basis[0].label} {basis[0].value} "
                    f"{_citation(evidence)}。"
                )
                break
    if not parts:
        return AnswerDraft(
            status="refused",
            answer="",
            refusal_reason="现有证据没有给出符合条件的产品列表",
        )
    return AnswerDraft(
        status="answered",
        answer="符合条件的产品有：\n" + "\n".join(parts),
    )


def _answer_scenario(
    analysis: QueryAnalysis, evidence_items: Sequence[Mapping[str, Any]]
) -> AnswerDraft:
    scenario_items = [
        evidence
        for evidence in evidence_items
        if evidence.get("chunk_type") == "matrix_scenario"
    ]
    if not scenario_items:
        scenario_items = list(evidence_items[:1])
    if not scenario_items:
        return AnswerDraft(
            status="refused",
            answer="",
            refusal_reason="现有证据没有覆盖该场景",
        )
    evidence = scenario_items[0]
    fields = (
        ("目标用户群", "目标用户群"),
        ("典型应用场景", "典型作业"),
        ("首选外骨骼类型", "首选外骨骼类型"),
        ("推荐产品（原文）", "原文推荐产品"),
    )
    parts: list[str] = []
    for label, display in fields:
        lines = _find_label_lines(evidence, (label,))
        if lines:
            parts.append(f"{display}：{lines[0].value} {_citation(evidence)}。")
    if not parts:
        return AnswerDraft(
            status="refused",
            answer="",
            refusal_reason="场景证据缺少可回答字段",
        )
    return AnswerDraft(status="answered", answer="\n".join(parts))


def _answer_section(
    analysis: QueryAnalysis, evidence_items: Sequence[Mapping[str, Any]]
) -> AnswerDraft:
    section_items = [
        evidence for evidence in evidence_items if evidence.get("chunk_type") == "section"
    ]
    if not section_items:
        section_items = list(evidence_items[:1])
    if not section_items:
        return AnswerDraft(
            status="refused",
            answer="",
            refusal_reason="现有证据没有覆盖该章节",
        )
    evidence = section_items[0]
    query = normalize_text(analysis.query)
    parsed = [
        line
        for line in parse_evidence_lines(_evidence_text(evidence))
        if line.label not in {"章节"}
    ]
    if "全称" in query:
        labels: tuple[str, ...] = ("公司名称",)
    elif "地址" in query:
        labels = ("公司地址",)
    elif "联系" in query or "电话" in query or "邮箱" in query:
        labels = ("电话", "邮箱")
    elif "售后" in query or "服务" in query:
        labels = (
            "售后响应",
            "服务内容",
            "及时响应",
            "产品操作培训",
            "定制化产品方案",
        )
    else:
        labels = ()
    selected = [line for line in parsed if line.label in labels] if labels else parsed
    if not selected:
        selected = parsed[:6]
    if not selected:
        return AnswerDraft(
            status="refused",
            answer="",
            refusal_reason="章节证据没有可用内容",
        )
    parts = [
        f"{line.label + '：' if line.label else ''}{line.value} {_citation(evidence)}。"
        for line in selected
    ]
    return AnswerDraft(status="answered", answer="\n".join(parts))


def _answer_quality(
    analysis: QueryAnalysis, evidence_items: Sequence[Mapping[str, Any]]
) -> AnswerDraft:
    parts: list[str] = []
    missing: list[str] = []
    for product_id in analysis.product_ids:
        product_items = _product_evidence(
            evidence_items,
            product_id,
            preferred_chunk_types=("product_profile", "product_specs"),
        )
        if not product_items:
            missing.append(f"{product_id} 的证据")
            continue
        notes = _quality_notes(product_id, product_items)
        if notes:
            parts.extend(notes)
        else:
            missing.append(f"{product_id} 的质量问题")
    if not parts:
        return AnswerDraft(
            status="refused",
            answer="",
            refusal_reason="现有证据没有显示明确的质量问题",
            missing_parts=missing,
        )
    return AnswerDraft(
        status="partial" if missing else "answered",
        answer="\n".join(parts),
        missing_parts=missing,
    )


def _compose_draft(
    analysis: QueryAnalysis, evidence_items: Sequence[Mapping[str, Any]]
) -> AnswerDraft:
    if not evidence_items:
        if analysis.product_ids:
            missing_products = "、".join(analysis.product_ids)
            reason = f"产品目录中没有找到 {missing_products} 的相关信息"
        else:
            reason = "现有证据不足以回答这个问题"
        return AnswerDraft(status="refused", answer="", refusal_reason=reason)

    unsupported = _detect_unsupported_fields(analysis.query, evidence_items)
    if analysis.intent == "comparison":
        draft = _answer_comparison(analysis, evidence_items)
    elif analysis.intent == "fact":
        draft = _answer_fact(analysis, evidence_items)
    elif analysis.intent == "profile":
        draft = _answer_profile(analysis, evidence_items)
    elif analysis.intent == "filter":
        draft = _answer_filter(analysis, evidence_items)
    elif analysis.intent == "scenario":
        draft = _answer_scenario(analysis, evidence_items)
    elif analysis.intent == "section":
        draft = _answer_section(analysis, evidence_items)
    elif analysis.intent == "quality":
        draft = _answer_quality(analysis, evidence_items)
    elif analysis.intent == "product" and analysis.product_ids:
        draft = _answer_profile(analysis, evidence_items)
    else:
        draft = AnswerDraft(
            status="refused",
            answer="",
            refusal_reason="现有证据不足以给出可靠回答",
        )

    if unsupported:
        notes = [item["message"] for item in unsupported]
        if not draft.answer:
            return AnswerDraft(
                status="refused",
                answer="",
                missing_parts=draft.missing_parts + notes,
                refusal_reason="；".join(notes),
            )
        draft.notes.extend(notes)
        draft.status = "partial"
        draft.answer += "\n" + "\n".join(f"补充说明：{note}。" for note in notes)
    return draft


def extract_citation_ids(answer: str) -> list[str]:
    ids: list[str] = []

    def add(evidence_id: str) -> None:
        if evidence_id not in ids:
            ids.append(evidence_id)

    for match in CITATION_RANGE_RE.finditer(answer):
        start, end = int(match.group(1)), int(match.group(2))
        if start > end:
            start, end = end, start
        for number in range(start, end + 1):
            add(f"E{number}")
    for match in CITATION_RE.finditer(answer):
        add(f"E{match.group(1)}")
    return ids


def _normalize_grounding_text(text: str) -> str:
    normalized = normalize_text(text)
    normalized = (
        normalized.replace("×", "x")
        .replace("*", "x")
        .replace("✕", "x")
        .replace("`", "")
        .replace("**", "")
    )
    return re.sub(r"\s+", "", normalized)


def _iter_grounding_sentences(answer: str) -> Iterable[str]:
    without_citations = CITATION_RANGE_RE.sub("", answer)
    without_citations = CITATION_RE.sub("", without_citations)
    for line in without_citations.splitlines():
        for sentence in re.split(r"(?<=[。；;!?！？])", line):
            if sentence.strip():
                yield sentence


def _truncate_at_missing_marker(text: str) -> str:
    positions = [text.find(marker) for marker in MISSING_MARKERS if marker in text]
    if not positions:
        return text
    return text[: min(positions)]


def validate_grounding(
    answer: str, evidence_items: Sequence[Mapping[str, Any]], citations: Sequence[str]
) -> dict[str, Any]:
    cited = set(citations)
    cited_text = _normalize_grounding_text(
        "\n".join(
            _evidence_text(evidence)
            for evidence in evidence_items
            if evidence["evidence_id"] in cited
        )
    )
    checked_tokens: list[str] = []
    unsupported_tokens: list[str] = []
    for sentence in _iter_grounding_sentences(answer):
        checkable = _truncate_at_missing_marker(sentence)
        for token in GROUNDING_TOKEN_RE.findall(checkable):
            normalized_token = _normalize_grounding_text(token)
            if normalized_token in checked_tokens:
                continue
            checked_tokens.append(normalized_token)
            if normalized_token not in cited_text:
                unsupported_tokens.append(token)
    return {
        "valid": not unsupported_tokens,
        "checked_tokens": checked_tokens,
        "unsupported_tokens": unsupported_tokens,
    }


def _is_heading_like(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if stripped.startswith("#"):
        return True
    cleaned = re.sub(r"^[\-\*\s]+", "", stripped)
    if cleaned.endswith(("：", ":")):
        return True
    if re.fullmatch(r"\*\*[^*]+\*\*", cleaned):
        return True
    return False


def validate_citation_coverage(answer: str) -> dict[str, Any]:
    uncited_blocks: list[str] = []
    for block in re.split(r"\n\s*\n", answer):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        substantive = [line for line in lines if not _is_heading_like(line)]
        if not substantive:
            continue
        uncited: list[str] = []
        for line in substantive:
            claim = _truncate_at_missing_marker(line)
            claim = CITATION_RANGE_RE.sub("", claim)
            claim = CITATION_RE.sub("", claim)
            if re.search(r"C\d{3}|\d", claim):
                uncited.append(line)
        if not uncited:
            continue
        if CITATION_RE.search(block) or CITATION_RANGE_RE.search(block):
            continue
        uncited_blocks.append(" / ".join(uncited[:2]))
    return {"valid": not uncited_blocks, "uncited_factual_lines": uncited_blocks}


def _validate_llm_answer(
    answer: str,
    evidence_items: Sequence[Mapping[str, Any]],
    unsupported: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    citations = extract_citation_ids(answer)
    available_ids = {item["evidence_id"] for item in evidence_items}
    unknown_citations = [item for item in citations if item not in available_ids]
    grounding = validate_grounding(answer, evidence_items, citations)
    coverage = validate_citation_coverage(answer)
    missing_only = (
        bool(unsupported)
        and not citations
        and not coverage["uncited_factual_lines"]
    )
    valid = not (
        (not citations and not missing_only)
        or unknown_citations
        or not grounding["valid"]
        or not coverage["valid"]
    )
    return {
        "valid": valid,
        "citations": citations,
        "unknown_citations": unknown_citations,
        "grounding": grounding,
        "coverage": coverage,
        "missing_only": missing_only,
    }


def _build_repair_prompt(
    user_prompt: str, answer: str, validation: Mapping[str, Any]
) -> str:
    problems: list[str] = []
    if not validation["citations"] and not validation["missing_only"]:
        problems.append("答案没有标注任何 [E#] 引用。")
    if validation["unknown_citations"]:
        problems.append(
            "使用了当前证据包中不存在的引用编号："
            + "、".join(validation["unknown_citations"])
        )
    if not validation["coverage"]["valid"]:
        problems.append(
            "以下段落没有标注引用："
            + "；".join(validation["coverage"]["uncited_factual_lines"])
        )
    if not validation["grounding"]["valid"]:
        problems.append(
            "以下数值没有出现在被引用的证据原文中："
            + "、".join(validation["grounding"]["unsupported_tokens"])
        )
    return (
        f"{user_prompt}\n\n"
        f"你上一次的回答如下：\n{answer}\n\n"
        "该回答未通过校验：\n- "
        + "\n- ".join(problems)
        + "\n\n请重写答案：保留正确内容，为每个事实段落补上真实存在的 [E#] 引用，"
        "不要新增证据中没有的数字、产品号或结论。只输出重写后的答案。"
    )


class GroundedAnswerService:
    def __init__(
        self,
        *,
        retriever: HybridRetriever | None = None,
        max_evidence: int = MAX_EVIDENCE,
        llm_client: Any | None = None,
        generation_mode: str | None = None,
    ) -> None:
        self.retriever = retriever or HybridRetriever(engine=get_engine())
        self.max_evidence = min(max_evidence, MAX_EVIDENCE)
        self._search_lock = Lock()
        self.generation_mode = generation_mode or settings.answer_generation_mode
        self.llm_client = llm_client
        if self.llm_client is None and settings.llm_configured:
            self.llm_client = OpenAICompatibleClient(
                LLMConfig(
                    base_url=settings.llm_base_url,
                    api_key=settings.llm_api_key,
                    model=settings.llm_model,
                    timeout_seconds=settings.llm_timeout_seconds,
                )
            )

    def ask(self, query: str, *, top_k: int = MAX_EVIDENCE) -> dict[str, Any]:
        if not query.strip():
            raise ValueError("Query must not be empty")
        evidence_top_k = max(1, min(top_k, self.max_evidence))
        with self._search_lock:
            packet = self.retriever.search_with_evidence(
                query,
                top_k=evidence_top_k,
                evidence_top_k=evidence_top_k,
            )
        analysis = analyze_query(query)
        evidence = packet["evidence"]

        if not evidence:
            reason = (
                f"产品目录中没有找到 {'、'.join(analysis.product_ids)} 的相关信息"
                if analysis.product_ids
                else "现有证据不足以回答这个问题"
            )
            return {
                "query": query,
                "status": "refused",
                "answer": "",
                "citations": [],
                "missing_parts": [],
                "notes": [],
                "refusal_reason": reason,
                "generation_mode": self.generation_mode,
                "analysis": analysis.as_dict(),
                "citation_validation": {
                    "valid": True,
                    "unknown_citation_ids": [],
                    "uncited_factual_lines": [],
                },
                "grounding_validation": {
                    "valid": True,
                    "checked_tokens": [],
                    "unsupported_tokens": [],
                },
                "evidence": evidence,
            }

        if self.generation_mode == "local":
            return self._ask_local(query, analysis, evidence)
        return self._ask_llm(query, analysis, evidence)

    def _ask_local(
        self,
        query: str,
        analysis: QueryAnalysis,
        evidence: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        draft = _compose_draft(analysis, evidence)
        citations = extract_citation_ids(draft.answer)
        available_ids = {item["evidence_id"] for item in evidence}
        unknown_citations = [item for item in citations if item not in available_ids]
        grounding = validate_grounding(draft.answer, evidence, citations)
        if draft.status != "refused" and (
            not citations or unknown_citations or not grounding["valid"]
        ):
            draft = AnswerDraft(
                status="refused",
                answer="",
                refusal_reason="回答引用校验失败，已拒绝输出未经证据支持的内容",
            )
            citations = []
            grounding = {
                "valid": False,
                "checked_tokens": grounding["checked_tokens"],
                "unsupported_tokens": grounding["unsupported_tokens"],
            }
        return {
            "query": query,
            "status": draft.status,
            "answer": draft.answer,
            "citations": citations,
            "missing_parts": draft.missing_parts,
            "notes": draft.notes,
            "refusal_reason": draft.refusal_reason,
            "generation_mode": "local",
            "analysis": analysis.as_dict(),
            "citation_validation": {
                "valid": not unknown_citations,
                "unknown_citation_ids": unknown_citations,
                "uncited_factual_lines": [],
            },
            "grounding_validation": grounding,
            "evidence": evidence,
        }

    def _ask_llm(
        self,
        query: str,
        analysis: QueryAnalysis,
        evidence: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        if self.llm_client is None:
            return self._error_packet(
                query,
                analysis,
                evidence,
                "未配置可用的 LLM API，不能生成答案",
            )

        unsupported = _detect_unsupported_fields(query, evidence)
        notes = [item["message"] for item in unsupported]
        attempts = 0
        try:
            system_prompt, user_prompt = build_llm_messages(query, evidence)
            answer = self.llm_client.generate(system_prompt, user_prompt)
            attempts = 1
            validation = _validate_llm_answer(answer, evidence, unsupported)
            if not validation["valid"]:
                repair_prompt = _build_repair_prompt(user_prompt, answer, validation)
                answer = self.llm_client.generate(system_prompt, repair_prompt)
                attempts = 2
                validation = _validate_llm_answer(answer, evidence, unsupported)
        except LLMError as exc:
            return self._error_packet(
                query,
                analysis,
                evidence,
                f"LLM 调用失败：{type(exc).__name__}",
            )
        except Exception as exc:
            return self._error_packet(
                query,
                analysis,
                evidence,
                f"LLM 调用异常：{type(exc).__name__}",
            )

        citations = validation["citations"]
        unknown_citations = validation["unknown_citations"]
        grounding = validation["grounding"]
        coverage = validation["coverage"]
        missing_only = validation["missing_only"]
        if not validation["valid"]:
            return {
                "query": query,
                "status": "error",
                "answer": "",
                "citations": citations,
                "missing_parts": notes,
                "notes": notes,
                "refusal_reason": "LLM 输出未通过引用或数值 grounding 校验，已拒绝展示",
                "generation_mode": "llm",
                "analysis": analysis.as_dict(),
                "citation_validation": {
                    "valid": not unknown_citations and coverage["valid"],
                    "unknown_citation_ids": unknown_citations,
                    **coverage,
                },
                "grounding_validation": grounding,
                "attempts": attempts,
                "evidence": evidence,
            }

        status = "refused" if missing_only else ("partial" if notes else "answered")
        return {
            "query": query,
            "status": status,
            "answer": answer,
            "citations": citations,
            "missing_parts": notes,
            "notes": notes,
            "refusal_reason": answer if status == "refused" else None,
            "generation_mode": "llm",
            "analysis": analysis.as_dict(),
            "citation_validation": {
                "valid": not unknown_citations and coverage["valid"],
                "unknown_citation_ids": unknown_citations,
                **coverage,
            },
            "grounding_validation": grounding,
            "attempts": attempts,
            "evidence": evidence,
        }

    def _error_packet(
        self,
        query: str,
        analysis: QueryAnalysis,
        evidence: Sequence[Mapping[str, Any]],
        message: str,
    ) -> dict[str, Any]:
        return {
            "query": query,
            "status": "error",
            "answer": "",
            "citations": [],
            "missing_parts": [],
            "notes": [],
            "refusal_reason": message,
            "generation_mode": "llm",
            "analysis": analysis.as_dict(),
            "citation_validation": {
                "valid": False,
                "unknown_citation_ids": [],
                "uncited_factual_lines": [],
            },
            "grounding_validation": {
                "valid": False,
                "checked_tokens": [],
                "unsupported_tokens": [],
            },
            "evidence": evidence,
        }
