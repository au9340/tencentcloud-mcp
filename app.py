#!/usr/bin/env python3
"""腾讯云 MCP 服务器 —— 单文件版（SCF Web 函数 / 本地通用，零第三方依赖）。

4 个工具覆盖全量 API（Code Mode：spec 留在服务端，模型写代码查 + 调）：
  search   写 Python 在 Action 目录里筛选
  execute  写 Python 用 tencent.request(...) 调用腾讯云 API
  docs     查 Action 参数含义 / 是否需要 region / 文档链接
  whoami   当前身份（sts:GetCallerIdentity，失败回退 cam:GetUserAppId）

用法：
  python3 app.py                              本地 http://127.0.0.1:8787/mcp
  python3 app.py --host 0.0.0.0 --port 9000   SCF Web 函数（由 scf_bootstrap 调用）
  python3 app.py --selftest                   自检（不联网、不需要密钥）

鉴权：纯透传，服务端不存凭据
  Authorization: Bearer <secretId>:<secretKey>[:<sessionToken>]
  Authorization: Bearer base64(<secretId>:<secretKey>[:<sessionToken>])

环境变量（全部可选）：
  MCP_DEFAULT_REGION / MCP_MAX_REQUESTS(20) / MCP_TIMEOUT_MS(20000)
  MCP_REQUEST_TIMEOUT_S(55) / MCP_REQUIRE_CONFIRM / MCP_ALLOW_ENV_CREDENTIALS / MCP_ENGINE(api|sdk)
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import base64
import binascii
import builtins
import hashlib
import hmac
import inspect
import json
import os
import re
import socket
import textwrap
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qsl, urlsplit

VERSION = "0.3.1"
DEFAULT_PROTOCOL = "2025-06-18"
SUPPORTED_PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
MAX_CODE_BYTES = 20_000
MAX_PARAMS_BYTES = 256 * 1024
MAX_RESULT_CHARS = 6_000 * 4  # ~6000 tokens


def _env_str(name: str, default: str = "") -> str:
    return os.environ.get(name) or default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name) or default)
    except ValueError:
        return default


# =========================================================================== 目录
# 相当于 cloudflare/mcp 里那份 OpenAPI spec 的瘦身版：只要“指路牌”。
# action 的值：("说明", {参数: 说明}, {标记})，标记支持 requiresRegion=False / dangerous=True
CATALOG: dict[str, dict[str, Any]] = {
    "cvm": {
        "version": "2017-03-12",
        "product": "云服务器 CVM",
        "doc": "https://cloud.tencent.com/document/api/213",
        "actions": {
            "DescribeInstances": (
                "查询实例列表",
                {
                    "InstanceIds": "Array of String，如 [\"ins-xxx\"]",
                    "Filters": "Array of Filter，Name 可选 instance-id/instance-name/zone",
                    "Limit": "Integer，默认 20，最大 100",
                    "Offset": "Integer",
                },
            ),
            "DescribeRegions": ("列出支持地域", {}, {"requiresRegion": False}),
            "DescribeZones": "列出某地域下的可用区",
            "RunInstances": (
                "创建实例",
                {
                    "ImageId": "String",
                    "InstanceType": "String，如 S5.MEDIUM2",
                    "Placement": "Placement 对象，{Zone: \"ap-guangzhou-3\"}",
                    "InstanceChargeType": "POSTPAID_BY_HOUR / PREPAID",
                    "InstanceCount": "Integer",
                },
                {"dangerous": True},
            ),
            "StartInstances": ("开机", {"InstanceIds": "Array of String"}, {"dangerous": True}),
            "StopInstances": (
                "关机（StopType=SOFT 为软关机）",
                {"InstanceIds": "Array of String", "StopType": "SOFT / HARD / SOFT_FIRST"},
                {"dangerous": True},
            ),
            "RebootInstances": ("重启实例", {"InstanceIds": "Array of String"}, {"dangerous": True}),
            "TerminateInstances": ("销毁实例（不可逆）", {"InstanceIds": "Array of String"}, {"dangerous": True}),
            "ModifyInstancesAttribute": (
                "修改实例名称或安全组绑定",
                {"InstanceIds": "Array of String", "InstanceName": "String"},
            ),
        },
    },
    "vpc": {
        "version": "2017-03-12",
        "product": "私有网络 VPC",
        "doc": "https://cloud.tencent.com/document/api/215",
        "actions": {
            "DescribeVpcs": (
                "查询 VPC 列表",
                {"VpcIds": "Array of String", "Filters": "Array of Filter", "Limit": "Integer，默认 10", "Offset": "Integer"},
            ),
            "CreateVpc": ("创建 VPC", {"VpcName": "String", "CidrBlock": "String，如 10.0.0.0/16"}),
            "DeleteVpc": ("删除 VPC（需先清空子网）", {"VpcId": "String"}, {"dangerous": True}),
            "DescribeSubnets": ("查询子网列表", {"VpcId": "String", "SubnetIds": "Array of String"}),
            "DescribeSecurityGroups": (
                "查询安全组及其规则",
                {"SecurityGroupIds": "Array of String，如 [\"sg-xxx\"]", "Filters": "Array of Filter"},
            ),
            "DescribeSecurityGroupPolicies": ("查询安全组入站/出站规则明细", {"SecurityGroupId": "String"}),
            "DescribeAddresses": ("查询弹性公网 IP 列表", {"AddressIds": "Array of String", "Filters": "Array of Filter"}),
            "DescribeRouteTables": ("查询路由表", {"RouteTableIds": "Array of String", "Filters": "Array of Filter"}),
        },
    },
    "cbs": {
        "version": "2017-03-12",
        "product": "云硬盘 CBS",
        "doc": "https://cloud.tencent.com/document/api/362",
        "actions": {
            "DescribeDisks": (
                "查询云硬盘列表（含挂载信息、类型、容量）",
                {
                    "DiskIds": "Array of String，如 [\"disk-xxx\"]",
                    "Filters": "Array of Filter，Name 可选 disk-name/disk-usage/instance-id",
                    "Limit": "Integer",
                    "Offset": "Integer",
                },
            ),
            "DescribeDiskConfigQuota": (
                "查询可创建的云盘类型与配额",
                {"DiskChargeType": "POSTPAID_BY_HOUR / PREPAID", "DiskUsage": "SYSTEM_DISK / DATA_DISK"},
            ),
            "CreateDisks": (
                "创建云硬盘",
                {
                    "DiskSize": "Integer，GB",
                    "DiskType": "CLOUD_PREMIUM / CLOUD_SSD / CLOUD_BASIC",
                    "Placement": "{Zone}",
                    "DiskCount": "Integer",
                },
            ),
            "AttachDisks": ("挂载云盘到实例", {"DiskIds": "Array of String", "InstanceId": "String"}),
            "DetachDisks": ("卸载云盘（不删数据）", {"DiskIds": "Array of String"}, {"dangerous": True}),
            "DeleteDisks": ("销毁云盘（不可逆）", {"DiskIds": "Array of String"}, {"dangerous": True}),
        },
    },
    "clb": {
        "version": "2017-03-12",
        "product": "负载均衡 CLB",
        "doc": "https://cloud.tencent.com/document/api/214",
        "actions": {
            "DescribeLoadBalancers": (
                "查询负载均衡实例列表",
                {
                    "LoadBalancerIds": "Array of String，如 [\"lb-xxx\"]",
                    "Filters": "Array of Filter",
                    "Limit": "Integer",
                    "Offset": "Integer",
                },
            ),
            "DescribeListeners": (
                "查询监听器列表",
                {"LoadBalancerIds": "Array of String", "Protocol": "HTTP / HTTPS / TCP / UDP"},
            ),
            "DescribeTargets": ("查询监听器绑定的后端机器", {"LoadBalancerId": "String", "ListenerIds": "Array of String"}),
            "RegisterTargets": (
                "绑定后端机器到监听器",
                {"LoadBalancerId": "String", "ListenerId": "String", "Targets": "Array of Target {InstanceId, Port, Weight}"},
            ),
            "DeregisterTargets": (
                "解绑后端机器",
                {"LoadBalancerId": "String", "ListenerId": "String", "Targets": "Array of Target"},
                {"dangerous": True},
            ),
            "DeleteLoadBalancer": ("删除负载均衡实例", {"LoadBalancerIds": "Array of String"}, {"dangerous": True}),
        },
    },
    "lighthouse": {
        "version": "2020-03-24",
        "product": "轻量应用服务器 Lighthouse",
        "doc": "https://cloud.tencent.com/document/api/1207",
        "actions": {
            "DescribeInstances": (
                "查询轻量实例列表",
                {
                    "InstanceIds": "Array of String，如 [\"lhins-xxx\"]",
                    "Filters": "Array of Filter",
                    "Limit": "Integer",
                    "Offset": "Integer",
                },
            ),
            "DescribeRegions": ("列出轻量服务器可用地域", {}, {"requiresRegion": False}),
            "DescribeBlueprints": "列出可用镜像",
            "DescribeBundles": "列出套餐（Bundle）",
            "StartInstances": ("开机", {"InstanceIds": "Array of String"}, {"dangerous": True}),
            "StopInstances": ("关机", {"InstanceIds": "Array of String"}, {"dangerous": True}),
            "RebootInstances": ("重启", {"InstanceIds": "Array of String"}, {"dangerous": True}),
            "TerminateInstances": ("销毁轻量实例（不可逆）", {"InstanceIds": "Array of String"}, {"dangerous": True}),
        },
    },
    "scf": {
        "version": "2018-04-16",
        "product": "云函数 SCF",
        "doc": "https://cloud.tencent.com/document/api/583",
        "actions": {
            "ListFunctions": (
                "列出函数",
                {"Namespace": "String，默认 default", "Limit": "Integer", "Offset": "Integer"},
            ),
            "GetFunction": ("获取函数详情", {"FunctionName": "String", "Namespace": "String"}),
            "Invoke": (
                "同步/异步调用函数",
                {
                    "FunctionName": "String",
                    "InvocationType": "RequestResponse / Event",
                    "ClientContext": "String，base64 的 JSON",
                    "Qualifier": "String",
                },
                {"dangerous": True},
            ),
            "ListNamespaces": "列出命名空间",
            "GetFunctionLogs": (
                "查询函数调用日志",
                {"FunctionName": "String", "Limit": "Integer", "StartTime": "String"},
            ),
            "ListTriggers": ("列出函数触发器", {"FunctionName": "String", "Namespace": "String"}),
        },
    },
    "tat": {
        "version": "2020-10-28",
        "product": "自动化助手 TAT",
        "doc": "https://cloud.tencent.com/document/api/1340",
        "actions": {
            "RunCommand": (
                "在实例上批量执行 Shell/PowerShell 命令（异步）",
                {
                    "CommandType": "SHELL / POWERSHELL / BAT",
                    "Content": "String，base64 编码后的命令",
                    "InstanceIds": "Array of String",
                    "Timeout": "Integer，秒",
                },
                {"dangerous": True},
            ),
            "DescribeCommands": ("查询命令列表", {"CommandIds": "Array of String"}),
            "DescribeInvocations": ("查询执行活动列表", {"InvocationIds": "Array of String"}),
            "DescribeInvocationTasks": (
                "查询执行任务明细（含输出、退出码）",
                {"InvocationTaskIds": "Array of String", "Filters": "Array of Filter"},
            ),
            "DescribeRegions": ("列出 TAT 支持的地域", {}, {"requiresRegion": False}),
        },
    },
    "cam": {
        "version": "2019-01-16",
        "product": "访问管理 CAM",
        "doc": "https://cloud.tencent.com/document/api/598",
        "actions": {
            "GetUserAppId": ("获取当前身份的 Uin / AppId / OwnerUin", {}, {"requiresRegion": False}),
            "ListUsers": ("列出子用户", {"Limit": "Integer", "Offset": "Integer"}, {"requiresRegion": False}),
            "ListGroups": ("列出用户组", {}, {"requiresRegion": False}),
            "ListRoles": ("列出角色", {}, {"requiresRegion": False}),
            "ListPolicies": (
                "列出策略（Scope=Local 自定义 / QCS 预设）",
                {"Scope": "All / QCS / Local", "Keyword": "String"},
                {"requiresRegion": False},
            ),
            "ListAttachedUserPolicies": (
                "列出某个子用户绑定的策略",
                {"TargetUin": "Integer，子用户 Uin"},
                {"requiresRegion": False},
            ),
        },
    },
    "sts": {
        "version": "2018-08-13",
        "product": "临时密钥 STS",
        "doc": "https://cloud.tencent.com/document/api/1312",
        "actions": {
            "GetCallerIdentity": ("返回当前凭据身份，whoami 用", {}, {"requiresRegion": False}),
            "GetFederationToken": (
                "获取临时访问凭证",
                {"Name": "String", "DurationSeconds": "Integer，默认 7200", "Policy": "String"},
                {"requiresRegion": False},
            ),
            "AssumeRole": (
                "扮演角色，获取角色临时凭证",
                {"RoleArn": "String", "RoleSessionName": "String", "DurationSeconds": "Integer"},
                {"requiresRegion": False},
            ),
        },
    },
    "dnspod": {
        "version": "2021-03-23",
        "product": "DNSPod 域名解析",
        "doc": "https://cloud.tencent.com/document/api/1427",
        "actions": {
            "DescribeDomainList": (
                "列出账号下的域名",
                {"Type": "ALL / MY / SHARE", "Offset": "Integer", "Limit": "Integer"},
                {"requiresRegion": False},
            ),
            "DescribeRecordList": (
                "查询某个域名的解析记录",
                {
                    "Domain": "String，如 example.com",
                    "Subdomain": "String，主机记录，如 www",
                    "RecordType": "A / AAAA / CNAME / TXT / MX / NS",
                    "Limit": "Integer，默认 100",
                },
                {"requiresRegion": False},
            ),
            "CreateRecord": (
                "新增解析记录",
                {
                    "Domain": "String",
                    "SubDomain": "String，@ 表示根域名",
                    "RecordType": "String",
                    "RecordLine": "String，如 默认",
                    "Value": "String",
                    "TTL": "Integer，默认 600",
                },
                {"requiresRegion": False},
            ),
            "ModifyRecord": (
                "修改解析记录",
                {"Domain": "String", "RecordId": "Integer", "SubDomain": "String", "RecordType": "String", "Value": "String"},
                {"requiresRegion": False},
            ),
            "DeleteRecord": (
                "删除解析记录",
                {"Domain": "String", "RecordId": "Integer"},
                {"dangerous": True, "requiresRegion": False},
            ),
        },
    },
}


def _flatten() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for service, doc in CATALOG.items():
        for action, meta in doc["actions"].items():
            if isinstance(meta, str):
                summary, params, flags = meta, {}, {}
            else:
                summary = meta[0]
                params = meta[1] if len(meta) > 1 else {}
                flags = meta[2] if len(meta) > 2 else {}
            items.append(
                {
                    "service": service,
                    "version": doc["version"],
                    "product": doc["product"],
                    "action": action,
                    "summary": summary,
                    "requiresRegion": flags.get("requiresRegion", True) is not False,
                    "dangerous": flags.get("dangerous", False) is True,
                    "params": params,
                    "docUrl": doc["doc"],
                }
            )
    return items


ACTIONS = _flatten()


def resolve_version(service: str) -> str | None:
    doc = CATALOG.get(service)
    return doc["version"] if doc else None


def action_meta(service: str, action: str) -> dict[str, Any] | None:
    doc = CATALOG.get(service)
    if not doc:
        return None
    return doc["actions"].get(action)


def search_actions(query: str, limit: int = 8) -> list[dict[str, Any]]:
    terms = [t for t in re.split(r"[\s,;/]+", query.lower()) if t]
    if not terms:
        return ACTIONS[:limit]
    scored: list[tuple[int, dict[str, Any]]] = []
    for entry in ACTIONS:
        haystack = " ".join(
            [entry["service"], entry["product"], entry["action"], entry["summary"]]
            + list(entry["params"].keys())
            + [str(v) for v in entry["params"].values()]
        ).lower()
        score = 0
        for term in terms:
            if term not in haystack:
                continue
            score += 1
            if term in entry["action"].lower():
                score += 2
            if term == entry["service"]:
                score += 1
        if score:
            scored.append((score, entry))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [entry for _, entry in scored[:limit]]


# ============================================================== 签名与 HTTP 调用
TC3_ALGORITHM = "TC3-HMAC-SHA256"
CONTENT_TYPE = "application/json; charset=utf-8"
SERVICE_RE = re.compile(r"^[a-z][a-z0-9-]{1,30}$")
ACTION_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]{0,63}$")
REGION_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,30}$")
VERSION_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ApiError(Exception):
    pass


class CodeRejected(ValueError):
    pass


class AuthError(Exception):
    pass


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _hmac(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def sign_tc3(
    secret_id: str,
    secret_key: str,
    service: str,
    action: str,
    version: str,
    payload: str,
    region: str | None = None,
    token: str | None = None,
    timestamp: int | None = None,
    host: str | None = None,
) -> tuple[str, dict[str, str]]:
    """腾讯云 API 3.0 签名（TC3-HMAC-SHA256，POST + JSON）。"""
    ts = timestamp if timestamp is not None else int(time.time())
    date = time.strftime("%Y-%m-%d", time.gmtime(ts))
    host = host or f"{service}.tencentcloudapi.com"

    canonical_headers = (
        f"content-type:{CONTENT_TYPE}\nhost:{host}\nx-tc-action:{action.lower()}\n"
    )
    signed_headers = "content-type;host;x-tc-action"
    canonical_request = "\n".join(
        ["POST", "/", "", canonical_headers, signed_headers, _sha256_hex(payload)]
    )
    scope = f"{date}/{service}/tc3_request"
    string_to_sign = "\n".join([TC3_ALGORITHM, str(ts), scope, _sha256_hex(canonical_request)])

    key = _hmac(f"TC3{secret_key}".encode("utf-8"), date)
    key = _hmac(key, service)
    key = _hmac(key, "tc3_request")
    signature = hmac.new(key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    headers = {
        "Authorization": (
            f"{TC3_ALGORITHM} Credential={secret_id}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        ),
        "Content-Type": CONTENT_TYPE,
        "Host": host,
        "X-TC-Action": action,
        "X-TC-Timestamp": str(ts),
        "X-TC-Version": version,
    }
    if region:
        headers["X-TC-Region"] = region
    if token:
        headers["X-TC-Token"] = token
    return f"https://{host}/", headers


@dataclass(frozen=True)
class Credentials:
    secret_id: str
    secret_key: str
    token: str | None = None

    def fingerprint(self) -> str:
        return f"secretId:{self.secret_id[:6]}***" + (":sts" if self.token else "")


def parse_credentials(headers: dict[str, str]) -> Credentials | None:
    normalized = {k.lower(): v for k, v in headers.items()}
    raw = normalized.get("authorization", "")
    if raw:
        parts = raw.split(None, 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise AuthError("Authorization 只支持 Bearer 方案")
        token = parts[1].strip()
        if ":" not in token:
            try:
                token = base64.b64decode(token, validate=True).decode("utf-8")
            except (binascii.Error, UnicodeDecodeError) as exc:
                raise AuthError(
                    "Bearer 格式应为 <secretId>:<secretKey>[:<sessionToken>]，或整串 base64"
                ) from exc
        secret_id, _, rest = token.partition(":")
        secret_key, _, session = rest.partition(":")
        if not secret_id or not secret_key:
            raise AuthError("Bearer 缺少 secretId 或 secretKey")
        return Credentials(secret_id, secret_key, session or None)

    if _env_str("MCP_ALLOW_ENV_CREDENTIALS") == "1":
        secret_id = _env_str("TENCENTCLOUD_SECRET_ID")
        secret_key = _env_str("TENCENTCLOUD_SECRET_KEY")
        if secret_id and secret_key:
            return Credentials(secret_id, secret_key, _env_str("TENCENTCLOUD_SESSION_TOKEN") or None)
    return None


def _snake(action: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", action).lower()


@dataclass
class Ctx:
    """一次请求的上下文（无状态，每个 POST 重建）。"""

    credentials: Credentials | None = None
    engine: str = "api"
    default_region: str | None = None
    max_requests: int = 20
    timeout_ms: int = 20_000
    require_confirm: bool = False
    truncate: bool = True
    deadline: float | None = None

    @classmethod
    def build(cls, credentials: Credentials | None, query: dict[str, Any], deadline: float | None) -> "Ctx":
        engine = str(query.get("engine") or _env_str("MCP_ENGINE", "api")).lower()
        return cls(
            credentials=credentials,
            engine=engine if engine in {"api", "sdk"} else "api",
            default_region=_env_str("MCP_DEFAULT_REGION") or None,
            max_requests=_env_int("MCP_MAX_REQUESTS", 20),
            timeout_ms=_env_int("MCP_TIMEOUT_MS", 20_000),
            require_confirm=_env_str("MCP_REQUIRE_CONFIRM") == "1",
            truncate=str(query.get("truncateToolResult", "true")).lower() != "false",
            deadline=deadline,
        )

    def timeout(self, default_ms: int | None = None) -> float:
        base = max(1.0, (default_ms or self.timeout_ms) / 1000)
        if self.deadline is None:
            return base
        return max(1.0, min(base, self.deadline - time.monotonic()))


class TencentClient:
    """版本/region 推导 + confirm 安全闸 + 限流 + 超时，全在这里。"""

    def __init__(self, credentials: Credentials, ctx: Ctx) -> None:
        self.credentials = credentials
        self.ctx = ctx
        self.calls = 0

    def _resolve(
        self, service: Any, action: Any, params: Any, region: Any, version: Any, confirm: Any
    ) -> tuple[str, str, str, str | None, dict[str, Any]]:
        code = str(service or "").strip().lower()
        name = str(action or "").strip()
        if not SERVICE_RE.match(code):
            raise ApiError('service 不合规，应形如 "cvm"')
        if not ACTION_RE.match(name):
            raise ApiError('action 不合规，应形如 "DescribeInstances"')

        params = {} if params is None else params
        if not isinstance(params, dict):
            raise ApiError('params 必须是对象，如 {"Limit": 10}')
        if len(json.dumps(params, ensure_ascii=False)) > MAX_PARAMS_BYTES:
            raise ApiError(f"params 太大（>{MAX_PARAMS_BYTES} 字节）")

        ver = str(version) if version else resolve_version(code)
        if not ver:
            raise ApiError(
                f'无法确定 service="{code}" 的 version：目录里没有该产品。'
                f'请显式传 version，如 tencent.request(service="{code}", version="2017-03-12", action="{name}")'
            )
        if not VERSION_RE.match(ver):
            raise ApiError('version 应形如 "2017-03-12"')

        meta = action_meta(code, name) or {}
        reg = region or self.ctx.default_region
        if reg is not None:
            reg = str(reg)
            if not REGION_RE.match(reg):
                raise ApiError('region 应形如 "ap-guangzhou"')
        if not reg and meta.get("requiresRegion", True) is not False:
            raise ApiError(
                f"{code}:{name} 需要 region。请在 execute 里传 region（如 ap-guangzhou），"
                "或设环境变量 MCP_DEFAULT_REGION。"
            )
        if self.ctx.require_confirm and meta.get("dangerous") and confirm is not True:
            raise ApiError(f"安全闸：{code}:{name} 是写/删类高危操作，需要 confirm=True")

        return code, name, ver, reg, params

    def request(
        self,
        service: Any = None,
        action: Any = None,
        params: Any = None,
        region: Any = None,
        version: Any = None,
        confirm: Any = False,
    ) -> dict[str, Any]:
        if self.calls >= self.ctx.max_requests:
            raise ApiError(
                f"单次 execute 最多 {self.ctx.max_requests} 次 API 请求（已打满），"
                "请在代码里合并调用或调大 MCP_MAX_REQUESTS。"
            )
        code, name, ver, reg, body = self._resolve(service, action, params, region, version, confirm)
        self.calls += 1

        started = time.monotonic()
        if self.ctx.engine == "sdk":
            result = self._call_sdk(code, name, ver, reg, body)
        else:
            result = self._call_api(code, name, ver, reg, body)
        result["_latencyMs"] = int((time.monotonic() - started) * 1000)
        return result

    def _call_api(
        self, service: str, action: str, version: str, region: str | None, params: dict[str, Any]
    ) -> dict[str, Any]:
        payload = json.dumps(params, ensure_ascii=False, separators=(",", ":"))
        url, headers = sign_tc3(
            self.credentials.secret_id,
            self.credentials.secret_key,
            service,
            action,
            version,
            payload,
            region=region,
            token=self.credentials.token,
        )
        req = urllib.request.Request(url, data=payload.encode("utf-8"), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.ctx.timeout()) as resp:
                text = resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise ApiError(f"HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
            raise ApiError(f"{service}:{action} 请求失败或超时：{exc}") from exc

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ApiError(f"非 JSON 响应：{text[:300]}") from exc

        reply = data.get("Response", data) if isinstance(data, dict) else data
        if not isinstance(reply, dict):
            raise ApiError(f"异常响应：{str(reply)[:300]}")
        error = reply.get("Error")
        if error:
            raise ApiError(
                f"[{error.get('Code')}] {error.get('Message')} (RequestId: {reply.get('RequestId')})"
            )
        reply["_engine"] = "api"
        return reply

    def _call_sdk(
        self, service: str, action: str, version: str, region: str | None, params: dict[str, Any]
    ) -> dict[str, Any]:
        """可选引擎：需自行 pip install tencentcloud-sdk-python-<product>。"""
        import importlib

        vpath = version.replace("-", "")
        try:
            client_module = importlib.import_module(f"tencentcloud.{service}.v{vpath}.{service}_client")
            models_module = importlib.import_module(f"tencentcloud.{service}.v{vpath}.models")
            from tencentcloud.common.credential import Credential
        except ModuleNotFoundError as exc:
            raise ApiError(
                "engine=sdk 需要 pip install tencentcloud-sdk-python-common 与 "
                "tencentcloud-sdk-python-<product>；SCF 上建议直接用 engine=api"
            ) from exc

        client = getattr(client_module, f"{service.capitalize()}Client")(
            Credential(
                self.credentials.secret_id,
                self.credentials.secret_key,
                self.credentials.token or "",
            ),
            region or "",
        )
        req = getattr(models_module, f"{action}Request")()
        req.from_json_string(json.dumps(params, ensure_ascii=False))
        result = json.loads(getattr(client, _snake(action))(req).to_json_string())
        result["_engine"] = "sdk"
        return result


class Facade:
    """沙箱里的 `tencent`：tencent.request({...}) 或 tencent.request(service=..., ...)"""

    ALLOWED = ("service", "action", "params", "region", "version", "confirm")

    def __init__(self, client: TencentClient) -> None:
        self._client = client

    @property
    def calls(self) -> int:
        return self._client.calls

    async def request(self, spec: Any = None, **kwargs: Any) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        if spec is not None:
            if not isinstance(spec, dict):
                raise ApiError("request() 第一个参数必须是 dict")
            merged.update(spec)
        merged.update(kwargs)
        unknown = sorted(set(merged) - set(self.ALLOWED))
        if unknown:
            raise ApiError(f"request() 不支持的参数：{unknown}，可用：{list(self.ALLOWED)}")
        return self._client.request(**merged)

    async def call(self, spec: Any = None, **kwargs: Any) -> dict[str, Any]:
        return await self.request(spec, **kwargs)


# =================================================================== 代码沙箱
_SAFE_NAMES = (
    "abs all any bool dict divmod enumerate Exception filter float int isinstance len list "
    "map max min range repr reversed round RuntimeError set slice sorted str sum tuple "
    "TypeError ValueError zip"
).split()

SAFE_BUILTINS: dict[str, Any] = {name: getattr(builtins, name) for name in _SAFE_NAMES}

_BLOCKED_NAMES = {
    "eval", "exec", "open", "compile", "input", "getattr", "setattr", "delattr",
    "vars", "globals", "locals", "breakpoint", "memoryview", "object",
}


def _validate(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise CodeRejected("沙箱不允许 import；可用：tencent / spec / search_actions / region")
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            raise CodeRejected("沙箱不允许 global / nonlocal")
        if isinstance(node, ast.Name) and (node.id.startswith("__") or node.id in _BLOCKED_NAMES):
            raise CodeRejected(f"沙箱不允许使用 {node.id}")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise CodeRejected("沙箱不允许访问双下划线属性")


def run_code(code: str, env: dict[str, Any], timeout_s: float = 15.0) -> Any:
    """跑模型写的 Python。带限制的 exec，不是安全边界。"""
    if not code or not code.strip():
        raise CodeRejected("code 不能为空")
    if len(code.encode("utf-8")) > MAX_CODE_BYTES:
        raise CodeRejected(f"code 太长（>{MAX_CODE_BYTES} 字节）")

    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError:
        # 模型可能直接写顶层 return / await，当成函数体再解析
        _validate(ast.parse("async def __code__():\n" + textwrap.indent(code, "    ")))
        body = code
    else:
        _validate(tree)
        if tree.body and isinstance(tree.body[-1], ast.Expr):
            last = tree.body[-1]
            tree.body[-1] = ast.Return(value=last.value)
        body = "\n".join(ast.unparse(node) for node in tree.body) or "pass"

    module = compile("async def __code__():\n" + textwrap.indent(body, "    "), "<mcp-code>", "exec")
    namespace: dict[str, Any] = {"__builtins__": SAFE_BUILTINS, **env}
    exec(module, namespace)  # noqa: S102 - 受限 builtins + AST 白名单
    entry = namespace["__code__"]

    async def runner() -> Any:
        return await asyncio.wait_for(entry(), timeout=timeout_s)

    value = asyncio.run(runner())
    if inspect.iscoroutine(value):
        value.close()
        raise CodeRejected("返回了未 await 的协程，请写 `return await tencent.request(...)`")
    return value


# ======================================================================= 工具
TOOLS: list[dict[str, Any]] = [
    {
        "name": "search",
        "title": "Search Tencent Cloud API actions",
        "description": (
            "用代码查询腾讯云 Action 目录（不返回全量 schema）。写一段 Python 函数体，可用 await，必须 return。\n\n"
            '可用变量：spec["services"] / spec["actions"] / search_actions(keyword, limit=20) / total / region\n\n'
            '示例：return [a for a in spec["actions"] if a["service"] == "cvm"][:10]'
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"code": {"type": "string", "description": "Python 函数体，必须 return"}},
            "required": ["code"],
            "additionalProperties": False,
        },
    },
    {
        "name": "execute",
        "title": "Execute Tencent Cloud API calls via code",
        "description": (
            "用代码调用腾讯云 API。写一段 Python 函数体，只 return 需要的数据。\n\n"
            '可用：tencent.request({"service": "cvm", "action": "DescribeInstances", "params": {...}, "region": "ap-guangzhou"})\n'
            "  service = API 域名子域：cvm/vpc/cbs/clb/lighthouse/scf/tat/cam/sts/dnspod（未收录产品传 version）\n"
            "  params 平铺（腾讯云 RPC 风格），version/region 省略时自动推导\n"
            '示例：r = await tencent.request(service="cvm", action="DescribeInstances", params={"Limit": 20})\n'
            '      return [{"id": i["InstanceId"], "state": i["InstanceState"]} for i in r["InstanceSet"]]'
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python 函数体，必须 return"},
                "region": {"type": "string", "description": "本次执行地域，如 ap-guangzhou"},
                "explain": {"type": "string", "description": "一句话说明意图（审计用）"},
            },
            "required": ["code"],
            "additionalProperties": False,
        },
    },
    {
        "name": "docs",
        "title": "Look up Tencent Cloud API action docs",
        "description": "按关键词查 Action 的参数含义、是否需要 region、是否高危、官方文档链接。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": '关键词，如 "cvm 实例"'},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "whoami",
        "title": "Who am I",
        "description": "返回当前连接的身份、执行引擎、默认地域。用于区分连接、排查权限。",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]

INSTRUCTIONS = (
    f"腾讯云 API MCP 服务器 v{VERSION}，Code Mode：4 个工具覆盖全量 API。\n"
    "1) 不确定接口先用 search 或 docs；2) 用 execute 写 Python 调 tencent.request(...)；3) whoami 看当前身份。\n"
    'params 平铺（不要包成 {"Params": {...}}）；大部分 Action 需要 region；'
    "单次 execute 有 API 调用次数上限，结果超长会被截断，只返回必要字段。"
)


def _text(value: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": value}]}


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except (TypeError, ValueError) as exc:
        return f"结果无法序列化：{exc}"


def _truncate(text: str, ctx: Ctx) -> str:
    if not ctx.truncate or len(text) <= MAX_RESULT_CHARS:
        return text
    return (
        text[:MAX_RESULT_CHARS]
        + f"\n--- TRUNCATED ---\n（原 {len(text)} 字符；只返回必要字段，或加 ?truncateToolResult=false）"
    )


def _code_of(arguments: dict[str, Any]) -> str:
    code = arguments.get("code")
    if not isinstance(code, str) or not code.strip():
        raise CodeRejected("code 必须是非空字符串")
    return code


def _creds_of(ctx: Ctx) -> Credentials:
    if ctx.credentials is None:
        raise AuthError("调用工具需要凭据：Authorization: Bearer <secretId>:<secretKey>[:<sessionToken>]")
    return ctx.credentials


def call_tool(name: str, arguments: Any, ctx: Ctx) -> dict[str, Any]:
    args = arguments or {}
    if not isinstance(args, dict):
        raise ApiError("arguments 必须是对象")

    if name == "search":
        value = run_code(
            _code_of(args),
            {
                "spec": {"services": CATALOG, "actions": ACTIONS},
                "search_actions": lambda q, limit=20: search_actions(str(q), min(int(limit), 50)),
                "total": len(ACTIONS),
                "region": ctx.default_region,
            },
            timeout_s=ctx.timeout(15_000),
        )
        return _text(_truncate(_stringify(value), ctx))

    if name == "execute":
        client = TencentClient(_creds_of(ctx), ctx)
        region = args.get("region") or ctx.default_region
        value = run_code(
            _code_of(args),
            {
                "tencent": Facade(client),
                "region": region,
                "spec": {"services": CATALOG, "actions": ACTIONS},
            },
            timeout_s=ctx.timeout(15_000),
        )
        payload: dict[str, Any] = {
            "ok": True,
            "engine": ctx.engine,
            "region": region,
            "apiCalls": client.calls,
            "result": value,
        }
        if args.get("explain"):
            payload["explain"] = args["explain"]
        return _text(_truncate(_stringify(payload), ctx))

    if name == "docs":
        query = args.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ApiError("query 必须是非空字符串")
        entries = search_actions(query, int(args.get("limit") or 8))
        if not entries:
            return _text(f'没找到匹配 "{query}" 的 Action。换个更短的关键词，或用 search 遍历 spec["actions"]。')
        blocks = []
        for entry in entries:
            flags = ("需要 region" if entry["requiresRegion"] else "不需要 region") + (
                "，写/删类操作" if entry["dangerous"] else "，只读"
            )
            params = (
                "\n".join(f"  - {k}：{v}" for k, v in entry["params"].items())
                or "  - （未收录，见官方文档）"
            )
            blocks.append(
                f"### {entry['service']}:{entry['action']}（{entry['product']}，version {entry['version']}）\n"
                f"{entry['summary']}\n- {flags}\n- 常用参数：\n{params}\n- 文档：{entry['docUrl']}"
            )
        return _text("\n\n".join(blocks))

    if name == "whoami":
        creds = _creds_of(ctx)
        client = TencentClient(creds, ctx)
        source, note = "sts:GetCallerIdentity", None
        try:
            identity = client.request("sts", "GetCallerIdentity", version="2018-08-13")
        except ApiError as exc:
            source = "cam:GetUserAppId"
            note = f"sts 失败，回退 CAM：{exc}"
            identity = client.request("cam", "GetUserAppId", version="2019-01-16")
        payload = {
            "ok": True,
            "source": source,
            "credential": creds.fingerprint(),
            "engine": ctx.engine,
            "defaultRegion": ctx.default_region,
            "identity": identity,
        }
        if note:
            payload["note"] = note
        return _text(_truncate(_stringify(payload), ctx))

    raise ApiError(f"未知工具：{name}")


# ================================================================= MCP 协议层
CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
    "Access-Control-Allow-Headers": "authorization, content-type, accept, mcp-protocol-version, mcp-session-id",
    "Access-Control-Max-Age": "86400",
}
_ACCEPTED = object()


def _rpc_ok(msg_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _rpc_err(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _json_http(status: int, payload: Any) -> tuple[int, dict[str, str], str]:
    headers = dict(CORS)
    headers["Content-Type"] = "application/json; charset=utf-8"
    return status, headers, json.dumps(payload, ensure_ascii=False)


def _accepted() -> tuple[int, dict[str, str], str]:
    return 202, {"Content-Type": "application/json; charset=utf-8", **CORS}, ""


def _handle_message(message: Any, headers: dict[str, str], query: dict[str, Any], deadline: float | None):
    if not isinstance(message, dict) or not isinstance(message.get("method"), str):
        return _rpc_err(
            message.get("id") if isinstance(message, dict) else None,
            -32600,
            "无效的 JSON-RPC 请求",
        )

    msg_id, method = message.get("id"), message["method"]
    params = message.get("params")
    params = params if isinstance(params, dict) else {}

    if method.startswith("notifications/"):
        return _ACCEPTED

    if method == "initialize":
        requested = params.get("protocolVersion")
        return _rpc_ok(
            msg_id,
            {
                "protocolVersion": requested if requested in SUPPORTED_PROTOCOLS else DEFAULT_PROTOCOL,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "tencentcloud-mcp", "version": VERSION},
                "instructions": INSTRUCTIONS,
            },
        )

    if method == "ping":
        return _rpc_ok(msg_id, {})
    if method == "tools/list":
        return _rpc_ok(msg_id, {"tools": TOOLS})
    if method == "resources/list":
        return _rpc_ok(msg_id, {"resources": []})
    if method == "prompts/list":
        return _rpc_ok(msg_id, {"prompts": []})

    if method == "tools/call":
        name = params.get("name")
        if not isinstance(name, str) or not name:
            return _rpc_err(msg_id, -32602, "tools/call 缺少 name")
        try:
            ctx = Ctx.build(parse_credentials(headers), query, deadline)
            return _rpc_ok(msg_id, call_tool(name, params.get("arguments"), ctx))
        except AuthError as exc:
            return _rpc_err(msg_id, -32001, str(exc))
        except (ApiError, CodeRejected) as exc:
            return _rpc_ok(msg_id, {"content": [{"type": "text", "text": str(exc)}], "isError": True})
        except Exception as exc:  # noqa: BLE001 - 别让网关 5xx
            return _rpc_ok(
                msg_id, {"content": [{"type": "text", "text": f"工具异常：{exc}"}], "isError": True}
            )

    return _rpc_err(msg_id, -32601, f"不支持的方法：{method}")


def handle_http(
    method: str,
    path: str,
    headers: dict[str, str],
    body: str,
    query: dict[str, Any] | None = None,
    deadline: float | None = None,
) -> tuple[int, dict[str, str], str]:
    """HTTP -> JSON-RPC。SCF Web 函数与本地服务器都走这里。"""
    method = (method or "POST").upper()
    query = query or {}

    if method == "OPTIONS":
        return 200, dict(CORS), ""
    if method != "POST":
        status, resp_headers, text = _json_http(405, _rpc_err(None, -32000, "无状态 MCP 服务器只接受 POST"))
        resp_headers["Allow"] = "POST, OPTIONS"
        return status, resp_headers, text
    if not body.strip():
        return _json_http(400, _rpc_err(None, -32700, "请求体为空"))

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        return _json_http(400, _rpc_err(None, -32700, f"JSON 解析失败：{exc}"))

    if isinstance(payload, list):
        responses = [
            outcome
            for outcome in (_handle_message(item, headers, query, deadline) for item in payload)
            if outcome is not _ACCEPTED
        ]
        return _json_http(200, responses) if responses else _accepted()

    outcome = _handle_message(payload, headers, query, deadline)
    return _accepted() if outcome is _ACCEPTED else _json_http(200, outcome)


# ================================================================== HTTP 服务器
REQUEST_TIMEOUT_S = float(_env_int("MCP_REQUEST_TIMEOUT_S", 55))


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = f"tencentcloud-mcp/{VERSION}"

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

        status, resp_headers, text = handle_http(
            method, parts.path, headers, body, query, time.monotonic() + REQUEST_TIMEOUT_S
        )

        accept = headers.get("accept", "")
        wants_sse = query.get("stream") == "1" or (
            "text/event-stream" in accept and "application/json" not in accept
        )
        if wants_sse and status == 200 and text:
            self._send_sse(text)
        else:
            self._send(status, resp_headers, text)

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


# ======================================================================= 自检

def _selftest() -> int:
    ok = True

    def check(name: str, fn) -> None:
        nonlocal ok
        try:
            fn()
            print(f"  ok   {name}")
        except Exception as exc:  # noqa: BLE001
            ok = False
            print(f"  FAIL {name}: {exc}")

    def t_tc3() -> None:
        url, headers = sign_tc3(
            "AKIDEXAMPLE",
            "SECRET",
            "cvm",
            "DescribeInstances",
            "2017-03-12",
            "{}",
            region="ap-guangzhou",
            timestamp=1551113065,
        )
        assert url == "https://cvm.tencentcloudapi.com/", url
        assert "2019-02-25/cvm/tc3_request" in headers["Authorization"], headers
        assert len(headers["Authorization"].rsplit("Signature=", 1)[1]) == 64

    def t_catalog() -> None:
        assert len(ACTIONS) >= 50, len(ACTIONS)
        assert any(h["action"] == "DescribeInstances" for h in search_actions("cvm 实例"))

    def t_sandbox() -> None:
        assert run_code("1 + 1", {}) == 2

        async def fake(**kwargs):
            return {"total": 2}

        class Fake:
            request = staticmethod(fake)

        assert run_code('r = await tencent.request(action="x")\nreturn r["total"]', {"tencent": Fake()}) == 2
        for bad in ("import os", "return __import__('os')", "open('/etc/passwd')"):
            try:
                run_code(bad, {})
            except CodeRejected:
                continue
            raise AssertionError(f"应该被拒绝：{bad}")

    def t_protocol() -> None:
        status, _, body = handle_http(
            "POST", "/mcp", {}, json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        )
        assert status == 200, status
        names = [tool["name"] for tool in json.loads(body)["result"]["tools"]]
        assert names == ["search", "execute", "docs", "whoami"], names
        status, _, _ = handle_http(
            "POST", "/mcp", {}, json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
        )
        assert status == 202, status
        status, _, _ = handle_http("GET", "/mcp", {}, "")
        assert status == 405, status

    def t_tools() -> None:
        text = call_tool("docs", {"query": "cvm 实例"}, Ctx())["content"][0]["text"]
        assert "DescribeInstances" in text, text[:200]

    print(f"tencentcloud-mcp {VERSION} selftest")
    for name, fn in [
        ("TC3 签名", t_tc3),
        ("Action 目录", t_catalog),
        ("代码沙箱", t_sandbox),
        ("MCP 协议", t_protocol),
        ("docs 工具", t_tools),
    ]:
        check(name, fn)
    print("全部通过" if ok else "有失败项")
    return 0 if ok else 1


# ======================================================================= 入口
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="tencentcloud-mcp (single file)")
    parser.add_argument("--host", default=_env_str("MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=_env_int("MCP_PORT", 8787))
    parser.add_argument("--selftest", action="store_true", help="自检后退出（不联网）")
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.daemon_threads = True
    print(f"tencentcloud-mcp {VERSION} listening on http://{args.host}:{args.port}/mcp", flush=True)
    print(
        f"试一下：curl -s localhost:{args.port}/mcp -H 'content-type: application/json' "
        '-d \'{"jsonrpc":"2.0","id":1,"method":"tools/list"}\'',
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbye", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
