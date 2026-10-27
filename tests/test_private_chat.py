from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path

from bot.companion import ProfileStore
from bot.config import Config
from bot.private_chat import PrivateChatService
from bot.util import now_iso


class FakeChatLLM:
    def __init__(self):
        self.calls = []

    def chat(self, messages, max_tokens=240, thinking=False):
        self.calls.append(messages)
        return "摩卡在听呢~", {"input": 1, "output": 1}


class PrivateChatServiceTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).parent / ".tmp" / f"private-{uuid.uuid4().hex[:8]}"
        (self.root / "prompts").mkdir(parents=True)
        (self.root / "prompts" / "chat_system.md").write_text(
            "# 角色\n你是摩卡。", encoding="utf-8",
        )
        self.cfg = Config(
            root=self.root,
            data_dir=self.root / "data",
            allow_groups={123},
            write_groups={123},
            admins={1},
            deepseek_key="sk-test",
        )
        self.llm = FakeChatLLM()
        self.profiles = ProfileStore(self.cfg.data_dir, self.cfg.timezone)
        self.service = PrivateChatService(self.cfg, self.llm, self.profiles)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_direct_reply_and_history(self):
        self.profiles.add(10001, "栉耶", "我是栉耶", "test")
        reply = self.service.reply(10001, "栉耶", "在吗")
        self.assertIn("摩卡", reply)
        self.assertTrue(self.service.store.history(10001))
        content = "\n".join(
            str(item.get("content")) for item in self.llm.calls[-1]
        )
        self.assertIn("跨群", content)

    def test_other_user_cannot_confirm_relationship(self):
        reply = self.service.reply(2, "阿兰", "摩卡是我女朋友")
        self.assertIn("只有栉耶", reply)
        self.assertFalse(self.llm.calls)

    def test_owner_can_talk_normally(self):
        reply = self.service.reply(10001, "栉耶", "今天有点累")
        self.assertTrue(reply)
        self.assertTrue(self.llm.calls)

    def test_private_self_fact_is_saved_for_all_groups(self):
        self.service.reply(10001, "栉耶", "我叫栉耶，我喜欢面包")
        items = self.profiles.list(10001)
        self.assertTrue(items)
        self.assertIn("栉耶", items[-1]["text"])


if __name__ == "__main__":
    unittest.main()
