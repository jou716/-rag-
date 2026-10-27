from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import BASE_DIR
from app.db import get_engine
from core.hybrid_search import (
    DEFAULT_CHANNEL_WEIGHTS,
    DEFAULT_RERANK_POOL,
    DEFAULT_RERANK_WEIGHT,
    DEFAULT_RRF_K,
    HybridRetriever,
)
from core.reranker import get_reranker_info

ALL_MODES = ("exact", "bm25", "vector", "hybrid", "hybrid_rerank")
K_VALUES = (1, 3, 5, 10)


def load_questions() -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in (BASE_DIR / "eval" / "questions.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]


def score_question(question: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    expected_chunks = set(question["expected_chunk_ids"])
    expected_sources = set(question["expected_source_block_ids"])
    chunk_ranks = [
        rank
        for rank, result in enumerate(results, start=1)
        if result["chunk_id"] in expected_chunks
    ]
    source_ranks = [
        rank
        for rank, result in enumerate(results, start=1)
        if expected_sources & set(result.get("source_block_ids", []))
    ]
    first_chunk_rank = min(chunk_ranks) if chunk_ranks else None
    first_source_rank = min(source_ranks) if source_ranks else None
    scores: dict[str, Any] = {}
    for k in K_VALUES:
        retrieved = {result["chunk_id"] for result in results[:k]}
        scores[f"hit@{k}"] = 1.0 if first_chunk_rank and first_chunk_rank <= k else 0.0
        scores[f"chunk_recall@{k}"] = (
            len(expected_chunks & retrieved) / len(expected_chunks)
            if expected_chunks
            else 0.0
        )
    scores["mrr@10"] = 1.0 / first_chunk_rank if first_chunk_rank and first_chunk_rank <= 10 else 0.0
    scores["source_hit@5"] = 1.0 if first_source_rank and first_source_rank <= 5 else 0.0
    return {
        "question_id": question["question_id"],
        "question": question["question"],
        "route_hint": question["route_hint"],
        "question_type": question["question_type"],
        "expected_chunk_ids": sorted(expected_chunks),
        "first_expected_rank": first_chunk_rank,
        "first_source_rank": first_source_rank,
        "top_chunks": [result["chunk_id"] for result in results],
        **scores,
    }


def aggregate(items: list[dict[str, Any]]) -> dict[str, float]:
    metric_names = (
        "hit@1",
        "hit@3",
        "hit@5",
        "chunk_recall@5",
        "chunk_recall@10",
        "mrr@10",
        "source_hit@5",
    )
    return {
        name: round(sum(item[name] for item in items) / len(items), 4)
        if items
        else 0.0
        for name in metric_names
    }


def grouped_aggregate(
    items: list[dict[str, Any]], field: str
) -> dict[str, dict[str, float]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        groups[item[field]].append(item)
    return {key: aggregate(value) for key, value in sorted(groups.items())}


def evaluate_mode(
    retriever: HybridRetriever,
    questions: list[dict[str, Any]],
    mode: str,
    top_k: int,
) -> dict[str, Any]:
    scored: list[dict[str, Any]] = []
    started = time.perf_counter()
    for question in questions:
        results = retriever.search(question["question"], top_k=top_k, mode=mode)
        scored.append(score_question(question, results))
    elapsed = time.perf_counter() - started
    return {
        "mode": mode,
        "summary": aggregate(scored),
        "by_route": grouped_aggregate(scored, "route_hint"),
        "by_type": grouped_aggregate(scored, "question_type"),
        "latency_ms_per_query": round(elapsed * 1000 / max(1, len(questions)), 2),
        "questions": scored,
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# N7 检索评测",
        "",
        f"- 可回答题：{report['evaluated_questions']}",
        f"- 跳过不可回答题：{report['skipped_unanswerable']}",
        f"- 评测截断：top {report['top_k']}",
        "",
        "## 总体结果",
        "",
        "| 模式 | Hit@1 | Hit@3 | Hit@5 | Chunk Recall@5 | Chunk Recall@10 | MRR@10 | Source Hit@5 | 平均延迟 ms |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for mode in report["results"]:
        summary = mode["summary"]
        lines.append(
            "| {mode} | {hit1:.4f} | {hit3:.4f} | {hit5:.4f} | {recall5:.4f} | "
            "{recall10:.4f} | {mrr:.4f} | {source:.4f} | {latency:.2f} |".format(
                mode=mode["mode"],
                hit1=summary["hit@1"],
                hit3=summary["hit@3"],
                hit5=summary["hit@5"],
                recall5=summary["chunk_recall@5"],
                recall10=summary["chunk_recall@10"],
                mrr=summary["mrr@10"],
                source=summary["source_hit@5"],
                latency=mode["latency_ms_per_query"],
            )
        )

    best_mode = max(report["results"], key=lambda item: item["summary"]["mrr@10"])
    lines.extend(
        [
            "",
            f"## 最佳模式分路由：{best_mode['mode']}",
            "",
            "| 路由 | Hit@1 | Hit@3 | Hit@5 | Chunk Recall@10 | MRR@10 |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for route, summary in best_mode["by_route"].items():
        lines.append(
            "| {route} | {hit1:.4f} | {hit3:.4f} | {hit5:.4f} | {recall:.4f} | {mrr:.4f} |".format(
                route=route,
                hit1=summary["hit@1"],
                hit3=summary["hit@3"],
                hit5=summary["hit@5"],
                recall=summary["chunk_recall@10"],
                mrr=summary["mrr@10"],
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate retrieval modes")
    parser.add_argument(
        "--modes",
        default=",".join(ALL_MODES),
        help="comma-separated modes: exact,bm25,vector,hybrid,hybrid_rerank",
    )
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--limit", type=int, help="only evaluate first N answerable questions")
    args = parser.parse_args()

    modes = tuple(mode.strip() for mode in args.modes.split(",") if mode.strip())
    unknown = sorted(set(modes) - set(ALL_MODES))
    if unknown:
        raise SystemExit(f"Unknown modes: {', '.join(unknown)}")

    questions = [question for question in load_questions() if question["answerable"]]
    if args.limit:
        questions = questions[: args.limit]

    retriever = HybridRetriever(engine=get_engine())
    results = [
        evaluate_mode(retriever, questions, mode, top_k=args.top_k)
        for mode in modes
    ]
    report = {
        "version": 1,
        "evaluated_questions": len(questions),
        "skipped_unanswerable": 45 - len(questions),
        "top_k": args.top_k,
        "config": {
            "channel_weights": DEFAULT_CHANNEL_WEIGHTS,
            "rrf_k": DEFAULT_RRF_K,
            "rerank_pool": DEFAULT_RERANK_POOL,
            "rerank_weight": DEFAULT_RERANK_WEIGHT,
            "reranker": get_reranker_info().as_dict()
            if "hybrid_rerank" in modes
            else None,
        },
        "results": results,
    }

    output_dir = BASE_DIR / "data" / "indexes"
    json_path = output_dir / "retrieval_eval.json"
    md_path = output_dir / "retrieval_eval.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_markdown(report, md_path)

    print(
        json.dumps(
            {
                mode["mode"]: mode["summary"] | {
                    "latency_ms_per_query": mode["latency_ms_per_query"]
                }
                for mode in results
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(f"json={json_path}")
    print(f"markdown={md_path}")


if __name__ == "__main__":
    main()
