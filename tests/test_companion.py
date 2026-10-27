from __future__ import annotations

import shutil
import time
import unittest
import uuid
from pathlib import Path

from bot.companion import (
    MemoryStore,
    ReminderStore,
    parse_reminder_time,
)


class CompanionStoreTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).parent / ".tmp" / f"companion-{uuid.uuid4().hex[:8]}"
        self.root.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_memory_add_relevant_forget(self):
        memory = MemoryStore(self.root, 123)
        self.assertIsNotNone(memory.add(2, "兰", "我喜欢吃面包", "manual"))
        self.assertEqual(memory.count(), 1)
        self.assertIsNone(memory.add(2, "兰", "我喜欢吃面包"))
        self.assertEqual(len(memory.relevant(2, "面包")), 1)
        self.assertEqual(memory.forget(2, "面包"), 1)
        self.assertEqual(memory.count(), 0)

    def test_reminders_due_and_cancel(self):
        store = ReminderStore(self.root)
        item = store.add(2, "private", 2, "喝水", time.time() - 1, "阿兰")
        due = store.due()
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0]["text"], "喝水")
        self.assertEqual(store.list(2), [])
        second = store.add(2, "group", 123, "开会", time.time() + 3600)
        self.assertTrue(store.cancel(second["id"], 2))
        self.assertFalse(store.cancel(item["id"], 2))

    def test_parse_reminder_time(self):
        now = time.time()
        relative = parse_reminder_time("30分钟")
        self.assertIsNotNone(relative)
        self.assertGreater(relative, now + 1700)
        tomorrow = parse_reminder_time("明天 09:00")
        self.assertIsNotNone(tomorrow)
        self.assertGreater(tomorrow, now)
        self.assertIsNone(parse_reminder_time("没有时间"))


if __name__ == "__main__":
    unittest.main()
