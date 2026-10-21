# 部署到 SCF Web 函数

按顺序做，全程大约 10 分钟。

## 0. 先本地跑通（30 秒，推荐）

```bash
python3.10 serve.py     # http://127.0.0.1:8787/mcp

# 另一个终端
curl -s localhost:8787/mcp -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | head -c 200
```

能返回 `"tools"` 就说明业务代码没问题，剩下的都是部署配置。

## 1. 打包

```bash
make package
unzip -l dist/tencentcloud-mcp.zip
```

zip 根目录必须是这些（**不能多套一层文件夹**）：

```
scf_bootstrap
serve.py
main.py
mcp_tc/
```

> `make package` 会 `chmod +x scf_bootstrap` 再压缩。如果你用 Finder / 资源管理器重新压一遍，可执行位会丢，平台会报 `permission denied`。

## 2. 控制台字段对照

| 控制台项 | 填什么 |
| --- | --- |
| 创建方式 | 从头开始 → **函数类型：Web 函数** |
| 运行环境 | **Python 3.10** |
| 提交方法 | 上传 zip 包 → `dist/tencentcloud-mcp.zip` |
| 启动脚本 | `scf_bootstrap`（默认值，不用改） |
| 执行超时 | **60 秒** |
| 内存 | 256 MB |
| 环境变量 | 可选：`MCP_DEFAULT_REGION=ap-guangzhou`、`MCP_MAX_REQUESTS=20`、`MCP_REQUIRE_CONFIRM=1`（公网开放**不要**设 `MCP_ALLOW_ENV_CREDENTIALS=1`） |
| 最大并发 | **5**（公网开放必设，防被打满） |
| 触发器 | Web 函数自带访问路径/函数 URL，**不用挂 API 网关** |

需要的权限：腾讯云子账号执行这些 API。

## 3. 上传后自测

```bash
URL='https://<你的访问路径>'

# ① 协议活着（不需要密钥）
curl -s "$URL" -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | head -c 300

# ② 目录可读（不需要密钥）
curl -s "$URL" -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"docs","arguments":{"query":"cvm 实例"}}}' | head -c 300

# ③ 身份通（需要透传 key）
curl -s "$URL" -H 'content-type: application/json' \
  -H "authorization: Bearer $TENCENTCLOUD_SECRET_ID:$TENCENTCLOUD_SECRET_KEY" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"whoami","arguments":{}}}'

# ④ 真打一次 API
curl -s "$URL" -H 'content-type: application/json' \
  -H "authorization: Bearer $TENCENTCLOUD_SECRET_ID:$TENCENTCLOUD_SECRET_KEY" \
  -d '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"execute","arguments":{"region":"ap-guangzhou","code":"r = await tencent.request(service=\"cvm\", action=\"DescribeInstances\", params={\"Limit\": 1})\nreturn len(r[\"InstanceSet\"])"}}}'
```

① ② 不需要密钥也应当成功；③ ④ 返回 `isError: true` 时看 `text` 里的腾讯云错误码。

## 4. 接客户端

```bash
claude mcp add tencentcloud --transport http "$URL" \
  --header "Authorization: Bearer $TENCENTCLOUD_SECRET_ID:$TENCENTCLOUD_SECRET_KEY"
```

```json
{
  "mcpServers": {
    "tencentcloud": {
      "type": "http",
      "url": "https://<你的访问路径>",
      "headers": { "Authorization": "Bearer <secretId>:<secretKey>" }
    }
  }
}
```

> VS Code 的配置根键是 `servers` 而不是 `mcpServers`。

## 5. 启动失败排查

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `scf_bootstrap not found` | zip 根目录多套了一层文件夹 | 在 `dist/tencentcloud-mcp/` **目录内**打 zip，不要打父目录 |
| `Permission denied` | 丢了可执行位 | 用 `make package` 重新生成；或在 Linux 上 `chmod +x scf_bootstrap` 后重压 |
| `bad interpreter: ^M` | CRLF 换行 | `dos2unix scf_bootstrap`；git 用户设 `core.autocrlf=false` 后重新 checkout |
| 健康检查失败 / 初始化超时 | 监听了 `127.0.0.1` 或非 9000 端口 | bootstrap 必须 `--host 0.0.0.0 --port 9000` |
| `ModuleNotFoundError: mcp_tc` | 缺少 `mcp_tc/` 或工作目录不对 | 检查 zip 内容；bootstrap 里已有 `cd $(dirname $0)` |
| 请求 502 / 504 | 函数超时小于实际耗时 | 超时调 60s；`MCP_REQUEST_TIMEOUT_S` 调到 55 以内 |
| `tools/call` 返回 code `-32001` | 没带 Authorization | 加 `-H "authorization: Bearer id:key"` |
| `isError: true` + `AuthFailure.*` | key 无权限或被 IP 限制 | 换子账号授权；API 密钥开了「IP 白名单」时要放行函数出口 IP |

## 6. 看日志

`print` 直接进 stdout（`PYTHONUNBUFFERED=1`，实时）。控制台 → 函数 → 日志查询，按 `tools/call` 搜就能看到每次调用的耗时与错误。

**别在网关/函数日志里开 Authorization 头记录** —— 透传模式下那就是明文密钥。
