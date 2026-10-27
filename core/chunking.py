from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

PROFILE_METRIC_KEYS = {
    "tier",
    "product_type",
    "target_users",
    "applications",
    "power_source",
}

SEPARATOR_TEXTS = {"---", "—", "-"}

CATEGORY_KEYS = {
    "上肢外骨骼": "upper_limb",
    "腰背外骨骼": "waist_back",
    "负重下肢外骨骼": "lower_limb_load",
}

POWER_KEYS = {"电": "electric", "被": "passive"}

MATRIX_PREFIXES = ("3.", "4.", "5.")


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _heading_ids_by_path(parse_result: dict[str, Any]) -> dict[tuple[str, ...], str]:
    return {
        tuple(section["section_path"]): section["block_id"]
        for section in parse_result["report"]["sections"]
    }


def _heading_ids_for_path(
    path: list[str], heading_by_path: dict[tuple[str, ...], str]
) -> list[str]:
    return [
        heading_by_path[tuple(path[: index + 1])]
        for index in range(len(path))
        if tuple(path[: index + 1]) in heading_by_path
    ]


def _chunk(
    chunk_id: str,
    chunk_type: str,
    title: str,
    text: str,
    raw_text: str,
    section_path: list[str],
    source_block_ids: list[str],
    heading_block_ids: list[str],
    product_ids: list[str] | None = None,
    category_keys: list[str] | None = None,
    tier_keys: list[str] | None = None,
    power_types: list[str] | None = None,
    spec_ids: list[str] | None = None,
    metric_keys: list[str] | None = None,
    quality_flags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "chunk_id": chunk_id,
        "chunk_type": chunk_type,
        "title": title,
        "text": text,
        "raw_text": raw_text,
        "section_path": section_path,
        "source_block_ids": _unique(source_block_ids),
        "heading_block_ids": _unique(heading_block_ids),
        "product_ids": _unique(product_ids or []),
        "category_keys": _unique(category_keys or []),
        "tier_keys": _unique(tier_keys or []),
        "power_types": _unique(power_types or []),
        "spec_ids": _unique(spec_ids or []),
        "metric_keys": _unique(metric_keys or []),
        "quality_flags": _unique(quality_flags or []),
        "char_count": len(text),
        "metadata": metadata or {},
    }


def _quality_flags_by_product(catalog: dict[str, Any]) -> dict[str, list[str]]:
    flags: dict[str, list[str]] = defaultdict(list)
    for issue in catalog["quality_report"]["issues"]:
        product_id = issue.get("product_id")
        if product_id:
            flags[product_id].append(issue["issue_type"])
    return flags


def _product_chunks(
    catalog: dict[str, Any],
    heading_by_path: dict[tuple[str, ...], str],
    blocks_by_product: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    flags_by_product = _quality_flags_by_product(catalog)

    for product in catalog["products"]:
        product_id = product["product_id"]
        path = product["section_path"]
        heading_ids = _heading_ids_for_path(path, heading_by_path)
        heading_block_id = product["source_heading_block_id"]
        specs_by_key: dict[str, dict[str, Any]] = {}
        for spec in product["specs"]:
            specs_by_key.setdefault(spec["metric_key"], spec)

        profile_lines = [
            f"产品编号：{product_id}",
            f"产品类别：{product['category_label']}",
            f"产品层级：{product['tier_label'] or '未识别'}",
            f"动力类型：{product['power_type_label']}",
        ]
        profile_specs: list[dict[str, Any]] = []
        for metric_key in ("product_type", "target_users", "applications", "power_source"):
            spec = specs_by_key.get(metric_key)
            if spec:
                profile_lines.append(f"{spec['metric_label']}：{spec['raw_value']}")
                profile_specs.append(spec)

        profile_source_ids = [heading_block_id] + [
            spec["source_block_id"]
            for spec in product["specs"]
            if spec["metric_key"] in PROFILE_METRIC_KEYS
        ]
        chunks.append(
            _chunk(
                chunk_id=f"chunk_product_{product_id}_profile",
                chunk_type="product_profile",
                title=f"{product_id} 产品概览",
                text="\n".join(profile_lines),
                raw_text="\n".join(
                    [product_id]
                    + [f"{spec['metric_label']}：{spec['raw_value']}" for spec in profile_specs]
                ),
                section_path=path,
                source_block_ids=profile_source_ids,
                heading_block_ids=heading_ids,
                product_ids=[product_id],
                category_keys=[product["category_key"]],
                tier_keys=[product["tier_key"]],
                power_types=[product["power_type"]],
                spec_ids=[spec["spec_id"] for spec in profile_specs],
                metric_keys=[spec["metric_key"] for spec in profile_specs],
                quality_flags=flags_by_product.get(product_id, []),
                metadata={
                    "quality_status": product["quality_status"],
                    "tier_raw": product["tier_raw"],
                    "power_source_raw": product["power_source_raw"],
                },
            )
        )

        spec_items = [
            spec for spec in product["specs"] if spec["metric_key"] not in PROFILE_METRIC_KEYS
        ]
        spec_lines = [
            f"产品编号：{product_id}",
            f"产品类别：{product['category_label']}",
            f"产品层级：{product['tier_label'] or '未识别'}",
            "规格明细：",
        ]
        spec_lines.extend(
            f"- {spec['metric_label']}：{spec['raw_value']}" for spec in spec_items
        )
        container_block_ids = [
            block["block_id"]
            for block in blocks_by_product.get(product_id, [])
            if block["text"].startswith("- **规格**")
        ]
        chunks.append(
            _chunk(
                chunk_id=f"chunk_product_{product_id}_specs",
                chunk_type="product_specs",
                title=f"{product_id} 规格明细",
                text="\n".join(spec_lines),
                raw_text="\n".join(
                    [product_id]
                    + [f"{spec['metric_label']}：{spec['raw_value']}" for spec in spec_items]
                ),
                section_path=path,
                source_block_ids=[heading_block_id]
                + container_block_ids
                + [spec["source_block_id"] for spec in spec_items],
                heading_block_ids=heading_ids,
                product_ids=[product_id],
                category_keys=[product["category_key"]],
                tier_keys=[product["tier_key"]],
                power_types=[product["power_type"]],
                spec_ids=[spec["spec_id"] for spec in spec_items],
                metric_keys=[spec["metric_key"] for spec in spec_items],
                quality_flags=flags_by_product.get(product_id, []),
                metadata={
                    "quality_status": product["quality_status"],
                    "spec_count": len(spec_items),
                    "container_block_ids": container_block_ids,
                },
            )
        )

    return chunks


def _section_chunks(
    parse_result: dict[str, Any],
    heading_by_path: dict[tuple[str, ...], str],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for block in parse_result["blocks"]:
        if block.get("product_id"):
            continue
        if block["block_type"] in {"heading", "table_row"}:
            continue
        if block["text"].strip() in SEPARATOR_TEXTS:
            continue
        path = block["section_path"]
        if len(path) > 1 and path[1].startswith(MATRIX_PREFIXES):
            continue
        if path:
            grouped[tuple(path)].append(block)

    chunks: list[dict[str, Any]] = []
    for path, blocks in sorted(
        grouped.items(), key=lambda item: item[1][0]["order"]
    ):
        heading_id = heading_by_path.get(path)
        if not heading_id:
            continue
        title = path[-1]
        lines = [f"章节：{' > '.join(path[1:]) if len(path) > 1 else title}"]
        lines.extend(block["text"] for block in blocks)
        chunks.append(
            _chunk(
                chunk_id=f"chunk_section_{heading_id}",
                chunk_type="section",
                title=title,
                text="\n".join(lines),
                raw_text="\n".join(block["text"] for block in blocks),
                section_path=list(path),
                source_block_ids=[heading_id] + [block["block_id"] for block in blocks],
                heading_block_ids=_heading_ids_for_path(list(path), heading_by_path),
                metadata={
                    "block_types": sorted({block["block_type"] for block in blocks}),
                    "block_count": len(blocks),
                },
            )
        )

    return chunks


def _tier_keys_from_label(label: str) -> list[str]:
    if "Tier 1" in label:
        return ["entry"]
    if "Tier 2" in label:
        return ["mid"]
    if "Tier 3" in label:
        return ["high"]
    return []


def _power_types_from_refs(refs: list[dict[str, Any]]) -> list[str]:
    return [
        POWER_KEYS[ref["power_marker"]]
        for ref in refs
        if ref.get("power_marker") in POWER_KEYS
    ]


def _matrix_chunks(
    catalog: dict[str, Any],
    blocks_by_id: dict[str, dict[str, Any]],
    heading_by_path: dict[tuple[str, ...], str],
    header_by_table: dict[str, str],
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []

    for row in catalog["matrices"]["scenario_matrix"]:
        block = blocks_by_id[row["source_block_id"]]
        path = block["section_path"]
        heading_id = heading_by_path[tuple(path)]
        refs = row["recommended_product_ids_json"]
        fields = [
            ("目标用户群", row["target_user_group"]),
            ("典型应用场景", row["scenarios"]),
            ("核心痛点", row["pain_points"]),
            ("核心动作", row["core_actions"]),
            ("易伤部位", row["injury_parts"]),
            ("首选外骨骼类型", row["preferred_exo_type"]),
            ("推荐产品（原文）", row["recommended_product_ids_raw"]),
        ]
        chunks.append(
            _chunk(
                chunk_id=f"chunk_matrix_scenario_{row['scenario_id']}",
                chunk_type="matrix_scenario",
                title=f"场景矩阵｜{row['target_user_group']}",
                text="\n".join(
                    ["矩阵：应用场景与用户群映射"]
                    + [f"{label}：{value}" for label, value in fields]
                ),
                raw_text="\n".join(f"{label}：{value}" for label, value in fields),
                section_path=path,
                source_block_ids=[
                    heading_id,
                    header_by_table.get(block["table_id"], ""),
                    row["source_block_id"],
                ],
                heading_block_ids=_heading_ids_for_path(path, heading_by_path),
                product_ids=[ref["product_id"] for ref in refs],
                power_types=_power_types_from_refs(refs),
                metadata={
                    "matrix": "scenario",
                    "header_block_id": header_by_table.get(block["table_id"]),
                    "product_refs": refs,
                    "recommended_product_ids_raw": row["recommended_product_ids_raw"],
                },
            )
        )

    for row in catalog["matrices"]["tier_matrix"]:
        block = blocks_by_id[row["source_block_id"]]
        path = block["section_path"]
        heading_id = heading_by_path[tuple(path)]
        refs = row["product_ids_json"]
        fields = [
            ("产品层级", row["tier_label"]),
            ("市场定位", row["market_position"]),
            ("产品形态", row["product_forms"]),
            ("适用场景", row["scenarios"]),
            ("推荐产品（原文）", row["product_ids_raw"]),
        ]
        chunks.append(
            _chunk(
                chunk_id=f"chunk_matrix_tier_{row['tier_id']}",
                chunk_type="matrix_tier",
                title=f"分级矩阵｜{row['tier_label']}",
                text="\n".join(
                    ["矩阵：产品分级与选型指南"]
                    + [f"{label}：{value}" for label, value in fields]
                ),
                raw_text="\n".join(f"{label}：{value}" for label, value in fields),
                section_path=path,
                source_block_ids=[
                    heading_id,
                    header_by_table.get(block["table_id"], ""),
                    row["source_block_id"],
                ],
                heading_block_ids=_heading_ids_for_path(path, heading_by_path),
                product_ids=[ref["product_id"] for ref in refs],
                category_keys=[
                    CATEGORY_KEYS[ref["category_label"]]
                    for ref in refs
                    if ref.get("category_label") in CATEGORY_KEYS
                ],
                tier_keys=_tier_keys_from_label(row["tier_label"]),
                power_types=_power_types_from_refs(refs),
                metadata={
                    "matrix": "tier",
                    "header_block_id": header_by_table.get(block["table_id"]),
                    "product_refs": refs,
                    "product_ids_raw": row["product_ids_raw"],
                },
            )
        )

    for row in catalog["matrices"]["category_matrix"]:
        block = blocks_by_id[row["source_block_id"]]
        path = block["section_path"]
        heading_id = heading_by_path[tuple(path)]
        refs = row["product_ids_json"]
        fields = [
            ("类别", row["category_label"]),
            ("核心功能", row["core_function"]),
            ("典型场景", row["scenarios"]),
            ("推荐产品（原文）", row["product_ids_raw"]),
        ]
        chunks.append(
            _chunk(
                chunk_id=f"chunk_matrix_category_{row['category_id']}",
                chunk_type="matrix_category",
                title=f"分类矩阵｜{row['category_label']}",
                text="\n".join(
                    ["矩阵：产品分类与功能匹配"]
                    + [f"{label}：{value}" for label, value in fields]
                ),
                raw_text="\n".join(f"{label}：{value}" for label, value in fields),
                section_path=path,
                source_block_ids=[
                    heading_id,
                    header_by_table.get(block["table_id"], ""),
                    row["source_block_id"],
                ],
                heading_block_ids=_heading_ids_for_path(path, heading_by_path),
                product_ids=[ref["product_id"] for ref in refs],
                category_keys=[CATEGORY_KEYS[row["category_label"]]]
                if row["category_label"] in CATEGORY_KEYS
                else [],
                power_types=_power_types_from_refs(refs),
                metadata={
                    "matrix": "category",
                    "header_block_id": header_by_table.get(block["table_id"]),
                    "product_refs": refs,
                    "product_ids_raw": row["product_ids_raw"],
                },
            )
        )

    return chunks


def _legend_chunk(
    parse_result: dict[str, Any],
    heading_by_path: dict[tuple[str, ...], str],
) -> dict[str, Any] | None:
    notes = [
        block
        for block in parse_result["blocks"]
        if block["text"].startswith("(注：电=") or block["text"].startswith("（注：电=")
    ]
    if not notes:
        return None

    unique_texts = _unique(block["text"] for block in notes)
    matrix_headings = [
        heading_by_path[tuple(block["section_path"])]
        for block in notes
        if tuple(block["section_path"]) in heading_by_path
    ]
    return _chunk(
        chunk_id="chunk_matrix_legend",
        chunk_type="matrix_legend",
        title="矩阵符号说明",
        text="矩阵符号说明：\n" + "\n".join(unique_texts),
        raw_text="\n".join(block["text"] for block in notes),
        section_path=notes[0]["section_path"][:1],
        source_block_ids=[block["block_id"] for block in notes],
        heading_block_ids=matrix_headings,
        metadata={"note_count": len(notes)},
    )


def build_chunks(
    parse_result: dict[str, Any], catalog: dict[str, Any]
) -> list[dict[str, Any]]:
    heading_by_path = _heading_ids_by_path(parse_result)
    blocks_by_id = {block["block_id"]: block for block in parse_result["blocks"]}
    blocks_by_product: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for block in parse_result["blocks"]:
        product_id = block.get("product_id")
        if product_id:
            blocks_by_product[product_id].append(block)
    header_by_table = {
        block["table_id"]: block["block_id"]
        for block in parse_result["blocks"]
        if block["block_type"] == "table_row" and block.get("row_index") == 1
    }
    chunks = _product_chunks(catalog, heading_by_path, blocks_by_product)
    chunks.extend(_section_chunks(parse_result, heading_by_path))
    chunks.extend(
        _matrix_chunks(
            catalog, blocks_by_id, heading_by_path, header_by_table
        )
    )
    legend = _legend_chunk(parse_result, heading_by_path)
    if legend:
        chunks.append(legend)
    return chunks


def build_chunk_report(
    chunks: list[dict[str, Any]], parse_result: dict[str, Any]
) -> dict[str, Any]:
    block_ids = [block["block_id"] for block in parse_result["blocks"]]
    direct = {
        block_id
        for chunk in chunks
        for block_id in chunk["source_block_ids"]
    }
    structural = {
        block_id
        for chunk in chunks
        for block_id in chunk["heading_block_ids"]
    }
    separators = {
        block["block_id"]
        for block in parse_result["blocks"]
        if block["text"].strip() in SEPARATOR_TEXTS
    }
    uncovered = [
        block_id
        for block_id in block_ids
        if block_id not in direct and block_id not in structural and block_id not in separators
    ]
    char_counts = [chunk["char_count"] for chunk in chunks]
    duplicate_ids = [
        chunk_id
        for chunk_id, count in Counter(chunk["chunk_id"] for chunk in chunks).items()
        if count > 1
    ]
    product_ids = {
        product_id
        for chunk in chunks
        for product_id in chunk["product_ids"]
    }
    profile_ids = {
        chunk["product_ids"][0]
        for chunk in chunks
        if chunk["chunk_type"] == "product_profile"
    }
    spec_ids = {
        chunk["product_ids"][0]
        for chunk in chunks
        if chunk["chunk_type"] == "product_specs"
    }

    warnings: list[str] = []
    if duplicate_ids:
        warnings.append(f"Duplicate chunk ids: {duplicate_ids}")
    if uncovered:
        warnings.append(f"Uncovered blocks: {len(uncovered)}")
    if product_ids - profile_ids:
        warnings.append(f"Products missing profile chunk: {sorted(product_ids - profile_ids)}")
    if product_ids - spec_ids:
        warnings.append(f"Products missing specs chunk: {sorted(product_ids - spec_ids)}")
    if any(not chunk["source_block_ids"] for chunk in chunks):
        warnings.append("Chunks without source blocks found")

    return {
        "source": parse_result["report"]["source"],
        "counts": {
            "chunks": len(chunks),
            "by_type": dict(Counter(chunk["chunk_type"] for chunk in chunks)),
            "unique_chunk_ids": len({chunk["chunk_id"] for chunk in chunks}),
            "products": len(product_ids),
        },
        "char_stats": {
            "min": min(char_counts) if char_counts else 0,
            "max": max(char_counts) if char_counts else 0,
            "avg": round(sum(char_counts) / len(char_counts), 1) if char_counts else 0,
        },
        "coverage": {
            "total_blocks": len(block_ids),
            "directly_referenced": len(direct),
            "structurally_referenced": len(structural),
            "covered": len(set(block_ids) - set(uncovered)),
            "excluded_separators": len(separators),
            "uncovered": uncovered,
        },
        "warnings": warnings,
    }


def render_chunk_preview(
    chunks: list[dict[str, Any]], report: dict[str, Any]
) -> str:
    lines = [
        "# N4 检索语料预览",
        "",
        f"- chunk 总数：{report['counts']['chunks']}",
        f"- 覆盖产品：{report['counts']['products']}",
        f"- 字符数：最小 {report['char_stats']['min']}，"
        f"最大 {report['char_stats']['max']}，平均 {report['char_stats']['avg']}",
        f"- 未覆盖原文块：{len(report['coverage']['uncovered'])}",
        "",
    ]
    for chunk in chunks:
        lines.extend(
            [
                f"## {chunk['chunk_id']}｜{chunk['title']}",
                "",
                f"- 类型：`{chunk['chunk_type']}`",
                f"- 产品：{', '.join(chunk['product_ids']) or '-'}",
                f"- 类别：{', '.join(chunk['category_keys']) or '-'}",
                f"- 来源块：{', '.join(chunk['source_block_ids'])}",
                f"- 字符数：{chunk['char_count']}",
                "",
                "```text",
                chunk["text"],
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def write_chunk_artifacts(
    chunks: list[dict[str, Any]],
    report: dict[str, Any],
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "chunks.jsonl").write_text(
        "".join(json.dumps(chunk, ensure_ascii=False) + "\n" for chunk in chunks),
        encoding="utf-8",
    )
    (output_dir / "chunk_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with (output_dir / "chunks.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "chunk_id",
                "chunk_type",
                "title",
                "product_ids",
                "category_keys",
                "tier_keys",
                "power_types",
                "char_count",
                "source_block_ids",
                "text",
            ],
        )
        writer.writeheader()
        for chunk in chunks:
            writer.writerow(
                {
                    "chunk_id": chunk["chunk_id"],
                    "chunk_type": chunk["chunk_type"],
                    "title": chunk["title"],
                    "product_ids": "|".join(chunk["product_ids"]),
                    "category_keys": "|".join(chunk["category_keys"]),
                    "tier_keys": "|".join(chunk["tier_keys"]),
                    "power_types": "|".join(chunk["power_types"]),
                    "char_count": chunk["char_count"],
                    "source_block_ids": "|".join(chunk["source_block_ids"]),
                    "text": chunk["text"],
                }
            )
    (output_dir / "chunk_preview.md").write_text(
        render_chunk_preview(chunks, report) + "\n",
        encoding="utf-8",
    )
