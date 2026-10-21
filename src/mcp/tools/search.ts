import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { actionList, catalog, searchActions } from "../../catalog/index.js";
import { runUserCode } from "../../core/sandbox.js";
import { stringify, truncateText } from "../../core/truncate.js";
import type { ToolContext } from "../context.js";
import { errorResult, textResult } from "../result.js";

const DESCRIPTION = `
用代码查询腾讯云 Action 目录（Code Mode，不返回全量 schema）。写一段 JS 函数体，可用 await，必须 return。

可用变量：
- spec.services：{ [service]: { version, product, docUrl, actions } }
- spec.actions：扁平数组 [{ service, version, product, action, summary, requiresRegion, dangerous, params }]
- searchActions(keyword, limit?)：关键词检索，返回同样的扁平条目
- total：目录里 Action 总数

示例：
const hits = spec.actions.filter(a => a.service === "cvm" && /instance/i.test(a.action));
return hits.map(({ service, action, version, summary }) => ({ service, action, version, summary }));
`.trim();

export function registerSearchTool(server: McpServer, ctx: ToolContext): void {
  server.registerTool(
    "search",
    {
      title: "Search Tencent Cloud API actions",
      description: DESCRIPTION,
      inputSchema: {
        code: z.string().min(1).describe("JS 函数体，可用 await，必须 return 一个 JSON 可序列化的值"),
      },
    },
    async ({ code }) => {
      try {
        const result = await runUserCode(code, {
          spec: { services: catalog, actions: actionList },
          searchActions: (query: string, limit?: number) =>
            searchActions(String(query), limit),
          total: actionList.length,
        });
        return textResult(
          truncateText(stringify(result), {
            enabled: ctx.truncateToolResult,
            maxTokens: 6_000,
          }),
        );
      } catch (error) {
        return errorResult((error as Error).message);
      }
    },
  );
}
