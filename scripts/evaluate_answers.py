from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import BASE_DIR
from core.answer import GroundedAnswerService, MAX_EVIDENCE


def load_questions() -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in (BASE_DIR / "eval" / "questions.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]


def _cited_evidence(result: dict[str, Any]) -> list[dict[str, Any]]:
    cited = set(result["citations"])
    return [
        evidence for evidence in result["evidence"] if evidence["evidence_id"] in cited
    ]


def _safe_unanswerable(result: dict[str, Any]) -> bool:
    if result["status"] == "refused":
        return True
    if result["status"] != "partial":
        return False
    text = result["answer"]
    return any(
        marker in text
        for marker in ("未提供", "未提及", "无法确认", "无法回答", "未找到")
    )


def score_question(question: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    expected_blocks = set(question["expected_source_block_ids"])
    cited_evidence = _cited_evidence(result)
    cited_blocks = {
        block_id
        for evidence in cited_evidence
        for block_id in evidence.get("source", {}).get("block_ids", [])
    }
    expected_hits = expected_blocks & cited_blocks
    answerable = bool(question["answerable"])
    answered = result["status"] in {"answered", "partial"}
    citation_valid = bool(result["citation_validation"]["valid"])
    grounding_valid = bool(result["grounding_validation"]["valid"])
    if answerable:
        success = answered and citation_valid and grounding_valid
        safe = success
    else:
        success = _safe_unanswerable(result)
        safe = success
    return {
        "question_id": question["question_id"],
        "question": question["question"],
        "question_type": question["question_type"],
        "answerable": answerable,
        "status": result["status"],
        "citations": result["citations"],
        "cited_chunk_ids": [item["chunk_id"] for item in cited_evidence],
        "cited_source_block_ids": sorted(cited_blocks),
        "expected_source_block_ids": sorted(expected_blocks),
        "source_hit": bool(expected_hits) if answerable else None,
        "source_recall": (
            len(expected_hits) / len(expected_blocks)
            if answerable and expected_blocks
            else None
        ),
        "citation_present": bool(result["citations"]) if answered else None,
        "citation_valid": citation_valid,
        "grounding_valid": grounding_valid,
        "safe": safe,
        "success": success,
        "answer": result["answer"],
        "refusal_reason": result["refusal_reason"],
    }


def summarize(items: list[dict[str, Any]], latency_ms: float) -> dict[str, Any]:
    answerable = [item for item in items if item["answerable"]]
    unanswerable = [item for item in items if not item["answerable"]]
    answered_or_partial = [
        item for item in answerable if item["status"] in {"answered", "partial"}
    ]
    checkable = [item for item in items if item["status"] != "refused"]
    return {
        "questions": len(items),
        "answerable": len(answerable),
        "unanswerable": len(unanswerable),
        "answer_rate": round(len(answered_or_partial) / len(answerable), 4),
        "answered_rate": round(
            sum(item["status"] == "answered" for item in answerable) / len(answerable),
            4,
        ),
        "strict_refusal_rate_unanswerable": round(
            sum(item["status"] == "refused" for item in unanswerable)
            / len(unanswerable),
            4,
        ),
        "safe_unanswerable_rate": round(
            sum(item["safe"] for item in unanswerable) / len(unanswerable), 4
        ),
        "citation_presence_rate": round(
            sum(bool(item["citation_present"]) for item in checkable) / len(checkable),
            4,
        ),
        "citation_validity_rate": round(
            sum(item["citation_valid"] for item in checkable) / len(checkable), 4
        ),
        "grounding_validity_rate": round(
            sum(item["grounding_valid"] for item in checkable) / len(checkable), 4
        ),
        "source_hit_rate": round(
            sum(bool(item["source_hit"]) for item in answered_or_partial)
            / len(answered_or_partial),
            4,
        ),
        "mean_source_recall": round(
            sum(item["source_recall"] for item in answered_or_partial)
            / len(answered_or_partial),
            4,
        ),
        "latency_ms_per_query": round(latency_ms, 2),
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    summary = report["summary"]
    lines = [
        "# N8 答案、引用与拒答评测",
        "",
        f"- 总问题数：{summary['questions']}",
        f"- 可回答：{summary['answerable']}",
        f"- 不可回答：{summary['unanswerable']}",
        f"- 平均单题延迟：{summary['latency_ms_per_query']:.2f} ms",
        "",
        "## 总体指标",
        "",
        "| 指标 | 结果 |",
        "| --- | ---: |",
        f"| 可回答题回答率 | {summary['answer_rate']:.4f} |",
        f"| 可回答题完整回答率 | {summary['answered_rate']:.4f} |",
        f"| 不可回答题严格拒答率 | {summary['strict_refusal_rate_unanswerable']:.4f} |",
        f"| 不可回答题安全处理率 | {summary['safe_unanswerable_rate']:.4f} |",
        f"| 引用存在率 | {summary['citation_presence_rate']:.4f} |",
        f"| 引用编号有效率 | {summary['citation_validity_rate']:.4f} |",
        f"| 数值 grounding 有效率 | {summary['grounding_validity_rate']:.4f} |",
        f"| 预期原文块命中率 | {summary['source_hit_rate']:.4f} |",
        f"| 预期原文块平均召回 | {summary['mean_source_recall']:.4f} |",
        "",
        "## 逐题结果",
        "",
        "| 题号 | 类型 | 状态 | 引用 | 原文命中 | 安全 |",
        "| --- | --- | --- | --- | ---: | ---: |",
    ]
    for item in report["questions"]:
        lines.append(
            f"| {item['question_id']} | {item['question_type']} | {item['status']} | "
            f"{','.join(item['citations']) or '-'} | "
            f"{'-' if item['source_hit'] is None else int(item['source_hit'])} | "
            f"{int(item['safe'])} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate grounded answers")
    parser.add_argument("--top-k", type=int, default=MAX_EVIDENCE)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    questions = load_questions()
    if args.limit:
        questions = questions[: args.limit]
    service = GroundedAnswerService()
    scored: list[dict[str, Any]] = []
    started = time.perf_counter()
    for question in questions:
        result = service.ask(question["question"], top_k=args.top_k)
        scored.append(score_question(question, result))
    elapsed_ms = (time.perf_counter() - started) * 1000 / max(1, len(questions))
    report = {
        "version": 1,
        "top_k": args.top_k,
        "summary": summarize(scored, elapsed_ms),
        "questions": scored,
    }

    output_dir = BASE_DIR / "data" / "indexes"
    json_path = output_dir / "answer_eval.json"
    md_path = output_dir / "answer_eval.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_markdown(report, md_path)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"json={json_path}")
    print(f"markdown={md_path}")


if __name__ == "__main__":
    main()
