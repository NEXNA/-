"""NapCat 项目路由与登录 QQ 管理。

Mocha 控制台只做两件事：
1. 把 OneBot 上报目标切到某个已登记项目；
2. 为新的 NapCat 登录 QQ 准备配置并可选重启。

不修改项目数据，不把事件同时发给两个项目。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from .napcat import NapCatError, NapCatWebUI

DEFAULT_NAPCAT_ROOT = Path(r"D:\NapCat.Shell.Windows.OneKey")


def find_config_dir(base: Path | str | None = None) -> Path:
    explicit = os.environ.get("NAPCAT_CONFIG_DIR", "").strip()
    if explicit:
        path = Path(explicit)
        if path.is_dir():
            return path
        raise ValueError(f"NAPCAT_CONFIG_DIR 不存在：{path}")
    root = Path(base) if base else DEFAULT_NAPCAT_ROOT
    candidates = sorted(root.glob("NapCat.*/versions/*/resources/app/napcat/config"))
    for path in candidates:
        if path.is_dir():
            return path
    raise ValueError(f"没有找到 NapCat 配置目录：{root}")


def clean_qq(value: object) -> str:
    return re.sub(r"\D", "", str(value or ""))


def list_accounts(config_dir: Path) -> list[str]:
    accounts = []
    for path in config_dir.iterdir():
        match = re.fullmatch(r"onebot11_(\d{5,12})\.json", path.name)
        if match and path.is_file():
            accounts.append(match.group(1))
    return sorted(set(accounts))


def load_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_config(path: Path, data: dict) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if path.exists():
        backup = path.with_name(path.name + f".bak-{stamp}")
        shutil.copy2(path, backup)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _ensure_server(network: dict) -> dict:
    servers = network.setdefault("httpServers", [])
    if not servers:
        servers.append({
            "enable": True,
            "name": "青叶摩卡https",
            "host": "127.0.0.1",
            "port": 3000,
            "enableCors": True,
            "enableWebsocket": True,
            "messagePostFormat": "array",
            "token": "",
            "debug": False,
        })
    server = servers[0]
    server["enable"] = True
    server["host"] = "127.0.0.1"
    server["port"] = 3000
    return server


def ensure_projects(data: dict, projects: list[dict], active: str) -> list[dict]:
    """只保留一个启用的上报客户端。未知客户端一律停用。"""
    network = data.setdefault("network", {})
    _ensure_server(network)
    clients = network.setdefault("httpClients", [])
    by_key: dict[str, dict] = {}
    for project in projects:
        key = str(project["key"])
        name = str(project["name"])
        url = str(project["url"])
        token = str(project.get("token") or "")
        found = None
        for client in clients:
            same_name = str(client.get("name") or "") == name
            same_url = str(client.get("url") or "").split("?")[0] == url.split("?")[0]
            if same_name or same_url:
                found = client
                break
        if found is None:
            found = {
                "name": name,
                "url": url,
                "reportSelfMessage": False,
                "messagePostFormat": "array",
                "token": token,
                "debug": False,
            }
            clients.append(found)
        found.update({
            "name": name,
            "url": url,
            "reportSelfMessage": False,
            "messagePostFormat": "array",
            "token": token,
            "debug": False,
            "enable": key == active,
        })
        by_key[key] = found
    for client in clients:
        if not any(client is item for item in by_key.values()):
            client["enable"] = False
    return clients


def read_target(data: dict, projects: list[dict]) -> str:
    clients = (data.get("network") or {}).get("httpClients") or []
    for project in projects:
        for client in clients:
            if (client.get("enable")
                    and (client.get("name") == project["name"]
                         or str(client.get("url", "")).split("?")[0]
                         == str(project["url"]).split("?")[0])):
                return str(project["key"])
    return ""


def active_from_config(path: Path, projects: list[dict]) -> str:
    try:
        return read_target(load_config(path), projects)
    except (OSError, json.JSONDecodeError):
        return ""


def apply_live(config: dict, webui_url: str, webui_token: str) -> None:
    client = NapCatWebUI(webui_url, webui_token)
    client.login()
    client._post(  # noqa: SLF001 - 内部 API 客户端封装
        "/OB11Config/SetConfig",
        {"config": json.dumps(config, ensure_ascii=False)},
        client.credential(),
    )


def apply_projects(config_dir: Path, qq: str, projects: list[dict],
                   active: str, webui_url: str, webui_token: str) -> dict:
    qq = clean_qq(qq)
    if not qq:
        raise ValueError("没有当前登录 QQ")
    if active not in {p["key"] for p in projects}:
        raise ValueError("未知的上报项目")
    path = config_dir / f"onebot11_{qq}.json"
    if not path.exists():
        raise ValueError(f"没有这个 QQ 的 OneBot 配置：{path.name}")
    data = load_config(path)
    ensure_projects(data, projects, active)
    write_config(path, data)
    apply_live(data, webui_url, webui_token)
    return {
        "qq": qq,
        "active": active,
        "config": str(path),
        "clients": [
            {"name": c.get("name"), "enable": bool(c.get("enable")),
             "url": c.get("url")}
            for c in data["network"]["httpClients"]
        ],
    }


def _default_quick_bat(config_dir: Path) -> Path:
    for parent in config_dir.parents:
        candidate = parent / "napcat.quick.bat"
        if candidate.exists():
            return candidate
    raise ValueError("找不到 napcat.quick.bat")


def _write_quick_bat(path: Path, target: str) -> None:
    text = path.read_text(encoding="utf-8-sig") if path.exists() else (
        "@echo off\nchcp 65001\n.\\NapCatWinBootMain.exe 10086\npause\n"
    )
    if re.search(r"NapCatWinBootMain\.exe\s+\d+", text):
        text = re.sub(
            r"(NapCatWinBootMain\.exe\s+)\d+", rf"\g<1>{target}", text,
        )
    else:
        text = text.rstrip() + f"\n.\\NapCatWinBootMain.exe {target}\n"
    path.write_text(text, encoding="utf-8")


def _ensure_core_configs(config_dir: Path, target: str,
                         current: str) -> None:
    for prefix, default in (
        ("napcat_", {"fileLog": False, "consoleLog": True}),
        ("napcat_protocol_", {"enable": False}),
    ):
        target_path = config_dir / f"{prefix}{target}.json"
        if target_path.exists():
            continue
        current_path = config_dir / f"{prefix}{current}.json"
        if current_path.exists():
            shutil.copy2(current_path, target_path)
        else:
            write_config(target_path, default)


def prepare_account(config_dir: Path, target_qq: str, current_qq: str,
                    projects: list[dict], active: str) -> dict:
    target = clean_qq(target_qq)
    current = clean_qq(current_qq)
    if not 5 <= len(target) <= 12:
        raise ValueError("QQ 号格式不对")
    target_path = config_dir / f"onebot11_{target}.json"
    if target_path.exists():
        data = load_config(target_path)
    elif current and (config_dir / f"onebot11_{current}.json").exists():
        data = load_config(config_dir / f"onebot11_{current}.json")
    else:
        data = {"network": {}}
    ensure_projects(data, projects, active)
    write_config(target_path, data)
    if current:
        _ensure_core_configs(config_dir, target, current)
    quick = _default_quick_bat(config_dir)
    _write_quick_bat(quick, target)
    return {
        "qq": target,
        "current": current,
        "config": str(target_path),
        "quick_bat": str(quick),
        "accounts": list_accounts(config_dir),
    }


def restart_napcat(quick_bat: Path) -> bool:
    shell_dir = quick_bat.parent
    script = f"""
$ErrorActionPreference = 'SilentlyContinue'
$dir = '{str(shell_dir).replace("'", "''")}'
$main = Get-CimInstance Win32_Process -Filter "Name='QQ.exe'" |
  Where-Object {{ $_.ExecutablePath -like '*NapCat*' -and $_.CommandLine -notmatch '--type=' }} |
  Select-Object -First 1
$boot = Get-CimInstance Win32_Process -Filter "Name='NapCatWinBootMain.exe'" |
  Select-Object -First 1
if ($main) {{ Stop-Process -Id $main.ProcessId -Force }}
Start-Sleep -Seconds 2
if ($boot) {{ Stop-Process -Id $boot.ProcessId -Force }}
Start-Sleep -Seconds 2
Start-Process -FilePath 'cmd.exe' -ArgumentList '/c','napcat.quick.bat' -WorkingDirectory $dir
"""
    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0,
        )
    try:
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            creationflags=flags, close_fds=True,
        )
        return True
    except Exception:  # noqa: BLE001
        return False


def switch_account(config_dir: Path, target_qq: str, current_qq: str,
                   projects: list[dict], active: str,
                   restart: bool = False) -> dict:
    result = prepare_account(
        config_dir, target_qq, current_qq, projects, active,
    )
    result["restart_requested"] = bool(restart)
    result["restart_started"] = (
        restart_napcat(Path(result["quick_bat"])) if restart else False
    )
    return result
