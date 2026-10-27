"""从 B 站公开搜索页抓二次元图，存到本地 stickers/bilibili/。

不登录、不绕过验证：只用公开的搜索/封面接口，拿不到就跳过。
"""

from __future__ import annotations

import base64
import hashlib
import html
import io
import json
import logging
import random
import re
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageStat

from .util import now_iso

logger = logging.getLogger(__name__)

DEFAULT_KEYWORDS = [
    "二次元 表情包",
    "动漫 表情包",
    "二次元 梗图",
    "动漫 沙雕表情包",
]
MAX_IMAGE_BYTES = 5 * 1024 * 1024
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) qq-setting-bot/1.0"


class BiliImageError(Exception):
    pass


class BiliImageStore:
    def __init__(self, root: Path, limit: int = 2000,
                 timezone: str = "Asia/Shanghai", api_key: str = "",
                 base_url: str = "https://api.deepseek.com",
                 model: str = "deepseek-chat"):
        self.root = Path(root)
        self.dir = self.root / "stickers" / "bilibili"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.dir / "index.json"
        self.limit = max(1, int(limit))
        self.timezone = timezone
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._lock = threading.RLock()

    # ---------- index ----------

    def _load(self) -> dict:
        if not self.index_path.exists():
            return {"version": 1, "items": []}
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return {"version": 1, "items": []}
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            return {"version": 1, "items": []}
        return data

    def _save(self, data: dict) -> None:
        tmp = self.index_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.index_path)

    def count(self) -> int:
        with self._lock:
            return len(self._load()["items"])

    def status(self) -> dict:
        with self._lock:
            data = self._load()
            items = data["items"]
            return {
                "count": len(items),
                "usable": sum(1 for item in items if item.get("usable") is True),
                "classified": sum(1 for item in items if "classified_at" in item),
                "limit": self.limit,
                "path": str(self.dir),
            }

    def random_image(self, quality_only: bool = True) -> Path | None:
        with self._lock:
            items = self._load()["items"]
        random.shuffle(items)
        for item in items:
            if quality_only and item.get("usable") is not True:
                continue
            path = self.dir / str(item.get("file") or "")
            if path.is_file():
                return path
        return None

    def pick_for_text(self, text: str) -> Path | None:
        """按关键词/标签挑图；对不上就不发，避免随机无关图。"""
        hay_text = str(text or "").lower()
        tokens: set[str] = set()
        for chunk in re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z]{3,}", hay_text):
            if re.fullmatch(r"[a-zA-Z]+", chunk):
                tokens.add(chunk)
                continue
            for size in (2, 3, 4):
                for start in range(0, max(0, len(chunk) - size + 1)):
                    tokens.add(chunk[start:start + size])
        if not tokens:
            return None
        with self._lock:
            items = [dict(item) for item in self._load()["items"]]
        scored = []
        for item in items:
            if item.get("usable") is False:
                continue
            hay = " ".join(
                str(item.get(key) or "") for key in ("caption", "tags", "title", "keyword")
            ).lower()
            score = sum(1 for token in tokens if token in hay)
            if score:
                scored.append((score + random.random() * 0.5, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        for _, item in scored:
            path = self.dir / str(item.get("file") or "")
            if path.is_file():
                return path
        return None

    # ---------- quality / vision ----------

    def _inspect(self, data: bytes) -> dict | None:
        try:
            with Image.open(io.BytesIO(data)) as image:
                width, height = image.size
                if width < 160 or height < 160 or width * height < 40_000:
                    return None
                if width / max(1, height) > 5 or height / max(1, width) > 5:
                    return None
                gray = image.convert("L")
                variance = ImageStat.Stat(gray).var[0]
                if variance < 10:
                    return None
                small = gray.resize((8, 8))
                pixels = list(small.getdata())
                average = sum(pixels) / len(pixels)
                bits = "".join("1" if p >= average else "0" for p in pixels)
                phash = f"{int(bits, 2):016x}"
                return {"width": width, "height": height, "phash": phash}
        except Exception as exc:  # noqa: BLE001
            logger.warning("图片质量检查失败：%s", exc)
            return None

    @staticmethod
    def _phash_distance(a: str, b: str) -> int:
        try:
            return (int(a, 16) ^ int(b, 16)).bit_count()
        except (TypeError, ValueError):
            return 99

    def classify(self, path: Path) -> dict:
        if not self.api_key:
            return {}
        data = Path(path).read_bytes()
        kind = _image_kind(data) or "jpeg"
        mime = {"jpeg": "image/jpeg", "png": "image/png",
                "gif": "image/gif", "webp": "image/webp"}[kind]
        uri = f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
        prompt = (
            "只输出 JSON，不要解释："
            '{"usable":true/false,"meaning":"一句话画面内容",'
            '"tags":["3个中文标签"],"mood":"情绪"}。'
            "判断这张图是否适合做 QQ 聊天配图；纯文字截图、广告、"
            "空白、二维码、无意义封面、低信息量为 false。"
        )
        body = json.dumps({
            "model": self.model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": uri}},
                ],
            }],
            "max_tokens": 220,
            "temperature": 0.2,
        }).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + "/chat/completions", data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8", "replace")
        data = json.loads(raw)
        content = str(data["choices"][0]["message"]["content"] or "")
        start, end = content.find("{"), content.rfind("}")
        if start < 0 or end <= start:
            return {}
        parsed = json.loads(content[start:end + 1])
        return parsed if isinstance(parsed, dict) else {}

    def classify_item(self, item: dict) -> bool:
        path = self.dir / str(item.get("file") or "")
        if not path.is_file():
            return False
        try:
            info = self.classify(path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("图片分类失败：%s", exc)
            return True
        if not info:
            return True
        usable = bool(info.get("usable", True))
        with self._lock:
            index = self._load()
            for current in index["items"]:
                if current.get("hash") == item.get("hash"):
                    current["usable"] = usable
                    current["caption"] = str(info.get("meaning") or "")[:200]
                    current["tags"] = " ".join(
                        str(tag) for tag in (info.get("tags") or [])[:5]
                    )
                    current["mood"] = str(info.get("mood") or "")[:40]
                    current["classified_at"] = now_iso(self.timezone)
                    break
            if not usable:
                index["items"] = [
                    current for current in index["items"]
                    if current.get("hash") != item.get("hash")
                ]
            self._save(index)
        if not usable:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        return usable

    def classify_pending(self, limit: int = 40) -> dict:
        if not self.api_key:
            return {"checked": 0, "removed": 0, "left": self.count()}
        checked = removed = 0
        with self._lock:
            items = [dict(item) for item in self._load()["items"]
                     if "classified_at" not in item]
        for item in items:
            if checked >= max(1, limit):
                break
            checked += 1
            if not self.classify_item(item):
                removed += 1
        return {"checked": checked, "removed": removed, "left": self.count()}

    # ---------- add ----------

    def add(self, data: bytes, meta: dict) -> dict | None:
        if not data or len(data) > MAX_IMAGE_BYTES:
            return None
        kind = _image_kind(data)
        if kind is None:
            return None
        quality = self._inspect(data)
        if quality is None:
            return None
        digest = hashlib.sha256(data).hexdigest()
        with self._lock:
            index = self._load()
            if len(index["items"]) >= self.limit:
                return None
            if any(item.get("hash") == digest for item in index["items"]):
                return None
            for item in index["items"]:
                old = str(item.get("phash") or "")
                if old and self._phash_distance(old, quality["phash"]) <= 4:
                    return None
            ext = {"jpeg": "jpg", "png": "png", "gif": "gif", "webp": "webp"}[kind]
            filename = f"bili-{digest[:16]}.{ext}"
            path = self.dir / filename
            if not path.exists():
                path.write_bytes(data)
            item = {
                "file": filename,
                "hash": digest,
                "phash": quality["phash"],
                "width": quality["width"],
                "height": quality["height"],
                "url": str(meta.get("url") or ""),
                "title": str(meta.get("title") or "")[:200],
                "keyword": str(meta.get("keyword") or "")[:100],
                "tags": str(meta.get("tags") or "")[:200],
                "added_at": now_iso(self.timezone),
            }
            index["items"].append(item)
            self._save(index)
            return item

    # ---------- fetch ----------

    def fetch(self, keyword: str | None = None, count: int = 10,
              pages: int = 2) -> dict:
        with self._lock:
            current = len(self._load()["items"])
        want = max(1, min(50, int(count)))
        if current >= self.limit:
            return {"added": 0, "skipped": 0, "errors": 0, "count": current,
                    "limit": self.limit, "full": True, "keyword": keyword or ""}

        keywords = [keyword.strip()] if keyword and keyword.strip() else DEFAULT_KEYWORDS
        candidates: list[dict] = []
        seen_urls: set[str] = set()
        errors = 0
        for word in keywords:
            for page in range(1, max(1, min(5, pages)) + 1):
                if len(candidates) >= want * 10:
                    break
                try:
                    results = self._search(word, page)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("B站找图搜索失败（%s/%s）：%s", word, page, exc)
                    errors += 1
                    continue
                for item in results:
                    url = item.get("url")
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    candidates.append(item)
                time.sleep(0.5)

        added = 0
        skipped = 0
        added_files: list[str] = []
        while candidates and added < want and current + added < self.limit:
            item = candidates.pop(0)
            try:
                data = self._download(item["url"])
            except Exception as exc:  # noqa: BLE001
                logger.warning("B站找图下载失败：%s", exc)
                errors += 1
                continue
            if data is None:
                skipped += 1
                continue
            item = self.add(data, item)
            if item is None:
                skipped += 1
            elif self.api_key and not self.classify_item(item):
                skipped += 1
            else:
                added += 1
                added_files.append(str(item.get("file") or ""))
            time.sleep(0.25)

        final = self.count()
        return {
            "added": added,
            "skipped": skipped,
            "errors": errors,
            "count": final,
            "limit": self.limit,
            "full": final >= self.limit,
            "keyword": keyword or "默认二次元关键词",
            "files": added_files,
        }

    def _search(self, keyword: str, page: int) -> list[dict]:
        """优先搜专栏封面，失败再退回视频/热门封面；都只取 B 站公开结果。"""
        attempts = (
            lambda: self._search_articles(keyword, page),
            lambda: self._search_videos(keyword, page),
            lambda: self._search_popular(page),
        )
        for attempt in attempts:
            try:
                items = attempt()
            except Exception as exc:  # noqa: BLE001
                logger.warning("B站搜索接口失败：%s", exc)
                continue
            if items:
                return items
        return []

    def _search_popular(self, page: int) -> list[dict]:
        data = self._api_json(
            "https://api.bilibili.com/x/web-interface/popular?"
            + urllib.parse.urlencode({"ps": 30, "pn": page})
        )
        if data.get("code") != 0:
            return []
        rows = (data.get("data") or {}).get("list") or []
        items = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            pic = row.get("pic")
            if isinstance(pic, str) and pic.strip():
                items.append({
                    "url": pic.strip(),
                    "title": _plain_text(row.get("title") or ""),
                    "keyword": "热门",
                })
        return items

    def _api_json(self, url: str) -> dict:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Referer": "https://www.bilibili.com/",
                "Cookie": "buvid3=0",
                "Accept": "application/json,text/plain,*/*",
            },
        )
        with urllib.request.urlopen(request, timeout=12) as response:
            raw = response.read()
        return json.loads(raw.decode("utf-8"))

    def _search_articles(self, keyword: str, page: int) -> list[dict]:
        query = urllib.parse.urlencode({
            "search_type": "article",
            "keyword": keyword,
            "page": page,
        })
        data = self._api_json(
            "https://api.bilibili.com/x/web-interface/search/type?" + query
        )
        if data.get("code") != 0:
            return []
        results = (data.get("data") or {}).get("result") or []
        items = []
        for row in results:
            if not isinstance(row, dict):
                continue
            title = _plain_text(row.get("title") or "")
            urls = row.get("image_urls") or []
            if isinstance(urls, str):
                urls = [urls]
            for url in urls:
                if isinstance(url, str) and url.strip():
                    items.append({"url": url.strip(), "title": title,
                                  "keyword": keyword})
        return items

    def _search_videos(self, keyword: str, page: int) -> list[dict]:
        query = urllib.parse.urlencode({
            "search_type": "video",
            "keyword": keyword,
            "page": page,
        })
        data = self._api_json(
            "https://api.bilibili.com/x/web-interface/search/type?" + query
        )
        if data.get("code") != 0:
            return []
        results = (data.get("data") or {}).get("result") or []
        items = []
        for row in results:
            if not isinstance(row, dict):
                continue
            pic = row.get("pic")
            if isinstance(pic, str) and pic.strip():
                items.append({
                    "url": pic.strip(),
                    "title": _plain_text(row.get("title") or ""),
                    "keyword": keyword,
                })
        return items

    def _download(self, url: str) -> bytes | None:
        if url.startswith("//"):
            url = "https:" + url
        elif url.startswith("http://"):
            url = "https://" + url[len("http://"):]
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or "").lower()
        if not (host == "bilibili.com" or host.endswith(".bilibili.com")
                or host == "hdslb.com" or host.endswith(".hdslb.com")
                or host == "biliimg.com" or host.endswith(".biliimg.com")):
            return None
        request = urllib.request.Request(
            url,
            headers={"User-Agent": USER_AGENT, "Referer": "https://www.bilibili.com/"},
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            content_type = (response.headers.get("Content-Type") or "").lower()
            if "image" not in content_type and not content_type.startswith("application/octet"):
                return None
            data = response.read(MAX_IMAGE_BYTES + 1)
        if len(data) > MAX_IMAGE_BYTES:
            return None
        return data


def _image_kind(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "gif"
    if len(data) > 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def _plain_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", str(text))
    return html.unescape(text).strip()
