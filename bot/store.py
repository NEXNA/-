from __future__ import annotations

import copy
import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .canon import empty_canon
from .util import atomic_write_json, atomic_write_text, now_iso


class StoreError(Exception):
    pass


DEFAULT_STATE = {
    "next_raw_id": 1,
    "processed_upto": 0,
    "deleted_raw_ids": [],
    "seen_msg_ids": [],
    "usage_date": "",
    "usage_input": 0,
    "usage_output": 0,
    "last_organize": None,
    "created_at": "",
    "chat_enabled": None,
    "chat_cooldown": None,
    "chat_last_at": 0.0,
    "chat_usage_date": "",
    "chat_input": 0,
    "chat_output": 0,
    "chat_notice_date": "",
    "auto_enabled": None,
    "auto_cooldown": None,
    "auto_probability": None,
    "auto_min_messages": None,
    "auto_last_at": 0.0,
    "auto_msg_count": 0,
    "sticker_enabled": None,
    "sticker_chance": None,
    "thinking_enabled": None,
    "web_enabled": None,
    "sleep_until": 0.0,
    "bread_count": 0,
    "bread_last_at": 0.0,
}


class GroupStore:
    """一个群一个目录。raw 只追加，canon 由整理流程整体替换。"""

    def __init__(self, data_root: Path, group_id: int, timezone: str = "Asia/Shanghai"):
        self.group_id = int(group_id)
        self.timezone = timezone
        self.dir = Path(data_root) / str(self.group_id)
        self.raw_path = self.dir / "raw.jsonl"
        self.canon_path = self.dir / "canon.json"
        self.bandori_path = self.dir / "bandori.json"
        self.state_path = self.dir / "state.json"
        self.calls_path = self.dir / "calls.json"
        self.economy_path = self.dir / "economy.json"
        self.fun_path = self.dir / "fun.json"
        self.changelog_path = self.dir / "changelog.md"
        self.snapshot_dir = self.dir / "snapshots"
        self.export_dir = self.dir / "exports"
        self._lock = threading.RLock()
        self.dir.mkdir(parents=True, exist_ok=True)
        self.snapshot_dir.mkdir(exist_ok=True)
        self.export_dir.mkdir(exist_ok=True)
        self.state = self._load_state()

    # ---------- state ----------

    def _load_state(self) -> dict:
        if not self.state_path.exists():
            state = copy.deepcopy(DEFAULT_STATE)
            state["created_at"] = now_iso(self.timezone)
            atomic_write_json(self.state_path, state)
            return state
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StoreError(f"state.json 损坏：{self.state_path}（{exc}）") from exc
        merged = copy.deepcopy(DEFAULT_STATE)
        merged.update(state)
        return merged

    def _save_state(self) -> None:
        atomic_write_json(self.state_path, self.state)

    # ---------- raw ----------

    def append_raw(self, user_id: int, nick: str, text: str,
                   msg_id: str = "", kind: str = "text") -> dict:
        text = (text or "").strip()
        if not text:
            raise ValueError("素材为空")
        with self._lock:
            entry = {
                "id": int(self.state["next_raw_id"]),
                "msg_id": str(msg_id or ""),
                "uid": int(user_id),
                "nick": nick or str(user_id),
                "text": text,
                "kind": kind,
                "ts": now_iso(self.timezone),
            }
            # 先占号再写 raw：中途崩溃最多跳号，不会产生重复 id
            self.state["next_raw_id"] = entry["id"] + 1
            self._save_state()
            with open(self.raw_path, "a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            return entry

    def _iter_raw(self):
        if not self.raw_path.exists():
            return
        with open(self.raw_path, "r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    # 崩溃留下的半行，跳过
                    continue

    def raw_since(self, after_id: int = 0, limit: int | None = None) -> list[dict]:
        with self._lock:
            deleted = {int(x) for x in self.state.get("deleted_raw_ids", [])}
            items = [
                e for e in self._iter_raw()
                if int(e.get("id", 0)) > int(after_id) and int(e.get("id", 0)) not in deleted
            ]
            return items[:limit] if limit else items

    def pending(self, limit: int | None = None) -> list[dict]:
        with self._lock:
            upto = int(self.state["processed_upto"])
            deleted = {int(x) for x in self.state.get("deleted_raw_ids", [])}
            items = [
                e for e in self._iter_raw()
                if int(e.get("id", 0)) > upto and int(e.get("id", 0)) not in deleted
            ]
            return items[:limit] if limit else items

    def count_pending(self) -> int:
        return len(self.pending())

    def delete_pending(self, raw_id: int) -> dict | None:
        """删除一条尚未整理的素材。raw 文件保留，逻辑上隐藏，便于审计。"""
        with self._lock:
            upto = int(self.state["processed_upto"])
            target = None
            for entry in self._iter_raw():
                if int(entry.get("id", 0)) == int(raw_id):
                    target = entry
                    break
            if target is None or int(target.get("id", 0)) <= upto:
                return None
            deleted = {int(x) for x in self.state.get("deleted_raw_ids", [])}
            deleted.add(int(raw_id))
            self.state["deleted_raw_ids"] = sorted(deleted)
            self._save_state()
            return target

    def mark_processed(self, upto: int) -> None:
        with self._lock:
            self.state["processed_upto"] = max(int(self.state["processed_upto"]), int(upto))
            self.state["last_organize"] = now_iso(self.timezone)
            self._save_state()

    # ---------- seen ----------

    def is_seen(self, msg_id: str) -> bool:
        with self._lock:
            return str(msg_id) in self.state.get("seen_msg_ids", [])

    def mark_seen(self, msg_id: str) -> None:
        if not msg_id:
            return
        with self._lock:
            seen = self.state.setdefault("seen_msg_ids", [])
            if msg_id in seen:
                return
            seen.append(str(msg_id))
            if len(seen) > 500:
                del seen[:-500]
            self._save_state()

    # ---------- canon ----------

    def load_canon(self) -> dict:
        return self._load_canon_file(self.canon_path)

    def save_canon(self, canon: dict) -> None:
        with self._lock:
            atomic_write_json(self.canon_path, canon)

    def load_bandori(self) -> dict:
        return self._load_canon_file(self.bandori_path)

    def save_bandori(self, canon: dict) -> None:
        with self._lock:
            atomic_write_json(self.bandori_path, canon)

    def _load_canon_file(self, path: Path) -> dict:
        if not path.exists():
            return empty_canon()
        try:
            canon = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StoreError(f"{path.name} 损坏：{path}（{exc}）") from exc
        if not isinstance(canon, dict) or "entities" not in canon:
            raise StoreError(f"{path.name} 结构不对：{path}")
        return canon

    # ---------- snapshot / rollback ----------

    def snapshot(self, canon: dict) -> Path:
        with self._lock:
            stamp = datetime.now(ZoneInfo(self.timezone)).strftime("%Y%m%d-%H%M%S-%f")
            path = self.snapshot_dir / f"canon-{stamp}.json"
            payload = {
                "at": now_iso(self.timezone),
                "processed_upto": int(self.state["processed_upto"]),
                "canon": canon,
            }
            atomic_write_json(path, payload)
            return path

    def list_snapshots(self) -> list[Path]:
        return sorted(self.snapshot_dir.glob("canon-*.json"))

    def restore_latest(self) -> tuple[dict, int, str] | None:
        with self._lock:
            files = self.list_snapshots()
            if not files:
                return None
            path = files[-1]
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            used = self.snapshot_dir / "used"
            used.mkdir(exist_ok=True)
            os.replace(path, used / path.name)
            self.state["processed_upto"] = int(payload.get("processed_upto", 0))
            self._save_state()
            return payload["canon"], self.state["processed_upto"], path.name

    # ---------- usage ----------

    def add_usage(self, input_tokens: int, output_tokens: int, today: str) -> None:
        with self._lock:
            if self.state.get("usage_date") != today:
                self.state["usage_date"] = today
                self.state["usage_input"] = 0
                self.state["usage_output"] = 0
            self.state["usage_input"] = int(self.state.get("usage_input", 0)) + int(input_tokens)
            self.state["usage_output"] = int(self.state.get("usage_output", 0)) + int(output_tokens)
            self._save_state()

    def usage(self, today: str) -> tuple[int, int]:
        with self._lock:
            if self.state.get("usage_date") != today:
                return 0, 0
            return int(self.state.get("usage_input", 0)), int(self.state.get("usage_output", 0))

    # ---------- chat ----------

    def set_state(self, key: str, value) -> None:
        with self._lock:
            self.state[key] = value
            self._save_state()

    def chat_enabled(self, default: bool = True) -> bool:
        value = self.state.get("chat_enabled")
        return bool(default) if value is None else bool(value)

    def chat_cooldown(self, default: int = 20) -> int:
        value = self.state.get("chat_cooldown")
        try:
            return int(default) if value is None else int(value)
        except (TypeError, ValueError):
            return int(default)

    def chat_budget(self, default: int, today: str) -> int:
        """今日临时聊天上限；日期变了自动回到配置值。"""
        if str(self.state.get("chat_budget_date") or "") != str(today):
            return int(default)
        value = self.state.get("chat_budget_override")
        try:
            return int(default) if value is None else int(value)
        except (TypeError, ValueError):
            return int(default)

    def set_chat_budget(self, value: int, today: str) -> None:
        with self._lock:
            self.state["chat_budget_date"] = str(today)
            self.state["chat_budget_override"] = max(0, int(value))
            self.state.pop("chat_notice_date", None)
            self._save_state()

    def reset_chat_budget(self) -> None:
        with self._lock:
            self.state.pop("chat_budget_date", None)
            self.state.pop("chat_budget_override", None)
            self.state.pop("chat_notice_date", None)
            self._save_state()

    def chat_last_at(self) -> float:
        try:
            return float(self.state.get("chat_last_at") or 0)
        except (TypeError, ValueError):
            return 0.0

    def touch_chat(self) -> None:
        with self._lock:
            self.state["chat_last_at"] = time.time()
            self._save_state()

    def add_chat_usage(self, input_tokens: int, output_tokens: int, today: str) -> None:
        with self._lock:
            if self.state.get("chat_usage_date") != today:
                self.state["chat_usage_date"] = today
                self.state["chat_input"] = 0
                self.state["chat_output"] = 0
            self.state["chat_input"] = int(self.state.get("chat_input", 0)) + int(input_tokens)
            self.state["chat_output"] = int(self.state.get("chat_output", 0)) + int(output_tokens)
            self._save_state()

    def chat_usage(self, today: str) -> tuple[int, int]:
        with self._lock:
            if self.state.get("chat_usage_date") != today:
                return 0, 0
            return int(self.state.get("chat_input", 0)), int(self.state.get("chat_output", 0))

    # ---------- auto speak ----------

    def auto_enabled(self, default: bool = True) -> bool:
        value = self.state.get("auto_enabled")
        return bool(default) if value is None else bool(value)

    def auto_cooldown(self, default: int = 180) -> int:
        value = self.state.get("auto_cooldown")
        try:
            return int(default) if value is None else int(value)
        except (TypeError, ValueError):
            return int(default)

    def auto_probability(self, default: int = 4) -> int:
        value = self.state.get("auto_probability")
        try:
            return int(default) if value is None else int(value)
        except (TypeError, ValueError):
            return int(default)

    def auto_min_messages(self, default: int = 6) -> int:
        value = self.state.get("auto_min_messages")
        try:
            return int(default) if value is None else int(value)
        except (TypeError, ValueError):
            return int(default)

    def auto_last_at(self) -> float:
        try:
            return float(self.state.get("auto_last_at") or 0)
        except (TypeError, ValueError):
            return 0.0

    def auto_msg_count(self) -> int:
        try:
            return int(self.state.get("auto_msg_count") or 0)
        except (TypeError, ValueError):
            return 0

    def bump_auto_count(self) -> int:
        # 高频计数不落盘，重启后从 0 开始；设置和上次发言时间会落盘。
        with self._lock:
            self.state["auto_msg_count"] = self.auto_msg_count() + 1
            return self.state["auto_msg_count"]

    def reset_auto(self) -> None:
        with self._lock:
            self.state["auto_msg_count"] = 0
            self.state["auto_last_at"] = time.time()
            self._save_state()

    # ---------- stickers ----------

    def sticker_enabled(self, default: bool = True) -> bool:
        value = self.state.get("sticker_enabled")
        return bool(default) if value is None else bool(value)

    def sticker_chance(self, default: int = 25) -> int:
        value = self.state.get("sticker_chance")
        try:
            return int(default) if value is None else int(value)
        except (TypeError, ValueError):
            return int(default)

    def thinking_enabled(self, default: bool = False) -> bool:
        value = self.state.get("thinking_enabled")
        return bool(default) if value is None else bool(value)

    def web_enabled(self, default: bool = False) -> bool:
        value = self.state.get("web_enabled")
        return bool(default) if value is None else bool(value)

    # ---------- calls / 谁在找摩卡 ----------

    def _load_calls(self) -> dict:
        if not self.calls_path.exists():
            return {"version": 1, "calls": []}
        try:
            data = json.loads(self.calls_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return {"version": 1, "calls": []}
        if not isinstance(data, dict) or not isinstance(data.get("calls"), list):
            return {"version": 1, "calls": []}
        return data

    def record_call(self, user_id: int, nick: str, text: str, msg_id: str,
                    kind: str = "name") -> dict:
        with self._lock:
            data = self._load_calls()
            calls = data["calls"]
            if msg_id:
                for item in calls:
                    if str(item.get("msg_id")) == str(msg_id):
                        return item
            entry = {
                "msg_id": str(msg_id or ""),
                "uid": int(user_id),
                "nick": nick or str(user_id),
                "text": str(text or "")[:300],
                "kind": kind,
                "at": now_iso(self.timezone),
                "answered_at": None,
            }
            calls.append(entry)
            data["calls"] = calls[-100:]
            atomic_write_json(self.calls_path, data)
            return entry

    def mark_call_answered(self, msg_id: str) -> None:
        if not msg_id:
            return
        with self._lock:
            data = self._load_calls()
            changed = False
            for item in data["calls"]:
                if str(item.get("msg_id")) == str(msg_id) and not item.get("answered_at"):
                    item["answered_at"] = now_iso(self.timezone)
                    changed = True
                    break
            if changed:
                atomic_write_json(self.calls_path, data)

    def recent_calls(self, limit: int = 10, unanswered_only: bool = False) -> list[dict]:
        with self._lock:
            calls = list(self._load_calls()["calls"])
        if unanswered_only:
            calls = [item for item in calls if not item.get("answered_at")]
        return list(reversed(calls[-max(1, limit):]))

    def clear_calls(self) -> None:
        with self._lock:
            atomic_write_json(self.calls_path, {"version": 1, "calls": []})

    # ---------- 娱乐：经济 / 饥饿 / 困意 / 心情 ----------

    def _load_economy(self) -> dict:
        if not self.economy_path.exists():
            return {"version": 1, "wallets": {}, "infinite": False, "work_last": {}}
        try:
            data = json.loads(self.economy_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return {"version": 1, "wallets": {}, "infinite": False, "work_last": {}}
        if not isinstance(data, dict):
            return {"version": 1, "wallets": {}, "infinite": False, "work_last": {}}
        data.setdefault("wallets", {})
        data.setdefault("work_last", {})
        data.setdefault("infinite", False)
        return data

    def _save_economy(self, data: dict) -> None:
        atomic_write_json(self.economy_path, data)

    def wallet(self, user_id: int, starting: int = 0) -> dict:
        with self._lock:
            data = self._load_economy()
            key = str(int(user_id))
            if key not in data["wallets"]:
                data["wallets"][key] = max(0, int(starting))
                self._save_economy(data)
            return {
                "coins": int(data["wallets"].get(key, 0)),
                "infinite": bool(data.get("infinite")),
            }

    def add_coins(self, user_id: int, amount: int) -> int:
        with self._lock:
            data = self._load_economy()
            key = str(int(user_id))
            data["wallets"][key] = max(0, int(data["wallets"].get(key, 0)) + int(amount))
            self._save_economy(data)
            return int(data["wallets"][key])

    def spend_coins(self, user_id: int, amount: int, infinite: bool = False) -> bool:
        with self._lock:
            data = self._load_economy()
            key = str(int(user_id))
            if infinite:
                data["wallets"].setdefault(key, 0)
                self._save_economy(data)
                return True
            coins = int(data["wallets"].get(key, 0))
            if coins < int(amount):
                return False
            data["wallets"][key] = coins - int(amount)
            self._save_economy(data)
            return True

    def infinite_currency(self) -> bool:
        with self._lock:
            return bool(self._load_economy().get("infinite"))

    def set_infinite(self, enabled: bool) -> None:
        with self._lock:
            data = self._load_economy()
            data["infinite"] = bool(enabled)
            self._save_economy(data)

    def work(self, user_id: int, amount: int, cooldown: int) -> tuple[bool, int, int]:
        """返回 (是否成功, 剩余冷却秒, 当前余额)。"""
        with self._lock:
            now = time.time()
            data = self._load_economy()
            key = str(int(user_id))
            last = float(data["work_last"].get(key, 0) or 0)
            if last and now - last < max(0, cooldown):
                return False, max(1, int(cooldown - (now - last))), int(data["wallets"].get(key, 0))
            data["wallets"][key] = max(0, int(data["wallets"].get(key, 0)) + int(amount))
            data["work_last"][key] = now
            self._save_economy(data)
            return True, 0, int(data["wallets"][key])

    def _default_fun(self) -> dict:
        return {
            "hunger": 70.0,
            "sleepiness": 55.0,
            "mood": 70.0,
            "updated_at": time.time(),
            "sleep_rested": True,
        }

    def _load_fun(self) -> dict:
        data = self._default_fun()
        if self.fun_path.exists():
            try:
                raw = json.loads(self.fun_path.read_text(encoding="utf-8-sig"))
                if isinstance(raw, dict):
                    data.update(raw)
            except (OSError, json.JSONDecodeError):
                pass
        return data

    def _save_fun(self, data: dict) -> None:
        atomic_write_json(self.fun_path, data)

    def fun_decay_enabled(self, default: bool = True) -> bool:
        value = self.state.get("fun_decay_enabled")
        return bool(default) if value is None else bool(value)

    def set_fun_decay(self, enabled: bool) -> None:
        with self._lock:
            self.state["fun_decay_enabled"] = bool(enabled)
            self._save_state()
            # 立即推进一次时间戳，避免关闭期间攒下要补扣的时间。
            data = self._load_fun()
            data["updated_at"] = time.time()
            self._save_fun(data)

    def must_reply_users(self) -> set[int]:
        raw = self.state.get("must_reply_users") or []
        result: set[int] = set()
        for item in raw:
            try:
                result.add(int(item))
            except (TypeError, ValueError):
                continue
        return result

    def add_must_reply(self, user_id: int) -> bool:
        with self._lock:
            users = self.must_reply_users()
            if int(user_id) in users:
                return False
            users.add(int(user_id))
            self.state["must_reply_users"] = sorted(users)
            self._save_state()
            return True

    def remove_must_reply(self, user_id: int) -> bool:
        with self._lock:
            users = self.must_reply_users()
            if int(user_id) not in users:
                return False
            users.discard(int(user_id))
            self.state["must_reply_users"] = sorted(users)
            self._save_state()
            return True

    def clear_must_reply(self) -> None:
        with self._lock:
            self.state["must_reply_users"] = []
            self._save_state()

    def fun_stats(self, hunger_decay: float = 6.0,
                  sleepiness_decay: float = 4.0,
                  mood_decay: float = 3.0,
                  decay_enabled: bool = True) -> dict:
        with self._lock:
            data = self._load_fun()
            now = time.time()
            changed = False
            if (not data.get("sleep_rested", True)
                    and self.sleep_until() > 0
                    and self.sleep_until() <= now):
                data["sleepiness"] = max(0.0, float(data["sleepiness"]) - 40.0)
                data["mood"] = min(100.0, float(data["mood"]) + 10.0)
                data["sleep_rested"] = True
                self.state["sleep_until"] = 0
                self._save_state()
                changed = True
            hours = max(0.0, now - float(data.get("updated_at") or now)) / 3600.0
            if hours > 0:
                if decay_enabled:
                    data["hunger"] = max(0.0, float(data["hunger"]) - hunger_decay * hours)
                    data["sleepiness"] = max(0.0, float(data["sleepiness"]) - sleepiness_decay * hours)
                    data["mood"] = max(0.0, float(data["mood"]) - mood_decay * hours)
                # 关闭衰减时也推进 updated_at，重新打开后不会补扣。
                data["updated_at"] = now
                changed = True
            if changed:
                self._save_fun(data)
            return {
                "hunger": int(round(float(data["hunger"]))),
                "sleepiness": int(round(float(data["sleepiness"]))),
                "mood": int(round(float(data["mood"]))),
            }

    def sleep_until(self) -> float:
        try:
            return float(self.state.get("sleep_until") or 0)
        except (TypeError, ValueError):
            return 0.0

    def is_sleeping(self) -> bool:
        return self.sleep_until() > time.time()

    def sleep_for(self, minutes: int) -> float:
        with self._lock:
            until = time.time() + max(1, int(minutes)) * 60
            self.state["sleep_until"] = until
            self._save_state()
            data = self._load_fun()
            data["sleep_rested"] = False
            self._save_fun(data)
            return until

    def wake_up(self) -> bool:
        with self._lock:
            was = self.is_sleeping()
            self.state["sleep_until"] = 0
            self._save_state()
            data = self._load_fun()
            if not data.get("sleep_rested", True):
                data["sleepiness"] = max(0.0, float(data["sleepiness"]) - 40.0)
                data["mood"] = min(100.0, float(data["mood"]) + 10.0)
            data["sleep_rested"] = True
            self._save_fun(data)
            return was

    def bread_count(self) -> int:
        try:
            return int(self.state.get("bread_count") or 0)
        except (TypeError, ValueError):
            return 0

    def bread_last_at(self) -> float:
        try:
            return float(self.state.get("bread_last_at") or 0)
        except (TypeError, ValueError):
            return 0.0

    def eat_bread(self, bread: dict, hunger_decay: float = 6.0,
                  sleepiness_decay: float = 4.0, mood_decay: float = 3.0,
                  decay_enabled: bool = True) -> dict:
        stats = self.fun_stats(hunger_decay, sleepiness_decay, mood_decay, decay_enabled)
        with self._lock:
            data = self._load_fun()
            data["hunger"] = min(100.0, float(data["hunger"]) + float(bread.get("hunger", 0)))
            data["mood"] = min(100.0, float(data["mood"]) + float(bread.get("mood", 0)))
            data["sleepiness"] = min(100.0, float(data["sleepiness"]) + float(bread.get("sleepiness", 0)))
            data["updated_at"] = time.time()
            self._save_fun(data)
            self.state["bread_count"] = self.bread_count() + 1
            self.state["bread_last_at"] = time.time()
            self._save_state()
            return {
                "hunger": int(round(float(data["hunger"]))),
                "sleepiness": int(round(float(data["sleepiness"]))),
                "mood": int(round(float(data["mood"]))),
                "count": self.bread_count(),
            }

    def feed_bread(self, cooldown: int = 60) -> tuple[bool, int]:
        """保留旧接口；新逻辑请用 eat_bread()。"""
        with self._lock:
            now = time.time()
            last = self.bread_last_at()
            if last and now - last < max(0, cooldown):
                return False, self.bread_count()
            self.state["bread_count"] = self.bread_count() + 1
            self.state["bread_last_at"] = now
            self._save_state()
            return True, self.bread_count()

    # ---------- output ----------

    def append_changelog(self, title: str, lines: list[str]) -> None:
        body = [f"\n## {now_iso(self.timezone)} · {title}", ""]
        body.extend(f"- {line}" for line in lines)
        body.append("")
        with self._lock:
            with open(self.changelog_path, "a", encoding="utf-8", newline="\n") as f:
                f.write("\n".join(body) + "\n")

    def save_export(self, text: str, ext: str = "md") -> Path:
        stamp = datetime.now(ZoneInfo(self.timezone)).strftime("%Y%m%d-%H%M%S-%f")
        path = self.export_dir / f"settings-{stamp}.{ext}"
        atomic_write_text(path, text)
        return path

    def health(self) -> dict:
        return {
            "group_id": self.group_id,
            "pending": self.count_pending(),
            "entities": len(self.load_canon().get("entities", {})),
            "last_organize": self.state.get("last_organize"),
        }
