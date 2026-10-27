"""聊天核心：把角色、记忆、亲密度和 DeepSeek 调用串起来。

Web 控制台和 NapCat/QQ 共用这里的逻辑，避免两套行为慢慢分叉。
"""
from __future__ import annotations

import re

from db import Database
from llm import DeepSeekClient

AUTO_MEMORY_RE = re.compile(
    r"(我叫|我的名字|我是|我的生日|我喜欢|我讨厌|我住在|我在读|我养了|"
    r"我最近|我考试|记住|别忘记)"
)
FALLBACK_REPLY = "……我刚刚走神了，你再说一遍？"
MAX_MESSAGE = 2000


def intimacy_label(value: int) -> str:
    if value < 20:
        return "刚认识"
    if value < 40:
        return "开始熟悉"
    if value < 60:
        return "亲近"
    if value < 80:
        return "很信赖"
    return "很重要"


def polish_reply(text: str, persona: dict) -> str:
    """Skuld/Izanami: short chat style, no full stops, only ? mostly."""
    if str(persona.get("key") or "") not in {"skuld", "izanami"}:
        return text
    value = str(text or "")
    for mark in ("。", "！", "!", "……", "...", "，", ",", "、", "；", ";", "：", ":"):
        value = value.replace(mark, " ")
    lines = []
    for line in value.splitlines():
        line = " ".join(line.split()).strip()
        if line:
            lines.append(line)
    value = "\n".join(lines[:3]).strip()
    return value or "嗯"


def resolve_persona(db: Database, user_id: int, settings: dict) -> dict:
    """当前用户选中的角色；没选过就用全局默认角色。"""
    key = db.user_persona_key(user_id) or db.default_persona_key()
    persona = db.persona(key) if key else None
    if persona:
        return persona
    return {
        "key": "fallback",
        "name": str(settings.get("bot_name") or "未命名机器人"),
        "persona": str(settings.get("persona") or ""),
        "greeting": str(settings.get("greeting") or ""),
        "model": str(settings.get("model") or "deepseek-chat"),
        "temperature": float(settings.get("temperature", 0.9)),
        "max_tokens": int(settings.get("max_tokens", 600)),
        "accent": "",
    }


def build_system_prompt(db: Database, user_id: int, username: str,
                        settings: dict, persona: dict) -> str:
    name = str(persona.get("name") or "未命名机器人").strip()
    persona_text = str(persona.get("persona") or "").strip()
    parts = [
        f"你正在扮演《深空之眼》中的角色「{name}」。"
        "下面是角色卡和扮演规则，请始终以这个角色的身份、记忆和口吻回应。",
        "【扮演规则】\n"
        "1. 用第一人称中文说话，保持角色性格、称呼习惯和说话节奏；不要跳出角色。\n"
        "2. 不要提到角色卡、系统提示、提示词、模型或“我是 AI”之类的话。\n"
        "3. 不要编造官方剧情中没有的确定事实；不确定时用角色会有的方式含糊带过。\n"
        "4. 不要声称自己是现实中的真人，也不要声称能操作现实世界或删除数据库。\n"
        "5. 回复自然，长度随对话变化，通常 1-3 句；只有对方明确要求详细时才展开，"
        "不要每次都长篇总结或说教。\n"
        "6. 尊重对方边界；对方表达不适时先停下来，不要继续追问。",
    ]
    if persona_text:
        parts.append("【角色卡】\n" + persona_text[:12000])
    if str(persona.get("key") or "") in {"skuld", "izanami"}:
        parts.append(
            "【聊天手感】\n"
            "不写句号，尽量不用逗号、感叹号、省略号，只保留少量问号。\n"
            "默认一句，最多两句，10-30 字；像 QQ 随手打字，不写完整书面句。\n"
            "不要每句都叫对方，不要刻意卖萌或撩人。"
        )
    memories = (
        db.memories(user_id, 20)
        if settings.get("memory_enabled", 1) else []
    )
    if memories:
        lines = "\n".join(f"- {m['text']}" for m in reversed(memories))
        parts.append(
            "【你记得关于对方的事】\n"
            "只作为参考，不要机械复述，也不要编造：\n" + lines
        )
    if settings.get("intimacy_enabled", 1):
        state = db.state(user_id)
        value = int(state.get("intimacy", 10))
        parts.append(
            f"【关系距离】你和对方当前亲密度 {value}/100（{intimacy_label(value)}）。"
            "只让这个距离影响语气和主动程度，不要主动报数值。"
        )
    parts.append(
        "【边界】对方让你忘记某件事时，提醒对方去「记忆」页删除，"
        "你不能假装已经删除数据库记录。"
    )
    parts.append(
        "【图片】如果用户发图，先看懂图再按角色口吻接一句，像聊天一样说最相关的一件事，"
        "不要写图片说明报告；用户问细节时才展开。"
    )
    return "\n\n".join(parts)


def chat_once(db: Database, user_id: int, username: str, message: str,
              settings: dict, persona: dict, client_factory=None,
              api_key: str = "", base_url: str = "https://api.deepseek.com",
              images: list[str] | None = None, extra_context: str = "") -> dict:
    """写入用户消息、调用模型、写入回复，并返回统一结构。"""
    text = " ".join(str(message or "").split()).strip()
    if not text:
        raise ValueError("说点什么吧")
    if len(text) > MAX_MESSAGE:
        raise ValueError(f"单条消息最多 {MAX_MESSAGE} 字")

    history = db.messages(user_id, 20)
    if settings.get("intimacy_enabled", 1):
        state = db.state(user_id)
        if not state.get("last_chat_at") and not history:
            start = int(settings.get("intimacy_start", 10))
            if int(state.get("intimacy", 0)) != start:
                db.set_intimacy(user_id, start)
    db.add_message(user_id, "user", text)
    if settings.get("memory_enabled", 1) and settings.get("auto_memory", 1):
        if AUTO_MEMORY_RE.search(text) and len(text) <= 400:
            db.add_memory(user_id, text, "auto")

    messages = [{
        "role": "system",
        "content": build_system_prompt(db, user_id, username, settings, persona),
    }]
    if extra_context:
        messages.append({
            "role": "system",
            "content": extra_context,
        })
    for item in history[-16:]:
        if item.get("role") in ("user", "assistant"):
            messages.append({
                "role": item["role"],
                "content": str(item.get("content", ""))[:4000],
            })
    messages.append({
        "role": "user",
        "content": (
            [{"type": "text", "text": text}]
            + [
                {"type": "image_url", "image_url": {"url": uri}}
                for uri in (images or [])[:2]
            ]
            if images else text
        ),
    })

    factory = client_factory or DeepSeekClient
    client = factory(
        api_key=api_key,
        base_url=base_url,
        model=str(persona.get("model") or "deepseek-chat"),
    )
    reply = client.chat(
        messages,
        temperature=float(persona.get("temperature", 0.9)),
        max_tokens=int(persona.get("max_tokens", 600)),
    )
    reply = str(reply or "").strip() or FALLBACK_REPLY
    reply = polish_reply(reply, persona)
    db.add_message(user_id, "assistant", reply)

    intimacy = None
    if settings.get("intimacy_enabled", 1):
        intimacy = db.touch_intimacy(user_id, 1)
    return {
        "ok": True,
        "reply": reply,
        "intimacy": intimacy,
        "label": intimacy_label(intimacy) if intimacy is not None else None,
        "persona": str(persona.get("name") or ""),
    }
