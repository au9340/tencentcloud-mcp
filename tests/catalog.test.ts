import { describe, expect, it } from "vitest";
import { actionList, catalog, resolveVersion, searchActions } from "../src/catalog/index.js";

describe("catalog", () => {
  it("每个 Action 都有 summary，且带版本信息", () => {
    expect(actionList.length).toBeGreaterThan(30);
    for (const entry of actionList) {
      expect(entry.summary.length).toBeGreaterThan(0);
      expect(entry.version).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      expect(entry.docUrl.startsWith("https://cloud.tencent.com/")).toBe(true);
    }
  });

  it("resolveVersion 能从 service 推出 API 版本", () => {
    expect(resolveVersion("cvm")).toBe("2017-03-12");
    expect(resolveVersion("dnspod")).toBe("2021-03-23");
    expect(resolveVersion("unknown-service")).toBeUndefined();
  });

  it("sts/cam/dnspod 的 Action 不需要 region", () => {
    expect(catalog.sts?.actions.GetCallerIdentity?.requiresRegion).toBe(false);
    expect(catalog.cam?.actions.ListUsers?.requiresRegion).toBe(false);
    expect(catalog.dnspod?.actions.DescribeDomainList?.requiresRegion).toBe(false);
    expect(catalog.cvm?.actions.DescribeInstances?.requiresRegion).toBeUndefined();
  });

  it("searchActions 能按关键词命中", () => {
    const hits = searchActions("cvm 实例");
    expect(hits.length).toBeGreaterThan(0);
    expect(hits.some((entry) => entry.service === "cvm")).toBe(true);

    const dns = searchActions("dnspod 记录");
    expect(dns.some((entry) => entry.service === "dnspod")).toBe(true);
  });
});
