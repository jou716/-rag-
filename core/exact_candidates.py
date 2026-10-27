from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from core.query_analysis import QueryAnalysis
from core.text_analysis import normalize_text


@dataclass(frozen=True)
class ExactCandidate:
    chunk_id: str
    rank: int
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "rank": self.rank,
            "reason": self.reason,
        }


def _chunks_by_product(chunks: Sequence[dict[str, Any]]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for chunk in chunks:
        if chunk["chunk_type"] not in {"product_profile", "product_specs"}:
            continue
        for product_id in chunk.get("product_ids", []):
            result.setdefault(product_id, {})[chunk["chunk_type"]] = chunk["chunk_id"]
    return result


def _append(
    candidates: list[ExactCandidate], chunk_id: str | None, reason: str
) -> None:
    if not chunk_id or any(candidate.chunk_id == chunk_id for candidate in candidates):
        return
    candidates.append(
        ExactCandidate(chunk_id=chunk_id, rank=len(candidates) + 1, reason=reason)
    )


def _matching_filter_matrix(
    chunks: Sequence[dict[str, Any]], analysis: QueryAnalysis
) -> str | None:
    matrix_type = "matrix_tier" if analysis.tier_keys else "matrix_category"
    for chunk in chunks:
        if chunk["chunk_type"] != matrix_type:
            continue
        if analysis.tier_keys and set(chunk.get("tier_keys", [])) & set(analysis.tier_keys):
            return chunk["chunk_id"]
        if analysis.category_keys and set(chunk.get("category_keys", [])) & set(
            analysis.category_keys
        ):
            return chunk["chunk_id"]
    return None


def _matching_scenario(
    chunks: Sequence[dict[str, Any]], normalized_query: str
) -> str | None:
    best: tuple[float, str] | None = None
    for chunk in chunks:
        if chunk["chunk_type"] != "matrix_scenario":
            continue
        title = chunk["title"].split("｜", 1)[-1]
        target = normalize_text(title)
        if target and target in normalized_query:
            return chunk["chunk_id"]

        query_bigrams = {
            normalized_query[index : index + 2]
            for index in range(max(0, len(normalized_query) - 1))
        }
        target_bigrams = {
            target[index : index + 2] for index in range(max(0, len(target) - 1))
        }
        overlap = len(query_bigrams & target_bigrams) / max(1, len(target_bigrams))
        if best is None or overlap > best[0]:
            best = (overlap, chunk["chunk_id"])
    return best[1] if best and best[0] >= 0.25 else None


def _direct_product_chunks(
    analysis: QueryAnalysis,
    product_chunks: dict[str, dict[str, str]],
) -> list[tuple[str, str]]:
    ordered: list[tuple[str, str]] = []
    profile_first = any(
        term in analysis.normalized
        for term in ("属于", "哪一类", "是什么产品", "适合什么", "面向哪些")
    )
    for product_id in analysis.product_ids:
        chunks = product_chunks.get(product_id, {})
        if analysis.intent in {"comparison", "fact"}:
            types = ("product_specs",)
        elif analysis.intent == "profile":
            types = ("product_profile",)
        elif analysis.intent == "quality":
            types = (
                ("product_profile", "product_specs")
                if profile_first
                else ("product_specs", "product_profile")
            )
        else:
            types = ("product_specs", "product_profile")
        for chunk_type in types:
            if chunk_type in chunks:
                ordered.append((chunks[chunk_type], f"{product_id}:{chunk_type}"))
    return ordered


def build_exact_candidates(
    analysis: QueryAnalysis,
    chunks: Sequence[dict[str, Any]],
    matched_products: Sequence[dict[str, Any]] = (),
) -> list[ExactCandidate]:
    candidates: list[ExactCandidate] = []

    if analysis.intent == "scenario":
        _append(
            candidates,
            _matching_scenario(chunks, analysis.normalized),
            "scenario_matrix",
        )
        return candidates

    if analysis.intent == "filter":
        _append(
            candidates,
            _matching_filter_matrix(chunks, analysis),
            "filter_matrix",
        )
        product_chunks = _chunks_by_product(chunks)
        matched_ids = [product["product_id"] for product in matched_products]
        for product_id in matched_ids:
            _append(
                candidates,
                product_chunks.get(product_id, {}).get("product_profile"),
                f"mysql_filter:{product_id}",
            )
        return candidates

    product_chunks = _chunks_by_product(chunks)
    for chunk_id, reason in _direct_product_chunks(analysis, product_chunks):
        _append(candidates, chunk_id, reason)
    return candidates
