from __future__ import annotations

import json
import shutil
import unittest
import uuid
from pathlib import Path

from bot.canon import empty_canon
from bot.store import GroupStore


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(__file__).parent / ".tmp" / f"store-{uuid.uuid4().hex[:8]}"
        self.tmp.mkdir(parents=True)
        self.store = GroupStore(self.tmp, 123)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_append_and_pending(self):
        first = self.store.append_raw(1, "兰", "林晚是医师", "m1")
        second = self.store.append_raw(2, "小陈", "林晚二十七", "m2")
        self.assertEqual((first["id"], second["id"]), (1, 2))
        self.assertEqual(len(self.store.pending()), 2)
        self.assertEqual(self.store.count_pending(), 2)

    def test_mark_processed(self):
        self.store.append_raw(1, "兰", "a", "m1")
        self.store.append_raw(1, "兰", "b", "m2")
        self.store.mark_processed(1)
        self.assertEqual([e["text"] for e in self.store.pending()], ["b"])
        self.store.mark_processed(2)
        self.assertEqual(self.store.pending(), [])

    def test_raw_since(self):
        for i in range(3):
            self.store.append_raw(1, "兰", str(i), f"m{i}")
        self.assertEqual([e["id"] for e in self.store.raw_since(1)], [2, 3])
        self.assertEqual([e["id"] for e in self.store.raw_since(0, 2)], [1, 2])

    def test_snapshot_and_restore(self):
        self.store.append_raw(1, "兰", "a", "m1")
        self.store.mark_processed(1)
        canon = empty_canon()
        canon["updated_at"] = "before"
        self.store.save_canon(canon)
        self.store.snapshot(canon)
        canon["updated_at"] = "after"
        self.store.save_canon(canon)
        restored = self.store.restore_latest()
        self.assertIsNotNone(restored)
        restored_canon, upto, _ = restored
        self.assertEqual(restored_canon["updated_at"], "before")
        self.assertEqual(upto, 1)

    def test_usage_resets_on_new_day(self):
        self.store.add_usage(100, 20, "2026-10-19")
        self.assertEqual(self.store.usage("2026-10-19"), (100, 20))
        self.assertEqual(self.store.usage("2026-10-20"), (0, 0))
        self.store.add_usage(5, 5, "2026-10-20")
        self.assertEqual(self.store.usage("2026-10-20"), (5, 5))

    def test_seen_ids_persist(self):
        self.store.mark_seen("m1")
        self.assertTrue(self.store.is_seen("m1"))
        reloaded = GroupStore(self.tmp, 123)
        self.assertTrue(reloaded.is_seen("m1"))

    def test_corrupt_canon_raises(self):
        self.store.canon_path.write_text("{oops", encoding="utf-8")
        with self.assertRaises(Exception):
            self.store.load_canon()

    def test_export_file(self):
        path = self.store.save_export("# hello\n")
        self.assertTrue(path.exists())
        self.assertEqual(path.read_text(encoding="utf-8"), "# hello\n")
        data = json.loads((self.store.dir / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(data["next_raw_id"], 1)

    def test_stats_decay_and_sleep_rest(self):
        import time
        fun = self.store._load_fun()
        fun.update(hunger=100, sleepiness=100, mood=100,
                   updated_at=time.time() - 7200)
        self.store._save_fun(fun)
        stats = self.store.fun_stats(5, 2, 1)
        self.assertEqual(stats, {"hunger": 90, "sleepiness": 96, "mood": 98})
        self.store.sleep_for(1)
        self.store.wake_up()
        after = self.store.fun_stats(0, 0, 0)
        self.assertLess(after["sleepiness"], stats["sleepiness"])

    def test_economy_work_and_infinite(self):
        self.assertEqual(self.store.wallet(9, 80)["coins"], 80)
        ok, wait, coins = self.store.work(9, 20, 600)
        self.assertTrue(ok)
        self.assertEqual(wait, 0)
        self.assertEqual(coins, 100)
        ok, wait, _ = self.store.work(9, 20, 600)
        self.assertFalse(ok)
        self.assertGreater(wait, 0)
        self.store.set_infinite(True)
        self.assertTrue(self.store.spend_coins(9, 999, infinite=True))
        self.assertEqual(self.store.wallet(9, 0)["coins"], 100)

    def test_fun_decay_toggle(self):
        import time
        fun = self.store._load_fun()
        fun.update(hunger=100, sleepiness=100, mood=100,
                   updated_at=time.time() - 7200)
        self.store._save_fun(fun)
        self.store.set_fun_decay(False)
        stats = self.store.fun_stats(5, 2, 1, decay_enabled=False)
        self.assertEqual(stats, {"hunger": 100, "sleepiness": 100, "mood": 100})
        self.store.set_fun_decay(True)
        self.assertEqual(self.store.fun_stats(5, 2, 1), stats)

    def test_chat_budget_override_expires_next_day(self):
        self.assertEqual(self.store.chat_budget(1000, "2026-10-21"), 1000)
        self.store.set_chat_budget(500, "2026-10-21")
        self.assertEqual(self.store.chat_budget(1000, "2026-10-21"), 500)
        self.assertEqual(self.store.chat_budget(1000, "2026-10-22"), 1000)
        self.store.reset_chat_budget()
        self.assertEqual(self.store.chat_budget(1000, "2026-10-21"), 1000)


if __name__ == "__main__":
    unittest.main()
