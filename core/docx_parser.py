from __future__ import annotations

import hashlib
import csv
import json
import re
from pathlib import Path
from typing import Any, Iterator

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

HEADING_RE = re.compile(r"^(#{1,4})\s+(.+?)\s*$")
PRODUCT_ID_RE = re.compile(r"^C\d{3}$")
WHITESPACE_RE = re.compile(r"\s+")


def clean_text(text: str) -> str:
    return WHITESPACE_RE.sub(" ", text.replace("\u00a0", " ")).strip()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_body_items(document: Document) -> Iterator[Paragraph | Table]:
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield Table(child, document)


def current_product_id(section_path: list[str]) -> str | None:
    for value in reversed(section_path):
        if PRODUCT_ID_RE.match(value):
            return value
    return None


def parse_docx(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Source document not found: {path}")

    document = Document(path)
    doc_hash = file_sha256(path)[:8]
    body = document.element.body

    blocks: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    sections: list[dict[str, Any]] = []
    products: list[dict[str, Any]] = []
    warnings: list[str] = []

    heading_stack: list[tuple[int, str]] = []
    paragraph_total = 0
    paragraph_nonempty = 0
    table_index = 0
    order = 0

    for item in iter_body_items(document):
        if isinstance(item, Paragraph):
            paragraph_total += 1
            raw_text = item.text
            text = clean_text(raw_text)
            if not text:
                continue

            paragraph_nonempty += 1
            heading_match = HEADING_RE.match(text)
            if heading_match:
                level = len(heading_match.group(1))
                heading_text = clean_text(heading_match.group(2))
                heading_stack = [
                    (stack_level, stack_text)
                    for stack_level, stack_text in heading_stack
                    if stack_level < level
                ]
                heading_stack.append((level, heading_text))
                section_path = [value for _, value in heading_stack]

                order += 1
                block_id = f"blk_{doc_hash}_p{paragraph_total:04d}"
                product_id = (
                    heading_text
                    if level == 4 and PRODUCT_ID_RE.match(heading_text)
                    else None
                )
                block = {
                    "block_id": block_id,
                    "order": order,
                    "block_type": "heading",
                    "text": heading_text,
                    "raw_text": raw_text,
                    "section_path": section_path,
                    "heading_level": level,
                    "product_id": product_id,
                    "source": {
                        "paragraph_index": paragraph_total,
                        "word_style": item.style.name if item.style else "",
                    },
                }
                blocks.append(block)
                sections.append(
                    {
                        "block_id": block_id,
                        "order": order,
                        "level": level,
                        "title": heading_text,
                        "section_path": section_path,
                        "product_id": product_id,
                    }
                )
                if product_id:
                    products.append(
                        {
                            "product_id": product_id,
                            "heading_block_id": block_id,
                            "order": order,
                            "section_path": section_path,
                            "category_section": (
                                section_path[-2] if len(section_path) >= 2 else ""
                            ),
                        }
                    )
                continue

            order += 1
            block_id = f"blk_{doc_hash}_p{paragraph_total:04d}"
            section_path = [value for _, value in heading_stack]
            block_type = "list_item" if text.startswith(("- ", "* ")) else "paragraph"
            blocks.append(
                {
                    "block_id": block_id,
                    "order": order,
                    "block_type": block_type,
                    "text": text,
                    "raw_text": raw_text,
                    "section_path": section_path,
                    "heading_level": None,
                    "product_id": current_product_id(section_path),
                    "source": {
                        "paragraph_index": paragraph_total,
                        "word_style": item.style.name if item.style else "",
                    },
                }
            )
            continue

        if isinstance(item, Table):
            table_index += 1
            table_id = f"tbl_{doc_hash}_t{table_index:02d}"
            section_path = [value for _, value in heading_stack]
            source_rows: list[dict[str, Any]] = []

            for row_index, row in enumerate(item.rows, start=1):
                cells: list[dict[str, Any]] = []
                for col_index, cell in enumerate(row.cells, start=1):
                    cell_text = clean_text(cell.text)
                    cells.append(
                        {
                            "cell_id": f"{table_id}_r{row_index:02d}_c{col_index:02d}",
                            "row_index": row_index,
                            "col_index": col_index,
                            "text": cell_text,
                        }
                    )
                source_rows.append({"row_index": row_index, "cells": cells})

            headers = (
                [cell["text"] for cell in source_rows[0]["cells"]]
                if source_rows
                else []
            )

            table_rows: list[dict[str, Any]] = []
            for row in source_rows:
                row_index = row["row_index"]
                cells = row["cells"]
                row_block_id = f"{table_id}_r{row_index:02d}"
                row_text = " | ".join(cell["text"] for cell in cells)
                values = {
                    header: cell["text"]
                    for header, cell in zip(headers, cells, strict=False)
                }
                row_record = {
                    "row_block_id": row_block_id,
                    "row_index": row_index,
                    "cells": cells,
                    "text": row_text,
                    "values": values,
                }
                table_rows.append(row_record)

                order += 1
                blocks.append(
                    {
                        "block_id": row_block_id,
                        "order": order,
                        "block_type": "table_row",
                        "text": row_text,
                        "raw_text": row_text,
                        "section_path": section_path,
                        "heading_level": None,
                        "product_id": None,
                        "table_id": table_id,
                        "row_index": row_index,
                        "headers": headers,
                        "cells": cells,
                        "values": values,
                        "source": {
                            "table_index": table_index,
                            "table_id": table_id,
                            "row_index": row_index,
                        },
                    }
                )

            if table_rows and len(table_rows[0]["cells"]) != len(headers):
                warnings.append(
                    f"Table {table_index} header/cell count mismatch"
                )
            empty_cells = sum(
                1
                for row in table_rows
                for cell in row["cells"]
                if not cell["text"]
            )
            if empty_cells:
                warnings.append(
                    f"Table {table_index} contains {empty_cells} empty cells"
                )

            tables.append(
                {
                    "table_id": table_id,
                    "section_path": section_path,
                    "n_rows": len(table_rows),
                    "n_cols": len(headers),
                    "headers": headers,
                    "rows": table_rows,
                }
            )

    heading_count = sum(1 for block in blocks if block["block_type"] == "heading")
    table_row_count = sum(1 for block in blocks if block["block_type"] == "table_row")
    table_cell_count = sum(
        len(row["cells"]) for table in tables for row in table["rows"]
    )

    if len(products) != 16:
        warnings.append(f"Expected 16 products, found {len(products)}")
    if len(tables) != 3:
        warnings.append(f"Expected 3 tables, found {len(tables)}")
    if table_row_count != 14:
        warnings.append(f"Expected 14 table rows, found {table_row_count}")
    if table_cell_count != 78:
        warnings.append(f"Expected 78 table cells, found {table_cell_count}")

    report = {
        "source": {
            "path": str(path.resolve()),
            "sha256": file_sha256(path),
            "size_bytes": path.stat().st_size,
        },
        "counts": {
            "top_level_elements": len(list(body.iterchildren())),
            "paragraphs_total": paragraph_total,
            "paragraphs_nonempty": paragraph_nonempty,
            "headings": heading_count,
            "tables": len(tables),
            "table_rows": table_row_count,
            "table_cells": table_cell_count,
            "blocks_total": len(blocks),
            "products": len(products),
        },
        "sections": sections,
        "products": products,
        "table_summaries": [
            {
                "table_id": table["table_id"],
                "section_path": table["section_path"],
                "n_rows": table["n_rows"],
                "n_cols": table["n_cols"],
                "headers": table["headers"],
            }
            for table in tables
        ],
        "warnings": warnings,
    }
    return {"blocks": blocks, "tables": tables, "report": report}


def write_parse_artifacts(result: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    blocks_path = output_dir / "document_blocks.jsonl"
    tables_path = output_dir / "tables.json"
    report_path = output_dir / "parse_report.json"
    block_csv_path = output_dir / "block_inventory.csv"
    product_csv_path = output_dir / "products_raw.csv"

    with blocks_path.open("w", encoding="utf-8") as handle:
        for block in result["blocks"]:
            handle.write(json.dumps(block, ensure_ascii=False) + "\n")

    tables_path.write_text(
        json.dumps(result["tables"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(
        json.dumps(result["report"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with block_csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "block_id",
                "order",
                "block_type",
                "product_id",
                "heading_level",
                "section_path",
                "text",
            ],
        )
        writer.writeheader()
        for block in result["blocks"]:
            writer.writerow(
                {
                    "block_id": block["block_id"],
                    "order": block["order"],
                    "block_type": block["block_type"],
                    "product_id": block.get("product_id") or "",
                    "heading_level": block.get("heading_level") or "",
                    "section_path": " > ".join(block["section_path"]),
                    "text": block["text"],
                }
            )

    with product_csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "product_id",
                "category_section",
                "heading_block_id",
                "section_path",
            ],
        )
        writer.writeheader()
        for product in result["report"]["products"]:
            writer.writerow(
                {
                    "product_id": product["product_id"],
                    "category_section": product["category_section"],
                    "heading_block_id": product["heading_block_id"],
                    "section_path": " > ".join(product["section_path"]),
                }
            )
