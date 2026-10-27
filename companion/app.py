"""陪伴工作台：带登录的聊天机器人控制台。

启动：python app.py
数据：data/companion.db
"""
from __future__ import annotations

import argparse
import json
import os
import re
import threading
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from chat_engine import chat_once, intimacy_label, resolve_persona
from db import Database
from fortune import dumps as fortune_dumps
from fortune import make_fortune, today
from llm import LLMError
from napcat import NapCatBridge
from ui import (
    auth_page,
    chat_page,
    design_page,
    fortune_page,
    memories_page,
    panel_page,
    settings_page,
)

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "companion.db"
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'self'; style-src 'unsafe-inline'; "
        "script-src 'unsafe-inline'; img-src 'self' data:; "
        "connect-src 'self'; form-action 'self'"
    ),
}


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


class AppServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, db: Database, napcat: NapCatBridge | None = None):
        super().__init__(address, Handler)
        self.db = db
        self.napcat = napcat


class Handler(BaseHTTPRequestHandler):
    server_version = "CompanionStudio/1.1"
    sys_version = ""

    @property
    def db(self) -> Database:
        return self.server.db  # type: ignore[attr-defined]

    @property
    def napcat(self):
        return self.server.napcat  # type: ignore[attr-defined]

    def log_message(self, fmt, *args):
        # 控制台只打印简短访问日志，不记录密码、聊天内容和 token。
        message = fmt % args
        message = re.sub(r"(token|access_token)=[^&\s]+", r"\1=***", message)
        print(f"[{self.log_date_time_string()}] {message}")

    # ---------- response helpers ----------
    def _headers(self, status: int, content_type: str, length: int,
                 extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        for key, value in SECURITY_HEADERS.items():
            self.send_header(key, value)
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()

    def html(self, body: str, status: int = 200) -> None:
        data = body.encode("utf-8")
        self._headers(status, "text/html; charset=utf-8", len(data))
        self.wfile.write(data)

    def json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(data))
        self.wfile.write(data)

    def redirect(self, location: str, cookie: str | None = None) -> None:
        extra = {"Location": location}
        if cookie:
            extra["Set-Cookie"] = cookie
        self._headers(HTTPStatus.SEE_OTHER, "text/plain; charset=utf-8", 0, extra)

    def cookie(self) -> str:
        raw = self.headers.get("Cookie", "")
        try:
            jar = SimpleCookie(raw)
            morsel = jar.get("sid")
            return morsel.value if morsel else ""
        except Exception:  # noqa: BLE001
            return ""

    def user(self) -> int | None:
        return self.db.session_user(self.cookie())

    def request_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > 1_000_000:
            raise ValueError("请求太大")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("JSON 格式错误") from exc
        if not isinstance(data, dict):
            raise ValueError("JSON 必须是对象")
        return data

    def form(self) -> dict[str, str]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(min(length, 100_000)).decode("utf-8", errors="replace")
        parsed = urllib.parse.parse_qs(raw, keep_blank_values=True)
        return {key: values[-1] if values else "" for key, values in parsed.items()}

    # ---------- auth ----------
    def session_cookie(self, token: str) -> str:
        return (
            f"sid={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={7 * 86400}"
        )

    # ---------- GET ----------
    def do_GET(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        try:
            if path == "/login":
                if self.db.user_count() == 0:
                    return self.redirect("/setup")
                if self.user():
                    return self.redirect("/")
                return self.html(auth_page("login"))
            if path == "/setup":
                if self.db.user_count() > 0:
                    return self.redirect("/login")
                return self.html(auth_page("setup"))
            if path == "/logout":
                token = self.cookie()
                if token:
                    self.db.delete_session(token)
                return self.redirect(
                    "/login",
                    "sid=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0",
                )
            if path == "/favicon.ico":
                self._headers(HTTPStatus.NO_CONTENT, "image/x-icon", 0)
                return
            if path == "/napcat/health":
                if not self.napcat:
                    return self.json({"ok": False, "enabled": False})
                return self.json({"ok": True, **self.napcat.health()})
            user_id = self.user()
            if not user_id:
                return self.redirect("/login")
            row = self.db.user_by_id(user_id)
            username = self._display_name(row)
            settings = self.db.settings()
            persona = self._persona(user_id, settings)
            personas = self.db.personas()
            if path == "/":
                history = self.db.messages(user_id, 40)
                state = self._ensure_state(user_id, settings)
                fortune = None
                if settings.get("fortune_enabled", 1):
                    fortune = self._fortune(user_id, username, settings)
                return self.html(chat_page(
                    settings, username, history, int(state["intimacy"]),
                    fortune, persona, personas,
                ))
            if path == "/settings":
                return self.html(settings_page(
                    settings, username, personas, persona["key"],
                    self.db.qq_for_user(user_id),
                    bool(self.napcat and self.napcat.enabled),
                    self.napcat.bot_qq if self.napcat else "",
                    self.db.qq_whitelist(),
                    bool(settings.get("qq_whitelist_enabled", 0)),
                    self._napcat_accounts(),
                ))
            if path == "/memories":
                return self.html(memories_page(
                    settings, username, self.db.memories(user_id, 200), persona,
                ))
            if path == "/fortune":
                payload = None
                if settings.get("fortune_enabled", 1):
                    payload = self._fortune(user_id, username, settings)
                return self.html(fortune_page(
                    settings, username, payload, persona,
                ))
            if path == "/panel":
                state = self._ensure_state(user_id, settings)
                payload = None
                if settings.get("fortune_enabled", 1):
                    payload = self._fortune(user_id, username, settings)
                return self.html(panel_page(
                    settings, username, persona, state,
                    len(self.db.memories(user_id, 200)),
                    self.db.qq_for_user(user_id), payload,
                    os.environ.get("NAPCAT_BOT_QQ", ""),
                ))
            if path == "/design":
                try:
                    content = (ROOT / "design" / "character_bible.md").read_text(
                        encoding="utf-8",
                    )
                except OSError:
                    content = "角色资料文件不存在。"
                return self.html(design_page(
                    username, persona.get("name", ""), content,
                ))
            if path == "/api/state":
                state = self._ensure_state(user_id, settings)
                return self.json({
                    "ok": True,
                    "intimacy": int(state["intimacy"]),
                    "label": intimacy_label(int(state["intimacy"])),
                    "settings": self._public_settings(settings),
                    "persona": persona,
                    "personas": personas,
                    "qq": self.db.qq_for_user(user_id),
                    "napcat": self.napcat.health() if self.napcat else {
                        "enabled": False,
                    },
                })
            if path == "/api/personas":
                return self.json({
                    "ok": True, "personas": personas,
                    "active": persona["key"],
                })
            if path == "/api/fortune":
                if not settings.get("fortune_enabled", 1):
                    return self.json({"ok": False, "error": "今日运势已关闭"}, 400)
                return self.json({
                    "ok": True,
                    "fortune": self._fortune(user_id, username, settings),
                })
            if path == "/api/memories":
                return self.json({
                    "ok": True,
                    "memories": self.db.memories(user_id, 200),
                })
            if path == "/api/history":
                return self.json({
                    "ok": True,
                    "messages": self.db.messages(user_id, 100),
                })
            return self.json({"ok": False, "error": "页面不存在"}, 404)
        except Exception as exc:  # noqa: BLE001
            print("GET error:", type(exc).__name__, exc)
            return self.json({"ok": False, "error": "服务器错误"}, 500)

    # ---------- POST ----------
    def do_POST(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        try:
            if path == "/napcat/event":
                if not self.napcat:
                    return self.json({"ok": False, "error": "NapCat 未启用"}, 503)
                return self.napcat.handle_http(self)
            if path == "/setup":
                if self.db.user_count() > 0:
                    return self.redirect("/login")
                data = self.form()
                username = data.get("username", "")
                password = data.get("password", "")
                password2 = data.get("password2", "")
                if password != password2:
                    return self.html(auth_page("setup", "两次密码不一致"))
                try:
                    user_id = self.db.create_user(username, password)
                except Exception as exc:  # noqa: BLE001
                    return self.html(auth_page("setup", str(exc)))
                settings = self.db.settings()
                self.db.set_intimacy(user_id, int(settings.get("intimacy_start", 10)))
                token = self.db.create_session(user_id)
                return self.redirect("/", self.session_cookie(token))
            if path == "/login":
                data = self.form()
                user_id = self.db.check_login(
                    data.get("username", ""), data.get("password", ""),
                )
                if not user_id:
                    return self.html(auth_page("login", "用户名或密码不对"))
                token = self.db.create_session(user_id)
                return self.redirect("/", self.session_cookie(token))
            user_id = self.user()
            if not user_id:
                return self.json({"ok": False, "error": "请先登录"}, 401)
            settings = self.db.settings()
            if path == "/api/chat":
                return self._chat(user_id, settings)
            if path == "/api/settings":
                data = self.request_json()
                return self._update_settings(data)
            if path == "/api/personas/save":
                data = self.request_json()
                return self._update_persona(data)
            if path == "/api/persona/switch":
                data = self.request_json()
                key = str(data.get("key") or "")
                self.db.set_user_persona(user_id, key)
                persona = self._persona(user_id, settings)
                return self.json({
                    "ok": True, "active": persona["key"], "persona": persona,
                })
            if path == "/api/qq/bind-code":
                return self._qq_bind_code(user_id)
            if path == "/api/qq/unbind":
                self.db.unbind_qq(user_id)
                return self.json({"ok": True, "qq": ""})
            if path == "/api/qq/whitelist/add":
                data = self.request_json()
                item = self.db.add_qq_whitelist(
                    str(data.get("qq") or ""), str(data.get("note") or ""),
                )
                return self.json({
                    "ok": True, "item": item,
                    "whitelist": self.db.qq_whitelist(),
                })
            if path == "/api/qq/whitelist/remove":
                data = self.request_json()
                removed = self.db.remove_qq_whitelist(str(data.get("qq") or ""))
                return self.json({
                    "ok": removed, "removed": removed,
                    "whitelist": self.db.qq_whitelist(),
                })
            if path == "/api/qq/whitelist/toggle":
                data = self.request_json()
                enabled = 1 if data.get("enabled") else 0
                self.db.update_settings({"qq_whitelist_enabled": enabled})
                return self.json({"ok": True, "enabled": bool(enabled)})
            if path == "/api/napcat/switch":
                return self.json({
                    "ok": False,
                    "error": "本项目已与 NapCat 隔离，不接入 QQ；QQ 功能只在青叶摩卡项目里。",
                }, 403)
            if path == "/api/intimacy":
                data = self.request_json()
                value = max(0, min(100, int(data.get("intimacy", 0))))
                self.db.set_intimacy(user_id, value)
                return self.json({
                    "ok": True, "intimacy": value,
                    "label": intimacy_label(value),
                })
            if path == "/api/memories":
                data = self.request_json()
                item = self.db.add_memory(
                    user_id, str(data.get("text", "")), "manual",
                )
                return self.json({
                    "ok": True, "memory": item,
                    "memories": self.db.memories(user_id, 200),
                })
            if path == "/api/memories/delete":
                data = self.request_json()
                ok = self.db.delete_memory(user_id, int(data.get("id", 0)))
                return self.json({"ok": ok})
            if path == "/api/memories/clear":
                removed = self.db.clear_memories(user_id)
                return self.json({"ok": True, "removed": removed})
            if path == "/api/history/clear":
                self.db.clear_messages(user_id)
                return self.json({"ok": True})
            return self.json({"ok": False, "error": "接口不存在"}, 404)
        except (ValueError, TypeError) as exc:
            return self.json({"ok": False, "error": str(exc)}, 400)
        except Exception as exc:  # noqa: BLE001
            print("POST error:", type(exc).__name__, exc)
            return self.json({"ok": False, "error": "服务器错误"}, 500)

    # ---------- domain ----------
    def _ensure_state(self, user_id: int, settings: dict) -> dict:
        state = self.db.state(user_id)
        if not state.get("last_chat_at") and not self.db.messages(user_id, 1):
            start = int(settings.get("intimacy_start", 10))
            if int(state.get("intimacy", 0)) != start:
                self.db.set_intimacy(user_id, start)
                state["intimacy"] = start
        return state

    def _display_name(self, row) -> str:
        if not row:
            return "用户"
        keys = set(row.keys())
        nickname = str(row["nickname"] or "") if "nickname" in keys else ""
        return nickname or str(row["username"] or "用户")

    def _persona(self, user_id: int, settings: dict) -> dict:
        return resolve_persona(self.db, user_id, settings)

    def _public_settings(self, settings: dict) -> dict:
        keys = (
            "bot_name", "greeting", "model", "temperature", "max_tokens",
            "memory_enabled", "auto_memory", "fortune_enabled",
            "intimacy_enabled", "intimacy_start", "default_persona",
            "qq_whitelist_enabled",
        )
        return {key: settings.get(key) for key in keys}

    def _fortune(self, user_id: int, username: str, settings: dict) -> dict:
        day = today()
        state = self.db.state(user_id)
        if state.get("fortune_date") == day and state.get("fortune_json"):
            try:
                return json.loads(state["fortune_json"])
            except json.JSONDecodeError:
                pass
        payload = make_fortune(user_id, username, day)
        self.db.save_fortune(user_id, day, fortune_dumps(payload))
        return payload

    def _chat(self, user_id: int, settings: dict) -> None:
        data = self.request_json()
        message = " ".join(str(data.get("message", "")).split()).strip()
        if not message:
            return self.json({"ok": False, "error": "说点什么吧"}, 400)
        if len(message) > 2000:
            return self.json({"ok": False, "error": "单条消息最多 2000 字"}, 400)
        row = self.db.user_by_id(user_id)
        username = self._display_name(row)
        persona = self._persona(user_id, settings)
        try:
            result = chat_once(
                self.db, user_id, username, message, settings, persona,
                api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
                base_url=os.environ.get(
                    "DEEPSEEK_BASE_URL", "https://api.deepseek.com",
                ),
            )
        except ValueError as exc:
            return self.json({"ok": False, "error": str(exc)}, 400)
        except LLMError as exc:
            return self.json({"ok": False, "error": str(exc)}, 502)
        return self.json(result)

    def _update_persona(self, data: dict) -> None:
        key = str(data.get("key") or "").strip()
        if not self.db.persona(key):
            raise ValueError("角色不存在")
        name = str(data.get("name", "")).strip()[:40]
        persona_text = str(data.get("persona", "")).strip()[:12000]
        greeting = str(data.get("greeting", "")).strip()[:500]
        model = str(data.get("model", "deepseek-chat"))
        if model not in ("deepseek-chat", "deepseek-reasoner", "deepseek-flash"):
            raise ValueError("不支持的模型")
        if not name:
            raise ValueError("角色名不能为空")
        if len(persona_text) < 10:
            raise ValueError("角色设定太短")
        temperature = max(0.0, min(1.5, float(data.get("temperature", 0.9))))
        max_tokens = max(64, min(4096, int(data.get("max_tokens", 600))))
        updated = self.db.save_persona(key, {
            "name": name,
            "persona": persona_text,
            "greeting": greeting,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
        })
        return self.json({"ok": True, "persona": updated})

    def _napcat_accounts(self) -> list[str]:
        # 隔离：新项目不读取、不修改 NapCat 账号。
        return []

    def _qq_bind_code(self, user_id: int) -> None:
        if not self.napcat or not self.napcat.enabled:
            return self.json({"ok": False, "error": "NapCat 未启用"}, 503)
        qq = self.db.qq_for_user(user_id)
        if qq:
            return self.json({
                "ok": True, "qq": qq, "code": "",
                "bot_qq": self.napcat.bot_qq,
            })
        code, ttl = self.napcat.issue_bind_code(user_id)
        return self.json({
            "ok": True, "qq": "", "code": code,
            "expires_in": ttl, "bot_qq": self.napcat.bot_qq,
        })

    def _update_settings(self, data: dict) -> None:
        try:
            intimacy_start = max(0, min(100, int(data.get("intimacy_start", 10))))
            values = {
                "memory_enabled": 1 if data.get("memory_enabled") else 0,
                "auto_memory": 1 if data.get("auto_memory") else 0,
                "fortune_enabled": 1 if data.get("fortune_enabled") else 0,
                "intimacy_enabled": 1 if data.get("intimacy_enabled") else 0,
                "intimacy_start": intimacy_start,
            }
            if "qq_whitelist_enabled" in data:
                values["qq_whitelist_enabled"] = (
                    1 if data.get("qq_whitelist_enabled") else 0
                )
            updated = self.db.update_settings(values)
        except (TypeError, ValueError) as exc:
            return self.json({"ok": False, "error": str(exc)}, 400)
        return self.json({
            "ok": True,
            "settings": self._public_settings(updated),
        })


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="陪伴工作台")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args(argv)

    load_env(ROOT / ".env")
    db = Database(DB_PATH)
    settings = db.settings()
    napcat = NapCatBridge.from_env(db)
    if napcat.enabled:
        napcat.sync_login()
        napcat.start_private_poll()
    print("=" * 54)
    print("  陪伴工作台 · Companion Studio")
    print("  角色：诗蔻蒂 / 伊邪那美（可在控制台切换）")
    print(f"  数据：{DB_PATH}")
    print(f"  地址：http://{args.host}:{args.port}")
    if napcat.enabled:
        print(f"  NapCat：作为可切换目标启用  bot QQ={napcat.bot_qq or '未填写'}")
    else:
        print("  NapCat：未启用（由 Mocha 控制台切换上报目标）")
    print("=" * 54)
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("警告：没有 DEEPSEEK_API_KEY，聊天会报错。请在 .env 填写。")
    if not args.no_open:
        threading.Timer(
            0.8, lambda: webbrowser.open(f"http://127.0.0.1:{args.port}"),
        ).start()
    server = AppServer((args.host, args.port), db, napcat)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        server.server_close()
        if napcat:
            napcat.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
