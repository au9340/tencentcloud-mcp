from __future__ import annotations

import json
import logging
import time
from typing import Any

from . import __version__, tools
from .auth import AuthError, resolve_credentials
from .context import RequestContext
from .errors import CodeRejected, McpError, TencentApiError, ValidationError

log = logging.getLogger("tencentcloud-mcp")

DEFAULT_PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
    "Access-Control-Allow-Headers": (
        "authorization, content-type, accept, mcp-protocol-version, mcp-session-id"
    ),
    "Access-Control-Max-Age": "86400",
}

INSTRUCTIONS = f"""
这是腾讯云 API 的 MCP 服务器（v{__version__}），采用 Code Mode：只有 4 个工具，但覆盖全量 API。

标准工作流：
1. 不确定用哪个接口时先调 search：写 Python 在 Action 目录里筛选，只返回你需要的那几条。
2. 再调 execute：写 Python 用 tencent.request(...) 真实调用 API，并在代码里过滤/聚合，只 return 需要的数据。
3. 需要参数含义/文档链接时调 docs；需要知道当前连接是哪个账号时调 whoami。

硬约束：
- service 是 API 域名子域（cvm / vpc / cbs / clb / lighthouse / scf / tat / cam / sts / dnspod）。
- 大部分 Action 需要 region；省略时依次取：tencent.request(region=..) > execute 的 region > 环境变量 MCP_DEFAULT_REGION。
- params 平铺（腾讯云 RPC 风格），不要包成 {{"Params": {{...}}}}。
- 单次 execute 有 API 调用次数上限（默认 20），结果超过 ~6000 tokens 会被截断 → 只返回必需字段。
- 写/删/重启类操作（目录里 dangerous）先向用户确认；服务端开启确认闸时需传 confirm=True。
""".strip()

_ACCEPTED = object()


def _rpc_result(msg_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _rpc_error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _json_response(status: int, payload: Any) -> tuple[int, dict[str, str], str]:
    headers = dict(CORS_HEADERS)
    headers["Content-Type"] = "application/json; charset=utf-8"
    return status, headers, json.dumps(payload, ensure_ascii=False)


def _accepted() -> tuple[int, dict[str, str], str]:
    headers = dict(CORS_HEADERS)
    headers["Content-Type"] = "application/json; charset=utf-8"
    return 202, headers, ""


def _handle_message(
    message: Any,
    headers: dict[str, str],
    query: dict[str, Any],
    deadline: float | None,
) -> dict[str, Any] | object:
    if not isinstance(message, dict) or not isinstance(message.get("method"), str):
        msg_id = message.get("id") if isinstance(message, dict) else None
        return _rpc_error(msg_id, -32600, "无效的 JSON-RPC 请求")

    msg_id = message.get("id")
    method = message["method"]
    params = message.get("params") or {}

    if method.startswith("notifications/"):
        return _ACCEPTED

    if method == "initialize":
        requested = params.get("protocolVersion") if isinstance(params, dict) else None
        version = (
            requested if requested in SUPPORTED_PROTOCOL_VERSIONS else DEFAULT_PROTOCOL_VERSION
        )
        return _rpc_result(
            msg_id,
            {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "tencentcloud-mcp", "version": __version__},
                "instructions": INSTRUCTIONS,
            },
        )

    if method == "ping":
        return _rpc_result(msg_id, {})

    if method == "tools/list":
        return _rpc_result(msg_id, {"tools": tools.TOOL_DEFS})

    if method == "resources/list":
        return _rpc_result(msg_id, {"resources": []})

    if method == "prompts/list":
        return _rpc_result(msg_id, {"prompts": []})

    if method == "tools/call":
        if not isinstance(params, dict):
            return _rpc_error(msg_id, -32602, "tools/call 的 params 必须是对象")
        name = params.get("name")
        if not isinstance(name, str) or not name:
            return _rpc_error(msg_id, -32602, "tools/call 缺少 name")

        started = time.monotonic()
        try:
            credentials = resolve_credentials(headers)
            ctx = RequestContext.build(credentials, query, deadline)
            result = tools.call_tool(name, params.get("arguments"), ctx)
            log.info("tools/call %s ok (%dms)", name, int((time.monotonic() - started) * 1000))
            return _rpc_result(msg_id, result)
        except AuthError as exc:
            return _rpc_error(msg_id, -32001, str(exc))
        except (ValidationError, CodeRejected, TencentApiError, McpError) as exc:
            log.warning("tools/call %s failed: %s", name, exc)
            return _rpc_result(
                msg_id, {"content": [{"type": "text", "text": str(exc)}], "isError": True}
            )
        except Exception as exc:  # noqa: BLE001 - 工具层任何异常都回给模型，别让网关 5xx
            log.exception("tools/call %s crashed", name)
            return _rpc_result(
                msg_id,
                {"content": [{"type": "text", "text": f"工具执行异常：{exc}"}], "isError": True},
            )

    return _rpc_error(msg_id, -32601, f"不支持的方法：{method}")


def handle_http(
    method: str,
    path: str,
    headers: dict[str, str],
    body: str,
    query: dict[str, Any] | None = None,
    deadline: float | None = None,
) -> tuple[int, dict[str, str], str]:
    """把 HTTP 请求转成 JSON-RPC 响应。SCF 事件函数与本地 http.server 都走这里。"""
    method = (method or "POST").upper()
    query = query or {}

    if method == "OPTIONS":
        return 200, dict(CORS_HEADERS), ""

    if method != "POST":
        payload = {
            "jsonrpc": "2.0",
            "error": {
                "code": -32000,
                "message": "无状态 MCP 服务器只接受 POST（Streamable HTTP，JSON response 模式）",
            },
            "id": None,
        }
        status, response_headers, text = _json_response(405, payload)
        response_headers["Allow"] = "POST, OPTIONS"
        return status, response_headers, text

    if not body or not body.strip():
        return _json_response(400, _rpc_error(None, -32700, "请求体为空"))

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        return _json_response(400, _rpc_error(None, -32700, f"JSON 解析失败：{exc}"))

    if isinstance(payload, list):
        responses: list[Any] = []
        for item in payload:
            outcome = _handle_message(item, headers, query, deadline)
            if outcome is _ACCEPTED:
                continue
            responses.append(outcome)
        if not responses:
            return _accepted()
        return _json_response(200, responses)

    outcome = _handle_message(payload, headers, query, deadline)
    if outcome is _ACCEPTED:
        return _accepted()
    return _json_response(200, outcome)
