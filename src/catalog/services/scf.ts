import type { ServiceDoc } from "../types.js";

export const scf: ServiceDoc = {
  version: "2018-04-16",
  product: "云函数 SCF",
  docUrl: "https://cloud.tencent.com/document/api/583",
  actions: {
    ListFunctions: {
      summary: "列出函数。",
      params: { Namespace: "String，命名空间，默认 default", Limit: "Integer", Offset: "Integer" },
    },
    GetFunction: {
      summary: "获取函数详情（配置、代码地址等）。",
      params: { FunctionName: "String", Namespace: "String" },
    },
    Invoke: {
      summary: "同步/异步调用函数。",
      dangerous: true,
      params: {
        FunctionName: "String",
        InvocationType: "String，RequestResponse（同步）/ Event（异步）",
        ClientContext: "String，传给函数的 JSON 字符串（base64 后）",
        Qualifier: "String，版本或别名",
      },
    },
    ListNamespaces: { summary: "列出命名空间。" },
    GetFunctionLogs: {
      summary: "查询函数调用日志。",
      params: { FunctionName: "String", Limit: "Integer", StartTime: "String，如 2026-10-21 00:00:00" },
    },
    ListTriggers: {
      summary: "列出函数的触发器。",
      params: { FunctionName: "String", Namespace: "String" },
    },
  },
};
