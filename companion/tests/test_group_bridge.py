from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import napcat
from db import Database
from napcat import NapCatBridge


class FakeAPI:
    def __init__(self):
        self.groups = []
        self.privates = []

    def send_group_text(self, group_id, text):
        self.groups.append((group_id, text))

    def send_private_text(self, qq, text):
        self.privates.append((qq, text))


class GroupBridgeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="companion-group-"))
        self.db = Database(self.tmp / "test.db")
        self.api = FakeAPI()
        self.bridge = NapCatBridge(
            self.db, enabled=True, event_token="t", bot_qq="999999",
            api=self.api, logger=lambda *_: None,
        )
        self.original = napcat.chat_once
        napcat.chat_once = lambda *args, **kwargs: {
            "reply": "我在。", "persona": "诗蔻蒂",
        }

    def tearDown(self):
        napcat.chat_once = self.original
        self.bridge.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def event(self, text, at=True, group_id="123456", message_id="m1"):
        segments = []
        if at:
            segments.append({"type": "at", "data": {"qq": "999999"}})
        segments.append({"type": "text", "data": {"text": text}})
        return {
            "post_type": "message", "message_type": "group",
            "group_id": group_id, "user_id": "222222",
            "self_id": "999999", "message_id": message_id,
            "sender": {"nickname": "群友"},
            "message": segments,
        }

    def test_group_at_replies(self):
        result = self.bridge.process_event(self.event("在吗"))
        self.assertTrue(result["ok"])
        self.assertEqual(result["reply"], "我在。")
        self.assertTrue(self.api.groups)

    def test_group_without_at_is_ignored(self):
        result = self.bridge.process_event(self.event("在吗", at=False))
        self.assertFalse(result["ok"])
        self.assertFalse(self.api.groups)

    def test_group_whitelist_blocks_unlisted_group(self):
        self.db.update_settings({"group_whitelist_enabled": 1})
        result = self.bridge.process_event(self.event("在吗"))
        self.assertFalse(result["ok"])
        self.assertFalse(self.api.groups)
        self.db.add_group_whitelist("123456")
        result = self.bridge.process_event(self.event("在吗", message_id="m2"))
        self.assertTrue(result["ok"])

    def test_private_panel_command(self):
        self.db.create_user("admin", "secret123")
        self.bridge.owner_qq = "10001"
        event = {
            "post_type": "message", "message_type": "private",
            "user_id": "10001", "message_id": "panel-1",
            "self_id": "999999", "sender": {"nickname": "管理员"},
            "message": [{"type": "text", "data": {"text": "/面板"}}],
        }
        result = self.bridge.process_event(event)
        self.assertTrue(result["ok"])
        self.assertIn("私聊面板", result["reply"])
        self.assertTrue(self.api.privates)


if __name__ == "__main__":
    unittest.main()
