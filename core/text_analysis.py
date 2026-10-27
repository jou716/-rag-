from __future__ import annotations

import re
import unicodedata

CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]+")
ALNUM_RE = re.compile(r"[a-z0-9]+(?:[._-][a-z0-9]+)*")
NUMBER_UNIT_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(kgf|kg|g|n·m|wh|mah|cm|mm|n|v|h|s|%|小时|秒|次|档)",
    re.IGNORECASE,
)

STOPWORDS = {
    "的",
    "了",
    "是",
    "在",
    "和",
    "与",
    "及",
    "或",
    "有",
    "无",
    "为",
    "对",
    "把",
    "将",
    "中",
    "个",
    "款",
    "请",
    "问",
    "吗",
    "呢",
    "啊",
    "什么",
    "多少",
    "哪些",
    "哪个",
    "怎么",
    "如何",
    "是否",
    "可以",
    "以及",
    "这个",
    "那个",
    "我们",
    "你们",
    "他们",
    "一下",
    "请问",
    "多",
    "少",
    "哪",
    "些",
    "什",
    "么",
    "怎",
    "样",
}

BIGRAM_STOP_CHARS = set(STOPWORDS) - {"中"}


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).lower()
    return (
        normalized.replace("－", "-")
        .replace("–", "-")
        .replace("—", "-")
        .replace("～", "~")
        .replace("（", "(")
        .replace("）", ")")
        .replace("，", ",")
        .replace("、", ",")
    )


def tokenize(text: str) -> list[str]:
    normalized = normalize_text(text)
    tokens: list[str] = []

    for match in NUMBER_UNIT_RE.finditer(normalized):
        number, unit = match.groups()
        tokens.append(f"{number}{unit}")

    for match in ALNUM_RE.finditer(normalized):
        token = match.group(0)
        if token not in STOPWORDS:
            tokens.append(token)

    for run in CJK_RUN_RE.findall(normalized):
        for char in run:
            if char not in STOPWORDS:
                tokens.append(char)
        for index in range(len(run) - 1):
            bigram = run[index : index + 2]
            if bigram not in STOPWORDS and not (set(bigram) & BIGRAM_STOP_CHARS):
                tokens.append(bigram)

    return tokens
