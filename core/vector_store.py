from __future__ import annotations

import json
import time
import uuid
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from qdrant_client import QdrantClient, models

from app.config import BASE_DIR

COLLECTION_NAME = "exo_chunks"
DEFAULT_QDRANT_PATH = BASE_DIR / "data" / "indexes" / "qdrant"
POINT_NAMESPACE = uuid.UUID("63dbb30c-1d5a-4f5b-9f52-39b7ee1b3b2c")
PAYLOAD_INDEX_FIELDS = (
    "chunk_type",
    "product_ids",
    "category_keys",
    "tier_keys",
    "power_types",
    "quality_status",
)


@dataclass(frozen=True)
class VectorFilters:
    product_ids: tuple[str, ...] = ()
    category_keys: tuple[str, ...] = ()
    tier_keys: tuple[str, ...] = ()
    power_types: tuple[str, ...] = ()
    chunk_types: tuple[str, ...] = ()
    quality_status: tuple[str, ...] = ()

    def to_qdrant_filter(self) -> models.Filter | None:
        conditions: list[models.FieldCondition] = []
        for key, values in (
            ("product_ids", self.product_ids),
            ("category_keys", self.category_keys),
            ("tier_keys", self.tier_keys),
            ("power_types", self.power_types),
            ("chunk_type", self.chunk_types),
            ("quality_status", self.quality_status),
        ):
            if values:
                conditions.append(
                    models.FieldCondition(
                        key=key,
                        match=models.MatchAny(any=list(values)),
                    )
                )
        return models.Filter(must=conditions) if conditions else None


@dataclass
class VectorSearchResult:
    rank: int
    score: float
    chunk_id: str
    chunk_type: str
    title: str
    text: str
    product_ids: list[str] = field(default_factory=list)
    category_keys: list[str] = field(default_factory=list)
    tier_keys: list[str] = field(default_factory=list)
    power_types: list[str] = field(default_factory=list)
    quality_status: str | None = None
    source_block_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "score": round(self.score, 6),
            "chunk_id": self.chunk_id,
            "chunk_type": self.chunk_type,
            "title": self.title,
            "product_ids": self.product_ids,
            "category_keys": self.category_keys,
            "tier_keys": self.tier_keys,
            "power_types": self.power_types,
            "quality_status": self.quality_status,
            "source_block_ids": self.source_block_ids,
            "text": self.text,
        }


def point_id_for_chunk(chunk_id: str) -> str:
    return str(uuid.uuid5(POINT_NAMESPACE, chunk_id))


def build_payload(chunk: dict[str, Any]) -> dict[str, Any]:
    metadata = chunk.get("metadata") or {}
    return {
        "chunk_id": chunk["chunk_id"],
        "chunk_type": chunk["chunk_type"],
        "title": chunk["title"],
        "text": chunk["text"],
        "section_path": chunk.get("section_path", []),
        "product_ids": chunk.get("product_ids", []),
        "category_keys": chunk.get("category_keys", []),
        "tier_keys": chunk.get("tier_keys", []),
        "power_types": chunk.get("power_types", []),
        "quality_status": metadata.get("quality_status"),
        "quality_flags": chunk.get("quality_flags", []),
        "spec_ids": chunk.get("spec_ids", []),
        "metric_keys": chunk.get("metric_keys", []),
        "source_block_ids": chunk.get("source_block_ids", []),
        "heading_block_ids": chunk.get("heading_block_ids", []),
    }


def open_client(path: Path | str = DEFAULT_QDRANT_PATH) -> QdrantClient:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(5):
        try:
            return QdrantClient(path=str(path))
        except RuntimeError as exc:
            if "already accessed by another instance" not in str(exc) or attempt == 4:
                raise
            time.sleep(0.2 * (attempt + 1))
    raise RuntimeError(f"Unable to open Qdrant local storage: {path}")


def recreate_collection(
    client: QdrantClient,
    vector_size: int,
    collection_name: str = COLLECTION_NAME,
) -> None:
    if client.collection_exists(collection_name):
        client.delete_collection(collection_name)
    client.create_collection(
        collection_name=collection_name,
        vectors_config=models.VectorParams(
            size=vector_size,
            distance=models.Distance.COSINE,
        ),
    )
    for field_name in PAYLOAD_INDEX_FIELDS:
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="Payload indexes have no effect in the local Qdrant.*",
                category=UserWarning,
            )
            client.create_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                field_schema=models.PayloadSchemaType.KEYWORD,
            )


def upsert_chunks(
    client: QdrantClient,
    chunks: Sequence[dict[str, Any]],
    vectors: Sequence[Sequence[float]],
    collection_name: str = COLLECTION_NAME,
    batch_size: int = 64,
) -> int:
    if len(chunks) != len(vectors):
        raise ValueError("chunks and vectors must have the same length")
    if not chunks:
        return 0

    dimension = len(vectors[0])
    if any(len(vector) != dimension for vector in vectors):
        raise ValueError("All vectors must have the same dimension")

    points = [
        models.PointStruct(
            id=point_id_for_chunk(chunk["chunk_id"]),
            vector=list(vector),
            payload=build_payload(chunk),
        )
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]
    for start in range(0, len(points), batch_size):
        client.upsert(
            collection_name=collection_name,
            points=points[start : start + batch_size],
            wait=True,
        )
    return len(points)


def build_vector_index(
    chunks: Sequence[dict[str, Any]],
    vectors: Sequence[Sequence[float]],
    index_path: Path | str = DEFAULT_QDRANT_PATH,
    collection_name: str = COLLECTION_NAME,
) -> dict[str, Any]:
    if not vectors:
        raise ValueError("At least one vector is required")
    client = open_client(index_path)
    try:
        recreate_collection(client, vector_size=len(vectors[0]), collection_name=collection_name)
        written = upsert_chunks(client, chunks, vectors, collection_name=collection_name)
        collection = client.get_collection(collection_name)
        return {
            "collection_name": collection_name,
            "points_count": collection.points_count,
            "written": written,
            "vector_size": len(vectors[0]),
            "distance": "cosine",
        }
    finally:
        client.close()


def search_vectors(
    query_vector: Sequence[float],
    top_k: int = 5,
    filters: VectorFilters | None = None,
    index_path: Path | str = DEFAULT_QDRANT_PATH,
    collection_name: str = COLLECTION_NAME,
) -> list[VectorSearchResult]:
    client = open_client(index_path)
    try:
        if not client.collection_exists(collection_name):
            raise RuntimeError(
                f"Qdrant collection missing: {collection_name}. Run scripts/build_vectors.py first."
            )
        response = client.query_points(
            collection_name=collection_name,
            query=list(query_vector),
            query_filter=(filters or VectorFilters()).to_qdrant_filter(),
            limit=top_k,
            with_payload=True,
            with_vectors=False,
        )
        results: list[VectorSearchResult] = []
        for rank, point in enumerate(response.points, start=1):
            payload = point.payload or {}
            results.append(
                VectorSearchResult(
                    rank=rank,
                    score=float(point.score),
                    chunk_id=payload["chunk_id"],
                    chunk_type=payload["chunk_type"],
                    title=payload["title"],
                    text=payload.get("text", ""),
                    product_ids=payload.get("product_ids", []),
                    category_keys=payload.get("category_keys", []),
                    tier_keys=payload.get("tier_keys", []),
                    power_types=payload.get("power_types", []),
                    quality_status=payload.get("quality_status"),
                    source_block_ids=payload.get("source_block_ids", []),
                )
            )
        return results
    finally:
        client.close()


def collection_manifest(
    index_path: Path | str = DEFAULT_QDRANT_PATH,
    collection_name: str = COLLECTION_NAME,
) -> dict[str, Any]:
    client = open_client(index_path)
    try:
        if not client.collection_exists(collection_name):
            raise RuntimeError(f"Qdrant collection missing: {collection_name}")
        info = client.get_collection(collection_name)
        points, _ = client.scroll(
            collection_name=collection_name,
            limit=10_000,
            with_payload=True,
            with_vectors=False,
        )
        return {
            "collection_name": collection_name,
            "points_count": info.points_count,
            "vector_size": info.config.params.vectors.size,
            "distance": info.config.params.vectors.distance.value,
            "chunk_ids": sorted((point.payload or {}).get("chunk_id") for point in points),
        }
    finally:
        client.close()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
