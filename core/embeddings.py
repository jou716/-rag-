from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from fastembed import TextEmbedding

from app.config import BASE_DIR

MODEL_NAME = "BAAI/bge-small-zh-v1.5"
MODEL_DIR = BASE_DIR / "data" / "models" / "bge-small-zh-v1.5"
MODEL_MANIFEST_PATH = MODEL_DIR / "manifest.json"
MODEL_DIMENSION = 512
PROVIDER_NAME = "fastembed-onnx"

REQUIRED_MODEL_FILES = (
    "config.json",
    "model_optimized.onnx",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.txt",
)


@dataclass(frozen=True)
class EmbeddingInfo:
    model_name: str
    provider: str
    revision: str
    dimension: int
    distance: str = "cosine"
    normalized: bool = True
    query_prefix: str = ""
    document_template: str = "title+section+text"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_model_manifest() -> dict[str, Any]:
    if not MODEL_MANIFEST_PATH.exists():
        raise FileNotFoundError(
            f"Embedding model manifest missing: {MODEL_MANIFEST_PATH}. "
            "Run scripts/fetch_embedding_model.py first."
        )
    return json.loads(MODEL_MANIFEST_PATH.read_text(encoding="utf-8"))


def get_embedding_info() -> EmbeddingInfo:
    manifest = load_model_manifest()
    missing = [name for name in REQUIRED_MODEL_FILES if not (MODEL_DIR / name).is_file()]
    if missing:
        raise FileNotFoundError(
            "Embedding model files missing: "
            + ", ".join(missing)
            + ". Run scripts/fetch_embedding_model.py first."
        )
    return EmbeddingInfo(
        model_name=manifest["model_name"],
        provider=manifest["provider"],
        revision=manifest["revision"],
        dimension=int(manifest["dimension"]),
    )


def build_embedding_text(chunk: dict[str, Any]) -> str:
    parts = [
        f"标题：{chunk['title']}",
        f"类型：{chunk['chunk_type']}",
    ]
    if chunk.get("product_ids"):
        parts.append("产品编号：" + "、".join(chunk["product_ids"]))
    if chunk.get("category_keys"):
        parts.append("产品类别：" + "、".join(chunk["category_keys"]))
    if chunk.get("tier_keys"):
        parts.append("产品层级：" + "、".join(chunk["tier_keys"]))
    if chunk.get("power_types"):
        parts.append("动力类型：" + "、".join(chunk["power_types"]))
    if chunk.get("section_path"):
        parts.append("章节：" + " > ".join(chunk["section_path"]))
    parts.append(chunk["text"])
    return "\n".join(parts)


@lru_cache(maxsize=1)
def _get_model() -> TextEmbedding:
    info = get_embedding_info()
    if info.dimension != MODEL_DIMENSION:
        raise ValueError(
            f"Unexpected embedding dimension in manifest: {info.dimension} != {MODEL_DIMENSION}"
        )
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    threads = max(1, min(4, os.cpu_count() or 1))
    return TextEmbedding(
        model_name=MODEL_NAME,
        specific_model_path=str(MODEL_DIR),
        cache_dir=str(MODEL_DIR.parent / "fastembed-cache"),
        threads=threads,
        cuda=False,
    )


def embed_texts(texts: Sequence[str], batch_size: int = 32) -> list[list[float]]:
    if not texts:
        return []
    vectors = _get_model().embed(list(texts), batch_size=batch_size)
    result = [np.asarray(vector, dtype=np.float32).tolist() for vector in vectors]
    if any(len(vector) != MODEL_DIMENSION for vector in result):
        raise ValueError("Embedding dimension mismatch")
    return result


def embed_query(query: str) -> list[float]:
    info = get_embedding_info()
    prepared = info.query_prefix + query
    return embed_texts([prepared], batch_size=1)[0]


def embed_chunks(chunks: Sequence[dict[str, Any]], batch_size: int = 32) -> list[list[float]]:
    return embed_texts([build_embedding_text(chunk) for chunk in chunks], batch_size=batch_size)
