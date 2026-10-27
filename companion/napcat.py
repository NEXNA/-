"""NapCat / OneBot 11 私聊桥接。

NapCat 通过 HTTP 客户端把私聊事件 POST 到 /napcat/event；
本模块用 NapCat 的 HTTP API 把回复发回去。QQ 号在网页里绑定一次后，
后续私聊就自动以对应账号的身份使用角色、记忆、亲密度和运势。
"""
from __future__ import annotations

import base64
import collections
import hmac
import html
import json
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from chat_engine import chat_once, intimacy_label, resolve_persona
from db import Database
from fortune import make_fortune, today
from llm import LLMError
from web_search import format_context, search_web

UNBOUND_TEXT = (
    "这个 QQ 还没有绑定陪伴工作台账号。\n"
    "请先在网页端登录，打开「机器人设定」→「QQ 绑定」，"
    "生成 6 位绑定码，然后在这里发送：/bind 123456"
)
HELP_TEXT = (
    "可用指令：\n"
    "/面板 打开功能面板\n"
    "/切换 查看或切换角色\n"
    "/运势 看今天的运势\n"
    "/记忆 看最近记住的事\n"
    "/亲密度 看关系距离\n"
    "/搜 关键词 查最新信息\n"
    "/状态 当前角色、亲密度和记忆数量\n"
    "/bind 123456 绑定网页账号\n"
    "直接发消息就是聊天。"
)
WHITELIST_TEXT = (
    "这个 QQ 不在陪伴工作台的白名单里。\n"
    "请让管理员在网页端「机器人设定」→「QQ 白名单」里添加这个 QQ，"
    "或暂时关闭白名单开关。"
)


class NapCatError(Exception):
    pass


def _clean_qq(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _truthy(value: str | None, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def split_text(text: str, limit: int = 1400) -> list[str]:
    """按段落切分长回复，避免超过 QQ 单条消息限制。"""
    text = str(text or "").strip()
    if not text:
        return []
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:
            if current:
                chunks.append(current.rstrip())
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        if len(current) + len(line) > limit and current:
            chunks.append(current.rstrip())
            current = ""
        current += line
    if current.strip():
        chunks.append(current.rstrip())
    return chunks


def extract_text(event: dict) -> str:
    message = event.get("message")
    parts: list[str] = []
    if isinstance(message, list):
        for segment in message:
            if not isinstance(segment, dict):
                continue
            if segment.get("type") == "text":
                data = segment.get("data") or {}
                parts.append(str(data.get("text") or ""))
    elif isinstance(message, str):
        parts.append(message)
    text = "".join(parts).strip()
    if not text:
        raw = str(event.get("raw_message") or "").strip()
        if raw and "[CQ:" not in raw:
            text = raw
    return text


def extract_image_sources(event: dict) -> list[str]:
    sources: list[str] = []
    message = event.get("message")
    if isinstance(message, list):
        for segment in message:
            if not isinstance(segment, dict) or segment.get("type") != "image":
                continue
            data = segment.get("data") or {}
            for key in ("url", "file", "path", "base64"):
                value = str(data.get(key) or "").strip()
                if value:
                    sources.append(value)
    raw = str(event.get("raw_message") or "")
    for match in re.finditer(r"\[CQ:image,[^\]]+\]", raw):
        for key in ("url", "file"):
            found = re.search(rf"{key}=([^,\]]+)", match.group(0))
            if found:
                sources.append(html.unescape(found.group(1)))
    return list(dict.fromkeys(sources))


def _image_mime(data: bytes) -> str:
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if data.startswith(b"GIF8"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def load_image_data_uris(sources: list[str], limit: int = 1) -> list[str]:
    result: list[str] = []
    for source in sources:
        if len(result) >= limit:
            break
        value = html.unescape(str(source or "").strip())
        data: bytes | None = None
        try:
            if value.startswith("//"):
                value = "https:" + value
            if value.startswith(("http://", "https://")):
                request = urllib.request.Request(
                    value, headers={"User-Agent": "Mozilla/5.0"},
                )
                with urllib.request.urlopen(request, timeout=12) as response:
                    data = response.read(6_000_000)
            elif value.startswith("base64://"):
                data = base64.b64decode(value[9:])
            elif value.startswith("file://"):
                raw = value[8:] if value.startswith("file:///") else value[7:]
                data = Path(urllib.parse.unquote(raw)).read_bytes()
            elif Path(value).is_file():
                data = Path(value).read_bytes()
        except (OSError, ValueError, urllib.error.URLError) as exc:
            print(f"[image] 读取失败：{exc}", flush=True)
        if data:
            result.append(
                f"data:{_image_mime(data)};base64,{base64.b64encode(data).decode('ascii')}"
            )
    return result


def _bearer(headers: Any, query: dict) -> str:
    auth = str(headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return str(
        headers.get("X-NapCat-Token")
        or query.get("token")
        or query.get("access_token")
        or ""
    ).strip()


class OneBotAPI:
    def __init__(self, base_url: str, token: str = "", timeout: int = 20):
        self.base_url = base_url.rstrip("/")
        self.token = token.strip()
        self.timeout = timeout

    def call(self, action: str, payload: dict | None = None) -> Any:
        body = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(
            f"{self.base_url}/{action}", data=body, headers=headers, method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise NapCatError(f"NapCat HTTP {exc.code}: {detail}") from exc
        except Exception as exc:  # noqa: BLE001
            raise NapCatError(f"连接 NapCat 失败：{exc}") from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise NapCatError(f"NapCat 返回格式异常：{raw[:200]}") from exc
        if int(data.get("retcode", 0)) != 0:
            raise NapCatError(str(data.get("message") or data.get("wording") or data))
        return data.get("data")

    def send_private_text(self, qq: str, text: str) -> None:
        for chunk in split_text(text):
            self.call("send_private_msg", {
                "user_id": int(qq),
                "message": [{"type": "text", "data": {"text": chunk}}],
            })

    def send_group_text(self, group_id: str, text: str) -> None:
        for chunk in split_text(text):
            self.call("send_group_msg", {
                "group_id": int(group_id),
                "message": [{"type": "text", "data": {"text": chunk}}],
            })

    def get_login_info(self) -> dict:
        data = self.call("get_login_info")
        return data if isinstance(data, dict) else {}


class NapCatBridge:
    def __init__(self, db: Database, *, enabled: bool = False,
                 event_token: str = "", api_base: str = "http://127.0.0.1:3000",
                 api_token: str = "", owner_qq: str = "", bot_qq: str = "",
                 api_key: str = "", base_url: str = "https://api.deepseek.com",
                 api: OneBotAPI | None = None, logger=print):
        self.db = db
        self.enabled = enabled
        self.event_token = event_token.strip()
        self.owner_qq = _clean_qq(owner_qq)
        self.bot_qq = _clean_qq(bot_qq)
        self.api_key = api_key
        self.base_url = base_url
        self.logger = logger
        self.api = api or OneBotAPI(api_base, api_token)
        self.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="napcat")
        self._lock = threading.Lock()
        self._stats_lock = threading.Lock()
        self._bind_codes: dict[str, tuple[int, float]] = {}
        self._seen: collections.OrderedDict[str, float] = collections.OrderedDict()
        self._last_seen: dict[str, float] = {}
        self._poll_stop = threading.Event()
        self._poll_thread: threading.Thread | None = None
        self._poll_last_error = ""
        self._stats: dict[str, object] = {
            "events": 0,
            "messages": 0,
            "last_event_at": "",
            "last_event_type": "",
            "last_message_at": "",
            "last_error": "",
        }

    @classmethod
    def from_env(cls, db: Database, logger=print) -> "NapCatBridge":
        return cls(
            db,
            enabled=_truthy(os.environ.get("NAPCAT_ENABLED"), False),
            event_token=os.environ.get("NAPCAT_EVENT_TOKEN", ""),
            api_base=os.environ.get("NAPCAT_API_URL", "http://127.0.0.1:3000"),
            api_token=os.environ.get("NAPCAT_API_TOKEN", ""),
            owner_qq=os.environ.get("NAPCAT_OWNER_QQ", ""),
            bot_qq=os.environ.get("NAPCAT_BOT_QQ", ""),
            api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
            base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            logger=logger,
        )

    # ---------- HTTP entry ----------
    def authorized(self, headers: Any, query: dict) -> bool:
        if not self.enabled or not self.event_token:
            return False
        return hmac.compare_digest(_bearer(headers, query), self.event_token)

    def sync_login(self) -> str:
        """以 NapCat 实际登录号为准，避免切号后群聊 @ 识别失效。"""
        try:
            info = self.api.get_login_info()
            value = _clean_qq(info.get("user_id"))
            if value:
                self.bot_qq = value
            return self.bot_qq
        except NapCatError as exc:
            self.logger(f"[napcat] 读取登录号失败：{exc}")
            return self.bot_qq

    def handle_http(self, handler) -> None:
        """由 app.py 调用：校验 token，尽快返回 204，然后异步处理。"""
        if not self.enabled:
            handler.json({"ok": False, "error": "NapCat 未启用"}, 503)
            return
        from urllib.parse import parse_qs, urlparse
        query = {
            key: values[-1]
            for key, values in parse_qs(urlparse(handler.path).query).items()
            if values
        }
        if not self.authorized(handler.headers, query):
            handler.json({"ok": False, "error": "NapCat token 不对"}, 401)
            return
        try:
            event = handler.request_json()
        except ValueError as exc:
            handler.json({"ok": False, "error": str(exc)}, 400)
            return
        self._record_event(event)
        self.logger(
            f"[napcat] 收到 {event.get('post_type', '')}/"
            f"{event.get('message_type', '')} user={event.get('user_id', '')}"
        )
        self.accept(event)
        handler.json({"status": "ok", "retcode": 0})

    def _record_event(self, event: dict) -> None:
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        kind = f"{event.get('post_type', '')}/{event.get('message_type', '')}"
        with self._stats_lock:
            self._stats["events"] = int(self._stats["events"]) + 1
            self._stats["last_event_at"] = now
            self._stats["last_event_type"] = kind
            if event.get("post_type") == "message":
                self._stats["messages"] = int(self._stats["messages"]) + 1
                self._stats["last_message_at"] = now

    def _record_error(self, message: str) -> None:
        with self._stats_lock:
            self._stats["last_error"] = str(message)[:300]

    def accept(self, event: dict) -> None:
        if event.get("post_type") != "message":
            return
        if event.get("message_type") not in ("private", "group"):
            return
        qq = _clean_qq(event.get("user_id"))
        if not qq or qq == self.bot_qq:
            return
        scope = _clean_qq(event.get("group_id")) if event.get("message_type") == "group" else qq
        key = str(event.get("message_id") or "") or (
            f"{event.get('message_type')}:{scope}:{qq}:"
            f"{event.get('time')}:{extract_text(event)[:120]}"
        )
        now = time.time()
        with self._lock:
            if key in self._seen:
                return
            self._seen[key] = now
            while len(self._seen) > 1000:
                self._seen.popitem(last=False)
            rate_key = f"{event.get('message_type')}:{scope}:{qq}"
            last = self._last_seen.get(rate_key, 0.0)
            if now - last < 0.7:
                return
            self._last_seen[rate_key] = now
        self.executor.submit(self._safe_process, event)

    def _safe_process(self, event: dict) -> None:
        try:
            self.process_event(event)
        except Exception as exc:  # noqa: BLE001
            self.logger(f"[napcat] 处理失败 {type(exc).__name__}: {exc}")

    def _at_bot(self, event: dict) -> bool:
        target = self.bot_qq or _clean_qq(event.get("self_id"))
        for segment in event.get("message") or []:
            if not isinstance(segment, dict) or segment.get("type") != "at":
                continue
            qq = _clean_qq((segment.get("data") or {}).get("qq"))
            if target and qq == target:
                return True
        return bool(target and f"[CQ:at,qq={target}" in str(event.get("raw_message") or ""))

    def _process_group(self, event: dict, qq: str, text: str,
                       images: list[str] | None = None) -> dict:
        group_id = _clean_qq(event.get("group_id"))
        if not group_id:
            return {"ok": False, "error": "没有群号"}
        settings = self.db.settings()
        if (settings.get("group_whitelist_enabled", 0)
                and not self.db.is_group_whitelisted(group_id)):
            self._record_error("群不在白名单")
            return {"ok": False, "error": "群不在白名单"}
        if not text and not images:
            return {"ok": False, "error": "非文字消息"}
        active_names = {str(item.get("name") or "") for item in self.db.personas()}
        mentioned = self._at_bot(event) or any(
            name and name in text for name in active_names
        )
        if not mentioned:
            return {"ok": False, "error": "没有叫机器人"}
        if not text:
            text = "（发了一张图）"
        sender = event.get("sender") or {}
        nickname = str(sender.get("card") or sender.get("nickname") or "").strip()
        try:
            user = self.db.ensure_guest(qq, nickname or f"群友{qq[-4:]}")
            persona = resolve_persona(self.db, int(user["id"]), settings)
            result = chat_once(
                self.db, int(user["id"]), nickname or user["username"], text,
                settings, persona, api_key=self.api_key, base_url=self.base_url,
                images=images,
                extra_context=(
                    self._search_context(text) if self._needs_search(text) else ""
                ),
            )
            self.api.send_group_text(group_id, str(result["reply"]))
            return {
                "ok": True, "reply": result["reply"], "group_id": group_id,
                "qq": qq, "persona": result.get("persona"),
            }
        except (ValueError, LLMError, NapCatError) as exc:
            self.logger(f"[napcat] 群聊处理失败：{exc}")
            self._record_error(str(exc))
            try:
                self.api.send_group_text(group_id, "（这条没接住，稍后再试）")
            except NapCatError:
                pass
            return {"ok": False, "error": str(exc)}

    # ---------- core ----------
    def process_event(self, event: dict) -> dict:
        """同步处理一条事件；测试可直接调用。"""
        qq = _clean_qq(event.get("user_id"))
        if not qq:
            return {"ok": False, "error": "没有 QQ 号"}
        text = extract_text(event)
        images = load_image_data_uris(extract_image_sources(event), limit=1)
        if event.get("message_type") == "group":
            return self._process_group(event, qq, text, images)
        command = text.strip()
        is_bind = command.startswith(("/bind", "/绑定"))
        settings = self.db.settings()
        if (settings.get("qq_whitelist_enabled", 0)
                and not self._allowed(qq) and not is_bind):
            self._send(qq, WHITELIST_TEXT)
            self._record_error("QQ 不在白名单")
            return {"ok": False, "error": "QQ 不在白名单"}
        if not text:
            if images:
                text = "（发了一张图）"
            else:
                self._send(qq, "现在支持文字和图片，发图时最好配一句想问什么。")
                return {"ok": False, "error": "非文字消息"}
        sender = event.get("sender") or {}
        nickname = str(sender.get("card") or sender.get("nickname") or "").strip()

        if is_bind:
            return self._cmd_bind(qq, nickname, command)

        user = self.db.user_by_qq(qq)
        if not user and self.owner_qq and qq == self.owner_qq:
            admin = self.db.first_admin()
            if admin:
                self.db.bind_qq(int(admin["id"]), qq, nickname)
                user = self.db.user_by_qq(qq)
        if not user:
            self._send(qq, UNBOUND_TEXT)
            return {"ok": False, "error": "QQ 未绑定"}

        user_id = int(user["id"])
        if command.startswith("/"):
            return self._command(user, qq, command)

        persona = resolve_persona(self.db, user_id, settings)
        display_name = str(user["nickname"] or user["username"] or "")
        try:
            result = chat_once(
                self.db, user_id, display_name, text, settings, persona,
                api_key=self.api_key, base_url=self.base_url, images=images,
                extra_context=(
                    self._search_context(text) if self._needs_search(text) else ""
                ),
            )
        except ValueError as exc:
            self._send(qq, str(exc))
            self._record_error(str(exc))
            return {"ok": False, "error": str(exc)}
        except LLMError as exc:
            self.logger(f"[napcat] LLM 失败：{exc}")
            self._record_error(str(exc))
            self._send(qq, "（连接模型失败，稍后再试）")
            return {"ok": False, "error": str(exc)}
        self._send(qq, str(result["reply"]))
        return {
            "ok": True, "reply": result["reply"],
            "persona": result.get("persona"), "qq": qq,
        }

    def _allowed(self, qq: str) -> bool:
        if self.owner_qq and qq == self.owner_qq:
            return True
        return self.db.is_qq_whitelisted(qq)

    @staticmethod
    def _needs_search(text: str) -> bool:
        if not text or text.startswith("/") or len(text) > 160:
            return False
        terms = (
            "最新", "更新", "版本", "活动", "卡池", "公告", "新闻",
            "上线", "发售", "剧情", "价格",
        )
        return any(term in text for term in terms)

    def _search_context(self, text: str) -> str:
        try:
            results = search_web(text, 4)
            return format_context(results)
        except Exception as exc:  # noqa: BLE001
            self.logger(f"[search] 失败：{exc}")
            return ""

    def _command(self, user, qq: str, command: str) -> dict:
        parts = command.split(maxsplit=1)
        name = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""
        if name in {"/help", "/帮助", "/?", "帮助"}:
            self._send(qq, HELP_TEXT)
            return {"ok": True, "reply": HELP_TEXT}
        if name in {"/switch", "/persona", "/切换", "/角色"}:
            return self._cmd_persona(user, qq, arg)
        if name in {"/panel", "/面板", "/菜单", "/功能", "/功能面板"}:
            return self._cmd_panel(user, qq)
        if name in {"/fortune", "/运势"}:
            return self._cmd_fortune(user, qq, arg)
        if name in {"/memory", "/memories", "/记忆"}:
            return self._cmd_memories(user, qq)
        if name in {"/intimacy", "/亲密度"}:
            return self._cmd_intimacy(user, qq)
        if name in {"/search", "/搜", "/搜索"}:
            return self._cmd_search(qq, arg)
        if name in {"/status", "/状态"}:
            return self._cmd_status(user, qq)
        self._send(qq, HELP_TEXT)
        return {"ok": False, "error": "未知指令"}

    @staticmethod
    def _panel_url() -> str:
        return (
            os.environ.get("COMPANION_PUBLIC_URL")
            or "http://127.0.0.1:8765"
        ).rstrip("/")

    def _cmd_panel(self, user, qq: str) -> dict:
        user_id = int(user["id"])
        state = self.db.state(user_id)
        key = self.db.user_persona_key(user_id) or self.db.default_persona_key()
        persona = self.db.persona(key)
        count = len(self.db.memories(user_id, 200))
        text = (
            "┌ 陪伴工作台 · 私聊面板\n"
            f"│ 角色：{persona['name'] if persona else '未设置'}\n"
            f"│ 陪伴QQ：{self.bot_qq or '未识别'}\n"
            f"│ 亲密度：{int(state.get('intimacy', 0))}/100"
            f"（{intimacy_label(int(state.get('intimacy', 0)))}）\n"
            f"│ 记忆：{count} 条\n"
            "├ 指令\n"
            "│ /切换           查看 / 切换角色\n"
            "│ /运势           今日运势\n"
            "│ /记忆           最近记住的事\n"
            "│ /亲密度         关系距离\n"
            "│ /搜 关键词      查最新信息\n"
            "│ /状态           当前状态\n"
            "│ /bind 123456    绑定网页账号\n"
            f"├ 网页面板\n│ {self._panel_url()}/panel\n"
            "└ 直接发消息就是聊天"
        )
        self._send(qq, text)
        return {"ok": True, "reply": text}

    def _cmd_fortune(self, user, qq: str, date: str = "") -> dict:
        user_id = int(user["id"])
        day = date.strip() if date.strip() else today()
        if day == today():
            state = self.db.state(user_id)
            if state.get("fortune_date") == day and state.get("fortune_json"):
                try:
                    payload = json.loads(state["fortune_json"])
                except json.JSONDecodeError:
                    payload = None
                if payload:
                    text = (
                        f"{payload['date']} 的运势\n"
                        f"综合 {'★' * int(payload['overall'])}"
                        f"{'☆' * (5 - int(payload['overall']))}\n"
                        f"感情 {int(payload['love'])}/5 · 工作 {int(payload['work'])}/5"
                        f" · 财运 {int(payload['wealth'])}/5\n"
                        f"{payload['summary']}"
                    )
                    self._send(qq, text)
                    return {"ok": True, "reply": text}
        payload = make_fortune(user_id, str(user["username"]), day)
        self.db.save_fortune(user_id, day, json.dumps(payload, ensure_ascii=False))
        text = (
            f"{payload['date']} 的运势\n"
            f"综合 {'★' * int(payload['overall'])}"
            f"{'☆' * (5 - int(payload['overall']))}\n"
            f"感情 {int(payload['love'])}/5 · 工作 {int(payload['work'])}/5"
            f" · 财运 {int(payload['wealth'])}/5\n"
            f"{payload['summary']}"
        )
        self._send(qq, text)
        return {"ok": True, "reply": text}

    def _cmd_memories(self, user, qq: str) -> dict:
        rows = self.db.memories(int(user["id"]), 8)
        if not rows:
            text = "还没有长期记忆。直接在私聊里说「记住……」也可以。"
        else:
            lines = ["最近记住的事："]
            for item in rows:
                lines.append(f"- {item['text']}")
            text = "\n".join(lines)
        self._send(qq, text)
        return {"ok": True, "reply": text}

    def _cmd_intimacy(self, user, qq: str) -> dict:
        value = int(self.db.state(int(user["id"])).get("intimacy", 0))
        text = f"当前亲密度：{value}/100（{intimacy_label(value)}）"
        self._send(qq, text)
        return {"ok": True, "reply": text}

    def _cmd_search(self, qq: str, query: str) -> dict:
        if not query:
            text = "用法：/搜 深空之眼 最新版本"
            self._send(qq, text)
            return {"ok": False, "error": "没有关键词"}
        results = search_web(query, 4)
        if not results:
            text = "没搜到 换个关键词试试"
        else:
            lines = ["搜到这些"]
            for index, item in enumerate(results, 1):
                title = str(item.get("title") or "")[:80]
                snippet = str(item.get("snippet") or "")[:120]
                lines.append(f"{index} {title}")
                if snippet:
                    lines.append(snippet)
            text = "\n".join(lines)
        self._send(qq, text)
        return {"ok": True, "reply": text, "results": results}

    def _cmd_persona(self, user, qq: str, arg: str) -> dict:
        personas = self.db.personas()
        if not arg:
            active = self.db.user_persona_key(int(user["id"])) or self.db.default_persona_key()
            lines = ["可用角色："]
            for item in personas:
                mark = "（当前）" if item["key"] == active else ""
                lines.append(f"- {item['name']}{mark}")
            lines.append("发送 /切换 角色名 切换。")
            text = "\n".join(lines)
            self._send(qq, text)
            return {"ok": True, "reply": text}
        norm = arg.strip().lower()
        aliases = {
            "诗蔻蒂": "skuld", "诗寇蒂": "skuld", "skuld": "skuld",
            "hope": "skuld", "绮望": "skuld",
            "伊邪那美": "izanami", "鸦越千羽": "izanami",
            "千羽": "izanami", "izanami": "izanami",
        }
        target_key = aliases.get(norm.split("（")[0].strip())
        if target_key:
            matches = [item for item in personas if item["key"] == target_key]
        else:
            matches = []
        for item in personas:
            if matches:
                break
            candidates = {
                str(item["key"]).lower(),
                str(item["name"]).strip().lower(),
                str(item["name"]).split("（")[0].strip().lower(),
            }
            if norm in candidates or norm.split("（")[0].strip() in candidates:
                matches.append(item)
        if not matches:
            matches = [
                item for item in personas
                if norm in str(item["name"]).lower() or norm in str(item["key"]).lower()
            ]
        if len(matches) != 1:
            self._send(qq, "没有找到这个角色。发送 /切换 查看列表。")
            return {"ok": False, "error": "角色不明确"}
        target = matches[0]
        self.db.set_user_persona(int(user["id"]), str(target["key"]))
        text = f"已切换到「{target['name']}」。"
        self._send(qq, text)
        return {"ok": True, "reply": text, "persona": target["name"]}

    def _cmd_status(self, user, qq: str) -> dict:
        user_id = int(user["id"])
        state = self.db.state(user_id)
        key = self.db.user_persona_key(user_id) or self.db.default_persona_key()
        persona = self.db.persona(key)
        count = len(self.db.memories(user_id, 200))
        text = (
            f"当前角色：{persona['name'] if persona else '未设置'}\n"
            f"亲密度：{int(state.get('intimacy', 0))}/100\n"
            f"记忆：{count} 条\n"
            f"绑定 QQ：{qq}"
        )
        self._send(qq, text)
        return {"ok": True, "reply": text}

    def _cmd_bind(self, qq: str, nickname: str, command: str) -> dict:
        existing = self.db.user_by_qq(qq)
        if existing:
            text = f"这个 QQ 已经绑定了账号「{existing['username']}」。"
            self._send(qq, text)
            return {"ok": True, "reply": text}
        parts = command.split(maxsplit=1)
        code = parts[1].strip() if len(parts) > 1 else ""
        if not re.fullmatch(r"\d{6}", code):
            self._send(qq, "用法：/bind 123456\n绑定码在网页端「机器人设定」→「QQ 绑定」生成。")
            return {"ok": False, "error": "绑定码格式不对"}
        entry = self._consume_code(code)
        if not entry:
            self._send(qq, "绑定码无效或已过期，请回网页重新生成。")
            return {"ok": False, "error": "绑定码无效"}
        user_id, _ = entry
        try:
            self.db.bind_qq(user_id, qq, nickname)
        except ValueError as exc:
            self._send(qq, str(exc))
            return {"ok": False, "error": str(exc)}
        row = self.db.user_by_id(user_id)
        text = f"绑定成功，现在是「{row['username'] if row else user_id}」的 QQ 私聊身份。"
        self._send(qq, text)
        return {"ok": True, "reply": text, "qq": qq}

    # ---------- web binding code ----------
    def issue_bind_code(self, user_id: int, ttl: int = 600) -> tuple[str, int]:
        code = f"{secrets.randbelow(1_000_000):06d}"
        now = time.time()
        with self._lock:
            self._bind_codes = {
                key: value for key, value in self._bind_codes.items()
                if value[0] != int(user_id) and value[1] > now
            }
            self._bind_codes[code] = (int(user_id), now + ttl)
        return code, ttl

    def _consume_code(self, code: str) -> tuple[int, float] | None:
        now = time.time()
        with self._lock:
            entry = self._bind_codes.pop(code, None)
            if not entry or entry[1] <= now:
                return None
            return entry

    def _send(self, qq: str, text: str) -> None:
        try:
            self.api.send_private_text(qq, text)
        except NapCatError as exc:
            self.logger(f"[napcat] 发送失败：{exc}")
            self._record_error(f"发送失败：{exc}")

    def health(self) -> dict:
        with self._stats_lock:
            stats = dict(self._stats)
        settings = self.db.settings()
        return {
            "enabled": self.enabled,
            "bot_qq": self.bot_qq,
            "api": self.api.base_url,
            "whitelist_enabled": bool(settings.get("qq_whitelist_enabled", 0)),
            "whitelist_count": self.db.qq_whitelist_count(),
            "poll_alive": bool(self._poll_thread and self._poll_thread.is_alive()),
            "poll_error": self._poll_last_error,
            **stats,
        }

    def start_private_poll(self) -> None:
        """HTTP 上报客户端偶尔只发心跳时，用消息历史兜底私聊。"""
        if self._poll_thread or not self.enabled or not self.owner_qq:
            return
        self._poll_thread = threading.Thread(
            target=self._private_poll_loop, name="napcat-private-poll",
            daemon=True,
        )
        self._poll_thread.start()
        self.logger(
            f"[poll] started owner={self.owner_qq} bot={self.bot_qq}"
        )

    def _private_poll_loop(self) -> None:
        seeded = False
        while not self._poll_stop.is_set():
            try:
                data = self.api.call(
                    "get_friend_msg_history",
                    {"user_id": int(self.owner_qq), "count": 20},
                )
                messages = data.get("messages") if isinstance(data, dict) else []
                if not seeded:
                    for item in messages or []:
                        mid = str(item.get("message_id") or "")
                        if mid:
                            self._seen[mid] = time.time()
                    seeded = True
                    self.logger(f"[poll] seeded {len(messages or [])} messages")
                else:
                    self.logger(f"[poll] checked {len(messages or [])} messages")
                    for item in messages or []:
                        if item.get("user_id") == int(self.bot_qq or 0):
                            continue
                        mid = str(item.get("message_id") or "")
                        if not mid:
                            continue
                        if mid in self._seen:
                            continue
                        self.logger(
                            f"[poll] new {mid} user={item.get('user_id')} "
                            f"text={str(item.get('raw_message') or '')[:40]}"
                        )
                        while len(self._seen) > 2000:
                            self._seen.popitem(last=False)
                        event = dict(item)
                        event["post_type"] = "message"
                        event["message_type"] = "private"
                        event["self_id"] = int(self.bot_qq or 0)
                        self.accept(event)
            except Exception as exc:  # noqa: BLE001
                self._poll_last_error = str(exc)[:300]
                self._record_error(f"私聊轮询：{exc}")
                self.logger(f"[poll] error {exc}")
            self._poll_stop.wait(2.0)

    def close(self) -> None:
        self._poll_stop.set()
        self.executor.shutdown(wait=False, cancel_futures=True)
