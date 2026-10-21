from __future__ import annotations

import json
import re
import socket
import time
import urllib.error
import urllib.request
from typing import Any

from . import catalog, tc3
from .auth import Credentials
from .errors import TencentApiError, ValidationError

SERVICE_RE = re.compile(r"^[a-z][a-z0-9-]{1,30}$")
ACTION_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]{0,63}$")
REGION_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,30}$")
VERSION_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

MAX_PARAMS_BYTES = 256 * 1024
ALLOWED_KEYS = ("service", "action", "params", "region", "version", "confirm")


def _snake(action: str) -> str:
    """DescribeInstances -> describe_instances（Python SDK 方法名）"""
    out: list[str] = []
    for index, char in enumerate(action):
        if char.isupper() and index:
            out.append("_")
        out.append(char.lower())
    return "".join(out)


class TencentClient:
    """统一服务：版本/region 推导、限流、超时都在这里。"""

    def __init__(
        self,
        credentials: Credentials,
        engine: str = "api",
        default_region: str | None = None,
        max_requests: int = 20,
        timeout_ms: int = 20_000,
        require_confirm: bool = False,
        deadline: float | None = None,
    ) -> None:
        self.credentials = credentials
        self.engine = engine
        self.default_region = default_region
        self.max_requests = max_requests
        self.timeout_ms = timeout_ms
        self.require_confirm = require_confirm
        self.deadline = deadline
        self.calls = 0

    # ------------------------------------------------------------------ 校验
    def _resolve(
        self,
        service: Any,
        action: Any,
        params: Any,
        region: Any,
        version: Any,
        confirm: Any,
    ) -> tuple[str, str, str, str | None, dict[str, Any]]:
        service_code = str(service or "").strip().lower()
        action_name = str(action or "").strip()
        if not SERVICE_RE.match(service_code):
            raise ValidationError('service 不合规，应形如 "cvm"（= API 域名子域，小写字母/数字/连字符）')
        if not ACTION_RE.match(action_name):
            raise ValidationError('action 不合规，应形如 "DescribeInstances"（大驼峰）')

        if params is None:
            params = {}
        if not isinstance(params, dict):
            raise ValidationError("params 必须是对象，例如 {\"Limit\": 10}")
        try:
            params_bytes = len(json.dumps(params, ensure_ascii=False))
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"params 不能序列化为 JSON：{exc}") from exc
        if params_bytes > MAX_PARAMS_BYTES:
            raise ValidationError(f"params 太大（>{MAX_PARAMS_BYTES} 字节）")

        version_value = str(version) if version else catalog.resolve_version(service_code)
        if not version_value:
            raise ValidationError(
                f'无法确定 service="{service_code}" 的 version：目录里没有这个产品。'
                f'请显式传 version，例如 {{ service: "{service_code}", version: "2017-03-12", action: "{action_name}" }}'
            )
        if not VERSION_RE.match(version_value):
            raise ValidationError('version 应形如 "2017-03-12"')

        meta = catalog.action_meta(service_code, action_name) or {}
        requires_region = meta.get("requiresRegion", True) is not False

        region_value = region or self.default_region
        if region_value is not None:
            region_value = str(region_value)
            if not REGION_RE.match(region_value):
                raise ValidationError('region 应形如 "ap-guangzhou"')
        if not region_value and requires_region:
            raise ValidationError(
                f"{service_code}:{action_name} 需要 region。请在 execute 参数里传 region（如 \"ap-guangzhou\"），"
                "或设置环境变量 MCP_DEFAULT_REGION。"
            )

        if self.require_confirm and meta.get("dangerous") and confirm is not True:
            raise ValidationError(
                f"安全闸：{service_code}:{action_name} 是写/删类高危操作，需要 confirm=True（先向用户确认再重试）"
            )

        return service_code, action_name, version_value, region_value, params

    def _timeout(self) -> float:
        base = max(1.0, self.timeout_ms / 1000)
        if self.deadline is None:
            return base
        remaining = self.deadline - time.monotonic()
        return max(1.0, min(base, remaining))

    # ------------------------------------------------------------------ 调用
    def request(
        self,
        service: Any = None,
        action: Any = None,
        params: Any = None,
        region: Any = None,
        version: Any = None,
        confirm: Any = False,
    ) -> dict[str, Any]:
        if self.calls >= self.max_requests:
            raise ValidationError(
                f"单次 execute 最多发起 {self.max_requests} 次 API 请求（已打满）。"
                "请在代码里合并调用，或调大环境变量 MCP_MAX_REQUESTS。"
            )

        code, name, ver, reg, body = self._resolve(service, action, params, region, version, confirm)
        self.calls += 1
        if self.engine == "sdk":
            return self._call_sdk(code, name, ver, reg, body)
        return self._call_api(code, name, ver, reg, body)

    def _call_api(
        self,
        service: str,
        action: str,
        version: str,
        region: str | None,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        payload = json.dumps(params, ensure_ascii=False, separators=(",", ":"))
        url, headers = tc3.sign(
            secret_id=self.credentials.secret_id,
            secret_key=self.credentials.secret_key,
            service=service,
            action=action,
            version=version,
            payload=payload,
            region=region,
            token=self.credentials.token,
        )
        request = urllib.request.Request(
            url, data=payload.encode("utf-8"), headers=headers, method="POST"
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=self._timeout()) as response:
                text = response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise TencentApiError(f"HTTP{exc.code}", detail) from exc
        except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
            raise ValidationError(f"{service}:{action} 请求失败或超时：{exc}") from exc

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise TencentApiError("NonJsonResponse", f"HTTP 响应不是 JSON：{text[:300]}") from exc

        reply = data.get("Response", data) if isinstance(data, dict) else data
        if not isinstance(reply, dict):
            raise TencentApiError("UnexpectedResponse", str(reply)[:300])

        error = reply.get("Error")
        if error:
            raise TencentApiError(
                str(error.get("Code", "Unknown")),
                str(error.get("Message", "")),
                reply.get("RequestId"),
            )

        reply["_engine"] = "api"
        reply["_latencyMs"] = int((time.monotonic() - started) * 1000)
        return reply

    def _call_sdk(
        self,
        service: str,
        action: str,
        version: str,
        region: str | None,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """可选引擎：需自行安装 tencentcloud-sdk-python-<product>。"""
        import importlib

        version_path = version.replace("-", "")
        try:
            client_module = importlib.import_module(
                f"tencentcloud.{service}.v{version_path}.{service}_client"
            )
            models_module = importlib.import_module(
                f"tencentcloud.{service}.v{version_path}.models"
            )
            from tencentcloud.common.credential import Credential
        except ModuleNotFoundError as exc:
            raise ValidationError(
                "engine=sdk 需要 pip install tencentcloud-sdk-python-common 与 tencentcloud-sdk-python-<product>；"
                "SCF 上建议直接用 engine=api（零依赖、体积小）"
            ) from exc

        started = time.monotonic()
        client_cls = getattr(client_module, f"{service.capitalize()}Client")
        request_cls = getattr(models_module, f"{action}Request")
        client = client_cls(
            Credential(
                self.credentials.secret_id,
                self.credentials.secret_key,
                self.credentials.token or "",
            ),
            region or "",
        )
        request = request_cls()
        request.from_json_string(json.dumps(params, ensure_ascii=False))
        response = getattr(client, _snake(action))(request)
        result = json.loads(response.to_json_string())
        result["_engine"] = "sdk"
        result["_latencyMs"] = int((time.monotonic() - started) * 1000)
        return result


class TencentFacade:
    """沙箱里看到的 `tencent` 对象。

    - `await tencent.request({"service": "cvm", "action": "DescribeInstances"})`
    - `await tencent.request(service="cvm", action="DescribeInstances", params={...})`
    """

    def __init__(self, client: TencentClient) -> None:
        self._client = client

    @property
    def calls(self) -> int:
        return self._client.calls

    async def request(self, spec: Any = None, **kwargs: Any) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        if spec is not None:
            if not isinstance(spec, dict):
                raise ValidationError("request() 的第一个参数必须是对象(dict)")
            merged.update(spec)
        merged.update(kwargs)
        unknown = sorted(set(merged) - set(ALLOWED_KEYS))
        if unknown:
            raise ValidationError(f"request() 不支持这些参数：{unknown}，可用：{list(ALLOWED_KEYS)}")
        return self._client.request(**merged)

    async def call(self, spec: Any = None, **kwargs: Any) -> dict[str, Any]:
        return await self.request(spec, **kwargs)
