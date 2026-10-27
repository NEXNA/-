"""把已经混在主 canon 里的 BanG Dream! 资料拆到 bandori.json。

用法：
    python tools/split_bandori.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from bot.canon import entity_key  # noqa: E402
from bot.config import Config  # noqa: E402
from bot.store import GroupStore  # noqa: E402
from bot.util import now_iso  # noqa: E402
from seed_bandori import BANDS  # noqa: E402


def seeded_keys() -> set[str]:
    keys = set()
    for band, members in BANDS.items():
        keys.add(entity_key("faction", band))
        for name, *_ in members:
            keys.add(entity_key("character", name))
    keys.add(entity_key("faction", "sumimi"))
    keys.add(entity_key("location", "山吹烘焙坊"))
    return keys


def main() -> int:
    cfg = Config.load(ROOT)
    store = GroupStore(cfg.data_dir, 123456789, cfg.timezone)
    main_canon = store.load_canon()
    bandori = store.load_bandori()
    keys = seeded_keys()

    store.snapshot(main_canon)
    moved = 0
    for key in sorted(keys):
        ent = main_canon.get("entities", {}).pop(key, None)
        if ent is not None:
            bandori.setdefault("entities", {})[key] = ent
            moved += 1

    bandori.setdefault("version", 1)
    bandori.setdefault("conflicts", {})
    bandori.setdefault("questions", {})
    bandori.setdefault("meta", {"conflict_seq": 0, "question_seq": 0})
    bandori["updated_at"] = now_iso()

    main_canon["updated_at"] = now_iso()
    store.save_canon(main_canon)
    store.save_bandori(bandori)
    store.append_changelog("分离 BanG Dream! 资料", [
        f"- 从主 canon 移出 {moved} 个邦多利条目到 bandori.json",
        f"- 主 canon 剩余 {len(main_canon.get('entities', {}))} 条",
        f"- 邦多利库 {len(bandori.get('entities', {}))} 条",
    ])
    print(f"移出 {moved} 条")
    print(f"主世界 canon：{len(main_canon.get('entities', {}))} 条")
    print(f"BanG Dream! bandori.json：{len(bandori.get('entities', {}))} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
