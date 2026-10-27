from __future__ import annotations

import hashlib
import re
from typing import Any


ISSUE_TYPE_LABELS = {
    "height_field_conflict": "身高字段冲突",
    "assist_payload_inconsistency": "助力与负载冲突",
    "assist_load_semantics_mismatch": "助力/负载语义不一致",
    "missing_tier": "缺少产品层级",
    "category_boundary": "类别边界待确认",
    "incomplete_specs": "原文规格不完整",
    "missing_usage_fields": "缺少适用信息",
    "tier_matrix_category_conflict": "分级表与明细类别冲突",
    "category_matrix_conflict": "分类表与明细类别冲突",
    "matrix_product_separator_missing": "矩阵产品分隔符缺失",
    "assist_unit_inconsistency": "助力单位不统一",
}

SEVERITY_LABELS = {"high": "高危", "medium": "中危", "low": "低危"}


def _md_cell(value: Any) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def _fmt_num(value: Any) -> str:
    if isinstance(value, (int, float)) and float(value).is_integer():
        return str(int(value))
    return str(value)


def make_issue_id(issue_type: str, product_id: str | None, field_name: str | None) -> str:
    key = f"{issue_type}|{product_id or 'global'}|{field_name or ''}"
    return "issue_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def build_quality_issues(
    products: list[dict[str, Any]],
    all_specs: list[dict[str, Any]],
    matrices: dict[str, list[dict[str, Any]]],
    incomplete_sources: dict[str, str],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    product_by_id = {product["product_id"]: product for product in products}

    def add_issue(
        issue_type: str,
        severity: str,
        message: str,
        product_id: str | None = None,
        field_name: str | None = None,
        source_block_ids: list[str] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        issues.append(
            {
                "issue_id": make_issue_id(issue_type, product_id, field_name),
                "issue_type": issue_type,
                "severity": severity,
                "product_id": product_id,
                "field_name": field_name,
                "message": message,
                "source_block_ids": source_block_ids or [],
                "details_json": details or {},
            }
        )

    def find_spec(product: dict[str, Any], metric_key: str) -> dict[str, Any] | None:
        return next(
            (spec for spec in product["specs"] if spec["metric_key"] == metric_key),
            None,
        )

    for product in products:
        product_id = product["product_id"]
        heading_id = product["source_heading_block_id"]
        type_spec = find_spec(product, "product_type")
        type_source = type_spec["source_block_id"] if type_spec else heading_id

        if product["tier_key"] == "unknown":
            add_issue(
                "missing_tier",
                "medium",
                f"{product_id} 缺少“产品层级”字段",
                product_id,
                "tier",
                [heading_id],
            )

        if product_id in incomplete_sources:
            add_issue(
                "incomplete_specs",
                "high",
                f"{product_id} 的规格原文明确标注为不完整",
                product_id,
                "specs",
                [incomplete_sources[product_id], heading_id],
            )

        missing_usage = [
            field_name
            for field_name in ("target_users", "applications")
            if not product[field_name]
        ]
        if missing_usage:
            add_issue(
                "missing_usage_fields",
                "medium",
                f"{product_id} 缺少目标用户或应用场景",
                product_id,
                ",".join(missing_usage),
                [heading_id],
            )

        if product["category_key"] == "lower_limb_load" and "腰臂" in product["product_type_text"]:
            add_issue(
                "category_boundary",
                "high",
                f"{product_id} 位于下肢章节，但类型描述为“腰臂外骨骼套装”",
                product_id,
                "category",
                [heading_id, type_source],
            )

        if "背心" in product["product_type_text"] or "推车" in product["product_type_text"]:
            add_issue(
                "category_boundary",
                "high",
                f"{product_id} 是电动推车联动背心，是否归入下肢外骨骼需确认",
                product_id,
                "category",
                [heading_id, type_source],
            )

        assist = find_spec(product, "max_assist")
        if assist:
            metadata = assist.get("metadata_json") or {}
            secondary_max = metadata.get("secondary_max")
            if (
                assist.get("value_num") is not None
                and secondary_max is not None
                and assist["value_num"] > secondary_max
            ):
                add_issue(
                    "assist_payload_inconsistency",
                    "high",
                    f"{product_id} 的最大助力大于同一原文中的助力负载上限",
                    product_id,
                    "max_assist",
                    [assist["source_block_id"]],
                    {
                        "max_assist": assist["value_num"],
                        "secondary_range": metadata.get("secondary_range"),
                    },
                )

        max_load = find_spec(product, "max_load")
        if (
            "最大助力" in product["product_type_text"]
            and not find_spec(product, "max_assist")
            and max_load
        ):
            add_issue(
                "assist_load_semantics_mismatch",
                "medium",
                f"{product_id} 的类型描述写“最大助力”，规格表写“最大负载”",
                product_id,
                "max_assist",
                [type_source, max_load["source_block_id"]],
            )

        applicable_height = find_spec(product, "applicable_height")
        recommended_height = find_spec(product, "recommended_height")
        if applicable_height and recommended_height:
            applicable_range = (
                applicable_height["value_min"],
                applicable_height["value_max"],
            )
            recommended_range = (
                recommended_height["value_min"],
                recommended_height["value_max"],
            )
            if applicable_range != recommended_range:
                add_issue(
                    "height_field_conflict",
                    "medium",
                    f"{product_id} 的“适用身高范围”和“推荐身高”不一致",
                    product_id,
                    "height",
                    [
                        applicable_height["source_block_id"],
                        recommended_height["source_block_id"],
                    ],
                    {
                        "applicable_height": applicable_range,
                        "recommended_height": recommended_range,
                    },
                )

    for row in matrices["tier_matrix"]:
        for ref in row["product_ids_json"]:
            product = product_by_id.get(ref["product_id"])
            if product and product["category_label"] != ref["category_label"]:
                add_issue(
                    "tier_matrix_category_conflict",
                    "high",
                    f"{ref['product_id']} 在分级表中归入“{ref['category_label']}”，"
                    f"但产品明细归入“{product['category_label']}”",
                    ref["product_id"],
                    "category",
                    [row["source_block_id"], product["source_heading_block_id"]],
                    {
                        "tier_matrix_category": ref["category_label"],
                        "product_detail_category": product["category_label"],
                    },
                )

    for row in matrices["category_matrix"]:
        for ref in row["product_ids_json"]:
            product = product_by_id.get(ref["product_id"])
            if product and product["category_label"] != row["category_label"]:
                add_issue(
                    "category_matrix_conflict",
                    "high",
                    f"{ref['product_id']} 在分类表中归入“{row['category_label']}”，"
                    f"但产品明细归入“{product['category_label']}”",
                    ref["product_id"],
                    "category",
                    [row["source_block_id"], product["source_heading_block_id"]],
                )

    matrix_rows: list[dict[str, Any]] = []
    for matrix_name in ("scenario_matrix", "tier_matrix", "category_matrix"):
        for row in matrices[matrix_name]:
            raw = row.get("recommended_product_ids_raw") or row.get("product_ids_raw") or ""
            if re.search(r"\)\s*C\d", raw):
                matrix_rows.append(
                    {
                        "matrix": matrix_name,
                        "source_block_id": row["source_block_id"],
                        "raw": raw,
                    }
                )
    if matrix_rows:
        add_issue(
            "matrix_product_separator_missing",
            "low",
            "矩阵中的推荐产品 ID 存在缺少分隔符的拼接",
            None,
            "product_ids",
            [item["source_block_id"] for item in matrix_rows],
            {"rows": matrix_rows},
        )

    force_specs = [
        spec
        for spec in all_specs
        if spec["metric_key"] == "max_assist"
        and spec["unit_normalized"] in {"kg", "kgf", "N"}
    ]
    force_units = sorted({spec["unit_normalized"] for spec in force_specs})
    if len(force_units) > 1:
        add_issue(
            "assist_unit_inconsistency",
            "medium",
            "最大助力在不同产品中使用 kg、kgf、N 等不同单位",
            None,
            "max_assist",
            [spec["source_block_id"] for spec in force_specs],
            {
                "units": force_units,
                "values": [
                    {
                        "product_id": spec["product_id"],
                        "raw_value": spec["raw_value"],
                    }
                    for spec in force_specs
                ],
            },
        )

    issue_product_ids = {
        issue["product_id"] for issue in issues if issue["product_id"]
    }
    for product in products:
        product["quality_status"] = (
            "needs_review"
            if product["product_id"] in issue_product_ids
            else "ok"
        )

    return issues


def _issue_evidence(issue: dict[str, Any]) -> str:
    details = issue.get("details_json") or {}
    issue_type = issue["issue_type"]
    if issue_type == "height_field_conflict":
        applicable = details.get("applicable_height") or [None, None]
        recommended = details.get("recommended_height") or [None, None]
        return (
            f"适用 {_fmt_num(applicable[0])}–{_fmt_num(applicable[1])}；"
            f"推荐 {_fmt_num(recommended[0])}–{_fmt_num(recommended[1])}"
        )
    if issue_type == "assist_payload_inconsistency":
        return (
            f"最大助力 {_fmt_num(details.get('max_assist'))}；"
            f"原文助力负载 {details.get('secondary_range')}"
        )
    if issue_type == "tier_matrix_category_conflict":
        return (
            f"分级表：{details.get('tier_matrix_category')}；"
            f"产品明细：{details.get('product_detail_category')}"
        )
    if issue_type == "assist_unit_inconsistency":
        return "混用单位：" + "、".join(details.get("units") or [])
    if issue_type == "matrix_product_separator_missing":
        rows = details.get("rows") or []
        return f"涉及 {len(rows)} 个矩阵行，原文存在产品 ID 粘连"
    return "见来源块原文"


def render_quality_markdown(catalog: dict[str, Any]) -> str:
    report = catalog["quality_report"]
    summary = report["summary"]
    issues = report["issues"]
    products = catalog["products"]
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    sorted_issues = sorted(
        issues,
        key=lambda issue: (
            severity_rank.get(issue["severity"], 9),
            issue.get("product_id") or "",
            issue["issue_type"],
        ),
    )

    issues_by_product: dict[str, list[dict[str, Any]]] = {}
    for issue in sorted_issues:
        product_id = issue.get("product_id")
        if product_id:
            issues_by_product.setdefault(product_id, []).append(issue)

    lines = [
        "# N3 数据质量报告",
        "",
        "## 结论",
        "",
        f"- 产品数：{summary['products']}",
        f"- 规格数：{summary['specs']}",
        (
            f"- 问题数：{summary['issues']}（高危 "
            f"{summary['by_severity'].get('high', 0)}、中危 "
            f"{summary['by_severity'].get('medium', 0)}、低危 "
            f"{summary['by_severity'].get('low', 0)}）"
        ),
        f"- 需人工复核产品：{len(summary['products_needing_review'])} 款",
        "",
        "本报告只标记问题，不改写原文，也不覆盖原始值。后续检索语料仍以",
        "`document_blocks.jsonl` 中的原始 block 为准，产品模型只作为结构化索引。",
        "",
        "## 需人工复核的产品",
        "",
        "| 产品 | 类别 | 层级 | 规格数 | 问题类型 |",
        "| --- | --- | --- | ---: | --- |",
    ]

    product_by_id = {product["product_id"]: product for product in products}
    for product_id in summary["products_needing_review"]:
        product = product_by_id[product_id]
        issue_labels = sorted(
            {
                ISSUE_TYPE_LABELS.get(issue["issue_type"], issue["issue_type"])
                for issue in issues_by_product.get(product_id, [])
            }
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    _md_cell(product_id),
                    _md_cell(product["category_label"]),
                    _md_cell(product["tier_label"] or "未识别"),
                    _md_cell(product["spec_count"]),
                    _md_cell("、".join(issue_labels)),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## 问题明细",
            "",
            "| 严重度 | 产品 | 问题 | 字段 | 说明 | 证据 | 来源块 |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for issue in sorted_issues:
        lines.append(
            "| "
            + " | ".join(
                [
                    _md_cell(SEVERITY_LABELS.get(issue["severity"], issue["severity"])),
                    _md_cell(issue.get("product_id") or "全局"),
                    _md_cell(
                        ISSUE_TYPE_LABELS.get(
                            issue["issue_type"], issue["issue_type"]
                        )
                    ),
                    _md_cell(issue.get("field_name") or "-"),
                    _md_cell(issue["message"]),
                    _md_cell(_issue_evidence(issue)),
                    _md_cell("<br>".join(issue.get("source_block_ids") or [])),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## 全部产品状态",
            "",
            "| 产品 | 类别 | 层级 | 动力 | 规格数 | 状态 |",
            "| --- | --- | --- | --- | ---: | --- |",
        ]
    )
    for product in products:
        status = "需复核" if product["quality_status"] == "needs_review" else "通过"
        lines.append(
            "| "
            + " | ".join(
                [
                    _md_cell(product["product_id"]),
                    _md_cell(product["category_label"]),
                    _md_cell(product["tier_label"] or "未识别"),
                    _md_cell(product["power_type_label"]),
                    _md_cell(product["spec_count"]),
                    _md_cell(status),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## 处理原则",
            "",
            "- 源文档中的矛盾、缺字段和单位混用只做标记，不在导入阶段擅自修正。",
            "- `needs_review` 产品仍可被检索，但回答时应同时展示质量标记和原文来源。",
            "- 精确筛选与数值比较以 MySQL 结构化字段为准；语义召回以原始 block 为准。",
            "",
        ]
    )
    return "\n".join(lines)
