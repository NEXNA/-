from __future__ import annotations

import base64
import json
import logging
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from .util import split_message

logger = logging.getLogger(__name__)


class OneBotError(Exception):
    pass


@dataclass
class Message:
    group_id: int
    user_id: int
    msg_id: str
    nick: str
    text: str
    at_me: bool
    reply_id: str | None
    self_id: int
    has_image: bool = False
    image_urls: list[str] = field(default_factory=list)
    image_files: list[str] = field(default_factory=list)
    has_face: bool = False
    at_user_ids: list[int] = field(default_factory=list)
    is_private: bool = False


def _unescape(text: str) -> str:
    return (text.replace("&#91;", "[").replace("&#93;", "]")
            .replace("&#44;", ",").replace("&amp;", "&"))


def _parse_cq(raw: str, self_id: int) -> tuple[str, bool, str | None]:
    raw = _unescape(raw)
    at_me = bool(re.search(rf"\[CQ:at,qq={self_id}(?:,|\])", raw))
    reply = re.search(r"\[CQ:reply,id=(-?\d+)\]", raw)
    text = re.sub(r"\[CQ:[^\]]+\]", "", raw).strip()
    card_links = _bili_links(raw)
    if card_links:
        text = (text + " " + " ".join(card_links)).strip()
    return text, at_me, reply.group(1) if reply else None


_BILI_URL_RE = re.compile(
    r"https?://(?:b23\.tv|bilibili\.com/video)/[^\s\"'<>\\]+", re.I
)
_BILI_BV_RE = re.compile(r"BV[0-9A-Za-z]{10}")


def _bili_links(raw: str) -> list[str]:
    value = str(raw or "").replace("\\/", "/")
    result: list[str] = []
    for match in _BILI_URL_RE.finditer(value):
        url = match.group(0).rstrip("。，,.)）]")
        if url not in result:
            result.append(url)
    for match in _BILI_BV_RE.finditer(value):
        bvid = match.group(0)
        if bvid not in result:
            result.append(bvid)
    return result


def _segments_to_text(segments) -> str:
    parts = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        kind = seg.get("type")
        data = seg.get("data") or {}
        if kind == "text":
            parts.append(str(data.get("text", "")))
        elif kind in ("json", "xml"):
            raw = data.get("data") if isinstance(data, dict) else data
            if isinstance(raw, (dict, list)):
                raw = json.dumps(raw, ensure_ascii=False)
            if isinstance(raw, str):
                text = raw
                try:
                    text = json.dumps(json.loads(raw), ensure_ascii=False)
                except (ValueError, TypeError):
                    pass
                links = _bili_links(text)
                if links:
                    parts.append(" " + " ".join(links))
    return "".join(parts).strip()


def parse_event(event: dict, self_id: int | None = None) -> Message | None:
    if event.get("post_type") != "message":
        return None
    if event.get("message_type") not in ("group", "private"):
        return None
    try:
        user_id = int(event["user_id"])
        if str(event.get("message_type") or "") == "private" or "group_id" not in event:
            group_id = 0
            is_private = True
        else:
            group_id = int(event["group_id"])
            is_private = False
    except (KeyError, TypeError, ValueError):
        return None
    self_id = int(self_id or event.get("self_id") or 0)
    sender = event.get("sender") or {}
    nick = str(sender.get("card") or sender.get("nickname") or user_id)
    msg_id = str(event.get("message_id") or "")
    segments = event.get("message")

    reply_id: str | None = None
    at_me = False
    at_user_ids: list[int] = []
    has_image = False
    image_urls: list[str] = []
    image_files: list[str] = []
    has_face = False
    if isinstance(segments, list):
        text = _segments_to_text(segments)
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            kind = seg.get("type")
            data = seg.get("data") or {}
            if kind == "at":
                qq = str(data.get("qq") or "")
                if qq.isdigit():
                    at_user_ids.append(int(qq))
                if qq == str(self_id):
                    at_me = True
            elif kind == "reply":
                reply_id = str(data.get("id") or "") or None
            elif kind == "image":
                has_image = True
                if data.get("url"):
                    image_urls.append(str(data["url"]))
                if data.get("file"):
                    image_files.append(str(data["file"]))
            elif kind == "face":
                has_face = True
    else:
        raw = str(event.get("raw_message") or segments or "")
        text, at_me, reply_id = _parse_cq(raw, self_id)
        at_user_ids = [int(x) for x in re.findall(r"\[CQ:at,qq=(\d+)\]", raw)]
        has_image = "[CQ:image" in raw
        has_face = "[CQ:face" in raw
        for match in re.finditer(r"\[CQ:image,([^\]]+)\]", raw):
            params = match.group(1)
            url = re.search(r"(?:^|,)url=([^,]+)", params)
            file = re.search(r"(?:^|,)file=([^,]+)", params)
            if url:
                image_urls.append(_unescape(url.group(1)))
            if file:
                image_files.append(_unescape(file.group(1)))

    return Message(
        group_id=group_id,
        user_id=user_id,
        msg_id=msg_id,
        nick=nick,
        text=text,
        at_me=at_me,
        reply_id=reply_id,
        self_id=self_id,
        has_image=has_image,
        image_urls=image_urls,
        image_files=image_files,
        has_face=has_face,
        at_user_ids=at_user_ids,
        is_private=is_private,
    )


class OneBotClient:
    def __init__(self, api_base: str, access_token: str = "", timeout: int = 15):
        self.api_base = api_base.rstrip("/")
        self.access_token = access_token
        self.timeout = timeout

    def _call(self, action: str, **params) -> dict:
        body = json.dumps(params, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        request = urllib.request.Request(
            f"{self.api_base}/{action}", data=body, headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass
            raise OneBotError(f"{action} 失败：HTTP {exc.code} {detail[:200]}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise OneBotError(f"{action} 连不上 NapCat：{exc}") from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise OneBotError(f"{action} 返回非 JSON：{raw[:200]}") from exc
        if data.get("retcode") not in (0, None) or data.get("status") == "failed":
            raise OneBotError(f"{action} 失败：{data.get('wording') or data}")
        return data.get("data") or {}

    def send_text(self, group_id: int, text: str, reply_to: str | None = None,
                  face_ids: list[int] | None = None) -> list[str]:
        chunks = split_message(text, 800)
        if not chunks and face_ids:
            chunks = [""]
        if not chunks:
            return []
        sent: list[str] = []
        for index, chunk in enumerate(chunks):
            message = []
            if reply_to and index == 0:
                message.append({"type": "reply", "data": {"id": str(reply_to)}})
            if chunk:
                message.append({"type": "text", "data": {"text": chunk}})
            if face_ids and index == len(chunks) - 1:
                for face_id in face_ids:
                    message.append({"type": "face", "data": {"id": str(face_id)}})
            data = self._call("send_group_msg", group_id=group_id, message=message)
            if data.get("message_id") is not None:
                sent.append(str(data["message_id"]))
        return sent

    def get_msg(self, message_id: str) -> dict:
        return self._call("get_msg", message_id=message_id)

    def get_login_info(self) -> dict:
        return self._call("get_login_info")

    def send_private_text(self, user_id: int, text: str,
                          reply_to: str | None = None,
                          face_ids: list[int] | None = None) -> list[str]:
        chunks = split_message(text, 800)
        if not chunks and face_ids:
            chunks = [""]
        if not chunks:
            return []
        sent: list[str] = []
        for index, chunk in enumerate(chunks):
            message = []
            if reply_to and index == 0:
                message.append({"type": "reply", "data": {"id": str(reply_to)}})
            if chunk:
                message.append({"type": "text", "data": {"text": chunk}})
            if face_ids and index == len(chunks) - 1:
                for face_id in face_ids:
                    message.append({"type": "face", "data": {"id": str(face_id)}})
            data = self._call("send_private_msg", user_id=user_id, message=message)
            if data.get("message_id") is not None:
                sent.append(str(data["message_id"]))
        return sent

    def send_private_image(self, user_id: int, path: Path | str,
                           send_mode: str = "base64") -> list[str]:
        path = Path(path)
        if send_mode == "path":
            segment = {"type": "image", "data": {"file": path.resolve().as_uri()}}
        else:
            data = base64.b64encode(path.read_bytes()).decode("ascii")
            segment = {"type": "image", "data": {"file": f"base64://{data}"}}
        result = self._call("send_private_msg", user_id=user_id, message=[segment])
        return [str(result["message_id"])] if result.get("message_id") is not None else []

    def send_private_voice(self, user_id: int, path: Path | str) -> list[str]:
        path = Path(path)
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        segment = {"type": "record", "data": {"file": f"base64://{data}"}}
        result = self._call("send_private_msg", user_id=user_id, message=[segment])
        return [str(result["message_id"])] if result.get("message_id") is not None else []

    def send_group_voice(self, group_id: int, path: Path | str) -> list[str]:
        path = Path(path)
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        segment = {"type": "record", "data": {"file": f"base64://{data}"}}
        result = self._call("send_group_msg", group_id=group_id, message=[segment])
        return [str(result["message_id"])] if result.get("message_id") is not None else []

    def fetch_custom_faces(self, count: int = 48) -> list[dict]:
        """取 QQ 收藏表情。优先用带 md5/url 的详情接口。"""
        data = None
        try:
            data = self._call("fetch_custom_face_detail", count=count)
        except OneBotError as exc:
            logger.info("fetch_custom_face_detail 不可用，改用 fetch_custom_face：%s", exc)
            try:
                data = self._call("fetch_custom_face", count=count)
            except OneBotError as exc2:
                raise OneBotError(f"取 QQ 收藏表情失败：{exc2}") from exc2
        if not isinstance(data, list):
            return []
        result: list[dict] = []
        for item in data:
            if isinstance(item, dict):
                result.append(item)
            elif isinstance(item, str):
                result.append({"url": item})
        return result

    def send_image(self, group_id: int, path: Path | str,
                   reply_to: str | None = None, send_mode: str = "base64",
                   remote_url: str | None = None) -> list[str]:
        path = Path(path)
        data = path.read_bytes()
        encoded = base64.b64encode(data).decode("ascii")
        candidates: list[str] = []
        if send_mode == "path":
            candidates.append(path.resolve().as_uri())
            candidates.append(f"base64://{encoded}")
        else:
            candidates.append(f"base64://{encoded}")
            candidates.append(path.resolve().as_uri())
        if remote_url:
            candidates.append(remote_url)

        last_error: OneBotError | None = None
        for file in candidates:
            message = []
            if reply_to:
                message.append({"type": "reply", "data": {"id": str(reply_to)}})
            message.append({"type": "image", "data": {"file": file}})
            try:
                result = self._call("send_group_msg", group_id=group_id, message=message)
            except OneBotError as exc:
                last_error = exc
                logger.info("图片发送方式失败，尝试下一种：%s", type(exc).__name__)
                continue
            sent = []
            if result.get("message_id") is not None:
                sent.append(str(result["message_id"]))
            return sent
        if last_error:
            raise last_error
        return []

    def quoted_text(self, message_id: str) -> tuple[str, str] | None:
        try:
            data = self.get_msg(message_id)
        except OneBotError as exc:
            logger.warning("取引用消息失败：%s", exc)
            return None
        sender = data.get("sender") or {}
        nick = str(sender.get("card") or sender.get("nickname") or "")
        message = data.get("message") or []
        if isinstance(message, list):
            text = _segments_to_text(message)
        else:
            text, _, _ = _parse_cq(str(message), 0)
        if not text:
            return None
        return nick, text

    def upload_group_file(self, group_id: int, path: Path | str, name: str) -> None:
        self._call("upload_group_file", group_id=group_id,
                   file=str(Path(path).resolve()), name=name)

    def health(self) -> dict:
        try:
            data = self._call("get_status")
            return {"ok": True, "data": data}
        except OneBotError as exc:
            return {"ok": False, "error": str(exc)}
