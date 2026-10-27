from __future__ import annotations

import re
from typing import Any


def parse_product_refs(raw: str) -> list[dict[str, str | None]]:
    return [
        {"product_id": match.group(1), "power_marker": match.group(2)}
        for match in re.finditer(r"(C\d{3})(?:\s*[（(]([电被])[）)])?", raw)
    ]


def parse_tier_segments(raw: str) -> list[dict[str, str | None]]:
    category_map = {
        "上肢": "上肢外骨骼",
        "腰背": "腰背外骨骼",
        "负重": "负重下肢外骨骼",
    }
    matches = list(re.finditer(r"(上肢|腰背|负重)\s*[：:]", raw))
    records: list[dict[str, str | None]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        segment = raw[start:end].strip(" 、，;；")
        category_label = category_map[match.group(1)]
        for ref in parse_product_refs(segment):
            records.append(
                {
                    "product_id": ref["product_id"],
                    "power_marker": ref["power_marker"],
                    "category_label": category_label,
                }
            )
    return records


def build_matrices(tables: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    scenario_matrix: list[dict[str, Any]] = []
    tier_matrix: list[dict[str, Any]] = []
    category_matrix: list[dict[str, Any]] = []

    for table in tables:
        headers = table["headers"]
        data_rows = [row for row in table["rows"] if row["row_index"] > 1]

        if "目标用户群" in headers:
            for row in data_rows:
                values = row["values"]
                raw_ids = values.get("推荐产品ID", "")
                scenario_matrix.append(
                    {
                        "scenario_id": row["row_block_id"],
                        "target_user_group": values.get("目标用户群", ""),
                        "scenarios": values.get("典型应用场景", ""),
                        "pain_points": values.get("核心痛点", ""),
                        "core_actions": values.get("核心动作", ""),
                        "injury_parts": values.get("易伤部位", ""),
                        "preferred_exo_type": values.get("首选外骨骼类型", ""),
                        "recommended_product_ids_raw": raw_ids,
                        "recommended_product_ids_json": parse_product_refs(raw_ids),
                        "source_block_id": row["row_block_id"],
                    }
                )

        elif "产品层级" in headers:
            for row in data_rows:
                cells = row["cells"]
                raw_ids = cells[-1]["text"]
                tier_matrix.append(
                    {
                        "tier_id": row["row_block_id"],
                        "tier_label": cells[0]["text"],
                        "market_position": cells[1]["text"],
                        "product_forms": cells[2]["text"],
                        "scenarios": cells[3]["text"],
                        "product_ids_raw": raw_ids,
                        "product_ids_json": parse_tier_segments(raw_ids),
                        "source_block_id": row["row_block_id"],
                    }
                )

        elif "类别" in headers:
            for row in data_rows:
                cells = row["cells"]
                raw_ids = cells[-1]["text"]
                category_matrix.append(
                    {
                        "category_id": row["row_block_id"],
                        "category_label": cells[0]["text"],
                        "core_function": cells[1]["text"],
                        "scenarios": cells[2]["text"],
                        "product_ids_raw": raw_ids,
                        "product_ids_json": parse_product_refs(raw_ids),
                        "source_block_id": row["row_block_id"],
                    }
                )

    return {
        "scenario_matrix": scenario_matrix,
        "tier_matrix": tier_matrix,
        "category_matrix": category_matrix,
    }
