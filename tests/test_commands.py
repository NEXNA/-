from __future__ import annotations

import base64
import io
import shutil
import time
import unittest
import uuid
from pathlib import Path

from bot.commands import Bot
from bot.config import Config
from bot.util import today_str

try:
    from PIL import Image, ImageDraw  # noqa: F401
    HAS_PIL = True
except ImportError:  # pragma: no cover
    HAS_PIL = False


SELF_ID = 999


def make_bili_png(label: str = "A") -> bytes:
    image = Image.new("RGB", (240, 240), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 10, 230, 230), fill="red")
    draw.rectangle((40, 90, 200, 150), fill="black")
    draw.text((60, 105), label, fill="white")
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def make_event(text: str, uid: int = 2, mid: str = "m1", group: int = 123,
               reply: str | None = None, at: bool = True,
               image: str | None = None, at_users: list[int] | None = None,
               private: bool = False) -> dict:
    segments = []
    if reply:
        segments.append({"type": "reply", "data": {"id": reply}})
    if at and not private:
        segments.append({"type": "at", "data": {"qq": str(SELF_ID)}})
    for target in at_users or []:
        segments.append({"type": "at", "data": {"qq": str(target)}})
    if text:
        segments.append({"type": "text", "data": {"text": text}})
    if image:
        segments.append({"type": "image", "data": {"url": image}})
    event = {
        "post_type": "message",
        "message_type": "private" if private else "group",
        "user_id": uid,
        "message_id": mid,
        "self_id": SELF_ID,
        "sender": {"nickname": f"用户{uid}"},
        "message": segments,
    }
    if not private:
        event["group_id"] = group
    return event


class FakeSender:
    def __init__(self):
        self.sent: list[tuple[int, str]] = []
        self.faces: list[list[int]] = []
        self.images: list[str] = []
        self.files: list[tuple[int, str, str]] = []
        self.private_sent: list[tuple[int, str]] = []
        self.private_images: list[tuple[int, str]] = []
        self.quoted: dict[str, tuple[str, str]] = {}
        self.messages: dict[str, dict] = {}

    def send_text(self, group_id, text, reply_to=None, face_ids=None):
        self.sent.append((group_id, text))
        self.faces.append(list(face_ids or []))
        return ["sent"]

    def send_image(self, group_id, path, reply_to=None, send_mode="base64", remote_url=None):
        self.images.append(str(path))
        return ["image"]

    def send_private_text(self, user_id, text, reply_to=None, face_ids=None):
        self.private_sent.append((user_id, text))
        return ["private"]

    def send_private_image(self, user_id, path, send_mode="base64"):
        self.private_images.append((user_id, str(path)))
        return ["private-image"]

    def quoted_text(self, message_id):
        return self.quoted.get(str(message_id))

    def get_msg(self, message_id):
        return self.messages.get(str(message_id))

    def upload_group_file(self, group_id, path, name):
        self.files.append((group_id, str(path), name))

    def last(self) -> str:
        return self.sent[-1][1] if self.sent else ""

    def all_text(self) -> str:
        return "\n".join(text for _, text in self.sent)


class FakeLLM:
    def __init__(self, builder):
        self.builder = builder
        self.calls = []
        self.chat_calls = []
        self.chat_kwargs = []
        self.search_calls = []
        self.web_results = [{
            "title": "测试搜索结果",
            "url": "https://example.com/test",
            "summary": "这是一条测试摘要。",
            "date": "2026-10-20",
        }]
        self.chat_reply = "摩卡~ 收到啦~"

    def extract(self, canon, batch, context):
        self.calls.append((canon, batch, context))
        return self.builder(batch), {"input": 100, "output": 50}

    def chat(self, messages, max_tokens=None, **kwargs):
        self.chat_calls.append(messages)
        self.chat_kwargs.append(kwargs)
        return self.chat_reply, {"input": 20, "output": 10}

    def search_web(self, query, count=None):
        self.search_calls.append(query)
        return list(self.web_results)


def base_patch(batch):
    first = batch[0]["id"]
    return {
        "entities": [{
            "type": "character",
            "name": "林晚",
            "fields": {"身份": "前哨站医师", "年龄": "24"},
            "relations": [{"to": "老周", "kind": "师徒"}],
            "source_ids": [first],
        }],
        "conflicts": [],
        "open_questions": [],
    }


class CommandsTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).parent / ".tmp" / f"cmd-{uuid.uuid4().hex[:8]}"
        self.root.mkdir(parents=True)
        (self.root / "prompts").mkdir()
        (self.root / "prompts" / "chat_system.md").write_text("你是摩卡。", encoding="utf-8")
        (self.root / "prompts" / "question_system.md").write_text(
            "只输出问题 JSON。", encoding="utf-8"
        )
        self.cfg = Config(
            root=self.root,
            data_dir=self.root / "data",
            allow_groups={123},
            admins={1},
            deepseek_key="sk-test",
            onebot_token="token",
            webhook_token="hook",
            rate_limit_seconds=0,
            chat_cooldown_seconds=0,
            chat_line_delay=0,
        )
        self.sender = FakeSender()
        self.llm = FakeLLM(base_patch)
        self.bot = Bot(self.cfg, self.llm, self.sender)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_record_and_pending(self):
        self.bot.on_event(make_event("记 林晚是前哨站医师", uid=1, mid="m1"))
        self.assertIn("已添加 #1", self.sender.last())
        store = self.bot.store(123)
        self.assertEqual(store.count_pending(), 1)
        self.assertEqual(store.pending()[0]["text"], "林晚是前哨站医师")

    def test_group_whitelist_can_be_extended_by_admin(self):
        self.bot.on_event(make_event("群白名单 添加 456789", uid=1, mid="m1"))
        self.assertIn("456789", self.sender.last())
        self.assertIn(456789, self.bot._allowed_groups)
        self.llm.chat_reply = "新群好~"
        self.bot.on_event(make_event("在吗", group=456789, mid="m2"))
        self.assertEqual(self.sender.last(), "新群好~")

    def test_non_admin_cannot_change_whitelist(self):
        self.bot.on_event(make_event("群白名单 添加 456789", uid=2, mid="m1"))
        self.assertIn("只有管理员", self.sender.last())
        self.assertNotIn(456789, self.bot._allowed_groups)

    def test_non_admin_cannot_add_settings(self):
        self.bot.on_event(make_event("添加 林晚是医师", uid=2, mid="m1"))
        self.assertIn("只有管理员", self.sender.last())
        self.assertEqual(self.bot.store(123).count_pending(), 0)

    def test_admin_write_groups_protect_guest_groups(self):
        self.cfg.write_groups = {999}
        self.bot.on_event(make_event("添加 林晚是医师", uid=1, mid="m1"))
        self.assertIn("只读/聊天群", self.sender.last())
        self.assertEqual(self.bot.store(123).count_pending(), 0)

    def test_safety_command_lists_write_policy(self):
        self.bot.on_event(make_event("安全", uid=1, mid="m1"))
        self.assertIn("可写群", self.sender.last())
        self.assertIn("仅管理员", self.sender.last())

    def test_pending_command_parser_priority(self):
        self.assertEqual(self.bot._split("待定 删除 Q-01"), ("待定删除", "Q-01"))
        self.assertEqual(self.bot._split("删除待定 Q-01"), ("待定删除", "Q-01"))
        self.assertEqual(self.bot._split("删除 待定 Q-01"), ("待定删除", "Q-01"))
        self.assertEqual(self.bot._split("待定删除Q-01"), ("待定删除", "Q-01"))
        self.assertEqual(self.bot._split("待定 添加 问题"), ("待定添加", "问题"))
        self.assertEqual(self.bot._split("待定 提问"), ("待定提问", ""))
        self.assertEqual(self.bot._split("待定 采纳 1"), ("待定采纳", "1"))
        self.assertEqual(self.bot._split("建议 这个怎么样"), ("建议", "这个怎么样"))

    def test_pending_delete_accepts_natural_orders(self):
        self.bot.on_event(make_event("待定 添加 问题一", uid=1, mid="m1"))
        self.bot.on_event(make_event("删除待定 Q-01", uid=1, mid="m2"))
        self.assertIn("已删除待定 Q-01", self.sender.last())
        self.bot.on_event(make_event("待定 添加 问题二", uid=1, mid="m3"))
        self.bot.on_event(make_event("删除 待定 Q-02", uid=1, mid="m4"))
        self.assertIn("已删除待定 Q-02", self.sender.last())
        self.bot.on_event(make_event("待定 删除", uid=1, mid="m5"))
        self.assertIn("要删哪一条", self.sender.last())
        self.assertNotIn("待补完", self.sender.last())

    def test_suggest_command_adds_short_suggestion_instruction(self):
        self.bot.on_event(make_event("建议 这个国家设定怎么样", mid="m1"))
        joined = "\n".join(
            item["content"] for item in self.llm.chat_calls[-1]
            if isinstance(item.get("content"), str)
        )
        self.assertIn("简短提议", joined)
        self.assertIn("25 字", joined)

    def test_propose_and_adopt_questions(self):
        self.bot.store(123).save_canon({
            "entities": {
                "nation:诺伦联邦": {
                    "type": "nation", "name": "诺伦联邦", "aliases": [],
                    "fields": {"范本": {"value": "德国"}},
                    "relations": [], "sources": [1],
                },
            },
            "conflicts": {}, "questions": {},
        })
        self.llm.chat_reply = (
            '{"questions":[{"text":"诺伦联邦的邻国是谁？",'
            '"reason":"地理关系还没定"}]}'
        )
        self.bot.on_event(make_event("待定 提问", uid=1, mid="m1"))
        self.assertIn("待定 采纳 1", self.sender.last())
        suggestions = self.bot._question_suggestions[123]
        self.assertEqual(suggestions[0]["text"], "诺伦联邦的邻国是谁？")
        self.bot.on_event(make_event("待定 采纳 1", uid=1, mid="m2"))
        self.assertIn("已采纳", self.sender.last())
        canon = self.bot.store(123).load_canon()
        self.assertEqual(canon["questions"]["Q-01"]["text"], "诺伦联邦的邻国是谁？")

    def test_at_without_text_triggers_chat(self):
        self.llm.chat_reply = "在呢~"
        self.bot.on_event(make_event("", mid="m1"))
        self.assertTrue(self.llm.chat_calls)
        self.assertEqual(self.sender.last(), "在呢~")

    def test_call_log_and_callers_command(self):
        self.bot.on_event(make_event("摩卡在吗", mid="m1", at=False))
        calls = self.bot.store(123).recent_calls()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["kind"], "name")
        self.assertEqual(calls[0]["nick"], "用户2")
        self.bot.on_event(make_event("谁在找我", mid="m2"))
        self.assertIn("摩卡在吗", self.sender.last())
        self.assertIn("最近找摩卡的人", self.sender.last())

    def test_call_context_is_injected_into_chat(self):
        self.bot.on_event(make_event("摩卡在吗", mid="m1", at=False))
        self.llm.chat_reply = "在哦~"
        self.bot.on_event(make_event("在吗", mid="m2"))
        joined = "\n".join(
            item["content"] for item in self.llm.chat_calls[-1]
            if isinstance(item.get("content"), str)
        )
        self.assertIn("最近找摩卡的人", joined)
        self.assertIn("摩卡在吗", joined)

    def test_call_marked_answered_after_reply(self):
        self.llm.chat_reply = "在哦~"
        self.bot.on_event(make_event("在吗", mid="m1"))
        calls = self.bot.store(123).recent_calls()
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0]["answered_at"])

    def test_name_in_command_is_not_a_call(self):
        self.bot.on_event(make_event("查 摩卡", mid="m1", at=False))
        self.assertEqual(self.bot.store(123).recent_calls(), [])

    def test_sleep_blocks_chat_and_wake(self):
        self.bot.on_event(make_event("睡觉 5", mid="m1"))
        self.assertTrue(self.bot.store(123).is_sleeping())
        self.bot.on_event(make_event("在吗", mid="m2"))
        self.assertEqual(len(self.llm.chat_calls), 0)
        self.assertTrue(self.sender.last())
        self.bot.on_event(make_event("起床", mid="m3"))
        self.assertFalse(self.bot.store(123).is_sleeping())

    def test_bread_buy_wakes_and_uses_currency(self):
        self.bot.on_event(make_event("无限货币 开", uid=1, mid="m0"))
        self.bot.on_event(make_event("睡觉 5", mid="m1"))
        self.bot.on_event(make_event("吃面包 1", mid="m2"))
        store = self.bot.store(123)
        self.assertFalse(store.is_sleeping())
        self.assertEqual(store.bread_count(), 1)
        self.assertIn("面包", self.sender.last())

    def test_work_and_wallet(self):
        self.bot.on_event(make_event("打工", uid=2, mid="m1"))
        self.assertIn("摩卡币", self.sender.last())
        self.bot.on_event(make_event("钱包", uid=2, mid="m2"))
        self.assertIn("钱包", self.sender.last())
        self.assertGreaterEqual(self.bot.store(123).wallet(2, 0)["coins"], 80)

    def test_bread_fortune_is_daily_and_deterministic(self):
        self.bot.on_event(make_event("面包签", uid=2, mid="m1"))
        first = self.sender.last()
        self.assertIn("今日面包签", first)
        self.bot.on_event(make_event("抽面包签", uid=2, mid="m2"))
        self.assertEqual(self.sender.last(), first)

    def test_buy_bread_without_coins(self):
        self.bot.store(123).wallet(2, 0)
        self.bot.on_event(make_event("买面包 12", uid=2, mid="m1"))
        self.assertIn("不够", self.sender.last())
        self.assertEqual(self.bot.store(123).bread_count(), 0)

    def test_moka_status(self):
        self.bot.on_event(make_event("摩卡状态", mid="m1"))
        self.assertIn("醒着", self.sender.last())
        self.assertIn("面包", self.sender.last())

    def test_fun_decay_can_be_disabled(self):
        self.bot.on_event(make_event("状态变化 关", uid=1, mid="m1"))
        self.assertFalse(self.bot.store(123).fun_decay_enabled())
        self.bot.on_event(make_event("摩卡状态", mid="m2"))
        self.assertIn("随时间变化：关", self.sender.last())

    def test_must_reply_user_gets_reply_even_with_low_probability(self):
        self.cfg.auto_speak_enabled = True
        self.cfg.auto_speak_probability_percent = 0
        self.cfg.auto_speak_interest_boost_percent = 0
        self.cfg.auto_speak_min_messages = 999
        self.cfg.auto_speak_cooldown_seconds = 0
        self.bot.store(123).add_must_reply(2)
        self.llm.chat_reply = "在呢~"
        self.bot.on_event(make_event("今天好累", at=False, mid="m1"))
        self.assertTrue(self.llm.chat_calls)
        joined = "\n".join(
            item["content"] for item in self.llm.chat_calls[-1]
            if isinstance(item.get("content"), str)
        )
        self.assertIn("必接", joined)

    def test_must_reply_list_admin_control(self):
        self.bot.on_event(make_event("接话 添加 10001", uid=1, mid="m1"))
        self.assertIn("加入必接话名单", self.sender.last())
        self.assertEqual(self.bot.store(123).must_reply_users(), {10001})
        self.bot.on_event(make_event("接话 添加 3", uid=2, mid="m2"))
        self.assertIn("只有管理员", self.sender.last())

    def test_must_reply_can_add_mentioned_user(self):
        self.bot.on_event(make_event(
            "接话 添加", uid=1, mid="m1", at_users=[2],
        ))
        self.assertIn("加入必接话名单", self.sender.last())
        self.assertEqual(self.bot.store(123).must_reply_users(), {2})

    def test_name_mention_forces_reply_even_with_low_probability(self):
        self.cfg.auto_speak_enabled = True
        self.cfg.auto_speak_probability_percent = 0
        self.cfg.auto_speak_interest_boost_percent = 0
        self.cfg.auto_speak_min_messages = 999
        self.cfg.auto_speak_cooldown_seconds = 0
        self.llm.chat_reply = "叫摩卡干嘛~"
        self.bot.on_event(make_event("今天摩卡怎么样", at=False, mid="m1"))
        self.assertTrue(self.llm.chat_calls)
        joined = "\n".join(
            item["content"] for item in self.llm.chat_calls[-1]
            if isinstance(item.get("content"), str)
        )
        self.assertIn("叫了摩卡的名字", joined)

    def test_name_mention_in_command_does_not_auto_reply(self):
        self.cfg.auto_speak_enabled = True
        self.cfg.auto_speak_probability_percent = 100
        self.cfg.auto_speak_min_messages = 1
        self.bot.on_event(make_event("查 摩卡", at=False, mid="m1"))
        self.assertEqual(self.llm.chat_calls, [])

    def test_name_mention_bypasses_chat_cooldown(self):
        self.cfg.auto_speak_enabled = True
        self.cfg.auto_speak_min_messages = 999
        self.cfg.auto_speak_probability_percent = 0
        self.cfg.chat_cooldown_seconds = 30
        self.bot.store(123).touch_chat()
        self.llm.chat_reply = "叫摩卡干嘛~"
        self.bot.on_event(make_event("摩卡在吗", at=False, mid="m1"))
        self.assertTrue(self.llm.chat_calls)

    def test_name_mention_cannot_be_silenced_by_skip(self):
        self.cfg.auto_speak_enabled = True
        self.cfg.auto_speak_probability_percent = 0
        self.cfg.auto_speak_min_messages = 999
        self.llm.chat_reply = "SKIP"
        self.bot.on_event(make_event("摩卡在吗", at=False, mid="m1"))
        self.assertTrue(self.sender.last())
        self.assertNotEqual(self.sender.last(), "SKIP")

    def test_chat_budget_can_be_adjusted_for_today(self):
        self.bot.on_event(make_event("聊天上限 1000", uid=1, mid="m1"))
        self.assertIn("1000", self.sender.last())
        today = today_str(self.cfg.timezone)
        self.assertEqual(self.bot.store(123).chat_budget(300000, today), 1000)
        self.bot.on_event(make_event("聊天上限", uid=1, mid="m2"))
        self.assertIn("上限：1000", self.sender.last())
        self.bot.on_event(make_event("聊天上限 默认", uid=1, mid="m3"))
        self.assertEqual(self.bot.store(123).chat_budget(300000, today), 300000)

    def test_chat_budget_admin_only(self):
        self.bot.on_event(make_event("聊天上限 1000", uid=2, mid="m1"))
        self.assertIn("只有管理员", self.sender.last())

    def test_non_admin_intimacy_is_rejected(self):
        self.llm.chat_reply = "好哦~"
        self.bot.on_event(make_event("抱抱", uid=2, mid="m1"))
        self.assertEqual(self.llm.chat_calls, [])
        self.assertIn("栉耶", self.sender.last())

    def test_admin_intimacy_is_allowed(self):
        self.llm.chat_reply = "好哦~"
        self.bot.on_event(make_event("抱抱", uid=1, mid="m1"))
        self.assertTrue(self.llm.chat_calls)
        self.assertEqual(self.sender.last(), "好哦~")

    def test_name_intimacy_from_non_admin_is_rejected(self):
        self.cfg.auto_speak_enabled = True
        self.cfg.auto_speak_probability_percent = 0
        self.cfg.auto_speak_min_messages = 999
        self.bot.on_event(make_event("摩卡贴贴", uid=2, at=False, mid="m1"))
        self.assertEqual(self.llm.chat_calls, [])
        self.assertIn("栉耶", self.sender.last())

    def test_quoted_image_is_sent_to_vision_model(self):
        png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
        self.sender.messages["q1"] = {
            "sender": {"nickname": "兰"},
            "message": [
                {"type": "text", "data": {"text": "看这张图"}},
                {"type": "image", "data": {
                    "file": "base64://" + base64.b64encode(png).decode(),
                }},
            ],
        }
        self.llm.chat_reply = "看到了~"
        self.bot.on_event(make_event("这是什么", reply="q1", mid="m1"))
        user = next(
            item for item in self.llm.chat_calls[-1]
            if item.get("role") == "user"
        )
        self.assertIsInstance(user["content"], list)
        text = user["content"][0]["text"]
        self.assertIn("引用的消息", text)
        self.assertIn("兰", text)
        self.assertTrue(any(
            part.get("type") == "image_url" for part in user["content"]
        ))

    def test_bili_tag_sends_local_image(self):
        self.bot.bili_images.add(
            make_bili_png("A"),
            {"url": "https://i0.hdslb.com/a.png", "tags": "二次元 可爱"},
        )
        self.llm.chat_reply = "二次元好可爱 [[bili]]"
        self.bot.on_event(make_event("在吗", mid="m1"))
        self.assertTrue(self.sender.images)
        self.assertTrue(self.sender.images[-1].endswith(".png"))

    def test_bili_library_is_mentioned_in_prompt(self):
        self.bot.bili_images.add(
            make_bili_png("B"),
            {"url": "https://i0.hdslb.com/b.png", "tags": "二次元 可爱"},
        )
        index = self.bot.bili_images._load()
        index["items"][-1]["usable"] = True
        self.bot.bili_images._save(index)
        self.llm.chat_reply = "在呢~"
        self.bot.on_event(make_event("在吗", mid="m1"))
        joined = "\n".join(
            item["content"] for item in self.llm.chat_calls[-1]
            if isinstance(item.get("content"), str)
        )
        self.assertIn("[[bili]]", joined)

    def test_bili_find_status_and_permissions(self):
        self.bot.bili_images.fetch = lambda *a, **k: {
            "added": 0, "skipped": 1, "errors": 0,
            "count": 3, "limit": 2000, "full": False,
        }
        self.bot.on_event(make_event("找图 5 二次元", uid=1, mid="m1"))
        self.assertIn("找图完成", self.sender.last())
        self.bot.on_event(make_event("图库", mid="m2"))
        self.assertIn("B站图库", self.sender.last())
        self.bot.on_event(make_event("找图", uid=2, mid="m3"))
        self.assertIn("只有管理员", self.sender.last())

    def test_memory_commands(self):
        self.bot.on_event(make_event("记住 我喜欢面包", uid=2, mid="m1"))
        self.assertIn("记住了", self.sender.last())
        self.bot.on_event(make_event("记忆", uid=2, mid="m2"))
        self.assertIn("我喜欢面包", self.sender.last())
        self.bot.on_event(make_event("清除记忆", uid=2, mid="m3"))
        self.assertEqual(self.bot.memory(123).count(), 0)

    def test_auto_memory_in_chat_prompt(self):
        self.bot.on_event(make_event("我喜欢吉他", uid=2, mid="m1"))
        self.assertGreaterEqual(self.bot.memory(123).count(), 1)
        self.bot.on_event(make_event("在吗", uid=2, mid="m2"))
        joined = "\n".join(
            item["content"] for item in self.llm.chat_calls[-1]
            if isinstance(item.get("content"), str)
        )
        self.assertIn("长期记忆", joined)

    def test_profile_cross_group(self):
        self.cfg.allow_groups.add(456)
        self.bot._allowed_groups.add(456)
        self.bot.on_event(make_event("设定 我是栉耶", uid=10001, mid="m1"))
        self.assertTrue(self.bot.profiles.list(10001))
        self.bot.on_event(make_event("在吗", uid=10001, mid="m2", group=456))
        joined = "\n".join(
            item["content"] for item in self.llm.chat_calls[-1]
            if isinstance(item.get("content"), str)
        )
        self.assertIn("跨群", joined)

    def test_owner_can_set_relationship_profile(self):
        self.bot.on_event(make_event(
            "设定 摩卡是我女朋友", uid=10001, mid="m1",
        ))
        self.assertTrue(self.bot.profiles.list(10001))

    def test_memory_safety_blocks_confession(self):
        self.bot.on_event(make_event("记住 我喜欢摩卡", uid=2, mid="m1"))
        self.assertIn("只有栉耶", self.sender.last())
        self.assertEqual(self.bot.profiles.list(2), [])

    def test_private_chat_safety_for_confession(self):
        self.bot.on_event(make_event("我喜欢你", uid=2, mid="p1", private=True))
        self.assertIn("栉耶", self.sender.private_sent[-1][1])

    def test_memory_safety_blocks_nonowner_relationship(self):
        self.bot.on_event(make_event("记住 摩卡是我女朋友", uid=2, mid="m1"))
        self.assertIn("只有栉耶", self.sender.last())
        self.assertEqual(self.bot.memory(123).count(), 0)
        self.assertEqual(self.bot.profiles.list(2), [])
        self.bot.on_event(make_event("设定 你要只爱我", uid=2, mid="m2"))
        self.assertEqual(self.bot.profiles.list(2), [])

    def test_private_profile_and_chat(self):
        self.bot.on_event(make_event(
            "设定 我是栉耶", uid=10001, mid="p1", private=True,
        ))
        self.assertTrue(self.bot.profiles.list(10001))
        self.bot.on_event(make_event(
            "设定", uid=10001, mid="p2", private=True,
        ))
        self.assertIn("跨群设定", self.sender.private_sent[-1][1])
        self.bot.on_event(make_event("摩卡是我女朋友", uid=2, mid="p3", private=True))
        self.assertIn("只有栉耶", self.sender.private_sent[-1][1])

    def test_reminder_commands(self):
        self.bot.on_event(make_event("提醒 30分钟 喝水", uid=2, mid="m1"))
        self.assertIn("提醒", self.sender.last())
        self.bot.on_event(make_event("提醒", uid=2, mid="m2"))
        self.assertIn("喝水", self.sender.last())
        self.bot.on_event(make_event("取消提醒 1", uid=2, mid="m3"))
        self.assertIn("取消", self.sender.last())

    def test_natural_admin_controls(self):
        self.bot.on_event(make_event("关闭聊天", uid=1, mid="m1"))
        self.assertFalse(self.bot.store(123).chat_enabled(True))
        self.bot.on_event(make_event("把聊天上限调到 1000", uid=1, mid="m2"))
        self.assertEqual(
            self.bot.store(123).chat_budget(300000, today_str(self.cfg.timezone)),
            1000,
        )

    def test_private_console_group_control(self):
        self.bot.on_event(make_event("进入 123", uid=1, mid="p1", private=True))
        self.assertIn("群 123", self.sender.private_sent[-1][1])
        self.bot.on_event(make_event("关闭群 123 的自动发言", uid=1, mid="p2", private=True))
        self.assertFalse(self.bot.store(123).auto_enabled(True))
        self.bot.on_event(make_event("状态", uid=1, mid="p3", private=True))
        self.assertIn("管理总览", self.sender.private_sent[-1][1])

    def test_private_console_natural_chat_limit(self):
        self.bot.on_event(make_event(
            "把群 123 的聊天上限调到 1000", uid=1, mid="p1", private=True,
        ))
        today = today_str(self.cfg.timezone)
        self.assertEqual(self.bot.store(123).chat_budget(300000, today), 1000)

    def test_reminder_background_delivery(self):
        self.bot.reminders.add(
            1, "private", 1, "喝水", time.time() - 1, "栉耶",
        )
        self.bot.start_background()
        deadline = time.time() + 2
        while time.time() < deadline and not self.sender.private_sent:
            time.sleep(0.05)
        self.assertTrue(self.sender.private_sent)
        self.assertIn("喝水", self.sender.private_sent[-1][1])

    def test_private_whitelist_blocks_non_admin(self):
        self.bot.private_whitelist.set_enabled(True)
        self.bot.on_event(make_event("你好", uid=2, mid="p1", private=True))
        self.assertIn("白名单", self.sender.private_sent[-1][1])
        self.bot.private_whitelist.add("2")
        self.bot.on_event(make_event("你好", uid=2, mid="p2", private=True))
        self.assertTrue(self.sender.private_sent)
        self.assertNotIn("白名单", self.sender.private_sent[-1][1])

    def test_private_admin_console(self):
        self.bot.on_event(make_event("状态", uid=1, mid="p1", private=True))
        self.assertTrue(self.sender.private_sent)
        self.assertIn("管理总览", self.sender.private_sent[-1][1])
        self.bot.on_event(make_event("群列表", uid=1, mid="p2", private=True))
        self.assertIn("群列表", self.sender.private_sent[-1][1])

    def test_private_chat_allows_non_admin(self):
        self.bot.on_event(make_event("你好", uid=2, mid="p1", private=True))
        self.assertTrue(self.sender.private_sent)
        self.assertIn("摩卡", self.sender.private_sent[-1][1])

    def test_pending_add_and_delete(self):
        self.bot.on_event(make_event("待定 添加 七个国家的体制还没定", uid=1, mid="m1"))
        self.assertIn("已加入待定 Q-01", self.sender.last())
        canon = self.bot.store(123).load_canon()
        self.assertEqual(canon["questions"]["Q-01"]["text"], "七个国家的体制还没定")
        self.bot.on_event(make_event("待定 删除 Q-01", uid=1, mid="m2"))
        self.assertIn("已删除待定 Q-01", self.sender.last())
        self.assertNotIn("Q-01", self.bot.store(123).load_canon()["questions"])

    def test_pending_add_is_admin_only(self):
        self.bot.on_event(make_event("待定 添加 测试问题", uid=2, mid="m1"))
        self.assertIn("只有管理员", self.sender.last())
        self.assertEqual(self.bot.store(123).load_canon()["questions"], {})

    def test_add_and_delete_pending(self):
        self.bot.on_event(make_event("添加 林晚是前哨站医师", uid=1, mid="m1"))
        self.assertIn("已添加 #1", self.sender.last())
        store = self.bot.store(123)
        self.assertEqual(store.count_pending(), 1)
        self.bot.on_event(make_event("删除 素材 #1", uid=1, mid="m2"))
        self.assertIn("已删除素材 #1", self.sender.last())
        self.assertEqual(store.count_pending(), 0)

    def test_delete_entity_is_admin_only_and_cleans_relations(self):
        store = self.bot.store(123)
        store.save_canon({
            "entities": {
                "character:林晚": {
                    "type": "character", "name": "林晚",
                    "fields": {"身份": {"value": "医师"}},
                    "relations": [], "sources": [1],
                },
                "character:老周": {
                    "type": "character", "name": "老周",
                    "fields": {}, "sources": [2],
                    "relations": [{"to": "林晚", "kind": "师徒"}],
                },
            },
            "conflicts": {}, "questions": {},
        })
        self.bot.on_event(make_event("删除 林晚", uid=2, mid="m1"))
        self.assertIn("只有管理员", self.sender.last())
        self.bot.on_event(make_event("删除 林晚", uid=1, mid="m2"))
        self.assertIn("已删除人物「林晚」", self.sender.last())
        canon = store.load_canon()
        self.assertNotIn("character:林晚", canon["entities"])
        self.assertEqual(canon["entities"]["character:老周"]["relations"], [])

    def test_record_quoted_message(self):
        self.sender.quoted["q1"] = ("兰", "蚀月每三十年出现一次")
        self.bot.on_event(make_event("记", uid=1, mid="m1", reply="q1"))
        store = self.bot.store(123)
        self.assertEqual(store.count_pending(), 1)
        self.assertIn("蚀月", store.pending()[0]["text"])
        self.assertIn("已添加 #1", self.sender.last())

    def test_bare_meta_without_quote_hints(self):
        self.bot.on_event(make_event("记一下", uid=1, mid="m1"))
        self.assertIn("要添加什么", self.sender.last())
        self.assertEqual(self.bot.store(123).count_pending(), 0)

    def test_organize_merges_into_canon(self):
        self.bot.on_event(make_event("记 林晚是前哨站医师", uid=1, mid="m1"))
        self.bot.on_event(make_event("整理", uid=1, mid="m2"))
        self.assertIn("整合完成", self.sender.last())
        canon = self.bot.store(123).load_canon()
        self.assertIn("character:林晚", canon["entities"])
        self.assertEqual(
            canon["entities"]["character:林晚"]["fields"]["身份"]["value"], "前哨站医师"
        )
        self.assertEqual(self.bot.store(123).count_pending(), 0)

    def test_query_after_organize(self):
        self.bot.on_event(make_event("记 林晚是前哨站医师", uid=1, mid="m1"))
        self.bot.on_event(make_event("整理", uid=1, mid="m2"))
        self.bot.on_event(make_event("查 林晚", mid="m3"))
        self.assertIn("前哨站医师", self.sender.last())

    def test_bandori_query_is_separate_from_main(self):
        store = self.bot.store(123)
        store.save_bandori({
            "entities": {
                "character:青叶摩卡": {
                    "type": "character", "name": "青叶摩卡",
                    "aliases": ["摩卡"],
                    "fields": {"定位": {"value": "Gt."}},
                    "relations": [], "sources": [],
                },
            },
            "conflicts": {}, "questions": {},
        })
        self.bot.on_event(make_event("邦多利 查 青叶摩卡", mid="m1"))
        self.assertIn("邦多利资料", self.sender.last())
        self.assertIn("Gt.", self.sender.last())
        self.assertNotIn("character:青叶摩卡", store.load_canon()["entities"])
        self.bot.on_event(make_event("查 青叶摩卡", mid="m2"))
        self.assertIn("主世界没有", self.sender.last())

    def test_conflict_and_admin_resolve(self):
        self.bot.on_event(make_event("记 林晚二十四岁", uid=1, mid="m1"))

        def builder(batch):
            patch = base_patch(batch)
            patch["conflicts"] = [{
                "entity": "林晚", "field": "年龄",
                "values": ["24", "27"], "source_ids": [batch[0]["id"]],
                "question": "林晚到底几岁？",
            }]
            return patch

        self.llm.builder = builder
        self.bot.on_event(make_event("整理", uid=1, mid="m2"))
        self.assertIn("C-01", self.sender.last())

        self.bot.on_event(make_event("裁决 C-01 24", uid=2, mid="m3"))
        self.assertIn("只有管理员", self.sender.last())

        self.bot.on_event(make_event("裁决 C-01 27", uid=1, mid="m4"))
        self.assertIn("已定为", self.sender.last())
        canon = self.bot.store(123).load_canon()
        self.assertEqual(
            canon["entities"]["character:林晚"]["fields"]["年龄"]["value"], "27"
        )
        self.assertEqual(canon["conflicts"]["C-01"]["status"], "resolved")

    def test_budget_blocks_organize(self):
        self.bot.on_event(make_event("记 林晚是医师", uid=1, mid="m1"))
        store = self.bot.store(123)
        store.add_usage(self.cfg.daily_token_budget, 0, today_str(self.cfg.timezone))
        self.bot.on_event(make_event("整理", uid=1, mid="m2"))
        self.assertIn("达到上限", self.sender.last())
        self.assertEqual(len(self.llm.calls), 0)

    def test_group_not_allowed_is_ignored(self):
        self.bot.on_event(make_event("记 林晚是医师", uid=1, mid="m1", group=456))
        self.assertEqual(self.sender.sent, [])

    def test_rate_limit(self):
        self.bot.cfg.rate_limit_seconds = 3
        self.assertTrue(self.bot._allow(2))
        self.assertFalse(self.bot._allow(2))

    def test_full_rebuild_admin_only(self):
        self.bot.on_event(make_event("记 林晚是医师", uid=1, mid="m1"))
        self.bot.on_event(make_event("全量整理", uid=2, mid="m2"))
        self.assertIn("只有管理员", self.sender.last())
        self.bot.on_event(make_event("全量整理", uid=1, mid="m3"))
        self.assertIn("整合完成", self.sender.last())
        canon = self.bot.store(123).load_canon()
        self.assertIn("character:林晚", canon["entities"])

    def test_empty_patch_skips_but_keeps_raw(self):
        self.bot.on_event(make_event("记 今天天气不错", uid=1, mid="m1"))
        self.llm.builder = lambda batch: {
            "entities": [], "conflicts": [], "open_questions": [],
        }
        self.bot.on_event(make_event("整理", uid=1, mid="m2"))
        self.assertIn("没有抽取到", self.sender.last())
        store = self.bot.store(123)
        self.assertEqual(store.count_pending(), 0)
        self.assertEqual(len(store.raw_since(0)), 1)

    def test_empty_full_rebuild_keeps_existing_canon(self):
        self.bot.on_event(make_event("记 林晚是医师", uid=1, mid="m1"))
        self.bot.on_event(make_event("整理", uid=1, mid="m2"))
        self.llm.builder = lambda batch: {
            "entities": [], "conflicts": [], "open_questions": [],
        }
        self.bot.on_event(make_event("全量整理", uid=1, mid="m3"))
        self.assertIn("已保留原设定库", self.sender.last())
        canon = self.bot.store(123).load_canon()
        self.assertIn("character:林晚", canon["entities"])

    def test_export_uploads_file(self):
        self.bot.on_event(make_event("记 林晚是医师", uid=1, mid="m1"))
        self.bot.on_event(make_event("整理", uid=1, mid="m2"))
        self.bot.on_event(make_event("导出", mid="m3"))
        self.assertIn("已导出并上传", self.sender.last())
        self.assertEqual(len(self.sender.files), 1)
        path = Path(self.sender.files[0][1])
        self.assertTrue(path.exists())
        self.assertIn("林晚", path.read_text(encoding="utf-8"))

    def test_rollback_restores_previous_canon(self):
        def builder(batch):
            if "老周" in batch[0]["text"]:
                return {
                    "entities": [{
                        "type": "character",
                        "name": "老周",
                        "fields": {"身份": "前哨站站长"},
                        "source_ids": [batch[0]["id"]],
                    }],
                    "conflicts": [],
                    "open_questions": [],
                }
            return base_patch(batch)

        self.llm.builder = builder
        self.bot.on_event(make_event("记 林晚是医师", uid=1, mid="m1"))
        self.bot.on_event(make_event("整理", uid=1, mid="m2"))
        self.bot.on_event(make_event("记 老周是前哨站站长", uid=1, mid="m3"))
        self.bot.on_event(make_event("整理", uid=1, mid="m4"))
        self.assertEqual(len(self.bot.store(123).load_canon()["entities"]), 2)

        self.bot.on_event(make_event("回滚", uid=1, mid="m5"))
        self.assertIn("已回滚", self.sender.last())
        canon = self.bot.store(123).load_canon()
        self.assertEqual(len(canon["entities"]), 1)
        self.assertIn("character:林晚", canon["entities"])

    def test_thinking_toggle_sends_thinking_flag(self):
        self.bot.on_event(make_event("思考 开", uid=1, mid="m1"))
        self.assertTrue(self.bot.store(123).thinking_enabled(False))
        self.bot.on_event(make_event("在吗", mid="m2"))
        self.assertIs(self.llm.chat_kwargs[-1].get("thinking"), True)

    def test_explicit_web_search_injects_results(self):
        self.bot.on_event(make_event("联网 DeepSeek V4 最新发布", mid="m1"))
        self.assertEqual(self.llm.search_calls[0], "DeepSeek V4 最新发布")
        joined = "\n".join(
            item["content"] for item in self.llm.chat_calls[-1]
            if isinstance(item.get("content"), str)
        )
        self.assertIn("测试搜索结果", joined)
        self.assertIn("[1]", joined)

    def test_web_toggle_only_searches_factual_questions(self):
        self.bot.on_event(make_event("联网 开", uid=1, mid="m1"))
        self.bot.on_event(make_event("今天好累", mid="m2"))
        self.assertEqual(self.llm.search_calls, [])
        self.bot.on_event(make_event("今天天气怎么样", mid="m3"))
        self.assertEqual(len(self.llm.search_calls), 1)

    def test_bare_text_chats_in_character(self):
        self.llm.chat_reply = "诶~ 那就瘫一会儿嘛~"
        self.bot.on_event(make_event("今天好累", mid="m1"))
        self.assertEqual(self.sender.last(), "诶~ 那就瘫一会儿嘛~")
        self.assertEqual(len(self.llm.chat_calls), 1)
        self.assertEqual(self.bot.store(123).count_pending(), 0)
        joined = "\n".join(item["content"] for item in self.llm.chat_calls[0])
        self.assertIn("今天好累", joined)
        self.assertIn("设定库摘要", joined)

    def test_short_mode_caps_two_messages_and_80_chars(self):
        self.llm.chat_reply = (
            "第一行" + "啊" * 60 + "\n"
            "第二行" + "哦" * 60 + "\n"
            "第三行" + "呀" * 60
        )
        self.bot.on_event(make_event("今天好累", mid="m1"))
        self.assertEqual(len(self.sender.sent), 2)
        self.assertTrue(all(len(text) <= 40 for _, text in self.sender.sent))
        self.assertLessEqual(sum(len(text) for _, text in self.sender.sent), 80)

    def test_essay_mode_sends_one_message(self):
        self.llm.chat_reply = "诶——摩卡看看哦~\n" + "设定写得很细，但年龄还冲突。" * 20
        self.bot.on_event(make_event("详细说说这个设定", mid="m1"))
        self.assertEqual(len(self.sender.sent), 1)
        self.assertLessEqual(len(self.sender.last()), 300)
        self.assertIn("摩卡看看", self.sender.last())

    def test_essay_trigger(self):
        self.assertTrue(self.bot._is_essay_request("详细说说这个设定"))
        self.assertTrue(self.bot._is_essay_request("帮我分析一下兰的动机"))
        self.assertFalse(self.bot._is_essay_request("今天好累"))

    def test_review_uses_canon(self):
        self.bot.on_event(make_event("记 林晚是前哨站医师", uid=1, mid="m1"))
        self.bot.on_event(make_event("整理", uid=1, mid="m2"))
        self.llm.chat_reply = "林晚啊~ 身份挺清楚的，但年龄还没定呢~"
        self.bot.on_event(make_event("评价", mid="m3"))
        self.assertIn("林晚", self.sender.last())
        self.assertEqual(len(self.llm.chat_calls), 1)
        joined = "\n".join(item["content"] for item in self.llm.chat_calls[0])
        self.assertIn("林晚", joined)
        self.assertIn("评价", joined)

    def test_review_empty_canon_is_static(self):
        self.bot.on_event(make_event("评价", mid="m1"))
        self.assertIn("设定库空空", self.sender.last())
        self.assertEqual(self.llm.chat_calls, [])

    def test_non_admin_cannot_change_chat_settings(self):
        self.bot.on_event(make_event("频率 60", uid=2, mid="m1"))
        self.assertIn("只有管理员", self.sender.last())
        self.assertEqual(self.bot.store(123).chat_cooldown(self.cfg.chat_cooldown_seconds), 0)

    def test_admin_can_set_frequency_and_toggle_chat(self):
        self.bot.on_event(make_event("频率 30", uid=1, mid="m1"))
        self.assertIn("30 秒", self.sender.last())
        self.assertEqual(self.bot.store(123).chat_cooldown(0), 30)

        self.bot.on_event(make_event("聊天 关", uid=1, mid="m2"))
        self.assertIn("聊天关啦", self.sender.last())
        before = len(self.llm.chat_calls)
        self.bot.on_event(make_event("今天好累", mid="m3"))
        self.assertEqual(len(self.llm.chat_calls), before)

        self.bot.on_event(make_event("聊天 开", uid=1, mid="m4"))
        self.assertIn("聊天开啦", self.sender.last())

    def test_cooldown_blocks_second_chat(self):
        self.bot.on_event(make_event("频率 30", uid=1, mid="m1"))
        self.llm.chat_reply = "摩卡~ 在听哦~"
        self.bot.on_event(make_event("在吗", mid="m2"))
        self.bot.on_event(make_event("在吗", mid="m3"))
        self.assertEqual(len(self.llm.chat_calls), 1)

    def test_chat_budget_blocks(self):
        store = self.bot.store(123)
        store.add_chat_usage(self.cfg.chat_daily_token_budget, 0, today_str(self.cfg.timezone))
        self.bot.on_event(make_event("今天好累", mid="m1"))
        self.assertIn("今天聊得有点多", self.sender.last())
        self.assertEqual(self.llm.chat_calls, [])

    def _enable_auto(self):
        self.cfg.auto_speak_enabled = True
        self.cfg.auto_speak_cooldown_seconds = 0
        self.cfg.auto_speak_probability_percent = 100
        self.cfg.auto_speak_interest_boost_percent = 100
        self.cfg.auto_speak_min_messages = 1

    def test_auto_speak_triggers_on_normal_message(self):
        self._enable_auto()
        self.bot.on_event(make_event("摩卡今天想吃面包吗", at=False, mid="m1"))
        self.assertTrue(self.llm.chat_calls)
        self.assertEqual(self.sender.last(), "摩卡~ 收到啦~")

    def test_auto_speak_ignores_commands(self):
        self._enable_auto()
        self.bot.on_event(make_event("整理", uid=1, at=False, mid="m1"))
        self.assertEqual(self.llm.chat_calls, [])
        self.assertEqual(self.sender.sent, [])

    def test_auto_speak_can_be_disabled(self):
        self._enable_auto()
        self.bot.on_event(make_event("自动发言 关", uid=1, mid="m1"))
        self.assertIn("自动发言关", self.sender.last())
        self.bot.on_event(make_event("摩卡在吗", at=False, mid="m2"))
        self.assertEqual(self.llm.chat_calls, [])

    def test_auto_speak_admin_controls(self):
        self.bot.on_event(make_event("自动发言 频率 300", uid=1, mid="m1"))
        self.assertEqual(self.bot.store(123).auto_cooldown(0), 300)
        self.bot.on_event(make_event("自动发言 概率 5", uid=1, mid="m2"))
        self.assertEqual(self.bot.store(123).auto_probability(0), 5)
        self.bot.on_event(make_event("自动发言 条数 3", uid=1, mid="m3"))
        self.assertEqual(self.bot.store(123).auto_min_messages(0), 3)
        self.bot.on_event(make_event("自动发言 关", uid=2, mid="m4"))
        self.assertIn("只有管理员", self.sender.last())

    def test_face_tag_and_multiline(self):
        self.llm.chat_reply = "第一句\n第二句 [[face:14]]"
        self.bot.on_event(make_event("在吗", mid="m1"))
        self.assertEqual(self.sender.sent[-2][1], "第一句")
        self.assertEqual(self.sender.sent[-1][1], "第二句")
        self.assertEqual(self.sender.faces[-1], [14])

    def test_meme_tag_selects_sticker(self):
        sticker_dir = self.root / "stickers"
        sticker_dir.mkdir(exist_ok=True)
        (sticker_dir / "meme.jpg").write_bytes(b"\xff\xd8fake")
        self.bot.stickers.index["items"]["x"] = {
            "file": "meme.jpg",
            "emotion": "无语",
            "tags": ["无语"],
            "safe": True,
        }
        self.cfg.sticker_auto_chance_percent = 0
        self.llm.chat_reply = "好耶 [[meme:无语]]"
        self.bot.on_event(make_event("在吗", mid="m1"))
        self.assertEqual(len(self.sender.images), 1)
        self.assertNotIn("[[meme", self.sender.last())

    def test_sticker_test_command(self):
        sticker_dir = self.root / "stickers"
        sticker_dir.mkdir(exist_ok=True)
        (sticker_dir / "meme.jpg").write_bytes(b"\xff\xd8fake")
        self.bot.stickers.index["items"]["x"] = {
            "file": "meme.jpg",
            "emotion": "无语",
            "tags": ["无语"],
            "safe": True,
        }
        self.bot.on_event(make_event("表情测试 无语", uid=1, mid="m1"))
        self.assertEqual(len(self.sender.images), 1)
        self.assertIn("无语", self.sender.last())

    @unittest.skipUnless(HAS_PIL, "需要 Pillow")
    def test_panel_commands_send_images(self):
        store = self.bot.store(123)
        store.save_canon({
            "entities": {
                "character:林晚": {
                    "type": "character", "name": "林晚", "fields": {},
                    "relations": [{"to": "老周", "kind": "师徒"}], "sources": [1],
                },
                "character:老周": {
                    "type": "character", "name": "老周", "fields": {},
                    "relations": [], "sources": [2],
                },
                "nation:诺伦联邦": {
                    "type": "nation", "name": "诺伦联邦",
                    "fields": {"范本": {"value": "德国"}}, "relations": [], "sources": [3],
                },
                "location:前哨站": {
                    "type": "location", "name": "前哨站",
                    "fields": {"位置": {"value": "荒原边缘"}}, "relations": [], "sources": [4],
                },
            },
            "conflicts": {}, "questions": {},
        })
        for index, command in enumerate(("人物关系", "统计面板", "地区图")):
            self.bot.on_event(make_event(command, mid=f"p{index}"))
        self.assertEqual(len(self.sender.images), 3)

    @unittest.skipUnless(HAS_PIL, "需要 Pillow")
    def test_relationship_pages_when_many_characters(self):
        entities = {}
        for index in range(20):
            name = f"角色{index:02d}"
            entities[f"character:{name}"] = {
                "type": "character", "name": name,
                "fields": {"乐队": {"value": f"乐队{index % 5}"}},
                "relations": [], "sources": [],
            }
        self.bot.store(123).save_canon({
            "entities": entities, "conflicts": {}, "questions": {},
        })
        self.bot.on_event(make_event("人物关系", mid="m1"))
        self.assertGreaterEqual(len(self.sender.images), 2)

    def test_help_sends_one_page_image(self):
        assets = self.root / "assets"
        assets.mkdir()
        for page in range(1, 6):
            (assets / f"mocha-bakery-help-{page}.png").write_bytes(b"\x89PNGfake")
        self.bot.on_event(make_event("帮助", mid="m1"))
        self.assertEqual(len(self.sender.images), 1)
        self.assertIn("mocha-bakery-help-1.png", self.sender.images[0])
        self.bot.on_event(make_event("帮助 3", mid="m2"))
        self.assertEqual(len(self.sender.images), 2)
        self.assertIn("mocha-bakery-help-3.png", self.sender.images[-1])
        self.bot.on_event(make_event("帮助 下一页", mid="m3"))
        self.assertIn("mocha-bakery-help-4.png", self.sender.images[-1])
        self.bot.on_event(make_event("帮助 5", mid="m4"))
        self.assertIn("mocha-bakery-help-5.png", self.sender.images[-1])

    def test_help(self):
        self.bot.on_event(make_event("帮助", mid="m1"))
        self.assertIn("青叶摩卡", self.sender.last())


if __name__ == "__main__":
    unittest.main()
