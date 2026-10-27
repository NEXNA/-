"""Generate a Bilibili login QR and save the credential for Mocha."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from bilibili_api import login_v2
from bilibili_api.utils.picture import Picture

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DATA.mkdir(parents=True, exist_ok=True)
QR_PATH = DATA / "bili_login_qr.png"
CRED_PATH = DATA / "bili_credential.json"
STATUS_PATH = DATA / "bili_login_status.json"


def _status(ok: bool, reason: str = "") -> None:
    STATUS_PATH.write_text(
        json.dumps(
            {"ok": ok, "reason": reason, "time": int(time.time())},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )


async def main() -> None:
    # 网页扫码通道在部分账号上会返回空 Cookie；TV 通道的 cookie_info 更稳定。
    qr = login_v2.QrCodeLogin(login_v2.QrCodeLoginChannel.TV)
    await qr.generate_qrcode()
    picture = qr.get_qrcode_picture()
    if isinstance(picture, Picture):
        picture.to_file(str(QR_PATH))
    else:
        Path(str(picture)).replace(QR_PATH)
    _status(False, "waiting")
    print(f"QR={QR_PATH}", flush=True)
    deadline = time.time() + 180
    while time.time() < deadline:
        state = await qr.check_state()
        if state == login_v2.QrCodeLoginEvents.DONE:
            credential = qr.get_credential()
            data = {
                "sessdata": credential.sessdata or "",
                "bili_jct": credential.bili_jct or "",
                "buvid3": credential.buvid3 or "",
                "dedeuserid": credential.dedeuserid or "",
                "ac_time_value": credential.ac_time_value or "",
            }
            if not data["sessdata"] or not data["bili_jct"] or not data["dedeuserid"]:
                # B站可能在实名/风控校验后返回空 Cookie；绝不能用空凭证覆盖旧文件
                _status(False, "empty_credential")
                print("LOGIN_EMPTY", flush=True)
                return
            CRED_PATH.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            _status(True, "ok")
            print("LOGIN_OK", flush=True)
            return
        print(f"STATE={getattr(state, 'value', state)}", flush=True)
        await asyncio.sleep(2)
    _status(False, "timeout")
    print("LOGIN_TIMEOUT", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
