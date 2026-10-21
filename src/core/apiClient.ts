import { signTC3 } from "./tc3.js";
import type { Credentials, ResolvedRequest } from "./types.js";

export class TencentApiError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly requestId?: string,
  ) {
    super(`[${code}] ${message}${requestId ? ` (RequestId: ${requestId})` : ""}`);
    this.name = "TencentApiError";
  }
}

interface ApiResponse {
  Response?: {
    RequestId?: string;
    Error?: { Code?: string; Message?: string };
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

/** 直接用官方 HTTP API（自签 TC3），不依赖 SDK，任何产品都能打 */
export async function callApi(
  request: ResolvedRequest,
  credentials: Credentials,
  options: { timeoutMs?: number } = {},
): Promise<Record<string, unknown>> {
  const payload = JSON.stringify(request.params ?? {});
  const signed = signTC3({
    secretId: credentials.secretId,
    secretKey: credentials.secretKey,
    ...(credentials.token ? { token: credentials.token } : {}),
    service: request.service,
    action: request.action,
    version: request.version,
    ...(request.region ? { region: request.region } : {}),
    payload,
  });

  const response = await fetch(signed.url, {
    method: "POST",
    headers: signed.headers,
    body: signed.payload,
    signal: AbortSignal.timeout(options.timeoutMs ?? 20_000),
  });

  const text = await response.text();
  let json: ApiResponse;
  try {
    json = JSON.parse(text) as ApiResponse;
  } catch {
    throw new Error(
      `腾讯云返回了非 JSON 响应 (HTTP ${response.status}): ${text.slice(0, 300)}`,
    );
  }

  const reply = (json.Response ?? json) as NonNullable<ApiResponse["Response"]>;
  if (reply.Error?.Code) {
    throw new TencentApiError(reply.Error.Code, reply.Error.Message ?? "", reply.RequestId);
  }
  if (!response.ok) {
    throw new Error(`腾讯云 API HTTP ${response.status}: ${text.slice(0, 300)}`);
  }

  return reply as Record<string, unknown>;
}
