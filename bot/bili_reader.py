"""Bilibili search / video reader for Mocha.

Uses bilibili-api-python; credentials are produced by scripts/bili_login.py.
"""
from __future__ import annotations

import asyncio
import html
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import aiohttp
from bilibili_api import Credential, search, video

BILI_BV_RE = re.compile(r"BV[0-9A-Za-z]{10}")
BILI_URL_RE = re.compile(r"https?://(?:b23\.tv|bilibili\.com/video)/\S+", re.I)
_CACHE: dict[str, tuple[float, dict]] = {}


class BiliError(Exception):
    pass


def load_credential(path: Path) -> Credential | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or not data.get("sessdata"):
        return None
    return Credential(
        sessdata=str(data.get("sessdata") or ""),
        bili_jct=str(data.get("bili_jct") or ""),
        buvid3=str(data.get("buvid3") or ""),
        dedeuserid=str(data.get("dedeuserid") or ""),
        ac_time_value=str(data.get("ac_time_value") or ""),
    )


def extract_bvid(text: str) -> str:
    match = BILI_BV_RE.search(str(text or ""))
    if match:
        return match.group(0)
    url_match = BILI_URL_RE.search(str(text or ""))
    if not url_match:
        return ""
    url = url_match.group(0).rstrip("。，,.)）]")
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=12) as response:
            final = response.geturl()
        match = BILI_BV_RE.search(final)
        return match.group(0) if match else ""
    except Exception:  # noqa: BLE001
        return ""


def _plain(text: Any) -> str:
    value = re.sub(r"<[^>]+>", "", str(text or ""))
    return " ".join(html.unescape(value).split())


async def _search(keyword: str, limit: int = 5) -> list[dict]:
    result = await search.search_by_type(
        keyword=keyword,
        search_type=search.SearchObjectType.VIDEO,
        page=1,
    )
    items = []
    for item in (result.get("result") or [])[:limit]:
        bvid = str(item.get("bvid") or "")
        if not bvid:
            continue
        items.append({
            "bvid": bvid,
            "title": _plain(item.get("title")),
            "author": _plain(item.get("author")),
            "play": item.get("play"),
            "duration": item.get("duration"),
            "description": _plain(item.get("description")),
        })
    return items


async def _subtitle(video_obj: video.Video, info: dict) -> str:
    cid = info.get("cid") or 0
    if not cid and info.get("pages"):
        cid = info["pages"][0].get("cid") or 0
    if not cid:
        return ""
    data = await video_obj.get_subtitle(cid=cid)
    subtitles = data.get("subtitles") or []
    if not subtitles:
        return ""
    target = next(
        (item for item in subtitles if item.get("lan") in ("ai-zh", "zh-CN", "zh")),
        subtitles[0],
    )
    url = str(target.get("subtitle_url") or "")
    if url.startswith("//"):
        url = "https:" + url
    if not url:
        return ""
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=20) as response:
            payload = await response.json()
    lines = [
        str(item.get("content") or "")
        for item in payload.get("body", [])
        if item.get("content")
    ]
    return "\n".join(lines)[:20000]


async def _read(bvid: str, credential: Credential | None) -> dict:
    video_obj = video.Video(bvid=bvid, credential=credential)
    info = await video_obj.get_info()
    desc = _plain(info.get("desc"))
    subtitle = ""
    subtitle_error = ""
    if credential is not None:
        try:
            subtitle = await _subtitle(video_obj, info)
        except Exception as exc:  # noqa: BLE001
            subtitle_error = type(exc).__name__
    else:
        subtitle_error = "未登录 B站，读不到字幕"
    return {
        "bvid": bvid,
        "title": _plain(info.get("title")),
        "author": _plain((info.get("owner") or {}).get("name")),
        "duration": info.get("duration"),
        "desc": desc[:4000],
        "subtitle": subtitle,
        "subtitle_error": subtitle_error,
    }


class BiliReader:
    def __init__(self, credential_path: Path, cache_ttl: int = 1800,
                 fallback_path: Path | None = None):
        self.credential_path = Path(credential_path)
        self.fallback_path = Path(fallback_path) if fallback_path else None
        self.cache_ttl = max(60, int(cache_ttl))

    def credential(self) -> Credential | None:
        credential = load_credential(self.credential_path)
        if credential is None and self.fallback_path is not None:
            credential = load_credential(self.fallback_path)
        return credential

    def search(self, keyword: str, limit: int = 5) -> list[dict]:
        key = "search:" + keyword.strip().lower() + f":{limit}"
        cached = _CACHE.get(key)
        if cached and time.time() - cached[0] < self.cache_ttl:
            return cached[1]
        try:
            items = asyncio.run(_search(keyword, limit))
        except Exception as exc:  # noqa: BLE001
            raise BiliError(f"B站搜索失败：{exc}") from exc
        _CACHE[key] = (time.time(), items)
        return items

    def read(self, bvid: str) -> dict:
        key = "video:" + bvid
        cached = _CACHE.get(key)
        if cached and time.time() - cached[0] < self.cache_ttl:
            return cached[1]
        try:
            data = asyncio.run(_read(bvid, self.credential()))
        except Exception as exc:  # noqa: BLE001
            raise BiliError(f"读取B站视频失败：{exc}") from exc
        _CACHE[key] = (time.time(), data)
        return data


def resolve_bvid(text: str) -> str:
    return extract_bvid(text)
