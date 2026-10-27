from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from core.matrices import build_matrices
from core.product_extract import build_products
from core.quality import build_quality_issues, render_quality_markdown

REQUIRED_PRODUCT_FIELDS = ["tier", "product_type", "target_users", "applications"]


def build_catalog(parse_result: dict[str, Any]) -> dict[str, Any]:
    products, all_specs, incomplete_sources = build_products(parse_result)
    matrices = build_matrices(parse_result["tables"])
    issues = build_quality_issues(
        products, all_specs, matrices, incomplete_sources
    )
    quality_report = {
        "source": parse_result["report"]["source"],
        "summary": {
            "products": len(products),
            "specs": len(all_specs),
            "issues": len(issues),
            "by_severity": dict(Counter(issue["severity"] for issue in issues)),
            "by_type": dict(Counter(issue["issue_type"] for issue in issues)),
            "products_needing_review": sorted(
                {
                    issue["product_id"]
                    for issue in issues
                    if issue["product_id"]
                }
            ),
        },
        "issues": issues,
    }
    return {
        "source": parse_result["report"]["source"],
        "products": products,
        "matrices": matrices,
        "quality_report": quality_report,
    }


def write_catalog_artifacts(catalog: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "matrices.json").write_text(
        json.dumps(catalog["matrices"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "quality_report.json").write_text(
        json.dumps(catalog["quality_report"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "quality_report.md").write_text(
        render_quality_markdown(catalog) + "\n",
        encoding="utf-8",
    )

    issues_by_product: dict[str, list[str]] = defaultdict(list)
    for issue in catalog["quality_report"]["issues"]:
        if issue["product_id"]:
            issues_by_product[issue["product_id"]].append(issue["issue_type"])

    with (output_dir / "product_review.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "product_id",
                "category_label",
                "tier_label",
                "power_type",
                "spec_count",
                "missing_fields",
                "quality_status",
                "quality_flags",
                "source_heading_block_id",
            ],
        )
        writer.writeheader()
        for product in catalog["products"]:
            present_keys = {spec["metric_key"] for spec in product["specs"]}
            missing_fields = [
                field_name
                for field_name in REQUIRED_PRODUCT_FIELDS
                if field_name not in present_keys
            ]
            writer.writerow(
                {
                    "product_id": product["product_id"],
                    "category_label": product["category_label"],
                    "tier_label": product["tier_label"],
                    "power_type": product["power_type"],
                    "spec_count": product["spec_count"],
                    "missing_fields": ",".join(missing_fields),
                    "quality_status": product["quality_status"],
                    "quality_flags": ",".join(
                        sorted(set(issues_by_product.get(product["product_id"], [])))
                    ),
                    "source_heading_block_id": product["source_heading_block_id"],
                }
            )
