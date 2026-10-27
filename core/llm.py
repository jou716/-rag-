from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass


class LLMError(RuntimeError):
    pass


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    api_key: str
    model: str
    timeout_seconds: int = 90


class OpenAICompatibleClient:
    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        url = self.config.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.config.model,
            "temperature": 0.0,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.config.timeout_seconds
            ) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise LLMError(f"LLM request failed: {type(exc).__name__}") from exc
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("LLM response does not contain message content") from exc
        if not isinstance(content, str) or not content.strip():
            raise LLMError("LLM returned an empty answer")
        return content.strip()
