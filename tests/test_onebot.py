from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path

from bot.onebot import OneBotClient, parse_event


class ParseEventTest(unittest.TestCase):
    def test_array_segments(self):
        event = {
            "post_type": "message",
            "message_type": "group",
            "group_id": 123,
            "user_id": 2,
            "message_id": "m1",
            "self_id": 999,
            "sender": {"card": "兰", "nickname": "nick"},
            "message": [
                {"type": "reply", "data": {"id": "q1"}},
                {"type": "at", "data": {"qq": "999"}},
                {"type": "text", "data": {"text": " 林晚是医师 "}},
            ],
        }
        msg = parse_event(event)
        self.assertIsNotNone(msg)
        self.assertEqual(msg.group_id, 123)
        self.assertEqual(msg.nick, "兰")
        self.assertEqual(msg.text, "林晚是医师")
        self.assertTrue(msg.at_me)
        self.assertEqual(msg.at_user_ids, [999])
        self.assertEqual(msg.reply_id, "q1")

    def test_cq_fallback(self):
        event = {
            "post_type": "message",
            "message_type": "group",
            "group_id": 123,
            "user_id": 2,
            "message_id": "m1",
            "self_id": 999,
            "sender": {"nickname": "兰"},
            "message": "[CQ:reply,id=-5][CQ:at,qq=999] 林晚是医师",
        }
        msg = parse_event(event)
        self.assertTrue(msg.at_me)
        self.assertEqual(msg.reply_id, "-5")
        self.assertEqual(msg.text, "林晚是医师")

    def test_bilibili_json_share_card(self):
        card = ('{"app":"com.tencent.structmsg","meta":{"news":{'
                '"title":"B站视频","jumpUrl":"https://www.bilibili.com/video/BV1HR4y197qP"}}}')
        event = {
            "post_type": "message", "message_type": "group",
            "group_id": 123, "user_id": 2, "message_id": "m1", "self_id": 999,
            "sender": {"nickname": "a"},
            "message": [{"type": "json", "data": {"data": card}}],
        }
        msg = parse_event(event)
        self.assertIn("BV1HR4y197qP", msg.text)

    def test_bilibili_cq_json_card(self):
        event = {
            "post_type": "message", "message_type": "group",
            "group_id": 123, "user_id": 2, "message_id": "m1", "self_id": 999,
            "sender": {"nickname": "a"},
            "message": (
                '[CQ:json,data={"meta":{"news":{"jumpUrl":'
                '"https:\\/\\/b23.tv\\/abc123"}}}]'
            ),
        }
        msg = parse_event(event)
        self.assertIn("https://b23.tv/abc123", msg.text)

    def test_not_at_me(self):
        event = {
            "post_type": "message", "message_type": "group",
            "group_id": 123, "user_id": 2, "message_id": "m1", "self_id": 999,
            "sender": {"nickname": "a"},
            "message": [{"type": "text", "data": {"text": "随便聊聊"}}],
        }
        msg = parse_event(event)
        self.assertFalse(msg.at_me)

    def test_image_and_face_segments(self):
        event = {
            "post_type": "message", "message_type": "group",
            "group_id": 123, "user_id": 2, "message_id": "m1", "self_id": 999,
            "sender": {"nickname": "a"},
            "message": [
                {"type": "image", "data": {"url": "https://example.com/a.png",
                                           "file": "a.png"}},
                {"type": "face", "data": {"id": "13"}},
            ],
        }
        msg = parse_event(event)
        self.assertTrue(msg.has_image)
        self.assertEqual(msg.image_urls, ["https://example.com/a.png"])
        self.assertEqual(msg.image_files, ["a.png"])
        self.assertTrue(msg.has_face)

    def test_ignores_non_group(self):
        self.assertIsNone(parse_event({"post_type": "message", "message_type": "private"}))
        self.assertIsNone(parse_event({"post_type": "notice"}))


class FakeOneBot(OneBotClient):
    def __init__(self):
        super().__init__("http://127.0.0.1:1", "token")
        self.calls = []

    def _call(self, action, **params):
        self.calls.append((action, params))
        return {"message_id": len(self.calls)}


class SendTest(unittest.TestCase):
    def test_long_text_is_split_and_reply_only_on_first(self):
        client = FakeOneBot()
        text = "\n".join("设定" * 100 for _ in range(10))
        client.send_text(123, text, reply_to="42")
        self.assertGreater(len(client.calls), 1)
        first = client.calls[0][1]["message"]
        self.assertEqual(first[0], {"type": "reply", "data": {"id": "42"}})
        second = client.calls[1][1]["message"]
        self.assertEqual(second[0]["type"], "text")

    def test_face_segment_is_appended(self):
        client = FakeOneBot()
        client.send_text(123, "好耶~", face_ids=[13])
        message = client.calls[0][1]["message"]
        self.assertEqual(message[-1], {"type": "face", "data": {"id": "13"}})

    def test_send_image_uses_base64(self):
        client = FakeOneBot()
        root = Path(__file__).parent / ".tmp" / f"img-{uuid.uuid4().hex[:8]}"
        root.mkdir(parents=True)
        path = root / "a.jpg"
        path.write_bytes(b"\xff\xd8fake")
        try:
            client.send_image(123, path)
            message = client.calls[0][1]["message"]
            self.assertEqual(message[0]["type"], "image")
            self.assertTrue(message[0]["data"]["file"].startswith("base64://"))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_quoted_text(self):
        client = FakeOneBot()
        client.get_msg = lambda message_id: {  # type: ignore[method-assign]
            "sender": {"card": "兰"},
            "message": [{"type": "text", "data": {"text": "蚀月每三十年出现"}}],
        }
        quoted = client.quoted_text("q1")
        self.assertEqual(quoted, ("兰", "蚀月每三十年出现"))

    def test_upload_group_file(self):
        client = FakeOneBot()
        client.upload_group_file(123, "C:/tmp/a.md", "a.md")
        self.assertEqual(client.calls[0][0], "upload_group_file")
        self.assertEqual(client.calls[0][1]["name"], "a.md")


if __name__ == "__main__":
    unittest.main()
