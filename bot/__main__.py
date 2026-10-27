from __future__ import annotations

import argparse
import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .commands import Bot
from .config import Config, ConfigError
from .llm import DeepSeekClient
from .onebot import OneBotClient
from .server import serve

ROOT = Path(__file__).resolve().parent.parent


def setup_logging(level: str) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file_handler = RotatingFileHandler(
        log_dir / "bot.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        handlers=[file_handler, console],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qq-setting-bot")
    parser.add_argument("--config", default=None, help="配置文件路径，默认 config.toml")
    parser.add_argument("--check", action="store_true", help="只检查配置，不启动")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    setup_logging(args.log_level)
    try:
        cfg = Config.load(ROOT, args.config, require_secrets=not args.check)
    except ConfigError as exc:
        print(f"[配置错误] {exc}", file=sys.stderr)
        return 2

    if args.check:
        print(json.dumps(cfg.describe(), ensure_ascii=False, indent=2))
        prompt = ROOT / "prompts" / "extract_system.md"
        print(f"\n提示词文件：{'存在' if prompt.exists() else '缺失'} {prompt}")
        print(f"数据目录：{cfg.data_dir}")
        return 0

    for warning in cfg.warnings:
        logging.getLogger("config").warning(warning)

    llm = DeepSeekClient(cfg)
    sender = OneBotClient(cfg.onebot_api, cfg.onebot_token, timeout=15)
    bot = Bot(cfg, llm, sender)
    bot.start_background()

    webhook = f"http://{cfg.host}:{cfg.port}/event?token={cfg.webhook_token}"
    (ROOT / "logs").mkdir(exist_ok=True)
    (ROOT / "logs" / "webhook-url.txt").write_text(webhook + "\n", encoding="utf-8")

    banner = (
        "\n"
        "========================================\n"
        " QQ 设定整理机器人\n"
        f" 配置文件 : {ROOT / (args.config or 'config.toml')}\n"
        f" 允许群   : {', '.join(map(str, sorted(cfg.allow_groups)))}\n"
        f" 管理员   : {', '.join(map(str, sorted(cfg.admins))) or '（未设置）'}\n"
        f" 模型     : {cfg.deepseek_model}\n"
        f" Webhook  : {webhook}\n"
        f" 健康检查 : http://{cfg.host}:{cfg.port}/healthz\n"
        "========================================\n"
        "把上面的 Webhook 地址填进 NapCat 的「HTTP 上报」\n"
        "按 Ctrl+C 停止\n"
    )
    print(banner)
    print("数据加载：")
    for group_id in sorted(cfg.allow_groups):
        try:
            store = bot.store(group_id)
            canon = store.load_canon()
            bandori = store.load_bandori()
            print(
                f"  群 {group_id}：主世界 {len(canon.get('entities', {}))} 个实体，"
                f"邦多利 {len(bandori.get('entities', {}))} 条，"
                f"{store.count_pending()} 条待整合"
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  群 {group_id}：读取数据失败：{exc}")
    try:
        print(f"表情包：{len(bot.stickers.usable_items())} 张（{bot.stickers.dir}）")
    except Exception as exc:  # noqa: BLE001
        print(f"表情包：读取失败：{exc}")
    print()
    logging.getLogger("main").info("启动：群 %s，模型 %s",
                                   sorted(cfg.allow_groups), cfg.deepseek_model)
    serve(bot, cfg)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n已停止。")
        raise SystemExit(0)
