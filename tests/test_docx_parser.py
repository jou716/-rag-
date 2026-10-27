import pytest

from app.config import settings
from core.docx_parser import clean_text, parse_docx

requires_docx = pytest.mark.skipif(
    not settings.source_doc_path.is_file(),
    reason="source DOCX is not included in the public repository",
)


def test_clean_text_normalizes_whitespace() -> None:
    assert clean_text("  C615\n  电池  ") == "C615 电池"


@requires_docx
def test_parser_counts_products_tables_and_cells() -> None:
    result = parse_docx(settings.source_doc_path)
    counts = result["report"]["counts"]

    assert counts["products"] == 16
    assert counts["tables"] == 3
    assert counts["table_rows"] == 14
    assert counts["table_cells"] == 78
    assert counts["headings"] >= 29
    assert counts["paragraphs_nonempty"] == 257


@requires_docx
def test_product_sections_are_traceable() -> None:
    result = parse_docx(settings.source_doc_path)
    product = next(
        item for item in result["report"]["products"] if item["product_id"] == "C615"
    )
    assert "6.1 上肢外骨骼" in product["section_path"]
    assert product["heading_block_id"]


@requires_docx
def test_table_rows_have_headers_and_cell_ids() -> None:
    result = parse_docx(settings.source_doc_path)
    table = result["tables"][0]

    assert table["n_cols"] == 7
    assert table["headers"][0] == "目标用户群"
    assert table["rows"][1]["cells"][0]["cell_id"].endswith("r02_c01")


@requires_docx
def test_block_ids_are_deterministic() -> None:
    first = parse_docx(settings.source_doc_path)
    second = parse_docx(settings.source_doc_path)

    assert [block["block_id"] for block in first["blocks"]] == [
        block["block_id"] for block in second["blocks"]
    ]
