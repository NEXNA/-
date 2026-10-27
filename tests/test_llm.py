from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path

from bot.canon import empty_canon
from bot.config import Config
from bot.llm import (
    DeepSeekClient,
    LLMError,
    build_user_prompt,
    canon_for_prompt,
    parse_json_object,
)


class ParseTest(unittest.TestCase):
    def test_plain_json(self):
        self.assertEqual(parse_json_object('{"a": 1}'), {"a": 1})

    def test_fenced_json(self):
        self.assertEqual(parse_json_object('```json\n{"a": 1}\n```'), {"a": 1})

    def test_bad_json(self):
        with self.assertRaises(LLMError):
            parse_json_object("not json")

    def test_empty(self):
        with self.assertRaises(LLMError):
            parse_json_object("")

    def test_object_required(self):
        with self.assertRaises(LLMError):
            parse_json_object("[1,2]")


class PromptTest(unittest.TestCase):
    def test_compact_canon_drops_sources(self):
        canon = empty_canon()
        canon["entities"]["character:林晚"] = {
            "type": "character", "name": "林晚", "aliases": [],
            "fields": {"身份": {"value": "医师", "sources": [1], "conflict_ids": []}},
            "relations": [], "sources": [1],
        }
        compact = canon_for_prompt(canon)
        self.assertEqual(
            compact["entities"]["character:林晚"]["fields"], {"身份": "医师"}
        )

    def test_prompt_contains_material_ids(self):
        canon = empty_canon()
        batch = [{"id": 12, "nick": "兰", "text": "林晚是医师"}]
        context = [{"nick": "小陈", "text": "她多少岁"}]
        prompt = build_user_prompt(canon, batch, context)
        self.assertIn("[12] 兰", prompt)
        self.assertIn("小陈", prompt)
        self.assertIn("不是素材", prompt)

    def test_prompt_rejects_huge_canon(self):
        canon = empty_canon()
        for i in range(50):
            canon["entities"][f"character:角色{i}"] = {
                "type": "character", "name": f"角色{i}", "aliases": [],
                "fields": {"介绍": {"value": "很长" * 200, "sources": [1]}},
                "relations": [], "sources": [1],
            }
        with self.assertRaises(LLMError):
            build_user_prompt(canon, [], [], max_canon_chars=500)


class ClientTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).parent / ".tmp" / f"llm-{uuid.uuid4().hex[:8]}"
        (self.root / "prompts").mkdir(parents=True)
        (self.root / "prompts" / "extract_system.md").write_text(
            "输出 json。", encoding="utf-8"
        )
        self.cfg = Config(
            root=self.root,
            data_dir=self.root / "data",
            allow_groups={123},
            deepseek_key="sk-test",
            deepseek_model="deepseek-flash",
        )
        self.client = DeepSeekClient(self.cfg)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_extract_parses_patch_and_usage(self):
        captured = {}

        def fake_post(payload):
            captured.update(payload)
            return {
                "choices": [{
                    "message": {"content": '{"entities": [], "open_questions": []}'},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 120, "completion_tokens": 30},
            }

        self.client._post = fake_post  # type: ignore[method-assign]
        patch, usage = self.client.extract(empty_canon(), [{"id": 1, "nick": "a", "text": "b"}], [])
        self.assertEqual(patch["entities"], [])
        self.assertEqual(usage, {"input": 120, "output": 30})
        self.assertEqual(captured["thinking"], {"type": "disabled"})
        self.assertEqual(captured["response_format"], {"type": "json_object"})

    def test_truncated_output_raises(self):
        def fake_post(payload):
            return {
                "choices": [{
                    "message": {"content": '{"entities": []}'},
                    "finish_reason": "length",
                }],
            }

        self.client._post = fake_post  # type: ignore[method-assign]
        with self.assertRaises(LLMError):
            self.client.extract(empty_canon(), [{"id": 1, "nick": "a", "text": "b"}], [])

    def test_chat_parses_content(self):
        def fake_post(payload):
            self.assertEqual(payload["thinking"], {"type": "disabled"})
            return {
                "choices": [{
                    "message": {"content": "摩卡~ 在听哦~"},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 30, "completion_tokens": 8},
            }

        self.client._post = fake_post  # type: ignore[method-assign]
        text, usage = self.client.chat([{"role": "user", "content": "在吗"}])
        self.assertEqual(text, "摩卡~ 在听哦~")
        self.assertEqual(usage, {"input": 30, "output": 8})

    def test_chat_thinking_payload(self):
        captured = {}

        def fake_post(payload):
            captured.update(payload)
            return {
                "choices": [{
                    "message": {"content": "想好了~"},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 30, "completion_tokens": 8},
            }

        self.client._post = fake_post  # type: ignore[method-assign]
        text, _usage = self.client.chat(
            [{"role": "user", "content": "在吗"}], thinking=True,
        )
        self.assertEqual(text, "想好了~")
        self.assertEqual(captured["thinking"], {"type": "enabled"})
        self.assertEqual(captured["reasoning_effort"], "high")
        self.assertNotIn("temperature", captured)

    def test_search_web_returns_clean_results(self):
        captured = {}

        def fake_post_url(url, payload, timeout=None):
            captured["url"] = url
            captured["payload"] = payload
            return {"results": [{
                "title": "标题", "url": "https://example.com",
                "summary": "摘要", "snippet": "片段", "date": "2026-10-20",
            }]}

        self.client._post_url = fake_post_url  # type: ignore[method-assign]
        results = self.client.search_web("测试", 3)
        self.assertEqual(results[0]["title"], "标题")
        self.assertTrue(captured["url"].endswith("/v1/tools/search"))
        self.assertEqual(captured["payload"]["query"], "测试")

    def test_missing_prompt_raises(self):
        (self.root / "prompts" / "extract_system.md").unlink()

        def fake_post(payload):  # pragma: no cover
            raise AssertionError("不应该走到请求")

        self.client._post = fake_post  # type: ignore[method-assign]
        with self.assertRaises(LLMError):
            self.client.extract(empty_canon(), [{"id": 1, "nick": "a", "text": "b"}], [])


if __name__ == "__main__":
    unittest.main()
