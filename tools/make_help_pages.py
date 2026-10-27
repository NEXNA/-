"""生成「青叶摩卡的面包坊」多页帮助图。

每页独立 PNG，机器人每次「帮助」只发一张。
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import make_help_card as base  # noqa: E402

ROOT = TOOLS.parent
OUT_DIR = ROOT / "assets"

PAGES = [
    {
        "title": "开始与记录",
        "left": ["01"],
        "right": ["02"],
        "warm": "欢迎回来。这里是青叶摩卡的面包坊，设定慢慢写，面包趁热吃。",
        "note": "不用急着一次写完，摩卡会陪你慢慢理。",
    },
    {
        "title": "聊天与安全",
        "left": ["04"],
        "right": ["06", "05"],
        "warm": "聊天不用急，摩卡会听；重要的事，她会多问一句。",
        "note": "被叫到名字，她会回头；不想说话时，也可以安静待着。",
    },
    {
        "title": "面板、娱乐与面包坊",
        "left": ["03", "08"],
        "right": ["07"],
        "warm": "累了就睡一会儿，饿了就买个面包；世界可以等一等。",
        "note": "面包要趁热，睡觉要盖好被子。",
    },
    {
        "title": "B站图库与小提示",
        "left": ["09"],
        "right": ["tips"],
        "warm": "谢谢你陪摩卡走到这里。想找图、想聊天，随时回来。",
        "note": "图库空了也没关系，故事才是主食。",
    },
    {
        "title": "记忆、提醒与私聊后台",
        "left": ["10"],
        "right": ["11"],
        "warm": "记住你随口说过的小事，也记得给你留一盏灯。",
        "note": "私聊我，管理后台就在那边。",
    },
]

SECTIONS = {}
for number, title, rows in base.LEFT_SECTIONS + base.RIGHT_SECTIONS:
    SECTIONS[number] = (number, title, rows)
SECTIONS["10"] = ("10", "长期记忆与设定", [
    ("@青叶摩卡 记住 <内容>", "让摩卡记住一件事", False),
    ("@青叶摩卡 设定 我是…", "跨群设定，所有群都记得", False),
    ("@青叶摩卡 记忆 / 设定", "查看 / 删除设定", False),
    ("@青叶摩卡 隐私", "查看 / 删除自己的数据", False),
    ("@青叶摩卡 提醒 30分钟 喝水", "定时提醒", False),
    ("@青叶摩卡 提醒 / 取消提醒 3", "查看 / 取消提醒", False),
])
SECTIONS["11"] = ("11", "私聊管理后台", [
    ("私聊：群列表 / 进入 <群号>", "切换管理的群", True),
    ("状态 / 待定 / 删除待定 Q-01", "查看和处理", True),
    ("聊天 开/关", "群聊开关", True),
    ("自动发言 开/关", "自动接话开关", True),
    ("广播 <内容>", "发到当前群", True),
])


def _canvas(width: int, height: int):
    img = Image.new("RGB", (width, height), base.BG_TOP)
    draw = ImageDraw.Draw(img)
    for y in range(height):
        t = y / max(1, height - 1)
        color = tuple(int(base.BG_TOP[i] * (1 - t) + base.BG_BOTTOM[i] * t)
                      for i in range(3))
        draw.line([(0, y), (width, y)], fill=color)
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.ellipse((-180, -220, 480, 440), fill=(0, 204, 170, 24))
    od.ellipse((width - 360, 120, width + 240, 720), fill=(255, 209, 102, 16))
    od.ellipse((width - 420, height - 460, width + 200, height + 80),
               fill=(255, 143, 163, 13))
    rng = random.Random(7)
    for _ in range(80):
        x = rng.randint(0, width)
        y = rng.randint(0, height)
        r = rng.choice([1, 1, 2])
        od.ellipse((x, y, x + r, y + r), fill=(255, 255, 255, 24))
    img = Image.alpha_composite(img.convert("RGBA"), overlay)
    return img, ImageDraw.Draw(img)


def draw_header(draw, page: int, total: int, title: str) -> None:
    draw.ellipse((base.PAD, 50, base.PAD + 96, 146), fill=base.ACCENT)
    draw.text((base.PAD + 48, 98), "M", font=base.font(48, True),
              fill=base.CREAM, anchor="mm")
    draw.text((base.PAD + 116, 52), "青叶摩卡的面包坊", font=base.font(48, True),
              fill=base.CREAM)
    draw.text((base.PAD + 118, 112), f"使用帮助 · 第 {page}/{total} 页 · {title}",
              font=base.font(23), fill=base.ACCENT_LIGHT)
    pill = (base.PAD + 118, 154, base.PAD + 300, 190)
    draw.rounded_rectangle(pill, radius=18, fill=(0, 204, 170, 38),
                           outline=base.ACCENT_LIGHT, width=1)
    draw.text((base.PAD + 209, 172), "Afterglow × 面包坊", font=base.font(17, True),
              fill=base.ACCENT_LIGHT, anchor="mm")
    next_page = 1 if page == total else page + 1
    draw.text((base.PAD, 218),
              f"帮助分页啦：每次只发一张，发「帮助 {next_page}」可以看下一页。",
              font=base.font(21), fill=(206, 238, 231))


def draw_tip_card(img, draw, x: int, y: int, title: str, tips: list[str]):
    h = 74 + len(tips) * 46 + 14
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle((x + 8, y + 8, x + base.COL_W + 8, y + h + 8),
                         radius=26, fill=(0, 12, 11, 55))
    img = Image.alpha_composite(img, shadow)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((x, y, x + base.COL_W, y + h), radius=26,
                           fill=(0, 204, 170, 30))
    draw.text((x + 24, y + 20), title, font=base.font(26, True),
              fill=(214, 248, 241))
    for index, tip in enumerate(tips):
        lines = base.wrap_chars(draw, f"· {tip}", base.font(17),
                                base.COL_W - 48, 2)
        for line_index, text in enumerate(lines):
            draw.text((x + 24, y + 68 + index * 46 + line_index * 21), text,
                      font=base.font(17), fill=(176, 224, 216))
    return img, draw, h


def draw_warm_card(img, draw, x: int, y: int, text: str):
    h = 176
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle((x + 8, y + 8, x + base.COL_W + 8, y + h + 8),
                         radius=26, fill=(0, 12, 11, 55))
    img = Image.alpha_composite(img, shadow)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((x, y, x + base.COL_W, y + h), radius=26,
                           fill=(0, 204, 170, 30))
    draw.text((x + 24, y + 20), "摩卡想说", font=base.font(24, True),
              fill=(214, 248, 241))
    lines = base.wrap_chars(draw, text, base.font(19), base.COL_W - 48, 3)
    for index, line in enumerate(lines):
        draw.text((x + 24, y + 66 + index * 30), line,
                  font=base.font(19), fill=(224, 250, 244))
    return img, draw, h


def main() -> int:
    total = len(PAGES)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for index, page in enumerate(PAGES, 1):
        left_items = [SECTIONS[key] for key in page["left"]]
        right_items = [SECTIONS[key] for key in page["right"] if key in SECTIONS]
        right_has_tips = "tips" in page["right"]

        left_h = sum(base.card_height(rows) + base.CARD_GAP
                     for _, _, rows in left_items)
        right_h = sum(base.card_height(rows) + base.CARD_GAP
                      for _, _, rows in right_items)
        tips_h = (74 + len(base.TIPS) * 46 + 14) if right_has_tips else 0
        if right_has_tips:
            right_h += tips_h + base.CARD_GAP
        content_h = max(left_h, right_h)
        height = base.HEADER_H + content_h + 150
        img, draw = _canvas(base.W, height)
        draw_header(draw, index, total, page["title"])

        y = base.HEADER_H
        for number, title, rows in left_items:
            img, draw = base.draw_section(
                img, draw, base.LEFT_X, y, number, title, rows,
            )
            y += base.card_height(rows) + base.CARD_GAP
        left_end = y

        y = base.HEADER_H
        for number, title, rows in right_items:
            img, draw = base.draw_section(
                img, draw, base.RIGHT_X, y, number, title, rows,
            )
            y += base.card_height(rows) + base.CARD_GAP
        right_end = y
        if right_has_tips:
            img, draw, tips_h = draw_tip_card(
                img, draw, base.RIGHT_X, y, "小提示", base.TIPS,
            )
            y += tips_h
            right_end = y

        page_bottom = base.HEADER_H + content_h
        if page_bottom - left_end > 200:
            img, draw, _ = draw_warm_card(
                img, draw, base.LEFT_X, left_end + 8, page.get("note", page["warm"]),
            )
        elif page_bottom - right_end > 200:
            img, draw, _ = draw_warm_card(
                img, draw, base.RIGHT_X, right_end + 8, page.get("note", page["warm"]),
            )

        # 页码 + 温馨话放在页脚，不挤压功能列表。
        draw.line([(base.PAD, height - 96), (base.W - base.PAD, height - 96)],
                  fill=(80, 150, 140), width=1)
        next_page = 1 if index == total else index + 1
        draw.text(
            (base.W // 2, height - 64),
            f"第 {index}/{total} 页 · 发「帮助 {next_page}」继续看 · "
            "更多说明见 README.md",
            font=base.font(18), fill=(150, 205, 196), anchor="mm",
        )
        draw.text(
            (base.W // 2, height - 28), page["warm"],
            font=base.font(19), fill=(214, 248, 241), anchor="mm",
        )

        out = OUT_DIR / f"mocha-bakery-help-{index}.png"
        img.convert("RGB").save(out, "PNG", optimize=True)
        print(f"已生成：{out}  {img.size[0]}x{img.size[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
