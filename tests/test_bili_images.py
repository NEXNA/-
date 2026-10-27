from __future__ import annotations

import io
import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

from bot.bili_images import BiliImageStore


def make_png(color: str, label: str) -> bytes:
    image = Image.new("RGB", (240, 240), "white")
    draw = ImageDraw.Draw(image)
    if label == "A":
        draw.rectangle((10, 10, 230, 230), fill=color)
        draw.rectangle((40, 90, 200, 150), fill="black")
        draw.text((60, 105), label, fill="white")
    elif label == "B":
        image = Image.effect_noise((240, 240), 100).convert("RGB")
        draw = ImageDraw.Draw(image)
        draw.rectangle((80, 20, 160, 220), fill="black")
    else:
        draw.rectangle((10, 30, 230, 90), fill=color)
        draw.rectangle((10, 150, 230, 210), fill="black")
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


PNG = make_png("red", "A")
PNG2 = make_png("blue", "B")
PNG3 = make_png("green", "C")


class BiliImageStoreTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).parent / ".tmp" / f"bili-{uuid.uuid4().hex[:8]}"
        self.root.mkdir(parents=True)
        self.store = BiliImageStore(self.root, limit=2)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_add_dedupe_and_limit(self):
        first = self.store.add(PNG, {"url": "https://i0.hdslb.com/a.png"})
        self.assertIsNotNone(first)
        self.assertEqual(self.store.count(), 1)
        self.assertIsNone(self.store.add(PNG, {"url": "https://i0.hdslb.com/a.png"}))
        self.assertEqual(self.store.count(), 1)
        self.assertIsNotNone(self.store.add(PNG2, {"url": "https://i0.hdslb.com/b.png"}))
        self.assertEqual(self.store.count(), 2)
        self.assertIsNone(self.store.add(
            PNG3,
            {"url": "https://i0.hdslb.com/c.png"},
        ))
        self.assertTrue(self.store.random_image(quality_only=False).exists())

    def test_non_image_rejected(self):
        self.assertIsNone(self.store.add(b"not an image", {}))
        self.assertEqual(self.store.count(), 0)

    def test_fetch_with_fake_search(self):
        candidates = [
            {"url": "https://i0.hdslb.com/a.png", "title": "a", "keyword": "x"},
            {"url": "https://i0.hdslb.com/b.png", "title": "b", "keyword": "x"},
        ]
        self.store._search = lambda keyword, page: candidates  # type: ignore[method-assign]
        self.store._download = lambda url: PNG  # type: ignore[method-assign]
        with patch("bot.bili_images.time.sleep", lambda _: None):
            result = self.store.fetch("x", count=1, pages=1)
        self.assertEqual(result["added"], 1)
        self.assertEqual(result["count"], 1)


if __name__ == "__main__":
    unittest.main()
