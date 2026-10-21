import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { createRequester } from "../core/requester.js";
import type { ToolContext } from "./context.js";
import { registerDocsTool } from "./tools/docs.js";
import { registerExecuteTool } from "./tools/execute.js";
import { registerSearchTool } from "./tools/search.js";
import { registerWhoamiTool } from "./tools/whoami.js";

const INSTRUCTIONS = `
这是腾讯云 API 的 MCP 服务器，采用 Code Mode：工具只有 4 个，但覆盖全量 API。

标准工作流：
1. 不确定用哪个接口时，先调 search：写 JS 在 Action 目录里筛选（只返回你需要的几条）。
2. 再调 execute：写 JS 用 tencent.request({ service, action, params, region }) 真正调用 API，
   并在代码里直接过滤/聚合，只 return 你需要的数据。
3. 需要看参数含义/文档链接时调 docs；需要知道当前连接是哪个账号时调 whoami。

硬性规则：
- service 是 API 域名子域（cvm / vpc / cbs / clb / lighthouse / scf / tat / cam / sts / dnspod）。
- 大部分 Action 需要 region（如 ap-guangzhou）；省略时依次用：request() 里的 region > execute 的 region > 服务端默认地域。
- 参数（params）平铺在对象里，不是嵌套在 “Params” 字段下。
- 单次 execute 有 API 调用次数上限（默认 20）；结果超过 ~6000 tokens 会被截断，所以只返回必需字段。
- 写/删/重启类操作（目录里 dangerous: true）先向用户确认再执行；服务端开启确认闸时需要传 confirm: true。
`.trim();

export function buildServer(ctx: ToolContext): McpServer {
  const server = new McpServer(
    {
      name: "tencentcloud-mcp",
      version: "0.1.0",
      title: "Tencent Cloud API (Code Mode)",
    },
    { instructions: INSTRUCTIONS },
  );

  const requester = createRequester({
    credentials: ctx.credentials,
    engine: ctx.engine,
    defaultRegion: ctx.defaultRegion,
    maxRequests: ctx.maxRequests,
    timeoutMs: ctx.timeoutMs,
    requireConfirm: ctx.requireConfirm,
  });

  registerSearchTool(server, ctx);
  registerExecuteTool(server, ctx, requester);
  registerDocsTool(server, ctx);
  registerWhoamiTool(server, ctx, requester);

  return server;
}
