"""Per-project access files for the Mocha control panel."""
from __future__ import annotations

import json
import threading
from pathlib import Path

from .util import atomic_write_json


class PrivateWhitelist:
    def __init__(self, data_dir: Path):
        self.path = Path(data_dir) / "private_whitelist.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            data = {}
        users = data.get("users") if isinstance(data, dict) else []
        return {
            "enabled": bool(data.get("enabled")) if isinstance(data, dict) else False,
            "users": sorted({str(x) for x in users or [] if str(x).isdigit()}),
        }

    def save(self, data: dict) -> None:
        atomic_write_json(self.path, {
            "enabled": bool(data.get("enabled")),
            "users": sorted({str(x) for x in data.get("users", []) if str(x).isdigit()}),
        })

    def enabled(self) -> bool:
        return self.load()["enabled"]

    def users(self) -> list[str]:
        return self.load()["users"]

    def add(self, qq: str) -> None:
        with self._lock:
            data = self.load()
            if qq not in data["users"]:
                data["users"].append(qq)
                self.save(data)

    def remove(self, qq: str) -> None:
        with self._lock:
            data = self.load()
            data["users"] = [x for x in data["users"] if x != qq]
            self.save(data)

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            data = self.load()
            data["enabled"] = bool(enabled)
            self.save(data)

    def allowed(self, qq: int, admins: set[int]) -> bool:
        data = self.load()
        if not data["enabled"]:
            return True
        return int(qq) in admins or str(int(qq)) in data["users"]


def load_extra_groups(data_dir: Path) -> list[int]:
    path = Path(data_dir) / "whitelist.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return sorted({int(x) for x in data.get("groups", [])})
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return []


def save_extra_groups(data_dir: Path, groups: list[int]) -> None:
    atomic_write_json(Path(data_dir) / "whitelist.json", {
        "groups": sorted({int(x) for x in groups}),
    })
