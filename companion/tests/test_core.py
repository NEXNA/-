from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from db import Database
from fortune import make_fortune

TMP_ROOT = Path(__file__).resolve().parent.parent / ".tmp-tests"
TMP_ROOT.mkdir(parents=True, exist_ok=True)


class CoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="companion-test-", dir=TMP_ROOT))
        self.db = Database(self.tmp / "test.db")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_new_database_has_two_personas_and_no_admin(self):
        settings = self.db.settings()
        self.assertEqual(settings["bot_name"], "")
        self.assertEqual(self.db.user_count(), 0)
        personas = self.db.personas()
        self.assertEqual([item["key"] for item in personas], ["skuld", "izanami"])
        self.assertEqual(personas[0]["name"], "诗蔻蒂")
        self.assertEqual(personas[1]["name"], "伊邪那美")
        self.assertGreater(len(personas[0]["persona"]), 1500)
        self.assertGreater(len(personas[1]["persona"]), 1500)

    def test_setup_login_session(self):
        uid = self.db.create_user("admin", "secret123")
        self.assertEqual(self.db.check_login("admin", "secret123"), uid)
        self.assertIsNone(self.db.check_login("admin", "wrong"))
        token = self.db.create_session(uid)
        self.assertEqual(self.db.session_user(token), uid)
        self.db.delete_session(token)
        self.assertIsNone(self.db.session_user(token))

    def test_persona_switch_and_qq_binding(self):
        uid = self.db.create_user("admin", "secret123")
        self.assertEqual(self.db.user_persona_key(uid), "")
        self.db.set_user_persona(uid, "izanami")
        self.assertEqual(self.db.user_persona_key(uid), "izanami")
        with self.assertRaises(ValueError):
            self.db.set_user_persona(uid, "missing")

        self.db.bind_qq(uid, "123456789", "阿岚")
        row = self.db.user_by_qq("123456789")
        self.assertEqual(int(row["id"]), uid)
        self.assertEqual(self.db.qq_for_user(uid), "123456789")
        self.assertTrue(self.db.is_qq_whitelisted("123456789"))

        other = self.db.create_user("other", "secret123")
        with self.assertRaises(ValueError):
            self.db.bind_qq(other, "123456789")
        self.db.unbind_qq(uid)
        self.assertEqual(self.db.qq_for_user(uid), "")

    def test_qq_whitelist(self):
        self.assertEqual(self.db.qq_whitelist(), [])
        item = self.db.add_qq_whitelist("123456789", "我的小号")
        self.assertEqual(item["qq"], "123456789")
        self.assertTrue(self.db.is_qq_whitelisted("123456789"))
        self.assertEqual(self.db.qq_whitelist_count(), 1)
        self.db.add_qq_whitelist("123456789", "改备注")
        self.assertEqual(self.db.qq_whitelist()[0]["note"], "改备注")
        self.assertFalse(self.db.remove_qq_whitelist("000"))
        self.assertTrue(self.db.remove_qq_whitelist("123456789"))
        self.assertEqual(self.db.qq_whitelist_count(), 0)
        with self.assertRaises(ValueError):
            self.db.add_qq_whitelist("abc")

    def test_memory_and_intimacy(self):
        uid = self.db.create_user("admin", "secret123")
        self.db.add_memory(uid, "我喜欢下雨天")
        self.db.add_memory(uid, "我喜欢下雨天")
        self.assertEqual(len(self.db.memories(uid)), 1)
        self.assertEqual(self.db.touch_intimacy(uid, 1), 11)
        self.db.set_intimacy(uid, 55)
        self.assertEqual(self.db.state(uid)["intimacy"], 55)
        self.assertEqual(self.db.clear_memories(uid), 1)

    def test_fortune_is_stable_per_day(self):
        one = make_fortune(1, "admin", "2026-10-21")
        two = make_fortune(1, "admin", "2026-10-21")
        self.assertEqual(one, two)
        self.assertIn(one["overall"], range(1, 6))
        self.assertTrue(one["summary"])


if __name__ == "__main__":
    unittest.main()
