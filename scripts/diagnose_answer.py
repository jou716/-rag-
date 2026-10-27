from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.answer import (
    GroundedAnswerService,
    extract_citation_ids,
    validate_citation_coverage,
    validate_grounding,
)
from core.prompting import build_llm_messages


class RecordingClient:
    def __init__(self, delegate):
        self.delegate = delegate
        self.last_raw = None
        self.last_system = None
        self.last_user = None

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.last_system = system_prompt
        self.last_user = user_prompt
        self.last_raw = self.delegate.generate(system_prompt, user_prompt)
        return self.last_raw


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--top-k", type=int, default=8)
    args = parser.parse_args()

    base = GroundedAnswerService(generation_mode="llm")
    recorder = RecordingClient(base.llm_client)
    service = GroundedAnswerService(generation_mode="llm", llm_client=recorder)
    result = service.ask(args.query, top_k=args.top_k)

    evidence = result["evidence"]
    print("=== SERVICE STATUS ===", result["status"])
    print("refusal:", result.get("refusal_reason"))
    print("answer:", result.get("answer"))
    print("citations:", result.get("citations"))
    print("citation_validation:", json.dumps(result["citation_validation"], ensure_ascii=False))
    print("grounding_validation:", json.dumps(result["grounding_validation"], ensure_ascii=False))
    print("\n=== EVIDENCE ===")
    for item in evidence:
        print(f"[{item['evidence_id']}] {item.get('title')} | {' > '.join(item.get('section_path') or [])}")
        print(f"  products={item.get('product_ids')} quality={item.get('quality_status')} flags={item.get('quality_flags')}")
        print(f"  text={item.get('text')}")
    print("\n=== RAW ANSWER ===")
    print(recorder.last_raw)
    raw = recorder.last_raw or ""
    citations = extract_citation_ids(raw)
    print("\n=== RAW CITATIONS ===", citations)
    print("=== RAW COVERAGE ===", json.dumps(validate_citation_coverage(raw), ensure_ascii=False))
    print("=== RAW GROUNDING ===", json.dumps(validate_grounding(raw, evidence, citations), ensure_ascii=False))


if __name__ == "__main__":
    main()
