"""面包坊：静态菜单数据。

价格和回复量都在这里改，命令和图片共用同一份数据。
"""

from __future__ import annotations

import re

CURRENCY = "摩卡币"

BAKERIES: list[dict] = [
    {
        "key": "yamabuki",
        "name": "山吹烘焙坊",
        "tag": "放学路上最香的那一家",
        "breads": [
            {"id": 1, "name": "招牌奶油面包", "price": 25, "hunger": 25, "mood": 8, "sleepiness": 2, "emoji": "🍞"},
            {"id": 2, "name": "咖喱面包", "price": 35, "hunger": 35, "mood": 10, "sleepiness": 3, "emoji": "🍛"},
            {"id": 3, "name": "巧克力螺旋", "price": 40, "hunger": 22, "mood": 15, "sleepiness": 2, "emoji": "🍫"},
        ],
    },
    {
        "key": "hazawa",
        "name": "羽泽咖啡店",
        "tag": "吐司要厚切，咖啡要续杯",
        "breads": [
            {"id": 4, "name": "厚切吐司", "price": 30, "hunger": 28, "mood": 7, "sleepiness": 1, "emoji": "🍞"},
            {"id": 5, "name": "火腿三明治", "price": 45, "hunger": 40, "mood": 12, "sleepiness": 2, "emoji": "🥪"},
            {"id": 6, "name": "蜂蜜吐司", "price": 38, "hunger": 30, "mood": 10, "sleepiness": 2, "emoji": "🍯"},
        ],
    },
    {
        "key": "moca",
        "name": "摩卡面包坊",
        "tag": "面包和咖啡都要双份",
        "breads": [
            {"id": 7, "name": "摩卡咖啡面包", "price": 55, "hunger": 32, "mood": 20, "sleepiness": 4, "emoji": "☕"},
            {"id": 8, "name": "巧克力面包", "price": 50, "hunger": 26, "mood": 18, "sleepiness": 3, "emoji": "🍫"},
            {"id": 9, "name": "抹茶面包", "price": 48, "hunger": 28, "mood": 16, "sleepiness": 2, "emoji": "🍵"},
        ],
    },
    {
        "key": "night",
        "name": "深夜面包房",
        "tag": "熬夜的人也需要碳水",
        "breads": [
            {"id": 10, "name": "芝士焗面包", "price": 65, "hunger": 45, "mood": 15, "sleepiness": 4, "emoji": "🧀"},
            {"id": 11, "name": "蒜香法棍", "price": 60, "hunger": 40, "mood": 12, "sleepiness": 3, "emoji": "🥖"},
            {"id": 12, "name": "奶油夹心", "price": 70, "hunger": 35, "mood": 25, "sleepiness": 5, "emoji": "🧁"},
        ],
    },
]

ALL_BREADS: list[dict] = []
for _shop in BAKERIES:
    for _bread in _shop["breads"]:
        item = dict(_bread)
        item["shop"] = _shop["name"]
        item["shop_key"] = _shop["key"]
        ALL_BREADS.append(item)


def find_bread(token: str) -> dict | None:
    value = (token or "").strip()
    match = re.match(r"^[#＃]?\s*(\d{1,3})$", value)
    if match:
        target = int(match.group(1))
        for bread in ALL_BREADS:
            if bread["id"] == target:
                return bread
        return None
    for bread in ALL_BREADS:
        if bread["name"] == value:
            return bread
    return None


def bread_by_id(bread_id: int) -> dict | None:
    for bread in ALL_BREADS:
        if bread["id"] == bread_id:
            return bread
    return None
