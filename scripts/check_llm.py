from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from core.llm import LLMConfig, LLMError, OpenAICompatibleClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Check the configured LLM endpoint")
    parser.add_argument("--model", default=settings.llm_model)
    args = parser.parse_args()
    client = OpenAICompatibleClient(
        LLMConfig(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=args.model,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    )
    started = time.perf_counter()
    try:
        answer = client.generate("你是连通性测试助手。", "只输出四个字：连接成功")
    except LLMError as exc:
        print(f"model={args.model} failed: {exc}")
        raise SystemExit(1)
    elapsed = (time.perf_counter() - started) * 1000
    print(f"model={args.model} latency_ms={elapsed:.0f} output={answer}")


if __name__ == "__main__":
    main()
