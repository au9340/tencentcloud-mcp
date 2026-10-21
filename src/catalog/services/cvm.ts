import type { ServiceDoc } from "../types.js";

export const cvm: ServiceDoc = {
  version: "2017-03-12",
  product: "云服务器 CVM",
  docUrl: "https://cloud.tencent.com/document/api/213",
  actions: {
    DescribeInstances: {
      summary: "查询实例列表（可按 ID / 过滤条件 / 标签分页拉取）。",
      params: {
        InstanceIds: "Array of String，实例 ID 列表，如 [\"ins-xxx\"]",
        Filters: "Array of Filter，Name 可选 instance-id / instance-name / zone / project-id",
        Limit: "Integer，返回数量，默认 20，最大 100",
        Offset: "Integer，偏移量",
      },
    },
    DescribeRegions: {
      summary: "列出 CVM 支持的地域。",
      requiresRegion: false,
    },
    DescribeZones: { summary: "列出某地域下的可用区。" },
    RunInstances: {
      summary: "创建一台或多台实例（按量计费需传入 ImageId、InstanceType、Placement）。",
      dangerous: true,
      params: {
        ImageId: "String，镜像 ID",
        InstanceType: "String，机型，如 S5.MEDIUM2",
        Placement: "Placement 对象，{ Zone: \"ap-guangzhou-3\" }",
        InstanceChargeType: "String，POSTPAID_BY_HOUR / PREPAID",
        InstanceCount: "Integer，数量",
      },
    },
    StartInstances: {
      summary: "开机。",
      dangerous: true,
      params: { InstanceIds: "Array of String，实例 ID 列表" },
    },
    StopInstances: {
      summary: "关机（StopType=SOFT 为软关机）。",
      dangerous: true,
      params: {
        InstanceIds: "Array of String，实例 ID 列表",
        StopType: "String，SOFT / HARD / SOFT_FIRST",
      },
    },
    RebootInstances: {
      summary: "重启实例。",
      dangerous: true,
      params: { InstanceIds: "Array of String，实例 ID 列表" },
    },
    TerminateInstances: {
      summary: "销毁实例（退还机器，不可逆）。",
      dangerous: true,
      params: { InstanceIds: "Array of String，实例 ID 列表" },
    },
    ModifyInstancesAttribute: {
      summary: "修改实例名称或安全组绑定。",
      params: { InstanceIds: "Array of String", InstanceName: "String，新名称" },
    },
  },
};
