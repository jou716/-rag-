from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import get_engine
from core.hybrid_search import HybridRetriever


def _check_common(packet: dict) -> None:
    evidence = packet["evidence"]
    assert 1 <= len(evidence) <= 8
    assert [item["evidence_id"] for item in evidence] == [
        f"E{rank}" for rank in range(1, len(evidence) + 1)
    ]
    for item in evidence:
        source = item["source"]
        assert source["document"]["file_name"] == "工业外骨骼产品目录.docx"
        assert len(source["document"]["sha256"]) == 64
        assert source["block_ids"]
        assert source["blocks"]
        assert not source["missing_block_ids"]


def main() -> None:
    retriever = HybridRetriever(engine=get_engine())

    comparison = retriever.search_with_evidence(
        "C615 和 C616 的电池与续航有什么区别？",
        top_k=3,
        evidence_top_k=8,
    )
    _check_common(comparison)
    assert [item["chunk_id"] for item in comparison["evidence"][:2]] == [
        "card_product_C615",
        "card_product_C616",
    ]
    assert comparison["evidence"][0]["card_chunk_ids"] == [
        "chunk_product_C615_profile",
        "chunk_product_C615_specs",
    ]

    scenario = retriever.search_with_evidence(
        "物流搬运与装卸场景推荐哪些产品？",
        top_k=3,
        evidence_top_k=8,
    )
    _check_common(scenario)
    first = scenario["evidence"][0]
    assert first["chunk_id"] == "chunk_matrix_scenario_tbl_ac98d42e_t01_r02"
    assert any(
        block["locator"]["kind"] == "table_row"
        for block in first["source"]["blocks"]
    )

    summary = {
        "comparison": {
            "returned": len(comparison["evidence"]),
            "evidence_ids": [item["evidence_id"] for item in comparison["evidence"]],
            "chunks": [item["chunk_id"] for item in comparison["evidence"]],
        },
        "scenario": {
            "returned": len(scenario["evidence"]),
            "evidence_ids": [item["evidence_id"] for item in scenario["evidence"]],
            "chunks": [item["chunk_id"] for item in scenario["evidence"]],
            "first_locator": first["source"]["blocks"][-1]["locator"],
        },
        "status": "passed",
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
