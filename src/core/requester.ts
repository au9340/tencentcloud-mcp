import type { Credentials, ResolvedRequest } from "./types.js";

/**
 * 走官方 Node SDK（可选依赖，按需 npm i tencentcloud-sdk-nodejs）。
 * 好处：官方的重试/超时/类型行为；代价：镜像体积大。
 */
export async function callSdk(
  request: ResolvedRequest,
  credentials: Credentials,
): Promise<Record<string, unknown>> {
  let sdk: Record<string, any>;
  try {
    const mod: any = await import("tencentcloud-sdk-nodejs");
    sdk = (mod.default ?? mod) as Record<string, any>;
  } catch {
    throw new Error(
      "engine=sdk 需要可选依赖：npm i tencentcloud-sdk-nodejs （或改用 engine=api 直连 HTTP API）",
    );
  }

  const Client = sdk[request.service]?.[request.version]?.Client as
    | (new (options: Record<string, unknown>) => Record<string, any>)
    | undefined;

  if (!Client) {
    throw new Error(
      `SDK 中找不到 ${request.service}.${request.version} 的 Client；请确认产品短名/版本，或改用 engine=api。`,
    );
  }

  const client = new Client({
    credential: {
      secretId: credentials.secretId,
      secretKey: credentials.secretKey,
      ...(credentials.token ? { token: credentials.token } : {}),
    },
    ...(request.region ? { region: request.region } : {}),
    profile: {
      httpProfile: { endpoint: `${request.service}.tencentcloudapi.com` },
    },
  });

  const method = request.action.charAt(0).toLowerCase() + request.action.slice(1);
  const fn = client[method];
  if (typeof fn !== "function") {
    throw new Error(`SDK Client 上没有方法 ${method}（对应 Action ${request.action}）`);
  }

  const started = Date.now();
  const result = (await fn.call(client, request.params ?? {})) as Record<string, unknown>;
  return { ...result, _engine: "sdk", _latencyMs: Date.now() - started };
}
