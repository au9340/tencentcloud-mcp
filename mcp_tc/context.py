from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .auth import Credentials

DEFAULT_TIMEOUT_MS = 20_000
DEFAULT_MAX_REQUESTS = 20


def _env_int(name: str, default: int) -> int:
    import os

    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass
class RequestContext:
    """一次 MCP 请求的上下文（无状态：每个 POST 重新构建）。"""

    credentials: Credentials | None = None
    engine: str = "api"
    default_region: str | None = None
    max_requests: int = DEFAULT_MAX_REQUESTS
    timeout_ms: int = DEFAULT_TIMEOUT_MS
    require_confirm: bool = False
    truncate: bool = True
    deadline: float | None = None

    @classmethod
    def build(
        cls,
        credentials: Credentials | None,
        query: dict[str, Any] | None = None,
        deadline: float | None = None,
    ) -> "RequestContext":
        import os

        query = query or {}
        engine = str(query.get("engine") or os.environ.get("MCP_ENGINE") or "api").lower()
        if engine not in {"api", "sdk"}:
            engine = "api"
        truncate = str(query.get("truncateToolResult", "true")).lower() != "false"
        return cls(
            credentials=credentials,
            engine=engine,
            default_region=os.environ.get("MCP_DEFAULT_REGION") or None,
            max_requests=_env_int("MCP_MAX_REQUESTS", DEFAULT_MAX_REQUESTS),
            timeout_ms=_env_int("MCP_TIMEOUT_MS", DEFAULT_TIMEOUT_MS),
            require_confirm=os.environ.get("MCP_REQUIRE_CONFIRM") == "1",
            truncate=truncate,
            deadline=deadline,
        )

    def remaining_s(self) -> float | None:
        if self.deadline is None:
            return None
        return max(0.0, self.deadline - time.monotonic())
