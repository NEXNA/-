"""把 NapCat 的 OneBot11 网络配置改成与本项目 .env 一致。

会做四件事：
1. 把「HTTP 服务端」的 Token 改成 .env 里的 ONEBOT_ACCESS_TOKEN；
2. 把「HTTP 客户端」的 URL 改成 http://127.0.0.1:8080/event?token=...，
   并把 Token 改成 .env 里的 WEBHOOK_TOKEN；
3. 关闭「WebSocket 客户端 / 反向 WS」——本项目不用 WS，开着只会 404 重连；
4. 关掉 reportSelfMessage，避免机器人自己的消息再触发一遍。

用法：
    双击 fix-napcat.bat
    或 python tools/fix_napcat.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class FixError(Exception):
    pass


def mask(value: str) -> str:
    if not value:
        return "(空)"
    if len(value) <= 8:
        return "***"
    return value[:4] + "***" + value[-2:]


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


def find_config(explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit)
        if not path.exists():
            raise FixError(f"找不到配置文件：{path}")
        return path

    candidates: list[Path] = []
    for base in (
        Path("D:/NapCat.Shell.Windows.OneKey"),
        Path("C:/NapCat.Shell.Windows.OneKey"),
        Path.home() / "NapCat.Shell.Windows.OneKey",
        Path("D:/"),
        Path("C:/"),
    ):
        if not base.exists():
            continue
        try:
            candidates.extend(base.glob("NapCat*/**/config/onebot11_*.json"))
        except OSError:
            continue
        if candidates:
            break
    if not candidates:
        raise FixError(
            "没找到 onebot11_*.json。请用 --config 指定，例如：\n"
            r'  python tools\fix_napcat.py --config "D:\NapCat...\config\onebot11_3826300285.json"'
        )
    return max(candidates, key=lambda p: p.stat().st_mtime)


def update(data: dict, onebot_token: str, webhook_token: str) -> list[str]:
    changes: list[str] = []
    network = data.setdefault("network", {})

    servers = network.setdefault("httpServers", [])
    if not servers:
        servers.append({"enable": True, "name": "qq-setting-bot", "host": "127.0.0.1",
                        "port": 3000, "messagePostFormat": "array", "token": onebot_token})
        changes.append("新建 HTTP 服务端（127.0.0.1:3000）")
    for server in servers:
        server["host"] = "127.0.0.1"
        server["token"] = onebot_token
        server["messagePostFormat"] = "array"
        server["enable"] = True
    changes.append(f"HTTP 服务端 Token -> {mask(onebot_token)}（端口保持原样）")

    clients = network.setdefault("httpClients", [])
    if not clients:
        clients.append({"enable": True, "name": "qq-setting-bot", "url": "",
                        "messagePostFormat": "array", "token": webhook_token,
                        "reportSelfMessage": False})
        changes.append("新建 HTTP 客户端（事件推送）")
    url = f"http://127.0.0.1:8080/event?token={webhook_token}"
    for client in clients:
        client["url"] = url
        client["token"] = webhook_token
        client["messagePostFormat"] = "array"
        client["reportSelfMessage"] = False
        client["enable"] = True
    changes.append("HTTP 客户端 URL -> http://127.0.0.1:8080/event?token=***")

    websockets = network.get("websocketClients", [])
    disabled = 0
    for item in websockets:
        if item.get("enable"):
            item["enable"] = False
            disabled += 1
    if disabled:
        changes.append(f"关闭 {disabled} 个 WebSocket 客户端（本项目不用 WS）")

    return changes


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", help="onebot11_*.json 的完整路径")
    parser.add_argument("--dry-run", action="store_true", help="只显示，不写入")
    args = parser.parse_args(argv)

    try:
        env = read_env(ROOT / ".env")
        onebot_token = env.get("ONEBOT_ACCESS_TOKEN", "")
        webhook_token = env.get("WEBHOOK_TOKEN", "")
        if not onebot_token or onebot_token.startswith("change-me"):
            raise FixError("ONEBOT_ACCESS_TOKEN 还是空的/示例值，先跑 setup.bat")
        if not webhook_token or webhook_token.startswith("change-me"):
            raise FixError("WEBHOOK_TOKEN 还是空的/示例值，先跑 setup.bat")

        path = find_config(args.config)
        print(f"配置文件：{path}")
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        changes = update(data, onebot_token, webhook_token)
        for line in changes:
            print(f"  - {line}")

        if args.dry_run:
            print("\n--dry-run：没有写入。")
            return 0

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = path.with_suffix(path.suffix + f".bak-{stamp}")
        shutil.copy2(path, backup)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(f"\n✅ 已写入。备份：{backup.name}")
        print("NapCat 不会自动读取外部改的文件，必须重启它才生效：")
        print("  关闭 NapCat 窗口 → 重新运行 napcat.quick.bat")
        print("如果 NapCat 退出时把旧配置写回，停掉后再跑一次本脚本即可。")
        return 0
    except (FixError, OSError, json.JSONDecodeError) as exc:
        print(f"\n[修复失败] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
