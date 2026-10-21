# tencentcloud-mcp

> 用 4 个工具覆盖整个腾讯云 API。结构照搬 [`cloudflare/mcp`](https://github.com/cloudflare/mcp) 的 Code Mode 思路：`search` 给你一份瘦目录，`execute` 让你写代码打 API，另外还有 `docs` 和 `whoami`。

远程 MCP 服务器，Streamable HTTP，无状态（每个请求一份 server 实例），可以直接被 Claude Code / Cursor / VS Code / Codex 连。

## 为什么不是几千个工具

腾讯云 API 和 Cloudflare API 一样是“端点海洋”。把每个 Action 都注册成 MCP 工具，光工具定义就吃掉整个上下文窗口：

| 方案 | 工具数 | 估算 token |
| --- | --- | --- |
| 把 API 文档/OpenAPI 塞 prompt | — | 百万级 |
| 原生 MCP（全量 schema） | 数千 | 几十万～百万 |
| **Code Mode（本仓库）** | **4** | **～1k（固定）** |

原理：spec 留在服务端，模型只拿到“怎么找”，找到后再写 JS 调用，只回传结果。token 消耗与 API 规模脱钩。

## 结构

```
MCP client (Claude Code / Cursor / VS Code ...)
  │  POST /mcp   Streamable HTTP + JSON-RPC
  ▼
┌──────────────────────────────────────────────────────────┐
│ src/index.ts           传输层：/mcp、/healthz、Bearer 鉴权  │
├──────────────────────────────────────────────────────────┤
│ src/mcp/server.ts      工具面：4 个 tool，每次请求重建       │
│   search  execute  docs  whoami                          │
├──────────────────────────────────────────────────────────┤
│ src/core/sandbox.ts    执行层：跑模型写的 JS（vm）           │
│   注入 tencent.request() / spec / region                  │
├──────────────────────────────────────────────────────────┤
│ src/core/requester.ts  ｜版本·region·confirm·限流          │
│   ├── apiClient.ts     TC3-HMAC-SHA256 直连官方 HTTP API   │
│   └── sdkClient.ts     tencentcloud-sdk-nodejs（可选）     │
├──────────────────────────────────────────────────────────┤
│ src/catalog/           Action 目录（spec 的瘦身版）         │
└──────────────────────────────────────────────────────────┘
```

和 Cloudflare 版的对应关系：

| Cloudflare | 本仓库 |
| --- | --- |
| `@cloudflare/codemode` + Dynamic Worker | `src/core/sandbox.ts`（`node:vm`，可换成 Workers isolate） |
| OpenAPI spec（2M tokens，留在服务端） | `src/catalog/`（服务名 + 版本 + 常用参数） |
| `POST https://<service>.cloudflareapi.com` | `POST https://<service>.tencentcloudapi.com` + TC3 签名 |
| OAuth / Bearer API token | Bearer `secretId:secretKey[:token]` / 服务端环境变量 |
| 结果截断 ~6k tokens | 同名参数 `?truncateToolResult=false` |

## 4 个工具

| 工具 | 作用 |
| --- | --- |
| `search` | 写 JS 在 Action 目录里筛选：`spec.actions` / `spec.services` / `searchActions(kw)` |
| `execute` | 写 JS 调 `tencent.request({ service, action, params, region })`，在代码里过滤/聚合后只 return 需要的字段 |
| `docs` | 关键词查参数含义、是否需要 region、是否高危、官方文档链接 |
| `whoami` | 当前身份（`sts:GetCallerIdentity`，失败回退 `cam:GetUserAppId`）+ 引擎 + 默认地域 |

## 快速开始

```bash
npm install
cp .env.example .env      # 填 TENCENTCLOUD_SECRET_ID / SECRET_KEY
npm run dev               # http://127.0.0.1:8787/mcp
```

自测（不需要客户端）：

```bash
curl -s http://127.0.0.1:8787/healthz | jq

curl -s http://127.0.0.1:8787/mcp \
  -H 'content-type: application/json' \
  -H 'accept: application/json, text/event-stream' \
  -H "authorization: Bearer $TENCENTCLOUD_SECRET_ID:$TENCENTCLOUD_SECRET_KEY" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | jq '.result.tools[].name'
```

接入客户端：

```bash
# Claude Code
claude mcp add tencentcloud --transport http http://127.0.0.1:8787/mcp \
  --header "Authorization: Bearer $TENCENTCLOUD_SECRET_ID:$TENCENTCLOUD_SECRET_KEY"
```

```json
{
  "mcpServers": {
    "tencentcloud": {
      "type": "http",
      "url": "http://127.0.0.1:8787/mcp",
      "headers": { "Authorization": "Bearer <secretId>:<secretKey>" }
    }
  }
}
```

> VS Code 的配置根键是 `servers`，不是 `mcpServers`。

## Code Mode 实战

第一步，模型自己找接口（不消耗全量 schema）：

```js
// search 的 code 参数
const hits = spec.actions.filter(
  (a) => a.service === "cvm" && /instance/i.test(a.action),
);
return hits.map(({ service, action, version, summary }) => ({ service, action, version, summary }));
```

第二步，一次 execute 完成“查 + 过滤 + 只要关键字段”：

```js
// execute 的 code 参数（region=ap-guangzhou）
const r = await tencent.request({
  service: "cvm",
  action: "DescribeInstances",
  params: { Limit: 50 },
});
return r.InstanceSet.map((i) => ({
  id: i.InstanceId,
  name: i.InstanceName,
  state: i.InstanceState,
  ip: i.PublicIpAddresses?.[0] ?? null,
}));
```

也可以在一次 execute 里串多个调用（跨产品也行），中间结果不用回上下文：

```js
const disks = await tencent.request({ service: "cbs", action: "DescribeDisks", params: { Limit: 100 } });
const idle = disks.DiskSet.filter((d) => d.DiskState === "UNATTACHED");
return { idleCount: idle.length, ids: idle.map((d) => d.DiskId) };
```

## 两种执行引擎

`engine` 决定 `tencent.request()` 底层怎么打：

| engine | 实现 | 适合 |
| --- | --- | --- |
| `api`（默认） | 自己实现 TC3-HMAC-SHA256，`fetch` 直连 `https://<service>.tencentcloudapi.com` | 零依赖、任何产品、体积小 |
| `sdk` | 官方 `tencentcloud-sdk-nodejs` 动态选 Client/Action | 想要官方重试/类型/行为 |

```bash
npm i tencentcloud-sdk-nodejs   # 只有用 sdk 引擎才需要
# 全局：TENCENT_MCP_ENGINE=sdk
# 单连接：http://127.0.0.1:8787/mcp?engine=sdk
```

两种引擎的入参/出参约定一致，`execute` 返回里会带 `engine` 方便确认。

## 鉴权

1. **按请求传（推荐，多租户）**
   `Authorization: Bearer <secretId>:<secretKey>[:<sessionToken>]`，或整串 base64（`printf "id:key" | base64`）。
   建议用子账号 + 最小权限策略 + 临时密钥（STS）。
2. **服务端环境变量（单租户 / 自用）**
   `TENCENTCLOUD_SECRET_ID` / `TENCENTCLOUD_SECRET_KEY` / `TENCENTCLOUD_SESSION_TOKEN`。

没做 OAuth：腾讯云没有对 MCP 的公共 OAuth 端点，所以这里用 Bearer；一键授权的 OAuth 可以作为下一步。

## 参数

| 位置 | 参数 | 说明 |
| --- | --- | --- |
| URL | `?engine=api\|sdk` | 覆盖执行引擎 |
| URL | `?truncateToolResult=false` | 关闭 ~6k token 结果截断（客户端自己会兜住结果时用） |
| env | `TENCENT_MCP_DEFAULT_REGION` | 默认地域，`execute` 没传 region 时用 |
| env | `TENCENT_MCP_MAX_REQUESTS` | 单次 execute 最大 API 调用数（默认 20） |
| env | `TENCENT_MCP_TIMEOUT_MS` | 单个 API 请求超时（默认 20000） |
| env | `TENCENT_MCP_REQUIRE_CONFIRM=true` | 高危 Action 必须带 `confirm: true` 才执行 |

## 加一个产品

不用改任何框架代码，两步：

1. 新建 `src/catalog/services/xxx.ts`，导出 `ServiceDoc`（`version` / `product` / `docUrl` / `actions`）。
2. 在 `src/catalog/index.ts` 的 `catalog` 里注册。

已收录：`cvm` `vpc` `cbs` `clb` `lighthouse` `scf` `tat` `cam` `sts` `dnspod`。
没收录的产品也能用，`execute` 里显式传 `version` 即可，例如：

```js
await tencent.request({ service: "cynosdb", version: "2019-01-07", action: "DescribeClusters", region: "ap-guangzhou", params: {} });
```

## 安全边界（重要）

- `node:vm` **不是安全边界**，只防误操作（拿不到 `require` / `process` / `fs`）。生产多租户请把 `src/core/sandbox.ts` 换成 Cloudflare Workers Dynamic Worker isolate、gVisor/Firecracker 容器，或至少把服务跑在独立容器里 + 只给它一个窄权限子账号。
- 默认就有 `TENCENT_MCP_MAX_REQUESTS` 限流、单请求超时和结果截断。
- 真要防误删：`TENCENT_MCP_REQUIRE_CONFIRM=true`，再配子账号策略（禁止 `*:Delete*`）。
- 凭据不会进模型上下文：签名/请求都在沙箱外部完成。

## 目录结构

```
src/
  index.ts              # HTTP + 鉴权 + 每请求一个 server 实例
  mcp/
    server.ts           # McpServer + instructions
    context.ts result.ts
    tools/{search,execute,docs,whoami}.ts
  core/
    auth.ts             # Bearer / env -> Credentials
    tc3.ts              # TC3-HMAC-SHA256 签名
    apiClient.ts        # engine=api
    sdkClient.ts        # engine=sdk
    requester.ts        # 版本/region/confirm/限流
    sandbox.ts          # 跑模型写的 JS
    truncate.ts
  catalog/
    index.ts types.ts
    services/*.ts
```

## 开发

```bash
npm run typecheck
npm test
npm run build && npm start
```

Docker：

```bash
docker build -t tencentcloud-mcp .
docker run --rm -p 8787:8787 -e TENCENTCLOUD_SECRET_ID=... -e TENCENTCLOUD_SECRET_KEY=... tencentcloud-mcp
```

## Roadmap

- [ ] OAuth 2.1 接入（替代手工 Bearer）
- [ ] catalog 从腾讯云 API 文档/OpenAPI 自动生成，覆盖全部产品
- [ ] MCP `skills` 扩展（把常用 playbook 当 skill 发）
- [ ] Cloudflare Workers 版：用 Dynamic Worker 替换 `node:vm`
- [ ] 按请求的审计日志（谁、什么 action、结果）

## License

MIT
