from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from core.text_analysis import tokenize

FIELD_NAMES = ["title", "text", "section", "tags"]
FIELD_WEIGHTS = {"title": 3.0, "text": 1.0, "section": 1.5, "tags": 2.0}
FIELD_B = {"title": 0.5, "text": 0.75, "section": 0.6, "tags": 0.5}
K1 = 1.2


def _chunk_fields(chunk: dict[str, Any]) -> dict[str, str]:
    tags = " ".join(
        chunk.get("product_ids", [])
        + chunk.get("category_keys", [])
        + chunk.get("tier_keys", [])
        + chunk.get("power_types", [])
        + chunk.get("quality_flags", [])
        + [chunk.get("chunk_type", "")]
        + [chunk.get("metadata", {}).get("quality_status", "")]
    )
    return {
        "title": chunk["title"],
        "text": chunk["text"],
        "section": " ".join(chunk.get("section_path", [])),
        "tags": tags,
    }


def build_bm25_index(
    chunks: list[dict[str, Any]], source_hash: str | None = None
) -> dict[str, Any]:
    postings: dict[str, dict[str, list[int]]] = defaultdict(
        lambda: defaultdict(lambda: [0, 0, 0, 0])
    )
    doc_freq: Counter[str] = Counter()
    totals = {field: 0 for field in FIELD_NAMES}
    documents: dict[str, dict[str, Any]] = {}

    for chunk in chunks:
        chunk_id = chunk["chunk_id"]
        fields = _chunk_fields(chunk)
        field_lengths = {field: len(tokenize(fields[field])) for field in FIELD_NAMES}
        for field in FIELD_NAMES:
            totals[field] += field_lengths[field]

        seen_terms: set[str] = set()
        for field_index, field in enumerate(FIELD_NAMES):
            counts = Counter(tokenize(fields[field]))
            for term, count in counts.items():
                postings[term][chunk_id][field_index] = count
                seen_terms.add(term)
        for term in seen_terms:
            doc_freq[term] += 1

        documents[chunk_id] = {
            "chunk_id": chunk_id,
            "chunk_type": chunk["chunk_type"],
            "title": chunk["title"],
            "product_ids": chunk.get("product_ids", []),
            "category_keys": chunk.get("category_keys", []),
            "tier_keys": chunk.get("tier_keys", []),
            "power_types": chunk.get("power_types", []),
            "quality_status": chunk.get("metadata", {}).get("quality_status"),
            "source_block_ids": chunk.get("source_block_ids", []),
            "text": chunk["text"],
            "field_lengths": field_lengths,
        }

    count = len(chunks)
    return {
        "version": 1,
        "source_hash": source_hash,
        "chunk_count": count,
        "config": {
            "k1": K1,
            "field_weights": FIELD_WEIGHTS,
            "field_b": FIELD_B,
        },
        "avg_field_lengths": {
            field: round(totals[field] / count, 4) if count else 0.0
            for field in FIELD_NAMES
        },
        "documents": documents,
        "postings": {
            term: {chunk_id: tfs for chunk_id, tfs in chunk_postings.items()}
            for term, chunk_postings in postings.items()
        },
        "doc_freq": dict(doc_freq),
    }


def _matches_filters(document: dict[str, Any], filters: dict[str, Any] | None) -> bool:
    if not filters:
        return True
    for key in ("category_keys", "tier_keys", "power_types"):
        wanted = filters.get(key)
        if wanted and not (set(wanted) & set(document.get(key, []))):
            return False
    wanted_products = filters.get("product_ids")
    if wanted_products and not (set(wanted_products) & set(document.get("product_ids", []))):
        return False
    wanted_types = filters.get("chunk_types")
    if wanted_types and document.get("chunk_type") not in wanted_types:
        return False
    wanted_quality = filters.get("quality_status")
    if wanted_quality and document.get("quality_status") not in wanted_quality:
        return False
    return True


def search_bm25(
    index: dict[str, Any],
    query: str,
    top_k: int = 10,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    query_terms = sorted(set(tokenize(query)))
    if not query_terms or not index["chunk_count"]:
        return []

    allowed_ids = {
        chunk_id
        for chunk_id, document in index["documents"].items()
        if _matches_filters(document, filters)
    }
    if not allowed_ids:
        return []

    scores: dict[str, float] = defaultdict(float)
    matched: dict[str, set[str]] = defaultdict(set)
    total = index["chunk_count"]

    for term in query_terms:
        term_postings = index["postings"].get(term)
        if not term_postings:
            continue
        df = index["doc_freq"][term]
        idf = math.log(1 + (total - df + 0.5) / (df + 0.5))
        for chunk_id, tfs in term_postings.items():
            if chunk_id not in allowed_ids:
                continue
            document = index["documents"][chunk_id]
            field_lengths = document["field_lengths"]
            norm_tf = 0.0
            for field_index, field in enumerate(FIELD_NAMES):
                tf = tfs[field_index]
                if not tf:
                    continue
                avg_length = index["avg_field_lengths"][field] or 1.0
                denominator = (
                    1 - FIELD_B[field]
                    + FIELD_B[field] * field_lengths[field] / avg_length
                )
                norm_tf += FIELD_WEIGHTS[field] * tf / denominator
            if norm_tf <= 0:
                continue
            scores[chunk_id] += idf * norm_tf * (K1 + 1) / (norm_tf + K1)
            matched[chunk_id].add(term)

    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    results: list[dict[str, Any]] = []
    for chunk_id, score in ranked[:top_k]:
        document = index["documents"][chunk_id]
        results.append(
            {
                "chunk_id": chunk_id,
                "score": round(score, 6),
                "title": document["title"],
                "chunk_type": document["chunk_type"],
                "product_ids": document["product_ids"],
                "source_block_ids": document["source_block_ids"],
                "quality_status": document["quality_status"],
                "matched_terms": sorted(
                    term
                    for term in matched[chunk_id]
                    if len(term) > 1 or term.isdigit()
                ),
                "snippet": document["text"][:220].replace("\n", " / "),
            }
        )
    return results


def save_bm25_index(index: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(index, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def load_bm25_index(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
