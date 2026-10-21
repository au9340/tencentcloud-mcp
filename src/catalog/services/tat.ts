import type { ServiceDoc } from "../types.js";

export const tat: ServiceDoc = {
  version: "2020-10-28",
  product: "自动化助手 TAT",
  docUrl: "https://cloud.tencent.com/document/api/1340",
  actions: {
    RunCommand: {
      summary: "在实例上批量执行 Shell/PowerShell 命令（异步，用 DescribeInvocationTasks 查结果）。",
      dangerous: true,
      params: {
        CommandType: "String，SHELL / POWERSHELL / BAT",
        Content: "String，base64 编码后的命令内容",
        InstanceIds: "Array of String，目标实例 ID",
        Timeout: "Integer，秒",
        WorkingDirectory: "String",
      },
    },
    DescribeCommands: { summary: "查询命令列表。", params: { CommandIds: "Array of String" } },
    DescribeInvocations: {
      summary: "查询执行活动（Invocation）列表。",
      params: { InvocationIds: "Array of String" },
    },
    DescribeInvocationTasks: {
      summary: "查询执行任务明细（含输出、退出码）。",
      params: {
        InvocationTaskIds: "Array of String",
        Filters: "Array of Filter，Name 可选 task-id / instance-id / invocation-id",
      },
    },
    DescribeRegions: { summary: "列出 TAT 支持的地域。", requiresRegion: false },
  },
};
