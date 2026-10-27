"""青叶摩卡的面包坊 · 本地控制台。

双击 control_panel.bat 启动。读取项目里的 data/ 和配置，不需要浏览器/服务器。
"""
from __future__ import annotations

import base64
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.request
import webbrowser
from datetime import datetime
from io import BytesIO
from pathlib import Path
from tkinter import messagebox, ttk
from zoneinfo import ZoneInfo

try:
    import qrcode
except ImportError:  # pragma: no cover
    qrcode = None
from PIL import Image, ImageTk

from bot.access import PrivateWhitelist, load_extra_groups, save_extra_groups
from bot.access_admin import CompanionAccess
from bot.bili_images import BiliImageStore
from bot.bili_comments import BiliCommentError, BiliCommenter
from bot.canon import remove_question
from bot.companion import MemoryStore, ProfileStore, ReminderStore, parse_reminder_time
from bot.config import Config
from bot.llm import DeepSeekClient
from bot.memory_safety import OWNER_QQ, check_memory
from bot.napcat import NapCatError, NapCatWebUI
from bot.napcat_admin import (
    active_from_config,
    apply_projects,
    find_config_dir,
    list_accounts,
    switch_account,
)
from bot.onebot import OneBotClient, OneBotError
from bot.private_chat import PrivateChatService
from bot.store import GroupStore
from bot.util import atomic_write_json, short, today_str

ROOT = Path(__file__).resolve().parent
COMPANION_ROOT = ROOT / "companion"
COMPANION_PORT = 8765
COMPANION_NAPCAT_WEBUI = "http://127.0.0.1:6100"
TASK_NAME = "QQSettingBot"
NO_WINDOW = 0x08000000 if os.name == "nt" else 0

COLORS = {
    "bg": "#F3F7F4",
    "sidebar": "#073B36",
    "sidebar_hover": "#0C5148",
    "accent": "#00B894",
    "accent_dark": "#007A66",
    "card": "#FFFFFF",
    "ink": "#16372E",
    "muted": "#6B8078",
    "line": "#DCE8E2",
    "warn": "#C07830",
}


class MochaControlPanel:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("青叶摩卡的面包坊 · 控制台")
        self.root.geometry("1120x720")
        self.root.minsize(1120, 700)
        self.root.configure(bg=COLORS["bg"])

        try:
            self.cfg = Config.load(ROOT)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("配置读取失败", str(exc), parent=root)
            raise SystemExit(1) from exc

        self.groups = self._load_groups()
        preferred = sorted(self.cfg.write_groups)[0] if self.cfg.write_groups else None
        if preferred is not None and preferred in self.groups:
            default_group = preferred
        else:
            default_group = self.groups[0] if self.groups else ""
        self.group_var = tk.StringVar(value=str(default_group) if default_group else "")
        self._stores: dict[int, GroupStore] = {}
        self._memories: dict[int, MemoryStore] = {}
        self._reminders = ReminderStore(self.cfg.data_dir, self.cfg.timezone)
        self._bili = BiliImageStore(
            self.cfg.root, self.cfg.bili_image_limit, self.cfg.timezone,
            api_key=self.cfg.deepseek_key, base_url=self.cfg.deepseek_base,
        )
        self.projects = self._project_defs()
        self.current_qq = ""
        self.napcat_config_dir: Path | None = None
        self.route_var = tk.StringVar(value="")
        self.route_account_var = tk.StringVar(value="")
        self.qr_account_var = tk.StringVar(value="")
        self.access_project_var = tk.StringVar(value="青叶摩卡")
        self.mocha_private = PrivateWhitelist(self.cfg.data_dir)
        self.companion_access = CompanionAccess(
            COMPANION_ROOT / "data" / "companion.db"
        )
        self.profiles = ProfileStore(self.cfg.data_dir, self.cfg.timezone)
        self.llm = DeepSeekClient(self.cfg)
        self.private_chat = PrivateChatService(self.cfg, self.llm, self.profiles)
        self.desktop_path = Path(self.cfg.data_dir) / "desktop.json"
        desktop = self._read_desktop()
        self.napcat_url_var = tk.StringVar(
            value=str(desktop.get("napcat_url") or self.cfg.napcat_webui_url),
        )
        self.napcat_token_var = tk.StringVar(
            value=str(desktop.get("napcat_token") or self.cfg.napcat_webui_token),
        )
        self._napcat_poll = None
        self._qr_photo = None
        self._bili_login_proc = None
        self._bili_login_started = 0.0
        self._bili_qr_photo = None
        self._bili_poll = None
        self._chat_busy = False
        self.ui_queue: queue.Queue = queue.Queue()
        self.pages: dict[str, tk.Frame] = {}
        self.nav_buttons: dict[str, tk.Button] = {}
        self.current_page = "overview"
        self._build_style()
        self._build_shell()
        self._build_overview()
        self._build_chat()
        self._build_groups()
        self._build_memory()
        self._build_reminders()
        self._build_qqlogin()
        self._build_bili_login()
        self._build_routing()
        self._build_studio()
        self._build_access()
        self._build_settings()
        self.show_page("overview")
        self.refresh_all()
        self.root.after(100, self._drain_ui_queue)
        self.root.after(5000, self._auto_refresh)

    # ---------- infra ----------
    def _project_defs(self) -> list[dict]:
        companion_token = "replace-me-companion-event-token"
        env_path = COMPANION_ROOT / ".env"
        try:
            for line in env_path.read_text(encoding="utf-8-sig").splitlines():
                if line.strip().startswith("NAPCAT_EVENT_TOKEN="):
                    companion_token = line.split("=", 1)[1].strip()
                    break
        except OSError:
            pass
        return [
            {
                "key": "mocha",
                "name": "青叶摩卡httpc",
                "label": "青叶摩卡",
                "url": f"http://127.0.0.1:{self.cfg.port}/event?token={self.cfg.webhook_token}",
                "token": self.cfg.webhook_token,
            },
            {
                "key": "companion",
                "name": "陪伴工作台",
                "label": "陪伴工作台",
                "url": (
                    "http://127.0.0.1:8765/napcat/event"
                    f"?token={companion_token}"
                ),
                "token": companion_token,
            },
        ]

    def _load_groups(self) -> list[int]:
        groups = set(self.cfg.allow_groups)
        Path(self.cfg.data_dir).mkdir(parents=True, exist_ok=True)
        path = Path(self.cfg.data_dir) / "whitelist.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            groups.update(int(x) for x in data.get("groups", []))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
        for item in Path(self.cfg.data_dir).iterdir():
            if item.is_dir() and item.name.isdigit():
                groups.add(int(item.name))
        return sorted(groups)

    def store(self, gid: int) -> GroupStore:
        if gid not in self._stores:
            self._stores[gid] = GroupStore(self.cfg.data_dir, gid, self.cfg.timezone)
        return self._stores[gid]

    def memory(self, gid: int) -> MemoryStore:
        if gid not in self._memories:
            self._memories[gid] = MemoryStore(
                self.cfg.data_dir, gid, self.cfg.timezone,
            )
        return self._memories[gid]

    def selected_group(self) -> int:
        try:
            return int(self.group_var.get())
        except (TypeError, ValueError):
            return self.groups[0] if self.groups else 0

    def _run(self, args: list[str], timeout: int = 20) -> tuple[int, str]:
        try:
            result = subprocess.run(
                args, capture_output=True, text=True, timeout=timeout,
                creationflags=NO_WINDOW,
            )
            return result.returncode, (result.stdout or "") + (result.stderr or "")
        except Exception as exc:  # noqa: BLE001
            return 1, str(exc)

    def _health(self) -> dict | None:
        try:
            with urllib.request.urlopen(
                f"http://{self.cfg.host}:{self.cfg.port}/healthz", timeout=1,
            ) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            return None

    def _read_desktop(self) -> dict:
        try:
            data = json.loads(self.desktop_path.read_text(encoding="utf-8-sig"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_desktop(self) -> None:
        data = self._read_desktop()
        data["napcat_url"] = self.napcat_url_var.get().strip()
        data["napcat_token"] = self.napcat_token_var.get().strip()
        atomic_write_json(self.desktop_path, data)

    def _task_state(self) -> str:
        code, text = self._run(["schtasks", "/Query", "/TN", TASK_NAME, "/FO", "LIST"])
        if code != 0:
            return "未注册"
        for line in text.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                if key.strip() in ("Status", "状态"):
                    return value.strip()
        return "已注册"

    # ---------- style/shell ----------
    def _build_style(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "App.Treeview", background=COLORS["card"], fieldbackground=COLORS["card"],
            foreground=COLORS["ink"], rowheight=28, borderwidth=0,
            font=("Microsoft YaHei UI", 10),
        )
        style.configure(
            "App.Treeview.Heading", background="#E8F2EE",
            foreground=COLORS["ink"], relief="flat",
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        style.map("App.Treeview", background=[("selected", "#CFF3E8")])
        style.configure(
            "TButton", font=("Microsoft YaHei UI", 10),
            padding=(12, 6), borderwidth=0,
        )
        style.configure(
            "Accent.TButton", background=COLORS["accent"],
            foreground="white", font=("Microsoft YaHei UI", 10, "bold"),
        )
        style.map("Accent.TButton", background=[("active", COLORS["accent_dark"])])
        style.configure(
            "TEntry", padding=5, fieldbackground="white",
        )
        style.configure(
            "TCombobox", padding=4,
        )

    def _build_shell(self) -> None:
        sidebar = tk.Frame(self.root, bg=COLORS["sidebar"], width=228)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        tk.Label(
            sidebar, text="M", bg=COLORS["accent"], fg="white",
            font=("Microsoft YaHei UI", 30, "bold"), width=2, height=1,
        ).pack(pady=(34, 10))
        tk.Label(
            sidebar, text="青叶摩卡\n的面包坊", bg=COLORS["sidebar"],
            fg="white", font=("Microsoft YaHei UI", 19, "bold"),
            justify="center",
        ).pack()
        tk.Label(
            sidebar, text="本地控制台", bg=COLORS["sidebar"],
            fg="#8FD8C8", font=("Microsoft YaHei UI", 10),
        ).pack(pady=(4, 26))

        for key, label in (
            ("overview", "总览"),
            ("chat", "和摩卡聊天"),
            ("groups", "群管理"),
            ("memory", "长期记忆"),
            ("reminders", "提醒"),
            ("qqlogin", "QQ 扫码登录"),
            ("bililogin", "B站扫码登录"),
            ("studio", "项目设计"),
            ("access", "项目白名单"),
            ("settings", "设置"),
        ):
            button = tk.Button(
                sidebar, text=f"  {label}", anchor="w",
                bg=COLORS["sidebar"], fg="#D8F7EF",
                activebackground=COLORS["sidebar_hover"],
                activeforeground="white", relief="flat", bd=0,
                font=("Microsoft YaHei UI", 12), padx=28, pady=11,
                cursor="hand2", command=lambda k=key: self.show_page(k),
            )
            button.pack(fill="x", padx=14, pady=2)
            self.nav_buttons[key] = button

        tk.Label(
            sidebar, text="本地读取 data/ · 不需要浏览器",
            bg=COLORS["sidebar"], fg="#6FA99E",
            font=("Microsoft YaHei UI", 9), wraplength=180,
        ).pack(side="bottom", pady=24)

        main = tk.Frame(self.root, bg=COLORS["bg"])
        main.pack(side="left", fill="both", expand=True)

        header = tk.Frame(main, bg=COLORS["bg"], height=86)
        header.pack(fill="x", padx=28, pady=(20, 4))
        header.pack_propagate(False)
        self.title_label = tk.Label(
            header, text="总览", bg=COLORS["bg"], fg=COLORS["ink"],
            font=("Microsoft YaHei UI", 23, "bold"),
        )
        self.title_label.pack(side="left", anchor="w")
        self.status_label = tk.Label(
            header, text="检查中…", bg="#E6F5EF", fg=COLORS["accent_dark"],
            font=("Microsoft YaHei UI", 10, "bold"), padx=14, pady=6,
        )
        self.status_label.pack(side="right", anchor="e")

        self.body = tk.Frame(main, bg=COLORS["bg"])
        self.body.pack(fill="both", expand=True, padx=28, pady=(0, 24))

    def show_page(self, key: str) -> None:
        self.current_page = key
        titles = {
            "overview": "总览",
            "chat": "和摩卡聊天",
            "groups": "群管理",
            "memory": "长期记忆",
            "reminders": "提醒",
            "qqlogin": "QQ 扫码登录",
            "bililogin": "B站扫码登录",
            "studio": "项目设计",
            "access": "项目白名单",
            "settings": "设置",
        }
        self.title_label.configure(text=titles.get(key, "控制台"))
        for name, page in self.pages.items():
            page.pack_forget()
        self.pages[key].pack(fill="both", expand=True)
        for name, button in self.nav_buttons.items():
            button.configure(
                bg=COLORS["sidebar_hover"] if name == key else COLORS["sidebar"],
                fg="white" if name == key else "#D8F7EF",
            )
        if key == "groups":
            self._refresh_group_page()
        elif key == "memory":
            self._refresh_memory_page()
        elif key == "reminders":
            self._refresh_reminder_page()
        elif key == "chat":
            self._refresh_chat()
        elif key == "qqlogin":
            self._refresh_napcat()
            self._refresh_routing()
        elif key == "bililogin":
            self._refresh_bili_login()
        elif key == "routing":
            self._refresh_routing()
        elif key == "studio":
            self._refresh_studio()
        elif key == "access":
            self._refresh_access()
        elif key == "settings":
            self._refresh_settings()

    # ---------- card helpers ----------
    def _card(self, parent, **pack) -> tk.Frame:
        frame = tk.Frame(parent, bg=COLORS["card"], bd=0, highlightthickness=1,
                         highlightbackground=COLORS["line"])
        frame.pack(**pack)
        return frame

    def _label(self, parent, text: str, size: int = 10, bold: bool = False,
               color: str | None = None, **pack) -> tk.Label:
        label = tk.Label(
            parent, text=text, bg=parent.cget("bg"),
            fg=color or COLORS["ink"],
            font=("Microsoft YaHei UI", size, "bold" if bold else "normal"),
            justify="left", anchor="w",
        )
        label.pack(**pack)
        return label

    # ---------- overview ----------
    def _build_overview(self) -> None:
        page = tk.Frame(self.body, bg=COLORS["bg"])
        self.pages["overview"] = page

        cards = tk.Frame(page, bg=COLORS["bg"])
        cards.pack(fill="x")
        self.overview_vars = {}
        specs = [
            ("bot", "bot 状态", "—"),
            ("groups", "白名单群", "—"),
            ("entities", "设定条目", "—"),
            ("bili", "B站图库", "—"),
        ]
        for index, (key, title, value) in enumerate(specs):
            card = tk.Frame(cards, bg=COLORS["card"], highlightthickness=1,
                            highlightbackground=COLORS["line"])
            row, column = divmod(index, 2)
            card.grid(
                row=row, column=column, sticky="nsew",
                padx=(0 if column == 0 else 8, 0),
                pady=(0 if row == 0 else 8, 0),
            )
            cards.columnconfigure(column, weight=1)
            cards.rowconfigure(row, weight=1)
            tk.Label(card, text=title, bg=COLORS["card"], fg=COLORS["muted"],
                     font=("Microsoft YaHei UI", 10)).pack(anchor="w", padx=18, pady=(16, 4))
            var = tk.StringVar(value=value)
            self.overview_vars[key] = var
            tk.Label(card, textvariable=var, bg=COLORS["card"], fg=COLORS["ink"],
                     font=("Microsoft YaHei UI", 18, "bold")).pack(anchor="w", padx=18, pady=(0, 16))
        self.overview_wrap = cards

        actions = tk.Frame(page, bg=COLORS["bg"])
        actions.pack(fill="x", pady=18)
        for index, (text, command, accent) in enumerate((
            ("启动 bot", self._start_bot, True),
            ("停止 bot", self._stop_bot, False),
            ("重启 bot", self._restart_bot, False),
            ("刷新", self.refresh_all, False),
            ("打开项目目录", lambda: os.startfile(ROOT), False),
        )):
            row, column = divmod(index, 3)
            actions.columnconfigure(column, weight=1)
            ttk.Button(
                actions, text=text, command=command,
                style="Accent.TButton" if accent else "TButton",
            ).grid(
                row=row, column=column, sticky="ew",
                padx=(0 if column == 0 else 8, 0),
                pady=(0 if row == 0 else 8, 0),
            )

        info = tk.Frame(page, bg=COLORS["bg"])
        info.pack(fill="both", expand=True)
        left = tk.Frame(info, bg=COLORS["card"], highlightthickness=1,
                        highlightbackground=COLORS["line"])
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        tk.Label(left, text="运行概况", bg=COLORS["card"], fg=COLORS["ink"],
                 font=("Microsoft YaHei UI", 13, "bold")).pack(anchor="w", padx=18, pady=(16, 8))
        self.overview_detail = tk.Label(
            left, text="", bg=COLORS["card"], fg=COLORS["muted"],
            font=("Microsoft YaHei UI", 10), justify="left", anchor="nw",
        )
        self.overview_detail.pack(fill="both", expand=True, padx=18, pady=(0, 16))

        right = tk.Frame(info, bg=COLORS["card"], highlightthickness=1,
                         highlightbackground=COLORS["line"])
        right.pack(side="left", fill="both", expand=True)
        tk.Label(right, text="快捷入口", bg=COLORS["card"], fg=COLORS["ink"],
                 font=("Microsoft YaHei UI", 13, "bold")).pack(anchor="w", padx=18, pady=(16, 8))
        for text, path in (
            ("打开 help 图目录", ROOT / "assets"),
            ("打开 B站图库", ROOT / "stickers" / "bilibili"),
            ("打开日志", ROOT / "logs"),
            ("打开 config.toml", ROOT / "config.toml"),
        ):
            link = tk.Label(
                right, text=f"  {text}", bg=COLORS["card"], fg=COLORS["accent_dark"],
                font=("Microsoft YaHei UI", 10, "underline"), cursor="hand2",
            )
            link.pack(anchor="w", padx=18, pady=5)
            link.bind("<Button-1>", lambda _e, p=path: os.startfile(p))

    def refresh_all(self) -> None:
        self._refresh_overview()
        if self.current_page == "groups":
            self._refresh_group_page()
        elif self.current_page == "memory":
            self._refresh_memory_page()
        elif self.current_page == "reminders":
            self._refresh_reminder_page()

    def _refresh_overview(self) -> None:
        health = self._health()
        online = bool(health and health.get("ok"))
        self.overview_vars["bot"].set("在线" if online else "离线")
        self.status_label.configure(
            text="● 运行中" if online else "● 未运行",
            bg="#E6F5EF" if online else "#FBE9E7",
            fg=COLORS["accent_dark"] if online else "#A33B2E",
        )
        self.overview_vars["groups"].set(str(len(self.groups)))
        total_entities = 0
        total_pending = 0
        details = []
        for gid in self.groups:
            try:
                store = self.store(gid)
                canon = store.load_canon()
                entities = len(canon.get("entities", {}))
                pending = store.count_pending()
                total_entities += entities
                total_pending += pending
                details.append(f"群 {gid}：{entities} 条设定，{pending} 条待整合")
            except Exception as exc:  # noqa: BLE001
                details.append(f"群 {gid}：读取失败（{type(exc).__name__}）")
        self.overview_vars["entities"].set(str(total_entities))
        try:
            bili = self._bili.status()
            self.overview_vars["bili"].set(f"{bili['count']} / {bili['limit']}")
        except Exception:  # noqa: BLE001
            self.overview_vars["bili"].set("—")
        task = self._task_state()
        self.overview_detail.configure(
            text="\n".join([
                f"计划任务：{task}",
                f"Webhook：{self.cfg.host}:{self.cfg.port}",
                f"管理员：{'、'.join(str(x) for x in sorted(self.cfg.admins))}",
                f"可写群：{'、'.join(str(x) for x in sorted(self.cfg.write_groups)) or '所有允许群'}",
                "",
                *details,
            ])
        )

    def _start_bot(self) -> None:
        if self._health():
            self.status_label.configure(text="● 已在线", bg="#E6F5EF",
                                        fg=COLORS["accent_dark"])
            return
        self._run(["schtasks", "/Run", "/TN", TASK_NAME])
        self.root.after(2000, self._refresh_overview)

    def _stop_bot(self) -> None:
        self._run(["schtasks", "/End", "/TN", TASK_NAME])
        self.root.after(1500, self._refresh_overview)

    def _restart_bot(self) -> None:
        self._run(["schtasks", "/End", "/TN", TASK_NAME])
        time.sleep(1)
        self._run(["schtasks", "/Run", "/TN", TASK_NAME])
        self.root.after(2500, self._refresh_overview)

    # ---------- chat ----------
    def _build_chat(self) -> None:
        page = tk.Frame(self.body, bg=COLORS["bg"])
        self.pages["chat"] = page

        left = tk.Frame(page, bg=COLORS["card"], highlightthickness=1,
                        highlightbackground=COLORS["line"])
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        tk.Label(left, text="和摩卡说话", bg=COLORS["card"], fg=COLORS["ink"],
                 font=("Microsoft YaHei UI", 13, "bold")).pack(
            anchor="w", padx=16, pady=(12, 4),
        )
        tk.Label(left, text="这段对话和 QQ 私聊共用历史；设定会带到其他群。",
                 bg=COLORS["card"], fg=COLORS["muted"],
                 font=("Microsoft YaHei UI", 9)).pack(anchor="w", padx=16, pady=(0, 8))

        chat_frame = tk.Frame(left, bg=COLORS["card"])
        chat_frame.pack(fill="both", expand=True, padx=16)
        scroll = ttk.Scrollbar(chat_frame)
        scroll.pack(side="right", fill="y")
        self.chat_text = tk.Text(
            chat_frame, wrap="word", bg="#F8FCFA", fg=COLORS["ink"],
            relief="flat", padx=12, pady=10, spacing1=4, spacing3=8,
            font=("Microsoft YaHei UI", 10), state="disabled",
            yscrollcommand=scroll.set,
        )
        self.chat_text.pack(side="left", fill="both", expand=True)
        scroll.configure(command=self.chat_text.yview)
        self.chat_text.tag_configure("me", foreground=COLORS["accent_dark"],
                                     font=("Microsoft YaHei UI", 10, "bold"))
        self.chat_text.tag_configure("mocha", foreground=COLORS["ink"],
                                     font=("Microsoft YaHei UI", 10))

        entry_row = tk.Frame(left, bg=COLORS["card"])
        entry_row.pack(fill="x", padx=16, pady=12)
        self.chat_entry = tk.Text(
            entry_row, height=3, wrap="word", bg="white", fg=COLORS["ink"],
            relief="solid", bd=1, font=("Microsoft YaHei UI", 10),
        )
        self.chat_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.chat_entry.bind("<Control-Return>", lambda _e: self._send_chat())
        self.chat_send_button = ttk.Button(
            entry_row, text="发送", style="Accent.TButton", command=self._send_chat,
        )
        self.chat_send_button.pack(side="left")
        ttk.Button(left, text="清空这段对话", command=self._clear_chat).pack(
            anchor="e", padx=16, pady=(0, 12),
        )

        right = tk.Frame(page, bg=COLORS["card"], width=300,
                         highlightthickness=1, highlightbackground=COLORS["line"])
        right.pack(side="right", fill="y")
        right.pack_propagate(False)
        tk.Label(right, text="关于我的设定", bg=COLORS["card"], fg=COLORS["ink"],
                 font=("Microsoft YaHei UI", 12, "bold")).pack(
            anchor="w", padx=14, pady=(14, 2),
        )
        tk.Label(right, text="会带到所有群和私聊。", bg=COLORS["card"],
                 fg=COLORS["muted"], font=("Microsoft YaHei UI", 9)).pack(
            anchor="w", padx=14, pady=(0, 8),
        )
        self.profile_list = tk.Listbox(
            right, bg="#F8FCFA", fg=COLORS["ink"], relief="flat",
            font=("Microsoft YaHei UI", 10), selectbackground="#CFF3E8",
            selectforeground=COLORS["ink"], activestyle="none",
        )
        self.profile_list.pack(fill="both", expand=True, padx=14)
        self.profile_list.bind("<<ListboxSelect>>", lambda _e: None)
        profile_entry = tk.Frame(right, bg=COLORS["card"])
        profile_entry.pack(fill="x", padx=14, pady=(8, 0))
        self.profile_var = tk.StringVar()
        ttk.Entry(profile_entry, textvariable=self.profile_var).pack(
            fill="x", pady=(0, 6),
        )
        row = tk.Frame(profile_entry, bg=COLORS["card"])
        row.pack(fill="x")
        ttk.Button(row, text="添加", command=self._add_profile).pack(side="left")
        ttk.Button(row, text="删除选中", command=self._delete_profile).pack(
            side="left", padx=(6, 0),
        )
        self.profile_map: dict[int, int] = {}
        self._refresh_chat()

    def _append_chat(self, role: str, text: str) -> None:
        self.chat_text.configure(state="normal")
        label = "你" if role == "user" else "摩卡"
        tag = "me" if role == "user" else "mocha"
        self.chat_text.insert("end", f"{label}：", tag)
        self.chat_text.insert("end", f"{text}\n\n")
        self.chat_text.configure(state="disabled")
        self.chat_text.see("end")

    def _refresh_chat(self) -> None:
        self.chat_text.configure(state="normal")
        self.chat_text.delete("1.0", "end")
        history = self.private_chat.store.history(OWNER_QQ)
        if not history:
            self.chat_text.insert(
                "end",
                "摩卡：在呢~ 这里是只有你能看到的桌面私聊。\n"
                "可以在这边说设定，也可以直接在 QQ 私聊我。\n\n",
            )
        for item in history:
            role = item.get("role")
            if role in ("user", "assistant"):
                self._append_chat("user" if role == "user" else "assistant",
                                  str(item.get("text", "")))
        self.chat_text.configure(state="disabled")
        self._refresh_profiles()

    def _refresh_profiles(self) -> None:
        self.profile_list.delete(0, "end")
        self.profile_map.clear()
        for item in self.profiles.list(OWNER_QQ):
            index = self.profile_list.size()
            self.profile_list.insert("end", item.get("text", ""))
            self.profile_map[index] = int(item.get("id", 0))

    def _send_chat(self) -> None:
        if self._chat_busy:
            return
        text = self.chat_entry.get("1.0", "end").strip()
        if not text:
            return
        self.chat_entry.delete("1.0", "end")
        self._append_chat("user", text)
        if text.startswith(("设定", "记住")):
            content = re.sub(r"^(?:设定|记住)\s*[:：]?\s*", "", text).strip()
            violation = check_memory(content, OWNER_QQ)
            if violation:
                self._append_chat("assistant", violation)
                return
            if content:
                item = self.profiles.add(OWNER_QQ, "坂口栉耶", content, source="desktop-chat")
                self._refresh_profiles()
                self._append_chat(
                    "assistant",
                    f"记住啦，会带到其他群：{item['text']}" if item else "这条已经记过啦~",
                )
            else:
                self._append_chat("assistant", "要记住什么？")
            return
        self._chat_busy = True
        self.chat_send_button.configure(state="disabled")

        def worker() -> None:
            try:
                reply = self.private_chat.reply(OWNER_QQ, "坂口栉耶", text)
            except Exception as exc:  # noqa: BLE001
                reply = f"摩卡现在有点卡壳~（{type(exc).__name__}）"
            self.ui_queue.put(("chat_reply", reply))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_chat(self, reply: str) -> None:
        self._append_chat("assistant", reply)
        self._refresh_profiles()
        self._chat_busy = False
        self.chat_send_button.configure(state="normal")

    def _clear_chat(self) -> None:
        if not messagebox.askyesno("清空对话", "清空和摩卡的私聊历史？", parent=self.root):
            return
        self.private_chat.store.clear(OWNER_QQ)
        self._refresh_chat()

    def _add_profile(self) -> None:
        value = self.profile_var.get().strip()
        if not value:
            return
        violation = check_memory(value, OWNER_QQ)
        if violation:
            messagebox.showwarning("不能保存", violation, parent=self.root)
            return
        self.profiles.add(OWNER_QQ, "坂口栉耶", value, source="desktop")
        self.profile_var.set("")
        self._refresh_profiles()

    def _delete_profile(self) -> None:
        selection = self.profile_list.curselection()
        if not selection:
            return
        item_id = self.profile_map.get(selection[0], 0)
        if not item_id:
            return
        # 按内容删除，兼容 ProfileStore 的数字 id。
        value = self.profile_list.get(selection[0])
        if messagebox.askyesno("删除设定", f"删除「{value}」？", parent=self.root):
            self.profiles.forget(OWNER_QQ, value)
            self._refresh_profiles()

    # ---------- groups ----------

    def _group_box(self, parent) -> ttk.Combobox:
        combo = ttk.Combobox(
            parent, textvariable=self.group_var,
            values=[str(x) for x in self.groups], state="readonly", width=18,
        )
        combo.pack(side="left", padx=(0, 8))
        combo.bind("<<ComboboxSelected>>", lambda _e: self._on_group_changed())
        return combo

    def _on_group_changed(self) -> None:
        if self.current_page == "groups":
            self._refresh_group_page()
        elif self.current_page == "memory":
            self._refresh_memory_page()
        elif self.current_page == "reminders":
            self._refresh_reminder_page()

    def _build_groups(self) -> None:
        page = tk.Frame(self.body, bg=COLORS["bg"])
        self.pages["groups"] = page

        top = tk.Frame(page, bg=COLORS["bg"])
        top.pack(fill="x", pady=(0, 12))
        tk.Label(top, text="当前群", bg=COLORS["bg"], fg=COLORS["muted"],
                 font=("Microsoft YaHei UI", 10)).pack(side="left", padx=(0, 8))
        self._group_box(top)
        ttk.Button(top, text="刷新", command=self._refresh_group_page).pack(side="left")

        self.group_summary = tk.Label(
            page, text="", bg=COLORS["card"], fg=COLORS["ink"],
            font=("Microsoft YaHei UI", 10), justify="left", anchor="w",
            padx=18, pady=14, highlightthickness=1,
            highlightbackground=COLORS["line"], wraplength=1020,
        )
        self.group_summary.pack(fill="x", pady=(0, 12))

        controls = tk.Frame(page, bg=COLORS["card"], highlightthickness=1,
                            highlightbackground=COLORS["line"])
        controls.pack(fill="x", pady=(0, 12))
        inner = tk.Frame(controls, bg=COLORS["card"])
        inner.pack(fill="x", padx=18, pady=14)
        self.chat_var = tk.BooleanVar()
        self.auto_var = tk.BooleanVar()
        tk.Checkbutton(
            inner, text="允许聊天", variable=self.chat_var, bg=COLORS["card"],
            fg=COLORS["ink"], activebackground=COLORS["card"],
            font=("Microsoft YaHei UI", 10),
        ).pack(side="left", padx=(0, 18))
        tk.Checkbutton(
            inner, text="允许自动接话", variable=self.auto_var, bg=COLORS["card"],
            fg=COLORS["ink"], activebackground=COLORS["card"],
            font=("Microsoft YaHei UI", 10),
        ).pack(side="left", padx=(0, 22))
        tk.Label(inner, text="冷却(秒)", bg=COLORS["card"], fg=COLORS["muted"],
                 font=("Microsoft YaHei UI", 10)).pack(side="left", padx=(0, 5))
        self.cooldown_var = tk.StringVar()
        ttk.Entry(inner, textvariable=self.cooldown_var, width=7).pack(side="left", padx=(0, 18))
        tk.Label(inner, text="今日 chat 上限", bg=COLORS["card"], fg=COLORS["muted"],
                 font=("Microsoft YaHei UI", 10)).pack(side="left", padx=(0, 5))
        self.limit_var = tk.StringVar()
        ttk.Entry(inner, textvariable=self.limit_var, width=10).pack(side="left", padx=(0, 12))
        ttk.Button(inner, text="保存", command=self._save_group_settings).pack(side="left")

        pending_frame = tk.Frame(page, bg=COLORS["card"], highlightthickness=1,
                                 highlightbackground=COLORS["line"])
        pending_frame.pack(fill="both", expand=True, pady=(0, 12))
        head = tk.Frame(pending_frame, bg=COLORS["card"])
        head.pack(fill="x", padx=16, pady=(12, 4))
        tk.Label(head, text="待定问题", bg=COLORS["card"], fg=COLORS["ink"],
                 font=("Microsoft YaHei UI", 12, "bold")).pack(side="left")
        ttk.Button(head, text="删除选中", command=self._delete_pending).pack(side="right")
        self.pending_tree = ttk.Treeview(
            pending_frame, columns=("id", "text"), show="headings",
            style="App.Treeview", height=7,
        )
        self.pending_tree.heading("id", text="编号")
        self.pending_tree.heading("text", text="问题")
        self.pending_tree.column("id", width=80, anchor="w")
        self.pending_tree.column("text", width=700, anchor="w")
        self.pending_tree.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        broadcast = tk.Frame(page, bg=COLORS["card"], highlightthickness=1,
                             highlightbackground=COLORS["line"])
        broadcast.pack(fill="x")
        tk.Label(broadcast, text="广播到当前群", bg=COLORS["card"], fg=COLORS["ink"],
                 font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w", padx=16, pady=(12, 4))
        row = tk.Frame(broadcast, bg=COLORS["card"])
        row.pack(fill="x", padx=16, pady=(0, 14))
        self.broadcast_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.broadcast_var).pack(
            side="left", fill="x", expand=True, padx=(0, 8),
        )
        ttk.Button(row, text="发送", style="Accent.TButton",
                   command=self._send_broadcast).pack(side="left")

    def _refresh_group_page(self) -> None:
        gid = self.selected_group()
        if not gid:
            return
        try:
            store = self.store(gid)
            canon = store.load_canon()
            today = today_str(self.cfg.timezone)
            used_in, used_out = store.chat_usage(today)
            limit = store.chat_budget(self.cfg.chat_daily_token_budget, today)
            self.group_summary.configure(
                text=(
                    f"群 {gid}   实体 {len(canon.get('entities', {}))}   "
                    f"待整合 {store.count_pending()}   "
                    f"今日 chat token {used_in + used_out} / "
                    f"{'不限' if limit <= 0 else limit}   "
                    f"可写 {'是' if (not self.cfg.write_groups or gid in self.cfg.write_groups) else '否'}"
                )
            )
            self.chat_var.set(store.chat_enabled(self.cfg.chat_enabled))
            self.auto_var.set(store.auto_enabled(self.cfg.auto_speak_enabled))
            self.cooldown_var.set(str(store.chat_cooldown(self.cfg.chat_cooldown_seconds)))
            self.limit_var.set("" if limit <= 0 else str(limit))
            for item in self.pending_tree.get_children():
                self.pending_tree.delete(item)
            for qid, question in sorted(canon.get("questions", {}).items()):
                if question.get("status") == "open":
                    self.pending_tree.insert("", "end", iid=qid,
                                             values=(qid, question.get("text", "")))
        except Exception as exc:  # noqa: BLE001
            self.group_summary.configure(text=f"读取失败：{type(exc).__name__}: {exc}")

    def _save_group_settings(self) -> None:
        gid = self.selected_group()
        if not gid:
            return
        try:
            store = self.store(gid)
            store.set_state("chat_enabled", bool(self.chat_var.get()))
            store.set_state("auto_enabled", bool(self.auto_var.get()))
            store.set_state(
                "chat_cooldown", max(0, int(self.cooldown_var.get() or 0)),
            )
            value = self.limit_var.get().strip()
            if value:
                store.set_chat_budget(max(0, int(value)), today_str(self.cfg.timezone))
            else:
                store.reset_chat_budget()
            self._refresh_group_page()
            self._flash("群设置已保存")
        except ValueError:
            messagebox.showerror("保存失败", "冷却和 token 上限必须是整数。", parent=self.root)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("保存失败", str(exc), parent=self.root)

    def _delete_pending(self) -> None:
        selection = self.pending_tree.selection()
        if not selection:
            return
        qid = selection[0]
        if not messagebox.askyesno("删除待定", f"删除 {qid}？会先做快照。", parent=self.root):
            return
        gid = self.selected_group()
        store = self.store(gid)
        try:
            canon = store.load_canon()
            store.snapshot(canon)
            remove_question(canon, qid)
            store.save_canon(canon)
            store.append_changelog("控制台删除待定", [f"- {qid}"])
            self._refresh_group_page()
            self._flash(f"已删除 {qid}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("删除失败", str(exc), parent=self.root)

    def _send_broadcast(self) -> None:
        text = self.broadcast_var.get().strip()
        if not text:
            return
        gid = self.selected_group()
        sender = OneBotClient(self.cfg.onebot_api, self.cfg.onebot_token, timeout=15)
        try:
            sender.send_text(gid, text)
            self.broadcast_var.set("")
            self._flash(f"已发到群 {gid}")
        except OneBotError as exc:
            messagebox.showerror("发送失败", str(exc), parent=self.root)

    # ---------- memory ----------
    def _build_memory(self) -> None:
        page = tk.Frame(self.body, bg=COLORS["bg"])
        self.pages["memory"] = page

        top = tk.Frame(page, bg=COLORS["bg"])
        top.pack(fill="x", pady=(0, 12))
        tk.Label(top, text="群", bg=COLORS["bg"], fg=COLORS["muted"],
                 font=("Microsoft YaHei UI", 10)).pack(side="left", padx=(0, 8))
        self._group_box(top)
        ttk.Button(top, text="刷新", command=self._refresh_memory_page).pack(side="left")
        ttk.Button(top, text="清空本群记忆", command=self._clear_all_memory).pack(
            side="left", padx=(8, 0),
        )

        card = tk.Frame(page, bg=COLORS["card"], highlightthickness=1,
                        highlightbackground=COLORS["line"])
        card.pack(fill="both", expand=True, pady=(0, 12))
        self.memory_tree = ttk.Treeview(
            card, columns=("qq", "nick", "text", "time"), show="headings",
            style="App.Treeview",
        )
        for key, title, width in (
            ("qq", "QQ", 90), ("nick", "昵称", 110),
            ("text", "记忆", 460), ("time", "时间", 140),
        ):
            self.memory_tree.heading(key, text=title)
            self.memory_tree.column(key, width=width, anchor="w")
        self.memory_tree.pack(fill="both", expand=True, padx=16, pady=(16, 8))

        bottom = tk.Frame(page, bg=COLORS["bg"])
        bottom.pack(fill="x")
        ttk.Button(bottom, text="删除选中用户记忆",
                   command=self._delete_memory).pack(side="left")
        tk.Label(bottom, text="QQ", bg=COLORS["bg"], fg=COLORS["muted"],
                 font=("Microsoft YaHei UI", 10)).pack(side="left", padx=(12, 4))
        self.memory_qq = tk.StringVar()
        ttk.Entry(bottom, textvariable=self.memory_qq, width=14).pack(side="left")
        tk.Label(bottom, text="内容", bg=COLORS["bg"], fg=COLORS["muted"],
                 font=("Microsoft YaHei UI", 10)).pack(side="left", padx=(10, 4))
        self.memory_text = tk.StringVar()
        ttk.Entry(bottom, textvariable=self.memory_text).pack(
            side="left", fill="x", expand=True, padx=(0, 8),
        )
        ttk.Button(bottom, text="添加", command=self._add_memory).pack(side="left")

    def _refresh_memory_page(self) -> None:
        for item in self.memory_tree.get_children():
            self.memory_tree.delete(item)
        gid = self.selected_group()
        if not gid:
            return
        for item in self.memory(gid).list(None, 500):
            self.memory_tree.insert(
                "", "end",
                iid=str(item.get("id")),
                values=(
                    item.get("uid"), item.get("nick"),
                    short(item.get("text", ""), 80), item.get("at", ""),
                ),
            )

    def _delete_memory(self) -> None:
        selection = self.memory_tree.selection()
        if not selection:
            return
        uid = int(self.memory_tree.item(selection[0], "values")[0])
        if not messagebox.askyesno("删除记忆", f"删除 QQ {uid} 的全部长期记忆？", parent=self.root):
            return
        removed = self.memory(self.selected_group()).forget(uid, None)
        self._refresh_memory_page()
        self._flash(f"已删除 {removed} 条记忆")

    def _clear_all_memory(self) -> None:
        gid = self.selected_group()
        if not gid:
            return
        if not messagebox.askyesno("清空记忆", f"清空群 {gid} 的全部长期记忆？", parent=self.root):
            return
        memory = self.memory(gid)
        removed = 0
        for item in memory.list(None, 100000):
            removed += memory.forget(int(item.get("uid", 0)), None)
        self._refresh_memory_page()
        self._flash(f"已清空 {removed} 条记忆")

    def _add_memory(self) -> None:
        qq = self.memory_qq.get().strip()
        value = self.memory_text.get().strip()
        if not qq.isdigit() or not value:
            messagebox.showwarning("提示", "填 QQ 号和记忆内容。", parent=self.root)
            return
        self.memory(self.selected_group()).add(
            int(qq), qq, value, kind="desktop", source="desktop",
        )
        self.memory_text.set("")
        self._refresh_memory_page()
        self._flash("记忆已添加")

    # ---------- reminders ----------
    def _build_reminders(self) -> None:
        page = tk.Frame(self.body, bg=COLORS["bg"])
        self.pages["reminders"] = page

        top = tk.Frame(page, bg=COLORS["bg"])
        top.pack(fill="x", pady=(0, 12))
        tk.Label(top, text="提醒发送到群", bg=COLORS["bg"], fg=COLORS["muted"],
                 font=("Microsoft YaHei UI", 10)).pack(side="left", padx=(0, 8))
        self._group_box(top)

        card = tk.Frame(page, bg=COLORS["card"], highlightthickness=1,
                        highlightbackground=COLORS["line"])
        card.pack(fill="both", expand=True, pady=(0, 12))
        self.reminder_tree = ttk.Treeview(
            card, columns=("id", "time", "target", "text"), show="headings",
            style="App.Treeview",
        )
        for key, title, width in (
            ("id", "编号", 60), ("time", "时间", 140),
            ("target", "目标", 110), ("text", "内容", 470),
        ):
            self.reminder_tree.heading(key, text=title)
            self.reminder_tree.column(key, width=width, anchor="w")
        self.reminder_tree.pack(fill="both", expand=True, padx=16, pady=(16, 8))

        form = tk.Frame(page, bg=COLORS["card"], highlightthickness=1,
                        highlightbackground=COLORS["line"])
        form.pack(fill="x")
        tk.Label(form, text="新提醒", bg=COLORS["card"], fg=COLORS["ink"],
                 font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w", padx=16, pady=(12, 6))
        row = tk.Frame(form, bg=COLORS["card"])
        row.pack(fill="x", padx=16, pady=(0, 14))
        self.reminder_time = tk.StringVar(value="30分钟")
        self.reminder_text = tk.StringVar()
        ttk.Entry(row, textvariable=self.reminder_time, width=14).pack(side="left", padx=(0, 8))
        ttk.Entry(row, textvariable=self.reminder_text).pack(
            side="left", fill="x", expand=True, padx=(0, 8),
        )
        ttk.Button(row, text="添加", command=self._add_reminder).pack(side="left")
        ttk.Button(row, text="取消选中", command=self._cancel_reminder).pack(
            side="left", padx=(8, 0),
        )

    def _refresh_reminder_page(self) -> None:
        for item in self.reminder_tree.get_children():
            self.reminder_tree.delete(item)
        for item in self._reminders.list(None):
            due = datetime.fromtimestamp(
                float(item.get("due_at", 0)), ZoneInfo(self.cfg.timezone),
            ).strftime("%m-%d %H:%M")
            target = f"{item.get('target_type')}:{item.get('target_id')}"
            self.reminder_tree.insert(
                "", "end", iid=str(item.get("id")),
                values=(item.get("id"), due, target, item.get("text", "")),
            )

    def _add_reminder(self) -> None:
        value = self.reminder_text.get().strip()
        due = parse_reminder_time(self.reminder_time.get(), self.cfg.timezone)
        if due is None or not value:
            messagebox.showwarning("提示", "时间示例：30分钟、明天 09:00、2026-10-22 09:00", parent=self.root)
            return
        owner = sorted(self.cfg.admins)[0] if self.cfg.admins else 0
        self._reminders.add(
            owner, "group", self.selected_group(), value, due, "控制台",
        )
        self.reminder_text.set("")
        self._refresh_reminder_page()
        self._flash("提醒已添加")

    def _cancel_reminder(self) -> None:
        selection = self.reminder_tree.selection()
        if not selection:
            return
        rid = int(selection[0])
        owner = sorted(self.cfg.admins)[0] if self.cfg.admins else 0
        if self._reminders.cancel(rid, owner):
            self._refresh_reminder_page()
            self._flash("提醒已取消")

    # ---------- QQ login ----------
    def _build_qqlogin(self) -> None:
        page = tk.Frame(self.body, bg=COLORS["bg"])
        self.pages["qqlogin"] = page

        card = tk.Frame(page, bg=COLORS["card"], highlightthickness=1,
                        highlightbackground=COLORS["line"])
        card.pack(fill="both", expand=True)
        tk.Label(card, text="NapCat · QQ 扫码登录", bg=COLORS["card"],
                 fg=COLORS["ink"], font=("Microsoft YaHei UI", 16, "bold")).pack(
            anchor="w", padx=22, pady=(20, 2),
        )
        tk.Label(
            card, text="用手机 QQ 扫描二维码；登录成功后 bot 会自动连上。",
            bg=COLORS["card"], fg=COLORS["muted"],
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w", padx=22, pady=(0, 14))

        form = tk.Frame(card, bg=COLORS["card"])
        form.pack(fill="x", padx=22)
        tk.Label(form, text="WebUI 地址", bg=COLORS["card"], fg=COLORS["muted"],
                 font=("Microsoft YaHei UI", 9)).grid(row=0, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.napcat_url_var, width=40).grid(
            row=1, column=0, sticky="w", padx=(0, 12), pady=(2, 8),
        )
        tk.Label(form, text="WebUI Token", bg=COLORS["card"], fg=COLORS["muted"],
                 font=("Microsoft YaHei UI", 9)).grid(row=0, column=1, sticky="w")
        ttk.Entry(form, textvariable=self.napcat_token_var, width=28).grid(
            row=1, column=1, sticky="w", pady=(2, 8),
        )
        ttk.Button(form, text="保存地址/Token", command=self._save_napcat).grid(
            row=1, column=2, padx=(10, 0), pady=(2, 8),
        )
        ttk.Button(form, text="打开 NapCat WebUI",
                   command=lambda: webbrowser.open(self.napcat_url_var.get())).grid(
            row=1, column=3, padx=(10, 0), pady=(2, 8),
        )

        body = tk.Frame(card, bg=COLORS["card"])
        body.pack(fill="both", expand=True, padx=22, pady=(8, 20))
        left = tk.Frame(body, bg=COLORS["card"])
        left.pack(side="left", fill="y")
        self.qq_status = tk.Label(
            left, text="未检查", bg="#F8FCFA", fg=COLORS["muted"],
            font=("Microsoft YaHei UI", 11), width=38, height=3,
            justify="center", wraplength=320,
        )
        self.qq_status.pack(pady=(10, 8))
        self.qr_label = tk.Label(left, bg="white", width=260, height=260,
                                 relief="solid", bd=1)
        self.qr_label.pack()
        buttons = tk.Frame(left, bg=COLORS["card"])
        buttons.pack(pady=12)
        ttk.Button(buttons, text="获取二维码", style="Accent.TButton",
                   command=self._napcat_login).pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="检查登录状态",
                   command=self._napcat_login).pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="刷新二维码",
                   command=self._napcat_login).pack(side="left")

        right = tk.Frame(body, bg=COLORS["card"])
        right.pack(side="left", fill="both", expand=True, padx=(28, 0))
        tk.Label(right, text="怎么用", bg=COLORS["card"], fg=COLORS["ink"],
                 font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w")
        tk.Label(
            right,
            text=(
                "1. 确保 NapCat 已经启动。\n"
                "2. 点「获取二维码」。\n"
                "3. 手机 QQ 扫码，并在手机上确认。\n"
                "4. 这里显示「QQ 已登录」后，bot 会自动连上。\n\n"
                "如果显示「QQ 已登录」，说明当前 NapCat 已经在线。"
                "要换号，用下面的「切换登录 QQ」。\n\n"
                "Token 在 NapCat 的 webui.json 里；"
                "地址通常是 http://127.0.0.1:6099。"
            ),
            bg=COLORS["card"], fg=COLORS["muted"],
            font=("Microsoft YaHei UI", 10), justify="left", anchor="nw",
            wraplength=460,
        ).pack(anchor="w", pady=(8, 0))

        switch = tk.Frame(right, bg="#F8FCFA", highlightthickness=1,
                          highlightbackground=COLORS["line"])
        switch.pack(fill="x", pady=(16, 0))
        tk.Label(switch, text="切换摩卡登录 QQ（仅 6099）", bg="#F8FCFA", fg=COLORS["ink"],
                 font=("Microsoft YaHei UI", 11, "bold")).pack(
            anchor="w", padx=12, pady=(10, 2),
        )
        self.qr_account_label = tk.Label(
            switch, text="当前：检查中…", bg="#F8FCFA", fg=COLORS["muted"],
            font=("Microsoft YaHei UI", 9),
        )
        self.qr_account_label.pack(anchor="w", padx=12, pady=(0, 6))
        row = tk.Frame(switch, bg="#F8FCFA")
        row.pack(fill="x", padx=12)
        self.qr_account_combo = ttk.Combobox(
            row, textvariable=self.qr_account_var, values=[], width=16,
        )
        self.qr_account_combo.pack(side="left", padx=(0, 8))
        ttk.Button(row, text="只写配置", command=lambda: self._switch_qr_account(False)).pack(
            side="left", padx=(0, 6),
        )
        ttk.Button(row, text="切换并重启", command=lambda: self._switch_qr_account(True)).pack(
            side="left", padx=(0, 6),
        )
        ttk.Button(row, text="重启并显示扫码", command=self._restart_for_qr).pack(
            side="left",
        )
        tk.Label(
            switch,
            text="这里只切摩卡 6099；陪伴账号请在 6100 的 NapCat WebUI 管理。\n"
                 "选目标 QQ 后点「重启并显示扫码」；重启会让摩卡 NapCat 短暂离线。\n"
                 "新 QQ 第一次登录通常需要扫码，二维码会出现在左边。",
            bg="#F8FCFA", fg=COLORS["muted"],
            font=("Microsoft YaHei UI", 8), justify="left",
            wraplength=420,
        ).pack(anchor="w", padx=12, pady=(6, 10))

    def _napcat_client(self) -> NapCatWebUI:
        return NapCatWebUI(
            self.napcat_url_var.get().strip(),
            self.napcat_token_var.get().strip(),
        )

    def _save_napcat(self) -> None:
        try:
            self._save_desktop()
            self._flash("NapCat 地址/Token 已保存")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("保存失败", str(exc), parent=self.root)

    def _refresh_napcat(self) -> None:
        if not hasattr(self, "qq_status"):
            return
        self.qq_status.configure(text="正在检查 NapCat…", fg=COLORS["muted"])
        client = self._napcat_client()
        threading.Thread(
            target=self._napcat_check_worker, args=(client,), daemon=True,
        ).start()

    def _napcat_check_worker(self, client: NapCatWebUI) -> None:
        try:
            status = client.status()
            self.ui_queue.put(("napcat_status", status))
        except Exception as exc:  # noqa: BLE001
            self.ui_queue.put(("napcat_error", str(exc)))

    def _napcat_login(self) -> None:
        self.qq_status.configure(text="正在获取二维码…", fg=COLORS["muted"])
        self._qr_photo = None
        self.qr_label.configure(image="", text="")
        client = self._napcat_client()
        threading.Thread(
            target=self._napcat_login_worker, args=(client,), daemon=True,
        ).start()

    def _napcat_login_worker(self, client: NapCatWebUI) -> None:
        try:
            status = client.status()
            if status.get("isLogin"):
                self.ui_queue.put(("napcat_status", status))
                return
            qr = client.qrcode()
            if not qr:
                self.ui_queue.put(("napcat_status", status))
                return
            self.ui_queue.put(("napcat_qr", qr))
            self.ui_queue.put(("napcat_poll", None))
        except Exception as exc:  # noqa: BLE001
            self.ui_queue.put(("napcat_error", str(exc)))

    def _apply_napcat_status(self, status: dict) -> None:
        if status.get("isLogin"):
            if self._napcat_poll:
                try:
                    self.root.after_cancel(self._napcat_poll)
                except Exception:  # noqa: BLE001
                    pass
                self._napcat_poll = None
            self.qq_status.configure(
                text="✅ QQ 已登录\nNapCat 在线，bot 可以直接连。",
                fg=COLORS["accent_dark"],
            )
            self.qr_label.configure(image="", text="已登录", fg=COLORS["muted"])
            self._qr_photo = None
            return
        phase = status.get("loginPhase") or ""
        text = "等待扫码" if not phase else f"登录状态：{phase}"
        self.qq_status.configure(text=text, fg=COLORS["ink"])

    def _show_qr(self, raw: str) -> None:
        try:
            image = self._qr_image(raw)
            if image is None:
                self.qr_label.configure(
                    image="", text="二维码生成失败\n" + short(raw, 80),
                    fg=COLORS["muted"],
                )
                return
            photo = ImageTk.PhotoImage(image)
            self._qr_photo = photo
            self.qr_label.configure(image=photo, text="")
            self.qq_status.configure(
                text="请用手机 QQ 扫描二维码\n扫描后在这里确认",
                fg=COLORS["ink"],
            )
        except Exception as exc:  # noqa: BLE001
            self._napcat_error(str(exc))

    def _qr_image(self, raw: str) -> Image.Image | None:
        raw = str(raw or "").strip()
        if not raw:
            return None
        # NapCat 的 qrcode 通常是二维码内容字符串；也兼容直接给图片 base64。
        if raw.startswith("data:image"):
            raw = raw.split(",", 1)[-1]
        try:
            if len(raw) > 300:
                data = base64.b64decode(raw)
                return Image.open(BytesIO(data)).convert("RGB").resize((260, 260))
        except Exception:  # noqa: BLE001
            pass
        if qrcode is None:
            return None
        qr = qrcode.QRCode(box_size=6, border=2)
        qr.add_data(raw)
        qr.make(fit=True)
        image = qr.make_image(fill_color="#073B36", back_color="white").convert("RGB")
        return image.resize((260, 260))

    def _schedule_napcat_poll(self) -> None:
        if self._napcat_poll:
            try:
                self.root.after_cancel(self._napcat_poll)
            except Exception:  # noqa: BLE001
                pass
        self._napcat_poll = self.root.after(2500, self._poll_napcat)

    def _poll_napcat(self) -> None:
        self._napcat_poll = None
        client = self._napcat_client()
        threading.Thread(
            target=self._poll_napcat_worker, args=(client,), daemon=True,
        ).start()

    def _poll_napcat_worker(self, client: NapCatWebUI) -> None:
        try:
            status = client.status()
            self.ui_queue.put(("napcat_status", status))
            if not status.get("isLogin"):
                self.ui_queue.put(("napcat_poll", None))
        except Exception:  # noqa: BLE001
            self.ui_queue.put(("napcat_poll", None))

    def _napcat_error(self, message: str) -> None:
        self.qq_status.configure(text="登录服务不可用", fg="#A33B2E")
        self.qr_label.configure(image="", text="—", fg=COLORS["muted"])
        messagebox.showerror(
            "NapCat 登录失败",
            f"{message}\n\n请确认 NapCat 已启动，WebUI 地址和 Token 正确。",
            parent=self.root,
        )

    # ---------- Bilibili login ----------
    def _build_bili_login(self) -> None:
        page = tk.Frame(self.body, bg=COLORS["bg"])
        self.pages["bililogin"] = page

        card = tk.Frame(page, bg=COLORS["card"], highlightthickness=1,
                        highlightbackground=COLORS["line"])
        card.pack(fill="both", expand=True)
        tk.Label(card, text="B站 · 扫码登录", bg=COLORS["card"],
                 fg=COLORS["ink"], font=("Microsoft YaHei UI", 16, "bold")).pack(
            anchor="w", padx=22, pady=(20, 2),
        )
        tk.Label(
            card, text="给摩卡登录 B 站：扫码后评论、回复和定时刷视频才能用。",
            bg=COLORS["card"], fg=COLORS["muted"],
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor="w", padx=22, pady=(0, 14))

        body = tk.Frame(card, bg=COLORS["card"])
        body.pack(fill="both", expand=True, padx=22, pady=(4, 20))
        left = tk.Frame(body, bg=COLORS["card"])
        left.pack(side="left", fill="y")
        self.bili_login_status = tk.Label(
            left, text="未登录", bg="#F8FCFA", fg=COLORS["muted"],
            font=("Microsoft YaHei UI", 11), width=38, height=3,
            justify="center", wraplength=320,
        )
        self.bili_login_status.pack(pady=(10, 8))
        blank = tk.PhotoImage(width=260, height=260)
        blank.put("#FFFFFF", to=(0, 0, 260, 260))
        self._bili_qr_blank = blank
        self.bili_qr_label = tk.Label(
            left, bg="white", width=260, height=260, relief="solid", bd=1,
            image=blank, compound="center",
            text="点「获取二维码」\n用手机 B站 扫码",
            fg=COLORS["muted"], font=("Microsoft YaHei UI", 10),
        )
        self.bili_qr_label.pack()
        buttons = tk.Frame(left, bg=COLORS["card"])
        buttons.pack(pady=12)
        ttk.Button(buttons, text="获取二维码", style="Accent.TButton",
                   command=self._bili_login_start).pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="检查登录状态",
                   command=self._bili_login_check).pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="取消扫码",
                   command=self._bili_login_stop).pack(side="left")

        right = tk.Frame(body, bg=COLORS["card"])
        right.pack(side="left", fill="both", expand=True, padx=(28, 0))
        tk.Label(right, text="怎么用", bg=COLORS["card"], fg=COLORS["ink"],
                 font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w")
        tk.Label(
            right,
            text=(
                "1. 点「获取二维码」。\n"
                "2. 手机 B站 → 我的 → 扫一扫。\n"
                "3. 扫完在手机上点确认。\n"
                "4. 显示「登录成功」后，摩卡就能读字幕和评论。\n\n"
                "二维码约 180 秒有效；过期就点「获取二维码」刷新。\n"
                "登录凭证会写进 data/bili_credential.json。\n\n"
                "当前 config.toml 里 comment_enabled = false；"
                "登录成功后要把评论恢复，就把它改成 true 并重启摩卡。\n\n"
                "如果 B站 因实名/高危行为拒绝登录，控制台不会绕过，"
                "只能换一个已实名的账号或走 B站 官方申诉。"
            ),
            bg=COLORS["card"], fg=COLORS["muted"],
            font=("Microsoft YaHei UI", 10), justify="left", anchor="nw",
            wraplength=460,
        ).pack(anchor="w", pady=(8, 0))
        self.bili_login_detail = tk.Label(
            right, text="", bg=COLORS["card"], fg=COLORS["ink"],
            font=("Microsoft YaHei UI", 10), justify="left", anchor="nw",
            wraplength=460,
        )
        self.bili_login_detail.pack(anchor="w", pady=(18, 0))

    def _bili_credential_path(self) -> Path:
        return Path(self.cfg.data_dir) / "bili_credential.json"

    def _bili_credential_ok(self, path: Path | None = None) -> bool:
        path = path or self._bili_credential_path()
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return False
        return bool(
            isinstance(data, dict)
            and str(data.get("sessdata") or "").strip()
            and str(data.get("bili_jct") or "").strip()
            and str(data.get("dedeuserid") or "").strip()
        )

    def _bili_login_status_reason(self) -> str:
        path = Path(self.cfg.data_dir) / "bili_login_status.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return ""
        return str(data.get("reason") or "")

    def _refresh_bili_login(self) -> None:
        if not hasattr(self, "bili_login_status"):
            return
        path = self._bili_credential_path()
        reason = self._bili_login_status_reason()
        if path.is_file() and self._bili_credential_ok(path):
            self.bili_login_status.configure(
                text="已保存 B 站凭证\n点「检查登录状态」确认是否有效",
                fg=COLORS["ink"],
            )
            self.bili_login_detail.configure(
                text=f"凭证文件：{path}\n最后修改：{datetime.fromtimestamp(path.stat().st_mtime):%Y-%m-%d %H:%M}"
            )
        elif path.is_file():
            detail = "B站返回了不完整凭证（常见于实名/风控拦截）。"
            if reason == "empty_credential":
                detail = "B站返回空 Cookie，登录没有真正完成。\n常见原因：实名/高危行为风控。"
            self.bili_login_status.configure(
                text="凭证不完整，未登录\n请重新扫码或换已实名账号",
                fg="#A33B2E",
            )
            self.bili_login_detail.configure(
                text=detail + f"\n凭证文件：{path}"
            )
        else:
            self.bili_login_status.configure(text="未登录", fg=COLORS["muted"])
            self.bili_login_detail.configure(text="还没有 B 站登录凭证。")

    def _show_bili_qr_file(self, path: Path) -> bool:
        try:
            data = path.read_bytes()
            image = Image.open(BytesIO(data)).convert("RGB").resize((260, 260))
            photo = ImageTk.PhotoImage(image)
            self._bili_qr_photo = photo
            self.bili_qr_label.configure(image=photo, text="")
            return True
        except Exception:  # noqa: BLE001
            return False

    def _bili_login_start(self) -> None:
        self._bili_login_stop(silent=True)
        self._bili_login_started = time.time()
        self._bili_qr_photo = None
        self.bili_qr_label.configure(image=self._bili_qr_blank, text="正在生成二维码…")
        self.bili_login_status.configure(text="正在生成二维码…", fg=COLORS["muted"])
        self.bili_login_detail.configure(text="")
        script = ROOT / "scripts" / "bili_login.py"
        if not script.is_file():
            self.bili_login_status.configure(text="缺少 scripts/bili_login.py", fg="#A33B2E")
            return
        try:
            self._bili_login_proc = subprocess.Popen(
                [sys.executable, str(script)],
                cwd=str(ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=NO_WINDOW,
            )
        except Exception as exc:  # noqa: BLE001
            self.bili_login_status.configure(text=f"启动失败：{exc}", fg="#A33B2E")
            return
        self.root.after(800, self._bili_login_poll)

    def _bili_login_poll(self) -> None:
        self._bili_poll = None
        started = self._bili_login_started
        cred = self._bili_credential_path()
        qr = Path(self.cfg.data_dir) / "bili_login_qr.png"
        try:
            if cred.is_file() and cred.stat().st_mtime >= started - 2:
                if self._bili_credential_ok(cred):
                    self.bili_login_status.configure(
                        text="✅ B站登录成功\n凭证已保存，摩卡可以直接用。",
                        fg=COLORS["accent_dark"],
                    )
                    self.bili_login_detail.configure(
                        text=f"凭证文件：{cred}\n可以回到群里/私聊测试 B站 功能。"
                    )
                    self.bili_qr_label.configure(image=self._bili_qr_blank, text="登录成功", fg=COLORS["accent_dark"])
                    self._bili_qr_photo = None
                    self._bili_login_stop(silent=True)
                    return
                self.bili_login_status.configure(
                    text="登录没有真正完成\nB站返回了空凭证",
                    fg="#A33B2E",
                )
                self.bili_login_detail.configure(
                    text="常见原因：B站实名/高危行为风控。\n"
                         "旧凭证没有被空文件覆盖；可以换已实名账号再试。"
                )
                self.bili_qr_label.configure(
                    image=self._bili_qr_blank, text="登录失败", fg="#A33B2E"
                )
                self._bili_qr_photo = None
                self._bili_login_stop(silent=True)
                return
        except OSError:
            pass
        if qr.is_file() and qr.stat().st_mtime >= started - 2:
            if self._show_bili_qr_file(qr):
                self.bili_login_status.configure(
                    text="请用手机 B站 扫码\n扫完在手机上点确认",
                    fg=COLORS["ink"],
                )
        proc = self._bili_login_proc
        if proc is not None and proc.poll() is not None:
            # 脚本已退出：成功时上面已处理；否则提示过期/空凭证。
            if not (cred.is_file() and cred.stat().st_mtime >= started - 2
                    and self._bili_credential_ok(cred)):
                reason = self._bili_login_status_reason()
                if reason == "empty_credential":
                    self.bili_login_status.configure(
                        text="登录没有真正完成\nB站返回了空凭证",
                        fg="#A33B2E",
                    )
                    self.bili_login_detail.configure(
                        text="常见原因：B站实名/高危行为风控。\n"
                             "旧凭证没有被空文件覆盖；可以换已实名账号再试。"
                    )
                    self.bili_qr_label.configure(
                        image=self._bili_qr_blank, text="登录失败", fg="#A33B2E"
                    )
                else:
                    self.bili_login_status.configure(
                        text="二维码已过期或登录未完成\n点「获取二维码」重新来",
                        fg=COLORS["warn"],
                    )
                    self.bili_qr_label.configure(image=self._bili_qr_blank, text="二维码过期", fg=COLORS["muted"])
                self._bili_qr_photo = None
            return
        self._bili_poll = self.root.after(1200, self._bili_login_poll)

    def _bili_login_stop(self, silent: bool = False) -> None:
        if self._bili_poll:
            try:
                self.root.after_cancel(self._bili_poll)
            except Exception:  # noqa: BLE001
                pass
            self._bili_poll = None
        proc = self._bili_login_proc
        self._bili_login_proc = None
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:  # noqa: BLE001
                pass
        if not silent:
            self._refresh_bili_login()
            self.bili_qr_label.configure(image=self._bili_qr_blank, text="已退出登录界面", fg=COLORS["muted"])
            self._bili_qr_photo = None

    def _bili_login_check(self) -> None:
        self.bili_login_status.configure(text="正在检查 B站 登录…", fg=COLORS["muted"])
        threading.Thread(target=self._bili_check_worker, daemon=True).start()

    def _bili_check_worker(self) -> None:
        try:
            client = BiliCommenter(
                self._bili_credential_path(),
                fallback_path=Path.home() / ".dsh" / "bili-duty" / "bili_credential.json",
            )
            info = client.self_info()
            self.ui_queue.put(("bili_login_ok", info))
        except Exception as exc:  # noqa: BLE001
            self.ui_queue.put(("bili_login_error", str(exc)))

    def _apply_bili_login_ok(self, info: dict) -> None:
        self.bili_login_status.configure(
            text=f"✅ 已登录：{info.get('name') or info.get('mid')}",
            fg=COLORS["accent_dark"],
        )
        self.bili_login_detail.configure(
            text=f"B站 UID：{info.get('mid')}\n凭证有效。"
        )

    # ---------- NapCat routing ----------
    def _build_routing(self) -> None:
        page = tk.Frame(self.body, bg=COLORS["bg"])
        self.pages["routing"] = page
        tk.Label(
            page, text="双 NapCat 独立模式：本页只管摩卡（6099 / 3000）；陪伴工作台在 6100 / 3001，不再共用。",
            bg=COLORS["bg"], fg=COLORS["muted"],
            font=("Microsoft YaHei UI", 10),
        ).pack(anchor="w", pady=(0, 12))

        route_card = tk.Frame(page, bg=COLORS["card"], highlightthickness=1,
                              highlightbackground=COLORS["line"])
        route_card.pack(fill="x", pady=(0, 12))
        head = tk.Frame(route_card, bg=COLORS["card"])
        head.pack(fill="x", padx=18, pady=(16, 4))
        tk.Label(head, text="上报项目", bg=COLORS["card"], fg=COLORS["ink"],
                 font=("Microsoft YaHei UI", 13, "bold")).pack(side="left")
        self.route_status = tk.Label(
            head, text="检查中…", bg=COLORS["card"], fg=COLORS["muted"],
            font=("Microsoft YaHei UI", 10),
        )
        self.route_status.pack(side="right")

        projects_frame = tk.Frame(route_card, bg=COLORS["card"])
        projects_frame.pack(fill="x", padx=18, pady=(4, 8))
        for project in self.projects:
            text = f"{project['label']}  ·  {project['url'].split('?')[0]}"
            tk.Radiobutton(
                projects_frame, text=text, variable=self.route_var,
                value=project["key"], bg=COLORS["card"], fg=COLORS["ink"],
                activebackground=COLORS["card"], selectcolor="#E6F5EF",
                font=("Microsoft YaHei UI", 10), anchor="w",
            ).pack(anchor="w", pady=3)
        tk.Label(
            route_card,
            text="切换只改变 NapCat 的 httpClients：被选中的项目 enable=true，另一个自动停用。"
                 "不会删除任何项目数据。",
            bg=COLORS["card"], fg=COLORS["muted"],
            font=("Microsoft YaHei UI", 9), justify="left", wraplength=900,
        ).pack(anchor="w", padx=18, pady=(2, 10))
        route_buttons = tk.Frame(route_card, bg=COLORS["card"])
        route_buttons.pack(fill="x", padx=18, pady=(0, 16))
        ttk.Button(route_buttons, text="应用上报目标", style="Accent.TButton",
                   command=self._apply_route).pack(side="left")
        ttk.Button(route_buttons, text="刷新", command=self._refresh_routing).pack(
            side="left", padx=(8, 0),
        )

        account_card = tk.Frame(page, bg=COLORS["card"], highlightthickness=1,
                                highlightbackground=COLORS["line"])
        account_card.pack(fill="x")
        tk.Label(account_card, text="NapCat 登录 QQ", bg=COLORS["card"],
                 fg=COLORS["ink"], font=("Microsoft YaHei UI", 13, "bold")).pack(
            anchor="w", padx=18, pady=(16, 2),
        )
        self.route_account_label = tk.Label(
            account_card, text="当前：检查中…", bg=COLORS["card"],
            fg=COLORS["muted"], font=("Microsoft YaHei UI", 10),
        )
        self.route_account_label.pack(anchor="w", padx=18, pady=(0, 8))
        row = tk.Frame(account_card, bg=COLORS["card"])
        row.pack(fill="x", padx=18)
        self.account_combo = ttk.Combobox(
            row, textvariable=self.route_account_var, values=[], width=18,
        )
        self.account_combo.pack(side="left", padx=(0, 8))
        ttk.Button(row, text="只写配置（不重启）",
                   command=lambda: self._switch_napcat_account(False)).pack(
            side="left", padx=(0, 8),
        )
        ttk.Button(row, text="保存并重启 NapCat",
                   command=lambda: self._switch_napcat_account(True)).pack(
            side="left",
        )
        tk.Label(
            account_card,
            text="切换的是 NapCat 登录的机器人 QQ，不是群友 QQ。"
                 "新 QQ 第一次登录可能需要扫码；重启期间 bot 会短暂离线。",
            bg=COLORS["card"], fg=COLORS["muted"],
            font=("Microsoft YaHei UI", 9), justify="left", wraplength=900,
        ).pack(anchor="w", padx=18, pady=(10, 16))
        self._refresh_routing()

    def _refresh_routing(self) -> None:
        if not hasattr(self, "route_status"):
            return
        threading.Thread(target=self._routing_worker, daemon=True).start()

    def _routing_worker(self) -> None:
        try:
            sender = OneBotClient(self.cfg.onebot_api, self.cfg.onebot_token, timeout=8)
            info = sender.get_login_info()
            qq = str(info.get("user_id") or "")
            config_dir = find_config_dir()
            accounts = list_accounts(config_dir)
            labels = {item: item for item in accounts}
            try:
                web = NapCatWebUI(
                    self.cfg.napcat_webui_url,
                    self.cfg.napcat_webui_token,
                )
                for item in web.quick_login_list():
                    account = str(item.get("uin") or "").strip()
                    if account:
                        accounts.append(account)
                        labels[account] = (
                            f"{account} · {item.get('nickName') or 'QQ'}"
                        )
            except Exception:  # noqa: BLE001
                pass
            accounts = sorted(set(accounts))
            display = [labels.get(item, item) for item in accounts]
            path = config_dir / f"onebot11_{qq}.json"
            active = active_from_config(path, self.projects) if qq else ""
            self.ui_queue.put(("routing_state", {
                "qq": qq,
                "accounts": accounts,
                "account_labels": display,
                "active": active,
                "config_dir": str(config_dir),
            }))
        except Exception as exc:  # noqa: BLE001
            self.ui_queue.put(("routing_error", str(exc)))

    def _apply_route(self) -> None:
        active = self.route_var.get()
        if not self.napcat_config_dir or not self.current_qq:
            messagebox.showwarning("提示", "还没读到当前 NapCat QQ，先刷新。", parent=self.root)
            return
        if active not in {p["key"] for p in self.projects}:
            messagebox.showwarning("提示", "先选择一个上报项目。", parent=self.root)
            return
        if not messagebox.askyesno(
            "切换上报目标",
            f"切换后只有「{self._project_label(active)}」接收 QQ 事件，"
            "另一个项目会自动停用。\n\n继续？",
            parent=self.root,
        ):
            return
        config_dir = self.napcat_config_dir
        qq = self.current_qq
        self.route_status.configure(text="正在应用…", fg=COLORS["muted"])

        def worker() -> None:
            try:
                result = apply_projects(
                    config_dir, qq, self.projects, active,
                    self.cfg.napcat_webui_url, self.cfg.napcat_webui_token,
                )
                self.ui_queue.put(("routing_result", {
                    "message": f"已切换到「{self._project_label(active)}」",
                    "result": result,
                }))
            except Exception as exc:  # noqa: BLE001
                self.ui_queue.put(("routing_error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _project_label(self, key: str) -> str:
        for project in self.projects:
            if project["key"] == key:
                return project["label"]
        return key

    def _switch_napcat_account(self, restart: bool) -> None:
        raw = self.route_account_var.get().strip()
        match = re.search(r"(?<!\d)(\d{5,12})(?!\d)", raw)
        target = match.group(1) if match else ""
        if not target:
            messagebox.showwarning("提示", "填 5-12 位 QQ 号，或从下拉框选择。", parent=self.root)
            return
        if restart and not messagebox.askyesno(
            "切换登录 QQ",
            f"将 NapCat 登录 QQ 切到 {target} 并重启？\n\n"
            "NapCat 和 bot 会短暂离线；新 QQ 可能需要扫码。",
            parent=self.root,
        ):
            return
        if not self.napcat_config_dir or not self.current_qq:
            messagebox.showwarning("提示", "还没读到当前 NapCat 状态，先刷新。", parent=self.root)
            return
        config_dir = self.napcat_config_dir
        current = self.current_qq
        active = self.route_var.get()
        if not active:
            active = active_from_config(
                config_dir / f"onebot11_{current}.json", self.projects,
            ) or "mocha"
        self.route_status.configure(text="正在准备账号配置…", fg=COLORS["muted"])

        def worker() -> None:
            try:
                result = switch_account(
                    config_dir, target, current, self.projects, active,
                    restart=restart,
                )
                message = (
                    f"已准备 QQ {target} 的配置"
                    + ("，正在重启 NapCat。" if result.get("restart_started") else "。")
                )
                self.ui_queue.put(("routing_result", {
                    "message": message, "result": result,
                }))
            except Exception as exc:  # noqa: BLE001
                self.ui_queue.put(("routing_error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _switch_qr_account(self, restart: bool) -> None:
        self._preserve_active_route()
        self.route_account_var.set(self.qr_account_var.get().strip())
        self._switch_napcat_account(restart)

    def _preserve_active_route(self) -> None:
        """换 QQ 不改项目路由；以当前 onebot 配置为准。"""
        if not self.napcat_config_dir or not self.current_qq:
            return
        active = active_from_config(
            self.napcat_config_dir / f"onebot11_{self.current_qq}.json",
            self.projects,
        )
        if active:
            self.route_var.set(active)

    def _restart_for_qr(self) -> None:
        self._preserve_active_route()
        raw = self.qr_account_var.get().strip()
        match = re.search(r"(?<!\d)(\d{5,12})(?!\d)", raw)
        if not match:
            messagebox.showwarning(
                "提示", "先选择或输入要登录的 QQ 号。", parent=self.root,
            )
            return
        target = match.group(1)
        self.route_account_var.set(target)
        self._switch_napcat_account(True)
        # NapCat 重启有延迟：多次尝试，等 QQ 进入未登录状态后取二维码。
        for delay in (8000, 13000, 19000):
            self.root.after(delay, self._napcat_login)

    def _apply_routing_state(self, payload: dict) -> None:
        self.current_qq = str(payload.get("qq") or "")
        self.napcat_config_dir = Path(payload["config_dir"]) if payload.get("config_dir") else None
        accounts = [str(x) for x in payload.get("accounts") or []]
        display = [str(x) for x in payload.get("account_labels") or accounts]
        self.account_combo.configure(values=display)
        if hasattr(self, "qr_account_combo"):
            self.qr_account_combo.configure(values=display)
        if self.current_qq and not self.route_account_var.get():
            self.route_account_var.set(self.current_qq)
        if hasattr(self, "qr_account_label"):
            self.qr_account_label.configure(
                text=f"当前：{self.current_qq or '未识别'}",
            )
        if self.current_qq and hasattr(self, "qr_account_combo") and not self.qr_account_var.get():
            self.qr_account_var.set(self.current_qq)
        active = str(payload.get("active") or "")
        if active:
            self.route_var.set(active)
        elif not self.route_var.get():
            self.route_var.set("mocha")
        label = self._project_label(active) if active else "未识别"
        self.route_status.configure(
            text=f"当前上报：{label}", fg=COLORS["accent_dark"],
        )
        if hasattr(self, "studio_route_label"):
            self.studio_route_label.configure(
                text=f"摩卡 6099 / 3000 · QQ {self.current_qq or '未登录'}",
            )
        self.route_account_label.configure(
            text=f"当前：{self.current_qq or '未识别'}  ·  配置目录：{self.napcat_config_dir or '—'}",
        )

    # ---------- companion studio ----------
    def _route_to(self, key: str) -> None:
        self.route_var.set(key)
        self._apply_route()

    def _build_studio(self) -> None:
        page = tk.Frame(self.body, bg=COLORS["bg"])
        self.pages["studio"] = page
        card = tk.Frame(page, bg=COLORS["card"], highlightthickness=1,
                        highlightbackground=COLORS["line"])
        card.pack(fill="x", pady=(0, 12))
        tk.Label(card, text="陪伴工作台", bg=COLORS["card"], fg=COLORS["ink"],
                 font=("Microsoft YaHei UI", 18, "bold")).pack(
            anchor="w", padx=22, pady=(20, 2),
        )
        tk.Label(
            card, text="已并入当前项目，代码在 companion/，数据仍在它自己的数据库里。",
            bg=COLORS["card"], fg=COLORS["muted"],
            font=("Microsoft YaHei UI", 10),
        ).pack(anchor="w", padx=22, pady=(0, 12))
        self.studio_status = tk.Label(
            card, text="检查中…", bg="#F8FCFA", fg=COLORS["muted"],
            font=("Microsoft YaHei UI", 12), padx=16, pady=14,
            anchor="w", justify="left",
        )
        self.studio_status.pack(fill="x", padx=22, pady=(0, 12))
        row = tk.Frame(card, bg=COLORS["card"])
        row.pack(fill="x", padx=22, pady=(0, 18))
        ttk.Button(row, text="打开陪伴工作台", style="Accent.TButton",
                   command=lambda: webbrowser.open(
                       f"http://127.0.0.1:{COMPANION_PORT}/"
                   )).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="打开机器人设定",
                   command=lambda: webbrowser.open(
                       f"http://127.0.0.1:{COMPANION_PORT}/settings"
                   )).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="启动", command=self._start_studio).pack(
            side="left", padx=(0, 8),
        )
        ttk.Button(row, text="停止", command=self._stop_studio).pack(
            side="left", padx=(0, 8),
        )
        ttk.Button(row, text="重启", command=self._restart_studio).pack(
            side="left",
        )
        route_row = tk.Frame(card, bg=COLORS["card"])
        route_row.pack(fill="x", padx=22, pady=(0, 16))
        tk.Label(route_row, text="双 NapCat 独立运行：", bg=COLORS["card"],
                 fg=COLORS["muted"], font=("Microsoft YaHei UI", 9)).pack(
            side="left",
        )
        self.studio_route_label = tk.Label(
            route_row, text="摩卡 6099 / 3000 · QQ 3826300285",
            bg=COLORS["card"], fg=COLORS["ink"],
            font=("Microsoft YaHei UI", 9, "bold"),
        )
        self.studio_route_label.pack(side="left", padx=(0, 12))
        tk.Label(
            route_row, text="陪伴 6100 / 3001 · QQ 3848406242",
            bg=COLORS["card"], fg=COLORS["accent_dark"],
            font=("Microsoft YaHei UI", 9, "bold"),
        ).pack(side="left", padx=(0, 10))
        ttk.Button(
            route_row, text="打开陪伴 NapCat",
            command=lambda: webbrowser.open(COMPANION_NAPCAT_WEBUI),
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            route_row, text="项目白名单",
            command=lambda: self.show_page("access"),
        ).pack(side="left")

        info = tk.Frame(page, bg=COLORS["card"], highlightthickness=1,
                        highlightbackground=COLORS["line"])
        info.pack(fill="both", expand=True)
        tk.Label(info, text="项目设计入口", bg=COLORS["card"], fg=COLORS["ink"],
                 font=("Microsoft YaHei UI", 13, "bold")).pack(
            anchor="w", padx=20, pady=(16, 6),
        )
        tk.Label(
            info,
            text=(
                "陪伴工作台是一个独立的 Web 控制台：\n"
                "  · 角色 / system prompt / 开场白 / 模型参数\n"
                "  · 长期记忆、今日运势、亲密度\n"
                "  · 登录账号和两套角色卡\n\n"
                "它不是摩卡的人格，也不会复用摩卡数据。\n"
                "如果要让它接收 QQ 私聊，去「NapCat 路由」把上报目标切到陪伴工作台；"
                "同一时刻只会有一个项目接收。"
            ),
            bg=COLORS["card"], fg=COLORS["muted"],
            font=("Microsoft YaHei UI", 10), justify="left", anchor="nw",
            wraplength=900,
        ).pack(anchor="w", padx=20, pady=(0, 14))
        links = tk.Frame(info, bg=COLORS["card"])
        links.pack(fill="x", padx=20, pady=(0, 18))
        for text, command in (
            ("打开 companion 目录", lambda: os.startfile(COMPANION_ROOT)),
            ("打开 README", lambda: os.startfile(COMPANION_ROOT / "README.md")),
            ("打开角色资料", lambda: os.startfile(
                COMPANION_ROOT / "design" / "character_bible.md"
            )),
            ("打开陪伴 NapCat", lambda: webbrowser.open(COMPANION_NAPCAT_WEBUI)),
        ):
            ttk.Button(links, text=text, command=command).pack(
                side="left", padx=(0, 8),
            )
        self._refresh_studio()

    def _studio_health(self) -> bool:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{COMPANION_PORT}/login", timeout=2,
            ) as response:
                return response.status == 200
        except Exception:  # noqa: BLE001
            return False

    def _refresh_studio(self) -> None:
        if not hasattr(self, "studio_status"):
            return
        threading.Thread(target=self._studio_worker, daemon=True).start()

    def _studio_worker(self) -> None:
        online = self._studio_health()
        self.ui_queue.put(("studio_state", {"online": online}))

    def _apply_studio_state(self, payload: dict) -> None:
        online = bool(payload.get("online"))
        self.studio_status.configure(
            text=(
                "● 在线 · http://127.0.0.1:8765\n"
                f"项目目录：{COMPANION_ROOT}\n"
                "数据：companion/data/companion.db"
                if online else
                "○ 未运行\n"
                f"项目目录：{COMPANION_ROOT}\n"
                "点「启动」后会打开 8765 控制台。"
            ),
            fg=COLORS["accent_dark"] if online else COLORS["muted"],
        )

    def _start_studio(self) -> None:
        if self._studio_health():
            self._flash("陪伴工作台已经在线")
            return
        if not (COMPANION_ROOT / "app.py").exists():
            messagebox.showerror("启动失败", f"找不到 {COMPANION_ROOT / 'app.py'}", parent=self.root)
            return
        python = Path(sys.executable)
        if python.name.lower() == "pythonw.exe":
            candidate = python.with_name("python.exe")
            if candidate.exists():
                python = candidate
        subprocess.Popen(
            [str(python), str(COMPANION_ROOT / "app.py"), "--no-open"],
            cwd=str(COMPANION_ROOT),
            creationflags=NO_WINDOW,
        )
        self._flash("陪伴工作台启动中…")
        self.root.after(2500, self._refresh_studio)

    def _stop_studio(self) -> None:
        if not messagebox.askyesno(
            "停止陪伴工作台",
            "停止 8765 的陪伴工作台？\n摩卡 bot 和 NapCat 不会受影响。",
            parent=self.root,
        ):
            return
        script = (
            "Get-CimInstance Win32_Process | Where-Object { "
            "($_.Name -eq 'python.exe' -or $_.Name -eq 'pythonw.exe') -and "
            "$_.CommandLine -like '*companion*app.py*' } | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
        )
        self._run(["powershell", "-NoProfile", "-Command", script])
        self._flash("陪伴工作台已停止")
        self.root.after(800, self._refresh_studio)

    def _restart_studio(self) -> None:
        self._stop_studio()
        self.root.after(1200, self._start_studio)

    # ---------- project access ----------
    def _build_access(self) -> None:
        page = tk.Frame(self.body, bg=COLORS["bg"])
        self.pages["access"] = page
        top = tk.Frame(page, bg=COLORS["bg"])
        top.pack(fill="x", pady=(0, 10))
        tk.Label(top, text="项目", bg=COLORS["bg"], fg=COLORS["muted"],
                 font=("Microsoft YaHei UI", 10)).pack(side="left", padx=(0, 8))
        combo = ttk.Combobox(
            top, textvariable=self.access_project_var,
            values=["青叶摩卡", "陪伴工作台"], state="readonly", width=18,
        )
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_access())
        ttk.Button(top, text="刷新", command=self._refresh_access).pack(
            side="left", padx=(8, 0),
        )

        cards = tk.Frame(page, bg=COLORS["bg"])
        cards.pack(fill="both", expand=True)
        private_card = tk.Frame(cards, bg=COLORS["card"], highlightthickness=1,
                                highlightbackground=COLORS["line"])
        private_card.pack(side="left", fill="both", expand=True, padx=(0, 8))
        group_card = tk.Frame(cards, bg=COLORS["card"], highlightthickness=1,
                              highlightbackground=COLORS["line"])
        group_card.pack(side="left", fill="both", expand=True)

        tk.Label(private_card, text="私人账号白名单", bg=COLORS["card"],
                 fg=COLORS["ink"], font=("Microsoft YaHei UI", 13, "bold")).pack(
            anchor="w", padx=16, pady=(14, 2),
        )
        tk.Label(private_card, text="只允许名单里的 QQ 私聊；管理员始终可用。",
                 bg=COLORS["card"], fg=COLORS["muted"],
                 font=("Microsoft YaHei UI", 9)).pack(anchor="w", padx=16)
        self.access_private_var = tk.BooleanVar()
        self.access_private_check = tk.Checkbutton(
            private_card, text="启用私聊白名单", variable=self.access_private_var,
            bg=COLORS["card"], fg=COLORS["ink"], activebackground=COLORS["card"],
            command=self._toggle_access_private,
        )
        self.access_private_check.pack(anchor="w", padx=16, pady=(8, 4))
        self.access_private_list = tk.Listbox(
            private_card, bg="#F8FCFA", relief="flat", height=10,
            font=("Microsoft YaHei UI", 10),
        )
        self.access_private_list.pack(fill="both", expand=True, padx=16, pady=(4, 6))
        p_row = tk.Frame(private_card, bg=COLORS["card"])
        p_row.pack(fill="x", padx=16, pady=(0, 14))
        self.access_private_entry = tk.StringVar()
        ttk.Entry(p_row, textvariable=self.access_private_entry, width=16).pack(
            side="left", padx=(0, 6),
        )
        ttk.Button(p_row, text="添加", command=self._add_access_private).pack(
            side="left", padx=(0, 6),
        )
        ttk.Button(p_row, text="移除选中",
                   command=self._remove_access_private).pack(side="left")

        tk.Label(group_card, text="群白名单", bg=COLORS["card"],
                 fg=COLORS["ink"], font=("Microsoft YaHei UI", 13, "bold")).pack(
            anchor="w", padx=16, pady=(14, 2),
        )
        self.access_group_note = tk.Label(
            group_card, text="", bg=COLORS["card"], fg=COLORS["muted"],
            font=("Microsoft YaHei UI", 9), justify="left", wraplength=440,
        )
        self.access_group_note.pack(anchor="w", padx=16)
        self.access_group_var = tk.BooleanVar()
        self.access_group_check = tk.Checkbutton(
            group_card, text="启用群白名单", variable=self.access_group_var,
            bg=COLORS["card"], fg=COLORS["ink"], activebackground=COLORS["card"],
            command=self._toggle_access_group,
        )
        self.access_group_check.pack(anchor="w", padx=16, pady=(8, 4))
        self.access_group_list = tk.Listbox(
            group_card, bg="#F8FCFA", relief="flat", height=10,
            font=("Microsoft YaHei UI", 10),
        )
        self.access_group_list.pack(fill="both", expand=True, padx=16, pady=(4, 6))
        g_row = tk.Frame(group_card, bg=COLORS["card"])
        g_row.pack(fill="x", padx=16, pady=(0, 14))
        self.access_group_entry = tk.StringVar()
        ttk.Entry(g_row, textvariable=self.access_group_entry, width=16).pack(
            side="left", padx=(0, 6),
        )
        ttk.Button(g_row, text="添加", command=self._add_access_group).pack(
            side="left", padx=(0, 6),
        )
        ttk.Button(g_row, text="移除选中",
                   command=self._remove_access_group).pack(side="left")
        self._refresh_access()

    def _access_key(self) -> str:
        return "companion" if self.access_project_var.get() == "陪伴工作台" else "mocha"

    def _refresh_access(self) -> None:
        if not hasattr(self, "access_private_list"):
            return
        self.access_private_list.delete(0, "end")
        self.access_group_list.delete(0, "end")
        if self._access_key() == "mocha":
            enabled = self.mocha_private.enabled()
            self.access_private_var.set(enabled)
            for qq in self.mocha_private.users():
                self.access_private_list.insert("end", qq)
            base = sorted(self.cfg.allow_groups)
            extra = load_extra_groups(self.cfg.data_dir)
            for gid in base:
                self.access_group_list.insert("end", f"{gid}  ·  配置基础群")
            for gid in extra:
                if gid not in base:
                    self.access_group_list.insert("end", f"{gid}  ·  白名单")
            self.access_group_var.set(True)
            self.access_group_check.configure(state="disabled")
            self.access_group_note.configure(
                text="摩卡按 config.toml 的 allow_groups + 这里新增的群工作。"
                     "基础群不能在这里移除；新增群会对下一条消息立即生效。"
            )
        else:
            self.access_private_var.set(self.companion_access.private_enabled())
            for item in self.companion_access.private_list():
                note = f"  ·  {item['note']}" if item.get("note") else ""
                self.access_private_list.insert("end", f"{item['qq']}{note}")
            self.access_group_var.set(self.companion_access.group_enabled())
            self.access_group_check.configure(state="normal")
            for item in self.companion_access.group_list():
                note = f"  ·  {item['note']}" if item.get("note") else ""
                self.access_group_list.insert("end", f"{item['group_id']}{note}")
            self.access_group_note.configure(
                text="陪伴工作台：开启后只回应名单里的群；@ 或在消息里叫角色名才回复。"
            )

    def _toggle_access_private(self) -> None:
        try:
            if self._access_key() == "mocha":
                self.mocha_private.set_enabled(self.access_private_var.get())
            else:
                self.companion_access.set_private_enabled(self.access_private_var.get())
            self._flash("私聊白名单已更新")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("保存失败", str(exc), parent=self.root)

    def _toggle_access_group(self) -> None:
        if self._access_key() != "companion":
            return
        try:
            self.companion_access.set_group_enabled(self.access_group_var.get())
            self._flash("群白名单已更新")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("保存失败", str(exc), parent=self.root)

    def _add_access_private(self) -> None:
        raw = self.access_private_entry.get().strip()
        match = re.search(r"\d{5,12}", raw)
        if not match:
            messagebox.showwarning("提示", "填 5-12 位 QQ 号。", parent=self.root)
            return
        qq = match.group(0)
        try:
            if self._access_key() == "mocha":
                self.mocha_private.add(qq)
            else:
                self.companion_access.add_private(qq)
            self.access_private_entry.set("")
            self._refresh_access()
            self._flash(f"已加入私聊白名单：{qq}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("添加失败", str(exc), parent=self.root)

    def _remove_access_private(self) -> None:
        selection = self.access_private_list.curselection()
        if not selection:
            return
        text = self.access_private_list.get(selection[0])
        qq = re.search(r"\d{5,12}", text)
        if not qq:
            return
        if self._access_key() == "mocha":
            self.mocha_private.remove(qq.group(0))
        else:
            self.companion_access.remove_private(qq.group(0))
        self._refresh_access()

    def _add_access_group(self) -> None:
        raw = self.access_group_entry.get().strip()
        match = re.search(r"\d{5,12}", raw)
        if not match:
            messagebox.showwarning("提示", "填 5-12 位群号。", parent=self.root)
            return
        gid = int(match.group(0))
        try:
            if self._access_key() == "mocha":
                if gid in self.cfg.allow_groups:
                    self._flash("这已经是配置基础群")
                    return
                extra = load_extra_groups(self.cfg.data_dir)
                if gid not in extra:
                    extra.append(gid)
                    save_extra_groups(self.cfg.data_dir, extra)
            else:
                self.companion_access.add_group(str(gid))
            self.access_group_entry.set("")
            self._refresh_access()
            self._flash(f"已加入群白名单：{gid}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("添加失败", str(exc), parent=self.root)

    def _remove_access_group(self) -> None:
        selection = self.access_group_list.curselection()
        if not selection:
            return
        text = self.access_group_list.get(selection[0])
        match = re.search(r"\d{5,12}", text)
        if not match:
            return
        gid = int(match.group(0))
        if self._access_key() == "mocha":
            if gid in self.cfg.allow_groups:
                messagebox.showwarning(
                    "不能移除", "这是 config.toml 的基础群；请改 config.toml。",
                    parent=self.root,
                )
                return
            extra = [x for x in load_extra_groups(self.cfg.data_dir) if x != gid]
            save_extra_groups(self.cfg.data_dir, extra)
        else:
            self.companion_access.remove_group(str(gid))
        self._refresh_access()

    # ---------- settings ----------


    def _build_settings(self) -> None:
        page = tk.Frame(self.body, bg=COLORS["bg"])
        self.pages["settings"] = page
        card = tk.Frame(page, bg=COLORS["card"], highlightthickness=1,
                        highlightbackground=COLORS["line"])
        card.pack(fill="both", expand=True)
        self.settings_text = tk.Label(
            card, text="", bg=COLORS["card"], fg=COLORS["ink"],
            font=("Microsoft YaHei UI", 10), justify="left", anchor="nw",
        )
        self.settings_text.pack(fill="both", expand=True, padx=22, pady=22)
        row = tk.Frame(card, bg=COLORS["card"])
        row.pack(fill="x", padx=22, pady=(0, 20))
        for text, path in (
            ("打开 config.toml", ROOT / "config.toml"),
            ("打开 .env", ROOT / ".env"),
            ("打开 data", ROOT / "data"),
            ("打开 README", ROOT / "README.md"),
        ):
            ttk.Button(row, text=text, command=lambda p=path: os.startfile(p)).pack(
                side="left", padx=(0, 8),
            )

    def _refresh_settings(self) -> None:
        try:
            bili = self._bili.status()
        except Exception:  # noqa: BLE001
            bili = {"count": 0, "limit": 0, "path": ""}
        self.settings_text.configure(
            text="\n".join([
                f"项目目录：{ROOT}",
                f"数据目录：{self.cfg.data_dir}",
                f"管理员：{'、'.join(str(x) for x in sorted(self.cfg.admins)) or '（空）'}",
                f"允许群：{'、'.join(str(x) for x in self.groups) or '（空）'}",
                f"可写群：{'、'.join(str(x) for x in sorted(self.cfg.write_groups)) or '所有允许群'}",
                f"计划任务：{TASK_NAME}（{self._task_state()}）",
                f"B站图库：{bili['count']} / {bili['limit']}",
                f"图库目录：{bili['path']}",
                "",
                "这个控制台直接读写本地 data/ 和 config.toml，",
                "适合单机使用；如果以后做多用户产品，需要改成带登录的后台服务。",
            ])
        )

    # ---------- helpers ----------
    def _drain_ui_queue(self) -> None:
        while True:
            try:
                kind, payload = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                if kind == "chat_reply":
                    self._finish_chat(str(payload))
                elif kind == "napcat_status":
                    self._apply_napcat_status(payload)
                elif kind == "napcat_qr":
                    self._show_qr(str(payload))
                elif kind == "napcat_poll":
                    self._schedule_napcat_poll()
                elif kind == "napcat_error":
                    self._napcat_error(str(payload))
                elif kind == "bili_login_ok":
                    self._apply_bili_login_ok(payload)
                elif kind == "bili_login_error":
                    self.bili_login_status.configure(
                        text=f"B站 登录不可用\n{str(payload)[:120]}",
                        fg="#A33B2E",
                    )
                elif kind == "routing_state":
                    self._apply_routing_state(payload)
                elif kind == "routing_result":
                    self.route_status.configure(
                        text=payload.get("message", "完成"),
                        fg=COLORS["accent_dark"],
                    )
                    self._flash(payload.get("message", "完成"))
                    self._refresh_routing()
                    self._refresh_studio()
                elif kind == "routing_error":
                    self.route_status.configure(text="操作失败", fg="#A33B2E")
                    messagebox.showerror("NapCat 操作失败", str(payload), parent=self.root)
                elif kind == "studio_state":
                    self._apply_studio_state(payload)
            except Exception:  # noqa: BLE001
                pass
        self.root.after(100, self._drain_ui_queue)

    def _flash(self, text: str) -> None:
        self.status_label.configure(text=f"● {text}", bg="#E6F5EF",
                                    fg=COLORS["accent_dark"])
        self.root.after(2500, self._refresh_overview)

    def _auto_refresh(self) -> None:
        try:
            self._refresh_overview()
            if self.current_page == "settings":
                self._refresh_settings()
        except Exception:  # noqa: BLE001
            pass
        self.root.after(5000, self._auto_refresh)

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    root = tk.Tk()
    app = MochaControlPanel(root)
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
