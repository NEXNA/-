"""不连 QQ、不连 DeepSeek 的端到端演示。

启动一个假的 NapCat HTTP API 和一个真实的 bot webhook 服务，
用规则版“假模型”走一遍：添加 → 整合 → 冲突 → 裁决 → 查询 → 导出。

运行：
    python tools/demo.py
"""
from __future__ import annotations

import json
import shutil
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bot.commands import Bot  # noqa: E402
from bot.config import Config  # noqa: E402
from bot.server import EventServer  # noqa: E402

GROUP = 123
ADMIN = 1
SELF_ID = 999
API_PORT = 13000
HOOK_PORT = 18080


class FakeNapCat(BaseHTTPRequestHandler):
    replies: list[str] = []
    files: list[str] = []
    counter = 0

    def _json(self, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        params = json.loads(self.rfile.read(length) or b"{}")
        action = self.path.lstrip("/")
        type(self).counter += 1
        if action == "send_group_msg":
            text = "".join(
                str(seg.get("data", {}).get("text", ""))
                for seg in params.get("message", [])
                if seg.get("type") == "text"
            )
            type(self).replies.append(text)
            print(f"\n机器人 > {text}")
        elif action == "upload_group_file":
            type(self).files.append(str(params.get("name")))
            print(f"\n[群文件] {params.get('name')}")
        self._json({"status": "ok", "retcode": 0,
                    "data": {"message_id": str(type(self).counter)}})

    def log_message(self, fmt, *args):
        return


class RuleLLM:
    """只认演示里的几个关键词，替代真实 DeepSeek。"""

    def extract(self, canon, batch, context):
        entities = []
        relation = None
        if any("老周" in e["text"] for e in batch):
            relation = {"to": "老周", "kind": "师徒"}
            entities.append({
                "type": "character", "name": "老周", "aliases": [],
                "fields": {"身份": "前哨站站长"}, "relations": [],
                "source_ids": [next(e["id"] for e in batch if "老周" in e["text"])],
            })
        for entry in batch:
            if "林晚" not in entry["text"]:
                continue
            fields = {"身份": "前哨站医师"}
            if "二十四" in entry["text"]:
                fields["年龄"] = "24"
            entities.append({
                "type": "character", "name": "林晚", "aliases": ["晚姐"],
                "fields": fields,
                "relations": [relation] if relation else [],
                "source_ids": [entry["id"]],
            })
        conflicts = []
        for entry in batch:
            if "二十七" in entry["text"]:
                source_24 = next(
                    (e["id"] for e in batch if "二十四" in e["text"]), entry["id"]
                )
                conflicts.append({
                    "entity": "林晚", "field": "年龄",
                    "values": [
                        {"value": "24", "source_ids": [source_24]},
                        {"value": "27", "source_ids": [entry["id"]]},
                    ],
                    "question": "林晚到底几岁？",
                })
        return {"entities": entities, "conflicts": conflicts,
                "open_questions": []}, {"input": 500, "output": 80}

    def chat(self, messages, max_tokens=None):
        return "诶~ 那就瘫一会儿嘛~ 反正地球少转一圈也不会怎样~", {
            "input": 800, "output": 40,
        }


def event(text: str, uid: int, mid: str) -> dict:
    return {
        "post_type": "message", "message_type": "group",
        "group_id": GROUP, "user_id": uid, "message_id": mid,
        "self_id": SELF_ID, "sender": {"nickname": f"用户{uid}"},
        "message": [
            {"type": "at", "data": {"qq": str(SELF_ID)}},
            {"type": "text", "data": {"text": text}},
        ],
    }


def post(text: str, uid: int, mid: str) -> None:
    body = json.dumps(event(text, uid, mid), ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{HOOK_PORT}/event?token=demo-token",
        data=body, headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as resp:
        resp.read()
    time.sleep(0.35)


def main() -> int:
    data_dir = ROOT / "demo-data"
    shutil.rmtree(data_dir, ignore_errors=True)
    cfg = Config(
        root=ROOT,
        port=HOOK_PORT,
        data_dir=data_dir,
        allow_groups={GROUP},
        admins={ADMIN},
        deepseek_key="demo",
        onebot_api=f"http://127.0.0.1:{API_PORT}",
        onebot_token="demo",
        webhook_token="demo-token",
        rate_limit_seconds=0,
        chat_cooldown_seconds=0,
        max_batch=20,
    )
    bot = Bot(cfg, RuleLLM(), None)  # type: ignore[arg-type]
    from bot.onebot import OneBotClient
    bot.sender = OneBotClient(cfg.onebot_api, cfg.onebot_token)

    api = ThreadingHTTPServer(("127.0.0.1", API_PORT), FakeNapCat)
    api_thread = threading.Thread(target=api.serve_forever, daemon=True)
    api_thread.start()

    hook = EventServer((cfg.host, cfg.port), bot, cfg.webhook_token)
    hook_thread = threading.Thread(target=hook.serve_forever, daemon=True)
    hook_thread.start()
    time.sleep(0.3)

    print("=" * 60)
    print("演示：把群里的设定碎片整合成结构化设定库")
    print("=" * 60)

    post("添加 林晚是前哨站的医师，今年二十四岁", 2, "m1")
    post("添加 老周是她师父", 2, "m2")
    post("添加 不对，林晚二十七了", 3, "m3")
    print("\n（以上是群聊素材，下面开始整合）")
    post("整合", 2, "m4")
    post("待定", 2, "m5")
    post("裁决 C-01 27", ADMIN, "m6")
    post("查 林晚", 2, "m7")
    post("导出", 2, "m8")
    post("今天好累", 2, "m9")

    time.sleep(0.5)
    canon = json.loads((data_dir / str(GROUP) / "canon.json").read_text(encoding="utf-8"))
    print("\n" + "=" * 60)
    print("最终设定库：")
    print(json.dumps(canon["entities"], ensure_ascii=False, indent=2))
    print(f"\n数据文件：{data_dir}")
    print(f"群文件：{FakeNapCat.files}")

    hook.shutdown()
    hook.server_close()
    api.shutdown()
    api.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
