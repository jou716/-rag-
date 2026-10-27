from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "ExoRAG"
    assert body["source_doc"]["exists"] == settings.source_doc_path.is_file()
    assert "password" not in str(body).lower()


def test_database_health_is_explicit_when_not_configured() -> None:
    response = client.get("/health/db")

    if response.status_code == 200:
        assert response.json()["status"] == "ok"
    else:
        assert response.status_code == 503
        assert response.json()["status"] in {"not_configured", "error"}
