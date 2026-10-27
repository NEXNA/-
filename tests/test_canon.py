from __future__ import annotations

import unittest

from bot.canon import (
    apply_patch,
    empty_canon,
    open_conflicts,
    remove_entity,
    render_digest,
    render_full,
    resolve_conflict,
    search,
)


def entity(name="林晚", etype="character", fields=None, aliases=None,
           relations=None, sources=None):
    return {
        "type": etype,
        "name": name,
        "aliases": aliases or [],
        "fields": fields or {},
        "relations": relations or [],
        "source_ids": sources or [1],
    }


def apply(canon, entities=None, conflicts=None, questions=None, allowed=None):
    patch = {"entities": entities or [], "conflicts": conflicts or [],
             "open_questions": questions or []}
    return apply_patch(canon, patch, set(allowed or [1, 2, 3]), "2026-10-19T18:00:00+08:00")


class CanonTest(unittest.TestCase):
    def test_add_entity_and_field(self):
        canon = empty_canon()
        stats = apply(canon, [entity(fields={"身份": "前哨站医师"})])
        self.assertEqual(stats["added"], 1)
        key = "character:林晚"
        self.assertIn(key, canon["entities"])
        self.assertEqual(canon["entities"][key]["fields"]["身份"]["value"], "前哨站医师")
        self.assertEqual(canon["entities"][key]["fields"]["身份"]["sources"], [1])

    def test_alias_merges_into_same_entity(self):
        canon = empty_canon()
        apply(canon, [entity(aliases=["晚姐"], fields={"身份": "医师"})])
        stats = apply(canon, [entity(name="晚姐", fields={"年龄": "24"}, sources=[2])])
        self.assertEqual(len(canon["entities"]), 1)
        self.assertEqual(stats["updated"], 1)
        key = "character:林晚"
        self.assertIn("年龄", canon["entities"][key]["fields"])

    def test_conflicting_value_does_not_overwrite(self):
        canon = empty_canon()
        apply(canon, [entity(fields={"年龄": "24"})])
        stats = apply(canon, [entity(fields={"年龄": "27"}, sources=[2])])
        self.assertEqual(stats["conflicts_new"], 1)
        field = canon["entities"]["character:林晚"]["fields"]["年龄"]
        self.assertEqual(field["value"], "24")
        self.assertEqual(field["conflict_ids"], ["C-01"])
        conflict = canon["conflicts"]["C-01"]
        self.assertEqual([v["value"] for v in conflict["values"]], ["24", "27"])
        self.assertEqual(conflict["status"], "open")

    def test_third_value_extends_existing_conflict(self):
        canon = empty_canon()
        apply(canon, [entity(fields={"年龄": "24"})])
        apply(canon, [entity(fields={"年龄": "27"}, sources=[2])])
        stats = apply(canon, [entity(fields={"年龄": "30"}, sources=[3])])
        self.assertEqual(stats["conflicts_new"], 0)
        self.assertEqual(stats["conflicts_extended"], 1)
        self.assertEqual(len(canon["conflicts"]), 1)
        self.assertEqual(len(canon["conflicts"]["C-01"]["values"]), 3)

    def test_invalid_source_is_dropped(self):
        canon = empty_canon()
        stats = apply(canon, [entity(sources=[99])])
        self.assertEqual(stats["dropped"], 1)
        self.assertEqual(canon["entities"], {})

    def test_string_sources_are_parsed(self):
        canon = empty_canon()
        item = entity()
        item["source_ids"] = "1, 2"
        stats = apply(canon, [item])
        self.assertEqual(stats["added"], 1)
        self.assertEqual(canon["entities"]["character:林晚"]["sources"], [1, 2])

    def test_missing_source_is_dropped(self):
        canon = empty_canon()
        bad = entity()
        bad["source_ids"] = []
        stats = apply(canon, [bad])
        self.assertEqual(stats["dropped"], 1)

    def test_conflict_reported_by_model(self):
        canon = empty_canon()
        stats = apply(
            canon,
            [entity(fields={"年龄": "24"})],
            conflicts=[{
                "entity": "林晚", "field": "年龄",
                "values": ["24", "27"], "source_ids": [1, 2],
                "question": "林晚到底几岁？",
            }],
        )
        self.assertEqual(stats["conflicts_new"], 1)
        self.assertEqual(canon["conflicts"]["C-01"]["question"], "林晚到底几岁？")

    def test_conflict_values_keep_their_own_sources(self):
        canon = empty_canon()
        apply(
            canon,
            [entity(fields={"年龄": "24"})],
            conflicts=[{
                "entity": "林晚", "field": "年龄",
                "values": [
                    {"value": "24", "source_ids": [1]},
                    {"value": "27", "source_ids": [2]},
                ],
                "question": "几岁？",
            }],
        )
        values = canon["conflicts"]["C-01"]["values"]
        self.assertEqual(values[0]["sources"], [1])
        self.assertEqual(values[1]["sources"], [2])

    def test_resolve_conflict_updates_field(self):
        canon = empty_canon()
        apply(canon, [entity(fields={"年龄": "24"})])
        apply(canon, [entity(fields={"年龄": "27"}, sources=[2])])
        conflict = resolve_conflict(canon, "c-01", "27", 10001, "2026-10-19T19:00:00+08:00")
        self.assertEqual(conflict["status"], "resolved")
        field = canon["entities"]["character:林晚"]["fields"]["年龄"]
        self.assertEqual(field["value"], "27")
        self.assertEqual(field["conflict_ids"], [])
        self.assertEqual(open_conflicts(canon), [])

    def test_resolve_rejects_unknown_value(self):
        canon = empty_canon()
        apply(canon, [entity(fields={"年龄": "24"})])
        apply(canon, [entity(fields={"年龄": "27"}, sources=[2])])
        with self.assertRaises(ValueError):
            resolve_conflict(canon, "C-01", "99", 10001, "now")

    def test_questions_dedupe(self):
        canon = empty_canon()
        apply(canon, questions=[{"text": "蚀月的成因？", "source_ids": [1]}])
        stats = apply(canon, questions=[{"text": "蚀月的成因?", "source_ids": [2]}])
        self.assertEqual(stats["questions"], 0)
        self.assertEqual(len(canon["questions"]), 1)

    def test_relations_and_search(self):
        canon = empty_canon()
        apply(canon, [entity(fields={"身份": "医师"}, relations=[{"to": "老周", "kind": "师徒"}])])
        self.assertEqual(canon["entities"]["character:林晚"]["relations"][0]["to"], "老周")
        self.assertEqual(search(canon, "晚"), ["character:林晚"])
        self.assertEqual(search(canon, "医师"), ["character:林晚"])
        self.assertEqual(search(canon, "不存在"), [])

    def test_render_full_contains_sections(self):
        canon = empty_canon()
        apply(canon, [entity(fields={"身份": "医师"})])
        text = render_full(canon, 123)
        self.assertIn("## 人物", text)
        self.assertIn("林晚", text)
        self.assertIn("医师（#1）", text)

    def test_render_digest(self):
        canon = empty_canon()
        apply(canon, [entity(fields={"身份": "医师", "年龄": "24"})])
        apply(canon, [entity(fields={"年龄": "27"}, sources=[2])])
        digest = render_digest(canon, 2000)
        self.assertIn("林晚", digest)
        self.assertIn("医师", digest)
        self.assertIn("待裁决", digest)
        self.assertEqual(render_digest(empty_canon()), "（设定库还是空的）")

    def test_remove_entity_cleans_relations_and_conflicts(self):
        canon = empty_canon()
        apply(canon, [
            entity(),
            entity(name="老周", relations=[{"to": "林晚", "kind": "师徒"}]),
        ])
        canon["conflicts"]["C-01"] = {
            "id": "C-01", "key": "character:林晚", "entity": "林晚",
            "status": "open",
        }
        removed = remove_entity(canon, "character:林晚")
        self.assertEqual(removed["name"], "林晚")
        self.assertNotIn("character:林晚", canon["entities"])
        self.assertNotIn("C-01", canon["conflicts"])
        self.assertEqual(canon["entities"]["character:老周"]["relations"], [])

    def test_patch_must_be_object(self):
        canon = empty_canon()
        with self.assertRaises(Exception):
            apply_patch(canon, [], set(), "now")


if __name__ == "__main__":
    unittest.main()
