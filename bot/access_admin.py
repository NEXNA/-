"""Local access management for the two projects in the Mocha console."""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path


def _clean(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


class CompanionAccess:
    def __init__(self, db_path: Path):
        self.path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=8)
        conn.row_factory = sqlite3.Row
        return conn

    def _setting(self, key: str) -> int:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    f"SELECT {key} FROM settings WHERE id = 1"
                ).fetchone()
                return int(row[key] or 0) if row else 0
        except sqlite3.Error:
            return 0

    def _set_setting(self, key: str, value: int) -> None:
        with self._connect() as conn:
            conn.execute(
                f"UPDATE settings SET {key} = ? WHERE id = 1", (int(bool(value)),)
            )

    def private_enabled(self) -> bool:
        return bool(self._setting("qq_whitelist_enabled"))

    def set_private_enabled(self, enabled: bool) -> None:
        self._set_setting("qq_whitelist_enabled", int(enabled))

    def private_list(self) -> list[dict]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT qq, note, created_at FROM qq_whitelist "
                    "ORDER BY created_at DESC, qq"
                ).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error:
            return []

    def add_private(self, qq: str, note: str = "") -> None:
        value = _clean(qq)
        if not 5 <= len(value) <= 12:
            raise ValueError("QQ 号格式不对")
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO qq_whitelist (qq, note, created_at) "
                "VALUES (?, ?, datetime('now')) "
                "ON CONFLICT(qq) DO UPDATE SET note = excluded.note",
                (value, note[:100]),
            )

    def remove_private(self, qq: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM qq_whitelist WHERE qq = ?", (_clean(qq),))

    def group_enabled(self) -> bool:
        return bool(self._setting("group_whitelist_enabled"))

    def set_group_enabled(self, enabled: bool) -> None:
        self._set_setting("group_whitelist_enabled", int(enabled))

    def group_list(self) -> list[dict]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT group_id, note, created_at FROM group_whitelist "
                    "ORDER BY created_at DESC, group_id"
                ).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error:
            return []

    def add_group(self, group_id: str, note: str = "") -> None:
        value = _clean(group_id)
        if not 5 <= len(value) <= 12:
            raise ValueError("群号格式不对")
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO group_whitelist (group_id, note, created_at) "
                "VALUES (?, ?, datetime('now')) "
                "ON CONFLICT(group_id) DO UPDATE SET note = excluded.note",
                (value, note[:100]),
            )

    def remove_group(self, group_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM group_whitelist WHERE group_id = ?",
                (_clean(group_id),),
            )
