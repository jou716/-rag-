from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from app.config import BASE_DIR
from app.db import get_engine
from core.bm25 import load_bm25_index, search_bm25
from core.embeddings import build_embedding_text, embed_query
from core.evidence import DEFAULT_EVIDENCE_LIMIT, build_evidence_bundle
from core.exact_candidates import ExactCandidate, build_exact_candidates
from core.exact_search import search_products
from core.query_analysis import QueryAnalysis, analyze_query
from core.reranker import rerank_logits, sigmoid
from core.vector_store import VectorFilters, search_vectors

DEFAULT_CHANNEL_WEIGHTS = {"exact": 1.6, "bm25": 1.0, "vector": 1.0}
DEFAULT_RRF_K = 60
DEFAULT_RERANK_POOL = 20
DEFAULT_RERANK_WEIGHT = 0.75
PRODUCT_PART_TYPES = ("product_profile", "product_specs")


def _product_card_text(parts: dict[str, dict[str, Any]]) -> str:
    profile = parts.get("product_profile")
    specs = parts.get("product_specs")
    if profile and specs:
        spec_lines = [
            line
            for line in specs["text"].splitlines()
            if not line.startswith(("产品编号：", "产品类别：", "产品层级："))
        ]
        return "\n".join([profile["text"], *spec_lines])
    chunk = profile or specs
    return chunk["text"] if chunk else ""


def build_product_card(
    product_id: str,
    parts: dict[str, dict[str, Any]],
    *,
    primary_chunk_type: str = "product_profile",
    retrieval: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    ordered = [parts[chunk_type] for chunk_type in PRODUCT_PART_TYPES if chunk_type in parts]
    if not ordered:
        return None
    primary = parts.get(primary_chunk_type) or ordered[0]
    quality_statuses = [
        (chunk.get("metadata") or {}).get("quality_status") for chunk in ordered
    ]
    quality_status = (
        "needs_review"
        if "needs_review" in quality_statuses
        else next((status for status in quality_statuses if status), None)
    )
    quality_flags = list(
        dict.fromkeys(
            flag for chunk in ordered for flag in chunk.get("quality_flags") or []
        )
    )
    source_block_ids = list(
        dict.fromkeys(
            block_id
            for chunk in ordered
            for block_id in chunk.get("source_block_ids") or []
        )
    )
    card = {
        "chunk_id": f"card_product_{product_id}",
        "chunk_type": primary["chunk_type"],
        "title": f"{product_id} 产品卡（概览 + 规格）",
        "text": _product_card_text(parts),
        "section_path": primary.get("section_path", []),
        "product_ids": [product_id],
        "category_keys": primary.get("category_keys", []),
        "tier_keys": primary.get("tier_keys", []),
        "power_types": primary.get("power_types", []),
        "quality_status": quality_status,
        "quality_flags": quality_flags,
        "source_block_ids": source_block_ids,
        "card_chunk_ids": [chunk["chunk_id"] for chunk in ordered],
        "rrf_score": 0.0,
        "channel_ranks": {},
        "channel_scores": {},
        "reranker_probability": None,
        "normalized_rrf": None,
        "final_score": 0.0,
    }
    if retrieval:
        for key in (
            "rrf_score",
            "channel_ranks",
            "channel_scores",
            "reranker_probability",
            "normalized_rrf",
            "final_score",
        ):
            card[key] = retrieval.get(key, card[key])
    return card


@lru_cache(maxsize=1)
def load_chunks() -> tuple[dict[str, Any], ...]:
    path = BASE_DIR / "data" / "processed" / "chunks.jsonl"
    return tuple(
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


@lru_cache(maxsize=1)
def load_default_bm25_index() -> dict[str, Any]:
    return load_bm25_index(BASE_DIR / "data" / "indexes" / "bm25_index.json")


@dataclass
class FusedCandidate:
    chunk_id: str
    rrf_score: float = 0.0
    channel_ranks: dict[str, int] = field(default_factory=dict)
    channel_scores: dict[str, float] = field(default_factory=dict)
    reranker_logit: float | None = None
    reranker_probability: float | None = None
    normalized_rrf: float | None = None
    final_score: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "rrf_score": round(self.rrf_score, 8),
            "channel_ranks": self.channel_ranks,
            "channel_scores": {
                channel: round(score, 6)
                for channel, score in self.channel_scores.items()
            },
            "reranker_logit": (
                round(self.reranker_logit, 6)
                if self.reranker_logit is not None
                else None
            ),
            "reranker_probability": (
                round(self.reranker_probability, 6)
                if self.reranker_probability is not None
                else None
            ),
            "normalized_rrf": (
                round(self.normalized_rrf, 6)
                if self.normalized_rrf is not None
                else None
            ),
            "final_score": round(self.final_score, 6),
        }


def reciprocal_rank_fusion(
    channel_results: dict[str, Sequence[dict[str, Any]]],
    weights: dict[str, float] | None = None,
    rrf_k: int = DEFAULT_RRF_K,
) -> dict[str, FusedCandidate]:
    weights = weights or DEFAULT_CHANNEL_WEIGHTS
    fused: dict[str, FusedCandidate] = {}
    for channel, results in channel_results.items():
        weight = weights.get(channel, 1.0)
        for rank, result in enumerate(results, start=1):
            chunk_id = result["chunk_id"]
            candidate = fused.setdefault(chunk_id, FusedCandidate(chunk_id=chunk_id))
            candidate.rrf_score += weight / (rrf_k + rank)
            candidate.channel_ranks[channel] = rank
            candidate.channel_scores[channel] = float(result.get("score", 0.0))
    return fused


def normalize_scores(values: Sequence[float]) -> list[float]:
    if not values:
        return []
    low = min(values)
    high = max(values)
    if high == low:
        return [0.0 for _ in values]
    return [(value - low) / (high - low) for value in values]


def blend_rerank_scores(
    rrf_scores: Sequence[float],
    reranker_probabilities: Sequence[float],
    rerank_weight: float = DEFAULT_RERANK_WEIGHT,
) -> tuple[list[float], list[float]]:
    if len(rrf_scores) != len(reranker_probabilities):
        raise ValueError("RRF and reranker score counts must match")
    normalized_rrf = normalize_scores(rrf_scores)
    final_scores = [
        rerank_weight * rerank_probability
        + (1 - rerank_weight) * normalized_rrf_score
        for rerank_probability, normalized_rrf_score in zip(
            reranker_probabilities, normalized_rrf, strict=True
        )
    ]
    return final_scores, normalized_rrf


def _bm25_filters(analysis: QueryAnalysis) -> dict[str, Any] | None:
    filters: dict[str, Any] = {}
    if analysis.intent in {"fact", "product", "profile", "comparison", "quality"}:
        filters["product_ids"] = list(analysis.product_ids)
    elif analysis.intent == "filter":
        filters["category_keys"] = list(analysis.category_keys)
        filters["tier_keys"] = list(analysis.tier_keys)
        filters["power_types"] = list(analysis.power_types)
    if analysis.chunk_types:
        filters["chunk_types"] = list(analysis.chunk_types)
    return {key: value for key, value in filters.items() if value} or None


def _vector_filters(analysis: QueryAnalysis) -> VectorFilters:
    if analysis.intent in {"fact", "product", "profile", "comparison", "quality"}:
        return VectorFilters(
            product_ids=analysis.product_ids,
            chunk_types=analysis.chunk_types,
        )
    if analysis.intent == "filter":
        return VectorFilters(
            category_keys=analysis.category_keys,
            tier_keys=analysis.tier_keys,
            power_types=analysis.power_types,
            chunk_types=analysis.chunk_types,
        )
    return VectorFilters(chunk_types=analysis.chunk_types)


class HybridRetriever:
    def __init__(
        self,
        *,
        engine: Any | None = None,
        chunks: Sequence[dict[str, Any]] | None = None,
        bm25_index: dict[str, Any] | None = None,
        channel_weights: dict[str, float] | None = None,
        rrf_k: int = DEFAULT_RRF_K,
        rerank_pool: int = DEFAULT_RERANK_POOL,
        rerank_weight: float = DEFAULT_RERANK_WEIGHT,
        enable_reranker: bool = True,
    ) -> None:
        self.engine = engine
        self.chunks = list(chunks or load_chunks())
        self.chunks_by_id = {chunk["chunk_id"]: chunk for chunk in self.chunks}
        self.product_parts: dict[str, dict[str, dict[str, Any]]] = {}
        for chunk in self.chunks:
            if chunk.get("chunk_type") not in PRODUCT_PART_TYPES:
                continue
            for product_id in chunk.get("product_ids") or []:
                self.product_parts.setdefault(product_id, {})[
                    chunk["chunk_type"]
                ] = chunk
        self.bm25_index = bm25_index or load_default_bm25_index()
        self.channel_weights = channel_weights or DEFAULT_CHANNEL_WEIGHTS
        self.rrf_k = rrf_k
        self.rerank_pool = rerank_pool
        self.rerank_weight = rerank_weight
        self.enable_reranker = enable_reranker

    def _get_engine(self) -> Any:
        if self.engine is None:
            self.engine = get_engine()
        return self.engine

    def _matched_products(self, analysis: QueryAnalysis) -> list[dict[str, Any]]:
        if analysis.intent == "filter":
            return search_products(
                self._get_engine(),
                category_keys=list(analysis.category_keys) or None,
                tier_keys=list(analysis.tier_keys) or None,
                power_types=list(analysis.power_types) or None,
            )
        if analysis.product_ids and analysis.intent in {
            "fact",
            "product",
            "profile",
            "comparison",
            "quality",
        }:
            return search_products(
                self._get_engine(),
                product_ids=list(analysis.product_ids),
            )
        return []

    def _exact_channel(
        self, analysis: QueryAnalysis
    ) -> tuple[list[dict[str, Any]], list[ExactCandidate]]:
        matched_products = self._matched_products(analysis)
        exact_candidates = build_exact_candidates(analysis, self.chunks, matched_products)
        results = [
            {
                "chunk_id": candidate.chunk_id,
                "score": 1.0 / candidate.rank,
                "reason": candidate.reason,
            }
            for candidate in exact_candidates
        ]
        return results, exact_candidates

    def _bm25_channel(
        self, query: str, analysis: QueryAnalysis, limit: int
    ) -> list[dict[str, Any]]:
        results = search_bm25(
            self.bm25_index,
            query,
            top_k=limit,
            filters=_bm25_filters(analysis),
        )
        return [dict(result) for result in results]

    def _vector_channel(
        self, query: str, analysis: QueryAnalysis, limit: int
    ) -> list[dict[str, Any]]:
        return [
            result.as_dict()
            for result in search_vectors(
                embed_query(query),
                top_k=limit,
                filters=_vector_filters(analysis),
            )
        ]

    def _hydrate(self, candidate: FusedCandidate) -> dict[str, Any]:
        chunk = self.chunks_by_id[candidate.chunk_id]
        return candidate.as_dict() | {
            "chunk_type": chunk["chunk_type"],
            "title": chunk["title"],
            "text": chunk["text"],
            "section_path": chunk.get("section_path", []),
            "product_ids": chunk.get("product_ids", []),
            "category_keys": chunk.get("category_keys", []),
            "tier_keys": chunk.get("tier_keys", []),
            "power_types": chunk.get("power_types", []),
            "quality_status": (chunk.get("metadata") or {}).get("quality_status"),
            "quality_flags": chunk.get("quality_flags", []),
            "source_block_ids": chunk.get("source_block_ids", []),
        }

    def _product_card(
        self,
        product_id: str,
        analysis: QueryAnalysis,
        retrieval: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        parts = self.product_parts.get(product_id)
        if not parts:
            return None
        primary_chunk_type = (
            "product_specs"
            if analysis.intent in {"fact", "comparison"}
            else "product_profile"
        )
        return build_product_card(
            product_id,
            parts,
            primary_chunk_type=primary_chunk_type,
            retrieval=retrieval,
        )

    def _expand_product_cards(
        self,
        results: Sequence[dict[str, Any]],
        analysis: QueryAnalysis,
    ) -> list[dict[str, Any]]:
        expanded: list[dict[str, Any]] = []
        used: set[str] = set()
        carded_products: set[str] = set()
        for result in results:
            product_ids = list(result.get("product_ids") or [])
            if (
                result.get("chunk_type") in PRODUCT_PART_TYPES
                and len(product_ids) == 1
                and product_ids[0] not in carded_products
            ):
                product_id = product_ids[0]
                card = self._product_card(product_id, analysis, retrieval=result)
                if card is not None:
                    expanded.append(card)
                    carded_products.add(product_id)
                    used.update(card["card_chunk_ids"])
                    continue
            if result["chunk_id"] not in used:
                expanded.append(result)
                used.add(result["chunk_id"])
        return expanded

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        mode: str = "hybrid_rerank",
        channel_limit: int = 20,
    ) -> list[dict[str, Any]]:
        analysis = analyze_query(query)
        exact_results: list[dict[str, Any]] = []
        exact_details: list[ExactCandidate] = []
        bm25_results: list[dict[str, Any]] = []
        vector_results: list[dict[str, Any]] = []

        if mode == "exact":
            exact_results, exact_details = self._exact_channel(analysis)
        elif mode == "bm25":
            bm25_results = self._bm25_channel(query, analysis, channel_limit)
        elif mode == "vector":
            vector_results = self._vector_channel(query, analysis, channel_limit)
        elif mode in {"hybrid", "hybrid_rerank"}:
            exact_results, exact_details = self._exact_channel(analysis)
            bm25_results = self._bm25_channel(query, analysis, channel_limit)
            vector_results = self._vector_channel(query, analysis, channel_limit)
        else:
            raise ValueError(f"Unknown retrieval mode: {mode}")

        channel_results = {
            "exact": exact_results,
            "bm25": bm25_results,
            "vector": vector_results,
        }
        channel_results = {key: value for key, value in channel_results.items() if value}
        fused = reciprocal_rank_fusion(
            channel_results,
            weights=self.channel_weights,
            rrf_k=self.rrf_k,
        )
        candidates = sorted(
            fused.values(), key=lambda candidate: (-candidate.rrf_score, candidate.chunk_id)
        )

        if mode == "hybrid_rerank" and candidates:
            rerank_candidates = candidates[: self.rerank_pool]
            documents = [
                build_embedding_text(self.chunks_by_id[candidate.chunk_id])
                for candidate in rerank_candidates
            ]
            logits = rerank_logits(query, documents)
            probabilities = [sigmoid(logit) for logit in logits]
            final_scores, normalized_rrf = blend_rerank_scores(
                [candidate.rrf_score for candidate in rerank_candidates],
                probabilities,
                rerank_weight=self.rerank_weight,
            )
            for candidate, logit, probability, final_score, normalized in zip(
                rerank_candidates,
                logits,
                probabilities,
                final_scores,
                normalized_rrf,
                strict=True,
            ):
                candidate.reranker_logit = logit
                candidate.reranker_probability = probability
                candidate.normalized_rrf = normalized
                candidate.final_score = final_score
            remaining = candidates[self.rerank_pool :]
            for candidate in remaining:
                candidate.final_score = 0.0
            candidates = sorted(
                candidates,
                key=lambda candidate: (
                    -candidate.final_score,
                    -candidate.rrf_score,
                    candidate.chunk_id,
                ),
            )
        else:
            for candidate in candidates:
                candidate.final_score = candidate.rrf_score

        results = [self._hydrate(candidate) for candidate in candidates[:top_k]]
        if mode == "exact":
            reasons = {candidate.chunk_id: candidate.reason for candidate in exact_details}
            for result in results:
                result["exact_reason"] = reasons.get(result["chunk_id"])
        return results

    def search_with_evidence(
        self,
        query: str,
        *,
        top_k: int = DEFAULT_EVIDENCE_LIMIT,
        evidence_top_k: int = DEFAULT_EVIDENCE_LIMIT,
        mode: str = "hybrid_rerank",
        channel_limit: int = 20,
    ) -> dict[str, Any]:
        if top_k < 1 or evidence_top_k < 1:
            raise ValueError("top_k and evidence_top_k must be at least 1")
        analysis = analyze_query(query)
        retrieval_limit = max(top_k, evidence_top_k)
        if analysis.intent == "filter":
            retrieval_limit = max(retrieval_limit, channel_limit)
        results = self.search(
            query,
            top_k=retrieval_limit,
            mode=mode,
            channel_limit=channel_limit,
        )
        evidence_results = self._spread_by_product(results, analysis)[:evidence_top_k]
        return {
            "query": query,
            "analysis": analysis.as_dict(),
            "retrieval_mode": mode,
            "results": results[:top_k],
            "evidence": build_evidence_bundle(evidence_results),
        }

    def _spread_by_product(
        self,
        results: Sequence[dict[str, Any]],
        analysis: QueryAnalysis,
    ) -> list[dict[str, Any]]:
        if analysis.intent != "filter":
            return self._expand_product_cards(results, analysis)
        ordered: list[dict[str, Any]] = []
        used: set[str] = set()
        for result in results:
            if result.get("chunk_type") in {"matrix_category", "matrix_tier"}:
                ordered.append(result)
                used.add(result["chunk_id"])
                break
        for product in self._matched_products(analysis):
            product_id = product["product_id"]
            product_results = [
                result
                for result in results
                if product_id in (result.get("product_ids") or [])
                and result.get("chunk_type") in PRODUCT_PART_TYPES
            ]
            best_result = max(
                product_results,
                key=lambda result: float(result.get("final_score") or 0.0),
                default=None,
            )
            card = self._product_card(product_id, analysis, retrieval=best_result)
            if card is not None:
                ordered.append(card)
                used.update(card["card_chunk_ids"])
                continue
            candidates = [
                result
                for result in product_results
                if result["chunk_id"] not in used
            ]
            if not candidates:
                continue
            candidates.sort(
                key=lambda result: (
                    0 if result.get("chunk_type") == "product_specs" else 1,
                    -float(result.get("final_score") or 0.0),
                )
            )
            ordered.append(candidates[0])
            used.add(candidates[0]["chunk_id"])
        for result in results:
            if result["chunk_id"] not in used:
                ordered.append(result)
                used.add(result["chunk_id"])
        return ordered
