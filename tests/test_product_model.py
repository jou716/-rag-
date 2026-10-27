import pytest

from app.config import settings
from core.catalog import build_catalog
from core.docx_parser import parse_docx
from core.measurements import parse_measurement
from core.quality import render_quality_markdown

requires_docx = pytest.mark.skipif(
    not settings.source_doc_path.is_file(),
    reason="source DOCX is not included in the public repository",
)


def build_test_catalog() -> dict:
    return build_catalog(parse_docx(settings.source_doc_path))


def test_measurement_ranges_and_units() -> None:
    range_value = parse_measurement("50–100 kg", "mass")
    assert range_value["value_min"] == 50
    assert range_value["value_max"] == 100
    assert range_value["unit_normalized"] == "kg"

    battery = parse_measurement("92Wh（36V 锂离子）", "battery")
    assert battery["value_num"] == 92
    assert battery["unit_normalized"] == "Wh"
    assert battery["metadata_json"]["voltage_v"] == 36


@requires_docx
def test_catalog_has_16_products_and_specs() -> None:
    catalog = build_test_catalog()
    assert len(catalog["products"]) == 16
    assert all(product["spec_count"] > 0 for product in catalog["products"])


@requires_docx
def test_c615_key_fields() -> None:
    catalog = build_test_catalog()
    product = next(
        item for item in catalog["products"] if item["product_id"] == "C615"
    )
    specs = {spec["metric_key"]: spec for spec in product["specs"]}

    assert product["category_key"] == "upper_limb"
    assert product["tier_key"] == "high"
    assert product["power_type"] == "electric"
    assert specs["weight"]["value_num"] == 3.9
    assert specs["battery"]["value_num"] == 92
    assert specs["max_assist"]["value_num"] == 20
    assert specs["runtime"]["value_min"] == 6
    assert specs["runtime"]["value_max"] == 8


@requires_docx
def test_known_quality_issues_are_detected() -> None:
    catalog = build_test_catalog()
    issue_types = {issue["issue_type"] for issue in catalog["quality_report"]["issues"]}

    assert "missing_tier" in issue_types
    assert "incomplete_specs" in issue_types
    assert "tier_matrix_category_conflict" in issue_types
    assert "assist_payload_inconsistency" in issue_types
    assert "height_field_conflict" in issue_types
    assert "assist_unit_inconsistency" in issue_types
    assert "category_boundary" in issue_types


@requires_docx
def test_c656_is_marked_needs_review() -> None:
    catalog = build_test_catalog()
    product = next(
        item for item in catalog["products"] if item["product_id"] == "C656"
    )
    assert product["quality_status"] == "needs_review"


@requires_docx
def test_quality_markdown_contains_review_summary() -> None:
    catalog = build_test_catalog()
    markdown = render_quality_markdown(catalog)

    assert "# N3 数据质量报告" in markdown
    assert "问题数：14（高危 6、中危 7、低危 1）" in markdown
    assert "| C655 | 腰背外骨骼" in markdown
    assert "## 问题明细" in markdown
