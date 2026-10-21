import { describe, expect, it } from "vitest";
import { runUserCode } from "../src/core/sandbox.js";
import { truncateText } from "../src/core/truncate.js";

describe("Code Mode 沙箱", () => {
  it("可以 await 注入的能力并 return 结果", async () => {
    const result = await runUserCode(
      `const a = await tencent.request({ service: "cvm", action: "DescribeInstances" });\nreturn { count: a.total, region };`,
      {
        region: "ap-guangzhou",
        tencent: { request: async () => ({ total: 2 }) },
      },
    );
    expect(result).toEqual({ count: 2, region: "ap-guangzhou" });
  });

  it("拿不到 require / process", async () => {
    await expect(runUserCode('return typeof require', {})).resolves.toBe("undefined");
    await expect(runUserCode('return typeof process', {})).resolves.toBe("undefined");
  });

  it("代码抛错时带上原始信息", async () => {
    await expect(runUserCode('throw new Error("boom")', {})).rejects.toThrow(/boom/);
  });
});

describe("truncateText", () => {
  it("超过上限时截断并标记", () => {
    const text = "a".repeat(10);
    expect(truncateText(text, { maxTokens: 1 })).toContain("TRUNCATED");
    expect(truncateText(text, { maxTokens: 100 })).toBe(text);
    expect(truncateText(text, { enabled: false, maxTokens: 1 })).toBe(text);
  });
});
