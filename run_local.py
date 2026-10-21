"""本地开发服务器：python run_local.py [--port 8787]

只为了在本机用 curl / MCP Inspector 调，生产请用 SCF。
"""

from __future__ import annotations

import argparse
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, urlsplit

from mcp_tc.server import handle_http

TIMEOUT_S = 60


class Handler(BaseHTTPRequestHandler):
    server_version = "tencentcloud-mcp/0.2"

    def do_POST(self) -> None:  # noqa: N802
        self._handle("POST")

    def do_GET(self) -> None:  # noqa: N802
        self._handle("GET")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._handle("OPTIONS")

    def do_DELETE(self) -> None:  # noqa: N802
        self._handle("DELETE")

    def _handle(self, method: str) -> None:
        length = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(length).decode("utf-8", "replace") if length else ""
        headers = {k.lower(): v for k, v in self.headers.items()}
        query = dict(parse_qsl(urlsplit(self.path).query))

        status, response_headers, text = handle_http(
            method=method,
            path=urlsplit(self.path).path,
            headers=headers,
            body=body,
            query=query,
            deadline=time.monotonic() + TIMEOUT_S,
        )

        data = text.encode("utf-8")
        self.send_response(status)
        for key, value in response_headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if data:
            self.wfile.write(data)

    def log_message(self, fmt: str, *args) -> None:
        print(f"[{self.log_date_time_string()}] {fmt % args}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"tencentcloud-mcp listening on http://{args.host}:{args.port}/mcp")
    print('试一下：curl -s localhost:%d/mcp -H \'content-type: application/json\' '
          '-d \'{"jsonrpc":"2.0","id":1,"method":"tools/list"}\'' % args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
