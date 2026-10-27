from __future__ import annotations

import http.cookiejar
import json
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import app as app_module
import chat_engine
from db import Database

TMP_ROOT = Path(__file__).resolve().parent.parent / ".tmp-tests"
TMP_ROOT.mkdir(parents=True, exist_ok=True)


class FakeLLM:
    def __init__(self, *args, **kwargs):
        pass

    def chat(self, messages, temperature=0.9, max_tokens=600):
        return "这是测试回复。"


class WebTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="companion-web-", dir=TMP_ROOT))
        self.db = Database(self.tmp / "test.db")
        self.original = chat_engine.DeepSeekClient
        chat_engine.DeepSeekClient = FakeLLM
        self.server = app_module.AppServer(("127.0.0.1", 0), self.db)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar),
        )

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        chat_engine.DeepSeekClient = self.original
        shutil.rmtree(self.tmp, ignore_errors=True)

    def post_form(self, path: str, fields: dict):
        data = urllib.parse.urlencode(fields).encode()
        return self.opener.open(
            self.base + path, data=data, timeout=5,
        )

    def post_json(self, path: str, payload: dict):
        request = urllib.request.Request(
            self.base + path,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        return self.opener.open(request, timeout=5)

    def setup_admin(self):
        return self.post_form("/setup", {
            "username": "admin", "password": "secret123",
            "password2": "secret123",
        })

    def test_setup_login_chat_settings_persona(self):
        response = self.opener.open(self.base + "/", timeout=5)
        self.assertTrue(response.geturl().endswith("/setup"))

        response = self.setup_admin()
        html = response.read().decode()
        self.assertIn("诗蔻蒂", html)
        self.assertIn("伊邪那美", html)

        response = self.opener.open(self.base + "/", timeout=5)
        html = response.read().decode()
        self.assertIn("诗蔻蒂", html)
        self.assertIn("当前角色", html)

        response = self.opener.open(self.base + "/settings", timeout=5)
        html = response.read().decode()
        self.assertNotIn("QQ 绑定", html)
        self.assertNotIn("QQ 白名单", html)
        self.assertNotIn("NapCat 登录 QQ", html)

        response = self.post_json("/api/personas/save", {
            "key": "skuld", "name": "诗蔻蒂",
            "persona": "你是诗蔻蒂。你叫对方小昙。说话很短，省略号很多。",
            "greeting": "……小昙？", "model": "deepseek-chat",
            "temperature": 0.8, "max_tokens": 500,
        })
        self.assertTrue(json.loads(response.read())["ok"])

        response = self.post_json("/api/persona/switch", {"key": "izanami"})
        self.assertEqual(json.loads(response.read())["active"], "izanami")

        response = self.post_json("/api/settings", {
            "memory_enabled": 1, "auto_memory": 1,
            "fortune_enabled": 1, "intimacy_enabled": 1,
            "intimacy_start": 10,
        })
        self.assertTrue(json.loads(response.read())["ok"])

        response = self.post_json("/api/chat", {"message": "我叫阿岚，我喜欢面包"})
        payload = json.loads(response.read())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["reply"], "这是测试回复")
        self.assertEqual(payload["intimacy"], 11)
        self.assertEqual(payload["persona"], "伊邪那美")
        self.assertTrue(self.db.memories(1))

        response = self.opener.open(self.base + "/api/state", timeout=5)
        state = json.loads(response.read())
        self.assertEqual(state["persona"]["key"], "izanami")
        self.assertEqual(len(state["personas"]), 2)

    def test_fortune_page_and_api(self):
        self.setup_admin()
        response = self.opener.open(self.base + "/fortune", timeout=5)
        self.assertIn("今日运势", response.read().decode())
        response = self.opener.open(self.base + "/api/fortune", timeout=5)
        self.assertTrue(json.loads(response.read())["fortune"]["date"])

    def test_panel_page(self):
        self.setup_admin()
        response = self.opener.open(self.base + "/panel", timeout=5)
        html = response.read().decode()
        self.assertIn("功能面板", html)
        self.assertIn("/panel", html)
        self.assertIn("私聊里的面板", html)

    def test_napcat_event_is_disabled_without_bridge(self):
        self.setup_admin()
        response = self.opener.open(self.base + "/napcat/health", timeout=5)
        self.assertFalse(json.loads(response.read())["enabled"])

        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.post_json("/api/napcat/switch", {"qq": "222222222"})
        self.assertEqual(raised.exception.code, 403)

        with self.assertRaises(urllib.error.HTTPError) as raised:
            request = urllib.request.Request(
                self.base + "/napcat/event", data=b"{}",
                headers={"Content-Type": "application/json"}, method="POST",
            )
            self.opener.open(request, timeout=5)
        self.assertEqual(raised.exception.code, 503)


if __name__ == "__main__":
    unittest.main()
