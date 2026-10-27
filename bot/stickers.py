from __future__ import annotations

import base64
import hashlib
import json
import logging
import random
import urllib.request
from collections import Counter
from pathlib import Path

from .llm import LLMError, parse_json_object
from .util import atomic_write_json, now_iso

logger = logging.getLogger(__name__)

EMOTIONS = [
    "开心", "得意", "偷笑", "无语", "疑惑", "困", "饿",
    "害羞", "生气", "难过", "惊讶", "敷衍", "可爱", "其他",
]
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}

ANALYZE_SYSTEM = """你是 QQ 表情包分类器。看图片，判断它在群聊里表达的情绪和适用场景。
只输出一个 JSON 对象，不要解释、不要 Markdown：
{
  "emotion": "开心|得意|偷笑|无语|疑惑|困|饿|害羞|生气|难过|惊讶|敷衍|可爱|其他",
  "tags": ["最多4个短词"],
  "description": "不超过30字",
  "is_meme": true,
  "safe": true
}
`is_meme` 表示这张图是否适合当聊天表情包（反应图、梗图、角色表情）；
照片、截图、长图、文档、聊天记录一律 false。
安全规则（按普通 QQ 群标准）：
- 性暗示、胸部/内衣/本子/成人梗、擦边内容 → safe=false
- 脏话、辱骂、挑衅、血腥、政治、广告 → safe=false
- 只有普通动漫/角色反应图、可爱/搞笑图才给 safe=true"""


def _mime(data: bytes) -> str:
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if data.startswith(b"GIF8"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def _ext(data: bytes) -> str:
    return {
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
    }.get(_mime(data), ".jpg")


class StickerLibrary:
    def __init__(self, root: Path, llm, timezone: str = "Asia/Shanghai"):
        self.root = Path(root)
        self.dir = self.root / "stickers"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.dir / "index.json"
        self.llm = llm
        self.timezone = timezone
        self.last_usage = {"input": 0, "output": 0}
        self.index = self._load()
        self._mtime = self._index_mtime()

    def _index_mtime(self) -> float:
        try:
            return self.index_path.stat().st_mtime
        except OSError:
            return 0.0

    def _refresh(self) -> None:
        mtime = self._index_mtime()
        if mtime != self._mtime:
            self.index = self._load()
            self._mtime = mtime

    # ---------- index ----------

    def _load(self) -> dict:
        if not self.index_path.exists():
            return {"version": 1, "updated_at": "", "items": {}}
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            logger.exception("表情索引损坏，重建空索引")
            return {"version": 1, "updated_at": "", "items": {}}
        if not isinstance(data, dict) or not isinstance(data.get("items"), dict):
            return {"version": 1, "updated_at": "", "items": {}}
        return data

    def _save(self) -> None:
        self.index["updated_at"] = now_iso(self.timezone)
        atomic_write_json(self.index_path, self.index)
        self._mtime = self._index_mtime()

    @property
    def items(self) -> dict:
        self._refresh()
        return self.index.get("items", {})

    def has_items(self) -> bool:
        return bool(self.usable_items())

    def usable_items(self) -> list[dict]:
        self._refresh()
        result = []
        for item in self.items.values():
            if not item.get("safe", True):
                continue
            if item.get("is_meme") is False:
                continue
            path = self.dir / str(item.get("file", ""))
            if item.get("file") and path.exists():
                result.append(item)
        return result

    def path(self, item: dict) -> Path:
        return self.dir / str(item["file"])

    def available_tags(self, limit: int = 15) -> list[str]:
        counter: Counter[str] = Counter()
        for item in self.usable_items():
            emotion = str(item.get("emotion") or "其他")
            counter[emotion] += 1
            for tag in item.get("tags", [])[:4]:
                tag = str(tag).strip()
                if tag:
                    counter[tag] += 1
        return [name for name, _ in counter.most_common(limit)]

    def pick(self, tag: str) -> dict | None:
        target = str(tag or "").strip().lower()
        if not target:
            return None
        candidates = []
        for item in self.usable_items():
            emotion = str(item.get("emotion") or "").lower()
            tags = [str(t).lower() for t in item.get("tags", [])]
            if emotion == target or target in tags:
                candidates.append(item)
        return random.choice(candidates) if candidates else None

    def pick_for_text(self, text: str) -> dict | None:
        lowered = (text or "").lower()
        hints = [
            (("笑", "哈", "草", "乐", "233"), "开心"),
            (("无语", "白", "啧", "服了", "离谱"), "无语"),
            (("困", "睡", "累", "瘫"), "困"),
            (("饿", "吃", "面包", "馋", "山吹"), "饿"),
            (("?", "？", "问", "疑", "为什么"), "疑惑"),
            (("得意", "赢", "厉害", "牛", "赚"), "得意"),
            (("生气", "怒", "气", "烦"), "生气"),
            (("难过", "哭", "呜", "委屈"), "难过"),
            (("可爱", "害羞", "羞", "萌"), "害羞"),
            (("惊", "卧槽", "啊", "居然"), "惊讶"),
        ]
        for words, emotion in hints:
            if any(word in lowered for word in words):
                item = self.pick(emotion)
                if item:
                    return item
        return None

    def stats(self) -> dict:
        items = list(self.items.values())
        emotions = Counter(str(i.get("emotion") or "其他") for i in items)
        return {
            "count": len(items),
            "usable": len(self.usable_items()),
            "emotions": dict(emotions.most_common(10)),
            "updated_at": self.index.get("updated_at") or "从未同步",
            "dir": str(self.dir),
        }

    # ---------- import ----------

    def sync_from_napcat(self, sender, count: int = 48) -> dict:
        details = sender.fetch_custom_faces(count)
        self.last_usage = {"input": 0, "output": 0}
        counts = {"total": len(details), "added": 0, "skipped": 0,
                  "failed": 0, "analyzed": 0}
        for detail in details:
            md5 = str(detail.get("md5") or "").upper()
            url = str(detail.get("url") or "")
            if not md5:
                md5 = hashlib.md5((url or str(detail)).encode("utf-8")).hexdigest().upper()
            if md5 in self.items:
                counts["skipped"] += 1
                continue
            data = self._download(url) if url else None
            if data is None:
                for key in ("emoPath", "thumbPath"):
                    data = self._read_local(str(detail.get(key) or ""))
                    if data:
                        break
            if not data:
                counts["failed"] += 1
                continue
            path = self.dir / f"{md5}{_ext(data)}"
            path.write_bytes(data)
            meta = self.analyze_file(path)
            if meta is None:
                counts["failed"] += 1
                try:
                    path.unlink()
                except OSError:
                    pass
                continue
            self.items[md5] = {
                "file": path.name,
                "md5": md5,
                "emotion": meta["emotion"],
                "tags": meta["tags"],
                "description": meta["description"],
                "is_meme": meta["is_meme"],
                "safe": meta["safe"],
                "source": "qq_favorite",
                "url": url,
                "res_id": detail.get("resId") or "",
                "added_at": now_iso(self.timezone),
            }
            counts["added"] += 1
            counts["analyzed"] += 1
        self._save()
        counts["usage"] = dict(self.last_usage)
        return counts

    def scan_local(self) -> dict:
        self.last_usage = {"input": 0, "output": 0}
        counts = {"found": 0, "added": 0, "skipped": 0, "failed": 0}
        for path in sorted(self.dir.iterdir()):
            if not path.is_file() or path.suffix.lower() not in IMAGE_EXTS:
                continue
            counts["found"] += 1
            data = path.read_bytes()
            md5 = hashlib.md5(data).hexdigest().upper()
            if md5 in self.items:
                counts["skipped"] += 1
                continue
            meta = self.analyze_file(path)
            if meta is None:
                counts["failed"] += 1
                continue
            self.items[md5] = {
                "file": path.name,
                "md5": md5,
                **meta,
                "source": "local",
                "url": "",
                "res_id": "",
                "added_at": now_iso(self.timezone),
            }
            counts["added"] += 1
        self._save()
        counts["usage"] = dict(self.last_usage)
        return counts

    # ---------- analysis ----------

    def analyze_file(self, path: Path) -> dict | None:
        try:
            data = path.read_bytes()
        except OSError:
            return None
        mime = _mime(data)
        data_uri = f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
        messages = [
            {"role": "system", "content": ANALYZE_SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "分析这张 QQ 表情包，只输出 JSON。"},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            },
        ]
        try:
            text, usage = self.llm.chat(messages, max_tokens=220, temperature=0.2)
            self.last_usage["input"] += int(usage.get("input", 0))
            self.last_usage["output"] += int(usage.get("output", 0))
            raw = parse_json_object(text)
        except (LLMError, ValueError) as exc:
            logger.warning("表情分析失败 %s：%s", path.name, exc)
            return None

        emotion = str(raw.get("emotion") or "其他").strip()
        if emotion not in EMOTIONS:
            emotion = "其他"
        tags = raw.get("tags") or []
        if isinstance(tags, str):
            tags = [tags]
        tags = [str(tag).strip()[:12] for tag in tags if str(tag).strip()][:4]
        description = str(raw.get("description") or "").strip()[:60]
        is_meme = bool(raw.get("is_meme", False))
        safe_raw = raw.get("safe", True)
        if isinstance(safe_raw, str):
            safe = safe_raw.strip().lower() not in {"false", "0", "no", "不安全"}
        else:
            safe = bool(safe_raw)
        return {
            "emotion": emotion,
            "tags": tags,
            "description": description,
            "is_meme": is_meme,
            "safe": safe,
        }

    # ---------- helpers ----------

    def _download(self, url: str) -> bytes | None:
        if not (url.startswith("http://") or url.startswith("https://")):
            return None
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=15) as resp:
                data = resp.read(8_000_000)
            return data or None
        except OSError as exc:
            logger.warning("下载表情失败 %s：%s", url[:80], exc)
            return None

    def _read_local(self, value: str) -> bytes | None:
        if not value:
            return None
        try:
            path = Path(value)
            if path.exists() and path.is_file():
                return path.read_bytes()
        except OSError:
            pass
        return None
