"""旧版帮助长图版式；现在由 make_help_pages.py 复用分页生成。

用法：
    python tools/make_help_pages.py
输出：
    assets/mocha-bakery-help-1..4.png
"""
from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "help.png"

W = 1400
PAD = 60
COL_W = 620
COL_GAP = 40
LEFT_X = PAD
RIGHT_X = PAD + COL_W + COL_GAP
HEADER_H = 280
ROW_H = 58
CARD_GAP = 20

FONT_REG = r"C:\Windows\Fonts\msyh.ttc"
FONT_BOLD = r"C:\Windows\Fonts\msyhbd.ttc"

BG_TOP = (7, 43, 40)
BG_BOTTOM = (10, 71, 65)
ACCENT = (0, 204, 170)
ACCENT_LIGHT = (128, 236, 214)
CREAM = (255, 253, 246)
INK = (22, 55, 50)
MUTED = (104, 128, 122)
GOLD = (255, 209, 102)

LEFT_SECTIONS = [
    ("01", "添加与维护", [
        ("@青叶摩卡 添加 <内容>", "新增一条设定素材（管理员）", True),
        ("引用消息 + @青叶摩卡 添加", "把引用内容加进来（管理员）", True),
        ("@青叶摩卡 整合", "合并素材，标出冲突（管理员）", True),
        ("@青叶摩卡 全量整合", "重建全部（管理员）", True),
        ("@青叶摩卡 删除 <名字>", "删除条目（管理员）", True),
        ("@青叶摩卡 删除 素材 #12", "删除待整合素材（管理员）", True),
    ]),
    ("02", "查询与输出", [
        ("@青叶摩卡 查 <名字>", "查人物/势力/地点", False),
        ("@青叶摩卡 待定", "看待裁决和待补完", False),
        ("@青叶摩卡 待定 添加 <问题>", "手动加待定（管理员）", True),
        ("@青叶摩卡 待定 删除 Q-01", "手动删待定（管理员）", True),
        ("@青叶摩卡 待定 提问", "让摩卡提新问题（管理员）", True),
        ("@青叶摩卡 待定 采纳 1", "采纳为待定（管理员）", True),
        ("@青叶摩卡 待定 忽略", "丢弃建议（管理员）", True),
        ("@青叶摩卡 谁在找我", "看谁找过摩卡", False),
        ("@青叶摩卡 裁决 C-01 27", "选定冲突的值（管理员）", True),
        ("@青叶摩卡 导出", "导出 Markdown", False),
        ("@青叶摩卡 回滚", "撤销上次整理（管理员）", True),
        ("@青叶摩卡 状态", "看素材数和今日 token", False),
    ]),
    ("03", "面板与邦多利", [
        ("@青叶摩卡 人物关系", "生成人物关系图", False),
        ("@青叶摩卡 统计面板", "设定统计仪表盘", False),
        ("@青叶摩卡 地区图", "国家/地区资料卡", False),
        ("@青叶摩卡 邦多利 查 <名字>", "查独立邦多利库", False),
        ("@青叶摩卡 邦多利 人物关系", "邦多利关系图", False),
        ("@青叶摩卡 邦多利 统计面板", "邦多利统计", False),
    ]),
]

RIGHT_SECTIONS = [
    ("04", "聊天与自动发言", [
        ("@青叶摩卡 说点什么", "直接聊天，不用命令", False),
        ("@青叶摩卡 聊 <内容>", "明确走聊天", False),
        ("@青叶摩卡 建议 <问题>", "回答 + 一句短建议", False),
        ("@青叶摩卡 评价", "点评当前设定库", False),
        ("@青叶摩卡 自动发言", "看/调自动接话（管理员）", True),
        ("@青叶摩卡 频率 30", "回复间隔（管理员）", True),
        ("@青叶摩卡 聊天 开/关", "开关闲聊（管理员）", True),
        ("@青叶摩卡 聊天上限 500000", "今日 token 上限（管理员）", True),
        ("@青叶摩卡 接话 添加 <QQ/@人>", "必接谁的话（管理员）", True),
    ]),
    ("05", "meme 表情包", [
        ("@青叶摩卡 表情", "看表情库和本群设置（管理员）", True),
        ("@青叶摩卡 表情同步 48", "从 QQ 收藏同步（管理员）", True),
        ("@青叶摩卡 表情扫描", "扫描 stickers/（管理员）", True),
        ("@青叶摩卡 表情测试 无语", "发一张测试（管理员）", True),
    ]),
    ("06", "模型开关", [
        ("@青叶摩卡 思考 开/关", "深度思考（管理员）", True),
        ("@青叶摩卡 联网 开/关", "自动联网（管理员）", True),
        ("@青叶摩卡 联网 <问题>", "查一次网页", False),
        ("@青叶摩卡 搜索 <问题>", "同上，显式搜索", False),
        ("@青叶摩卡 安全", "看群白名单/写权限（管理员）", True),
        ("@青叶摩卡 群白名单", "临时添加/查看允许群（管理员）", True),
    ]),
    ("07", "娱乐", [
        ("@青叶摩卡 睡觉 [30]", "睡一会儿（默认 30 分钟）", False),
        ("@青叶摩卡 起床", "叫醒摩卡", False),
        ("@青叶摩卡 摩卡状态", "饱腹 / 困意 / 心情 / 钱包", False),
        ("@青叶摩卡 状态变化 开/关", "自然衰减开关（管理员）", True),
    ]),
    ("08", "面包坊", [
        ("@青叶摩卡 面包坊", "单开一页：菜单 + 状态", False),
        ("@青叶摩卡 买面包 1", "花摩卡币买面包", False),
        ("@青叶摩卡 打工", "随机赚摩卡币", False),
        ("@青叶摩卡 钱包", "看自己的摩卡币", False),
        ("@青叶摩卡 无限货币 开/关", "管理员专属", True),
    ]),
    ("09", "B站图库", [
        ("@青叶摩卡 找图 [数量] [词]", "从B站收二次元图（管理员）", True),
        ("@青叶摩卡 图库", "看本地张数/上限", False),
        ("@青叶摩卡 随机图", "随机发一张本地图", False),
    ]),
]

TIPS = [
    "旧命令「记」「整理」仍然可用，但帮助里只列新的。",
    "「删除」会先做快照，删错了可以发「回滚」。",
    "人物关系/统计面板/地区图默认来自主世界 canon.json；邦多利是独立库。",
    "叫到「摩卡」名字会直接接话；仍受聊天/自动/睡觉限制。",
    "亲密举动只对栉耶或管理员开放，其他人会被拒绝。",
    "回复一张图并 @摩卡，她能看到引用的那张图。",
    "聊天默认 1-2 条短消息；说「详细说说」才会展开。",
]


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REG, size, index=0)


def wrap_chars(draw: ImageDraw.ImageDraw, text: str, f, max_width: int,
               max_lines: int = 2) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in text:
        if draw.textlength(current + char, font=f) <= max_width:
            current += char
        else:
            if current:
                lines.append(current)
            current = char
            if len(lines) >= max_lines:
                break
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) == max_lines and sum(len(x) for x in lines) < len(text):
        lines[-1] = lines[-1][:-1] + "…"
    return lines


def card_height(rows) -> int:
    return 66 + len(rows) * ROW_H + 20


def draw_header(draw: ImageDraw.ImageDraw) -> None:
    draw.ellipse((PAD, 52, PAD + 104, 156), fill=ACCENT)
    draw.text((PAD + 52, 104), "M", font=font(54, True), fill=CREAM, anchor="mm")
    draw.text((PAD + 126, 58), "青叶摩卡的面包坊", font=font(50, True), fill=CREAM)
    draw.text((PAD + 128, 124), "添加 · 删除 · 整合 · 面板 · 聊天 · 面包 · 图库",
              font=font(24), fill=ACCENT_LIGHT)
    pill = (PAD + 128, 166, PAD + 254, 204)
    draw.rounded_rectangle(pill, radius=19, fill=(0, 204, 170, 38),
                           outline=ACCENT_LIGHT, width=1)
    draw.text((PAD + 191, 185), "Afterglow", font=font(19, True),
              fill=ACCENT_LIGHT, anchor="mm")
    draw.text((PAD, 226), "添加设定用「添加」，合并用「整合」，删条目用「删除」。",
              font=font(22), fill=(206, 238, 231))


def draw_section(img, draw, x: int, y: int, number: str, title: str, rows):
    h = card_height(rows)
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle((x + 8, y + 8, x + COL_W + 8, y + h + 8), radius=26,
                         fill=(0, 12, 11, 55))
    img = Image.alpha_composite(img, shadow)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((x, y, x + COL_W, y + h), radius=26, fill=CREAM)
    draw.rounded_rectangle((x + 20, y + 18, x + 62, y + 58), radius=14,
                           fill=(0, 204, 170, 30))
    draw.text((x + 41, y + 38), number, font=font(19, True),
              fill=(0, 140, 118), anchor="mm")
    draw.text((x + 80, y + 36), title, font=font(28, True), fill=INK)

    row_y = y + 66
    for index, (command, desc, admin) in enumerate(rows):
        command_font = font(21, True)
        while draw.textlength(command, font=command_font) > 320 and command_font.size > 15:
            command_font = font(command_font.size - 1, True)
        draw.text((x + 24, row_y + 28), command, font=command_font,
                  fill=(0, 122, 106), anchor="lm")

        desc_text = desc.replace("（管理员）", "").strip()
        desc_font = font(17)
        desc_x = x + 350
        desc_width = 160 if admin else 225
        lines = wrap_chars(draw, desc_text, desc_font, desc_width, 2)
        for line_index, line in enumerate(lines):
            draw.text((desc_x, row_y + 16 + line_index * 21), line,
                      font=desc_font, fill=MUTED, anchor="lm")
        if admin:
            draw.rounded_rectangle((x + COL_W - 82, row_y + 15,
                                    x + COL_W - 20, row_y + 41),
                                   radius=13, fill=(255, 231, 176))
            draw.text((x + COL_W - 51, row_y + 28), "管理员",
                      font=font(14, True), fill=(122, 74, 0), anchor="mm")
        if index < len(rows) - 1:
            draw.line([(x + 24, row_y + 56), (x + COL_W - 24, row_y + 56)],
                      fill=(232, 245, 241), width=1)
        row_y += ROW_H
    return img, draw


def draw_tips(img, draw, x: int, y: int, height: int):
    draw.rounded_rectangle((x, y, x + COL_W, y + height), radius=26,
                           fill=(0, 204, 170, 30))
    draw.text((x + 24, y + 20), "小提示", font=font(26, True), fill=(214, 248, 241))
    for index, tip in enumerate(TIPS):
        line = f"· {tip}"
        lines = wrap_chars(draw, line, font(17), COL_W - 48, 2)
        for line_index, text in enumerate(lines):
            draw.text((x + 24, y + 64 + index * 46 + line_index * 21), text,
                      font=font(17), fill=(176, 224, 216))
    return img, draw


def main() -> int:
    left_height = sum(card_height(rows) + CARD_GAP for _, _, rows in LEFT_SECTIONS)
    right_height = sum(card_height(rows) + CARD_GAP for _, _, rows in RIGHT_SECTIONS)
    tips_h = 240
    right_height += tips_h + CARD_GAP
    height = HEADER_H + max(left_height, right_height) + 150

    img = Image.new("RGB", (W, height), BG_TOP)
    draw = ImageDraw.Draw(img)
    for y in range(height):
        t = y / max(1, height - 1)
        color = tuple(int(BG_TOP[i] * (1 - t) + BG_BOTTOM[i] * t) for i in range(3))
        draw.line([(0, y), (W, y)], fill=color)

    overlay = Image.new("RGBA", (W, height), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.ellipse((-180, -220, 480, 440), fill=(0, 204, 170, 25))
    od.ellipse((W - 360, 120, W + 240, 720), fill=(255, 209, 102, 16))
    od.ellipse((W - 420, height - 460, W + 200, height + 80),
               fill=(255, 143, 163, 14))
    rng = random.Random(7)
    for _ in range(100):
        x = rng.randint(0, W)
        y = rng.randint(0, height)
        r = rng.choice([1, 1, 2])
        od.ellipse((x, y, x + r, y + r), fill=(255, 255, 255, 26))
    img = Image.alpha_composite(img.convert("RGBA"), overlay)
    draw = ImageDraw.Draw(img)

    draw_header(draw)

    y = HEADER_H
    for number, title, rows in LEFT_SECTIONS:
        img, draw = draw_section(img, draw, LEFT_X, y, number, title, rows)
        y += card_height(rows) + CARD_GAP

    y = HEADER_H
    for number, title, rows in RIGHT_SECTIONS:
        img, draw = draw_section(img, draw, RIGHT_X, y, number, title, rows)
        y += card_height(rows) + CARD_GAP
    img, draw = draw_tips(img, draw, RIGHT_X, y, tips_h)

    draw.text((W // 2, height - 54),
              "更多说明见 README.md · 发「@青叶摩卡 帮助」随时看这张图",
              font=font(18), fill=(150, 205, 196), anchor="mm")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(OUT, "PNG", optimize=True)
    print(f"已生成：{OUT}  {img.size[0]}x{img.size[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
