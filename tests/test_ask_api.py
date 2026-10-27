import pytest
from fastapi.testclient import TestClient

from app.api.ask import get_answer_service
from app.config import BASE_DIR, settings
from app.main import app

client = TestClient(app)

LOCAL_INDEX_READY = (
    settings.source_doc_path.is_file()
    and (BASE_DIR / "data" / "processed" / "chunks.jsonl").is_file()
    and (BASE_DIR / "data" / "indexes" / "bm25_index.json").is_file()
    and (BASE_DIR / "data" / "indexes" / "vector_manifest.json").is_file()
)


class FakeAnswerService:
    def ask(self, query: str, *, top_k: int = 15) -> dict:
        return {
            "query": query,
            "status": "answered",
            "answer": "C615 的续航为 6–8 小时 [E1]。",
            "citations": ["E1"],
            "missing_parts": [],
            "notes": [],
            "refusal_reason": None,
            "generation_mode": "evidence_composer",
            "analysis": {"intent": "fact"},
            "citation_validation": {"valid": True, "unknown_citation_ids": []},
            "grounding_validation": {
                "valid": True,
                "checked_tokens": ["8 小时"],
                "unsupported_tokens": [],
            },
            "evidence": [{"evidence_id": "E1", "title": "C615 规格明细"}],
        }


def test_ask_endpoint_returns_answer_and_evidence() -> None:
    app.dependency_overrides[get_answer_service] = lambda: FakeAnswerService()
    try:
        response = client.post("/ask", json={"query": "C615 的续航时间是多少？"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "answered"
    assert body["citations"] == ["E1"]
    assert body["evidence"][0]["evidence_id"] == "E1"


@pytest.mark.skipif(
    not LOCAL_INDEX_READY,
    reason="local corpus and indexes are not included in the public repository",
)
def test_ask_endpoint_accepts_fifteen_evidence_items() -> None:
    response = client.post(
        "/ask",
        json={"query": "C615 的续航时间是多少？", "top_k": 15},
    )

    assert response.status_code == 200


def test_ask_endpoint_rejects_more_than_fifteen_evidence_items() -> None:
    response = client.post(
        "/ask",
        json={"query": "C615 的续航时间是多少？", "top_k": 16},
    )

    assert response.status_code == 422
