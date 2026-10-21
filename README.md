# tencentcloud-mcp

> 4 个工具覆盖整个腾讯云 API。结构照搬 [`cloudflare/mcp`](https://github.com/cloudflare/mcp) 的 Code Mode：`search` 给一份瘦目录，`execute` 让你写代码打 API，另加 `docs` 和 `whoami`。

**Python 3.10、零第三方依赖、为腾讯云函数 SCF 定制**：目录直接打 zip 上传就能跑，没有 pip 安装步骤、没有 cold start 时的依赖解压开销。

```
你的 MCP 客户端  ──POST /mcp──►  SCF（main.main_handler）  ──TC3 签名──►  *.tencentcloudapi.com
  Bearer secretId:secretKey            无状态、无存储               用调用方自己的密钥
```

## 两个部署约束（决定了实现）

1. **SCF 事件函数不能流式返回**。所以本服务器只实现 Streamable HTTP 的 **JSON response** 模式（一次 POST 一次完整 JSON），不提供 SSE。客户端发 `Accept: application/json, text/event-stream` 也能正常工作，因为服务端声明返回 `application/json`。
2. **不想在 SCF 里装 `mcp` SDK 的 ASGI 栈**，所以 `mcp_tc/server.py` 手写了最小 MCP 层：`initialize` / `tools/list` / `tools/call` / `ping` / notifications、批量请求、CORS、JSON-RPC 错误码。协议面很小且稳定，换来“一个 zip 就能跑”。

## 4 个工具

| 工具 | 作用 |
| --- | --- |
| `search` | 写 Python 在 Action 目录里筛选：`spec["actions"]` / `search_actions(kw)` |
| `execute` | 写 Python 调 `tencent.request(...)`，在代码里串联/过滤/聚合，只 return 需要的字段 |
| `docs` | 关键词查参数含义、是否需要 region、是否高危、官方文档链接 |
| `whoami` | 当前身份（`sts:GetCallerIdentity`，失败回退 `cam:GetUserAppId`）+ 引擎 + 默认地域 |

为什么不是几十个工具：腾讯云 API 几千个 Action，全量 schema 会直接吃光上下文。Code Mode 把 spec 留在服务端，token 消耗固定在 ~1k，与 API 规模脱钩。

## 部署到 SCF（控制台，5 分钟）

```bash
make package          # 生成 dist/tencentcloud-mcp.zip（只有 main.py + mcp_tc/）
```

1. **新建函数**：地域任选（如广州）→ 运行环境 **Python 3.10** → 提交方式 **上传 zip 包** → 选 `dist/tencentcloud-mcp.zip`。
2. **执行方法**：`main.main_handler`。
3. **函数配置**：内存 256MB、超时 **60s**（一次 execute 可能串几次 API）。
4. **环境变量**（可选）：`MCP_DEFAULT_REGION=ap-guangzhou`、`MCP_MAX_REQUESTS=20`、`MCP_REQUIRE_CONFIRM=1`。
5. **触发器**：
   - 简单方式：开 **函数 URL**（公网访问），路径随意，`POST <url>` 即 MCP 端点。
   - 常规方式：**API 网关**触发器，请求方法勾 `POST` + `OPTIONS`（CORS 预检），后端超时 ≥ 30s。
6. **客户端连接**（把 `<URL>` 换成你的触发地址）：

```bash
claude mcp add tencentcloud --transport http <URL> \
  --header "Authorization: Bearer $TENCENTCLOUD_SECRET_ID:$TENCENTCLOUD_SECRET_KEY"
```

```json
{
  "mcpServers": {
    "tencentcloud": {
      "type": "http",
      "url": "<URL>",
      "headers": { "Authorization": "Bearer <secretId>:<secretKey>" }
    }
  }
}
```

自测（部署完先跑这个）：

```bash
curl -s <URL> -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | head -c 300

curl -s <URL> -H 'content-type: application/json' \
  -H "authorization: Bearer $TENCENTCLOUD_SECRET_ID:$TENCENTCLOUD_SECRET_KEY" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"whoami","arguments":{}}}'
```

## 本地开发

```bash
python3.10 run_local.py          # http://127.0.0.1:8787/mcp
make test                        # 不需要网络、不需要密钥
```

## 鉴权：纯透传

```
Authorization: Bearer <secretId>:<secretKey>[:<sessionToken>]
Authorization: Bearer base64(<secretId>:<secretKey>[:<sessionToken>])
```

- 服务端**不存任何凭据**，每次请求用调用方自己的 key 签名，用完即丢。
- `MCP_ALLOW_ENV_CREDENTIALS=1` 才会回退到函数环境变量里的 key。**公网开放时保持 0**，否则不带头的请求会烧你自己的账号。
- 建议客户端用**子账号 + 最小权限策略 + STS 临时密钥**（`whoami` 会显示是不是 `:sts`）。

## 公网开放的加固清单

既然不设鉴权、随便谁都能打，至少把这几项做了：

| 防线 | 做法 |
| --- | --- |
| 入口限流 | API 网关 / 函数 URL 配流控（如 10 QPS），或前面挂 WAF |
| 并发上限 | SCF 函数配置里设“最大并发”（比如 5），防被打满账单 |
| 预算 | 配告警 + 单函数调用次数告警 |
| 代码执行 | `MCP_MAX_REQUESTS=10~20`、`MCP_TIMEOUT_MS=20000`；必要时开 `MCP_REQUIRE_CONFIRM=1` |
| 密钥泄露 | 日志只记方法名/耗时，不记 Authorization；`whoami` 只回 `secretId` 前 6 位掩码 |
| 写操作 | 客户端侧给子账号策略禁 `*:Delete*`，比任何代码闸都硬 |

## Code Mode 实战

```python
# search：先自己找接口
return [a for a in spec["actions"] if a["service"] == "cvm" and "Instance" in a["action"]]
```

```python
# execute：查 + 过滤 + 只要关键字段（region=ap-guangzhou）
r = await tencent.request(service="cvm", action="DescribeInstances", params={"Limit": 50})
return [{"id": i["InstanceId"], "name": i["InstanceName"], "state": i["InstanceState"]}
        for i in r["InstanceSet"] if i["InstanceState"] == "RUNNING"]
```

```python
# 一次 execute 串多个产品，中间结果不回上下文
disks = await tencent.request(service="cbs", action="DescribeDisks", params={"Limit": 100})
idle = [d for d in disks["DiskSet"] if d["DiskState"] == "UNATTACHED"]
return {"idleCount": len(idle), "ids": [d["DiskId"] for d in idle]}
```

没收录的产品也能用，显式传 `version`：

```python
return await tencent.request(service="cynosdb", version="2019-01-07", action="DescribeClusters",
                             region="ap-guangzhou", params={})
```

## 两种执行引擎

| engine | 实现 | 适合 |
| --- | --- | --- |
| `api`（默认） | `mcp_tc/tc3.py` 自签 TC3，`urllib` 直连官方 HTTP API | SCF、零依赖、任何产品 |
| `sdk` | 动态 `import tencentcloud.<service>.v<version>` 调官方 SDK | 本机/容器，想用官方重试与模型 |

切换：`MCP_ENGINE=sdk` 或单连接 `?engine=sdk`（需自行 `pip install tencentcloud-sdk-python-common tencentcloud-sdk-python-cvm ...`）。

## 参数

| 位置 | 参数 | 默认 | 说明 |
| --- | --- | --- | --- |
| URL | `?engine=api\|sdk` | api | 覆盖执行引擎 |
| URL | `?truncateToolResult=false` | true | 关闭 ~6k token 结果截断 |
| env | `MCP_DEFAULT_REGION` | — | 默认地域 |
| env | `MCP_MAX_REQUESTS` | 20 | 单次 execute 最大 API 调用数 |
| env | `MCP_TIMEOUT_MS` | 20000 | 单个 API 请求超时 |
| env | `MCP_REQUIRE_CONFIRM` | 0 | 高危 Action 必须 `confirm=True` |
| env | `MCP_ALLOW_ENV_CREDENTIALS` | 0 | 是否允许回退到环境变量密钥 |

## 目录结构

```
main.py              # SCF 入口：main.main_handler（事件函数 / API 网关 / 函数 URL）
run_local.py         # 本地 http.server，复用同一套 dispatch
mcp_tc/
  server.py          # 最小 MCP JSON-RPC 层 + CORS + 路由
  tools.py           # 4 个工具的定义与实现
  client.py          # TencentClient（版本/region/confirm/限流/超时）+ 沙箱门面
  tc3.py             # TC3-HMAC-SHA256 签名
  auth.py            # Bearer 透传解析、env 回退开关
  sandbox.py         # AST 白名单 + 受限 exec（跑模型写的 Python）
  catalog.py         # catalog.json 加载 / 扁平化 / 关键词检索
  catalog.json       # Action 目录（10 产品 / ~60 Action）
  context.py         # 每次请求的上下文（无状态）
tests/test_smoke.py  # 无网络单测
Makefile             # make test / dev / package
```

## 安全边界（必读）

- `sandbox.py` 是 **AST 白名单 + 受限 `exec`**：禁用 import、eval/exec/open、`__dunder__`，`__builtins__` 只留安全白名单。但它**不是**隔离边界 —— 能拿到的权限 = 该次请求的 key + 进程能做的事（Python 能被绕过的点很多）。
- 你这种“公网 + 透传”的形态下，沙箱逃逸的真实收益是：拿到同时段其他请求的 key、环境变量、内网。所以：
  - 保持 `MCP_ALLOW_ENV_CREDENTIALS=0`（环境里没有长期密钥可偷）；
  - 函数所在 VPC 不要放敏感内网资源；
  - 真要对外大规模开放，把 `execute` 的代码执行下沉到独立隔离执行器（Firecracker / gVisor / K8s job），或改成“声明式批量调用”不给跑代码。
- 已知限制：SCF 响应体上限 6MB（已用 24k 字符截断兜住）、无 SSE、冷启动 ~数百 ms。

## Roadmap

- [ ] 声明式 `execute`（`calls: [{service, action, params}]`，完全不跑代码）
- [ ] `catalog.json` 自动生成，覆盖全量产品
- [ ] 可选 OAuth 2.1 网关
- [ ] 执行器下沉（gVisor / K8s job）

## License

MIT
