import type { ServiceDoc } from "../types.js";

export const cbs: ServiceDoc = {
  version: "2017-03-12",
  product: "云硬盘 CBS",
  docUrl: "https://cloud.tencent.com/document/api/362",
  actions: {
    DescribeDisks: {
      summary: "查询云硬盘列表（含挂载信息、类型、容量）。",
      params: {
        DiskIds: "Array of String，如 [\"disk-xxx\"]",
        Filters: "Array of Filter，Name 可选 disk-name / disk-usage / instance-id",
        Limit: "Integer",
        Offset: "Integer",
      },
    },
    DescribeDiskConfigQuota: {
      summary: "查询可创建的云盘类型与配额。",
      params: { DiskChargeType: "String，POSTPAID_BY_HOUR / PREPAID", DiskUsage: "String，SYSTEM_DISK / DATA_DISK" },
    },
    CreateDisks: {
      summary: "创建云硬盘（需 DiskSize、DiskType，可指定 Zone）。",
      params: {
        DiskSize: "Integer，GB",
        DiskType: "String，CLOUD_PREMIUM / CLOUD_SSD / CLOUD_BASIC",
        Placement: "Placement 对象 { Zone }",
        DiskCount: "Integer",
      },
    },
    AttachDisks: {
      summary: "挂载云盘到实例。",
      params: { DiskIds: "Array of String", InstanceId: "String" },
    },
    DetachDisks: {
      summary: "卸载云盘（不删数据）。",
      dangerous: true,
      params: { DiskIds: "Array of String", InstanceId: "String，可选" },
    },
    DeleteDisks: {
      summary: "销毁云盘（不可逆）。",
      dangerous: true,
      params: { DiskIds: "Array of String" },
    },
  },
};
