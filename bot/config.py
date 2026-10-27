from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(Exception):
    pass


def load_dotenv(path: Path) -> None:
    """极简 .env 读取：KEY=VALUE，# 开头为注释，已存在的环境变量优先。"""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def _as_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return default


def _as_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int_set(value) -> set[int]:
    result: set[int] = set()
    if isinstance(value, (list, tuple, set)):
        for item in value:
            try:
                result.add(int(item))
            except (TypeError, ValueError):
                continue
    return result


def _as_str_set(value) -> set[str]:
    result: set[str] = set()
    if isinstance(value, str):
        value = [value]
    if isinstance(value, (list, tuple, set)):
        for item in value:
            text = str(item).strip().lower()
            if text:
                result.add(text)
    return result


@dataclass
class Config:
    root: Path
    host: str = "127.0.0.1"
    port: int = 8080
    data_dir: Path = field(default_factory=lambda: Path("data"))
    max_input_chars: int = 2000
    context_messages: int = 8
    rate_limit_seconds: int = 3
    max_batch: int = 40
    max_full_batches: int = 10
    organize_admins_only: bool = False
    timezone: str = "Asia/Shanghai"

    onebot_api: str = "http://127.0.0.1:3000"
    onebot_token: str = ""
    napcat_webui_url: str = "http://127.0.0.1:6099"
    napcat_webui_token: str = ""

    deepseek_base: str = "https://api.deepseek.com"
    deepseek_key: str = ""
    deepseek_model: str = "deepseek-flash"
    max_tokens: int = 16000
    timeout_seconds: int = 180
    max_canon_chars: int = 300_000
    daily_token_budget: int = 2_000_000

    chat_enabled: bool = True
    chat_cooldown_seconds: int = 20
    chat_daily_token_budget: int = 300_000
    chat_max_tokens: int = 600
    chat_history: int = 8
    chat_max_canon_chars: int = 10_000
    chat_admin_bypass: bool = True
    chat_line_delay: float = 0.45
    chat_thinking_default: bool = False
    chat_reasoning_effort: str = "high"
    chat_thinking_max_tokens: int = 1200
    chat_web_search_default: bool = False
    chat_web_search_count: int = 5

    auto_speak_enabled: bool = True
    auto_speak_cooldown_seconds: int = 180
    auto_speak_probability_percent: int = 4
    auto_speak_interest_boost_percent: int = 35
    auto_speak_min_messages: int = 6
    auto_speak_max_lines: int = 2
    auto_speak_vision: bool = True
    auto_speak_keywords: set[str] = field(default_factory=lambda: {
        "摩卡", "モカ", "moca", "面包", "吉他", "兰", "afterglow", "山吹", "莉莎",
    })

    sticker_enabled: bool = True
    sticker_auto_chance_percent: int = 25
    sticker_max_sync: int = 48
    sticker_send_mode: str = "base64"

    allow_groups: set[int] = field(default_factory=set)
    admins: set[int] = field(default_factory=set)
    write_groups: set[int] = field(default_factory=set)
    webhook_token: str = ""

    starting_coins: int = 80
    work_cooldown_seconds: int = 600
    work_min_coins: int = 15
    work_max_coins: int = 40
    hunger_decay_per_hour: float = 6.0
    sleepiness_decay_per_hour: float = 4.0
    mood_decay_per_hour: float = 3.0
    bili_image_enabled: bool = True
    bili_image_limit: int = 2000
    bili_fetch_default: int = 10
    bili_chat_chance_percent: int = 8
    bili_comment_mention: str = "青叶摩卡面包坊"
    bili_comment_max_chars: int = 100
    bili_comment_cooldown_seconds: int = 300
    bili_comment_enabled: bool = True

    voice_enabled: bool = False
    voice_api_url: str = "http://127.0.0.1:7860/v1/audio/speech"
    voice_model: str = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
    voice_name: str = "mocha_v1"
    voice_format: str = "wav"
    voice_timeout_seconds: int = 300
    voice_max_chars: int = 80
    voice_cooldown_seconds: int = 120

    warnings: list[str] = field(default_factory=list)

    # ---------- 加载 ----------

    @classmethod
    def load(cls, root: Path, config_path: str | Path | None = None,
             require_secrets: bool = True) -> "Config":
        root = Path(root).resolve()
        load_dotenv(root / ".env")
        path = Path(config_path) if config_path else root / "config.toml"
        if not path.is_absolute():
            path = root / path
        if not path.exists():
            raise ConfigError(f"找不到配置文件：{path}")

        try:
            data = tomllib.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
            raise ConfigError(f"配置文件读取失败：{path}（{exc}）") from exc

        bot = data.get("bot", {})
        onebot = data.get("onebot", {})
        napcat = data.get("napcat", {})
        deepseek = data.get("deepseek", {})
        chat = data.get("chat", {})
        auto_speak = data.get("auto_speak", {})
        sticker = data.get("sticker", {})
        access = data.get("access", {})
        safety = data.get("safety", {})
        fun = data.get("fun", {})
        bili = data.get("bili", {})
        voice = data.get("voice", {})

        keywords = _as_str_set(auto_speak.get("keywords"))
        if not keywords:
            keywords = {
                "摩卡", "モカ", "moca", "面包", "吉他", "兰", "afterglow", "山吹", "莉莎",
            }

        cfg = cls(
            root=root,
            host=str(bot.get("host", "127.0.0.1")),
            port=_as_int(bot.get("port"), 8080),
            data_dir=(root / str(bot.get("data_dir", "data"))).resolve(),
            max_input_chars=_as_int(bot.get("max_input_chars"), 2000),
            context_messages=_as_int(bot.get("context_messages"), 8),
            rate_limit_seconds=_as_int(bot.get("rate_limit_seconds"), 3),
            max_batch=_as_int(bot.get("max_batch"), 40),
            max_full_batches=_as_int(bot.get("max_full_batches"), 10),
            organize_admins_only=_as_bool(bot.get("organize_admins_only"), False),
            timezone=str(bot.get("timezone", "Asia/Shanghai")),
            onebot_api=str(onebot.get("api_base", "http://127.0.0.1:3000")).rstrip("/"),
            onebot_token=os.environ.get("ONEBOT_ACCESS_TOKEN", "")
            or str(onebot.get("access_token", "")),
            napcat_webui_url=str(
                os.environ.get("NAPCAT_WEBUI_URL")
                or napcat.get("webui_url", "http://127.0.0.1:6099")
            ).rstrip("/"),
            napcat_webui_token=os.environ.get("NAPCAT_WEBUI_TOKEN", "")
            or str(napcat.get("webui_token", "")),
            deepseek_base=str(deepseek.get("base_url", "https://api.deepseek.com")).rstrip("/"),
            deepseek_key=os.environ.get("DEEPSEEK_API_KEY", ""),
            deepseek_model=os.environ.get("DEEPSEEK_MODEL", "")
            or str(deepseek.get("model", "deepseek-flash")),
            max_tokens=_as_int(deepseek.get("max_tokens"), 16000),
            timeout_seconds=_as_int(deepseek.get("timeout_seconds"), 180),
            max_canon_chars=_as_int(deepseek.get("max_canon_chars"), 300_000),
            daily_token_budget=_as_int(deepseek.get("daily_token_budget"), 2_000_000),
            chat_enabled=_as_bool(chat.get("enabled"), True),
            chat_cooldown_seconds=_as_int(chat.get("cooldown_seconds"), 20),
            chat_daily_token_budget=_as_int(chat.get("daily_token_budget"), 300_000),
            chat_max_tokens=_as_int(chat.get("max_tokens"), 600),
            chat_history=_as_int(chat.get("history"), 8),
            chat_max_canon_chars=_as_int(chat.get("max_canon_chars"), 10_000),
            chat_admin_bypass=_as_bool(chat.get("admin_bypass_cooldown"), True),
            chat_line_delay=_as_float(chat.get("line_delay_seconds"), 0.45),
            chat_thinking_default=_as_bool(chat.get("thinking_default"), False),
            chat_reasoning_effort=str(chat.get("reasoning_effort", "high")),
            chat_thinking_max_tokens=_as_int(chat.get("thinking_max_tokens"), 1200),
            chat_web_search_default=_as_bool(chat.get("web_search_default"), False),
            chat_web_search_count=_as_int(chat.get("web_search_count"), 5),
            auto_speak_enabled=_as_bool(auto_speak.get("enabled"), True),
            auto_speak_cooldown_seconds=_as_int(auto_speak.get("cooldown_seconds"), 180),
            auto_speak_probability_percent=_as_int(auto_speak.get("probability_percent"), 4),
            auto_speak_interest_boost_percent=_as_int(auto_speak.get("interest_boost_percent"), 35),
            auto_speak_min_messages=_as_int(auto_speak.get("min_messages"), 6),
            auto_speak_max_lines=_as_int(auto_speak.get("max_lines"), 2),
            auto_speak_vision=_as_bool(auto_speak.get("vision"), True),
            auto_speak_keywords=keywords,
            sticker_enabled=_as_bool(sticker.get("enabled"), True),
            sticker_auto_chance_percent=_as_int(sticker.get("auto_chance_percent"), 25),
            sticker_max_sync=_as_int(sticker.get("max_sync"), 48),
            sticker_send_mode=str(sticker.get("send_mode", "base64")),
            allow_groups=_as_int_set(access.get("allow_groups")),
            admins=_as_int_set(access.get("admins")),
            write_groups=_as_int_set(safety.get("write_groups")),
            starting_coins=_as_int(fun.get("starting_coins"), 80),
            work_cooldown_seconds=_as_int(fun.get("work_cooldown_seconds"), 600),
            work_min_coins=_as_int(fun.get("work_min_coins"), 15),
            work_max_coins=_as_int(fun.get("work_max_coins"), 40),
            hunger_decay_per_hour=_as_float(fun.get("hunger_decay_per_hour"), 6.0),
            sleepiness_decay_per_hour=_as_float(fun.get("sleepiness_decay_per_hour"), 4.0),
            mood_decay_per_hour=_as_float(fun.get("mood_decay_per_hour"), 3.0),
            bili_image_enabled=_as_bool(bili.get("enabled"), True),
            bili_image_limit=_as_int(bili.get("image_limit"), 2000),
            bili_fetch_default=_as_int(bili.get("fetch_default"), 10),
            bili_chat_chance_percent=_as_int(bili.get("chat_chance_percent"), 8),
            bili_comment_mention=str(
                bili.get("comment_mention") or "青叶摩卡面包坊"
            ),
            bili_comment_max_chars=_as_int(bili.get("comment_max_chars"), 100),
            bili_comment_cooldown_seconds=_as_int(
                bili.get("comment_cooldown_seconds"), 300
            ),
            bili_comment_enabled=_as_bool(bili.get("comment_enabled"), True),
            voice_enabled=_as_bool(voice.get("enabled"), False),
            voice_api_url=str(
                voice.get("api_url", "http://127.0.0.1:7860/v1/audio/speech")
            ).rstrip("/"),
            voice_model=str(
                voice.get("model", "Qwen/Qwen3-TTS-12Hz-1.7B-Base")
            ),
            voice_name=str(voice.get("voice", "mocha_v1")),
            voice_format=str(voice.get("format", "wav")),
            voice_timeout_seconds=_as_int(voice.get("timeout_seconds"), 300),
            voice_max_chars=_as_int(voice.get("max_chars"), 80),
            voice_cooldown_seconds=_as_int(voice.get("cooldown_seconds"), 120),
            webhook_token=os.environ.get("WEBHOOK_TOKEN", "")
            or str(bot.get("webhook_token", "")),
        )
        cfg.validate(require_secrets)
        return cfg

    # ---------- 校验 ----------

    def validate(self, require_secrets: bool = True) -> None:
        if not (1 <= self.port <= 65535):
            raise ConfigError(f"端口不合法：{self.port}")
        if not self.allow_groups:
            raise ConfigError("access.allow_groups 为空：必须填写允许使用的 QQ 群号")
        if self.allow_groups and 123456789 in self.allow_groups:
            self.warnings.append("access.allow_groups 里还有示例群号 123456789，请替换成真实群号")
        if self.admins and 10001 in self.admins:
            self.warnings.append("access.admins 里还有示例管理员 10001，请替换成你的 QQ 号")
        if not self.admins:
            self.warnings.append("access.admins 为空：将没人能执行「裁决」「全量整合」「回滚」")
        if self.write_groups - self.allow_groups:
            self.warnings.append("safety.write_groups 里有不在 allow_groups 的群号，写操作会被忽略")
        if require_secrets:
            if not self.deepseek_key:
                raise ConfigError("缺少 DEEPSEEK_API_KEY，请写进 .env")
            if self.deepseek_key.strip() in {
                "sk-xxxxxxxxxxxxxxxxxxxxxxxx", "sk-xxx", "sk-test"
            } or self.deepseek_key.startswith("sk-xxxx"):
                raise ConfigError("DEEPSEEK_API_KEY 还是示例值，请填真实的 API Key")
            if not self.webhook_token:
                raise ConfigError("缺少 WEBHOOK_TOKEN，请写进 .env")
            if self.webhook_token.startswith("change-me"):
                raise ConfigError("WEBHOOK_TOKEN 还是示例值，请改成自己的随机串")
            if not self.onebot_token:
                raise ConfigError("缺少 ONEBOT_ACCESS_TOKEN，请写进 .env")
            if self.onebot_token.startswith("change-me"):
                raise ConfigError("ONEBOT_ACCESS_TOKEN 还是示例值，请改成自己的随机串")
            if 123456789 in self.allow_groups:
                raise ConfigError(
                    "access.allow_groups 还是示例群号 123456789，请改成真实群号"
                )

    def describe(self) -> dict:
        def mask(value: str) -> str:
            if not value:
                return "(未设置)"
            return value[:4] + "***" + value[-2:] if len(value) > 8 else "***"

        return {
            "config_root": str(self.root),
            "webhook": f"http://{self.host}:{self.port}/event",
            "data_dir": str(self.data_dir),
            "onebot_api": self.onebot_api,
            "onebot_token": mask(self.onebot_token),
            "napcat_webui_url": self.napcat_webui_url,
            "napcat_webui_token": mask(self.napcat_webui_token),
            "webhook_token": mask(self.webhook_token),
            "deepseek_api": self.deepseek_base,
            "deepseek_key": mask(self.deepseek_key),
            "deepseek_model": self.deepseek_model,
            "allow_groups": sorted(self.allow_groups),
            "admins": sorted(self.admins),
            "write_groups": sorted(self.write_groups),
            "starting_coins": self.starting_coins,
            "bili_image_limit": self.bili_image_limit,
            "warnings": self.warnings,
        }
