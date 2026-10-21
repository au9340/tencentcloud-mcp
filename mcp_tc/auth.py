from __future__ import annotations

import base64
import binascii
import os
from dataclasses import dataclass

from .errors import AuthError


@dataclass(frozen=True)
class Credentials:
    secret_id: str
    secret_key: str
    token: str | None = None

    def fingerprint(self) -> str:
        masked = self.secret_id[:6] + "***"
        return f"secretId:{masked}" + (":sts" if self.token else "")


def _decode_bearer(raw: str) -> str:
    """支持 <id>:<key>[:token] 与整串 base64。"""
    if ":" in raw:
        return raw
    try:
        return base64.b64decode(raw, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise AuthError(
            "Bearer token 格式应为 <secretId>:<secretKey>[:<sessionToken>]，或整串 base64。"
        ) from exc


def allow_env_fallback() -> bool:
    return os.environ.get("MCP_ALLOW_ENV_CREDENTIALS", "") == "1"


def resolve_credentials(headers: dict[str, str]) -> Credentials | None:
    """透传模式：调用方自己的 secretId/secretKey，服务端不存凭据。"""
    normalized = {k.lower(): v for k, v in headers.items()}
    header = normalized.get("authorization", "")

    if header:
        parts = header.split(None, 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise AuthError("Authorization 头只支持 Bearer 方案")
        decoded = _decode_bearer(parts[1].strip())
        secret_id, _, rest = decoded.partition(":")
        secret_key, _, token = rest.partition(":")
        if not secret_id or not secret_key:
            raise AuthError("Bearer token 缺少 secretId 或 secretKey")
        return Credentials(secret_id=secret_id, secret_key=secret_key, token=token or None)

    if allow_env_fallback():
        secret_id = os.environ.get("TENCENTCLOUD_SECRET_ID")
        secret_key = os.environ.get("TENCENTCLOUD_SECRET_KEY")
        if secret_id and secret_key:
            return Credentials(
                secret_id=secret_id,
                secret_key=secret_key,
                token=os.environ.get("TENCENTCLOUD_SESSION_TOKEN") or None,
            )

    return None
