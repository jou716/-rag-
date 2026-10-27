from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.answer import MAX_EVIDENCE, GroundedAnswerService


def _print_human(packet: dict) -> None:
    print(f"问题：{packet['query']}")
    print(f"状态：{packet['status']}")
    print("答案：")
    print(packet["answer"] or packet["refusal_reason"])
    print(f"引用：{', '.join(packet['citations']) or '无'}")
    if packet["missing_parts"]:
        print(f"缺失部分：{'；'.join(packet['missing_parts'])}")
    print("证据：")
    for evidence in packet["evidence"]:
        locators = "；".join(
            block.get("locator", {}).get("label", block.get("block_id", ""))
            for block in evidence["source"]["blocks"]
            if not block.get("missing")
        )
        print(
            f"- {evidence['evidence_id']} {evidence['title']} "
            f"({evidence['chunk_id']})"
        )
        print(f"  定位：{locators or '未找到原文定位'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Grounded ExoRAG answer demo")
    parser.add_argument("--query", required=True)
    parser.add_argument(
        "--top-k",
        type=int,
        default=MAX_EVIDENCE,
        choices=range(1, MAX_EVIDENCE + 1),
    )
    parser.add_argument("--json", action="store_true", help="print full JSON packet")
    args = parser.parse_args()

    service = GroundedAnswerService()
    packet = service.ask(args.query, top_k=args.top_k)
    if args.json:
        print(json.dumps(packet, ensure_ascii=False, indent=2))
    else:
        _print_human(packet)


if __name__ == "__main__":
    main()
