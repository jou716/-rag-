from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SourceBlock(Base):
    __tablename__ = "source_blocks"

    block_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_hash: Mapped[str] = mapped_column(String(64), index=True)
    block_type: Mapped[str] = mapped_column(String(32), index=True)
    order_index: Mapped[int] = mapped_column(Integer, index=True)
    section_path: Mapped[list[Any]] = mapped_column(JSON)
    product_id: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    text: Mapped[str] = mapped_column(Text)
    raw_text: Mapped[str] = mapped_column(Text)
    heading_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    table_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    row_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_json: Mapped[dict[str, Any]] = mapped_column(JSON)


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        Index("idx_product_filter", "category_key", "tier_key", "power_type"),
    )

    product_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    category_key: Mapped[str] = mapped_column(String(32), index=True)
    category_label: Mapped[str] = mapped_column(String(64))
    tier_key: Mapped[str] = mapped_column(String(16), index=True)
    tier_label: Mapped[str] = mapped_column(String(64))
    power_type: Mapped[str] = mapped_column(String(32), index=True)
    power_type_label: Mapped[str] = mapped_column(String(32))
    product_type_text: Mapped[str] = mapped_column(Text)
    target_users: Mapped[str] = mapped_column(Text)
    applications: Mapped[str] = mapped_column(Text)
    source_heading_block_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("source_blocks.block_id")
    )
    quality_status: Mapped[str] = mapped_column(String(16), index=True)


class ProductSpec(Base):
    __tablename__ = "product_specs"
    __table_args__ = (
        Index("idx_spec_product_metric", "product_id", "metric_key"),
        Index("idx_spec_metric_unit", "metric_key", "unit_normalized"),
    )

    spec_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    product_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("products.product_id"), index=True
    )
    spec_order: Mapped[int] = mapped_column(Integer)
    metric_key: Mapped[str] = mapped_column(String(64), index=True)
    metric_label: Mapped[str] = mapped_column(String(128))
    raw_value: Mapped[str] = mapped_column(Text)
    value_text: Mapped[str] = mapped_column(Text)
    value_num: Mapped[float | None] = mapped_column(Numeric(14, 4), nullable=True)
    value_min: Mapped[float | None] = mapped_column(Numeric(14, 4), nullable=True)
    value_max: Mapped[float | None] = mapped_column(Numeric(14, 4), nullable=True)
    unit_raw: Mapped[str | None] = mapped_column(String(32), nullable=True)
    unit_normalized: Mapped[str | None] = mapped_column(String(32), nullable=True)
    unit_family: Mapped[str | None] = mapped_column(String(32), nullable=True)
    qualifier: Mapped[str | None] = mapped_column(String(16), nullable=True)
    scope: Mapped[str | None] = mapped_column(String(32), nullable=True)
    value_n: Mapped[float | None] = mapped_column(Numeric(14, 4), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    source_block_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("source_blocks.block_id"), index=True
    )
    quality_flag: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ScenarioMatrix(Base):
    __tablename__ = "scenario_matrix"

    scenario_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    target_user_group: Mapped[str] = mapped_column(Text)
    scenarios: Mapped[str] = mapped_column(Text)
    pain_points: Mapped[str] = mapped_column(Text)
    core_actions: Mapped[str] = mapped_column(Text)
    injury_parts: Mapped[str] = mapped_column(Text)
    preferred_exo_type: Mapped[str] = mapped_column(Text)
    recommended_product_ids_raw: Mapped[str] = mapped_column(Text)
    recommended_product_ids_json: Mapped[list[Any]] = mapped_column(JSON)
    source_block_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("source_blocks.block_id")
    )


class TierMatrix(Base):
    __tablename__ = "tier_matrix"

    tier_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tier_label: Mapped[str] = mapped_column(Text)
    market_position: Mapped[str] = mapped_column(Text)
    product_forms: Mapped[str] = mapped_column(Text)
    scenarios: Mapped[str] = mapped_column(Text)
    product_ids_raw: Mapped[str] = mapped_column(Text)
    product_ids_json: Mapped[list[Any]] = mapped_column(JSON)
    source_block_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("source_blocks.block_id")
    )


class CategoryMatrix(Base):
    __tablename__ = "category_matrix"

    category_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    category_label: Mapped[str] = mapped_column(Text)
    core_function: Mapped[str] = mapped_column(Text)
    scenarios: Mapped[str] = mapped_column(Text)
    product_ids_raw: Mapped[str] = mapped_column(Text)
    product_ids_json: Mapped[list[Any]] = mapped_column(JSON)
    source_block_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("source_blocks.block_id")
    )


class DataQualityIssue(Base):
    __tablename__ = "data_quality_issues"

    issue_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    issue_type: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(16), index=True)
    product_id: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    field_name: Mapped[str | None] = mapped_column(String(96), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    source_block_ids: Mapped[list[Any]] = mapped_column(JSON)
    details_json: Mapped[dict[str, Any]] = mapped_column(JSON)
