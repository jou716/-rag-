import gradio as gr
from fastapi.testclient import TestClient

from app.main import app
from app.ui import (
    _render_answer,
    _render_meta,
    _render_status,
    build_ui,
    render_evidence_html,
)

client = TestClient(app)


def test_ui_route_is_mounted() -> None:
    response = client.get("/ui/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_build_ui_returns_blocks() -> None:
    demo = build_ui()

    assert isinstance(demo, gr.Blocks)


def test_evidence_html_escapes_untrusted_text_and_shows_traceability() -> None:
    evidence = {
        "evidence_id": "E1",
        "title": "<script>alert(1)</script>",
        "text": "<b>原文</b>\n第二行",
        "section_path": ["产品目录", "C615"],
        "chunk_id": "chunk_c615",
        "chunk_type": "product_specs",
        "quality_status": "needs_review",
        "quality_flags": ["tier_matrix_category_conflict"],
        "source": {
            "blocks": [
                {
                    "block_id": "blk_1",
                    "locator": {"label": "Word 段落 180"},
                }
            ]
        },
        "retrieval": {
            "final_score": 0.7966,
            "channel_ranks": {"exact": 1, "bm25": 2, "vector": 3},
        },
    }

    rendered = render_evidence_html([evidence])

    assert "exo-card" in rendered
    assert "E1" in rendered
    assert "Word 段落 180" in rendered
    assert "exact #1" in rendered
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "&lt;b&gt;原文&lt;/b&gt;" in rendered


def test_render_status_and_partial_answer() -> None:
    packet = {
        "status": "partial",
        "answer": "目录中有 C615 的基础信息。",
        "refusal_reason": None,
    }

    assert "⚠️" in _render_status(packet, 123)
    assert "可确认的部分" in _render_answer(packet)


def test_render_meta_lists_citations_and_missing_fields() -> None:
    meta = _render_meta(
        {
            "citations": ["E1", "E2"],
            "generation_mode": "llm",
            "analysis": {"intent": "comparison", "product_ids": ["C615", "C616"]},
            "missing_parts": ["产品目录未提供价格信息"],
            "notes": [],
            "evidence": [{}, {}],
        }
    )

    assert "`E1`" in meta
    assert "`E2`" in meta
    assert "产品目录未提供价格信息" in meta
    assert "证据数量" in meta
