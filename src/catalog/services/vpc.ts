import type { ServiceDoc } from "../types.js";

export const vpc: ServiceDoc = {
  version: "2017-03-12",
  product: "私有网络 VPC",
  docUrl: "https://cloud.tencent.com/document/api/215",
  actions: {
    DescribeVpcs: {
      summary: "查询 VPC 列表。",
      params: {
        VpcIds: "Array of String，VPC ID 列表",
        Filters: "Array of Filter，Name 可选 vpc-name / is-default / tag:tag-key",
        Limit: "Integer，默认 10",
        Offset: "Integer",
      },
    },
    CreateVpc: {
      summary: "创建 VPC，需要 VpcName 与 CidrBlock。",
      params: { VpcName: "String", CidrBlock: "String，如 10.0.0.0/16" },
    },
    DeleteVpc: {
      summary: "删除 VPC（需先清空子网等资源）。",
      dangerous: true,
      params: { VpcId: "String" },
    },
    DescribeSubnets: {
      summary: "查询子网列表。",
      params: { VpcId: "String，可选，按 VPC 过滤", SubnetIds: "Array of String" },
    },
    DescribeSecurityGroups: {
      summary: "查询安全组及其规则。",
      params: {
        SecurityGroupIds: "Array of String，如 [\"sg-xxx\"]",
        Filters: "Array of Filter，Name 可选 security-group-name / project-id",
      },
    },
    DescribeSecurityGroupPolicies: {
      summary: "查询某个安全组的入站/出站规则明细。",
      params: { SecurityGroupId: "String" },
    },
    DescribeAddresses: {
      summary: "查询弹性公网 IP 列表。",
      params: { AddressIds: "Array of String", Filters: "Array of Filter" },
    },
    DescribeRouteTables: {
      summary: "查询路由表。",
      params: { RouteTableIds: "Array of String", Filters: "Array of Filter" },
    },
  },
};
