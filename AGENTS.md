# AGENTS.md

给在本仓库里干活的 AI agent 的硬约束。

## 不改的东西

- 工具面固定 4 个：`search` / `execute` / `docs` / `whoami`。**不要**新增 `list_instances` 这类专用工具，那正是 Code Mode 要避免的方向。
- 保持**零第三方依赖**（`requirements.txt` 为空是特性，不是遗漏）。SCF 上传 zip 就能跑，不要引入 `mcp`、`FastAPI`、`pydantic`。
- 保持**无状态**：每个 POST 重建 `RequestContext`，服务端不存会话、不存凭据。

## 改代码时注意

- 面向 Python **3.10**（`X | None` 写法可用，`match` 可用，不要用 3.11+ 新特性）。
- 所有出网调用必须走 `mcp_tc/client.py::TencentClient.request`，否则会绕过版本推导、region 校验、confirm 安全闸和限流。
- 任何 model-facing 的文本必须过 `tools._truncate`。
- 沙箱新增能力（如新变量）要同时改 `sandbox.py` 的 `SAFE_BUILTINS`/AST 校验与 `tools.py` 的 env 构造。
- 响应必须是 SCF 的 `{isBase64Encoded, statusCode, headers, body}` 形状。

## 提交前

```bash
make test        # 无网络、无密钥
```
