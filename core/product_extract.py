from __future__ import annotations

from collections import defaultdict
from typing import Any

from core.measurements import (
    infer_power_type,
    normalize_category,
    normalize_tier,
    parse_field_item,
)


def build_products(parse_result: dict[str, Any]) -> tuple[
    list[dict[str, Any]], list[dict[str, Any]], dict[str, str]
]:
    blocks = parse_result["blocks"]
    by_product: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for block in blocks:
        if block.get("product_id"):
            by_product[block["product_id"]].append(block)

    products: list[dict[str, Any]] = []
    all_specs: list[dict[str, Any]] = []
    incomplete_sources: dict[str, str] = {}

    for product_entry in parse_result["report"]["products"]:
        product_id = product_entry["product_id"]
        product_blocks = by_product[product_id]
        heading = next(
            block for block in product_blocks if block["block_type"] == "heading"
        )

        specs: list[dict[str, Any]] = []
        tier_raw: str | None = None
        product_type_text: str | None = None
        target_users: str | None = None
        applications: str | None = None
        power_source_raw: str | None = None

        for block in product_blocks:
            if block["block_type"] == "heading":
                continue
            parsed = parse_field_item(block)
            if not parsed:
                continue
            if parsed["kind"] == "container":
                if parsed.get("note") and "未完整" in parsed["note"]:
                    incomplete_sources[product_id] = parsed["source_block_id"]
                continue

            spec_order = len(specs) + 1
            spec = {
                "spec_id": f"spec_{product_id}_{spec_order:02d}",
                "product_id": product_id,
                "spec_order": spec_order,
                **parsed,
            }
            specs.append(spec)
            all_specs.append(spec)

            if spec["metric_key"] == "tier" and not tier_raw:
                tier_raw = spec["value_text"]
            elif spec["metric_key"] == "product_type":
                if not product_type_text or len(spec["value_text"]) > len(product_type_text):
                    product_type_text = spec["value_text"]
            elif spec["metric_key"] == "target_users" and not target_users:
                target_users = spec["value_text"]
            elif spec["metric_key"] == "applications" and not applications:
                applications = spec["value_text"]
            elif spec["metric_key"] == "power_source" and not power_source_raw:
                power_source_raw = spec["value_text"]

        category_key, category_label = normalize_category(
            product_entry["category_section"]
        )
        tier_key, tier_label = normalize_tier(tier_raw)
        power_key, power_label = infer_power_type(power_source_raw, product_type_text)

        products.append(
            {
                "product_id": product_id,
                "category_key": category_key,
                "category_label": category_label,
                "tier_key": tier_key,
                "tier_label": tier_label,
                "tier_raw": tier_raw,
                "power_type": power_key,
                "power_type_label": power_label,
                "power_source_raw": power_source_raw,
                "product_type_text": product_type_text or "",
                "target_users": target_users or "",
                "applications": applications or "",
                "source_heading_block_id": heading["block_id"],
                "section_path": product_entry["section_path"],
                "spec_count": len(specs),
                "quality_status": "ok",
                "specs": specs,
            }
        )

    return products, all_specs, incomplete_sources
