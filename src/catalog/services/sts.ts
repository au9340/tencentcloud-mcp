import type { ServiceDoc } from "../types.js";

export const sts: ServiceDoc = {
  version: "2018-08-13",
  product: "临时密钥 STS",
  docUrl: "https://cloud.tencent.com/document/api/1312",
  actions: {
    GetCallerIdentity: {
      summary: "返回当前凭据的身份（AccountId / UserId / Arn），用于 whoami。",
      requiresRegion: false,
    },
    GetFederationToken: {
      summary: "获取临时访问凭证。",
      requiresRegion: false,
      params: { Name: "String，临时凭证名称", DurationSeconds: "Integer，默认 7200", Policy: "String，策略 JSON" },
    },
    AssumeRole: {
      summary: "扮演角色，获取角色临时凭证。",
      requiresRegion: false,
      params: {
        RoleArn: "String，角色 ARN",
        RoleSessionName: "String",
        DurationSeconds: "Integer，默认 7200",
      },
    },
  },
};
