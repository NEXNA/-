from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request

from .config import Config
from .util import short

logger = logging.getLogger(__name__)


class LLMError(Exception):
    pass


class LLMTransient(LLMError):
    pass


def parse_json_object(text: str) -> dict:
    """模型偶尔会包一层 ```json，这里做容错。"""
    if not text or not text.strip():
        raise LLMError("模型返回了空内容")
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise LLMError(f"模型输出不是 JSON：{short(text, 120)}")
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise LLMError(f"JSON 解析失败：{exc}") from exc
    if not isinstance(data, dict):
        raise LLMError("模型输出的 JSON 不是对象")
    return data


def canon_for_prompt(canon: dict) -> dict:
    """去掉来源、时间等模型不需要的字段，控制输入体积。"""
    entities = {}
    for key, ent in canon.get("entities", {}).items():
        entities[key] = {
            "type": ent.get("type"),
            "name": ent.get("name"),
            "aliases": ent.get("aliases", []),
            "fields": {name: item.get("value") for name, item in ent.get("fields", {}).items()},
            "relations": [
                {"to": rel.get("to"), "kind": rel.get("kind")}
                for rel in ent.get("relations", [])
            ],
        }
    conflicts = [
        {
            "id": c.get("id"),
            "entity": c.get("entity"),
            "field": c.get("field"),
            "values": [v.get("value") for v in c.get("values", [])],
        }
        for c in canon.get("conflicts", {}).values()
        if c.get("status") == "open"
    ]
    questions = [
        q.get("text") for q in canon.get("questions", {}).values()
        if q.get("status") == "open"
    ]
    return {
        "entities": entities,
        "open_conflicts": conflicts,
        "open_questions": questions,
    }


def build_user_prompt(canon: dict, batch: list[dict], context: list[dict],
                      max_canon_chars: int = 300_000) -> str:
    compact = canon_for_prompt(canon)
    canon_text = json.dumps(compact, ensure_ascii=False, indent=1)
    if len(canon_text) > max_canon_chars:
        raise LLMError(
            f"设定库太大（{len(canon_text)} 字符，上限 {max_canon_chars}）。"
            "请先发「导出」备份，再清理 canon.json 里的冗余字段。"
        )

    ctx_lines = []
    for item in context:
        text = " ".join(str(item.get("text", "")).split())[:200]
        if text:
            ctx_lines.append(f"{item.get('nick', '')}: {text}")

    batch_lines = []
    for entry in batch:
        text = " ".join(str(entry.get("text", "")).split())[:1500]
        batch_lines.append(f"[{entry['id']}] {entry.get('nick', '')}: {text}")

    return (
        "【现有设定库】\n"
        f"{canon_text}\n\n"
        "【最近聊天 · 仅用于理解指代，不是素材，不得引用】\n"
        + ("\n".join(ctx_lines) or "（无）")
        + "\n\n【待整理素材 · 唯一允许引用的来源】\n"
        + "\n".join(batch_lines)
        + "\n\n按 system 里的 schema 输出 JSON。"
    )

class DeepSeekClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.prompt_path = cfg.root / "prompts" / "extract_system.md"

    def _system_prompt(self) -> str:
        try:
            return self.prompt_path.read_text(encoding="utf-8-sig")
        except OSError as exc:
            raise LLMError(f"读不到提示词文件：{self.prompt_path}") from exc

    def extract(self, canon: dict, batch: list[dict],
                context: list[dict]) -> tuple[dict, dict]:
        user = build_user_prompt(canon, batch, context, self.cfg.max_canon_chars)
        payload = {
            "model": self.cfg.deepseek_model,
            "messages": [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": self.cfg.max_tokens,
            "temperature": 0.2,
            "stream": False,
            "thinking": {"type": "disabled"},
        }
        data = self._post(payload)
        try:
            choice = data["choices"][0]
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("DeepSeek 返回结构异常") from exc
        if choice.get("finish_reason") == "length":
            raise LLMError("模型输出被 max_tokens 截断，请调大 max_tokens 或减小 max_batch")
        patch = parse_json_object(content)
        usage = data.get("usage") or {}
        usage = {
            "input": int(usage.get("prompt_tokens", 0)),
            "output": int(usage.get("completion_tokens", 0)),
        }
        logger.info("DeepSeek 用量：输入 %s，输出 %s", usage["input"], usage["output"])
        return patch, usage

    def chat(self, messages: list[dict], max_tokens: int | None = None,
             temperature: float = 0.9, thinking: bool | None = None,
             reasoning_effort: str | None = None) -> tuple[str, dict]:
        """普通对话，不走 JSON 模式。messages 里应包含 system。"""
        use_thinking = self.cfg.chat_thinking_default if thinking is None else bool(thinking)
        payload = {
            "model": self.cfg.deepseek_model,
            "messages": messages,
            "max_tokens": int(max_tokens or self.cfg.chat_max_tokens),
            "stream": False,
            "thinking": {"type": "enabled" if use_thinking else "disabled"},
        }
        if use_thinking:
            payload["reasoning_effort"] = reasoning_effort or self.cfg.chat_reasoning_effort
        else:
            # 思考模式不支持 temperature；非思考模式照常传
            payload["temperature"] = temperature
        data = self._post(payload)
        try:
            choice = data["choices"][0]
            content = choice["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("DeepSeek 返回结构异常") from exc
        if not content.strip():
            raise LLMError("模型返回了空内容")
        if choice.get("finish_reason") == "length":
            logger.warning("聊天输出被 max_tokens 截断")
        usage = data.get("usage") or {}
        usage = {
            "input": int(usage.get("prompt_tokens", 0)),
            "output": int(usage.get("completion_tokens", 0)),
        }
        logger.debug("聊天用量：输入 %s，输出 %s", usage["input"], usage["output"])
        return content.strip(), usage

    def search_web(self, query: str, count: int | None = None) -> list[dict]:
        """调用 DeepSeek 自研搜索，返回标题/URL/摘要。搜索结果是不可信外部数据。"""
        query = (query or "").strip()[:128]
        if not query:
            return []
        count = max(1, min(50, int(count or self.cfg.chat_web_search_count)))
        base = self.cfg.deepseek_base.rstrip("/")
        if base.endswith("/v1"):
            url = f"{base}/tools/search"
        else:
            url = f"{base}/v1/tools/search"
        payload = {"query": query, "count": count, "need_content": False}
        data = self._post_url(url, payload, timeout=min(60, self.cfg.timeout_seconds))
        results = data.get("results") or []
        cleaned = []
        for item in results[:count]:
            if not isinstance(item, dict):
                continue
            cleaned.append({
                "title": str(item.get("title") or "").strip(),
                "url": str(item.get("url") or "").strip(),
                "summary": str(item.get("summary") or item.get("snippet") or "").strip(),
                "date": str(item.get("date") or "").strip(),
            })
        logger.info("联网搜索：%s -> %s 条", query, len(cleaned))
        return cleaned

    # ---------- HTTP ----------

    def _post(self, payload: dict) -> dict:
        url = f"{self.cfg.deepseek_base}/chat/completions"
        data = self._post_url(url, payload)
        choices = data.get("choices") or []
        content = ""
        if choices:
            content = (choices[0].get("message") or {}).get("content") or ""
        if not content.strip():
            raise LLMError("模型返回了空内容")
        return data

    def _post_url(self, url: str, payload: dict, timeout: int | None = None) -> dict:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.cfg.deepseek_key}",
            "User-Agent": "qq-setting-bot/1.0",
        }
        last_error: Exception | None = None
        wait = timeout or self.cfg.timeout_seconds
        for attempt in range(3):
            request = urllib.request.Request(url, data=body, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(request, timeout=wait) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
                data = json.loads(raw)
                if "error" in data:
                    raise LLMError(f"DeepSeek 错误：{short(str(data['error']), 200)}")
                return data
            except urllib.error.HTTPError as exc:
                detail = ""
                try:
                    detail = exc.read().decode("utf-8", errors="replace")
                except Exception:  # noqa: BLE001
                    pass
                message = f"HTTP {exc.code}：{short(detail, 300)}"
                if exc.code in (401, 403):
                    raise LLMError(f"认证失败，检查 DEEPSEEK_API_KEY（{message}）") from exc
                if exc.code == 429 or 500 <= exc.code < 600:
                    last_error = LLMTransient(message)
                else:
                    raise LLMError(message) from exc
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = LLMTransient(f"网络错误：{exc}")
            if attempt < 2:
                delay = 2 * (attempt + 1)
                logger.warning("DeepSeek 调用失败，%ss 后重试：%s", delay, last_error)
                time.sleep(delay)
        raise LLMError(f"DeepSeek 调用失败：{last_error}")
