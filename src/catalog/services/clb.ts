import type { ServiceDoc } from "../types.js";

export const clb: ServiceDoc = {
  version: "2017-03-12",
  product: "负载均衡 CLB",
  docUrl: "https://cloud.tencent.com/document/api/214",
  actions: {
    DescribeLoadBalancers: {
      summary: "查询负载均衡实例列表。",
      params: {
        LoadBalancerIds: "Array of String，如 [\"lb-xxx\"]",
        Filters: "Array of Filter，Name 可选 loadbalancer-name / loadbalancer-id / vip",
        Limit: "Integer",
        Offset: "Integer",
      },
    },
    DescribeListeners: {
      summary: "查询监听器列表。",
      params: { LoadBalancerIds: "Array of String", Protocol: "String，HTTP / HTTPS / TCP / UDP" },
    },
    DescribeTargets: {
      summary: "查询监听器绑定的后端机器。",
      params: { LoadBalancerId: "String", ListenerIds: "Array of String" },
    },
    RegisterTargets: {
      summary: "绑定后端机器到监听器。",
      params: {
        LoadBalancerId: "String",
        ListenerId: "String",
        Targets: "Array of Target { InstanceId, Port, Weight }",
      },
    },
    DeregisterTargets: {
      summary: "解绑后端机器。",
      dangerous: true,
      params: {
        LoadBalancerId: "String",
        ListenerId: "String",
        Targets: "Array of Target { InstanceId, Port }",
      },
    },
    DeleteLoadBalancer: {
      summary: "删除负载均衡实例。",
      dangerous: true,
      params: { LoadBalancerIds: "Array of String" },
    },
  },
};
