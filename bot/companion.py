"""长期记忆、关系、提醒。

这些是产品化能力的最小版本：JSON 持久化、按群隔离、可删除。
"""

from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .util import atomic_write_json, now_iso, norm_text


class MemoryStore:
    def __init__(self, data_root: Path, group_id: int, timezone: str = "Asia/Shanghai"):
        self.group_id = int(group_id)
        self.timezone = timezone
        folder = Path(data_root) / (str(group_id) if group_id else "_private")
        folder.mkdir(parents=True, exist_ok=True)
        self.path = folder / "memory.json"
        self._lock = threading.RLock()

    def _load(self) -> dict:
        if not self.path.exists():
            return {"version": 1, "next_id": 1, "items": []}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return {"version": 1, "next_id": 1, "items": []}
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            return {"version": 1, "next_id": 1, "items": []}
        data.setdefault("next_id", len(data["items"]) + 1)
        return data

    def _save(self, data: dict) -> None:
        atomic_write_json(self.path, data)

    def add(self, user_id: int, nick: str, text: str, kind: str = "fact",
            source: str = "manual") -> dict | None:
        value = " ".join(str(text or "").split()).strip()
        if len(value) < 2:
            return None
        value = value[:500]
        with self._lock:
            data = self._load()
            normalized = norm_text(value)
            for item in data["items"]:
                if int(item.get("uid", 0)) == int(user_id) and norm_text(item.get("text")) == normalized:
                    return None
            item = {
                "id": int(data["next_id"]),
                "uid": int(user_id),
                "nick": str(nick or user_id),
                "text": value,
                "kind": kind,
                "source": source,
                "at": now_iso(self.timezone),
            }
            data["next_id"] = item["id"] + 1
            data["items"].append(item)
            data["items"] = data["items"][-500:]
            self._save(data)
            return item

    def list(self, user_id: int | None = None, limit: int = 20) -> list[dict]:
        with self._lock:
            items = list(self._load()["items"])
        if user_id is not None:
            items = [x for x in items if int(x.get("uid", 0)) == int(user_id)]
        return items[-max(1, limit):]

    def relevant(self, user_id: int, query: str, limit: int = 6) -> list[dict]:
        with self._lock:
            items = [x for x in self._load()["items"]
                     if int(x.get("uid", 0)) == int(user_id)]
        if not items:
            return []
        chars = set(norm_text(query or ""))
        scored = []
        for index, item in enumerate(items):
            text = norm_text(item.get("text"))
            score = len(chars & set(text)) if chars else 0
            scored.append((score, index, item))
        scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
        return [row[2] for row in scored[:max(1, limit)]]

    def forget(self, user_id: int, keyword: str | None = None) -> int:
        with self._lock:
            data = self._load()
            before = len(data["items"])
            if keyword:
                target = norm_text(keyword)
                data["items"] = [
                    x for x in data["items"]
                    if not (int(x.get("uid", 0)) == int(user_id)
                            and target in norm_text(x.get("text")))
                ]
            else:
                data["items"] = [
                    x for x in data["items"]
                    if int(x.get("uid", 0)) != int(user_id)
                ]
            removed = before - len(data["items"])
            if removed:
                self._save(data)
            return removed

    def clear(self) -> None:
        with self._lock:
            self._save({"version": 1, "next_id": 1, "items": []})

    def count(self) -> int:
        with self._lock:
            return len(self._load()["items"])


class ProfileStore:
    """跨群、跨私聊保存“关于这个人”的设定。"""

    def __init__(self, data_root: Path, timezone: str = "Asia/Shanghai"):
        self.timezone = timezone
        self.path = Path(data_root) / "profiles.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _load(self) -> dict:
        if not self.path.exists():
            return {"version": 1, "users": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return {"version": 1, "users": {}}
        if not isinstance(data, dict) or not isinstance(data.get("users"), dict):
            return {"version": 1, "users": {}}
        return data

    def _save(self, data: dict) -> None:
        atomic_write_json(self.path, data)

    def add(self, user_id: int, nick: str, text: str,
            source: str = "manual") -> dict | None:
        value = " ".join(str(text or "").split()).strip()
        if len(value) < 2:
            return None
        value = value[:500]
        with self._lock:
            data = self._load()
            key = str(int(user_id))
            user = data["users"].setdefault(
                key, {"uid": int(user_id), "nick": str(nick or user_id), "items": []},
            )
            user["nick"] = str(nick or user.get("nick") or user_id)
            normalized = norm_text(value)
            for item in user["items"]:
                if norm_text(item.get("text")) == normalized:
                    return None
            item = {
                "id": max((int(x.get("id", 0)) for x in user["items"]), default=0) + 1,
                "text": value,
                "source": source,
                "at": now_iso(self.timezone),
            }
            user["items"].append(item)
            user["items"] = user["items"][-100:]
            self._save(data)
            return item

    def list(self, user_id: int, limit: int = 100) -> list[dict]:
        with self._lock:
            items = list(self._load()["users"].get(str(int(user_id)), {}).get("items", []))
        return items[-max(1, limit):]

    def forget(self, user_id: int, keyword: str | None = None) -> int:
        with self._lock:
            data = self._load()
            key = str(int(user_id))
            user = data["users"].get(key)
            if not user:
                return 0
            before = len(user["items"])
            if keyword:
                target = norm_text(keyword)
                user["items"] = [
                    x for x in user["items"] if target not in norm_text(x.get("text"))
                ]
            else:
                user["items"] = []
            removed = before - len(user["items"])
            if removed:
                self._save(data)
            return removed

    def context(self, user_id: int, nick: str = "") -> str:
        items = self.list(user_id, 12)
        if not items:
            return ""
        lines = "\n".join(f"- {item.get('text', '')}" for item in items)
        return f"【{nick or user_id} 的长期设定（跨群）】\n{lines}"


class ReminderStore:
    def __init__(self, data_root: Path, timezone: str = "Asia/Shanghai"):
        self.timezone = timezone
        self.path = Path(data_root) / "reminders.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _load(self) -> dict:
        if not self.path.exists():
            return {"version": 1, "next_id": 1, "items": []}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return {"version": 1, "next_id": 1, "items": []}
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            return {"version": 1, "next_id": 1, "items": []}
        data.setdefault("next_id", len(data["items"]) + 1)
        return data

    def _save(self, data: dict) -> None:
        atomic_write_json(self.path, data)

    def add(self, owner_id: int, target_type: str, target_id: int,
            text: str, due_at: float, nick: str = "") -> dict:
        with self._lock:
            data = self._load()
            item = {
                "id": int(data["next_id"]),
                "owner": int(owner_id),
                "nick": str(nick or owner_id),
                "target_type": target_type,
                "target_id": int(target_id),
                "text": str(text or "")[:300],
                "due_at": float(due_at),
                "created_at": now_iso(self.timezone),
                "done": False,
            }
            data["next_id"] = item["id"] + 1
            data["items"].append(item)
            self._save(data)
            return item

    def list(self, owner_id: int | None = None, include_done: bool = False) -> list[dict]:
        with self._lock:
            items = list(self._load()["items"])
        if owner_id is not None:
            items = [x for x in items if int(x.get("owner", 0)) == int(owner_id)]
        if not include_done:
            items = [x for x in items if not x.get("done")]
        items.sort(key=lambda x: float(x.get("due_at", 0)))
        return items

    def cancel(self, reminder_id: int, owner_id: int) -> bool:
        with self._lock:
            data = self._load()
            for item in data["items"]:
                if (int(item.get("id", 0)) == int(reminder_id)
                        and int(item.get("owner", 0)) == int(owner_id)
                        and not item.get("done")):
                    item["done"] = True
                    self._save(data)
                    return True
            return False

    def due(self, now: float | None = None) -> list[dict]:
        current = time.time() if now is None else now
        with self._lock:
            data = self._load()
            items = [x for x in data["items"]
                     if not x.get("done") and float(x.get("due_at", 0)) <= current]
            for item in items:
                item["done"] = True
            if items:
                self._save(data)
            return items


def parse_reminder_time(text: str, timezone: str = "Asia/Shanghai") -> float | None:
    """支持「30分钟」「2小时」「今天 18:00」「明天 09:00」「2026-10-22 09:00」。"""
    value = " ".join(str(text or "").split()).strip()
    if not value:
        return None
    now = datetime.now(ZoneInfo(timezone))
    match = re.search(r"(\d{1,4})\s*(分钟|分|小时|钟头)", value)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        seconds = amount * (3600 if unit in ("小时", "钟头") else 60)
        return time.time() + seconds
    match = re.search(r"(今天|明天|后天)\s*(\d{1,2})[:：](\d{2})", value)
    if match:
        day_offset = {"今天": 0, "明天": 1, "后天": 2}[match.group(1)]
        target = (now + timedelta(days=day_offset)).replace(
            hour=int(match.group(2)), minute=int(match.group(3)),
            second=0, microsecond=0,
        )
        if day_offset == 0 and target <= now:
            target += timedelta(days=1)
        return target.timestamp()
    match = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2})[:：](\d{2})", value)
    if match:
        try:
            target = datetime(
                int(match.group(1)), int(match.group(2)), int(match.group(3)),
                int(match.group(4)), int(match.group(5)),
                tzinfo=ZoneInfo(timezone),
            )
        except ValueError:
            return None
        return target.timestamp() if target > now else None
    match = re.search(r"(?<!\d)(\d{1,2})[:：](\d{2})(?!\d)", value)
    if match:
        target = now.replace(
            hour=int(match.group(1)), minute=int(match.group(2)),
            second=0, microsecond=0,
        )
        if target <= now:
            target += timedelta(days=1)
        return target.timestamp()
    return None
