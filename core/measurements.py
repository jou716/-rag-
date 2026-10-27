from __future__ import annotations

import re
from typing import Any

BOLD_FIELD_RE = re.compile(
    r"^\*\*(?P<label>[^*]+?)\*\*(?:（(?P<note>[^）]+)）)?[：:]\s*(?P<value>.*)$"
)
PLAIN_FIELD_RE = re.compile(r"^(?P<label>[^：:]+?)[：:]\s*(?P<value>.*)$")

NUMBER = r"-?\d+(?:,\d{3})*(?:\.\d+)?"
UNIT = r"(?:%|kgf|kg|g|N·m|N|Wh|mAh|V|cm|mm|h|小时|秒|s|°C|℃|次|个|档)"
RANGE_RE = re.compile(
    rf"(?P<a>{NUMBER})\s*(?P<u1>{UNIT})?\s*(?:~|–|—|-|至)\s*"
    rf"(?P<b>{NUMBER})\s*(?P<u2>{UNIT})?"
)
SINGLE_RE = re.compile(rf"(?P<a>{NUMBER})\s*(?P<u>{UNIT})?")

CATEGORY_DEFS = {
    "上肢": ("upper_limb", "上肢外骨骼"),
    "腰背": ("waist_back", "腰背外骨骼"),
    "下肢": ("lower_limb_load", "负重下肢外骨骼"),
}

TIER_DEFS = {
    "入门": ("entry", "入门级｜基础防护"),
    "中端": ("mid", "中端｜均衡性能"),
    "高端": ("high", "高端｜先进智能"),
}

METRIC_DEFS: dict[str, tuple[str, str]] = {
    "产品层级": ("tier", "text"),
    "类型": ("product_type", "text"),
    "目标用户": ("target_users", "text"),
    "应用场景": ("applications", "text"),
    "净重": ("weight", "mass"),
    "单体重量": ("weight", "mass"),
    "系统总重": ("system_weight", "mass"),
    "自由度": ("dof", "count"),
    "动力源": ("power_source", "text"),
    "电池": ("battery", "battery"),
    "电池规格": ("battery", "battery"),
    "最大手臂助力": ("max_assist", "force_or_mass"),
    "最大肩部助力": ("max_shoulder_assist", "force_or_mass"),
    "最大助力": ("max_assist", "force_or_mass"),
    "助力范围": ("assist_range", "force_or_mass"),
    "最大负载": ("max_load", "mass"),
    "推荐负载": ("recommended_load", "mass"),
    "助力": ("assist", "force_or_mass"),
    "助力扭矩": ("assist_torque", "torque"),
    "工作温度": ("operating_temperature", "temperature"),
    "续航": ("runtime", "time"),
    "电池续航": ("runtime", "time"),
    "推荐体重": ("recommended_user_weight", "mass"),
    "推荐用户体重": ("recommended_user_weight", "mass"),
    "最大用户体重": ("max_user_weight", "mass"),
    "减载效率": ("relief_efficiency", "percent"),
    "行走助力效率": ("walking_assist_efficiency", "percent"),
    "站立助力效率": ("standing_assist_efficiency", "percent"),
    "推荐身高": ("recommended_height", "length"),
    "推荐用户身高": ("recommended_height", "length"),
    "适用身高范围": ("applicable_height", "length"),
    "尺寸/适用身高": ("applicable_height", "length"),
    "尺寸": ("dimensions", "dimension"),
    "电机": ("motors", "count"),
    "防水": ("ip_rating", "text"),
    "腰围": ("waist_range", "length"),
    "穿脱时间": ("don_time", "time"),
    "易损件寿命": ("service_life", "count"),
    "材料": ("materials", "text"),
    "支撑方式": ("support_type", "text"),
    "特性": ("feature", "text"),
    "调节方式": ("adjustment", "text"),
    "每侧髋最大": ("max_hip_assist_per_side", "force_or_mass"),
    "每膝最大": ("max_knee_assist_per_knee", "force_or_mass"),
    "其他": ("other", "text"),
}

NUMERIC_KINDS = {
    "mass",
    "force_or_mass",
    "length",
    "time",
    "percent",
    "count",
    "temperature",
    "torque",
    "battery",
    "dimension",
}

UNIT_NORMALIZATION = {
    "kg": "kg",
    "kgf": "kgf",
    "g": "g",
    "N": "N",
    "N·m": "N·m",
    "Wh": "Wh",
    "mAh": "mAh",
    "V": "V",
    "cm": "cm",
    "mm": "mm",
    "h": "h",
    "小时": "h",
    "秒": "s",
    "s": "s",
    "°C": "°C",
    "℃": "°C",
    "%": "%",
    "次": "count",
    "个": "count",
    "档": "count",
}

UNIT_FAMILY = {
    "kg": "mass",
    "g": "mass",
    "kgf": "force",
    "N": "force",
    "N·m": "torque",
    "Wh": "energy",
    "mAh": "charge",
    "V": "voltage",
    "cm": "length",
    "mm": "length",
    "h": "time",
    "s": "time",
    "°C": "temperature",
    "%": "percent",
    "count": "count",
}


def normalize_category(section: str) -> tuple[str, str]:
    for marker, definition in CATEGORY_DEFS.items():
        if marker in section:
            return definition
    return ("unknown", "未知类别")


def normalize_tier(raw: str | None) -> tuple[str, str]:
    if not raw:
        return ("unknown", "")
    for marker, definition in TIER_DEFS.items():
        if marker in raw:
            return definition
    return ("unknown", raw)


def infer_power_type(
    power_source: str | None, product_type: str | None
) -> tuple[str, str]:
    text = " ".join(value for value in (power_source, product_type) if value)
    if "被动" in text:
        return ("passive", "被动")
    if "推车" in text:
        return ("electric_cart", "电动推车联动")
    if "电动" in text or "主动" in text or "动力" in text:
        return ("electric", "电动/动力")
    return ("unknown", "未知")


def detect_scope(raw: str) -> str | None:
    if "每臂" in raw:
        return "per_arm"
    if "每侧髋" in raw:
        return "per_side_hip"
    if "每膝" in raw:
        return "per_knee"
    if "含电池" in raw:
        return "including_battery"
    if "仅限车主" in raw:
        return "owner_only"
    return None


def detect_qualifier(raw: str) -> str | None:
    if any(marker in raw for marker in ("≤", "不超过", "最多")):
        return "lte"
    if any(marker in raw for marker in ("≥", "以上", "至少")):
        return "gte"
    if any(marker in raw for marker in ("约", "≈")):
        return "approx"
    return None


def parse_number(raw: str | None) -> float | None:
    if not raw:
        return None
    return float(raw.replace(",", ""))


def normalize_unit(raw: str | None) -> str | None:
    if not raw:
        return None
    return UNIT_NORMALIZATION.get(raw, raw)


def unit_family(unit: str | None) -> str | None:
    if not unit:
        return None
    return UNIT_FAMILY.get(unit)


def empty_measurement() -> dict[str, Any]:
    return {
        "value_num": None,
        "value_min": None,
        "value_max": None,
        "unit_raw": None,
        "unit_normalized": None,
        "unit_family": None,
        "qualifier": None,
        "value_n": None,
        "metadata_json": {},
    }


def parse_measurement(raw: str, kind: str) -> dict[str, Any]:
    result = empty_measurement()
    text = raw.strip()
    if not text:
        return result

    result["qualifier"] = detect_qualifier(text)

    if kind == "battery":
        match = re.search(r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>Wh|mAh)", text, re.I)
        if match:
            unit = match.group("unit")
            result["value_num"] = float(match.group("value"))
            result["unit_raw"] = unit
            result["unit_normalized"] = normalize_unit(unit)
            result["unit_family"] = unit_family(result["unit_normalized"])
        voltage = re.search(r"(?P<value>\d+(?:\.\d+)?)\s*V\b", text)
        if voltage:
            result["metadata_json"]["voltage_v"] = float(voltage.group("value"))
        if "锂离子" in text:
            result["metadata_json"]["chemistry"] = "锂离子"

    elif kind == "torque":
        match = re.search(r"最大\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>N·m)", text)
        if not match:
            match = SINGLE_RE.search(text)
        if match:
            value = match.groupdict().get("value") or match.groupdict().get("a")
            unit = match.groupdict().get("unit") or match.groupdict().get("u")
            result["value_num"] = parse_number(value)
            result["unit_raw"] = unit
            result["unit_normalized"] = normalize_unit(unit)
            result["unit_family"] = unit_family(result["unit_normalized"])
        levels = re.search(r"(?P<value>\d+)\s*档", text)
        if levels:
            result["metadata_json"]["levels"] = int(levels.group("value"))

    elif kind == "dimension":
        numbers = [float(value) for value in re.findall(r"\d+(?:\.\d+)?", text)]
        if numbers:
            result["metadata_json"]["dimensions_mm"] = numbers
            result["unit_raw"] = "mm"
            result["unit_normalized"] = "mm"
            result["unit_family"] = "length"

    else:
        main_text = re.sub(r"[（(][^）)]*[）)]", " ", text)
        range_match = RANGE_RE.search(main_text)
        if range_match:
            result["value_min"] = parse_number(range_match.group("a"))
            result["value_max"] = parse_number(range_match.group("b"))
            unit = range_match.group("u1") or range_match.group("u2")
            result["unit_raw"] = unit
            result["unit_normalized"] = normalize_unit(unit)
            result["unit_family"] = unit_family(result["unit_normalized"])
        else:
            single_match = SINGLE_RE.search(main_text)
            if single_match:
                result["value_num"] = parse_number(single_match.group("a"))
                unit = single_match.group("u")
                result["unit_raw"] = unit
                result["unit_normalized"] = normalize_unit(unit)
                result["unit_family"] = unit_family(result["unit_normalized"])

    if result["unit_normalized"] == "kgf" and result["value_num"] is not None:
        result["value_n"] = result["value_num"] * 9.80665
    elif result["unit_normalized"] == "N" and result["value_num"] is not None:
        result["value_n"] = result["value_num"]

    secondary = re.search(r"助力负载[：:]\s*([^）)]+)", text)
    if secondary:
        secondary_raw = secondary.group(1).strip()
        parsed_secondary = parse_measurement(secondary_raw, "force_or_mass")
        result["metadata_json"].update(
            {
                "secondary_range": secondary_raw,
                "secondary_min": parsed_secondary["value_min"],
                "secondary_max": parsed_secondary["value_max"],
                "secondary_unit": parsed_secondary["unit_normalized"],
            }
        )
    if "含电池" in text:
        result["metadata_json"]["includes_battery"] = True
    if "仅限车主" in text:
        result["metadata_json"]["owner_only"] = True

    return result


def parse_field_item(block: dict[str, Any]) -> dict[str, Any] | None:
    text = block["text"].strip()
    if not text.startswith("- "):
        return None
    body = text[2:].strip()
    if not body or body in {"---", "—"}:
        return None

    note = None
    match = BOLD_FIELD_RE.match(body)
    if match:
        label = match.group("label").strip()
        note = match.group("note")
        value = match.group("value").strip()
    else:
        match = PLAIN_FIELD_RE.match(body)
        if match:
            label = match.group("label").strip()
            value = match.group("value").strip()
        elif re.match(r"^\d+\s*秒快速穿脱$", body):
            label = "穿脱时间"
            value = body
        elif body.startswith("每侧髋最大"):
            label = "每侧髋最大"
            value = body[len("每侧髋最大") :].strip()
        elif body.startswith("每膝最大"):
            label = "每膝最大"
            value = body[len("每膝最大") :].strip()
        elif body == "线性支撑力":
            label = "支撑方式"
            value = body
        elif body.startswith("碳纤维结构"):
            label = "材料"
            value = body
        elif body.startswith("被动机械助力"):
            label = "特性"
            value = body
        elif body.startswith("单扣同步调节"):
            label = "调节方式"
            value = body
        else:
            label = "其他"
            value = body

    if label == "规格":
        return {"kind": "container", "note": note, "source_block_id": block["block_id"]}

    metric_key, metric_kind = METRIC_DEFS.get(label, ("other", "text"))
    measurement = parse_measurement(value, metric_kind)
    quality_flag = None
    if metric_key == "other":
        quality_flag = "unmapped_metric"
    elif metric_kind in NUMERIC_KINDS:
        has_value = (
            measurement["value_num"] is not None
            or measurement["value_min"] is not None
            or measurement["value_max"] is not None
            or bool(measurement["metadata_json"].get("dimensions_mm"))
        )
        if not has_value:
            quality_flag = "numeric_parse_failed"

    return {
        "kind": "spec",
        "metric_key": metric_key,
        "metric_label": label,
        "raw_value": value,
        "value_text": value,
        "value_num": measurement["value_num"],
        "value_min": measurement["value_min"],
        "value_max": measurement["value_max"],
        "unit_raw": measurement["unit_raw"],
        "unit_normalized": measurement["unit_normalized"],
        "unit_family": measurement["unit_family"],
        "qualifier": measurement["qualifier"],
        "scope": detect_scope(value),
        "value_n": measurement["value_n"],
        "metadata_json": measurement["metadata_json"],
        "source_block_id": block["block_id"],
        "quality_flag": quality_flag,
    }
