# tencentcloud-mcp

> 4 个工具覆盖整个腾讯云 API。结构照搬 [`cloudflare/mcp`](https://github.com/cloudflare/mcp) 的 Code Mode：`search` 给一份瘦目录，`execute` 让你写代码打 API，另加 `docs` 和 `whoami`。

**Python 3.10、零第三方依赖、为 SCF Web 函数定制**：`make package` 出一个 ~50KB 的 zip，上传就能跑，没有 pip、没有依赖解压。

```
MCP 客户端 ──POST /mcp──► SCF Web 函数（serve.py, 0.0.0.0:9000）──TC3 签名──► *.tencentcloudapi.com
  Bearer secretId:secretKey        无状态、无存储                    用调用方自己的密钥
```

## Web 函数 vs 事件函数（对这套代码的影响）

| | 事件函数 `main_handler(event, ctx)` | **Web 函数**（本项目） |
| --- | --- | --- |
| 运行模型 | 每次调用喂一个完整 event，返回一个完整 body | 常驻进程 + 平台反向代理，自己监听 **9000** 端口 |
| 入口 | 控制台填 `main.main_handler` | 代码根目录的 **`scf_bootstrap`** 启动脚本 |
| 流式响应 | 不支持（必须一次给完） | 支持（SSE / chunked） |
| 前置组件 | 必须配 API 网关触发器 | 函数 URL / 默认域名直接可用 |
| 冷启动 | 较快 | 略慢（要起进程），可用预置并发 |
| 本项目支持 | 保留 `main.py` 作为兼容入口 | **默认路径** `serve.py` |

所以现在：`scf_bootstrap` → `python3 serve.py --host 0.0.0.0 --port 9000`，`main.py` 仍保留给事件函数用。

### Web 函数的三个坑（必看）

1. `scf_bootstrap` 必须**可执行**（`chmod +x`，`make package` 已处理；用 Finder/资源管理器重新打包会丢权限位）。
2. 必须 **LF** 换行、无 BOM。
3. 必须监听 **`0.0.0.0:9000`**（端口固定 9000，写 `127.0.0.1` 会被判定启动失败）。

## 部署（Web 函数，5 分钟）

```bash
make package        # → dist/tencentcloud-mcp.zip
```

1. 新建函数 → 函数类型选 **Web 函数** → 运行环境 **Python 3.10** → 上传 zip。
2. 启动脚本填 `scf_bootstrap`（默认值），无需填执行方法。
3. 超时 **60s**、内存 256MB（`serve.py` 单请求预算 55s，可用 `MCP_REQUEST_TIMEOUT_S` 调）。
4. 环境变量（可选）：`MCP_DEFAULT_REGION=ap-guangzhou`、`MCP_MAX_REQUESTS=20`、`MCP_REQUIRE_CONFIRM=1`。
5. 拿到**访问路径 / 函数 URL**，直接当 MCP 端点用（路径不敏感，任何 path 的 POST 都进 MCP）。

```bash
claude mcp add tencentcloud --transport http <URL> \
  --header "Authorization: Bearer $TENCENTCLOUD_SECRET_ID:$TENCENTCLOUD_SECRET_KEY"
```

自测：

```bash
curl -s <URL> -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | head -c 300
```

## 本地开发

```bash
python3.10 serve.py     # http://127.0.0.1:8787/mcp
make test               # 无网络、无密钥
```

Web 函数才能用的流式：加 `?stream=1`（或客户端 Accept 只要 `text/event-stream`），响应就是 `event: message` + `data: <json>` 的 SSE 分帧；默认仍是普通 JSON，兼容性最好。

## 4 个工具

| 工具 | 作用 |
| --- | --- |
| `search` | 写 Python 在 Action 目录里筛选：`spec["actions"]` / `search_actions(kw)` |
| `execute` | 写 Python 调 `tencent.request(...)`，在代码里串联/过滤/聚合，只 return 需要的字段 |
| `docs` | 关键词查参数含义、是否需要 region、是否高危、官方文档链接 |
| `whoami` | 当前身份（`sts:GetCallerIdentity`，失败回退 `cam:GetUserAppId`）+ 引擎 + 默认地域 |

为什么不是几十个工具：腾讯云 API 几千个 Action，全量 schema 会吃光上下文。Code Mode 把 spec 留在服务端，token 固定在 ~1k，与 API 规模脱钩。

## 为什么手写协议层，而不用官方 `mcp` SDK（ASGI）

官方 Python `mcp` SDK 的 Streamable HTTP 是一套 **ASGI 应用**（`StreamableHTTPSessionManager` + Starlette/uvicorn）：

- **WSGI** 是同步模型 `app(environ, start_response)`，一次请求一次完整返回；
- **ASGI** 是异步模型 `async def app(scope, receive, send)`，能 WebSocket、能 SSE、能流式、有 lifespan（应用生命周期）。FastAPI / Starlette / uvicorn 就是 ASGI 栈。

ASGI 要求**常驻进程 + 事件循环 + 流式 send**。事件函数每次只给你一个 event、只收一个 body，塞 ASGI 进去只能伪造（丑且脆）。Web 函数其实**天然适合** ASGI —— 但那就得把 starlette/uvicorn/pydantic 一起打进 zip：体积从 ~50KB 变几 MB，冷启动变慢。

当前取舍：手写的 `mcp_tc/server.py` 只实现 `initialize` / `tools/list` / `tools/call` / `ping` / notifications / 批量 / CORS，协议面很小且稳定。**想要 session 管理、resources/prompts、标准 SSE 会话，再换官方 SDK 更划算。**

## 自签 TC3 vs 官方 SDK

| | 自签 TC3（`engine=api`，默认） | 官方 SDK（`engine=sdk`） |
| --- | --- | --- |
| 单次调用 | 拼 payload + `urllib`，约 10 行 | `XxxRequest()` + `client.DescribeXxx(req)`，约 5 行 |
| 依赖 | 0 | 每产品一个包（`common` + `<product>`） |
| 运行时切任意产品/版本 | 天然支持（`service` + `version` 字符串） | 要动态 `import` client + models、反射类名、CamelCase→snake_case，反而更长 |
| 参数校验 | 服务端报错，带 RequestId | 本地模型校验，早失败但错误信息不带文档 |
| 体积 | ~50KB | 单产品 MB 级 |

**结论**：接口固定的少数几个产品 → SDK 更简洁、更稳；要做“覆盖全量 API 的 Code Mode 网关” → SDK 的简洁建立在“你提前知道调哪个产品”之上，自签才是最短路径。实际代码量：`tc3.py` 有效逻辑 ~40 行且一次写对；`client.py` 里的 `_call_sdk` 反而要 30 行胶水。

## 鉴权：纯透传

```
Authorization: Bearer <secretId>:<secretKey>[:<sessionToken>]
Authorization: Bearer base64(...)
```

服务端**不存任何凭据**；`MCP_ALLOW_ENV_CREDENTIALS=1` 才会回退到环境变量（公网开放时保持 0）。建议客户端用子账号 + 最小权限 + STS 临时密钥（`whoami` 会显示 `:sts`）。

## 公网开放的加固清单

| 防线 | 做法 |
| --- | --- |
| 别记 Authorization | API 网关/函数 URL 访问日志若记录 header，透传的 key 会明文落盘 —— 这是最大真实泄露面 |
| 限流 | 网关流控或 Web 函数“最大并发”（如 5） |
| 预算 | 函数调用次数/费用告警 |
| 执行 | `MCP_MAX_REQUESTS=10~20`、`MCP_REQUEST_TIMEOUT_S=55`，必要时 `MCP_REQUIRE_CONFIRM=1` |
| 写操作 | 客户端侧用子账号策略禁 `*:Delete*`，比任何代码闸都硬 |

## Code Mode 示例

```python
# search
return [a for a in spec["actions"] if a["service"] == "cvm" and "Instance" in a["action"]]
```

```python
# execute（region=ap-guangzhou）
r = await tencent.request(service="cvm", action="DescribeInstances", params={"Limit": 50})
return [{"id": i["InstanceId"], "state": i["InstanceState"]} for i in r["InstanceSet"]]
```

```python
# 一次 execute 串多个产品，中间结果不回上下文
disks = await tencent.request(service="cbs", action="DescribeDisks", params={"Limit": 100})
idle = [d for d in disks["DiskSet"] if d["DiskState"] == "UNATTACHED"]
return {"idleCount": len(idle), "ids": [d["DiskId"] for d in idle]}
```

未收录产品显式传 `version`：`tencent.request(service="cynosdb", version="2019-01-07", action="DescribeClusters", region="ap-guangzhou", params={})`。

## 参数

| 位置 | 参数 | 默认 | 说明 |
| --- | --- | --- | --- |
| URL | `?engine=api\|sdk` | api | 覆盖执行引擎 |
| URL | `?stream=1` | off | SSE 分帧（仅 Web 函数/本地） |
| URL | `?truncateToolResult=false` | true | 关闭 ~6k token 结果截断 |
| env | `MCP_DEFAULT_REGION` | — | 默认地域 |
| env | `MCP_MAX_REQUESTS` | 20 | 单次 execute 最大 API 调用数 |
| env | `MCP_TIMEOUT_MS` | 20000 | 单个 API 请求超时 |
| env | `MCP_REQUEST_TIMEOUT_S` | 55 | 整个 HTTP 请求预算 |
| env | `MCP_REQUIRE_CONFIRM` | 0 | 高危 Action 必须 `confirm=True` |
| env | `MCP_ALLOW_ENV_CREDENTIALS` | 0 | 是否回退到环境变量密钥 |

## 目录结构

```
scf_bootstrap        # Web 函数启动脚本（chmod +x，LF，监听 0.0.0.0:9000）
serve.py             # HTTP 服务：本地开发 + Web 函数进程入口（含可选 SSE）
main.py              # 事件函数入口 main.main_handler（兼容保留）
mcp_tc/
  server.py          # 最小 MCP JSON-RPC 层 + CORS
  tools.py           # 4 个工具
  client.py          # TencentClient（版本/region/confirm/限流/超时）+ 沙箱门面
  tc3.py             # TC3-HMAC-SHA256 签名
  auth.py            # Bearer 透传解析
  sandbox.py         # AST 白名单 + 受限 exec
  catalog.py/json    # Action 目录（10 产品 / 61 Action）
  context.py errors.py
tests/test_smoke.py  # 无网络单测
Makefile             # make test / dev / package
```

## 安全边界（必读）

- `sandbox.py` 是 **AST 白名单 + 受限 `exec`**（禁 import、eval/exec/open、`__dunder__`，`__builtins__` 只留白名单），**不是隔离边界**。公网 + 透传形态下，逃逸的收益是“同时段其他请求的 key + 环境变量 + 内网”，所以：保持 `MCP_ALLOW_ENV_CREDENTIALS=0`、函数 VPC 别挂敏感内网、必要时把执行下沉到 gVisor/Firecracker。
- 结果截断 24k 字符；Web 函数无 6MB 事件响应限制，但仍建议只返回必要字段。

## Roadmap

- [ ] 声明式 `execute`（`calls: [{service, action, params}]`，完全不跑代码）
- [ ] `catalog.json` 自动生成，覆盖全量产品
- [ ] 可选切换到官方 `mcp` SDK + uvicorn（Web 函数下才成立）
- [ ] 执行器下沉（gVisor / K8s job）

## License

MIT
