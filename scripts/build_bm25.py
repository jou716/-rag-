import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import BASE_DIR
from core.bm25 import build_bm25_index, save_bm25_index, search_bm25

SMOKE_QUERIES = [
    "C615 续航时间是多少",
    "物流搬运与装卸推荐哪些产品",
    "公司售后响应",
    "C656 规格不完整",
    "最大助力 60 kg 腰背外骨骼",
]


def main() -> None:
    processed = BASE_DIR / "data" / "processed"
    index_dir = BASE_DIR / "data" / "indexes"
    chunks = [
        json.loads(line)
        for line in (processed / "chunks.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    chunk_report = json.loads(
        (processed / "chunk_report.json").read_text(encoding="utf-8")
    )
    source_hash = chunk_report["source"]["sha256"]

    index = build_bm25_index(chunks, source_hash=source_hash)
    index_path = index_dir / "bm25_index.json"
    save_bm25_index(index, index_path)

    top_terms = sorted(
        (
            {"term": term, "doc_freq": count}
            for term, count in index["doc_freq"].items()
            if len(term) > 1
        ),
        key=lambda item: (-item["doc_freq"], item["term"]),
    )[:30]

    report = {
        "source": chunk_report["source"],
        "index_path": str(index_path),
        "index_size_bytes": index_path.stat().st_size,
        "counts": {
            "chunks": index["chunk_count"],
            "vocabulary": len(index["doc_freq"]),
        },
        "config": index["config"],
        "avg_field_lengths": index["avg_field_lengths"],
        "top_terms": top_terms,
        "smoke_queries": {
            query: search_bm25(index, query, top_k=3) for query in SMOKE_QUERIES
        },
    }
    (index_dir / "bm25_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["counts"], ensure_ascii=False, indent=2))
    print(json.dumps(report["avg_field_lengths"], ensure_ascii=False, indent=2))
    print(f"index={index_path}")


if __name__ == "__main__":
    main()
