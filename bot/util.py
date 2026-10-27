from __future__ import annotations

import json
import os
import tempfile
import unicodedata
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

DEFAULT_TZ = "Asia/Shanghai"


def now_iso(tz: str = DEFAULT_TZ) -> str:
    return datetime.now(ZoneInfo(tz)).isoformat(timespec="seconds")


def today_str(tz: str = DEFAULT_TZ) -> str:
    return datetime.now(ZoneInfo(tz)).strftime("%Y-%m-%d")


def atomic_write_text(path: Path, text: str) -> None:
    """先写临时文件再替换，避免断电/崩溃留下半个 JSON。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=path.suffix)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def atomic_write_json(path: Path, data) -> None:
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def norm_text(value: object) -> str:
    """归一化：全角转半角、压缩空白、英文小写。只用于比较，不用于展示。"""
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = " ".join(text.split())
    return text.strip().lower()


def clean_value(value: object, limit: int = 500) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return None
    text = " ".join(str(value).split()).strip()
    if not text:
        return None
    return text[:limit]


def split_message(text: str, limit: int = 1200) -> list[str]:
    """按行切分长回复，QQ 单条消息不要过长。"""
    text = text.strip()
    if len(text) <= limit:
        return [text] if text else []
    chunks: list[str] = []
    buf = ""
    for line in text.splitlines():
        while len(line) > limit:
            if buf:
                chunks.append(buf)
                buf = ""
            chunks.append(line[:limit])
            line = line[limit:]
        if len(buf) + len(line) + 1 > limit:
            chunks.append(buf)
            buf = line
        else:
            buf = f"{buf}\n{line}" if buf else line
    if buf:
        chunks.append(buf)
    return chunks


def short(text: str, limit: int = 60) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
