"""SQLite storage for the companion workbench."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from persona_seed import SEED_PERSONAS


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), 210_000,
    )
    return digest.hex(), salt


def verify_password(password: str, salt: str, expected: str) -> bool:
    digest, _ = hash_password(password, salt)
    return hmac.compare_digest(digest, expected)


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    qq TEXT,
                    nickname TEXT NOT NULL DEFAULT '',
                    is_admin INTEGER NOT NULL DEFAULT 0,
                    auth_source TEXT NOT NULL DEFAULT 'password'
                );
                CREATE TABLE IF NOT EXISTS settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    bot_name TEXT NOT NULL DEFAULT '',
                    persona TEXT NOT NULL DEFAULT '',
                    greeting TEXT NOT NULL DEFAULT '',
                    model TEXT NOT NULL DEFAULT 'deepseek-chat',
                    temperature REAL NOT NULL DEFAULT 0.9,
                    max_tokens INTEGER NOT NULL DEFAULT 600,
                    memory_enabled INTEGER NOT NULL DEFAULT 1,
                    auto_memory INTEGER NOT NULL DEFAULT 1,
                    fortune_enabled INTEGER NOT NULL DEFAULT 1,
                    intimacy_enabled INTEGER NOT NULL DEFAULT 1,
                    intimacy_start INTEGER NOT NULL DEFAULT 10,
                    default_persona TEXT NOT NULL DEFAULT 'skuld',
                    qq_whitelist_enabled INTEGER NOT NULL DEFAULT 0,
                    group_whitelist_enabled INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS qq_whitelist (
                    qq TEXT PRIMARY KEY,
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS group_whitelist (
                    group_id TEXT PRIMARY KEY,
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS personas (
                    key TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    persona TEXT NOT NULL DEFAULT '',
                    greeting TEXT NOT NULL DEFAULT '',
                    model TEXT NOT NULL DEFAULT 'deepseek-chat',
                    temperature REAL NOT NULL DEFAULT 0.9,
                    max_tokens INTEGER NOT NULL DEFAULT 600,
                    accent TEXT NOT NULL DEFAULT '',
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'manual',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS state (
                    user_id INTEGER PRIMARY KEY,
                    intimacy INTEGER NOT NULL DEFAULT 10,
                    last_chat_at TEXT NOT NULL DEFAULT '',
                    fortune_date TEXT NOT NULL DEFAULT '',
                    fortune_json TEXT NOT NULL DEFAULT '',
                    persona_key TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    expires_at REAL NOT NULL
                );
                """
            )
            conn.execute(
                "INSERT OR IGNORE INTO settings (id) VALUES (1)"
            )
            self._migrate(conn)
            self._seed_personas(conn)
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_qq "
                "ON users(qq) WHERE qq IS NOT NULL AND qq != ''"
            )
            conn.execute(
                "UPDATE users SET is_admin = 1 WHERE id = "
                "(SELECT MIN(id) FROM users) AND NOT EXISTS "
                "(SELECT 1 FROM users WHERE is_admin = 1)"
            )

    @staticmethod
    def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
        return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}

    def _migrate(self, conn: sqlite3.Connection) -> None:
        additions = {
            "users": {
                "qq": "qq TEXT",
                "nickname": "nickname TEXT NOT NULL DEFAULT ''",
                "is_admin": "is_admin INTEGER NOT NULL DEFAULT 0",
                "auth_source": "auth_source TEXT NOT NULL DEFAULT 'password'",
            },
            "settings": {
                "default_persona": "default_persona TEXT NOT NULL DEFAULT 'skuld'",
                "qq_whitelist_enabled": "qq_whitelist_enabled INTEGER NOT NULL DEFAULT 0",
                "group_whitelist_enabled": "group_whitelist_enabled INTEGER NOT NULL DEFAULT 0",
            },
            "state": {
                "persona_key": "persona_key TEXT NOT NULL DEFAULT ''",
            },
        }
        for table, columns in additions.items():
            existing = self._columns(conn, table)
            for name, ddl in columns.items():
                if name not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")

    @staticmethod
    def _seed_personas(conn: sqlite3.Connection) -> None:
        for item in SEED_PERSONAS:
            conn.execute(
                "INSERT OR IGNORE INTO personas "
                "(key, name, persona, greeting, model, temperature, max_tokens, "
                "accent, sort_order, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item["key"], item["name"], item.get("persona", ""),
                    item.get("greeting", ""), item.get("model", "deepseek-chat"),
                    float(item.get("temperature", 0.9)),
                    int(item.get("max_tokens", 600)), item.get("accent", ""),
                    int(item.get("sort_order", 0)), now_iso(),
                ),
            )
        conn.execute(
            "UPDATE settings SET default_persona = ? "
            "WHERE id = 1 AND (default_persona IS NULL OR default_persona = '')",
            (SEED_PERSONAS[0]["key"],),
        )

    # ---------- auth ----------
    def user_count(self) -> int:
        with self.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])

    def create_user(self, username: str, password: str) -> int:
        username = username.strip()
        if not 2 <= len(username) <= 32:
            raise ValueError("用户名长度需要 2-32 个字符")
        if len(password) < 6:
            raise ValueError("密码至少 6 位")
        digest, salt = hash_password(password)
        with self.connect() as conn:
            is_admin = int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]) == 0
            cur = conn.execute(
                "INSERT INTO users "
                "(username, password_hash, salt, created_at, is_admin, auth_source) "
                "VALUES (?, ?, ?, ?, ?, 'password')",
                (username, digest, salt, now_iso(), 1 if is_admin else 0),
            )
            user_id = int(cur.lastrowid)
            conn.execute(
                "INSERT OR IGNORE INTO state (user_id) VALUES (?)", (user_id,)
            )
            return user_id

    def user_by_qq(self, qq: str) -> sqlite3.Row | None:
        value = re.sub(r"\D", "", str(qq or ""))
        if not value:
            return None
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM users WHERE qq = ?", (value,)
            ).fetchone()

    def first_admin(self) -> sqlite3.Row | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE is_admin = 1 ORDER BY id LIMIT 1"
            ).fetchone()
            if row:
                return row
            return conn.execute(
                "SELECT * FROM users ORDER BY id LIMIT 1"
            ).fetchone()

    def bind_qq(self, user_id: int, qq: str, nickname: str = "") -> str:
        value = re.sub(r"\D", "", str(qq or ""))
        if not 5 <= len(value) <= 12:
            raise ValueError("QQ 号格式不对")
        with self.connect() as conn:
            other = conn.execute(
                "SELECT id FROM users WHERE qq = ? AND id != ?",
                (value, int(user_id)),
            ).fetchone()
            if other:
                raise ValueError("这个 QQ 已经绑定了其他账号")
            try:
                conn.execute(
                    "UPDATE users SET qq = ?, nickname = ? WHERE id = ?",
                    (value, str(nickname or "")[:64], int(user_id)),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("这个 QQ 已经绑定了其他账号") from exc
        self.add_qq_whitelist(value, "绑定账号")
        return value

    def unbind_qq(self, user_id: int) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE users SET qq = NULL, nickname = '' WHERE id = ?",
                (int(user_id),),
            )

    def ensure_guest(self, qq: str, nickname: str = "") -> sqlite3.Row:
        """群聊里没有绑定网页账号的群友，自动建一个 guest 身份。"""
        value = re.sub(r"\D", "", str(qq or ""))
        if not 5 <= len(value) <= 12:
            raise ValueError("QQ 号格式不对")
        existing = self.user_by_qq(value)
        if existing:
            return existing
        username = f"qq_{value}"
        base = username
        suffix = 0
        while self.find_user(username):
            suffix += 1
            username = f"{base}_{suffix}"
        user_id = self.create_user(username, secrets.token_urlsafe(24))
        self.bind_qq(user_id, value, nickname or f"群友{value[-4:]}")
        row = self.user_by_qq(value)
        if not row:
            raise ValueError("创建群聊身份失败")
        return row

    def qq_for_user(self, user_id: int) -> str:
        row = self.user_by_id(user_id)
        return str(row["qq"] or "") if row else ""

    # ---------- QQ 白名单 ----------
    def qq_whitelist(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT qq, note, created_at FROM qq_whitelist "
                "ORDER BY created_at DESC, qq"
            ).fetchall()
        return [dict(row) for row in rows]

    def is_qq_whitelisted(self, qq: str) -> bool:
        value = re.sub(r"\D", "", str(qq or ""))
        if not value:
            return False
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM qq_whitelist WHERE qq = ?", (value,)
            ).fetchone()
        return bool(row)

    def add_qq_whitelist(self, qq: str, note: str = "") -> dict:
        value = re.sub(r"\D", "", str(qq or ""))
        if not 5 <= len(value) <= 12:
            raise ValueError("QQ 号格式不对")
        clean_note = " ".join(str(note or "").split()).strip()[:100]
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO qq_whitelist (qq, note, created_at) VALUES (?, ?, ?) "
                "ON CONFLICT(qq) DO UPDATE SET note = excluded.note",
                (value, clean_note, now_iso()),
            )
        return {"qq": value, "note": clean_note}

    def remove_qq_whitelist(self, qq: str) -> bool:
        value = re.sub(r"\D", "", str(qq or ""))
        if not value:
            return False
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM qq_whitelist WHERE qq = ?", (value,))
            return cur.rowcount > 0

    def qq_whitelist_count(self) -> int:
        with self.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM qq_whitelist").fetchone()[0])

    # ---------- group whitelist ----------
    def group_whitelist(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT group_id, note, created_at FROM group_whitelist "
                "ORDER BY created_at DESC, group_id"
            ).fetchall()
        return [dict(row) for row in rows]

    def is_group_whitelisted(self, group_id: str) -> bool:
        value = re.sub(r"\D", "", str(group_id or ""))
        if not value:
            return False
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM group_whitelist WHERE group_id = ?", (value,)
            ).fetchone()
        return bool(row)

    def add_group_whitelist(self, group_id: str, note: str = "") -> dict:
        value = re.sub(r"\D", "", str(group_id or ""))
        if not 5 <= len(value) <= 12:
            raise ValueError("群号格式不对")
        clean_note = " ".join(str(note or "").split()).strip()[:100]
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO group_whitelist (group_id, note, created_at) "
                "VALUES (?, ?, ?) ON CONFLICT(group_id) DO UPDATE SET note = excluded.note",
                (value, clean_note, now_iso()),
            )
        return {"group_id": value, "note": clean_note}

    def remove_group_whitelist(self, group_id: str) -> bool:
        value = re.sub(r"\D", "", str(group_id or ""))
        if not value:
            return False
        with self.connect() as conn:
            cur = conn.execute(
                "DELETE FROM group_whitelist WHERE group_id = ?", (value,)
            )
            return cur.rowcount > 0

    def group_whitelist_count(self) -> int:
        with self.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM group_whitelist").fetchone()[0])

    def find_user(self, username: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM users WHERE username = ?", (username.strip(),)
            ).fetchone()

    def user_by_id(self, user_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM users WHERE id = ?", (int(user_id),)
            ).fetchone()

    def check_login(self, username: str, password: str) -> int | None:
        row = self.find_user(username)
        if row is None:
            return None
        if verify_password(password, row["salt"], row["password_hash"]):
            return int(row["id"])
        return None

    def create_session(self, user_id: int, days: int = 7) -> str:
        token = secrets.token_urlsafe(32)
        expires = time.time() + days * 86400
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
                (token, int(user_id), expires),
            )
        return token

    def session_user(self, token: str) -> int | None:
        if not token:
            return None
        with self.connect() as conn:
            row = conn.execute(
                "SELECT user_id, expires_at FROM sessions WHERE token = ?", (token,)
            ).fetchone()
            if not row:
                return None
            if float(row["expires_at"]) < time.time():
                conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
                return None
            return int(row["user_id"])

    def delete_session(self, token: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))

    # ---------- settings ----------
    def settings(self) -> dict:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
            return dict(row) if row else {}

    def update_settings(self, values: dict) -> dict:
        allowed = {
            "bot_name", "persona", "greeting", "model", "temperature",
            "max_tokens", "memory_enabled", "auto_memory",
            "fortune_enabled", "intimacy_enabled", "intimacy_start",
            "default_persona", "qq_whitelist_enabled", "group_whitelist_enabled",
        }
        values = {k: v for k, v in values.items() if k in allowed}
        if not values:
            return self.settings()
        columns = ", ".join(f"{key} = ?" for key in values)
        params = list(values.values()) + [1]
        with self.connect() as conn:
            conn.execute(f"UPDATE settings SET {columns} WHERE id = ?", params)
        return self.settings()

    # ---------- personas ----------
    def personas(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM personas ORDER BY sort_order, key"
            ).fetchall()
        return [dict(row) for row in rows]

    def persona(self, key: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM personas WHERE key = ?", (str(key or ""),)
            ).fetchone()
        return dict(row) if row else None

    def default_persona_key(self) -> str:
        settings = self.settings()
        key = str(settings.get("default_persona") or "")
        if key and self.persona(key):
            return key
        rows = self.personas()
        return str(rows[0]["key"]) if rows else ""

    def user_persona_key(self, user_id: int) -> str:
        key = str(self.state(user_id).get("persona_key") or "")
        return key if key and self.persona(key) else ""

    def set_user_persona(self, user_id: int, key: str) -> str:
        if not self.persona(key):
            raise ValueError("角色不存在")
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO state (user_id, persona_key) VALUES (?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET persona_key = excluded.persona_key",
                (int(user_id), str(key)),
            )
        return str(key)

    def save_persona(self, key: str, values: dict) -> dict:
        allowed = {
            "name", "persona", "greeting", "model", "temperature",
            "max_tokens", "accent", "sort_order",
        }
        values = {k: v for k, v in values.items() if k in allowed}
        if not values:
            return self.persona(key) or {}
        if not self.persona(key):
            raise ValueError("角色不存在")
        columns = ", ".join(f"{name} = ?" for name in values)
        params = list(values.values()) + [now_iso(), str(key)]
        with self.connect() as conn:
            conn.execute(
                f"UPDATE personas SET {columns}, updated_at = ? WHERE key = ?",
                params,
            )
        return self.persona(key) or {}

    # ---------- messages ----------
    def add_message(self, user_id: int, role: str, content: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO messages (user_id, role, content, created_at) "
                "VALUES (?, ?, ?, ?)",
                (int(user_id), role, str(content)[:8000], now_iso()),
            )

    def messages(self, user_id: int, limit: int = 20) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT role, content FROM messages WHERE user_id = ? "
                "ORDER BY id DESC LIMIT ?",
                (int(user_id), max(1, limit)),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def clear_messages(self, user_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM messages WHERE user_id = ?", (int(user_id),))

    # ---------- memories ----------
    def add_memory(self, user_id: int, text: str,
                   source: str = "manual") -> dict | None:
        value = " ".join(str(text or "").split()).strip()[:500]
        if len(value) < 2:
            return None
        with self.connect() as conn:
            exists = conn.execute(
                "SELECT id FROM memories WHERE user_id = ? AND text = ?",
                (int(user_id), value),
            ).fetchone()
            if exists:
                return None
            cur = conn.execute(
                "INSERT INTO memories (user_id, text, source, created_at) "
                "VALUES (?, ?, ?, ?)",
                (int(user_id), value, source, now_iso()),
            )
            return {
                "id": int(cur.lastrowid), "text": value, "source": source,
                "created_at": now_iso(),
            }

    def memories(self, user_id: int, limit: int = 100) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, text, source, created_at FROM memories "
                "WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                (int(user_id), max(1, limit)),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_memory(self, user_id: int, memory_id: int) -> bool:
        with self.connect() as conn:
            cur = conn.execute(
                "DELETE FROM memories WHERE id = ? AND user_id = ?",
                (int(memory_id), int(user_id)),
            )
            return cur.rowcount > 0

    def clear_memories(self, user_id: int) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "DELETE FROM memories WHERE user_id = ?", (int(user_id),),
            )
            return cur.rowcount

    # ---------- state ----------
    def state(self, user_id: int) -> dict:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM state WHERE user_id = ?", (int(user_id),),
            ).fetchone()
            if row:
                return dict(row)
            conn.execute("INSERT INTO state (user_id) VALUES (?)", (int(user_id),))
            return {
                "user_id": int(user_id), "intimacy": 10,
                "last_chat_at": "", "fortune_date": "", "fortune_json": "",
                "persona_key": "",
            }

    def set_intimacy(self, user_id: int, value: int) -> int:
        value = max(0, min(100, int(value)))
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO state (user_id, intimacy) VALUES (?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET intimacy = excluded.intimacy",
                (int(user_id), value),
            )
        return value

    def touch_intimacy(self, user_id: int, delta: int = 1) -> int:
        with self.connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO state (user_id) VALUES (?)", (int(user_id),)
            )
            conn.execute(
                "UPDATE state SET intimacy = MIN(100, MAX(0, intimacy + ?)), "
                "last_chat_at = ? WHERE user_id = ?",
                (int(delta), now_iso(), int(user_id)),
            )
            row = conn.execute(
                "SELECT intimacy FROM state WHERE user_id = ?", (int(user_id),),
            ).fetchone()
            return int(row["intimacy"])

    def save_fortune(self, user_id: int, date: str, payload: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO state (user_id, fortune_date, fortune_json) "
                "VALUES (?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET "
                "fortune_date = excluded.fortune_date, "
                "fortune_json = excluded.fortune_json",
                (int(user_id), date, payload),
            )
