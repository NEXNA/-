import unittest

from bot.bili_reader import extract_bvid


class BiliReaderUrlTests(unittest.TestCase):
    def test_extracts_bv_from_video_url(self):
        text = "分享 https://www.bilibili.com/video/BV1HR4y197qP?share_source=copy"
        self.assertEqual(extract_bvid(text), "BV1HR4y197qP")

    def test_extracts_bv_from_plain_text(self):
        self.assertEqual(extract_bvid("看看 BV1HR4y197qP 这个"), "BV1HR4y197qP")

    def test_non_bilibili_text(self):
        self.assertEqual(extract_bvid("今天吃什么"), "")


if __name__ == "__main__":
    unittest.main()
