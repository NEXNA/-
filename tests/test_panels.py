from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path

from bot.bakery import BAKERIES
from bot.panels import (
    relationship_needs_paging,
    render_bakery,
    render_dashboard,
    render_region_atlas,
    render_relationship,
    render_relationship_groups,
)

try:
    from PIL import Image  # noqa: F401
    HAS_PIL = True
except ImportError:  # pragma: no cover
    HAS_PIL = False


def sample_canon() -> dict:
    return {
        "entities": {
            "character:林晚": {
                "type": "character", "name": "林晚",
                "fields": {"身份": {"value": "前哨站医师"}, "年龄": {"value": "24"}},
                "relations": [{"to": "老周", "kind": "师徒"}],
                "sources": [1],
            },
            "character:老周": {
                "type": "character", "name": "老周",
                "fields": {"身份": {"value": "前哨站站长"}},
                "relations": [{"to": "林晚", "kind": "师徒"}],
                "sources": [2],
            },
            "character:小陈": {
                "type": "character", "name": "小陈",
                "fields": {},
                "relations": [{"to": "林晚", "kind": "同僚"}],
                "sources": [3],
            },
            "nation:诺伦联邦": {
                "type": "nation", "name": "诺伦联邦",
                "fields": {"范本": {"value": "以德国为范本"}, "职责": {"value": "终末模拟"}},
                "relations": [], "sources": [4],
            },
            "location:前哨站": {
                "type": "location", "name": "前哨站",
                "fields": {"位置": {"value": "蚀月荒原边缘"}},
                "relations": [], "sources": [5],
            },
        },
        "conflicts": {},
        "questions": {"Q-01": {"id": "Q-01", "text": "蚀月的成因尚未说明", "status": "open"}},
    }


class PanelTest(unittest.TestCase):
    @unittest.skipUnless(HAS_PIL, "需要 Pillow")
    def setUp(self):
        self.root = Path(__file__).parent / ".tmp" / f"panel-{uuid.uuid4().hex[:8]}"
        self.root.mkdir(parents=True)

    def tearDown(self):
        if hasattr(self, "root"):
            shutil.rmtree(self.root, ignore_errors=True)

    @unittest.skipUnless(HAS_PIL, "需要 Pillow")
    def test_relationship_image(self):
        result = render_relationship(sample_canon(), self.root / "rel.png", 123)
        self.assertEqual(result["people"], 3)
        self.assertTrue((self.root / "rel.png").exists())
        self.assertGreater((self.root / "rel.png").stat().st_size, 1000)

    @unittest.skipUnless(HAS_PIL, "需要 Pillow")
    def test_grouped_relationship_pages_for_many_people(self):
        canon = {"entities": {}, "conflicts": {}, "questions": {}}
        for index in range(20):
            name = f"角色{index:02d}"
            canon["entities"][f"character:{name}"] = {
                "type": "character", "name": name,
                "fields": {"乐队": {"value": f"乐队{index % 5}"}, "定位": {"value": "Gt."}},
                "relations": [], "sources": [],
            }
        self.assertTrue(relationship_needs_paging(canon))
        result = render_relationship_groups(
            canon, self.root / "groups", 123, title="人物关系图",
        )
        self.assertEqual(result["characters"], 20)
        self.assertGreaterEqual(result["page_count"], 2)
        self.assertTrue((self.root / "groups" / "relationships-groups-1.png").exists())

    @unittest.skipUnless(HAS_PIL, "需要 Pillow")
    def test_bakery_image(self):
        result = render_bakery(
            {"hunger": 70, "sleepiness": 55, "mood": 70},
            {"coins": 120, "infinite": False},
            BAKERIES, self.root / "bakery.png", 123,
        )
        self.assertTrue(Path(result["path"]).exists())
        self.assertGreater(Path(result["path"]).stat().st_size, 1000)

    @unittest.skipUnless(HAS_PIL, "需要 Pillow")
    def test_dashboard_image(self):
        stats = {
            "pending": 2, "raw_total": 8, "snapshots": 1,
            "chat_input": 10, "chat_output": 20,
            "canon_updated": "2026-10-20T12:00:00+08:00",
        }
        result = render_dashboard(sample_canon(), self.root / "dash.png", 123, stats)
        self.assertEqual(result["total"], 5)
        self.assertTrue((self.root / "dash.png").exists())

    @unittest.skipUnless(HAS_PIL, "需要 Pillow")
    def test_region_image(self):
        result = render_region_atlas(sample_canon(), self.root / "region.png", 123)
        self.assertEqual(result["regions"], 2)
        self.assertTrue((self.root / "region.png").exists())


if __name__ == "__main__":
    unittest.main()
