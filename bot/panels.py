from __future__ import annotations

import math
import random
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .canon import TYPE_LABELS, TYPE_ORDER, find_key, open_conflicts, open_questions
from .util import norm_text

# 延迟导入 Pillow，让没装 Pillow 的环境还能正常聊天/整理，只在出图时报错。
FONT_REG = r"C:\Windows\Fonts\msyh.ttc"
FONT_BOLD = r"C:\Windows\Fonts\msyhbd.ttc"

BG_TOP = (7, 39, 37)
BG_BOTTOM = (10, 68, 62)
CREAM = (255, 253, 246)
INK = (22, 55, 50)
MUTED = (104, 128, 122)
ACCENT = (0, 204, 170)
GOLD = (255, 209, 102)
PINK = (255, 143, 163)
BLUE = (120, 190, 230)

TYPE_COLORS = {
    "character": (0, 204, 170),
    "faction": (255, 143, 163),
    "nation": (255, 209, 102),
    "region": (128, 236, 214),
    "location": (120, 190, 230),
    "item": (214, 180, 255),
    "event": (255, 180, 120),
    "rule": (180, 220, 150),
    "term": (200, 200, 200),
    "other": (180, 180, 180),
}


class PanelError(Exception):
    pass


def _pil():
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:  # pragma: no cover - 依赖本机环境
        raise PanelError("缺少 Pillow，先运行：pip install pillow") from exc
    return Image, ImageDraw, ImageFont


def _font(size: int, bold: bool = False):
    _Image, _ImageDraw, ImageFont = _pil()
    try:
        return ImageFont.truetype(FONT_BOLD if bold else FONT_REG, size, index=0)
    except OSError:
        return ImageFont.load_default()


def _wrap(draw, text: str, font, max_width: int, max_lines: int = 3) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in str(text):
        if draw.textlength(current + char, font=font) <= max_width:
            current += char
        else:
            if current:
                lines.append(current)
            current = char
            if len(lines) >= max_lines:
                break
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) == max_lines and sum(len(x) for x in lines) < len(str(text)):
        lines[-1] = lines[-1][:-1] + "…"
    return lines


def _fit_font(draw, text: str, max_width: int, size: int, bold: bool = False,
              min_size: int = 14):
    font = _font(size, bold)
    while draw.textlength(text, font=font) > max_width and size > min_size:
        size -= 1
        font = _font(size, bold)
    return font


def _canvas(width: int, height: int):
    Image, ImageDraw, _ImageFont = _pil()
    img = Image.new("RGB", (width, height), BG_TOP)
    draw = ImageDraw.Draw(img)
    for y in range(height):
        t = y / max(1, height - 1)
        draw.line(
            [(0, y), (width, y)],
            fill=tuple(int(BG_TOP[i] * (1 - t) + BG_BOTTOM[i] * t) for i in range(3)),
        )
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.ellipse((-180, -220, 520, 480), fill=(0, 204, 170, 24))
    od.ellipse((width - 380, 80, width + 220, 680), fill=(255, 209, 102, 16))
    od.ellipse((width - 420, height - 460, width + 180, height + 80),
               fill=(255, 143, 163, 14))
    rng = random.Random(11)
    for _ in range(100):
        x = rng.randint(0, width)
        y = rng.randint(0, height)
        r = rng.choice([1, 1, 2])
        od.ellipse((x, y, x + r, y + r), fill=(255, 255, 255, 24))
    img = Image.alpha_composite(img.convert("RGBA"), overlay)
    return img, ImageDraw.Draw(img)


def _header(draw, width: int, title: str, subtitle: str, group_id: int,
            stamp: str) -> None:
    draw.text((70, 58), title, font=_font(54, True), fill=CREAM)
    draw.text((72, 128), subtitle, font=_font(24), fill=(175, 230, 220))
    draw.text((width - 70, 72), f"群 {group_id}", font=_font(24, True),
              fill=GOLD, anchor="ra")
    draw.text((width - 70, 108), stamp, font=_font(18), fill=(160, 210, 202),
              anchor="ra")


def _footer(draw, width: int, height: int, text: str) -> None:
    draw.line([(70, height - 74), (width - 70, height - 74)],
              fill=(80, 150, 140), width=1)
    draw.text((width // 2, height - 42), text, font=_font(17),
              fill=(150, 205, 196), anchor="mm")


def _save(img, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out_path, "PNG", optimize=True)


# ---------- 人物关系图（分组分页） ----------

def _field_value(ent: dict, name: str) -> str:
    item = ent.get("fields", {}).get(name, {})
    if isinstance(item, dict):
        return str(item.get("value") or "").strip()
    return str(item or "").strip()


def relationship_groups(canon: dict) -> list[dict]:
    entities = canon.get("entities", {})
    by_name: dict[str, dict] = {}
    for ent in entities.values():
        by_name[norm_text(ent.get("name"))] = ent
        for alias in ent.get("aliases", []):
            by_name[norm_text(alias)] = ent

    groups: dict[str, dict] = {}
    for ent in entities.values():
        if ent.get("type") != "character":
            continue
        group_name = ""
        for field_name in ("乐队", "势力", "阵营", "组织", "国家", "地区", "所属"):
            group_name = _field_value(ent, field_name)
            if group_name:
                break
        if not group_name:
            for rel in ent.get("relations", []):
                target = by_name.get(norm_text(rel.get("to")))
                if target and target.get("type") in {"faction", "nation"}:
                    group_name = str(target.get("name") or "")
                    break
        group_name = group_name or "其他"
        group = groups.setdefault(group_name, {
            "name": group_name,
            "hub": by_name.get(norm_text(group_name)),
            "members": [],
        })
        group["members"].append(ent)

    result = []
    for group in groups.values():
        group["members"].sort(key=lambda ent: str(ent.get("name") or ""))
        result.append(group)
    result.sort(key=lambda group: (group["name"] == "其他", group["name"]))
    return result


def relationship_needs_paging(canon: dict, max_characters: int = 12) -> bool:
    count = sum(
        1 for ent in canon.get("entities", {}).values()
        if ent.get("type") == "character"
    )
    return count > max_characters


def _draw_group_panel(img, draw, x: int, y: int, group: dict,
                      members: list[dict], label: str) -> None:
    Image, ImageDraw, _ = _pil()
    w, h = 720, 620
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle((x + 7, y + 8, x + w + 7, y + h + 8), radius=24,
                         fill=(0, 12, 11, 50))
    img = Image.alpha_composite(img, shadow)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((x, y, x + w, y + h), radius=24, fill=CREAM)

    hub = group.get("hub")
    hub_name = str((hub or {}).get("name") or group["name"])
    hub_type = "乐队" if hub and hub.get("type") == "faction" and "乐队" in _field_value(hub, "类型") else "势力"
    if not hub:
        hub_type = "未建组"
    draw.text((x + 28, y + 22), label, font=_fit_font(draw, label, 470, 25, True, 15),
              fill=INK)
    draw.rounded_rectangle((x + w - 112, y + 22, x + w - 24, y + 52), radius=13,
                           fill=(0, 204, 170, 32))
    draw.text((x + w - 68, y + 37), hub_type, font=_font(14, True),
              fill=(0, 118, 100), anchor="mm")

    hub_box = (x + 210, y + 78, x + 510, y + 134)
    draw.rounded_rectangle(hub_box, radius=22, fill=(0, 204, 170, 34),
                           outline=ACCENT, width=2)
    hub_font = _fit_font(draw, hub_name, 280, 21, True, 11)
    draw.text((x + 360, y + 106), hub_name, font=hub_font, fill=(0, 100, 86),
              anchor="mm")

    positions = []
    for index, member in enumerate(members[:6]):
        col = index % 2
        row = index // 2
        px = x + 45 + col * 330
        py = y + 205 + row * 72
        positions.append((px, py, member))
        draw.line([(x + 360, y + 136), (px + 150, py + 26)],
                  fill=(0, 160, 138, 90), width=2)

    for index, (px, py, member) in enumerate(positions):
        color = (0, 204, 170) if index % 2 == 0 else (0, 170, 145)
        draw.rounded_rectangle((px, py, px + 300, py + 52), radius=18,
                               fill=(248, 255, 252), outline=color, width=2)
        name = str(member.get("name") or "")
        role = _field_value(member, "定位") or _field_value(member, "身份")
        name_font = _fit_font(draw, name, 190, 18, True, 11)
        draw.text((px + 14, py + 26), name, font=name_font, fill=INK, anchor="lm")
        if role:
            role_font = _fit_font(draw, role, 82, 14, False, 9)
            draw.text((px + 286, py + 26), role, font=role_font, fill=(90, 120, 112),
                      anchor="rm")

    member_names = {norm_text(m.get("name")) for m in members}
    hub_key = norm_text(hub_name)
    inside = []
    outside = []
    for member in members:
        for rel in member.get("relations", []):
            target = norm_text(rel.get("to"))
            text = f"{rel.get('kind', '关系')} → {rel.get('to')}"
            if target in member_names or target == hub_key:
                if rel.get("kind") in ("所属乐队", "成员", "所属组合"):
                    continue
                if text not in inside:
                    inside.append(text)
            else:
                if text not in outside:
                    outside.append(text)

    if inside:
        draw.text((x + 28, y + 500),
                  _wrap(draw, "组内：" + "；".join(inside[:2]), _font(15), 660, 1)[0],
                  font=_font(15), fill=(0, 120, 102))
    if outside:
        draw.text((x + 28, y + 540),
                  _wrap(draw, "外部：" + "；".join(outside[:2]), _font(14), 660, 1)[0],
                  font=_font(14), fill=(130, 100, 90))
    return img, draw


def render_relationship_groups(canon: dict, out_dir: Path, group_id: int,
                              timezone: str = "Asia/Shanghai",
                              title: str = "人物关系图",
                              source: str = "canon.json") -> dict:
    _Image, _ImageDraw, _ = _pil()
    groups = relationship_groups(canon)
    if not groups:
        raise PanelError("还没有人物关系可以画~ 先添加几个角色吧。")

    panels = []
    for group in groups:
        members = group["members"]
        chunks = [members[i:i + 6] for i in range(0, len(members), 6)]
        for index, chunk in enumerate(chunks):
            label = group["name"]
            if len(chunks) > 1:
                label += f"（{index + 1}/{len(chunks)}）"
            panels.append({"group": group, "members": chunk, "label": label})

    pages = [panels[i:i + 4] for i in range(0, len(panels), 4)]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(ZoneInfo(timezone)).strftime("%Y-%m-%d %H:%M")
    paths = []
    total_chars = sum(len(group["members"]) for group in groups)
    for page_index, page in enumerate(pages, 1):
        rows = (len(page) + 1) // 2
        width = 1600
        height = 220 + rows * 620 + max(0, rows - 1) * 24 + 110
        img, draw = _canvas(width, height)
        _header(draw, width, title,
                f"第 {page_index}/{len(pages)} 页 · {len(groups)} 组 / {total_chars} 人",
                group_id, stamp)
        for panel_index, panel in enumerate(page):
            x = 60 + (panel_index % 2) * 744
            y = 220 + (panel_index // 2) * 644
            img, draw = _draw_group_panel(
                img, draw, x, y, panel["group"], panel["members"], panel["label"]
            )
        _footer(draw, width, height,
                f"来自 {source} · 每组最多 6 人，完整分组")
        path = out_dir / f"relationships-groups-{page_index}.png"
        _save(img, path)
        paths.append(str(path))
    return {
        "pages": paths,
        "groups": len(groups),
        "characters": total_chars,
        "page_count": len(pages),
    }


# ---------- 面包坊 ----------

def _stat_bar(draw, x: int, y: int, width: int, value: int,
              color: tuple[int, int, int], invert: bool = False) -> None:
    draw.rounded_rectangle((x, y, x + width, y + 16), radius=8,
                           fill=(226, 238, 232))
    ratio = max(0.0, min(1.0, value / 100.0))
    fill_ratio = (1.0 - ratio) if invert else ratio
    fill_width = max(4, int(width * fill_ratio))
    draw.rounded_rectangle((x, y, x + fill_width, y + 16), radius=8, fill=color)


def render_bakery(stats: dict, wallet: dict, bakeries: list[dict],
                  out_path: Path, group_id: int, timezone: str = "Asia/Shanghai",
                  infinite: bool = False, currency: str = "摩卡币") -> dict:
    if not bakeries:
        raise PanelError("面包坊还没有面包~")
    width, height = 1500, 1500
    img, draw = _canvas(width, height)
    stamp = datetime.now(ZoneInfo(timezone)).strftime("%Y-%m-%d %H:%M")
    _header(draw, width, "摩卡面包坊",
            f"饱腹 {stats['hunger']} / 困意 {stats['sleepiness']} / 心情 {stats['mood']}",
            group_id, stamp)

    draw.rounded_rectangle((60, 178, 1440, 345), radius=24, fill=CREAM)
    labels = [
        ("饱腹", stats["hunger"], (0, 190, 150), False),
        ("困意（越低越精神）", stats["sleepiness"], (255, 143, 163), True),
        ("心情", stats["mood"], (255, 180, 90), False),
    ]
    for index, (label, value, color, invert) in enumerate(labels):
        x = 92 + index * 450
        draw.text((x, 198), label, font=_font(18, True), fill=INK)
        draw.text((x + 350, 198), f"{value}/100", font=_font(18, True),
                  fill=color, anchor="ra")
        _stat_bar(draw, x, 232, 350, value, color, invert)
    if infinite:
        money = f"钱包：{currency} ∞（无限货币）"
    else:
        money = f"钱包：{currency} {wallet.get('coins', 0)}"
    draw.text((92, 286), money, font=_font(22, True), fill=(0, 120, 100))
    draw.text((1390, 286), "发「买面包 <编号>」", font=_font(17),
              fill=MUTED, anchor="ra")

    for index, bakery in enumerate(bakeries[:4]):
        x = 60 + (index % 2) * 715
        y = 380 + (index // 2) * 520
        w, h = 680, 490
        draw.rounded_rectangle((x + 6, y + 7, x + w + 6, y + h + 7), radius=22,
                               fill=(0, 14, 12))
        draw.rounded_rectangle((x, y, x + w, y + h), radius=22, fill=CREAM)
        draw.text((x + 28, y + 20), bakery["name"], font=_font(26, True),
                  fill=INK)
        draw.text((x + 28, y + 58), bakery.get("tag", ""), font=_font(15),
                  fill=MUTED)
        for row, bread in enumerate(bakery["breads"]):
            by = y + 102 + row * 116
            draw.rounded_rectangle((x + 22, by, x + w - 22, by + 104), radius=16,
                                   fill=(248, 255, 252), outline=(208, 232, 223), width=1)
            draw.rounded_rectangle((x + 38, by + 18, x + 82, by + 58), radius=12,
                                   fill=(0, 204, 170, 38))
            draw.text((x + 60, by + 38), f"#{bread['id']}", font=_font(17, True),
                      fill=(0, 120, 100), anchor="mm")
            draw.text((x + 98, by + 14), bread["name"],
                      font=_font(20, True), fill=INK)
            draw.text((x + w - 34, by + 16), f"{bread['price']} {currency}",
                      font=_font(18, True), fill=(180, 105, 55), anchor="ra")
            draw.text(
                (x + 98, by + 57),
                f"饱腹 +{bread['hunger']}  心情 +{bread['mood']}  困意 +{bread.get('sleepiness', 0)}",
                font=_font(15), fill=(90, 125, 114),
            )
    _footer(draw, width, height,
            "打工赚摩卡币 · 买面包喂摩卡 · 管理员可开无限货币")
    _save(img, out_path)
    return {"path": str(out_path)}



def render_relationship(canon: dict, out_path: Path, group_id: int,
                        timezone: str = "Asia/Shanghai",
                        title: str = "人物关系图",
                        source: str = "canon.json") -> dict:
    _Image, _ImageDraw, _ = _pil()
    entities = canon.get("entities", {})
    characters = [
        (key, ent) for key, ent in entities.items()
        if ent.get("type") == "character"
    ]
    if len(characters) < 2:
        raise PanelError("人物还不够画关系图，先用「添加」记几个角色吧~")

    by_name: dict[str, str] = {}
    for key, ent in entities.items():
        if ent.get("type") not in {"character", "faction"}:
            continue
        by_name[norm_text(ent.get("name"))] = key
        for alias in ent.get("aliases", []):
            by_name[norm_text(alias)] = key

    all_edges = []
    missing = 0
    node_map = {key: ent for key, ent in characters}
    for key, ent in characters:
        for rel in ent.get("relations", []):
            target = by_name.get(norm_text(rel.get("to")))
            if target and target != key:
                target_ent = entities.get(target)
                if target_ent and target_ent.get("type") in {"character", "faction"}:
                    all_edges.append((key, target, str(rel.get("kind") or "关系")))
                    node_map[target] = target_ent
                else:
                    missing += 1
            elif not target:
                missing += 1

    if not all_edges:
        raise PanelError("还没有明确的人物/乐队关系，先记几条「A 是 B 的师父」这类设定吧~")

    # 双向的同一关系只画一条，避免两根线/两个标签叠在一起。
    edges = []
    seen_edges = set()
    for src, dst, kind in all_edges:
        edge_key = (min(src, dst), max(src, dst), str(kind))
        if edge_key in seen_edges:
            continue
        seen_edges.add(edge_key)
        edges.append((src, dst, kind))

    degree = Counter()
    for src, dst, _kind in edges:
        degree[src] += 1
        degree[dst] += 1
    limit = 30
    if len(node_map) > limit:
        factions = [key for key, ent in node_map.items() if ent.get("type") == "faction"]
        factions.sort(key=lambda key: (-degree[key], key))
        selected = set(factions[:limit])
        # 每个入选乐队至少保留一个角色，避免出现完全孤立的乐队节点。
        for band_key in factions[:limit]:
            candidates = []
            for key, ent in node_map.items():
                if ent.get("type") != "character":
                    continue
                band_name = str(ent.get("fields", {}).get("乐队", {}).get("value", ""))
                if by_name.get(norm_text(band_name)) == band_key:
                    candidates.append(key)
            candidates.sort(key=lambda key: (-degree[key], key))
            if candidates and len(selected) < limit:
                selected.add(candidates[0])
        for key, _ in sorted(node_map.items(),
                             key=lambda item: (-degree[item[0]], item[0])):
            if len(selected) >= limit:
                break
            selected.add(key)
        chosen = selected
    else:
        chosen = set(node_map)
    nodes = [(key, ent) for key, ent in node_map.items() if key in chosen]
    edges = [edge for edge in edges if edge[0] in chosen and edge[1] in chosen]

    count = len(nodes)
    people_count = sum(1 for _, ent in nodes if ent.get("type") == "character")
    faction_count = count - people_count
    width = 1800 if count > 24 else 1600
    height = 1320 if count <= 3 else (1800 if count > 24 else 1720)
    img, draw = _canvas(width, height)
    stamp = datetime.now(ZoneInfo(timezone)).strftime("%Y-%m-%d %H:%M")
    subtitle = f"{people_count} 位人物 · {faction_count} 个乐队/势力 · {len(edges)} 条关系"
    if missing:
        subtitle += f" · 另有 {missing} 条目标未收录"
    _header(draw, width, title, subtitle, group_id, stamp)

    cx, cy = width // 2, 700 if count <= 3 else 880
    positions = {}
    faction_nodes = [(key, ent) for key, ent in nodes if ent.get("type") == "faction"]
    people_nodes = [(key, ent) for key, ent in nodes if ent.get("type") == "character"]
    if count == 1:
        positions[nodes[0][0]] = (cx, cy)
    elif faction_nodes:
        # 乐队/势力放外圈，角色在内圈均匀排开；每条成员线指向自己的乐队。
        factions = sorted(faction_nodes, key=lambda item: item[1].get("name", ""))
        band_order = {key: index for index, (key, _) in enumerate(factions)}

        def band_index(key: str) -> int:
            ent = node_map.get(key, {})
            band_name = str(ent.get("fields", {}).get("乐队", {}).get("value", ""))
            band_key = by_name.get(norm_text(band_name))
            return band_order.get(band_key, 999)

        ordered_people = sorted(
            people_nodes,
            key=lambda item: (band_index(item[0]), item[1].get("name", "")),
        )
        for index, (key, _ent) in enumerate(factions):
            angle = -math.pi / 2 + 2 * math.pi * index / len(factions)
            positions[key] = (
                int(cx + 700 * math.cos(angle)),
                int(cy + 700 * 0.86 * math.sin(angle)),
            )
        for index, (key, _ent) in enumerate(ordered_people):
            angle = -math.pi / 2 + 2 * math.pi * index / max(1, len(ordered_people))
            positions[key] = (
                int(cx + 470 * math.cos(angle)),
                int(cy + 470 * 0.86 * math.sin(angle)),
            )
    else:
        radius = 250 if count <= 3 else 650
        for index, (key, _ent) in enumerate(nodes):
            angle = -math.pi / 2 + 2 * math.pi * index / count
            positions[key] = (
                int(cx + radius * math.cos(angle)),
                int(cy + radius * 0.86 * math.sin(angle)),
            )

    # 先画边
    edge_font = _font(16)
    node_by_key = dict(nodes)
    for src, dst, kind in edges:
        x1, y1 = positions[src]
        x2, y2 = positions[dst]
        dx, dy = x2 - x1, y2 - y1
        length = max(1.0, math.hypot(dx, dy))
        ux, uy = dx / length, dy / length
        src_faction = node_by_key[src].get("type") == "faction"
        dst_faction = node_by_key[dst].get("type") == "faction"
        r1 = 66 if src_faction else (46 if faction_nodes else 60)
        r2 = 66 if dst_faction else (46 if faction_nodes else 60)
        start = (x1 + ux * (r1 + 4), y1 + uy * (r1 + 4))
        end = (x2 - ux * (r2 + 6), y2 - uy * (r2 + 6))
        draw.line([start, end], fill=(0, 160, 138, 130), width=2)
        ax, ay = end
        px, py = -uy, ux
        draw.polygon([
            (ax, ay),
            (ax - ux * 14 + px * 6, ay - uy * 14 + py * 6),
            (ax - ux * 14 - px * 6, ay - uy * 14 - py * 6),
        ], fill=(0, 160, 138, 210))
        if len(edges) <= 36 and kind not in ("所属乐队", "成员", "所属组合"):
            mx, my = (start[0] + end[0]) / 2, (start[1] + end[1]) / 2
            label = str(kind)[:8]
            tw = draw.textlength(label, font=edge_font)
            bx = mx + px * 14
            by = my + py * 14
            draw.rounded_rectangle(
                (bx - tw / 2 - 6, by - 12, bx + tw / 2 + 6, by + 12),
                radius=9, fill=(255, 253, 246),
            )
            draw.text((bx, by), label, font=edge_font, fill=(0, 112, 96),
                      anchor="mm")

    # 再画节点
    for index, (key, ent) in enumerate(nodes):
        x, y = positions[key]
        is_faction = ent.get("type") == "faction"
        color = TYPE_COLORS["faction"] if is_faction else TYPE_COLORS["character"]
        r = 66 if is_faction else (46 if faction_nodes else 60)
        draw.ellipse((x - r + 3, y - r + 9, x + r + 3, y + r + 9),
                     fill=(0, 0, 0, 55))
        draw.ellipse((x - r, y - r, x + r, y + r), fill=CREAM)
        draw.ellipse((x - r, y - r, x + r, y + r), outline=color, width=5)
        name = str(ent.get("name") or key)
        font = _fit_font(draw, name, r * 2 - 26, 20 if is_faction else 18, True, 9)
        lines = _wrap(draw, name, font, r * 2 - 16, 2)
        start_y = y - (len(lines) - 1) * 12 - 2
        for line_index, line in enumerate(lines):
            draw.text((x, start_y + line_index * 23), line, font=font,
                      fill=INK, anchor="mm")
        label = "人物"
        if is_faction:
            type_field = ent.get("fields", {}).get("类型", {})
            label = "乐队" if "乐队" in str(type_field.get("value", "")) else "势力"
        draw.text((x, y + r - 13), label, font=_font(13),
                  fill=(0, 120, 102) if not is_faction else (155, 75, 95),
                  anchor="mm")

    # 图例/说明
    legend_y = height - 140
    draw.rounded_rectangle((70, legend_y, width - 70, legend_y + 64),
                           radius=22, fill=(0, 204, 170, 26))
    draw.text((100, legend_y + 22),
              "箭头 A → B 表示 A 对 B 的关系；只画明确写过的关系。",
              font=_font(20), fill=(210, 244, 236))
    draw.text((100, legend_y + 48),
              f"共 {len(entities)} 个条目；关系图最多显示 30 个节点（人物 + 乐队/势力）。",
              font=_font(16), fill=(160, 210, 202))
    _footer(draw, width, height, f"来自 {source} · 摩卡整理屋")
    _save(img, out_path)
    return {"people": people_count, "edges": len(edges), "missing": missing,
            "nodes": count, "path": str(out_path)}


# ---------- 设定统计面板 ----------

def render_dashboard(canon: dict, out_path: Path, group_id: int, stats: dict,
                     timezone: str = "Asia/Shanghai",
                     title: str = "设定统计面板",
                     source: str = "canon.json") -> dict:
    _Image, _ImageDraw, _ = _pil()
    width, height = 1200, 1620
    img, draw = _canvas(width, height)
    stamp = datetime.now(ZoneInfo(timezone)).strftime("%Y-%m-%d %H:%M")
    _header(draw, width, title, "设定库 · 待办 · token 使用情况",
            group_id, stamp)

    entities = canon.get("entities", {})
    by_type = Counter(ent.get("type", "other") for ent in entities.values())
    conflicts = list(canon.get("conflicts", {}).values())
    open_conf = [c for c in conflicts if c.get("status") == "open"]
    resolved_conf = [c for c in conflicts if c.get("status") != "open"]
    questions = open_questions(canon)

    cards = [
        ("总条目", len(entities), "个", ACCENT),
        ("人物", by_type.get("character", 0), "位", (0, 204, 170)),
        ("势力/国家", by_type.get("faction", 0) + by_type.get("nation", 0), "个", PINK),
        ("地点/地区", by_type.get("location", 0) + by_type.get("region", 0), "个", BLUE),
        ("待整合素材", stats.get("pending", 0), "条", GOLD),
        ("待裁决冲突", len(open_conf), "条", (255, 120, 120)),
    ]
    card_w, card_h = 330, 156
    for index, (label, value, unit, color) in enumerate(cards):
        col = index % 3
        row = index // 3
        x = 70 + col * 360
        y = 220 + row * 178
        draw.rounded_rectangle((x, y, x + card_w, y + card_h), radius=24,
                               fill=CREAM)
        draw.rounded_rectangle((x, y, x + 10, y + card_h), radius=5, fill=color)
        draw.text((x + 30, y + 24), label, font=_font(20), fill=MUTED)
        draw.text((x + 30, y + 60), str(value), font=_font(54, True), fill=INK)
        draw.text((x + 30 + draw.textlength(str(value), font=_font(54, True)) + 8,
                   y + 88), unit, font=_font(18), fill=MUTED)

    # 类型分布
    chart_x, chart_y, chart_w, chart_h = 70, 600, 1060, 430
    draw.rounded_rectangle((chart_x, chart_y, chart_x + chart_w, chart_y + chart_h),
                           radius=26, fill=CREAM)
    draw.text((chart_x + 30, chart_y + 24), "条目类型分布",
              font=_font(30, True), fill=INK)
    draw.text((chart_x + chart_w - 30, chart_y + 32), f"共 {len(entities)} 条",
              font=_font(18), fill=MUTED, anchor="ra")
    rows = [(etype, by_type.get(etype, 0)) for etype in TYPE_ORDER
            if by_type.get(etype, 0)]
    if not rows:
        draw.text((chart_x + 30, chart_y + 120), "设定库还是空的，先「添加」几条吧~",
                  font=_font(24), fill=MUTED)
    max_value = max((count for _, count in rows), default=1)
    bar_x, bar_top, bar_w = chart_x + 170, chart_y + 88, 700
    for index, (etype, count) in enumerate(rows[:10]):
        y = bar_top + index * 32
        color = TYPE_COLORS.get(etype, (180, 180, 180))
        draw.text((chart_x + 30, y + 2), TYPE_LABELS.get(etype, etype),
                  font=_font(18), fill=INK, anchor="lm")
        draw.rounded_rectangle((bar_x, y - 10, bar_x + bar_w, y + 12),
                               radius=10, fill=(232, 245, 241))
        filled = int(bar_w * count / max_value) if max_value else 0
        if filled > 0:
            draw.rounded_rectangle((bar_x, y - 10, bar_x + max(18, filled), y + 12),
                                   radius=10, fill=color)
        draw.text((bar_x + bar_w + 16, y + 2), str(count), font=_font(18, True),
                  fill=INK, anchor="lm")

    # 待办 + 状态
    box_y = 1070
    draw.rounded_rectangle((70, box_y, 575, box_y + 300), radius=26, fill=CREAM)
    draw.text((100, box_y + 26), "待办", font=_font(30, True), fill=INK)
    todo = [
        ("待裁决冲突", len(open_conf), "条"),
        ("待补完问题", len(questions), "条"),
        ("待整合素材", stats.get("pending", 0), "条"),
        ("已裁决冲突", len(resolved_conf), "条"),
    ]
    for index, (label, value, unit) in enumerate(todo):
        y = box_y + 78 + index * 48
        draw.text((100, y), label, font=_font(20), fill=MUTED, anchor="lm")
        draw.text((520, y), f"{value} {unit}", font=_font(24, True),
                  fill=INK, anchor="rm")

    draw.rounded_rectangle((625, box_y, 1130, box_y + 300), radius=26, fill=CREAM)
    draw.text((655, box_y + 26), "运行状态", font=_font(30, True), fill=INK)
    chat_in = stats.get("chat_input", 0)
    chat_out = stats.get("chat_output", 0)
    status = [
        ("今日聊天 token", f"{chat_in + chat_out}"),
        ("素材总数", f"{stats.get('raw_total', 0)}"),
        ("快照数量", f"{stats.get('snapshots', 0)}"),
        ("设定更新时间", str(stats.get("canon_updated") or "还没整理")[:16]),
    ]
    for index, (label, value) in enumerate(status):
        y = box_y + 78 + index * 48
        draw.text((655, y), label, font=_font(20), fill=MUTED, anchor="lm")
        draw.text((1095, y), value, font=_font(20, True), fill=INK, anchor="rm")

    _footer(draw, width, height,
            f"来自 {source} / state.json · 数字是当前快照")
    _save(img, out_path)
    return {"path": str(out_path), "total": len(entities)}


# ---------- 国家/地区设定图 ----------

def render_region_atlas(canon: dict, out_path: Path, group_id: int,
                        timezone: str = "Asia/Shanghai",
                        title: str = "国家 / 地区设定图",
                        source: str = "canon.json") -> dict:
    _Image, _ImageDraw, _ = _pil()
    entities = list(canon.get("entities", {}).values())
    regions = [ent for ent in entities if ent.get("type") in {"nation", "region", "location"}]
    include_factions = len(regions) < 4
    if include_factions:
        regions += [ent for ent in entities if ent.get("type") == "faction"]
    if not regions:
        raise PanelError("还没有国家/地区相关设定，先添加几条「诺伦联邦是…」这样的内容吧~")
    regions = regions[:12]

    width = 1200
    # 先估算高度：两列卡片
    card_w = 500
    rows = (len(regions) + 1) // 2
    card_h = 300
    height = 300 + rows * (card_h + 28) + 150
    img, draw = _canvas(width, height)
    stamp = datetime.now(ZoneInfo(timezone)).strftime("%Y-%m-%d %H:%M")
    _header(draw, width, title, "根据设定库生成的资料卡 · 不是实际地图",
            group_id, stamp)

    # 抽象地图底纹
    for index in range(4):
        color = (0, 204, 170, 16 + index * 4)
        draw.arc((80 - index * 30, 190 - index * 18, 760 + index * 40, 650 + index * 30),
                 200, 340, fill=color, width=2)
        draw.arc((420 - index * 20, 180 - index * 20, 1180 + index * 30, 700 + index * 40),
                 20, 160, fill=color, width=2)

    for index, ent in enumerate(regions):
        col = index % 2
        row = index // 2
        x = 70 + col * 560
        y = 300 + row * (card_h + 28)
        etype = ent.get("type", "other")
        color = TYPE_COLORS.get(etype, (180, 180, 180))
        draw.rounded_rectangle((x, y, x + card_w, y + card_h), radius=28, fill=CREAM)
        draw.rounded_rectangle((x, y, x + 12, y + card_h), radius=6, fill=color)
        name = str(ent.get("name") or "未命名")
        name_font = _fit_font(draw, name, 330, 30, True, 18)
        draw.text((x + 34, y + 26), name, font=name_font, fill=INK)
        label = TYPE_LABELS.get(etype, etype)
        tw = draw.textlength(label, font=_font(16, True))
        draw.rounded_rectangle((x + card_w - tw - 52, y + 26,
                                x + card_w - 24, y + 58),
                               radius=14, fill=(0, 204, 170, 34))
        draw.text((x + card_w - 38 - tw / 2, y + 42), label,
                  font=_font(16, True), fill=(0, 120, 102), anchor="mm")

        fields = list(ent.get("fields", {}).items())[:4]
        field_y = y + 82
        for field_name, item in fields:
            value = str(item.get("value") if isinstance(item, dict) else item)
            line = f"{field_name}：{value}"
            lines = _wrap(draw, line, _font(18), card_w - 64, 2)
            for line_text in lines:
                draw.text((x + 34, field_y), line_text, font=_font(18), fill=MUTED)
                field_y += 26
            field_y += 4

        rels = ent.get("relations", [])[:2]
        if rels:
            rel_text = "；".join(
                f"{rel.get('kind', '关系')} → {rel.get('to')}" for rel in rels
            )
            rel_text = _wrap(draw, "关系：" + rel_text, _font(16), card_w - 68, 1)[0]
            draw.text((x + 34, y + card_h - 42), rel_text,
                      font=_font(16), fill=(0, 120, 102))

    # 待补完只放在页脚，避免卡片底部被长问题撑爆
    questions = open_questions(canon)
    footer = f"来自 {source} · 资料卡不是实际地理坐标"
    if questions:
        footer += f" · 另有 {len(questions)} 条地区问题待补完"
    _footer(draw, width, height, footer)
    _save(img, out_path)
    return {"path": str(out_path), "regions": len(regions)}
