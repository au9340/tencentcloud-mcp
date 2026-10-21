import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from serve import Handler


class QuietHandler(Handler):
    """安静版的 Handler：不刷访问日志。"""

    def log_message(self, fmt, *args):  # noqa: D102
        pass


class HttpEndToEndTest(unittest.TestCase):
    """走真实 socket 验证 serve.py —— 也就是 Web 函数里真正跑的那条路径。"""

    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        cls.server.daemon_threads = True
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def _post(self, payload, headers=None, path="/mcp"):
        request = urllib.request.Request(
            self._url(path),
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, dict(response.headers), response.read().decode("utf-8")

    def test_tools_list_over_http(self):
        status, headers, body = self._post({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers.get("Content-Type", ""))
        names = [tool["name"] for tool in json.loads(body)["result"]["tools"]]
        self.assertEqual(names, ["search", "execute", "docs", "whoami"])

    def test_any_path_is_mcp(self):
        status, _, body = self._post(
            {"jsonrpc": "2.0", "id": 7, "method": "ping"}, path="/release/mcp"
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["result"], {})

    def test_sse_framing(self):
        status, headers, body = self._post(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            headers={"Accept": "text/event-stream"},
            path="/mcp?stream=1",
        )
        self.assertEqual(status, 200)
        self.assertIn("text/event-stream", headers.get("Content-Type", ""))
        self.assertTrue(body.startswith("event: message\ndata: "))
        self.assertTrue(body.endswith("\n\n"))
        payload = body[len("event: message\ndata: ") :].strip()
        self.assertIn("tools", json.loads(payload)["result"])

    def test_cors_preflight(self):
        request = urllib.request.Request(self._url("/mcp"), method="OPTIONS")
        with urllib.request.urlopen(request, timeout=10) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers["Access-Control-Allow-Origin"], "*")

    def test_get_is_405(self):
        request = urllib.request.Request(self._url("/mcp"), method="GET")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(request, timeout=10)
        self.assertEqual(ctx.exception.code, 405)

    def test_notification_returns_202(self):
        status, _, body = self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertEqual(status, 202)
        self.assertEqual(body, "")


if __name__ == "__main__":
    unittest.main()
