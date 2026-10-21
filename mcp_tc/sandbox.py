from __future__ import annotations

import ast
import asyncio
import inspect
import textwrap
from typing import Any

from .errors import CodeRejected

SAFE_BUILTINS: dict[str, Any] = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "divmod": divmod,
    "enumerate": enumerate,
    "Exception": Exception,
    "filter": filter,
    "float": float,
    "int": int,
    "isinstance": isinstance,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "None": None,
    "print": lambda *a, **k: None,
    "range": range,
    "repr": repr,
    "reversed": reversed,
    "round": round,
    "RuntimeError": RuntimeError,
    "set": set,
    "slice": slice,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "TypeError": TypeError,
    "ValueError": ValueError,
    "zip": zip,
}

MAX_CODE_BYTES = 20_000


def _validate(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise CodeRejected("沙箱不允许 import：可用变量只有 tencent / spec / search_actions / region")
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            raise CodeRejected("沙箱不允许 global / nonlocal")
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise CodeRejected("沙箱不允许使用双下划线名称")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise CodeRejected("沙箱不允许访问双下划线属性")
        if isinstance(node, ast.Name) and node.id in {"eval", "exec", "open", "compile", "input", "__import__"}:
            raise CodeRejected(f"沙箱不允许使用 {node.id}")


def _prepare_body(code: str) -> str:
    """把最后一行表达式作为返回值；兼容模型直接写顶层 return 的写法。"""
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError:
        # 模型可能直接写了 `return {...}`（JS 习惯），当作函数体再试一次
        wrapped = "async def __check__():\n" + textwrap.indent(code or "pass", "    ")
        tree = ast.parse(wrapped)
        _validate(tree)
        return code

    _validate(tree)
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        last = tree.body[-1]
        tree.body[-1] = ast.Return(value=last.value)
    return "\n".join(ast.unparse(node) for node in tree.body) or "pass"


def run_code(
    code: str,
    globals_map: dict[str, Any],
    timeout_s: float = 15.0,
) -> Any:
    """执行模型写的 Python 代码（Code Mode 的执行层）。

    注意：这是“带限制的 exec”，不是安全边界。进程内没有 seccomp/namespace，
    能拿到的权限 = 该次请求的凭据 + 进程能做的事。生产多租户请下沉到独立的
    isolate / 容器执行器里。
    """
    if not code or not code.strip():
        raise CodeRejected("code 不能为空")
    if len(code.encode("utf-8")) > MAX_CODE_BYTES:
        raise CodeRejected(f"code 太长（>{MAX_CODE_BYTES} 字节）")

    body = _prepare_body(code)
    source = "async def __mcp_entry__():\n" + textwrap.indent(body, "    ")
    module = compile(source, "<mcp-code>", "exec")

    namespace: dict[str, Any] = {"__builtins__": SAFE_BUILTINS}
    exec(module, namespace)  # noqa: S102 - 受限 globals + AST 白名单
    entry = namespace["__mcp_entry__"]

    async def _runner() -> Any:
        return await asyncio.wait_for(entry(), timeout=timeout_s)

    result = asyncio.run(_runner())
    if inspect.iscoroutine(result):
        result.close()
        raise CodeRejected(
            "返回了一个未 await 的协程（第一次让模型写 await，比如 `return await tencent.request(...)`）"
        )
    return result
