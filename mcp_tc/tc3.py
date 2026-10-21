from __future__ import annotations

import hashlib
import hmac
import time

ALGORITHM = "TC3-HMAC-SHA256"
CONTENT_TYPE = "application/json; charset=utf-8"


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _hmac(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def sign(
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
    """腾讯云 API 3.0 签名（TC3-HMAC-SHA256，POST + JSON）。

    文档：https://cloud.tencent.com/document/api/213/30654
    """
    ts = timestamp if timestamp is not None else int(time.time())
    date = time.strftime("%Y-%m-%d", time.gmtime(ts))
    host = host or f"{service}.tencentcloudapi.com"

    canonical_headers = (
        f"content-type:{CONTENT_TYPE}\n"
        f"host:{host}\n"
        f"x-tc-action:{action.lower()}\n"
    )
    signed_headers = "content-type;host;x-tc-action"

    canonical_request = "\n".join(
        ["POST", "/", "", canonical_headers, signed_headers, _sha256_hex(payload)]
    )

    credential_scope = f"{date}/{service}/tc3_request"
    string_to_sign = "\n".join(
        [ALGORITHM, str(ts), credential_scope, _sha256_hex(canonical_request)]
    )

    secret_date = _hmac(f"TC3{secret_key}".encode("utf-8"), date)
    secret_service = _hmac(secret_date, service)
    secret_signing = _hmac(secret_service, "tc3_request")
    signature = hmac.new(
        secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    headers = {
        "Authorization": (
            f"{ALGORITHM} Credential={secret_id}/{credential_scope}, "
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
