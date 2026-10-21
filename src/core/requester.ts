import { catalog, resolveVersion } from "../catalog/index.js";
import { callApi } from "./apiClient.js";
import { callSdk } from "./sdkClient.js";
import type { Credentials, Engine, ResolvedRequest, TencentRequestInput } from "./types.js";

export interface RequesterOptions {
  credentials: Credentials;
  engine: Engine;
  defaultRegion?: string | undefined;
  /** 单次 execute 允许的最大 API 请求数，防止模型写出循环狂打 API */
  maxRequests?: number;
  timeoutMs?: number;
  /** 高危 Action（写/删）是否必须先传 confirm: true */
  requireConfirm?: boolean;
}

export interface Requester {
  request(input: TencentRequestInput): Promise<Record<string, unknown>>;
  readonly calls: number;
}

export function createRequester(options: RequesterOptions): Requester {
  const maxRequests = options.maxRequests ?? 20;
  const timeoutMs = options.timeoutMs ?? 20_000;
  let calls = 0;

  const resolve = (input: TencentRequestInput): ResolvedRequest => {
    const service = String(input.service ?? "").trim().toLowerCase();
    const action = String(input.action ?? "").trim();
    if (!service) throw new Error('request() 需要 service，例如 "cvm"');
    if (!action) throw new Error('request() 需要 action，例如 "DescribeInstances"');

    const version = input.version ?? resolveVersion(service);
    if (!version) {
      throw new Error(
        `无法确定 service="${service}" 的版本：catalog 里没有这个产品。` +
          `请显式传 version，例如 { service: "${service}", version: "2017-03-12", action: "${action}" }，` +
          `或在 src/catalog/services/ 下补充该产品的 catalog。`,
      );
    }

    const meta = catalog[service]?.actions[action];
    const requiresRegion = meta ? meta.requiresRegion !== false : true;
    const region = input.region ?? options.defaultRegion;
    if (!region && requiresRegion) {
      throw new Error(
        `${service}:${action} 需要 Region。请在 execute 参数里传 region（如 "ap-guangzhou"），` +
          `或设置服务端默认地域 TENCENT_MCP_DEFAULT_REGION。`,
      );
    }

    if (options.requireConfirm && meta?.dangerous && input.confirm !== true) {
      throw new Error(
        `安全闸：${service}:${action} 是写/删类高危操作，需要 confirm: true` +
          `（模型应先向用户确认，再带上 confirm: true 重试）。`,
      );
    }

    return {
      service,
      action,
      version,
      ...(region ? { region } : {}),
      params: (input.params ?? {}) as Record<string, unknown>,
    };
  };

  return {
    get calls() {
      return calls;
    },
    async request(input: TencentRequestInput) {
      if (calls >= maxRequests) {
        throw new Error(
          `单次 execute 最多发起 ${maxRequests} 次 API 请求（已打满）。请把多次调用合并到一段代码里只取需要的结果，` +
            `或调大 TENCENT_MCP_MAX_REQUESTS。`,
        );
      }
      const request = resolve(input);
      calls += 1;
      const started = Date.now();

      const result =
        options.engine === "sdk"
          ? await callSdk(request, options.credentials)
          : await callApi(request, options.credentials, { timeoutMs });

      if (options.engine === "api") {
        return { ...result, _engine: "api", _latencyMs: Date.now() - started };
      }
      return result;
    },
  };
}
