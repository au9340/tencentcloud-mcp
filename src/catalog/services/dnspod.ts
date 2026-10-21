import type { ServiceDoc } from "../types.js";

export const dnspod: ServiceDoc = {
  version: "2021-03-23",
  product: "DNSPod 域名解析",
  docUrl: "https://cloud.tencent.com/document/api/1427",
  actions: {
    DescribeDomainList: {
      summary: "列出账号下的域名。",
      requiresRegion: false,
      params: { Type: "String，ALL / MY / SHARE / ISMARK", Offset: "Integer", Limit: "Integer" },
    },
    DescribeRecordList: {
      summary: "查询某个域名的解析记录。",
      requiresRegion: false,
      params: {
        Domain: "String，如 example.com",
        Subdomain: "String，主机记录，如 www",
        RecordType: "String，A / AAAA / CNAME / TXT / MX / NS",
        Limit: "Integer，默认 100",
        Offset: "Integer",
      },
    },
    CreateRecord: {
      summary: "新增解析记录。",
      requiresRegion: false,
      params: {
        Domain: "String",
        SubDomain: "String，主机记录，@ 表示根域名",
        RecordType: "String",
        RecordLine: "String，线路，如 默认",
        Value: "String，记录值",
        TTL: "Integer，默认 600",
      },
    },
    ModifyRecord: {
      summary: "修改解析记录。",
      requiresRegion: false,
      params: {
        Domain: "String",
        RecordId: "Integer",
        SubDomain: "String",
        RecordType: "String",
        RecordLine: "String",
        Value: "String",
      },
    },
    DeleteRecord: {
      summary: "删除解析记录。",
      dangerous: true,
      requiresRegion: false,
      params: { Domain: "String", RecordId: "Integer" },
    },
  },
};
