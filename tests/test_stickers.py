from __future__ import annotations

import json
import shutil
import unittest
import uuid
from pathlib import Path

from bot.stickers import StickerLibrary


class FakeLLM:
    def __init__(self, response: str):
        self.response = response
        self.calls = []

    def chat(self, messages, max_tokens=None, temperature=0.9):
        self.calls.append(messages)
        return self.response, {"input": 10, "output": 5}


class StickerTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).parent / ".tmp" / f"sticker-{uuid.uuid4().hex[:8]}"
        self.root.mkdir(parents=True)
        self.dir = self.root / "stickers"
        self.dir.mkdir()
        self.image = self.dir / "meme.jpg"
        self.image.write_bytes(b"\xff\xd8fakejpeg")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_analyze_file(self):
        llm = FakeLLM(json.dumps({
            "emotion": "无语", "tags": ["无语", "呆滞"],
            "description": "半睁眼", "is_meme": True, "safe": True,
        }, ensure_ascii=False))
        lib = StickerLibrary(self.root, llm)
        meta = lib.analyze_file(self.image)
        self.assertEqual(meta["emotion"], "无语")
        self.assertEqual(meta["tags"], ["无语", "呆滞"])
        self.assertTrue(meta["is_meme"])
        self.assertTrue(meta["safe"])

    def test_pick_and_tags(self):
        llm = FakeLLM('{"emotion":"无语","tags":["无语","嫌弃"],"description":"","safe":true}')
        lib = StickerLibrary(self.root, llm)
        lib.index["items"]["x"] = {
            "file": "meme.jpg", "emotion": "无语",
            "tags": ["无语", "嫌弃"], "safe": True,
        }
        self.assertTrue(lib.has_items())
        self.assertIsNotNone(lib.pick("无语"))
        self.assertIsNotNone(lib.pick("嫌弃"))
        self.assertIsNone(lib.pick("开心"))
        self.assertIn("无语", lib.available_tags())
        self.assertEqual(lib.stats()["count"], 1)

    def test_unsafe_is_not_usable(self):
        lib = StickerLibrary(self.root, FakeLLM("{}"))
        lib.index["items"]["x"] = {
            "file": "meme.jpg", "emotion": "其他", "tags": [], "safe": False,
        }
        self.assertFalse(lib.has_items())
        self.assertIsNone(lib.pick("其他"))

    def test_scan_local(self):
        llm = FakeLLM('{"emotion":"开心","tags":["笑"],"description":"","is_meme":true,"safe":true}')
        lib = StickerLibrary(self.root, llm)
        counts = lib.scan_local()
        self.assertEqual(counts["found"], 1)
        self.assertEqual(counts["added"], 1)
        self.assertTrue(lib.has_items())


if __name__ == "__main__":
    unittest.main()
