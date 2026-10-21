import { createHash, createHmac } from "node:crypto";

const ALGORITHM = "TC3-HMAC-SHA256";
const CONTENT_TYPE = "application/json; charset=utf-8";

function sha256Hex(input: string): string {
  return createHash("sha256").update(input, "utf8").digest("hex");
}

function hmac(key: string | Buffer, message: string): Buffer {
  return createHmac("sha256", key).update(message, "utf8").digest();
}

export interface SignOptions {
  secretId: string;
  secretKey: string;
  token?: string;
  /** 产品短名，同时用于签名 scope 与默认域名 */
  service: string;
  action: string;
  version: string;
  region?: string;
  /** JSON 字符串请求体（腾讯云 RPC 风格：参数平铺在 body 顶层） */
  payload: string;
  /** 秒级时间戳，默认 now，仅测试时传 */
  timestamp?: number;
  host?: string;
}

export interface SignedRequest {
  url: string;
  headers: Record<string, string>;
  payload: string;
}

/**
 * 腾讯云 API 3.0 签名（TC3-HMAC-SHA256），POST + JSON。
 * 文档：https://cloud.tencent.com/document/api/213/30654
 */
export function signTC3(options: SignOptions): SignedRequest {
  const timestamp = options.timestamp ?? Math.floor(Date.now() / 1000);
  const date = new Date(timestamp * 1000).toISOString().slice(0, 10);
  const host = options.host ?? `${options.service}.tencentcloudapi.com`;

  const canonicalHeaders =
    `content-type:${CONTENT_TYPE}\n` + `host:${host}\n` + `x-tc-action:${options.action.toLowerCase()}\n`;
  const signedHeaders = "content-type;host;x-tc-action";

  const canonicalRequest = [
    "POST",
    "/",
    "",
    canonicalHeaders,
    signedHeaders,
    sha256Hex(options.payload),
  ].join("\n");

  const credentialScope = `${date}/${options.service}/tc3_request`;
  const stringToSign = [
    ALGORITHM,
    String(timestamp),
    credentialScope,
    sha256Hex(canonicalRequest),
  ].join("\n");

  const secretDate = hmac(`TC3${options.secretKey}`, date);
  const secretService = hmac(secretDate, options.service);
  const secretSigning = hmac(secretService, "tc3_request");
  const signature = createHmac("sha256", secretSigning)
    .update(stringToSign, "utf8")
    .digest("hex");

  const headers: Record<string, string> = {
    Authorization:
      `${ALGORITHM} Credential=${options.secretId}/${credentialScope}, ` +
      `SignedHeaders=${signedHeaders}, Signature=${signature}`,
    "Content-Type": CONTENT_TYPE,
    Host: host,
    "X-TC-Action": options.action,
    "X-TC-Timestamp": String(timestamp),
    "X-TC-Version": options.version,
  };

  if (options.region) headers["X-TC-Region"] = options.region;
  if (options.token) headers["X-TC-Token"] = options.token;

  return { url: `https://${host}/`, headers, payload: options.payload };
}
