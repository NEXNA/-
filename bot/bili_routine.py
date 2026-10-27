"""Persistent settings for Mocha's Bilibili browsing routine."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

DEFAULT_PREFERENCES = [
    "BanG Dream",
    "Afterglow",
    "青叶摩卡",
    "邦多利",
    "动漫 音乐",
    "咖啡 面包",
    "吉他 日常",
]


class BiliRoutineStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._data = self._load()

    def _defaults(self) -> dict:
        return {
            "preferences": list(DEFAULT_PREFERENCES),
            "schedule": {"enabled": False, "time": "21:30", "count": 2},
            "share_view_enabled": True,
            "last_run_date": "",
            "comments": [],
            "seen_replies": [],
        }

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return self._defaults()
        base = self._defaults()
        if isinstance(data, dict):
            base.update(data)
        if not isinstance(base.get("preferences"), list):
            base["preferences"] = list(DEFAULT_PREFERENCES)
        if not isinstance(base.get("schedule"), dict):
            base["schedule"] = self._defaults()["schedule"]
        if not isinstance(base.get("comments"), list):
            base["comments"] = []
        if not isinstance(base.get("seen_replies"), list):
            base["seen_replies"] = []
        return base

    def _save(self) -> None:
        temp = self.path.with_suffix(".tmp")
        temp.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp.replace(self.path)

    def preferences(self) -> list[str]:
        return list(self._data.get("preferences") or DEFAULT_PREFERENCES)

    def set_preferences(self, values: list[str]) -> list[str]:
        cleaned = []
        for value in values:
            item = " ".join(str(value or "").split()).strip()
            if item and item not in cleaned:
                cleaned.append(item[:30])
        if not cleaned:
            cleaned = list(DEFAULT_PREFERENCES)
        cleaned = cleaned[:10]
        with self._lock:
            self._data["preferences"] = cleaned
            self._save()
        return cleaned

    def schedule(self) -> dict:
        return dict(self._data.get("schedule") or {})

    def share_view_enabled(self) -> bool:
        return bool(self._data.get("share_view_enabled", True))

    def set_share_view(self, enabled: bool) -> bool:
        with self._lock:
            self._data["share_view_enabled"] = bool(enabled)
            self._save()
        return bool(enabled)

    def set_schedule(self, time_text: str, count: int) -> dict:
        schedule = {"enabled": True, "time": time_text, "count": int(count)}
        with self._lock:
            self._data["schedule"] = schedule
            self._save()
        return schedule

    def disable_schedule(self) -> dict:
        schedule = self.schedule()
        schedule["enabled"] = False
        with self._lock:
            self._data["schedule"] = schedule
            self._save()
        return schedule

    def last_run_date(self) -> str:
        return str(self._data.get("last_run_date") or "")

    def mark_run(self, date_text: str) -> None:
        with self._lock:
            self._data["last_run_date"] = date_text
            self._save()

    def comments(self) -> list[dict]:
        return list(self._data.get("comments") or [])

    def add_comment(self, bvid: str, rpid: int, title: str) -> None:
        record = {
            "bvid": bvid,
            "rpid": int(rpid),
            "title": title,
            "created": int(time.time()),
            "my_rpids": [int(rpid)],
        }
        with self._lock:
            items = self._data.setdefault("comments", [])
            items = [item for item in items if int(item.get("rpid") or 0) != int(rpid)]
            items.insert(0, record)
            self._data["comments"] = items[:80]
            self._save()

    def add_my_reply(self, root_rpid: int, reply_rpid: int) -> None:
        with self._lock:
            for item in self._data.get("comments") or []:
                if int(item.get("rpid") or 0) == int(root_rpid):
                    rpids = item.setdefault("my_rpids", [int(root_rpid)])
                    if int(reply_rpid) not in rpids:
                        rpids.append(int(reply_rpid))
                    self._save()
                    return

    def seen_reply(self, rpid: int) -> bool:
        return str(rpid) in {str(x) for x in self._data.get("seen_replies") or []}

    def mark_reply(self, rpid: int) -> None:
        with self._lock:
            items = self._data.setdefault("seen_replies", [])
            if str(rpid) not in {str(x) for x in items}:
                items.append(str(rpid))
                self._data["seen_replies"] = items[-2000:]
                self._save()
