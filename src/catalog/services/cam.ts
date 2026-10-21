import type { ServiceDoc } from "../types.js";

export const cam: ServiceDoc = {
  version: "2019-01-16",
  product: "访问管理 CAM",
  docUrl: "https://cloud.tencent.com/document/api/598",
  actions: {
    GetUserAppId: {
      summary: "获取当前身份的主账号 Uin / AppId / OwnerUin。",
      requiresRegion: false,
    },
    ListUsers: {
      summary: "列出子用户。",
      requiresRegion: false,
      params: { Limit: "Integer", Offset: "Integer" },
    },
    ListGroups: { summary: "列出用户组。", requiresRegion: false },
    ListRoles: { summary: "列出角色。", requiresRegion: false },
    ListPolicies: {
      summary: "列出策略（Scope=Local 自定义 / QCS 预设）。",
      requiresRegion: false,
      params: { Scope: "String，All / QCS / Local", Keyword: "String" },
    },
    ListAttachedUserPolicies: {
      summary: "列出某个子用户绑定的策略。",
      requiresRegion: false,
      params: { TargetUin: "Integer，子用户 Uin" },
    },
  },
};
