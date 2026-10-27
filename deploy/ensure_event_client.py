"""Ensure a NapCat HTTP event client is enabled and actually reloaded.

Some NapCat restarts load the onebot config but do not start the HTTP client
until SetConfig is called. This helper toggles the named client off/on.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bot.napcat import NapCatWebUI  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--webui", default="http://127.0.0.1:6100")
    parser.add_argument("--token", required=True)
    parser.add_argument("--name", default="陪伴工作台")
    parser.add_argument("--url", default="http://127.0.0.1:8765/napcat/event?token=replace-me")
    parser.add_argument("--retries", type=int, default=6)
    args = parser.parse_args()
    last = ""
    for attempt in range(1, args.retries + 1):
        try:
            web = NapCatWebUI(args.webui, args.token)
            web.login()
            data = web._post("/OB11Config/GetConfig", {}, web.credential())["data"]
            clients = data["network"]["httpClients"]
            target = None
            for client in clients:
                if args.name in str(client.get("name", "")):
                    target = client
                    break
            if target is None:
                target = {"name": args.name, "url": args.url}
                clients.append(target)
            target["enable"] = False
            target["url"] = args.url
            web._post("/OB11Config/SetConfig", {
                "config": json.dumps(data, ensure_ascii=False),
            }, web.credential())
            time.sleep(0.4)
            target["enable"] = True
            web._post("/OB11Config/SetConfig", {
                "config": json.dumps(data, ensure_ascii=False),
            }, web.credential())
            print(f"event client reloaded: {args.name} -> {args.url}")
            return 0
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
            print(f"waiting for NapCat ({attempt}/{args.retries}): {last}")
            time.sleep(3)
    print(f"failed: {last}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
