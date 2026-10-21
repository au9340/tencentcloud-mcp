"""SCF 入口：事件函数 + API 网关 / 函数 URL 触发器。

部署要点：
- 运行时 Python 3.10，执行方法填 main.main_handler
- 触发器：API 网关（或函数 URL），后端超时 >= 30s，SCF 超时 >= 60s
- 不需要安装任何依赖，目录直接打 zip 上传即可
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from typing import Any
from urllib.parse import parse_qsl

from mcp_tc.server import handle_http

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
log = logging.getLogger("tencentcloud-mcp")


def _headers(event: dict[str, Any]) -> dict[str, str]:
    raw = event.get("headers") or {}
    return {str(k).lower(): v for k, v in raw.items() if isinstance(v, str)}


def _query(event: dict[str, Any]) -> dict[str, Any]:
    raw = event.get("queryString") or event.get("query") or {}
    if isinstance(raw, str):
        return dict(parse_qsl(raw))
    if isinstance(raw, dict):
        if "values" in raw and isinstance(raw["values"], dict):
            return {k: v for k, v in raw["values"].items() if isinstance(v, str)}
        return {str(k): v for k, v in raw.items() if isinstance(v, (str, int, float))}
    return {}


def _body(event: dict[str, Any]) -> str:
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        try:
            return base64.b64decode(body).decode("utf-8", "replace")
        except (ValueError, TypeError):
            return ""
    return body


def _deadline(context: Any) -> float:
    remaining_ms = 0
    getter = getattr(context, "get_remaining_time_in_millis", None)
    if callable(getter):
        try:
            remaining_ms = int(getter())
        except Exception:  # noqa: BLE001 - 不同触发方式 context 不一样
            remaining_ms = 0
    if not remaining_ms:
        remaining_ms = int(getattr(context, "time_limit_in_ms", 60_000) or 60_000)
    # 留 2s 给序列化与回包
    return time.monotonic() + max(1.0, remaining_ms / 1000 - 2.0)


def main_handler(event: dict[str, Any] | None = None, context: Any = None) -> dict[str, Any]:
    event = event or {}
    started = time.monotonic()
    method = (
        event.get("httpMethod")
        or (event.get("requestContext") or {}).get("httpMethod")
        or "POST"
    ).upper()
    path = event.get("path") or event.get("rawPath") or "/mcp"

    try:
        status, headers, body = handle_http(
            method=method,
            path=path,
            headers=_headers(event),
            body=_body(event),
            query=_query(event),
            deadline=_deadline(context),
        )
    except Exception:  # noqa: BLE001 - 网关前面不能 5xx
        log.exception("unhandled error")
        status = 500
        headers = {"Content-Type": "application/json; charset=utf-8"}
        body = json.dumps(
            {"jsonrpc": "2.0", "error": {"code": -32603, "message": "internal error"}, "id": None}
        )

    log.info("%s %s -> %s (%dms)", method, path, status, int((time.monotonic() - started) * 1000))
    return {
        "isBase64Encoded": False,
        "statusCode": status,
        "headers": headers,
        "body": body,
    }
