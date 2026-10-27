from __future__ import annotations

import http.client
import json
import threading
import time
import unittest

from bot.server import EventServer


class StubBot:
    def __init__(self):
        self.events = []

    def on_event(self, event):
        self.events.append(event)

    def health(self):
        return {"ok": True}


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.bot = StubBot()
        self.server = EventServer(("127.0.0.1", 0), self.bot, "test-token")
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        time.sleep(0.05)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def _post(self, path: str, body: bytes, headers: dict | None = None,
              chunked: bool = False):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.putrequest("POST", path)
        for key, value in (headers or {}).items():
            conn.putheader(key, value)
        if chunked:
            conn.putheader("Transfer-Encoding", "chunked")
        else:
            conn.putheader("Content-Length", str(len(body)))
        conn.endheaders()
        if chunked:
            conn.send(f"{len(body):x}\r\n".encode() + body + b"\r\n0\r\n\r\n")
        else:
            conn.send(body)
        response = conn.getresponse()
        data = response.read()
        conn.close()
        return response.status, data

    def _wait_events(self, count: int) -> None:
        for _ in range(50):
            if len(self.bot.events) >= count:
                return
            time.sleep(0.02)
        self.fail(f"只收到 {len(self.bot.events)} 个事件")

    def test_content_length_event(self):
        body = json.dumps({"post_type": "meta_event"}).encode()
        status, _ = self._post("/event?token=test-token", body,
                               {"Content-Type": "application/json"})
        self.assertEqual(status, 200)
        self._wait_events(1)

    def test_chunked_event(self):
        body = json.dumps({"post_type": "meta_event"}).encode()
        status, _ = self._post("/event?token=test-token", body,
                               {"Content-Type": "application/json"}, chunked=True)
        self.assertEqual(status, 200)
        self._wait_events(1)

    def test_root_path_is_accepted(self):
        body = json.dumps({"post_type": "meta_event"}).encode()
        status, _ = self._post("/?token=test-token", body,
                               {"Content-Type": "application/json"})
        self.assertEqual(status, 200)
        self._wait_events(1)

    def test_bad_token_rejected(self):
        body = b"{}"
        status, _ = self._post("/event?token=wrong", body,
                               {"Content-Type": "application/json"})
        self.assertEqual(status, 403)

    def test_bad_json_rejected(self):
        status, _ = self._post("/event?token=test-token", b"not json",
                               {"Content-Type": "application/json"})
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
