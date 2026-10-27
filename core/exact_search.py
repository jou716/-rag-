from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from core.db_schema import Product, ProductSpec

FORCE_METRICS = {
    "max_assist",
    "max_shoulder_assist",
    "assist_range",
    "assist",
    "max_hip_assist_per_side",
    "max_knee_assist_per_knee",
}
MASS_METRICS = {
    "weight",
    "system_weight",
    "max_load",
    "recommended_load",
    "recommended_user_weight",
    "max_user_weight",
}
LENGTH_METRICS = {"applicable_height", "recommended_height", "waist_range"}
TIME_METRICS = {"runtime", "don_time"}
PERCENT_METRICS = {
    "relief_efficiency",
    "walking_assist_efficiency",
    "standing_assist_efficiency",
}
COUNT_METRICS = {"dof", "motors", "service_life"}
TEMPERATURE_METRICS = {"operating_temperature"}
TORQUE_METRICS = {"assist_torque"}
BATTERY_METRICS = {"battery"}


def _serialize_spec(spec: ProductSpec) -> dict[str, Any]:
    return {
        "spec_id": spec.spec_id,
        "metric_key": spec.metric_key,
        "metric_label": spec.metric_label,
        "raw_value": spec.raw_value,
        "value_num": float(spec.value_num) if spec.value_num is not None else None,
        "value_min": float(spec.value_min) if spec.value_min is not None else None,
        "value_max": float(spec.value_max) if spec.value_max is not None else None,
        "unit_normalized": spec.unit_normalized,
        "unit_family": spec.unit_family,
        "qualifier": spec.qualifier,
        "scope": spec.scope,
        "source_block_id": spec.source_block_id,
        "quality_flag": spec.quality_flag,
    }


def _serialize_product(
    product: Product, specs: list[ProductSpec]
) -> dict[str, Any]:
    return {
        "product_id": product.product_id,
        "category_key": product.category_key,
        "category_label": product.category_label,
        "tier_key": product.tier_key,
        "tier_label": product.tier_label,
        "power_type": product.power_type,
        "power_type_label": product.power_type_label,
        "product_type_text": product.product_type_text,
        "target_users": product.target_users,
        "applications": product.applications,
        "quality_status": product.quality_status,
        "source_heading_block_id": product.source_heading_block_id,
        "specs": [_serialize_spec(spec) for spec in specs],
    }


def search_products(
    engine: Engine,
    *,
    product_ids: list[str] | None = None,
    category_keys: list[str] | None = None,
    tier_keys: list[str] | None = None,
    power_types: list[str] | None = None,
    quality_status: list[str] | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    statement = select(Product)
    if product_ids:
        statement = statement.where(Product.product_id.in_(product_ids))
    if category_keys:
        statement = statement.where(Product.category_key.in_(category_keys))
    if tier_keys:
        statement = statement.where(Product.tier_key.in_(tier_keys))
    if power_types:
        statement = statement.where(Product.power_type.in_(power_types))
    if quality_status:
        statement = statement.where(Product.quality_status.in_(quality_status))

    with Session(engine) as session:
        products = list(
            session.scalars(
                statement.order_by(Product.product_id).limit(limit)
            ).all()
        )
        if not products:
            return []
        ids = [product.product_id for product in products]
        specs = list(
            session.scalars(
                select(ProductSpec)
                .where(ProductSpec.product_id.in_(ids))
                .order_by(ProductSpec.product_id, ProductSpec.spec_order)
            ).all()
        )

    specs_by_product: dict[str, list[ProductSpec]] = {}
    for spec in specs:
        specs_by_product.setdefault(spec.product_id, []).append(spec)
    return [
        _serialize_product(product, specs_by_product.get(product.product_id, []))
        for product in products
    ]


def get_product(engine: Engine, product_id: str) -> dict[str, Any] | None:
    products = search_products(engine, product_ids=[product_id], limit=1)
    return products[0] if products else None


def _family(metric_key: str) -> str:
    if metric_key in FORCE_METRICS:
        return "force"
    if metric_key in MASS_METRICS:
        return "mass"
    if metric_key in LENGTH_METRICS:
        return "length"
    if metric_key in TIME_METRICS:
        return "time"
    if metric_key in PERCENT_METRICS:
        return "percent"
    if metric_key in COUNT_METRICS:
        return "count"
    if metric_key in TEMPERATURE_METRICS:
        return "temperature"
    if metric_key in TORQUE_METRICS:
        return "torque"
    if metric_key in BATTERY_METRICS:
        return "battery"
    return "native"


def _base_unit(family: str) -> str:
    return {
        "force": "kgf",
        "mass": "kg",
        "length": "cm",
        "time": "h",
        "percent": "%",
        "count": "count",
        "temperature": "°C",
        "torque": "N·m",
        "battery": "Wh",
        "native": "native",
    }[family]


def _convert(value: float | None, unit: str | None, family: str) -> float | None:
    if value is None:
        return None
    normalized = (unit or "").lower()
    if family == "force":
        if normalized in {"kg", "kgf", ""}:
            return value
        if normalized == "n":
            return value / 9.80665
    if family == "mass":
        if normalized in {"kg", ""}:
            return value
        if normalized == "g":
            return value / 1000
    if family == "length":
        if normalized in {"cm", ""}:
            return value
        if normalized == "mm":
            return value / 10
    if family == "time":
        if normalized in {"h", "小时", ""}:
            return value
        if normalized in {"s", "秒"}:
            return value / 3600
    if family in {"percent", "count", "temperature", "torque"}:
        return value
    if family == "battery":
        return value
    return value


def comparable_range(spec: dict[str, Any]) -> dict[str, Any]:
    family = _family(spec["metric_key"])
    unit = spec.get("unit_normalized")
    if spec.get("value_min") is not None or spec.get("value_max") is not None:
        low = _convert(spec.get("value_min"), unit, family)
        high = _convert(spec.get("value_max"), unit, family)
    else:
        low = high = _convert(spec.get("value_num"), unit, family)
    return {
        "low": low,
        "high": high,
        "unit": _base_unit(family) if family != "native" else unit,
        "family": family,
    }


def _matches(
    comparable: dict[str, Any], op: str, target: float
) -> bool:
    low = comparable["low"]
    high = comparable["high"]
    if low is None and high is None:
        return False
    if op == "eq":
        if low is not None and high is not None:
            return low <= target <= high
        return target == (low if low is not None else high)
    if op == "ge":
        return (high if high is not None else low) >= target
    if op == "gt":
        return (high if high is not None else low) > target
    if op == "le":
        return (low if low is not None else high) <= target
    if op == "lt":
        return (low if low is not None else high) < target
    if op == "between":
        return False if low is None or high is None else low <= target <= high
    raise ValueError(f"Unsupported operator: {op}")


def find_products_by_metric(
    engine: Engine,
    *,
    metric_key: str,
    op: str,
    value: float,
    unit: str | None = None,
    category_keys: list[str] | None = None,
    tier_keys: list[str] | None = None,
    power_types: list[str] | None = None,
    quality_status: list[str] | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    family = _family(metric_key)
    target_unit = _base_unit(family) if family != "native" else (unit or "native")
    target = _convert(value, unit or target_unit, family)
    if target is None:
        raise ValueError("Metric value must be numeric")

    products = search_products(
        engine,
        category_keys=category_keys,
        tier_keys=tier_keys,
        power_types=power_types,
        quality_status=quality_status,
        limit=limit,
    )
    results: list[dict[str, Any]] = []
    for product in products:
        for spec in product["specs"]:
            if spec["metric_key"] != metric_key:
                continue
            comparable = comparable_range(spec)
            if not _matches(comparable, op, target):
                continue
            results.append(
                {
                    "product_id": product["product_id"],
                    "category_label": product["category_label"],
                    "tier_label": product["tier_label"],
                    "power_type_label": product["power_type_label"],
                    "quality_status": product["quality_status"],
                    "metric_key": metric_key,
                    "metric_label": spec["metric_label"],
                    "raw_value": spec["raw_value"],
                    "value_num": spec["value_num"],
                    "value_min": spec["value_min"],
                    "value_max": spec["value_max"],
                    "unit_normalized": spec["unit_normalized"],
                    "comparable_low": comparable["low"],
                    "comparable_high": comparable["high"],
                    "comparable_unit": comparable["unit"],
                    "source_block_id": spec["source_block_id"],
                }
            )
    results.sort(
        key=lambda item: (
            item["comparable_high"]
            if item["comparable_high"] is not None
            else item["comparable_low"] or 0
        ),
        reverse=True,
    )
    return results
