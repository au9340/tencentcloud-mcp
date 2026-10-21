import type { IncomingHttpHeaders } from "node:http";
import type { Credentials, Engine } from "./types.js";

export class UnauthorizedError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "UnauthorizedError";
  }
}

/**
 * 两种凭据模式，与 cloudflare/mcp 的 “OAuth / Bearer API Token” 对应：
 *
 * 1) 按请求传入（推荐，多租户）：
 *      Authorization: Bearer <secretId>:<secretKey>[:<sessionToken>]
 *      Authorization: Bearer base64(<secretId>:<secretKey>[:<sessionToken>])
 * 2) 服务端环境变量（单租户 / 自用）：
 *      TENCENTCLOUD_SECRET_ID / TENCENTCLOUD_SECRET_KEY / TENCENTCLOUD_SESSION_TOKEN
 */
export function resolveCredentials(headers: IncomingHttpHeaders): Credentials {
  const header = headers.authorization;
  if (header && /^Bearer\s+/i.test(header)) {
    const raw = header.replace(/^Bearer\s+/i, "").trim();
    const decoded = raw.includes(":") ? raw : Buffer.from(raw, "base64").toString("utf8");
    const [secretId, secretKey, token] = decoded.split(":");
    if (!secretId || !secretKey) {
      throw new UnauthorizedError(
        "Bearer token 格式应为 <secretId>:<secretKey>[:<sessionToken>]，或整体 base64 编码。",
      );
    }
    return { secretId, secretKey, ...(token ? { token } : {}) };
  }

  const secretId = process.env.TENCENTCLOUD_SECRET_ID;
  const secretKey = process.env.TENCENTCLOUD_SECRET_KEY;
  const token = process.env.TENCENTCLOUD_SESSION_TOKEN;

  if (!secretId || !secretKey) {
    throw new UnauthorizedError(
      "缺少腾讯云凭据：请在 Authorization: Bearer <secretId>:<secretKey> 中传入，" +
        "或配置环境变量 TENCENTCLOUD_SECRET_ID / TENCENTCLOUD_SECRET_KEY。",
    );
  }

  return { secretId, secretKey, ...(token ? { token } : {}) };
}

/** 当前服务端的默认执行引擎 */
export function resolveEngine(value?: string | null): Engine {
  const raw = (value ?? process.env.TENCENT_MCP_ENGINE ?? "api").toLowerCase();
  if (raw === "sdk" || raw === "api") return raw;
  throw new Error(`未知的 engine="${raw}"，只支持 api | sdk。`);
}

/** 给客户端看的身份标识，用于区分连接（类似 cloudflare/mcp 的 whoami） */
export function credentialFingerprint(credentials: Credentials): string {
  return `secretId:${credentials.secretId.slice(0, 6)}***${credentials.token ? ":sts" : ""}`;
}
