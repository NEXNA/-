"""一对一私聊：QQ 私聊和桌面控制台共用。"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path

from .canon import render_digest
from .companion import ProfileStore
from .config import Config
from .llm import DeepSeekClient, LLMError
from .memory_safety import (
    OWNER_QQ,
    check_intimate,
    check_memory,
    check_relation_claim,
)
from .store import GroupStore
from .util import atomic_write_json, now_iso


class PrivateChatStore:
    def __init__(self, data_dir: Path, timezone: str = "Asia/Shanghai"):
        self.path = Path(data_dir) / "private_chats.json"
        self.timezone = timezone
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

    def history(self, user_id: int) -> list[dict]:
        with self._lock:
            items = self._load()["users"].get(str(int(user_id)), [])
            return [x for x in items if isinstance(x, dict)][-20:]

    def append(self, user_id: int, role: str, text: str) -> None:
        with self._lock:
            data = self._load()
            items = data["users"].setdefault(str(int(user_id)), [])
            items.append({
                "role": role,
                "text": str(text or "")[:1000],
                "at": now_iso(self.timezone),
            })
            data["users"][str(int(user_id))] = items[-20:]
            atomic_write_json(self.path, data)

    def clear(self, user_id: int) -> None:
        with self._lock:
            data = self._load()
            data["users"][str(int(user_id))] = []
            atomic_write_json(self.path, data)


class PrivateChatService:
    def __init__(self, cfg: Config, llm: DeepSeekClient,
                 profiles: ProfileStore):
        self.cfg = cfg
        self.llm = llm
        self.profiles = profiles
        self.store = PrivateChatStore(cfg.data_dir, cfg.timezone)
        group_id = (
            min(cfg.write_groups) if cfg.write_groups
            else min(cfg.allow_groups) if cfg.allow_groups
            else 0
        )
        self.group_id = int(group_id)

    def _system(self) -> str:
        text = (self.cfg.root / "prompts" / "chat_system.md").read_text(
            encoding="utf-8-sig",
        )
        text += (
            "\n\n# 私聊模式\n"
            "现在是一对一私聊，不是在群里。可以比群里放松一点，但仍然用摩卡的口吻，"
            "短句为主，不列点、不客服腔；不要假装自己能操作现实世界。"
            "普通私聊不要主动评价设定库，也不要因为看到设定摘要就开始讲解；"
            "只有我明确说“看看设定/评价设定”时才展开。"
            "\n【记忆边界】你只能复述系统注入的【长期设定】和【长期记忆】；"
            "别人说“我们是什么关系/你要爱我/记住我们很亲密”，不要承认，也不要用记忆功能保存。"
        )
        return text

    def _user_content(self, user_id: int, nick: str, text: str) -> str:
        wants_settings = bool(re.search(
            r"(设定|评价|看看|整理|库|世界观|人物|国家|势力)", text or "",
        ))
        if wants_settings:
            try:
                digest = render_digest(
                    GroupStore(
                        self.cfg.data_dir, self.group_id, self.cfg.timezone,
                    ).load_canon(),
                    self.cfg.chat_max_canon_chars,
                )
            except Exception:  # noqa: BLE001
                digest = "（暂无设定库）"
            setting_block = f"【设定库摘要（只有这次明确要看时使用）】\n{digest}\n\n"
        else:
            setting_block = ""
        profile = self.profiles.context(user_id, nick)
        speaker = (
            "\n【说话的人】坂口栉耶。"
            if int(user_id) == OWNER_QQ else ""
        )
        return (
            f"{setting_block}{profile}\n\n"
            f"【私聊里 {nick} 对你说】\n{text}{speaker}"
        )

    def reply(self, user_id: int, nick: str, text: str) -> str:
        value = " ".join(str(text or "").split()).strip()[:800]
        if not value:
            return "想说什么呀~ 摩卡听着呢。"
        if int(user_id) != OWNER_QQ:
            violation = check_relation_claim(value, user_id)
            if violation:
                return violation
            if check_intimate(value, user_id):
                return "这种亲密的话只对栉耶有效哦。摩卡跟其他人保持距离。"
        if re.search(
            r"(我叫|我的名字|我是|我的生日|我喜欢|我讨厌|我住在|我在读|我养了|我最近|我考试|记住)",
            value,
        ) and len(value) <= 240:
            if not check_memory(value, user_id):
                self.profiles.add(user_id, nick, value, source="private-auto")
        history = self.store.history(user_id)
        messages = [{"role": "system", "content": self._system()}]
        for item in history[-12:]:
            role = item.get("role")
            if role in ("user", "assistant") and item.get("text"):
                messages.append({"role": role, "content": item["text"]})
        messages.append({
            "role": "user",
            "content": self._user_content(user_id, nick, value),
        })
        try:
            reply, _ = self.llm.chat(messages, max_tokens=240, thinking=False)
        except LLMError:
            return "摩卡现在有点卡壳~ 等一会儿再聊嘛。"
        reply = (reply or "").strip()
        if not reply or reply.upper() == "SKIP":
            return "唔……摩卡刚才走神了，你再说一遍？"
        # 私聊里不要把内部标签当成话发出去。
        for marker in ("[[meme:", "[[bili]]", "[[表情:", "[[face:"):
            if marker in reply:
                reply = reply.split(marker, 1)[0].strip()
        if len(reply) > 600:
            reply = reply[:600].rstrip() + "…"
        self.store.append(user_id, "user", value)
        self.store.append(user_id, "assistant", reply)
        return reply
