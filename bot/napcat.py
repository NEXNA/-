"""NapCat WebUI 的最小客户端：登录、查状态、取登录二维码。"""
from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request


class NapCatError(Exception):
    pass


class NapCatWebUI:
    def __init__(self, base_url: str, token: str, timeout: int = 6):
        self.base_url = str(base_url or "http://127.0.0.1:6099").rstrip("/")
        if self.base_url.endswith("/api"):
            self.base_url = self.base_url[:-4]
        self.token = str(token or "")
        self.timeout = timeout
        self._credential: str | None = None

    def _post(self, path: str, payload: dict | None = None,
              credential: str | None = None) -> dict:
        body = json.dumps(payload or {}).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + "/api" + path, data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        if credential:
            request.add_header("Authorization", f"Bearer {credential}")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
                status = response.status
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise NapCatError(f"WebUI HTTP {exc.code}：{raw[:200]}") from exc
        except Exception as exc:  # noqa: BLE001
            raise NapCatError(f"连不上 NapCat WebUI：{exc}") from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise NapCatError(f"WebUI 返回不是 JSON（HTTP {status}）") from exc
        if data.get("code") not in (0, None):
            raise NapCatError(str(data.get("message") or data))
        return data

    def login(self) -> str:
        if not self.token:
            raise NapCatError("没有填写 WebUI Token")
        digest = hashlib.sha256((self.token + ".napcat").encode("utf-8")).hexdigest()
        data = self._post("/auth/login", {"hash": digest})
        credential = (data.get("data") or {}).get("Credential")
        if not credential:
            raise NapCatError("WebUI 登录没有返回 Credential")
        self._credential = str(credential)
        return self._credential

    def credential(self) -> str:
        return self._credential or self.login()

    def status(self) -> dict:
        data = self._post("/QQLogin/CheckLoginStatus", {}, self.credential())
        return data.get("data") or {}

    def qrcode(self) -> str | None:
        status = self.status()
        if status.get("isLogin"):
            return None
        try:
            data = self._post("/QQLogin/GetQQLoginQrcode", {}, self.credential())
        except NapCatError as exc:
            if "Logined" in str(exc) or "登录" in str(exc):
                return None
            raise
        qrcode = (data.get("data") or {}).get("qrcode")
        if not qrcode:
            qrcode = (data.get("data") or {}).get("qrcodeurl")
        return str(qrcode) if qrcode else None

    def login_info(self) -> dict:
        data = self._post("/QQLogin/GetQQLoginInfo", {}, self.credential())
        return data.get("data") or {}

    def quick_login_list(self) -> list[dict]:
        data = self._post(
            "/QQLogin/GetQuickLoginListNew", {}, self.credential(),
        )
        value = data.get("data") or []
        return [item for item in value if isinstance(item, dict)]
