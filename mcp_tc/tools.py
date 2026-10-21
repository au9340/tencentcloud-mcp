from __future__ import annotations

import json
import time
from typing import Any

from . import catalog
from .client import TencentClient, TencentFacade
from .context import RequestContext
from .errors import AuthError, CodeRejected, TencentApiError, ValidationError
from .sandbox import run_code

MAX_RESULT_CHARS = 6_000 * 4
MAX_CODE_BYTES = 20_000

SEARCH_DESCRIPTION = """
用代码查询腾讯云 Action 目录（Code Mode，不把全量 schema 塞回上下文）。写一段 Python 函数体，可用 await，必须 return。

可用变量：
- spec["services"]：{ service: { version, product, docUrl, actions } }
- spec["actions"]：扁平列表 [{ service, version, product, action, summary, requiresRegion, dangerous, params }]
- search_actions(keyword, limit=20)：关键词检索，返回同样的扁平条目
- total：目录中 Action 总数

示例：
return [a for a in spec["actions"] if a["service"] == "cvm" and "Instance" in a["action"]][:10]
""".strip()

EXECUTE_DESCRIPTION = """
用代码调用腾讯云 API（Code Mode 的执行层）。写一段 Python 函数体，只 return 你需要的数据。

可用变量：
- tencent.request({ "service": ..., "action": ..., "params": {...}, "region": ..., "version": ..., "confirm": ... })
  或 tencent.request(service="cvm", action="DescribeInstances", params={...})
  * service：产品短名（= API 域名子域）：cvm / vpc / cbs / clb / lighthouse / scf / tat / cam / sts / dnspod
  * action：大驼峰 Action，如 DescribeInstances
  * params：腾讯云 RPC 风格参数平铺，如 {"Filters": [{"Name": "instance-name", "Values": ["web"]}], "Limit": 10}
  * version 省略时从目录推导；region 省略时用本工具参数或服务端默认地域
- region：当前生效地域（可能为 None）
- spec["actions"]：同 search 工具

示例：
r = await tencent.request(service="cvm", action="DescribeInstances", params={"Limit": 20})
return [{"id": i["InstanceId"], "state": i["InstanceState"]} for i in r["InstanceSet"]]
""".strip()

TOOL_DEFS: list[dict[str, Any]] = [
    {
        "name": "search",
        "title": "Search Tencent Cloud API actions",
        "description": SEARCH_DESCRIPTION,
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python 函数体，可用 await，必须 return 一个可 JSON 序列化的值",
                }
            },
            "required": ["code"],
            "additionalProperties": False,
        },
    },
    {
        "name": "execute",
        "title": "Execute Tencent Cloud API calls via code",
        "description": EXECUTE_DESCRIPTION,
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python 函数体，可用 await，必须 return 一个可 JSON 序列化的值",
                },
                "region": {
                    "type": "string",
                    "description": "本次执行的地域，如 ap-guangzhou；省略则用服务端默认地域",
                },
                "explain": {"type": "string", "description": "一句话说明这次要做什么（审计用）"},
            },
            "required": ["code"],
            "additionalProperties": False,
        },
    },
    {
        "name": "docs",
        "title": "Look up Tencent Cloud API action docs",
        "description": "按关键词检索 Action 目录，返回参数含义、是否需要 region、是否高危、官方文档链接。不确定接口名/参数名时先用它。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": '关键词，可多个，如 "cvm 实例" 或 "dnspod 记录"'},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "description": "返回条数，默认 8"},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "whoami",
        "title": "Who am I",
        "description": "返回当前连接的身份（主账号 Uin/AppId 或子用户）、执行引擎与默认地域。用于区分多个连接、排查权限问题。",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]


def call_tool(name: str, arguments: Any, ctx: RequestContext) -> dict[str, Any]:
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise ValidationError("arguments 必须是对象")

    if name == "search":
        return _search(arguments, ctx)
    if name == "execute":
        return _execute(arguments, ctx)
    if name == "docs":
        return _docs(arguments, ctx)
    if name == "whoami":
        return _whoami(arguments, ctx)
    raise ValidationError(f"未知工具：{name}")


# --------------------------------------------------------------------- helpers
def _text(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except (TypeError, ValueError) as exc:
        return f"结果无法序列化为 JSON：{exc}"


def _truncate(text: str, ctx: RequestContext) -> str:
    if not ctx.truncate or len(text) <= MAX_RESULT_CHARS:
        return text
    return (
        text[:MAX_RESULT_CHARS]
        + f"\n--- TRUNCATED ---\n（原始 {len(text)} 字符，已截断到 {MAX_RESULT_CHARS}；"
        "请在代码里只返回需要的字段，或加 ?truncateToolResult=false 关闭截断）"
    )


def _require_code(arguments: dict[str, Any]) -> str:
    code = arguments.get("code")
    if not isinstance(code, str) or not code.strip():
        raise ValidationError("code 必须是非空字符串")
    if len(code.encode("utf-8")) > MAX_CODE_BYTES:
        raise ValidationError(f"code 太长（>{MAX_CODE_BYTES} 字节）")
    return code


def _budget(ctx: RequestContext, default: float = 15.0) -> float:
    remaining = ctx.remaining_s()
    if remaining is None:
        return default
    return max(1.0, min(default, remaining - 0.5))


def _require_credentials(ctx: RequestContext):
    if ctx.credentials is None:
        raise AuthError(
            "调用工具需要腾讯云凭据：请加请求头 Authorization: Bearer <secretId>:<secretKey>[:<sessionToken>]"
        )
    return ctx.credentials


# ----------------------------------------------------------------------- tools
def _search(arguments: dict[str, Any], ctx: RequestContext) -> dict[str, Any]:
    code = _require_code(arguments)
    env = {
        "spec": {"services": catalog.load(), "actions": catalog.flatten()},
        "search_actions": lambda query, limit=20: catalog.search(str(query), min(int(limit), 50)),
        "total": len(catalog.flatten()),
        "region": ctx.default_region,
    }
    value = run_code(code, env, timeout_s=_budget(ctx))
    return _text(_truncate(_stringify(value), ctx))


def _execute(arguments: dict[str, Any], ctx: RequestContext) -> dict[str, Any]:
    credentials = _require_credentials(ctx)
    code = _require_code(arguments)
    region = arguments.get("region") or ctx.default_region

    client = TencentClient(
        credentials,
        engine=ctx.engine,
        default_region=region,
        max_requests=ctx.max_requests,
        timeout_ms=ctx.timeout_ms,
        require_confirm=ctx.require_confirm,
        deadline=ctx.deadline,
    )
    env = {
        "tencent": TencentFacade(client),
        "region": region,
        "spec": {"services": catalog.load(), "actions": catalog.flatten()},
    }

    started = time.monotonic()
    value = run_code(code, env, timeout_s=_budget(ctx))
    payload: dict[str, Any] = {
        "ok": True,
        "engine": ctx.engine,
        "region": region,
        "apiCalls": client.calls,
        "latencyMs": int((time.monotonic() - started) * 1000),
        "result": value,
    }
    if arguments.get("explain"):
        payload["explain"] = arguments["explain"]
    return _text(_truncate(_stringify(payload), ctx))


def _docs(arguments: dict[str, Any], ctx: RequestContext) -> dict[str, Any]:
    query = arguments.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ValidationError("query 必须是非空字符串")
    limit = arguments.get("limit") or 8
    entries = catalog.search(query, int(limit))

    if not entries:
        return _text(
            f'目录里没找到匹配 "{query}" 的 Action。\n'
            "可以：① 换更短的关键词（cvm / disk / DNS）；② 用 search 写代码遍历 spec[\"actions\"]；"
            "③ 在 mcp_tc/catalog.json 里补充该产品。"
        )

    blocks: list[str] = []
    for entry in entries:
        flags = [
            "需要 region" if entry["requiresRegion"] else "不需要 region",
            "写/删类操作" if entry["dangerous"] else "只读",
        ]
        params = entry["params"]
        if params:
            param_lines = "\n".join(f"  - {k}：{v}" for k, v in params.items())
        else:
            param_lines = "  - （未收录关键参数，请看官方文档）"
        blocks.append(
            f"### {entry['service']}:{entry['action']}（{entry['product']}，version {entry['version']}）\n"
            f"{entry['summary']}\n"
            f"- {'，'.join(flags)}\n"
            f"- 常用参数：\n{param_lines}\n"
            f"- 文档：{entry['docUrl']}"
        )

    return _text(
        "\n\n".join(blocks)
        + '\n\n调用方式：execute({ code: `r = await tencent.request(service="...", action="...", params={...}); return r` })'
    )


def _whoami(arguments: dict[str, Any], ctx: RequestContext) -> dict[str, Any]:
    credentials = _require_credentials(ctx)
    client = TencentClient(
        credentials,
        engine=ctx.engine,
        default_region=ctx.default_region,
        max_requests=2,
        timeout_ms=ctx.timeout_ms,
        deadline=ctx.deadline,
    )

    source = "sts:GetCallerIdentity"
    note: str | None = None
    try:
        identity = client.request("sts", "GetCallerIdentity", version="2018-08-13")
    except (TencentApiError, ValidationError) as exc:
        source = "cam:GetUserAppId"
        note = f"sts:GetCallerIdentity 失败，已回退 CAM：{exc}"
        identity = client.request("cam", "GetUserAppId", version="2019-01-16")

    payload = {
        "ok": True,
        "source": source,
        "credential": credentials.fingerprint(),
        "engine": ctx.engine,
        "defaultRegion": ctx.default_region,
        "identity": identity,
    }
    if note:
        payload["note"] = note
    return _text(_truncate(_stringify(payload), ctx))
