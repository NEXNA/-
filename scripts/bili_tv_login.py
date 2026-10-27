"""Bilibili TV-channel QR login (fallback when web QR returns empty cookies)."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from bilibili_api import login_v2
from bilibili_api.utils.picture import Picture

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
QR_PATH = DATA / "bili_tv_login_qr.png"
CRED_PATH = DATA / "bili_credential.json"
STATUS_PATH = DATA / "bili_login_status.json"


def status(ok: bool, reason: str) -> None:
    STATUS_PATH.write_text(
        json.dumps({"ok": ok, "reason": reason, "time": int(time.time())},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


async def main() -> None:
    qr = login_v2.QrCodeLogin(login_v2.QrCodeLoginChannel.TV)
    await qr.generate_qrcode()
    picture = qr.get_qrcode_picture()
    if isinstance(picture, Picture):
        picture.to_file(str(QR_PATH))
    status(False, "waiting_tv")
    print(f"QR={QR_PATH}", flush=True)
    deadline = time.time() + 180
    while time.time() < deadline:
        state = await qr.check_state()
        if state == login_v2.QrCodeLoginEvents.DONE:
            cred = qr.get_credential()
            data = {
                "sessdata": cred.sessdata or "",
                "bili_jct": cred.bili_jct or "",
                "buvid3": cred.buvid3 or "",
                "dedeuserid": cred.dedeuserid or "",
                "ac_time_value": cred.ac_time_value or "",
            }
            if not data["sessdata"] or not data["bili_jct"] or not data["dedeuserid"]:
                status(False, "empty_credential_tv")
                print("LOGIN_EMPTY", flush=True)
                return
            CRED_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
            status(True, "ok_tv")
            print("LOGIN_OK", flush=True)
            return
        print(f"STATE={getattr(state, 'value', state)}", flush=True)
        await asyncio.sleep(2)
    status(False, "timeout_tv")
    print("LOGIN_TIMEOUT", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
