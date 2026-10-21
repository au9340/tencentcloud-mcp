import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { actionList, catalog } from "../../catalog/index.js";
import type { Requester } from "../../core/requester.js";
import { runUserCode } from "../../core/sandbox.js";
import type { TencentRequestInput } from "../../core/types.js";
import { stringify, truncateText } from "../../core/truncate.js";
import type { ToolContext } from "../context.js";
import { errorResult, textResult } from "../result.js";

const DESCRIPTION = `
用代码调用腾讯云 API（Code Mode 的执行层）。写一段 JS 函数体，可用 await，只 return 你需要的数据。

可用变量：
- tencent.request({ service, action, params?, region?, version?, confirm? })
  * service：产品短名（= API 域名子域）：cvm / vpc / cbs / clb / lighthouse / scf / tat / cam / sts / dnspod
  * action：大驼峰 Action，如 DescribeInstances
  * version：省略时从目录推导
  * region：省略时用本工具的 region 参数或服务端默认地域
  * params：腾讯云 RPC 风格，参数平铺，如 { Filters: [{ Name: "instance-name", Values: ["web"] }], Limit: 10 }
  * confirm：仅高危 Action 在开启确认闸时需要
- region：当前生效的地域字符串（可能为 null）
- spec.services / spec.actions：与 search 工具一样的 Action 目录

示例：
const r = await tencent.request({ service: "cvm", action: "DescribeInstances", params: { Limit: 20 } });
return r.InstanceSet.map(i => ({ id: i.InstanceId, name: i.InstanceName, state: i.InstanceState, ip: i.PublicIpAddresses?.[0] }));
`.trim();

export function registerExecuteTool(
  server: McpServer,
  ctx: ToolContext,
  requester: Requester,
): void {
  server.registerTool(
    "execute",
    {
      title: "Execute Tencent Cloud API calls via code",
      description: DESCRIPTION,
      inputSchema: {
        code: z.string().min(1).describe("JS 函数体，可用 await，必须 return 一个 JSON 可序列化的值"),
        region: z
          .string()
          .optional()
          .describe("本次执行使用的地域，如 ap-guangzhou；省略则用服务端默认地域"),
        explain: z.string().optional().describe("一句话说明这次要做什么，便于日志/审计"),
      },
    },
    async ({ code, region, explain }) => {
      const effectiveRegion = region ?? ctx.defaultRegion ?? null;
      try {
        const result = await runUserCode(code, {
          tencent: {
            request: (input: TencentRequestInput) =>
              requester.request({
                ...input,
                ...(input?.region || !region ? {} : { region }),
              }),
            call: (input: TencentRequestInput) =>
              requester.request({
                ...input,
                ...(input?.region || !region ? {} : { region }),
              }),
          },
          region: effectiveRegion,
          spec: { services: catalog, actions: actionList },
        });

        const payload = {
          ok: true,
          engine: ctx.engine,
          region: effectiveRegion,
          apiCalls: requester.calls,
          ...(explain ? { explain } : {}),
          result,
        };

        return textResult(
          truncateText(stringify(payload), {
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
