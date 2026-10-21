import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { credentialFingerprint } from "../../core/auth.js";
import type { Requester } from "../../core/requester.js";
import { stringify, truncateText } from "../../core/truncate.js";
import type { ToolContext } from "../context.js";
import { errorResult, textResult } from "../result.js";

export function registerWhoamiTool(
  server: McpServer,
  ctx: ToolContext,
  requester: Requester,
): void {
  server.registerTool(
    "whoami",
    {
      title: "Who am I",
      description:
        "返回当前连接的身份（主账号 Uin/AppId 或子用户），以及本次会话使用的地域与执行引擎。" +
        "用于区分多个连接、排查权限问题；无参数。",
      inputSchema: {},
    },
    async () => {
      try {
        let identity: Record<string, unknown>;
        let source = "sts:GetCallerIdentity";
        let note: string | undefined;

        try {
          identity = await requester.request({
            service: "sts",
            action: "GetCallerIdentity",
            version: "2018-08-13",
          });
        } catch (stsError) {
          source = "cam:GetUserAppId";
          note = `sts:GetCallerIdentity 失败，已回退 CAM：${(stsError as Error).message}`;
          identity = await requester.request({
            service: "cam",
            action: "GetUserAppId",
            version: "2019-01-16",
          });
        }

        return textResult(
          truncateText(
            stringify({
              ok: true,
              source,
              credential: credentialFingerprint(ctx.credentials),
              engine: ctx.engine,
              defaultRegion: ctx.defaultRegion ?? null,
              identity,
              ...(note ? { note } : {}),
            }),
            { enabled: ctx.truncateToolResult },
          ),
        );
      } catch (error) {
        return errorResult(`whoami 失败：${(error as Error).message}`);
      }
    },
  );
}
