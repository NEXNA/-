import tempfile
import unittest
from pathlib import Path

from bot.bili_routine import BiliRoutineStore


class BiliRoutineStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "routine.json"
        self.store = BiliRoutineStore(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_defaults(self):
        self.assertEqual(self.store.schedule()["enabled"], False)
        self.assertTrue(self.store.share_view_enabled())
        self.assertIn("BanG Dream", self.store.preferences())

    def test_share_view_toggle_persists(self):
        self.store.set_share_view(False)
        reloaded = BiliRoutineStore(self.path)
        self.assertFalse(reloaded.share_view_enabled())

    def test_schedule_and_preferences_persist(self):
        self.store.set_schedule("21:30", 3)
        self.store.set_preferences(["摩卡", "面包", "摩卡"])
        reloaded = BiliRoutineStore(self.path)
        self.assertEqual(reloaded.schedule()["time"], "21:30")
        self.assertEqual(reloaded.schedule()["count"], 3)
        self.assertEqual(reloaded.preferences(), ["摩卡", "面包"])

    def test_comments_and_seen_replies(self):
        self.store.add_comment("BV1xx", 123, "标题")
        self.store.mark_reply(456)
        reloaded = BiliRoutineStore(self.path)
        self.assertEqual(reloaded.comments()[0]["rpid"], 123)
        self.assertTrue(reloaded.seen_reply(456))
        self.assertFalse(reloaded.seen_reply(789))


if __name__ == "__main__":
    unittest.main()
