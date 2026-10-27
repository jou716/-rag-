import pytest

from core.reranker import RERANKER_DIR, get_reranker_info, rerank_probabilities, sigmoid

pytestmark = pytest.mark.skipif(
    not (RERANKER_DIR / "onnx" / "model_int8.onnx").is_file(),
    reason="reranker model not downloaded",
)


def test_reranker_metadata() -> None:
    info = get_reranker_info()

    assert info.model_name == "BAAI/bge-reranker-v2-m3-int8"
    assert info.provider == "fastembed-onnx-cross-encoder"
    assert len(info.revision) == 40


def test_sigmoid_is_stable_for_extreme_logits() -> None:
    assert sigmoid(0) == 0.5
    assert 0 < sigmoid(-50) < 1e-20
    assert 0 <= sigmoid(-1000) < 1e-10
    assert 1 - 1e-10 < sigmoid(1000) <= 1


def test_cross_encoder_ranks_relevant_document_first() -> None:
    probabilities = rerank_probabilities(
        "C615 电池续航时间多久？",
        [
            "C615 规格明细 电池 92Wh 续航 6–8 小时",
            "公司提供 7×24 小时售后响应",
        ],
    )

    assert probabilities[0] > probabilities[1]
