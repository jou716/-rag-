from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.main import app


def main() -> None:
    parser = argparse.ArgumentParser(description="Call the real /ask route")
    parser.add_argument("query")
    parser.add_argument("--top-k", type=int, default=8)
    args = parser.parse_args()
    with TestClient(app) as client:
        response = client.post(
            "/ask", json={"query": args.query, "top_k": args.top_k}
        )
    response.raise_for_status()
    body = response.json()
    print(f"status={body['status']}")
    print(f"generation_mode={body['generation_mode']}")
    print(f"citations={','.join(body['citations']) or '-'}")
    print(f"evidence_count={len(body['evidence'])}")
    print(f"answer={body['answer']}")
    if body["refusal_reason"]:
        print(f"refusal_reason={body['refusal_reason']}")
    print("top_evidence:")
    for item in body["evidence"][:3]:
        score = item["retrieval"].get("final_score")
        print(
            f"  {item['evidence_id']} rank={item['rank']} "
            f"score={score:.4f} title={item.get('title')}"
        )


if __name__ == "__main__":
    main()
