import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import BASE_DIR

ALLOWED_TYPES = {
    "fact",
    "profile",
    "filter",
    "scenario",
    "comparison",
    "section",
    "quality",
    "unanswerable",
}
ALLOWED_ROUTES = {"exact_sql", "semantic", "hybrid", "unanswerable"}
REQUIRED_FIELDS = {
    "question_id",
    "question",
    "question_type",
    "route_hint",
    "answerable",
    "expected_product_ids",
    "expected_metric_keys",
    "expected_chunk_ids",
    "expected_source_block_ids",
    "reference_answer",
    "difficulty",
}


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> None:
    eval_path = BASE_DIR / "eval" / "questions.jsonl"
    questions = load_jsonl(eval_path)
    chunks = load_jsonl(BASE_DIR / "data" / "processed" / "chunks.jsonl")
    blocks = load_jsonl(BASE_DIR / "data" / "processed" / "document_blocks.jsonl")
    catalog = json.loads(
        (BASE_DIR / "data" / "processed" / "catalog.json").read_text(
            encoding="utf-8"
        )
    )

    chunk_ids = {chunk["chunk_id"] for chunk in chunks}
    block_ids = {block["block_id"] for block in blocks}
    product_ids = {product["product_id"] for product in catalog["products"]}

    errors: list[str] = []
    question_ids = [question.get("question_id") for question in questions]
    duplicate_ids = [
        question_id
        for question_id, count in Counter(question_ids).items()
        if count > 1
    ]
    if duplicate_ids:
        errors.append(f"Duplicate question ids: {duplicate_ids}")

    for question in questions:
        question_id = question.get("question_id", "<missing>")
        missing_fields = REQUIRED_FIELDS - set(question)
        if missing_fields:
            errors.append(f"{question_id}: missing fields {sorted(missing_fields)}")
            continue
        if question["question_type"] not in ALLOWED_TYPES:
            errors.append(f"{question_id}: unknown question_type")
        if question["route_hint"] not in ALLOWED_ROUTES:
            errors.append(f"{question_id}: unknown route_hint")
        unknown_chunks = set(question["expected_chunk_ids"]) - chunk_ids
        if unknown_chunks:
            errors.append(f"{question_id}: unknown chunks {sorted(unknown_chunks)}")
        unknown_blocks = set(question["expected_source_block_ids"]) - block_ids
        if unknown_blocks:
            errors.append(f"{question_id}: unknown blocks {sorted(unknown_blocks)}")
        unknown_products = set(question["expected_product_ids"]) - product_ids
        if unknown_products:
            errors.append(f"{question_id}: unknown products {sorted(unknown_products)}")
        if question["answerable"]:
            if not question["reference_answer"].strip():
                errors.append(f"{question_id}: answerable but empty reference_answer")
            if not question["expected_chunk_ids"]:
                errors.append(f"{question_id}: answerable but no expected chunks")
            if not question["expected_source_block_ids"]:
                errors.append(f"{question_id}: answerable but no expected sources")
            if question["route_hint"] == "unanswerable":
                errors.append(f"{question_id}: answerable but route is unanswerable")
        else:
            if question["expected_chunk_ids"] or question["expected_source_block_ids"]:
                errors.append(f"{question_id}: unanswerable but has evidence")
            if question["route_hint"] != "unanswerable":
                errors.append(f"{question_id}: unanswerable must use unanswerable route")

    report = {
        "questions": len(questions),
        "answerable": sum(1 for question in questions if question["answerable"]),
        "unanswerable": sum(
            1 for question in questions if not question["answerable"]
        ),
        "by_type": dict(Counter(question["question_type"] for question in questions)),
        "by_route": dict(Counter(question["route_hint"] for question in questions)),
        "errors": errors,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
