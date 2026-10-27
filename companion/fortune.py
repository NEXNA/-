"""每日运势：只做娱乐，确定性生成，不依赖模型。"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from zoneinfo import ZoneInfo

COLORS = ["薄荷绿", "暖橙", "雾蓝", "奶油白", "樱粉", "墨绿", "浅金", "灰紫"]
GOOD = [
    "整理房间", "散步", "听一首老歌", "给朋友发消息", "早点睡",
    "写三行日记", "喝一杯热水", "读几页书", "晒十分钟太阳", "做一件小事",
]
BAD = [
    "熬夜", "空腹喝咖啡", "临时改计划", "翻旧聊天记录", "冲动消费",
    "把话说太满", "和自己较劲", "拖到最后一刻", "在情绪里做决定", "忘记吃饭",
]
SUMMARIES = [
    "今天适合把节奏放慢一点，先把眼前的小事做好。",
    "会有一点小波折，但不影响整体；别急着下结论。",
    "适合主动一点，你的一句话可能让事情变得不一样。",
    "今天的好运藏在细节里，留意身边人随口提的事。",
    "状态不错，适合做一件一直拖着的小事。",
    "可能会有点累，允许自己休息，不用把每件事都做完。",
]


def _number(*parts: object, modulo: int) -> int:
    raw = ":".join(str(p) for p in parts).encode("utf-8")
    return int(hashlib.sha256(raw).hexdigest()[:12], 16) % modulo


def today(timezone: str = "Asia/Shanghai") -> str:
    return datetime.now(ZoneInfo(timezone)).date().isoformat()


def make_fortune(user_id: int, nickname: str, date: str | None = None,
                 timezone: str = "Asia/Shanghai") -> dict:
    day = date or today(timezone)
    seed = f"{user_id}:{day}:{nickname}"
    overall = _number(seed, "overall", modulo=5) + 1
    love = _number(seed, "love", modulo=5) + 1
    work = _number(seed, "work", modulo=5) + 1
    wealth = _number(seed, "wealth", modulo=5) + 1
    return {
        "date": day,
        "overall": overall,
        "love": love,
        "work": work,
        "wealth": wealth,
        "summary": SUMMARIES[_number(seed, "summary", modulo=len(SUMMARIES))],
        "lucky_color": COLORS[_number(seed, "color", modulo=len(COLORS))],
        "lucky_number": _number(seed, "number", modulo=9) + 1,
        "good": GOOD[_number(seed, "good", modulo=len(GOOD))],
        "bad": BAD[_number(seed, "bad", modulo=len(BAD))],
        "note": "运势只是娱乐，不替代现实判断。",
    }


def dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
