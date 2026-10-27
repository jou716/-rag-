from __future__ import annotations

import html
import os
import time
from collections.abc import Mapping, Sequence
from typing import Any

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

import gradio as gr

from app.api.ask import get_answer_service
from core.answer import MAX_EVIDENCE

STATUS_META = {
    "answered": ("✅", "已回答"),
    "partial": ("⚠️", "部分回答"),
    "refused": ("🚫", "已拒答"),
    "error": ("❌", "生成失败"),
}

CUSTOM_CSS = """
.exo-header { margin-bottom: 4px; }
.exo-subtitle { opacity: .78; margin-top: -6px; }
.exo-evidence { display: flex; flex-direction: column; gap: 10px; }
.exo-card {
    border: 1px solid var(--border-color-primary, #d1d5db);
    border-radius: 10px;
    overflow: hidden;
    background: var(--background-fill-primary, transparent);
}
.exo-card summary {
    cursor: pointer;
    padding: 10px 12px;
    font-weight: 600;
    background: var(--background-fill-secondary, rgba(127, 127, 127, .08));
}
.exo-id {
    display: inline-block;
    min-width: 2.2em;
    padding: 1px 6px;
    margin-right: 6px;
    border-radius: 6px;
    background: #2563eb;
    color: #fff;
    font-size: 12px;
    text-align: center;
}
.exo-score { float: right; opacity: .72; font-weight: 500; font-size: 12px; }
.exo-body { padding: 12px; }
.exo-meta { font-size: 12px; opacity: .78; line-height: 1.7; margin-bottom: 8px; }
.exo-text {
    white-space: pre-wrap;
    font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
    font-size: 13px;
    line-height: 1.6;
    padding: 10px;
    border-radius: 8px;
    background: var(--background-fill-secondary, rgba(127, 127, 127, .08));
}
.exo-rank { font-size: 12px; opacity: .75; margin-top: 8px; }
.exo-empty { padding: 18px; text-align: center; opacity: .6; }
"""


def _escape(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _locator_text(evidence: Mapping[str, Any]) -> str:
    source = evidence.get("source") or {}
    blocks = source.get("blocks") or []
    labels: list[str] = []
    for block in blocks:
        if block.get("missing"):
            continue
        label = (block.get("locator") or {}).get("label")
        labels.append(label or block.get("block_id") or "未知定位")
    return "；".join(labels) or "未找到原文定位"


def _rank_text(evidence: Mapping[str, Any]) -> str:
    retrieval = evidence.get("retrieval") or {}
    ranks = retrieval.get("channel_ranks") or {}
    if not ranks:
        return "无检索排名"
    ordered = sorted(ranks.items(), key=lambda item: (item[1], item[0]))
    return " · ".join(f"{name} #{rank}" for name, rank in ordered)


def render_evidence_html(evidence_items: Sequence[Mapping[str, Any]]) -> str:
    if not evidence_items:
        return '<div class="exo-empty">没有返回证据。</div>'
    cards: list[str] = []
    for index, evidence in enumerate(evidence_items):
        retrieval = evidence.get("retrieval") or {}
        score = retrieval.get("final_score")
        score_text = f"{score:.4f}" if isinstance(score, (int, float)) else "-"
        section = " > ".join(evidence.get("section_path") or []) or "未标注章节"
        quality_status = evidence.get("quality_status") or "normal"
        quality_flags = "、".join(evidence.get("quality_flags") or []) or "无"
        quality = (
            f"质量状态：{_escape(quality_status)}；质量标记：{_escape(quality_flags)}"
        )
        card_chunk_ids = evidence.get("card_chunk_ids") or []
        card_parts = (
            f"产品卡合并：{_escape(' + '.join(card_chunk_ids))}<br>"
            if len(card_chunk_ids) > 1
            else ""
        )
        open_attr = " open" if index == 0 else ""
        cards.append(
            f'<details class="exo-card"{open_attr}>'
            f"<summary>"
            f'<span class="exo-id">{_escape(evidence.get("evidence_id"))}</span>'
            f'{_escape(evidence.get("title") or "未命名证据")}'
            f'<span class="exo-score">score {_escape(score_text)}</span>'
            f"</summary>"
            f'<div class="exo-body">'
            f'<div class="exo-meta">'
            f"章节：{_escape(section)}<br>"
            f"定位：{_escape(_locator_text(evidence))}<br>"
            f"Chunk：{_escape(evidence.get('chunk_id'))} "
            f"({_escape(evidence.get('chunk_type'))})<br>"
            f"{card_parts}"
            f"{quality}"
            f"</div>"
            f'<div class="exo-text">{_escape(evidence.get("text"))}</div>'
            f'<div class="exo-rank">{_escape(_rank_text(evidence))}</div>'
            f"</div>"
            f"</details>"
        )
    return '<div class="exo-evidence">' + "".join(cards) + "</div>"


def _render_status(packet: Mapping[str, Any], elapsed_ms: float) -> str:
    icon, label = STATUS_META.get(
        packet.get("status", ""), ("ℹ️", str(packet.get("status", "未知")))
    )
    return f"### {icon} {label}\n`{elapsed_ms:.0f} ms`"


def _render_answer(packet: Mapping[str, Any]) -> str:
    answer = (packet.get("answer") or "").strip()
    if answer:
        if packet.get("status") == "partial":
            return "> 以下为产品目录中可确认的部分。\n\n" + answer
        return answer
    reason = (packet.get("refusal_reason") or "没有生成答案").strip()
    return f"> {reason}"


def _render_meta(packet: Mapping[str, Any]) -> str:
    citations = packet.get("citations") or []
    citation_text = "、".join(f"`{item}`" for item in citations) or "无"
    analysis = packet.get("analysis") or {}
    rows = [
        f"**引用**：{citation_text}",
        f"**生成模式**：`{packet.get('generation_mode', '-')}`",
    ]
    intent = analysis.get("intent")
    if intent:
        rows.append(f"**问题意图**：`{intent}`")
    products = analysis.get("product_ids") or []
    if products:
        rows.append("**识别产品**：" + "、".join(f"`{item}`" for item in products))
    missing = packet.get("missing_parts") or []
    if missing:
        rows.append("**缺失字段**：" + "；".join(str(item) for item in missing))
    notes = packet.get("notes") or []
    if notes:
        rows.append("**质量提示**：" + "；".join(str(item) for item in notes))
    evidence = packet.get("evidence") or []
    rows.append(f"**证据数量**：{len(evidence)}")
    return "　".join(rows[:2]) + "\n\n" + "　".join(rows[2:])


def answer_query(query: str) -> tuple[str, str, str, str, dict[str, Any]]:
    query = (query or "").strip()
    if not query:
        return (
            "### ⚠️ 请输入问题",
            "> 例如：C615 和 C616 的电池与续航有什么区别？",
            "",
            '<div class="exo-empty">还没有检索证据。</div>',
            {},
        )
    started = time.perf_counter()
    try:
        packet = get_answer_service().ask(query, top_k=MAX_EVIDENCE)
    except Exception as exc:  # noqa: BLE001 - surface a safe UI error
        elapsed_ms = (time.perf_counter() - started) * 1000
        message = f"服务调用失败：{type(exc).__name__}"
        packet = {
            "query": query,
            "status": "error",
            "answer": "",
            "citations": [],
            "missing_parts": [],
            "notes": [],
            "refusal_reason": message,
            "generation_mode": "unknown",
            "analysis": {},
            "evidence": [],
        }
    else:
        elapsed_ms = (time.perf_counter() - started) * 1000
    return (
        _render_status(packet, elapsed_ms),
        _render_answer(packet),
        _render_meta(packet),
        render_evidence_html(packet.get("evidence") or []),
        packet,
    )


def _clear() -> tuple[str, str, str, str, dict[str, Any]]:
    return (
        "",
        "",
        "",
        '<div class="exo-empty">还没有检索证据。</div>',
        {},
    )


def build_ui() -> gr.Blocks:
    with gr.Blocks(
        title="ExoRAG · 工业外骨骼选型问答",
        theme=gr.themes.Soft(),
        css=CUSTOM_CSS,
        fill_width=True,
        analytics_enabled=False,
    ) as demo:
        gr.Markdown(
            "# ExoRAG · 工业外骨骼选型问答\n"
            "基于《工业外骨骼产品目录》的混合检索、重排与受约束生成。"
            "答案中的 `[E1]`、`[E2]` 可在下方证据卡中逐条核对。",
            elem_classes=["exo-header"],
        )
        gr.Markdown(
            "`MySQL 精确检索` · `BM25F` · `Qdrant 向量召回` · `BGE Reranker` · `qwen-max`",
            elem_classes=["exo-subtitle"],
        )

        with gr.Row():
            with gr.Column(scale=5):
                query = gr.Textbox(
                    label="你的问题",
                    placeholder="例如：C615 和 C616 的电池与续航有什么区别？",
                    lines=3,
                    max_lines=6,
                )
                with gr.Row():
                    ask_button = gr.Button("提问", variant="primary", scale=3)
                    clear_button = gr.Button("清空", scale=1)
                gr.Examples(
                    examples=[
                        ["C615 的续航时间是多少？"],
                        ["C615 和 C616 的电池与续航有什么区别？"],
                        ["高端电动上肢外骨骼有哪些？"],
                        ["物流搬运与装卸场景推荐哪些产品？"],
                        ["C655 的最大助力到底是多少？"],
                        ["C615 的价格是多少？"],
                    ],
                    inputs=[query],
                    label="示例问题",
                )

            with gr.Column(scale=7):
                status = gr.Markdown("### 等待提问")
                answer = gr.Markdown(
                    "> 输入问题后，这里会显示带 `[E#]` 引用的答案。",
                )
                meta = gr.Markdown("")

        gr.Markdown("## 可溯源证据")
        evidence = gr.HTML(
            '<div class="exo-empty">还没有检索证据。</div>',
        )
        with gr.Accordion("原始返回 JSON", open=False):
            raw_json = gr.JSON(label="Grounded answer packet")

        ask_button.click(
            fn=answer_query,
            inputs=[query],
            outputs=[status, answer, meta, evidence, raw_json],
            api_name="ask_ui",
        )
        query.submit(
            fn=answer_query,
            inputs=[query],
            outputs=[status, answer, meta, evidence, raw_json],
        )
        clear_button.click(
            fn=_clear,
            inputs=None,
            outputs=[status, answer, meta, evidence, raw_json],
        )
    return demo.queue(default_concurrency_limit=1)


def mount_ui(app: Any) -> Any:
    return gr.mount_gradio_app(app, build_ui(), path="/ui")
