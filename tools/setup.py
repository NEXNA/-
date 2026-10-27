"""交互式初始化：写 .env 和 config.toml 的群号/管理员。

用法（推荐）：
    双击 setup.bat

也可以手动：
    python tools/setup.py
"""
from __future__ import annotations

import argparse
import getpass
import re
import secrets
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLACEHOLDER_GROUP = 123456789
PLACEHOLDER_ADMIN = 10001


class SetupError(Exception):
    pass


def read_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def read_config(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise SetupError(f"读不了 {path}：{exc}") from exc


def set_int_list(text: str, key: str, values: list[int]) -> str:
    pattern = rf"(?m)^{re.escape(key)}\s*=\s*\[[^\]]*\]"
    replacement = f"{key} = [{', '.join(str(v) for v in values)}]"
    new_text, count = re.subn(pattern, replacement, text)
    if count == 0:
        raise SetupError(f"config.toml 里找不到 {key} = [...]，请先恢复默认配置")
    return new_text


def build_env(deepseek_key: str, onebot_token: str, webhook_token: str) -> str:
    return (
        "# 由 setup.py 生成；不要提交、不要发群、不要截图。\n"
        f"DEEPSEEK_API_KEY={deepseek_key}\n"
        f"ONEBOT_ACCESS_TOKEN={onebot_token}\n"
        f"WEBHOOK_TOKEN={webhook_token}\n"
    )


def ask(prompt: str, default: str = "") -> str:
    hint = f"（默认 {default}）" if default else ""
    value = input(f"{prompt}{hint}：").strip()
    return value or default


def validate_number(value: str, label: str) -> int:
    if not value.isdigit():
        raise SetupError(f"{label} 必须是纯数字：{value!r}")
    number = int(value)
    if not (10000 <= number <= 999999999999):
        raise SetupError(f"{label} 看起来不对：{number}")
    return number


def run(root: Path, args: argparse.Namespace) -> None:
    config_path = root / "config.toml"
    env_path = root / ".env"
    if not config_path.exists():
        raise SetupError(f"找不到 {config_path}")

    data = read_config(config_path)
    access = data.get("access", {})
    current_groups = access.get("allow_groups") or []
    current_admins = access.get("admins") or []
    env = read_env(env_path)

    print("=" * 56)
    print(" QQ 设定整理机器人 · 初始化")
    print("=" * 56)
    if current_groups == [PLACEHOLDER_GROUP]:
        print("⚠️ 当前群号还是示例 123456789")
    if current_admins == [PLACEHOLDER_ADMIN]:
        print("⚠️ 当前管理员还是示例 10001")
    print()

    if args.group:
        group = validate_number(args.group, "群号")
    else:
        default = str(current_groups[0]) if current_groups else ""
        if default == str(PLACEHOLDER_GROUP):
            default = ""
        group = validate_number(ask("QQ 群号", default), "群号")

    if args.admin:
        admin = validate_number(args.admin, "管理员 QQ")
    else:
        default = str(current_admins[0]) if current_admins else ""
        if default == str(PLACEHOLDER_ADMIN):
            default = ""
        admin = validate_number(ask("管理员 QQ 号", default), "管理员 QQ")

    if args.key:
        key = args.key.strip()
    else:
        key = getpass.getpass("DeepSeek API Key（输入不回显，粘贴后回车）：").strip()
    if len(key) < 20 or key.startswith("sk-xxxx"):
        raise SetupError("API Key 看起来还是空的或示例值，请到 platform.deepseek.com 申请")

    onebot = args.onebot.strip() if args.onebot else ask(
        "NapCat HTTP 服务端 Token（回车自动生成）"
    )
    webhook = args.webhook.strip() if args.webhook else ask(
        "Webhook Token（回车自动生成）"
    )
    onebot = onebot or env.get("ONEBOT_ACCESS_TOKEN", "")
    webhook = webhook or env.get("WEBHOOK_TOKEN", "")
    if not onebot or onebot.startswith("change-me"):
        onebot = secrets.token_urlsafe(24)
    if not webhook or webhook.startswith("change-me"):
        webhook = secrets.token_urlsafe(24)

    config_text = config_path.read_text(encoding="utf-8-sig")
    config_text = set_int_list(config_text, "allow_groups", [group])
    config_text = set_int_list(config_text, "admins", [admin])
    config_path.write_text(config_text, encoding="utf-8", newline="\n")
    env_path.write_text(build_env(key, onebot, webhook), encoding="utf-8", newline="\n")

    print()
    print("✅ 已写入：")
    print(f"   群号     : {group}")
    print(f"   管理员   : {admin}")
    print(f"   .env     : {env_path}")
    print(f"   配置     : {config_path}")
    print()
    print("NapCat 里这样填：")
    print("  HTTP 服务端 → Token:")
    print(f"    {onebot}")
    print("  HTTP 客户端 → URL:")
    print(f"    http://127.0.0.1:8080/event?token={webhook}")
    print("  HTTP 客户端 → Token:")
    print(f"    {webhook}")
    print()
    print("下一步：双击 start.bat（或运行 .\\run.ps1）")
    print("注意：不要把这个窗口里的 Token/Key 发到群里。")


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT), help="项目目录，默认当前项目")
    parser.add_argument("--group", help="群号（非交互）")
    parser.add_argument("--admin", help="管理员 QQ（非交互）")
    parser.add_argument("--key", help="DeepSeek API Key（非交互，测试用）")
    parser.add_argument("--onebot", help="ONEBOT Token（非交互）")
    parser.add_argument("--webhook", help="Webhook Token（非交互）")
    args = parser.parse_args(argv)
    try:
        run(Path(args.root).resolve(), args)
    except SetupError as exc:
        print(f"\n[初始化失败] {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\n已取消。")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
