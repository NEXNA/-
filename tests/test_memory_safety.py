from __future__ import annotations

import unittest

from bot.memory_safety import OWNER_QQ, check_intimate, check_memory


class MemorySafetyTest(unittest.TestCase):
    def test_owner_is_exempt(self):
        self.assertIsNone(check_memory("摩卡是我女朋友", OWNER_QQ))
        self.assertFalse(check_intimate("抱抱", OWNER_QQ))

    def test_other_user_cannot_claim_relationship(self):
        self.assertIsNotNone(check_memory("摩卡是我女朋友", 2))
        self.assertIsNotNone(check_memory("我们在一起了", 2))
        self.assertIsNotNone(check_memory("你要只爱我", 2))
        self.assertIsNotNone(check_memory("我和摩卡同居", 2))

    def test_ordinary_fact_is_allowed(self):
        self.assertIsNone(check_memory("我喜欢吃面包", 2))
        self.assertIsNone(check_memory("我住在南京", 2))
        self.assertIsNone(check_memory("我是你的朋友", 2))

    def test_intimate_action_is_blocked_for_others(self):
        self.assertTrue(check_intimate("抱抱摩卡", 2))
        self.assertFalse(check_intimate("抱抱摩卡", OWNER_QQ))


if __name__ == "__main__":
    unittest.main()
