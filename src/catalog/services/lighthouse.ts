import type { ServiceDoc } from "../types.js";

export const lighthouse: ServiceDoc = {
  version: "2020-03-24",
  product: "轻量应用服务器 Lighthouse",
  docUrl: "https://cloud.tencent.com/document/api/1207",
  actions: {
    DescribeInstances: {
      summary: "查询轻量实例列表。",
      params: {
        InstanceIds: "Array of String，如 [\"lhins-xxx\"]",
        Filters: "Array of Filter，Name 可选 instance-name / instance-id",
        Limit: "Integer",
        Offset: "Integer",
      },
    },
    DescribeRegions: { summary: "列出轻量服务器可用地域。", requiresRegion: false },
    DescribeBlueprints: { summary: "列出可用镜像（套餐/系统镜像）。" },
    DescribeBundles: { summary: "列出套餐（Bundle）列表。" },
    StartInstances: {
      summary: "开机。",
      dangerous: true,
      params: { InstanceIds: "Array of String" },
    },
    StopInstances: {
      summary: "关机。",
      dangerous: true,
      params: { InstanceIds: "Array of String" },
    },
    RebootInstances: {
      summary: "重启。",
      dangerous: true,
      params: { InstanceIds: "Array of String" },
    },
    TerminateInstances: {
      summary: "销毁轻量实例（不可逆）。",
      dangerous: true,
      params: { InstanceIds: "Array of String" },
    },
  },
};
