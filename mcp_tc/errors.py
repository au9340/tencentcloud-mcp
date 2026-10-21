class McpError(Exception):
    """JSON-RPC 层错误"""

    def __init__(self, message: str, code: int = -32603):
        super().__init__(message)
        self.code = code


class AuthError(Exception):
    """缺少或无法解析凭据"""


class ValidationError(ValueError):
    """入参校验失败"""


class CodeRejected(ValueError):
    """模型代码未通过沙箱校验"""


class TencentApiError(Exception):
    """腾讯云 API 返回 Response.Error"""

    def __init__(self, code: str, message: str, request_id: str | None = None):
        suffix = f" (RequestId: {request_id})" if request_id else ""
        super().__init__(f"[{code}] {message}{suffix}")
        self.code = code
        self.request_id = request_id
