"""Qwen TTS client for Mocha's optional group voice."""
from __future__ import annotations

import hashlib
import json
import logging
import re
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)


class QwenTTSError(Exception):
    pass


def clean_for_tts(text: str) -> str:
    value = str(text or "")
    value = re.sub(r"\[\[[^\]]+\]\]", " ", value)
    value = re.sub(r"\[CQ:[^\]]+\]", " ", value)
    value = re.sub(r"https?://\S+", " ", value)
    value = re.sub(r"[`*_#>|]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:80]


class QwenTTS:
    def __init__(self, api_url: str, model: str, voice: str,
                 response_format: str = "wav", timeout: int = 300,
                 cache_dir: Path | None = None,
                 max_chars: int = 80):
        self.api_url = api_url.rstrip("/")
        self.model = model
        self.voice = voice
        self.response_format = response_format
        self.timeout = max(10, int(timeout))
        self.max_chars = max(1, int(max_chars))
        self.cache_dir = Path(cache_dir or "data/voice_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def synthesize(self, text: str) -> Path:
        value = clean_for_tts(text)[: self.max_chars]
        if not value:
            raise QwenTTSError("语音文本为空")
        key = hashlib.sha256(
            f"{self.model}|{self.voice}|{self.response_format}|{value}".encode("utf-8")
        ).hexdigest()[:24]
        suffix = "wav" if self.response_format == "wav" else self.response_format
        target = self.cache_dir / f"{key}.{suffix}"
        if target.is_file() and target.stat().st_size > 1000:
            return target
        body = json.dumps({
            "model": self.model,
            "voice": self.voice,
            "input": value,
            "response_format": self.response_format,
            "language": "chinese",
        }).encode("utf-8")
        request = urllib.request.Request(
            self.api_url, data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = response.read()
                content_type = (response.headers.get("Content-Type") or "").lower()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise QwenTTSError(f"Qwen TTS HTTP {exc.code}: {detail}") from exc
        except Exception as exc:  # noqa: BLE001
            raise QwenTTSError(f"Qwen TTS 连接失败：{exc}") from exc
        if not data or "audio" not in content_type:
            raise QwenTTSError(f"Qwen TTS 没有返回音频：{content_type}")
        target.write_bytes(data)
        return target

    def warm(self) -> bool:
        try:
            self.synthesize("嗯")
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Qwen TTS 预热失败：%s", exc)
            return False
