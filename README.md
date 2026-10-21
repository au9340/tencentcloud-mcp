# 腾讯云 MCP（单文件版）

两个文件就够：`app.py`（全部逻辑，零第三方依赖）+ `scf_bootstrap`（SCF Web 函数启动脚本）。
4 个工具：`search` / `execute` / `docs` / `whoami`，覆盖腾讯云全量 API（Code Mode）。

## 本地试

```bash
python3 app.py --selftest     # 自检，不联网、不需要密钥
python3 app.py                # http://127.0.0.1:8787/mcp

curl -s localhost:8787/mcp -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | head -c 200
```

## 上传到 SCF Web 函数

```bash
chmod +x scf_bootstrap
zip -r ../tencentcloud-mcp.zip . -x '.git/*'      # zip 根目录必须是 scf_bootstrap
```

控制台：**Web 函数** / **Python 3.10** / 上传 zip / 启动脚本 `scf_bootstrap` / 超时 **60s** / 最大并发 **5** / 监听端口 9000。
环境变量可选：`MCP_DEFAULT_REGION=ap-guangzhou`。

上传后自测（前两条不需要密钥）：

```bash
URL='https://<你的访问路径>'
curl -s "$URL" -H 'content-type: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | head -c 200
curl -s "$URL" -H 'content-type: application/json' -H "authorization: Bearer $TENCENTCLOUD_SECRET_ID:$TENCENTCLOUD_SECRET_KEY" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"whoami","arguments":{}}}'
```

## 接客户端

```bash
claude mcp add tencentcloud --transport http "$URL" \
  --header "Authorization: Bearer $TENCENTCLOUD_SECRET_ID:$TENCENTCLOUD_SECRET_KEY"
```

```json
{ "mcpServers": { "tencentcloud": {
  "type": "http", "url": "https://<访问路径>",
  "headers": { "Authorization": "Bearer <secretId>:<secretKey>" } } } }
```

## 三个必须知道

1. **凭据是透传的**：`Authorization: Bearer <secretId>:<secretKey>[:<sessionToken>]`，服务端不存密钥。公网开放时**不要**设 `MCP_ALLOW_ENV_CREDENTIALS=1`。
2. **别在网关/函数日志里记录 Authorization 头**，那就是明文密钥。
3. **沙箱不是安全边界**：`app.py` 里是 AST 白名单 + 受限 `exec`，能挡误操作，挡不住恶意逃逸。真要对外大规模开放，把代码执行下沉到独立隔离执行器。

## 参数（环境变量，全部可选）

| 变量 | 默认 | 含义 |
| --- | --- | --- |
| `MCP_DEFAULT_REGION` | — | 默认地域，execute 没传 region 时用 |
| `MCP_MAX_REQUESTS` | 20 | 单次 execute 最多 API 调用数 |
| `MCP_TIMEOUT_MS` | 20000 | 单个 API 请求超时 |
| `MCP_REQUEST_TIMEOUT_S` | 55 | 整个 HTTP 请求预算 |
| `MCP_REQUIRE_CONFIRM` | 0 | 写/删类 Action 需 `confirm=True` |
| `MCP_ALLOW_ENV_CREDENTIALS` | 0 | 是否回退到环境变量密钥 |
| `MCP_ENGINE` | api | `api`（自签 TC3）或 `sdk`（官方 SDK） |

URL 参数：`?engine=api|sdk`、`?stream=1`（SSE）、`?truncateToolResult=false`。

MIT
