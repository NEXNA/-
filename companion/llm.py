"""DeepSeek OpenAI-compatible chat client (stdlib only)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request


class LLMError(Exception):
    pass


class DeepSeekClient:
    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com",
                 model: str = "deepseek-chat", timeout: int = 60):
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def chat(self, messages: list[dict], temperature: float = 0.9,
             max_tokens: int = 600) -> str:
        if not self.api_key:
            raise LLMError("没有配置 DEEPSEEK_API_KEY")
        body = json.dumps({
            "model": self.model,
            "messages": messages,
            "temperature": max(0.0, min(2.0, float(temperature))),
            "max_tokens": max(64, min(4096, int(max_tokens))),
            "stream": False,
        }).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + "/chat/completions", data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise LLMError(f"DeepSeek HTTP {exc.code}: {detail}") from exc
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"连接 DeepSeek 失败：{exc}") from exc
        try:
            data = json.loads(raw)
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise LLMError(f"DeepSeek 返回格式异常：{raw[:300]}") from exc
        return str(content or "").strip()
