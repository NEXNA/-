"""Read and post Bilibili comments as the logged-in Mocha account."""
from __future__ import annotations

import asyncio
import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from bilibili_api import comment, user, video

from .bili_reader import BiliError, load_credential, resolve_bvid


class BiliCommentError(Exception):
    pass


class BiliCommenter:
    def __init__(self, credential_path: Path, fallback_path: Path | None = None,
                 max_chars: int = 100):
        self.credential_path = Path(credential_path)
        self.fallback_path = Path(fallback_path) if fallback_path else None
        self.max_chars = max(20, int(max_chars))
        self._self: dict | None = None

    def credential(self):
        cred = load_credential(self.credential_path)
        if cred is None and self.fallback_path is not None:
            cred = load_credential(self.fallback_path)
        return cred

    def require_credential(self):
        cred = self.credential()
        if cred is None:
            raise BiliCommentError("没登录B站，先扫码登录一次")
        return cred

    def self_info(self) -> dict:
        if self._self is not None:
            return self._self
        async def fetch():
            return await user.get_self_info(self.require_credential())
        try:
            info = asyncio.run(fetch())
        except Exception as exc:  # noqa: BLE001
            raise BiliCommentError(f"读取B站账号失败：{exc}") from exc
        self._self = {
            "mid": int(info.get("mid") or 0),
            "name": str(info.get("name") or ""),
        }
        return self._self

    def comments(self, bvid: str, limit: int = 30) -> list[dict]:
        cred = self.require_credential()
        async def fetch():
            video_obj = video.Video(bvid=bvid, credential=cred)
            info = await video_obj.get_info()
            aid = int(info.get("aid") or 0)
            if not aid:
                raise BiliCommentError("拿不到视频 aid")
            raw: dict[int, dict] = {}
            for order in (comment.OrderType.TIME, comment.OrderType.LIKE):
                data = await comment.get_comments(
                    oid=aid,
                    type_=comment.CommentResourceType.VIDEO,
                    page_index=1,
                    order=order,
                    credential=cred,
                )
                for item in data.get("replies") or []:
                    raw[int(item.get("rpid") or 0)] = item
            items = []
            for item in sorted(
                raw.values(), key=lambda x: int(x.get("ctime") or 0), reverse=True
            )[:limit]:
                member = item.get("member") or {}
                content = item.get("content") or {}
                items.append({
                    "rpid": int(item.get("rpid") or 0),
                    "root": int(item.get("root") or 0),
                    "parent": int(item.get("parent") or 0),
                    "mid": int(member.get("mid") or item.get("mid") or 0),
                    "uname": str(member.get("uname") or ""),
                    "message": str(content.get("message") or ""),
                    "ctime": int(item.get("ctime") or 0),
                })
            return aid, items
        try:
            aid, items = asyncio.run(fetch())
        except BiliCommentError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise BiliCommentError(f"读取B站评论失败：{exc}") from exc
        return items

    def post(self, bvid: str, text: str, root: int = 0,
             parent: int = 0) -> dict:
        value = " ".join(str(text or "").split()).strip()[: self.max_chars]
        if not value:
            raise BiliCommentError("评论内容为空")
        cred = self.require_credential()
        async def send():
            video_obj = video.Video(bvid=bvid, credential=cred)
            info = await video_obj.get_info()
            aid = int(info.get("aid") or 0)
            if not aid:
                raise BiliCommentError("拿不到视频 aid")
            return await comment.send_comment(
                text=value,
                oid=aid,
                type_=comment.CommentResourceType.VIDEO,
                root=root or None,
                parent=parent or None,
                credential=cred,
            )
        try:
            result = asyncio.run(send())
        except BiliCommentError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise BiliCommentError(f"B站发评论失败：{exc}") from exc
        if not result.get("rpid"):
            raise BiliCommentError(str(result.get("message") or result))
        return {
            "rpid": int(result.get("rpid") or 0),
            "root": int(result.get("root") or 0),
            "parent": int(result.get("parent") or 0),
            "toast": str(result.get("success_toast") or ""),
        }

    def replies(self, bvid: str, root_rpid: int) -> list[dict]:
        """Get replies under one of Mocha's top-level comments."""
        cred = self.require_credential()
        async def get_aid():
            video_obj = video.Video(bvid=bvid, credential=cred)
            info = await video_obj.get_info()
            return int(info.get("aid") or 0)
        try:
            aid = asyncio.run(get_aid())
        except Exception as exc:  # noqa: BLE001
            raise BiliCommentError(f"读取视频 aid 失败：{exc}") from exc
        if not aid:
            raise BiliCommentError("拿不到视频 aid")
        query = urllib.parse.urlencode({
            "oid": aid, "type": 1, "root": int(root_rpid),
            "pn": 1, "ps": 20,
        })
        request = urllib.request.Request(
            "https://api.bilibili.com/x/v2/reply/reply?" + query,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://www.bilibili.com/",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read())
        except Exception as exc:  # noqa: BLE001
            raise BiliCommentError(f"读取B站回复失败：{exc}") from exc
        if payload.get("code") != 0:
            if payload.get("code") == 12006:
                return []
            raise BiliCommentError(
                f"读取B站回复失败：{payload.get('message') or payload.get('code')}"
            )
        items = []
        for item in (payload.get("data") or {}).get("replies") or []:
            member = item.get("member") or {}
            content = item.get("content") or {}
            items.append({
                "rpid": int(item.get("rpid") or 0),
                "root": int(item.get("root") or 0),
                "parent": int(item.get("parent") or 0),
                "mid": int(member.get("mid") or item.get("mid") or 0),
                "uname": str(member.get("uname") or ""),
                "message": str(content.get("message") or ""),
                "ctime": int(item.get("ctime") or 0),
            })
        return items

    def find_target(self, bvid: str, rpid: int = 0) -> tuple[dict | None, dict]:
        me = self.self_info()
        items = self.comments(bvid, limit=50)
        if rpid:
            for item in items:
                if item["rpid"] == rpid:
                    return item, me
            return None, me
        for item in items:
            if item["mid"] != me["mid"] and item["message"]:
                return item, me
        return None, me
