from __future__ import annotations

from typing import Any, Mapping, Sequence

SYSTEM_PROMPT = """你是工业外骨骼产品目录问答助手。
只能使用用户消息中提供的证据回答，不得使用外部知识，不得猜测或补写。
每个事实性段落至少标注一个对应的证据编号，例如 [E1] 或 [E1][E2]。
每个列表项都应尽量在行尾标注引用；如果整个列表都来自同一段证据，可以在该列表最后一项统一标注一次。
不要使用 [E1–E5] 这类范围引用，需要多个证据时逐个写 [E1][E2][E3]。
证据没有覆盖的字段必须明确写“产品目录未提供”，不能硬答。
如果用户只询问价格、认证、蓝牙等目录未提供的字段，只说明该字段缺失，不要顺手输出整份产品概览。
如果问题同时包含可回答字段和未提供字段，先回答已有证据支持的部分，再说明缺失部分。
如果证据的质量状态为 needs_review，或质量标记非空，必须明确说明冲突、缺失或需要人工复核，不能只给单一数值。
如果同一字段在证据中出现多个冲突值，必须把证据中的各个值全部列出，再说明需要复核。
如果问题要求列举（例如“有哪些”“列出”“都有哪些”），必须把证据中所有符合条件的产品全部列出，不能只挑其中几款；同一产品有多条证据时合并为一条，不要重复。
不要输出证据编号范围之外的引用，不要篡改数字、单位、产品号或原文条件。
"""


def build_evidence_context(evidence_items: Sequence[Mapping[str, Any]]) -> str:
    blocks: list[str] = []
    for evidence in evidence_items:
        section = " > ".join(evidence.get("section_path") or [])
        quality_status = evidence.get("quality_status") or "normal"
        quality_flags = ", ".join(evidence.get("quality_flags") or []) or "none"
        blocks.append(
            f"[{evidence['evidence_id']}] {evidence.get('title', '')}\n"
            f"章节：{section}\n"
            f"质量状态：{quality_status}\n"
            f"质量标记：{quality_flags}\n"
            f"{evidence.get('text', '')}"
        )
    return "\n\n".join(blocks)


def build_llm_messages(
    query: str, evidence_items: Sequence[Mapping[str, Any]]
) -> tuple[str, str]:
    user_prompt = (
        f"问题：{query}\n\n"
        f"可用证据：\n{build_evidence_context(evidence_items)}\n\n"
        "请给出简洁、可核对的中文答案。"
    )
    return SYSTEM_PROMPT, user_prompt
