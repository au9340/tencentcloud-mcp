export interface Credentials {
  secretId: string;
  secretKey: string;
  /** 临时凭据（STS）时的 token */
  token?: string;
}

/** api = 自签 TC3 直连 API；sdk = 官方 Node SDK */
export type Engine = "api" | "sdk";

/** 代码沙箱里 tencent.request() 的入参 */
export interface TencentRequestInput {
  /** 产品短名，即 API 域名的子域：cvm / vpc / cbs / lighthouse / scf / tat / cam / sts / dnspod / clb */
  service: string;
  /** 大驼峰 Action 名，例如 DescribeInstances */
  action: string;
  /** 版本，省略时从 catalog 推导 */
  version?: string;
  /** 地域，例如 ap-guangzhou；省略时用 region 参数或服务端默认值 */
  region?: string;
  params?: Record<string, unknown>;
  /** 高危 Action 需要显式确认（TENCENT_MCP_REQUIRE_CONFIRM=true 时生效） */
  confirm?: boolean;
}

export interface ResolvedRequest {
  service: string;
  action: string;
  version: string;
  region?: string;
  params: Record<string, unknown>;
}
