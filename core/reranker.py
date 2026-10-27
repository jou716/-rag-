from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Sequence

from fastembed.rerank.cross_encoder import TextCrossEncoder

from app.config import BASE_DIR

RERANKER_NAME = "BAAI/bge-reranker-v2-m3-int8"
RERANKER_DIR = BASE_DIR / "data" / "models" / "bge-reranker-v2-m3-int8"
RERANKER_MANIFEST_PATH = RERANKER_DIR / "manifest.json"
REQUIRED_RERANKER_FILES = (
    "config.json",
    "onnx/model_int8.onnx",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
)


@dataclass(frozen=True)
class RerankerInfo:
    model_name: str
    provider: str
    revision: str
    score_transform: str = "sigmoid"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_reranker_manifest() -> dict[str, Any]:
    if not RERANKER_MANIFEST_PATH.exists():
        raise FileNotFoundError(
            f"Reranker manifest missing: {RERANKER_MANIFEST_PATH}. "
            "Run scripts/fetch_reranker_model.py first."
        )
    return json.loads(RERANKER_MANIFEST_PATH.read_text(encoding="utf-8"))


def get_reranker_info() -> RerankerInfo:
    manifest = load_reranker_manifest()
    missing = [name for name in REQUIRED_RERANKER_FILES if not (RERANKER_DIR / name).is_file()]
    if missing:
        raise FileNotFoundError(
            "Reranker model files missing: "
            + ", ".join(missing)
            + ". Run scripts/fetch_reranker_model.py first."
        )
    return RerankerInfo(
        model_name=manifest["model_name"],
        provider=manifest["provider"],
        revision=manifest["revision"],
    )


@lru_cache(maxsize=1)
def _get_model() -> TextCrossEncoder:
    get_reranker_info()
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    threads = max(1, min(4, os.cpu_count() or 1))
    return TextCrossEncoder(
        model_name=RERANKER_NAME,
        specific_model_path=str(RERANKER_DIR),
        cache_dir=str(RERANKER_DIR.parent / "fastembed-cache"),
        threads=threads,
        cuda=False,
    )


def rerank_logits(
    query: str, documents: Sequence[str], batch_size: int = 16
) -> list[float]:
    if not documents:
        return []
    return [float(score) for score in _get_model().rerank(query, documents, batch_size=batch_size)]


def sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exponent = math.exp(value)
    return exponent / (1.0 + exponent)


def rerank_probabilities(
    query: str, documents: Sequence[str], batch_size: int = 16
) -> list[float]:
    return [sigmoid(score) for score in rerank_logits(query, documents, batch_size=batch_size)]
