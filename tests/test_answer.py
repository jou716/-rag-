from core.answer import (
    GroundedAnswerService,
    _compose_draft,
    extract_citation_ids,
    validate_citation_coverage,
    validate_grounding,
)
from core.query_analysis import analyze_query


def evidence(
    evidence_id: str,
    *,
    chunk_type: str,
    text: str,
    product_ids: list[str] | None = None,
    quality_flags: list[str] | None = None,
    section_path: list[str] | None = None,
) -> dict:
    return {
        "evidence_id": evidence_id,
        "citation": f"[{evidence_id}]",
        "rank": int(evidence_id[1:]),
        "chunk_id": f"chunk_{evidence_id.lower()}",
        "chunk_type": chunk_type,
        "title": f"证据 {evidence_id}",
        "text": text,
        "section_path": section_path or ["产品目录", "6. 产品规格明细", "C615"],
        "product_ids": product_ids or [],
        "quality_status": "needs_review" if quality_flags else None,
        "quality_flags": quality_flags or [],
        "source_block_ids": [f"blk_{evidence_id.lower()}"],
        "source": {},
        "retrieval": {},
    }


def test_fact_answer_uses_cited_evidence_value() -> None:
    analysis = analyze_query("C615 的续航时间是多少？")
    items = [
        evidence(
            "E1",
            chunk_type="product_specs",
            text="产品编号：C615\n- 电池：92Wh（36V 锂离子）\n- 续航：6–8 小时",
            product_ids=["C615"],
        )
    ]

    draft = _compose_draft(analysis, items)

    assert draft.status == "answered"
    assert "6–8 小时" in draft.answer
    assert "[E1]" in draft.answer
    assert validate_grounding(draft.answer, items, ["E1"])["valid"] is True


def test_comparison_answer_covers_both_products() -> None:
    analysis = analyze_query("C615 和 C616 的电池与续航有什么区别？")
    items = [
        evidence(
            "E1",
            chunk_type="product_specs",
            text="产品编号：C615\n- 电池：92Wh\n- 续航：6–8 小时",
            product_ids=["C615"],
        ),
        evidence(
            "E2",
            chunk_type="product_specs",
            text="产品编号：C616\n- 电池：92Wh\n- 续航：3–8 小时",
            product_ids=["C616"],
        ),
    ]

    draft = _compose_draft(analysis, items)

    assert "C615" in draft.answer and "C616" in draft.answer
    assert "6–8 小时" in draft.answer and "3–8 小时" in draft.answer
    assert extract_citation_ids(draft.answer) == ["E1", "E2"]


def test_filter_answer_lists_products_with_citations() -> None:
    analysis = analyze_query("高端电动上肢外骨骼有哪些？")
    items = [
        evidence(
            "E1",
            chunk_type="product_profile",
            text="产品编号：C615\n产品类别：上肢外骨骼\n产品层级：高端｜先进智能\n动力类型：电动/动力",
            product_ids=["C615"],
        )
    ]

    draft = _compose_draft(analysis, items)

    assert "C615" in draft.answer
    assert "[E1]" in draft.answer


def test_electric_filter_lists_cart_linked_product() -> None:
    analysis = analyze_query("下肢外骨骼有哪些是电动的")
    items = [
        evidence(
            "E1",
            chunk_type="product_profile",
            text=(
                "产品编号：C689\n产品类别：负重下肢外骨骼\n"
                "产品层级：高端｜先进智能\n动力类型：电动/动力"
            ),
            product_ids=["C689"],
        ),
        evidence(
            "E2",
            chunk_type="product_profile",
            text=(
                "产品编号：C680\n产品类别：负重下肢外骨骼\n"
                "产品层级：未识别\n动力类型：电动推车联动"
            ),
            product_ids=["C680"],
        ),
    ]

    draft = _compose_draft(analysis, items)

    assert "C689" in draft.answer
    assert "C680" in draft.answer
    assert "电动推车联动" in draft.answer


def test_price_query_returns_product_overview_and_explicit_missing_note() -> None:
    analysis = analyze_query("C615 的价格是多少？")
    items = [
        evidence(
            "E1",
            chunk_type="product_profile",
            text=(
                "产品编号：C615\n产品类别：上肢外骨骼\n产品层级：高端｜先进智能\n"
                "动力类型：电动/动力\n类型：AI 动力上肢外骨骼"
            ),
            product_ids=["C615"],
        )
    ]

    draft = _compose_draft(analysis, items)

    assert draft.status == "partial"
    assert "产品目录未提供价格信息" in draft.answer
    assert "AI 动力上肢外骨骼" in draft.answer


def test_no_evidence_is_refused() -> None:
    analysis = analyze_query("C999 的续航时间是多少？")

    draft = _compose_draft(analysis, [])

    assert draft.status == "refused"
    assert draft.refusal_reason is not None
    assert "C999" in draft.refusal_reason


def test_quality_conflict_cites_the_evidence_that_contains_both_values() -> None:
    analysis = analyze_query("C655 的最大助力到底是多少？")
    items = [
        evidence(
            "E1",
            chunk_type="product_profile",
            text="产品编号：C655\n类型：被动腰背外骨骼；最大助力 25 kg",
            product_ids=["C655"],
            quality_flags=["assist_payload_inconsistency"],
        ),
        evidence(
            "E2",
            chunk_type="product_specs",
            text="产品编号：C655\n- 最大助力：25 kg（助力负载：4–10 kg）",
            product_ids=["C655"],
            quality_flags=["assist_payload_inconsistency"],
        ),
    ]

    draft = _compose_draft(analysis, items)

    assert "4–10 kg" in draft.answer
    assert "[E2]" in draft.answer


def test_grounding_rejects_number_absent_from_cited_evidence() -> None:
    items = [
        evidence(
            "E1",
            chunk_type="product_specs",
            text="产品编号：C615\n- 续航：6–8 小时",
            product_ids=["C615"],
        )
    ]

    validation = validate_grounding("C615 的续航为 12 小时 [E1]。", items, ["E1"])

    assert validation["valid"] is False
    assert validation["unsupported_tokens"] == ["12 小时"]


def test_extract_citations_expands_ranges() -> None:
    assert extract_citation_ids("价格未提及 [E1–E3]。") == ["E1", "E2", "E3"]
    assert extract_citation_ids("价格未提及 [E1]–[E3]。") == ["E1", "E2", "E3"]


def test_citation_coverage_allows_list_level_citation() -> None:
    answer = (
        "可通过以下方式联系公司：\n"
        "- 电话：+86 195 2661 2838\n"
        "- 邮箱：correxon@correxonhealth.com\n"
        "- 地址：中国广东省东莞市 [E1]"
    )

    validation = validate_citation_coverage(answer)

    assert validation["valid"] is True


def test_grounding_ignores_spacing_and_multiplication_sign() -> None:
    items = [
        evidence(
            "E1",
            chunk_type="section",
            text="售后响应：7×24 全天候响应；及时响应：24 小时服务与支持。",
        )
    ]

    validation = validate_grounding(
        "提供 7×24 响应和 24小时服务 [E1]。", items, ["E1"]
    )

    assert validation["valid"] is True


def test_grounding_ignores_numbers_in_missing_information_clause() -> None:
    items = [
        evidence(
            "E1",
            chunk_type="section",
            text="售后响应：7×24 全天候响应。",
        )
    ]

    validation = validate_grounding(
        "提供 7×24 响应 [E1]。产品目录未提供：2小时内首次响应等时限。",
        items,
        ["E1"],
    )

    assert validation["valid"] is True


class FakeRetriever:
    def __init__(self, items: list[dict]) -> None:
        self.items = items

    def search_with_evidence(
        self, query: str, *, top_k: int, evidence_top_k: int
    ) -> dict:
        return {"analysis": {}, "results": self.items, "evidence": self.items}


def test_service_returns_answer_with_valid_citations_and_grounding() -> None:
    service = GroundedAnswerService(
        retriever=FakeRetriever(
            [
                evidence(
                    "E1",
                    chunk_type="product_specs",
                    text="产品编号：C615\n- 续航：6–8 小时",
                    product_ids=["C615"],
                )
            ]
        ),
        generation_mode="local",
    )

    result = service.ask("C615 的续航时间是多少？")

    assert result["status"] == "answered"
    assert result["citation_validation"]["valid"] is True
    assert result["grounding_validation"]["valid"] is True


class FakeLLMClient:
    def __init__(self, answer: str) -> None:
        self.answer = answer

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        assert "只能使用" in system_prompt
        assert "[E1]" in user_prompt
        return self.answer


class QueuedLLMClient:
    def __init__(self, answers: list[str]) -> None:
        self.answers = answers
        self.calls = 0

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        answer = self.answers[min(self.calls, len(self.answers) - 1)]
        self.calls += 1
        return answer


def test_llm_mode_uses_model_answer_when_validation_passes() -> None:
    service = GroundedAnswerService(
        retriever=FakeRetriever(
            [
                evidence(
                    "E1",
                    chunk_type="product_specs",
                    text="产品编号：C615\n- 续航：6–8 小时",
                    product_ids=["C615"],
                )
            ]
        ),
        llm_client=FakeLLMClient("C615 的续航为 6–8 小时 [E1]。"),
        generation_mode="llm",
    )

    result = service.ask("C615 的续航时间是多少？")

    assert result["status"] == "answered"
    assert result["generation_mode"] == "llm"
    assert result["answer"] == "C615 的续航为 6–8 小时 [E1]。"


def test_llm_mode_rejects_answer_without_citation() -> None:
    service = GroundedAnswerService(
        retriever=FakeRetriever(
            [
                evidence(
                    "E1",
                    chunk_type="product_specs",
                    text="产品编号：C615\n- 续航：6–8 小时",
                    product_ids=["C615"],
                )
            ]
        ),
        llm_client=FakeLLMClient("C615 的续航为 6–8 小时。"),
        generation_mode="llm",
    )

    result = service.ask("C615 的续航时间是多少？")

    assert result["status"] == "error"
    assert result["answer"] == ""


def test_llm_mode_retries_once_when_citation_is_missing() -> None:
    client = QueuedLLMClient(
        ["C615 的续航为 6–8 小时。", "C615 的续航为 6–8 小时 [E1]。"]
    )
    service = GroundedAnswerService(
        retriever=FakeRetriever(
            [
                evidence(
                    "E1",
                    chunk_type="product_specs",
                    text="产品编号：C615\n- 续航：6–8 小时",
                    product_ids=["C615"],
                )
            ]
        ),
        llm_client=client,
        generation_mode="llm",
    )

    result = service.ask("C615 的续航时间是多少？")

    assert result["status"] == "answered"
    assert result["attempts"] == 2
    assert client.calls == 2
