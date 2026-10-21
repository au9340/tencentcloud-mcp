"""HTTP 服务：同时是本地开发服务器和 SCF Web 函数的进程入口。

本地：python3.10 serve.py                          → 127.0.0.1:8787
SCF ：scf_bootstrap 执行 python3 -u serve.py --host 0.0.0.0 --port 9000
"""

from __future__ import annotations

import argparse
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, urlsplit

from mcp_tc.server import handle_http

# 单次请求总预算（秒）：要比 SCF 函数超时略小
TIMEOUT_S = float(os.environ.get("MCP_REQUEST_TIMEOUT_S", "55"))


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
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
        parts = urlsplit(self.path)
        length = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(length).decode("utf-8", "replace") if length else ""
        headers = {k.lower(): v for k, v in self.headers.items()}
        query = dict(parse_qsl(parts.query))

        status, response_headers, text = handle_http(
            method=method,
            path=parts.path,
            headers=headers,
            body=body,
            query=query,
            deadline=time.monotonic() + TIMEOUT_S,
        )

        # Web 函数才有流式能力：显式 ?stream=1，或客户端只要 text/event-stream
        accept = headers.get("accept", "")
        wants_sse = str(query.get("stream", "")) == "1" or (
            "text/event-stream" in accept and "application/json" not in accept
        )

        if wants_sse and status == 200 and text:
            self._send_sse(text)
        else:
            self._send(status, response_headers, text)

    def _send(self, status: int, headers: dict[str, str], text: str) -> None:
        data = text.encode("utf-8")
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if data:
            self.wfile.write(data)

    def _send_sse(self, text: str) -> None:
        """MCP Streamable HTTP 的 SSE 分帧：event: message + data: <json>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(b"event: message\ndata: " + text.encode("utf-8") + b"\n\n")
        self.wfile.flush()
        self.close_connection = True

    def log_message(self, fmt: str, *args) -> None:
        print(f"[{self.log_date_time_string()}] {fmt % args}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="tencentcloud-mcp HTTP server")
    parser.add_argument("--host", default=os.environ.get("MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MCP_PORT", "8787")))
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.daemon_threads = True
    print(f"tencentcloud-mcp listening on http://{args.host}:{args.port}/mcp", flush=True)
    print(
        "试一下：curl -s localhost:%d/mcp -H 'content-type: application/json' "
        '-d \'{"jsonrpc":"2.0","id":1,"method":"tools/list"}\'' % args.port,
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbye", flush=True)


if __name__ == "__main__":
    main()
