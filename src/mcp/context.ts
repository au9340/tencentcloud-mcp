import type { Credentials, Engine } from "../core/types.js";
import type { Requester } from "../core/requester.js";

/** 每次 HTTP 请求一份，与 cloudflare/mcp 的 stateless 一致：不在服务端存会话 */
export interface ToolContext {
  credentials: Credentials;
  engine: Engine;
  /** 是否截断工具结果（?truncateToolResult=false 关闭） */
  truncateToolResult: boolean;
  defaultRegion?: string | undefined;
  maxRequests: number;
  timeoutMs: number;
  requireConfirm: boolean;
}

export interface ExecuteContext extends ToolContext {
  requester: Requester;
}
