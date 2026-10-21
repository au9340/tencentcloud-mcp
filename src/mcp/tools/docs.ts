import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { searchActions } from "../../catalog/index.js";
import type { ToolContext } from "../context.js";
import { textResult } from "../result.js";

export function registerDocsTool(server: McpServer, _ctx: ToolContext): void {
  server.registerTool(
    "docs",
    {
      title: "Look up Tencent Cloud API action docs",
      description:
        "按关键词检索 Action 目录，返回参数含义、是否需要 region、是否高危以及官方文档链接。" +
        "适合在知道大概要做什么、但不确定接口名/参数名时使用。",
      inputSchema: {
        query: z.string().min(1).describe("关键词，可多个，如 \"cvm 实例 列表\" 或 \"dnspod 记录\""),
        limit: z.number().int().min(1).max(50).optional().describe("返回条数，默认 8"),
      },
    },
    async ({ query, limit }) => {
      const entries = searchActions(query, limit ?? 8);
      if (!entries.length) {
        return textResult(
          `目录里没找到匹配 "${query}" 的 Action。\n` +
            "可以：① 换更短的关键词（如 cvm / disk / DNS）；② 直接用 search 工具写代码遍历 spec.actions；" +
            "③ 在 src/catalog/services/ 里补充该产品的 catalog。",
        );
      }

      const blocks = entries.map((entry) => {
        const flags = [
          entry.requiresRegion ? "需要 region" : "不需要 region",
          entry.dangerous ? "⚠️ 写/删类操作" : "只读",
        ].join("，");
        const params = Object.entries(entry.params);
        const paramLines = params.length
          ? params.map(([name, desc]) => `  - \`${name}\`：${desc}`).join("\n")
          : "  - （未收录关键参数，请参考官方文档）";
        return [
          `### ${entry.service}:${entry.action}（${entry.product}，version ${entry.version}）`,
          entry.summary,
          `- ${flags}`,
          "- 常用参数：",
          paramLines,
          `- 文档：${entry.docUrl}`,
        ].join("\n");
      });

      return textResult(
        blocks.join("\n\n") +
          "\n\n调用方式：execute({ code: `return await tencent.request({ service, action, params });` })",
      );
    },
  );
}
