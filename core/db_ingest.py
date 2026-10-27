from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from core.db_schema import (
    Base,
    CategoryMatrix,
    DataQualityIssue,
    Product,
    ProductSpec,
    ScenarioMatrix,
    SourceBlock,
    TierMatrix,
)


def create_schema(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def load_catalog(
    engine: Engine,
    parse_result: dict[str, Any],
    catalog: dict[str, Any],
) -> dict[str, int]:
    source_hash = parse_result["report"]["source"]["sha256"]

    with Session(engine) as session:
        with session.begin():
            for model in (
                DataQualityIssue,
                ProductSpec,
                ScenarioMatrix,
                TierMatrix,
                CategoryMatrix,
                Product,
                SourceBlock,
            ):
                session.execute(delete(model))

            session.add_all(
                [
                    SourceBlock(
                        block_id=block["block_id"],
                        source_hash=source_hash,
                        block_type=block["block_type"],
                        order_index=block["order"],
                        section_path=block["section_path"],
                        product_id=block.get("product_id"),
                        text=block["text"],
                        raw_text=block["raw_text"],
                        heading_level=block.get("heading_level"),
                        table_id=block.get("table_id"),
                        row_index=block.get("row_index"),
                        source_json=block["source"],
                    )
                    for block in parse_result["blocks"]
                ]
            )
            session.flush()

            session.add_all(
                [
                    Product(
                        product_id=product["product_id"],
                        category_key=product["category_key"],
                        category_label=product["category_label"],
                        tier_key=product["tier_key"],
                        tier_label=product["tier_label"],
                        power_type=product["power_type"],
                        power_type_label=product["power_type_label"],
                        product_type_text=product["product_type_text"],
                        target_users=product["target_users"],
                        applications=product["applications"],
                        source_heading_block_id=product["source_heading_block_id"],
                        quality_status=product["quality_status"],
                    )
                    for product in catalog["products"]
                ]
            )
            session.flush()

            session.add_all(
                [
                    ProductSpec(
                        spec_id=spec["spec_id"],
                        product_id=spec["product_id"],
                        spec_order=spec["spec_order"],
                        metric_key=spec["metric_key"],
                        metric_label=spec["metric_label"],
                        raw_value=spec["raw_value"],
                        value_text=spec["value_text"],
                        value_num=spec["value_num"],
                        value_min=spec["value_min"],
                        value_max=spec["value_max"],
                        unit_raw=spec["unit_raw"],
                        unit_normalized=spec["unit_normalized"],
                        unit_family=spec["unit_family"],
                        qualifier=spec["qualifier"],
                        scope=spec["scope"],
                        value_n=spec["value_n"],
                        metadata_json=spec["metadata_json"],
                        source_block_id=spec["source_block_id"],
                        quality_flag=spec["quality_flag"],
                    )
                    for product in catalog["products"]
                    for spec in product["specs"]
                ]
            )
            session.flush()

            session.add_all(
                [
                    ScenarioMatrix(**row)
                    for row in catalog["matrices"]["scenario_matrix"]
                ]
            )
            session.add_all(
                [TierMatrix(**row) for row in catalog["matrices"]["tier_matrix"]]
            )
            session.add_all(
                [
                    CategoryMatrix(**row)
                    for row in catalog["matrices"]["category_matrix"]
                ]
            )
            session.add_all(
                [
                    DataQualityIssue(**issue)
                    for issue in catalog["quality_report"]["issues"]
                ]
            )

    return table_counts(engine)


def table_counts(engine: Engine) -> dict[str, int]:
    models = {
        "source_blocks": SourceBlock,
        "products": Product,
        "product_specs": ProductSpec,
        "scenario_matrix": ScenarioMatrix,
        "tier_matrix": TierMatrix,
        "category_matrix": CategoryMatrix,
        "data_quality_issues": DataQualityIssue,
    }
    with Session(engine) as session:
        return {
            name: session.scalar(select(func.count()).select_from(model)) or 0
            for name, model in models.items()
        }
