from __future__ import annotations

import hmac
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .commands import Bot
from .config import Config

logger = logging.getLogger(__name__)


class EventServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, bot: Bot, webhook_token: str):
        super().__init__(address, EventHandler)
        self.bot = bot
        self.webhook_token = webhook_token
        self.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="event")

    def shutdown(self) -> None:  # type: ignore[override]
        self.executor.shutdown(wait=False, cancel_futures=True)
        super().shutdown()


class EventHandler(BaseHTTPRequestHandler):
    server_version = "QQSettingBot/1.0"
    server: EventServer

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        candidates = [
            (query.get("token") or [""])[0],
            (query.get("access_token") or [""])[0],
            self.headers.get("X-Webhook-Token", ""),
        ]
        auth = self.headers.get("Authorization", "")
        if auth:
            candidates.append(auth.strip())
        if auth.lower().startswith("bearer "):
            candidates.append(auth[7:].strip())
        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "event":
            candidates.append(parts[1])
        expected = self.server.webhook_token
        return bool(expected) and any(
            candidate and hmac.compare_digest(candidate, expected)
            for candidate in candidates
        )

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            self._json(200, self.server.bot.health())
        elif parsed.path == "/":
            self._json(200, {"service": "qq-setting-bot", "ok": True})
        else:
            self._json(404, {"error": "not found"})

    MAX_BODY = 2_000_000

    def _read_body(self) -> tuple[bytes | None, str]:
        """读请求体；兼容 NapCat 用 chunked 发送、没有 Content-Length 的情况。"""
        transfer = self.headers.get("Transfer-Encoding", "").lower()
        if "chunked" in transfer:
            data = bytearray()
            while True:
                line = self.rfile.readline(65536).strip()
                if not line:
                    return None, "bad chunk"
                try:
                    size = int(line.split(b";", 1)[0], 16)
                except ValueError:
                    return None, "bad chunk size"
                if size == 0:
                    # 读完 trailer 和结尾空行
                    while True:
                        trailer = self.rfile.readline(65536)
                        if trailer in (b"\r\n", b"\n", b""):
                            break
                    break
                if size < 0 or len(data) + size > self.MAX_BODY:
                    return None, "body too large"
                chunk = self.rfile.read(size)
                if len(chunk) != size:
                    return None, "short chunk"
                data.extend(chunk)
                self.rfile.read(2)  # 每块结尾的 CRLF
            return bytes(data), ""

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None, "bad content-length"
        if length <= 0 or length > self.MAX_BODY:
            return None, f"bad length ({length})"
        return self.rfile.read(length), ""

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        # 兼容 NapCat 把上报地址填成 http://127.0.0.1:8080（没有 /event）的情况
        if parsed.path not in ("/", "/event") and not parsed.path.startswith("/event/"):
            self._json(404, {"error": "not found"})
            return
        if not self._authorized():
            self._json(403, {"error": "bad token"})
            return
        if self.headers.get("Expect", "").lower() == "100-continue":
            self.wfile.write(b"HTTP/1.1 100 Continue\r\n\r\n")

        body, error = self._read_body()
        if body is None:
            logger.warning("拒绝上报：%s（Content-Length=%r, Transfer-Encoding=%r）",
                           error, self.headers.get("Content-Length"),
                           self.headers.get("Transfer-Encoding"))
            self._json(400, {"error": error})
            return
        try:
            event = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            logger.warning("上报不是合法 JSON：%s（%s 字节）", exc, len(body))
            self._json(400, {"error": "bad json"})
            return
        # 先回 200，避免 NapCat 上报超时；真正处理放到线程池
        self._json(200, {"status": "ok", "retcode": 0})
        try:
            self.server.executor.submit(self.server.bot.on_event, event)
        except RuntimeError:
            logger.warning("线程池已关闭，丢弃事件")

    def log_message(self, fmt: str, *args) -> None:
        # 不记录 query string，避免 webhook token 进日志
        logger.debug("%s - %s %s", self.address_string(), self.command,
                     urlparse(self.path).path)


def serve(bot: Bot, cfg: Config) -> None:
    try:
        server = EventServer((cfg.host, cfg.port), bot, cfg.webhook_token)
    except OSError as exc:
        logger.error("无法监听 %s:%s（端口被占用？）：%s", cfg.host, cfg.port, exc)
        raise SystemExit(3) from exc
    logger.info("webhook 监听 http://%s:%s/event", cfg.host, cfg.port)
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.shutdown()
        server.server_close()
